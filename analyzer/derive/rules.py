"""Rule derivation (Tier 3, P5-5): where the business decisions live.

Builds typed ``rules`` from the ``rule`` signals the extraction tier emitted
(never from a source re-read; invariant I1). A rule is a discrete unit of
decision or constraint logic, kinded ``validation`` | ``calculation`` |
``policy`` | ``io`` (LENS-DESIGN.md L6; TARGET-ARCHITECTURE.md section 6
integration note). Each rule records its owning component, its enclosing symbol
where resolvable, its trigger context (linked to the capability the enclosing
symbol defines, where one exists), an entity link for io rules whose constrained
field lives on a P5-2 data entity, a MECHANICAL summary (the condition text and
outcome, never a natural-language explanation: that is Phase 7 enrichment,
invariant I1), evidence (file, line, snippet), and a confidence tier (I3:
``certain`` for declared/schema-anchored rules, ``inferred`` for shape-matched
guards, formulae, and branching).

This pass runs after ``derive_capabilities`` and ``derive_entities`` so the
capability-symbol map and the entity-field map are available for cross-linking.

Emission is deterministic (invariant I4): rules are id-sorted, inputs/outputs/
evidence are sorted, and ids are content-and-path-derived (a hash over
file/line/summary), never discovery-order-derived.
"""

from __future__ import annotations

import hashlib
from typing import Optional

from .capabilities import _resolve_symbol, _slug, _snippet, _symbols_by_file
from .context import Deriver

__all__ = ["derive_rules"]


def _hash8(*parts: object) -> str:
    h = hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8"))
    return h.hexdigest()[:8]


def _capability_symbol_map(d: Deriver) -> dict[str, str]:
    """Map an enclosing symbol id -> the capability id it defines, if any."""
    out: dict[str, str] = {}
    for cap in d.capabilities:
        sym = (cap.get("detail") or {}).get("symbol")
        if sym and sym not in out:
            out[sym] = cap["id"]
    return out


def _entity_field_map(d: Deriver) -> dict[tuple[str, str], str]:
    """Map (declaring-file, field_name) -> entity id for io cross-linking.

    Keyed by the entity's declaring file (from its evidence), so an io rule
    links only to an entity declared in the SAME file. A same-component fallback
    was rejected: it links a field-name collision (a DTO ``email`` and an
    unrelated table ``email`` in the same component) to the wrong entity.
    Precision over recall (P5-5 card).
    """
    out: dict[tuple[str, str], str] = {}
    for ent in d.data_entities:
        files = {e.get("file") for e in ent.get("evidence") or [] if e.get("file")}
        for f in ent.get("fields") or []:
            fname = f.get("name")
            if not fname:
                continue
            for fpath in files:
                out.setdefault((fpath, fname), ent["id"])
    return out


def derive_rules(d: Deriver) -> None:
    """Build typed rules from stored ``rule`` signals; record them on ``d``."""
    symbols_by_file = _symbols_by_file(d)
    cap_by_symbol = _capability_symbol_map(d)
    entity_by_field = _entity_field_map(d)
    rules: list[dict] = []

    def owner(path: str) -> Optional[str]:
        comp = d._find_component_for_file(path)
        return comp.id if comp else None

    for path in sorted(d.view.signals_by_path):
        signals = d.view.signals_by_path[path]
        component_id = owner(path)
        content = d.view.content(path)
        for sig in signals:
            if sig["kind"] != "rule":
                continue
            v = sig.get("value") or {}
            kind = v.get("kind")
            summary = v.get("summary") or ""
            line = sig.get("line")
            if not kind or not summary:
                continue

            rule_id = (
                f"rule:{component_id}:{kind}:"
                f"{_slug(v.get('anchor') or kind)}-{_hash8(path, line, summary)}"
            )

            detail: dict = {"anchor": v.get("anchor")}
            if v.get("framework"):
                detail["framework"] = v["framework"]
            if v.get("inputs"):
                detail["inputs"] = sorted(v["inputs"])
            if v.get("outputs"):
                detail["outputs"] = sorted(v["outputs"])
            if v.get("field"):
                detail["field"] = v["field"]

            # Enclosing symbol + trigger context.
            sym = _resolve_symbol(symbols_by_file.get(path, []), line)
            trigger: dict = {}
            if sym is not None:
                detail["symbol"] = sym.id
                cap_id = cap_by_symbol.get(sym.id)
                if cap_id:
                    trigger["capability"] = cap_id
                else:
                    trigger["symbol"] = sym.id
            if trigger:
                detail["trigger"] = trigger

            # Entity link for io rules whose constrained field is declared on an
            # entity in the same file (Data-lens L3 cross-reference).
            if kind == "io" and v.get("field") is not None:
                ent_id = entity_by_field.get((path, v["field"]))
                if ent_id:
                    detail["entity"] = ent_id

            rules.append({
                "id": rule_id,
                "component_id": component_id,
                "kind": kind,
                "summary": summary,
                "detail": detail,
                "evidence": [{
                    "file": path, "line": line, "snippet": _snippet(content, line),
                }],
                "confidence": v.get("confidence") or "inferred",
            })

    rules.sort(key=lambda r: r["id"])
    d.rules = rules
    by_comp: dict[str, list[dict]] = {}
    for rule in rules:
        cid = rule["component_id"]
        if cid is None:
            continue
        by_comp.setdefault(cid, []).append(rule)
    d._rules_by_component = by_comp
