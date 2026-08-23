"""Per-partition fault isolation for the enrichment driver (card R1 wave 3).

Before wave 3, an UNEXPECTED exception inside ``_enhance_partition`` (a bug, not
a handled invoke or validation failure, which already degrade in-band to a
``failed`` PartitionOutcome) re-raised through ``fut.result()`` and crashed the
whole ``run_enhance``. These tests drive the REAL pipeline over the polyglot
fixture, inject an unexpected exception into the real partition worker, and prove
the run completes with that partition recorded ``failed`` (the same all-or-
nothing discipline the validation path uses) instead of crashing. The recorded
reason is scrubbed via the honest-gap backbone, so it is deterministic (no
traceback, no heap addresses). Retry and cost logic are untouched (that is R2).

Fail-before: these injection tests raise against the pre-wave-3 engine and pass
now that the per-partition bulkhead is in place.
"""

from __future__ import annotations

import json
import os
import re

from analyzer.derive import derive_all
from analyzer.enrich import engine
from analyzer.enrich.engine import (
    EnhanceConfig,
    InvokeResult,
    PartitionOutcome,
    run_enhance,
)
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")

FIXED_CLOCK = lambda: "2026-07-21T00:00:00+00:00"  # noqa: E731

_VALID_ARCH = {
    "summary": "A polyglot demo: an API server, a web client, and libraries.",
    "data_flow_narrative": "Requests enter the API, which reads shared libraries.",
}


class _ArchInvoker:
    """Returns a valid architecture narrative and nothing else.

    The partition worker is monkeypatched to raise, so it never calls the
    invoker; only the architecture-narrative path does. Keeping that path clean
    isolates the test to the partition-failure behavior.
    """

    def __call__(self, prompt: str) -> InvokeResult:
        return InvokeResult(ok=True, text=json.dumps(_VALID_ARCH), cost_usd=0.0)


def _build_fixture_store(tmp_path):
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    derive_all(store, "polyglot", root_path=POLYGLOT)
    store.close()
    return db


def _config(tmp_path, db, **kw):
    return EnhanceConfig(store_path=db, root=tmp_path, **kw)


def test_unexpected_partition_exception_degrades_to_failed_outcome(tmp_path, monkeypatch):
    db = _build_fixture_store(tmp_path)
    monkeypatch.setattr(engine, "_enhance_partition", _boom_partition)
    # Must NOT raise: every partition degrades to a recorded failure.
    report = run_enhance(
        _config(tmp_path, db), invoker=_ArchInvoker(), clock=FIXED_CLOCK
    )
    assert report.partition_count >= 1
    assert report.failed_partitions == [p.id for p in report.partitions]
    for outcome in report.partitions:
        assert outcome.status == "failed"
        assert outcome.errors
        assert outcome.errors[0].startswith("partition raised an unexpected error:")
        assert "RuntimeError: injected partition fault" in outcome.errors[0]
    # The report is a whole, honest object, not a crash; ok is False.
    assert report.ok is False


def test_partition_failure_reason_is_scrubbed_and_deterministic(tmp_path, monkeypatch):
    # A heap address in the exception message must be collapsed so the recorded
    # reason is deterministic across runs (the honest-gap scrubbing contract).
    db = _build_fixture_store(tmp_path)
    monkeypatch.setattr(engine, "_enhance_partition", _boom_with_address)
    report = run_enhance(
        _config(tmp_path, db), invoker=_ArchInvoker(), clock=FIXED_CLOCK
    )
    err = report.partitions[0].errors[0]
    assert "0x..." in err
    assert not re.search(r"0x[0-9a-fA-F]{4,}", err), f"raw heap address survived: {err}"


def test_one_bad_partition_does_not_abort_a_dry_run(tmp_path, monkeypatch):
    # A dry run never reaches the futures loop (it invokes nothing), so a broken
    # partition worker cannot affect it: the plan preview is still produced. This
    # guards that the bulkhead did not disturb the dry-run path.
    db = _build_fixture_store(tmp_path)
    monkeypatch.setattr(engine, "_enhance_partition", _boom_partition)
    report = run_enhance(
        _config(tmp_path, db, dry_run=True), invoker=_ArchInvoker(), clock=FIXED_CLOCK
    )
    assert report.dry_run is True
    assert report.plan_preview  # the plan was previewed, nothing invoked


def test_unexpected_architecture_exception_degrades_without_crash(tmp_path, monkeypatch):
    # Adversarial review of PR #75, finding 2: the architecture-narrative producer
    # is a peer unit to the partitions. An unexpected exception there must degrade
    # to a recorded note (narrative left unenriched) instead of crashing the run,
    # while the partitions that succeeded still complete.
    db = _build_fixture_store(tmp_path)

    def _ok_partition(partition, facts, scorer, invoker, clock):
        outcome = PartitionOutcome(
            id=partition.id,
            component_ids=list(partition.component_ids),
            relationship_keys=list(partition.relationship_keys),
            status="enriched",
        )
        return outcome, {"components": {}, "relationships": {}}

    def _arch_boom(*_a, **_k):
        raise RuntimeError("architecture narrative exploded")

    monkeypatch.setattr(engine, "_enhance_partition", _ok_partition)
    monkeypatch.setattr(engine, "_enhance_architecture", _arch_boom)
    # Must NOT raise: the arch producer is isolated.
    report = run_enhance(
        _config(tmp_path, db), invoker=_ArchInvoker(), clock=FIXED_CLOCK
    )
    assert report.architecture_enriched is False
    assert any(
        "architecture narrative raised an unexpected error" in n for n in report.notes
    )
    assert not report.failed_partitions  # the partitions themselves succeeded


def _boom_partition(*_args, **_kwargs):
    raise RuntimeError("injected partition fault")


def _boom_with_address(*_args, **_kwargs):
    raise RuntimeError(f"partition worker {object()!r} exploded")


def test_a_relationship_heavy_partition_is_chunked_to_bound_the_response():
    """The demanded response is bounded, not just the input.

    Fail-before: the 2026-08-22 smoke planned src/vs/workbench with 331
    relationships in one partition; the ~78k-token response truncated
    mid-JSON and the run's most important items vanished from the census.
    """
    from analyzer.enrich.partition import plan_partitions

    components = [
        {"id": "hub", "metrics": {"lines": 10}, "children": []},
        {"id": "spoke", "metrics": {"lines": 10}, "children": []},
    ]
    relationships = [
        {"source": "hub", "target": f"ext-{i:03d}", "type": "import"}
        for i in range(101)
    ]
    plan = plan_partitions(
        components, relationships,
        max_lines=50_000, max_components=30, min_components=1,
        max_relationships=40,
    )
    chunks = [p for p in plan.partitions if "hub" in p.component_ids]
    assert len(chunks) == 3, "101 relationships at a bound of 40 is three chunks"
    assert all(len(p.relationship_keys) <= 40 for p in plan.partitions)
    # Every chunk repeats the owning components, so relationship contracts
    # keep their context and component answers are never lost.
    assert all(set(p.component_ids) >= {"hub"} for p in chunks)
    # Nothing dropped: the union of chunk relationships is the full set.
    seen = set()
    for p in chunks:
        seen.update(p.relationship_keys)
    assert len(seen) == 101
    # Ids stay dense and deterministic after renumbering.
    assert [p.id for p in plan.partitions] == list(range(len(plan.partitions)))
