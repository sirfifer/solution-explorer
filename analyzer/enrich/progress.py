"""Item-level progress for a run that takes hours.

The ledger says what a run SPENT, one row per completed model call. That is the
right record for accounting and the wrong one for watching: a call that takes
four minutes contributes nothing until it finishes, so a board driven by the
ledger alone shows a frozen number and then a jump. Worse, the ledger's unit is
the call, and a viewer wants the unit to be the work: a run enhancing 569
components and 5,453 relationships that reports "0 of 1" has told the reader
nothing except that something is happening somewhere.

This stream carries the other half: what the run PLANNED, which items are being
worked right now, and which have landed. It is written by the engine and tailed
by whatever is watching, on the same one-JSON-object-per-line contract as the
ledger so a tail never has to parse a partial write.

Two rules, both learned the hard way:

**Observability must never fail the work it watches.** Every write is fenced.
A full disk costs progress reporting, never the run.

**It reports, it does not narrate.** Events are emitted when something actually
changes state, not on a timer, and they carry counts rather than prose. The
sampling and the pacing belong to the reader, which can decide how often to
look; a stream that logged every thought would be noise nobody reads.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

__all__ = ["ProgressStream", "NullProgress"]


class NullProgress:
    """The no-op used when a run has nowhere to publish. Same surface."""

    def plan(self, **fields: Any) -> None: ...

    def rung_start(self, **fields: Any) -> None: ...

    def unit_start(self, **fields: Any) -> None: ...

    def unit_end(self, **fields: Any) -> None: ...

    def phase_start(self, **fields: Any) -> None: ...

    def phase_end(self, **fields: Any) -> None: ...

    def note(self, **fields: Any) -> None: ...

    def close(self) -> None: ...


class ProgressStream:
    """Append-only item-level progress events for one run."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._seq = 0

    # --- the events ---------------------------------------------------------

    def plan(
        self,
        *,
        rung: str,
        partitions: int,
        components: int,
        relationships: int,
    ) -> None:
        """The denominator, published BEFORE any work starts.

        A progress bar without this is either absent or lying. It is emitted
        per rung because the ladder's later rungs do not know their own size
        until the rung below has decided what to escalate.
        """
        self._emit(
            "plan",
            rung=rung,
            partitions=partitions,
            components=components,
            relationships=relationships,
            targets=components + relationships,
        )

    def rung_start(self, *, rung: str, model: str, effort: str, items: int) -> None:
        self._emit("rung_start", rung=rung, model=model, effort=effort, items=items)

    def unit_start(
        self,
        *,
        rung: str,
        unit_id: Any,
        label: str,
        components: int,
        relationships: int,
        sample: Optional[list] = None,
    ) -> None:
        """One unit of work has been handed to a model and is now in flight.

        ``label`` and ``sample`` are what make a progress line answer "what is
        it doing RIGHT NOW" at the level a reader cares about: the names of the
        components being enhanced, not the index of an opaque partition.
        """
        self._emit(
            "unit_start",
            rung=rung,
            unit_id=unit_id,
            label=label,
            components=components,
            relationships=relationships,
            sample=list(sample or [])[:6],
            started_at=time.time(),
        )

    def unit_end(
        self,
        *,
        rung: str,
        unit_id: Any,
        ok: bool,
        answered: int = 0,
        escalated: int = 0,
        detail: Optional[str] = None,
    ) -> None:
        self._emit(
            "unit_end",
            rung=rung,
            unit_id=unit_id,
            ok=bool(ok),
            answered=answered,
            escalated=escalated,
            detail=detail,
            ended_at=time.time(),
        )

    def phase_start(self, *, phase: str) -> None:
        """A pipeline phase has begun. Emitted for EVERY phase, not just the
        ladder, so a watcher never has to infer silence as either progress or
        a stall."""
        self._emit("phase_start", phase=phase, started_at=time.time())

    def phase_end(self, *, phase: str, status: str, spent_usd: float = 0.0) -> None:
        self._emit(
            "phase_end", phase=phase, status=status,
            spent_usd=spent_usd, ended_at=time.time(),
        )

    def note(self, *, message: str, **fields: Any) -> None:
        self._emit("note", message=message, **fields)

    def close(self) -> None:
        self._emit("close")

    # --- transport ----------------------------------------------------------

    def _emit(self, event: str, **fields: Any) -> None:
        with self._lock:
            self._seq += 1
            payload = {"seq": self._seq, "at": time.time(), "event": event}
            payload.update(fields)
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                line = json.dumps(payload, sort_keys=True, default=str) + "\n"
                # Opened per write and flushed, because the reader is a
                # different process tailing by byte offset: a buffered handle
                # would make progress arrive in blocks, which is the reporting
                # failure this exists to fix.
                with open(self._path, "a", encoding="utf-8") as stream:
                    stream.write(line)
                    stream.flush()
                    os.fsync(stream.fileno())
            except (OSError, TypeError, ValueError):
                pass  # never let reporting break the run
