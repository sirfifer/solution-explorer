"""Tests for P7-2: the headless enrichment CLI.

Covers the deterministic pieces (partition planning, prompt construction from
store facts, --update staleness scoping, dry-run) and the failure path (a
schema-invalid response is rejected and, after one retry, recorded failed with
its targets left unenriched). The Claude invocation is mocked here so these
tests are hermetic and free; the real headless proof runs separately and is
recorded in TASKS.md.
"""

from __future__ import annotations

import json
import os

from analyzer.derive import derive_all
from analyzer.enrich.engine import (
    EnhanceConfig,
    InvokeResult,
    run_enhance,
)
from analyzer.enrich.partition import (
    plan_partitions,
    relationship_key,
)
from analyzer.enrich.prompts import (
    StoreFacts,
    build_architecture_prompt,
    build_partition_prompt,
)
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")

FIXED_CLOCK = lambda: "2026-07-13T00:00:00+00:00"  # noqa: E731


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _build_fixture_store(tmp_path):
    """Extract + derive the polyglot fixture into an on-disk store; return path."""
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    derive_all(store, "polyglot", root_path=POLYGLOT)
    store.close()
    return db


def _valid_component_ai(with_role=True):
    ai = {
        "help_text": (
            "This component is part of the polyglot system. It handles a specific "
            "slice of the domain and exposes it to its neighbours. It reads and "
            "writes the data described below. Without it, the related flow cannot "
            "complete."
        ),
        "data_handled": "Domain records, request payloads, and identifiers.",
        "criticality": "supporting",
        "tech_context": "Uses its language idiomatically within the wider system.",
    }
    if with_role:
        ai["architectural_role"] = "business-logic"
    return ai


def _valid_relationship_ai():
    return {
        "data_flow_description": "The source sends requests to the target over HTTP.",
        "importance": "primary",
    }


def _valid_arch_ai():
    return {
        "summary": (
            "The polyglot system spans several languages behind a small API. "
            "Clients call the API which coordinates the rest. Libraries provide "
            "shared logic. It is a fixture, deliberately small."
        ),
        "data_flow_narrative": (
            "A request enters the web layer, which calls the API over HTTP, which "
            "consults libraries and a worker before responding."
        ),
        "component_groups": [
            {"name": "Services", "component_ids": ["services/api", "services/web"]}
        ],
        "tech_diversity": "Swift, Rust, Ruby, Python, TypeScript, and Go.",
        "test_health_summary": "Testing is minimal across this fixture.",
        "observations": [],
    }


def _extract_components_from_prompt(prompt):
    """Pull the COMPONENTS json list out of a partition prompt."""
    marker = "COMPONENTS (produce an ai_enhance for every id):\n"
    start = prompt.index(marker) + len(marker)
    end = prompt.index("\n\nRELATIONSHIPS", start)
    return json.loads(prompt[start:end])


def _extract_relationships_from_prompt(prompt):
    marker = "RELATIONSHIPS (produce an ai_enhance for every key):\n"
    start = prompt.index(marker) + len(marker)
    end = prompt.index("\n\nReturn the JSON object now.", start)
    return json.loads(prompt[start:end])


class RecordingInvoker:
    """A fake invoker that answers prompts with valid (or forced-invalid) JSON.

    It parses the component ids and relationship keys out of the prompt, so it
    produces a schema-valid response for exactly the targets the engine asked
    for, without any model. ``bad_component`` forces one component's criticality
    invalid to exercise the schema-rejection path.
    """

    def __init__(self, bad_component=None):
        self.calls = []
        self.bad_component = bad_component

    def __call__(self, prompt):
        self.calls.append(prompt)
        if "architecture-level summary" in prompt:
            return InvokeResult(ok=True, text=json.dumps(_valid_arch_ai()), cost_usd=0.01)
        comps = _extract_components_from_prompt(prompt)
        rels = _extract_relationships_from_prompt(prompt)
        response = {"components": {}, "relationships": {}}
        for c in comps:
            ai = _valid_component_ai()
            if self.bad_component is not None and c["id"] == self.bad_component:
                ai["criticality"] = "super-critical"  # invalid enum
            response["components"][c["id"]] = ai
        for r in rels:
            response["relationships"][r["key"]] = _valid_relationship_ai()
        return InvokeResult(ok=True, text=json.dumps(response), cost_usd=0.02)


class ExplodingInvoker:
    def __call__(self, prompt):  # pragma: no cover - must never be called
        raise AssertionError("invoker must not be called")


# ---------------------------------------------------------------------------
# partition planning
# ---------------------------------------------------------------------------

def _tree(cid, lines=10, children=None):
    return {"id": cid, "metrics": {"lines": lines}, "children": children or []}


def test_partition_plan_is_deterministic():
    comps = [
        _tree("b", 10),
        _tree("a", 10, [_tree("a/x", 5), _tree("a/y", 5)]),
    ]
    rels = [{"source": "a/x", "target": "b", "type": "import"}]
    p1 = plan_partitions(comps, rels)
    p2 = plan_partitions(list(reversed(comps)), rels)
    # Same components regardless of input order, same partition ids.
    assert [p.component_ids for p in p1.partitions] == [p.component_ids for p in p2.partitions]


def test_partition_respects_component_cap_by_splitting_subtree():
    # A subtree of 1 root + 4 children with a cap of 3 must split at the child
    # level, keeping the root attached to one group (never orphaned).
    kids = [_tree(f"r/c{i}", 5) for i in range(4)]
    comps = [_tree("r", 100, kids)]
    plan = plan_partitions(comps, [], max_components=3, min_components=1)
    all_ids = {cid for p in plan.partitions for cid in p.component_ids}
    assert all_ids == {"r", "r/c0", "r/c1", "r/c2", "r/c3"}
    assert plan.count >= 2  # it split
    assert all(p.size <= 3 for p in plan.partitions)


def test_partition_affinity_merge_folds_small_groups():
    # Two singletons that share a relationship fold into one partition.
    comps = [_tree("a", 5), _tree("b", 5)]
    rels = [{"source": "a", "target": "b", "type": "import"}]
    plan = plan_partitions(comps, rels, min_components=2, max_components=30)
    assert plan.count == 1
    assert set(plan.partitions[0].component_ids) == {"a", "b"}


def test_partition_include_ids_scopes_to_update_set():
    comps = [_tree("a", 5), _tree("b", 5), _tree("c", 5)]
    plan = plan_partitions(comps, [], include_ids={"a", "c"}, min_components=1)
    ids = {cid for p in plan.partitions for cid in p.component_ids}
    assert ids == {"a", "c"}


def test_relationship_key_format():
    assert relationship_key({"source": "x", "target": "y", "type": "http"}) == "x|y|http"


# ---------------------------------------------------------------------------
# prompt construction from store facts
# ---------------------------------------------------------------------------

def _facts_for_fixture(tmp_path):
    db = _build_fixture_store(tmp_path)
    store = FactStore(str(db))
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    facts = StoreFacts(
        arch, store.capabilities(), store.data_entities(), store.rules(),
        arch.get("relationships", []),
    )
    return facts, arch, store


def test_partition_prompt_embeds_store_facts_and_contract(tmp_path):
    facts, arch, store = _facts_for_fixture(tmp_path)
    try:
        plan = plan_partitions(arch["components"], arch.get("relationships", []))
        prompt = build_partition_prompt(plan.partitions[0], facts)
        # Contract pieces.
        assert "ROLE VOCABULARY" in prompt
        assert "api-gateway" in prompt
        assert "criticality" in prompt
        # Store facts: the api component and its language, plus edge counts.
        assert "services/api" in prompt
        assert "python" in prompt
        assert "inbound_edges" in prompt
        # The relationship key is present for enhancement.
        assert "services/web/src|services/api|http" in prompt
    finally:
        store.close()


def test_architecture_prompt_has_root_contract(tmp_path):
    facts, arch, store = _facts_for_fixture(tmp_path)
    try:
        prompt = build_architecture_prompt(facts)
        assert "architecture-level summary" in prompt
        assert "data_flow_narrative" in prompt
        assert "STATS:" in prompt
    finally:
        store.close()


# ---------------------------------------------------------------------------
# engine: happy path (mocked model), dry-run, failure path, update scoping
# ---------------------------------------------------------------------------

def _config(tmp_path, db, **kw):
    return EnhanceConfig(store_path=db, root=tmp_path, **kw)


def test_dry_run_invokes_nothing(tmp_path):
    db = _build_fixture_store(tmp_path)
    report = run_enhance(
        _config(tmp_path, db, dry_run=True), invoker=ExplodingInvoker(), clock=FIXED_CLOCK
    )
    assert report.dry_run is True
    assert report.partition_count == 1
    assert report.plan_preview  # a plan was produced
    assert report.components_enriched == 0


def test_full_run_writes_provenance_stamped_rows_and_passes_gate(tmp_path):
    db = _build_fixture_store(tmp_path)
    invoker = RecordingInvoker()
    report = run_enhance(
        _config(tmp_path, db, threshold=85.0), invoker=invoker, clock=FIXED_CLOCK
    )
    assert report.components_enriched == 8
    assert report.relationships_enriched == 1
    assert report.architecture_enriched is True
    assert not report.failed_partitions
    # Rows are provenance-stamped (digest present, created_at from the clock).
    store = FactStore(str(db))
    try:
        rows = store.enrichment()
        comp_rows = [r for r in rows if r["target_kind"] == "component"]
        assert len(comp_rows) == 8
        assert all(r["derived_from_hash"] for r in comp_rows)
        assert all(r["created_at"] == FIXED_CLOCK() for r in comp_rows)
    finally:
        store.close()
    # The gate ran and passed at threshold on the fixture scale.
    assert report.scorer_pass is True
    assert report.ok is True


def test_invalid_response_is_rejected_and_targets_stay_unenriched(tmp_path):
    db = _build_fixture_store(tmp_path)
    # Force one component's criticality invalid on every attempt.
    invoker = RecordingInvoker(bad_component="services/api")
    report = run_enhance(
        _config(tmp_path, db), invoker=invoker, clock=FIXED_CLOCK
    )
    # The single partition holds all components, so a bad one fails the whole
    # partition after a retry: nothing is written (never junk).
    assert report.failed_partitions == [0]
    assert report.components_enriched == 0
    assert report.partitions[0].attempts == 2  # tried once, retried once
    assert report.ok is False
    store = FactStore(str(db))
    try:
        assert [r for r in store.enrichment() if r["target_kind"] == "component"] == []
    finally:
        store.close()


def test_update_scopes_to_stale_plus_neighbours_then_zero(tmp_path):
    db = _build_fixture_store(tmp_path)
    # 1. Full enhancement.
    full = run_enhance(_config(tmp_path, db), invoker=RecordingInvoker(), clock=FIXED_CLOCK)
    assert full.components_enriched == 8

    # 2. Force services/api stale by corrupting its stored digest, then update.
    store = FactStore(str(db))
    store._conn.execute(
        "UPDATE enrichment SET derived_from_hash = 'stale-digest' "
        "WHERE target_kind = 'component' AND target_id = 'services/api'"
    )
    store.commit()
    store.close()

    upd = run_enhance(_config(tmp_path, db, update=True), invoker=RecordingInvoker(), clock=FIXED_CLOCK)
    # services/api is stale; its neighbour services/web/src (via the http edge)
    # is pulled in. Exactly those two are re-enhanced.
    enriched = {
        cid
        for p in upd.partitions
        for cid in p.component_ids
        if p.status == "enriched"
    }
    assert enriched == {"services/api", "services/web/src"}
    assert upd.components_enriched == 2
    assert upd.mode == "update"

    # 3. A second no-change update enhances zero targets (all fresh).
    zero = run_enhance(_config(tmp_path, db, update=True), invoker=RecordingInvoker(), clock=FIXED_CLOCK)
    assert zero.components_enriched == 0
    assert zero.partition_count == 0
    assert zero.architecture_enriched is False
