"""Human-first projection sidecars for the adaptive viewer.

The normal manifest is the Workbench payload and ``ai.json`` is the machine
front door.  These three small documents answer bounded human entry questions
without asking the browser to invent architectural meaning:

* ``orientation.json`` -- identity, a system portrait, question routes, trust;
* ``support.json`` -- configuration, external reliance, entry points, data;
* ``security.json`` -- observable security mechanisms, boundaries and unknowns.

Every builder is a pure function over the prepared architecture and its
already-derived projection sections.  No filesystem scan, network request, or
model call occurs here.  Writers sort keys, and every list has an explicit
stable order (invariant I4).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Optional

from .coverage import coverage_families, format_source_percent

__all__ = [
    "ORIENTATION_FILENAME",
    "SUPPORT_FILENAME",
    "SECURITY_FILENAME",
    "build_orientation",
    "build_support_view",
    "build_security_view",
    "write_human_view",
]

ORIENTATION_FILENAME = "orientation.json"
SUPPORT_FILENAME = "support.json"
SECURITY_FILENAME = "security.json"

_CLIENT_TYPES = {
    "ios-client", "android-client", "mobile-client", "web-client",
    "desktop-app", "watch-app", "screen", "tab", "tab-container",
}
_SERVICE_TYPES = {"api-server", "service", "worker", "server"}
_TOOL_TYPES = {"cli-tool", "infrastructure"}
_DATA_WORDS = re.compile(
    r"(?:^|[/ _-])(?:data|database|models?|schemas?|stores?|persistence|migrations?)(?:$|[/ _-])",
    re.I,
)
_CREDENTIAL_WORDS = re.compile(
    r"(?:secret|token|password|passwd|credential|api[_-]?key|private[_-]?key|client[_-]?secret)",
    re.I,
)
_SENSITIVE_WORDS = re.compile(
    r"(?:user|account|profile|email|phone|address|credential|token|session|payment|health|medical|location)",
    re.I,
)
_SECURITY_WORDS = re.compile(
    r"(?:security|secret|credential|authentication|authorization|authn|authz|injection|vulnerab|encrypt|tls|privacy)",
    re.I,
)


def _components(tree: Iterable[dict]) -> list[dict]:
    """Flatten a component tree in stable pre-order, de-duplicated by id."""
    result: list[dict] = []
    seen: set[str] = set()

    def walk(nodes: Iterable[dict]) -> None:
        for component in nodes or []:
            component_id = str(component.get("id", ""))
            if component_id and component_id not in seen:
                seen.add(component_id)
                result.append(component)
            walk(component.get("children") or [])

    walk(tree)
    return result


def _component_index(arch: dict) -> tuple[list[dict], dict[str, dict]]:
    components = _components(arch.get("components") or [])
    return components, {str(c.get("id")): c for c in components if c.get("id")}


def _group_for(component: dict) -> str:
    component_type = str(component.get("type") or "").lower()
    # Group from structural identity only. Prose commonly says a module
    # "models" behavior; treating that verb as a data-layer path put VS Code's
    # editor core under persistence.
    searchable = " ".join(
        str(component.get(key) or "") for key in ("name", "path")
    )
    if component_type in _CLIENT_TYPES:
        return "experience"
    if _DATA_WORDS.search(searchable):
        return "data"
    if component_type in _SERVICE_TYPES:
        return "services"
    if component_type in _TOOL_TYPES:
        return "operations"
    return "core"


_GROUP_META = {
    "experience": ("Experiences", "Client-facing products and user flows"),
    "core": ("Core system", "Application and domain implementation"),
    "services": ("Services & interfaces", "Runtime services and API boundaries"),
    "data": ("Data & persistence", "Models, schemas, stores and migrations"),
    "operations": ("Operations & tools", "Infrastructure and operational tooling"),
}


def _representative_rank(group_id: str, component: dict) -> tuple:
    """Rank credible entry targets ahead of incidental descendants.

    A system-area card is an orientation promise, so its first target must be a
    recognizable application or subsystem boundary. Alphabetical order made a
    nested generated-output folder the representative Experience in a real
    project. Keep the order deterministic while preferring role-appropriate,
    structurally meaningful containers near the root.
    """
    component_id = str(component.get("id") or "")
    component_type = str(component.get("type") or "").lower()
    searchable = " ".join(
        str(component.get(key) or "") for key in ("id", "name", "path")
    ).lower()
    depth = component_id.count("/")
    child_count = len(component.get("children") or [])

    type_priority = 2
    semantic_priority = 1
    if group_id == "experience":
        type_priority = 0 if component_type in {
            "ios-client", "android-client", "mobile-client", "desktop-app",
            "watch-app", "web-client",
        } else 1
    elif group_id == "services":
        type_priority = {
            "api-server": 0, "service": 1, "worker": 2, "server": 2,
        }.get(component_type, 3)
    elif group_id == "data":
        if re.search(r"(?:^|[/ _-])database$", searchable):
            semantic_priority = 0
        elif re.search(r"(?:^|[/ _-])migrations?(?:$|[/ _-])", searchable):
            semantic_priority = 1
        else:
            semantic_priority = 2
        type_priority = 0 if component_type in {"module", "package"} else 1
    elif group_id == "operations":
        type_priority = 0 if component_type == "infrastructure" else 1
    else:
        type_priority = 0 if component_type in {"module", "package", "library"} else 1

    # A synthetic projection root can be a useful graph target, but it is not a
    # useful example of one area inside that graph.
    synthetic_root = 1 if component_id == "root" else 0
    return (
        synthetic_root,
        semantic_priority,
        type_priority,
        depth,
        -child_count,
        component_id,
    )


def _coverage_trust(coverage: Optional[dict]) -> dict:
    if not coverage:
        return {"status": "unavailable", "percent": None, "target": "coverage.json"}
    families = coverage_families(coverage.get("summary") or {})
    summary = coverage.get("summary") or {}
    analyzed = families["analyzed"]
    gaps = families["gap"]
    inventory_total = sum(int(value or 0) for value in summary.values())
    excluded = sum(
        int(value or 0)
        for key, value in summary.items()
        if str(key).startswith("excluded:")
    )
    binary = int(summary.get("binary") or 0)
    percent = float(format_source_percent(families))
    return {
        "status": "complete" if gaps == 0 else "has_gaps",
        "percent": percent,
        "analyzed": analyzed,
        "gaps": gaps,
        "inventory_total": inventory_total,
        "excluded": excluded,
        "binary": binary,
        "target": "coverage.json",
    }


def _component_docs_text(component: dict) -> str:
    docs = component.get("docs") or {}
    return "\n".join(str(value) for value in docs.values() if value)


def _deployment_posture(arch: dict) -> Optional[dict]:
    """Build an evidence-tiered deployment posture without inventing topology.

    Repository prose is a claim, not runtime proof. Direct provider references
    extracted from product source are stronger observations. Both remain
    visible with their distinct statement kinds so contradictory or incomplete
    repositories degrade to an honest set of claims instead of one false story.
    """
    components, _ = _component_index(arch)
    evidence: list[tuple[str, str]] = []
    for component in components:
        docs = component.get("docs") or {}
        for field in ("claude_md", "readme", "architecture_notes"):
            value = docs.get(field)
            if value:
                evidence.append((f"{component.get('id') or 'root'}.docs.{field}", str(value)))
    combined = "\n".join(value for _, value in evidence)
    rows: list[dict] = []
    standalone = re.search(r"\bstandalone (?:mobile )?app\b", combined, re.I)
    if standalone:
        source = next(path for path, text in evidence if re.search(r"\bstandalone (?:mobile )?app\b", text, re.I))
        rows.append({
            "id": "primary-runtime",
            "label": "Standalone application",
            "posture": "standalone",
            "statement_kind": "repository_claim",
            "evidence": {"source": source, "phrase": standalone.group(0)},
        })

    server = re.search(
        r"communicates with (?:the )?(.{0,60}?server) via ([^.\n]+)",
        combined,
        re.I,
    )
    source_independent = re.search(r"zero source-level dependencies on server code", combined, re.I)
    if standalone and server and source_independent:
        source = next(path for path, text in evidence if server.group(0) in text)
        rows.append({
            "id": "companion-backend",
            "label": server.group(1).strip(),
            "posture": "optional",
            "detail": f"Available via {server.group(2).strip()}; the repository says the client has no source-level dependency on server code.",
            "statement_kind": "repository_claim",
            "evidence": {
                "source": source,
                "phrase": f"{server.group(0)}; {source_independent.group(0)}",
            },
        })

    on_device = re.search(r"\bon-device\b", combined, re.I)
    if on_device:
        source = next(path for path, text in evidence if re.search(r"\bon-device\b", text, re.I))
        rows.append({
            "id": "on-device",
            "label": "On-device execution is supported",
            "posture": "on_device",
            "statement_kind": "repository_claim",
            "evidence": {"source": source, "phrase": on_device.group(0)},
        })

    direct = re.search(
        r"\b(?:connects?\s+)?direct(?:ly)?\s+to\s+(?:the )?(?:cloud )?provider\b"
        r"|\bdevice[- ]to[- ]provider\b",
        combined,
        re.I,
    )
    if direct:
        source = next(path for path, text in evidence if direct.group(0) in text)
        rows.append({
            "id": "direct-provider",
            "label": "The client can contact providers without an application proxy",
            "posture": "direct_to_provider",
            "statement_kind": "repository_claim",
            "evidence": {"source": source, "phrase": direct.group(0)},
        })

    # A URL embedded in a client component is direct source evidence that the
    # client references that provider. It does not prove a production request
    # occurred, which is why the statement says "references" rather than
    # "connects" and keeps authentication explicitly observable elsewhere.
    direct_services: list[dict] = []
    for component in components:
        for service in component.get("external_services") or []:
            if not isinstance(service, dict) or not service.get("name"):
                continue
            direct_services.append({
                "name": str(service["name"]),
                "protocol": service.get("protocol"),
                "evidence": service.get("evidence") or {"component_id": component.get("id")},
            })
    if direct_services and not any(row["id"] == "direct-provider" for row in rows):
        # Label and evidence must describe the same component. Combining every
        # provider name but citing only the first component made the source link
        # incapable of supporting the displayed statement.
        by_component: dict[str, list[dict]] = defaultdict(list)
        for service in direct_services:
            evidence = service.get("evidence") or {}
            component_id = str(evidence.get("component_id") or "")
            by_component[component_id].append(service)
        _, evidenced_services = sorted(
            by_component.items(),
            key=lambda item: (-len({row["name"] for row in item[1]}), item[0]),
        )[0]
        names = sorted({row["name"] for row in evidenced_services})
        rows.append({
            "id": "direct-provider",
            "label": "Direct provider references are present in the client",
            "posture": "direct_to_provider",
            "detail": ", ".join(names[:6]) + (" and others" if len(names) > 6 else ""),
            "statement_kind": "observed_source_reference",
            "evidence": evidenced_services[0]["evidence"],
        })

    if not rows:
        return None
    return {
        "status": "evidence_tiered",
        "method_caveat": "Repository claims are separated from source-observed provider references. Runtime deployment remains configuration-dependent.",
        "items": rows,
    }


def build_support_view(arch: dict) -> dict:
    """Build the evidence-honest Support/Operations view.

    The ranking is deliberately mechanical: external reliance weighs three,
    required configuration two, and ticket-facing entry points one.  It is an
    attention order, never a failure probability.
    """
    components, index = _component_index(arch)
    configuration: list[dict] = []
    external: list[dict] = []

    for component in components:
        component_id = str(component.get("id") or "")
        component_name = str(component.get("name") or component_id)
        docs = component.get("docs") or {}
        for key in sorted(set(docs.get("env_vars") or [])):
            configuration.append({
                "key": str(key),
                "component_id": component_id,
                "component_name": component_name,
                "kind": "environment_variable",
                "evidence": {"component_id": component_id},
            })
        for config in component.get("config_files") or []:
            if isinstance(config, dict):
                path = config.get("path") or config.get("type")
            else:
                path = str(config)
            if path:
                configuration.append({
                    "key": str(path),
                    "component_id": component_id,
                    "component_name": component_name,
                    "kind": "configuration_file",
                    "evidence": {"path": str(path)},
                })
        for service in component.get("external_services") or []:
            if isinstance(service, dict):
                service_name = service.get("name")
                category = service.get("category") or "external"
                protocol = service.get("protocol")
                port = service.get("port")
                authentication = service.get("authentication") or "not_observable"
                service_evidence = service.get("evidence") or {"component_id": component_id}
            else:
                service_name = str(service)
                category = "external"
                protocol = None
                port = None
                authentication = "not_observable"
                service_evidence = {"component_id": component_id}
            if not service_name:
                continue
            external.append({
                "name": str(service_name),
                "category": str(category),
                "protocol": protocol,
                "port": port,
                "authentication": authentication,
                "component_id": component_id,
                "component_name": component_name,
                "evidence": service_evidence,
            })

    entry_points: list[dict] = []
    for capability in sorted(arch.get("capabilities") or [], key=lambda c: str(c.get("id", ""))):
        owner = str(capability.get("component_id") or "")
        entry_points.append({
            "id": str(capability.get("id") or ""),
            "name": str(capability.get("name") or capability.get("id") or "entry point"),
            "kind": str(capability.get("kind") or "capability"),
            "component_id": owner or None,
            "component_name": str(index.get(owner, {}).get("name") or owner) if owner else None,
            "confidence": str(capability.get("confidence") or "inferred"),
            "evidence": capability.get("evidence") or [],
        })

    data_handled: list[dict] = []
    for entity in sorted(arch.get("data_entities") or [], key=lambda e: str(e.get("id", ""))):
        data_handled.append({
            "id": str(entity.get("id") or ""),
            "name": str(entity.get("name") or entity.get("id") or "entity"),
            "kind": str(entity.get("kind") or "entity"),
            "component_id": entity.get("component_id"),
            "confidence": "inferred" if entity.get("inferred") else "certain",
            "evidence": entity.get("evidence") or [],
        })

    score: dict[str, int] = defaultdict(int)
    reasons: dict[str, set[str]] = defaultdict(set)
    for row in external:
        if row["component_id"]:
            score[row["component_id"]] += 3
            reasons[row["component_id"]].add("external reliance")
    for row in configuration:
        if row["component_id"]:
            score[row["component_id"]] += 2
            reasons[row["component_id"]].add("configuration")
    for row in entry_points:
        if row["component_id"]:
            score[row["component_id"]] += 1
            reasons[row["component_id"]].add("entry point")

    attention = [
        {
            "component_id": component_id,
            "component_name": str(index.get(component_id, {}).get("name") or component_id),
            "attention_score": value,
            "reasons": sorted(reasons[component_id]),
        }
        for component_id, value in score.items()
    ]
    attention.sort(key=lambda row: (-row["attention_score"], row["component_id"]))

    configuration.sort(key=lambda row: (row["key"].lower(), row["component_id"]))
    external.sort(key=lambda row: (row["name"].lower(), row["component_id"]))

    return {
        "schema": "syscorpus.support/v1",
        "method_caveat": (
            "Ranked attention combines observed external reliance, configuration "
            "surface, and entry points. It is not incident probability or uptime data."
        ),
        "configuration": configuration,
        "external_dependencies": external,
        "entry_points": entry_points,
        "data_handled": data_handled,
        "attention": attention,
        "counts": {
            "configuration": len(configuration),
            "external_dependencies": len(external),
            "entry_points": len(entry_points),
            "data_entities": len(data_handled),
            "attention_components": len(attention),
        },
    }


def build_security_view(
    arch: dict,
    *,
    signals_by_path: Optional[dict[str, list[dict]]] = None,
) -> dict:
    """Build an observable-security view without producing a security verdict."""
    components, index = _component_index(arch)
    credentials: list[dict] = []
    for component in components:
        docs = component.get("docs") or {}
        for key in sorted(set(docs.get("env_vars") or [])):
            if _CREDENTIAL_WORDS.search(str(key)):
                credentials.append({
                    "key": str(key),
                    "component_id": str(component.get("id") or ""),
                    "component_name": str(component.get("name") or component.get("id") or ""),
                    "claim": "credential configuration is referenced",
                    "confidence": "certain",
                    "evidence": {"component_id": str(component.get("id") or "")},
                })

    mechanisms: list[dict] = []
    boundaries: list[dict] = []
    for relationship in sorted(
        arch.get("relationships") or [],
        key=lambda r: (str(r.get("source", "")), str(r.get("target", "")), str(r.get("type", ""))),
    ):
        if (relationship.get("verdict") or {}).get("status") == "refuted":
            continue
        source = str(relationship.get("source") or "")
        target = str(relationship.get("target") or "")
        authentication = relationship.get("authentication")
        middleware = [str(m) for m in relationship.get("middleware") or []]
        auth_middleware = [m for m in middleware if _SECURITY_WORDS.search(m)]
        if authentication or auth_middleware:
            mechanisms.append({
                "source": source,
                "target": target,
                "mechanism": str(authentication or ", ".join(auth_middleware)),
                "confidence": "certain",
                "evidence": {"relationship": [source, target]},
            })

        protocol = str(relationship.get("protocol") or relationship.get("transport") or "unknown")
        protocol_lower = protocol.lower()
        if protocol_lower in {"https", "wss", "tls", "mtls"}:
            transport_state = "encrypted_observed"
        elif protocol_lower in {"http", "ws"}:
            transport_state = "cleartext_label_observed"
        else:
            transport_state = "not_observable"
        boundaries.append({
            "source": source,
            "source_name": str(index.get(source, {}).get("name") or source),
            "target": target,
            "target_name": str(index.get(target, {}).get("name") or target),
            "type": str(relationship.get("type") or "relationship"),
            "protocol": protocol,
            "transport_state": transport_state,
            "evidence": {"relationship": [source, target]},
        })

    # External service references are communication boundaries even when the
    # remote provider is not modeled as a component node. Preserve the scheme,
    # port, and explicit authentication unknown instead of drawing a blank edge.
    for component in components:
        component_id = str(component.get("id") or "")
        for service in component.get("external_services") or []:
            if not isinstance(service, dict):
                continue
            protocol = str(service.get("protocol") or "unknown").lower()
            service_name = str(service.get("name") or "external service")
            boundaries.append({
                "source": component_id,
                "source_name": str(component.get("name") or component_id),
                "target": f"external:{service_name}",
                "target_name": service_name,
                "type": "external_service",
                "protocol": protocol,
                "port": service.get("port"),
                "authentication": service.get("authentication") or "not_observable",
                "transport_state": (
                    "encrypted_observed" if protocol in {"https", "wss", "tls", "mtls"}
                    else "cleartext_label_observed" if protocol in {"http", "ws"}
                    else "not_observable"
                ),
                "evidence": service.get("evidence") or {"component_id": component_id},
            })

    # Platform-local controls do not appear on graph edges. Preserve them as
    # first-class observed mechanisms when component file facts provide direct
    # import, path, module-doc, or symbol-name evidence.
    seen_local: set[tuple[str, str]] = set()
    local_candidates: list[tuple[int, str, str, str, str, dict]] = []
    signals_by_path = signals_by_path or {}
    file_rows = [row for row in arch.get("files") or [] if isinstance(row, dict)]
    candidates_by_file: dict[str, list[dict]] = defaultdict(list)
    for component in components:
        for row in component.get("files") or []:
            path = str(row.get("path") or "") if isinstance(row, dict) else str(row)
            if path:
                candidates_by_file[path].append(component)

    owned_file_rows: list[tuple[dict, dict]] = []
    by_path = {str(row.get("path") or ""): row for row in file_rows}
    for path, candidates in candidates_by_file.items():
        file_row = by_path.get(path)
        if file_row is None:
            file_row = next(
                (
                    row for component in candidates
                    for row in component.get("files") or []
                    if isinstance(row, dict) and str(row.get("path") or "") == path
                ),
                None,
            )
        if file_row is None:
            continue
        # Component trees may repeat a descendant file on ancestors. Attribute
        # a local mechanism once, to the deepest explicit owner.
        owner = max(
            candidates,
            key=lambda component: len(str(component.get("path") or "").split("/")),
        )
        owned_file_rows.append((owner, file_row))

    for component, file_row in owned_file_rows:
        component_id = str(component.get("id") or "")
        path = str(file_row.get("path") or "")
        imports = {str(value) for value in file_row.get("imports") or []}
        symbols = " ".join(str(value) for value in file_row.get("symbols") or [])
        searchable = " ".join([path, str(file_row.get("module_doc") or ""), symbols])
        direct_symbols: list[tuple[str, Optional[int]]] = []
        for signal in signals_by_path.get(path, []):
            if signal.get("kind") != "symbol_reference":
                continue
            value = signal.get("value") or {}
            name = str(value.get("name") or "") if isinstance(value, dict) else ""
            if name:
                direct_symbols.append((name, signal.get("line")))

        local: list[tuple[int, str, str, dict]] = []
        if "Security" in imports and re.search(r"keychain|api.?key", searchable, re.I):
            local.append((0, "iOS Keychain", "credential storage", {
                "file": path,
                "signal": "Security import and Keychain symbol",
            }))
        protection_refs = [
            (name, line) for name, line in direct_symbols
            if name in {"FileProtectionType", "NSPersistentStoreFileProtectionKey"}
        ]
        if protection_refs:
            line = min((int(line) for _, line in protection_refs if line is not None), default=None)
            evidence = {
                "file": path,
                "signal": "FileProtectionType / NSPersistentStoreFileProtectionKey symbol reference",
            }
            if line is not None:
                evidence["line"] = line
            local.append((0, "iOS file protection", "protected local storage", evidence))
        elif re.search(r"file.?protection|NSFileProtection", searchable, re.I):
            local.append((1, "iOS file protection", "protected local storage", {
                "file": path,
                "signal": "import/symbol/documentation reference",
            }))
        for rank, mechanism, purpose, evidence in local:
            local_candidates.append((rank, component_id, mechanism, path, purpose, evidence))

    for _, component_id, mechanism, _path, purpose, evidence in sorted(local_candidates):
        component = index.get(component_id) or {}
        key = (component_id, mechanism)
        if key in seen_local:
            continue
        seen_local.add(key)
        mechanisms.append({
            "source": component_id,
            "target": "device-security-boundary",
            "mechanism": mechanism,
            "purpose": purpose,
            "confidence": "certain",
            "evidence": evidence,
        })
        if mechanism == "iOS Keychain":
            credentials.append({
                "key": "API keys",
                "component_id": component_id,
                "component_name": str(component.get("name") or component_id),
                "claim": "credential storage in iOS Keychain is referenced",
                "confidence": "certain",
                "evidence": evidence,
            })

    sensitive_data: list[dict] = []
    for entity in sorted(arch.get("data_entities") or [], key=lambda e: str(e.get("id", ""))):
        fields = [str(field.get("name") or "") for field in entity.get("fields") or [] if isinstance(field, dict)]
        searchable = " ".join([str(entity.get("name") or ""), *fields])
        matches = sorted({match.group(0).lower() for match in _SENSITIVE_WORDS.finditer(searchable)})
        if matches:
            sensitive_data.append({
                "entity_id": str(entity.get("id") or ""),
                "entity_name": str(entity.get("name") or entity.get("id") or "entity"),
                "component_id": entity.get("component_id"),
                "matched_terms": matches,
                "confidence": "inferred",
                "evidence": entity.get("evidence") or [],
            })

    findings: list[dict] = []
    for finding in sorted(arch.get("findings") or [], key=lambda f: str(f.get("id", ""))):
        searchable = " ".join(
            str(finding.get(key) or "") for key in ("kind", "summary", "detail")
        )
        if _SECURITY_WORDS.search(searchable):
            findings.append({
                "id": str(finding.get("id") or ""),
                "kind": str(finding.get("kind") or "security_lead"),
                "summary": str(finding.get("summary") or finding.get("detail") or "Security-related lead"),
                "confidence": finding.get("confidence"),
                "verification_status": finding.get("verification_status") or "unverified",
                "evidence": finding.get("evidence") or [],
            })

    return {
        "schema": "syscorpus.security/v1",
        "method_caveat": (
            "Repository-observable mechanisms and leads only. This is not a "
            "security audit, compliance verdict, penetration test, or assurance of safety."
        ),
        "mechanisms": mechanisms,
        "credential_configuration": credentials,
        "communication_boundaries": boundaries,
        "sensitive_data_leads": sensitive_data,
        "findings": findings,
        "not_observable": [
            "runtime control effectiveness",
            "deployed secret values",
            "identity-provider policy",
            "network perimeter configuration",
            "incident response performance",
        ],
        "counts": {
            "mechanisms": len(mechanisms),
            "credential_configuration": len(credentials),
            "communication_boundaries": len(boundaries),
            "sensitive_data_leads": len(sensitive_data),
            "findings": len(findings),
        },
    }


_FLOW_EDGE_TYPES = frozenset({"navigation", "tab", "modal", "embed"})
_FLOW_COMPONENT_TYPES = frozenset({"screen", "tab", "tab-container"})


def _has_flow_data(arch: dict) -> bool:
    """hasFlowData from viewer/src/lenses/flow.ts: is there a Flow lens to offer?"""
    if any(
        str(r.get("type") or "") in _FLOW_EDGE_TYPES
        for r in arch.get("relationships") or []
    ):
        return True

    def walk(components: list) -> bool:
        for component in components or []:
            if str(component.get("type") or "") in _FLOW_COMPONENT_TYPES:
                return True
            if any(a.get("target_view") for a in component.get("actions") or [] if isinstance(a, dict)):
                return True
            if walk(component.get("children") or []):
                return True
        return False

    return walk(arch.get("components") or [])


def build_orientation(
    arch: dict,
    *,
    coverage: Optional[dict] = None,
    support: Optional[dict] = None,
    security: Optional[dict] = None,
) -> dict:
    """Build the bounded human orientation contract."""
    components, _ = _component_index(arch)
    component_group: dict[str, str] = {}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for component in components:
        component_id = str(component.get("id") or "")
        group = _group_for(component)
        component_group[component_id] = group
        grouped[group].append(component)

    # A lone service in a large codebase is an implementation detail, not a
    # useful top-level area. Preserve small-repository behavior and genuine
    # service groupings while avoiding a 1-vs-hundreds portrait split.
    if len(components) >= 50 and len(grouped.get("services") or []) == 1:
        lone_service = grouped.pop("services")[0]
        grouped["core"].append(lone_service)
        service_id = str(lone_service.get("id") or "")
        if service_id:
            component_group[service_id] = "core"

    portrait_nodes: list[dict] = []
    for group_id in _GROUP_META:
        members = grouped.get(group_id) or []
        if not members:
            continue
        label, role = _GROUP_META[group_id]
        member_ids = [
            str(component.get("id"))
            for component in sorted(members, key=lambda row: _representative_rank(group_id, row))
            if component.get("id")
        ]
        portrait_nodes.append({
            "id": f"orientation:{group_id}",
            "label": label,
            "role": role,
            "member_count": len(member_ids),
            "stable_targets": member_ids[:12],
            "target_truncated": len(member_ids) > 12,
            "statement_kind": "deterministic_grouping",
        })

    edge_counts: dict[tuple[str, str], int] = defaultdict(int)
    edge_samples: dict[tuple[str, str], list[list[str]]] = defaultdict(list)
    for relationship in arch.get("relationships") or []:
        if (relationship.get("verdict") or {}).get("status") == "refuted":
            continue
        source = str(relationship.get("source") or "")
        target = str(relationship.get("target") or "")
        source_group = component_group.get(source)
        target_group = component_group.get(target)
        if not source_group or not target_group or source_group == target_group:
            continue
        pair = (source_group, target_group)
        edge_counts[pair] += 1
        if len(edge_samples[pair]) < 8:
            edge_samples[pair].append([source, target])
    portrait_edges = [
        {
            "source": f"orientation:{source}",
            "target": f"orientation:{target}",
            "relationship_count": count,
            "evidence_pairs": edge_samples[(source, target)],
        }
        for (source, target), count in sorted(edge_counts.items())
    ]

    # The Flow lens exists only for subjects with UI navigation data: screens,
    # tabs, navigation edges (viewer/src/lenses/flow.ts hasFlowData, mirrored
    # here). For any other subject the honest answer to "how does the core
    # experience work" is the first guided tour, walked on the Structure lens.
    # Naming a lens the viewer cannot offer sent readers to Structure with no
    # explanation (GUI crawl 2026-09-02, overview.route_wrong_target).
    flow_lens = _has_flow_data(arch)
    first_tour_id = (arch.get("tours") or [{}])[0].get("id")
    questions = [
        {
            "id": "organization",
            "label": "How is it organized?",
            "target": {"lens": "structure", "semantic_level": "system"},
            "available": True,
        },
        {
            "id": "flow",
            "label": "How does the core experience work?",
            "target": {
                "lens": "flow" if flow_lens else "structure",
                "tour_id": first_tour_id,
            },
            "available": flow_lens or bool(arch.get("tours")),
        },
        {
            "id": "capabilities",
            "label": "What can this system do?",
            "target": {"lens": "capability"},
            "available": bool(arch.get("capabilities")),
        },
        {
            "id": "data",
            "label": "Where does data live?",
            "target": {"lens": "data"},
            "available": bool(arch.get("data_entities")),
        },
        {
            "id": "attention",
            "label": "Where should I look first?",
            "target": {"surface": "findings"},
            "available": bool(arch.get("findings") or arch.get("gaps")),
        },
        {
            "id": "support",
            "label": "What could make this fail in operation?",
            "target": {"lens": "support"},
            "available": bool(support) and any(
                int(value or 0) > 0 for value in (support.get("counts") or {}).values()
            ),
        },
        {
            "id": "security",
            "label": "What security mechanisms are visible?",
            "target": {"lens": "security"},
            "available": bool(security) and any(
                int(value or 0) > 0 for value in (security.get("counts") or {}).values()
            ),
        },
    ]

    ai = arch.get("ai_enhance") or {}
    interpreted = ai.get("summary") or arch.get("description")
    stats = arch.get("stats") or {}
    finding_rows = arch.get("findings") or []
    unverified = sum(
        1 for finding in finding_rows
        if str(finding.get("verification_status") or "unverified") == "unverified"
    )
    refuted = sum(
        1 for finding in finding_rows
        if str(finding.get("verification_status") or "unverified") == "refuted"
    )
    tours = arch.get("tours") or []
    first_tour = tours[0].get("id") if tours else None
    producer_status: dict[str, int] = defaultdict(int)
    for gap in arch.get("gaps") or []:
        producer_status[str(gap.get("status") or "unknown")] += 1

    return {
        "schema": "syscorpus.orientation/v1",
        "subject": {
            "id": str(arch.get("name") or "system"),
            "name": str(arch.get("name") or "System"),
            "kind": "multi-repository solution" if arch.get("repositories") else "software system",
            "repository": arch.get("repository"),
            "default_branch": arch.get("default_branch"),
            "generated_at": arch.get("generated_at"),
            "analyzer_version": arch.get("analyzer_version"),
        },
        "orientation": {
            "deterministic_statement": (
                f"{arch.get('name') or 'This system'} contains "
                f"{len(components)} mapped "
                f"components across {len(portrait_nodes)} system areas, connected by "
                f"{int(stats.get('total_relationships', len(arch.get('relationships') or [])) or 0)} relationships."
            ),
            "interpreted_statement": ({
                "text": str(interpreted),
                "status": "interpreted",
                "provenance": {
                    "derived_from_commit": ai.get("derived_from_commit"),
                    "stale": bool(ai.get("stale", False)),
                },
            } if interpreted else None),
            "default_path": ({"kind": "tour", "id": first_tour} if first_tour else {"kind": "question", "id": "organization"}),
        },
        "deployment_posture": _deployment_posture(arch),
        "portrait": {
            "semantic_level": "system",
            "method": "deterministic component-type and path grouping",
            "nodes": portrait_nodes,
            "edges": portrait_edges,
        },
        "question_routes": questions,
        "trust": {
            "source_coverage": _coverage_trust(coverage),
            "interpretation": {
                "status": (
                    "stale" if interpreted and bool(ai.get("stale", False))
                    else "present" if interpreted
                    else "absent"
                ),
                "component_count": sum(1 for c in components if c.get("ai_enhance")),
                "total_components": len(components),
            },
            "producer_gaps": len(arch.get("gaps") or []),
            "producer_gap_status": dict(sorted(producer_status.items())),
            "findings": {
                "total": len(finding_rows),
                "unverified": unverified,
                "refuted": refuted,
            },
            "direct_dependencies": sum(
                1
                for dependency in (arch.get("supply_chain") or {}).get("dependencies") or []
                if dependency.get("scope") == "direct"
            ),
        },
        "launch_targets": {
            "overview": {"mode": "overview"},
            "workbench": {"mode": "workbench", "lens": "structure", "semantic_level": "system"},
            "search": {"mode": "workbench", "surface": "search"},
        },
    }


def write_human_view(document: Optional[dict], path: Path, *, indent=2) -> Optional[Path]:
    """Write one sidecar deterministically; return None for an absent view."""
    if document is None:
        return None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(document, fh, indent=indent, default=str, sort_keys=True)
    return path
