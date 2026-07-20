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
    include_fixtures: bool = False,
) -> dict:
    """Build the CycloneDX 1.5 document dict for ``supply``.

    ``component_name`` names the metadata (root) component, normally the repo
    name. Only SHIPPING dependencies and targets are emitted by default (review
    finding 1): test/fixture-origin records are excluded from the CycloneDX
    components unless ``include_fixtures`` is set.

    The document carries NO timestamp (review finding 9): the serial number is
    content-derived (a UUIDv5 over the sorted component identities), so the whole
    document is byte-identical across runs on the same inputs, independent of the
    projection's ``generated_at`` (which is accepted for API stability and not
    written). Determinism is invariant I4.
    """
    from .models import ORIGIN_SHIPPING

    deps = supply.dependencies if include_fixtures else supply.shipping_dependencies()
    targets = supply.targets if include_fixtures else [
        t for t in supply.targets if t.origin == ORIGIN_SHIPPING
    ]

    components: list[dict] = []
    for dep in deps:
        components.append(_dependency_component(dep))
    for vendored in supply.vendored:
        components.append(_vendored_component(vendored))

    doc = {
        "bomFormat": BOM_FORMAT,
        "specVersion": SPEC_VERSION,
        "serialNumber": _serial_number(component_name, components),
        "version": 1,
        "metadata": {"component": _metadata_component(component_name, targets)},
        "components": components,
    }
    return doc


def _metadata_component(name: str, targets) -> dict:
    comp: dict = {
        "type": "application",
        "bom-ref": f"root:{name}",
        "name": name,
    }
    # Language target/SDK versions ride as properties so a standard CycloneDX
    # consumer sees them without knowing our supply_chain section.
    props = []
    for target in targets:
        props.append({
            "name": f"{_PROP}:target:{target.ecosystem}:{target.kind}",
            "value": target.constraint,
        })
    if props:
        comp["properties"] = props
    return comp


def _dependency_component(dep) -> dict:
    from .models import ORIGIN_SHIPPING

    is_test = dep.origin != ORIGIN_SHIPPING
    comp: dict = {
        "type": "library",
        "name": dep.name,
    }
    if dep.version:
        comp["version"] = dep.version
    # A test-origin component (only present when fixtures are included) namespaces
    # its bom-ref so it never collides with a shipping component of the same purl.
    ref_prefix = "test:" if is_test else ""
    if dep.purl:
        comp["purl"] = dep.purl
        comp["bom-ref"] = f"{ref_prefix}{dep.purl}"
    else:
        comp["bom-ref"] = f"{ref_prefix}{dep.key()}"
    props = [
        {"name": f"{_PROP}:ecosystem", "value": dep.ecosystem},
        {"name": f"{_PROP}:pin_status", "value": dep.pin_status},
        {"name": f"{_PROP}:scope", "value": dep.scope},
    ]
    if is_test:
        props.append({"name": f"{_PROP}:origin", "value": dep.origin})
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
