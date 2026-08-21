"""T8: synthesis. Tours, narrative, lenses, work orders. No model invoked.

The viewer's tour player and Tour contract have been built, tested, advertised
and never fed. These tests check that what P4 writes actually fits that contract,
by reading the TypeScript interface itself rather than by trusting a comment.

  1. TOURS MATCH THE VIEWER CONTRACT, and are validated at WRITE time, so a
     malformed tour never reaches the product to break in front of a reader.
  2. STEP ANCHORS ARE CHECKED by the same no-AI validator the claims go through.
     A step pointing past the end of a file is dropped, not written.
  3. THE OVERLAY IS NO-OP WHEN EMPTY. A store with no tour rows projects
     byte-identically, which is what keeps both golden corpora still.
  4. HONEST GAPS ARE MATERIAL. The prompt says so, because a narrative that
     quietly routes around the gaps is the seamless map we are not building.
  5. WORK ORDERS MUST BE ABLE TO CHANGE SOMETHING. "Look again" is rejected and
     the rejection is reported, never silently dropped.
"""

from __future__ import annotations

import copy
import json
import os
import re

import pytest

from analyzer.derive import derive_all
from analyzer.enrich.digest import DigestIndex
from analyzer.enrich.engine import InvokeResult
from analyzer.enrich.evidence import EvidenceValidator
from analyzer.enrich.overlay import TOUR_TARGET_KIND, apply_enrichment_overlay
from analyzer.enrich.pipeline import (
    LadderConfig,
    LadderPolicy,
    build_run_context,
    run_pipeline,
)
from analyzer.enrich.provenance import stamp_enrichment
from analyzer.enrich.synthesis import (
    MAX_TOUR_STEPS,
    SynthesisPhase,
    build_synthesis_prompt,
    validate_tour,
)
from analyzer.enrich.workorder import WorkOrder, parse_work_orders
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER_TYPES = os.path.join(REPO_ROOT, "viewer", "src", "types.ts")
FIXED_CLOCK = lambda: "2026-08-21T00:00:00+00:00"  # noqa: E731


@pytest.fixture
def world(tmp_path):
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    store.commit()
    from analyzer.enrich.partition import flatten_components

    comps = [c for c in flatten_components(arch.get("components", [])) if c.get("id")]
    real_file = next(f["path"] for f in store.files() if f.get("lines"))
    real_lines = next(int(f["lines"]) for f in store.files() if f.get("lines"))
    store.close()
    return {
        "db": db, "run_dir": tmp_path / "run", "arch": arch,
        "components": [c["id"] for c in comps],
        "real_file": real_file, "real_lines": real_lines,
    }


def _tour(world, *, steps=2, file=None, line=1, target=None):
    return {
        "id": "request-path",
        "title": "The request path",
        "description": "How a request reaches storage and comes back.",
        "steps": [
            {
                "target": target or world["components"][i % len(world["components"])],
                "title": f"Stop {i + 1}",
                "narration": f"What the reader learns at stop {i + 1}.",
                "evidence": {"file": file or world["real_file"], "line": line},
            }
            for i in range(steps)
        ],
    }


class ScriptedSynthesis:
    def __init__(self, payload, *, arch_ok=True):
        self.payload = payload
        self.arch_ok = arch_ok
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if "architecture-level summary" in prompt:
            if not self.arch_ok:
                return InvokeResult(ok=False, text="", error="unavailable")
            return InvokeResult(ok=True, cost_usd=0.01, text=json.dumps({
                "summary": "A small polyglot system with a web front and an api.",
                "data_flow_narrative": "A request enters the web tier and is "
                                       "forwarded to the api service.",
            }))
        return InvokeResult(ok=True, cost_usd=0.02, text=json.dumps(self.payload),
                            usage={"input_tokens": 2000, "output_tokens": 400})


def _synthesize(world, invoker, *, dry_run=False, policy=None):
    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT, run_dir=world["run_dir"],
        policy=policy or LadderPolicy(), dry_run=dry_run,
    )
    ctx = build_run_context(config, invoker_factory=lambda spec: invoker,
                            clock=FIXED_CLOCK)
    try:
        run_pipeline(ctx, [SynthesisPhase()])
        return ctx.results["p4_synthesis"], ctx
    finally:
        ctx.store.close()


# --- 1. tours match the viewer contract ---------------------------------------


def _viewer_interface(name: str) -> set[str]:
    """Field names declared on one interface in the viewer's types.ts."""
    source = open(VIEWER_TYPES, encoding="utf-8").read()
    match = re.search(rf"export interface {name} \{{(.*?)\n\}}", source, re.S)
    assert match, f"{name} not found in viewer/src/types.ts"
    return set(re.findall(r"^\s*(\w+)\??:", match.group(1), re.M))


def test_a_written_tour_uses_only_fields_the_viewer_declares(world):
    """Read the TypeScript, do not trust a comment about it."""
    tour_fields = _viewer_interface("Tour")
    step_fields = _viewer_interface("TourStep")
    evidence_fields = _viewer_interface("TourStepEvidence")
    assert {"id", "title", "description", "steps"} <= tour_fields

    payload = {"tours": [_tour(world)], "lenses": []}
    _synthesize(world, ScriptedSynthesis(payload))

    store = FactStore(str(world["db"]))
    try:
        rows = [r for r in store.enrichment() if r["target_kind"] == TOUR_TARGET_KIND]
        arch = copy.deepcopy(world["arch"])
        apply_enrichment_overlay(arch, store, digest_index=DigestIndex.from_store(store))
    finally:
        store.close()

    assert rows, "the tour should have been written"
    assert arch["tours"], "the overlay should project it"
    projected = arch["tours"][0]
    assert set(projected) <= tour_fields, f"unknown Tour fields: {set(projected) - tour_fields}"
    for step in projected["steps"]:
        assert set(step) <= step_fields, f"unknown TourStep fields: {set(step) - step_fields}"
        if "evidence" in step:
            assert set(step["evidence"]) <= evidence_fields


def test_the_projected_tour_carries_the_content_that_was_authored(world):
    payload = {"tours": [_tour(world, steps=3)], "lenses": []}
    _synthesize(world, ScriptedSynthesis(payload))

    store = FactStore(str(world["db"]))
    try:
        arch = copy.deepcopy(world["arch"])
        apply_enrichment_overlay(arch, store, digest_index=DigestIndex.from_store(store))
    finally:
        store.close()

    tour = arch["tours"][0]
    assert tour["id"] == "request-path"
    assert tour["title"] == "The request path"
    assert len(tour["steps"]) == 3
    assert tour["steps"][0]["narration"].startswith("What the reader learns")
    assert tour["steps"][0]["evidence"]["file"] == world["real_file"]


# --- 2. anchors are checked at write time -------------------------------------


def test_a_step_anchored_past_the_end_of_a_file_is_not_written(world):
    """Worse than a missing step: it fails visibly in front of the reader."""
    store = FactStore(str(world["db"]))
    try:
        validator = EvidenceValidator(store, root=POLYGLOT)
    finally:
        store.close()

    bad = _tour(world, steps=3, line=world["real_lines"] + 9999)
    tour, problems = validate_tour(
        bad, known_targets=set(world["components"]), validator=validator
    )
    assert tour is None
    assert any("past the end of" in p for p in problems)


def test_a_step_pointing_at_a_component_that_does_not_exist_is_rejected(world):
    bad = _tour(world, steps=3, target="services/imaginary")
    tour, problems = validate_tour(
        bad, known_targets=set(world["components"]), validator=None
    )
    assert tour is None
    assert any("is not a component in this map" in p for p in problems)


def test_a_tour_with_too_few_valid_steps_is_dropped_entirely(world):
    """One good step is not a walkthrough."""
    raw = _tour(world, steps=2)
    raw["steps"][1]["target"] = "does/not/exist"
    tour, problems = validate_tour(
        raw, known_targets=set(world["components"]), validator=None
    )
    assert tour is None
    assert any("needs at least" in p for p in problems)


def test_a_tour_longer_than_the_cap_is_truncated_and_says_so(world):
    raw = _tour(world, steps=MAX_TOUR_STEPS + 4)
    tour, problems = validate_tour(
        raw, known_targets=set(world["components"]), validator=None
    )
    assert tour is not None
    assert len(tour["steps"]) == MAX_TOUR_STEPS
    assert any("truncated" in p for p in problems)


def test_a_tour_missing_a_title_is_not_written(world):
    raw = _tour(world, steps=3)
    raw["title"] = ""
    tour, problems = validate_tour(
        raw, known_targets=set(world["components"]), validator=None
    )
    assert tour is None
    assert any("no title" in p for p in problems)


def test_rejected_tours_are_reported_rather_than_silently_dropped(world):
    bad = _tour(world, steps=3, line=world["real_lines"] + 9999)
    result, _ = _synthesize(world, ScriptedSynthesis({"tours": [bad], "lenses": []}))
    outcome = result.data["synthesis"]
    assert outcome.tours == []
    assert outcome.rejected_tours
    assert any("tour rejected" in n for n in outcome.notes)


# --- 3. the overlay is no-op when empty ---------------------------------------


def test_a_store_with_no_tour_rows_projects_byte_identically(world):
    """The property both golden corpora depend on."""
    store = FactStore(str(world["db"]))
    try:
        before = json.dumps(
            apply_enrichment_overlay(copy.deepcopy(world["arch"]), store),
            sort_keys=True, default=str,
        )
    finally:
        store.close()
    assert "tours" not in json.loads(before)
    assert before == json.dumps(copy.deepcopy(world["arch"]), sort_keys=True, default=str)


def test_a_tour_row_with_no_steps_does_not_create_an_empty_tours_key(world):
    store = FactStore(str(world["db"]))
    try:
        index = DigestIndex.from_store(store)
        stamp_enrichment(
            store, TOUR_TARGET_KIND, "empty",
            {"id": "empty", "title": "t", "description": "d", "steps": []},
            digest_index=index, commit_sha=None, clock=FIXED_CLOCK,
        )
        store.commit()
        arch = apply_enrichment_overlay(copy.deepcopy(world["arch"]), store, digest_index=index)
    finally:
        store.close()
    assert "tours" not in arch


def test_projected_tours_are_ordered_stably(world):
    payload = {"tours": [
        dict(_tour(world, steps=2), id="zebra", title="Z"),
        dict(_tour(world, steps=2), id="alpha", title="A"),
    ], "lenses": []}
    _synthesize(world, ScriptedSynthesis(payload))
    store = FactStore(str(world["db"]))
    try:
        arch = apply_enrichment_overlay(
            copy.deepcopy(world["arch"]), store, digest_index=DigestIndex.from_store(store)
        )
    finally:
        store.close()
    assert [t["id"] for t in arch["tours"]] == ["alpha", "zebra"]


def test_a_tour_carries_the_commit_it_was_anchored_against(world):
    payload = {"tours": [_tour(world, steps=2)], "lenses": []}
    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT, run_dir=world["run_dir"],
        policy=LadderPolicy(),
    )
    ctx = build_run_context(
        config, invoker_factory=lambda spec: ScriptedSynthesis(payload),
        clock=FIXED_CLOCK,
    )
    commit = ctx.commit_sha
    try:
        run_pipeline(ctx, [SynthesisPhase()])
    finally:
        ctx.store.close()

    store = FactStore(str(world["db"]))
    try:
        arch = apply_enrichment_overlay(
            copy.deepcopy(world["arch"]), store, digest_index=DigestIndex.from_store(store)
        )
    finally:
        store.close()
    tour = arch["tours"][0]
    if commit:
        assert tour["provenance"]["derived_from_commit"] == commit
    else:
        assert "provenance" not in tour


# --- 4. honest gaps are material ----------------------------------------------


def test_the_prompt_treats_honest_gaps_as_material_not_embarrassment():
    prompt = build_synthesis_prompt(
        brief={"identity": "x", "generated": True},
        components=[{"id": "a"}],
        census={"grounded@sonnet": 5, "honest-gap": 1},
        honest_gaps=[{"target_id": "svc", "questions": ["mechanism"]}],
        adjudication=None,
    )
    assert "WHAT COULD NOT BE ESTABLISHED" in prompt
    assert "This is" in prompt and "MATERIAL, not embarrassment" in prompt
    assert "quietly routes around its own" in prompt
    assert "svc" in prompt


def test_disputed_claims_are_named_so_no_tour_step_is_built_on_one():
    prompt = build_synthesis_prompt(
        brief=None, components=[{"id": "a"}], census={}, honest_gaps=[],
        adjudication={"unsupported_claims": [
            {"target_id": "svc", "question": "purpose", "reason": "not in that file"}
        ]},
    )
    assert "WHAT ADJUDICATION DISPUTED" in prompt
    assert "Do not build a tour step on one" in prompt


def test_synthesis_runs_after_adjudication_in_the_registry():
    """A story told over unverified labels narrates mistakes persuasively."""
    from analyzer.enrich.pipeline import PHASE_ORDER

    assert PHASE_ORDER.index("p3_adjudication") < PHASE_ORDER.index("p4_synthesis")


# --- 5. work orders must be able to change something --------------------------


def test_a_look_again_order_is_rejected_with_a_reason():
    orders, rejected = parse_work_orders(
        [{"scope": ["a"], "lens": "look again", "criteria": "be thorough",
          "expected_effect": "", "budget": {"max_targets": 4}}],
        issued_by="P4", cap=3,
    )
    assert orders == []
    assert rejected and "expected_effect must name which instrument moves" in rejected[0]


def test_a_valid_order_names_its_instrument_and_its_bound():
    order = WorkOrder(
        scope=["a", "b"], lens="check the auth boundary",
        criteria="every inbound call names its auth mechanism",
        expected_effect="truth: the identity verdict disagreement rate should fall",
        budget={"max_cost_usd": 1.0, "max_targets": 6},
    )
    assert order.valid
    assert order.instrument == "truth"
    assert order.max_targets == 6


def test_orders_beyond_the_cap_are_reported_rather_than_dropped():
    raw = [
        {"scope": ["a"], "lens": f"lens {i}", "criteria": "c",
         "expected_effect": "utility: x", "budget": {"max_targets": 2}}
        for i in range(5)
    ]
    orders, rejected = parse_work_orders(raw, issued_by="P4", cap=2)
    assert len(orders) == 2
    assert len(rejected) == 3
    assert all("cap of 2" in r for r in rejected)


def test_a_confirmed_lens_becomes_a_capped_work_order(world):
    payload = {
        "tours": [_tour(world, steps=2)],
        "lenses": [
            {"name": "boundary auth", "observation": "no service names its auth",
             "why_it_matters": "the reader is evaluating the boundary",
             "confidence": "high",
             "work_order": {"scope": world["components"][:2], "lens": "auth at edges",
                            "criteria": "each edge names its mechanism",
                            "expected_effect": "truth: identity verdicts",
                            "budget": {"max_cost_usd": 1.0, "max_targets": 4}}},
            {"name": "vague", "observation": "something",
             "work_order": {"lens": "have another look", "criteria": "",
                            "expected_effect": "", "budget": {}}},
        ],
    }
    result, _ = _synthesize(world, ScriptedSynthesis(payload))
    outcome = result.data["synthesis"]

    assert len(outcome.lenses) == 2
    assert len(outcome.work_orders) == 1
    assert outcome.work_orders[0].instrument == "truth"
    assert outcome.rejected_orders
    assert any("work order rejected" in n for n in outcome.notes)


# --- the rest -----------------------------------------------------------------


def test_the_narrative_reuses_the_existing_architecture_pass(world):
    """A second narrative writer would drift from the one the product renders."""
    invoker = ScriptedSynthesis({"tours": [_tour(world, steps=2)], "lenses": []})
    result, _ = _synthesize(world, invoker)
    assert result.data["synthesis"].narrative_written is True
    assert any("architecture-level summary" in p for p in invoker.prompts)

    store = FactStore(str(world["db"]))
    try:
        arch_rows = [r for r in store.enrichment() if r["target_kind"] == "architecture"]
    finally:
        store.close()
    assert len(arch_rows) == 1
    assert arch_rows[0]["payload"]["summary"].startswith("A small polyglot system")


def test_a_failed_narrative_does_not_stop_the_tours(world):
    invoker = ScriptedSynthesis({"tours": [_tour(world, steps=2)], "lenses": []},
                                arch_ok=False)
    result, _ = _synthesize(world, invoker)
    outcome = result.data["synthesis"]
    assert outcome.narrative_written is False
    assert outcome.tours, "a failed narrative must not cost the run its tours"
    assert result.status == "ok"


def test_producing_neither_a_narrative_nor_a_tour_is_a_failed_phase(world):
    invoker = ScriptedSynthesis({"tours": [], "lenses": []}, arch_ok=False)
    result, _ = _synthesize(world, invoker)
    assert result.status == "failed"
    assert any("neither a narrative nor a tour" in n for n in result.notes)


def test_a_dry_run_sizes_the_prompt_and_invokes_nothing(world):
    invoker = ScriptedSynthesis({"tours": [], "lenses": []})
    result, ctx = _synthesize(world, invoker, dry_run=True)
    assert invoker.prompts == []
    assert ctx.ledger == []
    assert result.data["prompt_chars"] > 0


def test_synthesis_is_written_beside_the_run_report(world):
    _synthesize(world, ScriptedSynthesis({"tours": [_tour(world, steps=2)], "lenses": []}))
    written = world["run_dir"] / "synthesis.json"
    assert written.is_file()
    data = json.loads(written.read_text())
    assert data["tours"][0]["id"] == "request-path"
