"""The nine MCP tools over the fact store (TARGET-ARCHITECTURE section 8,
extended by LENS-DESIGN section 6).

Each tool is a pure function ``(StoreContext, args) -> ToolResult`` reading only
the store (invariant I9, no LLM calls). Every response cites evidence file:line,
marks confidence, and marks AI staleness inline where applicable (invariants I3,
I5). The default rendering is compact structured text (the token-efficiency
thesis); passing ``json: true`` returns the same structured payload as JSON so a
machine consumer gets a stable shape.

The tools are transport-agnostic: server.py speaks JSON-RPC over stdio and calls
these; swapping to the official `mcp` SDK is a transport change only, this
registry is handed over unchanged (the recorded upgrade path).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from .context import StoreContext

# Response bounds (invariant: no silent truncation, always an "N more" notice).
DEFAULT_SEARCH_LIMIT = 30
DEFAULT_LIST_LIMIT = 50
DEFAULT_IMPACT_LIMIT = 50
MAX_LIMIT = 500
PREVIEW_LINES = 12


class ToolError(Exception):
    """A malformed-arguments error; the server maps it to a JSON-RPC error."""


@dataclass
class ToolResult:
    text: str
    data: dict


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[StoreContext, dict], ToolResult]


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _short_sha(sha: Optional[str]) -> str:
    return sha[:7] if sha else "?"


def _conf_tag(confidence: Optional[str], origin: Optional[str] = None) -> str:
    parts = [p for p in (confidence, origin) if p]
    return f"[{'/'.join(parts)}]" if parts else "[unknown]"


def _fmt_evidence(evidence: Any, limit: int = 2) -> str:
    """Render an evidence list as `path:line "snippet"` items, bounded."""
    if not isinstance(evidence, list) or not evidence:
        return "no evidence"
    out = []
    for ev in evidence[:limit]:
        if not isinstance(ev, dict):
            out.append(str(ev))
            continue
        loc = ev.get("file") or ev.get("path") or "?"
        line = ev.get("line")
        loc = f"{loc}:{line}" if line is not None else loc
        snippet = ev.get("snippet")
        out.append(f'{loc} "{snippet}"' if snippet else loc)
    if len(evidence) > limit:
        out.append(f"(+{len(evidence) - limit} more)")
    return "; ".join(out)


def _stale_suffix(ctx: StoreContext, row: Optional[dict]) -> str:
    """Inline staleness marker for an enrichment row (I5)."""
    stale = ctx.staleness_of_row(row)
    if stale is True:
        return f"  STALE (AI derived at {_short_sha(row.get('commit_sha'))}, code changed since)"
    return ""


def _stale_flag(ctx: StoreContext, row: Optional[dict]) -> Optional[bool]:
    return ctx.staleness_of_row(row)


def _limit_arg(args: dict, default: int) -> int:
    raw = args.get("limit", default)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise ToolError(f"'limit' must be an integer, got {raw!r}") from None
    if n <= 0:
        raise ToolError("'limit' must be positive")
    return min(n, MAX_LIMIT)


def _require_id(args: dict) -> str:
    val = args.get("id")
    if not isinstance(val, str) or not val:
        raise ToolError("missing required argument 'id'")
    return val


def _truncation_note(total: int, shown: int, what: str) -> Optional[str]:
    if total > shown:
        return f"... {total - shown} more {what} (raise 'limit' or add a filter)"
    return None


def _preview(text: Optional[str], lines: int = PREVIEW_LINES) -> str:
    if not text:
        return ""
    rows = text.splitlines()
    if len(rows) <= lines:
        return text.rstrip()
    return "\n".join(rows[:lines]) + f"\n... (+{len(rows) - lines} preview lines)"


# ---------------------------------------------------------------------------
# se_overview
# ---------------------------------------------------------------------------


def _tool_overview(ctx: StoreContext, args: dict) -> ToolResult:
    comps = ctx.components
    roles: dict[str, int] = {}
    for c in comps:
        roles[c.get("role") or "?"] = roles.get(c.get("role") or "?", 0) + 1

    cap_kinds: dict[str, int] = {}
    for cap in ctx.capabilities:
        cap_kinds[cap.get("kind") or "?"] = cap_kinds.get(cap.get("kind") or "?", 0) + 1

    findings = ctx.findings
    unverified = sum(1 for f in findings if f.get("verification_status") != "verified")

    cov = ctx.store.coverage_summary()
    cov_total = sum(cov.values())
    parsed = cov.get("parsed", 0)

    fresh = stale = unknown = 0
    for row in ctx.enrichment_rows:
        s = ctx.staleness_of_row(row)
        if s is True:
            stale += 1
        elif s is False:
            fresh += 1
        else:
            unknown += 1

    arch_row = ctx.enrichment_for("architecture", "@architecture")
    narrative = None
    if arch_row:
        payload = arch_row.get("payload") or {}
        narrative = (
            payload.get("description")
            or payload.get("summary")
            or payload.get("help_text")
        )

    data = {
        "components": {"total": len(comps), "by_role": roles},
        "capabilities": {"total": len(ctx.capabilities), "by_kind": cap_kinds},
        "data_entities": len(ctx.data_entities),
        "rules": len(ctx.rules),
        "concerns": len(ctx.concerns),
        "findings": {"total": len(findings), "unverified": unverified},
        "coverage": {"total": cov_total, "parsed": parsed, "by_disposition": cov},
        "enrichment": {"fresh": fresh, "stale": stale, "unknown": unknown},
        "architecture_narrative": narrative,
        "architecture_narrative_stale": _stale_flag(ctx, arch_row),
    }

    lines = ["ARCHITECTURE OVERVIEW"]
    role_str = ", ".join(f"{k}={v}" for k, v in sorted(roles.items()))
    lines.append(f"components: {len(comps)}  ({role_str})")
    if cap_kinds:
        cap_str = ", ".join(f"{k}={v}" for k, v in sorted(cap_kinds.items()))
        lines.append(f"capabilities: {len(ctx.capabilities)}  ({cap_str})")
    else:
        lines.append("capabilities: 0")
    lines.append(f"data entities: {len(ctx.data_entities)}")
    lines.append(f"rules: {len(ctx.rules)}")
    lines.append(f"concerns: {len(ctx.concerns)}")
    lines.append(f"findings: {len(findings)}  ({unverified} unverified)")
    cov_str = ", ".join(f"{k}={v}" for k, v in sorted(cov.items()))
    lines.append(f"coverage: {parsed}/{cov_total} parsed  ({cov_str})")
    lines.append(
        f"enrichment: {fresh} fresh, {stale} stale, {unknown} unknown provenance"
    )
    if narrative:
        suffix = _stale_suffix(ctx, arch_row)
        lines.append("")
        lines.append(f"AI architecture narrative:{suffix}")
        lines.append(f"  {narrative}")
    return ToolResult("\n".join(lines), data)


# ---------------------------------------------------------------------------
# se_search
# ---------------------------------------------------------------------------


def _tool_search(ctx: StoreContext, args: dict) -> ToolResult:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ToolError("missing required argument 'query'")
    kind = args.get("kind")
    limit = _limit_arg(args, DEFAULT_SEARCH_LIMIT)

    if not ctx.store.with_fts:
        raise ToolError("this SQLite build lacks FTS5; se_search is unavailable")

    # Fetch one extra to detect "more".
    try:
        hits = ctx.store.search(query, ref_kind=kind, limit=limit + 1)
    except RuntimeError as exc:
        raise ToolError(str(exc)) from exc

    more = len(hits) > limit
    hits = hits[:limit]

    results = []
    for h in hits:
        ref_kind = h["ref_kind"]
        ref_id = h["ref_id"]
        context = h.get("name") or h.get("path") or ""
        if not context and ref_kind == "enrichment":
            context = "(AI help text match)"
        results.append({"kind": ref_kind, "id": ref_id, "context": context})

    note = (
        f"... more hits exist beyond {limit} (raise 'limit')" if more else None
    )
    data = {
        "query": query,
        "count": len(results),
        "results": results,
        "truncated": more,
        "truncation_note": note,
    }

    lines = [f"SEARCH '{query}'  ({len(results)} hits)"]
    for r in results:
        ctx_str = f"  {r['context']}" if r["context"] else ""
        lines.append(f"  [{r['kind']}] {r['id']}{ctx_str}")
    if note:
        lines.append(note)
    return ToolResult("\n".join(lines), data)


# ---------------------------------------------------------------------------
# se_component
# ---------------------------------------------------------------------------


def _accessor_component(ctx: StoreContext, accessor_id: str) -> Optional[str]:
    """Resolve an entity-access accessor (component or symbol id) to a component."""
    if accessor_id in ctx.component_by_id:
        return accessor_id
    sym = ctx.symbol_by_id.get(accessor_id)
    if sym is not None:
        path = ctx.file_path_by_id.get(sym["file_id"])
        if path:
            return ctx.component_for_file(path)
    return None


def _component_activity(ctx: StoreContext, files: list[str]) -> Optional[dict]:
    commits = added = removed = 0
    last = None
    authors: set[str] = set()
    seen = False
    for path in files:
        row = ctx.activity_by_path.get(path)
        if row is None:
            continue
        seen = True
        commits += row.get("commit_count") or 0
        added += row.get("lines_added") or 0
        removed += row.get("lines_removed") or 0
        lm = row.get("last_modified")
        if lm and (last is None or lm > last):
            last = lm
        for a in ctx.authors_by_path.get(path, []):
            authors.add(a["author_key"])
    if not seen:
        return None
    return {
        "commit_count": commits,
        "lines_added": added,
        "lines_removed": removed,
        "last_modified": last,
        "authors": len(authors),
    }


def _tool_component(ctx: StoreContext, args: dict) -> ToolResult:
    cid = _require_id(args)
    comp = ctx.component_by_id.get(cid)
    if comp is None:
        raise ToolError(f"no component with id {cid!r}")

    files = ctx.files_of_component.get(cid, [])
    caps = ctx.capabilities_of.get(cid, [])
    rules = ctx.rules_of.get(cid, [])
    enr_row = ctx.enrichment_for("component", cid)

    entities = []
    for a in ctx.entity_access_rows:
        if _accessor_component(ctx, a["accessor_id"]) == cid:
            ent = ctx.entity_by_id.get(a["entity_id"])
            entities.append(
                {
                    "entity_id": a["entity_id"],
                    "name": ent.get("name") if ent else None,
                    "mode": a.get("mode"),
                    "confidence": a.get("confidence"),
                    "evidence": a.get("evidence"),
                }
            )

    def edge_view(e: dict, other_key: str) -> dict:
        verdict_row = ctx.edge_verdict_for(e["source_id"], e["target_id"], e["type"])
        verdict = None
        if verdict_row:
            payload = verdict_row.get("payload") or {}
            verdict = {
                "status": payload.get("status"),
                "reason": payload.get("reason"),
                "stale": _stale_flag(ctx, verdict_row),
            }
        return {
            "source": e["source_id"],
            "target": e["target_id"],
            "type": e["type"],
            "confidence": e.get("confidence"),
            "origin": e.get("origin"),
            "evidence": e.get("evidence"),
            "verdict": verdict,
        }

    edges_in = [edge_view(e, "source_id") for e in ctx.edges_in.get(cid, [])]
    edges_out = [edge_view(e, "target_id") for e in ctx.edges_out.get(cid, [])]
    activity = _component_activity(ctx, files)

    enrichment = None
    if enr_row:
        enrichment = {
            "payload": enr_row.get("payload"),
            "stale": _stale_flag(ctx, enr_row),
            "derived_from_commit": enr_row.get("commit_sha"),
        }

    data = {
        "id": cid,
        "name": comp.get("name"),
        "type": comp.get("type"),
        "role": comp.get("role"),
        "files": files,
        "capabilities": [
            {
                "id": c["id"],
                "kind": c.get("kind"),
                "name": c.get("name"),
                "confidence": c.get("confidence"),
                "evidence": c.get("evidence"),
            }
            for c in caps
        ],
        "rules": [
            {"id": r["id"], "kind": r.get("kind"), "summary": r.get("summary"),
             "confidence": r.get("confidence")}
            for r in rules
        ],
        "entities_touched": entities,
        "edges_in": edges_in,
        "edges_out": edges_out,
        "enrichment": enrichment,
        "activity": activity,
    }

    lines = [f"COMPONENT {cid}"]
    lines.append(f"name: {comp.get('name')}   type: {comp.get('type')}   role: {comp.get('role')}")
    if enrichment:
        p = enrichment["payload"] or {}
        desc = p.get("description") or p.get("help_text")
        if desc:
            lines.append(f"AI: {desc}{_stale_suffix(ctx, enr_row)}")
    lines.append(f"files ({len(files)}): " + (", ".join(files) if files else "none"))
    lines.append(f"capabilities ({len(caps)}):")
    for c in caps:
        lines.append(
            f"  - {c.get('kind')} {c.get('name')}  {_conf_tag(c.get('confidence'))}"
            f"  {_fmt_evidence(c.get('evidence'))}  ({c['id']})"
        )
    lines.append(f"rules ({len(rules)}):")
    for r in rules:
        lines.append(f"  - {r.get('kind')}: {r.get('summary')}  {_conf_tag(r.get('confidence'))}")
    lines.append(f"entities touched ({len(entities)}):")
    for e in entities:
        lines.append(
            f"  - {e['mode']} {e['name'] or e['entity_id']}  {_conf_tag(e['confidence'])}"
            f"  {_fmt_evidence(e['evidence'])}"
        )
    lines.append(f"edges in / who depends on this ({len(edges_in)}):")
    for e in edges_in:
        lines.append(_render_edge(ctx, e, cid, inbound=True))
    lines.append(f"edges out / what this depends on ({len(edges_out)}):")
    for e in edges_out:
        lines.append(_render_edge(ctx, e, cid, inbound=False))
    if activity:
        lines.append(
            f"activity: {activity['commit_count']} commits, "
            f"{activity['authors']} authors, last {activity['last_modified']}"
        )
    return ToolResult("\n".join(lines), data)


def _render_edge(ctx: StoreContext, e: dict, this_id: str, inbound: bool) -> str:
    other = e["source"] if inbound else e["target"]
    arrow = f"{other} --{e['type']}--> this" if inbound else f"this --{e['type']}--> {other}"
    verdict = ""
    if e.get("verdict") and e["verdict"].get("status"):
        v = e["verdict"]
        verdict = f"  verdict={v['status']}"
        if v.get("stale") is True:
            verdict += " (STALE)"
    return (
        f"  - {arrow}  {_conf_tag(e.get('confidence'), e.get('origin'))}"
        f"  {_fmt_evidence(e.get('evidence'))}{verdict}"
    )


# ---------------------------------------------------------------------------
# se_symbol
# ---------------------------------------------------------------------------


def _tool_symbol(ctx: StoreContext, args: dict) -> ToolResult:
    sid = _require_id(args)
    sym = ctx.symbol_by_id.get(sid)
    if sym is None:
        raise ToolError(f"no symbol with id {sid!r}")

    path = ctx.file_path_by_id.get(sym["file_id"])
    component = ctx.component_for_file(path) if path else None

    # Parent chain (nearest parent first).
    chain: list[str] = []
    pid = sym.get("parent_id")
    guard = 0
    while pid and guard < 100:
        parent = ctx.symbol_by_id.get(pid)
        if parent is None:
            break
        chain.append(pid)
        pid = parent.get("parent_id")
        guard += 1

    preview = sym.get("code_preview") or ""
    signature = ""
    for line in preview.splitlines():
        if line.strip():
            signature = line.strip()
            break
    if not signature:
        signature = f"{sym.get('kind') or 'symbol'} {sym.get('name')}"

    enr_row = ctx.enrichment_for("symbol", sid)
    enrichment = None
    if enr_row:
        enrichment = {
            "payload": enr_row.get("payload"),
            "stale": _stale_flag(ctx, enr_row),
            "derived_from_commit": enr_row.get("commit_sha"),
        }

    data = {
        "id": sid,
        "name": sym.get("name"),
        "kind": sym.get("kind"),
        "visibility": sym.get("visibility"),
        "signature": signature,
        "docstring": sym.get("docstring"),
        "file": path,
        "line": sym.get("line"),
        "end_line": sym.get("end_line"),
        "component": component,
        "parent_chain": chain,
        "code_preview": preview,
        "enrichment": enrichment,
    }

    lines = [f"SYMBOL {sid}"]
    loc = f"{path}:{sym.get('line')}" if path else "?"
    lines.append(f"{sym.get('kind')} {sym.get('name')}  [{sym.get('visibility')}]  {loc}")
    lines.append(f"signature: {signature}")
    if component:
        lines.append(f"component: {component}")
    if chain:
        lines.append("parent chain: " + " <- ".join(chain))
    if sym.get("docstring"):
        lines.append(f"doc: {sym['docstring']}")
    if enrichment and enrichment["payload"]:
        p = enrichment["payload"]
        desc = p.get("description") or p.get("help_text")
        if desc:
            lines.append(f"AI: {desc}{_stale_suffix(ctx, enr_row)}")
    if preview:
        lines.append("preview:")
        lines.append(_preview(preview))
    return ToolResult("\n".join(lines), data)


# ---------------------------------------------------------------------------
# se_refs
# ---------------------------------------------------------------------------


def _tool_refs(ctx: StoreContext, args: dict) -> ToolResult:
    rid = _require_id(args)
    direction = args.get("direction", "both")
    if direction not in ("in", "out", "both"):
        raise ToolError("'direction' must be 'in', 'out', or 'both'")

    # Scope note (TARGET-ARCHITECTURE section 10): references are resolved at
    # component granularity from import/dependency edges, not a compiler-grade
    # symbol call graph. A symbol id resolves to its containing component.
    resolved = rid
    scope = "component"
    if rid not in ctx.component_by_id:
        sym = ctx.symbol_by_id.get(rid)
        if sym is not None:
            path = ctx.file_path_by_id.get(sym["file_id"])
            resolved = ctx.component_for_file(path) if path else None
            scope = "symbol->component"
            if resolved is None:
                raise ToolError(f"symbol {rid!r} has no resolvable component")
        else:
            raise ToolError(f"no component or symbol with id {rid!r}")

    def view(e: dict, other: str) -> dict:
        return {
            "id": other,
            "type": e["type"],
            "confidence": e.get("confidence"),
            "origin": e.get("origin"),
            "evidence": e.get("evidence"),
        }

    importers = [view(e, e["source_id"]) for e in ctx.edges_in.get(resolved, [])]
    importees = [view(e, e["target_id"]) for e in ctx.edges_out.get(resolved, [])]

    data = {
        "id": rid,
        "resolved_component": resolved,
        "scope": scope,
        "reference_resolution": "import/dependency edges at component granularity "
        "(not a compiler-grade symbol call graph)",
    }
    if direction in ("in", "both"):
        data["importers"] = importers
    if direction in ("out", "both"):
        data["importees"] = importees

    lines = [f"REFS {rid}"]
    if scope != "component":
        lines.append(f"resolved to component: {resolved}")
    lines.append("scope: import/dependency edges at component granularity (see TARGET-ARCHITECTURE 10)")
    if direction in ("in", "both"):
        lines.append(f"importers / callers ({len(importers)}):")
        for r in importers:
            lines.append(
                f"  - {r['id']} --{r['type']}-->  {_conf_tag(r['confidence'], r['origin'])}"
                f"  {_fmt_evidence(r['evidence'])}"
            )
    if direction in ("out", "both"):
        lines.append(f"importees / callees ({len(importees)}):")
        for r in importees:
            lines.append(
                f"  - --{r['type']}--> {r['id']}  {_conf_tag(r['confidence'], r['origin'])}"
                f"  {_fmt_evidence(r['evidence'])}"
            )
    return ToolResult("\n".join(lines), data)


# ---------------------------------------------------------------------------
# se_impact
# ---------------------------------------------------------------------------


def _tool_impact(ctx: StoreContext, args: dict) -> ToolResult:
    sid = _require_id(args)
    if sid not in ctx.component_by_id:
        # Allow a symbol id, resolving to its component (blast radius is graph).
        sym = ctx.symbol_by_id.get(sid)
        if sym is not None:
            path = ctx.file_path_by_id.get(sym["file_id"])
            resolved = ctx.component_for_file(path) if path else None
            if resolved is None:
                raise ToolError(f"symbol {sid!r} has no resolvable component")
            sid = resolved
        else:
            raise ToolError(f"no component or symbol with id {sid!r}")

    depth = args.get("depth", 3)
    try:
        depth = int(depth)
    except (TypeError, ValueError):
        raise ToolError(f"'depth' must be an integer, got {depth!r}") from None
    if depth < 1:
        raise ToolError("'depth' must be >= 1")
    limit = _limit_arg(args, DEFAULT_IMPACT_LIMIT)

    # "What breaks if this changes" is the inbound blast radius: everything that
    # depends on this node (edges pointing at it), transitively. BFS over the
    # in-memory adjacency (store.edges loaded once) so each reached node carries
    # the edge that connected it (the per-hop evidence chain). The CTE
    # store.traverse gives the same set; BFS is used here for the evidence.
    adj = ctx.edges_in
    visited = {sid: 0}
    parent_edge: dict[str, dict] = {}
    frontier = [sid]
    d = 0
    while frontier and d < depth:
        d += 1
        nxt: list[str] = []
        for node in frontier:
            for e in sorted(adj.get(node, []), key=lambda x: (x["source_id"], x["type"])):
                nb = e["source_id"]
                if nb not in visited:
                    visited[nb] = d
                    parent_edge[nb] = e
                    nxt.append(nb)
        frontier = nxt

    reached = sorted(
        (n for n in visited if n != sid), key=lambda n: (visited[n], n)
    )
    total = len(reached)
    shown = reached[:limit]

    items = []
    for n in shown:
        e = parent_edge.get(n, {})
        comp = ctx.component_by_id.get(n)
        items.append(
            {
                "id": n,
                "depth": visited[n],
                "name": comp.get("name") if comp else None,
                "via": {
                    "from": e.get("source_id"),
                    "to": e.get("target_id"),
                    "type": e.get("type"),
                    "confidence": e.get("confidence"),
                    "evidence": e.get("evidence"),
                },
            }
        )

    note = _truncation_note(total, len(shown), "affected nodes")
    data = {
        "id": sid,
        "depth": depth,
        "affected_count": total,
        "affected": items,
        "truncation_note": note,
    }

    lines = [f"IMPACT of changing {sid}  (depth {depth}, {total} affected)"]
    lines.append("blast radius, ranked nearest-first (what breaks if this changes):")
    for it in items:
        via = it["via"]
        chain = (
            f"{via['from']} --{via['type']}--> {via['to']}"
            if via.get("from")
            else "?"
        )
        lines.append(
            f"  [{it['depth']}] {it['id']}  via {chain}  "
            f"{_conf_tag(via.get('confidence'))}  {_fmt_evidence(via.get('evidence'))}"
        )
    if note:
        lines.append(note)
    if not items:
        lines.append("  (nothing depends on this node)")
    return ToolResult("\n".join(lines), data)


# ---------------------------------------------------------------------------
# se_coverage
# ---------------------------------------------------------------------------


def _tool_coverage(ctx: StoreContext, args: dict) -> ToolResult:
    disposition = args.get("disposition")
    summary = ctx.store.coverage_summary()
    total = sum(summary.values())

    if disposition:
        limit = _limit_arg(args, DEFAULT_LIST_LIMIT)
        rows = ctx.store.coverage(disposition)
        shown = rows[:limit]
        note = _truncation_note(len(rows), len(shown), f"'{disposition}' rows")
        data = {
            "disposition": disposition,
            "count": len(rows),
            "rows": [
                {"path": r["path"], "reason": r.get("reason")} for r in shown
            ],
            "truncation_note": note,
        }
        lines = [f"COVERAGE disposition='{disposition}'  ({len(rows)} rows)"]
        for r in shown:
            reason = f"  ({r['reason']})" if r.get("reason") else ""
            lines.append(f"  {r['path']}{reason}")
        if note:
            lines.append(note)
        return ToolResult("\n".join(lines), data)

    data = {"total": total, "by_disposition": summary}
    lines = [f"COVERAGE LEDGER  ({total} files)"]
    parsed = summary.get("parsed", 0)
    lines.append(f"parsed: {parsed}/{total}")
    for k, v in sorted(summary.items()):
        if k == "parsed":
            continue
        lines.append(f"  {k}: {v}")
    lines.append("(pass disposition=<name> for the file list)")
    return ToolResult("\n".join(lines), data)


# ---------------------------------------------------------------------------
# se_rules
# ---------------------------------------------------------------------------


def _tool_rules(ctx: StoreContext, args: dict) -> ToolResult:
    component = args.get("component")
    entity = args.get("entity")
    kind = args.get("kind")
    query = args.get("query")
    limit = _limit_arg(args, DEFAULT_LIST_LIMIT)

    rows = list(ctx.rules)
    if component:
        rows = [r for r in rows if r.get("component_id") == component]
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    if entity:
        rows = [
            r for r in rows
            if _detail_mentions_entity(r.get("detail"), entity)
        ]
    if query:
        q = query.lower()
        rows = [
            r for r in rows
            if q in (r.get("summary") or "").lower()
            or q in (r.get("kind") or "").lower()
        ]

    total = len(rows)
    shown = rows[:limit]
    note = _truncation_note(total, len(shown), "rules")

    out = []
    for r in shown:
        enr_row = ctx.enrichment_for("rule", r["id"])
        name = None
        if enr_row:
            payload = enr_row.get("payload") or {}
            name = payload.get("name") or payload.get("statement")
        out.append(
            {
                "id": r["id"],
                "kind": r.get("kind"),
                "component": r.get("component_id"),
                "summary": r.get("summary"),
                "plain_language": name,
                "plain_language_stale": _stale_flag(ctx, enr_row),
                "confidence": r.get("confidence"),
                "evidence": r.get("evidence"),
            }
        )

    data = {"count": total, "rules": out, "truncation_note": note}
    lines = [f"RULES  ({total} match)"]
    for r in out:
        statement = f"  \"{r['plain_language']}\"" if r["plain_language"] else ""
        stale = "  STALE" if r["plain_language_stale"] is True else ""
        lines.append(
            f"  - [{r['kind']}] {r['summary']}{statement}{stale}  "
            f"{_conf_tag(r['confidence'])}  {_fmt_evidence(r['evidence'])}  ({r['id']})"
        )
    if note:
        lines.append(note)
    if not out:
        lines.append("  (no rules match; the Rules lens extraction may not have run)")
    return ToolResult("\n".join(lines), data)


def _detail_mentions_entity(detail: Any, entity: str) -> bool:
    if not isinstance(detail, dict):
        return False
    for key in ("entity", "entities", "constrained_entity"):
        val = detail.get(key)
        if val == entity or (isinstance(val, list) and entity in val):
            return True
    return False


# ---------------------------------------------------------------------------
# se_findings
# ---------------------------------------------------------------------------


def _tool_findings(ctx: StoreContext, args: dict) -> ToolResult:
    kind = args.get("kind")
    status = args.get("status")
    component = args.get("component")
    limit = _limit_arg(args, DEFAULT_LIST_LIMIT)

    rows = list(ctx.findings)  # already ranked (rank_score desc, id)
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    if status:
        rows = [r for r in rows if (r.get("verification_status") or "unverified") == status]
    if component:
        rows = [r for r in rows if _finding_touches(r, component)]

    total = len(rows)
    shown = rows[:limit]
    note = _truncation_note(total, len(shown), "findings")

    out = []
    for r in shown:
        vstatus = r.get("verification_status") or "unverified"
        # An AI verdict overlay may refine the stored status (P7-4).
        verdict_row = ctx.enrichment_for("finding-verdict", r["id"])
        if verdict_row:
            payload = verdict_row.get("payload") or {}
            vstatus = payload.get("verification_status") or vstatus
        out.append(
            {
                "id": r["id"],
                "kind": r.get("kind"),
                "summary": r.get("summary"),
                "verification_status": vstatus,
                "unverified": vstatus != "verified",
                "confidence": r.get("confidence"),
                "rank_score": r.get("rank_score"),
                "members": r.get("members"),
                "evidence": r.get("evidence"),
            }
        )

    # Concern membership for a component filter.
    concern_memberships = []
    if component:
        for c in ctx.concerns:
            if _concern_has_component(c, component):
                concern_memberships.append(
                    {"id": c["id"], "kind": c.get("kind"),
                     "title": c.get("title")}
                )

    data = {
        "count": total,
        "findings": out,
        "concern_memberships": concern_memberships,
        "truncation_note": note,
    }

    lines = [f"FINDINGS  ({total} match, ranked)"]
    for r in out:
        mark = "" if r["verification_status"] == "verified" else "  [UNVERIFIED]"
        members = r.get("members") or []
        mcount = len(members) if isinstance(members, list) else 0
        lines.append(
            f"  - [{r['kind']}] {r['summary']}  status={r['verification_status']}{mark}"
            f"  {mcount} members  {_conf_tag(r['confidence'])}  ({r['id']})"
        )
    if note:
        lines.append(note)
    if concern_memberships:
        lines.append(f"concern memberships of {component} ({len(concern_memberships)}):")
        for c in concern_memberships:
            lines.append(f"  - [{c['kind']}] {c['title'] or c['id']}  ({c['id']})")
    if not out and not concern_memberships:
        lines.append("  (no findings match)")
    return ToolResult("\n".join(lines), data)


def _finding_touches(finding: dict, component: str) -> bool:
    for m in finding.get("members") or []:
        if isinstance(m, dict) and (
            m.get("component_id") == component or m.get("id") == component
        ):
            return True
    return False


def _concern_has_component(concern: dict, component: str) -> bool:
    for m in concern.get("members") or []:
        if isinstance(m, dict) and m.get("component_id") == component:
            return True
    return False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_COMMON_JSON = {
    "json": {
        "type": "boolean",
        "description": "Return the structured payload as JSON instead of compact text.",
    }
}


def _schema(properties: dict, required: Optional[list[str]] = None) -> dict:
    props = dict(properties)
    props.update(_COMMON_JSON)
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    schema["additionalProperties"] = False
    return schema


TOOLS: list[ToolSpec] = [
    ToolSpec(
        "se_overview",
        "Architecture summary: component count and roles, capability counts by "
        "kind, entity/rule/concern/finding counts, coverage summary, enrichment "
        "fresh/stale counts, and the AI architecture narrative when present. No input.",
        _schema({}),
        _tool_overview,
    ),
    ToolSpec(
        "se_search",
        "Ranked full-text search over symbol/component names, paths, docstrings, "
        "and AI help text. Each hit carries its id, kind, and a one-line context.",
        _schema(
            {
                "query": {"type": "string", "description": "FTS5 query string."},
                "kind": {
                    "type": "string",
                    "description": "Optional ref_kind filter: symbol | component | enrichment.",
                },
                "limit": {"type": "integer", "description": "Max hits (default 30)."},
            },
            required=["query"],
        ),
        _tool_search,
    ),
    ToolSpec(
        "se_component",
        "The full component card: role, files, capabilities, entities touched, "
        "rules, edges in/out with evidence and confidence and AI verdicts, "
        "enrichment with staleness, and an activity summary.",
        _schema({"id": {"type": "string", "description": "Component id."}}, required=["id"]),
        _tool_component,
    ),
    ToolSpec(
        "se_symbol",
        "Symbol detail: signature, docstring, code preview, file:line, containing "
        "component, and the parent chain (enclosing class/module).",
        _schema({"id": {"type": "string", "description": "Symbol id (SCIP-style)."}}, required=["id"]),
        _tool_symbol,
    ),
    ToolSpec(
        "se_refs",
        "Importers and importees of a component (or a symbol's containing "
        "component) with confidence and evidence. Resolution is import/dependency "
        "level, not a compiler-grade call graph.",
        _schema(
            {
                "id": {"type": "string", "description": "Component or symbol id."},
                "direction": {
                    "type": "string",
                    "enum": ["in", "out", "both"],
                    "description": "in=importers, out=importees, both (default).",
                },
            },
            required=["id"],
        ),
        _tool_refs,
    ),
    ToolSpec(
        "se_impact",
        "Blast radius: everything that transitively depends on this node "
        "(what breaks if it changes), ranked nearest-first, with the per-hop "
        "evidence chain.",
        _schema(
            {
                "id": {"type": "string", "description": "Component or symbol id."},
                "depth": {"type": "integer", "description": "Max hops (default 3)."},
                "limit": {"type": "integer", "description": "Max nodes (default 50)."},
            },
            required=["id"],
        ),
        _tool_impact,
    ),
    ToolSpec(
        "se_coverage",
        "The coverage ledger: the disposition summary, or the file rows for one "
        "disposition when 'disposition' is given.",
        _schema(
            {
                "disposition": {
                    "type": "string",
                    "description": "Filter to one disposition (parsed, excluded:*, failed:*, binary).",
                },
                "limit": {"type": "integer", "description": "Max rows (default 50)."},
            }
        ),
        _tool_coverage,
    ),
    ToolSpec(
        "se_rules",
        "Business/validation rules, filterable by component, entity, kind, or a "
        "text query. Plain-language names appear when enrichment provides them; "
        "stale AI names are marked.",
        _schema(
            {
                "component": {"type": "string", "description": "Filter by owning component id."},
                "entity": {"type": "string", "description": "Filter by referenced data entity."},
                "kind": {"type": "string", "description": "validation | calculation | policy | io."},
                "query": {"type": "string", "description": "Substring match over the rule summary."},
                "limit": {"type": "integer", "description": "Max rules (default 50)."},
            }
        ),
        _tool_rules,
    ),
    ToolSpec(
        "se_findings",
        "Ranked correlation findings (duplication, unreferenced components, "
        "inconsistency, intent violations) with verification status always shown "
        "and unverified findings marked. Pass 'component' to also get its concern "
        "memberships.",
        _schema(
            {
                "kind": {"type": "string", "description": "duplication | unreferenced | inconsistency | ..."},
                "status": {
                    "type": "string",
                    "description": "Filter by verification_status (verified | unverified | refuted | uncertain).",
                },
                "component": {"type": "string", "description": "Only findings/concerns touching this component."},
                "limit": {"type": "integer", "description": "Max findings (default 50)."},
            }
        ),
        _tool_findings,
    ),
]

TOOLS_BY_NAME: dict[str, ToolSpec] = {t.name: t for t in TOOLS}


def call_tool(ctx: StoreContext, name: str, args: dict) -> ToolResult:
    """Dispatch to a tool by name. Raises KeyError for an unknown tool and
    ToolError for malformed arguments (the server maps both to JSON-RPC errors).
    """
    spec = TOOLS_BY_NAME.get(name)
    if spec is None:
        raise KeyError(name)
    return spec.handler(ctx, args or {})


def render_result(result: ToolResult, as_json: bool) -> str:
    """The text payload for a tool result: compact text or JSON."""
    if as_json:
        return json.dumps(result.data, indent=2, sort_keys=True, default=str)
    return result.text
