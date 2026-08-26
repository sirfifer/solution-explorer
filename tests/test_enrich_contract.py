"""T3: the completeness contract and the no-AI evidence validator.

The validator is pure code, so every check is unit-tested against a real store
built from the polyglot fixture, INCLUDING each failure mode: missing file,
out-of-range line, absent symbol, unknown edge. Those failure modes are the
point. The calibration measured 83 of 99 components scoring exactly 85.0 on a
form scorer while nothing checked whether one claim was true, and a citation
that points nowhere is exactly what a form scorer waves through.

The contract's own contracts:

  1. The grounding rule bites: an answer with no citation, or with only citations
     that fail validation, is E2 regardless of how confident it reads.
  2. A tier's self-declared state is an input, never the verdict.
  3. Applicability is structural: a component with no port is not asked about one.
  4. Failed questions travel with their trigger and a note, so the next rung
     starts from the named gap.
"""

from __future__ import annotations

import os

import pytest

from analyzer.derive import derive_all
from analyzer.enrich.contract import (
    COMPONENT_QUESTIONS,
    RELATIONSHIP_QUESTIONS,
    TRIGGERS,
    Answer,
    ContractState,
    FailedQuestion,
    build_census,
    evaluate,
    parse_answers,
    required_questions,
    terminal_key,
)
from analyzer.enrich.evidence import EvidenceValidator, normalize_path
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")


@pytest.fixture(scope="module")
def fixture_store(tmp_path_factory):
    """A real store over the polyglot fixture: real files, symbols and edges."""
    db = tmp_path_factory.mktemp("contract") / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    derive_all(store, "polyglot", root_path=POLYGLOT)
    store.commit()
    yield store
    store.close()


@pytest.fixture(scope="module")
def validator(fixture_store):
    return EvidenceValidator(fixture_store, root=POLYGLOT)


@pytest.fixture(scope="module")
def a_real_file(fixture_store):
    """A real indexed file with a known line count and at least one symbol."""
    by_id = {f["id"]: f for f in fixture_store.files()}
    for sym in fixture_store.symbols():
        f = by_id.get(sym["file_id"])
        if f and f.get("lines") and sym.get("name"):
            return f["path"], int(f["lines"]), sym["name"]
    raise AssertionError("polyglot fixture should have a file with symbols")


# --- the validator: what passes -----------------------------------------------


def test_a_real_file_citation_validates(validator, a_real_file):
    path, lines, _ = a_real_file
    assert validator.check({"kind": "file", "path": path}).ok is True
    assert validator.check({"kind": "file", "path": path, "line": lines}).ok is True
    assert validator.check({"kind": "file", "path": path, "line": 1}).ok is True


def test_a_real_symbol_citation_validates(validator, a_real_file):
    path, _, symbol = a_real_file
    assert validator.check({"kind": "symbol", "path": path, "symbol": symbol}).ok is True


def test_a_real_edge_citation_validates(validator, fixture_store):
    edges = fixture_store.edges()
    if not edges:
        pytest.skip("polyglot fixture produced no edges")
    edge = edges[0]
    assert validator.check({
        "kind": "edge",
        "source": edge["source_id"],
        "target": edge["target_id"],
        "edge_type": edge["type"],
    }).ok is True
    # Type-free form: the pair alone is enough.
    assert validator.check({
        "kind": "edge", "source": edge["source_id"], "target": edge["target_id"],
    }).ok is True


def test_paths_are_normalized_before_lookup(validator, a_real_file):
    """A differently-spelled real path is not a fake citation."""
    path, _, _ = a_real_file
    assert validator.check({"kind": "file", "path": "./" + path}).ok is True
    assert validator.check({"kind": "file", "path": "/" + path}).ok is True
    assert validator.check({"kind": "file", "path": path.replace("/", "\\")}).ok is True
    assert validator.check({"kind": "file", "path": os.path.join(POLYGLOT, path)}).ok is True
    assert normalize_path("  ./a/b.py  ") == "a/b.py"


# --- the validator: every failure mode ----------------------------------------


def test_missing_file_fails(validator):
    check = validator.check({"kind": "file", "path": "src/does/not/exist.py"})
    assert check.ok is False
    assert "not in the analyzed file set" in check.reason


def test_out_of_range_line_fails(validator, a_real_file):
    path, lines, _ = a_real_file
    check = validator.check({"kind": "file", "path": path, "line": lines + 5000})
    assert check.ok is False
    assert "past the end of" in check.reason
    assert str(lines) in check.reason


def test_a_non_positive_or_non_numeric_line_fails(validator, a_real_file):
    path, _, _ = a_real_file
    assert validator.check({"kind": "file", "path": path, "line": 0}).ok is False
    assert validator.check({"kind": "file", "path": path, "line": -3}).ok is False
    assert validator.check({"kind": "file", "path": path, "line": "somewhere"}).ok is False


def test_absent_symbol_fails_and_distinguishes_wrong_file_from_no_such_symbol(
    validator, a_real_file, fixture_store
):
    path, _, symbol = a_real_file
    invented = validator.check(
        {"kind": "symbol", "path": path, "symbol": "TotallyInventedSymbolName"}
    )
    assert invented.ok is False
    assert "not in the symbol index" in invented.reason

    # A real symbol cited against the wrong file is a different, more useful
    # failure than a symbol that does not exist at all. "Wrong file" now means
    # the symbol is neither defined nor referenced there: citing a symbol at
    # its USE site is legitimate and is how a relationship contract grounds
    # "X uses Y", so only a file that never mentions it at all is a failure.
    other = next(
        (f["path"] for f in fixture_store.files() if f["path"] != path), None
    )
    if other:
        misplaced = validator.check({"kind": "symbol", "path": other, "symbol": symbol})
        if not misplaced.ok:
            assert "is neither defined nor referenced in" in misplaced.reason


def test_unknown_edge_fails(validator):
    check = validator.check(
        {"kind": "edge", "source": "ghost-a", "target": "ghost-b", "edge_type": "imports"}
    )
    assert check.ok is False
    assert "no edge from" in check.reason


def test_wrong_edge_type_between_a_real_pair_says_so(validator, fixture_store):
    edges = fixture_store.edges()
    if not edges:
        pytest.skip("polyglot fixture produced no edges")
    edge = edges[0]
    check = validator.check({
        "kind": "edge",
        "source": edge["source_id"],
        "target": edge["target_id"],
        "edge_type": "definitely-not-a-real-edge-type",
    })
    assert check.ok is False
    assert "connected by another edge type" in check.reason


def test_malformed_and_unknown_kinds_fail_without_raising(validator):
    assert validator.check("just a string").ok is False
    assert validator.check(None).ok is False
    assert validator.check({"kind": "vibes", "path": "x.py"}).ok is False
    assert validator.check({"kind": "file"}).ok is False
    assert validator.check({"kind": "symbol", "path": "x.py"}).ok is False
    assert validator.check({"kind": "edge", "source": "a"}).ok is False


def test_one_good_citation_grounds_a_claim(validator, a_real_file):
    """Requiring every citation to be perfect would punish adding a weak second one."""
    path, _, _ = a_real_file
    items = [
        {"kind": "file", "path": "nowhere/at/all.py"},
        {"kind": "file", "path": path},
    ]
    assert validator.any_valid(items) is True
    assert len(validator.failures(items)) == 1


def test_a_validator_over_an_empty_store_rejects_everything(a_real_file):
    """Fail-before contrast: without the store index nothing can be grounded."""
    path, _, _ = a_real_file
    empty = EvidenceValidator(FactStore(":memory:"), root=POLYGLOT)
    assert empty.check({"kind": "file", "path": path}).ok is False


# --- required questions -------------------------------------------------------


def test_a_component_is_only_asked_what_it_can_answer():
    bare = required_questions("component", {})
    assert bare == ("purpose", "mechanism", "place", "identity.type", "next_step")
    assert "identity.port" not in bare

    rich = required_questions(
        "component", {"framework": "FastAPI", "port": 8000, "language": "python"}
    )
    assert set(rich) == set(COMPONENT_QUESTIONS)
    # Canonical order, so censuses are comparable across targets.
    assert list(rich) == [q for q in COMPONENT_QUESTIONS if q in set(rich)]


def test_empty_and_unknown_attributes_do_not_count_as_present():
    for value in ("", "  ", "None", "unknown", None):
        assert "identity.framework" not in required_questions(
            "component", {"framework": value}
        )


def test_relationships_carry_the_reduced_form():
    assert required_questions("relationship", {}) == RELATIONSHIP_QUESTIONS


# --- evaluation ---------------------------------------------------------------


def _grounded_answers(path: str) -> dict:
    cite = [{"kind": "file", "path": path}]
    return {
        q: {"claim": f"a real answer for {q}", "status": "answered", "evidence": cite}
        for q in ("purpose", "mechanism", "place", "identity.type", "next_step")
    }


def test_a_fully_answered_and_cited_component_is_grounded(validator, a_real_file):
    path, _, _ = a_real_file
    state = evaluate(
        target_kind="component",
        target_id="c1",
        rung="sonnet",
        answers=_grounded_answers(path),
        facts={},
        validator=validator,
    )
    assert state.state == "grounded"
    assert state.failed == []
    assert state.terminal == "grounded@sonnet"


def test_a_missing_required_answer_is_e1(validator, a_real_file):
    path, _, _ = a_real_file
    answers = _grounded_answers(path)
    del answers["mechanism"]
    state = evaluate(
        target_kind="component", target_id="c1", rung="sonnet",
        answers=answers, facts={}, validator=validator,
    )
    assert state.state == "escalate"
    assert state.failed_questions == ["mechanism"]
    assert state.triggers == ["E1"]
    assert "no answer was produced" in state.failed[0].note


def test_an_uncited_answer_is_e2_however_confident_it_reads(validator, a_real_file):
    """The grounding rule, which is the whole reason the contract is enforceable."""
    path, _, _ = a_real_file
    answers = _grounded_answers(path)
    answers["place"] = {
        "claim": "This is unambiguously the central orchestrator of the entire system.",
        "status": "answered",
        "evidence": [],
    }
    state = evaluate(
        target_kind="component", target_id="c1", rung="sonnet",
        answers=answers, facts={}, validator=validator,
    )
    assert state.state == "escalate"
    assert state.failed[0].question == "place"
    assert state.failed[0].trigger == "E2"
    assert state.failed[0].note == "the answer cites no evidence"


def test_an_answer_whose_citations_all_fail_validation_is_e2(validator, a_real_file):
    path, _, _ = a_real_file
    answers = _grounded_answers(path)
    answers["purpose"] = {
        "claim": "Handles the request lifecycle.",
        "status": "answered",
        "evidence": [{"kind": "file", "path": "invented/module.py", "line": 42}],
    }
    state = evaluate(
        target_kind="component", target_id="c1", rung="sonnet",
        answers=answers, facts={}, validator=validator,
    )
    assert state.failed[0].trigger == "E2"
    assert "no citation checked out" in state.failed[0].note
    assert "not in the analyzed file set" in state.failed[0].note


def test_uncertain_becomes_e2_and_dropped_becomes_e1(validator, a_real_file):
    path, _, _ = a_real_file
    answers = _grounded_answers(path)
    answers["purpose"] = {"claim": "maybe a cache", "status": "uncertain", "reason": "no docs"}
    answers["next_step"] = {"claim": "", "status": "dropped", "reason": "nothing to point at"}
    state = evaluate(
        target_kind="component", target_id="c1", rung="sonnet",
        answers=answers, facts={}, validator=validator,
    )
    by_q = {f.question: f for f in state.failed}
    assert by_q["purpose"].trigger == "E2"
    assert by_q["purpose"].note == "no docs"
    assert by_q["next_step"].trigger == "E1"


def test_declared_confusion_is_e5_with_the_confusion_named(validator, a_real_file):
    path, _, _ = a_real_file
    state = evaluate(
        target_kind="component", target_id="c1", rung="sonnet",
        answers=_grounded_answers(path), facts={}, validator=validator,
        declared_confusion="the docstring says cache, the code writes to Postgres",
    )
    assert state.state == "escalate"
    assert state.failed[-1].trigger == "E5"
    assert "writes to Postgres" in state.failed[-1].note
    assert state.declared_confusion


def test_a_tiers_self_declaration_is_recorded_but_never_the_verdict(validator, a_real_file):
    """A tier claiming grounded over a citation that points nowhere still escalates."""
    path, _, _ = a_real_file
    answers = _grounded_answers(path)
    answers["purpose"]["evidence"] = [{"kind": "file", "path": "not/real.py"}]
    state = evaluate(
        target_kind="component", target_id="c1", rung="sonnet",
        answers=answers, facts={}, validator=validator,
        self_declared="grounded",
    )
    assert state.self_declared == "grounded"
    assert state.state == "escalate"


def test_strict_identity_raises_e3_only_when_asked(validator, a_real_file):
    path, _, _ = a_real_file
    answers = _grounded_answers(path)
    answers["identity.type"] = {
        "claim": "a background worker", "status": "answered",
        "evidence": [{"kind": "file", "path": path}],
    }
    facts = {"type": "api-server"}
    lenient = evaluate(
        target_kind="component", target_id="c1", rung="sonnet",
        answers=answers, facts=facts, validator=validator,
    )
    assert lenient.state == "grounded"

    strict = evaluate(
        target_kind="component", target_id="c1", rung="sonnet",
        answers=answers, facts=facts, validator=validator, strict_identity=True,
    )
    assert strict.triggers == ["E3"]
    assert "api-server" in strict.failed[0].note


def test_history_records_what_the_previous_rung_concluded(validator, a_real_file):
    path, _, _ = a_real_file
    first = evaluate(
        target_kind="component", target_id="c1", rung="sonnet",
        answers={}, facts={}, validator=validator,
    )
    assert first.state == "escalate"
    second = evaluate(
        target_kind="component", target_id="c1", rung="opus",
        answers=_grounded_answers(path), facts={}, validator=validator,
        previous=first,
    )
    assert second.state == "grounded"
    assert second.terminal == "grounded@opus"
    assert second.history == ["sonnet:escalate"]


# --- answer coercion ----------------------------------------------------------


def test_a_bare_string_answer_is_coerced_rather_than_crashing():
    """A tier drifting to a bare string must not lose the whole partition."""
    answers = parse_answers({"purpose": "it handles auth"})
    assert answers["purpose"].claim == "it handles auth"
    assert answers["purpose"].evidence == []
    # No evidence means E2, which is the honest outcome for an uncited claim.
    assert Answer.from_any(12345).status == "dropped"
    assert parse_answers("not a dict") == {}


def test_an_unknown_status_falls_back_to_answered_and_is_then_graded():
    assert Answer.from_any({"claim": "x", "status": "definitely-fine"}).status == "answered"


# --- census -------------------------------------------------------------------


def test_the_census_counts_terminal_states_and_surfaces_the_unresolved():
    states = [
        ContractState("component", "a", state="grounded", rung="sonnet"),
        ContractState("component", "b", state="grounded", rung="sonnet"),
        ContractState("component", "c", state="grounded", rung="opus"),
        ContractState("component", "d", state="honest_gap", rung="fable"),
        ContractState("component", "e", state="escalate", rung="fable"),
    ]
    census = build_census(states)
    assert census.by_state == {
        "escalate@fable": 1,
        "grounded@opus": 1,
        "grounded@sonnet": 2,
        "honest-gap": 1,
    }
    assert census.total == 5
    assert census.grounded == 3
    assert census.grounded_fraction() == 0.6
    assert [s.target_id for s in census.honest_gaps] == ["d"]
    # A ladder that stopped with work outstanding is a different product, and
    # the determination has to be able to see that.
    assert [s.target_id for s in census.unresolved] == ["e"]


def test_terminal_keys_match_the_design_vocabulary():
    assert terminal_key("grounded", "sonnet") == "grounded@sonnet"
    assert terminal_key("grounded", "opus") == "grounded@opus"
    assert terminal_key("grounded", "fable") == "grounded@fable"
    assert terminal_key("honest_gap", "fable") == "honest-gap"


def test_every_trigger_in_the_design_is_defined():
    assert sorted(TRIGGERS) == ["E1", "E2", "E3", "E4", "E5"]


def test_a_contract_state_round_trips_through_its_dict():
    state = ContractState(
        "component", "a", state="escalate", rung="sonnet",
        attempt_ref="row-7", parser_first=["the import was aliased"],
    )
    state.failed.append(FailedQuestion("purpose", "E2", "no citation"))
    restored = ContractState.from_dict(state.to_dict())
    assert restored.to_dict() == state.to_dict()


# --- deterministic-first: the parser's answers are not the model's to fail -----


def test_a_parser_known_identity_attribute_cannot_escalate():
    """identity.* the analyzer already detected never climbs the ladder.

    The question exists only because the parser found the attribute, the prompt
    hands the value over, and strict_identity is off by default so nothing
    checks the model's restatement. On the 2026-08-25 unamentis-ios run this
    path sent identity.framework to Opus twice, at ~17.5x the per-item cost of
    the rung that already had the answer, to re-derive a fact and discard it.
    """
    from analyzer.enrich.contract import evaluate

    facts = {"framework": "SwiftUI", "language": "swift", "type": "module"}
    # The model says nothing useful about any of them.
    state = evaluate(
        target_kind="component",
        target_id="c1",
        rung="sonnet",
        answers={
            "purpose": {"claim": "does a thing", "status": "answered",
                        "evidence": [{"kind": "file", "path": "a.swift"}]},
            "mechanism": {"claim": "via a thing", "status": "answered",
                          "evidence": [{"kind": "file", "path": "a.swift"}]},
            "place": {"claim": "in the app", "status": "answered",
                      "evidence": [{"kind": "file", "path": "a.swift"}]},
            "next_step": {"claim": "read a.swift", "status": "answered",
                          "evidence": [{"kind": "file", "path": "a.swift"}]},
            "identity.framework": {"claim": "", "status": "uncertain"},
            "identity.language": {"claim": "", "status": "uncertain"},
            "identity.type": {"claim": "", "status": "uncertain"},
        },
        facts=facts,
        validator=None,
    )
    climbed = {str(f) for f in state.failed_questions}
    assert not any(q.startswith("identity.") for q in climbed), (
        f"a parser-known identity attribute escalated: {climbed}"
    )
    assert state.state == "grounded"


def test_a_real_question_still_escalates_when_the_parser_cannot_help():
    """The exemption is narrow: only identity, only when the parser has it."""
    from analyzer.enrich.contract import evaluate

    state = evaluate(
        target_kind="component",
        target_id="c1",
        rung="sonnet",
        answers={"purpose": {"claim": "", "status": "uncertain"}},
        facts={"framework": "SwiftUI"},
        validator=None,
    )
    assert state.state == "escalate"
    assert "purpose" in {str(f) for f in state.failed_questions}
    # The narrowness matters: identity.framework is settled by the parser and
    # must be absent, while identity.type is not in facts and must still climb.
    climbed = {str(f) for f in state.failed_questions}
    assert "identity.framework" not in climbed
    assert "identity.type" in climbed


def test_an_identity_attribute_the_parser_lacks_is_not_exempt():
    from analyzer.enrich.contract import _parser_settles

    assert _parser_settles("identity.framework", {"framework": "SwiftUI"}) is True
    assert _parser_settles("identity.framework", {"framework": ""}) is False
    assert _parser_settles("identity.framework", {"framework": "unknown"}) is False
    assert _parser_settles("identity.framework", {}) is False
    assert _parser_settles("purpose", {"purpose": "anything"}) is False
    assert _parser_settles("mechanism", {"mechanism": "x"}) is False


# --- citing the analyzer's own facts ------------------------------------------


def test_a_claim_from_the_analyzers_own_numbers_can_be_cited(fixture_store):
    """The gap that produced a 64.1% grounding disagreement rate.

    A component's fact block says inbound_edges: 17. A tier that reports "17
    components depend on this" is stating something TRUE and taken from the
    prompt it was given, but before "fact" evidence existed the only citable
    things were files, symbols and edges, and two edges cannot support a claim
    about seventeen. The claim was correct and unciteable, so it read as
    ungrounded, escalated to a more expensive tier that could not fix it
    either, and was then counted as a disagreement.
    """
    from analyzer.enrich.evidence import EvidenceValidator

    v = EvidenceValidator(fixture_store, root=POLYGLOT)
    v.attach_facts({"svc": {"inbound_edges": 17, "file_count": 4}})

    ok = v.check({"kind": "fact", "component": "svc", "field": "inbound_edges"})
    assert ok.ok is True
    assert ok.detail["value"] == 17


def test_fact_evidence_is_not_a_free_text_escape_hatch(fixture_store):
    """It must be able to fail, or it grounds everything and checks nothing."""
    from analyzer.enrich.evidence import EvidenceValidator

    v = EvidenceValidator(fixture_store, root=POLYGLOT)
    v.attach_facts({"svc": {"inbound_edges": 17}})

    # A field the analyzer never produces.
    assert v.check({"kind": "fact", "component": "svc", "field": "vibes"}).ok is False
    # A field not present for THIS component.
    missing = v.check({"kind": "fact", "component": "svc", "field": "framework"})
    assert missing.ok is False
    assert "produced no" in missing.reason
    # A component that does not exist.
    assert v.check({"kind": "fact", "component": "ghost", "field": "file_count"}).ok is False
    # Malformed.
    assert v.check({"kind": "fact", "component": "svc"}).ok is False
    assert v.check({"kind": "fact", "field": "file_count"}).ok is False


def test_fact_evidence_fails_closed_when_no_facts_were_attached(fixture_store):
    """A validator with no fact blocks must reject, never wave through."""
    from analyzer.enrich.evidence import EvidenceValidator

    v = EvidenceValidator(fixture_store, root=POLYGLOT)
    assert v.check({"kind": "fact", "component": "svc", "field": "file_count"}).ok is False


def test_the_validator_still_leaves_sufficiency_to_adjudication(fixture_store):
    """Citing a real fact does not make a wrong claim right.

    The component below reports file_count 0. A tier claiming "18 Swift files"
    while citing that field produces a VALID citation and a false claim, which
    is exactly the split the design asks for: the validator proves the pointer
    is real, adjudication judges whether the prose matches it.
    """
    from analyzer.enrich.evidence import EvidenceValidator

    v = EvidenceValidator(fixture_store, root=POLYGLOT)
    v.attach_facts({"audio": {"file_count": 0}})
    check = v.check({"kind": "fact", "component": "audio", "field": "file_count"})
    assert check.ok is True
    assert check.detail["value"] == 0, (
        "the real value must travel with the check so adjudication can compare"
    )
