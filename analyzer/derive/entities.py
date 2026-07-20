"""Data-entity derivation (Tier 3, P5-2): what the system knows.

Builds ``data_entities`` and ``entity_access`` from the ``data_entity`` signals
the extraction tier emitted (never from a source re-read; invariant I1). An
entity is an ORM model, a migration-declared table, or a standalone schema
(LENS-DESIGN.md L3; TARGET-ARCHITECTURE.md section 5). Each entity records its
owning component, its defining symbol where resolvable, merged fields, and
evidence (file, line, snippet).

``entity_access`` edges record which component reads or writes each entity, with
evidence and a confidence tier (invariant I3): ``certain`` when a file uses the
entity's class name in a verb-anchored ORM operation (direct model usage),
``inferred`` when only the entity's table name appears as a string literal
(string-matched table reference). Mode is ``write`` for create/update/delete/
instantiate operations, ``read`` otherwise.

Emission is deterministic (invariant I4): entities are id-sorted, access edges
are sorted by (accessor, entity, mode), fields and evidence are sorted, and ids
are content-derived, never order-derived.
"""

from __future__ import annotations

import re
from typing import Optional

from .capabilities import _resolve_symbol, _slug, _snippet, _symbols_by_file
from .context import Deriver
from .testing import is_fixture_path

__all__ = ["derive_entities"]

# Kind precedence when the same (component, name) is seen from several sources:
# a model declaration is the most specific, a bare schema the least.
_KIND_PRIORITY = {"model": 3, "table": 2, "migration": 1, "schema": 0}

_WRITE_RE = re.compile(
    r"\.save\s*\(|\.create\s*\(|\.bulk_create\s*\(|\.add\s*\(|\.insert\b|"
    r"\.update\s*\(|\.delete\s*\(|\.destroy\b|\.remove\s*\(|\bINSERT\s+INTO\b|"
    r"\bUPDATE\b|\bDELETE\s+FROM\b|\bnew\s+{name}\b|\b{name}\s*\(",
    re.IGNORECASE,
)
_READ_RE = re.compile(
    r"\.query\s*\(|\.filter\s*\(|\.get\s*\(|\.all\s*\(|\.find\w*\s*\(|"
    r"\.where\s*\(|\.first\b|\.count\s*\(|\.select\s*\(|\bSELECT\b|\.objects\b|"
    r"\.fetch\w*\s*\(",
    re.IGNORECASE,
)
_IMPORT_RE = re.compile(r"^\s*(import|from|require|use|#include|@import)\b")
_SQL_CTX_RE = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|FROM|INTO|JOIN|TABLE)\b", re.IGNORECASE
)
# A declaration line (a class/struct/model definition) is not an access to the
# entity it declares, even when it appears in a different component than the
# entity's own defining file (for example a Django model class and its migration
# share the name). Excluding declaration-shaped lines keeps those out.
_DECL_RE = re.compile(r"^\s*(?:export\s+|public\s+|final\s+|abstract\s+)*"
                      r"(class|struct|interface|type|model|def|func|record)\b")


class _Entity:
    """A data entity under construction, merged across occurrences."""

    __slots__ = ("id", "component_id", "name", "kind", "framework",
                 "table", "fields", "evidence", "symbol_id", "inferred",
                 "decl_files")

    def __init__(self, entity_id, component_id, name):
        self.id = entity_id
        self.component_id = component_id
        self.name = name
        self.kind = "schema"
        self.framework: Optional[str] = None
        self.table: Optional[str] = None
        self.fields: dict[str, Optional[str]] = {}
        self.evidence: list[dict] = []
        self.symbol_id: Optional[str] = None
        self.inferred = False
        # Files where this entity is declared, so its own definition (class
        # header, __tablename__, create_table, JSON title) is not counted as
        # access to itself.
        self.decl_files: set[str] = set()

    def merge(self, value: dict, file: str, line: Optional[int], content) -> None:
        kind = value.get("kind") or "schema"
        if _KIND_PRIORITY.get(kind, -1) > _KIND_PRIORITY.get(self.kind, -1):
            self.kind = kind
            self.framework = value.get("framework")
        if self.framework is None:
            self.framework = value.get("framework")
        if value.get("table") and not self.table:
            self.table = value["table"]
        if value.get("inferred"):
            self.inferred = True
        for f in value.get("fields") or []:
            fname = f.get("name")
            if not fname:
                continue
            if fname not in self.fields or (self.fields[fname] is None and f.get("type")):
                self.fields[fname] = f.get("type")
        self.evidence.append({"file": file, "line": line, "snippet": _snippet(content, line)})
        self.decl_files.add(file)

    def to_dict(self) -> dict:
        detail_fields = [
            {"name": n, "type": self.fields[n]} for n in sorted(self.fields)
        ]
        d = {
            "id": self.id,
            "component_id": self.component_id,
            "name": self.name,
            "kind": self.kind,
            "framework": self.framework,
            "fields": detail_fields,
            "evidence": sorted(
                self.evidence, key=lambda e: (e.get("file") or "", e.get("line") or 0)
            ),
        }
        if self.table:
            d["table"] = self.table
        if self.symbol_id:
            d["symbol"] = self.symbol_id
        if self.inferred:
            d["inferred"] = True
        # D6: fixture origin when every declaring file is under a test or fixture
        # directory. Marked (never dropped, so totality holds) so the viewer ranks
        # fixture entities behind product entities.
        if self.decl_files and all(is_fixture_path(f) for f in self.decl_files):
            d["fixture"] = True
        return d


def derive_entities(d: Deriver) -> None:
    """Build data entities and access edges from stored signals; record on ``d``."""
    symbols_by_file = _symbols_by_file(d)
    entities: dict[str, _Entity] = {}

    def owner(path: str) -> Optional[str]:
        comp = d._find_component_for_file(path)
        return comp.id if comp else None

    # -- 1. entities from data_entity signals ------------------------------
    for path in sorted(d.view.signals_by_path):
        signals = d.view.signals_by_path[path]
        component_id = owner(path)
        content = d.view.content(path)
        for sig in signals:
            if sig["kind"] != "data_entity":
                continue
            value = sig.get("value") or {}
            name = value.get("name")
            if not name:
                continue
            ent_id = f"entity:{component_id}:{_slug(name)}"
            ent = entities.get(ent_id)
            if ent is None:
                ent = _Entity(ent_id, component_id, name)
                entities[ent_id] = ent
            ent.merge(value, path, sig.get("line"), content)
            if ent.symbol_id is None:
                sym = _resolve_symbol(symbols_by_file.get(path, []), sig.get("line"))
                if sym is not None:
                    ent.symbol_id = sym.id

    # -- 2. access edges ---------------------------------------------------
    access = _derive_access(d, entities, owner)

    ordered = [entities[k].to_dict() for k in sorted(entities)]
    d.data_entities = ordered
    by_comp: dict[str, list[dict]] = {}
    for ent in ordered:
        cid = ent["component_id"]
        if cid is None:
            continue
        by_comp.setdefault(cid, []).append(ent)
    d._entities_by_component = by_comp
    d.entity_access = access


def _derive_access(d: Deriver, entities: dict[str, _Entity], owner) -> list[dict]:
    """Scan cached file content for read/write references to each entity."""
    # Index entities by their reference tokens for a cheap first-pass filter.
    ents = list(entities.values())
    # edge key -> {evidence, confidence}
    edges: dict[tuple[str, str, str], dict] = {}

    for path in sorted(d.view.content_by_path):
        content = d.view.content_by_path[path]
        if not content:
            continue
        accessor = owner(path)
        if accessor is None:
            continue
        lines = content.split("\n")
        for ent in ents:
            if path in ent.decl_files:
                continue  # a file does not "access" an entity it declares
            name = ent.name
            table = ent.table
            # certain path: an ORM model class used as a code identifier.
            is_model = ent.kind == "model"
            has_name = is_model and bool(name) and name in content
            # inferred path: the physical table name referenced in a query
            # (quoted literal, or a bare token in SQL context).
            table_token = table or (name if not is_model else None)
            has_table = bool(table_token) and table_token in content
            if not has_name and not has_table:
                continue
            name_re = re.compile(rf"\b{re.escape(name)}\b") if name else None
            table_re = re.compile(rf"\b{re.escape(table_token)}\b") if table_token else None
            table_lits = (
                [f'"{table_token}"', f"'{table_token}'", f"`{table_token}`"]
                if table_token else []
            )
            write_re = re.compile(
                _WRITE_RE.pattern.replace("{name}", re.escape(name or "\0")),
                re.IGNORECASE,
            )
            for i, ln in enumerate(lines, 1):
                if _IMPORT_RE.match(ln) or _DECL_RE.match(ln):
                    continue
                confidence: Optional[str] = None
                if (has_name and name_re and name_re.search(ln)
                        and (write_re.search(ln) or _READ_RE.search(ln))):
                    confidence = "certain"
                if confidence is None and has_table and table_re:
                    quoted = any(t in ln for t in table_lits)
                    in_sql = bool(table_re.search(ln)) and bool(_SQL_CTX_RE.search(ln))
                    if quoted or in_sql:
                        confidence = "inferred"
                if confidence is None:
                    continue
                mode = "write" if write_re.search(ln) else "read"
                key = (accessor, ent.id, mode)
                slot = edges.get(key)
                if slot is None:
                    slot = {"evidence": [], "confidence": confidence}
                    edges[key] = slot
                # certain outranks inferred if both seen for the same edge
                if confidence == "certain":
                    slot["confidence"] = "certain"
                slot["evidence"].append(
                    {"file": path, "line": i, "snippet": ln.strip()[:200]}
                )

    out = []
    for (accessor, entity_id, mode) in sorted(edges):
        slot = edges[(accessor, entity_id, mode)]
        out.append({
            "accessor_id": accessor,
            "entity_id": entity_id,
            "mode": mode,
            "confidence": slot["confidence"],
            "evidence": sorted(
                slot["evidence"], key=lambda e: (e["file"], e["line"])
            ),
        })
    return out
