"""The ladder is parallel, observable, and bounded (enrichment operability).

Born from the first real run (2026-08-22): 76 invocations executed strictly one
at a time for 10.8 hours, the registry's 45-minute wall budget was silently
unenforced on the enhance path, the ledger existed only in memory until the
report, and a timed-out call could never retry because the retry budget was
smaller than the per-attempt timeout.

The properties, in the order they matter:

  1. PARALLELISM NEVER CHANGES THE ANSWER. A parallel run and a sequential run
     of the same plan produce identical census, states and notes; parallelism
     buys wall time only.
  2. CALLS ACTUALLY OVERLAP. Proven with a barrier two in-flight calls must
     meet at, which a sequential executor can never satisfy.
  3. THE WALL CEILING IS REAL and stops new launches with an honest reason,
     exactly like the cost ceiling.
  4. THE LEDGER STREAMS. One JSON line per invocation lands in the run
     directory as it happens; a supervisor never faces an eleven-hour silence.
  5. WARM-FIRST. The first call finishes before the fan-out, so the shared
     prompt prefix is cached once, not once per worker.
  6. THE TRIGGER SAYS WHAT IT MEANS. A dry run names the armed limits, the
     projected wall time, and where to watch the run live.
"""

from __future__ import annotations

# ruff: noqa: F811 - `world` is the pytest fixture imported from
# tests.test_enrich_ladder; test parameters shadow the module-level name by
# design, which is how pytest fixture injection works.
import json
import threading
import time

from analyzer.enrich.ladder import LadderPhase
from analyzer.enrich.pipeline import (
    BudgetMeter,
    LadderConfig,
    LadderPolicy,
    PhaseResult,
    build_run_context,
    policy_invoker_factory,
    run_pipeline,
)
from tests.test_enrich_ladder import (  # noqa: F401 - world is a fixture import
    FIXED_CLOCK,
    POLYGLOT,
    ScriptedLadder,
    world,
)


class InstrumentedLadder(ScriptedLadder):
    """ScriptedLadder plus concurrency instrumentation, thread-safe."""

    def __init__(self, *args, delay_s: float = 0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.delay_s = delay_s
        self._lock = threading.Lock()
        self._active = 0
        # Per call: (active_at_start, started_monotonic, ended_monotonic).
        self.timeline = []

    def __call__(self, prompt):
        with self._lock:
            self._active += 1
            active_at_start = self._active
        started = time.monotonic()
        try:
            if self.delay_s:
                time.sleep(self.delay_s)
            return super().__call__(prompt)
        finally:
            ended = time.monotonic()
            with self._lock:
                self._active -= 1
                self.timeline.append((active_at_start, started, ended))


def _plan(world, cycle=("ground", "gap", "fake")):
    """A mixed plan over every component, exercising several terminal paths."""
    return {
        cid: (cycle[i % len(cycle)],)
        for i, cid in enumerate(sorted(world["components"]))
    }


def _run(world, plan, run_dir, *, policy, invoker=None, timer=None):
    """Run the ladder with per-component partitions and a scripted invoker.

    Unlike test_enrich_ladder's helper this does NOT replace ctx.budget, so the
    wall ceiling armed by build_run_context stays armed.
    """
    invoker = invoker or InstrumentedLadder(
        plan, world["real_file"], world["components"], world["relationships"],
        world["facts_by_id"],
    )
    config = LadderConfig(
        store_path=world["db"],
        root=POLYGLOT,
        run_dir=run_dir,
        policy=policy,
        max_components=1,
        min_components=1,
    )
    kwargs = {"invoker_factory": lambda spec: invoker, "clock": FIXED_CLOCK}
    if timer is not None:
        kwargs["timer"] = timer
    ctx = build_run_context(config, **kwargs)
    try:
        result = run_pipeline(ctx, [LadderPhase()])
        outcome = ctx.results["p2_ladder"].data["ladder"]
        return result, outcome, invoker, ctx
    finally:
        ctx.store.close()


def _state_map(outcome):
    return {
        key: (state.state, state.rung)
        for key, state in outcome.states.items()
    }


# --- 1. parallelism never changes the answer ----------------------------------


def test_parallel_and_sequential_runs_agree_everywhere(world, tmp_path):
    plan = _plan(world)

    sequential = InstrumentedLadder(
        plan, world["real_file"], world["components"], world["relationships"],
        world["facts_by_id"],
    )
    _, seq_outcome, _, seq_ctx = _run(
        world, plan, tmp_path / "seq",
        policy=LadderPolicy(max_parallel=1), invoker=sequential,
    )

    # Staggered delays force completion order to differ from submission order,
    # so absorb-in-partition-order is actually exercised, not vacuously true.
    parallel = InstrumentedLadder(
        plan, world["real_file"], world["components"], world["relationships"],
        world["facts_by_id"], delay_s=0.02,
    )
    _, par_outcome, _, par_ctx = _run(
        world, plan, tmp_path / "par",
        policy=LadderPolicy(max_parallel=4), invoker=parallel,
    )

    assert _state_map(par_outcome) == _state_map(seq_outcome)
    assert par_outcome.census.by_state == seq_outcome.census.by_state
    assert par_outcome.notes == seq_outcome.notes
    # The ledger's event ORDER is completion order, which is real timing
    # information and legitimately differs; what must agree is what ran.
    def ledger_multiset(ctx):
        return sorted(
            (row.phase, row.rung, row.targets, row.ok) for row in ctx.ledger
        )
    assert ledger_multiset(par_ctx) == ledger_multiset(seq_ctx)


# --- 2. calls actually overlap -------------------------------------------------


def test_parallel_calls_actually_overlap(world, tmp_path):
    """Two in-flight calls meet at a barrier a sequential executor cannot reach."""
    plan = _plan(world, cycle=("ground",))
    barrier = threading.Barrier(2, timeout=15)
    counter = {"n": 0}

    class BarrierLadder(InstrumentedLadder):
        def __call__(self, prompt):
            with self._lock:
                counter["n"] += 1
                call_number = counter["n"]
            # The warm-up call (1) runs alone by design; calls 2 and 3 must
            # coexist or the barrier trips its timeout and the test fails.
            if call_number in (2, 3):
                barrier.wait()
            return super().__call__(prompt)

    invoker = BarrierLadder(
        plan, world["real_file"], world["components"], world["relationships"],
        world["facts_by_id"],
    )
    _, outcome, _, _ = _run(
        world, plan, tmp_path / "run",
        policy=LadderPolicy(max_parallel=4), invoker=invoker,
    )
    assert not barrier.broken
    assert all(state.state == "grounded" for state in outcome.states.values())


# --- 3. the wall ceiling is real -----------------------------------------------


def test_wall_ceiling_stops_launching_with_the_honest_reason(world, tmp_path):
    ticks = {"now": 0.0}

    def timer():
        # Every read advances two minutes: after the first call's metering the
        # five-minute wall is spent, and no new work may launch.
        ticks["now"] += 120.0
        return ticks["now"]

    plan = _plan(world, cycle=("ground",))
    _, outcome, invoker, _ = _run(
        world, plan, tmp_path / "run",
        policy=LadderPolicy(max_parallel=1, max_wall_minutes=5.0, warm_first=True),
        timer=timer,
    )
    notes = " ".join(outcome.notes)
    assert "wall ceiling reached" in notes
    assert "not launched" in notes
    # Far fewer calls than components: the ceiling stopped the fan-out.
    assert len(invoker.timeline) < len(world["components"])


def test_budget_meter_names_which_ceiling_stopped_the_run():
    cost = BudgetMeter(ceiling=1.0)
    cost.charge(2.0)
    assert not cost.under()
    assert "cost ceiling" in cost.stop_reason()

    ticks = {"now": 0.0}

    def timer():
        return ticks["now"]

    wall = BudgetMeter()
    wall.configure_wall(60.0, timer)
    assert wall.under()
    ticks["now"] = 61.0
    assert not wall.under()
    assert "wall ceiling" in wall.stop_reason()


def test_budget_meter_charging_is_thread_safe():
    meter = BudgetMeter(ceiling=None)
    threads = [
        threading.Thread(target=lambda: [meter.charge(0.01) for _ in range(100)])
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert meter.charges == 800
    assert abs(meter.spent - 8.0) < 1e-6


def test_operator_checkpoint_pauses_then_resumes_without_losing_the_run(tmp_path):
    control = tmp_path / "control.json"
    meter = BudgetMeter()
    meter.configure_control(control, 1.0, poll_s=0.01)
    meter.charge(1.05)
    answers = []
    waiter = threading.Thread(target=lambda: answers.append(meter.under()))
    waiter.start()

    deadline = time.time() + 2
    while time.time() < deadline:
        packet = json.loads(control.read_text())
        if packet["state"] == "paused":
            break
        time.sleep(0.01)
    else:
        raise AssertionError("checkpoint never persisted the pause")
    assert waiter.is_alive(), "pause must block new work, not return a partial run"
    assert packet["spent_usd"] == 1.05
    assert "Review the live phase" in packet["recommendation"]

    packet.update({"state": "running", "pause_at_usd": 2.0})
    control.write_text(json.dumps(packet))
    waiter.join(timeout=2)
    assert answers == [True]
    assert meter.pause_at_usd == 2.0


def test_operator_cancel_releases_a_paused_waiter_as_a_cancelled_run(tmp_path):
    control = tmp_path / "control.json"
    meter = BudgetMeter()
    meter.configure_control(control, 1.0, poll_s=0.01)
    meter.charge(1.0)
    answers = []
    waiter = threading.Thread(target=lambda: answers.append(meter.under()))
    waiter.start()
    deadline = time.time() + 2
    while time.time() < deadline:
        packet = json.loads(control.read_text())
        if packet["state"] == "paused":
            break
        time.sleep(0.01)
    packet["state"] = "cancelled"
    control.write_text(json.dumps(packet))
    waiter.join(timeout=2)
    assert answers == [False]
    assert "cancelled by the operator" in meter.stop_reason()


def test_cancelled_pipeline_without_cost_ceiling_skips_cleanly(world, tmp_path):
    """Cancellation is a stop reason of its own; a None ceiling must not format."""
    invoker = InstrumentedLadder(
        _plan(world), world["real_file"], world["components"],
        world["relationships"], world["facts_by_id"],
    )
    ctx = build_run_context(
        LadderConfig(
            store_path=world["db"], root=POLYGLOT, run_dir=tmp_path / "run",
            policy=LadderPolicy(pause_at_cost_usd=50.0),
        ),
        invoker_factory=lambda spec: invoker, clock=FIXED_CLOCK,
    )
    packet = json.loads((tmp_path / "run" / "control.json").read_text())
    packet["state"] = "cancelled"
    (tmp_path / "run" / "control.json").write_text(json.dumps(packet))

    class Phase:
        def __init__(self, name):
            self.name = name

        def run(self, _ctx):
            return PhaseResult(self.name, "ok")

    try:
        result = run_pipeline(ctx, [Phase("first"), Phase("terminal")])
    finally:
        ctx.store.close()

    assert result.phases[0].status == "skipped"
    assert "cancelled by the operator" in result.phases[0].notes[0]
    assert result.phases[1].status == "ok"


def test_operator_pause_and_checkpoint_survive_process_reconstruction(tmp_path):
    control = tmp_path / "control.json"
    first = BudgetMeter()
    first.configure_control(control, 10.0, poll_s=0.01)
    packet = json.loads(control.read_text())
    packet.update({"state": "paused", "pause_at_usd": 12.0, "revision": 9})
    control.write_text(json.dumps(packet))

    reconstructed = BudgetMeter()
    reconstructed.configure_control(control, 99.0, poll_s=0.01)

    persisted = json.loads(control.read_text())
    assert persisted["state"] == "paused"
    assert persisted["revision"] == 9
    assert reconstructed.pause_at_usd == 12.0


def test_cost_reservations_cannot_sum_past_the_run_ceiling():
    meter = BudgetMeter(ceiling=2.0)
    reservations = [meter.reserve(slots=4) for _ in range(4)]
    assert reservations == [0.5, 0.5, 0.5, 0.5]
    assert meter.remaining() == 0.0
    assert meter.under() is False
    meter.settle(reservations[0], 0.1)
    assert abs(meter.spent - 0.1) < 1e-9
    assert abs(meter.reserve(slots=4) - 0.4) < 1e-9


# --- 4. the ledger streams ------------------------------------------------------


def test_every_invocation_streams_a_ledger_line(world, tmp_path):
    plan = _plan(world)
    run_dir = tmp_path / "run"
    _, _, _, ctx = _run(
        world, plan, run_dir, policy=LadderPolicy(max_parallel=3),
    )
    stream = run_dir / "ledger.jsonl"
    assert stream.exists()
    lines = [json.loads(line) for line in stream.read_text().splitlines()]
    assert len(lines) == len(ctx.ledger)
    for line in lines:
        assert line["phase"]
        assert "at" in line
        assert "spent_usd" in line


# --- 5. warm-first --------------------------------------------------------------


def test_the_first_call_runs_alone_then_the_pool_fans_out(world, tmp_path):
    plan = _plan(world, cycle=("ground",))
    invoker = InstrumentedLadder(
        plan, world["real_file"], world["components"], world["relationships"],
        world["facts_by_id"], delay_s=0.02,
    )
    _run(
        world, plan, tmp_path / "run",
        policy=LadderPolicy(max_parallel=4, warm_first=True), invoker=invoker,
    )
    assert len(invoker.timeline) >= 3
    ordered = sorted(invoker.timeline, key=lambda t: t[1])
    first_active, _, first_ended = ordered[0]
    assert first_active == 1
    # The warm call fully completes before anything else starts.
    assert all(started >= first_ended for _, started, _ in ordered[1:])


# --- 6. the trigger says what it means ------------------------------------------


def test_dry_run_projects_wall_time_and_names_the_armed_limits(world, tmp_path):
    plan = _plan(world)
    config = LadderConfig(
        store_path=world["db"], root=POLYGLOT, run_dir=tmp_path / "run",
        policy=LadderPolicy(
            max_cost_usd=45.0, max_wall_minutes=45.0, max_parallel=4
        ),
        dry_run=True, max_components=1, min_components=1,
    )
    invoker = InstrumentedLadder(
        plan, world["real_file"], world["components"], world["relationships"],
        world["facts_by_id"],
    )
    ctx = build_run_context(
        config, invoker_factory=lambda spec: invoker, clock=FIXED_CLOCK
    )
    try:
        run_pipeline(ctx, [LadderPhase()])
        notes = " ".join(ctx.results["p2_ladder"].notes)
    finally:
        ctx.store.close()
    assert "projection:" in notes
    assert "Armed limits" in notes
    assert "cost ceiling $45.00" in notes
    assert "wall ceiling 45 min" in notes
    assert "ledger.jsonl" in notes
    assert invoker.timeline == []


# --- 7. timeouts can recover -----------------------------------------------------


def test_the_retry_budget_scales_with_the_invoke_timeout():
    factory = policy_invoker_factory(
        LadderPolicy(invoke_timeout_s=1200, retry_attempts=2)
    )
    invoker = factory("anthropic-claude-cli:sonnet")
    # The per-attempt timeout reached the transport, and the retry budget
    # exceeds it, so a single full timeout no longer exhausts the budget and
    # one recovery attempt is actually possible.
    assert invoker._base.timeout == 1200
    assert invoker._policy.max_attempts == 2
    assert invoker._policy.total_budget_s > 1200
