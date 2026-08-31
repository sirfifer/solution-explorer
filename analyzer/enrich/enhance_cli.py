"""The `enhance` subcommand: headless AI enrichment over a v2 fact store.

Entry shape (recorded in TASKS.md P7-2): ``python3 analyze.py enhance [root]
--store <path> [options]``. Dispatched from ``analyzer/cli.py:main`` when the
first CLI token is ``enhance``, so ``analyze.py`` stays the single entrypoint and
the existing flag-based parser is untouched.

No hardcoded paths: the store defaults to ``<root>/.solution-explorer/index.db``
(the same default the v2 analyze path uses) and everything else derives from the
``root`` and ``--store`` arguments.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .engine import (
    CACHE_POLICIES,
    DEFAULT_MAX_COST_USD,
    DEFAULT_MAX_PARALLEL,
    DEFAULT_MODEL,
    EnhanceConfig,
    run_enhance,
)
from .models import DEFAULT_SOURCE, ModelSpec, known_sources
from .pipeline import DEFAULT_MODELS

DEFAULT_STORE_RELPATH = Path(".solution-explorer") / "index.db"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze.py enhance",
        description="Headless AI enrichment (DPEA) over a v2 fact store. Reads the "
        "store, partitions components, invokes Claude per partition, validates "
        "against the payload schema, writes provenance-stamped enrichment rows, "
        "and runs the quality scorer as a gate.",
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Repository root the store indexes (default: current directory). "
        "Used for the default store path and for the commit sha stamped on "
        "enrichment rows.",
    )
    parser.add_argument(
        "--store",
        default=None,
        help="Path to the v2 fact store (default: <root>/.solution-explorer/index.db).",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Re-enhance only stale or missing targets plus their architectural "
        "neighbours (staleness from enrichment provenance). Fresh targets are "
        "left untouched.",
    )
    parser.add_argument(
        "--max-partitions",
        type=int,
        default=None,
        help="Cap the number of partitions processed (cost control).",
    )
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=DEFAULT_MAX_PARALLEL,
        help=f"Maximum concurrent partition invocations (default: {DEFAULT_MAX_PARALLEL}).",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Model for enhancement (default: {DEFAULT_MODEL}, a sonnet-class model).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the partition plan and prompt sizes without invoking the model.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=85.0,
        help="Minimum quality score the gate requires (default: 85.0).",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Write the machine-readable run report to this JSON file.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=50_000,
        help="Soft per-partition line budget (default: 50000).",
    )
    parser.add_argument(
        "--max-components",
        type=int,
        default=30,
        help="Soft per-partition component cap (default: 30).",
    )
    parser.add_argument(
        "--min-components",
        type=int,
        default=5,
        help="Soft per-partition minimum before affinity merge (default: 5).",
    )
    parser.add_argument(
        "--max-cost-usd",
        type=float,
        default=None,
        help="Per-run cost ceiling in USD summed across ALL attempts, retries "
        f"included (classic pass default: {DEFAULT_MAX_COST_USD}; ladder default: "
        "disabled in favor of --pause-at-cost-usd). Once reached, no new "
        "partitions launch, in-flight ones finish, the rest are recorded as "
        "skipped, and the partial state is reported honestly. "
        "Pass a large value to effectively disable it.",
    )
    parser.add_argument(
        "--pause-at-cost-usd",
        type=float,
        default=None,
        help="Generous operator checkpoint for ladder runs. When reached, "
        "finish and bank calls already in flight, persist decision support in "
        "<run-dir>/control.json, and pause before any new model call until the "
        "dashboard resumes with a higher checkpoint or cancels. Unlike "
        "--max-cost-usd this is resumable and does not cap an answer.",
    )
    parser.add_argument(
        "--ladder",
        action="store_true",
        help="Run the full Enrichment Engine ladder (P1 orientation through P5 "
        "determination) instead of the single bulk-enrichment pass. Default off: "
        "without this flag the enhance path is byte-for-byte what it was.",
    )
    parser.add_argument(
        "--run-dir",
        default=None,
        help="Directory the ladder writes its Run Report and per-phase artifacts "
        "into (default: <root>/.solution-explorer/runs/<timestamp>). Ladder only.",
    )
    parser.add_argument(
        "--phase-model",
        action="append",
        default=None,
        metavar="KEY=SPEC",
        help="Bind one phase or rung to a source and model, repeatable. SPEC is "
        "'model' (the default source), 'source:model', or 'source:auto' to leave "
        "the model unpinned so that source routes the call itself. Keys: "
        + ", ".join(sorted(DEFAULT_MODELS)) + ". Ladder only.",
    )
    parser.add_argument(
        "--model-source",
        default=None,
        help="Default source for every tier binding that does not name one "
        f"(default: {DEFAULT_SOURCE}). Registered sources: "
        + ", ".join(known_sources()) + ". Ladder only.",
    )
    parser.add_argument(
        "--max-wall-minutes",
        type=float,
        default=None,
        help="Wall-clock ceiling for the whole ladder run, minutes. Soft, like "
        "the cost ceiling: in-flight work finishes, no new work launches, and "
        "the partial state is reported honestly. Ladder only.",
    )
    parser.add_argument(
        "--invoke-timeout-seconds",
        type=int,
        default=None,
        help="Per-attempt subprocess timeout for real model invocations "
        "(default 1200). The retry budget scales with it so a timed-out call "
        "gets one recovery attempt. Ladder only.",
    )
    parser.add_argument(
        "--min-rounds",
        type=int,
        default=None,
        help="Forced improvement rounds P5 must run even when it believes the map "
        "is done (default 1, the Wave 1 forced-iteration decision). Ladder only.",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Cap on P5 improvement rounds (default 2). Ladder only.",
    )
    parser.add_argument(
        "--spot-check-fraction",
        type=float,
        default=None,
        help="Fraction of grounded targets independently checked by P3 "
        "(default 0.1). Use 1.0 for a small release canary. Ladder only.",
    )
    parser.add_argument(
        "--max-spot-checks",
        type=int,
        default=None,
        help="Maximum grounded targets independently checked by P3 "
        "(default 25). Ladder only.",
    )
    parser.add_argument(
        "--retry-attempts",
        type=int,
        default=None,
        help="Transport attempts per logical invoke for the default invoker (1 "
        "initial plus retries), transient failures only, full-jitter backoff "
        "(default: 4). Deterministic failures (parse errors, 4xx) are never "
        "retried.",
    )
    parser.add_argument(
        "--cache-policy",
        choices=("adaptive", *sorted(CACHE_POLICIES)),
        default="adaptive",
        help="Prompt-cache policy. 'adaptive' disables caching for independent "
        "one-shot work and uses five-minute caching only for measured iterative "
        "phases. Concrete values force a whole-run validation arm.",
    )
    parser.add_argument(
        "--phase-cache",
        action="append",
        default=None,
        metavar="KEY=POLICY",
        help="Override adaptive caching for one ladder key, phase, or rung. "
        "POLICY is provider-default, 1h, 5m, or off. Repeatable; ladder only.",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 2
    store_path = (
        Path(args.store).resolve() if args.store else root / DEFAULT_STORE_RELPATH
    )
    if not store_path.exists():
        print(
            f"Error: fact store not found at {store_path}. Run "
            f"`python3 analyze.py {args.root} --store {store_path}` first to build it.",
            file=sys.stderr,
        )
        return 2

    # The ladder is a separate top-level path, not a mode of run_enhance. The
    # default path below is therefore untouched by its existence: with --ladder
    # off, main() reaches run_enhance with exactly the config it always built.
    if args.ladder:
        return _run_ladder_path(args, root, store_path)

    retry_policy = None
    if args.retry_attempts is not None:
        from .retry import RetryPolicy

        retry_policy = RetryPolicy(max_attempts=args.retry_attempts)

    config = EnhanceConfig(
        store_path=store_path,
        root=root,
        update=args.update,
        max_partitions=args.max_partitions,
        max_parallel=args.max_parallel,
        model=args.model,
        dry_run=args.dry_run,
        threshold=args.threshold,
        report_path=Path(args.report).resolve() if args.report else None,
        max_lines=args.max_lines,
        max_components=args.max_components,
        min_components=args.min_components,
        max_cost_usd=(
            DEFAULT_MAX_COST_USD
            if args.max_cost_usd is None
            else args.max_cost_usd
        ),
        retry_policy=retry_policy,
        cache_policy=args.cache_policy,
    )

    report = run_enhance(config)

    # Human-readable summary.
    print(f"Enhancement run ({report.mode} mode, {report.partition_count} partitions)")
    for note in report.notes:
        print(f"  note: {note}")
    if report.dry_run:
        print("  dry run: no model invoked. Partition plan:")
        for entry in report.plan_preview:
            pid = entry.get("id")
            if pid == "architecture":
                print(
                    f"    architecture-narrative: ~{entry['prompt_tokens_est']} tokens"
                )
            else:
                print(
                    f"    partition {pid}: {len(entry['components'])} components, "
                    f"{len(entry['relationships'])} relationships, "
                    f"~{entry['prompt_tokens_est']} tokens"
                )
        return 0

    for p in report.partitions:
        status = p.status.upper()
        line = f"    partition {p.id}: {status} ({len(p.component_ids)} components"
        line += f", {p.attempts} attempt(s))"
        print(line)
        if p.status in ("failed", "skipped"):
            for err in p.errors[:5]:
                print(f"      - {err}")
    print(
        f"  enriched: {report.components_enriched} components, "
        f"{report.relationships_enriched} relationships, "
        f"architecture={'yes' if report.architecture_enriched else 'no'}"
    )
    if report.total_cost_usd:
        print(f"  cost: ${report.total_cost_usd:.4f}")
    if report.scorer_pass is not None:
        print(f"  quality gate: {'PASS' if report.scorer_pass else 'FAIL'}")
        if report.scorer_summary:
            print(f"    {report.scorer_summary}")
    if report.failed_partitions:
        print(f"  FAILED partitions: {report.failed_partitions}")
    if config.report_path is not None:
        print(f"  report: {config.report_path}")

    return 0 if report.ok else 1


def _parse_phase_models(
    pairs: Optional[list[str]], default_source: str = DEFAULT_SOURCE
) -> tuple[dict, list[str]]:
    """Parse repeated KEY=SPEC tier bindings. Returns (bindings, errors).

    Two things are errors rather than silent no-ops, because both would be
    invisible afterwards and would misattribute whatever that rung produced: an
    unknown phase or rung key, and a source with no registered provider. The
    second is caught here, at configuration time, rather than when the rung first
    tries to invoke and the run has already spent everything below it.
    """
    models = dict(DEFAULT_MODELS)
    errors: list[str] = []
    if default_source not in known_sources():
        errors.append(
            f"--model-source: unknown source {default_source!r}; registered "
            "sources are " + (", ".join(known_sources()) or "(none)")
        )
        return models, errors
    for key in models:
        models[key] = ModelSpec.parse(models[key], default_source=default_source)
    for raw in pairs or []:
        if "=" not in raw:
            errors.append(f"--phase-model expects KEY=SPEC, got {raw!r}")
            continue
        key, _, spec_text = raw.partition("=")
        key, spec_text = key.strip(), spec_text.strip()
        if key not in DEFAULT_MODELS:
            errors.append(
                f"--phase-model: unknown key {key!r}; valid keys are "
                + ", ".join(sorted(DEFAULT_MODELS))
            )
            continue
        if not spec_text:
            errors.append(f"--phase-model: empty binding for key {key!r}")
            continue
        spec = ModelSpec.parse(spec_text, default_source=default_source)
        if spec.source not in known_sources():
            errors.append(
                f"--phase-model {key}: unknown source {spec.source!r}; registered "
                "sources are " + (", ".join(known_sources()) or "(none)")
            )
            continue
        models[key] = spec
    return models, errors


def _parse_phase_cache(pairs: Optional[list[str]]) -> tuple[dict[str, str], list[str]]:
    overrides: dict[str, str] = {}
    errors: list[str] = []
    for raw in pairs or []:
        key, sep, value = raw.partition("=")
        key, value = key.strip(), value.strip().lower()
        if not sep or not key:
            errors.append(f"--phase-cache expects KEY=POLICY, got {raw!r}")
        elif value not in CACHE_POLICIES:
            errors.append(
                f"--phase-cache {key}: unknown policy {value!r}; expected "
                + ", ".join(sorted(CACHE_POLICIES))
            )
        else:
            overrides[key] = value
    return overrides, errors


def _run_ladder_path(args, root: Path, store_path: Path) -> int:
    """The --ladder entry: build the policy, run the pipeline, print the summary."""
    from .pipeline import IterationPolicy, LadderConfig, LadderPolicy, run_ladder

    models, errors = _parse_phase_models(
        args.phase_model, args.model_source or DEFAULT_SOURCE
    )
    cache_overrides, cache_errors = _parse_phase_cache(args.phase_cache)
    errors.extend(cache_errors)
    if errors:
        for err in errors:
            print(f"Error: {err}", file=sys.stderr)
        return 2

    iteration = IterationPolicy(
        min_rounds=1 if args.min_rounds is None else args.min_rounds,
        max_rounds=2 if args.max_rounds is None else args.max_rounds,
    ).normalized()

    run_dir = (
        Path(args.run_dir).resolve()
        if args.run_dir
        else root / ".solution-explorer" / "runs" / _run_stamp()
    )

    policy = LadderPolicy(
        models=models,
        iteration=iteration,
        max_cost_usd=args.max_cost_usd,
        pause_at_cost_usd=args.pause_at_cost_usd,
        threshold=args.threshold,
        max_parallel=max(1, int(args.max_parallel or 1)),
        retry_attempts=(
            4 if args.retry_attempts is None else max(1, int(args.retry_attempts))
        ),
        cache_policy=args.cache_policy,
        cache_policy_overrides=cache_overrides,
    )
    if args.max_wall_minutes is not None:
        policy.max_wall_minutes = args.max_wall_minutes
    if args.invoke_timeout_seconds is not None:
        policy.invoke_timeout_s = args.invoke_timeout_seconds
    if args.spot_check_fraction is not None:
        policy.spot_check_fraction = max(
            0.0, min(1.0, float(args.spot_check_fraction))
        )
    if args.max_spot_checks is not None:
        policy.max_spot_checks = max(1, int(args.max_spot_checks))
    config = LadderConfig(
        store_path=store_path,
        root=root,
        run_dir=run_dir,
        policy=policy,
        dry_run=args.dry_run,
        max_partitions=args.max_partitions,
        max_lines=args.max_lines,
        max_components=args.max_components,
        min_components=args.min_components,
    )

    result = run_ladder(config)

    print(f"Enrichment ladder run ({len(result.phases)} phases)")
    print(f"  run dir: {run_dir}")
    bound = ", ".join(f"{k}={models[k].label}" for k in sorted(models))
    print(f"  tier bindings: {bound}")
    for phase in result.phases:
        print(f"    {phase.name}: {phase.status.upper()}")
        for note in phase.notes[:5]:
            print(f"      - {note}")
    for note in result.notes:
        print(f"  note: {note}")
    if result.ledger:
        print(
            f"  invocations: {len(result.ledger)}, "
            f"cost: ${result.total_cost_usd:.4f} API-equivalent "
            "(metered against the owner's subscription, not money spent)"
        )
    if result.ceiling_hit:
        reason = getattr(result, "stop_reason", None) or "run ceiling reached"
        print(f"  note: {reason}; partial state reported honestly")
    if result.failed_phases:
        print(f"  FAILED phases: {result.failed_phases}")
    if not result.ok:
        return 1
    if args.dry_run:
        return 0
    # 2 remains configuration/usage failure throughout this command. Quality
    # incomplete is distinct so automation can tell "could not run" from "ran
    # but must not publish" without parsing prose.
    return 0 if getattr(result, "quality_ok", result.ok) else 3


def _run_stamp() -> str:
    """UTC timestamp for a default run directory name."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
