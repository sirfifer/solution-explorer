"""Prebuilt search shards (TARGET-ARCHITECTURE.md 4.4; consumed by the viewer in P6-4).

The current viewer builds its search index in the browser from whatever is
loaded, so search "only finds identifiers" and split-mode symbols are
unsearchable until their component is visited. The fix is to emit the index at
projection time, covering:

  - component names, paths, and descriptions,
  - file paths and module docs,
  - symbol names and docstrings,
  - AI enrichment help text.

Entries are sorted by ``(ref_kind, ref_id)`` and chunked into fixed-size shards
so the viewer loads them lazily and the output is byte-identical run to run
(invariant I4). A ``search/manifest.json`` lists the shards and per-kind counts.

Both channels of enrichment are covered: help text inlined on arch components
(``ai_enhance.help_text``, the monolithic AI-baseline shape) and help text in
the store's ``enrichment`` rows (the Tier 2 overlay). Neither exists on the
parity fixtures, so the channel is empty there and exercised by unit tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

__all__ = ["build_search_entries", "shard_entries", "write_search_shards", "DEFAULT_SHARD_SIZE"]

DEFAULT_SHARD_SIZE = 2000
_MAX_TEXT = 2000  # cap free text per entry so shards stay bounded


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return " ".join(str(text).split())[:_MAX_TEXT]


def _component_file_owner(components: list) -> dict[str, str]:
    """Map file path -> owning component id (first owner wins, tree order)."""
    owner: dict[str, str] = {}

    def walk(comps: list) -> None:
        for comp in comps:
            cid = comp["id"]
            for fp in comp.get("files", []):
                owner.setdefault(fp, cid)
            walk(comp.get("children", []))

    walk(components)
    return owner


def _iter_components(components: list):
    for comp in components:
        yield comp
        yield from _iter_components(comp.get("children", []))


def build_search_entries(arch: dict, store=None) -> list[dict]:
    """Build the flat, deduplicated, sorted list of search entries.

    Each entry is ``{ref_kind, ref_id, name, path, component, text}``. The list
    is sorted by ``(ref_kind, ref_id)`` for determinism.
    """
    entries: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(ref_kind: str, ref_id: str, name: str, path: str, component: str, text: str) -> None:
        key = (ref_kind, ref_id)
        if key in seen:
            return
        seen.add(key)
        entries.append({
            "ref_kind": ref_kind,
            "ref_id": ref_id,
            "name": name or "",
            "path": path or "",
            "component": component or "",
            "text": _clean(text),
        })

    components = arch.get("components", [])
    owner = _component_file_owner(components)

    # Store enrichment is CANONICAL, so it is added FIRST: `add` keeps the first
    # entry per (ref_kind, ref_id), so a store enrichment row wins over any
    # inline ai_enhance help text carried on the same target. This reverses the
    # P4-5 Discovered dedupe (where inline won because components were processed
    # first); the store overlay is now the source of truth (P7-1).
    if store is not None:
        for row in store.enrichment():
            payload = row.get("payload") or {}
            help_text = payload.get("help_text") if isinstance(payload, dict) else None
            if help_text:
                ref = f"{row['target_kind']}:{row['target_id']}"
                add("enrichment", ref, "", "", row["target_id"], help_text)

    for comp in _iter_components(components):
        cid = comp["id"]
        desc = comp.get("description")
        if not desc:
            docs = comp.get("docs") or {}
            desc = docs.get("purpose")
        add("component", cid, comp.get("name", cid), comp.get("path", ""), cid, desc or "")

        # Enrichment help text inlined on the component (monolithic AI baseline).
        # Falls back to the store row above on a (ref_kind, ref_id) collision.
        ai = comp.get("ai_enhance") or {}
        help_text = ai.get("help_text")
        if help_text:
            add("enrichment", f"component:{cid}", comp.get("name", cid),
                comp.get("path", ""), cid, help_text)

    for f in arch.get("files", []):
        path = f["path"]
        name = path.rsplit("/", 1)[-1]
        add("file", path, name, path, owner.get(path, ""), f.get("module_doc") or "")

    for s in arch.get("symbols", []):
        sid = s["id"]
        fpath = s.get("file", "")
        add("symbol", sid, s.get("name", ""), fpath, owner.get(fpath, ""),
            s.get("docstring") or "")

    entries.sort(key=lambda e: (e["ref_kind"], e["ref_id"]))
    return entries


def shard_entries(entries: list[dict], shard_size: int = DEFAULT_SHARD_SIZE) -> dict:
    """Split entries into fixed-size shards. Return a manifest-plus-shards dict.

    Returns ``{"manifest": {...}, "shards": {filename: [entries]}}``. Shard
    filenames are zero-padded and stable given the sorted entry order.
    """
    if shard_size < 1:
        raise ValueError("shard_size must be >= 1")

    by_kind: dict[str, int] = {}
    for e in entries:
        by_kind[e["ref_kind"]] = by_kind.get(e["ref_kind"], 0) + 1

    shards: dict[str, list[dict]] = {}
    names: list[str] = []
    for i in range(0, len(entries), shard_size):
        name = f"search-{i // shard_size:04d}.json"
        shards[name] = entries[i:i + shard_size]
        names.append(name)

    manifest = {
        "version": 1,
        "shard_size": shard_size,
        "total": len(entries),
        "by_kind": dict(sorted(by_kind.items())),
        "fields": ["ref_kind", "ref_id", "name", "path", "component", "text"],
        "shards": names,
    }
    return {"manifest": manifest, "shards": shards}


def write_search_shards(
    arch: dict,
    output_dir: Path,
    *,
    store=None,
    shard_size: int = DEFAULT_SHARD_SIZE,
    indent=2,
) -> dict:
    """Emit ``search/manifest.json`` and ``search/search-*.json``. Return the manifest."""
    output_dir = Path(output_dir)
    search_dir = output_dir / "search"
    search_dir.mkdir(parents=True, exist_ok=True)

    entries = build_search_entries(arch, store)
    bundle = shard_entries(entries, shard_size)

    # Remove stale shards from a previous, larger dataset in this directory.
    keep = set(bundle["shards"]) | {"manifest.json"}
    for stale in sorted(search_dir.glob("search-*.json")):
        if stale.name not in keep:
            try:
                stale.unlink()
            except OSError:
                pass

    for name, shard in bundle["shards"].items():
        with open(search_dir / name, "w", encoding="utf-8") as fh:
            json.dump(shard, fh, indent=indent, default=str, sort_keys=True)

    with open(search_dir / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(bundle["manifest"], fh, indent=indent, default=str, sort_keys=True)

    return bundle["manifest"]
