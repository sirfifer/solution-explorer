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
from analyzer.enrich.contract import CONTRACT_KEY, ContractState, required_questions
from analyzer.enrich.engine import InvokeResult
from analyzer.enrich.ladder import CONTRACT_TARGET_KIND, LadderOutcome
from analyzer.enrich.partition import flatten_components
from analyzer.enrich.pipeline import (
    BudgetMeter,
    LadderConfig,
    LadderPolicy,
    build_run_context,
)
from analyzer.enrich.workorder import (
    WORK_ORDER_ASSIGNMENT,
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
        "facts_by_id": {c["id"]: c for c in flat},
        "real_file": real_file,
    }


class ScriptedOrder:
    """Answers a scoped work-order prompt; optionally proposes further orders."""

    def __init__(self, world, *, ground=True, propose_orders=False, ok=True):
        self.world = world
        self.ground = ground
        self.propose_orders = propose_orders
        self.ok = ok
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
        assert change["after"] == "grounded@p5"
        assert shared.states[("component", cid)].state == "grounded"


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
        assert product["help_text"].startswith("A revised four-sentence account")
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
    assert "an order is not a licence to redo finished work" in prompt


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


# --- 3. an order that changed nothing says so ---------------------------------


def test_an_order_that_changes_no_state_is_recorded_as_exactly_that(world):
    """A determination that cannot tell work from improvement buys empty rounds."""
    invoker = ScriptedOrder(world, ground=True)
    ctx = _ctx(world, invoker)
    shared = LadderOutcome()
    for cid in world["components"][:2]:
        shared.states[("component", cid)] = ContractState(
            "component", cid, state="grounded", rung="p5"
        )
    try:
        outcome = execute_work_order(ctx, _order(world), ladder_outcome=shared)
    finally:
        ctx.store.close()

    assert outcome.executed is True
    assert outcome.state_changes == {}
    assert outcome.changed_anything is False
    assert any("moved nothing" in n for n in outcome.notes)


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
