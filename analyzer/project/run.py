"""Opt-in v2 engine entry point: extract -> derive -> project.

Wired into analyzer/cli.py behind ``--engine v2`` (default stays ``v1``, the old
engine; no default behavior changes). This runs the full Program 2 pipeline:
Tier 1 extraction into an in-memory fact store, Tier 3 derivation, then Tier 4
projection to the same delivery artifacts the viewer already loads.

EXPERIMENTAL. The v2 engine is not the default and is not yet the cutover path
(that is P4-7). It exists so the projection tier can be driven end to end and
integration-tested against the real viewer build.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from .. import __version__
from ..derive import derive_all, derive_multi_from_config
from ..extract import extract_repo
from ..store import FactStore
from .pipeline import project_monolith, project_split


def run_v2(args) -> None:
    """Run the v2 pipeline from parsed CLI args (analyzer/cli.py ``main``)."""
    generated_at = datetime.now(timezone.utc).isoformat()
    indent = None if args.compact else 2

    store = None
    root = None
    if args.config:
        config_path = Path(args.config).resolve()
        if not config_path.exists():
            print(f"Error: Config file not found: {config_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Multi-repo mode (engine=v2): {config_path}")
        arch = derive_multi_from_config(config_path)
    else:
        root = Path(args.path).resolve()
        if not root.is_dir():
            print(f"Error: {root} is not a directory", file=sys.stderr)
            sys.exit(1)
        print(f"Scanning {root} (engine=v2)...")
        store = FactStore(":memory:")
        max_file_size = args.max_file_size if args.max_file_size else None
        extract_repo(root, store, max_file_size=max_file_size)
        _, arch = derive_all(store, root.name, root_path=str(root))

    if args.split:
        output_dir = (
            Path(args.output) if args.output != "architecture.json" else Path("architecture")
        )
        result = project_split(
            arch, output_dir, store=store, root=root,
            generated_at=generated_at, analyzer_version=__version__, indent=indent,
        )
        output_label = f"{output_dir}/"
    else:
        output_path = Path(args.output)
        result = project_monolith(
            arch, output_path, store=store, root=root,
            generated_at=generated_at, analyzer_version=__version__, indent=indent,
        )
        output_label = str(output_path)

    stats = arch.get("stats", {})
    print("\nAnalysis complete (engine=v2):")
    print(f"  Components: {stats.get('total_components', 0)}")
    print(f"  Files: {stats.get('total_files', 0)}")
    print(f"  Lines: {stats.get('total_lines', 0):,}")
    print(f"  Symbols: {stats.get('total_symbols', 0)}")
    print(f"  Relationships: {stats.get('total_relationships', 0)}")
    if result.coverage is not None:
        cov = result.coverage
        print(f"  Coverage: {cov['parsed']}/{cov['total']} parsed")
    print(f"\nOutput: {output_label}")
