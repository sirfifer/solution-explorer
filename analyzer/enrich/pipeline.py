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

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Protocol

from ..contracts import gap_from_exception
from .engine import Invoker, InvokeResult
from .models import DEFAULT_SOURCE, ModelSpec, build_invoker
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
    "resolve_models",
    "ModelSpec",
    "run_pipeline",
    "DEFAULT_MODELS",
    "PHASE_ORDER",
]

# Which SOURCE and model each phase and rung runs on (design section 2). Keys are
# the pipeline's own phase and rung names, never vendor ids, so a registry or a
# flag repoints one rung without touching any phase code.
#
# The ladder is a structure, not a vendor. Its rungs are defined by the kind of
# work they do, and today they are BOUND to Claude models on the owner's
# subscription. That binding is configuration: see analyzer/enrich/models.py for
# the source registry, and note that a binding may leave the model unpinned so
# the source routes the call itself.
DEFAULT_MODELS: dict[str, ModelSpec] = {
    "p1_orientation": ModelSpec(DEFAULT_SOURCE, "fable"),
    "p2a_bulk": ModelSpec(DEFAULT_SOURCE, "sonnet"),
    "p2b_escalated": ModelSpec(DEFAULT_SOURCE, "opus"),
    "p2c_residue": ModelSpec(DEFAULT_SOURCE, "fable"),
    "p3_adjudication": ModelSpec(DEFAULT_SOURCE, "opus"),
    "p4_synthesis": ModelSpec(DEFAULT_SOURCE, "fable"),
    "p5_determination": ModelSpec(DEFAULT_SOURCE, "fable"),
    "workorder": ModelSpec(DEFAULT_SOURCE, "sonnet"),
}


def resolve_models(
    raw: Optional[dict] = None, *, default_source: str = DEFAULT_SOURCE
) -> dict[str, ModelSpec]:
    """Merge tier bindings over the defaults, parsing every accepted form.

    Unknown keys are kept rather than dropped: a caller binding a rung this build
    does not know about is configuring something for a later one, and silently
    discarding it would be worse than carrying it.
    """
    out = dict(DEFAULT_MODELS)
    for key, value in (raw or {}).items():
        out[str(key)] = ModelSpec.parse(value, default_source=default_source)
    return out

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

# The output budget one response may use, thinking and answer text together.
DEFAULT_OUTPUT_CEILING = 64_000
# Warn once a response comes within this share of the ceiling. A response at
# 88% of the limit is not comfortable, it is one slightly longer answer away
# from truncating, and the 2026-08-25 run's very first call sat at exactly that
# figure while the run continued for another 99 minutes.
OUTPUT_CEILING_WARN = 0.85
# Projected mean output is multiplied by this before a preflight gate compares
# it against the ceiling. Real per-call output varies around its own mean by a
# wide margin (measured 0.72x to 1.90x across the recorded corpus), so a gate
# that checks the mean alone passes calls that then overflow: applying it to
# the 12 recorded overflows catches only 7. Held at the measured worst case
# until a run at pinned effort recalibrates it.
OUTPUT_DISPERSION_MAX = 1.90
# Characters of prompt text per billed token, used only to size the cacheable
# prefix in the ledger. Measured, not assumed: the mean of prefix characters
# over cache-creation tokens across 34 real CLI sessions
# (docs/quality/rearchitecture/reviews/ARCHITECT-ON-PROMPT-SPEC.md). It exists
# so the cache audit can compare a call's cache READ against the size of the
# prefix that call sent, which is the only comparison that catches a warm call
# reading somebody else's small entry.
PREFIX_CHARS_PER_TOKEN = 2.385


class BudgetExhausted(RuntimeError):
    """Raised when work is attempted past the shared ceiling.

    Phases are expected to check :meth:`BudgetMeter.under` before launching, the
    way the engine checks before submitting a partition. This exception is the
    backstop for a phase that does not. It prevents a new launch after the
    recorded ceiling is reached; it cannot stop an already-running provider
    response from exceeding a CLI allowance.
    """


@dataclass
class BudgetMeter:
    """One cost meter shared by every phase and rung of a ladder run.

    ``ceiling`` is the API-equivalent dollar ceiling for the whole run; None
    disables it. Provider-capable invokers reserve an allowance before launch,
    so parallel calls cannot each be handed the same remainder. The current
    Claude CLI receives that allowance through ``--max-budget-usd``, but its
    flag is not a server-side single-response cap: a live 2026-08-26 call billed
    more than the value. Overshoot is therefore detected and fails publication;
    an API transport with a hard output-token limit is required to prevent it.
    """

    ceiling: Optional[float] = None
    spent: float = 0.0
    charges: int = 0
    reserved: float = 0.0
    # Optional operator checkpoint. Unlike ``ceiling``, this is deliberately
    # resumable: reaching it persists a decision packet and blocks every NEW
    # launch until the dashboard writes either ``running`` with a higher
    # checkpoint or ``cancelled``. Calls already in flight finish and are
    # banked. The distinction is important: a quality run must not be turned
    # into a partial result merely because an estimate was a little low.
    pause_at_usd: Optional[float] = None
    control_path: Optional[Path] = None
    control_poll_s: float = 0.5
    _cancelled: bool = field(default=False, repr=False, compare=False)
    # The wall-clock ceiling, in seconds, with the same soft semantics as the
    # cost ceiling: work in flight when it is reached runs to completion, and
    # no NEW work launches. Configured via configure_wall because it needs the
    # run's injectable timer; None disables it. Added after the first real run
    # (2026-08-22), whose registry wall budget of 45 minutes was silently
    # unenforced on the enhance path while the run went 10.8 hours.
    wall_ceiling_s: Optional[float] = None
    _wall_timer: Optional[Callable[[], float]] = field(
        default=None, repr=False, compare=False
    )
    _wall_started: Optional[float] = field(default=None, repr=False, compare=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )

    def configure_wall(
        self, ceiling_s: Optional[float], timer: Callable[[], float]
    ) -> None:
        """Arm the wall ceiling. The clock starts at the moment of arming."""
        self.wall_ceiling_s = ceiling_s
        self._wall_timer = timer
        self._wall_started = timer() if ceiling_s is not None else None

    def configure_control(
        self,
        path: Optional[Path],
        pause_at_usd: Optional[float],
        *,
        poll_s: float = 0.5,
    ) -> None:
        """Create the persisted operator-control record for this run.

        A missing path disables interactive control. ``pause_at_usd`` may be
        omitted while retaining explicit dashboard cancel/pause controls.
        """
        self.control_path = Path(path) if path is not None else None
        self.pause_at_usd = (
            max(0.01, float(pause_at_usd))
            if pause_at_usd is not None
            else None
        )
        self.control_poll_s = max(0.01, float(poll_s))
        if self.control_path is not None:
            self.control_path.parent.mkdir(parents=True, exist_ok=True)
            existing = self._control_snapshot()
            if str(existing.get("state") or "") in {
                "running", "paused", "cancelled"
            }:
                # A process restart is not an operator decision. Preserve the
                # durable state and checkpoint exactly as the prior process
                # left them, especially a pause awaiting human review.
                persisted = existing.get("pause_at_usd")
                if persisted is not None:
                    try:
                        self.pause_at_usd = max(0.01, float(persisted))
                    except (TypeError, ValueError):
                        pass
                self._cancelled = existing.get("state") == "cancelled"
                return
            self._write_control(
                state="running",
                reason="operator checkpoint armed",
                recommendation="No action required; the run is proceeding.",
            )

    def _control_snapshot(self) -> dict:
        if self.control_path is None:
            return {}
        try:
            value = json.loads(self.control_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write_control(
        self, *, state: str, reason: str, recommendation: str
    ) -> None:
        if self.control_path is None:
            return
        current = self._control_snapshot()
        payload = {
            "version": 1,
            "state": state,
            "reason": reason,
            "recommendation": recommendation,
            "pause_at_usd": self.pause_at_usd,
            "spent_usd": round(self.spent, 6),
            "reserved_usd": round(self.reserved, 6),
            "completed_calls": self.charges,
            "wall_elapsed_s": self.wall_elapsed_s(),
            "actions": ["resume-with-new-checkpoint", "cancel"],
            "revision": int(current.get("revision") or 0) + 1,
            "updated_at": time.time(),
        }
        tmp = self.control_path.with_name(
            f".{self.control_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, self.control_path)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def _await_operator(self) -> bool:
        """Apply persisted pause/cancel commands before a new launch.

        This method is intentionally called by ``under``. Existing launch sites
        already use that one gate, so a newly added phase cannot accidentally
        bypass operator control. A pause blocks rather than returning false;
        returning false would make the pipeline skip work and publish a partial
        result, exactly the failure this control is designed to prevent.
        """
        if self.control_path is None:
            return not self._cancelled
        announced = False
        while True:
            command = self._control_snapshot()
            state = str(command.get("state") or "running")
            if state == "cancelled":
                self._cancelled = True
                return False
            new_checkpoint = command.get("pause_at_usd")
            if new_checkpoint is not None:
                try:
                    self.pause_at_usd = max(0.01, float(new_checkpoint))
                except (TypeError, ValueError):
                    pass
            threshold_hit = (
                self.pause_at_usd is not None
                and self.spent + self.reserved >= self.pause_at_usd
            )
            if state == "running" and not threshold_hit:
                return True
            if state == "running" and threshold_hit and not announced:
                self._write_control(
                    state="paused",
                    reason=(
                        "operator cost checkpoint reached: "
                        f"${self.spent:.2f} spent with ${self.reserved:.2f} reserved "
                        f"against ${self.pause_at_usd:.2f}"
                    ),
                    recommendation=(
                        "Review the live phase, failures, acceptance and repair rates. "
                        "Resume with a higher checkpoint if behavior is healthy; "
                        "cancel if spend reflects repeated or failed work."
                    ),
                )
                announced = True
            time.sleep(self.control_poll_s)

    def wall_elapsed_s(self) -> Optional[float]:
        if self._wall_started is None or self._wall_timer is None:
            return None
        return max(0.0, self._wall_timer() - self._wall_started)

    def _over_wall(self) -> bool:
        if self.wall_ceiling_s is None:
            return False
        elapsed = self.wall_elapsed_s()
        return elapsed is not None and elapsed >= self.wall_ceiling_s

    # ---- systemic-failure circuit ------------------------------------------
    #
    # The third ceiling, added after a real incident: the claude CLI's OAuth
    # session expired mid-run, every subsequent call failed identically in
    # ~0.6s at $0.00, and the run spent 1.7 HOURS dispatching 10,387 doomed
    # subprocesses. The cost ceiling never tripped because the failures were
    # free, and the wall ceiling was hours away. What should have stopped the
    # run is the run's own shape: thousands of consecutive, byte-identical
    # failures across DIFFERENT prompts is an environment problem, not a work
    # problem, and no amount of continuing can fix an environment problem.
    #
    # The rule is deliberately narrow: only an unbroken run of IDENTICAL
    # normalized error text trips it. Interleaved distinct failures never do,
    # and one success resets the count, so flaky-but-alive transports are
    # untouched. Recovery is cheap by design: enrichment reruns with --update
    # skip everything already banked, so failing fast costs a rerun command,
    # while failing slow costs hours and tells nobody.
    systemic_threshold: int = 5
    _consecutive_identical: int = 0
    _last_error_shape: Optional[str] = None
    _systemic_error: Optional[str] = None

    def note_result(self, ok: bool, error: Optional[str] = None) -> None:
        """Feed every invocation outcome to the circuit. Thread-safe."""
        with self._lock:
            if ok or not error:
                self._consecutive_identical = 0
                self._last_error_shape = None
                return
            shape = " ".join(str(error).lower().split())[:300]
            if shape == self._last_error_shape:
                self._consecutive_identical += 1
            else:
                self._last_error_shape = shape
                self._consecutive_identical = 1
            if (
                self._systemic_error is None
                and self._consecutive_identical >= self.systemic_threshold
            ):
                self._systemic_error = str(error)[:300]

    @property
    def systemic_failure(self) -> Optional[str]:
        return self._systemic_error

    def under(self) -> bool:
        """True while new work may be launched and operator control permits it."""
        if not self._await_operator():
            return False
        if self._systemic_error is not None:
            return False
        if self.ceiling is not None:
            with self._lock:
                if self.spent + self.reserved >= self.ceiling:
                    return False
        return not self._over_wall()

    def stop_reason(self) -> str:
        """Which ceiling stopped the run, for honest notes. Systemic wins ties:
        it is the only one of the three where the fix is outside this run."""
        if self._cancelled:
            return "run cancelled by the operator from the persisted control plane"
        if self._systemic_error is not None:
            return (
                f"systemic failure circuit open: {self.systemic_threshold} "
                f"consecutive identical failures ({self._systemic_error}). "
                f"The environment is broken, not the work; fix it (for auth: "
                f"run `claude` interactively once) and rerun. --update resumes, "
                f"skipping everything already enriched."
            )
        if self.ceiling is not None and self.spent >= self.ceiling:
            return f"run cost ceiling reached (${self.ceiling:.2f} API-equivalent)"
        if self._over_wall():
            return (
                f"run wall ceiling reached ({self.wall_ceiling_s / 60.0:.0f} minutes)"
            )
        return "run ceiling reached"

    def remaining(self) -> Optional[float]:
        if self.ceiling is None:
            return None
        with self._lock:
            return max(0.0, self.ceiling - self.spent - self.reserved)

    def reserve(self, *, slots: int = 1) -> Optional[float]:
        """Reserve one provider call's maximum spend atomically.

        Dividing the run ceiling by the configured concurrency gives every
        simultaneous call a usable allowance while ensuring their maxima sum to
        no more than the run ceiling. Sequential runs receive the entire
        remainder, so the cap does not arbitrarily lower answer quality.
        """
        if self.ceiling is None:
            return None
        with self._lock:
            available = max(0.0, self.ceiling - self.spent - self.reserved)
            if available < 0.01:
                return 0.0
            unit = self.ceiling / max(1, int(slots))
            amount = min(available, unit)
            self.reserved += amount
            return amount

    def settle(self, reservation: Optional[float], cost_usd: float) -> None:
        """Release a reservation and charge the provider's measured cost."""
        with self._lock:
            if reservation is not None:
                self.reserved = max(0.0, self.reserved - max(0.0, reservation))
            self.spent += max(0.0, float(cost_usd or 0.0))
            self.charges += 1

    def charge(self, cost_usd: float) -> None:
        # Locked: with parallel rungs, += from worker threads is a lost-update
        # race, and an undercounted meter is a broken ceiling.
        with self._lock:
            self.spent += max(0.0, float(cost_usd or 0.0))
            self.charges += 1

    def require(self) -> None:
        if not self.under():
            raise BudgetExhausted(self.stop_reason())


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
    tokens_cached: int = 0
    tokens_out: int = 0
    # Cache CREATION is broken out of tokens_in rather than folded into it. The
    # two bill differently (a cache write is 2x base input, a fresh input token
    # is 1x), so a row that merges them cannot distinguish a genuinely large
    # prompt from a continuation turn re-ingesting its own truncated output.
    # That indistinguishability is exactly what hid the 2026-08-25 overflow
    # loop. tokens_in remains the sum for every existing reader; the split is
    # additive.
    tokens_cache_write: int = 0
    tokens_fresh_in: int = 0
    effort: Optional[str] = None
    stop_reason: Optional[str] = None
    num_turns: int = 1
    partition_id: Optional[int] = None
    session_id: Optional[str] = None
    prefix_hash: Optional[str] = None
    # How big the cacheable prefix was, in billed tokens. Without it the cache
    # audit can only ask whether a call read ANY cached tokens, and a call that
    # read a small unrelated entry passes that test while writing its whole
    # prefix again. 0 means the row predates the field or the call sent no
    # prefix; the audit falls back to the zero-read rule for those.
    prefix_tokens_est: int = 0
    response_bytes: int = 0
    output_budget_bytes: Optional[int] = None
    output_budget_ok: Optional[bool] = None
    structured_output_enforced: bool = False
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
            "tokens_cached": self.tokens_cached,
            "tokens_out": self.tokens_out,
            "tokens_cache_write": self.tokens_cache_write,
            "tokens_fresh_in": self.tokens_fresh_in,
            "effort": self.effort,
            "stop_reason": self.stop_reason,
            "num_turns": self.num_turns,
            "partition_id": self.partition_id,
            "session_id": self.session_id,
            "prefix_hash": self.prefix_hash,
            "prefix_tokens_est": self.prefix_tokens_est,
            "response_bytes": self.response_bytes,
            "output_budget_bytes": self.output_budget_bytes,
            "output_budget_ok": self.output_budget_ok,
            "structured_output_enforced": self.structured_output_enforced,
            "cost_usd": round(self.cost_usd, 6),
            "wall_seconds": round(self.wall_seconds, 3),
            "retries": self.retries,
            "ok": self.ok,
            "error": self.error,
        }


def _usage_tokens(usage: dict) -> tuple[int, int, int, int, int]:
    """Pull token counts out of a CLI usage block.

    Returns ``(input, cached, output, cache_write, fresh_in)`` where ``input``
    is the historical sum ``fresh_in + cache_write`` kept for existing readers,
    and the last two are that sum's parts. They are reported separately because
    they bill at different rates: see :class:`LedgerRow`.

    ``input`` is fresh work: ``input_tokens`` plus ``cache_creation`` (both are
    full-price token processing). ``cached`` is ``cache_read_input_tokens``,
    reported SEPARATELY because a cache read costs roughly a tenth of fresh
    input: folding it into tokens_in made the first real run's opus rows read
    as ~743k input per call and made every cost-per-token calibration wrong.
    A missing or malformed block reads as zero rather than raising, because a
    ledger row must never be the thing that fails a run.
    """
    if not isinstance(usage, dict):
        return 0, 0, 0, 0, 0

    def _int(key: str) -> int:
        try:
            return int(usage.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    fresh = _int("input_tokens")
    cache_write = _int("cache_creation_input_tokens")
    return (
        fresh + cache_write,
        _int("cache_read_input_tokens"),
        _int("output_tokens"),
        cache_write,
        fresh,
    )


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
        effort: Optional[str] = None,
        partition_id: Optional[int] = None,
        output_budget_bytes: Optional[int] = None,
    ) -> None:
        self._inner = inner
        self._ctx = ctx
        self.phase = phase
        self.rung = rung
        self.model = model
        self.targets = targets
        self.effort = effort
        self.partition_id = partition_id
        self.output_budget_bytes = output_budget_bytes
        self.calls = 0

    def set_targets(self, value: int) -> None:
        """Set the exact number of targets answered by the next call."""
        self.targets = max(0, int(value))

    def __call__(self, prompt: str) -> InvokeResult:
        self.calls += 1
        if not self._ctx.budget.under():
            reason = f"not invoked: {self._ctx.budget.stop_reason()}"
            row = LedgerRow(
                phase=self.phase,
                rung=self.rung,
                model=self.model,
                targets=self.targets,
                ok=False,
                error=reason,
            )
            self._ctx.record_ledger_row(row)
            return InvokeResult(ok=False, text="", error=reason)
        reservation: Optional[float] = None
        budget_setter = getattr(self._inner, "set_max_budget_usd", None)
        if callable(budget_setter) and self._ctx.budget.ceiling is not None:
            reservation = self._ctx.budget.reserve(
                slots=max(1, self._ctx.policy.max_parallel)
            )
            if reservation is not None and reservation < 0.01:
                reason = "not invoked: run cost ceiling is fully reserved"
                self._ctx.record_ledger_row(LedgerRow(
                    phase=self.phase, rung=self.rung, model=self.model,
                    targets=self.targets, ok=False, error=reason,
                ))
                return InvokeResult(ok=False, text="", error=reason)
            budget_setter(reservation)
        started = self._ctx.timer()
        try:
            result = self._inner(prompt)
        except Exception:
            if reservation is not None:
                self._ctx.budget.settle(reservation, 0.0)
            raise
        wall = max(0.0, self._ctx.timer() - started)
        (
            tokens_in,
            tokens_cached,
            tokens_out,
            tokens_cache_write,
            tokens_fresh_in,
        ) = _usage_tokens(result.usage)
        if reservation is not None:
            self._ctx.budget.settle(reservation, result.cost_usd)
        else:
            self._ctx.budget.charge(result.cost_usd)
        if reservation is not None and result.cost_usd > reservation + 1e-9:
            result = replace(
                result, ok=False,
                error=(
                    f"provider exceeded its ${reservation:.6f} per-call cost "
                    f"reservation with ${result.cost_usd:.6f}"
                ),
            )
        # Every outcome feeds the systemic-failure circuit: one success resets
        # it, a run of identical failures opens it, and the pre-launch
        # budget.under() gate above then refuses all further work with the
        # reason attached, instead of dispatching doomed subprocesses for hours.
        self._ctx.budget.note_result(result.ok, result.error)
        # RetryingInvoker exposes the attempt count it used for the last logical
        # invoke; a plain invoker does not, so absence reads as no retries.
        retries = int(getattr(self._inner, "last_attempts", 1) or 1) - 1
        # A pinned pure-inference call is one turn. More than one means the
        # transport ran an agentic loop, which multiplies tokens and replaces
        # the JSON answer with tool narration: say so loudly.
        turns = 0
        stop_reason: Optional[str] = None
        if isinstance(result.usage, dict):
            try:
                turns = int(result.usage.get("num_turns") or 0)
            except (TypeError, ValueError):
                turns = 0
            raw_stop = result.usage.get("stop_reason")
            stop_reason = str(raw_stop) if raw_stop else None
        if turns > 1:
            self._ctx.notes.append(
                f"agentic drift: a {self.phase}/{self.rung} invocation used "
                f"{turns} turns; the transport is not pinned to pure inference"
            )
        # The output-ceiling tripwire. A response that reaches the model's
        # output limit has not answered, it has been cut off mid-sentence, and
        # the transport's own auto-continuation then re-ingests the fragment at
        # the 2x cache-creation rate. On 2026-08-25 this was visible in the
        # ledger from the very first call (56,605 tokens out, 88% of ceiling, at
        # $1.77 spent) and nothing looked. Warn at OUTPUT_CEILING_WARN, and
        # treat an explicit max_tokens stop as a failed call rather than a
        # successful one whose text happens to be truncated.
        ceiling = int(self._ctx.policy.output_ceiling or 0)
        if ceiling > 0 and tokens_out:
            share = tokens_out / ceiling
            if share >= OUTPUT_CEILING_WARN:
                self._ctx.notes.append(
                    f"output ceiling: a {self.phase}/{self.rung} call emitted "
                    f"{tokens_out:,} tokens, {share:.0%} of the {ceiling:,} "
                    "ceiling; responses this close to the limit truncate"
                )
        if stop_reason == "max_tokens" and result.ok:
            result = replace(
                result,
                ok=False,
                error=(
                    f"response hit the output ceiling ({tokens_out:,} tokens, "
                    "stop_reason=max_tokens): truncated, not answered"
                ),
            )
        from .prompts import split_cached_prompt

        prefix, _ = split_cached_prompt(prompt)
        prefix_hash = (
            hashlib.sha256(prefix.encode("utf-8")).hexdigest() if prefix is not None else None
        )
        # Sized from what the TRANSPORT sent, not from the prompt hashed here.
        # Only the CLI invoker actually ships a prefix as an appended system
        # prompt; an injected invoker leaves this 0, and a row that never used
        # the cache boundary must not claim a prefix the provider never saw.
        prefix_tokens_est = round(result.prefix_chars / PREFIX_CHARS_PER_TOKEN)
        response_bytes = len((result.text or "").encode("utf-8"))
        # The caller declared this a compact-budgeted call. That declaration,
        # not the response's self-reported shape, makes the byte ceiling apply.
        # Otherwise prose or a placeholder object can evade the exact gate.
        budget_applies = self.output_budget_bytes is not None
        output_budget_ok = (
            response_bytes <= self.output_budget_bytes
            if budget_applies and self.output_budget_bytes is not None else None
        )
        if output_budget_ok is False and result.ok:
            result = replace(
                result, ok=False,
                error=(
                    f"response exceeded its delivered-byte budget: "
                    f"{response_bytes:,} > {self.output_budget_bytes:,} UTF-8 bytes"
                ),
            )
        self._ctx.record_ledger_row(
            LedgerRow(
                phase=self.phase,
                rung=self.rung,
                model=self.model,
                targets=self.targets,
                tokens_in=tokens_in,
                tokens_cached=tokens_cached,
                tokens_out=tokens_out,
                tokens_cache_write=tokens_cache_write,
                tokens_fresh_in=tokens_fresh_in,
                effort=self.effort,
                stop_reason=stop_reason,
                num_turns=max(1, turns),
                partition_id=self.partition_id,
                session_id=result.session_id,
                prefix_hash=prefix_hash,
                prefix_tokens_est=prefix_tokens_est,
                response_bytes=response_bytes,
                output_budget_bytes=self.output_budget_bytes,
                output_budget_ok=output_budget_ok,
                structured_output_enforced=result.structured_output_enforced,
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

    models: dict[str, ModelSpec] = field(default_factory=lambda: dict(DEFAULT_MODELS))
    iteration: IterationPolicy = field(default_factory=IterationPolicy)
    max_cost_usd: Optional[float] = None
    # A generous, resumable operator checkpoint. It does not constrain an
    # individual answer and therefore cannot truncate quality. None disables
    # automatic pausing while dashboard pause/cancel remain available.
    pause_at_cost_usd: Optional[float] = None
    # Wall-clock ceiling for the whole run, minutes. Enforced by the shared
    # budget meter with the cost ceiling's soft semantics. None disables.
    max_wall_minutes: Optional[float] = None
    # Bounded parallelism for the ladder's independent invocations (rung 2a
    # partitions, escalation batches). 1 reproduces the sequential behaviour.
    # Modest default: the first parallel runs should measure the timeout rate
    # against the sequential baseline before anyone raises it.
    max_parallel: int = 4
    # Per-attempt subprocess timeout for real invokers. The first real run's
    # MEDIAN legitimate call ran ~554s against the old fixed 600s, so timeouts
    # were routine and, with the retry budget below the timeout, unrecoverable.
    invoke_timeout_s: int = 1200
    # Transport attempts per logical invocation. Kept on the ladder policy so
    # the CLI's --retry-attempts control reaches the real provider wrapper;
    # previously the flag was parsed but silently ignored on the ladder path.
    retry_attempts: int = 4
    # Run the first parallel task alone before fanning out, so the shared
    # prompt prefix lands in the provider's cache once instead of N times.
    warm_first: bool = True
    # The model's maximum output tokens for one response. Thinking and answer
    # text share this budget, so it is a property of the transport rather than
    # of the prompt. Used by the ceiling tripwire in MeteredInvoker and by the
    # preflight projection gate. 0 disables both, which no real run should do.
    output_ceiling: int = DEFAULT_OUTPUT_CEILING
    # Fraction of grounded items P3 spot-checks, weighted by importance.
    spot_check_fraction: float = 0.1
    max_spot_checks: int = 25
    # Cap on work orders a single issuing phase may emit (design 4.6, capped).
    max_work_orders: int = 3
    threshold: float = 85.0
    phases: tuple[str, ...] = PHASE_ORDER

    def model_for(self, key: str) -> ModelSpec:
        """The tier binding for a phase or rung. Never returns a bare model name."""
        spec = self.models.get(key) or DEFAULT_MODELS.get(key)
        if spec is None:
            return ModelSpec(DEFAULT_SOURCE, "sonnet")
        return ModelSpec.parse(spec)


def default_invoker_factory(spec: ModelSpec) -> Invoker:
    """Real invoker for a tier binding, resolved through the provider registry.

    Only used when a run does not inject its own factory. Every test injects one,
    which is how the whole pipeline is exercised without spending anything.
    """
    return build_invoker(spec)


def policy_invoker_factory(policy: LadderPolicy) -> Callable[[ModelSpec], Invoker]:
    """A factory that applies the policy's per-attempt timeout to real invokers.

    The retry total budget scales with the timeout, because a fixed 120s retry
    budget under a 600s per-attempt timeout meant a timed-out call could never
    retry: the first attempt alone exhausted the budget. One recovery attempt
    for a long-running call is the point of the policy.
    """
    from .retry import RetryPolicy

    retry = RetryPolicy(
        max_attempts=max(1, int(policy.retry_attempts)),
        total_budget_s=float(policy.invoke_timeout_s) + 300.0,
    )

    def factory(spec: ModelSpec) -> Invoker:
        return build_invoker(
            spec, retry_policy=retry, timeout_s=policy.invoke_timeout_s
        )

    return factory


@dataclass
class PhaseResult:
    """What one phase reports back to the pipeline."""

    name: str
    status: str = "ok"  # "ok" | "degraded" | "skipped" | "failed"
    notes: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "notes": list(self.notes)}


class Phase(Protocol):
    """A pipeline phase. Pure protocol so tests can substitute mock phases."""

    name: str

    def run(self, ctx: RunContext) -> PhaseResult:  # pragma: no cover - protocol
        ...


_UNSET = object()  # cache sentinel: None is a legitimate cached value


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
    invoker_factory: Callable[[ModelSpec], Invoker]
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
    # Guards the ledger and its on-disk stream under parallel rungs.
    _ledger_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )
    # Partition sizing for rung 2a, forwarded from LadderConfig. max_partitions
    # is the smoke-run bound: the ladder attempts only the N most important
    # partitions and says so. These lived on LadderConfig alone until 2026-08-22,
    # when a "smoke" run with --max-partitions 3 ran all 57 partitions to the
    # $45 ceiling because nothing on the ladder path ever read the field.
    max_partitions: Optional[int] = None
    max_lines: int = 50_000
    max_components: int = 30
    min_components: int = 5
    max_relationships: int = 40
    # Filled in by T9 so P4 and P5 can send work orders back down the ladder.
    # The default records orders without executing them, so a pipeline missing
    # the descent seam degrades visibly rather than silently dropping the order.
    descend: Optional[Callable[[Sequence[Any]], list[Any]]] = None
    # The design-signals digest, derived at most once per run. A sentinel
    # rather than None because None is a real result ("this subject yields no
    # signals") and must be cached like any other.
    _design_digest_cache: Any = field(default=_UNSET, repr=False, compare=False)
    _planned_partitions_cache: Any = field(default=_UNSET, repr=False, compare=False)

    def design_digest(self) -> Optional[dict]:
        """The compact design-signals digest for this subject, or None (D7).

        Cached so P1 orientation and P4 synthesis, which both offer the digest
        to their prompts, derive the signals once and brief the model on the
        same picture of the subject. The derivation is a full-store scan plus
        graph closure; paying it twice per run for identical input was
        measured, not hypothetical.
        """
        if self._design_digest_cache is _UNSET:
            from ..derive.design_signals import design_digest_for

            self._design_digest_cache = design_digest_for(self.store)
        return self._design_digest_cache

    def planned_partitions(self) -> tuple[Any, ...]:
        """The exact importance-ordered P2 plan every phase must share.

        P1 used to know only that a canary would run ``N`` partitions, while P2
        independently chose those partitions later.  That let orientation set
        criteria for Core code while the selected slice contained Knowledge
        Bowl UI, and P5 then spent repair rounds chasing targets the canary had
        never attempted.  Plan once, cache the immutable tuple, and let P1, P2,
        and P5 agree on the same scope by construction.
        """
        if self._planned_partitions_cache is _UNSET:
            from ..derive.importance import rank_components
            from .ladder import order_partitions
            from .partition import plan_partitions

            plan = plan_partitions(
                self.arch.get("components", []),
                self.arch.get("relationships", []),
                max_lines=self.max_lines,
                max_components=self.max_components,
                min_components=self.min_components,
                max_relationships=self.max_relationships,
            )
            ordered = order_partitions(plan.partitions, rank_components(self.store))
            self._planned_partitions_cache = tuple(ordered)
        return self._planned_partitions_cache

    def attempted_scope(self) -> dict[str, tuple[str, ...]]:
        """Exact component and relationship targets selected for rung 2a."""
        partitions = self.planned_partitions()
        if self.max_partitions is not None:
            partitions = partitions[: self.max_partitions]
        return {
            "components": tuple(dict.fromkeys(
                component_id
                for partition in partitions
                for component_id in partition.answered_component_ids
            )),
            "relationships": tuple(dict.fromkeys(
                relationship_key
                for partition in partitions
                for relationship_key in partition.relationship_keys
            )),
        }

    def invoker(
        self,
        key: str,
        *,
        phase: str,
        rung: Optional[str] = None,
        targets: int = 0,
        partition_id: Optional[int] = None,
        output_budget_bytes: Optional[int] = None,
    ) -> MeteredInvoker:
        """A metered invoker for one phase or rung, on that key's model.

        ``targets`` is how many contract targets the call actually answers for,
        which is what makes per-item economics comparable across rungs. It is
        not the partition's component count: the 2026-08-25 ledger recorded the
        latter and understated rung 2a's real work roughly fourfold.
        """
        spec = self.policy.model_for(key)
        return MeteredInvoker(
            self.invoker_factory(spec),
            ctx=self,
            phase=phase,
            rung=rung,
            model=spec.label,
            targets=targets,
            effort=spec.effort,
            partition_id=partition_id,
            output_budget_bytes=output_budget_bytes,
        )

    def record_ledger_row(self, row: LedgerRow) -> None:
        """Append a ledger row and stream it to the run directory.

        The stream (``ledger.jsonl``, one JSON object per line, appended the
        moment each invocation finishes) is the run's observability channel: a
        supervisor watching the file sees progress, cost so far, and stalls in
        real time instead of a silence that ends with the report. Streaming is
        best-effort by design: a full disk must degrade observability, never
        the run itself.
        """
        with self._ledger_lock:
            self.ledger.append(row)
            try:
                payload = row.to_dict()
                payload["at"] = self.clock()
                payload["spent_usd"] = round(self.budget.spent, 4)
                with open(self.run_path("ledger.jsonl"), "a") as stream:
                    stream.write(json.dumps(payload, sort_keys=True) + "\n")
            except OSError:
                if "ledger stream unavailable" not in " ".join(self.notes):
                    self.notes.append(
                        "ledger stream unavailable: ledger.jsonl could not be "
                        "written; the in-memory ledger and the report are "
                        "unaffected"
                    )

    def phase_data(self, name: str) -> dict:
        result = self.results.get(name)
        return result.data if result is not None else {}

    def run_path(self, *parts: str) -> Path:
        path = self.run_dir.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def progress(self):
        """The run's item-level progress stream, created on first use.

        Separate from the ledger because they answer different questions: the
        ledger records completed spend, this records work in flight. A watcher
        with only the former shows a still number for minutes at a time and
        cannot say which of 6,000 targets is being worked.
        """
        stream = getattr(self, "_progress_stream", None)
        if stream is None:
            from .progress import NullProgress, ProgressStream

            try:
                stream = ProgressStream(self.run_path("progress.jsonl"))
            except OSError:
                # Observability must never fail the work it watches. Writes are
                # already fenced; CREATING the stream calls run_path, which
                # makes directories, and an unwritable run directory would
                # otherwise take the whole run down at the first phase.
                stream = NullProgress()
            object.__setattr__(self, "_progress_stream", stream)
        return stream


@dataclass
class PipelineResult:
    """The outcome of a whole ladder run."""

    phases: list[PhaseResult] = field(default_factory=list)
    ledger: list[LedgerRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    cost_ceiling_usd: Optional[float] = None
    ceiling_hit: bool = False
    quality_status: str = "not-evaluated"
    quality_issues: list[str] = field(default_factory=list)
    audit: Optional[dict] = None

    @property
    def failed_phases(self) -> list[str]:
        return [p.name for p in self.phases if p.status == "failed"]

    @property
    def ok(self) -> bool:
        return not self.failed_phases

    @property
    def quality_ok(self) -> bool:
        return self.quality_status == "complete"

    def to_dict(self) -> dict:
        return {
            "phases": [p.to_dict() for p in self.phases],
            "ledger": [row.to_dict() for row in self.ledger],
            "notes": list(self.notes),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "cost_ceiling_usd": self.cost_ceiling_usd,
            "ceiling_hit": self.ceiling_hit,
            "failed_phases": self.failed_phases,
            "quality_status": self.quality_status,
            "quality_issues": list(self.quality_issues),
            "audit": self.audit,
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
                notes=["not run: " + ctx.budget.stop_reason()],
            )
            result.ceiling_hit = True
        else:
            # Announce the phase itself. The ladder publishes rich per-unit
            # progress, but everything after it (adjudication, synthesis,
            # determination, work orders) published nothing, so a board driven
            # by this stream froze on "rung 2c 100%" while roughly 40% of the
            # run's work carried on invisibly for another hour. A phase that is
            # working must say so even when it has no item-level story to tell.
            ctx.progress.phase_start(phase=phase.name)
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
        ctx.progress.phase_end(
            phase=phase.name,
            status=getattr(outcome, "status", "unknown"),
            spent_usd=round(ctx.budget.spent, 4),
        )
        ctx.results[phase.name] = outcome
        result.phases.append(outcome)

    if not ctx.budget.under():
        result.ceiling_hit = True
    result.ledger = list(ctx.ledger)
    result.total_cost_usd = ctx.budget.spent
    result.cost_ceiling_usd = ctx.budget.ceiling
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
    # Response bound: relationships per partition (each demands a contract
    # block in the reply). See partition.DEFAULT_MAX_RELATIONSHIPS.
    max_relationships: int = 40
    # Override for tests or hosts. The normal path writes control.json in the
    # run directory so the board and a restarted controller find the same state.
    control_path: Optional[Path] = None


def build_run_context(
    config: LadderConfig,
    *,
    invoker_factory: Optional[Callable[[ModelSpec], Invoker]] = None,
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
    budget = BudgetMeter(ceiling=config.policy.max_cost_usd)
    wall_minutes = config.policy.max_wall_minutes
    budget.configure_wall(
        float(wall_minutes) * 60.0 if wall_minutes is not None else None, timer
    )
    budget.configure_control(
        config.control_path or (Path(config.run_dir) / "control.json"),
        config.policy.pause_at_cost_usd,
    )
    # Coerce the paths here rather than trusting the dataclass annotation: a
    # caller passing a plain string is doing something reasonable, and failing on
    # it deep inside derivation would read as a store problem rather than a
    # configuration one.
    root = Path(config.root)
    store_path = Path(config.store_path)
    try:
        _, arch = derive_all(store, root.name, root_path=str(root))
        index = DigestIndex.from_store(store)
        facts = StoreFacts(
            arch,
            store.capabilities(),
            store.data_entities(),
            store.rules(),
            arch.get("relationships", []),
            root=root,
        )
        return RunContext(
            store=store,
            root=root,
            store_path=store_path,
            arch=arch,
            facts=facts,
            index=index,
            policy=config.policy,
            budget=budget,
            invoker_factory=invoker_factory or policy_invoker_factory(config.policy),
            run_dir=Path(config.run_dir),
            commit_sha=current_commit_sha(str(root)),
            seed=config.seed,
            dry_run=config.dry_run,
            max_partitions=config.max_partitions,
            max_lines=config.max_lines,
            max_components=config.max_components,
            min_components=config.min_components,
            max_relationships=config.max_relationships,
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
    from .adjudicate import AdjudicationPhase
    from .determine import DeterminationPhase
    from .ladder import LadderPhase
    from .orientation import OrientationPhase
    from .synthesis import SynthesisPhase

    registry: dict[str, Callable[[], Phase]] = {
        "p1_orientation": OrientationPhase,
        "p2_ladder": LadderPhase,
        "p3_adjudication": AdjudicationPhase,
        "p4_synthesis": SynthesisPhase,
        "p5_determination": DeterminationPhase,
    }
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
    invoker_factory: Optional[Callable[[ModelSpec], Invoker]] = None,
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
        result = run_pipeline(
            ctx, phases if phases is not None else build_phases(config.policy)
        )
        # Written here rather than inside P5, so a run whose determination phase
        # is the one that failed still produces a report. A run with no report is
        # a run nobody can audit, and that is the one outcome to rule out.
        # First write supplies the artifact consumed by the adversarial audit.
        # Then the same result is rewritten with the audit and publishability
        # verdict attached. A quality failure therefore cannot hide behind an
        # operationally successful phase list.
        from .completion import audit_run, evaluate_completion
        from .runreport import write_run_report

        result.quality_status, result.quality_issues = evaluate_completion(result)
        write_run_report(ctx, result)
        if not config.dry_run and any(
            phase.name == "p5_determination" for phase in result.phases
        ):
            result.audit = audit_run(config.run_dir, store_path=config.store_path)
            result.quality_status, result.quality_issues = evaluate_completion(
                result, audit=result.audit
            )
            write_run_report(ctx, result)
        result.notes = list(ctx.notes)
        return result
    finally:
        ctx.store.close()
