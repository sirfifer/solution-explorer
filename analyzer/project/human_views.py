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
_DATA_WORDS = re.compile(r"(?:data|database|model|schema|store|persist|migration)", re.I)
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
    searchable = " ".join(
        str(component.get(key) or "") for key in ("name", "path", "description")
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


def _coverage_trust(coverage: Optional[dict]) -> dict:
    if not coverage:
        return {"status": "unavailable", "percent": None, "target": "coverage.json"}
    families = coverage_families(coverage.get("summary") or {})
    analyzed = families["analyzed"]
    gaps = families["gap"]
    percent = float(format_source_percent(families))
    return {
        "status": "complete" if gaps == 0 else "has_gaps",
        "percent": percent,
        "analyzed": analyzed,
        "gaps": gaps,
        "target": "coverage.json",
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
            else:
                service_name = str(service)
                category = "external"
            if not service_name:
                continue
            external.append({
                "name": str(service_name),
                "category": str(category),
                "component_id": component_id,
                "component_name": component_name,
                "evidence": {"component_id": component_id},
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


def build_security_view(arch: dict) -> dict:
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

    portrait_nodes: list[dict] = []
    for group_id in _GROUP_META:
        members = grouped.get(group_id) or []
        if not members:
            continue
        label, role = _GROUP_META[group_id]
        member_ids = sorted(str(c.get("id")) for c in members if c.get("id"))
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
            "target": {"lens": "flow", "tour_id": (arch.get("tours") or [{}])[0].get("id")},
            "available": bool(arch.get("tours")) or any(
                str(r.get("type") or "") in {"navigation", "tab", "modal"}
                for r in arch.get("relationships") or []
            ),
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
        if str(finding.get("verification_status") or "unverified") != "verified"
    )
    tours = arch.get("tours") or []
    first_tour = tours[0].get("id") if tours else None
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
                f"{int(stats.get('total_components', len(components)) or len(components))} mapped "
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
                "status": "present" if interpreted else "absent",
                "component_count": sum(1 for c in components if c.get("ai_enhance")),
                "total_components": len(components),
            },
            "producer_gaps": len(arch.get("gaps") or []),
            "findings": {"total": len(finding_rows), "unverified": unverified},
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
