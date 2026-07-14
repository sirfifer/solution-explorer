"""Export bridge: project store enrichment onto an architecture dict (I5).

The store's ``enrichment`` overlay is the canonical source of AI content. This
applies it onto the viewer-compatible architecture dict at projection time:
each component, relationship, and the architecture root gets its ``ai_enhance``
block from the store when a row exists, REPLACING any inline copy (store wins;
see the reversal note below), and a stale row is served WITH a ``stale`` marker
plus the commit it was derived from, never dropped (I5).

Dedupe reversal (recorded decision, P7-1): the P4-5 Discovered note observed
that when both an inline ``ai_enhance`` and a store enrichment row exist for the
same target, the inline copy won because components were processed first. That
order is reversed here and in analyzer/project/search_shards.py: the store
overlay is canonical, so a re-enriched payload takes precedence over any stale
inline copy carried in a baseline architecture dict.
"""

from __future__ import annotations

import copy
from typing import Optional

from .digest import DigestIndex, relationship_target_id
from .staleness import staleness_of

__all__ = ["apply_enrichment_overlay"]


def _mark(payload: dict, stale: Optional[bool], commit_sha: Optional[str]) -> dict:
    """Return a copy of the payload with a staleness marker when stale.

    A fresh row is returned unmarked. A stale row (``stale is True``) gets
    ``stale: True`` and ``derived_from_commit`` (the commit the enrichment was
    derived from, so a consumer can say "accurate as of <commit>"). An unknown
    verdict (``stale is None``, an un-stamped legacy row) is left unmarked.
    """
    out = copy.deepcopy(payload) if isinstance(payload, dict) else payload
    if stale is True and isinstance(out, dict):
        out["stale"] = True
        out["derived_from_commit"] = commit_sha
    return out


def apply_enrichment_overlay(
    arch: dict, store, *, digest_index: Optional[DigestIndex] = None
) -> dict:
    """Overlay store enrichment onto ``arch`` in place; return ``arch``.

    No-op when the store has no enrichment rows, so a non-enriched pipeline (and
    every parity fixture) projects byte-identically to before (backward
    compatible, the ai_enhance optional-key precedent).
    """
    if store is None:
        return arch
    rows = store.enrichment()
    if not rows:
        return arch

    index = digest_index or DigestIndex.from_store(store)

    by_component: dict[str, dict] = {}
    by_relationship: dict[str, dict] = {}
    arch_row: Optional[dict] = None
    for row in rows:
        kind = row["target_kind"]
        if kind == "component":
            by_component[row["target_id"]] = row
        elif kind == "relationship":
            by_relationship[row["target_id"]] = row
        elif kind == "architecture":
            arch_row = row

    def marked_payload(row: dict) -> dict:
        current = index.for_target(row["target_kind"], row["target_id"])
        stale = staleness_of(row.get("derived_from_hash"), current)
        return _mark(row.get("payload") or {}, stale, row.get("commit_sha"))

    # Architecture root.
    if arch_row is not None:
        arch["ai_enhance"] = marked_payload(arch_row)

    # Components (recursive; store wins over any inline ai_enhance).
    def walk(components: list) -> None:
        for comp in components:
            row = by_component.get(comp.get("id"))
            if row is not None:
                comp["ai_enhance"] = marked_payload(row)
            walk(comp.get("children", []))

    walk(arch.get("components", []))

    # Relationships, matched by (source, target, type).
    for rel in arch.get("relationships", []):
        key = relationship_target_id(
            rel.get("source", ""), rel.get("target", ""), rel.get("type", "")
        )
        row = by_relationship.get(key)
        if row is not None:
            rel["ai_enhance"] = marked_payload(row)

    return arch
