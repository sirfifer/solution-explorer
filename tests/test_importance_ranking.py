"""T2: the navigation-importance ranking. Deterministic, no AI, not projected.

Contracts under test:

  1. THE SIGNALS DO WHAT THEY CLAIM. Fan-in, activity, entry-point and size each
     move the score in isolation, so a weight is not decorative.
  2. DETERMINISTIC AND STABLE. The same store ranks identically every time, ties
     included, because the ordering is total.
  3. BANDS ARE QUINTILES BY POSITION. Not by score value, so a repository whose
     scores cluster still gets a usable spread for effort weighting.
  4. HEAVY TAILS ARE DAMPED. One enormous outlier does not flatten everything
     below it into an undifferentiated floor. Fail-before contrast: plain
     max-normalization would.
  5. IT IS NOT IN THE PROJECTION. Ranking a real store leaves the projected
     architecture byte-identical, which is what keeps both golden corpora still.
"""

from __future__ import annotations

import copy
import json
import os

from analyzer.derive import derive_all
from analyzer.derive.importance import (
    BAND_COUNT,
    META_KEY,
    WEIGHTS,
    load_ranking,
    rank_components,
    store_ranking,
)
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")


# --- synthetic store ----------------------------------------------------------


def _store_with(components, edges=(), files=(), activity=()):
    """Build an in-memory store with exactly the facts a case needs."""
    store = FactStore(":memory:")
    path_to_id = {}
    for path in files:
        path_to_id[path] = store.add_file(path=path, language="python", lines=10, size_bytes=100)
    for comp in components:
        store.add_component(
            component_id=comp["id"],
            name=comp.get("name", comp["id"]),
            type=comp.get("type", "module"),
            path=comp.get("path", comp["id"]),
            parent_id=None,
            role=comp.get("type", "module"),
            meta=comp.get("meta", {}),
        )
        for path in comp.get("files", []):
            if path in path_to_id:
                store.link_component_file(comp["id"], path_to_id[path])
    for source, target, kind in edges:
        store.add_edge(source_id=source, target_id=target, type=kind, evidence=[], confidence="inferred")
    if activity:
        store.merge_file_activity(activity)
    store.commit()
    return store


def _plain(cid, **kw):
    return {"id": cid, "meta": {"metrics": {"lines": kw.pop("lines", 10)}}, **kw}


# --- 1. each signal moves the score ------------------------------------------


def test_fan_in_raises_the_score():
    store = _store_with(
        components=[_plain("a"), _plain("b"), _plain("c"), _plain("d")],
        edges=[("b", "a", "imports"), ("c", "a", "imports"), ("d", "a", "imports")],
    )
    try:
        ranking = rank_components(store)
        by_id = ranking.by_id
        assert by_id["a"].fan_in == 3
        assert by_id["a"].score > by_id["b"].score
        assert ranking.ordered_ids()[0] == "a"
    finally:
        store.close()


def test_distinct_partners_not_edge_count_drive_fan_in():
    """Two edges between the same pair are one dependency, not two.

    A chatty pair (an import edge and a call edge between the same components)
    must not outrank a component that genuinely many others depend on.
    """
    store = _store_with(
        components=[_plain("chatty"), _plain("depended"), _plain("x"), _plain("y"), _plain("z")],
        edges=[
            ("x", "chatty", "imports"),
            ("x", "chatty", "calls"),
            ("x", "chatty", "references"),
            ("x", "depended", "imports"),
            ("y", "depended", "imports"),
            ("z", "depended", "imports"),
        ],
    )
    try:
        by_id = rank_components(store).by_id
        assert by_id["chatty"].fan_in == 1
        assert by_id["depended"].fan_in == 3
        assert by_id["depended"].score > by_id["chatty"].score
    finally:
        store.close()


def test_activity_raises_the_score():
    store = _store_with(
        components=[
            {"id": "hot", "files": ["hot.py"], "meta": {"metrics": {"lines": 10}}},
            {"id": "cold", "files": ["cold.py"], "meta": {"metrics": {"lines": 10}}},
        ],
        files=["hot.py", "cold.py"],
        activity=[("hot.py", 200, 1000, 500, "2020-01-01", "2026-01-01"),
                  ("cold.py", 1, 10, 0, "2020-01-01", "2020-01-02")],
    )
    try:
        ranking = rank_components(store)
        by_id = ranking.by_id
        assert ranking.has_activity is True
        assert by_id["hot"].commits == 200
        assert by_id["cold"].commits == 1
        assert by_id["hot"].score > by_id["cold"].score
    finally:
        store.close()


def test_entry_points_are_recognised_three_ways_and_recorded():
    store = _store_with(
        components=[
            {"id": "svc", "meta": {"port": 8080, "metrics": {"lines": 10}}},
            {"id": "cli", "files": ["src/main.py"], "meta": {"metrics": {"lines": 10}}},
            {"id": "root", "meta": {"metrics": {"lines": 10}}},
            {"id": "leaf", "meta": {"metrics": {"lines": 10}}},
        ],
        edges=[("root", "leaf", "imports")],
        files=["src/main.py"],
    )
    try:
        by_id = rank_components(store).by_id
        assert by_id["svc"].is_entry_point and "listens on a port" in by_id["svc"].entry_reasons[0]
        assert by_id["cli"].is_entry_point and "entry file" in by_id["cli"].entry_reasons[0]
        assert by_id["root"].is_entry_point and "graph root" in by_id["root"].entry_reasons[0]
        # A leaf that things depend on is not an entry point.
        assert by_id["leaf"].is_entry_point is False
    finally:
        store.close()


def test_size_raises_the_score_but_least():
    store = _store_with(
        components=[_plain("big", lines=100_000), _plain("small", lines=1)],
    )
    try:
        by_id = rank_components(store).by_id
        assert by_id["big"].score > by_id["small"].score
        # Size alone cannot outweigh fan-in: its weight is the smallest.
        assert WEIGHTS["size"] < WEIGHTS["fan_in"]
        assert by_id["big"].score <= WEIGHTS["size"] + WEIGHTS["entry"] + 1e-9
    finally:
        store.close()


# --- 2. deterministic and stable ---------------------------------------------


def test_ranking_is_identical_across_repeated_runs_including_ties():
    """Every component here scores identically, so only the tie-break orders them."""
    store = _store_with(components=[_plain(cid) for cid in "hgfedcba"])
    try:
        first = rank_components(store).to_dict()
        second = rank_components(store).to_dict()
        assert first == second
        # A total order: ties break on component id, ascending.
        assert rank_components(store).ordered_ids() == list("abcdefgh")
    finally:
        store.close()


def test_a_ranking_round_trips_through_the_store():
    store = _store_with(components=[_plain("a"), _plain("b")])
    try:
        original = rank_components(store)
        assert load_ranking(store) is None  # nothing persisted yet
        store_ranking(store, original)
        assert store.get_meta(META_KEY)
        restored = load_ranking(store)
        assert restored is not None
        assert restored.to_dict() == original.to_dict()
    finally:
        store.close()


# --- 3. bands are quintiles by position --------------------------------------


def test_bands_are_quintiles_by_rank_position_not_by_score_value():
    """Twenty components whose scores cluster still spread across five bands."""
    store = _store_with(components=[_plain(f"c{i:02d}") for i in range(20)])
    try:
        ranking = rank_components(store)
        counts = ranking.band_counts()
        assert set(counts) == set(range(1, BAND_COUNT + 1))
        # Twenty components, five bands, four each: an even spread despite every
        # score being identical. A value-based cut would have put all twenty in
        # one band and told the ladder nothing about where to spend effort.
        assert list(counts.values()) == [4, 4, 4, 4, 4]
        assert ranking.items[0].band == 1
        assert ranking.items[-1].band == BAND_COUNT
    finally:
        store.close()


def test_an_unranked_id_reads_as_the_lowest_band():
    store = _store_with(components=[_plain("a")])
    try:
        ranking = rank_components(store)
        assert ranking.band_for("does-not-exist") == BAND_COUNT
        assert ranking.score_for("does-not-exist") == 0.0
    finally:
        store.close()


def test_an_empty_store_ranks_to_nothing_without_dividing_by_zero():
    store = _store_with(components=[])
    try:
        ranking = rank_components(store)
        assert len(ranking) == 0
        assert ranking.band_counts() == {b: 0 for b in range(1, BAND_COUNT + 1)}
    finally:
        store.close()


# --- 4. heavy tails are damped -----------------------------------------------


def test_one_outlier_does_not_flatten_everything_below_it():
    """Fail-before contrast for the log damping.

    With plain max-normalization, an outlier at 10,000 commits would put the
    100-commit and 10-commit components at 0.01 and 0.001 of the activity
    signal: indistinguishable, and the ranking below the hotspot becomes noise.
    Damped, they stay clearly separated.
    """
    store = _store_with(
        components=[
            {"id": "outlier", "files": ["o.py"], "meta": {"metrics": {"lines": 10}}},
            {"id": "busy", "files": ["b.py"], "meta": {"metrics": {"lines": 10}}},
            {"id": "quiet", "files": ["q.py"], "meta": {"metrics": {"lines": 10}}},
        ],
        files=["o.py", "b.py", "q.py"],
        activity=[
            ("o.py", 10_000, 1, 1, "2020-01-01", "2026-01-01"),
            ("b.py", 100, 1, 1, "2020-01-01", "2026-01-01"),
            ("q.py", 10, 1, 1, "2020-01-01", "2026-01-01"),
        ],
    )
    try:
        by_id = rank_components(store).by_id
        busy_share = by_id["busy"].score / by_id["outlier"].score
        quiet_share = by_id["quiet"].score / by_id["outlier"].score
        # Under plain max-normalization these ratios would be 0.01 and 0.001.
        assert busy_share > 0.4
        assert quiet_share > 0.2
        # And they remain ordered, so the damping did not erase the difference.
        assert by_id["outlier"].score > by_id["busy"].score > by_id["quiet"].score
    finally:
        store.close()


# --- 5. not in the projection -------------------------------------------------


def test_ranking_a_real_store_leaves_the_projection_byte_identical(tmp_path):
    """The ranking is store-internal: projecting after it changes nothing.

    This is the property both golden corpora depend on. Ranking and persisting
    must not perturb the derived architecture in any way.
    """
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    try:
        extract_repo(POLYGLOT, store)
        _, before = derive_all(store, "polyglot", root_path=POLYGLOT)
        snapshot = json.dumps(copy.deepcopy(before), sort_keys=True, default=str)

        ranking = rank_components(store)
        store_ranking(store, ranking)
        store.commit()

        assert len(ranking) > 0, "the polyglot fixture should produce components"

        _, after = derive_all(store, "polyglot", root_path=POLYGLOT)
        assert json.dumps(after, sort_keys=True, default=str) == snapshot

        # And the ranking itself never reaches the projected dict.
        assert "navigation_importance" not in snapshot
        assert "importance" not in json.dumps(after.get("stats", {}), default=str)
    finally:
        store.close()


def test_ranking_a_real_store_is_stable_across_a_re_derive(tmp_path):
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    try:
        extract_repo(POLYGLOT, store)
        derive_all(store, "polyglot", root_path=POLYGLOT)
        first = rank_components(store).to_dict()
        derive_all(store, "polyglot", root_path=POLYGLOT)
        second = rank_components(store).to_dict()
        assert first == second
    finally:
        store.close()
