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

from .engine import DEFAULT_MAX_PARALLEL, DEFAULT_MODEL, EnhanceConfig, run_enhance

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
        if p.status == "failed":
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
