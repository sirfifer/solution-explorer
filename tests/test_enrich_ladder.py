"""T5: the ladder. A scripted invoker drives real items to every terminal state.

No model is invoked. The invoker is a script: it inspects the prompt it is
handed, decides which rung is asking, and returns a canned response designed to
push specific components down specific paths. That is what lets one test assert
the whole ladder including the states that only occur three rungs deep.

The properties, in the order they matter:

  1. NO-REDO. Rung 2b's prompt contains rung 2a's actual attempt and the specific
     failed questions. This is a property of the prompt, so it is asserted
     against the prompt rather than hoped for.
  2. CLIMBING IS ADDITIVE. A higher rung that returns a thinner block does not
     delete the good answers below it. Fail-before contrast included.
  3. THE LADDER TERMINATES. Everything ends in exactly one terminal state, and
     what Fable cannot ground becomes a visible honest gap, never a faked answer
     and never a loop.
  4. IMPORTANCE GOES FIRST. Under a ceiling, the partial run covered the
     components a reader needs.
  5. THE PRODUCT NEVER SEES THE SCAFFOLDING. Contract answers land in their own
     store rows; the component rows carry what they always carried plus honest
     gaps.
"""

from __future__ import annotations

import json
import os

import pytest

from analyzer.derive import derive_all
from analyzer.enrich.contract import CONTRACT_KEY, required_questions
from analyzer.enrich.engine import InvokeResult
from analyzer.enrich.ladder import (
    CONTRACT_TARGET_KIND,
    LadderPhase,
    build_escalation_prompt,
    merge_payloads,
    order_partitions,
)
from analyzer.enrich.partition import flatten_components
from analyzer.enrich.pipeline import (
    BudgetMeter,
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


# --- the scripted invoker -----------------------------------------------------


class ScriptedLadder:
    """Answers as whichever rung the prompt says it is, per a per-component plan.

    plan[component_id] is a tuple of what each rung does, in order:
      "ground"  answer everything with a citation that validates
      "gap"     omit the mechanism answer, producing an E1
      "fake"    answer everything, but cite a file that does not exist (E2)
      "silent"  return nothing for this component at all
      "gapdecl" declare an honest gap on mechanism (terminal rung only)
    """

    def __init__(self, plan, real_file, all_components, all_relationships,
                 facts_by_id=None):
        self.plan = plan
        self.real_file = real_file
        self.all_components = all_components
        self.all_relationships = all_relationships
        # Answer exactly what each component is ASKED, the way a real rung
        # would: the required set is computed from the same facts the
        # validator uses, so a component with a language is asked about it.
        self.facts_by_id = facts_by_id or {}
        self.prompts = []
        self.cost = 0.0

    def __call__(self, prompt: str) -> InvokeResult:
        self.prompts.append(prompt)
        if "LAST rung" in prompt:
            rung = 2
        elif "HIGHER RUNG" in prompt:
            rung = 1
        else:
            rung = 0
        ids = [cid for cid in self.all_components if f'"{cid}"' in prompt]
        components = {}
        for cid in ids:
            steps = self.plan.get(cid, ("ground",))
            action = steps[rung] if rung < len(steps) else steps[-1]
            block = self._component(cid, action)
            if block is not None:
                components[cid] = block
        relationships = {}
        if rung == 0:
            for key in self.all_relationships:
                if key in prompt:
                    relationships[key] = self._relationship()
        return InvokeResult(
            ok=True,
            text=json.dumps({"components": components, "relationships": relationships}),
            cost_usd=0.01,
            usage={"input_tokens": 10, "output_tokens": 5},
        )

    def _cite(self, real: bool = True):
        path = self.real_file if real else "invented/never/existed.py"
        return [{"kind": "file", "path": path, "line": 1}]

    def _answers(self, questions, real=True):
        return {
            q: {"claim": f"a defensible claim about {q}", "status": "answered",
                "evidence": self._cite(real)}
            for q in questions
        }

    def _required(self, cid):
        return list(required_questions("component", self.facts_by_id.get(cid, {})))

    def _component(self, cid, action):
        full = self._required(cid)
        base = {
            "help_text": f"Four sentences describing {cid} and its neighbours.",
            "description": f"the {cid} component",
            "data_handled": "records and identifiers",
            "criticality": "supporting",
        }
        if action == "silent":
            return None
        if action == "ground":
            contract = {
                "parser_first": [], "answers": self._answers(full),
                "self_state": "grounded", "confusion": None,
                "substitution_check": f"only {cid} owns this path",
            }
        elif action == "gap":
            contract = {
                "parser_first": [f"{cid}'s framework was inferable from its manifest"],
                "answers": self._answers([q for q in full if q != "mechanism"]),
                "self_state": "escalate",
                "confusion": None,
                "substitution_check": f"only {cid} owns this path",
            }
        elif action == "fake":
            contract = {
                "parser_first": [], "answers": self._answers(full, real=False),
                "self_state": "grounded", "confusion": None,
                "substitution_check": f"only {cid} owns this path",
            }
        elif action == "gapdecl":
            contract = {
                "parser_first": [],
                "answers": dict(
                    self._answers([q for q in full if q != "mechanism"]),
                    mechanism={"claim": "", "status": "dropped",
                               "reason": "generated at build time"},
                ),
                "self_state": "escalate", "confusion": None,
                "substitution_check": f"only {cid} owns this path",
            }
            base["honest_gaps"] = [{
                "question": "mechanism",
                "why": "the dispatch table is generated at build time and no "
                       "source file contains it",
            }]
        else:
            raise AssertionError(f"unknown action {action}")
        base[CONTRACT_KEY] = contract
        return base

    def _relationship(self):
        return {
            "data_flow_description": "identifiers and payloads",
            "importance": "internal",
            CONTRACT_KEY: {
                "parser_first": [],
                "answers": self._answers(("flow", "why")),
                "self_state": "grounded",
            },
        }


# --- world --------------------------------------------------------------------


@pytest.fixture
def world(tmp_path):
    db = tmp_path / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    store.commit()
    flat = [c for c in flatten_components(arch.get("components", [])) if c.get("id")]
    components = [c["id"] for c in flat]
    facts_by_id = {c["id"]: c for c in flat}
    relationships = [
        f"{r.get('source','')}|{r.get('target','')}|{r.get('type','')}"
        for r in arch.get("relationships", [])
    ]
    real_file = next(f["path"] for f in store.files() if f.get("lines"))
    store.close()
    return {
        "db": db, "root": tmp_path, "arch": arch, "components": components,
        "relationships": relationships, "real_file": real_file,
        "facts_by_id": facts_by_id,
    }


def _run(world, plan, *, ceiling=None, tmp_path=None):
    invoker = ScriptedLadder(
        plan, world["real_file"], world["components"], world["relationships"],
        world["facts_by_id"],
    )
    config = LadderConfig(
        store_path=world["db"],
        root=POLYGLOT,
        run_dir=(tmp_path or world["root"]) / "run",
        policy=LadderPolicy(max_cost_usd=ceiling),
    )
    ctx = build_run_context(
        config, invoker_factory=lambda spec: invoker, clock=FIXED_CLOCK
    )
    ctx.budget = BudgetMeter(ceiling=ceiling)
    try:
        result = run_pipeline(ctx, [LadderPhase()])
        outcome = ctx.results["p2_ladder"].data["ladder"]
        return result, outcome, invoker, ctx
    finally:
        ctx.store.close()


# --- 1. no-redo ---------------------------------------------------------------


def test_a_higher_rung_receives_the_attempt_and_the_named_gaps(world):
    """The no-redo property is a test, not a hope."""
    target = world["components"][0]
    plan = {cid: ("ground",) for cid in world["components"]}
    plan[target] = ("gap", "ground", "ground")

    _, outcome, invoker, _ = _run(world, plan)

    escalation_prompts = [p for p in invoker.prompts if "HIGHER RUNG" in p]
    assert escalation_prompts, "the gapped component should have escalated"
    prompt = escalation_prompts[0]

    # The 2a attempt is in the prompt, verbatim.
    assert "previous_attempt" in prompt
    assert f"Four sentences describing {target} and its neighbours." in prompt
    assert "a defensible claim about purpose" in prompt
    # And the specific failed question, with its trigger, is why it climbed.
    assert "failed_questions" in prompt
    assert '"question": "mechanism"' in prompt
    assert '"trigger": "E1"' in prompt
    # The assignment says explicitly not to redo what already succeeded.
    assert "Do not rewrite an answer that was" in prompt
    assert "already right" in prompt


def test_the_terminal_rung_is_told_to_declare_a_gap_rather_than_paper_over_it(world):
    target = world["components"][0]
    plan = {cid: ("ground",) for cid in world["components"]}
    plan[target] = ("gap", "gap", "gapdecl")

    _, outcome, invoker, _ = _run(world, plan)

    terminal = [p for p in invoker.prompts if "LAST rung" in p]
    assert terminal
    assert "There is no rung after you and there is no loop." in terminal[0]
    assert "becomes a lie the map tells with confidence" in terminal[0]
    assert "honest_gaps" in terminal[0]


def test_an_escalation_prompt_is_never_a_blank_assignment():
    prompt = build_escalation_prompt(
        [{"target_kind": "component", "target_id": "c1",
          "previous_attempt": {"ai_enhance": {"help_text": "prior prose"}},
          "failed_questions": [{"question": "place", "trigger": "E2", "note": "no cite"}]}],
        rung="opus",
    )
    assert "prior prose" in prompt
    assert '"question": "place"' in prompt
    assert "You are not starting over." in prompt


# --- 2. climbing is additive --------------------------------------------------


def test_a_thinner_higher_rung_payload_does_not_delete_what_worked():
    lower = {"help_text": "a full four-sentence account", "data_handled": "records",
             "criticality": "critical", "description": "the thing"}
    higher = {"criticality": "important"}
    merged = merge_payloads(lower, higher)
    assert merged["criticality"] == "important"        # corrected
    assert merged["help_text"] == lower["help_text"]   # kept
    assert merged["description"] == "the thing"        # kept


def test_empty_values_from_a_higher_rung_never_overwrite_good_ones():
    """Fail-before contrast: a plain dict update would blank all three."""
    lower = {"help_text": "real prose", "key_user_flows": ["a", "b"], "port_assessment": "8080 serves the API"}
    higher = {"help_text": "", "key_user_flows": [], "port_assessment": None}
    merged = merge_payloads(lower, higher)
    assert merged == lower
    assert {**lower, **higher} != lower  # what a naive merge would have done


def test_a_climbing_item_keeps_the_answers_the_lower_rung_grounded(world):
    target = world["components"][0]
    plan = {cid: ("ground",) for cid in world["components"]}
    plan[target] = ("gap", "ground", "ground")

    _, outcome, _, _ = _run(world, plan)

    state = outcome.states[("component", target)]
    assert state.state == "grounded"
    assert state.rung == "opus"
    assert state.terminal == "grounded@opus"
    # The history records where it came from, so the census can say what climbed.
    assert state.history == ["sonnet:escalate"]
    # And the parser-first finding raised at 2a survived the climb.
    assert any(
        f["target_id"] == target and "manifest" in f["finding"]
        for f in outcome.parser_findings
    )


# --- 3. the ladder terminates -------------------------------------------------


def test_every_terminal_state_is_reachable_and_the_ladder_stops(world):
    """One run, four terminal states, no loop."""
    ids = world["components"]
    assert len(ids) >= 4, "the fixture needs at least four components for this test"
    grounded_at_sonnet, at_opus, at_fable, gapped = ids[0], ids[1], ids[2], ids[3]

    plan = {cid: ("ground",) for cid in ids}
    plan[grounded_at_sonnet] = ("ground",)
    plan[at_opus] = ("gap", "ground", "ground")
    plan[at_fable] = ("gap", "gap", "ground")
    plan[gapped] = ("gap", "gap", "gapdecl")

    result, outcome, invoker, ctx = _run(world, plan)

    assert result.ok is True
    terminals = {cid: outcome.states[("component", cid)].terminal for cid in ids[:4]}
    assert terminals[grounded_at_sonnet] == "grounded@sonnet"
    assert terminals[at_opus] == "grounded@opus"
    assert terminals[at_fable] == "grounded@fable"
    assert terminals[gapped] == "honest-gap"

    # Exactly three rungs ran. There is no fourth.
    rungs = set()
    for prompt in invoker.prompts:
        rungs.add("2c" if "LAST rung" in prompt else "2b" if "HIGHER RUNG" in prompt else "2a")
    assert rungs == {"2a", "2b", "2c"}

    census = outcome.census
    assert census.by_state["grounded@sonnet"] >= 1
    assert census.by_state["grounded@opus"] == 1
    assert census.by_state["grounded@fable"] == 1
    assert census.by_state["honest-gap"] == 1
    # Nothing is left asking to climb.
    assert census.unresolved == []


def test_an_honest_gap_is_visible_in_the_product_with_its_reason(world):
    gapped = world["components"][3]
    plan = {cid: ("ground",) for cid in world["components"]}
    plan[gapped] = ("gap", "gap", "gapdecl")

    _, outcome, _, ctx = _run(world, plan)

    store = FactStore(str(world["db"]))
    try:
        rows = {
            (r["target_kind"], r["target_id"]): r["payload"]
            for r in store.enrichment()
        }
    finally:
        store.close()
    payload = rows[("component", gapped)]
    assert payload["honest_gaps"] == [{
        "question": "mechanism",
        "why": "the dispatch table is generated at build time and no source file "
               "contains it",
    }]
    assert payload["help_text"]  # the rest of the product is intact


def test_an_item_the_last_rung_ignores_still_terminates_as_an_honest_gap(world):
    """No fake answer, no infinite loop, and not silently reported as grounded."""
    stubborn = world["components"][0]
    plan = {cid: ("ground",) for cid in world["components"]}
    plan[stubborn] = ("gap", "silent", "silent")

    _, outcome, _, _ = _run(world, plan)

    state = outcome.states[("component", stubborn)]
    assert state.terminal == "honest-gap"
    assert outcome.census.unresolved == []

    store = FactStore(str(world["db"]))
    try:
        payload = next(
            r["payload"] for r in store.enrichment()
            if r["target_kind"] == "component" and r["target_id"] == stubborn
        )
    finally:
        store.close()
    gaps = payload["honest_gaps"]
    assert gaps and gaps[0]["question"] == "mechanism"
    assert gaps[0]["why"]


def test_a_confident_but_uncitable_answer_climbs_rather_than_standing(world):
    """The E2 path end to end: nothing malformed, caught only by validation."""
    liar = world["components"][0]
    plan = {cid: ("ground",) for cid in world["components"]}
    plan[liar] = ("fake", "ground", "ground")

    _, outcome, invoker, _ = _run(world, plan)

    state = outcome.states[("component", liar)]
    assert state.rung == "opus"
    assert state.history == ["sonnet:escalate"]
    escalation = next(p for p in invoker.prompts if "HIGHER RUNG" in p)
    assert '"trigger": "E2"' in escalation
    assert "invented/never/existed.py" in escalation


# --- 4. importance goes first -------------------------------------------------


def test_partitions_are_ordered_by_their_most_important_component():
    """The ordering contract, tested directly rather than through a fixture.

    Ranked by its BEST component, not its average: one critical component makes
    a partition worth running even when the rest of it is quiet, and averaging
    would let a crowd of trivia outvote it.
    """
    from analyzer.derive.importance import ComponentImportance, ImportanceRanking
    from analyzer.enrich.partition import Partition

    ranking = ImportanceRanking(items=[
        ComponentImportance("critical", score=0.9, band=1),
        ComponentImportance("quiet-a", score=0.1, band=5),
        ComponentImportance("quiet-b", score=0.1, band=5),
        ComponentImportance("middling", score=0.5, band=3),
    ])
    quiet_crowd = Partition(id=0, component_ids=("quiet-a", "quiet-b"), relationship_keys=())
    has_critical = Partition(id=1, component_ids=("critical", "quiet-a"), relationship_keys=())
    middling = Partition(id=2, component_ids=("middling",), relationship_keys=())

    ordered = order_partitions([quiet_crowd, has_critical, middling], ranking)
    assert [p.id for p in ordered] == [1, 2, 0]


def test_partition_ordering_is_total_so_it_is_reproducible():
    from analyzer.derive.importance import ComponentImportance, ImportanceRanking
    from analyzer.enrich.partition import Partition

    ranking = ImportanceRanking(items=[
        ComponentImportance("a", score=0.4, band=2),
        ComponentImportance("b", score=0.4, band=2),
    ])
    parts = [
        Partition(id=7, component_ids=("b",), relationship_keys=()),
        Partition(id=3, component_ids=("a",), relationship_keys=()),
    ]
    assert [p.id for p in order_partitions(parts, ranking)] == [3, 7]
    assert [p.id for p in order_partitions(list(reversed(parts)), ranking)] == [3, 7]


def test_an_unranked_component_does_not_crash_the_ordering():
    from analyzer.derive.importance import ImportanceRanking
    from analyzer.enrich.partition import Partition

    empty = ImportanceRanking(items=[])
    parts = [Partition(id=1, component_ids=("x",), relationship_keys=())]
    assert [p.id for p in order_partitions(parts, empty)] == [1]


def test_the_ceiling_stops_a_later_rung_and_records_it_honestly(world):
    """Partial state is reported as partial, never as complete."""
    target = world["components"][0]
    plan = {cid: ("ground",) for cid in world["components"]}
    plan[target] = ("gap", "gap", "ground")

    # Enough for rung 2a and the 2b batch, not enough to launch 2c.
    _, outcome, invoker, _ = _run(world, plan, ceiling=0.015)

    assert any("cost ceiling reached" in n for n in outcome.notes)
    # The item that needed the last rung is recorded as an honest gap, not as
    # grounded and not as silently missing.
    state = outcome.states[("component", target)]
    assert state.terminal == "honest-gap"
    assert outcome.census.unresolved == []


# --- 5. the product never sees the scaffolding --------------------------------


def test_contract_answers_live_in_their_own_rows_never_in_the_product(world):
    plan = {cid: ("ground",) for cid in world["components"]}
    _run(world, plan)

    store = FactStore(str(world["db"]))
    try:
        rows = store.enrichment()
    finally:
        store.close()

    component_rows = [r for r in rows if r["target_kind"] == "component"]
    contract_rows = [r for r in rows if r["target_kind"] == CONTRACT_TARGET_KIND]
    assert component_rows and contract_rows

    for row in component_rows:
        assert CONTRACT_KEY not in row["payload"]
        assert "answers" not in row["payload"]
        assert row["payload"]["ai_enhance_version"] == 2
        assert row["payload"]["ai_enhanced_at"] == FIXED_CLOCK()

    # The scaffolding is present, in its own rows, with the answers intact.
    sample = contract_rows[0]["payload"]
    assert sample["state"] in ("grounded", "escalate", "honest_gap")
    assert sample["rung"] in ("sonnet", "opus", "fable")
    assert isinstance(sample["answers"], dict)


def test_relationships_are_enriched_and_carry_the_reduced_contract(world):
    if not world["relationships"]:
        pytest.skip("the fixture produced no relationships")
    plan = {cid: ("ground",) for cid in world["components"]}
    _, outcome, _, _ = _run(world, plan)

    rel_states = [s for s in outcome.states.values() if s.target_kind == "relationship"]
    assert rel_states
    assert all(s.state == "grounded" for s in rel_states)

    store = FactStore(str(world["db"]))
    try:
        rel_rows = [r for r in store.enrichment() if r["target_kind"] == "relationship"]
    finally:
        store.close()
    assert rel_rows
    assert all(CONTRACT_KEY not in r["payload"] for r in rel_rows)
    assert all(r["payload"]["importance"] == "internal" for r in rel_rows)


def test_a_dry_run_plans_the_ladder_and_invokes_nothing(world):
    invoker = ScriptedLadder(
        {}, world["real_file"], world["components"], world["relationships"],
        world["facts_by_id"],
    )
    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT,
        run_dir=world["root"] / "run", policy=LadderPolicy(), dry_run=True,
    )
    ctx = build_run_context(config, invoker_factory=lambda spec: invoker, clock=FIXED_CLOCK)
    try:
        run_pipeline(ctx, [LadderPhase()])
    finally:
        ctx.store.close()

    assert invoker.prompts == []
    assert ctx.ledger == []
    data = ctx.results["p2_ladder"].data
    assert data["plan_preview"]
    assert all(p["prompt_tokens_est"] > 0 for p in data["plan_preview"])
    # It says plainly that the upper rungs cannot be planned in advance, rather
    # than reporting a plan that omits them as if they were free.
    assert any("cannot" in n for n in ctx.results["p2_ladder"].notes)
