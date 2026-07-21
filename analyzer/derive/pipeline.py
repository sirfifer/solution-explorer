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

from ..contracts import Isolator, finalize_gaps, require, unresolved_reference_count
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
from . import storyboard as storyboard_pass
from . import testing as testing_pass
from .context import Deriver
from .storeview import StoreView

_REQUIRED_ARCH_KEYS = ("name", "components", "relationships", "symbols", "files", "stats")


def _tree_component_ids(components: list) -> list:
    """Collect every component id in the assembled tree, depth-first.

    Includes UI-flow children (Component nodes added under ``children`` by the
    flow passes), because they are real nodes the viewer renders and relationship
    endpoints legitimately point at them. Returned as a list (not a set) so the
    caller can detect duplicates.
    """
    ids: list = []

    def walk(comps: list) -> None:
        for comp in comps:
            ids.append(comp.get("id"))
            walk(comp.get("children", []))

    walk(components)
    return ids


def _check_output_contract(arch: dict) -> None:
    """Shape-and-completeness postcondition for the assembled architecture (R1).

    Asserts presence, shape, the by-construction count-consistency (each stats
    total is computed from the very array it summarizes), and, from wave 5, the
    cross-reference and count consistency that a whole assembled projection must
    satisfy. Shape-and-completeness only, never what a value IS (no validation
    creep). A clean run never trips it, so byte parity is preserved.

    The wave-5 additions were validated to produce ZERO gaps and no drift across
    flask, fastapi, the storyboard fixture, and the real iOS demo (530
    relationships, rich SwiftUI flows), which is what makes them safe:

      - Component id UNIQUENESS across the whole tree. A duplicate id is a real
        collision bug (F-CRIT-5 territory); none occurs on any validated corpus.
      - Relationship ENDPOINT RESOLUTION: every source and target resolves to a
        node id present in the tree. The earlier deferral worried that UI targets
        reference ids outside the component map, but the flow passes ADD those
        UI-flow children to the assembled tree, so UI edges resolve to them (0
        unresolved endpoints on the iOS demo's 530 edges). A dangling endpoint is
        a real inconsistency worth surfacing.
      - total_components BOUND: total_components counts the path-component map,
        which UI-flow children legitimately exceed in the tree (iOS demo: 99 vs
        190 nodes), so it is NOT equated to the node count. It is bounded instead:
        at least the number of root components (which are all path components) and
        at most the number of distinct tree node ids. This catches a count that
        is grossly inflated or below the roots it must contain, without the
        false-positive the naive tree-equality check would raise on UI repos.
    """
    require(isinstance(arch, dict), "derive output is not a dict")
    for key in _REQUIRED_ARCH_KEYS:
        require(key in arch, f"derive output missing required key '{key}'")
    for key in ("components", "relationships", "symbols", "files"):
        require(isinstance(arch[key], list), f"derive output '{key}' is not a list")
    require(isinstance(arch["stats"], dict), "derive output 'stats' is not a dict")
    stats = arch["stats"]
    require(
        stats.get("total_relationships") == len(arch["relationships"]),
        "stats.total_relationships does not match the relationships array",
    )
    require(
        stats.get("total_symbols") == len(arch["symbols"]),
        "stats.total_symbols does not match the symbols array",
    )
    require(
        stats.get("total_files") == len(arch["files"]),
        "stats.total_files does not match the files array",
    )

    # Cross-reference and count consistency (wave 5).
    tree_ids = _tree_component_ids(arch["components"])
    id_set = set(tree_ids)
    require(
        len(tree_ids) == len(id_set),
        "component tree contains duplicate component ids",
    )
    endpoints: list = []
    for rel in arch["relationships"]:
        endpoints.append(rel.get("source"))
        endpoints.append(rel.get("target"))
    require(
        unresolved_reference_count(id_set, endpoints) == 0,
        "one or more relationship endpoints do not resolve to a component tree id",
    )
    total_components = stats.get("total_components")
    require(
        isinstance(total_components, int)
        and len(arch["components"]) <= total_components <= len(id_set),
        "stats.total_components is out of the [root components, distinct tree ids] bound",
    )


def _skeleton_arch(root_name: str, root_path: str, description: str) -> dict:
    """A minimal but contract-valid architecture for the assembly-failure gap.

    Same top-level shape as ``_assemble`` with every collection empty and the
    stats totals at zero, so it passes ``_check_output_contract`` (its counts are
    consistent by construction). It is the honest "assembly produced nothing"
    fallback: severe degradation, but a whole well-formed document the viewer can
    render around, paired with the ``derive.assemble`` gap that explains it.
    """
    return {
        "name": root_name,
        "description": description,
        "repository": None,
        "default_branch": "main",
        "generated_at": "",
        "analyzer_version": "",
        "root_path": root_path,
        "components": [],
        "relationships": [],
        "capabilities": [],
        "data_entities": [],
        "entity_access": [],
        "rules": [],
        "concerns": [],
        "findings": [],
        "symbols": [],
        "files": [],
        "stats": {
            "total_files": 0,
            "total_lines": 0,
            "total_size_bytes": 0,
            "languages": {},
            "total_symbols": 0,
            "total_symbols_detected": 0,
            "total_components": 0,
            "total_relationships": 0,
        },
        "repositories": [],
    }


def derive_all(
    store: FactStore,
    root_name: str,
    *,
    repo: str = ".",
    root_path: str = "",
    description: str = "",
) -> tuple[Deriver, dict]:
    """Run all derivation passes and return (Deriver, architecture dict).

    Each pass runs under per-unit isolation (card R1): a pass that raises degrades
    to a deterministic honest gap recorded on ``arch["gaps"]`` instead of crashing
    the run, and the remaining passes still run. A healthy run records no gaps and
    omits the key entirely, so its output is byte-identical to the pre-isolation
    behavior (the golden gate and the full-vs-incremental byte-parity tests hold).
    """
    view = StoreView.load(store)
    d = Deriver(view, root_name, repo=repo)

    gaps: list = []
    iso = Isolator("derive", gaps)

    iso.run("derive.components.discover", components_pass.discover_components, d)
    iso.run("derive.components.associate-files", components_pass.associate_files, d)
    iso.run("derive.components.rekey-symbols", components_pass.rekey_symbols, d, store)
    iso.run("derive.roles.promote-types", roles_pass.promote_component_types, d)
    iso.run("derive.roles.improve-names", roles_pass.improve_component_names, d)
    iso.run("derive.roles.assign-ports", roles_pass.assign_server_ports, d)
    iso.run("derive.flow.ui-flows", flow_pass.detect_ui_flows, d)
    iso.run("derive.flow.ui-actions", flow_pass.detect_ui_actions, d)
    iso.run("derive.storyboard", storyboard_pass.derive_storyboard_flow, d)
    iso.run("derive.relationships", rel_pass.derive_relationships, d)
    iso.run("derive.metrics", _compute_metrics, d)
    iso.run("derive.testing", testing_pass.detect_testing, d)
    arch_description = iso.run(
        "derive.project-description", _project_description, d, description,
        default=description,
    )
    iso.run("derive.docs", docs_pass.extract_component_docs, d)
    iso.run("derive.capabilities", capabilities_pass.derive_capabilities, d)
    iso.run("derive.entities", entities_pass.derive_entities, d)
    iso.run("derive.rules", rules_pass.derive_rules, d)
    # Correlations run last: they read the components, edges, capabilities,
    # entities, rules, and clone-fragment signals every earlier pass produced.
    iso.run("derive.correlations", correlations_pass.derive_correlations, d)

    # Assembly is itself a producer: if a preceding pass corrupted shared state
    # before it degraded, assembly can raise. Isolate it too, degrading to a
    # minimal but contract-valid skeleton so the run still completes with an
    # honest gap instead of a crash (the skeleton is built lazily, so a healthy
    # run pays nothing).
    arch = iso.run(
        "derive.assemble", _assemble, d, root_name, root_path, arch_description,
        default_factory=lambda: _skeleton_arch(root_name, root_path, arch_description),
    )
    # Self-validating output: the assembled result must be shape-and-complete at
    # handoff. A violation is an honest gap, not a crash.
    iso.run("derive.output-contract", _check_output_contract, arch)
    # Flushing derived facts to the store is itself a producer: a store-write
    # failure degrades to a gap, and the arch dict (which the projection reads for
    # its components) is still returned whole.
    iso.run("derive.flush", _flush, store, d)

    if gaps:
        arch["gaps"] = finalize_gaps(gaps)
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
