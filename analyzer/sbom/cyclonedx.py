"""CycloneDX 1.5 JSON emission from a collected SupplyChain (P10-1).

CycloneDX is the interchange SBOM format; emitting it makes the tool's inventory
consumable by any SBOM tooling. This builds a 1.5 document deterministically:

  - ``specVersion`` is pinned to 1.5 and ``bomFormat`` to CycloneDX;
  - the metadata component is the repository itself (type application), carrying
    the language target/SDK versions as CycloneDX ``properties`` so a standard
    consumer sees requires-python / node engines / swift-tools-version too;
  - each dependency is a component (type library) with its name, resolved version
    when known, a purl when derivable, and properties recording pin status,
    scope, ecosystem, and evidence;
  - vendored directories are components (type library) with an evidence property;
  - the ``serialNumber`` is a content-derived ``urn:uuid`` (a UUIDv5 over the
    component identities) so two runs on the same inputs are byte-identical, with
    no random serial and no per-run timestamp beyond the projection's injected
    ``generated_at``.

No clock, no randomness: determinism is invariant I4.
"""

from __future__ import annotations

import uuid
from typing import Optional

from .collector import SupplyChain

__all__ = ["build_cyclonedx", "SPEC_VERSION", "BOM_FORMAT"]

SPEC_VERSION = "1.5"
BOM_FORMAT = "CycloneDX"

# A fixed namespace UUID so the content-derived serial number is reproducible.
# Derived once from the project name; never regenerated.
_SERIAL_NAMESPACE = uuid.UUID("5f3e9a1c-8b7d-4e2a-9c6f-1d0b2a3c4d5e")

# The property namespace for the tool's own non-standard fields on CycloneDX
# components and metadata.
_PROP = "solution_explorer"


def build_cyclonedx(
    supply: SupplyChain,
    *,
    component_name: str,
    generated_at: Optional[str] = None,
) -> dict:
    """Build the CycloneDX 1.5 document dict for ``supply``.

    ``component_name`` names the metadata (root) component, normally the repo
    name. ``generated_at`` is the projection's injected timestamp; it is the only
    time value in the document, so byte output is stable when it is held fixed.
    """
    components: list[dict] = []
    for dep in supply.dependencies:
        components.append(_dependency_component(dep))
    for vendored in supply.vendored:
        components.append(_vendored_component(vendored))

    metadata: dict = {
        "component": _metadata_component(component_name, supply),
    }
    if generated_at:
        metadata["timestamp"] = generated_at

    doc = {
        "bomFormat": BOM_FORMAT,
        "specVersion": SPEC_VERSION,
        "serialNumber": _serial_number(component_name, components),
        "version": 1,
        "metadata": metadata,
        "components": components,
    }
    return doc


def _metadata_component(name: str, supply: SupplyChain) -> dict:
    comp: dict = {
        "type": "application",
        "bom-ref": f"root:{name}",
        "name": name,
    }
    # Language target/SDK versions ride as properties so a standard CycloneDX
    # consumer sees them without knowing our supply_chain section.
    props = []
    for target in supply.targets:
        props.append({
            "name": f"{_PROP}:target:{target.ecosystem}:{target.kind}",
            "value": target.constraint,
        })
    if props:
        comp["properties"] = props
    return comp


def _dependency_component(dep) -> dict:
    comp: dict = {
        "type": "library",
        "name": dep.name,
    }
    if dep.version:
        comp["version"] = dep.version
    if dep.purl:
        comp["purl"] = dep.purl
        comp["bom-ref"] = dep.purl
    else:
        comp["bom-ref"] = dep.key()
    props = [
        {"name": f"{_PROP}:ecosystem", "value": dep.ecosystem},
        {"name": f"{_PROP}:pin_status", "value": dep.pin_status},
        {"name": f"{_PROP}:scope", "value": dep.scope},
    ]
    if dep.declared:
        props.append({"name": f"{_PROP}:declared", "value": dep.declared})
    if dep.evidence_file:
        ev = dep.evidence_file
        if dep.evidence_line is not None:
            ev = f"{ev}:{dep.evidence_line}"
        props.append({"name": f"{_PROP}:evidence", "value": ev})
    comp["properties"] = props
    return comp


def _vendored_component(vendored: dict) -> dict:
    path = vendored.get("path", "")
    comp: dict = {
        "type": "library",
        "name": path,
        "bom-ref": f"vendored:{path}",
        "properties": [
            {"name": f"{_PROP}:vendored", "value": "true"},
            {"name": f"{_PROP}:evidence", "value": path},
        ],
    }
    return comp


def _serial_number(name: str, components: list[dict]) -> str:
    """A reproducible ``urn:uuid`` derived from the component identities.

    The digest input is the metadata name plus each component's bom-ref and
    version, joined in list order (which the collector already sorted). Same
    inputs yield the same UUID; there is no random serial number.
    """
    parts = [name]
    for comp in components:
        parts.append(comp.get("bom-ref", ""))
        parts.append(comp.get("version", ""))
    digest_input = "\n".join(parts)
    derived = uuid.uuid5(_SERIAL_NAMESPACE, digest_input)
    return f"urn:uuid:{derived}"
