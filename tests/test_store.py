"""Tests for the v2 fact store: schema, symbol identity, FTS, and traversal.

Covers P4-1 acceptance:
- schema creates, migrates from empty, round-trips every entity type with a
  deterministic read order;
- the symbol ID grammar round-trips, including escaping and collision cases;
- FTS and bounded-depth traversal queries return the right rows.
"""

import sqlite3

import pytest

from analyzer.store import (
    SCHEMA_VERSION,
    FactStore,
    SymbolId,
    assign_symbol_ids,
    build_symbol_id,
    parse_symbol_id,
)
from analyzer.store.db import fts5_available
from analyzer.store.ids import decode_token, encode_token

# ---------------------------------------------------------------------------
# Symbol ID grammar
# ---------------------------------------------------------------------------

# Exhaustive-ish set of round-trip cases spanning every escaping rule and the
# multi-repo, nested-path, and disambiguator features.
ROUND_TRIP_CASES = [
    # repo, component, file, path, disambiguator
    (".", ".", "main.py", ("Foo",), 0),
    (".", ".", "src/app/main.py", ("Foo", "bar"), 0),
    (".", "src/app", "src/app/main.py", ("Outer", "Inner", "method"), 0),
    ("myrepo", ".", "lib.rs", ("Identifier", "render"), 0),
    ("org/name", "pkg", "a/b/c.go", ("Job", "Run"), 0),
    # spaces force quoting in every segment
    (".", "my app", "a b/c d.py", ("Foo Bar", "baz qux"), 0),
    # slash inside a descriptor forces quoting (but not in file segment)
    (".", ".", "a/b.py", ("weird/name",), 0),
    # hash inside a descriptor forces quoting; not confused with disambiguator
    (".", ".", "f.py", ("a#b",), 0),
    # backticks in names
    (".", ".", "f.py", ("a`b",), 0),
    (".", ".", "f.py", ("`",), 0),
    (".", ".", "f.py", ("``",), 0),
    # empty descriptor / empty segments
    (".", "", "f.py", ("",), 0),
    # disambiguators
    (".", ".", "f.py", ("foo",), 2),
    (".", ".", "f.py", ("foo",), 137),
    # disambiguator alongside a quoted leaf
    (".", ".", "f.py", ("a b",), 5),
    # deeply nested with mixed escaping
    ("r", "c", "d.py", ("A", "b c", "d/e", "f#g"), 3),
]


@pytest.mark.parametrize("repo,comp,file,path,dis", ROUND_TRIP_CASES)
def test_symbol_id_round_trip(repo, comp, file, path, dis):
    encoded = build_symbol_id(repo, comp, file, path, dis)
    parsed = parse_symbol_id(encoded)
    assert parsed == SymbolId(repo, comp, file, tuple(path), dis)
    # re-encoding the parsed value is stable
    assert parsed.encode() == encoded


def test_encoded_ids_are_human_readable_when_simple():
    assert build_symbol_id(".", ".", "src/app/main.py", ("Foo", "bar")) == \
        ". . src/app/main.py Foo/bar"
    assert build_symbol_id("api", "svc", "app/server.py", ("UserRepo", "get")) == \
        "api svc app/server.py UserRepo/get"


def test_slash_in_path_segment_not_quoted():
    # "/" is a legal path character in the file and component segments, so a
    # normal path renders verbatim; only descriptor-level "/" gets quoted.
    enc = build_symbol_id(".", "a/b", "a/b/c.py", ("Foo",))
    assert enc == ". a/b a/b/c.py Foo"


def test_token_encode_decode_primitives():
    assert encode_token("plain") == "plain"
    assert encode_token("") == "``"
    assert encode_token("a b") == "`a b`"
    assert encode_token("a/b", " /#") == "`a/b`"
    assert encode_token("a`b") == "`a``b`"
    for raw in ["", "plain", "a b", "a`b", "`", "``", "a/b#c", "  "]:
        assert decode_token(encode_token(raw, " /#")) == raw


def test_build_rejects_empty_path():
    with pytest.raises(ValueError):
        build_symbol_id(".", ".", "f.py", ())


def test_parse_rejects_wrong_segment_count():
    with pytest.raises(ValueError):
        parse_symbol_id("only two")


def test_collision_disambiguation_is_deterministic_and_unique():
    records = [
        (".", ".", "f.py", ("foo",)),
        (".", ".", "f.py", ("foo",)),
        (".", ".", "f.py", ("foo",)),
        (".", ".", "f.py", ("bar",)),
        (".", "other", "f.py", ("foo",)),  # different component: no collision
    ]
    ids = assign_symbol_ids(records)
    assert ids == [
        ". . f.py foo",
        ". . f.py foo#2",
        ". . f.py foo#3",
        ". . f.py bar",
        ". other f.py foo",
    ]
    assert len(set(ids)) == len(ids)
    # first occurrence keeps a bare (stable) id
    assert parse_symbol_id(ids[0]).disambiguator == 0
    assert parse_symbol_id(ids[1]).disambiguator == 2


def test_collision_result_is_order_stable():
    # Same input order yields the same assignment every time (I4 determinism).
    records = [(".", ".", "f.py", ("x",)) for _ in range(4)]
    assert assign_symbol_ids(records) == assign_symbol_ids(records)


def test_hash_in_name_survives_round_trip_without_being_a_disambiguator():
    enc = build_symbol_id(".", ".", "f.py", ("count#2",))
    parsed = parse_symbol_id(enc)
    assert parsed.path == ("count#2",)
    assert parsed.disambiguator == 0


# ---------------------------------------------------------------------------
# Schema lifecycle
# ---------------------------------------------------------------------------

def test_schema_creates_and_records_version():
    store = FactStore(":memory:")
    assert store.get_meta("schema_version") == str(SCHEMA_VERSION)
    store.close()


def test_schema_migrates_from_empty_on_disk(tmp_path):
    db_path = tmp_path / "index.db"
    # first open creates
    with FactStore(db_path) as s1:
        s1.add_file("a.py", "python", 1, 10, "h", "parsed")
    # second open on the same file is idempotent (create-if-not-exists)
    with FactStore(db_path) as s2:
        assert [f["path"] for f in s2.files()] == ["a.py"]
        assert s2.get_meta("schema_version") == str(SCHEMA_VERSION)


def test_wal_mode_enabled_on_disk(tmp_path):
    db_path = tmp_path / "index.db"
    with FactStore(db_path):
        pass
    conn = sqlite3.connect(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"


def test_schema_version_newer_than_code_raises(tmp_path, monkeypatch):
    # A store written by a newer analyzer must not be silently truncated: open
    # is a hard error (P5-4 added migration for OLDER stores; newer still errors).
    db_path = tmp_path / "index.db"
    with FactStore(db_path) as s:
        s.set_meta("schema_version", "999")
        s.commit()
    with pytest.raises(ValueError, match="newer than code"):
        FactStore(db_path)


def test_schema_migration_v1_to_v2_is_additive(tmp_path):
    # A v1 store (no activity tables) opened by v2 code gains the activity
    # tables additively, keeps its existing rows, and bumps schema_version.
    db_path = tmp_path / "index.db"
    with FactStore(db_path) as s:
        # Simulate a store created under schema v1: activity tables absent,
        # version stamped 1, and a pre-existing fact row to prove it survives.
        s._conn.executescript(
            "DROP TABLE IF EXISTS file_activity;"
            "DROP TABLE IF EXISTS file_activity_period;"
            "DROP TABLE IF EXISTS file_author;"
            "DROP TABLE IF EXISTS cochange_pair;"
        )
        s.set_meta("schema_version", "1")
        s.add_file("src/a.py", "python", 10, 100, "ha", "parsed")
        s.commit()
    # Re-open with current code: migration runs.
    with FactStore(db_path) as s:
        assert s.get_meta("schema_version") == "2"
        # Pre-existing row intact.
        assert [f["path"] for f in s.files()] == ["src/a.py"]
        # New tables exist and are usable.
        assert s.file_activity() == []
        s.merge_file_activity([("src/a.py", 2, 5, 1, "2020-01-01", "2020-02-01")])
        s.commit()
        assert s.file_activity()[0]["commit_count"] == 2


def test_activity_merge_is_additive(tmp_path):
    # Two merges over the same path add counts, fold first_seen MIN / last MAX.
    with FactStore(":memory:") as s:
        s.merge_file_activity([("f.py", 3, 30, 10, "2020-02-01", "2020-03-01")])
        s.merge_file_activity([("f.py", 2, 20, 5, "2020-01-01", "2020-04-01")])
        row = s.file_activity()[0]
        assert row["commit_count"] == 5
        assert row["lines_added"] == 50
        assert row["lines_removed"] == 15
        assert row["first_seen"] == "2020-01-01"
        assert row["last_modified"] == "2020-04-01"


def test_clear_activity_removes_rows_and_meta(tmp_path):
    with FactStore(":memory:") as s:
        s.merge_file_activity([("f.py", 1, 1, 0, "2020-01-01", "2020-01-01")])
        s.merge_cochange_pairs([("a.py", "b.py", 3)])
        s.set_meta("activity_head", "abc123")
        s.commit()
        s.clear_activity()
        assert s.file_activity() == []
        assert s.cochange_pairs() == []
        assert s.get_meta("activity_head") is None


# ---------------------------------------------------------------------------
# Round-trip every entity type with deterministic order
# ---------------------------------------------------------------------------

def _populate(store: FactStore):
    fa = store.add_file("src/b.py", "python", 20, 200, "hb", "parsed")
    fb = store.add_file("src/a.py", "python", 10, 100, "ha", "parsed")
    foo = build_symbol_id(".", ".", "src/a.py", ("Foo",))
    bar = build_symbol_id(".", ".", "src/a.py", ("Foo", "bar"))
    store.add_symbol(foo, fb, "Foo", "class", line=1, end_line=9, docstring="foo class")
    store.add_symbol(bar, fb, "bar", "method", parent_id=foo, line=2, end_line=3)
    store.add_symbol(
        build_symbol_id(".", ".", "src/b.py", ("helper",)), fa, "helper", "function",
        line=1, docstring="a helper",
    )
    store.add_signal(fb, "port", {"port": 8000}, line=5)
    store.add_signal(fa, "url", {"url": "http://api:8000"}, line=3)
    store.add_component("comp-b", "B", "library", "src/b", description="lib b")
    store.add_component("comp-a", "A", "application", "src/a", description="app a")
    store.link_component_file("comp-a", fb)
    store.link_component_file("comp-b", fa)
    store.add_edge("comp-a", "comp-b", "import", evidence=[{"file": "src/a.py", "line": 1}],
                   confidence="certain", origin="static")
    store.add_edge("comp-a", "infra:db", "database", evidence=[{"file": "src/a.py", "line": 2}],
                   confidence="inferred", origin="static")
    store.add_capability("cap-1", "comp-a", "api", "GET /users",
                         detail={"method": "GET", "path": "/users"},
                         evidence=[{"file": "src/a.py", "line": 4}], confidence="certain")
    store.add_data_entity("ent-1", "comp-a", "User", "model",
                          fields=[{"name": "id", "type": "int"}],
                          evidence=[{"file": "src/a.py", "line": 6}])
    store.add_entity_access("comp-a", "ent-1", "read",
                            evidence=[{"file": "src/a.py", "line": 7}], confidence="inferred")
    store.add_enrichment("component", "comp-a", {"summary": "the a app"},
                         derived_from_hash="ha", commit_sha="abc123",
                         created_at="2026-07-13T00:00:00Z", help_text="how to use the a app")
    store.add_coverage("src/a.py", "parsed")
    store.add_coverage("src/b.py", "parsed")
    store.add_coverage("node_modules/x.js", "excluded", "node_modules")
    store.add_coverage("big.bin", "failed", "too large")
    store.cache_facts("ha", "py-1", {"symbols": ["Foo"]})
    store.commit()


def test_round_trip_all_entities():
    store = FactStore(":memory:")
    _populate(store)

    files = store.files()
    assert [f["path"] for f in files] == ["src/a.py", "src/b.py"]  # sorted by path

    syms = store.symbols()
    assert [s["id"] for s in syms] == sorted(s["id"] for s in syms)  # sorted by id
    bar = next(s for s in syms if s["name"] == "bar")
    assert bar["parent_id"] == build_symbol_id(".", ".", "src/a.py", ("Foo",))
    assert bar["kind"] == "method"

    sigs = store.signals()
    assert {s["kind"] for s in sigs} == {"port", "url"}
    assert sigs[0]["value"] is not None  # JSON decoded back into a dict

    comps = store.components()
    assert [c["id"] for c in comps] == ["comp-a", "comp-b"]
    assert comps[0]["meta"] is None or isinstance(comps[0]["meta"], (dict, list))

    cf = store.component_files()
    assert {"comp-a", "comp-b"} == {r["component_id"] for r in cf}

    edges = store.edges()
    # sorted by (source_id, target_id, type): comp-a/comp-b before comp-a/infra:db
    assert [e["type"] for e in edges] == ["import", "database"]
    db_edge = next(e for e in edges if e["type"] == "database")
    assert db_edge["evidence"] == [{"file": "src/a.py", "line": 2}]
    assert db_edge["confidence"] == "inferred"

    caps = store.capabilities()
    assert caps[0]["detail"] == {"method": "GET", "path": "/users"}

    ents = store.data_entities()
    assert ents[0]["fields"] == [{"name": "id", "type": "int"}]

    acc = store.entity_access()
    assert acc[0]["mode"] == "read"

    enr = store.enrichment()
    assert enr[0]["payload"] == {"summary": "the a app"}
    assert enr[0]["derived_from_hash"] == "ha"
    assert enr[0]["commit_sha"] == "abc123"

    cov = store.coverage()
    assert [c["path"] for c in cov] == sorted(c["path"] for c in cov)
    assert store.coverage_summary() == {"excluded": 1, "failed": 1, "parsed": 2}
    assert [c["path"] for c in store.coverage("failed")] == ["big.bin"]

    assert store.get_cached_facts("ha", "py-1") == {"symbols": ["Foo"]}
    assert store.get_cached_facts("nope", "py-1") is None
    store.close()


def test_reads_are_deterministic_across_repeated_calls():
    store = FactStore(":memory:")
    _populate(store)
    for reader in (store.files, store.symbols, store.components, store.edges,
                   store.signals, store.coverage):
        assert reader() == reader()
    store.close()


def test_enrichment_upsert_replaces_by_target():
    store = FactStore(":memory:")
    store.add_component("c", "C", "library", "c")
    store.add_enrichment("component", "c", {"v": 1}, derived_from_hash="h1")
    store.add_enrichment("component", "c", {"v": 2}, derived_from_hash="h2")
    store.commit()
    enr = store.enrichment()
    assert len(enr) == 1
    assert enr[0]["payload"] == {"v": 2}
    assert enr[0]["derived_from_hash"] == "h2"
    store.close()


# ---------------------------------------------------------------------------
# Query surface
# ---------------------------------------------------------------------------

def test_lookup_by_name_and_path_and_kind():
    store = FactStore(":memory:")
    _populate(store)
    by_name = store.lookup_by_name("Foo")
    assert any(r["ref_kind"] == "symbol" for r in by_name)

    by_path = store.lookup_by_path("src/a.py")
    kinds = {r["ref_kind"] for r in by_path}
    assert "file" in kinds

    methods = store.symbols_by_kind("method")
    assert [s["name"] for s in methods] == ["bar"]
    apps = store.components_by_type("application")
    assert [c["id"] for c in apps] == ["comp-a"]
    store.close()


@pytest.mark.skipif(not fts5_available(), reason="SQLite build lacks FTS5")
def test_fts_search():
    store = FactStore(":memory:")
    _populate(store)
    # symbol name
    hits = store.search("helper")
    assert any(h["ref_id"].endswith("helper") for h in hits)
    # component description text
    hits = store.search("app")
    assert any(h["ref_kind"] == "component" for h in hits)
    # enrichment help text is indexed
    hits = store.search("how to use")
    assert any(h["ref_kind"] == "enrichment" for h in hits)
    # ref_kind filter
    hits = store.search("a", ref_kind="component")
    assert all(h["ref_kind"] == "component" for h in hits)
    store.close()


def test_search_raises_when_fts_unavailable():
    store = FactStore(":memory:", with_fts=False)
    _populate(store)
    with pytest.raises(RuntimeError):
        store.search("anything")
    store.close()


def test_bounded_depth_traversal_out_and_in():
    store = FactStore(":memory:")
    # chain: a -> b -> c -> d
    for src, tgt in [("a", "b"), ("b", "c"), ("c", "d")]:
        store.add_edge(src, tgt, "import")
    store.commit()

    out1 = store.traverse("a", "out", 1)
    assert [r["id"] for r in out1] == ["b"]
    out2 = store.traverse("a", "out", 2)
    assert [(r["id"], r["depth"]) for r in out2] == [("b", 1), ("c", 2)]
    out_all = store.traverse("a", "out", 10)
    assert [r["id"] for r in out_all] == ["b", "c", "d"]

    incoming = store.traverse("d", "in", 10)
    # ordered by (depth, id): c is depth 1, b depth 2, a depth 3
    assert [(r["id"], r["depth"]) for r in incoming] == [("c", 1), ("b", 2), ("a", 3)]

    assert store.traverse("a", "out", 0) == []
    with pytest.raises(ValueError):
        store.traverse("a", "sideways", 1)
    store.close()


def test_traversal_terminates_on_cycles():
    store = FactStore(":memory:")
    for src, tgt in [("a", "b"), ("b", "a")]:
        store.add_edge(src, tgt, "import")
    store.commit()
    reached = store.traverse("a", "out", 5)
    # 'b' is reachable; 'a' is the start and excluded; no infinite loop.
    assert [r["id"] for r in reached] == ["b"]
    store.close()


# ---------------------------------------------------------------------------
# Copilot review round on PR #12: strict grammar parsing and FTS upsert
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "malformed",
    [
        ". . src/a.py `Foo",            # unterminated quote
        ". . src/a.py `Foo`bar",        # characters after closing quote
        ". . src/a.py Fo`o",            # stray backtick in bareword
        ".  . src/a.py Foo",            # empty segment (double space)
        "`x . src/a.py Foo",            # unbalanced quote opens the string
    ],
)
def test_parse_rejects_malformed_symbol_ids(malformed):
    """The grammar is frozen, so parsing is strict (PR #12 Copilot finding 1).

    A malformed encoding must raise, never decode to a value that re-encoding
    would not reproduce.
    """
    from analyzer.store.ids import parse_symbol_id

    with pytest.raises(ValueError):
        parse_symbol_id(malformed)


def test_decode_token_rejects_malformed_tokens():
    for bad in ["", "`abc", "a`b", "`a`b`"]:
        with pytest.raises(ValueError):
            decode_token(bad)
    # The legitimate forms still round-trip.
    assert decode_token("``") == ""
    assert decode_token("````") == "`"
    assert decode_token("`a ``b`") == "a `b"


@pytest.mark.skipif(not fts5_available(), reason="fts5 not available")
def test_reenrichment_does_not_duplicate_search_hits():
    """Upserting enrichment must replace its FTS row (PR #12 Copilot finding 2)."""
    store = FactStore(":memory:")
    store.add_enrichment("component", "comp-a", {"v": 1}, help_text="original alpha help")
    store.add_enrichment("component", "comp-a", {"v": 2}, help_text="updated alpha help")
    store.commit()

    hits = store.search("alpha")
    refs = [(h["ref_kind"], h["ref_id"]) for h in hits]
    assert refs.count(("enrichment", "component:comp-a")) == 1

    # Dropping help_text on a later upsert removes the stale entry entirely.
    store.add_enrichment("component", "comp-a", {"v": 3}, help_text=None)
    store.commit()
    assert store.search("alpha") == []
    store.close()
