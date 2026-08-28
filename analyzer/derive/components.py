"""Component discovery, file association, and symbol re-keying (Tier 3).

Re-expresses ``ArchitectureScanner._discover_components`` and the component and
framework/port bits of ``_scan_files`` over the store. Marker-file existence
comes from the coverage ledger; marker-file content (for config parsing) comes
from the extraction cache through the StoreFS shim. Nothing reads the disk.

After discovery this pass re-keys the symbol grammar ids: the extraction tier
assigned each symbol's component segment with a lightweight nearest-marker
resolver (P4-2 Discovered row); component discovery here is authoritative, so
every symbol id (and its FTS row) is rebuilt via the frozen grammar in
analyzer/store/ids.py against the discovered component that owns the file.
"""

from __future__ import annotations

import os

from ..config_parsers import (
    parse_cargo_toml,
    parse_docker_compose,
    parse_gemfile,
    parse_package_json,
    parse_pyproject_toml,
    parse_sam_template,
    parse_serverless_yml,
)
from ..constants import COMPONENT_MARKERS, LANGUAGE_MAP
from ..models import Component
from ..utils import _framework_priority, _should_skip_dir
from .context import Deriver


def discover_components(d: Deriver) -> None:
    root_comp = Component(
        id=d._make_component_id(""), name=d.root_name, type="project", path="",
    )
    d._component_map[""] = root_comp

    dirs = [x for x in d.all_dirs_sorted()]

    # Register vendored repos (the extraction tier already detected and pruned
    # them; recreate the single "library" component the scanner would emit).
    for rel in sorted(d.view.vendored_dirs):
        comp_id = d._make_component_id(rel)
        if rel not in d._component_map:
            d._component_map[rel] = Component(
                id=comp_id, name=os.path.basename(rel), type="library", path=rel,
            )
        d._vendored_paths.add(rel)

    # Pass 1: markers.
    for rel in dirs:
        if rel and any(_should_skip_dir(seg) for seg in rel.split("/")):
            continue
        if rel in d._vendored_paths or d._is_under_vendored(rel):
            continue

        filenames = d.files_in_dir(rel)
        for marker, (lang, comp_type) in COMPONENT_MARKERS.items():
            if marker in filenames:
                # Scanner parity: the old engine's guard compares the component
                # ID against the path-keyed map, so the root (path "", id
                # "root") always passes and a root marker file replaces the
                # initial "project" component. Replicated exactly.
                comp_id = d._make_component_id(rel)
                if comp_id not in d._component_map:
                    name = os.path.basename(rel) if rel else d.root_name
                    comp = Component(
                        id=comp_id, name=name, type=comp_type,
                        path=rel, language=lang,
                    )
                    _apply_marker_metadata(d, comp, rel, marker)
                    d._component_map[rel] = comp
                break

    # Docker Compose services are architectural units even when they have no
    # source directory of their own. The config parser already extracted their
    # names and ports; collapsing db/cache into the repository root throws away
    # deterministic information and asks enrichment prose to compensate for a
    # component the map cannot address. Materialize only services that do not
    # already correspond to a discovered source component (for example the
    # fixture's ``api`` service is already ``services/api``).
    existing_service_names = {
        name
        for comp in d._component_map.values()
        for name in (
            comp.name.lower(),
            os.path.basename(comp.path).lower() if comp.path else "",
            comp.id.rsplit("/", 1)[-1].lower(),
        )
        if name
    }
    compose_components: list[tuple[str, Component]] = []
    for rel, owner in list(d._component_map.items()):
        for config in owner.config_files:
            if config.get("type") != "docker-compose":
                continue
            ports = {
                str(item.get("service") or ""): item.get("host")
                for item in (config.get("ports") or [])
                if isinstance(item, dict)
            }
            for service in config.get("services") or []:
                service = str(service).strip()
                if not service or service.lower() in existing_service_names:
                    continue
                base = os.path.join(rel, "compose") if rel else "compose"
                path = os.path.join(base, service)
                if path in d._component_map:
                    continue
                lowered = service.lower()
                if lowered in {
                    "db", "database", "postgres", "postgresql", "mysql",
                    "mariadb", "mongodb", "mongo",
                }:
                    comp_type = "database"
                elif lowered in {"cache", "redis", "memcached"}:
                    comp_type = "cache"
                else:
                    comp_type = "infrastructure"
                port = ports.get(service)
                compose_components.append((path, Component(
                    id=d._make_component_id(path),
                    name=service,
                    type=comp_type,
                    path=path,
                    description=(
                        f"Docker Compose service '{service}' declared in "
                        f"{config.get('path') or 'compose config'}"
                    ),
                    port=port if isinstance(port, int) else None,
                    config_files=[{
                        "type": "docker-compose-service",
                        "path": config.get("path"),
                        "service_name": service,
                    }],
                )))
                existing_service_names.add(lowered)
    d._component_map.update(compose_components)

    # Pass 2: intermediate module directories with >= 2 code files.
    for rel in dirs:
        if not rel:
            continue
        if any(_should_skip_dir(seg) for seg in rel.split("/")):
            continue
        if d._is_under_vendored(rel):
            continue
        filenames = d.files_in_dir(rel)
        code_files = [f for f in filenames if os.path.splitext(f)[1].lower() in LANGUAGE_MAP]
        if len(code_files) >= 2 and rel not in d._component_map:
            depth = rel.count(os.sep)
            if depth <= 4:
                parent_id = d._find_parent_component(rel)
                if parent_id is not None:
                    d._component_map[rel] = Component(
                        id=d._make_component_id(rel), name=os.path.basename(rel),
                        type="module", path=rel,
                    )


def _apply_marker_metadata(d: Deriver, comp: Component, rel: str, marker: str) -> None:
    """Config-file parsing at discovery, ported from the scanner (store-backed)."""
    marker_path = (d.root / rel / marker) if rel else (d.root / marker)
    rel_marker = os.path.join(rel, marker) if rel else marker

    if marker == "package.json":
        info = parse_package_json(marker_path)
        comp.name = info.get("name", comp.name)
        comp.description = info.get("description", "")
        comp.config_files.append({"type": "package.json", "path": rel_marker})
    elif marker == "Cargo.toml":
        info = parse_cargo_toml(marker_path)
        comp.name = info.get("name", comp.name) or comp.name
        comp.config_files.append({"type": "Cargo.toml", "path": rel_marker})
    elif marker == "pyproject.toml":
        info = parse_pyproject_toml(marker_path)
        comp.name = info.get("name", comp.name) or comp.name
        comp.config_files.append({"type": "pyproject.toml", "path": rel_marker})
    elif marker in ("docker-compose.yml", "docker-compose.yaml"):
        info = parse_docker_compose(marker_path)
        svc_names = info.get("services", [])
        if svc_names:
            comp.description = f"Services: {', '.join(svc_names)}"
        dc_ports = info.get("ports", [])
        if dc_ports and not comp.port:
            comp.port = dc_ports[0].get("host")
        comp.config_files.append({"type": "docker-compose", "path": rel_marker, **info})
    elif marker == "Info.plist":
        comp.type = "application"
        # Info.plist is binary and is not cached as text, so its name cannot be
        # parsed from the store. The component keeps its directory name. This is
        # the one config parse that cannot run store-only; recorded in Evidence.
        comp.config_files.append({"type": "Info.plist", "path": rel_marker})
    elif marker == "Gemfile":
        info = parse_gemfile(marker_path)
        if info.get("name"):
            comp.name = info["name"]
        comp.config_files.append({"type": "Gemfile", "path": rel_marker})
    elif marker in ("template.yaml", "template.yml"):
        info = parse_sam_template(marker_path)
        if info.get("functions"):
            comp.type = "api-server"
            fn_names = [f["name"] for f in info["functions"]]
            comp.description = f"AWS SAM: {', '.join(fn_names)}"
            if len(fn_names) == 1:
                comp.name = fn_names[0]
        comp.config_files.append({"type": "sam-template", "path": rel_marker, **info})
    elif marker in ("serverless.yml", "serverless.yaml"):
        info = parse_serverless_yml(marker_path)
        if info.get("functions"):
            comp.type = "api-server"
            fn_names = [f["name"] for f in info["functions"]]
            comp.description = f"Serverless: {', '.join(fn_names)}"
        comp.config_files.append({"type": "serverless", "path": rel_marker, **info})


def associate_files(d: Deriver) -> None:
    """Build the file list from the store and attach each file to a component.

    Also assigns framework and discovery-time ports from signals, mirroring the
    per-file work the scanner does in ``_scan_files`` (but reading extracted
    signals instead of re-parsing content).
    """
    from ..models import FileInfo

    server_types = {"api-server", "service", "infrastructure"}
    code_langs_present: dict[str, str] = {}

    for frow in sorted(d.view.files, key=lambda f: f["path"]):
        rel = frow["path"]
        if frow.get("parse_status") == "ci_config":
            # Store-internal rows cached for the root-bounded CI check; the
            # old engine excludes these paths from the architecture's files.
            continue
        if d._is_under_vendored(rel):
            continue
        lang = frow["language"] or ""
        lines = frow["lines"] or 0
        size = frow["size_bytes"] or 0
        d._total_lines += lines
        d._total_size += size
        if lang:
            d._language_counts[lang] += lines

        fi = FileInfo(
            path=rel, language=lang, lines=lines, size_bytes=size,
            symbols=list(d._symbol_ids_by_file.get(rel, [])),
            imports=list(d.view.imports(rel)),
            module_doc=d.view.module_doc_by_path.get(rel),
        )
        d._all_files.append(fi)

        comp = d._find_component_for_file(rel)
        if comp:
            comp.files.append(rel)

        # framework signal -> component (priority-resolved)
        sigs = d.view.signals(rel)
        for s in sigs:
            if s["kind"] == "framework":
                fw = (s["value"] or {}).get("name")
                if fw and comp:
                    if not comp.framework:
                        comp.framework = fw
                    elif _framework_priority(fw) > _framework_priority(comp.framework):
                        comp.framework = fw
        # discovery-time port (only server-typed components, as in the scanner)
        from ..constants import CODE_LANGUAGES
        if lang in CODE_LANGUAGES and comp and not comp.port and comp.type in server_types:
            for s in sigs:
                if s["kind"] == "port":
                    comp.port = (s["value"] or {}).get("port")
                    break

    _ = code_langs_present


def rekey_symbols(d: Deriver, store) -> None:
    """Re-key symbol grammar ids to the authoritative discovered components.

    The extraction tier used a nearest-marker component resolver for the id's
    component segment; component discovery is authoritative, so rebuild every id
    (and its FTS row) via the frozen grammar. Ids are reassigned per file in
    stored order so collision disambiguators stay stable (analyzer/store/ids.py).
    Parent references are remapped through the old->new id map.
    """
    from ..store import assign_symbol_ids, parse_symbol_id

    rows = store.symbols()  # ordered by id; re-group by file in stored order
    id_to_path = {f["id"]: f["path"] for f in d.view.files}

    # Group symbol rows by file, preserving each file's internal order via line
    # then id (a deterministic, store-independent order).
    by_file: dict[str, list[dict]] = {}
    for r in rows:
        fpath = id_to_path.get(r["file_id"])
        if fpath is None:
            continue
        by_file.setdefault(fpath, []).append(r)
    for fpath in by_file:
        by_file[fpath].sort(key=lambda r: (r["line"] if r["line"] is not None else 0, r["id"]))

    remap: dict[str, str] = {}
    new_rows: list[dict] = []
    for fpath in sorted(by_file):
        comp = d._find_component_for_file(fpath)
        component_seg = comp.id if comp else "."
        old_rows = by_file[fpath]
        records = []
        for r in old_rows:
            sid = parse_symbol_id(r["id"])
            records.append((d.repo, component_seg, sid.file, sid.path))
        new_ids = assign_symbol_ids(records)
        for r, new_id in zip(old_rows, new_ids, strict=True):
            remap[r["id"]] = new_id
            nr = dict(r)
            nr["id"] = new_id
            new_rows.append(nr)

    # Rewrite the symbols table (and its FTS rows) with the re-keyed ids.
    store._conn.execute("DELETE FROM symbols")
    if store.with_fts:
        store._conn.execute("DELETE FROM fts_docs WHERE ref_kind = 'symbol'")
    for nr in sorted(new_rows, key=lambda r: r["id"]):
        parent = nr.get("parent_id")
        store.add_symbol(
            symbol_id=nr["id"], file_id=nr["file_id"], name=nr["name"],
            kind=nr.get("kind"), parent_id=remap.get(parent, parent) if parent else None,
            line=nr.get("line"), end_line=nr.get("end_line"),
            visibility=nr.get("visibility"), docstring=nr.get("docstring"),
            code_preview=nr.get("code_preview"),
        )
    store.commit()

    # Reflect the re-keying in the in-memory model so metrics and the assembled
    # architecture use the authoritative ids.
    for fi in d._all_files:
        fi.symbols = [remap.get(s, s) for s in fi.symbols]
    for sym in d._all_symbols:
        sym.id = remap.get(sym.id, sym.id)
        if sym.parent:
            sym.parent = remap.get(sym.parent, sym.parent)
    new_by_file: dict[str, list[str]] = {}
    for fpath, rlist in by_file.items():
        new_by_file[fpath] = [remap[r["id"]] for r in rlist]
    d._symbol_ids_by_file.clear()
    d._symbol_ids_by_file.update(new_by_file)
