"""Command-line interface for the architecture analyzer."""

import argparse
import json
import sys
from pathlib import Path

from .models import to_dict
from .multi_repo import MultiRepoOrchestrator
from .scanner import ArchitectureScanner


def main():
    parser = argparse.ArgumentParser(
        description="Analyze codebase architecture and generate interactive visualization data."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to the repository root (default: current directory)",
    )
    parser.add_argument(
        "-o", "--output",
        default="architecture.json",
        help="Output JSON file path (default: architecture.json)",
    )
    parser.add_argument(
        "--max-file-size",
        type=int,
        default=500_000,
        help="Maximum file size to analyze in bytes (default: 500KB)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print JSON output (default: true)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Compact JSON output (overrides --pretty)",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=None,
        help="Maximum number of symbols to include (default: 5000 in single-file mode, unlimited in split mode; 0=unlimited)",
    )
    parser.add_argument(
        "--preview-lines",
        type=int,
        default=5,
        help="Max lines for code previews (default: 5)",
    )
    parser.add_argument(
        "--split",
        action="store_true",
        help="Output split files (manifest.json + per-component detail files) for lazy loading",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to solution-explorer.json for multi-repo analysis",
    )
    parser.add_argument(
        "--engine",
        choices=("v1", "v2"),
        default="v1",
        help="Analysis engine: v1 (default, current) or v2 (EXPERIMENTAL: "
             "extract/derive/project tiers). v2 does not change any v1 default.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate architecture data and report issues (requires pydantic)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Run incremental analysis with diff metadata against a baseline",
    )
    parser.add_argument(
        "--base-sha",
        default="",
        help="Base git commit SHA for incremental diff (default: empty, triggers full rescan)",
    )
    parser.add_argument(
        "--head-sha",
        default="HEAD",
        help="Head git commit SHA for incremental diff (default: HEAD)",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="Path to previous architecture.json baseline for diff comparison",
    )

    args = parser.parse_args()

    # Reject silently-ignored flag combinations. Previously the --incremental
    # branch returned before split handling (so --split was dropped) and
    # --config took precedence over --incremental with no warning (F-AN-9).
    if args.incremental and args.split:
        parser.error(
            "--incremental cannot be combined with --split; incremental mode "
            "writes a single architecture.json with diff metadata"
        )
    if args.config and args.incremental:
        parser.error(
            "--config (multi-repo) cannot be combined with --incremental; "
            "run one mode at a time"
        )

    # Opt-in v2 engine (EXPERIMENTAL). Routed before any v1 setup so it cannot
    # change a v1 default. Incremental v2 is P4-6; until then --engine v2 runs
    # the full extract/derive/project pipeline (no incremental path).
    if args.engine == "v2":
        if args.incremental:
            parser.error("--engine v2 does not support --incremental yet (P4-6)")
        from .project.run import run_v2

        run_v2(args)
        return

    # Determine max_symbols default based on mode
    if args.max_symbols is None:
        args.max_symbols = 0 if args.split else 5000

    scanner = None
    if args.config:
        config_path = Path(args.config).resolve()
        if not config_path.exists():
            print(f"Error: Config file not found: {config_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Multi-repo mode: {config_path}")
        orchestrator = MultiRepoOrchestrator(
            config_path,
            max_file_size=args.max_file_size,
            max_symbols=args.max_symbols,
            preview_lines=args.preview_lines,
        )
        arch = orchestrator.run()
    elif args.incremental:
        from .incremental import IncrementalAnalyzer, save_baseline_cache

        root = Path(args.path).resolve()
        if not root.is_dir():
            print(f"Error: {root} is not a directory", file=sys.stderr)
            sys.exit(1)

        # Resolve baseline path
        baseline_path = None
        if args.baseline:
            baseline_path = Path(args.baseline)
        else:
            default_baseline = root / ".arch-baseline" / "architecture.json"
            if default_baseline.is_file():
                baseline_path = default_baseline

        max_symbols = args.max_symbols if args.max_symbols is not None else 0

        print(f"Incremental scan: {root}")
        analyzer = IncrementalAnalyzer(
            root,
            base_sha=args.base_sha,
            head_sha=args.head_sha,
            baseline_path=baseline_path,
            max_file_size=args.max_file_size,
            max_symbols=max_symbols,
            preview_lines=args.preview_lines,
        )
        arch_dict = analyzer.run()

        # Write output
        indent = None if args.compact else 2
        output_path = Path(args.output)
        if str(args.output).endswith("/") or output_path.is_dir():
            output_path = output_path / "architecture.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(arch_dict, f, indent=indent, default=str)

        # Validate if requested
        if args.validate:
            from types import SimpleNamespace

            from .models import _validate_cross_refs

            ns = SimpleNamespace(
                components=arch_dict.get("components", []),
                relationships=arch_dict.get("relationships", []),
            )
            errors = _validate_cross_refs(ns)
            if errors:
                print(
                    f"\nValidation found {len(errors)} issue(s):",
                    file=sys.stderr,
                )
                for err in errors:
                    print(f"  - {err}", file=sys.stderr)
            else:
                print("\nValidation passed: all cross-references valid.")

        # Save baseline with cache files for next run
        baseline_dir = root / ".arch-baseline"
        save_baseline_cache(arch_dict, baseline_dir, root)

        stats = arch_dict.get("stats", {})
        incr = arch_dict.get("incremental", {})
        diff = incr.get("diff", {})
        print("\nAnalysis complete:")
        print(f"  Components: {stats.get('total_components', 0)}")
        print(f"  Files: {stats.get('total_files', 0)}")
        print(f"  Lines: {stats.get('total_lines', 0):,}")
        print(f"  Full rescan: {incr.get('full_rescan', True)}")
        print(f"  Components added: {len(diff.get('components_added', []))}")
        print(f"  Components modified: {len(diff.get('components_modified', []))}")
        print(f"  Components removed: {len(diff.get('components_removed', []))}")
        print(f"\nOutput: {output_path}")
        print(f"Baseline saved: {baseline_dir}")
        return
    else:
        root = Path(args.path).resolve()
        if not root.is_dir():
            print(f"Error: {root} is not a directory", file=sys.stderr)
            sys.exit(1)

        print(f"Scanning {root}...")
        scanner = ArchitectureScanner(
            root,
            max_file_size=args.max_file_size,
            max_symbols=args.max_symbols,
            preview_lines=args.preview_lines,
        )
        arch = scanner.scan()

    # Validate if requested
    if args.validate:
        errors = arch.validate_cross_references()
        if errors:
            print(f"\nValidation found {len(errors)} issue(s):", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
        else:
            print("\nValidation passed: all cross-references valid.")

    # Convert to dict and apply changelog
    arch_dict = to_dict(arch)
    indent = None if args.compact else 2

    if args.split:
        output_dir = Path(args.output) if args.output != "architecture.json" else Path("architecture")
        manifest_path = output_dir / "manifest.json"
        _apply_changelog(arch_dict, manifest_path)
        write_split(arch_dict, output_dir, indent)
        output_label = f"{output_dir}/"
    else:
        output_path = Path(args.output)
        _apply_changelog(arch_dict, output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(arch_dict, f, indent=indent, default=str)
        output_label = str(output_path)

    stats = arch.stats
    print("\nAnalysis complete:")
    print(f"  Components: {stats['total_components']}")
    print(f"  Files: {stats['total_files']}")
    print(f"  Lines: {stats['total_lines']:,}")
    print(f"  Symbols: {stats['total_symbols']}")
    print(f"  Relationships: {stats['total_relationships']}")
    print(f"  Languages: {', '.join(f'{k} ({v:,} lines)' for k, v in sorted(stats['languages'].items(), key=lambda x: -x[1]))}")
    print(f"\nOutput: {output_label}")

    if scanner is not None:
        _warn_dropped_data(scanner)


def _warn_dropped_data(scanner: ArchitectureScanner) -> None:
    """Print a prominent stderr warning when the scan silently dropped data.

    Covers the two single-file-mode truncation paths from F-AN-3: the symbol cap
    (`--max-symbols`) and files skipped for exceeding `--max-file-size`. Each
    warning names the count dropped and the flag that lifts the cap. Split mode
    runs uncapped by default, so `dropped_symbols` is 0 there and this stays quiet.
    """
    if scanner.dropped_symbols > 0:
        detected = scanner.dropped_symbols + scanner.max_symbols
        print(
            f"\nWARNING: symbol cap dropped {scanner.dropped_symbols:,} of "
            f"{detected:,} detected symbols from the output "
            f"(kept {scanner.max_symbols:,}).\n"
            f"         The viewer will not show the dropped symbols. "
            f"Re-run with --max-symbols 0 (unlimited) or --split for full coverage.",
            file=sys.stderr,
        )

    if scanner.skipped_large_files:
        count = len(scanner.skipped_large_files)
        largest = max(scanner.skipped_large_files, key=lambda f: f[1])
        print(
            f"\nWARNING: skipped {count:,} file(s) larger than "
            f"{scanner.max_file_size:,} bytes; their symbols are missing from the output.\n"
            f"         Largest skipped: {largest[0]} ({largest[1]:,} bytes).\n"
            f"         Re-run with a higher --max-file-size to include them.",
            file=sys.stderr,
        )


def _apply_changelog(arch_dict: dict, output_path: Path) -> None:
    """Add changelog to arch_dict by diffing against previous output if it exists.

    For non-incremental scans, we load the previous architecture.json at the
    output path (if any) as a baseline, compute a diff, and append a changelog
    entry. If no previous file exists, this is an initial scan.
    """
    from .incremental import IncrementalAnalyzer

    baseline = None
    if output_path.is_file():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                baseline = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    # Use a lightweight stub to access the diff/changelog methods
    analyzer = object.__new__(IncrementalAnalyzer)
    analyzer.head_sha = ""

    diff_summary = analyzer.compute_diff_summary(baseline, arch_dict)
    scan_type = "initial" if baseline is None else "full"
    prev_serial = (baseline or {}).get("changelog_serial", 0)
    entry = analyzer.build_changelog_entry(
        diff_summary, baseline, arch_dict, scan_type, prev_serial + 1
    )
    IncrementalAnalyzer._append_changelog(arch_dict, entry, baseline)


def safe_component_id(comp_id: str) -> str:
    """Make a component ID safe for use as a filename on NTFS and GitHub artifacts.

    GitHub's actions/upload-artifact rejects filenames containing any of:
    " : < > | * ? \\r \\n (NTFS-incompatible characters). Component IDs like
    "repo:unamentis" (from multi-repo mode) hit this. Viewer's loadComponentDetail
    must use the same escape scheme.
    """
    return (
        comp_id.replace("/", "--")
        .replace(":", "__")
    )


def write_split(arch_dict: dict, output_dir: Path, indent):
    """Write split output: manifest.json + per-component detail files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)

    # Build lookup tables for files and symbols
    all_file_paths = {f["path"]: f for f in arch_dict.get("files", [])}
    all_symbol_ids = {s["id"]: s for s in arch_dict.get("symbols", [])}

    detail_index = {}
    written_detail_files: set[str] = set()

    def process_components(components):
        for comp in components:
            comp_id = comp["id"]
            safe_id = safe_component_id(comp_id)

            # Collect files for this component
            comp_files = [all_file_paths[fp] for fp in comp.get("files", []) if fp in all_file_paths]

            # Collect symbols for these files
            file_symbol_ids = set()
            for f in comp_files:
                file_symbol_ids.update(f.get("symbols", []))
            comp_symbols = [all_symbol_ids[sid] for sid in file_symbol_ids if sid in all_symbol_ids]

            detail_index[comp_id] = {
                "symbolCount": len(comp_symbols),
                "fileCount": len(comp_files),
            }

            # Write detail file
            detail = {
                "symbols": comp_symbols,
                "files": comp_files,
            }
            detail_path = data_dir / f"detail-{safe_id}.json"
            written_detail_files.add(detail_path.name)
            with open(detail_path, "w", encoding="utf-8") as f:
                json.dump(detail, f, indent=indent, default=str)

            # Recurse into children
            process_components(comp.get("children", []))

    process_components(arch_dict["components"])

    # Prune stale detail files left by a previous, different dataset in this
    # directory. The guard is strict: only files matching the detail-*.json
    # pattern directly inside data/ are considered, and only those absent from
    # the current manifest are removed. Nothing else in the output tree is
    # touched (F-AN-10).
    pruned = 0
    for stale in data_dir.glob("detail-*.json"):
        if stale.name not in written_detail_files:
            try:
                stale.unlink()
                pruned += 1
            except OSError:
                pass

    # Build manifest (everything except symbols and files arrays)
    manifest = {k: v for k, v in arch_dict.items() if k not in ("symbols", "files")}
    manifest["component_detail_index"] = detail_index

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=indent, default=str)

    print(f"  Manifest: {manifest_path}")
    print(f"  Detail files: {len(detail_index)}")
    if pruned:
        print(f"  Pruned stale detail files: {pruned}")


if __name__ == "__main__":
    main()
