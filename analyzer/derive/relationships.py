"""Relationship inference as joins over signals (Tier 3, invariant I3).

Re-expresses ``ArchitectureScanner._detect_relationships`` and its helpers as
joins over the signals the extraction tier already emitted (port, url_reference,
http_client, db_driver, queue_driver, websocket_driver, grpc_driver) plus the
imports carried in the extraction facts. The old engine's O(components x files)
content rescans are gone: each edge is built from a stored signal and carries
its evidence (file, line, snippet) and a confidence tier (``certain`` for a
parsed fact resolved deterministically, ``inferred`` for a heuristic join).

Faithfulness note (enumerated for the P4-7 gate): port and service references
are joined from ``url_reference`` / ``http_client`` signals rather than a raw
content rescan, so a bare ``localhost:PORT`` or ``PORT=`` reference that is not
also a captured URL signal no longer yields an http edge. On the current
fixtures every real reference is a captured URL, so there is no diff.
"""

from __future__ import annotations

import os
import re
from typing import Optional
from urllib.parse import urlsplit

from ..constants import (
    AUTH_PATTERNS,
    DATA_FORMAT_PATTERNS,
    DOCKER_SERVICE_TYPES,
    EXTERNAL_CLOUD_APIS,
    GRPC_PATTERNS,
    MIDDLEWARE_PATTERNS,
    WEBSOCKET_PATTERNS,
)
from ..models import Relationship
from .context import Deriver

CLIENT_TYPES = {"ios-client", "android-client", "web-client", "mobile-client", "watch-app"}

# Component types that genuinely declare a network endpoint another component can
# call. An http edge to a target that is neither of these and binds no port is
# fabricated (D2), so it is never drawn from a name match alone.
SERVER_TYPES = {"api-server", "service", "infrastructure"}


def _evidence(file: str, line: Optional[int], snippet: str = "") -> list[dict]:
    return [{"file": file, "line": line, "snippet": snippet}]


def _sig_line(signals: list[dict], kind: str) -> Optional[int]:
    for s in signals:
        if s["kind"] == kind:
            return s["line"]
    return None


def derive_relationships(d: Deriver) -> None:
    relationships: list[Relationship] = []
    seen: set = set()
    evidence_by_key: dict = {}
    confidence_by_key: dict = {}
    origin_by_key: dict = {}

    content_ids = {c.id for c in d._component_map.values() if c.type == "content"}

    def add(src, tgt, type_, evidence, confidence, origin="static", **kw):
        key = (src, tgt, type_)
        if key in seen:
            return
        seen.add(key)
        relationships.append(Relationship(source=src, target=tgt, type=type_, **kw))
        evidence_by_key[key] = evidence
        confidence_by_key[key] = confidence
        origin_by_key[key] = origin

    # -- import edges (parsed imports resolved to components) --------------
    for fi in d._all_files:
        source_comp = d._find_component_for_file(fi.path)
        if not source_comp or source_comp.id in content_ids:
            continue
        for imp in fi.imports:
            target_comp = _resolve_import_to_component(d, imp, fi.path)
            if (target_comp and target_comp.id != source_comp.id
                    and target_comp.id not in content_ids):
                line = _locate(d, fi.path, imp)
                confidence = "certain" if imp.startswith(".") else "inferred"
                add(source_comp.id, target_comp.id, "import",
                    _evidence(fi.path, line, imp), confidence, "static", label=imp)

    # -- port-based http edges (port binding join url_reference) -----------
    port_map: dict[int, object] = {}
    for comp in d._component_map.values():
        if comp.port and comp.id not in content_ids:
            port_map[comp.port] = comp

    for fi in d._all_files:
        source_comp = d._find_component_for_file(fi.path)
        if not source_comp or source_comp.id in content_ids:
            continue
        urls = _url_signals(d, fi.path)
        for port, target_comp in port_map.items():
            if target_comp.id == source_comp.id:
                continue
            for url, line in urls:
                if re.search(rf":{port}\b", url):
                    add(source_comp.id, target_comp.id, "http",
                        _evidence(fi.path, line, url), "inferred", "static",
                        port=port, protocol="HTTP", label=f"port {port}",
                        bidirectional=True)
                    break

    # -- service-name http edges (url_reference join component name) -------
    service_name_map: dict[str, object] = {}
    for comp in d._component_map.values():
        if comp.id in content_ids:
            continue
        variants = [
            comp.name.lower().replace(" ", "-").replace("_", "-"),
            comp.name.lower().replace(" ", "_").replace("-", "_"),
            comp.name.lower().replace(" ", "").replace("-", "").replace("_", ""),
        ]
        if comp.path:
            dn = os.path.basename(comp.path).lower()
            variants += [dn, dn.replace("-", "_"), dn.replace("_", "-")]
        for v in variants:
            if v and len(v) > 2:
                service_name_map[v] = comp

    for fi in d._all_files:
        source_comp = d._find_component_for_file(fi.path)
        if not source_comp or source_comp.id in content_ids:
            continue
        # Only full URL references (with a scheme) can resolve to a callable
        # host. Bare service tokens (a `service:port` fragment captured from a
        # code string) stay per-component signals, never edges (D2): they are
        # exactly the fuzzy evidence that fabricated cross-fixture edges.
        refs = _url_signals(d, fi.path)
        for ref, line in refs:
            # D2: an http edge is drawn only when the URL host authority resolves
            # EXACTLY to a component that actually declares an endpoint (a bound
            # port or a server-type component). A component name appearing as a
            # substring somewhere inside an arbitrary URL (a github.com path, a
            # docs link, a token inside a test string) is not a call: the
            # url_reference stays a per-component signal, never an edge (external
            # cloud domains are captured by _external_services below).
            host = _url_host(ref)
            if not host or len(host) < 4:
                continue
            target_comp = service_name_map.get(host)
            if target_comp is None or target_comp.id == source_comp.id:
                continue
            if not _declares_endpoint(target_comp):
                continue
            add(source_comp.id, target_comp.id, "http",
                _evidence(fi.path, line, ref), "inferred", "static",
                protocol="HTTP", label=f"calls {host}", bidirectional=True)

    # -- client -> api-server via http_client signal -----------------------
    api_servers = [c for c in d._component_map.values()
                   if c.type in ("api-server", "service") and c.id not in content_ids]
    for fi in d._all_files:
        source_comp = d._find_component_for_file(fi.path)
        if not source_comp or source_comp.id in content_ids:
            continue
        if source_comp.type not in CLIENT_TYPES:
            continue
        hc_line = _sig_line(d.view.signals(fi.path), "http_client")
        if hc_line is None:
            continue
        urls = {u.lower() for u, _ in _url_signals(d, fi.path)}
        for api in api_servers:
            if api.id == source_comp.id:
                continue
            indicators = [
                api.name.lower().replace(" ", "-"),
                api.name.lower().replace(" ", "_"),
                os.path.basename(api.path).lower() if api.path else "",
            ]
            if api.port:
                indicators.append(f":{api.port}")
            matched = any(ind and len(ind) > 2 and ind in u
                          for u in urls for ind in indicators)
            if not matched and len(api_servers) == 1:
                matched = True
            if matched:
                add(source_comp.id, api.id, "http",
                    _evidence(fi.path, hc_line, "http client"), "inferred", "static",
                    protocol="HTTP", label="API call", bidirectional=True)

    # -- watch app -> iOS companion ----------------------------------------
    watch_apps = [c for c in d._component_map.values() if c.type == "watch-app"]
    ios_clients = [c for c in d._component_map.values() if c.type == "ios-client"]
    if watch_apps and ios_clients:
        for watch in watch_apps:
            best_ios = ios_clients[0]
            watch_parent = os.path.dirname(watch.path) if watch.path else ""
            for ios in ios_clients:
                ios_parent = os.path.dirname(ios.path) if ios.path else ""
                if (watch_parent == ios_parent
                        or watch.name.lower().replace(" watch", "")
                        .replace("watch", "").strip() in ios.name.lower()):
                    best_ios = ios
                    break
            add(watch.id, best_ios.id, "import",
                _evidence(watch.path, None, "companion app"), "inferred", "static",
                label="companion app")

    # -- docker-compose depends_on ----------------------------------------
    docker_services: dict[str, object] = {}
    for comp in d._component_map.values():
        for config in comp.config_files:
            if config.get("type") == "docker-compose":
                sn = config.get("service_name", "").lower()
                if sn:
                    docker_services[sn] = comp
                docker_services[comp.name.lower().replace(" ", "-")] = comp
    for comp in d._component_map.values():
        for config in comp.config_files:
            if config.get("type") == "docker-compose":
                for dep in config.get("depends_on", []):
                    target = docker_services.get(dep.lower())
                    if target and target.id != comp.id:
                        add(comp.id, target.id, "docker",
                            _evidence(next((c["path"] for c in comp.config_files
                                            if c.get("type") == "docker-compose"), ""), None,
                                      f"depends_on: {dep}"),
                            "certain", "config", label="depends_on")

    # -- client -> all-servers fallback (small projects) -------------------
    clients = [c for c in d._component_map.values()
               if c.type in CLIENT_TYPES and c.id not in content_ids]
    if clients and api_servers:
        client_ids = {c.id for c in clients}
        has_client_http = any(
            r.source in client_ids and r.type == "http" for r in relationships)
        if not has_client_http:
            for client in clients:
                for server in api_servers:
                    add(client.id, server.id, "http",
                        _evidence(client.path, None, "inferred single-backend"),
                        "inferred", "static",
                        protocol="HTTP", label="API (inferred)", bidirectional=True)

    # -- external services metadata (url_reference join cloud domains) -----
    _external_services(d, content_ids)

    # -- WatchConnectivity imports confirm Watch-iOS pairing ---------------
    from ..constants import WATCH_CONNECTIVITY_IMPORTS

    for fi in d._all_files:
        if fi.language != "swift":
            continue
        for imp in fi.imports:
            if imp in WATCH_CONNECTIVITY_IMPORTS:
                source_comp = d._find_component_for_file(fi.path)
                if not source_comp:
                    continue
                line = _locate(d, fi.path, f"import {imp}")
                if source_comp.type == "ios-client":
                    for watch in watch_apps:
                        add(watch.id, source_comp.id, "import",
                            _evidence(fi.path, line, f"import {imp}"),
                            "inferred", "static", label="WatchConnectivity")
                elif source_comp.type == "watch-app":
                    for ios in ios_clients:
                        add(source_comp.id, ios.id, "import",
                            _evidence(fi.path, line, f"import {imp}"),
                            "inferred", "static", label="WatchConnectivity")
                break  # only once per file

    # -- env / next.config API URLs join api servers -----------------------
    env_patterns = [
        r'(?:NEXT_PUBLIC_)?(?:API_URL|BACKEND_URL|SERVER_URL|WS_URL)\s*[=:]\s*["\']?([^"\'\s\n]+)',
        r'(?:destination|source|rewrites).*?["\']https?://([^"\']+)["\']',
    ]
    for fi in d._all_files:
        filename = os.path.basename(fi.path)
        if not (filename.startswith(".env") or filename in
                ("next.config.js", "next.config.ts", "next.config.mjs")):
            continue
        source_comp = d._find_component_for_file(fi.path)
        if not source_comp or source_comp.id in content_ids:
            continue
        if source_comp.type not in CLIENT_TYPES:
            continue
        content = d.view.content(fi.path)
        if content is None:
            continue
        for pattern in env_patterns:
            for m in re.finditer(pattern, content, re.IGNORECASE):
                url = m.group(1)
                if not url or url.startswith("$"):
                    continue
                line = content.count("\n", 0, m.start()) + 1
                for api in api_servers:
                    matched = bool(api.port and f":{api.port}" in url)
                    if api.name.lower().replace(" ", "-") in url.lower():
                        matched = True
                    if matched:
                        add(source_comp.id, api.id, "http",
                            _evidence(fi.path, line, url), "inferred", "config",
                            protocol="HTTP", label="env config", bidirectional=True)

    # -- websocket / grpc / database / queue via driver signals ------------
    _driver_edges(d, add, content_ids)

    # -- enrich http edges with auth / format / style / middleware ---------
    _enrich(d, relationships, content_ids)

    d.relationships = relationships
    d._rel_evidence = evidence_by_key
    d._rel_confidence = confidence_by_key
    d._rel_origin = origin_by_key


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _url_signals(d: Deriver, path: str) -> list[tuple[str, Optional[int]]]:
    out = []
    for s in d.view.signals(path):
        if s["kind"] == "url_reference":
            v = s["value"] or {}
            if v.get("url"):
                out.append((v["url"], s["line"]))
    return out


def _declares_endpoint(comp) -> bool:
    """True when ``comp`` genuinely exposes a network endpoint (D2 gate).

    Either it binds a port (a declared listen address) or it is a server-type
    component. A plain library/module named like a URL path segment declares no
    endpoint and never becomes an http target from a name match.
    """
    return comp.port is not None or comp.type in SERVER_TYPES


def _url_host(ref: str) -> Optional[str]:
    """The host authority of a URL/service reference, lowercased (D2).

    Full URLs are parsed for their netloc; a bare ``host:port`` (no scheme) and a
    plain service token (from a service signal) resolve to the host itself. Any
    path, query, userinfo, and port are stripped, so only the authority that a
    server actually answers on is returned. Returns None when the reference is
    not host-shaped. The resolution is exact by design: a component name found
    anywhere else in a URL (a path segment, a longer public domain) is not a host
    match and yields no edge.
    """
    r = ref.strip()
    if "://" in r:
        netloc = urlsplit(r).netloc
    elif "/" in r or "?" in r:
        return None
    elif ":" in r:
        netloc = r  # host:port with no scheme, e.g. api:8000
    elif "." not in r:
        netloc = r  # a bare service token, e.g. api
    else:
        return None
    netloc = netloc.rsplit("@", 1)[-1]
    host = netloc.rsplit(":", 1)[0] if ":" in netloc else netloc
    return host.lower() or None


def _locate(d: Deriver, path: str, needle: str) -> Optional[int]:
    content = d.view.content(path)
    if not content or not needle:
        return None
    idx = content.find(needle)
    return content.count("\n", 0, idx) + 1 if idx >= 0 else None


def _resolve_import_to_component(d: Deriver, import_name: str, source_file: str):
    if import_name.startswith("."):
        source_dir = os.path.dirname(source_file)
        current = source_dir
        for part in import_name.split("/"):
            if part == ".":
                continue
            elif part == "..":
                current = os.path.dirname(current)
            else:
                current = os.path.join(current, part)
        return d._find_component_for_file(current)
    import_lower = import_name.lower()
    for path, comp in d._component_map.items():
        comp_name = comp.name.lower().replace("-", "").replace("_", "")
        if import_lower.replace("-", "").replace("_", "") == comp_name:
            return comp
        if path and os.path.basename(path).lower() == import_lower:
            return comp
    return None


def _components_with_signal(d: Deriver, kind: str, content_ids: set):
    """Return {comp_id: (comp, file, line)} for the first file emitting ``kind``."""
    out: dict = {}
    for fi in d._all_files:
        comp = d._find_component_for_file(fi.path)
        if not comp or comp.id in content_ids or comp.type == "infrastructure":
            continue
        if comp.id in out:
            continue
        sigs = d.view.signals(fi.path)
        if any(s["kind"] == kind for s in sigs):
            out[comp.id] = (comp, fi.path, _sig_line(sigs, kind))
    return out


def _driver_edges(d: Deriver, add, content_ids: set) -> None:
    # websocket
    ws = _components_with_signal(d, "websocket_driver", content_ids)
    server_ids = {cid for cid, (c, _f, _l) in ws.items()
                  if c.type in ("api-server", "service", "infrastructure")}
    for cid, (comp, f, ln) in ws.items():
        if cid in server_ids:
            continue
        for sid in server_ids:
            add(comp.id, ws[sid][0].id, "websocket", _evidence(f, ln, "websocket"),
                "inferred", "static", protocol="WebSocket", label="WebSocket",
                bidirectional=True, data_format="json")
    # grpc
    grpc = _components_with_signal(d, "grpc_driver", content_ids)
    server_ids = {cid for cid, (c, _f, _l) in grpc.items()
                  if c.type in ("api-server", "service")}
    for cid, (comp, f, ln) in grpc.items():
        if cid in server_ids:
            continue
        for sid in server_ids:
            add(comp.id, grpc[sid][0].id, "grpc", _evidence(f, ln, "grpc"),
                "inferred", "static", protocol="gRPC", label="gRPC",
                bidirectional=True, data_format="protobuf", transport="http/2")
    # database / cache
    infra_services: dict = {}
    for comp in d._component_map.values():
        if comp.type == "infrastructure":
            name = comp.name.lower()
            for image_key, (rel_type, engine, port) in DOCKER_SERVICE_TYPES.items():
                if image_key in name:
                    infra_services[engine] = (comp, rel_type, port)
                    break
    for fi in d._all_files:
        comp = d._find_component_for_file(fi.path)
        if not comp or comp.id in content_ids or comp.type == "infrastructure":
            continue
        for s in d.view.signals(fi.path):
            if s["kind"] != "db_driver":
                continue
            engine = (s["value"] or {}).get("engine")
            lib = (s["value"] or {}).get("library")
            if engine in infra_services:
                target, rel_type, port = infra_services[engine]
                add(comp.id, target.id, rel_type, _evidence(fi.path, s["line"], lib or engine),
                    "inferred", "static", protocol=engine, label=lib, port=port,
                    connection_pattern=lib)
    # message queue
    queue_users: dict = {}
    for fi in d._all_files:
        comp = d._find_component_for_file(fi.path)
        if not comp or comp.id in content_ids or comp.type == "infrastructure":
            continue
        for s in d.view.signals(fi.path):
            if s["kind"] == "queue_driver":
                system = (s["value"] or {}).get("system")
                queue_users.setdefault(system, []).append((comp, fi.path, s["line"]))
                break
    infra_queues: dict = {}
    for comp in d._component_map.values():
        if comp.type == "infrastructure":
            name = comp.name.lower()
            for image_key, (rel_type, engine, port) in DOCKER_SERVICE_TYPES.items():
                if image_key in name and rel_type == "message_queue":
                    infra_queues[engine] = (comp, port)
                    break
    for system, users in queue_users.items():
        target_info = infra_queues.get(system)
        if target_info:
            target, port = target_info
            for comp, f, ln in users:
                add(comp.id, target.id, "message_queue", _evidence(f, ln, system),
                    "inferred", "static", protocol=system, label=system, port=port)
        elif len(users) >= 2:
            for i, (a, fa, la) in enumerate(users):
                for b, _fb, _lb in users[i + 1:]:
                    add(a.id, b.id, "message_queue", _evidence(fa, la, system),
                        "inferred", "static", protocol=system, label=system,
                        bidirectional=True)


def _external_services(d: Deriver, content_ids: set) -> None:
    by_comp: dict = {}
    for fi in d._all_files:
        comp = d._find_component_for_file(fi.path)
        if not comp or comp.id in content_ids:
            continue
        for url, _ln in _url_signals(d, fi.path):
            for domain, (service_name, category) in EXTERNAL_CLOUD_APIS.items():
                if domain in url:
                    by_comp.setdefault(comp.id, set()).add((service_name, category))
    for comp in d._component_map.values():
        if comp.id in by_comp:
            comp.external_services = [
                {"name": n, "category": c} for n, c in sorted(by_comp[comp.id])
            ]


def _combined_code(d: Deriver, comp_id: str, content_ids: set) -> str:
    from ..constants import CODE_LANGUAGES
    comp = next((c for c in d._component_map.values() if c.id == comp_id), None)
    if not comp or comp.id in content_ids:
        return ""
    parts = []
    for fpath in comp.files:
        fi = next((f for f in d._all_files if f.path == fpath), None)
        if not fi or fi.language not in CODE_LANGUAGES:
            continue
        c = d.view.content(fpath)
        if c:
            parts.append(c)
    return "\n".join(parts)


def _enrich(d: Deriver, relationships, content_ids: set) -> None:
    for rel in relationships:
        if rel.type != "http":
            continue
        source_content = _combined_code(d, rel.source, content_ids)
        if not source_content:
            continue
        if not rel.authentication:
            rel.authentication = _detect_auth(source_content)
        if not rel.data_format:
            rel.data_format = _detect_data_format(source_content)
        if not rel.api_style:
            rel.api_style = _detect_api_style(source_content, GRPC_PATTERNS)
        if not rel.middleware:
            target_content = _combined_code(d, rel.target, content_ids)
            if target_content:
                rel.middleware = _detect_middleware(target_content)


def _detect_auth(content: str) -> Optional[str]:
    for auth_type, patterns in AUTH_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, content):
                return auth_type
    return None


def _detect_data_format(content: str) -> Optional[str]:
    for fmt in ("protobuf", "graphql", "msgpack", "xml", "json"):
        for pattern in DATA_FORMAT_PATTERNS.get(fmt, []):
            if re.search(pattern, content):
                return fmt
    return None


def _detect_api_style(content: str, grpc_patterns) -> str:
    for pattern in DATA_FORMAT_PATTERNS.get("graphql", []):
        if re.search(pattern, content):
            return "graphql"
    for lang_patterns in grpc_patterns.values():
        for pattern in lang_patterns:
            if re.search(pattern, content):
                return "grpc"
    for lang_patterns in WEBSOCKET_PATTERNS.values():
        for pattern in lang_patterns:
            if re.search(pattern, content):
                return "websocket"
    return "rest"


def _detect_middleware(content: str) -> list[str]:
    found = []
    for mw_type, patterns in MIDDLEWARE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, content):
                found.append(mw_type)
                break
    return found
