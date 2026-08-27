"""Tests for P7-3: AI verification of inferred edges.

The polyglot fixture has exactly one inferred http edge
(services/web/src -> services/api). These tests mock the model for the
refuted/uncertain/invalid paths and the provenance/staleness/de-emphasis
mechanics; the real bounded run (a real ``confirmed`` verdict with a cost) is
recorded in TASKS.md P7-3 Evidence.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from analyzer.derive import derive_all
from analyzer.enrich import DigestIndex, apply_verdict_overlay, enrichment_staleness
from analyzer.enrich.digest import relationship_target_id
from analyzer.enrich.engine import InvokeResult
from analyzer.enrich.passes import VerifyConfig, verify_edges
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")
EDGE_KEY = relationship_target_id("services/web/src", "services/api", "http")

FIXED_CLOCK = lambda: "2026-07-13T00:00:00+00:00"  # noqa: E731


def _build_store(tmp_path):
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    derive_all(store, "polyglot", root_path=POLYGLOT)
    store.commit()
    store.close()
    return db


def _cfg(db, **kw):
    return VerifyConfig(store_path=db, root=Path(POLYGLOT), **kw)


def _ids_in(prompt):
    """The edge ids a batched verify prompt is asking about."""
    return re.findall(r'"id":\s*"([^"]+)"', prompt)


def _mock(status, reason="grounded reason", calls=None):
    """A model that answers every edge in the batch it was handed.

    Verification is batched: one call carries many independent edges and
    returns a verdict per id. A per-edge call spent nearly all of its cost
    re-sending the prompt for a 21-token answer, 754 times on one real run.
    """
    def invoker(prompt):
        if calls is not None:
            calls.append(prompt)
        verdicts = {
            eid: {"status": status, "reason": reason} for eid in _ids_in(prompt)
        }
        return InvokeResult(
            ok=True, text=json.dumps({"verdicts": verdicts}), cost_usd=0.01
        )
    return invoker


class _Exploding:
    called = False

    def __call__(self, prompt):
        _Exploding.called = True
        raise AssertionError("invoker must not be called")


def test_inferred_edge_gets_verdict_stamped_with_relationship_digest(tmp_path):
    db = _build_store(tmp_path)
    report = verify_edges(_cfg(db), invoker=_mock("confirmed"), clock=FIXED_CLOCK)
    assert report.ok and report.done == 1
    assert report.tally() == {"confirmed": 1}

    store = FactStore(str(db))
    rows = [r for r in store.enrichment() if r["target_kind"] == "edge-verdict"]
    assert len(rows) == 1
    row = rows[0]
    assert row["target_id"] == EDGE_KEY
    assert row["payload"]["status"] == "confirmed"
    # The stamped digest equals the current relationship digest (provenance).
    index = DigestIndex.from_store(store)
    assert row["derived_from_hash"] == index.for_target("edge-verdict", EDGE_KEY)
    assert row["derived_from_hash"] is not None
    store.close()


def test_refuted_edge_is_marked_and_de_emphasized_never_deleted(tmp_path):
    db = _build_store(tmp_path)
    verify_edges(_cfg(db), invoker=_mock("refuted", "the snippet is a bare string"), clock=FIXED_CLOCK)

    store = FactStore(str(db))
    # The edge itself is still in the store (never deleted, the gate line).
    assert any(
        e["source_id"] == "services/web/src" and e["target_id"] == "services/api"
        for e in store.edges()
    )
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    apply_verdict_overlay(arch, store)
    rel = next(r for r in arch["relationships"] if r["source"] == "services/web/src")
    assert rel["verdict"]["status"] == "refuted"
    assert rel["de_emphasized"] is True
    # The relationship is still present (marked, not removed).
    assert rel["target"] == "services/api"
    store.close()


def test_uncertain_verdict_recorded(tmp_path):
    db = _build_store(tmp_path)
    report = verify_edges(_cfg(db), invoker=_mock("uncertain"), clock=FIXED_CLOCK)
    assert report.tally() == {"uncertain": 1}
    store = FactStore(str(db))
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    apply_verdict_overlay(arch, store)
    rel = next(r for r in arch["relationships"] if r["source"] == "services/web/src")
    assert rel["verdict"]["status"] == "uncertain"
    assert "de_emphasized" not in rel  # only refuted edges are de-emphasized
    store.close()


def test_invalid_verdict_is_not_written(tmp_path):
    db = _build_store(tmp_path)

    def bad(prompt):
        return InvokeResult(ok=True, text=json.dumps({"status": "maybe", "reason": "x"}), cost_usd=0.01)

    report = verify_edges(_cfg(db), invoker=bad, clock=FIXED_CLOCK)
    assert not report.ok
    assert report.failed == [EDGE_KEY]
    store = FactStore(str(db))
    assert [r for r in store.enrichment() if r["target_kind"] == "edge-verdict"] == []
    store.close()


def test_dry_run_invokes_nothing(tmp_path):
    db = _build_store(tmp_path)
    _Exploding.called = False
    report = verify_edges(_cfg(db, dry_run=True), invoker=_Exploding(), clock=FIXED_CLOCK)
    assert report.dry_run and report.target_count == 1
    assert not _Exploding.called
    store = FactStore(str(db))
    assert [r for r in store.enrichment() if r["target_kind"] == "edge-verdict"] == []
    store.close()


def test_max_targets_zero_caps_to_no_work(tmp_path):
    db = _build_store(tmp_path)
    _Exploding.called = False
    report = verify_edges(_cfg(db, max_targets=0), invoker=_Exploding(), clock=FIXED_CLOCK)
    assert report.target_count == 0
    assert not _Exploding.called


def test_verdict_goes_stale_when_endpoint_code_changes(tmp_path):
    db = _build_store(tmp_path)
    verify_edges(_cfg(db), invoker=_mock("confirmed"), clock=FIXED_CLOCK)

    store = FactStore(str(db))
    fresh = {r["target_id"]: r for r in enrichment_staleness(store)
             if r["target_kind"] == "edge-verdict"}
    assert fresh[EDGE_KEY]["stale"] is False

    # Change an endpoint component's member file content: the relationship digest
    # (and thus the edge-verdict) must go stale, but the verdict payload is kept.
    store._conn.execute(
        "UPDATE files SET content_hash = 'CHANGED' WHERE path = 'services/api/api/server.py'"
    )
    store.commit()
    stale = {r["target_id"]: r for r in enrichment_staleness(store)
             if r["target_kind"] == "edge-verdict"}
    assert stale[EDGE_KEY]["stale"] is True
    assert stale[EDGE_KEY]["payload"]["status"] == "confirmed"  # served, not dropped

    # The projection carries the stale marker on the verdict.
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    apply_verdict_overlay(arch, store)
    rel = next(r for r in arch["relationships"] if r["source"] == "services/web/src")
    assert rel["verdict"]["stale"] is True
    store.close()


def test_update_reverifies_only_stale_or_missing(tmp_path):
    db = _build_store(tmp_path)
    verify_edges(_cfg(db), invoker=_mock("confirmed"), clock=FIXED_CLOCK)

    # A no-change --update re-verifies nothing (invoker must not be called).
    _Exploding.called = False
    report = verify_edges(_cfg(db, update=True), invoker=_Exploding(), clock=FIXED_CLOCK)
    assert report.target_count == 0 and not _Exploding.called

    # After an endpoint changes, --update re-verifies exactly the stale edge.
    store = FactStore(str(db))
    store._conn.execute(
        "UPDATE files SET content_hash = 'CHANGED2' WHERE path = 'services/api/api/server.py'"
    )
    store.commit()
    store.close()
    report2 = verify_edges(_cfg(db, update=True), invoker=_mock("refuted"), clock=FIXED_CLOCK)
    assert report2.target_count == 1 and report2.tally() == {"refuted": 1}


# --- batching: the fix for a pass that cost more than the work it verified ----


def test_many_edges_are_verified_in_one_call(tmp_path, monkeypatch):
    """The measurement that forced this: 754 calls, $10.50, 21 tokens each.

    Verification answers are a status and one sentence. A per-item call pays the
    whole prompt to get them, so on the 2026-08-25 unamentis-ios run the verify
    passes were 99% of the run's invocations and 76% of its cost, 3.4x the
    enhancement work they existed to check. The verdicts were always
    independent, so batching changes the bill and not the answers.
    """
    db = _build_store(tmp_path)
    calls = []
    report = verify_edges(
        _cfg(db, verify_batch=25), invoker=_mock("confirmed", calls=calls),
        clock=FIXED_CLOCK,
    )
    assert report.ok
    assert report.done >= 1
    # Every target answered, in far fewer calls than there were targets.
    assert len(calls) == 1, f"expected one batched call, got {len(calls)}"


def test_an_edge_with_no_verdict_in_its_batch_stays_unverified(tmp_path):
    """A missing answer is not a confirmation.

    The risk batching introduces is a model that returns fewer verdicts than it
    was asked for. An edge whose id is absent must stay unverified rather than
    inherit a neighbour's verdict or default to confirmed, because an unasked
    question has no answer.
    """
    db = _build_store(tmp_path)

    def silent(prompt):
        return InvokeResult(ok=True, text=json.dumps({"verdicts": {}}), cost_usd=0.01)

    report = verify_edges(_cfg(db), invoker=silent, clock=FIXED_CLOCK)
    assert report.done == 0
    store = FactStore(str(db))
    try:
        rows = [r for r in store.enrichment() if r["target_kind"] == "edge-verdict"]
        assert rows == [], "an unanswered edge must not be stamped with a verdict"
    finally:
        store.close()


def test_a_malformed_verdict_in_a_batch_fails_only_that_edge(tmp_path):
    """One bad entry must not discard the good verdicts beside it."""
    db = _build_store(tmp_path)

    def mixed(prompt):
        ids = _ids_in(prompt)
        verdicts = {}
        for i, eid in enumerate(ids):
            if i == 0:
                verdicts[eid] = {"status": "not-a-real-status", "reason": "x"}
            else:
                verdicts[eid] = {"status": "confirmed", "reason": "sound"}
        return InvokeResult(ok=True, text=json.dumps({"verdicts": verdicts}), cost_usd=0.01)

    report = verify_edges(_cfg(db), invoker=mixed, clock=FIXED_CLOCK)
    # The bad one failed; it did not take the batch down with it.
    bad = [o for o in report.outcomes if o.status == "failed"]
    assert len(bad) >= 1
    assert any("status must be one of" in e for o in bad for e in o.errors)


def test_a_batch_is_bounded_by_bytes_not_only_by_count():
    """One oversized member must not make the whole request impossible.

    Capping a batch by item count alone is the same mistake the fact blocks
    made. On the 2026-08-26 rebuild a batch of twelve identity payloads built a
    request of ~1,041,000 tokens against a 1,000,000 limit; the pass failed,
    retried, and failed again, losing those verdicts entirely.
    """
    from analyzer.enrich.passes import MAX_VERIFY_BATCH_CHARS, _batches

    small = [{"id": f"s{i}", "body": "x" * 100} for i in range(50)]
    assert len(_batches(small, 25)) == 2, "count still bounds a batch of small items"

    huge = [{"id": f"h{i}", "body": "x" * (MAX_VERIFY_BATCH_CHARS // 3)} for i in range(6)]
    batches = _batches(huge, 25)
    assert len(batches) > 1, "size must split a batch the count would have allowed"
    for b in batches:
        assert len(json.dumps(b)) <= MAX_VERIFY_BATCH_CHARS * 1.5

    # An item bigger than the whole budget still gets verified, alone.
    giant = [{"id": "g", "body": "x" * (MAX_VERIFY_BATCH_CHARS * 2)}]
    assert len(_batches(giant, 25)) == 1
    assert _batches(giant, 25)[0][0]["id"] == "g"


def test_every_target_survives_batching():
    """Batching must partition the targets, never drop or duplicate one."""
    from analyzer.enrich.passes import _batches

    items = [{"id": f"t{i}", "body": "y" * (i * 37)} for i in range(120)]
    flat = [x for b in _batches(items, 7) for x in b]
    assert [x["id"] for x in flat] == [x["id"] for x in items]
