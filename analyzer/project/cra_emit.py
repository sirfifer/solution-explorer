"""CRA readiness projection wiring (P10-4, Option C).

The projection tier calls ``emit_cra_readiness`` once per split or monolith run,
after the SBOM section is known. It:

  - runs the deterministic CRA-readiness checks against the scan root and the
    P10-1 supply_chain section;
  - writes a versioned, byte-stable ``cra-readiness.json`` beside sbom.json and
    ai.json (the standard per-projection artifact convention);
  - returns the findings for the ABSENT items so the pipeline can merge them
    into the existing findings surface (no new view).

Returns None (no file written, no findings) when there is no scan root (a
multi-repo top-level projection; per-member checklists come from each member's
own projection), matching sbom_emit. Determinism (invariant I4): the artifact
carries no clock and no random source, so it is byte-identical across runs on the
same repository state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..cra import build_cra_readiness

__all__ = ["emit_cra_readiness", "CRA_FILENAME", "CraEmitResult"]

CRA_FILENAME = "cra-readiness.json"


class CraEmitResult:
    """What one CRA emission yielded: the artifact path and the gap findings."""

    def __init__(self, artifact_path: Path, findings: list[dict]):
        self.artifact_path = artifact_path
        self.findings = findings


def emit_cra_readiness(
    output_dir: Path,
    *,
    root=None,
    supply_chain: Optional[dict] = None,
    indent=2,
) -> Optional[CraEmitResult]:
    """Build the checklist, write ``cra-readiness.json``, return the gap findings.

    ``supply_chain`` is the P10-1 supply_chain section (or None when no SBOM was
    emitted); it feeds the SBOM-present check. ``output_dir`` is the projection
    root (beside manifest.json in split mode, the parent of architecture.json in
    monolith mode).
    """
    if root is None:
        return None
    readiness = build_cra_readiness(Path(root), supply_chain=supply_chain)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / CRA_FILENAME
    with open(artifact_path, "w", encoding="utf-8") as fh:
        json.dump(readiness.to_artifact(), fh, indent=indent, default=str, sort_keys=True)

    return CraEmitResult(artifact_path, readiness.findings())
