"""Cached read-only view over a fact store for the MCP tools.

The MCP server opens one store for its lifetime and only reads it (invariant I9:
no writes, no LLM calls at query time). This context loads the store's tables
once and builds the lookup indexes every tool needs (by id, by component, edge
adjacency, enrichment by target), plus a single :class:`DigestIndex` so every
tool can mark AI content stale at read time (invariant I5) without recomputing.

Everything here is a pure read. Nothing in this package imports scanner.py or
incremental.py, and nothing writes to the store.
"""

from __future__ import annotations

from functools import cached_property
from typing import Optional

from ..enrich.digest import DigestIndex, relationship_target_id
from ..enrich.staleness import staleness_of
from ..store import FactStore

# Enrichment target kinds whose current digest the DigestIndex can resolve.
# A row of any other kind (for example a future 'rule' enrichment with no
# producer yet) gets an honest "unknown" staleness rather than a false "stale".
_DIGEST_KINDS = frozenset(
    {
        "component",
        "symbol",
        "relationship",
        "architecture",
        "edge-verdict",
        "concern",
        "finding",
        "finding-verdict",
    }
)


class StoreContext:
    """Lazily-cached, read-only lookups over one :class:`FactStore`."""

    def __init__(self, store: FactStore):
        self.store = store

    # -- raw tables (cached once) -----------------------------------------

    @cached_property
    def components(self) -> list[dict]:
        return self.store.components()

    @cached_property
    def edges(self) -> list[dict]:
        return self.store.edges()

    @cached_property
    def capabilities(self) -> list[dict]:
        return self.store.capabilities()

    @cached_property
    def data_entities(self) -> list[dict]:
        return self.store.data_entities()

    @cached_property
    def entity_access_rows(self) -> list[dict]:
        return self.store.entity_access()

    @cached_property
    def rules(self) -> list[dict]:
        return self.store.rules()

    @cached_property
    def concerns(self) -> list[dict]:
        return self.store.concerns()

    @cached_property
    def findings(self) -> list[dict]:
        return self.store.findings()

    @cached_property
    def enrichment_rows(self) -> list[dict]:
        return self.store.enrichment()

    @cached_property
    def file_activity(self) -> list[dict]:
        return self.store.file_activity()

    @cached_property
    def file_authors(self) -> list[dict]:
        return self.store.file_authors()

    # -- indexes ----------------------------------------------------------

    @cached_property
    def component_by_id(self) -> dict[str, dict]:
        return {c["id"]: c for c in self.components}

    @cached_property
    def children_of(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for c in self.components:
            pid = c.get("parent_id")
            if pid:
                out.setdefault(pid, []).append(c)
        return out

    @cached_property
    def files_of_component(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for row in self.store.component_files():
            out.setdefault(row["component_id"], []).append(row["path"])
        return out

    @cached_property
    def components_of_path(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for cid, paths in self.files_of_component.items():
            for p in paths:
                out.setdefault(p, []).append(cid)
        return out

    @cached_property
    def edges_out(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for e in self.edges:
            out.setdefault(e["source_id"], []).append(e)
        return out

    @cached_property
    def edges_in(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for e in self.edges:
            out.setdefault(e["target_id"], []).append(e)
        return out

    @cached_property
    def capabilities_of(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for cap in self.capabilities:
            out.setdefault(cap.get("component_id"), []).append(cap)
        return out

    @cached_property
    def rules_of(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for r in self.rules:
            out.setdefault(r.get("component_id"), []).append(r)
        return out

    @cached_property
    def entity_by_id(self) -> dict[str, dict]:
        return {e["id"]: e for e in self.data_entities}

    @cached_property
    def access_by_accessor(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for a in self.entity_access_rows:
            out.setdefault(a["accessor_id"], []).append(a)
        return out

    @cached_property
    def enrichment_by_target(self) -> dict[tuple[str, str], dict]:
        return {(r["target_kind"], r["target_id"]): r for r in self.enrichment_rows}

    @cached_property
    def activity_by_path(self) -> dict[str, dict]:
        return {r["path"]: r for r in self.file_activity}

    @cached_property
    def authors_by_path(self) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for a in self.file_authors:
            out.setdefault(a["path"], []).append(a)
        return out

    @cached_property
    def symbol_by_id(self) -> dict[str, dict]:
        return {s["id"]: s for s in self.store.symbols()}

    @cached_property
    def file_path_by_id(self) -> dict[int, str]:
        return {f["id"]: f["path"] for f in self.store.files()}

    @cached_property
    def digest_index(self) -> DigestIndex:
        return DigestIndex.from_store(self.store)

    @cached_property
    def design_signals(self):
        """Architecture quality signals, DERIVED on demand from this store (D6).

        Deliberately derived rather than read from the store's ``design_signals``
        meta blob, and that choice is the whole consistency guarantee. The blob
        is written only by a projection run with ``--design-signals``, and
        ``derive_all`` rebuilds components and edges without clearing meta, so a
        stored document can outlive the facts it was computed from. Deriving
        here means the MCP tools and the viewer are reading the same function
        over the same store, so their numbers agree by construction rather than
        by two producers happening to stay in step. A test compares the two
        surfaces directly.

        Pure read, so it honours this package's contract that nothing writes to
        the store.
        """
        from ..derive.design_signals import derive_design_signals

        return derive_design_signals(self.store)

    # -- helpers ----------------------------------------------------------

    def enrichment_for(self, kind: str, target_id: str) -> Optional[dict]:
        """The enrichment row for a target, or None."""
        return self.enrichment_by_target.get((kind, target_id))

    def edge_verdict_for(self, source: str, target: str, type: str) -> Optional[dict]:
        """The AI edge verdict row for an edge, keyed source|target|type (P7-3)."""
        key = relationship_target_id(source, target, type)
        return self.enrichment_by_target.get(("edge-verdict", key))

    def staleness_of_row(self, row: Optional[dict]) -> Optional[bool]:
        """True / False / None staleness for an enrichment row (I5).

        None means "unknown": either an un-stamped legacy row, or a target kind
        the digest index does not define (so we never assert a false 'stale').
        """
        if row is None:
            return None
        kind = row["target_kind"]
        if kind not in _DIGEST_KINDS:
            return None
        current = self.digest_index.for_target(kind, row["target_id"])
        return staleness_of(row.get("derived_from_hash"), current)

    def component_for_file(self, path: str) -> Optional[str]:
        """The (first, deterministic) component id owning a file path."""
        cids = self.components_of_path.get(path)
        return cids[0] if cids else None
