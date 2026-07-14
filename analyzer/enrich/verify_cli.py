"""The `verify` subcommand: Phase 7 edge verification (P7-3; extended by P7-4).

Entry shape (recorded in TASKS.md), dispatched from ``analyzer/cli.py:main`` on
the first CLI token so ``analyze.py`` stays the single entrypoint:

    analyze.py verify <edges> [root] --store <db> [options]

`verify edges` runs the inferred-edge verification pass (P7-3). P7-4 adds the
`intents` and `findings` verify targets and a sibling `name concerns` command.
The pass honors the P7-2 cost-control patterns: ``--max-targets`` bounds
invocations, ``--dry-run`` invokes nothing, the exit code reflects failure, and
nothing is written unless it validates.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .engine import DEFAULT_MODEL
from .passes import VerifyConfig, verify_edges

DEFAULT_STORE_RELPATH = Path(".solution-explorer") / "index.db"

_VERIFY_TARGETS = ("edges",)


def _base_parser(prog: str, targets: tuple[str, ...], target_help: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("target", choices=targets, help=target_help)
    parser.add_argument("root", nargs="?", default=".", help="Repository root the store indexes (default: current directory).")
    parser.add_argument("--store", default=None, help="Path to the v2 fact store (default: <root>/.solution-explorer/index.db).")
    parser.add_argument("--update", action="store_true", help="Re-process only stale or missing targets (staleness from provenance).")
    parser.add_argument("--max-targets", type=int, default=None, help="Cap the number of targets processed (cost control).")
    parser.add_argument("--max-parallel", type=int, default=4, help="Reserved for parallel invocation (default: 4).")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model for the pass (default: {DEFAULT_MODEL}).")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without invoking the model.")
    parser.add_argument("--report", default=None, help="Write the machine-readable run report to this JSON file.")
    return parser


def _resolve_store(args) -> tuple[Path, Path]:
    root = Path(args.root).resolve()
    store_path = Path(args.store).resolve() if args.store else root / DEFAULT_STORE_RELPATH
    return root, store_path


def _config(args, root: Path, store_path: Path, **extra) -> VerifyConfig:
    return VerifyConfig(
        store_path=store_path,
        root=root,
        update=args.update,
        max_targets=args.max_targets,
        max_parallel=args.max_parallel,
        model=args.model,
        dry_run=args.dry_run,
        report_path=Path(args.report).resolve() if args.report else None,
        **extra,
    )


def _print_report(report) -> None:
    print(f"{report.pass_name} ({report.mode} mode, {report.target_count} target(s))")
    for note in report.notes:
        print(f"  note: {note}")
    if report.dry_run:
        print(f"  dry run: no model invoked; {len(report.plan_preview)} prompt(s) planned")
        return
    tally = report.tally()
    if tally:
        print("  verdicts: " + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))
    print(f"  done: {report.done}, failed: {len(report.failed)}")
    if report.total_cost_usd:
        print(f"  cost: ${report.total_cost_usd:.4f}")
    if report.failed:
        print(f"  FAILED targets: {report.failed}")


def _run_and_report(reports) -> int:
    ok = True
    for report in reports:
        _print_report(report)
        ok = ok and report.ok
    return 0 if ok else 1


def _preflight(args) -> tuple[Path, Path]:
    root, store_path = _resolve_store(args)
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        raise SystemExit(2)
    if not store_path.exists():
        print(
            f"Error: fact store not found at {store_path}. Run "
            f"`python3 analyze.py {args.root} --store {store_path}` first to build it.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return root, store_path


def verify_main(argv: list[str]) -> int:
    parser = _base_parser("analyze.py verify", _VERIFY_TARGETS, "what to verify")
    args = parser.parse_args(argv)
    root, store_path = _preflight(args)
    reports = [verify_edges(_config(args, root, store_path))]
    return _run_and_report(reports)
