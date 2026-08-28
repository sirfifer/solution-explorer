#!/usr/bin/env python3
"""Publish a PROCESSING run to the testboard, live, as it executes.

The test harnesses already publish themselves. This is the other half: the
pipeline that actually builds a demo, fetch through deploy. They are genuinely
different activities and the board keeps them apart, because a failing test and
a failed analyze demand completely different responses. A red test says the
product is wrong. A failed analyze says the product did not get built at all.

Processing runs are the ones most worth watching, because they are the long
ones. An analyze of VS Code is minutes of silence; an enhance is longer and
costs real money. Before this, the only way to know how either was going was to
watch the terminal you started it in, which is exactly the blindness the board
exists to remove.

The record shape is deliberately identical to the crawl reporter's, so the
dashboard has one thing to render and neither side needs to know the other
exists. Same two files, same fields, same meanings:

    run.json      rewritten on every step, so a reader always sees current truth
    events.jsonl  append-only, so a crashed run leaves its history behind

Used as a context manager, so a step that raises still closes its record out
honestly instead of leaving a phantom "running" row on the board forever:

    with ProcessingRun("analyze", slug="vscode", data_dir=arch_dir) as run:
        run.step("scan", "walking the source tree")
        ...
        run.finish_step(detail="15,366 files")

Stdlib only, and every write is best effort. Observability must never be able
to fail the work it is watching: a board that breaks a build is worse than no
board.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent


def _runs_root() -> Path:
    return Path(
        os.environ.get("TESTBOARD_DIR") or (REPO_ROOT / ".testboard" / "runs")
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _age(seconds: float) -> str:
    """A wall-clock age a human reads at a glance: 44s, 2m14s, 1h03m."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


class ProcessingRun:
    """One pipeline stage, published as it happens.

    `total` is the number of steps expected. It may be unknown up front, in
    which case the board shows progress as a count rather than a percentage,
    which is honest: a fake denominator would produce a progress bar that lies.
    """

    def __init__(
        self,
        kind: str,
        slug: str,
        total: Optional[int] = None,
        data_dir: Optional[Path] = None,
        subject: Optional[str] = None,
        note: Optional[str] = None,
    ) -> None:
        self.kind = kind
        self.slug = slug
        self.subject = subject or slug
        self.started = time.time()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
        self.run_dir = _runs_root() / f"{stamp}-{kind}-{slug}"
        self._current_started: Optional[float] = None

        self.record: dict[str, Any] = {
            "testboard_version": 1,
            "id": self.run_dir.name,
            "kind": kind,
            "category": "processing",
            "subject": self.subject,
            "slug": slug,
            "status": "running",
            "started_at": _now(),
            "ended_at": None,
            "duration_ms": None,
            "data_dir": str(data_dir) if data_dir else None,
            "base_url": None,
            "budget": note or "",
            "versions": {"viewer_version": None, "analyzer_version": None, "dataset": None},
            "total": total or 0,
            "completed": 0,
            "passed": 0,
            "warned": 0,
            "failed": 0,
            "skipped": 0,
            "current": None,
            "cases": [],
            "coverage": [],
        }

    # ------------------------------------------------------------- lifecycle

    def __enter__(self) -> ProcessingRun:
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        self._emit({"type": "run_start", "subject": self.subject, "total": self.record["total"]})
        self._flush()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        # An exception closes the record as failed with the reason attached.
        # The alternative, a record stuck on "running" forever, is the worst
        # outcome: the board would show it as stalled and nobody could tell
        # whether it died or was killed on purpose.
        if exc is not None:
            if self._current_started is not None:
                self.finish_step(status="failed", detail=f"{type(exc).__name__}: {exc}")
            self.close(status="failed", reason=f"{type(exc).__name__}: {exc}")
        elif self.record["status"] == "running":
            self.close(status="failed" if self.record["failed"] else "passed")
        return False  # never swallow the exception

    def close(self, status: str = "passed", reason: Optional[str] = None) -> None:
        self.record["status"] = status
        self.record["ended_at"] = _now()
        self.record["duration_ms"] = round((time.time() - self.started) * 1000)
        self.record["current"] = None
        if reason:
            self.record["exit_reason"] = reason
        self._emit({
            "type": "run_end", "status": status,
            "passed": self.record["passed"], "failed": self.record["failed"],
            **({"reason": reason} if reason else {}),
        })
        self._flush()

    # ----------------------------------------------------------------- steps

    def step(self, title: str, detail: Optional[str] = None) -> None:
        """Begin a step. Closes the previous one as passed if still open."""
        if self._current_started is not None:
            self.finish_step()
        self._current_started = time.time()
        self.record["current"] = title
        self._emit({"type": "case_start", "title": title, **({"detail": detail} if detail else {})})
        self._flush()

    def finish_step(
        self, status: str = "passed", detail: Optional[str] = None, title: Optional[str] = None
    ) -> None:
        if self._current_started is None:
            return
        duration = round((time.time() - self._current_started) * 1000)
        entry = {
            "title": title or self.record["current"] or "step",
            "status": status,
            "duration_ms": duration,
            "coverage": [],
            "message": detail if status != "passed" else None,
        }
        self.record["cases"].append(entry)
        self.record["completed"] += 1
        if status == "passed":
            self.record["passed"] += 1
        elif status == "warned":
            self.record["warned"] += 1
        elif status == "skipped":
            self.record["skipped"] += 1
        else:
            self.record["failed"] += 1
        if detail and status == "passed":
            self.record["coverage"].append(f"{entry['title']}: {detail}")
        self.record["current"] = None
        self._current_started = None
        self._emit({"type": "case_end", **entry, **({"detail": detail} if detail else {})})
        self._flush()

    def note(self, message: str) -> None:
        """A measurement worth surfacing, e.g. '15,366 files walked'."""
        self.record["coverage"].append(message)
        self._emit({"type": "note", "message": message})
        self._flush()

    def stamp_dataset(self, arch_dir: Path) -> None:
        """Attach the produced dataset's identity once it exists."""
        try:
            manifest = json.loads((arch_dir / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        provenance = (manifest.get("activity") or {}).get("provenance") or {}
        self.record["versions"]["dataset"] = {
            "name": manifest.get("name"),
            "generated_at": manifest.get("generated_at"),
            "analyzer_version": manifest.get("analyzer_version"),
            "subject_sha": provenance.get("head"),
            "components": len(manifest.get("component_detail_index") or {}) or None,
        }
        self.record["versions"]["analyzer_version"] = manifest.get("analyzer_version")
        self._flush()

    # ------------------------------------------------------------------ io

    def _emit(self, event: dict) -> None:
        try:
            with open(self.run_dir / "events.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": _now(), **event}) + "\n")
        except OSError:
            pass  # never let the board break the build

    def _flush(self) -> None:
        try:
            (self.run_dir / "run.json").write_text(
                json.dumps(self.record, indent=2) + "\n", encoding="utf-8"
            )
        except OSError:
            pass


class LedgerWatch:
    """Live telemetry for a long child process, from its own artifacts.

    Exists because a two-hour enrichment ran as one silent board step, the
    board's staleness inference called the run stalled while it was healthy,
    and the owner rightly refused to run anything for hours blind again.

    Every number published is a fact from outside the watcher:

      the ledger    the child appends one JSON row per completed model call;
                    the watcher tails it and aggregates what actually landed
      the process   the child's live `claude` subprocesses, with their real
                    ages, read from the process table

    Pace: one tick every ``interval`` seconds, and AT MOST one event per tick,
    summarizing however many real calls completed since the last one. During a
    burst of thousands of small calls that is four aggregate events a minute,
    not thousands; during a nine-minute bulk call it is a live in-flight line
    and no event at all, because nothing completed and saying otherwise would
    be the fake heartbeat this deliberately is not. run.json is rewritten each
    tick with the updated truth, which also keeps the board's staleness
    inference honest as a side effect of real reporting rather than instead
    of it.

    Same rule as everything else in this module: observability must never be
    able to fail the work it watches. Every tick is fenced; a watcher error
    costs a tick, not the run.
    """

    def __init__(
        self,
        run: ProcessingRun,
        ledger_path: Path,
        child_pid: int,
        interval: float = 15.0,
        ps_fn=None,
        progress_path: Optional[Path] = None,
        control_path: Optional[Path] = None,
    ) -> None:
        import threading

        self._run = run
        self._ledger = Path(ledger_path)
        # The item-level stream the engine writes. Defaults beside the ledger,
        # which is where the engine puts it.
        self._progress = (
            Path(progress_path)
            if progress_path is not None
            else Path(ledger_path).with_name("progress.jsonl")
        )
        self._control = (
            Path(control_path)
            if control_path is not None
            else Path(ledger_path).with_name("control.json")
        )
        self._pid = child_pid
        self._interval = interval
        self._ps_fn = ps_fn or self._ps_children
        self._offset = 0
        self._progress_offset = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        # Aggregates across the whole watch: real completed work only.
        self.calls_ok = 0
        self.calls_failed = 0
        self.spent_usd = 0.0
        self.last_phase = ""
        # Work units, which is what a reader actually wants counted. A run
        # enhancing thousands of targets that reports "0 of 1" has said
        # nothing; these are the real numerator and denominator.
        self.targets_planned = 0
        self.targets_done = 0
        self.units_planned = 0
        self.units_done = 0
        self.rung = ""
        self.escalated = 0
        self.phase = ""
        self.phase_started = None
        # unit_id -> what it is and when it started, so the line can name what
        # is being worked right now instead of counting anonymous processes.
        self._in_flight: dict = {}

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5.0)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.tick()
            except Exception:
                pass  # a watcher error costs a tick, never the run

    # ----------------------------------------------------------------- ticks

    def tick(self) -> None:
        new_rows = self._read_new_rows()
        for row in new_rows:
            if row.get("ok"):
                self.calls_ok += 1
            else:
                self.calls_failed += 1
            self.spent_usd += float(row.get("cost_usd") or 0.0)
            phase = str(row.get("phase") or "")
            rung = row.get("rung")
            self.last_phase = f"{phase}/{rung}" if rung else phase

        self._read_progress()
        control = self._read_control()
        in_flight = self._ps_fn()

        if new_rows:
            self._run._emit({
                "type": "progress",
                "phase": self.last_phase,
                "new_calls": len(new_rows),
                "calls_ok": self.calls_ok,
                "calls_failed": self.calls_failed,
                "spent_usd": round(self.spent_usd, 4),
                "targets_done": self.targets_done,
                "targets_planned": self.targets_planned,
            })

        # The board's own progress bar counts work, not calls, and only once
        # the engine has published a denominator. Until then the record keeps
        # the count it was constructed with rather than inventing one.
        if self.targets_planned:
            self._run.record["total"] = self.targets_planned
            self._run.record["completed"] = min(self.targets_done, self.targets_planned)

        parts = []
        if control:
            # The full packet remains on the record for decision support and
            # resume/cancel actions. The one-line current state leads the live
            # status so a paused run can never look merely idle or stalled.
            self._run.record["enrichment_control"] = {
                **control,
                "path": str(self._control),
            }
            if control.get("state") == "paused":
                parts.append(
                    "PAUSED for owner decision: "
                    + str(control.get("reason") or "operator checkpoint")
                )
            elif control.get("state") == "cancelled":
                parts.append("CANCELLED by owner")
        # A phase with no item-level story still reports itself, with how long
        # it has been working, so silence is never mistaken for a stall.
        now = time.time()
        ladder_done = self.targets_planned and self.targets_done >= self.targets_planned
        if self.phase and (ladder_done or not self.rung):
            label = self.phase
            if self.phase_started:
                label += f" ({_age(now - self.phase_started)})"
            parts.append(label)
        elif self.rung:
            parts.append(f"rung {self.rung}")
        elif self.last_phase:
            parts.append(self.last_phase)
        if self.units_planned:
            parts.append(f"{self.units_done}/{self.units_planned} calls")
        if self.targets_planned:
            pct = 100.0 * self.targets_done / max(1, self.targets_planned)
            parts.append(
                f"{self.targets_done:,}/{self.targets_planned:,} items ({pct:.0f}%)"
            )
        parts.append(
            f"${self.spent_usd:.2f}"
            + (f", {self.calls_failed} failed" if self.calls_failed else "")
        )
        if self.escalated:
            parts.append(f"{self.escalated} escalated")

        if self._in_flight:
            # Name what is being worked, with its real age. This is the line
            # that answers "is it stuck, and on what".
            live = sorted(self._in_flight.values(), key=lambda u: u.get("started_at", now))
            shown = [
                f"{u.get('label') or u.get('unit_id')} {_age(now - u.get('started_at', now))}"
                for u in live[:3]
            ]
            more = len(live) - len(shown)
            parts.append(
                f"working: {'; '.join(shown)}" + (f" (+{more} more)" if more > 0 else "")
            )
        elif in_flight:
            parts.append(f"in flight: {len(in_flight)} ({', '.join(in_flight[:3])})")
        elif not new_rows:
            # True and worth saying: nothing completed this tick and nothing is
            # running. Either the run is between phases or something is wrong,
            # and the reader deserves the fact rather than a reassuring line.
            parts.append("no model call in flight")
        self._run.record["current"] = " · ".join(parts)
        self._run._flush()

    def _read_control(self) -> dict:
        try:
            value = json.loads(self._control.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _read_progress(self) -> None:
        """Fold the engine's item-level events into the watcher's counters."""
        for event in self._read_new_lines(self._progress, "_progress_offset"):
            kind = event.get("event")
            if kind == "plan":
                # Rungs accumulate: 2b's denominator adds to 2a's rather than
                # replacing it, because the run is not starting over.
                self.targets_planned += int(event.get("targets") or 0)
                self.units_planned += int(event.get("partitions") or 0)
                self.rung = str(event.get("rung") or self.rung)
                if event.get("rung") in ("2b", "2c"):
                    self.escalated += int(event.get("targets") or 0)
            elif kind == "unit_start":
                self.rung = str(event.get("rung") or self.rung)
                self._in_flight[str(event.get("unit_id"))] = event
            elif kind == "phase_start":
                # The ladder is not the whole run. Adjudication, synthesis and
                # determination publish no per-item story, so without this the
                # board froze on "rung 2c 100%" for an hour while they worked.
                self.phase = str(event.get("phase") or "")
                self.phase_started = float(event.get("started_at") or 0) or None
            elif kind == "phase_end":
                self.phase_started = None
            elif kind == "unit_end":
                self._in_flight.pop(str(event.get("unit_id")), None)
                self.units_done += 1
                self.targets_done += int(event.get("answered") or 0)

    def _read_new_lines(self, path: Path, offset_attr: str) -> list:
        """Tail one JSON-lines file from where this watcher last stopped."""
        rows = []
        offset = getattr(self, offset_attr)
        try:
            with open(path, encoding="utf-8") as fh:
                fh.seek(offset)
                for line in fh:
                    if not line.endswith("\n"):
                        break  # partial write; reread next tick
                    offset += len(line.encode("utf-8"))
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            setattr(self, offset_attr, offset)
        except OSError:
            pass  # stream not created yet
        return rows

    def _read_new_rows(self) -> list:
        return self._read_new_lines(self._ledger, "_offset")

    def _ps_children(self) -> list:
        """Ages of the child's live claude subprocesses, oldest first."""
        import subprocess

        try:
            out = subprocess.run(
                ["ps", "-axo", "pid=,ppid=,etime=,command="],
                capture_output=True, text=True, timeout=5,
            ).stdout
        except Exception:
            return []
        ages = []
        for line in out.splitlines():
            fields = line.split(None, 3)
            if len(fields) < 4:
                continue
            _pid, ppid, etime, command = fields
            if ppid == str(self._pid) and "claude" in command:
                ages.append(etime)
        return ages
