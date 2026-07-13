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
from . import components as components_pass
from . import docs as docs_pass
from . import flow as flow_pass
from . import relationships as rel_pass
from . import roles as roles_pass
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
        "symbols": [to_dict(s) for s in d._all_symbols],
        "files": [_file_dict(fi) for fi in d._all_files],
        "stats": _stats(d, relationships),
        "repositories": [],
    }


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
    store.commit()
