"""Projection overlay for AI verdicts (P7-3).

The deterministic tiers (extract/derive) produce edges with a confidence tier.
The Phase 7 edge-verification pass (P7-3) produces, as a provenance-stamped
enrichment row, a ``{confirmed, refuted, uncertain}`` verdict per inferred edge:

    edge-verdict   keyed by ``source|target|type``, payload ``{status, reason}``.

This module applies those rows onto the projected architecture dict at projection
time, the same shape and no-op-when-empty discipline as
``overlay.apply_enrichment_overlay``. It runs AFTER that overlay so it can read
enriched component help text if needed. Staleness is computed at read time from
the digest index and travels with each verdict (I5); a REFUTED edge is MARKED and
de-emphasized, never deleted (the Phase 7 gate line; LENS-DESIGN I15).

P7-4 extends this module with concern names and finding verdicts.
"""

from __future__ import annotations

from typing import Optional

from .digest import DigestIndex
from .staleness import staleness_of

__all__ = ["apply_verdict_overlay"]

_VERDICT_KINDS = frozenset({"edge-verdict"})


def _stale_marker(
    verdict: dict, stale: Optional[bool], commit_sha: Optional[str]
) -> dict:
    """Attach a staleness marker to a verdict dict when the row is stale."""
    if stale is True:
        verdict["stale"] = True
        verdict["derived_from_commit"] = commit_sha
    return verdict


def apply_verdict_overlay(
    arch: dict, store, *, digest_index: Optional[DigestIndex] = None
) -> dict:
    """Overlay edge verdicts onto ``arch``.

    In place; returns ``arch``. A complete no-op when the store carries no
    verdict enrichment kinds, so a non-verified projection (and every parity
    fixture) is byte-identical to before.
    """
    if store is None:
        return arch
    rows = [r for r in store.enrichment() if r["target_kind"] in _VERDICT_KINDS]
    if not rows:
        return arch

    index = digest_index or DigestIndex.from_store(store)

    edge_verdicts: dict[str, dict] = {}
    for row in rows:
        if row["target_kind"] == "edge-verdict":
            edge_verdicts[row["target_id"]] = row

    def staleness(row: dict) -> Optional[bool]:
        current = index.for_target(row["target_kind"], row["target_id"])
        return staleness_of(row.get("derived_from_hash"), current)

    # --- edge verdicts (P7-3) ------------------------------------------------
    for rel in arch.get("relationships", []):
        key = "{}|{}|{}".format(
            rel.get("source", ""), rel.get("target", ""), rel.get("type", "")
        )
        row = edge_verdicts.get(key)
        if row is None:
            continue
        payload = row.get("payload") or {}
        verdict = {
            "status": payload.get("status"),
            "reason": payload.get("reason"),
        }
        _stale_marker(verdict, staleness(row), row.get("commit_sha"))
        rel["verdict"] = verdict
        # Refuted edges are marked and de-emphasized, NEVER deleted (gate line).
        if payload.get("status") == "refuted":
            rel["de_emphasized"] = True

    return arch
