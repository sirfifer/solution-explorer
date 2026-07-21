"""Bounded, full-jitter retry for the outbound AI-enrichment invoke (card R2).

ROBUSTNESS-STRATEGY.md's "Retry, timeout, and the runaway defense" applied to the
one outbound surface in the batch enrichment pipeline: the ``claude`` CLI call in
``engine.ClaudeCliInvoker``. This layer sits UNDER the existing validation retry
(``passes._invoke_json`` and ``engine._enhance_partition`` retry once with
validator feedback for response QUALITY). Each logical invoke those drivers make
becomes, transparently, up to N TRANSPORT attempts here: a transient transport
failure is retried with full-jitter exponential backoff, a deterministic one is
returned immediately, and a per-invoke total-time budget guarantees retries can
never wedge a run.

Classification is a small pure function of the invoke OUTCOME
(:func:`classify_outcome`), exhaustively tested:

  - SUCCESS: ``result.ok`` is true.
  - TRANSIENT (retry): a spawn failure or subprocess timeout (the invoker's
    ``invocation failed:`` prefix); a structured API status the CLI reports in its
    JSON envelope's ``api_error_status`` that is a rate limit, request-timeout, or
    5xx/overload (429, 408, 425, 500, 502, 503, 504, 529); or, when there is no
    structured status, a free-text transient marker in the error message.
  - DETERMINISTIC (do NOT retry): a parse failure (the ``unparseable envelope:``
    prefix, a well-formed run that returned non-JSON), a non-transient API status
    (a 4xx such as 400/401/403/404), or any other nonzero exit. A parse failure
    is NEVER retried here: it fails identically every time and the semantic
    validation layer above owns response quality.

Grounded in a real ``claude`` CLI observation (v2.1.x): a model-not-found returns
exit 1 WITH a JSON envelope on stdout carrying ``is_error: true`` and
``api_error_status: 404``. So the structured status is the primary signal; the
free-text markers are a fallback for outcomes that carry no status (a subprocess
timeout, a spawn failure, or a bare nonzero exit).

Determinism and the injectable seams: the sleep, the monotonic clock, and the RNG
are all injectable, so tests are deterministic with NO real sleeping and NO real
time (the established fake-Invoker / fake-Clock pattern). A retried-then-successful
invoke returns an InvokeResult whose ``text`` is byte-identical to a first-try
success (only ``cost_usd`` is summed across attempts, which lands in the run
report, never in the stamped enrichment payload), so retry is invisible in the
projection.

Tooling deviation from the strategy (documented on purpose): ROBUSTNESS-STRATEGY.md
recommends the ``stamina`` library. R2 does NOT use it, for two concrete reasons.
(1) Zero-dependency core (invariant I7): stamina would be a new third-party
dependency, and even confined to the optional enrich extra it fights (2) the
established determinism seam. stamina drives its own ``time.monotonic``/``time.sleep``
and its test switch (``stamina.set_active(False)``) DISABLES retrying wholesale
rather than making the timing deterministic, so it cannot express the fake-clock /
fake-sleep tests this codebase uses for byte-parity. A small full-jitter policy
over the existing injectable seams is the honest fit: same algorithm (transient
only, full jitter, bounded attempts, total-time budget), no new dependency,
deterministic tests.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional

from .engine import Invoker, InvokeResult


class RetryDecision(str, Enum):
    """How one invoke outcome should be treated by the transport-retry layer."""

    SUCCESS = "success"
    TRANSIENT = "transient"
    DETERMINISTIC = "deterministic"


# Error-message prefixes that ClaudeCliInvoker builds. Shared here so the invoker
# and the classifier cannot drift: the invoker writes these, the classifier reads
# them. A spawn failure (OSError/SubprocessError) and a subprocess timeout both
# use the SPAWN prefix and are transient; the PARSE prefix is a well-formed run
# whose stdout was not JSON, which is deterministic and never retried here.
SPAWN_FAILURE_PREFIX = "invocation failed:"
PARSE_FAILURE_PREFIX = "unparseable envelope:"

# HTTP-style statuses the CLI reports in its JSON envelope (``api_error_status``)
# that are transient: request timeout, too-early, rate limit, and 5xx/overload.
# Anthropic uses 429 for rate limiting and 529 for overloaded.
_TRANSIENT_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504, 529})

# Lowercase phrase markers of a transient failure, used ONLY when there is no
# structured status (a bare nonzero exit whose message carries the signal). Phrase
# markers, never bare 3-digit numbers, so a token count like "1500" cannot be
# mistaken for a 500 server error.
_TRANSIENT_MARKERS = (
    "rate limit", "rate-limit", "ratelimit",
    "overloaded", "overload",
    "temporarily", "try again",
    "timed out", "timeout",
    "connection reset", "connection aborted", "connection refused", "broken pipe",
    "service unavailable", "bad gateway", "gateway timeout",
    "server error", "internal error",
)


def classify_outcome(result: InvokeResult) -> RetryDecision:
    """Classify one invoke outcome. Pure function, exhaustively tested.

    Order matters: a parse failure is deterministic even though its bytes could
    coincide with something else, and the structured status wins over free-text
    marker scanning when present.
    """
    if result.ok:
        return RetryDecision.SUCCESS
    err = result.error or ""
    # Parse failure: a well-formed run returned non-JSON. Never retried here.
    if err.startswith(PARSE_FAILURE_PREFIX):
        return RetryDecision.DETERMINISTIC
    # Structured API status is the primary, unambiguous signal.
    if result.status_code is not None:
        return (
            RetryDecision.TRANSIENT
            if result.status_code in _TRANSIENT_STATUS
            else RetryDecision.DETERMINISTIC
        )
    # Spawn failure or subprocess timeout: a bounded transient.
    if err.startswith(SPAWN_FAILURE_PREFIX):
        return RetryDecision.TRANSIENT
    # Fallback: a free-text transient marker in a bare nonzero-exit message.
    low = err.lower()
    if any(marker in low for marker in _TRANSIENT_MARKERS):
        return RetryDecision.TRANSIENT
    return RetryDecision.DETERMINISTIC


@dataclass
class RetryPolicy:
    """Transport-retry policy for one logical invoke. All fields injectable.

    Defaults, documented and justified in the R2 PR: up to four attempts (one
    initial plus three retries) rides out a short rate-limit or overload window
    without wedging; full-jitter exponential backoff over a 1s base capped at 30s
    per sleep spreads retries so they do not cluster; and a 120s per-invoke
    total-time budget bounds the added wall time, so combined with the existing
    600s per-attempt subprocess timeout a pathological repeated hang is capped to
    at most a couple of attempts rather than four full timeouts.
    """

    max_attempts: int = 4
    base_delay: float = 1.0
    max_delay: float = 30.0
    total_budget_s: float = 120.0


class RetryingInvoker:
    """Wrap an Invoker with transient-only, full-jitter, bounded transport retry.

    A drop-in ``Invoker`` (prompt -> InvokeResult). On a TRANSIENT outcome it
    retries with full-jitter backoff until it succeeds, exhausts the attempt
    count, or reaches the per-invoke total-time budget; on SUCCESS or a
    DETERMINISTIC outcome it returns immediately. The returned InvokeResult is the
    final attempt's result with ``cost_usd`` summed across ALL attempts (so the
    run's cost accounting, and the R2 cost ceiling, count retries), and otherwise
    byte-identical to what the underlying invoker produced, so a retried success
    stamps exactly like a first-try success.

    Seams (all injectable for deterministic tests): ``rng`` (full jitter),
    ``sleep`` (no real sleeping in tests), and ``monotonic`` (no real time in
    tests, for the budget).
    """

    def __init__(
        self,
        base: Invoker,
        policy: Optional[RetryPolicy] = None,
        *,
        rng: Optional[random.Random] = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._base = base
        self._policy = policy or RetryPolicy()
        self._rng = rng or random.Random()
        self._sleep = sleep
        self._monotonic = monotonic

    def _full_jitter(self, attempt: int) -> float:
        """Full-jitter backoff for a 1-based attempt index: uniform(0, cap)."""
        exp = self._policy.base_delay * (2 ** (attempt - 1))
        cap = min(self._policy.max_delay, exp)
        return self._rng.uniform(0.0, max(0.0, cap))

    def __call__(self, prompt: str) -> InvokeResult:
        policy = self._policy
        attempts = max(1, policy.max_attempts)
        start = self._monotonic()
        total_cost = 0.0
        last: Optional[InvokeResult] = None
        for attempt in range(1, attempts + 1):
            result = self._base(prompt)
            total_cost += result.cost_usd
            last = result
            decision = classify_outcome(result)
            if decision is not RetryDecision.TRANSIENT:
                # SUCCESS or DETERMINISTIC: stop, with cost summed across attempts.
                return replace(result, cost_usd=total_cost)
            if attempt >= attempts:
                break
            elapsed = self._monotonic() - start
            if elapsed >= policy.total_budget_s:
                break  # budget exhausted; do not launch another attempt
            sleep_s = self._full_jitter(attempt)
            remaining = policy.total_budget_s - elapsed
            if sleep_s > remaining:
                sleep_s = remaining
            self._sleep(sleep_s)
        # Exhausted (attempts or budget) on a persistent transient failure.
        return replace(last, cost_usd=total_cost)


__all__ = [
    "RetryDecision",
    "RetryPolicy",
    "RetryingInvoker",
    "classify_outcome",
    "SPAWN_FAILURE_PREFIX",
    "PARSE_FAILURE_PREFIX",
]
