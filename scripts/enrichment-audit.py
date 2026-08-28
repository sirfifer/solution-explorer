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
# prefix_tokens_est is derived from measured characters-per-token, not from the
# provider's private tokenizer. Treating it as exact produced a false failure
# on a healthy repeated P5 call whose 12,306-token read was just 29 tokens
# (0.24%) below the 12,335 estimate. One percent is a narrow deterministic
# measurement envelope; the cache regression this gate exists to catch is
# orders of magnitude larger (for example 120 tokens read for a 5,000-token
# prefix) and still fails decisively.
PREFIX_ESTIMATE_TOLERANCE = 0.01


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


def audit(
    run_dir: Path, *, baseline_output_tokens: int | None = None,
    target_ratio: float = 0.30, store_path: Path | None = None,
) -> dict:
    ledger = _rows(run_dir / "ledger.jsonl")
    events = _rows(run_dir / "progress.jsonl")
    failures = sorted((run_dir / "failures").glob("*.txt")) if (run_dir / "failures").is_dir() else []

    spend = sum(float(r.get("cost_usd") or 0) for r in ledger)
    out_tokens = sum(int(r.get("tokens_out") or 0) for r in ledger)
    ladder_rows = [r for r in ledger if r.get("phase") == "p2_ladder"]
    ladder_out_tokens = sum(int(r.get("tokens_out") or 0) for r in ladder_rows)
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
    not_low = {e: n for e, n in efforts.items() if e not in ("low", "UNSET")}
    if not_low:
        finding("fail", "effort", f"calls not pinned to low effort: {not_low}")

    # --- ceiling --------------------------------------------------------------
    truncated = [r for r in ledger if (r.get("stop_reason") or "") == "max_tokens"]
    near = [r for r in ledger if int(r.get("tokens_out") or 0) >= WARN_SHARE * OUTPUT_CEILING]
    if truncated:
        finding("fail", "ceiling", f"{len(truncated)} response(s) truncated at the output ceiling")
    if near:
        worst = max(int(r.get("tokens_out") or 0) for r in near)
        finding("warn", "ceiling", f"{len(near)} response(s) within {int(WARN_SHARE*100)}% of the ceiling (worst {worst:,})")

    # --- turns ----------------------------------------------------------------
    multi = [
        r for r in ledger
        if int(r.get("num_turns") or 1) > 1
        and not (
            r.get("structured_output_enforced")
            and int(r.get("num_turns") or 1) == 2
        )
    ]
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
    if failed:
        finding(
            "fail", "failed-invocations",
            f"{len(failed)} model invocation(s) failed; a fallback can recover "
            "content but cannot make the failed work or its accounting disappear",
        )

    # --- duplication ----------------------------------------------------------
    # Later-rung plans and answers are repeated WORK on the same targets, not
    # new targets.  The 2a plan is the unique-target denominator; the final
    # census is the unique-target numerator.
    bulk_plan = next(
        (e for e in events if e.get("event") == "plan" and e.get("rung") == "2a"),
        {},
    )
    planned_targets = int(bulk_plan.get("targets") or 0)
    final_report = {}
    try:
        final_report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    answered = int((final_report.get("census") or {}).get("total") or 0)
    units_done = sum(1 for e in events if e.get("event") == "unit_end")
    if planned_targets and answered != planned_targets:
        finding(
            "fail", "target-conservation",
            f"final census has {answered:,} targets for {planned_targets:,} planned; equality is required",
        )
    phase_notes = [
        str(note)
        for phase in (final_report.get("phases") or []) if isinstance(phase, dict)
        for note in (phase.get("notes") or [])
    ]
    coverage_notes = [note for note in phase_notes if "coverage violation" in note]
    if coverage_notes:
        finding(
            "fail", "target-conservation",
            f"{len(coverage_notes)} compact call(s) reported missing, extra, or duplicate targets",
        )

    # --- publication completion ---------------------------------------------
    determination = final_report.get("determination") or {}
    if determination.get("verdict") != "done":
        finding(
            "fail", "completion",
            f"determination verdict is {determination.get('verdict', 'missing')!r}, not 'done'",
        )
    non_met = [
        f"{item.get('criterion_id')}:{item.get('verdict')}"
        for item in (final_report.get("criteria") or []) if isinstance(item, dict)
        if item.get("verdict") != "met"
    ]
    if non_met:
        finding("fail", "completion", "criteria not met: " + ", ".join(non_met))
    adjudication = final_report.get("adjudication") or {}
    disagreement = adjudication.get("disagreement_rate")
    if disagreement is None:
        finding("fail", "completion", "adjudication disagreement is unmeasured")
    elif float(disagreement) > 0.20:
        finding(
            "fail", "completion",
            f"adjudication disagreement {float(disagreement):.1%} exceeds 20%",
        )
    identity = final_report.get("identity") or {}
    configured_cost_ceiling = (identity.get("policy") or {}).get("max_cost_usd")
    if (
        configured_cost_ceiling is not None
        and spend > float(configured_cost_ceiling) + 1e-9
    ):
        finding(
            "fail", "cost-ceiling-overshoot",
            f"measured cost ${spend:.6f} exceeded the configured "
            f"${float(configured_cost_ceiling):.6f} ceiling; the CLI allowance "
            "did not prevent billed overshoot",
        )

    # --- escalation -----------------------------------------------------------
    by_rung: dict[str, dict] = defaultdict(lambda: {"calls": 0, "cost": 0.0, "targets": 0, "out": 0})
    for r in ledger:
        key = r.get("rung") or r.get("phase") or "?"
        b = by_rung[key]
        b["calls"] += 1
        b["cost"] += float(r.get("cost_usd") or 0)
        b["targets"] += int(r.get("targets") or 0)
        b["out"] += int(r.get("tokens_out") or 0)
    esc_cost = sum(v["cost"] for k, v in by_rung.items() if k in ("2b", "2c", "opus", "fable"))
    if spend and esc_cost > 0.5 * spend:
        finding("warn", "escalation", f"escalated rungs are {esc_cost/spend:.0%} of spend; the cheap rung is not carrying the work")

    # --- coverage -------------------------------------------------------------
    # Exact equality above subsumes the old tolerance-based coverage check.

    # --- compact delivered-output and same-corpus billed-output gates ---------
    compact_rows = [r for r in ledger if r.get("output_budget_ok") is not None]
    compact_violations = [r for r in compact_rows if r.get("output_budget_ok") is False]
    if compact_violations:
        finding(
            "fail", "compact-output",
            f"{len(compact_violations)} compact response(s) exceeded their declared delivered-output budget",
        )
    cache_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in ledger:
        # Caching is a transport boundary, not a structured-output feature.
        # P5 deliberately has no compact schema but still carries the stable
        # prefix and must fail this predicate if repeated calls rewrite it.
        if row.get("prefix_hash"):
            cache_groups[(str(row.get("model")), str(row.get("prefix_hash")))].append(row)
    cache_misses = 0
    prefix_read_shortfalls = 0
    for rows in cache_groups.values():
        # warm_first deliberately permits one cold writer per stable prefix.
        zero_read = sum(1 for row in rows if int(row.get("tokens_cached") or 0) == 0)
        cache_misses += max(0, zero_read - 1)
        # Reading SOMETHING is not the same as reading THIS prefix. A call that
        # picked up a small unrelated entry satisfies the zero-read rule while
        # still writing its own stable block again at the 2x creation rate, so
        # every call but the group's coldest must read back at least its own
        # prefix. The coldest row is the one permitted writer, chosen by
        # measured reads rather than by ledger order, which parallel phases do
        # not guarantee. A row carrying no estimate is an older ledger and stays
        # governed by the zero-read rule alone, so the audit still runs on it.
        by_read = sorted(rows, key=lambda row: int(row.get("tokens_cached") or 0))
        for row in by_read[1:]:
            estimate = int(row.get("prefix_tokens_est") or 0)
            floor = int(estimate * (1.0 - PREFIX_ESTIMATE_TOLERANCE))
            if floor and int(row.get("tokens_cached") or 0) < floor:
                prefix_read_shortfalls += 1
    if cache_misses:
        finding(
            "fail", "cache-boundary",
            f"{cache_misses} non-warm cacheable call(s) read zero cached tokens",
        )
    if prefix_read_shortfalls:
        finding(
            "fail", "cache-boundary",
            f"{prefix_read_shortfalls} non-warm cacheable call(s) read fewer cached "
            "tokens than their own prefix outside the 1% tokenizer-estimate "
            "envelope; the stable block was rewritten, not reused",
        )
    # P5 and scoped work orders are repeated calls to one contract. Their
    # census, adjudication, round history, and assignment all belong in the
    # uncached tail, so more than one prefix hash in a run is itself a cache
    # boundary regression. The per-hash warm-first check above cannot catch
    # this: two cold singleton groups each look locally valid.
    stable_contract_hashes: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in ledger:
        phase = str(row.get("phase") or "")
        if phase not in ("p5_determination", "work_order"):
            continue
        prefix_hash = str(row.get("prefix_hash") or "")
        if prefix_hash:
            stable_contract_hashes[(phase, str(row.get("model") or ""))].add(
                prefix_hash
            )
    prefix_fragmentations = sum(
        len(hashes) - 1 for hashes in stable_contract_hashes.values()
        if len(hashes) > 1
    )
    if prefix_fragmentations:
        finding(
            "fail", "cache-boundary",
            f"{prefix_fragmentations} extra stable-contract prefix hash(es) "
            "were rendered within one run; changing work leaked into the "
            "cacheable P5/work-order prefix",
        )

    unexplained_gaps = []
    # Reasons live on the census contract state. The report's escalation table
    # intentionally avoids duplicating the failure objects, so auditing that
    # presentation layer silently inspected zero reasons on every real run.
    for item in ((final_report.get("census") or {}).get("items") or []):
        if not isinstance(item, dict) or item.get("state") not in {
            "honest-gap", "honest_gap",
        }:
            continue
        for failure in item.get("failed") or []:
            reason = str(failure.get("note") or "").strip() if isinstance(failure, dict) else ""
            if not reason or reason == "no answer was produced for a required question":
                unexplained_gaps.append(item.get("target_id"))
    if unexplained_gaps:
        finding(
            "fail", "honest-gap-quality",
            f"{len(unexplained_gaps)} honest gap question(s) have no specific "
            "reader-facing reason",
        )
    if baseline_output_tokens is not None:
        allowed = int(max(0, baseline_output_tokens) * target_ratio)
        if ladder_out_tokens > allowed:
            finding(
                "fail", "output-reduction",
                f"{ladder_out_tokens:,} ladder billed output tokens exceeds the same-corpus gate "
                f"{allowed:,} ({target_ratio:.1%} of baseline {baseline_output_tokens:,})",
            )

    # --- input-per-call ceilings by phase (V-P8) ------------------------------
    # Runaway diagnostics on what one call may ship. They sit deliberately
    # above the measured healthy shape: the 2026-08-27 UnaMentis canaries used
    # 41,028 and 43,453 tokens for the evidence-complete first determination
    # call. The old 35k value therefore rejected healthy quality context after
    # the fact/source handoff was repaired. A 70k guard is ~1.6x the measured
    # high-water mark: useful for detecting prompt regrowth, not a quality-
    # suppressing target or a runtime truncation control.
    input_ceilings = {
        "p5_determination": 70_000,
        "verify-identity": 15_000,
        "verify-edges": 30_000,
    }
    for r in ledger:
        ceiling_key = (
            r.get("rung") if r.get("rung") in input_ceilings
            else r.get("phase") if r.get("phase") in input_ceilings
            else None
        )
        if ceiling_key is None:
            continue
        call_in = int(r.get("tokens_fresh_in") or 0) + int(r.get("tokens_cache_write") or 0)
        if call_in > input_ceilings[ceiling_key]:
            finding(
                "fail", "input-ceiling",
                f"a {ceiling_key} call shipped {call_in:,} input tokens against "
                f"its {input_ceilings[ceiling_key]:,} ceiling",
            )

    # --- store-census conservation (P6) ---------------------------------------
    # The census is derived from in-memory states; the store is what every
    # later phase and rerun reads. The v2 build diverged 47 rows without any
    # check noticing. When the run dir names its store, compare terminal
    # distributions exactly.
    if store_path is not None and store_path.exists():
        import sqlite3

        stored_states: dict[str, int] = defaultdict(int)
        census_target_ids = {
            str(item.get("target_id") or "")
            for item in ((final_report.get("census") or {}).get("items") or [])
            if isinstance(item, dict) and item.get("target_id")
        }
        try:
            db = sqlite3.connect(str(store_path))
            for target_id, payload in db.execute(
                "select target_id, payload_json from enrichment "
                "where target_kind = 'contract-state'"
            ):
                if census_target_ids and str(target_id) not in census_target_ids:
                    continue
                try:
                    stored_states[json.loads(payload).get("state") or "?"] += 1
                except json.JSONDecodeError:
                    stored_states["?"] += 1
            db.close()
        except sqlite3.Error as exc:
            finding("warn", "store-conservation", f"store unreadable: {exc}")
            stored_states = {}
        census_states: dict[str, int] = defaultdict(int)
        for key, count in ((final_report.get("census") or {}).get("by_state") or {}).items():
            base = str(key).split("@")[0].replace("honest-gap", "honest_gap")
            census_states[base] += int(count or 0)
        if stored_states and dict(stored_states) != dict(census_states):
            finding(
                "fail", "store-conservation",
                f"store contract-state distribution {dict(stored_states)} does not "
                f"equal the census {dict(census_states)}; later phases and reruns "
                "read the store, and it is lying about terminal states",
            )

    bulk_rows = [r for r in ladder_rows if r.get("rung") == "2a"]
    bulk_attempted_targets = sum(int(r.get("targets") or 0) for r in bulk_rows)
    # Billed output is paid for every attempt, including a duplicate retry.
    # Divide by the unique planned population, not attempted ledger rows, or a
    # full-batch retry makes both numerator and denominator grow and hides the
    # exact waste this gate exists to detect.
    bulk_targets = planned_targets or answered
    bulk_output = sum(int(r.get("tokens_out") or 0) for r in bulk_rows)
    bulk_per_target = bulk_output / bulk_targets if bulk_targets else None
    # The quality-complete evidence vocabulary raised the measured compact run
    # from 384.1 to 420.8 tokens/target. 430 is the smallest round ceiling above
    # that same-corpus measurement (2.2% headroom), and remains a deterministic
    # 67.7% reduction from the 1,332-token baseline.
    if bulk_per_target is not None and bulk_per_target > 430:
        finding(
            "fail", "bulk-output-density",
            f"rung 2a emitted {bulk_per_target:.1f} billed tokens per target; limit is 430",
        )
    unique_targets = planned_targets or answered
    ladder_per_target = ladder_out_tokens / unique_targets if unique_targets else None
    if ladder_per_target is not None and ladder_per_target > 500:
        finding(
            "fail", "ladder-output-density",
            f"the ladder emitted {ladder_per_target:.1f} billed tokens per unique target; limit is 500",
        )
    escalation_rows = [
        r for r in ladder_rows if r.get("rung") in ("2b", "2c", "opus", "fable")
    ]
    escalation_targets = sum(int(r.get("targets") or 0) for r in escalation_rows)
    escalation_output = sum(int(r.get("tokens_out") or 0) for r in escalation_rows)
    escalation_per_attempt = (
        escalation_output / escalation_targets if escalation_targets else None
    )
    # Billed output includes provider-hidden reasoning that cannot be capped by
    # this transport.  The measured calibration spans 148 tokens/attempt over
    # three items, while an exact one-item replay of a *shorter* 411-byte answer
    # billed 384 tokens. Treating one or two attempts as a deterministic density
    # verdict therefore rewards provider variance, not prompt efficiency. Five
    # attempts is the smallest release sample; below it the exact byte ceiling
    # and the whole-ladder 500-token gate still fail hard, and this sub-gate is
    # reported as explicitly inconclusive rather than silently passed.
    escalation_sample_min = 5
    if escalation_per_attempt is not None and escalation_per_attempt > 260:
        level = "fail" if escalation_targets >= escalation_sample_min else "info"
        suffix = (
            ""
            if level == "fail"
            else f"; INCONCLUSIVE: only {escalation_targets} attempt(s), fewer than the "
            f"{escalation_sample_min}-attempt release sample"
        )
        finding(
            level, "escalation-output-density",
            f"escalations emitted {escalation_per_attempt:.1f} billed tokens per "
            f"attempt; limit is 260{suffix}",
        )

    # P5 work orders use the same delta-only repair contract as escalations and
    # must meet the same measured billed-output density. Keeping this separate
    # prevents dozens of one-target repair calls from hiding outside the P2
    # ladder gates, which the live UnaMentis canary did (33 calls for 34 targets,
    # 424 billed output tokens per attempt). This is a post-run diagnostic, not
    # a runtime truncation control; delivered answer bytes keep their structural
    # quality budget independently.
    work_order_rows = [r for r in ledger if r.get("phase") == "work_order"]
    work_order_attempts = sum(
        int(r.get("targets") or 0) for r in work_order_rows
    )
    work_order_output = sum(
        int(r.get("tokens_out") or 0) for r in work_order_rows
    )
    work_order_per_attempt = (
        work_order_output / work_order_attempts if work_order_attempts else None
    )
    if work_order_per_attempt is not None and work_order_per_attempt > 260:
        level = "fail" if work_order_attempts >= escalation_sample_min else "info"
        suffix = (
            "" if level == "fail" else
            f"; INCONCLUSIVE: only {work_order_attempts} attempt(s), fewer than "
            f"the {escalation_sample_min}-attempt release sample"
        )
        finding(
            level, "work-order-output-density",
            f"work orders emitted {work_order_per_attempt:.1f} billed tokens per "
            f"attempt; limit is 260{suffix}",
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
            "ladder_out": ladder_out_tokens,
            "output_share_of_billed": round(out_tokens / max(1, out_tokens + total_in), 4),
            "cache_hit_share": round(cache_read / max(1, cache_read + total_in), 4),
        },
        "work": {
            "planned_targets": planned_targets,
            "answered": answered,
            "units_done": units_done,
            "bulk_attempted_targets": bulk_attempted_targets,
            "bulk_unique_targets": bulk_targets,
            "usd_per_target": (
                round(spend / unique_targets, 5) if unique_targets else None
            ),
            "out_tokens_per_target": (
                round(out_tokens / unique_targets, 1) if unique_targets else None
            ),
        },
        "output_gate": {
            "baseline_output_tokens": baseline_output_tokens,
            "target_ratio": target_ratio if baseline_output_tokens is not None else None,
            "allowed_output_tokens": (
                int(baseline_output_tokens * target_ratio)
                if baseline_output_tokens is not None else None
            ),
            "compact_calls": len(compact_rows),
            "compact_budget_violations": len(compact_violations),
            "non_warm_cache_misses": cache_misses,
            "prefix_read_shortfalls": prefix_read_shortfalls,
            "stable_prefix_fragmentations": prefix_fragmentations,
            "bulk_tokens_per_target": (
                round(bulk_per_target, 1) if bulk_per_target is not None else None
            ),
            "ladder_tokens_per_unique_target": (
                round(ladder_per_target, 1) if ladder_per_target is not None else None
            ),
            "escalation_tokens_per_attempt": (
                round(escalation_per_attempt, 1)
                if escalation_per_attempt is not None else None
            ),
            "escalation_attempts": escalation_targets,
            "escalation_release_sample_min": escalation_sample_min,
            "work_order_tokens_per_attempt": (
                round(work_order_per_attempt, 1)
                if work_order_per_attempt is not None else None
            ),
            "work_order_attempts": work_order_attempts,
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
        "verdict": (
            "fail" if any(f["level"] == "fail" for f in findings)
            else "warn" if any(f["level"] == "warn" for f in findings)
            else "pass"
        ),
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--baseline-run-dir", type=Path,
        help="same-corpus baseline run; enforces the ladder billed-output reduction gate",
    )
    ap.add_argument(
        "--target-ratio", type=float, default=0.30,
        help="maximum new/baseline ladder billed-output ratio (default: 0.30)",
    )
    ap.add_argument(
        "--store", type=Path, default=None,
        help="the run's index.db; enforces store-census conservation (P6)",
    )
    args = ap.parse_args(argv)

    baseline = None
    if args.baseline_run_dir:
        baseline = sum(
            int(row.get("tokens_out") or 0)
            for row in _rows(args.baseline_run_dir / "ledger.jsonl")
            if row.get("phase") == "p2_ladder"
        )
    report = audit(
        args.run_dir, baseline_output_tokens=baseline,
        target_ratio=args.target_ratio, store_path=args.store,
    )
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
