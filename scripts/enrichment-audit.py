#!/usr/bin/env python3
"""Audit one enrichment run against what it was supposed to cost and do.

Written to be adversarial. Every number here is read from the run's own
artifacts, and every check is one the 2026-08-25 VS Code disaster would have
failed. A run that passes this has earned the claim that it worked; a run that
merely finished has not.

    scripts/enrichment-audit.py <run-dir> [--json]

Checks, in the order they mattered that day:

  effort        every call pinned, none inherited
  ceiling       no response near the output limit, none truncated
  turns         one turn per call; more means the transport ran an agent loop
  waste         output paid for and then discarded
  duplication   targets answered more than once
  escalation    how much work climbed, and what that cost
  economics     spend per target, per rung, and where the tokens actually went
  coverage      every planned target answered, escalated, or explicitly open
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

OUTPUT_CEILING = 64_000
WARN_SHARE = 0.85


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def audit(run_dir: Path) -> dict:
    ledger = _rows(run_dir / "ledger.jsonl")
    events = _rows(run_dir / "progress.jsonl")
    failures = sorted((run_dir / "failures").glob("*.txt")) if (run_dir / "failures").is_dir() else []

    calls = [r for r in ledger if r.get("tokens_out") or r.get("cost_usd")]
    spend = sum(float(r.get("cost_usd") or 0) for r in ledger)
    out_tokens = sum(int(r.get("tokens_out") or 0) for r in ledger)
    fresh_in = sum(int(r.get("tokens_fresh_in") or 0) for r in ledger)
    cache_write = sum(int(r.get("tokens_cache_write") or 0) for r in ledger)
    cache_read = sum(int(r.get("tokens_cached") or 0) for r in ledger)

    findings: list[dict] = []

    def finding(level: str, check: str, detail: str) -> None:
        findings.append({"level": level, "check": check, "detail": detail})

    # --- effort ---------------------------------------------------------------
    efforts = defaultdict(int)
    for r in ledger:
        efforts[r.get("effort") or "UNSET"] += 1
    if efforts.get("UNSET"):
        finding("fail", "effort", f"{efforts['UNSET']} call(s) recorded no effort: it was inherited, not pinned")
    hot = {e: n for e, n in efforts.items() if e in ("high", "xhigh")}
    if hot:
        finding("warn", "effort", f"calls at elevated effort: {hot}; measured 4.5x output vs low")

    # --- ceiling --------------------------------------------------------------
    truncated = [r for r in ledger if (r.get("stop_reason") or "") == "max_tokens"]
    near = [r for r in ledger if int(r.get("tokens_out") or 0) >= WARN_SHARE * OUTPUT_CEILING]
    if truncated:
        finding("fail", "ceiling", f"{len(truncated)} response(s) truncated at the output ceiling")
    if near:
        worst = max(int(r.get("tokens_out") or 0) for r in near)
        finding("warn", "ceiling", f"{len(near)} response(s) within {int(WARN_SHARE*100)}% of the ceiling (worst {worst:,})")

    # --- turns ----------------------------------------------------------------
    multi = [r for r in ledger if int(r.get("num_turns") or 1) > 1]
    if multi:
        finding("fail", "turns", f"{len(multi)} call(s) used more than one turn: the transport is not pinned to pure inference")

    # --- waste ----------------------------------------------------------------
    failed = [r for r in ledger if not r.get("ok")]
    wasted = sum(float(r.get("cost_usd") or 0) for r in failed)
    if failures:
        finding("warn", "waste", f"{len(failures)} unparseable response(s) preserved under failures/")
    if wasted > 0:
        finding(
            "warn" if wasted < 0.1 * max(spend, 1e-9) else "fail",
            "waste",
            f"${wasted:.2f} of ${spend:.2f} ({wasted/max(spend,1e-9):.1%}) spent on calls that returned nothing usable",
        )

    # --- duplication ----------------------------------------------------------
    planned_targets = sum(int(e.get("targets") or 0) for e in events if e.get("event") == "plan")
    answered = sum(int(e.get("answered") or 0) for e in events if e.get("event") == "unit_end")
    units_done = sum(1 for e in events if e.get("event") == "unit_end")
    if planned_targets and answered > planned_targets * 1.05:
        finding("fail", "duplication", f"{answered:,} answers for {planned_targets:,} planned targets ({answered/planned_targets:.2f}x)")

    # --- escalation -----------------------------------------------------------
    by_rung: dict[str, dict] = defaultdict(lambda: {"calls": 0, "cost": 0.0, "targets": 0, "out": 0})
    for r in ledger:
        key = r.get("rung") or r.get("phase") or "?"
        b = by_rung[key]
        b["calls"] += 1
        b["cost"] += float(r.get("cost_usd") or 0)
        b["targets"] += int(r.get("targets") or 0)
        b["out"] += int(r.get("tokens_out") or 0)
    esc_cost = sum(v["cost"] for k, v in by_rung.items() if k in ("2b", "2c"))
    if spend and esc_cost > 0.5 * spend:
        finding("warn", "escalation", f"escalated rungs are {esc_cost/spend:.0%} of spend; the cheap rung is not carrying the work")

    # --- coverage -------------------------------------------------------------
    if planned_targets and answered < planned_targets:
        gap = planned_targets - answered
        finding(
            "warn" if gap <= 0.02 * planned_targets else "fail",
            "coverage",
            f"{gap:,} of {planned_targets:,} planned targets were never answered",
        )

    total_in = fresh_in + cache_write
    return {
        "run_dir": str(run_dir),
        "spend_usd": round(spend, 4),
        "calls": len(ledger),
        "calls_failed": len(failed),
        "tokens": {
            "fresh_in": fresh_in,
            "cache_write": cache_write,
            "cache_read": cache_read,
            "out": out_tokens,
            "output_share_of_billed": round(out_tokens / max(1, out_tokens + total_in), 4),
            "cache_hit_share": round(cache_read / max(1, cache_read + total_in), 4),
        },
        "work": {
            "planned_targets": planned_targets,
            "answered": answered,
            "units_done": units_done,
            "usd_per_target": round(spend / answered, 5) if answered else None,
            "out_tokens_per_target": round(out_tokens / answered, 1) if answered else None,
        },
        "by_rung": {
            k: {
                "calls": v["calls"],
                "cost_usd": round(v["cost"], 4),
                "targets": v["targets"],
                "out_tokens": v["out"],
                "usd_per_target": round(v["cost"] / v["targets"], 5) if v["targets"] else None,
            }
            for k, v in sorted(by_rung.items())
        },
        "findings": findings,
        "verdict": "fail" if any(f["level"] == "fail" for f in findings) else ("warn" if findings else "pass"),
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    report = audit(args.run_dir)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["verdict"] != "fail" else 1

    t = report["tokens"]
    w = report["work"]
    print(f"run        {report['run_dir']}")
    print(f"spend      ${report['spend_usd']:.2f} across {report['calls']} call(s), {report['calls_failed']} failed")
    print(f"tokens     in {t['fresh_in']:,} fresh + {t['cache_write']:,} cache-write, {t['cache_read']:,} cache-read, out {t['out']:,}")
    print(f"           output is {t['output_share_of_billed']:.1%} of billed tokens; cache covers {t['cache_hit_share']:.1%} of input")
    if w["planned_targets"]:
        print(f"work       {w['answered']:,} of {w['planned_targets']:,} targets answered in {w['units_done']} unit(s)")
    if w["usd_per_target"] is not None:
        print(f"unit cost  ${w['usd_per_target']:.5f} per target, {w['out_tokens_per_target']:.0f} output tokens per target")
    print()
    print(f"{'rung':<18}{'calls':>6}{'cost':>9}{'targets':>9}{'out tok':>10}{'$/target':>11}")
    for rung, v in report["by_rung"].items():
        per = f"{v['usd_per_target']:.5f}" if v["usd_per_target"] else "-"
        print(f"{rung:<18}{v['calls']:>6}{v['cost_usd']:>9.3f}{v['targets']:>9}{v['out_tokens']:>10,}{per:>11}")
    print()
    if not report["findings"]:
        print("findings   none: every check the 2026-08-25 run failed, this run passes")
    for f in report["findings"]:
        print(f"{f['level'].upper():<10} {f['check']}: {f['detail']}")
    print(f"\nverdict    {report['verdict'].upper()}")
    return 0 if report["verdict"] != "fail" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
