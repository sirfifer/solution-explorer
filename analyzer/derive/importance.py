"""Navigation-importance ranking: which components a reader should meet first.

P0 of the Enrichment Engine (``docs/publication/ENRICHMENT-ENGINE.md`` section 3).
Deterministic, derive tier, no AI. It is the effort-weighting input for every
phase above it: the ladder spends its attention in importance order, and P3
samples its grounding spot-checks weighted the same way.

``analyzer/project/frontdoor.py`` already advertises this recipe to machine
readers ("to rank components by importance use activity.json hotspots and/or
each component's ai_enhance.criticality when enriched, plus relationship
fan-in"), and nothing computed it. This does.

**Why criticality is deliberately not an input.** The front door offers
``ai_enhance.criticality`` as one ranking signal. This ranking cannot use it.
Criticality is enrichment output, and this ranking is an input to enrichment;
feeding one into the other would make the ladder's effort weighting a function of
what the ladder already wrote. The four signals below are all mechanical facts
about the repository, available before any model runs.

**The four signals**, each normalized to [0, 1] and combined with fixed weights:

===============  ======  ==================================================
Signal           Weight  What it means
===============  ======  ==================================================
fan_in           0.35    How many distinct components depend on this one.
                         The strongest "the system needs this" signal, and
                         the one a reader most needs oriented early.
activity         0.30    Commits touching this component's files across the
                         full history. The strongest "humans keep coming
                         back to this" signal.
entry            0.20    Whether a reader plausibly enters here: a listening
                         port, a conventional entry file, or a graph root.
size             0.15    Lines of code. Weakest deliberately: big is not the
                         same as important, but tiny is rarely the heart of
                         a system.
===============  ======  ==================================================

Counts are heavy-tailed (one component with 4,000 commits and a long tail of
components with three), so the count signals are damped with ``log1p(x) /
log1p(max)`` rather than divided by the max. Without damping a single outlier
flattens every other component to near zero and the ranking degenerates into
"the one hotspot, then noise".

**Bands are quintiles by rank position, not by score value.** Band 1 is the most
important fifth, band 5 the least. Rank position is used because score values
cluster: on a repository where most components are quiet, a value-based cut would
put 90% of components in the bottom band and tell the ladder nothing about how to
spend effort inside that 90%.

**Storage: the store's meta table, key** ``navigation_importance``, as one JSON
document. Chosen over a new table because the ranking is read as a whole (the
pipeline weights all targets at once) and never joined against. It is written as
a record of what a run used, never as a cache: :func:`rank_components` recomputes
from current store state every time, because ``derive_all`` rebuilds components
and edges without clearing meta, so a trusted blob could outlive the facts it
was computed from.

**Not in the projection.** The ranking is store-internal in this build. Surfacing
it in the viewer or the projection would move golden baselines and is explicitly
out of scope (``ENRICHMENT-ENGINE-BUILD.md`` section 3).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = [
    "ComponentImportance",
    "ImportanceRanking",
    "rank_components",
    "store_ranking",
    "load_ranking",
    "META_KEY",
    "WEIGHTS",
    "ENTRY_FILENAMES",
]

META_KEY = "navigation_importance"

WEIGHTS = {
    "fan_in": 0.35,
    "activity": 0.30,
    "entry": 0.20,
    "size": 0.15,
}

# Conventional entry filenames across the languages the analyzer parses. A
# component owning one of these is somewhere a reader plausibly starts reading.
ENTRY_FILENAMES = {
    "main.py", "__main__.py", "app.py", "cli.py", "manage.py", "wsgi.py", "asgi.py",
    "index.js", "index.ts", "index.tsx", "index.jsx",
    "main.js", "main.ts", "main.tsx", "server.js", "server.ts", "app.ts", "app.js",
    "main.go", "main.rs", "main.swift", "main.dart",
    "program.cs", "startup.cs",
    "application.java", "main.java",
    "config.ru", "application.rb",
}

# How many bands the ranking is cut into. Quintiles, per the design.
BAND_COUNT = 5


@dataclass
class ComponentImportance:
    """One component's navigation-importance record."""

    component_id: str
    score: float
    band: int
    fan_in: int = 0
    fan_out: int = 0
    commits: int = 0
    lines: int = 0
    entry_reasons: list[str] = field(default_factory=list)

    @property
    def is_entry_point(self) -> bool:
        return bool(self.entry_reasons)

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "score": round(self.score, 6),
            "band": self.band,
            "fan_in": self.fan_in,
            "fan_out": self.fan_out,
            "commits": self.commits,
            "lines": self.lines,
            "entry_reasons": list(self.entry_reasons),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ComponentImportance:
        return cls(
            component_id=str(data.get("component_id", "")),
            score=float(data.get("score", 0.0) or 0.0),
            band=int(data.get("band", BAND_COUNT) or BAND_COUNT),
            fan_in=int(data.get("fan_in", 0) or 0),
            fan_out=int(data.get("fan_out", 0) or 0),
            commits=int(data.get("commits", 0) or 0),
            lines=int(data.get("lines", 0) or 0),
            entry_reasons=list(data.get("entry_reasons") or []),
        )


@dataclass
class ImportanceRanking:
    """The whole ranking: every component, ordered most important first."""

    items: list[ComponentImportance] = field(default_factory=list)
    has_activity: bool = False

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    @property
    def by_id(self) -> dict[str, ComponentImportance]:
        return {item.component_id: item for item in self.items}

    def score_for(self, component_id: str) -> float:
        item = self.by_id.get(component_id)
        return item.score if item is not None else 0.0

    def band_for(self, component_id: str) -> int:
        """The band a component sits in; an unranked id reads as the lowest band."""
        item = self.by_id.get(component_id)
        return item.band if item is not None else BAND_COUNT

    def ordered_ids(self) -> list[str]:
        return [item.component_id for item in self.items]

    def top(self, n: int) -> list[ComponentImportance]:
        return self.items[: max(0, n)]

    def band_counts(self) -> dict[int, int]:
        counts: dict[int, int] = {band: 0 for band in range(1, BAND_COUNT + 1)}
        for item in self.items:
            counts[item.band] = counts.get(item.band, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "weights": dict(WEIGHTS),
            "has_activity": self.has_activity,
            "band_count": BAND_COUNT,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict) -> ImportanceRanking:
        return cls(
            items=[ComponentImportance.from_dict(d) for d in data.get("items") or []],
            has_activity=bool(data.get("has_activity")),
        )


def _damped(value: float, maximum: float) -> float:
    """Log-damped normalization of a heavy-tailed count into [0, 1]."""
    if maximum <= 0:
        return 0.0
    return math.log1p(max(0.0, value)) / math.log1p(maximum)


def _component_lines(meta: Any) -> int:
    """Lines of code for a component, from its stored metrics block."""
    if not isinstance(meta, dict):
        return 0
    metrics = meta.get("metrics")
    if not isinstance(metrics, dict):
        return 0
    try:
        return int(metrics.get("lines") or 0)
    except (TypeError, ValueError):
        return 0


def _has_port(meta: Any) -> bool:
    if not isinstance(meta, dict):
        return False
    port = meta.get("port")
    return port is not None and str(port).strip() not in ("", "None")


def _entry_reasons(
    *,
    meta: Any,
    file_paths: list[str],
    fan_in: int,
    fan_out: int,
) -> list[str]:
    """Why a reader might enter the system here, from mechanical facts only.

    Three independent reasons, any of which counts, all of which are recorded so
    the Run Report can say why a component was weighted up rather than only that
    it was.
    """
    reasons: list[str] = []
    if _has_port(meta):
        reasons.append("listens on a port")
    named = sorted(
        {
            path.rsplit("/", 1)[-1]
            for path in file_paths
            if path.rsplit("/", 1)[-1].lower() in ENTRY_FILENAMES
        }
    )
    if named:
        reasons.append("owns a conventional entry file: " + ", ".join(named))
    if fan_in == 0 and fan_out > 0:
        # Nothing depends on it and it depends on things: a root of the
        # dependency graph, which is where reading naturally starts.
        reasons.append("dependency-graph root (no inbound edges, has outbound)")
    return reasons


def rank_components(store) -> ImportanceRanking:
    """Compute the navigation-importance ranking from current store state.

    Pure read of the store, deterministic, and stable under re-run: iteration is
    over sorted store readers and ties break on component id, so the same store
    always produces the same ordering and the same bands.
    """
    components = store.components()
    if not components:
        return ImportanceRanking(items=[], has_activity=False)

    known_ids = {comp["id"] for comp in components}

    # Fan-in and fan-out, counted over DISTINCT partner components. Two edges
    # between the same pair (say an import and a call) are one dependency, not
    # two, and counting them twice would let a chatty pair outrank a component
    # that genuinely many things depend on.
    inbound: dict[str, set[str]] = {cid: set() for cid in known_ids}
    outbound: dict[str, set[str]] = {cid: set() for cid in known_ids}
    for edge in store.edges():
        source = edge.get("source_id")
        target = edge.get("target_id")
        if source == target:
            continue
        if target in inbound and source is not None:
            inbound[target].add(source)
        if source in outbound and target is not None:
            outbound[source].add(target)

    # Files per component, and commits per file from the full-history activity
    # lens. A store with no activity rows (activity is optional) simply scores
    # zero on that signal for every component, which leaves the other three
    # deciding the order rather than flattening the ranking.
    files_by_component: dict[str, list[str]] = {cid: [] for cid in known_ids}
    for row in store.component_files():
        cid = row.get("component_id")
        if cid in files_by_component:
            files_by_component[cid].append(row.get("path") or "")

    commits_by_path: dict[str, int] = {}
    has_activity = False
    for row in store.file_activity():
        has_activity = True
        try:
            commits_by_path[row.get("path") or ""] = int(row.get("commit_count") or 0)
        except (TypeError, ValueError):
            continue

    raw: list[dict] = []
    for comp in components:
        cid = comp["id"]
        paths = sorted(files_by_component.get(cid, []))
        fan_in = len(inbound.get(cid, ()))
        fan_out = len(outbound.get(cid, ()))
        commits = sum(commits_by_path.get(path, 0) for path in paths)
        lines = _component_lines(comp.get("meta"))
        raw.append(
            {
                "component_id": cid,
                "fan_in": fan_in,
                "fan_out": fan_out,
                "commits": commits,
                "lines": lines,
                "entry_reasons": _entry_reasons(
                    meta=comp.get("meta"),
                    file_paths=paths,
                    fan_in=fan_in,
                    fan_out=fan_out,
                ),
            }
        )

    max_fan_in = max((r["fan_in"] for r in raw), default=0)
    max_commits = max((r["commits"] for r in raw), default=0)
    max_lines = max((r["lines"] for r in raw), default=0)

    items: list[ComponentImportance] = []
    for r in raw:
        score = (
            WEIGHTS["fan_in"] * _damped(r["fan_in"], max_fan_in)
            + WEIGHTS["activity"] * _damped(r["commits"], max_commits)
            + WEIGHTS["entry"] * (1.0 if r["entry_reasons"] else 0.0)
            + WEIGHTS["size"] * _damped(r["lines"], max_lines)
        )
        items.append(
            ComponentImportance(
                component_id=r["component_id"],
                score=score,
                band=BAND_COUNT,
                fan_in=r["fan_in"],
                fan_out=r["fan_out"],
                commits=r["commits"],
                lines=r["lines"],
                entry_reasons=r["entry_reasons"],
            )
        )

    # Highest score first; ties break on component id so the order is total and
    # therefore stable across runs.
    items.sort(key=lambda item: (-item.score, item.component_id))

    # Quintiles by rank position. Integer arithmetic only, so band edges are
    # reproducible and do not drift with floating point.
    total = len(items)
    for position, item in enumerate(items):
        band = (position * BAND_COUNT) // total + 1
        item.band = min(BAND_COUNT, band)

    return ImportanceRanking(items=items, has_activity=has_activity)


def store_ranking(store, ranking: ImportanceRanking) -> None:
    """Persist a ranking into the store's meta table as one JSON document."""
    store.set_meta(META_KEY, json.dumps(ranking.to_dict(), sort_keys=True))


def load_ranking(store) -> Optional[ImportanceRanking]:
    """Read a previously persisted ranking, or None when the store has none.

    Callers that need a ranking for a run should call :func:`rank_components`
    instead: this is for inspecting what a past run recorded, and a stored
    document can be older than the components it names.
    """
    raw = store.get_meta(META_KEY)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return ImportanceRanking.from_dict(data)
