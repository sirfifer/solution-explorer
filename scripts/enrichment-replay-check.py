#!/usr/bin/env python3
"""Preflight an enrichment run's 2a call plan without spending anything.

Rebuilds every plannable rung-2a prompt from a real store, through the SAME
code path the live rung uses (ladder.plan_compact_chunks feeds both), then
evaluates the checks that must pass before a dollar is spent
(IMPLEMENTATION-DELTA-PROMPT.md P13):

  prefix      one byte-identical cacheable prefix per target kind; a second
              hash means something per-call leaked into the prefix and every
              non-warm call will re-bill it at the 2x write rate
  projection  predicted billed output per call, at the measured scale
              (billed = 1.73 x o200k-equivalent of delivered text) and the
              G2 dispersion default 1.90, stays under 85% of the output
              ceiling
  context     no prompt approaches the context bound

The store is copied to a scratch location first: derivation writes tables,
and a preflight must never mutate the store it inspects.

    scripts/enrichment-replay-check.py --store <index.db> --root <subject-root>
        [--brief <brief.json>] [--json]

Escalation-repair calls depend on 2a's outcome and cannot be planned here;
their budgets are enforced live by the response budget and the audit gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from analyzer.derive import derive_all  # noqa: E402
from analyzer.derive.importance import rank_components  # noqa: E402
from analyzer.enrich.ladder import order_partitions, plan_compact_chunks  # noqa: E402
from analyzer.enrich.partition import plan_partitions  # noqa: E402
from analyzer.enrich.prompts import (  # noqa: E402
    StoreFacts,
    build_compact_component_prompt,
    build_compact_relationship_prompt,
    split_cached_prompt,
)
from analyzer.store import FactStore  # noqa: E402

# Measurement constants, all from the v2 full build (2026-08-26, unamentis-ios,
# 161 ledger rows joined to their CLI transcripts). Re-pin only with a
# committed measurement doc.
BILLED_PER_O200K = 1.73          # billed output per o200k token of delivered text
CHARS_PER_O200K = 3.77           # measured chars-per-o200k on delivered JSON
COMPONENT_BLOCK_O200K = 398      # mean compact component block (p95 562)
RELATIONSHIP_BLOCK_O200K = 80    # mean compact relationship block (p95 105)
DISPERSION = 1.90                # G2 default until Level 1 recalibrates
OUTPUT_CEILING = 64_000
CEILING_SHARE = 0.85
CONTEXT_WARN_CHARS = 500_000     # ~132k billed prompt tokens at 2.385 chars/tok


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", type=Path, required=True)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--brief", type=Path, default=None,
                    help="subject brief JSON; without it prefixes are checked brief-less")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    brief = json.loads(args.brief.read_text()) if args.brief else None

    with tempfile.TemporaryDirectory(prefix="replay-check-") as scratch:
        db_copy = Path(scratch) / "index.db"
        shutil.copyfile(args.store, db_copy)
        store = FactStore(str(db_copy))
        try:
            _, arch = derive_all(store, args.root.name, root_path=str(args.root))
            facts = StoreFacts(
                arch,
                store.capabilities(),
                store.data_entities(),
                store.rules(),
                arch.get("relationships", []),
            )
            ranking = rank_components(store)
            plan = plan_partitions(
                arch.get("components", []), arch.get("relationships", [])
            )
            partitions = order_partitions(plan.partitions, ranking)

            calls = []
            prefix_hashes: dict[str, set[str]] = defaultdict(set)
            for kind, part in plan_compact_chunks(partitions):
                if kind == "component":
                    prompt = build_compact_component_prompt(part, facts, brief=brief)
                    targets = len(part.answered_component_ids)
                    block = COMPONENT_BLOCK_O200K
                else:
                    prompt = build_compact_relationship_prompt(part, facts, brief=brief)
                    targets = len(part.relationship_keys)
                    block = RELATIONSHIP_BLOCK_O200K
                prefix, user = split_cached_prompt(prompt)
                prefix = prefix or ""
                digest = hashlib.sha256(prefix.encode("utf-8")).hexdigest()[:16]
                prefix_hashes[kind].add(digest)
                predicted_out = targets * block * BILLED_PER_O200K
                calls.append({
                    "kind": kind,
                    "targets": targets,
                    "prefix_chars": len(prefix),
                    "user_chars": len(user),
                    "prefix_hash": digest,
                    "predicted_out_tokens": round(predicted_out),
                    "projection_ok": predicted_out * DISPERSION
                    <= CEILING_SHARE * OUTPUT_CEILING,
                    "context_ok": len(prefix) + len(user) <= CONTEXT_WARN_CHARS,
                })
        finally:
            store.close()

    failures = []
    for kind, hashes in sorted(prefix_hashes.items()):
        if len(hashes) != 1:
            failures.append(
                f"prefix: {kind} calls render {len(hashes)} distinct prefixes; "
                "a byte-stable prefix per kind is the cache contract"
            )
    over = [c for c in calls if not c["projection_ok"]]
    if over:
        worst = max(c["predicted_out_tokens"] for c in over)
        failures.append(
            f"projection: {len(over)} call(s) project over "
            f"{CEILING_SHARE:.0%} of the {OUTPUT_CEILING:,} output ceiling "
            f"at dispersion {DISPERSION} (worst {worst:,})"
        )
    wide = [c for c in calls if not c["context_ok"]]
    if wide:
        failures.append(f"context: {len(wide)} prompt(s) exceed {CONTEXT_WARN_CHARS:,} chars")

    result = {
        "store": str(args.store),
        "calls_planned": len(calls),
        "by_kind": {
            kind: {
                "calls": sum(1 for c in calls if c["kind"] == kind),
                "targets": sum(c["targets"] for c in calls if c["kind"] == kind),
                "prefix_chars": next(
                    (c["prefix_chars"] for c in calls if c["kind"] == kind), 0
                ),
                "mean_user_chars": round(
                    sum(c["user_chars"] for c in calls if c["kind"] == kind)
                    / max(1, sum(1 for c in calls if c["kind"] == kind))
                ),
                "predicted_out_tokens": sum(
                    c["predicted_out_tokens"] for c in calls if c["kind"] == kind
                ),
            }
            for kind in sorted({c["kind"] for c in calls})
        },
        "failures": failures,
        "verdict": "fail" if failures else "pass",
        "calls": calls,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"store      {result['store']}")
        print(f"planned    {result['calls_planned']} rung-2a call(s)")
        for kind, v in result["by_kind"].items():
            print(
                f"  {kind:13s} calls={v['calls']:3d} targets={v['targets']:4d} "
                f"prefix={v['prefix_chars']:6d}ch user~{v['mean_user_chars']:6d}ch "
                f"projected_out={v['predicted_out_tokens']:7d} tok"
            )
        if not args.brief:
            print("note       no --brief given; live prefixes will differ by the brief block")
        for failure in failures:
            print(f"FAIL       {failure}")
        print(f"verdict    {result['verdict'].upper()}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
