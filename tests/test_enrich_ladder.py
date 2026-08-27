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
    COMPONENT_CALL_CAP,
    CONTRACT_TARGET_KIND,
    RELATIONSHIP_CALL_CAP,
    LadderPhase,
    build_escalation_prompt,
    merge_payloads,
    order_partitions,
    plan_compact_chunks,
)
from analyzer.enrich.partition import Partition, flatten_components
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
                 facts_by_id=None, duplicate_on_higher=None):
        self.plan = plan
        self.real_file = real_file
        self.all_components = all_components
        self.all_relationships = all_relationships
        # Answer exactly what each component is ASKED, the way a real rung
        # would: the required set is computed from the same facts the
        # validator uses, so a component with a language is asked about it.
        self.facts_by_id = facts_by_id or {}
        self.duplicate_on_higher = duplicate_on_higher
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
        relationship_call = "ENRICHMENT TASK: relationships" in prompt
        ids = [] if relationship_call else [
            cid for cid in self.all_components if f'"{cid}"' in prompt
        ]
        components = {}
        for cid in ids:
            steps = self.plan.get(cid, ("ground",))
            action = steps[rung] if rung < len(steps) else steps[-1]
            block = self._component(cid, action)
            if block is not None:
                components[cid] = block
        relationships = {}
        if relationship_call or '"target_kind": "relationship"' in prompt:
            for key in self.all_relationships:
                if key in prompt:
                    relationships[key] = self._relationship()
        if rung == 1 and self.duplicate_on_higher in components:
            cid = self.duplicate_on_higher
            # Compact arrays can represent the same target twice. The second
            # value must never silently win and ground an ambiguous repair.
            repair = {
                "i": cid,
                "q": {"mechanism": {"t": "a repaired mechanism", "e": [0]}},
            }
            components = [repair, dict(repair)]
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


def _run(world, plan, *, ceiling=None, tmp_path=None, duplicate_on_higher=None):
    invoker = ScriptedLadder(
        plan, world["real_file"], world["components"], world["relationships"],
        world["facts_by_id"], duplicate_on_higher,
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
    assert 'Repair ONLY what "todo" names' in prompt
    assert "Work that passed is finished" in prompt


def test_the_terminal_rung_is_told_to_declare_a_gap_rather_than_paper_over_it(world):
    target = world["components"][0]
    plan = {cid: ("ground",) for cid in world["components"]}
    plan[target] = ("gap", "gap", "gapdecl")

    _, outcome, invoker, _ = _run(world, plan)

    terminal = [p for p in invoker.prompts if "LAST rung" in p]
    assert terminal
    assert "There is no rung after you and there is no loop." in terminal[0]
    assert "is a lie the map tells with confidence" in terminal[0]
    # The addendum demands a reader-facing why, never the boilerplate phrase.
    assert "A gap declared honestly is a correct outcome." in terminal[0]
    assert 'Never write "could not be grounded" as the why' in terminal[0]


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
    assert state.entry_class == "reasoning"
    assert state.entry_class_basis == "lacked:0/trigger:1"
    # The history records where it came from, so the census can say what climbed.
    assert state.history == ["sonnet:escalate"]
    # And the parser-first finding raised at 2a survived the climb.
    assert any(
        f["target_id"] == target and "manifest" in f["finding"]
        for f in outcome.parser_findings
    )


def test_a_duplicate_higher_rung_repair_is_rejected_instead_of_last_write_wins(world):
    target = world["components"][0]
    plan = {cid: ("ground",) for cid in world["components"]}
    plan[target] = ("gap", "ground", "ground")

    _, outcome, _, _ = _run(
        world, plan, duplicate_on_higher=target,
    )

    # Opus's duplicate was ignored, so the unambiguous terminal repair did the
    # grounding. The coverage violation remains in the exit data.
    assert outcome.states[("component", target)].terminal == "grounded@fable"
    assert any(
        "duplicate_components" in note and target in note
        for note in outcome.notes
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
    # The item that needed the last rung stays in the escalate state: the
    # ceiling refused its call, so no model examined it, and an honest gap is a
    # claim of examination. This assertion used to expect honest-gap, and that
    # expectation was itself the poisoning defect in miniature: promoting the
    # never-launched item to a declared gap emptied census.unresolved, which
    # made a truncated run's census read as fully concluded. Partial reported
    # as partial means the item shows up as UNRESOLVED.
    state = outcome.states[("component", target)]
    assert state.state == "escalate"
    assert ("component", target) in {
        (u.target_kind, u.target_id) for u in outcome.census.unresolved
    }, "the unresolved item must be visible in the census"


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
    # Non-empty, and carrying real answers with their evidence. Asserting only
    # that the key is a dict let a defect through that wrote every contract row
    # with an empty answers block: the key was present, so the check passed.
    assert sample["answers"], "the contract row must carry the answers it graded"
    assert "purpose" in sample["answers"]
    assert sample["answers"]["purpose"]["claim"]
    assert sample["answers"]["purpose"]["evidence"]


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


def test_max_partitions_actually_bounds_the_ladder(world):
    """The smoke-run bound binds, and says what it excluded.

    Fail-before: LadderConfig declared max_partitions "for cheap smoke runs"
    and nothing on the ladder path read it, so a --max-partitions 3 smoke run
    against the real VS Code store (2026-08-22) ran all 57 partitions to the
    $45 ceiling. The flag must cap the ordered partition list, keep the most
    important partitions, and declare the exclusion in the run's notes.
    """

    class RefuseToInvoke:
        prompts: list = []

        def __call__(self, prompt):
            raise AssertionError("a dry run must not invoke")

    # Force one partition per component so the fixture yields several, then
    # cap to one.
    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT,
        run_dir=world["root"] / "run-cap", policy=LadderPolicy(), dry_run=True,
        max_partitions=1, max_components=1, min_components=1,
    )
    ctx = build_run_context(
        config, invoker_factory=lambda spec: RefuseToInvoke(), clock=FIXED_CLOCK
    )
    # The bounds must survive the config-to-context seam; this is where they
    # previously died.
    assert ctx.max_partitions == 1
    assert ctx.max_components == 1
    assert ctx.min_components == 1
    try:
        run_pipeline(ctx, [LadderPhase()])
        result = ctx.results["p2_ladder"]
    finally:
        ctx.store.close()

    preview = result.data["plan_preview"]
    assert len(preview) == 1, "the cap must bound what the ladder will attempt"
    notes = " ".join(result.notes)
    assert "capped to the 1 most important partition(s)" in notes
    assert "not attempted" in notes


# --- the honest_gap poisoning regression (2026-08-25 incident) ----------------


class _AuthDiesAtTerminal:
    """Delegates to the scripted ladder until the LAST rung, then fails every
    call the way the real incident did: instantly, identically, at $0.00."""

    def __init__(self, inner):
        self._inner = inner
        self.prompts = inner.prompts

    def __call__(self, prompt: str) -> InvokeResult:
        if "LAST rung" in prompt:
            return InvokeResult(
                ok=False, text="",
                error="claude exited 1: Failed to authenticate: OAuth session "
                      "expired and could not be refreshed",
            )
        return self._inner(prompt)


def test_a_failed_terminal_call_never_becomes_an_honest_gap(world, tmp_path):
    """The poisoning defect, pinned.

    In the first real enrichment run an OAuth expiry killed every terminal-rung
    call, and 106 items no model ever examined were stamped honest_gap: "we
    looked and could not establish this" about items nobody looked at. An
    honest gap is a claim about the CODE; a failed call is a claim about the
    RUN. An item whose terminal call fails must stay in the escalate state,
    which the census reports as unresolved and a rerun re-targets.
    """
    stubborn = world["components"][0]
    plan = {cid: ("ground",) for cid in world["components"]}
    plan[stubborn] = ("gap", "gap", "gap")  # climbs all the way to terminal

    scripted = ScriptedLadder(
        plan, world["real_file"], world["components"], world["relationships"],
        world["facts_by_id"],
    )
    invoker = _AuthDiesAtTerminal(scripted)
    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT, run_dir=tmp_path / "run",
        policy=LadderPolicy(),
    )
    ctx = build_run_context(
        config, invoker_factory=lambda spec: invoker, clock=FIXED_CLOCK
    )
    ctx.budget = BudgetMeter(ceiling=None)
    try:
        run_pipeline(ctx, [LadderPhase()])
        outcome = ctx.results["p2_ladder"].data["ladder"]

        state = outcome.states[("component", stubborn)]
        assert state.state == "escalate", (
            "a terminal call that never returned must leave the item "
            "unresolved, not declared"
        )
        assert not any(
            s.target_id == stubborn for s in outcome.honest_gaps
        ), "no model examined it, so no gap may be declared for it"
        assert any(
            "terminal call failed or was never launched" in n
            for n in outcome.notes
        ), "the run must say out loud why the item was left unresolved"

        # And nothing wrote a gap payload to the store for it.
        rows = [
            r for r in ctx.store.enrichment()
            if r["target_kind"] == "component" and r["target_id"] == stubborn
            and "honest_gaps" in (r.get("payload") or {})
        ]
        assert not rows
    finally:
        ctx.store.close()


def test_an_examined_item_the_terminal_model_leaves_ungapped_still_gaps(world):
    """The healthy half must survive the fix: when the terminal CALL returns
    and the model omits an item, the item is an honest gap exactly as before.
    (This is the existing ignores-test's semantics, restated beside the
    regression so the two halves of the rule live together.)"""
    stubborn = world["components"][0]
    plan = {cid: ("ground",) for cid in world["components"]}
    plan[stubborn] = ("gap", "silent", "silent")

    _, outcome, _, _ = _run(world, plan)
    assert outcome.states[("component", stubborn)].state == "honest_gap"


# --- the call plan and the store's terminal truth ------------------------------


def test_the_call_plan_chunks_components_at_21_and_relationships_at_80():
    # The G2 arithmetic prices a component call at targets x central block x
    # dispersion against the output ceiling; 21 is the largest count that
    # clears it at the 1.90 default. A 40-component partition must plan two
    # calls, and no chunk may exceed the caps.
    part = Partition(
        id=0,
        component_ids=tuple(f"c{i}" for i in range(40)),
        relationship_keys=tuple(f"r{i}" for i in range(200)),
        answers_components=True,
    )
    chunks = plan_compact_chunks([part])
    component_chunks = [p for kind, p in chunks if kind == "component"]
    relationship_chunks = [p for kind, p in chunks if kind == "relationship"]
    assert [len(p.answered_component_ids) for p in component_chunks] == [21, 19]
    assert [len(p.relationship_keys) for p in relationship_chunks] == [80, 80, 40]
    for p in component_chunks:
        assert len(p.answered_component_ids) <= COMPONENT_CALL_CAP
    for p in relationship_chunks:
        assert len(p.relationship_keys) <= RELATIONSHIP_CALL_CAP
    # Every id appears exactly once across the plan: chunking never loses or
    # duplicates a target.
    planned_c = [cid for p in component_chunks for cid in p.answered_component_ids]
    planned_r = [key for p in relationship_chunks for key in p.relationship_keys]
    assert planned_c == [f"c{i}" for i in range(40)]
    assert planned_r == [f"r{i}" for i in range(200)]


def test_the_stored_contract_rows_agree_with_the_census(world):
    # The census is derived from in-memory states; the store is what every
    # later phase and rerun reads. The 2026-08-26 v2 build shipped a store
    # that disagreed with its own census by 47 rows because state transitions
    # carrying no new payload never re-stamped their contract row. _finalize
    # now reconciles them, and this test holds that terminal truth forever
    # (predicate P6).
    stubborn = world["components"][0]
    plan = {cid: ("ground",) for cid in world["components"]}
    plan[stubborn] = ("gap", "gap", "gapdecl")

    _, outcome, _, _ = _run(world, plan)

    store = FactStore(str(world["db"]))
    try:
        stored = {}
        for row in store.enrichment():
            if row.get("target_kind") != CONTRACT_TARGET_KIND:
                continue
            state = (row.get("payload") or {}).get("state") or "?"
            stored[state] = stored.get(state, 0) + 1
    finally:
        store.close()

    census = {}
    for key, count in outcome.census.by_state.items():
        base = str(key).split("@")[0].replace("honest-gap", "honest_gap")
        census[base] = census.get(base, 0) + count
    assert stored == census, (
        f"store {stored} disagrees with census {census}: the store is lying "
        "about terminal states"
    )
