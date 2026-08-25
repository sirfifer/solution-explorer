"""Stage 3: baseline vs redesigned prompts and outputs, measured on the real store.

Everything here is offline: no model calls. Token counts are tiktoken o200k_base
scaled by the stage-1 fitted slope (1.5829, fitted on 35 real first-turn prompts
against billed prompt-side tokens, max residual 1.95%).
"""
import json
import sys
import hashlib
from pathlib import Path

sys.path.insert(0, "/Volumes/Studio/dev/solution-explorer")
import tiktoken

from analyzer.enrich.partition import plan_partitions
from analyzer.enrich.prompts import StoreFacts, build_contract_partition_prompt, ROLE_VOCABULARY
from analyzer.enrich.contract import _is_substitution_failure

ENC = tiktoken.get_encoding("o200k_base")
SCALE = 1.5829164598680414
HERE = Path(__file__).parent


def tok(s):
    return len(ENC.encode(s, disallowed_special=()))


def jtok(obj):
    return tok(json.dumps(obj, ensure_ascii=False))


def scaled(n):
    return n * SCALE


# --- load inputs --------------------------------------------------------------
arch = json.load(open(HERE / "data/arch.json"))
sf_in = json.load(open(HERE / "data/storefacts-inputs.json"))
facts = StoreFacts(
    arch, sf_in["capabilities"], sf_in["data_entities"], sf_in["rules"],
    arch.get("relationships", []),
)
brief_raw = json.load(open(
    "/Volumes/Studio/dev/solution-explorer/demos/runs/vscode/2026-08-25/enrichment/subject-brief.json"
))
brief = {
    "identity": brief_raw.get("identity"),
    "audience": brief_raw.get("audience"),
    "what_matters": brief_raw.get("what_matters") or [],
    "idiom_warnings": brief_raw.get("idiom_warnings") or [],
    "weighting_adjustments": brief_raw.get("weighting_adjustments") or [],
}

plan = plan_partitions(arch.get("components", []), arch.get("relationships", []))
parts = list(plan.partitions)

blocks = json.load(open(HERE / "stage1_blocks.json"))
comp_blocks = blocks["components"]
rel_blocks = blocks["relationships"]

results = {}

# --- 1. baseline input: current prompt over all 173 partitions ----------------
baseline_prompts = {}
for p in parts:
    baseline_prompts[p.id] = build_contract_partition_prompt(p, facts, brief=brief)
base_counts = {pid: tok(t) for pid, t in baseline_prompts.items()}
total_base_in = sum(base_counts.values())
results["baseline_input"] = {
    "partitions": len(parts),
    "total_o200k": total_base_in,
    "total_scaled": round(scaled(total_base_in)),
    "mean_scaled_per_call": round(scaled(total_base_in) / len(parts)),
    "min_scaled": round(scaled(min(base_counts.values()))),
    "max_scaled": round(scaled(max(base_counts.values()))),
}

# shared prefix of the current prompt (everything before the COMPONENTS payload)
sample = baseline_prompts[parts[0].id]
marker = "COMPONENTS (produce an ai_enhance WITH a contract"
prefix_len = sample.find(marker)
results["baseline_shared_prefix_scaled"] = round(scaled(tok(sample[:prefix_len])))

# --- 2. transform real killed-run blocks into the new schema ------------------

def evidence_menu(cid):
    f = facts.component_facts(cid)
    return f.get("files") or []


def map_citation_component(cid, item, menu):
    """Old evidence object -> new compact form. Returns (new_item, kind)."""
    if not isinstance(item, dict):
        return None, "dropped"
    kind = str(item.get("kind") or "").lower()
    path = item.get("path")
    line = item.get("line")
    symbol = item.get("symbol")
    if kind == "edge":
        out = {"kind": "edge", "source": item.get("source"), "target": item.get("target")}
        return out, "edge-object"
    if path in menu:
        i = menu.index(path)
        if symbol:
            return [i, symbol], "index-symbol"
        if line is not None:
            try:
                return [i, int(line)], "index-line"
            except (TypeError, ValueError):
                return i, "index"
        return i, "index"
    # escape hatch: full object (path outside the menu)
    out = {"kind": kind or "file", "path": path}
    if line is not None:
        out["line"] = line
    if symbol:
        out["symbol"] = symbol
    return out, "escape-object"


def transform_component(cid, block):
    stats = {"index": 0, "index-symbol": 0, "index-line": 0, "edge-object": 0,
             "escape-object": 0, "dropped": 0}
    menu = evidence_menu(cid)
    product = {k: v for k, v in block.items() if k != "contract"}
    product = {k: v for k, v in product.items()
               if v is not None and v != [] and v != "" and v != {}}
    contract = block.get("contract") or {}
    answers = contract.get("answers") or {}
    q = {}
    for name, ans in answers.items():
        if name.startswith("identity."):
            continue  # identity: silence is agreement; disagreement uses "id"
        if not isinstance(ans, dict):
            ans = {"claim": str(ans), "status": "answered", "evidence": []}
        status = str(ans.get("status") or "answered")
        claim = (ans.get("claim") or "").strip()
        entry = {}
        if claim:
            entry["t"] = claim
        if status == "answered":
            ev = []
            for item in (ans.get("evidence") or [])[:2]:
                new, kind = map_citation_component(cid, item, menu)
                stats[kind] += 1
                if new is not None:
                    ev.append(new)
            if ev:
                entry["e"] = ev
        else:
            entry["s"] = status[0]  # "u" | "d"
            if ans.get("reason"):
                entry["r"] = str(ans["reason"]).strip()
        q[name] = entry
    new = dict(product)
    new["q"] = q
    pf = [x for x in (contract.get("parser_first") or []) if str(x).strip()]
    if pf:
        new["pf"] = pf
    confusion = contract.get("confusion")
    if confusion:
        new["confusion"] = str(confusion)
    sub = contract.get("substitution_check")
    if isinstance(sub, str) and _is_substitution_failure(sub):
        new["generic"] = True
    return new, stats


def transform_relationship(key, block):
    stats = {"e_omitted": 0, "e_kept": 0}
    rf = facts.relationship_facts(key)
    menu = rf.get("evidence") or []
    menu_sigs = set()
    for m in menu:
        if isinstance(m, dict):
            menu_sigs.add(str(m.get("file") or m.get("path") or ""))
    product = {k: v for k, v in block.items() if k != "contract"}
    contract = block.get("contract") or {}
    answers = contract.get("answers") or {}
    new = {}
    if product.get("data_flow_description"):
        new["d"] = product["data_flow_description"]
    if product.get("importance"):
        new["imp"] = product["importance"]
    for name in ("flow", "why"):
        ans = answers.get(name)
        if not isinstance(ans, dict):
            if ans:
                new[name] = str(ans)
            continue
        status = str(ans.get("status") or "answered")
        claim = (ans.get("claim") or "").strip()
        if status == "answered":
            # default: grounded in the edge's own evidence; citation omitted.
            # keep an explicit citation only when it names a file outside the
            # relationship's own evidence list and outside the edge itself.
            kept = []
            for item in (ans.get("evidence") or []):
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("kind") or "").lower()
                if kind == "edge":
                    continue  # restates the edge the prompt names
                path = str(item.get("path") or "")
                if path and path in menu_sigs:
                    continue  # restates the prompt's own evidence
                # outside the menu: check whether the SOURCE component's files
                # carry it (still transcription of prompt context) else keep
                src = rf.get("source") or ""
                if path and path in (facts.component_facts(src).get("files") or []):
                    continue
                kept.append(item)
            if kept:
                stats["e_kept"] += 1
                new[name] = {"t": claim, "e": kept[:1]}
            else:
                stats["e_omitted"] += 1
                new[name] = claim
        else:
            new[name] = {"t": claim, "s": status[0],
                         **({"r": str(ans["reason"]).strip()} if ans.get("reason") else {})}
    confusion = contract.get("confusion")
    if confusion:
        new["confusion"] = str(confusion)
    return new, stats


# run transformation over every real block
comp_new = {}
comp_cite_stats = {"index": 0, "index-symbol": 0, "index-line": 0,
                   "edge-object": 0, "escape-object": 0, "dropped": 0}
old_comp_sizes, new_comp_sizes = [], []
for cid, block in comp_blocks.items():
    new, st = transform_component(cid, block)
    comp_new[cid] = new
    for k, v in st.items():
        comp_cite_stats[k] += v
    old_comp_sizes.append(jtok(block))
    new_comp_sizes.append(jtok(new))

rel_new = {}
rel_cite_stats = {"e_omitted": 0, "e_kept": 0}
old_rel_sizes, new_rel_sizes = [], []
for key, block in rel_blocks.items():
    new, st = transform_relationship(key, block)
    rel_new[key] = new
    for k, v in st.items():
        rel_cite_stats[k] += v
    old_rel_sizes.append(jtok(block))
    new_rel_sizes.append(jtok(new))


def mean(xs):
    return sum(xs) / len(xs) if xs else 0.0

results["block_transform"] = {
    "n_components": len(comp_blocks),
    "n_relationships": len(rel_blocks),
    "component_old_mean_scaled": round(scaled(mean(old_comp_sizes))),
    "component_new_mean_scaled": round(scaled(mean(new_comp_sizes))),
    "component_reduction": 1 - mean(new_comp_sizes) / mean(old_comp_sizes),
    "relationship_old_mean_scaled": round(scaled(mean(old_rel_sizes))),
    "relationship_new_mean_scaled": round(scaled(mean(new_rel_sizes))),
    "relationship_reduction": 1 - mean(new_rel_sizes) / mean(old_rel_sizes),
    "component_citations": comp_cite_stats,
    "relationship_citations": rel_cite_stats,
}

# distribution facts used by the defaults design
n_pf = sum(1 for b in comp_blocks.values()
           if (b.get("contract") or {}).get("parser_first"))
n_conf = sum(1 for b in comp_blocks.values()
             if (b.get("contract") or {}).get("confusion"))
n_esc = sum(1 for b in comp_blocks.values()
            if (b.get("contract") or {}).get("self_state") == "escalate")
results["component_marker_rates"] = {
    "parser_first_nonempty": n_pf / max(1, len(comp_blocks)),
    "confusion_nonnull": n_conf / max(1, len(comp_blocks)),
    "self_state_escalate": n_esc / max(1, len(comp_blocks)),
}

# --- 3. new call plan and new input prompts -----------------------------------
# component groups (the 55 distinct groups; the partitioner's chunking repeated
# them 3.52x, the new plan runs each group once)
groups = {}
for p in parts:
    groups.setdefault(p.component_ids, set()).update(p.relationship_keys)
group_list = sorted(groups.items(), key=lambda kv: kv[0][0])

# output-budget rule: projected output <= 45% of the 64k ceiling at low effort
CEILING = 64000
BUDGET = int(CEILING * 0.45)          # 28,800
FIXED_LOW = 1500                      # thinking upper bound at low (n=4 replays)
COMP_OUT = scaled(mean(new_comp_sizes))
REL_OUT = scaled(mean(new_rel_sizes))
comp_cap = int((BUDGET - FIXED_LOW) / COMP_OUT)
rel_cap = int((BUDGET - FIXED_LOW) / REL_OUT)
results["caps"] = {"component_call_cap": comp_cap, "relationship_call_cap": rel_cap,
                   "comp_out_each": round(COMP_OUT), "rel_out_each": round(REL_OUT)}

SHARED_2A_C = open(HERE / "prefix_2a_component.txt").read() if (HERE / "prefix_2a_component.txt").exists() else ""
SHARED_2A_R = open(HERE / "prefix_2a_relationship.txt").read() if (HERE / "prefix_2a_relationship.txt").exists() else ""


def build_2a_c_user(comp_ids):
    payload = [facts.component_facts(cid) for cid in comp_ids]
    return (
        "COMPONENTS (one response entry per id; each \"files\" list is that "
        "component's citation menu):\n"
        + json.dumps(payload, indent=2, default=str)
        + "\nReturn the JSON object now."
    )


def reduced_context(cid):
    f = facts.component_facts(cid)
    out = {"id": f.get("id"), "name": f.get("name"), "type": f.get("type"),
           "path": f.get("path"), "language": f.get("language"),
           "framework": f.get("framework")}
    if f.get("existing_description"):
        out["description"] = f["existing_description"]
    return {k: v for k, v in out.items() if v}


def build_2a_r_user(comp_ids, rel_keys):
    ctx_ids = set()
    for k in rel_keys:
        s, t, _ = (k.split("|") + ["", ""])[:3]
        ctx_ids.add(s)
        ctx_ids.add(t)
    ctx = [reduced_context(c) for c in sorted(ctx_ids) if c]
    rels = [facts.relationship_facts(k) for k in rel_keys]
    return (
        "CONTEXT (the components these edges connect):\n"
        + json.dumps(ctx, indent=2, default=str)
        + "\n\nRELATIONSHIPS (one response entry per key):\n"
        + json.dumps(rels, indent=2, default=str)
        + "\nReturn the JSON object now."
    )


# component calls
comp_calls = []
for comp_ids, _ in group_list:
    ids = list(comp_ids)
    for start in range(0, len(ids), comp_cap):
        chunk = ids[start:start + comp_cap]
        comp_calls.append(chunk)

# relationship calls
rel_calls = []
for comp_ids, rel_keys in group_list:
    keys = sorted(rel_keys)
    for start in range(0, len(keys), rel_cap):
        rel_calls.append((list(comp_ids), keys[start:start + rel_cap]))

comp_call_in = [tok(build_2a_c_user(c)) for c in comp_calls]
rel_call_in = [tok(build_2a_r_user(c, k)) for c, k in rel_calls]

new_out_comp_total = sum(len(c) for c in comp_calls) * COMP_OUT \
    + len(comp_calls) * FIXED_LOW
new_out_rel_total = sum(len(k) for _, k in rel_calls) * REL_OUT \
    + len(rel_calls) * FIXED_LOW

results["new_plan"] = {
    "component_calls": len(comp_calls),
    "relationship_calls": len(rel_calls),
    "total_calls": len(comp_calls) + len(rel_calls),
    "component_slots": sum(len(c) for c in comp_calls),
    "relationship_slots": sum(len(k) for _, k in rel_calls),
    "input_user_scaled_total": round(scaled(sum(comp_call_in) + sum(rel_call_in))),
    "input_user_scaled_mean_comp_call": round(scaled(mean(comp_call_in))),
    "input_user_scaled_mean_rel_call": round(scaled(mean(rel_call_in))),
    "output_scaled_total_including_thinking": round(new_out_comp_total + new_out_rel_total),
    "output_scaled_comp": round(new_out_comp_total),
    "output_scaled_rel": round(new_out_rel_total),
}

# baseline output at the killed run's own shape (for reference):
# postmortem block means x slots (source: efficiency postmortem)
results["baseline_output_reference"] = {
    "note": "efficiency postmortem: 1,770/component-block, 437/relationship, "
            "2,003 comp slots, 5,453 rel slots, xhigh fixed 29,244/call, "
            "per-comp reasoning 2,071 (3,221-1,150), delivered fixed 5,177/call",
}

# --- 4. worked example --------------------------------------------------------
# choose the group with the most components covered by real killed-run blocks
best = None
for comp_ids, rel_keys in group_list:
    covered = [c for c in comp_ids if c in comp_new]
    if covered and (best is None or len(covered) > len(best[2])):
        best = (comp_ids, rel_keys, covered)
wx_ids, wx_rels, wx_cov = best
results["worked_example"] = {
    "group_first_component": wx_ids[0],
    "group_size": len(wx_ids),
    "covered_by_real_blocks": len(wx_cov),
    "components": list(wx_ids),
}

# the worked example is the 2a-C call for this group (or its first chunk)
wx_chunk = list(wx_ids)[:comp_cap]
wx_user = build_2a_c_user(wx_chunk)
wx_out = {"components": []}
for cid in wx_chunk:
    if cid in comp_new:
        entry = dict(comp_new[cid])
        entry_out = {"i": cid}
        entry_out.update(entry)
        wx_out["components"].append(entry_out)
results["worked_example"].update({
    "user_message_o200k": tok(wx_user),
    "user_message_scaled": round(scaled(tok(wx_user))),
    "output_scaled_for_covered": round(scaled(jtok(wx_out))),
    "n_output_entries": len(wx_out["components"]),
})
open(HERE / "data/worked-example-user.txt", "w").write(wx_user)
json.dump(wx_out, open(HERE / "data/worked-example-output.json", "w"),
          indent=1, ensure_ascii=False)

# also dump one full old vs new block pair for the spec
pair_id = wx_cov[0]
json.dump({"old": comp_blocks[pair_id], "new": comp_new[pair_id]},
          open(HERE / "data/example-block-pair.json", "w"), indent=1,
          ensure_ascii=False)

# a relationship pair too
rk = next(iter(rel_new))
json.dump({"old": rel_blocks[rk], "new": rel_new[rk], "key": rk},
          open(HERE / "data/example-rel-pair.json", "w"), indent=1,
          ensure_ascii=False)

json.dump(results, open(HERE / "stage3_results.json", "w"), indent=2)
print(json.dumps(results, indent=2)[:6000])
