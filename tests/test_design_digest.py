"""D7: the design digest reaches the pipeline's context assembly.

The enrichment ladder's P1 orientation and P4 synthesis both assemble context
before they ask a model anything. These facts belong in that context: a phase
that knows the subject has a cycle at its heart writes a better brief than one
that does not.

The digest is OFFERED, not woven through. It is a compact block appended to the
existing prompts, and the prompts' own contracts are untouched; prompt redesign
waits for the first real ladder run and its calibration.

Contracts under test:

  1. THE DIGEST IS COMPACT AND BOUNDED. A pathological subject cannot flood a
     prompt with findings.
  2. IT IS PRESENT IN THE ASSEMBLED CONTEXT when the subject has signals.
  3. IT IS ABSENT ENTIRELY when it has none, so no empty section appears.
  4. IT CARRIES THE CAVEAT AND THE TENSION FRAMING, so a phase quoting a finding
     into a brief inherits what the method cannot see.
  5. NO MODEL IS INVOKED to produce or consume it. It is derive-tier arithmetic.
"""

from __future__ import annotations

import json
import os

from analyzer.derive import derive_all
from analyzer.derive.design_signals import (
    METHOD_CAVEAT,
    derive_design_signals,
    design_digest,
)
from analyzer.enrich.orientation import build_orientation_prompt
from analyzer.enrich.synthesis import build_synthesis_prompt
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")


def _signals_for_fixture():
    store = FactStore(":memory:")
    extract_repo(POLYGLOT, store)
    derive_all(store, "polyglot", root_path=POLYGLOT)
    return store, derive_design_signals(store)


# --- 1. compact and bounded ------------------------------------------------------


def test_the_digest_is_bounded_by_construction():
    store, signals = _signals_for_fixture()
    try:
        digest = design_digest(signals, max_findings=3, max_components=2)
        assert digest is not None
        assert len(digest["findings"]) <= 3
        assert len(digest["most_load_bearing"]) <= 2
        # Compact enough to append to a prompt without displacing the subject.
        assert len(json.dumps(digest)) < 8000
    finally:
        store.close()


def test_the_digest_reports_counts_and_the_most_load_bearing_components():
    store, signals = _signals_for_fixture()
    try:
        digest = design_digest(signals)
        assert digest["component_count"] == len(signals.items)
        for kind, count in digest["finding_counts"].items():
            assert count == len(signals.findings_of_kind(kind))
        radii = [c["blast_radius"] for c in digest["most_load_bearing"]]
        assert radii == sorted(radii, reverse=True), "ranked by what rides on it"
    finally:
        store.close()


def test_a_finding_in_the_digest_keeps_its_term_and_its_plain_sentence():
    store, signals = _signals_for_fixture()
    try:
        digest = design_digest(signals)
        assert digest["findings"], "the fixture must produce findings"
        by_term = {f.term for f in signals.findings}
        for entry in digest["findings"]:
            assert entry["term"] in by_term
            assert entry["says"]
            assert entry["term"] != entry["says"]
            assert entry["method"]
    finally:
        store.close()


# --- 2 and 3. present when there are signals, absent when there are none ----------


def test_the_digest_is_none_for_a_store_with_nothing_to_say():
    store = FactStore(":memory:")
    try:
        assert design_digest(derive_design_signals(store)) is None
    finally:
        store.close()


def test_the_orientation_prompt_carries_the_digest_when_signals_exist():
    store, signals = _signals_for_fixture()
    try:
        digest = design_digest(signals)
        prompt = build_orientation_prompt(
            name="polyglot", description="", stats={}, readme="",
            top_components=[], ranking_note="", design=digest,
        )
        assert "HOW THIS SYSTEM IS HELD TOGETHER" in prompt
        assert METHOD_CAVEAT in prompt
        # A real term from the translation table reached the context.
        assert any(f["term"] in prompt for f in digest["findings"])
    finally:
        store.close()


def test_the_orientation_prompt_has_no_design_section_without_a_digest():
    prompt = build_orientation_prompt(
        name="x", description="", stats={}, readme="", top_components=[],
        ranking_note="",
    )
    assert "HOW THIS SYSTEM IS HELD TOGETHER" not in prompt
    assert METHOD_CAVEAT not in prompt
    # And the prompt is still well formed: the contract and the closing
    # instruction survive the absence.
    assert "Return the JSON object now." in prompt


def test_the_synthesis_prompt_carries_the_digest_when_signals_exist():
    store, signals = _signals_for_fixture()
    try:
        digest = design_digest(signals)
        prompt = build_synthesis_prompt(
            brief=None, components=[], census={}, honest_gaps=[],
            adjudication=None, design=digest,
        )
        assert "HOW THIS SYSTEM IS HELD TOGETHER" in prompt
        assert METHOD_CAVEAT in prompt
    finally:
        store.close()


def test_the_synthesis_prompt_has_no_design_section_without_a_digest():
    prompt = build_synthesis_prompt(
        brief=None, components=[], census={}, honest_gaps=[], adjudication=None,
    )
    assert "HOW THIS SYSTEM IS HELD TOGETHER" not in prompt
    assert METHOD_CAVEAT not in prompt


def test_the_phases_assemble_the_digest_from_the_store():
    """The wiring itself: both phases reach the derivation, not a stale blob."""
    import inspect

    from analyzer.enrich.orientation import OrientationPhase
    from analyzer.enrich.synthesis import SynthesisPhase

    assert "design=design_digest(" in inspect.getsource(OrientationPhase.run)
    assert "design=self._design_digest(ctx)" in inspect.getsource(SynthesisPhase.run)
    assert "derive_design_signals" in inspect.getsource(SynthesisPhase._design_digest)


# --- 4. the caveat and the tension framing travel ----------------------------------


def test_the_digest_carries_the_caveat_and_refuses_to_sound_like_a_verdict():
    store, signals = _signals_for_fixture()
    try:
        digest = design_digest(signals)
        assert digest["method_caveat"] == METHOD_CAVEAT
        guidance = digest["how_to_use"]
        # Part 4: every finding is a tension, not a verdict.
        assert "tension" in guidance
        assert "not verdicts" in guidance or "not a defect" in guidance
        # And the two rules a consuming phase must not break.
        assert "no overall score" in guidance
        assert "never zero" in guidance
    finally:
        store.close()


def test_the_digest_offers_no_global_score():
    store, signals = _signals_for_fixture()
    try:
        blob = json.dumps(design_digest(signals))
        for banned in ("architecture_score", "design_score", "overall_score", "grade"):
            assert banned not in blob
    finally:
        store.close()


# --- 5. no model is invoked --------------------------------------------------------


def test_building_the_digest_invokes_no_model():
    """Derive-tier arithmetic. The seam is never reached, so nothing can spend.

    Fail-before: if the digest ever grew a model call, this store, which has no
    invoker attached and no network, would have to fail rather than pass.
    """
    store, signals = _signals_for_fixture()
    try:
        digest = design_digest(signals)
        assert digest is not None
        # Deterministic and repeatable, which a model call would not be.
        again = design_digest(derive_design_signals(store))
        assert json.dumps(digest, sort_keys=True) == json.dumps(again, sort_keys=True)
    finally:
        store.close()
