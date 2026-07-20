"""CRA readiness checklist for a projected repository (P10-4, Option C).

The owner's decision (see docs/remediation/CRA-EVALUATION.md): solution-explorer
is an evidence contributor to an EU Cyber Resilience Act technical file, not a
compliance system of record. So this module builds a truthful checklist, never a
dashboard, a score, or a red/green verdict (VISION.md No theater).

One collection pass over the repository plus the P10-1 supply_chain section
yields a ``CraReadiness``: a flat list of deterministic presence/absence items,
each with an evidence pointer or an explicit gap and a short CRA-clause
reference. Two artifacts fall out of it:

  - ``cra-readiness.json`` (versioned, byte-stable) beside sbom.json and ai.json,
    the portable structured readiness object;
  - findings for the ABSENT items only, joined into the existing findings surface
    so no new view is added.

The projection tier wires both in through ``analyzer/project/cra_emit.py``.
"""

from __future__ import annotations

from .checks import build_cra_readiness
from .models import (
    CRA_READINESS_VERSION,
    CRA_SCOPE,
    STATUS_ABSENT,
    STATUS_NOT_APPLICABLE,
    STATUS_PRESENT,
    CraItem,
    CraReadiness,
)

__all__ = [
    "build_cra_readiness",
    "CraReadiness",
    "CraItem",
    "CRA_READINESS_VERSION",
    "CRA_SCOPE",
    "STATUS_PRESENT",
    "STATUS_ABSENT",
    "STATUS_NOT_APPLICABLE",
]
