"""Per-file signal extraction for Tier 1 (TARGET-ARCHITECTURE.md section 4.1).

Signals are the raw observations Tier 3 derivation joins over: port bindings,
URL and service references, database/queue/websocket/gRPC driver usage, HTTP
client usage, endpoint declarations, CLI command declarations, UI actions with
their navigation target, env-var reads, and framework markers. In the old
engine (scanner.py) these are re-derived by re-reading each file many times;
here every signal for a file comes from a single content read.

Pattern tables are the SHARED SOURCE OF TRUTH in analyzer/constants.py, which
imports nothing and is safe to use without scanner.py. UI-action regexes reuse
the compiled patterns on analyzer.action_detector.UIActionDetector rather than
duplicating them. Endpoint, CLI-command/flag, and job patterns are the precise,
framework-anchored rules in frameworks.py (P5-1); they replaced the delegation to
analyzer/parsers/*.detect_api_endpoints, which stays as the legacy reference and
which the audited header-name false-positive class came from.

Every returned list is ordered by match position in the file, so extraction is
deterministic across processes (no set iteration; invariant I4).
"""

from __future__ import annotations

import re

from ..action_detector import UIActionDetector
from ..constants import (
    DATABASE_PATTERNS,
    GRPC_PATTERNS,
    HTTP_CLIENT_PATTERNS,
    MESSAGE_QUEUE_PATTERNS,
    QUEUE_NAME_PATTERNS,
    URL_EXTRACTION_PATTERNS,
    WEBSOCKET_PATTERNS,
)
from .entities import extract_entities, extract_schema_entities
from .facts import SignalRecord
from .frameworks import extract_cli, extract_endpoints, extract_jobs


def _line_of(content: str, pos: int) -> int:
    """1-based line number of a character offset."""
    return content.count("\n", 0, pos) + 1


# ---------------------------------------------------------------------------
# UI navigation targets: a Button/NavigationLink whose destination is a view.
# These are the target_view-bearing UI actions. SwiftUI flow (P4-3) refines
# these into navigation edges; here they are raw signals with evidence.
# ---------------------------------------------------------------------------

_NAV_TARGET_PATTERNS: list[re.Pattern] = [
    re.compile(r"NavigationLink\s*\([^)]*destination:\s*(\w+)\s*\("),
    re.compile(r"NavigationLink\s*(?:\([^)]*\))?\s*\{[^}]*?\}\s*\)?\s*\{\s*(\w+)\s*\("),
    re.compile(r"\.sheet\s*\([^)]*\)\s*\{\s*(\w+)\s*\("),
    re.compile(r"\.fullScreenCover\s*\([^)]*\)\s*\{\s*(\w+)\s*\("),
    re.compile(r"\.navigationDestination\s*\([^)]*\)\s*\{[^{}]*?(\w+)\s*\("),
]


def extract_signals(content: str, language: str, parser) -> list[SignalRecord]:
    """Extract every signal kind from one file's content, in a stable order.

    ``parser`` is the language parser instance (for its regex-backed detectors:
    ports, endpoints, env vars, framework). All other signals come from the
    shared constants tables applied to ``content`` directly.
    """
    out: list[SignalRecord] = []
    out.extend(_ports(content, parser))
    out.extend(_url_references(content))
    out.extend(_http_clients(content, language))
    out.extend(_db_drivers(content, language))
    out.extend(_queue_drivers(content, language))
    out.extend(_websocket_drivers(content, language))
    out.extend(_grpc_drivers(content, language))
    out.extend(_endpoints(content, language))
    out.extend(_cli_commands(content, language))
    out.extend(_jobs(content, language))
    out.extend(_ui_actions(content, language))
    out.extend(_env_vars(content, parser))
    out.extend(_framework(content, parser))
    return out


def _ports(content: str, parser) -> list[SignalRecord]:
    out = []
    for port in parser.detect_ports(content):
        # Recover a representative line by locating the port literal.
        m = re.search(rf"(?<!\d){port}(?!\d)", content)
        line = _line_of(content, m.start()) if m else None
        out.append(SignalRecord("port", {"port": port}, line))
    return out


def _url_references(content: str) -> list[SignalRecord]:
    out = []
    for pat in URL_EXTRACTION_PATTERNS:
        for m in re.finditer(pat, content):
            groups = m.groupdict()
            if groups.get("url"):
                out.append(SignalRecord(
                    "url_reference", {"url": groups["url"]}, _line_of(content, m.start())
                ))
            elif groups.get("service"):
                out.append(SignalRecord(
                    "url_reference", {"service": groups["service"]},
                    _line_of(content, m.start()),
                ))
    return out


def _http_clients(content: str, language: str) -> list[SignalRecord]:
    out = []
    for pat in HTTP_CLIENT_PATTERNS.get(language, []):
        for m in re.finditer(pat, content):
            out.append(SignalRecord(
                "http_client", {"evidence": m.group(0).strip()},
                _line_of(content, m.start()),
            ))
    return out


def _db_drivers(content: str, language: str) -> list[SignalRecord]:
    out = []
    for pat, library, engine in DATABASE_PATTERNS.get(language, []):
        for m in re.finditer(pat, content):
            out.append(SignalRecord(
                "db_driver", {"library": library, "engine": engine},
                _line_of(content, m.start()),
            ))
            break  # one signal per library per file is enough evidence
    return out


def _queue_drivers(content: str, language: str) -> list[SignalRecord]:
    out = []
    for pat, system in MESSAGE_QUEUE_PATTERNS.get(language, []):
        for m in re.finditer(pat, content):
            out.append(SignalRecord(
                "queue_driver", {"system": system}, _line_of(content, m.start())
            ))
            break
    for pat in QUEUE_NAME_PATTERNS:
        for m in re.finditer(pat, content):
            text = m.group(0)
            if ".subscribe" in text:
                direction = "consume"
            elif ".publish" in text:
                direction = "produce"
            else:
                direction = None
            value = {"name": m.group(1)}
            if direction:
                value["direction"] = direction
            out.append(SignalRecord(
                "queue_name", value, _line_of(content, m.start())
            ))
    return out


def _websocket_drivers(content: str, language: str) -> list[SignalRecord]:
    out = []
    for pat in WEBSOCKET_PATTERNS.get(language, []):
        for m in re.finditer(pat, content):
            out.append(SignalRecord(
                "websocket_driver", {"evidence": m.group(0).strip()},
                _line_of(content, m.start()),
            ))
            break
    return out


def _grpc_drivers(content: str, language: str) -> list[SignalRecord]:
    out = []
    for pat in GRPC_PATTERNS.get(language, []):
        for m in re.finditer(pat, content):
            out.append(SignalRecord(
                "grpc_driver", {"evidence": m.group(0).strip()},
                _line_of(content, m.start()),
            ))
            break
    return out


def _endpoints(content: str, language: str) -> list[SignalRecord]:
    """Endpoint signals from the precise per-framework rules (P5-1).

    Replaces the old delegation to ``parser.detect_api_endpoints``: every
    candidate passes through ``frameworks.is_route_path``, so header names
    (``Authorization``, ``X-Hub-Signature-256``) and outbound client URLs are
    never captured as routes. The signal value carries the matched ``framework``.
    """
    out = []
    for value, start in extract_endpoints(content, language):
        out.append(SignalRecord("endpoint", value, _line_of(content, start)))
    return out


def _cli_commands(content: str, language: str) -> list[SignalRecord]:
    commands, options = extract_cli(content, language)
    out = []
    for value, start in commands:
        out.append(SignalRecord("cli_command", value, _line_of(content, start)))
    for value, start in options:
        out.append(SignalRecord("cli_option", value, _line_of(content, start)))
    return out


def _jobs(content: str, language: str) -> list[SignalRecord]:
    """Scheduled / background job declarations (confidence 'inferred')."""
    out = []
    for value, start in extract_jobs(content, language):
        out.append(SignalRecord("job", value, _line_of(content, start)))
    return out


_UI_DETECTOR = UIActionDetector()


def _ui_actions(content: str, language: str) -> list[SignalRecord]:
    """Extract UI actions (with a navigation target_view where present).

    Reuses UIActionDetector's compiled patterns applied to ``content``
    directly, so the file is read only once. Navigation targets come from the
    local _NAV_TARGET_PATTERNS.
    """
    if language not in ("swift", "typescript", "javascript"):
        return []
    out: list[SignalRecord] = []
    d = _UI_DETECTOR

    if language == "swift":
        line_patterns = [
            (d.SWIFTUI_BUTTON_LABEL_RE, "button", 1, False),
            (d.IBACTION_RE, "ibaction", 1, True),
            (d.ADD_TARGET_RE, "button", 1, True),
            (d.CONFIRMATION_DIALOG_RE, "dialog", 1, False),
            (d.ALERT_RE, "alert", 1, False),
        ]
        for i, line in enumerate(content.split("\n"), 1):
            for rx, atype, grp, is_handler in line_patterns:
                m = rx.search(line)
                if m:
                    raw = m.group(grp)
                    label = d._humanize(raw) if is_handler else raw
                    out.append(SignalRecord("ui_action", {
                        "label": label, "action_type": atype,
                        "handler": raw if is_handler else None,
                        "target_view": None,
                    }, i))
            if d.ONTAP_RE.search(line):
                out.append(SignalRecord("ui_action", {
                    "label": "Tap gesture", "action_type": "gesture",
                    "handler": None, "target_view": None}, i))
        for rx, atype in (
            (d.TOOLBAR_ITEM_RE, "toolbar"),
            (d.CONTEXT_MENU_BUTTON_RE, "menu"),
            (d.SWIPE_ACTION_RE, "swipe"),
        ):
            for m in rx.finditer(content):
                out.append(SignalRecord("ui_action", {
                    "label": m.group(1), "action_type": atype,
                    "handler": None, "target_view": None,
                }, _line_of(content, m.start())))
    else:  # typescript / javascript
        for i, line in enumerate(content.split("\n"), 1):
            for rx, atype in ((d.ONCLICK_RE, "button"), (d.ONSUBMIT_RE, "form")):
                m = rx.search(line)
                if m:
                    handler = m.group(1)
                    out.append(SignalRecord("ui_action", {
                        "label": d._humanize(handler), "action_type": atype,
                        "handler": handler, "target_view": None,
                    }, i))

    # Navigation targets (target_view-bearing actions).
    for pat in _NAV_TARGET_PATTERNS:
        for m in pat.finditer(content):
            target = m.group(1)
            out.append(SignalRecord("ui_action", {
                "label": f"Navigate to {target}", "action_type": "navigation",
                "handler": None, "target_view": target,
            }, _line_of(content, m.start())))
    return out


def _env_vars(content: str, parser) -> list[SignalRecord]:
    out = []
    for name in parser.extract_env_vars(content):
        m = re.search(rf"\b{re.escape(name)}\b", content)
        line = _line_of(content, m.start()) if m else None
        out.append(SignalRecord("env_var", {"name": name}, line))
    return out


def _framework(content: str, parser) -> list[SignalRecord]:
    fw = parser.detect_framework(content)
    if fw:
        return [SignalRecord("framework", {"name": fw}, None)]
    return []


def extract_entity_signals(content: str, language: str, path: str) -> list[SignalRecord]:
    """Extract ``data_entity`` signals from one file (P5-2, Data lens L3).

    Parser-independent: ORM/model entities come from the per-framework rules in
    entities.py for code languages, and standalone-schema entities (Prisma, SQL
    DDL, JSON Schema) come from the schema extractors. Called from the runner
    alongside ``extract_signals`` so a file is still read exactly once. Every
    signal carries the match line where locatable, so derivation (Tier 3) can
    attach evidence and resolve the defining symbol.
    """
    out: list[SignalRecord] = []
    for value, start in extract_entities(content, language):
        out.append(SignalRecord("data_entity", value, _line_of(content, start)))
    for value, start in extract_schema_entities(content, language, path):
        out.append(SignalRecord("data_entity", value, _line_of(content, start)))
    return out
