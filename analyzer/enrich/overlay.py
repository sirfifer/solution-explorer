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

# The enrichment target kind P4 synthesis writes tours under. Defined here rather
# than imported from synthesis.py: the overlay is a projection concern and must
# not depend on the phase that happens to produce the rows.
TOUR_TARGET_KIND = "tour"

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
    tour_rows: list[dict] = []
    for row in rows:
        kind = row["target_kind"]
        if kind == "component":
            by_component[row["target_id"]] = row
        elif kind == "relationship":
            by_relationship[row["target_id"]] = row
        elif kind == "architecture":
            arch_row = row
        elif kind == TOUR_TARGET_KIND:
            tour_rows.append(row)

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
                payload = marked_payload(row)
                comp["ai_enhance"] = payload
                # D7: the viewer's tree and detail panel render the top-level
                # component.description (as "docs.purpose || component.description",
                # see viewer/src/components/ComponentNode.tsx and DetailPanel.tsx).
                # The enhance pass emits a one-line "description" inside the payload
                # (help_text stays the long-form). Surface that one-liner as the
                # component description when the mechanical projection left it empty,
                # so an enriched component shows a summary line. Never overwrite an
                # existing mechanical description, and never invent one when the
                # enrichment omitted it (older rows predate the description field and
                # simply stay blank until the next enhance --update).
                ai_desc = payload.get("description")
                if (
                    isinstance(ai_desc, str)
                    and ai_desc.strip()
                    and not (comp.get("description") or "").strip()
                ):
                    comp["description"] = ai_desc.strip()
            walk(comp.get("children", []))

    walk(arch.get("components", []))

    # Tours (P4 synthesis). The viewer's Tour contract is the shape, and the key
    # appears ONLY when tour rows exist, so a store that has never run synthesis
    # projects byte-identically to before. Sorted by id so the projection is
    # stable across runs (I4).
    if tour_rows:
        tours = []
        for row in sorted(tour_rows, key=lambda r: r["target_id"]):
            payload = row.get("payload")
            if not isinstance(payload, dict) or not payload.get("steps"):
                continue
            tour = {
                "id": payload.get("id") or row["target_id"],
                "title": payload.get("title") or "",
                "description": payload.get("description") or "",
                "steps": payload.get("steps") or [],
            }
            # Provenance carries the commit the tour was anchored against, and
            # the stale marker when its anchors have drifted since. A walkthrough
            # is never silently served as current when the code moved under it.
            current = index.for_target(TOUR_TARGET_KIND, row["target_id"])
            stale = staleness_of(row.get("derived_from_hash"), current)
            provenance: dict = {}
            if row.get("commit_sha"):
                provenance["derived_from_commit"] = row["commit_sha"]
            if stale is True:
                provenance["stale"] = True
            if provenance:
                tour["provenance"] = provenance
            tours.append(tour)
        if tours:
            arch["tours"] = tours

    # Relationships, matched by (source, target, type).
    for rel in arch.get("relationships", []):
        key = relationship_target_id(
            rel.get("source", ""), rel.get("target", ""), rel.get("type", "")
        )
        row = by_relationship.get(key)
        if row is not None:
            rel["ai_enhance"] = marked_payload(row)

    return arch
