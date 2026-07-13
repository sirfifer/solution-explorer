"""Per-component detail shards (the windowed-loading delivery format).

Mirrors the shape analyzer/cli.py ``write_split`` emits so the existing viewer
loads them unchanged: one ``detail-<safe_id>.json`` per component under
``data/``, each ``{"symbols": [...], "files": [...]}``, plus a
``component_detail_index`` (id -> counts) that rides in the manifest. Stale
detail files from a previous, different dataset in the same directory are
pruned (F-AN-10 / P2-7 item 6), which the old writer only gained on the
``--split`` default path.

Symbols and files are looked up from the store-derived arch dict's top-level
``symbols`` and ``files`` arrays; components own files by path, files own
symbols by id, exactly as the old writer resolves them.
"""

from __future__ import annotations

import json
from pathlib import Path

from .naming import safe_component_id

__all__ = ["write_detail_shards"]


def write_detail_shards(arch: dict, output_dir: Path, indent) -> dict:
    """Write per-component detail shards and return the ``component_detail_index``.

    The index maps component id -> ``{"symbolCount", "fileCount"}``. Traversal
    is the component tree in stored order (deterministic). Symbols per component
    are the union of their files' symbol-id lists, sorted for stable output.
    """
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    all_file_paths = {f["path"]: f for f in arch.get("files", [])}
    all_symbol_ids = {s["id"]: s for s in arch.get("symbols", [])}

    detail_index: dict = {}
    written: set[str] = set()

    def process(components: list) -> None:
        for comp in components:
            comp_id = comp["id"]
            safe_id = safe_component_id(comp_id)

            comp_files = [
                all_file_paths[fp]
                for fp in comp.get("files", [])
                if fp in all_file_paths
            ]

            file_symbol_ids: set[str] = set()
            for f in comp_files:
                file_symbol_ids.update(f.get("symbols", []))
            # Sort by id so the shard is byte-stable regardless of the set's
            # iteration order (invariant I4; no PYTHONHASHSEED dependence).
            comp_symbols = [
                all_symbol_ids[sid]
                for sid in sorted(file_symbol_ids)
                if sid in all_symbol_ids
            ]

            detail_index[comp_id] = {
                "symbolCount": len(comp_symbols),
                "fileCount": len(comp_files),
            }

            detail = {"symbols": comp_symbols, "files": comp_files}
            detail_path = data_dir / f"detail-{safe_id}.json"
            written.add(detail_path.name)
            with open(detail_path, "w", encoding="utf-8") as fh:
                json.dump(detail, fh, indent=indent, default=str, sort_keys=True)

            process(comp.get("children", []))

    process(arch.get("components", []))

    # Prune stale detail files (only detail-*.json directly under data/ that are
    # absent from this dataset). Nothing else in the tree is touched.
    for stale in sorted(data_dir.glob("detail-*.json")):
        if stale.name not in written:
            try:
                stale.unlink()
            except OSError:
                pass

    return detail_index
