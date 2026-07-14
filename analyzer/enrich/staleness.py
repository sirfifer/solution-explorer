"""Enrichment staleness, computed at read time (invariant I5).

Staleness is never stored. This module joins the store's enrichment rows against
the current :class:`DigestIndex` and marks each row fresh or stale. Stale rows
are returned with the marker, never dropped, so a consumer (projection, viewer,
MCP) always sees the enrichment plus the fact that the code it describes has
changed.
"""

from __future__ import annotations

from typing import Optional

from ..store import FactStore
from .digest import DigestIndex

__all__ = ["staleness_of", "enrichment_staleness"]


def staleness_of(
    stored_hash: Optional[str], current_digest: Optional[str]
) -> Optional[bool]:
    """The staleness verdict for one row.

    - ``True``  when the current digest differs from the stamped digest, or the
      target no longer exists (its digest is gone): the enrichment describes code
      that has changed or vanished.
    - ``False`` when the digests match: the enrichment is fresh.
    - ``None``  when the row carries no ``derived_from_hash`` (un-stamped legacy
      provenance): staleness is unknown, not asserted either way.
    """
    if stored_hash is None:
        return None
    return current_digest != stored_hash


def enrichment_staleness(
    store: FactStore, digest_index: Optional[DigestIndex] = None
) -> list[dict]:
    """Return every enrichment row joined with its current digest and verdict.

    Each returned row is the store row plus ``current_digest`` (None if the
    target is gone) and ``stale`` (True / False / None per :func:`staleness_of`).
    Rows are in the store's deterministic ``(target_kind, target_id)`` order and
    are NEVER filtered: a stale row is marked, not removed (I5).
    """
    index = digest_index or DigestIndex.from_store(store)
    out: list[dict] = []
    for row in store.enrichment():
        current = index.for_target(row["target_kind"], row["target_id"])
        marked = dict(row)
        marked["current_digest"] = current
        marked["stale"] = staleness_of(row.get("derived_from_hash"), current)
        out.append(marked)
    return out
