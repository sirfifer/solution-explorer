"""Command-line interface for the architecture analyzer."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

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

    args = parser.parse_args()

    # Determine max_symbols default based on mode
    if args.max_symbols is None:
        args.max_symbols = 0 if args.split else 5000

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

    # Write output
    indent = None if args.compact else 2

    if args.split:
        output_dir = Path(args.output) if args.output != "architecture.json" else Path("architecture")
        write_split(arch, output_dir, indent)
        output_label = f"{output_dir}/"
    else:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(asdict(arch), f, indent=indent, default=str)
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


def write_split(arch, output_dir: Path, indent):
    """Write split output: manifest.json + per-component detail files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)

    arch_dict = asdict(arch)

    # Build lookup tables for files and symbols
    all_file_paths = {f["path"]: f for f in arch_dict.get("files", [])}
    all_symbol_ids = {s["id"]: s for s in arch_dict.get("symbols", [])}

    detail_index = {}

    def process_components(components):
        for comp in components:
            comp_id = comp["id"]
            safe_id = comp_id.replace("/", "--")

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
            with open(detail_path, "w", encoding="utf-8") as f:
                json.dump(detail, f, indent=indent, default=str)

            # Recurse into children
            process_components(comp.get("children", []))

    process_components(arch_dict["components"])

    # Build manifest (everything except symbols and files arrays)
    manifest = {k: v for k, v in arch_dict.items() if k not in ("symbols", "files")}
    manifest["component_detail_index"] = detail_index

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=indent, default=str)

    print(f"  Manifest: {manifest_path}")
    print(f"  Detail files: {len(detail_index)}")


if __name__ == "__main__":
    main()
