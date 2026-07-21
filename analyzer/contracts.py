"""Output contracts and honest-gap isolation for producer units (card R1).

This is the robustness backbone from ROBUSTNESS-STRATEGY.md ("Self-validating
output" and "Fault isolation"). It generalizes the coverage ledger's one proven
idea, every file accounted for exactly once, to every producer: a unit that
cannot hand off a whole, well-formed result records a DETERMINISTIC honest gap
instead of crashing the run or shipping a fracture. The failing unit degrades to
an explicit "produced nothing, here is why" record that the artifact carries and
the viewer degrades around, exactly as the coverage ledger records a failed
file.

Three pieces, all pure stdlib:

  - ProducerGap: a deterministic honest-gap record (same input, same gap), so the
    byte-parity and golden-corpus contracts hold. It deliberately carries no
    traceback and no absolute paths, only the producer id, the coarse stage, a
    disposition-style status, and a reason built from the exception type and
    message. A traceback embeds machine-specific line numbers and filesystem
    paths that would break byte parity across environments, so it is never put in
    the artifact (structured logging is the place for a traceback, not the
    projection).
  - Isolator: the driver-level bulkhead. It runs one unit and, if that unit
    raises OR fails its output contract, records a gap and returns a caller-chosen
    default instead of propagating. A healthy unit is a transparent pass-through
    that changes nothing, so a clean run stays byte-identical (a critical
    contract: the golden gate and the full-vs-incremental byte-parity tests prove
    it, and they only hold because a run with no gaps adds no bytes).
  - require / PostconditionError: the shape-and-completeness postcondition helper.
    Assert presence, shape, count consistency, and cross-reference resolution;
    NEVER what a value is. Validation creep toward content checks is the failure
    mode and is deliberately out of scope.

Zero-dependency (invariant I7, local-first): pydantic is an OPTIONAL extra, so
the honest-gap machinery must run under pure stdlib. ProducerGap mirrors
analyzer/models.py's Pydantic-when-available / dataclass-fallback pattern, so it
gains model validation for free when pydantic is installed and works identically
without it. Nothing here imports pydantic at module top level or requires it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict as _dc_asdict
from dataclasses import dataclass, is_dataclass
from typing import Any

# The maximum length of a gap reason string. A pathological exception message
# (a giant repr) must not bloat the artifact; the reason is a human hint, not a
# payload. Truncation is announced so it is never a silent cut.
_REASON_CAP = 500


class PostconditionError(Exception):
    """A producer's output failed its shape-and-completeness contract.

    Raised by :func:`require`. The Isolator treats it exactly like any other
    unit failure: it becomes a deterministic honest gap, never a crashed run.
    """


def require(condition: bool, message: str) -> None:
    """Assert a shape-and-completeness postcondition, else raise PostconditionError.

    Use for presence, shape, count consistency, and cross-reference resolution.
    Do NOT use to assert what a value IS (validation creep); hold at whether the
    required things are present and mutually consistent.
    """
    if not condition:
        raise PostconditionError(message)


# ---------------------------------------------------------------------------
# The honest-gap record (Pydantic when available, dataclass fallback)
# ---------------------------------------------------------------------------

try:
    from pydantic import BaseModel

    _PYDANTIC = True
except ImportError:  # pragma: no cover - exercised in the zero-dep install
    _PYDANTIC = False


if _PYDANTIC:

    class ProducerGap(BaseModel):
        """A deterministic honest-gap record for one producer unit.

        ``status`` uses the coverage ledger's disposition vocabulary ("failed"),
        so a consumer that already reads the ledger speaks the same language.
        """

        producer: str
        stage: str
        status: str = "failed"
        reason: str = ""

else:

    @dataclass
    class ProducerGap:
        """A deterministic honest-gap record for one producer unit.

        ``status`` uses the coverage ledger's disposition vocabulary ("failed"),
        so a consumer that already reads the ledger speaks the same language.
        """

        producer: str
        stage: str
        status: str = "failed"
        reason: str = ""


def gap_to_dict(gap: Any) -> dict:
    """Serialize a ProducerGap (pydantic or dataclass) to a plain dict."""
    if hasattr(gap, "model_dump"):
        return gap.model_dump()
    if is_dataclass(gap) and not isinstance(gap, type):
        return _dc_asdict(gap)
    if isinstance(gap, dict):
        return gap
    raise TypeError(f"Cannot convert {type(gap)} to a gap dict")


def _scrub_reason(text: str) -> str:
    """Make a reason string deterministic and bounded.

    Collapses to a single line and caps the length. Determinism of the CONTENT
    is the producer's job (a unit that is a pure function of its input raises the
    same message every time); this only removes newlines that would fracture the
    single-line ledger convention and bounds a pathological length.
    """
    one_line = " ".join(str(text).split())
    if len(one_line) > _REASON_CAP:
        return one_line[:_REASON_CAP] + f"... (truncated, {len(one_line)} chars)"
    return one_line


def gap_from_exception(
    producer: str, stage: str, exc: BaseException, *, status: str = "failed"
) -> ProducerGap:
    """Build a deterministic honest gap from a caught exception.

    The reason is ``"<ExceptionType>: <message>"``, scrubbed to one bounded line.
    No traceback is captured, because a traceback embeds absolute paths and line
    numbers that vary across machines and would break byte parity.
    """
    reason = _scrub_reason(f"{type(exc).__name__}: {exc}")
    return ProducerGap(producer=producer, stage=stage, status=status, reason=reason)


def finalize_gaps(gaps: list) -> list[dict]:
    """Return the collected gaps as a deterministic, sorted list of dicts.

    Sorted by (producer, status, reason) so the artifact order is independent of
    execution order and stable run to run. Callers attach the result to the
    output ONLY when it is non-empty, so a clean run adds no bytes.
    """
    dicts = [gap_to_dict(g) for g in gaps]
    dicts.sort(key=lambda g: (g.get("producer", ""), g.get("status", ""), g.get("reason", "")))
    return dicts


# ---------------------------------------------------------------------------
# The driver-level bulkhead
# ---------------------------------------------------------------------------


class Isolator:
    """Per-unit exception isolation for a driver that runs units in sequence.

    Construct one per driver invocation with the coarse ``stage`` name and a list
    to collect gaps into. Wrap every unit in :meth:`run`. A unit that raises or
    fails its output contract (PostconditionError) becomes a deterministic honest
    gap in the list and yields ``default`` to the caller; the driver keeps going.
    A healthy unit is a transparent pass-through, so a clean run is byte-identical
    to the pre-isolation behavior.

    Only ``Exception`` is caught, never ``BaseException``: KeyboardInterrupt and
    SystemExit still propagate, so a user abort or an intended exit is honored.
    """

    def __init__(self, stage: str, gaps: list) -> None:
        self.stage = stage
        self.gaps = gaps

    def run(
        self,
        producer: str,
        fn: Callable[..., Any],
        *args: Any,
        default: Any = None,
        **kwargs: Any,
    ) -> Any:
        """Run one unit under isolation, recording a gap on failure."""
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - deliberate bulkhead boundary
            self.gaps.append(gap_from_exception(producer, self.stage, exc))
            return default

    def gap(self, producer: str, reason: str, *, status: str = "failed") -> None:
        """Record an honest gap directly (for a unit that reports its own failure
        without raising, mirroring the enrich PartitionOutcome pattern)."""
        self.gaps.append(
            ProducerGap(producer=producer, stage=self.stage, status=status,
                        reason=_scrub_reason(reason))
        )


# ---------------------------------------------------------------------------
# Optional reference-resolution helper (shape-and-completeness, never value)
# ---------------------------------------------------------------------------


def unresolved_reference_count(ids: set, refs: list) -> int:
    """Count references whose target id is not in ``ids``.

    A small helper for cross-reference-resolution postconditions. The caller
    decides whether a non-zero count is a contract violation (it may be legal for
    some producers to reference external ids), so this only counts; it does not
    assert. That keeps the helper reusable without baking in a policy.
    """
    return sum(1 for r in refs if r not in ids)
