#!/usr/bin/env python3
"""Judge a finished enrichment build on the things a reader will actually hit.

    scripts/build-quality-report.py <store.db> <run-dir>

Cost is the easy half and the ledger already answers it. This answers the other
half: is the map any good, and does it know where it is weak. Every number is
read from the store and the run report, and the checks are the ones the
2026-08-25 disaster and the 2026-08-26 cycle each turned out to need.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path


def main(db: str, run_dir: str) -> int:
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    report = {}
    p = Path(run_dir) / "report.json"
    if p.exists():
        report = json.loads(p.read_text())

    comps = {r["id"]: dict(r) for r in c.execute("SELECT * FROM components")}
    enriched, rels, gaps = {}, 0, []
    prose_lens, missing_desc = [], []
    for r in c.execute("SELECT target_kind,target_id,payload_json FROM enrichment"):
        if r["target_kind"] == "component":
            pl = json.loads(r["payload_json"])
            enriched[r["target_id"]] = pl
            for g in pl.get("honest_gaps") or []:
                gaps.append((r["target_id"], g.get("question"), g.get("why") or ""))
            d = (pl.get("description") or "").strip()
            h = (pl.get("help_text") or "").strip()
            if not d or not h:
                missing_desc.append(r["target_id"])
            prose_lens.append(len(h))
        elif r["target_kind"] == "relationship":
            rels += 1

    total = len(comps)
    cov = 100.0 * len(enriched) / max(1, total)
    print("=" * 68)
    print("COVERAGE")
    print(f"  components in the graph      {total}")
    print(f"  components enriched          {len(enriched)}  ({cov:.1f}%)")
    print(f"  relationships enriched       {rels}")
    print(f"  components missing prose     {len(missing_desc)}")
    if missing_desc[:5]:
        for m in missing_desc[:5]:
            print(f"     - {m}")

    print("\nHONESTY")
    print(f"  honest gaps declared         {len(gaps)}")
    byq = Counter(q for _, q, _ in gaps)
    for q, n in byq.most_common(6):
        print(f"     {q:<22} {n}")
    thin = [g for g in gaps if len(g[2]) < 40]
    print(f"  gaps with a thin explanation {len(thin)}  (a gap must say WHY)")

    adj = report.get("adjudication") or {}
    print("\nGROUNDING (the number that decides whether the prose is trustworthy)")
    if adj:
        checked = adj.get("checked")
        unsup = adj.get("unsupported")
        rate = adj.get("disagreement_rate")
        print(f"  claims spot-checked          {checked}")
        print(f"  unsupported by own evidence  {unsup}")
        if rate is not None:
            print(f"  disagreement rate            {rate:.1%}   <-- 64.1% before fact citations")
        for k in ("edges", "findings", "identity"):
            v = adj.get(k) or {}
            if v.get("target_count"):
                print(f"  verify {k:<10} {v.get('done')}/{v.get('target_count')}  {v.get('verdicts')}")

    census = (report.get("census") or {}).get("by_state") or {}
    if census:
        tot = sum(census.values())
        grounded = sum(v for k, v in census.items() if k.startswith("grounded"))
        print("\nCENSUS")
        for k, v in sorted(census.items()):
            print(f"  {k:<28} {v}")
        print(f"  grounded fraction            {100.0*grounded/max(1,tot):.1f}%")
        # Every target must be accounted for: answered, escalated, or an
        # explicit gap. Vanishing is what made the killed run unauditable.
        print(f"  accounted for                {tot}")

    led = Path(run_dir) / "ledger.jsonl"
    if led.exists():
        rows = [json.loads(l) for l in led.read_text().splitlines() if l.strip()]
        spend = sum(r.get("cost_usd") or 0 for r in rows)
        trunc = sum(1 for r in rows if (r.get("stop_reason") or "") == "max_tokens")
        multi = sum(1 for r in rows if int(r.get("num_turns") or 1) > 1)
        eff = Counter(r.get("effort") or "UNSET" for r in rows)
        print("\nRUN HEALTH")
        print(f"  invocations                  {len(rows)}")
        print(f"  spend                        ${spend:.2f}")
        print(f"  truncated at ceiling         {trunc}   (must be 0)")
        print(f"  multi-turn drift             {multi}   (must be 0)")
        print(f"  effort levels                {dict(eff)}")
        if enriched:
            print(f"  cost per enriched component  ${spend/len(enriched):.4f}")

    print("\nVERDICT INPUTS")
    problems = []
    if cov < 99:
        problems.append(f"{total-len(enriched)} components have no enrichment")
    if missing_desc:
        problems.append(f"{len(missing_desc)} enriched components lack prose")
    if adj.get("disagreement_rate") and adj["disagreement_rate"] > 0.25:
        problems.append(f"disagreement rate {adj['disagreement_rate']:.1%} is above 25%")
    if thin:
        problems.append(f"{len(thin)} honest gaps do not explain themselves")
    if not problems:
        print("  no blocking problems found")
    for x in problems:
        print(f"  PROBLEM: {x}")
    print("=" * 68)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
