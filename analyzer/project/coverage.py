"""Coverage-ledger projection (TARGET-ARCHITECTURE.md section 7; invariant I2).

The store's ``coverage`` table is the ledger: every file under the scan root
has exactly one disposition (``parsed``, ``excluded:<rule>``, ``failed``,
``binary``). This module reads it deterministically and shapes it two ways:

  - a **summary** (counts per disposition plus the total) that rides inside the
    manifest, so the viewer's coverage badge (P4-4) reads it without a second
    fetch;
  - the **full ledger** (every row) for the ``coverage.json`` shard and the
    monolithic projection, so the drill-in panel and the ``se_coverage`` MCP
    tool can list exclusions by rule and failures with reasons.

This absorbs P4-4 card item 1 (the projection-side ledger emission); P4-4 adds
the viewer badge and panel on top of what is emitted here.
"""

from __future__ import annotations

from typing import Optional

__all__ = ["build_coverage"]


def build_coverage(store) -> Optional[dict]:
    """Return ``{"summary", "total", "parsed", "rows"}`` from the store ledger.

    Returns ``None`` when the store has no coverage rows (for example a
    projection assembled from an arch dict with no backing store), so the
    projection can omit the key entirely and the viewer degrades to its
    pre-ledger behavior. Rows are ordered by path (the store reader sorts), so
    the output is deterministic.
    """
    if store is None:
        return None
    summary = store.coverage_summary()
    rows = store.coverage()
    if not rows:
        return None
    total = sum(summary.values())
    return {
        "summary": summary,
        "total": total,
        "parsed": summary.get("parsed", 0),
        "rows": rows,
    }


def coverage_manifest_summary(coverage: Optional[dict]) -> Optional[dict]:
    """The lightweight slice that rides in the manifest (no full row list)."""
    if not coverage:
        return None
    return {
        "summary": coverage["summary"],
        "total": coverage["total"],
        "parsed": coverage["parsed"],
    }
