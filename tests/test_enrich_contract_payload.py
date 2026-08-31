"""T4: the 2a payload. Canned responses only, no model invoked anywhere.

The three canned cases the build plan names, plus the two properties that keep
the contract out of the product:

  1. A canned GROUNDED response evaluates to grounded.
  2. A canned response that omits a required question and declares confusion
     evaluates to escalate carrying E1 and E5.
  3. A canned response whose claim cites a file that does not exist is converted
     to E2 BY THE VALIDATOR, not by the tier admitting anything. This is the
     case a form scorer waves through.
  4. The contract block never reaches a stamped product payload.
  5. The scorer tolerates the new keys and does not gate on them.
"""

from __future__ import annotations

import importlib.util
import json
import os

import pytest

from analyzer.derive import derive_all
from analyzer.enrich.contract import (
    CONTRACT_KEY,
    split_contract_payload,
    state_from_block,
)
from analyzer.enrich.engine import _clean_component_payload, load_scorer
from analyzer.enrich.evidence import EvidenceValidator
from analyzer.enrich.partition import plan_partitions
from analyzer.enrich.prompts import StoreFacts, build_contract_partition_prompt
from analyzer.enrich.provenance import iso_now
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    db = tmp_path_factory.mktemp("payload") / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    store.commit()
    facts = StoreFacts(
        arch, store.capabilities(), store.data_entities(), store.rules(),
        arch.get("relationships", []),
    )
    plan = plan_partitions(arch.get("components", []), arch.get("relationships", []))
    validator = EvidenceValidator(store, root=POLYGLOT)
    real_file = next(f["path"] for f in store.files() if f.get("lines"))
    yield {
        "store": store, "arch": arch, "facts": facts,
        "partition": plan.partitions[0], "validator": validator,
        "real_file": real_file,
    }
    store.close()


# --- the prompt ---------------------------------------------------------------


def test_parser_first_is_stated_as_the_first_question_before_anything_else(world):
    """Design rule 6: parser-first is the first question at every rung, no exceptions."""
    prompt = build_contract_partition_prompt(world["partition"], world["facts"])
    parser_at = prompt.index("parser_first")
    schema_at = prompt.index("Return ONLY a single JSON object")
    grounding_at = prompt.index("THE GROUNDING RULE")
    assert parser_at < grounding_at < schema_at
    assert "FIRST, BEFORE ANYTHING ELSE" in prompt
    # It is required, and an empty list is legitimate: a required key the model
    # is told to leave empty rather than fill invites no invention.
    assert "REQUIRED on every component" in prompt
    assert "An empty list is a legitimate" in prompt


def test_the_prompt_carries_the_grounding_rule_and_the_evidence_shapes(world):
    prompt = build_contract_partition_prompt(world["partition"], world["facts"])
    assert "A claim without evidence you can point at is not an answer" in prompt
    for kind in ("file", "symbol", "edge", "manifest", "doc"):
        assert f'"kind": "{kind}"' in prompt
    # It says the citations are checked, which is true, and says what happens.
    assert "mechanically after you answer" in prompt
    assert "better than citing something you invented" in prompt


def test_each_component_carries_the_exact_question_set_it_will_be_graded_on(world):
    """The rung and the validator must ask the same thing.

    A rung failed for missing a question it was never given would produce
    escalations that teach nothing and cost real money at the next rung.
    """
    prompt = build_contract_partition_prompt(world["partition"], world["facts"])
    assert "REQUIRED_QUESTIONS" in prompt
    body = prompt[prompt.index("COMPONENTS (produce"):]
    blob = body[body.index("["):body.index("RELATIONSHIPS (produce")]
    components = json.loads(blob.rsplit("]", 1)[0] + "]")
    assert components, "the partition should carry components"
    for comp in components:
        questions = comp["REQUIRED_QUESTIONS"]
        assert "purpose" in questions and "next_step" in questions
        # A component with no detected port is never asked about one.
        if not comp.get("port"):
            assert "identity.port" not in questions
        else:
            assert "identity.port" in questions


def test_a_higher_rungs_assignment_and_the_subject_brief_reach_the_prompt(world):
    prompt = build_contract_partition_prompt(
        world["partition"], world["facts"],
        assignment="You are CLOSING NAMED GAPS left by a previous rung.",
        brief={"idiom_warnings": ["comments are in German, code is in English"]},
    )
    assert prompt.startswith("You are CLOSING NAMED GAPS")
    assert "SUBJECT BRIEF" in prompt
    assert "comments are in German" in prompt


# --- canned response 1: grounded ----------------------------------------------


def _answers(questions, path, **overrides):
    block = {
        q: {
            "claim": f"a specific, defensible claim about {q}",
            "status": "answered",
            "evidence": [{"kind": "file", "path": path, "line": 1}],
        }
        for q in questions
    }
    block.update(overrides)
    return block


def test_a_canned_grounded_response_evaluates_to_grounded(world):
    path = world["real_file"]
    questions = ("purpose", "mechanism", "place", "identity.type", "next_step")
    payload = {
        "help_text": "Four sentences of perfectly reasonable prose about it.",
        "data_handled": "User records, session tokens",
        "criticality": "important",
        CONTRACT_KEY: {
            "parser_first": [],
            "answers": _answers(questions, path),
            "self_state": "grounded",
            "confusion": None,
            "substitution_check": "it is the only component that writes the audit log",
        },
    }
    product, block = split_contract_payload(payload)
    state = state_from_block(
        target_kind="component", target_id="c1", rung="sonnet",
        block=block, facts={}, validator=world["validator"],
    )
    assert state.state == "grounded"
    assert state.terminal == "grounded@sonnet"
    assert state.failed == []
    assert state.parser_first == []
    assert CONTRACT_KEY not in product


# --- canned response 2: E1 and E5 ---------------------------------------------


def test_a_canned_response_missing_a_question_and_declaring_confusion_is_e1_and_e5(world):
    path = world["real_file"]
    questions = ("purpose", "place", "identity.type", "next_step")  # mechanism omitted
    block = {
        "parser_first": ["the framework was inferable from the lockfile"],
        "answers": _answers(questions, path),
        "self_state": "escalate",
        "confusion": "the module is named cache but every write goes to Postgres",
        "substitution_check": "it is the only component importing psycopg",
    }
    state = state_from_block(
        target_kind="component", target_id="c1", rung="sonnet",
        block=block, facts={}, validator=world["validator"],
    )
    assert state.state == "escalate"
    by_q = {f.question: f for f in state.failed}
    assert by_q["mechanism"].trigger == "E1"
    assert any(f.trigger == "E5" for f in state.failed)
    assert "named cache but every write goes to Postgres" in state.declared_confusion
    # The parser-first finding survives into the record, which is what feeds the
    # capability cards in the Run Report.
    assert state.parser_first == ["the framework was inferable from the lockfile"]


def test_a_self_reported_substitution_failure_is_e4(world):
    path = world["real_file"]
    questions = ("purpose", "mechanism", "place", "identity.type", "next_step")
    block = {
        "parser_first": [],
        "answers": _answers(questions, path),
        "self_state": "grounded",
        "confusion": None,
        "substitution_check": "nothing unique; this would fit any sibling module",
    }
    state = state_from_block(
        target_kind="component", target_id="c1", rung="sonnet",
        block=block, facts={}, validator=world["validator"],
    )
    assert state.state == "escalate"
    assert [f.trigger for f in state.failed] == ["E4"]
    assert "would fit any sibling" in state.failed[0].note


# --- canned response 3: the validator converts an uncitable claim to E2 -------


def test_an_uncitable_claim_becomes_e2_by_validation_not_by_confession(world):
    """The case a form scorer waves through.

    Nothing about this response is malformed. Every required question is
    answered, every answer carries evidence, the tier declares itself grounded,
    and the prose is confident. It is only ungrounded because the file it cites
    is not in the analyzed set, which no form check would ever notice.
    """
    path = world["real_file"]
    questions = ("purpose", "mechanism", "place", "identity.type", "next_step")
    answers = _answers(questions, path)
    answers["mechanism"] = {
        "claim": "It dispatches through a central command bus in core/dispatch.py.",
        "status": "answered",
        "evidence": [{"kind": "file", "path": "core/dispatch.py", "line": 88}],
    }
    block = {
        "parser_first": [],
        "answers": answers,
        "self_state": "grounded",
        "confusion": None,
        "substitution_check": "only this component owns the dispatch table",
    }

    # Fail-before contrast: with no validator, the tier's confident claim stands.
    unchecked = state_from_block(
        target_kind="component", target_id="c1", rung="sonnet",
        block=block, facts={}, validator=None,
    )
    assert unchecked.state == "grounded"

    checked = state_from_block(
        target_kind="component", target_id="c1", rung="sonnet",
        block=block, facts={}, validator=world["validator"],
    )
    assert checked.state == "escalate"
    assert checked.failed[0].question == "mechanism"
    assert checked.failed[0].trigger == "E2"
    assert "core/dispatch.py" in checked.failed[0].note
    # And the overclaim is on the record.
    assert checked.self_declared == "grounded"


def test_a_relationship_carries_the_reduced_form(world):
    path = world["real_file"]
    block = {
        "parser_first": [],
        "answers": _answers(("flow", "why"), path),
        "self_state": "grounded",
    }
    state = state_from_block(
        target_kind="relationship", target_id="a|b|imports", rung="sonnet",
        block=block, validator=world["validator"],
    )
    assert state.state == "grounded"

    missing = state_from_block(
        target_kind="relationship", target_id="a|b|imports", rung="sonnet",
        block={"answers": _answers(("flow",), path)}, validator=world["validator"],
    )
    assert missing.failed_questions == ["why"]


# --- the contract stays out of the product ------------------------------------


def test_the_contract_block_never_reaches_a_stamped_product_payload(world):
    """Two independent guards, because this is the promise to the product.

    The splitter removes it, and the engine's cleaner would strip it even if the
    splitter were bypassed, because 'contract' is deliberately not in the
    allowlist the cleaner derives from the scorer.
    """
    scorer = load_scorer()
    payload = {
        "help_text": "prose", "data_handled": "things", "criticality": "supporting",
        CONTRACT_KEY: {"answers": {}, "self_state": "grounded"},
    }
    product, block = split_contract_payload(payload)
    assert CONTRACT_KEY not in product
    assert block == {"answers": {}, "self_state": "grounded"}

    # Even without the split, the cleaner strips it.
    cleaned = _clean_component_payload(scorer, payload, iso_now)
    assert CONTRACT_KEY not in cleaned
    assert cleaned["help_text"] == "prose"


def test_a_malformed_payload_degrades_to_no_contract_rather_than_raising():
    assert split_contract_payload(None) == ({}, {})
    assert split_contract_payload("nope") == ({}, {})
    assert split_contract_payload({"help_text": "x", CONTRACT_KEY: "not a dict"}) == (
        {"help_text": "x"}, {}
    )


# --- the scorer tolerates but does not gate -----------------------------------


def _scorer_module():
    spec = importlib.util.spec_from_file_location(
        "_scorer_under_test", "scripts/score-ai-enhancement-quality.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_scorer_tolerates_the_contract_key_without_scoring_it():
    scorer = _scorer_module()
    base = {
        "help_text": "Some prose.", "data_handled": "Records.",
        "criticality": "important", "ai_enhanced_at": "2026-08-21T00:00:00Z",
        "ai_enhance_version": 2,
    }
    assert scorer.validate_component_ai_enhance("c1", base) == []
    with_contract = dict(base, contract={"answers": {}, "self_state": "grounded"})
    assert scorer.validate_component_ai_enhance("c1", with_contract) == []
    # Tolerated, but NOT in the allowlist the engine stamps from, so it cannot
    # ride into the product on the back of being accepted here.
    assert "contract" not in (
        scorer.REQUIRED_COMPONENT_FIELDS | scorer.OPTIONAL_COMPONENT_FIELDS
    )


def test_the_scorer_accepts_honest_gaps_as_a_product_field():
    scorer = _scorer_module()
    payload = {
        "help_text": "Some prose.", "data_handled": "Records.",
        "criticality": "important", "ai_enhanced_at": "2026-08-21T00:00:00Z",
        "ai_enhance_version": 2,
        "honest_gaps": [{"question": "mechanism", "why": "the dispatch table is generated at build time"}],
    }
    assert scorer.validate_component_ai_enhance("c1", payload) == []
    assert "honest_gaps" in scorer.OPTIONAL_COMPONENT_FIELDS


def test_the_scorer_treats_a_complete_named_gap_as_a_truthful_field_result():
    scorer = _scorer_module()
    payload = {
        "criticality": "important", "ai_enhanced_at": "2026-08-21T00:00:00Z",
        "ai_enhance_version": 2,
        "honest_gaps": [
            {"question": question, "why": "the supplied evidence cannot establish it"}
            for question in (
                "purpose", "mechanism", "place", "why_matters", "data_handled"
            )
        ],
    }
    assert scorer.validate_component_ai_enhance("c1", payload) == []
    score, details = scorer.score_component("c1", payload)
    assert "missing_help_text" not in details
    assert "missing_data_handled" not in details
    assert "help_text_length" not in details
    assert score > 0


def test_the_scorer_accepts_relationship_honest_gaps_and_a_gapped_flow():
    scorer = _scorer_module()
    payload = {
        "importance": "primary", "ai_enhanced_at": "2026-08-21T00:00:00Z",
        "honest_gaps": [
            {"question": "flow", "why": "the supplied evidence cannot establish it"}
        ],
    }
    assert scorer.validate_relationship_ai_enhance(("a", "b", "uses"), payload) == []


def test_an_actually_unexpected_field_is_still_rejected():
    """Fail-before contrast: tolerance is a named list, not a hole in the check."""
    scorer = _scorer_module()
    payload = {
        "help_text": "Some prose.", "data_handled": "Records.",
        "criticality": "important", "ai_enhanced_at": "2026-08-21T00:00:00Z",
        "ai_enhance_version": 2, "vibes": "immaculate",
    }
    errors = scorer.validate_component_ai_enhance("c1", payload)
    assert any("unexpected field 'vibes'" in e for e in errors)
