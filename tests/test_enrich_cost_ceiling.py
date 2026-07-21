"""Engine-level R2 tests: cost ceiling and retry-invisible determinism.

These drive the REAL run_enhance over the polyglot fixture with injected fake
invokers (no real CLI, no real sleep, no real time), the established pattern.
Three contracts:

  1. COST CEILING. With a per-run ceiling, run_enhance stops LAUNCHING new
     partitions once the summed reported cost reaches it, lets in-flight ones
     finish, records the rest honestly as skipped, and exits successfully with
     the partial state. Fail-before contrast: with the ceiling disabled
     (max_cost_usd=None) every partition runs and cost accumulates unbounded.

  2. ALL-OR-NOTHING under the ceiling. A skipped partition is never half-stamped
     and is recorded "skipped" (not "failed"), so report.ok stays True.

  3. RETRY IS INVISIBLE. A run whose invoker fails transiently N times per invoke
     then succeeds (wrapped in the real RetryingInvoker with injected seams)
     stamps byte-identically to a run whose invoker succeeds first try. Retry
     changes cost accounting, never the stamped enrichment.
"""

from __future__ import annotations

import json
import os

from analyzer.derive import derive_all
from analyzer.enrich.engine import EnhanceConfig, InvokeResult, run_enhance
from analyzer.enrich.partition import flatten_components, relationship_key
from analyzer.enrich.retry import RetryingInvoker, RetryPolicy
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")
FIXED_CLOCK = lambda: "2026-07-21T00:00:00+00:00"  # noqa: E731


# --- fixture + canned valid response -----------------------------------------


def _build_store(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    store.close()
    return db, arch


def _canned_text(arch: dict) -> str:
    """A single valid response covering every component id, relationship key, and
    the architecture narrative, so any partition prompt and the arch prompt all
    validate against it."""
    comps = {
        c["id"]: {"help_text": "what it does", "data_handled": "none", "criticality": "supporting"}
        for c in flatten_components(arch.get("components", []))
    }
    rels = {
        relationship_key(r): {"data_flow_description": "flows", "importance": "internal"}
        for r in arch.get("relationships", [])
    }
    return json.dumps({
        "components": comps,
        "relationships": rels,
        "summary": "A polyglot demo.",
        "data_flow_narrative": "Requests flow through the services.",
    })


class CannedInvoker:
    """Succeeds first try with a fixed valid payload, at a fixed cost per call."""

    def __init__(self, text: str, cost: float = 0.0) -> None:
        self.text = text
        self.cost = cost
        self.calls = 0

    def __call__(self, prompt: str) -> InvokeResult:
        self.calls += 1
        return InvokeResult(ok=True, text=self.text, cost_usd=self.cost)


class FlakyCanned:
    """Fails transiently N times per distinct prompt, then returns the payload.

    Keyed on the prompt so each logical invoke (each partition, the arch
    narrative) gets exactly N transient failures then a success WITHIN one
    RetryingInvoker call (which passes the same prompt on each transport retry).
    """

    def __init__(self, text: str, transient_per_prompt: int = 2) -> None:
        self.text = text
        self.n = transient_per_prompt
        self.seen: dict[str, int] = {}

    def __call__(self, prompt: str) -> InvokeResult:
        k = self.seen.get(prompt, 0)
        self.seen[prompt] = k + 1
        if k < self.n:
            return InvokeResult(
                ok=False, text="", cost_usd=0.0, error="model reported error", status_code=503
            )
        return InvokeResult(ok=True, text=self.text, cost_usd=0.0)


def _small_partition_config(tmp_path, db, **kw):
    # max_components=1 / min_components=1 forces several small partitions (6 for
    # the polyglot fixture), which the ceiling and determinism tests need.
    # threshold=0 makes the quality gate pass: these tests exercise the R2 retry
    # and ceiling mechanics, not enrichment quality, so report.ok reflects only
    # partition success (the minimal canned payloads deliberately score low).
    kw.setdefault("threshold", 0.0)
    return EnhanceConfig(
        store_path=db, root=tmp_path, max_components=1, min_components=1, **kw
    )


def _enrichment_rows(db):
    """Semantic enrichment fields, sorted, for a byte-identical comparison.

    Only the fields that ship are compared (kind, id, payload, digest, commit,
    timestamp); any internal rowid is excluded, and the sort removes the
    thread-completion order dependence of insertion.
    """
    store = FactStore(str(db))
    try:
        rows = store.enrichment()
    finally:
        store.close()
    return sorted(
        (
            r["target_kind"],
            r["target_id"],
            json.dumps(r.get("payload"), sort_keys=True),
            r.get("derived_from_hash"),
            r.get("commit_sha"),
            r.get("created_at"),
        )
        for r in rows
    )


# --- cost ceiling ------------------------------------------------------------


def test_no_ceiling_enriches_everything_unbounded(tmp_path):
    # Fail-before contrast: with the ceiling disabled, every partition runs and
    # cost accumulates with no cutoff.
    db, arch = _build_store(tmp_path)
    inv = CannedInvoker(_canned_text(arch), cost=1.0)
    report = run_enhance(
        _small_partition_config(tmp_path, db, max_cost_usd=None),
        invoker=inv, clock=FIXED_CLOCK,
    )
    assert report.partition_count == 6
    assert all(p.status == "enriched" for p in report.partitions)
    assert not [p for p in report.partitions if p.status == "skipped"]
    assert report.components_enriched == 8  # every component enriched
    # 6 partitions + the architecture narrative, each $1.
    assert report.total_cost_usd >= 6.0
    # No partition failed. (report.ok also folds in the separate quality gate,
    # which the deliberately-minimal canned payloads do not clear; R2 is about
    # partition success and cost, not enrichment quality.)
    assert not report.failed_partitions


def test_ceiling_stops_launching_and_records_skips(tmp_path):
    db, arch = _build_store(tmp_path)
    inv = CannedInvoker(_canned_text(arch), cost=1.0)
    # max_parallel=1 makes submission strictly sequential, so the ceiling triggers
    # at a deterministic point: p1 (running 1) p2 (running 2) p3 (running 3 >= 2.5),
    # then no new launches -> p4,p5,p6 skipped.
    report = run_enhance(
        _small_partition_config(tmp_path, db, max_cost_usd=2.5, max_parallel=1),
        invoker=inv, clock=FIXED_CLOCK,
    )
    enriched = [p for p in report.partitions if p.status == "enriched"]
    skipped = [p for p in report.partitions if p.status == "skipped"]
    assert len(enriched) == 3
    assert len(skipped) == 3
    # Skipped partitions carry an honest reason and were never stamped.
    for p in skipped:
        assert p.errors and "cost ceiling reached" in p.errors[0]
    # The run succeeds with partial state: skipped is not failed (so R2 never
    # turns a truncated run into a failed one; the CLI exit reflects only the
    # separate quality gate).
    assert not report.failed_partitions
    # Cost is bounded near the ceiling (soft: the in-flight batch may overshoot,
    # but with max_parallel=1 that is a single partition).
    assert report.total_cost_usd == 3.0
    # A note explains the truncation, and the architecture narrative was skipped.
    assert any("cost ceiling reached" in n for n in report.notes)
    assert not report.architecture_enriched


def test_ceiling_skipped_partition_stamps_nothing(tmp_path):
    db, arch = _build_store(tmp_path)
    inv = CannedInvoker(_canned_text(arch), cost=1.0)
    report = run_enhance(
        _small_partition_config(tmp_path, db, max_cost_usd=2.5, max_parallel=1),
        invoker=inv, clock=FIXED_CLOCK,
    )
    skipped_component_ids = {
        cid for p in report.partitions if p.status == "skipped" for cid in p.component_ids
    }
    assert skipped_component_ids  # there are skipped components
    # None of the skipped components were stamped (all-or-nothing per partition).
    store = FactStore(str(db))
    try:
        stamped = {
            r["target_id"] for r in store.enrichment() if r["target_kind"] == "component"
        }
    finally:
        store.close()
    assert skipped_component_ids.isdisjoint(stamped)


# --- retry is invisible in the stamped output --------------------------------


def test_retried_success_stamps_byte_identically(tmp_path):
    # Run A: a plain first-try success.
    db_a, arch_a = _build_store(tmp_path / "a")
    canned = _canned_text(arch_a)
    report_a = run_enhance(
        _small_partition_config(tmp_path / "a", db_a, max_cost_usd=None),
        invoker=CannedInvoker(canned, cost=0.0), clock=FIXED_CLOCK,
    )
    # Run B: the SAME payload but reached only after 2 transient failures per
    # invoke, through the real RetryingInvoker with injected no-op sleep.
    db_b, arch_b = _build_store(tmp_path / "b")
    canned_b = _canned_text(arch_b)
    assert canned_b == canned  # identical fixtures -> identical canned payload
    retrying = RetryingInvoker(
        FlakyCanned(canned_b, transient_per_prompt=2),
        RetryPolicy(max_attempts=4),
        sleep=lambda _s: None,  # no real sleep in tests
        monotonic=lambda: 0.0,  # frozen clock: budget never trips
    )
    report_b = run_enhance(
        _small_partition_config(tmp_path / "b", db_b, max_cost_usd=None),
        invoker=retrying, clock=FIXED_CLOCK,
    )

    # Both runs enriched the same amount, and the stamped rows are byte-identical:
    # retry is invisible in the projection.
    assert report_a.components_enriched == report_b.components_enriched == 8
    assert report_a.architecture_enriched and report_b.architecture_enriched
    assert _enrichment_rows(db_a) == _enrichment_rows(db_b)


def test_transient_without_retry_fails_the_partition(tmp_path):
    # Fail-before: the SAME flaky invoker WITHOUT the retry wrapper. Its two
    # validation attempts both hit a transient 503 (transient_per_prompt=2), so
    # the partition is recorded failed. This is exactly the pre-R2 behavior the
    # RetryingInvoker fixes (compare test_retry_reaches_success_*).
    db, arch = _build_store(tmp_path)
    raw_flaky = FlakyCanned(_canned_text(arch), transient_per_prompt=2)
    report = run_enhance(
        _small_partition_config(tmp_path, db, max_cost_usd=None),
        invoker=raw_flaky, clock=FIXED_CLOCK,
    )
    assert report.failed_partitions  # at least one partition failed without retry
    assert report.components_enriched < 8


def test_retry_reaches_success_across_transient_failures(tmp_path):
    # A transient CLI failure that pre-R2 would kill a partition now retries and
    # the partition succeeds (fail-before: without retry, a 503 on attempt 1 would
    # fail the partition's validation loop and record it failed).
    db, arch = _build_store(tmp_path)
    retrying = RetryingInvoker(
        FlakyCanned(_canned_text(arch), transient_per_prompt=3),
        RetryPolicy(max_attempts=4),
        sleep=lambda _s: None,
        monotonic=lambda: 0.0,
    )
    report = run_enhance(
        _small_partition_config(tmp_path, db, max_cost_usd=None),
        invoker=retrying, clock=FIXED_CLOCK,
    )
    assert not report.failed_partitions
    assert report.components_enriched == 8
