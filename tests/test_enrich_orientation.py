"""T7: orientation. Canned responses, no model invoked.

The brief does two jobs nothing else in the ladder can do, and both are tested:

  1. IT SETS THE BAR P5 ANSWERS. The coupling is types, not convention: P1 emits
     Criterion objects and P5 consumes those same objects. A criterion that
     reached the brief is a criterion the determination has to answer.
  2. IT WARNS THE LADDER BEFORE THE LADDER STARTS. Idiom warnings reach the 2a
     prompt, so a rung meeting an unexplained convention is not surprised by it.

Plus the failure posture: orientation failing hands down a brief that SAYS it is
not a brief, rather than an empty document that reads like a real one.
"""

from __future__ import annotations

import json
import os

import pytest

from analyzer.derive import derive_all
from analyzer.enrich.contract import CONTRACT_KEY
from analyzer.enrich.engine import InvokeResult
from analyzer.enrich.ladder import LadderPhase, _brief_dict
from analyzer.enrich.orientation import (
    BRIEF_TARGET_KIND,
    Criterion,
    CriterionVerdict,
    OrientationPhase,
    SubjectBrief,
    load_brief,
    universal_criteria,
)
from analyzer.enrich.pipeline import (
    LadderConfig,
    LadderPolicy,
    build_run_context,
    run_pipeline,
)
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")
FIXED_CLOCK = lambda: "2026-08-21T00:00:00+00:00"  # noqa: E731

GOOD_BRIEF = {
    "identity": "A tiny polyglot solution used to exercise the analyzer across "
    "every supported language.",
    "audience": "An engineer deciding whether the analyzer handles their stack.",
    "what_matters": ["language coverage", "the component boundaries"],
    "criteria": [
        {"id": "s1", "statement": "Every language present is named on the component "
         "that carries it.", "why": "Language coverage is the whole point of this "
         "subject.", "how_to_check": "Compare stats.languages against component "
         "language fields."},
        {"id": "s2", "statement": "The service boundary between web and api is "
         "described from both sides.", "why": "It is the only real edge here.",
         "how_to_check": "Both components' place answers mention it."},
    ],
    "weighting_adjustments": ["spend less on the fixture's leaf packages"],
    "idiom_warnings": [
        "the rubylib package is deliberately empty of logic; it exists to prove "
        "the ruby parser runs"
    ],
}


@pytest.fixture
def world(tmp_path):
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    derive_all(store, "polyglot", root_path=POLYGLOT)
    store.commit()
    store.close()
    return {"db": db, "run_dir": tmp_path / "run"}


class CannedOrientation:
    def __init__(self, payload, ok=True, text=None):
        self.payload = payload
        self.ok = ok
        self.text = text
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if not self.ok:
            return InvokeResult(ok=False, text="", error="the model was unavailable")
        body = self.text if self.text is not None else json.dumps(self.payload)
        return InvokeResult(ok=True, text=body, cost_usd=0.02,
                            usage={"input_tokens": 900, "output_tokens": 120})


def _orient(world, invoker, dry_run=False):
    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT, run_dir=world["run_dir"],
        policy=LadderPolicy(), dry_run=dry_run,
    )
    ctx = build_run_context(config, invoker_factory=lambda spec: invoker,
                            clock=FIXED_CLOCK)
    try:
        run_pipeline(ctx, [OrientationPhase()])
        return ctx.results["p1_orientation"], ctx
    finally:
        ctx.store.close()


# --- 1. the brief sets the bar ------------------------------------------------


def test_a_good_brief_carries_subject_criteria_plus_the_universal_gates(world):
    invoker = CannedOrientation(GOOD_BRIEF)
    result, ctx = _orient(world, invoker)

    assert result.status == "ok"
    brief = result.data["brief"]
    assert brief.generated is True
    assert brief.identity.startswith("A tiny polyglot solution")
    assert [c.id for c in brief.subject_criteria] == ["s1", "s2"]

    # Universal gates are APPENDED, never substituted for: a brief with good
    # subject criteria still has to clear the floor.
    universal_ids = {c.id for c in universal_criteria()}
    assert universal_ids.issubset({c.id for c in brief.criteria})
    assert all(c.universal for c in brief.criteria if c.id in universal_ids)
    assert len(brief.criteria) == 2 + len(universal_criteria())


def test_the_criteria_p5_consumes_are_the_objects_p1_produced(world):
    """The coupling is types, not convention."""
    invoker = CannedOrientation(GOOD_BRIEF)
    result, _ = _orient(world, invoker)
    brief = result.data["brief"]

    for criterion in brief.criteria:
        assert isinstance(criterion, Criterion)
        # A verdict is produced AGAINST a criterion and carries its id, so a
        # criterion with no verdict is a structurally visible omission.
        verdict = CriterionVerdict(
            criterion_id=criterion.id, statement=criterion.statement
        )
        assert verdict.criterion_id == criterion.id
        assert verdict.verdict == "unknown"


def test_the_universal_gates_are_answerable_rather_than_wishes():
    """A criterion nothing could violate produces a verdict that means nothing."""
    for criterion in universal_criteria():
        assert criterion.statement
        assert criterion.why
        assert criterion.how_to_check, f"{criterion.id} has no way to check it"


def test_the_prompt_demands_criteria_that_could_fail(world):
    invoker = CannedOrientation(GOOD_BRIEF)
    _orient(world, invoker)
    prompt = invoker.prompts[0]
    assert "write bars that could FAIL" in prompt
    assert '"The map is accurate" is not a criterion' in prompt
    assert "how_to_check" in prompt
    assert "Do not bake inventory counts into a criterion" in prompt
    assert "test of whether the MAP faithfully explains" in prompt
    assert "reference-recording/configuration surface" in prompt


def test_parser_owned_inventory_counts_are_not_promoted_to_release_gates(world):
    payload = dict(GOOD_BRIEF)
    payload["criteria"] = [{
        "id": "s1",
        "statement": (
            "Every one of the 8 components and 11 languages appears in the map, "
            "and port 8000 is named."
        ),
        "why": "coverage",
        "how_to_check": "use the current mechanical inventory",
    }]
    result, _ = _orient(world, CannedOrientation(payload))

    criterion = result.data["brief"].subject_criteria[0]
    assert criterion.statement == (
        "Every component and language appears in the map, and port 8000 is named."
    )
    assert any("parser-owned inventory counts" in note
               for note in result.data["brief"].notes)


def test_the_brief_is_stored_in_the_store_and_beside_the_run_report(world):
    invoker = CannedOrientation(GOOD_BRIEF)
    _orient(world, invoker)

    store = FactStore(str(world["db"]))
    try:
        rows = [r for r in store.enrichment() if r["target_kind"] == BRIEF_TARGET_KIND]
        assert len(rows) == 1
        restored = load_brief(store)
    finally:
        store.close()
    assert restored is not None
    assert restored.identity == GOOD_BRIEF["identity"]
    assert [c.id for c in restored.subject_criteria] == ["s1", "s2"]

    written = world["run_dir"] / "subject-brief.json"
    assert written.is_file()
    on_disk = json.loads(written.read_text())
    assert on_disk["identity"] == GOOD_BRIEF["identity"]
    assert on_disk["idiom_warnings"] == GOOD_BRIEF["idiom_warnings"]


# --- 2. the brief warns the ladder --------------------------------------------


def test_orientation_sees_the_ranking_and_says_when_activity_is_missing(world):
    invoker = CannedOrientation(GOOD_BRIEF)
    _orient(world, invoker)
    prompt = invoker.prompts[0]
    assert "MOST NAVIGATIONALLY IMPORTANT COMPONENTS" in prompt
    assert "importance_band" in prompt
    # The fixture has no git history, and the prompt says so rather than letting
    # the ranking read as if activity had been considered.
    assert "no git activity data" in prompt


def test_bounded_canary_sets_slice_criteria_without_weakening_quality(world):
    invoker = CannedOrientation(GOOD_BRIEF)
    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT, run_dir=world["run_dir"],
        policy=LadderPolicy(), max_partitions=1,
    )
    ctx = build_run_context(
        config, invoker_factory=lambda spec: invoker, clock=FIXED_CLOCK
    )
    try:
        expected_scope = ctx.attempted_scope()
        run_pipeline(ctx, [OrientationPhase()])
    finally:
        ctx.store.close()

    prompt = invoker.prompts[0]
    assert "bounded validation canary" in prompt
    assert "selected slice, not full-system coverage" in prompt
    assert "Do not weaken evidence, grounding, specificity, or usefulness" in prompt
    assert "EXACT SELECTED SLICE" in prompt
    assert "reserve part of its sample" in prompt
    for target_id in (*expected_scope["components"], *expected_scope["relationships"]):
        assert target_id in prompt


def test_idiom_warnings_reach_the_rung_that_has_to_read_the_code(world):
    """The whole point of declaring confusion up front."""
    brief = SubjectBrief.from_dict(dict(GOOD_BRIEF, generated=True))

    class FakeCtx:
        def phase_data(self, name):
            return {"brief": brief}

    passed = _brief_dict(FakeCtx())
    assert passed is not None
    assert passed["idiom_warnings"] == GOOD_BRIEF["idiom_warnings"]
    assert passed["identity"] == GOOD_BRIEF["identity"]
    # The criteria are P5's business and would be noise in a per-partition prompt.
    assert "criteria" not in passed


def test_a_brief_that_was_never_generated_is_not_passed_down_as_if_it_were():
    fallback = SubjectBrief.fallback("the model was unavailable")

    class FakeCtx:
        def phase_data(self, name):
            return {"brief": fallback}

    assert _brief_dict(FakeCtx()) is None

    class NoPhase:
        def phase_data(self, name):
            return {}

    assert _brief_dict(NoPhase()) is None


def test_the_ladder_carries_the_brief_into_its_prompts(world):
    """End to end: P1 writes a brief, P2's prompt contains the warning."""
    seen = []

    def factory(spec):
        def invoke(prompt):
            seen.append(prompt)
            if "orienting an automated enrichment pipeline" in prompt:
                return InvokeResult(ok=True, text=json.dumps(GOOD_BRIEF), cost_usd=0.01)
            return InvokeResult(
                ok=True,
                text=json.dumps({"components": {}, "relationships": {}}),
                cost_usd=0.01,
            )

        return invoke

    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT, run_dir=world["run_dir"],
        policy=LadderPolicy(),
    )
    ctx = build_run_context(config, invoker_factory=factory, clock=FIXED_CLOCK)
    try:
        run_pipeline(ctx, [OrientationPhase(), LadderPhase()])
    finally:
        ctx.store.close()

    ladder_prompts = [p for p in seen if "SUBJECT BRIEF" in p]
    assert ladder_prompts, "the ladder prompt should carry the brief"
    assert "the rubylib package is deliberately empty of logic" in ladder_prompts[0]
    assert CONTRACT_KEY in ladder_prompts[0] or "contract" in ladder_prompts[0]


# --- failure posture ----------------------------------------------------------


def test_an_unavailable_model_produces_a_brief_that_says_it_is_not_a_brief(world):
    invoker = CannedOrientation(None, ok=False)
    result, _ = _orient(world, invoker)

    assert result.status == "failed"
    assert "NOT ORIENTED" in result.notes[0]
    brief = result.data["brief"]
    assert brief.generated is False
    assert brief.identity == ""
    assert brief.notes and "NO SUBJECT BRIEF" in brief.notes[0]
    # The floor still applies, so the determination has something real to answer.
    assert [c.id for c in brief.criteria] == [c.id for c in universal_criteria()]


def test_unparseable_output_degrades_the_same_way(world):
    invoker = CannedOrientation(None, text="I would be happy to help you with that!")
    result, _ = _orient(world, invoker)
    assert result.status == "failed"
    assert "unparseable" in result.notes[0]
    assert result.data["brief"].generated is False


def test_a_brief_with_no_identity_is_treated_as_no_brief(world):
    """Fail-before contrast: a well-formed empty document must not read as a brief."""
    invoker = CannedOrientation({"criteria": [], "identity": "", "audience": ""})
    result, _ = _orient(world, invoker)
    assert result.status == "failed"
    assert "no subject identity" in result.notes[0]


def test_a_degraded_brief_is_still_persisted_so_the_report_can_say_so(world):
    invoker = CannedOrientation(None, ok=False)
    _orient(world, invoker)
    store = FactStore(str(world["db"]))
    try:
        restored = load_brief(store)
    finally:
        store.close()
    assert restored is not None
    assert restored.generated is False
    assert "NO SUBJECT BRIEF" in restored.notes[0]


def test_a_dry_run_sizes_the_prompt_and_invokes_nothing(world):
    invoker = CannedOrientation(GOOD_BRIEF)
    result, ctx = _orient(world, invoker, dry_run=True)
    assert invoker.prompts == []
    assert ctx.ledger == []
    assert result.status == "ok"
    assert result.data["prompt_chars"] > 0


def test_a_criterion_coerces_from_a_bare_string_without_losing_it():
    """A model that returns a list of sentences still produces answerable criteria."""
    brief = SubjectBrief.from_dict({
        "identity": "x", "criteria": ["every service names its inbound protocol"],
    })
    assert len(brief.criteria) == 1
    assert brief.criteria[0].statement == "every service names its inbound protocol"
    assert brief.criteria[0].id == "c1"
