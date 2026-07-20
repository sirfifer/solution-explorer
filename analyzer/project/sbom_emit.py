"""SBOM projection wiring (P10-1): emit sbom.json and the supply_chain section.

The projection tier calls ``emit_sbom`` once per split or monolith run. It:

  - collects the supply chain from the scan root (deterministic manifest parsing,
    no package-manager execution, no network) plus the vendored directories the
    coverage inventory already found;
  - writes a CycloneDX 1.5 ``sbom.json`` beside the manifest / architecture.json
    (the standard interchange artifact), byte-stable;
  - returns the compact, viewer-native ``supply_chain`` section, which the
    pipeline stamps onto the projected arch so it rides in the manifest (split)
    and the monolith automatically (both read ``arch`` keys).

Returns None (no file written, no section) when there is no scan root (a
multi-repo top-level projection; per-member SBOMs come from each member's own
projection) or the repository carries no manifests. Determinism is invariant I4:
the only time value written is the projection's injected ``generated_at``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..sbom import build_cyclonedx, collect_supply_chain

__all__ = ["emit_sbom", "SBOM_FILENAME"]

SBOM_FILENAME = "sbom.json"


def emit_sbom(
    arch: dict,
    output_dir: Path,
    *,
    root=None,
    coverage: Optional[dict] = None,
    generated_at: Optional[str] = None,
    indent=2,
) -> Optional[dict]:
    """Collect the SBOM, write ``sbom.json`` into ``output_dir``, return the section.

    ``arch`` supplies the component name for the CycloneDX metadata component.
    ``coverage`` is the projection's coverage dict; its non-source inventory
    feeds the vendored references. ``output_dir`` is the projection root (beside
    ``manifest.json`` in split mode, the parent of ``architecture.json`` in
    monolith mode).
    """
    if root is None:
        return None
    supply = collect_supply_chain(Path(root), coverage=coverage)
    if supply is None:
        return None

    component_name = arch.get("name") or Path(root).name
    document = build_cyclonedx(
        supply, component_name=component_name, generated_at=generated_at
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    sbom_path = output_dir / SBOM_FILENAME
    with open(sbom_path, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=indent, default=str, sort_keys=True)

    return supply.to_section()
