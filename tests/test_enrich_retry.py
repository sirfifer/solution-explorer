"""Unit tests for the R2 transport-retry layer (analyzer/enrich/retry.py).

Two units under test, both with injected fakes (never a real CLI, never a real
sleep, never real time), the established determinism pattern:

  - classify_outcome: a pure function; tested EXHAUSTIVELY across the invoke
    surfaces surveyed from the real claude CLI (structured api_error_status,
    spawn/timeout, parse failure, free-text markers).
  - RetryingInvoker: transient-only retry with full-jitter backoff, bounded
    attempts, a per-invoke total-time budget, and cost summed across attempts.
    The sleep, monotonic clock, and RNG are injected so every assertion is
    deterministic with no wall-clock time.
"""

from __future__ import annotations

import random

import pytest

from analyzer.enrich.engine import InvokeResult, _coerce_status, _envelope_error
from analyzer.enrich.retry import (
    RetryDecision,
    RetryingInvoker,
    RetryPolicy,
    classify_outcome,
)

# --- fakes -------------------------------------------------------------------


class FakeClock:
    """A monotonic clock advanced only by the fake sleep (no real time)."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class MaxRng:
    """An RNG stub whose full-jitter draw is always the maximum (the cap)."""

    def uniform(self, a: float, b: float) -> float:
        return b


class SequenceBase:
    """An invoker returning a scripted result per call (last repeats)."""

    def __init__(self, results: list[InvokeResult]) -> None:
        self.results = list(results)
        self.calls = 0

    def __call__(self, prompt: str) -> InvokeResult:
        r = self.results[min(self.calls, len(self.results) - 1)]
        self.calls += 1
        return r


def _ok(text: str = "ok", cost: float = 0.0) -> InvokeResult:
    return InvokeResult(ok=True, text=text, cost_usd=cost)


def _transient(status: int = 503, cost: float = 0.0) -> InvokeResult:
    return InvokeResult(
        ok=False, text="", cost_usd=cost, error="model reported error", status_code=status
    )


def _deterministic(status: int = 404) -> InvokeResult:
    return InvokeResult(
        ok=False, text="", error=f"claude exited 1: bad ({status})", status_code=status
    )


# --- classify_outcome exhaustiveness -----------------------------------------


def test_classify_success():
    assert classify_outcome(_ok()) is RetryDecision.SUCCESS


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504, 529])
def test_classify_transient_statuses(status):
    r = InvokeResult(ok=False, text="", error="model reported error", status_code=status)
    assert classify_outcome(r) is RetryDecision.TRANSIENT


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 409, 422])
def test_classify_deterministic_statuses(status):
    r = InvokeResult(ok=False, text="", error="model reported error", status_code=status)
    assert classify_outcome(r) is RetryDecision.DETERMINISTIC


def test_classify_spawn_failure_is_transient():
    r = InvokeResult(ok=False, text="", error="invocation failed: [Errno 2] No such file or directory: 'claude'")
    assert classify_outcome(r) is RetryDecision.TRANSIENT


def test_classify_subprocess_timeout_is_transient():
    r = InvokeResult(ok=False, text="", error="invocation failed: Command '['claude']' timed out after 600 seconds")
    assert classify_outcome(r) is RetryDecision.TRANSIENT


def test_classify_parse_failure_is_deterministic():
    r = InvokeResult(ok=False, text="", error="unparseable envelope: Expecting value: line 1 column 1")
    assert classify_outcome(r) is RetryDecision.DETERMINISTIC


def test_parse_failure_wins_over_transient_looking_text():
    # A parse-failure prefix is checked FIRST, so even a message that mentions a
    # transient word is deterministic (a parse failure repeats identically).
    r = InvokeResult(ok=False, text="", error="unparseable envelope: timeout while decoding")
    assert classify_outcome(r) is RetryDecision.DETERMINISTIC


def test_free_text_marker_transient_without_status():
    r = InvokeResult(ok=False, text="", error="claude exited 1: overloaded, please try again later")
    assert classify_outcome(r) is RetryDecision.TRANSIENT


def test_free_text_no_marker_is_deterministic():
    r = InvokeResult(ok=False, text="", error="claude exited 1: permission denied")
    assert classify_outcome(r) is RetryDecision.DETERMINISTIC


def test_structured_status_wins_over_free_text_marker():
    # A 404 with an "overloaded" word still classifies deterministic: the
    # structured status is authoritative and checked before the marker scan.
    r = InvokeResult(ok=False, text="", error="claude exited 1: overloaded but 404", status_code=404)
    assert classify_outcome(r) is RetryDecision.DETERMINISTIC


def test_subscription_capacity_stop_is_not_retried_even_when_reported_as_429():
    r = InvokeResult(
        ok=False,
        text="",
        error="claude exited 1: You've hit your session limit · resets 5pm",
        status_code=429,
    )
    assert classify_outcome(r) is RetryDecision.DETERMINISTIC
    base = SequenceBase([r, _ok("must not be reached")])
    clock = FakeClock()
    inv = RetryingInvoker(
        base, RetryPolicy(max_attempts=4),
        sleep=clock.sleep, monotonic=clock.monotonic,
    )
    result = inv("prompt")
    assert not result.ok
    assert base.calls == 1
    assert clock.sleeps == []


def test_no_false_positive_on_numeric_token_count():
    # A token count of 1500 must NOT be read as a 500 server error (phrase
    # markers only, no bare 3-digit numbers).
    r = InvokeResult(ok=False, text="", error="claude exited 1: prompt was 1500 tokens, invalid schema")
    assert classify_outcome(r) is RetryDecision.DETERMINISTIC


# --- status coercion (adversarial review of PR #79, NIT 2) -------------------


def test_status_coercion_accepts_int_and_digit_string():
    # A CLI that reported api_error_status as the string "500" must still yield a
    # transient classification, not read as no-status (which would be treated
    # deterministic and never retried).
    assert _coerce_status(500) == 500
    assert _coerce_status("500") == 500
    assert _coerce_status("  429 ") == 429
    assert _coerce_status(True) is None  # bool is not a status
    assert _coerce_status("not-a-number") is None
    assert _coerce_status(None) is None


def test_envelope_error_coerces_string_status_to_transient():
    status, detail = _envelope_error('{"api_error_status": "503", "result": "overloaded"}')
    assert status == 503
    assert detail == "overloaded"
    r = InvokeResult(ok=False, text=detail, error="claude exited 1: overloaded", status_code=status)
    assert classify_outcome(r) is RetryDecision.TRANSIENT


# --- RetryingInvoker behavior ------------------------------------------------


def test_success_first_try_no_retry():
    base = SequenceBase([_ok("payload")])
    clock = FakeClock()
    inv = RetryingInvoker(base, RetryPolicy(), sleep=clock.sleep, monotonic=clock.monotonic)
    result = inv("prompt")
    assert result.ok and result.text == "payload"
    assert base.calls == 1
    assert clock.sleeps == []


def test_transient_then_success_is_invisible():
    # Fails transiently 2 times, then succeeds. The returned result is the
    # success, byte-identical in text to a first-try success; retry is invisible.
    base = SequenceBase([_transient(), _transient(), _ok("payload")])
    clock = FakeClock()
    inv = RetryingInvoker(
        base, RetryPolicy(max_attempts=4), rng=random.Random(1),
        sleep=clock.sleep, monotonic=clock.monotonic,
    )
    result = inv("prompt")
    assert result.ok and result.text == "payload"
    assert base.calls == 3  # 2 transient + 1 success
    assert len(clock.sleeps) == 2  # one backoff before each retry


def test_deterministic_failure_never_retried():
    base = SequenceBase([_deterministic(404), _ok("would-succeed")])
    clock = FakeClock()
    inv = RetryingInvoker(base, RetryPolicy(), sleep=clock.sleep, monotonic=clock.monotonic)
    result = inv("prompt")
    assert not result.ok
    assert base.calls == 1  # returned immediately, no retry
    assert clock.sleeps == []


def test_exhausts_attempts_on_persistent_transient():
    base = SequenceBase([_transient()])  # always transient
    clock = FakeClock()
    inv = RetryingInvoker(
        base, RetryPolicy(max_attempts=3), rng=random.Random(2),
        sleep=clock.sleep, monotonic=clock.monotonic,
    )
    result = inv("prompt")
    assert not result.ok
    assert base.calls == 3  # exactly max_attempts
    assert len(clock.sleeps) == 2  # a backoff between each of the 3 attempts


def test_cost_summed_across_all_attempts():
    base = SequenceBase([_transient(cost=0.01), _transient(cost=0.02), _ok("p", cost=0.05)])
    clock = FakeClock()
    inv = RetryingInvoker(
        base, RetryPolicy(max_attempts=4), rng=random.Random(3),
        sleep=clock.sleep, monotonic=clock.monotonic,
    )
    result = inv("prompt")
    assert result.ok
    assert result.cost_usd == pytest.approx(0.08)  # 0.01 + 0.02 + 0.05


def test_full_jitter_bounds_respected():
    # Every backoff sleep must lie within [0, cap] where cap doubles per attempt,
    # capped at max_delay. Seeded RNG makes this deterministic.
    base = SequenceBase([_transient()])
    clock = FakeClock()
    policy = RetryPolicy(max_attempts=6, base_delay=1.0, max_delay=30.0, total_budget_s=1e9)
    inv = RetryingInvoker(
        base, policy, rng=random.Random(12345), sleep=clock.sleep, monotonic=clock.monotonic
    )
    inv("prompt")
    assert len(clock.sleeps) == 5  # 6 attempts, 5 backoffs
    for i, slept in enumerate(clock.sleeps, start=1):
        cap = min(policy.max_delay, policy.base_delay * (2 ** (i - 1)))
        assert 0.0 <= slept <= cap, f"attempt {i}: {slept} not in [0, {cap}]"


def test_total_budget_stops_retries_early():
    # With a tight budget and maximal (capped) sleeps, retries stop before the
    # attempt count is exhausted: the budget is the limiter, not max_attempts.
    base = SequenceBase([_transient()])
    clock = FakeClock()
    policy = RetryPolicy(max_attempts=5, base_delay=10.0, max_delay=30.0, total_budget_s=15.0)
    inv = RetryingInvoker(
        base, policy, rng=MaxRng(), sleep=clock.sleep, monotonic=clock.monotonic
    )
    result = inv("prompt")
    assert not result.ok
    # attempt1 (t=0) sleeps 10 -> t=10; attempt2 (t=10<15) sleeps min(20, 5)=5 ->
    # t=15; attempt3 sees elapsed 15 >= budget 15 and stops. So 3 base calls, not 5.
    assert base.calls == 3
    assert base.calls < policy.max_attempts
    assert clock.sleeps == [10.0, 5.0]  # never sleeps past the budget


def test_max_attempts_one_means_no_retry():
    base = SequenceBase([_transient()])
    clock = FakeClock()
    inv = RetryingInvoker(base, RetryPolicy(max_attempts=1), sleep=clock.sleep, monotonic=clock.monotonic)
    result = inv("prompt")
    assert not result.ok
    assert base.calls == 1
    assert clock.sleeps == []


# ---------------------------------------------------- systemic-failure circuit


class TestSystemicFailureCircuit:
    """The run-level breaker, born from a real incident.

    The claude CLI's OAuth session expired mid-run; every later call failed
    identically in ~0.6s at $0.00, and the run dispatched 10,387 doomed
    subprocesses over 1.7 hours. The cost ceiling never tripped (failures are
    free) and the wall ceiling was hours away, so the meter needed a third
    ceiling: the shape of the failures themselves.
    """

    def _meter(self):
        from analyzer.enrich.pipeline import BudgetMeter

        return BudgetMeter(ceiling=None)

    def test_identical_failures_open_the_circuit(self):
        m = self._meter()
        for _ in range(5):
            assert m.under()
            m.note_result(False, "claude exited 1: Failed to authenticate: OAuth session expired")
        assert not m.under()
        assert "systemic failure circuit open" in m.stop_reason()
        assert "authenticate" in m.stop_reason()

    def test_explicit_capacity_reset_opens_the_circuit_immediately(self):
        m = self._meter()
        m.note_result(
            False,
            "claude exited 1: You've hit your session limit · resets 5pm",
        )
        assert not m.under()
        assert "session limit" in m.stop_reason()

    def test_distinct_failures_never_trip_it(self):
        """Interleaved different errors are a flaky transport, not a dead one."""
        m = self._meter()
        for i in range(50):
            m.note_result(False, f"claude exited 1: partition {i} returned invalid JSON")
        assert m.under(), "distinct error texts must not open the circuit"

    def test_one_success_resets_the_count(self):
        m = self._meter()
        for _ in range(4):
            m.note_result(False, "Failed to authenticate: OAuth session expired")
        m.note_result(True, None)
        for _ in range(4):
            m.note_result(False, "Failed to authenticate: OAuth session expired")
        assert m.under(), "a success between failures proves the transport is alive"

    def test_systemic_outranks_the_other_ceilings_in_the_reason(self):
        """The systemic reason carries the FIX, because it is the only ceiling
        whose remedy is outside the run."""
        m = self._meter()
        for _ in range(5):
            m.note_result(False, "Failed to authenticate: x")
        reason = m.stop_reason()
        assert "rerun" in reason and "--update" in reason

    def test_whitespace_and_case_variants_still_count_as_identical(self):
        m = self._meter()
        for variant in (
            "Failed to  authenticate: OAuth expired",
            "failed to authenticate:   oauth EXPIRED",
            "FAILED TO AUTHENTICATE: OAUTH EXPIRED",
            "failed to authenticate: oauth expired",
            "Failed To Authenticate: OAuth Expired",
        ):
            m.note_result(False, variant)
        assert not m.under(), "normalization must not let formatting reset the run"
