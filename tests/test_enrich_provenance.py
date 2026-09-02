"""Tests for P7-1: enrichment provenance and staleness.

Covers the frozen digest definition (analyzer/enrich/__init__.py), the write
path (stamp with digest, commit, injected clock), read-time staleness (the
named staleness-flip scenario, both via a content-hash edit and through a real
re-extract), the store-canonical overlay and the search dedupe reversal, and
the ai_enhance import bridge round-trip on a fixture plus digest stability
across PYTHONHASHSEED.
"""

from __future__ import annotations

import copy
import os
import subprocess
import sys

from analyzer.derive import derive_all
from analyzer.enrich import (
    ARCH_TARGET_ID,
    DigestIndex,
    apply_enrichment_overlay,
    architecture_digest,
    component_digest,
    enrichment_staleness,
    import_ai_baseline,
    relationship_target_id,
    stamp_enrichment,
    symbol_digest,
)
from analyzer.enrich.provenance import current_commit_sha
from analyzer.extract import extract_repo
from analyzer.project.search_shards import build_search_entries
from analyzer.store import FactStore, build_symbol_id

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")

FIXED_CLOCK = lambda: "2026-07-13T00:00:00+00:00"  # noqa: E731


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mini_store(hash_x: str = "h1", hash_y: str = "h2"):
    """A tiny store: component 'a' with two files, plus one symbol and one edge."""
    s = FactStore(":memory:")
    fx = s.add_file("a/x.py", content_hash=hash_x)
    fy = s.add_file("a/y.py", content_hash=hash_y)
    s.add_component("a", "a", type="library", path="a")
    s.add_component("b", "b", type="library", path="b")
    s.link_component_file("a", fx)
    s.link_component_file("a", fy)
    sid = build_symbol_id(".", "a", "a/x.py", ("foo",))
    s.add_symbol(sid, fx, "foo", kind="function")
    s.add_edge("a", "b", "import")
    s.commit()
    return s, sid


# ---------------------------------------------------------------------------
# digest definition
# ---------------------------------------------------------------------------

def test_component_digest_is_order_independent_and_content_addressed():
    a = component_digest([("z.py", "h2"), ("a.py", "h1")])
    b = component_digest([("a.py", "h1"), ("z.py", "h2")])
    assert a == b  # path-sorted, so input order does not matter
    # A content change flips the digest; an unrelated file's presence too.
    assert component_digest([("a.py", "h1")]) != component_digest([("a.py", "hX")])
    assert component_digest([("a.py", "h1")]) != component_digest([("a.py", "h1"), ("z.py", "h2")])


def test_empty_component_digest_is_stable():
    assert component_digest([]) == component_digest([])
    assert isinstance(component_digest([]), str) and component_digest([])


def test_symbol_digest_depends_on_file_hash_and_identity():
    sid = build_symbol_id(".", "a", "a/x.py", ("foo",))
    other = build_symbol_id(".", "a", "a/x.py", ("bar",))
    assert symbol_digest("h1", sid) != symbol_digest("hX", sid)  # file changed
    assert symbol_digest("h1", sid) != symbol_digest("h1", other)  # identity changed


def test_digest_index_covers_every_kind():
    store, sid = _mini_store()
    idx = DigestIndex.from_store(store)
    assert idx.for_target("component", "a") is not None
    assert idx.for_target("symbol", sid) is not None
    assert idx.for_target("relationship", relationship_target_id("a", "b", "import")) is not None
    assert idx.for_target("architecture", ARCH_TARGET_ID) == idx.architecture
    # A target that does not exist yields None (orphan), never an exception.
    assert idx.for_target("component", "does-not-exist") is None
    store.close()


def test_architecture_digest_reflects_component_change():
    d1 = architecture_digest([("a", "da"), ("b", "db")])
    d2 = architecture_digest([("a", "daX"), ("b", "db")])
    assert d1 != d2


# ---------------------------------------------------------------------------
# write path
# ---------------------------------------------------------------------------

def test_stamp_records_digest_commit_and_injected_clock():
    store, _ = _mini_store()
    idx = DigestIndex.from_store(store)
    digest = stamp_enrichment(
        store, "component", "a", {"help_text": "does A"},
        digest_index=idx, commit_sha="deadbeef", clock=FIXED_CLOCK,
    )
    assert digest == idx.component["a"]
    row = store.enrichment()[0]
    assert row["derived_from_hash"] == digest
    assert row["commit_sha"] == "deadbeef"
    assert row["created_at"] == "2026-07-13T00:00:00+00:00"
    store.close()


def test_current_commit_sha_is_nullable_outside_git(tmp_path):
    # A directory with no git tree yields None, not an exception (I5 nullable).
    assert current_commit_sha(str(tmp_path)) is None


# ---------------------------------------------------------------------------
# staleness (read time)
# ---------------------------------------------------------------------------

def test_fresh_right_after_stamp():
    store, _ = _mini_store()
    idx = DigestIndex.from_store(store)
    stamp_enrichment(store, "component", "a", {"x": 1}, digest_index=idx, clock=FIXED_CLOCK)
    rows = enrichment_staleness(store)
    assert rows[0]["stale"] is False


def test_staleness_flips_on_content_hash_change():
    """The named scenario, unit form: a member file's content hash changes."""
    store, _ = _mini_store(hash_x="h1")
    idx = DigestIndex.from_store(store)
    stamp_enrichment(store, "component", "a", {"help_text": "A"}, digest_index=idx, clock=FIXED_CLOCK)
    assert enrichment_staleness(store)[0]["stale"] is False

    # Simulate a re-extract that gave a/x.py new content.
    store._conn.execute("UPDATE files SET content_hash = 'h1-NEW' WHERE path = 'a/x.py'")
    store.commit()

    rows = enrichment_staleness(store)
    assert rows[0]["stale"] is True, "content change must flip staleness"
    # The payload is STILL served (never dropped, I5).
    assert rows[0]["payload"] == {"help_text": "A"}
    assert rows[0]["current_digest"] != rows[0]["derived_from_hash"]
    store.close()


def test_unstamped_row_has_unknown_staleness():
    store, _ = _mini_store()
    # A legacy row with no derived_from_hash: staleness is None (unknown).
    store.add_enrichment("component", "a", {"x": 1}, derived_from_hash=None)
    store.commit()
    rows = {r["target_id"]: r for r in enrichment_staleness(store)}
    assert rows["a"]["stale"] is None
    store.close()


def test_staleness_flip_through_real_extract(tmp_path):
    """Gate scenario end to end: enrich, edit a file, re-extract, read stale."""
    # Copy the polyglot fixture so we can edit a file.
    import shutil
    work = tmp_path / "repo"
    shutil.copytree(POLYGLOT, work)

    store = FactStore(":memory:")
    extract_repo(work, store)
    derive_all(store, "polyglot")

    # Pick a component that owns at least one editable text file.
    members = {}
    for row in store.component_files():
        members.setdefault(row["component_id"], []).append(row["path"])
    target_cid, target_files = None, None
    for cid, paths in sorted(members.items()):
        editable = [p for p in paths if (work / p).is_file()]
        if editable:
            target_cid, target_files = cid, editable
            break
    assert target_cid is not None

    idx = DigestIndex.from_store(store)
    stamp_enrichment(
        store, "component", target_cid, {"help_text": "component summary"},
        digest_index=idx, clock=FIXED_CLOCK,
    )
    assert enrichment_staleness(store)[0]["stale"] is False

    # Edit one member file so its content hash changes on re-extract.
    edited = work / sorted(target_files)[0]
    edited.write_text(edited.read_text() + "\n# provenance flip marker\n")

    # Re-extract (warm) and re-derive into the SAME store; enrichment survives.
    extract_repo(work, store)
    derive_all(store, "polyglot")

    rows = {r["target_id"]: r for r in enrichment_staleness(store)}
    assert rows[target_cid]["stale"] is True
    assert rows[target_cid]["payload"] == {"help_text": "component summary"}

    # The projection overlay still serves the payload, now with the marker (I5).
    _, arch = derive_all(store, "polyglot")
    apply_enrichment_overlay(arch, store)

    def find(comps):
        for c in comps:
            if c.get("id") == target_cid:
                return c
            r = find(c.get("children", []))
            if r:
                return r
    comp = find(arch["components"])
    assert comp is not None and comp["ai_enhance"]["stale"] is True
    assert comp["ai_enhance"]["help_text"] == "component summary"
    store.close()


# ---------------------------------------------------------------------------
# export overlay: store canonical (dedupe reversal)
# ---------------------------------------------------------------------------

def test_overlay_store_wins_over_inline_ai_enhance():
    store, _ = _mini_store()
    idx = DigestIndex.from_store(store)
    stamp_enrichment(
        store, "component", "a", {"help_text": "STORE canonical"},
        digest_index=idx, clock=FIXED_CLOCK,
    )
    arch = {
        "components": [
            {"id": "a", "children": [], "ai_enhance": {"help_text": "STALE inline"}},
            {"id": "b", "children": []},
        ],
        "relationships": [],
    }
    apply_enrichment_overlay(arch, store)
    # Store payload REPLACES the inline copy (reversal of the P4-5 dedupe).
    assert arch["components"][0]["ai_enhance"]["help_text"] == "STORE canonical"
    # A component with no store row keeps whatever it had (here: nothing).
    assert "ai_enhance" not in arch["components"][1]
    store.close()


def test_overlay_prunes_dangling_architecture_group_members():
    store, _ = _mini_store()
    idx = DigestIndex.from_store(store)
    stamp_enrichment(
        store,
        "architecture",
        ARCH_TARGET_ID,
        {
            "summary": "Grouped system",
            "component_groups": [
                {"name": "Live", "component_ids": ["a", "removed-generated-tree"]},
                {"name": "Removed", "component_ids": ["removed-generated-tree"]},
            ],
        },
        digest_index=idx,
        clock=FIXED_CLOCK,
    )
    arch = {
        "components": [{"id": "a", "children": []}, {"id": "b", "children": []}],
        "relationships": [],
    }

    apply_enrichment_overlay(arch, store)

    assert arch["ai_enhance"]["component_groups"] == [
        {"name": "Live", "component_ids": ["a"]},
    ]
    store.close()


def test_overlay_is_noop_without_enrichment():
    store, _ = _mini_store()
    arch = {"components": [{"id": "a", "children": [], "ai_enhance": {"x": 1}}], "relationships": []}
    before = copy.deepcopy(arch)
    apply_enrichment_overlay(arch, store)
    assert arch == before
    store.close()


def test_search_shards_store_enrichment_wins_over_inline():
    store, _ = _mini_store()
    idx = DigestIndex.from_store(store)
    stamp_enrichment(
        store, "component", "a", {"help_text": "STORE help"},
        digest_index=idx, clock=FIXED_CLOCK,
    )
    arch = {
        "components": [{"id": "a", "name": "a", "path": "a", "files": [],
                        "children": [], "ai_enhance": {"help_text": "INLINE help"}}],
        "files": [], "symbols": [],
    }
    entries = build_search_entries(arch, store)
    enr = [e for e in entries if e["ref_kind"] == "enrichment" and e["ref_id"] == "component:a"]
    assert len(enr) == 1
    assert enr[0]["text"] == "STORE help"  # store wins, inline loses on dedupe
    store.close()


# ---------------------------------------------------------------------------
# import bridge round-trip
# ---------------------------------------------------------------------------

def test_import_round_trip_on_fixture_with_real_ai_enhance():
    store = FactStore(":memory:")
    extract_repo(POLYGLOT, store)
    _, arch = derive_all(store, "polyglot")

    # Build a baseline by attaching real-shaped ai_enhance to two components,
    # one relationship, and the architecture root.
    baseline = copy.deepcopy(arch)
    comps = baseline["components"]
    first = comps[0]
    first_id = first["id"]
    first["ai_enhance"] = {
        "help_text": "the root component", "architectural_role": "orchestrator",
        "criticality": "high", "ai_enhance_version": 3,
    }
    if first.get("children"):
        child = first["children"][0]
        child["ai_enhance"] = {"help_text": "a child", "criticality": "medium"}
    baseline["ai_enhance"] = {"summary": "the whole system", "ai_enhance_version": 3}
    rel_key = None
    if baseline.get("relationships"):
        rel = baseline["relationships"][0]
        rel["ai_enhance"] = {"data_flow_description": "flows", "importance": "high"}
        rel_key = relationship_target_id(rel["source"], rel["target"], rel["type"])

    result = import_ai_baseline(store, baseline, clock=FIXED_CLOCK)
    assert result.components_imported >= 1
    assert first_id not in result.components_unmatched
    assert result.architecture_imported is True

    # Round-trip: overlay the store back onto a freshly derived arch and confirm
    # the payloads survive with the imported provenance flag, freshly stamped.
    _, arch2 = derive_all(store, "polyglot")
    apply_enrichment_overlay(arch2, store)

    def find(comps, cid):
        for c in comps:
            if c["id"] == cid:
                return c
            r = find(c.get("children", []), cid)
            if r:
                return r

    got = find(arch2["components"], first_id)
    assert got["ai_enhance"]["help_text"] == "the root component"
    assert got["ai_enhance"]["_provenance"]["imported"] is True
    assert got["ai_enhance"]["_provenance"]["commit"] == "unknown"
    assert "stale" not in got["ai_enhance"]  # fresh right after import
    assert arch2["ai_enhance"]["summary"] == "the whole system"
    if rel_key is not None:
        row = {r["target_id"]: r for r in store.enrichment()}.get(rel_key)
        assert row is not None and row["derived_from_hash"]
    store.close()


def test_import_reports_unmatched_without_guessing():
    store = FactStore(":memory:")
    extract_repo(POLYGLOT, store)
    derive_all(store, "polyglot")
    baseline = {
        "components": [{"id": "no-such-component", "children": [],
                        "ai_enhance": {"help_text": "orphan"}}],
        "relationships": [],
    }
    result = import_ai_baseline(store, baseline, clock=FIXED_CLOCK)
    assert result.components_imported == 0
    assert result.components_unmatched == ["no-such-component"]
    assert store.enrichment() == []  # nothing guessed onto a wrong target
    store.close()


# ---------------------------------------------------------------------------
# determinism across PYTHONHASHSEED
# ---------------------------------------------------------------------------

_DIGEST_PROG = """
import os, sys
sys.path.insert(0, %r)
from analyzer.store import FactStore, build_symbol_id
from analyzer.enrich import DigestIndex, ARCH_TARGET_ID, relationship_target_id
s = FactStore(":memory:")
fx = s.add_file("a/x.py", content_hash="h1")
fy = s.add_file("a/y.py", content_hash="h2")
s.add_component("a", "a", type="library", path="a")
s.add_component("b", "b", type="library", path="b")
s.link_component_file("a", fx); s.link_component_file("a", fy)
sid = build_symbol_id(".", "a", "a/x.py", ("foo",))
s.add_symbol(sid, fx, "foo", kind="function")
s.add_edge("a", "b", "import")
s.commit()
idx = DigestIndex.from_store(s)
print(idx.component["a"])
print(idx.symbol[sid])
print(idx.relationship[relationship_target_id("a","b","import")])
print(idx.architecture)
"""


def _run_with_seed(seed: str) -> str:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONHASHSEED=seed)
    out = subprocess.run(
        [sys.executable, "-c", _DIGEST_PROG % repo_root],
        capture_output=True, text=True, env=env, check=True,
    )
    return out.stdout


def test_digests_stable_across_pythonhashseed():
    a = _run_with_seed("0")
    b = _run_with_seed("1")
    assert a == b and a.strip(), "digests must be identical across PYTHONHASHSEED"
