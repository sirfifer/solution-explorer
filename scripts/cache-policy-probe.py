#!/usr/bin/env python3
"""Measure Claude prompt-cache policies on real enrichment prompts.

This is deliberately a provider probe, not a benchmark with toy text.  It
builds compact component prompts from a real fact store, runs the same calls
under isolated cache policies, validates every delivered compact payload, and
reports both the provider's measured usage and the uncached counterfactual.

Each arm receives a unique, harmless marker in its stable system prefix.  That
keeps a 1h arm from warming a later 5m arm while preserving the production
prompt shape.  Calls inside one arm are sequential so call one is unambiguously
cold and later calls can reuse it.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analyzer.enrich.compact import validate_compact_response  # noqa: E402
from analyzer.enrich.engine import CACHE_POLICIES, ClaudeCliInvoker  # noqa: E402
from analyzer.enrich.partition import Partition  # noqa: E402
from analyzer.enrich.pipeline import (  # noqa: E402
    LadderConfig,
    LadderPolicy,
    build_run_context,
)
from analyzer.enrich.prompts import (  # noqa: E402
    build_compact_component_prompt,
    split_cached_prompt,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--effort", default="low")
    parser.add_argument("--calls", type=int, default=4)
    parser.add_argument(
        "--policies", nargs="+", default=["off", "5m", "1h"],
        choices=sorted(CACHE_POLICIES),
    )
    return parser


def _usage(result) -> dict[str, int]:
    usage = result.usage if isinstance(result.usage, dict) else {}
    creation = usage.get("cache_creation") or {}
    total_write = int(usage.get("cache_creation_input_tokens") or 0)
    write_1h = int(creation.get("ephemeral_1h_input_tokens") or 0)
    write_5m = int(creation.get("ephemeral_5m_input_tokens") or 0)
    return {
        "fresh": int(usage.get("input_tokens") or 0),
        "write": total_write,
        "write_1h": write_1h,
        "write_5m": write_5m,
        "write_unknown": max(0, total_write - write_1h - write_5m),
        "read": int(usage.get("cache_read_input_tokens") or 0),
        "out": int(usage.get("output_tokens") or 0),
    }


def _cache_economics(tokens: dict[str, int]) -> dict:
    """Return exact input-equivalent economics; output is policy-invariant."""
    unknown = tokens["write_unknown"]
    actual = (
        tokens["fresh"]
        + 2.0 * tokens["write_1h"]
        + 1.25 * tokens["write_5m"]
        + 0.1 * tokens["read"]
    )
    uncached = tokens["fresh"] + tokens["write"] + tokens["read"]
    if unknown:
        return {
            "known": False,
            "actual_input_equivalent": None,
            "uncached_input_equivalent": uncached,
            "net_input_equivalent": None,
            "saving_fraction": None,
        }
    net = actual - uncached
    return {
        "known": True,
        "actual_input_equivalent": round(actual, 1),
        "uncached_input_equivalent": uncached,
        "net_input_equivalent": round(net, 1),
        "saving_fraction": round(-net / uncached, 4) if uncached else 0.0,
    }


def _real_prompts(root: Path, store: Path, count: int) -> list[str]:
    run_dir = Path("/tmp") / f"solution-explorer-cache-probe-{uuid.uuid4().hex}"
    config = LadderConfig(
        store_path=store,
        root=root,
        run_dir=run_dir,
        policy=LadderPolicy(cache_policy="off"),
        dry_run=True,
    )
    ctx = build_run_context(config)
    try:
        ids = [
            component_id
            for partition in ctx.planned_partitions()
            for component_id in partition.answered_component_ids
        ]
        ids = list(dict.fromkeys(ids))[:count]
        if len(ids) < count:
            raise RuntimeError(
                f"store has only {len(ids)} component prompts; requested {count}"
            )
        return [
            build_compact_component_prompt(
                Partition(index, (component_id,), (), True), ctx.facts
            )
            for index, component_id in enumerate(ids)
        ]
    finally:
        ctx.store.close()


def _marked(prompt: str, marker: str) -> str:
    prefix, user = split_cached_prompt(prompt)
    if prefix is None:
        raise RuntimeError("production compact prompt has no cache boundary")
    return (
        "<solution-explorer-system-prefix>\n"
        + prefix
        + f"\nCACHE POLICY PROBE MARKER: {marker}. Ignore this marker."
        + "\n</solution-explorer-system-prefix>\n"
        + user
    )


def run_probe(args: argparse.Namespace) -> dict:
    calls = max(2, int(args.calls))
    prompts = _real_prompts(args.root.resolve(), args.store.resolve(), calls)
    probe_id = uuid.uuid4().hex
    arms = []
    for policy in args.policies:
        marker = f"{probe_id}-{policy}"
        invoker = ClaudeCliInvoker(
            args.model, effort=args.effort, cache_policy=policy
        )
        rows = []
        totals = {key: 0 for key in (
            "fresh", "write", "write_1h", "write_5m", "write_unknown",
            "read", "out",
        )}
        for index, prompt in enumerate(prompts):
            result = invoker(_marked(prompt, marker))
            tokens = _usage(result)
            for key, value in tokens.items():
                totals[key] += value
            prefix, user = split_cached_prompt(_marked(prompt, marker))
            parsed = None
            errors = [result.error or "provider call failed"]
            if result.ok:
                try:
                    parsed = json.loads(result.text)
                except json.JSONDecodeError as exc:
                    errors = [f"invalid JSON: {exc}"]
                else:
                    parsed, errors, _ = validate_compact_response(
                        parsed, prefix=prefix, user=user
                    )
            rows.append({
                "call": index + 1,
                "ok": result.ok,
                "contract_valid": parsed is not None and not errors,
                "validation_errors": errors[:8],
                "cost_usd": round(float(result.cost_usd or 0.0), 6),
                "session_id": result.session_id,
                "tokens": tokens,
            })
        arms.append({
            "policy": policy,
            "calls": rows,
            "all_calls_ok": all(row["ok"] for row in rows),
            "all_contracts_valid": all(row["contract_valid"] for row in rows),
            "cost_usd": round(sum(row["cost_usd"] for row in rows), 6),
            "tokens": totals,
            "cache_economics": _cache_economics(totals),
        })
    return {
        "schema": "solution-explorer-cache-policy-probe/v1",
        "probe_id": probe_id,
        "subject": args.root.resolve().name,
        "store": str(args.store.resolve()),
        "model": args.model,
        "effort": args.effort,
        "calls_per_arm": calls,
        "arms": arms,
    }


def main() -> int:
    args = _parser().parse_args()
    report = run_probe(args)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if all(
        arm["all_calls_ok"] and arm["all_contracts_valid"]
        for arm in report["arms"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
