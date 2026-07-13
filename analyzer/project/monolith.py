"""Monolithic ``architecture.json`` projection (small repos, backward compat).

TARGET-ARCHITECTURE.md 4.4: "The monolithic architecture.json remains available
as a projection for small repos and backward compatibility." App.tsx falls back
to ``./architecture.json`` when no manifest is present, and loads its inline
``symbols`` / ``files`` arrays directly.

This is the same store-derived arch dict the split path uses, written whole,
with the coverage ledger embedded (summary plus full rows, cheap at small-repo
scale) so a single-file consumer still sees coverage. Old viewers ignore the
extra key.
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = ["write_monolith"]


def write_monolith(
    arch: dict,
    output_path: Path,
    *,
    coverage: dict | None = None,
    indent=2,
) -> Path:
    """Write the whole arch dict to ``output_path``. Return the path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = dict(arch)
    if coverage is not None:
        doc["coverage"] = coverage

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=indent, default=str, sort_keys=True)
    return output_path
