"""T1: the phase seam. Mock phases, no store, no model, no time.

Four contracts, each with a fail-before contrast where one is meaningful:

  1. ORDER AND HANDOFF. Phases run in registry order and each sees its
     predecessors' results on the context, so a phase reads what came before it
     from the context rather than by importing another phase.
  2. BULKHEAD. A phase that raises is recorded failed with a scrubbed
     deterministic reason and the pipeline CONTINUES, because the Run Report is
     written even on partial failure. Fail-before contrast: without the bulkhead
     the exception would propagate and no later phase would run.
  3. SHARED BUDGET. One meter spans all phases. Once the ceiling is reached, a
     later phase is recorded skipped rather than run, the terminal phase still
     runs (the run only exits through P5), and a metered invoker called past the
     ceiling spends nothing and says so.
  4. LEDGER COMPLETENESS. Every invocation through a metered invoker appends a
     ledger row carrying phase, rung, model, tokens and API-equivalent cost, and
     the retry count is the real transport attempt count, not a hardcoded zero.
"""

from __future__ import annotations

from pathlib import Path

from analyzer.enrich.engine import InvokeResult
from analyzer.enrich.pipeline import (
    DEFAULT_MODELS,
    BudgetMeter,
    LadderPolicy,
    Phase,
    PhaseResult,
    RunContext,
    run_pipeline,
)
from analyzer.enrich.retry import RetryingInvoker, RetryPolicy


# --- seams -------------------------------------------------------------------


class FakeClock:
    """Monotonic-looking timer that advances a fixed step per read."""

    def __init__(self, step: float = 0.5) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


def _context(*, ceiling=None, invoker_factory=None) -> RunContext:
    """A context with no store and no arch: the seam itself is what is under test."""
    return RunContext(
        store=None,
        root=Path("/nonexistent"),
        store_path=Path("/nonexistent/index.db"),
        arch={},
        facts=None,
        index=None,
        policy=LadderPolicy(max_cost_usd=ceiling),
        budget=BudgetMeter(ceiling=ceiling),
        invoker_factory=invoker_factory or (lambda model: None),
        run_dir=Path("/nonexistent/run"),
        timer=FakeClock(),
    )


class RecordingPhase:
    """Records the phase names it could see on the context when it ran."""

    def __init__(self, name: str, order: list) -> None:
        self.name = name
        self.order = order

    def run(self, ctx: RunContext) -> PhaseResult:
        self.order.append((self.name, sorted(ctx.results)))
        return PhaseResult(name=self.name, data={"saw": sorted(ctx.results)})


class RaisingPhase:
    def __init__(self, name: str) -> None:
        self.name = name

    def run(self, ctx: RunContext) -> PhaseResult:
        raise ValueError("deliberate phase explosion")


class SpendingPhase:
    """Burns a fixed cost through a metered invoker, the way a real phase does."""

    def __init__(self, name: str, cost: float, calls: int = 1) -> None:
        self.name = name
        self.cost = cost
        self.calls = calls

    def run(self, ctx: RunContext) -> PhaseResult:
        invoker = ctx.invoker("p2a_bulk", phase=self.name, rung="2a", targets=3)
        for _ in range(self.calls):
            invoker("prompt")
        return PhaseResult(name=self.name)


# --- 1. order and handoff -----------------------------------------------------


def test_phases_run_in_order_and_see_their_predecessors():
    order: list = []
    ctx = _context()
    phases: list[Phase] = [
        RecordingPhase("p1_orientation", order),
        RecordingPhase("p2_ladder", order),
        RecordingPhase("p5_determination", order),
    ]

    result = run_pipeline(ctx, phases)

    assert [p.name for p in result.phases] == [
        "p1_orientation",
        "p2_ladder",
        "p5_determination",
    ]
    # Each phase saw exactly the phases that ran before it, from the context.
    assert order[0][1] == []
    assert order[1][1] == ["p1_orientation"]
    assert order[2][1] == ["p1_orientation", "p2_ladder"]
    assert result.ok is True


# --- 2. bulkhead --------------------------------------------------------------


def test_a_raising_phase_is_bulkheaded_and_the_pipeline_continues():
    order: list = []
    ctx = _context()
    phases: list[Phase] = [
        RaisingPhase("p2_ladder"),
        RecordingPhase("p5_determination", order),
    ]

    result = run_pipeline(ctx, phases)

    failed = result.phases[0]
    assert failed.status == "failed"
    assert "unexpected error" in failed.notes[0]
    # Scrubbed and deterministic: the exception type and message, no traceback.
    assert "ValueError: deliberate phase explosion" in failed.notes[0]
    assert "Traceback" not in failed.notes[0]
    # The pipeline continued: the terminal phase still ran, so a report is possible.
    assert result.phases[1].status == "ok"
    assert [name for name, _ in order] == ["p5_determination"]
    assert result.failed_phases == ["p2_ladder"]
    assert result.ok is False


# --- 3. shared budget ---------------------------------------------------------


def test_one_budget_spans_phases_and_the_terminal_phase_still_runs():
    order: list = []
    ctx = _context(
        ceiling=1.0,
        invoker_factory=lambda model: (lambda prompt: InvokeResult(ok=True, text="{}", cost_usd=0.6)),
    )
    phases: list[Phase] = [
        SpendingPhase("p2_ladder", cost=0.6, calls=2),  # spends 1.2, over the 1.0 ceiling
        RecordingPhase("p4_synthesis", order),
        RecordingPhase("p5_determination", order),
    ]

    result = run_pipeline(ctx, phases)

    by_name = {p.name: p for p in result.phases}
    assert by_name["p2_ladder"].status == "ok"
    # A non-terminal phase past the ceiling is skipped, not run.
    assert by_name["p4_synthesis"].status == "skipped"
    assert "cost ceiling reached" in by_name["p4_synthesis"].notes[0]
    # The run only exits through P5, so the terminal phase runs regardless.
    assert by_name["p5_determination"].status == "ok"
    assert [name for name, _ in order] == ["p5_determination"]
    assert result.ceiling_hit is True
    assert ctx.budget.spent == 1.2


def test_a_metered_invoker_past_the_ceiling_spends_nothing_and_says_so():
    calls = {"n": 0}

    def factory(model):
        def invoke(prompt):
            calls["n"] += 1
            return InvokeResult(ok=True, text="{}", cost_usd=5.0)

        return invoke

    ctx = _context(ceiling=1.0, invoker_factory=factory)
    invoker = ctx.invoker("p2a_bulk", phase="p2_ladder", rung="2a")

    first = invoker("prompt")
    assert first.ok is True
    assert calls["n"] == 1

    second = invoker("prompt")
    assert second.ok is False
    assert "cost ceiling reached" in (second.error or "")
    # The underlying invoker was never reached, so nothing was spent.
    assert calls["n"] == 1
    assert ctx.budget.spent == 5.0
    # The refusal is ledgered, so the report shows what the ceiling stopped.
    assert ctx.ledger[-1].ok is False
    assert ctx.ledger[-1].cost_usd == 0.0


# --- 4. ledger completeness ---------------------------------------------------


def test_every_invocation_ledgers_phase_rung_model_tokens_and_cost():
    def factory(model):
        return lambda prompt: InvokeResult(
            ok=True,
            text="{}",
            cost_usd=0.25,
            usage={"input_tokens": 100, "cache_read_input_tokens": 20, "output_tokens": 7},
        )

    ctx = _context(invoker_factory=factory)
    run_pipeline(ctx, [SpendingPhase("p2_ladder", cost=0.25, calls=2)])

    assert len(ctx.ledger) == 2
    row = ctx.ledger[0]
    assert row.phase == "p2_ladder"
    assert row.rung == "2a"
    assert row.model == DEFAULT_MODELS["p2a_bulk"]
    assert row.targets == 3
    assert row.tokens_in == 120  # input plus cache reads, which are input work
    assert row.tokens_out == 7
    assert row.cost_usd == 0.25
    assert row.wall_seconds > 0
    assert row.retries == 0
    assert row.ok is True


def test_the_ledger_retry_count_is_the_real_transport_attempt_count():
    """Fail-before contrast: this is the field that would silently read zero.

    The ledger claims a retry count per invocation. It can only do that because
    RetryingInvoker now records the attempts it used; a wrapper that did not
    expose it would report zero retries on a call that in fact retried twice,
    which is a false number in the Run Report rather than a missing one.
    """
    attempts = {"n": 0}

    def flaky(prompt: str) -> InvokeResult:
        attempts["n"] += 1
        if attempts["n"] < 3:
            # A transient shape (5xx) so the retry layer classifies it as retryable.
            return InvokeResult(ok=False, text="", error="overloaded", status_code=529)
        return InvokeResult(ok=True, text="{}", cost_usd=0.1)

    retrying = RetryingInvoker(
        flaky,
        RetryPolicy(max_attempts=4),
        sleep=lambda _s: None,
        monotonic=FakeClock(0.01),
    )
    ctx = _context(invoker_factory=lambda model: retrying)

    invoker = ctx.invoker("p2a_bulk", phase="p2_ladder", rung="2a")
    result = invoker("prompt")

    assert result.ok is True
    assert attempts["n"] == 3
    assert ctx.ledger[-1].retries == 2  # three attempts is two retries
