"""Software Bill of Materials for a projected repository (P10-1, VISION.md).

The owner's hard requirement: every Solution Explorer site ships an accurate,
complete SBOM. All dependencies with versions and pin status, plus the
language-specific target/SDK versions surfaced separately, built deterministically
by parsing manifests and lockfiles only (no package-manager execution, no
network).

Two artifacts fall out of one collection pass:

  - a CycloneDX 1.5 JSON document (``sbom.json``), the standard interchange
    format, byte-stable with a content-derived serial number;
  - a compact, viewer-native ``supply_chain`` section carried in the projection
    manifest, so the viewer renders a supply chain surface without parsing
    CycloneDX.

``collect_supply_chain`` walks a repository and returns the aggregated
``SupplyChain``; ``build_cyclonedx`` turns it into the CycloneDX document. The
projection tier wires both in through ``analyzer/project/sbom_emit.py``.
"""

from __future__ import annotations

from .collector import SUPPLY_CHAIN_VERSION, SupplyChain, collect_supply_chain
from .cyclonedx import BOM_FORMAT, SPEC_VERSION, build_cyclonedx
from .models import Dependency, ParseWarning, Target

__all__ = [
    "collect_supply_chain",
    "build_cyclonedx",
    "SupplyChain",
    "SUPPLY_CHAIN_VERSION",
    "SPEC_VERSION",
    "BOM_FORMAT",
    "Dependency",
    "Target",
    "ParseWarning",
]
