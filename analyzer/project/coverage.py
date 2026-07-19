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

import math
from typing import Optional

from .inventory import NON_SOURCE_DISPOSITIONS, build_inventory

__all__ = [
    "build_coverage",
    "coverage_families",
    "format_source_percent",
]


def coverage_families(summary: dict) -> dict:
    """Split a disposition->count summary into the three coverage families.

    Mirrors the viewer's ``computeCoverageFamilies`` (CoverageBadge.tsx) exactly
    so the CLI summary line and the badge agree on the same numbers. ``parsed``
    is analyzed source; the known non-source dispositions are non-source;
    everything else that is not ``parsed`` is a source gap (loud), including any
    future excluded rule. The percent denominator is analyzed plus gaps only,
    never the non-source rows.
    """
    analyzed = 0
    gap = 0
    nonsource = 0
    for disposition, count in summary.items():
        if disposition == "parsed":
            analyzed += count
        elif disposition in NON_SOURCE_DISPOSITIONS:
            nonsource += count
        else:
            gap += count
    return {
        "analyzed": analyzed,
        "gap": gap,
        "nonsource": nonsource,
        "source_total": analyzed + gap,
    }


def format_source_percent(fam: dict) -> str:
    """Format the source-analyzed percent exactly as the viewer does.

    Mirrors ``formatSourcePercent`` (CoverageBadge.tsx): no source or no gaps
    reads exactly "100"; with a real gap it shows one decimal and never rounds up
    to a bare "100" while a gap exists, so a single skipped file cannot
    masquerade as full coverage. ``math.floor(x + 0.5)`` reproduces JavaScript
    ``Math.round`` (round half up), not Python's banker's rounding.
    """
    source_total = fam["source_total"]
    gap = fam["gap"]
    if source_total == 0 or gap == 0:
        return "100"
    percent = fam["analyzed"] / source_total * 100
    rounded = math.floor(percent * 10 + 0.5) / 10
    if rounded >= 100:
        rounded = 99.9
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.1f}"


def build_coverage(store, root=None) -> Optional[dict]:
    """Return ``{"summary", "total", "parsed", "rows", "inventory?"}`` from the ledger.

    Returns ``None`` when the store has no coverage rows (for example a
    projection assembled from an arch dict with no backing store), so the
    projection can omit the key entirely and the viewer degrades to its
    pre-ledger behavior. Rows are ordered by path (the store reader sorts), so
    the output is deterministic.

    ``root`` is passed through to the non-source inventory (P6-10), which may
    stat files for their size when the tree is available. The ``inventory`` key
    is additive and versioned: an older dataset without it degrades to exactly
    the pre-inventory coverage panel. It is omitted entirely when there are no
    non-source rows to classify.
    """
    if store is None:
        return None
    summary = store.coverage_summary()
    rows = store.coverage()
    if not rows:
        return None
    total = sum(summary.values())
    coverage = {
        "summary": summary,
        "total": total,
        "parsed": summary.get("parsed", 0),
        "rows": rows,
    }
    inventory = build_inventory(rows, root=root)
    if inventory is not None:
        coverage["inventory"] = inventory
    return coverage


def coverage_manifest_summary(coverage: Optional[dict]) -> Optional[dict]:
    """The lightweight slice that rides in the manifest (no full row list)."""
    if not coverage:
        return None
    return {
        "summary": coverage["summary"],
        "total": coverage["total"],
        "parsed": coverage["parsed"],
    }
