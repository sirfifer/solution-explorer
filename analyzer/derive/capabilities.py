"""Capability derivation (Tier 3, P5-1): what the system can be asked to do.

A capability is derived from the signals the extraction tier already emitted
(endpoint, cli_command, cli_option, queue_name, job), never from a source
re-read (invariant I1: deterministic skeleton). Kinds are ``api`` (REST/HTTP
operation), ``cli`` (command with flags), ``event`` (queue topic consumed or
emitted), and ``job`` (scheduled or background task). Each capability records
its owning component, its defining symbol where resolvable, evidence
(file, line, snippet), a confidence tier (I3: ``certain`` for parse-level
framework-anchored api/cli facts, ``inferred`` for heuristic event/job facts),
and a structured detail (method+path, command+flags, topic+direction).

Test-linkage groundwork (LENS-DESIGN.md L2): where a test file textually
references a capability's route path or command name, the association is
recorded in ``detail["tests"]`` with confidence ``inferred``. The full linkage
UI is P6-3; this pass lands the data.

Emission is deterministic (invariant I4): capabilities are id-sorted, evidence
and flags and tests are sorted, and ids are content-derived, never order-derived.
"""

from __future__ import annotations

import re
from typing import Optional

from .context import Deriver
from .testing import _is_test_file

__all__ = ["derive_capabilities"]

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("-", text.lower()).strip("-") or "unnamed"


def _snippet(content: Optional[str], line: Optional[int]) -> str:
    if not content or not line:
        return ""
    lines = content.split("\n")
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()[:200]
    return ""


def _symbols_by_file(d: Deriver) -> dict[str, list]:
    out: dict[str, list] = {}
    for s in d._all_symbols:
        out.setdefault(s.file, []).append(s)
    return out


def _resolve_symbol(symbols: list, line: Optional[int]) -> Optional[object]:
    """Innermost symbol whose range contains ``line``, else the nearest symbol
    starting within 3 lines below (the decorator-precedes-function case)."""
    if line is None or not symbols:
        return None
    containing = [
        s for s in symbols
        if s.line and s.end_line and s.line <= line <= s.end_line
    ]
    if containing:
        return min(containing, key=lambda s: (s.end_line - s.line, s.line, s.id))
    following = [s for s in symbols if s.line and 0 <= s.line - line <= 3]
    if following:
        return min(following, key=lambda s: (s.line, s.id))
    return None


class _Cap:
    """A capability under construction, merged across evidence occurrences."""

    __slots__ = ("id", "component_id", "kind", "name", "detail",
                 "evidence", "confidence", "symbol_id")

    def __init__(self, cap_id, component_id, kind, name, detail, confidence):
        self.id = cap_id
        self.component_id = component_id
        self.kind = kind
        self.name = name
        self.detail = detail
        self.evidence: list[dict] = []
        self.confidence = confidence
        self.symbol_id: Optional[str] = None

    def to_dict(self) -> dict:
        detail = dict(self.detail)
        if self.symbol_id:
            detail["symbol"] = self.symbol_id
        return {
            "id": self.id,
            "component_id": self.component_id,
            "kind": self.kind,
            "name": self.name,
            "detail": detail,
            "evidence": sorted(
                self.evidence, key=lambda e: (e.get("file") or "", e.get("line") or 0)
            ),
            "confidence": self.confidence,
        }


def derive_capabilities(d: Deriver) -> None:
    """Build capabilities from stored signals and record them on ``d``."""
    symbols_by_file = _symbols_by_file(d)
    caps: dict[str, _Cap] = {}

    def owner(path: str) -> Optional[str]:
        comp = d._find_component_for_file(path)
        return comp.id if comp else None

    def add(cap_id, component_id, kind, name, detail, confidence,
            file, line, content) -> _Cap:
        cap = caps.get(cap_id)
        if cap is None:
            cap = _Cap(cap_id, component_id, kind, name, detail, confidence)
            caps[cap_id] = cap
        cap.evidence.append({"file": file, "line": line, "snippet": _snippet(content, line)})
        if cap.symbol_id is None:
            sym = _resolve_symbol(symbols_by_file.get(file, []), line)
            if sym is not None:
                cap.symbol_id = sym.id
        return cap

    for path in sorted(d.view.signals_by_path):
        signals = d.view.signals_by_path[path]
        component_id = owner(path)
        content = d.view.content(path)

        # -- api: endpoint signals -----------------------------------------
        for sig in signals:
            if sig["kind"] != "endpoint":
                continue
            v = sig.get("value") or {}
            method = (v.get("method") or "ANY").upper()
            route = v.get("path") or ""
            name = f"{method} {route}".strip()
            cap_id = f"cap:{component_id}:api:{_slug(method + '-' + route)}"
            detail = {"method": method, "path": route, "framework": v.get("framework")}
            add(cap_id, component_id, "api", name, detail, "certain",
                path, sig.get("line"), content)

        # -- cli: command signals, flags attached by proximity -------------
        commands = sorted(
            (s for s in signals if s["kind"] == "cli_command"),
            key=lambda s: (s.get("line") or 0),
        )
        options = [s for s in signals if s["kind"] == "cli_option"]
        cmd_flags: dict[int, list[str]] = {i: [] for i in range(len(commands))}
        for opt in options:
            flag = (opt.get("value") or {}).get("flag")
            if not flag:
                continue
            oline = opt.get("line") or 0
            # nearest preceding command in this file, else the first command
            idx = None
            for i, cmd in enumerate(commands):
                if (cmd.get("line") or 0) <= oline:
                    idx = i
            if idx is None and commands:
                idx = 0
            if idx is not None:
                cmd_flags[idx].append(flag)

        for i, cmd in enumerate(commands):
            v = cmd.get("value") or {}
            line = cmd.get("line")
            name = v.get("name")
            if not name:
                sym = _resolve_symbol(symbols_by_file.get(path, []), line)
                name = sym.name if sym is not None else f"{path}:{line}"
            flags = sorted(set(cmd_flags[i]))
            cap_id = f"cap:{component_id}:cli:{_slug(name)}"
            detail = {"command": name, "framework": v.get("framework"), "flags": flags}
            cap = add(cap_id, component_id, "cli", name, detail, "certain",
                      path, line, content)
            # merge flags if the same command recurs across files/occurrences
            existing = set(cap.detail.get("flags", []))
            cap.detail["flags"] = sorted(existing | set(flags))

        # -- event: queue topic signals ------------------------------------
        for sig in signals:
            if sig["kind"] != "queue_name":
                continue
            v = sig.get("value") or {}
            topic = v.get("name")
            if not topic:
                continue
            direction = v.get("direction")
            name = topic if not direction else f"{topic} ({direction})"
            cap_id = f"cap:{component_id}:event:{_slug(topic + '-' + (direction or 'topic'))}"
            detail = {"topic": topic}
            if direction:
                detail["direction"] = direction
            add(cap_id, component_id, "event", name, detail, "inferred",
                path, sig.get("line"), content)

        # -- job: scheduled / background task signals ----------------------
        for sig in signals:
            if sig["kind"] != "job":
                continue
            v = sig.get("value") or {}
            line = sig.get("line")
            jname = v.get("name")
            if not jname:
                sym = _resolve_symbol(symbols_by_file.get(path, []), line)
                jname = sym.name if sym is not None else (v.get("trigger") or v.get("framework") or "job")
            trigger = v.get("trigger")
            sig_slug = _slug(jname + "-" + (trigger or v.get("framework") or ""))
            cap_id = f"cap:{component_id}:job:{sig_slug}"
            detail = {"name": jname, "framework": v.get("framework")}
            if trigger:
                detail["trigger"] = trigger
            add(cap_id, component_id, "job", jname, detail, "inferred",
                path, line, content)

    _attach_test_linkage(d, caps)

    ordered = [caps[k].to_dict() for k in sorted(caps)]
    d.capabilities = ordered
    by_comp: dict[str, list[dict]] = {}
    for cap in ordered:
        cid = cap["component_id"]
        if cid is None:
            continue
        by_comp.setdefault(cid, []).append(cap)
    d._capabilities_by_component = by_comp


def _attach_test_linkage(d: Deriver, caps: dict[str, _Cap]) -> None:
    """Record test files that textually reference a capability's path/command.

    A conservative, evidence-first heuristic (LENS-DESIGN L2): for each test
    file, look for the capability's route path (api) or command name (cli) as a
    literal substring, and record the first hit with confidence ``inferred``.
    Landed as data; the linkage UI is P6-3.
    """
    file_lang = {fi.path: fi.language for fi in d._all_files}
    test_contents: list[tuple[str, str]] = []
    for path, content in d.view.content_by_path.items():
        if content and _is_test_file(path, file_lang.get(path, "")):
            test_contents.append((path, content))
    if not test_contents:
        return
    test_contents.sort()

    for cap in caps.values():
        if cap.kind == "api":
            token = cap.detail.get("path") or ""
            # a parametrized route also matches on its static prefix
            static = re.split(r"[{:<]", token)[0].rstrip("/") if token else ""
            candidates = [t for t in (token, static) if t and t != "/"]
        elif cap.kind == "cli":
            token = cap.detail.get("command") or ""
            candidates = [token] if token and ":" not in token else []
        else:
            candidates = []
        if not candidates:
            continue
        links: list[dict] = []
        for tpath, tcontent in test_contents:
            hit_line = None
            for cand in candidates:
                idx = tcontent.find(cand)
                if idx >= 0:
                    hit_line = tcontent.count("\n", 0, idx) + 1
                    break
            if hit_line is not None:
                links.append({"file": tpath, "line": hit_line, "confidence": "inferred"})
        if links:
            cap.detail["tests"] = sorted(links, key=lambda x: (x["file"], x["line"]))
