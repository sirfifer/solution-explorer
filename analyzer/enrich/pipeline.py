"""The phase seam: composable phases and rungs over one shared run context.

This is the spine of the Enrichment Engine (``docs/publication/ENRICHMENT-ENGINE.md``
section 2). The existing :mod:`analyzer.enrich.engine` remains the bulk-enrichment
worker (invoker, transport retry, cost ceiling, partition loop); this module adds
the structure above it: an ordered set of phases (P0 context, P1 orientation, P2
the ladder, P3 adjudication, P4 synthesis, P5 determination), one shared budget
meter across all of them, a per-model invoker factory so each rung runs on its
own model, and a work ledger that records every invocation.

Three properties this seam exists to guarantee:

1. **One budget, many phases.** The engine's per-run cost ceiling meters a single
   partition loop. A ladder run spends across six phases and three rungs, so the
   meter has to be shared. :class:`BudgetMeter` carries the engine's semantics
   upward: stop launching new work once the ceiling is reached, let in-flight work
   finish, record the rest as skipped, and exit honestly with partial state.

2. **The run only exits through P5.** A phase that fails is recorded and the
   pipeline continues, because the Run Report is written even on partial failure
   (design section 5). A phase raising an unexpected exception is bulkheaded the
   same way the engine bulkheads a partition: a scrubbed deterministic reason, no
   traceback, no crash of the whole run.

3. **Every invocation is metered and ledgered.** Phases never call an invoker
   directly. They ask the context for one via :meth:`RunContext.invoker`, which
   wraps the model-specific invoker in a :class:`MeteredInvoker` that charges the
   shared budget and appends a :class:`LedgerRow`. The Run Report's work ledger is
   therefore a byproduct of the seam rather than something a phase must remember
   to maintain.

Cost figures throughout are API-equivalent units the ``claude`` CLI reports,
metered against the owner's subscription. They are never money spent. See
``ENRICHMENT-ENGINE.md`` section 2.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Protocol

from ..contracts import gap_from_exception
from .engine import ClaudeCliInvoker, Invoker, InvokeResult
from .provenance import Clock, iso_now

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..store import FactStore
    from .digest import DigestIndex
    from .prompts import StoreFacts

__all__ = [
    "BudgetMeter",
    "BudgetExhausted",
    "LedgerRow",
    "IterationPolicy",
    "LadderPolicy",
    "MeteredInvoker",
    "Phase",
    "PhaseResult",
    "PipelineResult",
    "RunContext",
    "default_invoker_factory",
    "run_pipeline",
    "DEFAULT_MODELS",
    "PHASE_ORDER",
]

# Which model each phase and rung runs on (design section 2). Keys are the
# pipeline's own phase/rung names, not CLI model ids, so a registry or a flag can
# repoint one rung without touching any phase code.
DEFAULT_MODELS: dict[str, str] = {
    "p1_orientation": "fable",
    "p2a_bulk": "sonnet",
    "p2b_escalated": "opus",
    "p2c_residue": "fable",
    "p3_adjudication": "opus",
    "p4_synthesis": "fable",
    "p5_determination": "fable",
    "workorder": "sonnet",
}

# The canonical phase order. P0 is deterministic context assembly and never
# invokes a model.
PHASE_ORDER: tuple[str, ...] = (
    "p0_context",
    "p1_orientation",
    "p2_ladder",
    "p3_adjudication",
    "p4_synthesis",
    "p5_determination",
)


class BudgetExhausted(RuntimeError):
    """Raised when work is attempted past the shared ceiling.

    Phases are expected to check :meth:`BudgetMeter.under` before launching, the
    way the engine checks before submitting a partition. This exception is the
    backstop for a phase that does not, so spend past the ceiling is impossible
    rather than merely discouraged.
    """


@dataclass
class BudgetMeter:
    """One cost meter shared by every phase and rung of a ladder run.

    ``ceiling`` is the API-equivalent dollar ceiling for the whole run; None
    disables it. The meter is soft in exactly the way the engine's is: work
    already in flight when the ceiling is reached runs to completion, so the
    total can exceed the ceiling by up to one batch, and no NEW work launches.
    """

    ceiling: Optional[float] = None
    spent: float = 0.0
    charges: int = 0

    def under(self) -> bool:
        """True while new work may be launched."""
        return self.ceiling is None or self.spent < self.ceiling

    def remaining(self) -> Optional[float]:
        if self.ceiling is None:
            return None
        return max(0.0, self.ceiling - self.spent)

    def charge(self, cost_usd: float) -> None:
        self.spent += max(0.0, float(cost_usd or 0.0))
        self.charges += 1

    def require(self) -> None:
        if not self.under():
            raise BudgetExhausted(
                f"run cost ceiling reached (${self.ceiling:.2f} API-equivalent)"
            )


@dataclass
class LedgerRow:
    """One row of the Run Report work ledger (design section 5).

    A row is one logical invocation: phase, rung, model, how many targets it
    covered, tokens in and out, API-equivalent cost, wall seconds, and how many
    transport retries the invoker reported underneath it.
    """

    phase: str
    rung: Optional[str]
    model: str
    targets: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    wall_seconds: float = 0.0
    retries: int = 0
    ok: bool = True
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "rung": self.rung,
            "model": self.model,
            "targets": self.targets,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 6),
            "wall_seconds": round(self.wall_seconds, 3),
            "retries": self.retries,
            "ok": self.ok,
            "error": self.error,
        }


def _usage_tokens(usage: dict) -> tuple[int, int]:
    """Pull (input, output) token counts out of a CLI usage block.

    The CLI reports ``input_tokens`` and ``output_tokens``, plus cache read and
    creation counts on a cached call. Cache-creation tokens are billed as input
    work, so they are counted as input; a missing or malformed block reads as
    zero rather than raising, because a ledger row must never be the thing that
    fails a run.
    """
    if not isinstance(usage, dict):
        return 0, 0

    def _int(key: str) -> int:
        try:
            return int(usage.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    tokens_in = (
        _int("input_tokens")
        + _int("cache_creation_input_tokens")
        + _int("cache_read_input_tokens")
    )
    return tokens_in, _int("output_tokens")


class MeteredInvoker:
    """Wrap an invoker so every call charges the shared budget and ledgers itself.

    Phases obtain one of these from :meth:`RunContext.invoker` rather than holding
    a raw invoker, which is what makes the work ledger complete by construction.
    A call attempted past the ceiling returns a failed :class:`InvokeResult` with
    a budget reason instead of spending, and is ledgered as a zero-cost failure so
    the report shows what the ceiling stopped.
    """

    def __init__(
        self,
        inner: Invoker,
        *,
        ctx: RunContext,
        phase: str,
        rung: Optional[str],
        model: str,
        targets: int = 0,
    ) -> None:
        self._inner = inner
        self._ctx = ctx
        self.phase = phase
        self.rung = rung
        self.model = model
        self.targets = targets
        self.calls = 0

    def __call__(self, prompt: str) -> InvokeResult:
        self.calls += 1
        if not self._ctx.budget.under():
            row = LedgerRow(
                phase=self.phase,
                rung=self.rung,
                model=self.model,
                targets=self.targets,
                ok=False,
                error="not invoked: run cost ceiling reached",
            )
            self._ctx.ledger.append(row)
            return InvokeResult(
                ok=False, text="", error="not invoked: run cost ceiling reached"
            )
        started = self._ctx.timer()
        result = self._inner(prompt)
        wall = max(0.0, self._ctx.timer() - started)
        tokens_in, tokens_out = _usage_tokens(result.usage)
        self._ctx.budget.charge(result.cost_usd)
        # RetryingInvoker exposes the attempt count it used for the last logical
        # invoke; a plain invoker does not, so absence reads as no retries.
        retries = int(getattr(self._inner, "last_attempts", 1) or 1) - 1
        self._ctx.ledger.append(
            LedgerRow(
                phase=self.phase,
                rung=self.rung,
                model=self.model,
                targets=self.targets,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=result.cost_usd,
                wall_seconds=wall,
                retries=max(0, retries),
                ok=result.ok,
                error=result.error,
            )
        )
        return result


@dataclass
class IterationPolicy:
    """P5's bounded loop (design section 3, forced iteration).

    ``min_rounds`` is the forced-improvement floor: on the first Wave 1 subjects
    the determination must run at least one improvement round even when it
    believes the map is done. ``max_rounds`` caps the loop so "not done" can never
    spin.
    """

    min_rounds: int = 1
    max_rounds: int = 2

    def normalized(self) -> IterationPolicy:
        lo = max(0, int(self.min_rounds))
        hi = max(lo, int(self.max_rounds))
        return IterationPolicy(min_rounds=lo, max_rounds=hi)


@dataclass
class LadderPolicy:
    """Everything a run needs to know that is not a fact about the subject."""

    models: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MODELS))
    iteration: IterationPolicy = field(default_factory=IterationPolicy)
    max_cost_usd: Optional[float] = None
    # Fraction of grounded items P3 spot-checks, weighted by importance.
    spot_check_fraction: float = 0.1
    max_spot_checks: int = 25
    # Cap on work orders a single issuing phase may emit (design 4.6, capped).
    max_work_orders: int = 3
    threshold: float = 85.0
    phases: tuple[str, ...] = PHASE_ORDER

    def model_for(self, key: str) -> str:
        return self.models.get(key, DEFAULT_MODELS.get(key, "sonnet"))


def default_invoker_factory(model: str) -> Invoker:
    """Real invoker for a model name: the `claude` CLI, wrapped in transport retry.

    Only used when a run does not inject its own factory. Every test injects one,
    which is how the whole pipeline is exercised without spending anything.
    """
    from .retry import RetryingInvoker, RetryPolicy

    return RetryingInvoker(ClaudeCliInvoker(model=model), policy=RetryPolicy())


@dataclass
class PhaseResult:
    """What one phase reports back to the pipeline."""

    name: str
    status: str = "ok"  # "ok" | "skipped" | "failed"
    notes: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "notes": list(self.notes)}


class Phase(Protocol):
    """A pipeline phase. Pure protocol so tests can substitute mock phases."""

    name: str

    def run(self, ctx: RunContext) -> PhaseResult:  # pragma: no cover - protocol
        ...


@dataclass
class RunContext:
    """Everything a phase reads and writes, assembled once by P0.

    The context is the only shared mutable state. Phases communicate through
    ``results`` (each phase's PhaseResult, keyed by name) rather than by importing
    one another, which is what keeps the phase set composable and the seam
    testable with mock phases.
    """

    store: FactStore
    root: Path
    store_path: Path
    arch: dict
    facts: StoreFacts
    index: DigestIndex
    policy: LadderPolicy
    budget: BudgetMeter
    invoker_factory: Callable[[str], Invoker]
    run_dir: Path
    commit_sha: Optional[str] = None
    seed: int = 0
    dry_run: bool = False
    clock: Clock = iso_now
    timer: Callable[[], float] = time.monotonic
    scorer: Any = None
    ledger: list[LedgerRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    results: dict[str, PhaseResult] = field(default_factory=dict)
    # Filled in by T9 so P4 and P5 can send work orders back down the ladder.
    # The default records orders without executing them, so a pipeline missing
    # the descent seam degrades visibly rather than silently dropping the order.
    descend: Optional[Callable[[Sequence[Any]], list[Any]]] = None

    def invoker(
        self,
        key: str,
        *,
        phase: str,
        rung: Optional[str] = None,
        targets: int = 0,
    ) -> MeteredInvoker:
        """A metered invoker for one phase or rung, on that key's model."""
        model = self.policy.model_for(key)
        return MeteredInvoker(
            self.invoker_factory(model),
            ctx=self,
            phase=phase,
            rung=rung,
            model=model,
            targets=targets,
        )

    def phase_data(self, name: str) -> dict:
        result = self.results.get(name)
        return result.data if result is not None else {}

    def run_path(self, *parts: str) -> Path:
        path = self.run_dir.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


@dataclass
class PipelineResult:
    """The outcome of a whole ladder run."""

    phases: list[PhaseResult] = field(default_factory=list)
    ledger: list[LedgerRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    ceiling_hit: bool = False

    @property
    def failed_phases(self) -> list[str]:
        return [p.name for p in self.phases if p.status == "failed"]

    @property
    def ok(self) -> bool:
        return not self.failed_phases

    def to_dict(self) -> dict:
        return {
            "phases": [p.to_dict() for p in self.phases],
            "ledger": [row.to_dict() for row in self.ledger],
            "notes": list(self.notes),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "ceiling_hit": self.ceiling_hit,
            "failed_phases": self.failed_phases,
        }


def run_pipeline(ctx: RunContext, phases: Iterable[Phase]) -> PipelineResult:
    """Run phases in order over one context and return the collected result.

    Three behaviours are load bearing and each has a test:

    * A phase that raises is bulkheaded into a ``failed`` PhaseResult carrying a
      scrubbed deterministic reason, and the pipeline continues. One broken phase
      never costs the run its report.
    * Once the shared ceiling is reached, later phases are recorded ``skipped``
      rather than run, except the terminal phase, because the run only exits
      through P5 and the Run Report is written even on partial failure.
    * Every PhaseResult lands in ``ctx.results`` before the next phase starts, so
      a phase reads its predecessors from the context and never by import.
    """
    result = PipelineResult()
    ordered = list(phases)
    terminal = ordered[-1].name if ordered else None

    for phase in ordered:
        if not ctx.budget.under() and phase.name != terminal:
            outcome = PhaseResult(
                name=phase.name,
                status="skipped",
                notes=[
                    "not run: run cost ceiling reached "
                    f"(${ctx.budget.ceiling:.2f} API-equivalent)"
                ],
            )
            result.ceiling_hit = True
        else:
            try:
                outcome = phase.run(ctx)
            except Exception as exc:  # noqa: BLE001 - per-phase bulkhead
                reason = gap_from_exception(
                    f"enrich.{phase.name}", "enrich", exc
                ).reason
                outcome = PhaseResult(
                    name=phase.name,
                    status="failed",
                    notes=[f"phase raised an unexpected error: {reason}"],
                )
        ctx.results[phase.name] = outcome
        result.phases.append(outcome)

    if not ctx.budget.under():
        result.ceiling_hit = True
    result.ledger = list(ctx.ledger)
    result.total_cost_usd = ctx.budget.spent
    result.notes = list(ctx.notes)
    return result


# --- P0: deterministic context assembly --------------------------------------


@dataclass
class LadderConfig:
    """Configuration for one ladder run, the P2-and-above analogue of EnhanceConfig."""

    store_path: Path
    root: Path
    run_dir: Path
    policy: LadderPolicy = field(default_factory=LadderPolicy)
    dry_run: bool = False
    seed: int = 0
    # Cap the number of bulk targets, for cheap smoke runs. None means everything.
    max_partitions: Optional[int] = None
    max_lines: int = 50_000
    max_components: int = 30
    min_components: int = 5


def build_run_context(
    config: LadderConfig,
    *,
    invoker_factory: Optional[Callable[[str], Invoker]] = None,
    clock: Clock = iso_now,
    timer: Callable[[], float] = time.monotonic,
    store: Optional[FactStore] = None,
) -> RunContext:
    """P0: assemble everything deterministic, invoking nothing.

    Derivation, the digest index, the store-fact grounding and the commit sha are
    all pure reads of the store. This is the one place the ladder touches the
    store's derived state, so every phase above works from the same projection and
    a phase can never silently re-derive against different facts.

    ``store`` may be injected by a caller that already holds one open; otherwise
    the caller owns closing the store this returns on ``ctx.store``.
    """
    from ..derive import derive_all
    from ..store import FactStore
    from .digest import DigestIndex
    from .engine import load_scorer
    from .prompts import StoreFacts
    from .provenance import current_commit_sha

    owned = store is None
    store = store or FactStore(str(config.store_path))
    try:
        _, arch = derive_all(store, config.root.name, root_path=str(config.root))
        index = DigestIndex.from_store(store)
        facts = StoreFacts(
            arch,
            store.capabilities(),
            store.data_entities(),
            store.rules(),
            arch.get("relationships", []),
        )
        return RunContext(
            store=store,
            root=config.root,
            store_path=config.store_path,
            arch=arch,
            facts=facts,
            index=index,
            policy=config.policy,
            budget=BudgetMeter(ceiling=config.policy.max_cost_usd),
            invoker_factory=invoker_factory or default_invoker_factory,
            run_dir=config.run_dir,
            commit_sha=current_commit_sha(str(config.root)),
            seed=config.seed,
            dry_run=config.dry_run,
            clock=clock,
            timer=timer,
            scorer=load_scorer(),
        )
    except Exception:
        if owned:
            store.close()
        raise


class NotBuiltPhase:
    """A registered phase whose implementation has not landed yet.

    It reports ``skipped`` with a loud note rather than ``ok``, so an incomplete
    pipeline can never read as a complete one. Every instance is removed as its
    task lands; none survive to the final sweep.
    """

    def __init__(self, name: str, task: str) -> None:
        self.name = name
        self.task = task

    def run(self, ctx: RunContext) -> PhaseResult:
        return PhaseResult(
            name=self.name,
            status="skipped",
            notes=[f"NOT IMPLEMENTED: {self.name} lands in {self.task}"],
        )


def build_phases(policy: LadderPolicy) -> list[Phase]:
    """The phase registry, in canonical order, filtered by the policy.

    Phases are constructed here and nowhere else, so the order and the model each
    rung runs on are settled in one place. A phase name in ``policy.phases`` that
    has no implementation yet yields a NotBuiltPhase, which reports skipped
    loudly.
    """
    registry: dict[str, Callable[[], Phase]] = {}
    phases: list[Phase] = []
    for name in policy.phases:
        if name == "p0_context":
            # P0 is build_run_context, already done before the pipeline runs.
            continue
        factory = registry.get(name)
        phases.append(factory() if factory else NotBuiltPhase(name, "a later task"))
    return phases


def run_ladder(
    config: LadderConfig,
    *,
    invoker_factory: Optional[Callable[[str], Invoker]] = None,
    clock: Clock = iso_now,
    timer: Callable[[], float] = time.monotonic,
    phases: Optional[Iterable[Phase]] = None,
) -> PipelineResult:
    """Top-level ladder entry: P0 context, then every phase, then the result.

    ``phases`` may be injected so tests can drive the seam with mock phases; by
    default the registry builds the real set. The store is opened here and closed
    here, which is why a phase never has to own its lifetime.
    """
    ctx = build_run_context(
        config, invoker_factory=invoker_factory, clock=clock, timer=timer
    )
    try:
        return run_pipeline(ctx, phases if phases is not None else build_phases(config.policy))
    finally:
        ctx.store.close()
