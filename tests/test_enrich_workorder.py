"""T9: work orders and descent. Scripted responses, no model invoked.

The two contracts the build plan names, plus the one that matters most in
practice:

  1. AN ORDER'S RESULTS CHANGE THE CENSUS. It runs as an ordinary scoped pass
     through the same absorb path and the same contract, not down a private
     route with its own rules.
  2. AN ORDER CANNOT SPAWN FURTHER ORDERS. One level, enforced structurally
     rather than by asking politely.
  3. AN ORDER THAT CHANGED NOTHING SAYS SO. "We did more work" is not the same
     claim as "the map got better", and a determination that cannot tell them
     apart will keep buying rounds that do nothing.
"""

from __future__ import annotations

import json
import os

import pytest

from analyzer.derive import derive_all
from analyzer.enrich.adjudicate import AdjudicationOutcome, SpotCheck
from analyzer.enrich.contract import (
    CONTRACT_KEY,
    ContractState,
    FailedQuestion,
    required_questions,
)
from analyzer.enrich.engine import InvokeResult
from analyzer.enrich.ladder import CONTRACT_TARGET_KIND, LadderOutcome
from analyzer.enrich.partition import flatten_components
from analyzer.enrich.pipeline import (
    BudgetMeter,
    LadderConfig,
    LadderPolicy,
    PhaseResult,
    build_run_context,
)
from analyzer.enrich.workorder import (
    WORK_ORDER_ASSIGNMENT,
    WORK_ORDER_TARGET_BATCH,
    WorkOrder,
    execute_work_order,
    make_descender,
)
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")
FIXED_CLOCK = lambda: "2026-08-21T00:00:00+00:00"  # noqa: E731


@pytest.fixture
def world(tmp_path):
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    store.commit()
    flat = [c for c in flatten_components(arch.get("components", [])) if c.get("id")]
    real_file = next(f["path"] for f in store.files() if f.get("lines"))
    store.close()
    return {
        "db": db, "run_dir": tmp_path / "run", "arch": arch,
        "components": [c["id"] for c in flat],
        "relationship": next(
            f"{r['source']}|{r['target']}|{r['type']}"
            for r in arch.get("relationships", [])
        ),
        "facts_by_id": {c["id"]: c for c in flat},
        "real_file": real_file,
    }


class ScriptedOrder:
    """Answers a scoped work-order prompt; optionally proposes further orders."""

    def __init__(self, world, *, ground=True, propose_orders=False, ok=True,
                 duplicate=False):
        self.world = world
        self.ground = ground
        self.propose_orders = propose_orders
        self.ok = ok
        self.duplicate = duplicate
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if not self.ok:
            return InvokeResult(ok=False, text="", error="unavailable")
        ids = [cid for cid in self.world["components"] if f'"{cid}"' in prompt]
        components = {}
        for cid in ids:
            questions = list(required_questions(
                "component", self.world["facts_by_id"].get(cid, {})
            ))
            if not self.ground:
                questions = [q for q in questions if q != "mechanism"]
            components[cid] = {
                "help_text": f"A revised four-sentence account of {cid}.",
                "data_handled": "records", "criticality": "important",
                CONTRACT_KEY: {
                    "parser_first": [],
                    "answers": {
                        q: {"claim": f"through the lens: {q}", "status": "answered",
                            "evidence": [{"kind": "file",
                                          "path": self.world["real_file"], "line": 1}]}
                        for q in questions
                    },
                    "self_state": "grounded" if self.ground else "escalate",
                    "substitution_check": f"only {cid} does this",
                },
            }
        body = {"components": components, "relationships": {}}
        if self.duplicate and ids:
            cid = ids[0]
            duplicate = {
                "i": cid,
                "q": {"purpose": {"t": "through the lens", "e": [0]}},
            }
            body["components"] = [duplicate, dict(duplicate)]
        if self.propose_orders:
            body["work_orders"] = [{
                "scope": self.world["components"][:1], "lens": "one more look",
                "criteria": "c", "expected_effect": "truth: x",
                "budget": {"max_targets": 3},
            }]
            body["lenses"] = [{"name": "another lens", "work_order": body["work_orders"][0]}]
        return InvokeResult(ok=True, text=json.dumps(body), cost_usd=0.01,
                            usage={"input_tokens": 100, "output_tokens": 50})


def _ctx(world, invoker, ceiling=None):
    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT, run_dir=world["run_dir"],
        policy=LadderPolicy(max_cost_usd=ceiling),
    )
    ctx = build_run_context(config, invoker_factory=lambda spec: invoker,
                            clock=FIXED_CLOCK)
    ctx.budget = BudgetMeter(ceiling=ceiling)
    return ctx


def _order(world, n=2, **kw):
    base = dict(
        scope=world["components"][:n],
        lens="every component names its inbound protocol",
        criteria="each answer cites the file where the protocol is set",
        expected_effect="truth: the grounded fraction should rise",
        budget={"max_cost_usd": 1.0, "max_targets": 8},
        issued_by="P5",
    )
    base.update(kw)
    return WorkOrder(**base)


# --- 1. an order's results change the census ----------------------------------


def test_an_order_moves_the_contract_state_of_the_targets_in_scope(world):
    invoker = ScriptedOrder(world, ground=True)
    ctx = _ctx(world, invoker)
    shared = LadderOutcome()
    # Start with the scope escalating, so there is something to move.
    for cid in world["components"][:2]:
        shared.states[("component", cid)] = ContractState(
            "component", cid, state="escalate", rung="sonnet"
        )

    try:
        outcome = execute_work_order(ctx, _order(world), ladder_outcome=shared)
    finally:
        ctx.store.close()

    assert outcome.executed is True
    assert outcome.changed_anything is True
    for cid in world["components"][:2]:
        change = outcome.state_changes[cid]
        assert change["before"] == "escalate@sonnet"
        # The rung records the tier that DID the work, which for a work order is
        # whatever the workorder binding resolves to, not the phase that issued
        # it. Recording "p5" there would claim the determination phase did
        # enrichment work it never did.
        assert change["after"] == "grounded@sonnet"
        assert shared.states[("component", cid)].state == "grounded"


def test_a_work_order_cannot_demote_a_grounded_contract_state(world):
    invoker = ScriptedOrder(world, ground=False)
    ctx = _ctx(world, invoker)
    cid = world["components"][0]
    shared = LadderOutcome()
    shared.states[("component", cid)] = ContractState(
        "component", cid, state="grounded", rung="opus"
    )
    try:
        outcome = execute_work_order(
            ctx, _order(world, n=1), ladder_outcome=shared
        )
    finally:
        ctx.store.close()

    assert outcome.executed is True
    assert outcome.changed_anything is False
    assert shared.states[("component", cid)].terminal == "grounded@opus"
    assert any(
        "rejected work-order result" in transition.get("resolution", "")
        for transition in shared.transitions
    )


def test_a_declined_question_does_not_discard_valid_sibling_repairs(world):
    cid = world["components"][0]
    facts = world["facts_by_id"][cid]
    required = required_questions("component", facts)
    original_answers = {
        question: {
            "claim": f"original {question}", "status": "answered",
            "evidence": [{
                "kind": "file", "path": world["real_file"], "line": 1,
            }],
        }
        for question in required
    }

    class PartialRepair:
        prompts = []

        def __call__(self, prompt):
            self.prompts.append(prompt)
            return InvokeResult(ok=True, cost_usd=0.01, text=json.dumps({
                "components": {cid: {CONTRACT_KEY: {"answers": {
                    "purpose": {
                        "claim": "repaired purpose", "status": "answered",
                        "evidence": [{
                            "kind": "file", "path": world["real_file"], "line": 1,
                        }],
                    },
                    "mechanism": {
                        "claim": "best bounded claim", "status": "uncertain",
                        "reason": "the exact behavior is absent",
                    },
                }}}},
                "relationships": {},
            }))

    shared = LadderOutcome(
        states={("component", cid): ContractState(
            "component", cid, state="grounded", rung="opus",
        )},
        payloads={("component", cid): {
            "help_text": "Original reader prose.",
            "contract": {"answers": original_answers},
        }},
    )
    ctx = _ctx(world, PartialRepair())
    try:
        outcome = execute_work_order(
            ctx, _order(world, n=1), ladder_outcome=shared,
        )
    finally:
        ctx.store.close()

    answers = shared.payloads[("component", cid)]["contract"]["answers"]
    assert answers["purpose"]["claim"] == "repaired purpose"
    assert answers["mechanism"]["claim"] == "original mechanism"
    assert shared.states[("component", cid)].terminal == "grounded@sonnet"
    assert cid in outcome.payload_changes
    assert any(
        "banked valid work-order answers" in transition.get("resolution", "")
        for transition in shared.transitions
    )


def test_independently_rejected_claim_can_become_a_terminal_honest_gap(world):
    cid = world["components"][0]

    class HonestGapRepair:
        def __call__(self, _prompt):
            return InvokeResult(ok=True, cost_usd=0.01, text=json.dumps({
                "components": [{
                    "i": cid,
                    "q": {"mechanism": {
                        "t": "The exact mechanism is not present in supplied facts.",
                        "s": "u", "r": "the method body is absent",
                        "l": "fact", "need": "the target method body",
                    }},
                }],
                "relationships": [],
            }))

    old_claim = "The file name proves this runtime mechanism."
    baseline_answers = {
        question: {
            "claim": old_claim if question == "mechanism" else f"supported {question}",
            "status": "answered",
            "evidence": [{
                "kind": "file", "path": world["real_file"], "line": 1,
            }],
        }
        for question in required_questions(
            "component", world["facts_by_id"][cid]
        )
    }
    shared = LadderOutcome(
        states={("component", cid): ContractState(
            "component", cid, state="grounded", rung="sonnet",
        )},
        payloads={("component", cid): {
            "contract": {"answers": baseline_answers},
        }},
    )
    ctx = _ctx(world, HonestGapRepair())
    ctx.results["p3_adjudication"] = PhaseResult(
        "p3_adjudication", "ok", data={"adjudication": AdjudicationOutcome(
            spot_checks=[SpotCheck(
                target_kind="component", target_id=cid, question="mechanism",
                claim=old_claim, supported=False,
                reason="a file name does not prove runtime behavior",
            )],
        )},
    )
    try:
        outcome = execute_work_order(
            ctx, _order(world, n=1), ladder_outcome=shared,
        )
    finally:
        ctx.store.close()

    answer = shared.payloads[("component", cid)]["contract"]["answers"]["mechanism"]
    assert outcome.executed
    assert shared.states[("component", cid)].state == "honest_gap"
    assert answer["status"] == "uncertain"
    assert answer["claim"] != old_claim


def test_existing_escalation_is_named_and_terminal_invalid_repair_becomes_gap(world):
    cid = world["components"][0]
    facts = world["facts_by_id"][cid]
    baseline_answers = {
        question: {
            "claim": f"supported {question}", "status": "answered",
            "evidence": [{
                "kind": "file", "path": world["real_file"], "line": 1,
            }],
        }
        for question in required_questions("component", facts)
    }

    class InvalidTerminalRepair:
        prompts = []

        def __call__(self, prompt):
            self.prompts.append(prompt)
            return InvokeResult(ok=True, cost_usd=0.01, text=json.dumps({
                "components": {cid: {CONTRACT_KEY: {"answers": {
                    "mechanism": {
                        "claim": "A replacement that still has no evidence.",
                        "status": "answered",
                        "evidence": [{"kind": "file", "path": "not-supplied.swift"}],
                    },
                }}}},
                "relationships": {},
            }))

    invoker = InvalidTerminalRepair()
    shared = LadderOutcome(
        states={("component", cid): ContractState(
            "component", cid, state="escalate", rung="sonnet",
            failed=[FailedQuestion("mechanism", "E2", "citation did not resolve")],
        )},
        payloads={("component", cid): {
            "help_text": "Previously rejected mechanism prose.",
            "contract": {"answers": baseline_answers},
        }},
    )
    ctx = _ctx(world, invoker)
    try:
        outcome = execute_work_order(
            ctx, _order(world, n=1), ladder_outcome=shared,
        )
    finally:
        ctx.store.close()

    answer = shared.payloads[("component", cid)]["contract"]["answers"]["mechanism"]
    assert outcome.executed
    assert '"todo": ["mechanism"]' in invoker.prompts[0]
    assert shared.states[("component", cid)].state == "honest_gap"
    assert answer["status"] == "uncertain"
    assert answer["claim"] == ""
    assert "replacement that still has no evidence" not in shared.payloads[
        ("component", cid)
    ].get("help_text", "").lower()
    assert shared.payloads[("component", cid)]["honest_gaps"][0]["question"] == "mechanism"


def test_an_order_runs_through_the_same_contract_and_writes_the_same_rows(world):
    invoker = ScriptedOrder(world, ground=True)
    ctx = _ctx(world, invoker)
    try:
        execute_work_order(ctx, _order(world), ladder_outcome=LadderOutcome())
    finally:
        ctx.store.close()

    store = FactStore(str(world["db"]))
    try:
        rows = {(r["target_kind"], r["target_id"]): r["payload"] for r in store.enrichment()}
    finally:
        store.close()

        for cid in world["components"][:2]:
            product = rows[("component", cid)]
            assert product["help_text"].startswith("through the lens: purpose")
            assert "A revised four-sentence account" not in product["help_text"]
        # The scaffolding stayed out of the product, exactly as in a normal rung.
        assert CONTRACT_KEY not in product
        contract = rows[(CONTRACT_TARGET_KIND, f"component:{cid}")]
        assert contract["state"] == "grounded"
        assert contract["answers"]["purpose"]["claim"].startswith("through the lens")


def test_the_order_prompt_carries_the_lens_the_criteria_and_the_expected_effect(world):
    invoker = ScriptedOrder(world)
    ctx = _ctx(world, invoker)
    try:
        execute_work_order(ctx, _order(world), ladder_outcome=LadderOutcome())
    finally:
        ctx.store.close()

    prompt = invoker.prompts[0]
    assert "SCOPED WORK ORDER" in prompt
    assert "every component names its inbound protocol" in prompt
    assert "each answer cites the file where the protocol is set" in prompt
    assert "truth: the grounded fraction should rise" in prompt
    assert "an order is not a licence to redo finished work" in prompt.lower()
    assert "no file-reading or repository tools" in prompt


def test_work_order_cannot_expand_the_attempted_census(world):
    """The 68→71 live-canary regression: P5 may repair, never add targets."""
    invoker = ScriptedOrder(world)
    ctx = _ctx(world, invoker)
    attempted = world["components"][0]
    outside = world["components"][1]
    shared = LadderOutcome(states={
        ("component", attempted): ContractState(
            "component", attempted, state="escalate", rung="sonnet"
        ),
    })
    order = _order(world, n=2)
    order.scope = [attempted, outside]
    try:
        outcome = execute_work_order(ctx, order, ladder_outcome=shared)
    finally:
        ctx.store.close()

    assert outcome.executed
    assert outcome.order.scope == [attempted]
    assert set(shared.states) == {("component", attempted)}
    assert f'"target_id": "{outside}"' not in invoker.prompts[0]
    assert any("outside the attempted ladder census" in note for note in outcome.notes)


def test_entirely_out_of_scope_work_order_is_rejected_without_spend(world):
    invoker = ScriptedOrder(world)
    ctx = _ctx(world, invoker)
    shared = LadderOutcome(states={
        ("component", world["components"][0]): ContractState(
            "component", world["components"][0], state="grounded", rung="sonnet"
        ),
    })
    order = _order(world, n=1)
    order.scope = [world["components"][1]]
    try:
        outcome = execute_work_order(ctx, order, ladder_outcome=shared)
    finally:
        ctx.store.close()

    assert not outcome.executed
    assert not invoker.prompts
    assert len(shared.states) == 1
    assert any("no work-order target belonged" in note for note in outcome.notes)


def test_the_order_prompt_carries_the_exact_adjudication_failures(world):
    invoker = ScriptedOrder(world)
    ctx = _ctx(world, invoker)
    cid = world["components"][0]
    adjudication = AdjudicationOutcome(spot_checks=[SpotCheck(
        target_kind="component", target_id=cid, question="mechanism",
        claim="The file name proves runtime behaviour.", supported=False,
        reason="A file path proves existence, not runtime behaviour.",
    )])
    ctx.results["p3_adjudication"] = PhaseResult(
        "p3_adjudication", "ok", data={"adjudication": adjudication},
    )
    shared = LadderOutcome()
    shared.payloads[("component", cid)] = {
        "contract": {"answers": {"mechanism": {
            "claim": "The file name proves runtime behaviour.",
            "status": "answered",
            "evidence": [{"kind": "file", "path": world["real_file"]}],
        }}}
    }
    try:
        execute_work_order(
            ctx, _order(world, n=1), ladder_outcome=shared,
        )
    finally:
        ctx.store.close()

    prompt = invoker.prompts[0]
    assert '"todo": ["mechanism"]' in prompt
    assert "The file name proves runtime behaviour." in prompt
    assert "A file path proves existence, not runtime behaviour." in prompt


def test_coverage_retry_banks_valid_sibling_and_reissues_only_missing_id(world):
    class OmitsSecondOnce(ScriptedOrder):
        def __call__(self, prompt):
            result = super().__call__(prompt)
            if len(self.prompts) != 1:
                return result
            body = json.loads(result.text)
            body["components"].pop(world["components"][1])
            return InvokeResult(
                ok=True, text=json.dumps(body), cost_usd=0.01,
                usage={"input_tokens": 100, "output_tokens": 50},
            )

    invoker = OmitsSecondOnce(world)
    ctx = _ctx(world, invoker)
    first, second = world["components"][:2]
    shared = LadderOutcome()
    for cid in (first, second):
        shared.states[("component", cid)] = ContractState(
            "component", cid, state="escalate", rung="sonnet"
        )
    try:
        outcome = execute_work_order(
            ctx, _order(world, n=2), ladder_outcome=shared
        )
    finally:
        ctx.store.close()

    assert len(invoker.prompts) == 2
    assert f'"target_id": "{second}"' in invoker.prompts[1]
    assert f'"target_id": "{first}"' not in invoker.prompts[1]
    assert "Do not repeat any target already banked" in invoker.prompts[1]
    assert all(shared.states[("component", cid)].state == "grounded"
               for cid in (first, second))
    assert any("valid siblings remain banked" in note for note in outcome.notes)


def test_named_failure_with_empty_delta_is_retried_without_rebuying_sibling(world):
    class EmptySecondOnce(ScriptedOrder):
        def __call__(self, prompt):
            result = super().__call__(prompt)
            if len(self.prompts) != 1:
                return result
            body = json.loads(result.text)
            body["components"][world["components"][1]] = {}
            return InvokeResult(
                ok=True, text=json.dumps(body), cost_usd=0.01,
                usage={"input_tokens": 100, "output_tokens": 50},
            )

    first, second = world["components"][:2]
    adjudication = AdjudicationOutcome(spot_checks=[SpotCheck(
        target_kind="component", target_id=second, question="purpose",
        claim="Uncited intent.", supported=False,
        reason="The supplied evidence does not carry intent.",
    )])
    invoker = EmptySecondOnce(world)
    ctx = _ctx(world, invoker)
    ctx.results["p3_adjudication"] = PhaseResult(
        "p3_adjudication", "ok", data={"adjudication": adjudication},
    )
    shared = LadderOutcome()
    for cid in (first, second):
        shared.states[("component", cid)] = ContractState(
            "component", cid, state="grounded", rung="sonnet"
        )
    try:
        outcome = execute_work_order(
            ctx, _order(world, n=2), ladder_outcome=shared
        )
    finally:
        ctx.store.close()

    assert len(invoker.prompts) == 2
    assert f'"target_id": "{second}"' in invoker.prompts[1]
    assert f'"target_id": "{first}"' not in invoker.prompts[1]
    assert "changed answer for every listed failed question" in invoker.prompts[1]
    assert any("did not repair every named question" in note for note in outcome.notes)


def test_partial_question_coverage_retries_the_target_until_every_todo_is_answered(world):
    class OmitsOneQuestionOnce(ScriptedOrder):
        def __call__(self, prompt):
            result = super().__call__(prompt)
            if len(self.prompts) != 1:
                return result
            body = json.loads(result.text)
            answers = body["components"][target][CONTRACT_KEY]["answers"]
            answers["mechanism"] = {
                "claim": "", "status": "uncertain",
                "reason": "no answer was produced for a required question",
            }
            return InvokeResult(
                ok=True, text=json.dumps(body), cost_usd=0.01,
                usage={"input_tokens": 100, "output_tokens": 50},
            )

    target = world["components"][0]
    invoker = OmitsOneQuestionOnce(world)
    ctx = _ctx(world, invoker)
    shared = LadderOutcome()
    shared.states[("component", target)] = ContractState(
        "component", target, state="escalate", rung="fable",
        failed=[
            FailedQuestion("purpose", "E1", "missing purpose"),
            FailedQuestion("mechanism", "E1", "missing mechanism"),
        ],
    )
    try:
        outcome = execute_work_order(
            ctx, _order(world, n=1), ladder_outcome=shared
        )
    finally:
        ctx.store.close()

    assert len(invoker.prompts) == 2
    assert '"target_id": "' + target + '"' in invoker.prompts[1]
    assert any(
        target in note and "mechanism" in note
        for note in outcome.notes
    )
    assert shared.states[("component", target)].state == "grounded"


def test_honest_gap_failures_are_named_in_the_repair_todo(world):
    target = world["components"][0]
    invoker = ScriptedOrder(world)
    ctx = _ctx(world, invoker)
    shared = LadderOutcome()
    shared.states[("component", target)] = ContractState(
        "component", target, state="honest_gap", rung="fable",
        failed=[FailedQuestion(
            "mechanism", "E1", "the terminal tier did not establish the mechanism"
        )],
    )
    try:
        execute_work_order(ctx, _order(world, n=1), ladder_outcome=shared)
    finally:
        ctx.store.close()

    item = json.loads(
        invoker.prompts[0].split("ITEMS:\n", 1)[1].split(
            "\nReturn the JSON object now.", 1
        )[0]
    )[0]
    assert item["todo"] == ["mechanism"]
    assert item["failed"][0]["question"] == "mechanism"
    assert shared.states[("component", target)].state == "grounded"


def test_a_relationship_named_by_an_order_is_repaired_and_rechecked(world):
    relationship_key = world["relationship"]
    source, target, edge_type = relationship_key.split("|", 2)

    class RelationshipOrder:
        def __init__(self):
            self.prompts = []

        def __call__(self, prompt):
            self.prompts.append(prompt)
            edge = {
                "kind": "edge", "source": source, "target": target,
                "edge_type": edge_type,
            }
            body = {
                "components": {},
                "relationships": {
                    relationship_key: {
                        "data_flow_description": f"{source} calls {target}.",
                        CONTRACT_KEY: {
                            "parser_first": [],
                            "answers": {
                                "flow": {
                                    "claim": f"{source} calls {target} over {edge_type}.",
                                    "status": "answered", "evidence": [edge],
                                },
                                "why": {
                                    "claim": "This connects the client to the API.",
                                    "status": "answered", "evidence": [edge],
                                },
                            },
                        },
                    }
                },
            }
            return InvokeResult(
                ok=True, text=json.dumps(body), cost_usd=0.01,
                usage={"input_tokens": 100, "output_tokens": 50},
            )

    invoker = RelationshipOrder()
    ctx = _ctx(world, invoker)
    shared = LadderOutcome()
    shared.states[("relationship", relationship_key)] = ContractState(
        "relationship", relationship_key, state="escalate", rung="sonnet"
    )
    order = WorkOrder(
        scope=[relationship_key],
        lens="repair the independently unsupported relationship claim",
        criteria="the relationship's flow and significance cite its real edge",
        expected_effect="truth: relationship disagreement decreases",
        budget={"max_cost_usd": 1.0, "max_targets": 1},
        issued_by="P5",
    )
    try:
        outcome = execute_work_order(ctx, order, ladder_outcome=shared)
    finally:
        ctx.store.close()

    assert '"target_kind": "relationship"' in invoker.prompts[0]
    assert outcome.targets_attempted == 1
    assert shared.states[("relationship", relationship_key)].state == "grounded"
    assert relationship_key in outcome.payload_changes


def test_the_scope_is_capped_by_the_orders_own_budget(world):
    invoker = ScriptedOrder(world)
    ctx = _ctx(world, invoker)
    order = _order(world, n=len(world["components"]),
                   budget={"max_cost_usd": 1.0, "max_targets": 2})
    try:
        outcome = execute_work_order(ctx, order, ladder_outcome=LadderOutcome())
    finally:
        ctx.store.close()
    assert outcome.targets_attempted <= 2 or len(outcome.state_changes) <= 2


def test_dense_work_orders_are_split_into_quality_sized_calls(world):
    """A repair order must not repurchase one oversized all-target response."""
    scope = [
        *world["components"][:WORK_ORDER_TARGET_BATCH],
        world["relationship"],
    ]
    assert len(scope) > WORK_ORDER_TARGET_BATCH
    invoker = ScriptedOrder(world)
    ctx = _ctx(world, invoker)
    order = WorkOrder(
        scope=scope,
        lens="repair a dense mixed component and relationship scope",
        criteria="every named target receives its own bounded repair",
        expected_effect="truth: every repair remains independently checkable",
        budget={"max_cost_usd": 10.0, "max_targets": len(scope)},
        issued_by="P5",
    )
    try:
        outcome = execute_work_order(ctx, order, ladder_outcome=LadderOutcome())
    finally:
        ctx.store.close()

    assert outcome.executed
    assert len(invoker.prompts) == 2
    assert invoker.prompts[0].count('"wire": "work-order/v1"') == (
        WORK_ORDER_TARGET_BATCH
    )
    assert all(
        prompt.count('"wire": "work-order/v1"') <= WORK_ORDER_TARGET_BATCH
        for prompt in invoker.prompts
    )


# --- 2. one level of federation ------------------------------------------------


def test_an_order_cannot_spawn_further_orders(world):
    """Enforced structurally, not by asking politely."""
    invoker = ScriptedOrder(world, propose_orders=True)
    ctx = _ctx(world, invoker)
    try:
        outcome = execute_work_order(ctx, _order(world), ladder_outcome=LadderOutcome())
    finally:
        ctx.store.close()

    # The response proposed one, and it went nowhere: the outcome has no field
    # that could carry it and nothing parsed one out.
    assert "work_orders" not in outcome.to_dict()
    assert not hasattr(outcome, "work_orders")
    assert outcome.executed is True
    # And the prompt told it not to bother.
    assert "Do NOT propose further work orders" in invoker.prompts[0]
    assert "the only level of follow-up there is" in invoker.prompts[0]


def test_the_assignment_text_states_the_one_level_rule():
    text = WORK_ORDER_ASSIGNMENT.format(lens="l", criteria="c", expected_effect="e")
    assert "Do NOT propose further work orders" in text


# --- 3. content change is a measured change -----------------------------------


def test_a_grounded_to_grounded_payload_repair_is_recorded_as_change(world):
    """Quality prose can improve without changing the contract-state label."""
    invoker = ScriptedOrder(world, ground=True)
    ctx = _ctx(world, invoker)
    shared = LadderOutcome()
    for cid in world["components"][:2]:
        shared.states[("component", cid)] = ContractState(
            "component", cid, state="grounded", rung="sonnet"
        )
    try:
        outcome = execute_work_order(ctx, _order(world), ladder_outcome=shared)
    finally:
        ctx.store.close()

    assert outcome.executed is True
    assert outcome.state_changes == {}
    assert outcome.payload_changes == sorted(world["components"][:2])
    assert outcome.changed_anything is True
    assert not outcome.notes


def test_an_invalid_order_is_not_executed_and_says_why(world):
    invoker = ScriptedOrder(world)
    ctx = _ctx(world, invoker)
    bad = _order(world, lens="", expected_effect="")
    try:
        outcome = execute_work_order(ctx, bad, ladder_outcome=LadderOutcome())
    finally:
        ctx.store.close()

    assert outcome.executed is False
    assert invoker.prompts == []
    assert "not executed" in outcome.notes[0]
    assert "no lens" in outcome.notes[0]


def test_an_order_past_the_ceiling_is_not_executed(world):
    invoker = ScriptedOrder(world)
    ctx = _ctx(world, invoker, ceiling=0.0)
    try:
        outcome = execute_work_order(ctx, _order(world), ladder_outcome=LadderOutcome())
    finally:
        ctx.store.close()
    assert outcome.executed is False
    assert invoker.prompts == []
    assert "cost ceiling reached" in outcome.notes[0]


def test_an_order_records_what_it_cost(world):
    invoker = ScriptedOrder(world)
    ctx = _ctx(world, invoker)
    try:
        outcome = execute_work_order(ctx, _order(world), ladder_outcome=LadderOutcome())
    finally:
        ctx.store.close()
    assert outcome.cost_usd > 0
    assert outcome.to_dict()["outcome"]["cost_usd"] == round(outcome.cost_usd, 6)


def test_an_unusable_response_leaves_the_order_honest_about_it(world):
    invoker = ScriptedOrder(world, ok=False)
    ctx = _ctx(world, invoker)
    try:
        outcome = execute_work_order(ctx, _order(world), ladder_outcome=LadderOutcome())
    finally:
        ctx.store.close()
    assert outcome.executed is False
    assert any("did not return" in n for n in outcome.notes)


def test_a_duplicate_work_order_target_is_rejected_and_reported(world):
    cid = world["components"][0]
    invoker = ScriptedOrder(world, duplicate=True)
    ctx = _ctx(world, invoker)
    shared = LadderOutcome()
    shared.states[("component", cid)] = ContractState(
        "component", cid, state="escalate", rung="sonnet"
    )
    try:
        outcome = execute_work_order(
            ctx, _order(world, n=1), ladder_outcome=shared
        )
    finally:
        ctx.store.close()

    assert shared.states[("component", cid)].state == "escalate"
    assert any(
        "compact coverage violation" in note and "duplicate_components" in note
        for note in outcome.notes
    )


# --- the descent seam ----------------------------------------------------------


def test_the_descender_runs_orders_in_issue_order_over_shared_state(world):
    """Two orders touching the same component must not both claim the change."""
    invoker = ScriptedOrder(world, ground=True)
    ctx = _ctx(world, invoker)
    shared = LadderOutcome()
    cid = world["components"][0]
    shared.states[("component", cid)] = ContractState(
        "component", cid, state="escalate", rung="sonnet"
    )
    descend = make_descender(ctx, shared)
    try:
        outcomes = descend([_order(world, n=1), _order(world, n=1)])
    finally:
        ctx.store.close()

    assert len(outcomes) == 2
    # The first order moved it; the second saw it already moved.
    assert outcomes[0].changed_anything is True
    assert outcomes[1].changed_anything is False
    assert any("moved nothing" in n for n in outcomes[1].notes)


def test_the_descent_seam_is_available_on_the_context(world):
    invoker = ScriptedOrder(world)
    ctx = _ctx(world, invoker)
    try:
        assert ctx.descend is None  # not wired until a phase needs it
        ctx.descend = make_descender(ctx, LadderOutcome())
        outcomes = ctx.descend([_order(world, n=1)])
    finally:
        ctx.store.close()
    assert len(outcomes) == 1
    assert outcomes[0].executed is True
