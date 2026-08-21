"""Design signals: the deterministic architecture-quality arithmetic.

Tier 1 of ``docs/research/architecture-quality-signals.md``. Derive tier, no AI,
free forever. Everything here is honest arithmetic over facts the store already
holds: component edges, symbol kinds, and git activity. Nothing here asks a
model anything.

The signals, and the forty-year lineage behind each, are catalogued in the
research document. This module computes them:

=========================  =================================================
Signal                     Computation
=========================  =================================================
fan_in (Ca)                Distinct components that depend on this one.
fan_out (Ce)               Distinct components this one depends on.
instability (I)            Ce / (Ca + Ce). High means volatile, easy to
                           change because little leans on it. Low means
                           load-bearing.
abstractness (A)           Abstract type declarations / all type
                           declarations.
distance (D)               |A + I - 1|. Distance from the main sequence, the
                           diagonal where abstractness and stability are in
                           balance.
blast_radius               Count of transitive dependents. If this changes,
                           this many components could break.
churn                      Commits touching the component's files, when the
                           store carries activity facts.
bands                      Quintiles per metric, q1 lowest through q5
                           highest.
=========================  =================================================

**Storage: the store's meta table, key** ``design_signals``, as one JSON
document, following the :mod:`analyzer.derive.importance` precedent from T2.
Chosen for the same reasons: the signals are read as a whole, never joined
against, and the document is a record of what a run computed rather than a
cache. :func:`derive_design_signals` recomputes from current store state every
time, because ``derive_all`` rebuilds components and edges without clearing
meta, so a trusted blob could outlive the facts it was computed from.

**Why the existing ``findings`` table is not reused.** The store already has a
``findings`` table (schema v4, correlations: duplication, orphan,
inconsistency). It is deliberately not reused here, for one structural reason:
its ``rank_score REAL NOT NULL`` column exists to rank findings against each
other across kinds, and design findings decline to do that. Part 4 of the
research document rules out a single architecture score and any cross-kind
severity ranking, so design findings carry ``rank_within_kind`` only. Borrowing
a table whose primary index is a cross-kind rank would smuggle the claim back
in through the schema.

**What this analysis cannot see.** Every surface that renders these signals
carries :data:`METHOD_CAVEAT` verbatim. Static edges are not runtime truth.

**Three deliberate departures from the naive arithmetic**, all in service of
not claiming more than the facts support:

1. *Undefined is null, not zero.* A component with no type declarations has no
   abstractness, and a component with no edges at all has no instability.
   Reporting 0.0 in those cases would be a fabrication with consequences: A=0
   plus I=0 computes to D=1, the worst possible distance, which would file a
   pure-functions module or an isolated component into the zone of pain on the
   strength of a number nobody measured. So they are ``None``, and every
   finding that needs them skips components that lack them.
2. *Abstractness is measured only in languages that can express it.* See
   :data:`ABSTRACTION_CAPABLE_LANGUAGES`. This one is load-bearing, and it is
   the largest correction this module makes to the research document's
   assumptions.
3. *Bands are value-based, not position-based.* This differs from
   ``importance.py``, on purpose. That module ranks a continuous score where
   ties are rare, so it cuts quintiles by rank position. These metrics are
   small integers where ties are the common case: on most repositories a
   majority of components share ``fan_in == 0``. Cutting by position would
   scatter identical values across different bands on a tiebreak, and the band
   is a user-visible claim. Here a band is computed from the count of
   components scoring strictly lower, so equal values always land in equal
   bands.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = [
    "ComponentDesign",
    "DesignFinding",
    "DesignSignals",
    "derive_design_signals",
    "store_design_signals",
    "load_design_signals",
    "boundary_strength_for",
    "strongly_connected_components",
    "pair_key",
    "split_pair_key",
    "META_KEY",
    "METHOD_CAVEAT",
    "METHOD_STATIC_GRAPH",
    "METHOD_GIT_HISTORY",
    "METHOD_STATIC_AND_HISTORY",
    "FINDING_KINDS",
    "TERMS",
    "ABSTRACT_TYPE_KINDS",
    "ABSTRACTION_CAPABLE_LANGUAGES",
    "TYPE_DECLARATION_KINDS",
    "BOUNDARY_STRENGTH",
    "BOUNDARY_ORDER",
    "BAND_COUNT",
    "MAX_FINDINGS_PER_KIND",
    "MIN_COCHANGE_SUPPORT",
]

META_KEY = "design_signals"

# The uniform Tier 1 caveat, quoted verbatim from
# docs/research/architecture-quality-signals.md Part 2. It is part of the
# projected payload, not something a rendering surface invents, so that the
# viewer, ai.json, and the MCP tools cannot drift into three different
# statements of what the method cannot see.
METHOD_CAVEAT = (
    "static import and declared communication edges only; runtime reflection, "
    "dependency injection wiring, and dynamic dispatch are invisible to this analysis"
)

# Abstractness numerator. These are the symbol kinds the extractors actually
# emit for a declaration that cannot be instantiated and exists to be
# implemented by something else.
#
# NOTE, and this is a real limit worth stating: abstract CLASSES are not in
# this set because no extractor distinguishes them. Verified by probing every
# parser: TypeScript's ``abstract_class_declaration`` is normalized to
# ``class`` (analyzer/parsers/typescript_ts.py), Java's ``abstract class`` is
# ``class``, a C++ pure-virtual class is ``class``, and Python's ABCs and
# ``typing.Protocol`` subclasses are plain ``class`` with no marker. The
# research document assumed abstract classes were distinguishable. They are
# not. Teaching the extractors to mark them is a named follow-on.
ABSTRACT_TYPE_KINDS = frozenset({"protocol", "interface", "trait"})

# Languages whose extractor can emit an abstract type kind at all. Verified
# empirically by running the extractors over a probe file per language and
# recording which kinds came back; ``tests/test_design_signals.py`` re-runs
# that probe and fails if this constant and the parsers disagree, so teaching a
# parser a new abstract kind cannot silently leave this list stale.
#
# WHY THIS GATE EXISTS, and it is the most consequential decision in the
# module. Python emits only ``class`` and ``function``: an ABC, a
# ``typing.Protocol``, and a plain data holder are indistinguishable. Without
# this gate, every Python component would compute A = 0.0. Since D = |A + I -
# 1|, a load-bearing Python component (low I, which is exactly what a good core
# module looks like) would compute D near 1.0 and be reported in the zone of
# pain. That is a false accusation, generated confidently, about the single
# most important component in the system, on every Python codebase, including
# both golden corpora. It is precisely the "quietly, credibly wrong" failure
# the Comprehension Review exposed.
#
# So abstractness is measured only over files whose language can express
# abstraction. A component with no such files reports ``abstractness: null``,
# which propagates to ``distance_main_sequence: null``, which makes it
# ineligible for zone-of-pain and zone-of-uselessness findings. Cycles,
# stability inversions, blast radius, boundary strength and change coupling do
# not depend on abstractness and are unaffected. The honest consequence is that
# Python, C++, Ruby and JavaScript subjects get a Design lens without the
# scatter plot and without zone findings, which is the correct amount to say
# given what the extractors can see.
ABSTRACTION_CAPABLE_LANGUAGES = frozenset(
    {"csharp", "go", "java", "rust", "swift", "typescript"}
)

# Abstractness denominator: named type declarations. Deliberately NOT every
# symbol. Martin's A is abstract classes over total classes, so functions,
# methods, properties and constants do not belong in the ratio: a module of 200
# free functions is not thereby 0% abstract, it simply declares no types.
# ``extension`` and ``impl`` are excluded because they add to a type declared
# elsewhere rather than declaring one, and counting them would let a language
# that spreads a type across many impl blocks (Rust, Swift) dilute its own
# abstractness. ``type`` (a type alias) is excluded because an alias renames a
# structure rather than declaring one.
TYPE_DECLARATION_KINDS = frozenset(
    {"class", "struct", "enum", "protocol", "interface", "trait", "actor"}
)

# How many bands each metric is cut into. Quintiles, matching the importance
# ranking's vocabulary so the two are read the same way.
BAND_COUNT = 5

# Boundary strength, Clean Architecture's boundary anatomy (research document
# Part 1.4) mapped onto the relationship vocabulary in analyzer/models.py.
# Each step up buys isolation and costs latency and operational complexity.
#
# The split into structural and communication already exists in the viewer
# (``getEdgeCategory``, viewer/src/utils/layout.ts). This refines that binary
# into the four-level spectrum without contradicting it: everything the viewer
# calls communication is service or process here, and everything it calls
# structural is source or deployment.
BOUNDARY_STRENGTH = {
    # Source-level: separated by convention only. Nothing but discipline stops
    # one side reaching into the other, and a rename breaks the caller.
    "import": "source",
    "uses": "source",
    "companion": "source",
    "navigation": "source",
    "tab": "source",
    "modal": "source",
    "embed": "source",
    # Deployment: separately built artifacts. A version boundary exists.
    "ffi": "deployment",
    "docker": "deployment",
    # Process: separate processes sharing a medium rather than a call stack.
    "file": "process",
    # Service: a network contract. The strongest isolation on offer, and the
    # most expensive.
    "http": "service",
    "websocket": "service",
    "grpc": "service",
    "database": "service",
    "message_queue": "service",
    "pubsub": "service",
    "event_bus": "service",
    "cache": "service",
}

# Ordered weakest to strongest, so a pair of components joined by several edges
# can be summarized by its strongest separation.
BOUNDARY_ORDER = ("source", "deployment", "process", "service")

# An unrecognized relationship type is treated as a source-level boundary: the
# weakest claim available, which is the honest default when the vocabulary has
# grown a term this module has not been taught.
DEFAULT_BOUNDARY_STRENGTH = "source"


@dataclass
class ComponentDesign:
    """One component's design metrics.

    ``instability``, ``abstractness`` and ``distance_main_sequence`` are
    ``None`` when the facts do not define them. See the module docstring.
    """

    component_id: str
    fan_in: int = 0
    fan_out: int = 0
    instability: Optional[float] = None
    abstractness: Optional[float] = None
    distance_main_sequence: Optional[float] = None
    blast_radius: int = 0
    churn: int = 0
    type_symbols: int = 0
    abstract_symbols: int = 0
    bands: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        out: dict[str, Any] = {
            "fan_in": self.fan_in,
            "fan_out": self.fan_out,
            "instability": _round(self.instability),
            "abstractness": _round(self.abstractness),
            "distance_main_sequence": _round(self.distance_main_sequence),
            "blast_radius": self.blast_radius,
            "bands": dict(self.bands),
        }
        return out

    def to_record(self) -> dict:
        """The fuller shape the store keeps, including the ratio's inputs."""
        record = self.to_dict()
        record["component_id"] = self.component_id
        record["churn"] = self.churn
        record["type_symbols"] = self.type_symbols
        record["abstract_symbols"] = self.abstract_symbols
        return record

    @classmethod
    def from_record(cls, data: dict) -> ComponentDesign:
        return cls(
            component_id=str(data.get("component_id", "")),
            fan_in=_int(data.get("fan_in")),
            fan_out=_int(data.get("fan_out")),
            instability=_opt_float(data.get("instability")),
            abstractness=_opt_float(data.get("abstractness")),
            distance_main_sequence=_opt_float(data.get("distance_main_sequence")),
            blast_radius=_int(data.get("blast_radius")),
            churn=_int(data.get("churn")),
            type_symbols=_int(data.get("type_symbols")),
            abstract_symbols=_int(data.get("abstract_symbols")),
            bands=dict(data.get("bands") or {}),
        )


@dataclass
class DesignSignals:
    """Every component's design metrics, plus what the whole computation knew."""

    items: list[ComponentDesign] = field(default_factory=list)
    has_activity: bool = False
    # Pair key "source\ttarget" to boundary strength, weakest-to-strongest
    # resolved. Kept beside the metrics because D2's findings and the
    # projection both read it.
    boundaries: dict[str, str] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    @property
    def by_id(self) -> dict[str, ComponentDesign]:
        return {item.component_id: item for item in self.items}

    def get(self, component_id: str) -> Optional[ComponentDesign]:
        return self.by_id.get(component_id)

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "method_caveat": METHOD_CAVEAT,
            "has_activity": self.has_activity,
            "band_count": BAND_COUNT,
            "items": [item.to_record() for item in self.items],
            "boundaries": dict(self.boundaries),
        }

    @classmethod
    def from_dict(cls, data: dict) -> DesignSignals:
        return cls(
            items=[ComponentDesign.from_record(d) for d in data.get("items") or []],
            has_activity=bool(data.get("has_activity")),
            boundaries=dict(data.get("boundaries") or {}),
        )


# --- small helpers ------------------------------------------------------------


def _round(value: Optional[float]) -> Optional[float]:
    """Round a ratio for storage, preserving None as None."""
    return None if value is None else round(value, 6)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pair_key(source: str, target: str) -> str:
    """The stable key a directed component pair is stored under."""
    return f"{source}\t{target}"


def split_pair_key(key: str) -> tuple[str, str]:
    source, _, target = key.partition("\t")
    return source, target


def boundary_strength_for(edge_type: Optional[str]) -> str:
    """Classify one relationship type onto the boundary-anatomy spectrum."""
    return BOUNDARY_STRENGTH.get((edge_type or "").strip().lower(), DEFAULT_BOUNDARY_STRENGTH)


def _strongest(a: str, b: str) -> str:
    """The stronger of two boundary classifications."""
    return a if BOUNDARY_ORDER.index(a) >= BOUNDARY_ORDER.index(b) else b


def _bands_for(values: dict[str, int]) -> dict[str, str]:
    """Cut a metric into quintiles so that equal values get equal bands.

    The band of a value is decided by how many components score strictly lower
    than it. That makes the cut a function of the value alone, so two
    components with the same fan-in can never be reported in different bands,
    which a position-based cut would do on a tiebreak.
    """
    if not values:
        return {}
    ordered = sorted(values.values())
    total = len(ordered)
    # For each distinct value, how many entries are strictly below it.
    strictly_below: dict[int, int] = {}
    for index, value in enumerate(ordered):
        if value not in strictly_below:
            strictly_below[value] = index
    out: dict[str, str] = {}
    for component_id, value in values.items():
        band = (strictly_below[value] * BAND_COUNT) // total + 1
        out[component_id] = f"q{min(BAND_COUNT, band)}"
    return out


def _transitive_dependents(
    component_ids: list[str], inbound: dict[str, set[str]]
) -> dict[str, int]:
    """Count, per component, how many components transitively depend on it.

    Breadth-first over reversed dependency edges from every node. The graph may
    contain cycles, so the walk is a visited-set traversal rather than a
    memoized DAG recursion; a component is never counted as its own dependent
    even when it sits inside a cycle that reaches back to it.

    Cost is O(V * E) worst case. Component graphs are small (tens to low
    hundreds of nodes on real subjects, against thousands of files), so this
    stays negligible, and the simple version is the one that stays obviously
    correct in the presence of cycles.
    """
    counts: dict[str, int] = {}
    for component_id in component_ids:
        seen: set[str] = set()
        frontier = [component_id]
        while frontier:
            current = frontier.pop()
            for dependent in inbound.get(current, ()):  # who depends on current
                if dependent not in seen and dependent != component_id:
                    seen.add(dependent)
                    frontier.append(dependent)
        counts[component_id] = len(seen)
    return counts


# --- the derivation -----------------------------------------------------------


def derive_design_signals(store) -> DesignSignals:
    """Compute every component's design metrics from current store state.

    Pure read, deterministic, and stable under re-run: iteration is over sorted
    store readers, sets are collapsed by counting rather than by order, and
    band cuts are a function of value alone.
    """
    components = store.components()
    if not components:
        return DesignSignals(items=[], has_activity=False, boundaries={})

    known_ids = {comp["id"] for comp in components}

    # Fan-in and fan-out over DISTINCT partner components, matching
    # importance.py: two edges between the same pair (an import and a call) are
    # one dependency, not two. Boundary strength is resolved per pair to the
    # strongest separation those edges provide, because a pair joined by both
    # an import and an HTTP call is separated by a network contract for the
    # HTTP traffic but only by convention for the import; the summary claim
    # that survives is the strongest one actually present.
    inbound: dict[str, set[str]] = {cid: set() for cid in known_ids}
    outbound: dict[str, set[str]] = {cid: set() for cid in known_ids}
    boundaries: dict[str, str] = {}
    for edge in store.edges():
        source = edge.get("source_id")
        target = edge.get("target_id")
        if source == target:
            continue
        if source not in known_ids or target not in known_ids:
            continue
        inbound[target].add(source)
        outbound[source].add(target)
        key = pair_key(source, target)
        strength = boundary_strength_for(edge.get("type"))
        boundaries[key] = _strongest(boundaries[key], strength) if key in boundaries else strength

    # Files per component, so symbol kinds and churn can be attributed.
    files_by_component: dict[str, list[str]] = {cid: [] for cid in known_ids}
    for row in store.component_files():
        cid = row.get("component_id")
        if cid in files_by_component:
            files_by_component[cid].append(row.get("path") or "")

    # Symbol kinds per file path, counted only in files whose language can
    # express abstraction. A file in a language the extractor cannot read
    # abstraction out of contributes to NEITHER the numerator nor the
    # denominator, so it lowers no ratio; it simply is not evidence either way.
    path_by_file_id: dict[Any, str] = {}
    for row in store.files():
        language = (row.get("language") or "").strip().lower()
        if language in ABSTRACTION_CAPABLE_LANGUAGES:
            path_by_file_id[row.get("id")] = row.get("path") or ""
    type_counts: dict[str, int] = {}
    abstract_counts: dict[str, int] = {}
    for symbol in store.symbols():
        kind = (symbol.get("kind") or "").strip().lower()
        if kind not in TYPE_DECLARATION_KINDS:
            continue
        path = path_by_file_id.get(symbol.get("file_id"))
        if not path:
            continue
        type_counts[path] = type_counts.get(path, 0) + 1
        if kind in ABSTRACT_TYPE_KINDS:
            abstract_counts[path] = abstract_counts.get(path, 0) + 1

    commits_by_path: dict[str, int] = {}
    has_activity = False
    for row in store.file_activity():
        has_activity = True
        try:
            commits_by_path[row.get("path") or ""] = int(row.get("commit_count") or 0)
        except (TypeError, ValueError):
            continue

    ordered_ids = sorted(known_ids)
    blast = _transitive_dependents(ordered_ids, inbound)

    items: list[ComponentDesign] = []
    for comp in components:
        cid = comp["id"]
        paths = sorted(files_by_component.get(cid, []))
        fan_in = len(inbound.get(cid, ()))
        fan_out = len(outbound.get(cid, ()))

        # Instability I = Ce / (Ca + Ce). Undefined for an isolated component:
        # nothing depends on it and it depends on nothing, so there is no
        # stability question to answer about it.
        total_coupling = fan_in + fan_out
        instability = (fan_out / total_coupling) if total_coupling else None

        # Abstractness A = abstract type declarations / all type declarations,
        # over abstraction-capable files only. Undefined when the component has
        # no such declarations: either it declares no types, or it is written
        # in a language whose abstraction this analysis cannot see.
        type_symbols = sum(type_counts.get(path, 0) for path in paths)
        abstract_symbols = sum(abstract_counts.get(path, 0) for path in paths)
        abstractness = (abstract_symbols / type_symbols) if type_symbols else None

        # Distance from the main sequence D = |A + I - 1|. Needs both, so it is
        # undefined whenever either input is.
        if instability is None or abstractness is None:
            distance = None
        else:
            distance = abs(abstractness + instability - 1.0)

        items.append(
            ComponentDesign(
                component_id=cid,
                fan_in=fan_in,
                fan_out=fan_out,
                instability=instability,
                abstractness=abstractness,
                distance_main_sequence=distance,
                blast_radius=blast.get(cid, 0),
                churn=sum(commits_by_path.get(path, 0) for path in paths),
                type_symbols=type_symbols,
                abstract_symbols=abstract_symbols,
            )
        )

    items.sort(key=lambda item: item.component_id)

    fan_in_bands = _bands_for({item.component_id: item.fan_in for item in items})
    fan_out_bands = _bands_for({item.component_id: item.fan_out for item in items})
    blast_bands = _bands_for({item.component_id: item.blast_radius for item in items})
    churn_bands = (
        _bands_for({item.component_id: item.churn for item in items}) if has_activity else {}
    )
    for item in items:
        bands = {
            "fan_in": fan_in_bands[item.component_id],
            "fan_out": fan_out_bands[item.component_id],
            "blast_radius": blast_bands[item.component_id],
        }
        # The churn band exists only when the store carries activity facts. An
        # absent key is the honest reading of "this repository's history was
        # not analyzed", and it is what stops a churn-dependent finding from
        # being made on a store that cannot support it.
        if churn_bands:
            bands["churn"] = churn_bands[item.component_id]
        item.bands = bands

    return DesignSignals(items=items, has_activity=has_activity, boundaries=boundaries)


def store_design_signals(store, signals: DesignSignals) -> None:
    """Persist design signals into the store's meta table as one JSON document."""
    store.set_meta(META_KEY, json.dumps(signals.to_dict(), sort_keys=True))


def load_design_signals(store) -> Optional[DesignSignals]:
    """Read previously persisted design signals, or None when the store has none.

    Callers that need signals for a run should call
    :func:`derive_design_signals` instead: this is for inspecting what a past
    run recorded, and a stored document can be older than the components it
    names.
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
    return DesignSignals.from_dict(data)
