"""Tier 3 orchestrator: run the derivation passes over the store.

Sequences the passes in the same order as ``ArchitectureScanner.scan`` (so the
re-expression is faithful), computes component metrics, derives project-level
info from cached content, extracts docs, then assembles a viewer-compatible
architecture dict and flushes the derived components and edges back to the
store. Every pass reads only the store; wrap a call in
``derive.instrumentation.source_read_audit`` to prove zero source reads.
"""

from __future__ import annotations

from collections import defaultdict

from ..models import Component, to_dict
from ..store import FactStore
from . import capabilities as capabilities_pass
from . import components as components_pass
from . import correlations as correlations_pass
from . import docs as docs_pass
from . import entities as entities_pass
from . import flow as flow_pass
from . import relationships as rel_pass
from . import roles as roles_pass
from . import rules as rules_pass
from . import testing as testing_pass
from .context import Deriver
from .storeview import StoreView


def derive_all(
    store: FactStore,
    root_name: str,
    *,
    repo: str = ".",
    root_path: str = "",
    description: str = "",
) -> tuple[Deriver, dict]:
    """Run all derivation passes and return (Deriver, architecture dict)."""
    view = StoreView.load(store)
    d = Deriver(view, root_name, repo=repo)

    components_pass.discover_components(d)
    components_pass.associate_files(d)
    components_pass.rekey_symbols(d, store)
    roles_pass.promote_component_types(d)
    roles_pass.improve_component_names(d)
    roles_pass.assign_server_ports(d)
    flow_pass.detect_ui_flows(d)
    flow_pass.detect_ui_actions(d)
    rel_pass.derive_relationships(d)
    _compute_metrics(d)
    testing_pass.detect_testing(d)
    arch_description = _project_description(d, description)
    docs_pass.extract_component_docs(d)
    capabilities_pass.derive_capabilities(d)
    entities_pass.derive_entities(d)
    rules_pass.derive_rules(d)
    # Correlations run last: they read the components, edges, capabilities,
    # entities, rules, and clone-fragment signals every earlier pass produced.
    correlations_pass.derive_correlations(d)

    arch = _assemble(d, root_name, root_path, arch_description)
    _flush(store, d)
    return d, arch


# ---------------------------------------------------------------------------
# metrics + project info (ported from the scanner, store-backed)
# ---------------------------------------------------------------------------

def _compute_metrics(d: Deriver) -> None:
    file_by_path = {fi.path: fi for fi in d._all_files}

    def compute(comp: Component) -> None:
        lang_counts: dict[str, int] = defaultdict(int)
        total_lines = total_size = symbol_count = 0
        for fpath in comp.files:
            fi = file_by_path.get(fpath)
            if not fi:
                continue
            total_lines += fi.lines
            total_size += fi.size_bytes
            lang_counts[fi.language] += fi.lines
            symbol_count += len(fi.symbols)
        comp.metrics = {
            "files": len(comp.files), "lines": total_lines,
            "size_bytes": total_size, "symbols": symbol_count,
            "languages": dict(lang_counts),
        }
        if lang_counts and not comp.language:
            comp.language = max(lang_counts, key=lang_counts.get)
        for child in comp.children:
            if isinstance(child, Component):
                compute(child)

    for comp in d._component_map.values():
        compute(comp)


def _project_description(d: Deriver, fallback: str) -> str:
    content = d.view.content("README.md") or d.view.content("README")
    if content:
        for line in content.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("="):
                return line[:200]
    return fallback


# ---------------------------------------------------------------------------
# assembly + store flush
# ---------------------------------------------------------------------------

def _assemble(d: Deriver, root_name: str, root_path: str, description: str) -> dict:
    components = _build_component_tree(d)
    _attach_capabilities(components, d._capabilities_by_component)
    _attach_entities(components, d._entities_by_component)
    _attach_rules(components, d._rules_by_component)
    _attach_id_refs(components, d._concerns_by_component, "concerns")
    _attach_id_refs(components, d._findings_by_component, "findings")
    relationships = _relationship_dicts(d)
    return {
        "name": root_name,
        "description": description,
        "repository": None,          # git remote is not a store fact
        "default_branch": "main",
        "generated_at": "",          # stripped by the parity normalizer
        "analyzer_version": "",      # stripped
        "root_path": root_path,      # stripped
        "components": components,
        "relationships": relationships,
        "capabilities": d.capabilities,   # flat index (P5-1); optional key
        "data_entities": d.data_entities, # flat index (P5-2); optional key
        "entity_access": d.entity_access, # flat index (P5-2); optional key
        "rules": d.rules,                 # flat index (P5-5); optional key
        "concerns": d.concerns,           # flat index (P5-6); optional key
        "findings": d.findings,           # ranked flat index (P5-6); optional key
        "symbols": [to_dict(s) for s in d._all_symbols],
        "files": [_file_dict(fi) for fi in d._all_files],
        "stats": _stats(d, relationships),
        "repositories": [],
    }


def _attach_capabilities(components: list, by_component: dict[str, list[dict]]) -> None:
    """Attach the optional per-component ``capabilities`` key in place.

    Set only when non-empty, so a component with no capabilities carries no key
    (matches the ai_enhance optional-key precedent; the viewer ignores it).
    """
    for comp in components:
        caps = by_component.get(comp.get("id"))
        if caps:
            comp["capabilities"] = caps
        _attach_capabilities(comp.get("children", []), by_component)


def _attach_entities(components: list, by_component: dict[str, list[dict]]) -> None:
    """Attach the optional per-component ``data_entities`` key in place (P5-2).

    Set only when non-empty, so a component with no entities carries no key
    (the ai_enhance optional-key precedent; the viewer ignores it).
    """
    for comp in components:
        ents = by_component.get(comp.get("id"))
        if ents:
            comp["data_entities"] = ents
        _attach_entities(comp.get("children", []), by_component)


def _attach_rules(components: list, by_component: dict[str, list[dict]]) -> None:
    """Attach the optional per-component ``rules`` key in place (P5-5).

    Set only when non-empty, so a component with no rules carries no key
    (the ai_enhance optional-key precedent; the viewer ignores it).
    """
    for comp in components:
        rls = by_component.get(comp.get("id"))
        if rls:
            comp["rules"] = rls
        _attach_rules(comp.get("children", []), by_component)


def _attach_id_refs(components: list, by_component: dict[str, list[str]], key: str) -> None:
    """Attach an optional per-component id-reference list in place (P5-6).

    Used for ``concerns`` and ``findings``: a component carries the ids of the
    concerns it belongs to and the findings that involve it (the full records
    live in the top-level flat indexes). Set only when non-empty, matching the
    ai_enhance optional-key precedent; old viewers ignore it.
    """
    for comp in components:
        refs = by_component.get(comp.get("id"))
        if refs:
            comp[key] = list(refs)
        _attach_id_refs(comp.get("children", []), by_component, key)


def _file_dict(fi) -> dict:
    dd = to_dict(fi)
    dd.setdefault("exports", [])
    return dd


def _relationship_dicts(d: Deriver) -> list[dict]:
    out = []
    for rel in d.relationships:
        dd = to_dict(rel)
        key = (rel.source, rel.target, rel.type)
        dd["evidence"] = d._rel_evidence.get(key, [])
        dd["confidence"] = d._rel_confidence.get(key)
        dd["origin"] = d._rel_origin.get(key)
        out.append(dd)
    for rel in d._ui_relationships:
        dd = to_dict(rel)
        key = (rel.source, rel.target, rel.type)
        dd["evidence"] = d._ui_edge_evidence.get(key, [])
        dd["confidence"] = "inferred"
        dd["origin"] = "static"
        out.append(dd)
    return out


def _build_component_tree(d: Deriver) -> list[dict]:
    children_map: dict[str, list[str]] = defaultdict(list)
    root_paths: list[str] = []
    for path in d._component_map:
        parent_path = d._find_parent_component(path)
        if parent_path is None or path == "":
            root_paths.append(path)
        else:
            children_map[parent_path].append(path)

    def serialize(path: str) -> dict:
        comp = d._component_map[path]
        dd = to_dict(comp)
        path_children = [serialize(cp) for cp in sorted(children_map.get(path, []))]
        ui_children = [to_dict(c) for c in comp.children if isinstance(c, Component)]
        dd["children"] = ui_children + path_children
        return dd

    return [serialize(p) for p in sorted(root_paths)]


def _stats(d: Deriver, relationships: list[dict]) -> dict:
    total_symbols = len(d._all_symbols)
    return {
        "total_files": len(d._all_files),
        "total_lines": d._total_lines,
        "total_size_bytes": d._total_size,
        "languages": dict(d._language_counts),
        "total_symbols": total_symbols,
        "total_symbols_detected": total_symbols,
        "total_components": len(d._component_map),
        "total_relationships": len(relationships),
    }


def _flush(store: FactStore, d: Deriver) -> None:
    """Write the derived components, memberships, and edges to the store.

    Passes read the store and write the store (TARGET-ARCHITECTURE.md 4.3).
    Components carry their role, port, framework and rich data in meta_json so
    the projection tier (P4-5) reads a complete component from the store.
    """
    store._conn.execute("DELETE FROM edges")
    store._conn.execute("DELETE FROM findings")        # derived; soft refs only
    store._conn.execute("DELETE FROM concerns")        # derived; soft refs only
    store._conn.execute("DELETE FROM rules")           # FK -> components
    store._conn.execute("DELETE FROM entity_access")   # FK -> data_entities
    store._conn.execute("DELETE FROM data_entities")   # FK -> components
    store._conn.execute("DELETE FROM capabilities")  # FK -> components; drop before components
    store._conn.execute("DELETE FROM component_files")
    store._conn.execute("DELETE FROM components")
    if store.with_fts:
        store._conn.execute("DELETE FROM fts_docs WHERE ref_kind = 'component'")

    path_to_file_id = {f["path"]: f["id"] for f in d.view.files}

    for path in sorted(d._component_map):
        comp = d._component_map[path]
        parent = d._find_parent_component(path)
        meta = {
            "framework": comp.framework, "port": comp.port,
            "description": comp.description, "config_files": comp.config_files,
            "docs": comp.docs, "metrics": comp.metrics,
            "testing": comp.testing, "external_services": comp.external_services,
            "actions": comp.actions, "language": comp.language,
        }
        store.add_component(
            component_id=comp.id, name=comp.name, type=comp.type, path=comp.path,
            parent_id=(d._component_map[parent].id if parent is not None and parent in d._component_map else None),
            role=comp.type, meta=meta,
            description=(comp.docs.get("purpose") if comp.docs else None),
        )
        for fpath in comp.files:
            fid = path_to_file_id.get(fpath)
            if fid is not None:
                store.link_component_file(comp.id, fid)

    for rel in list(d.relationships) + list(d._ui_relationships):
        key = (rel.source, rel.target, rel.type)
        store.add_edge(
            source_id=rel.source, target_id=rel.target, type=rel.type,
            evidence=d._rel_evidence.get(key) or d._ui_edge_evidence.get(key) or [],
            confidence=d._rel_confidence.get(key, "inferred"),
            origin=d._rel_origin.get(key, "static"),
        )

    # Capabilities land in the store (system of record, I6). Written after
    # components so the FK to components(id) holds; ids are content-derived so a
    # re-derive is idempotent. The defining symbol link, where resolved, rides
    # inside detail_json (the schema has no symbol column; additive, no migration).
    for cap in d.capabilities:
        store.add_capability(
            capability_id=cap["id"], component_id=cap["component_id"],
            kind=cap["kind"], name=cap["name"], detail=cap["detail"],
            evidence=cap["evidence"], confidence=cap["confidence"],
        )

    # Data entities and access edges land in the store (system of record, P5-2).
    # Entities are written after components (FK to components(id)); access edges
    # after entities (FK to data_entities(id)). Ids are content-derived, so a
    # re-derive is idempotent. The frozen P4-1 schema gives data_entities a
    # ``fields_json`` payload column (the entity analog of capabilities'
    # ``detail_json``): it carries the field list plus the framework/table/
    # symbol/inferred detail, so nothing is lost with no migration (I3/I4).
    written_entity_ids: set[str] = set()
    for ent in d.data_entities:
        detail = {"fields": list(ent.get("fields", [])),
                  "framework": ent.get("framework")}
        if ent.get("table"):
            detail["table"] = ent["table"]
        if ent.get("symbol"):
            detail["symbol"] = ent["symbol"]
        if ent.get("inferred"):
            detail["inferred"] = True
        store.add_data_entity(
            entity_id=ent["id"], component_id=ent["component_id"],
            name=ent["name"], kind=ent["kind"], fields=detail,
            evidence=ent.get("evidence", []),
        )
        written_entity_ids.add(ent["id"])
    for acc in d.entity_access:
        if acc["entity_id"] not in written_entity_ids:
            continue
        store.add_entity_access(
            accessor_id=acc["accessor_id"], entity_id=acc["entity_id"],
            mode=acc["mode"], evidence=acc["evidence"], confidence=acc["confidence"],
        )

    # Rules land in the store (system of record, P5-5). Written after components
    # so the FK to components(id) holds; ids are content-derived so a re-derive
    # is idempotent. The enclosing-symbol, trigger-capability, entity-link, and
    # constrained-field detail rides inside detail_json (the additive
    # payload-column pattern capabilities/entities use; no migration beyond the
    # v2 -> v3 rules table itself, I3/I4).
    for rule in d.rules:
        store.add_rule(
            rule_id=rule["id"], component_id=rule["component_id"],
            kind=rule["kind"], summary=rule["summary"], detail=rule["detail"],
            evidence=rule["evidence"], confidence=rule["confidence"],
        )

    # Correlations land in the store (system of record, P5-6). Concerns and
    # findings reference components by soft id (not FK), so ordering relative to
    # components does not matter; ids are content-derived so a re-derive is
    # idempotent. Findings default to verification_status='unverified' (P7-4
    # flips it, I15) and carry a deterministic rank_score (I11).
    for concern in d.concerns:
        store.add_concern(
            concern_id=concern["id"], kind=concern["kind"],
            title=concern.get("title"), basis=concern.get("basis"),
            members=concern["members"], detail=concern.get("detail"),
        )
    for finding in d.findings:
        store.add_finding(
            finding_id=finding["id"], kind=finding["kind"],
            summary=finding.get("summary"), members=finding["members"],
            evidence=finding.get("evidence"), confidence=finding.get("confidence"),
            verification_status=finding["verification_status"],
            rank_score=finding["rank_score"], detail=finding.get("detail"),
        )
    store.commit()
