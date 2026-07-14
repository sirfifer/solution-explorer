"""Manifest projection: the split-mode entry document the viewer loads first.

``App.tsx`` fetches ``./architecture/manifest.json`` before falling back to a
monolithic ``./architecture.json``. The manifest carries everything except the
heavy ``symbols`` and ``files`` arrays (those move into the per-component detail
shards), plus:

  - ``component_detail_index``: id -> counts, so the viewer sizes the tabs
    before the lazy detail fetch (existing key);
  - ``coverage``: the ledger summary (new optional key, absorbing P4-4 item 1;
    old viewers ignore it).

Keys are written sorted so identical input yields byte-identical output
(invariant I4).
"""

from __future__ import annotations

import json
from pathlib import Path

from .activity import activity_manifest_summary
from .coverage import coverage_manifest_summary
from .details import write_detail_shards

__all__ = ["write_manifest_and_details"]


def write_manifest_and_details(
    arch: dict,
    output_dir: Path,
    *,
    coverage: dict | None = None,
    activity: dict | None = None,
    indent=2,
) -> Path:
    """Write ``manifest.json`` plus the detail shards. Return the manifest path.

    ``arch`` is the store-derived architecture dict (already carrying
    ``changelog`` / ``changelog_serial`` and filled environment fields). The
    detail writer strips symbols/files into shards; the manifest is the arch
    dict minus those two arrays, plus the detail index and coverage summary.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    detail_index = write_detail_shards(arch, output_dir, indent)

    manifest = {k: v for k, v in arch.items() if k not in ("symbols", "files")}
    manifest["component_detail_index"] = detail_index
    summary = coverage_manifest_summary(coverage)
    if summary is not None:
        manifest["coverage"] = summary
    activity_summary = activity_manifest_summary(activity)
    if activity_summary is not None:
        manifest["activity"] = activity_summary

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=indent, default=str, sort_keys=True)
    return manifest_path
