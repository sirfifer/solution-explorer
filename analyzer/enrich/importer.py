"""Import bridge: an ai_enhance baseline into provenance-stamped enrichment rows.

This structurally replaces the interim merge script for the one-time migration
of an existing ``ai_enhance``-bearing architecture.json (the committed root
baseline, 23/23 components enhanced) into a v2 store. Each imported target is
resolved against the store by its stable identity and stamped with the store's
CURRENT digest.

Why the current digest, and why an explicit imported flag: an imported record
describes the code as it exists in the store at import time (we are asserting
"this baseline text matches this code now"). Stamping the current digest makes
the import read as FRESH now and go stale only when the code changes after
import, which is the correct behavior; stamping some unknown historical digest
would make every imported row read stale immediately and defeat the migration.
We cannot know which commit produced the baseline text, so ``commit_sha`` is
left None (unknown) and the payload carries an explicit
``_provenance = {"imported": True, ...}`` marker recording that this provenance
was asserted at import, not observed at enhancement time. This is the honest
representation of I5 for migrated data.

Resolution is by exact stable identity (component id, the same scheme in v1 and
v2; relationship (source, target, type)). Provenance makes the drift-tolerant
matcher unnecessary: a target that does not exist in the store is reported as
unmatched, never guessed onto a different target and never silently dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..store import FactStore
from .digest import ARCH_TARGET_ID, DigestIndex, relationship_target_id
from .provenance import Clock, iso_now, stamp_enrichment

__all__ = ["ImportResult", "import_ai_baseline"]

# Reserved payload key carrying import provenance metadata.
PROVENANCE_KEY = "_provenance"


@dataclass
class ImportResult:
    """Counts and unmatched ids from an import run."""

    components_imported: int = 0
    components_unmatched: list[str] = field(default_factory=list)
    relationships_imported: int = 0
    relationships_unmatched: list[str] = field(default_factory=list)
    architecture_imported: bool = False

    @property
    def total_imported(self) -> int:
        return (
            self.components_imported
            + self.relationships_imported
            + (1 if self.architecture_imported else 0)
        )


def _iter_components(components: list):
    for comp in components:
        yield comp
        yield from _iter_components(comp.get("children", []))


def _stamp_imported(
    store: FactStore,
    index: DigestIndex,
    target_kind: str,
    target_id: str,
    ai_enhance: Any,
    *,
    clock: Clock,
) -> bool:
    """Stamp one imported target if it exists in the store. Return True on import."""
    if index.for_target(target_kind, target_id) is None:
        return False
    payload = dict(ai_enhance) if isinstance(ai_enhance, dict) else {"value": ai_enhance}
    payload[PROVENANCE_KEY] = {
        "imported": True,
        "source": "ai_enhance-baseline",
        "commit": "unknown",
    }
    stamp_enrichment(
        store,
        target_kind,
        target_id,
        payload,
        digest_index=index,
        commit_sha=None,
        clock=clock,
    )
    return True


def import_ai_baseline(
    store: FactStore,
    baseline: dict,
    *,
    clock: Clock = iso_now,
    digest_index: Optional[DigestIndex] = None,
) -> ImportResult:
    """Import every ``ai_enhance`` block in ``baseline`` into ``store`` as enrichment.

    ``store`` must already carry the derived components, symbols, and edges for
    the same codebase (digests are computed from its current state). ``baseline``
    is a parsed architecture.json dict. Returns an :class:`ImportResult`.
    """
    index = digest_index or DigestIndex.from_store(store)
    result = ImportResult()

    # Components.
    for comp in _iter_components(baseline.get("components", [])):
        if "ai_enhance" not in comp:
            continue
        cid = comp.get("id", "")
        if _stamp_imported(store, index, "component", cid, comp["ai_enhance"], clock=clock):
            result.components_imported += 1
        else:
            result.components_unmatched.append(cid)

    # Relationships.
    for rel in baseline.get("relationships", []):
        if "ai_enhance" not in rel:
            continue
        key = relationship_target_id(
            rel.get("source", ""), rel.get("target", ""), rel.get("type", "")
        )
        if _stamp_imported(store, index, "relationship", key, rel["ai_enhance"], clock=clock):
            result.relationships_imported += 1
        else:
            result.relationships_unmatched.append(key)

    # Architecture root.
    if "ai_enhance" in baseline:
        result.architecture_imported = _stamp_imported(
            store, index, "architecture", ARCH_TARGET_ID, baseline["ai_enhance"], clock=clock
        )

    store.commit()
    return result
