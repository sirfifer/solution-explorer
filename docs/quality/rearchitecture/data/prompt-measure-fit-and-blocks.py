"""Stage 1: fit the tokenizer scale against the killed run's billed input, and
measure delivered JSON block composition on the real responses.

Fitting basis (stated in the spec): for every 2a session in the 2026-08-25 run
window whose first turn's usage is available, billed prompt-side tokens
(input_tokens + cache_creation_input_tokens + cache_read_input_tokens) are
regressed on the tiktoken o200k_base count of the exact first user message.
The slope is the o200k -> Claude scale; the intercept is the CLI's fixed
prompt-side overhead (system prompt etc.), which the fit separates out.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/Volumes/Studio/dev/solution-explorer")
import tiktoken

ENC = tiktoken.get_encoding("o200k_base")
TDIR = Path.home() / ".claude/projects/-Volumes-Studio-dev-solution-explorer"
OUT = Path(__file__).parent / "stage1_results.json"

import datetime

def run_window_files():
    lo = datetime.datetime(2026, 8, 25, 8, 0).timestamp()
    hi = datetime.datetime(2026, 8, 25, 10, 30).timestamp()
    out = []
    for p in TDIR.glob("*.jsonl"):
        m = p.stat().st_mtime
        if lo <= m <= hi:
            out.append(p)
    return sorted(out)


def parse_session(path):
    """Return dict with prompt text, per-turn usage, concatenated assistant text."""
    prompt = None
    usages = []       # one per unique assistant message id
    seen_ids = set()
    texts = []        # text blocks in order
    for line in open(path):
        try:
            ev = json.loads(line)
        except Exception:
            continue
        t = ev.get("type")
        if t == "user" and prompt is None:
            c = ev.get("message", {}).get("content")
            if isinstance(c, str):
                prompt = c
            elif isinstance(c, list):
                prompt = "".join(b.get("text", "") for b in c if isinstance(b, dict))
        elif t == "assistant":
            m = ev.get("message", {})
            mid = m.get("id")
            u = m.get("usage")
            if mid and mid not in seen_ids and u:
                seen_ids.add(mid)
                usages.append(u)
            for b in m.get("content") or []:
                if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
                    texts.append((mid, b["text"]))
    # Concatenate one text per assistant message id, in order.
    by_id = {}
    order = []
    for mid, text in texts:
        if mid not in by_id:
            by_id[mid] = ""
            order.append(mid)
        by_id[mid] += text
    full_text = "".join(by_id[mid] for mid in order)
    return {"prompt": prompt, "usages": usages, "text": full_text,
            "turns": len(usages), "session": path.stem}


def salvage_json(text):
    """The postmortem's salvage: strip fences anywhere, take brace span."""
    t = re.sub(r"```(?:json)?", "", text)
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end <= start:
        return None
    t = t[start : end + 1]
    try:
        return json.loads(t)
    except Exception:
        return None


def tok(s):
    return len(ENC.encode(s, disallowed_special=()))


def block_tokens(obj):
    """Token count of a JSON value serialized the way the model emits it."""
    return tok(json.dumps(obj, ensure_ascii=False))


def main():
    files = run_window_files()
    files = [f for f in files if f.is_file()]
    sessions = []
    for f in files:
        s = parse_session(f)
        if s["prompt"] and s["prompt"].startswith("You are enhancing"):
            sessions.append(s)
    print(f"2a sessions found: {len(sessions)}")

    # --- tokenizer fit -------------------------------------------------------
    pts = []
    for s in sessions:
        if not s["usages"]:
            continue
        u = s["usages"][0]
        billed = (
            int(u.get("input_tokens") or 0)
            + int(u.get("cache_creation_input_tokens") or 0)
            + int(u.get("cache_read_input_tokens") or 0)
        )
        n = tok(s["prompt"])
        pts.append((n, billed, s["session"],
                    int(u.get("cache_read_input_tokens") or 0)))
    # least squares y = a x + b
    import statistics
    N = len(pts)
    sx = sum(p[0] for p in pts); sy = sum(p[1] for p in pts)
    sxx = sum(p[0] * p[0] for p in pts); sxy = sum(p[0] * p[1] for p in pts)
    a = (N * sxy - sx * sy) / (N * sxx - sx * sx)
    b = (sy - a * sx) / N
    resid = [p[1] - (a * p[0] + b) for p in pts]
    max_rel_err = max(abs(r) / p[1] for r, p in zip(resid, pts))
    cache_reads = [p[3] for p in pts]
    fit = {
        "points": N,
        "slope": a,
        "intercept": b,
        "max_rel_err": max_rel_err,
        "cache_read_min": min(cache_reads),
        "cache_read_max": max(cache_reads),
    }
    print("fit:", json.dumps(fit, indent=2))

    # --- delivered block measurements ---------------------------------------
    comp_blocks = {}   # id -> block (last wins, matching absorb semantics)
    rel_blocks = {}
    parsed_sessions = 0
    for s in sessions:
        obj = salvage_json(s["text"]) if s["text"] else None
        if obj is None:
            continue
        parsed_sessions += 1
        for cid, block in (obj.get("components") or {}).items():
            if isinstance(block, dict):
                comp_blocks[cid] = block
        for key, block in (obj.get("relationships") or {}).items():
            if isinstance(block, dict):
                rel_blocks[key] = block
    print(f"parsed sessions: {parsed_sessions}, "
          f"components: {len(comp_blocks)}, relationships: {len(rel_blocks)}")

    def analyze_component(block):
        contract = block.get("contract") or {}
        product = {k: v for k, v in block.items() if k != "contract"}
        answers = contract.get("answers") or {}
        ev_tokens = 0
        for q, ans in answers.items():
            if isinstance(ans, dict):
                ev = ans.get("evidence")
                if isinstance(ev, list):
                    ev_tokens += block_tokens(ev)
        return {
            "total": block_tokens(block),
            "product": block_tokens(product),
            "contract": block_tokens(contract),
            "evidence": ev_tokens,
            "n_answers": len(answers),
        }

    comp_stats = [analyze_component(b) for b in comp_blocks.values()]
    rel_stats = [analyze_component(b) for b in rel_blocks.values()]

    def summarize(stats):
        if not stats:
            return {}
        keys = ["total", "product", "contract", "evidence", "n_answers"]
        return {k: sum(s[k] for s in stats) / len(stats) for k in keys}

    comp_summary = summarize(comp_stats)
    rel_summary = summarize(rel_stats)
    print("component mean (o200k raw):", json.dumps(comp_summary, indent=2))
    print("relationship mean (o200k raw):", json.dumps(rel_summary, indent=2))

    # scaled to claude tokens
    print("component mean total scaled:", comp_summary["total"] * a)
    print("relationship mean total scaled:", rel_summary["total"] * a)

    json.dump(
        {
            "fit": fit,
            "n_components": len(comp_blocks),
            "n_relationships": len(rel_blocks),
            "component_mean_o200k": comp_summary,
            "relationship_mean_o200k": rel_summary,
            "sessions": [
                {"session": s["session"], "turns": s["turns"],
                 "prompt_chars": len(s["prompt"]),
                 "usage_first": s["usages"][0] if s["usages"] else None}
                for s in sessions
            ],
        },
        open(OUT, "w"), indent=2, default=str,
    )
    # persist raw blocks for stage 3 (schema transformation)
    json.dump({"components": comp_blocks, "relationships": rel_blocks},
              open(Path(__file__).parent / "stage1_blocks.json", "w"),
              ensure_ascii=False)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
