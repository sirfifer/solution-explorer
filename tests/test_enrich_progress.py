"""Watching a run that takes hours.

The 2026-08-25 VS Code run enhanced 569 components and 5,453 relationships and
published a progress bar that read "0 of 1" for 100 minutes, with a status line
that named no component and could not distinguish "working" from "wedged".

These tests pin the properties that fix means, so a later refactor cannot walk
the observability back to a pulse:

- the denominator is the real work, not the number of pipeline stages
- progress counts items answered, not calls returned
- the line names WHAT is being worked, with its real age
- an escalated rung adds to the total rather than restarting it
- reporting can never fail the run it watches
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from analyzer.enrich.progress import NullProgress, ProgressStream  # noqa: E402
from testboard_emit import LedgerWatch, _age  # noqa: E402


class FakeRun:
    """Stands in for the board record a watcher publishes to."""

    def __init__(self) -> None:
        self.record = {"total": 0, "completed": 0, "current": None}
        self.events: list[dict] = []

    def _emit(self, event: dict) -> None:
        self.events.append(event)

    def _flush(self) -> None:
        pass


@pytest.fixture()
def wired(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("")
    progress = ProgressStream(tmp_path / "progress.jsonl")
    run = FakeRun()
    watch = LedgerWatch(run, ledger, child_pid=0, ps_fn=lambda: [])
    return run, watch, progress, ledger


def _bill(ledger: Path, cost: float = 0.25, ok: bool = True) -> None:
    with open(ledger, "a") as stream:
        stream.write(
            json.dumps(
                {"ok": ok, "cost_usd": cost, "phase": "p2_ladder", "rung": "2a"}
            )
            + "\n"
        )


# --- the denominator ----------------------------------------------------------


def test_the_denominator_is_the_real_work_not_the_stage_count(wired):
    run, watch, progress, _ = wired
    progress.plan(rung="2a", partitions=159, components=569, relationships=5453)
    watch.tick()
    assert run.record["total"] == 6022, "total must be every item to be enhanced"
    assert run.record["completed"] == 0


def test_no_denominator_is_invented_before_the_engine_publishes_one(wired):
    run, watch, _, ledger = wired
    _bill(ledger)
    watch.tick()
    assert run.record["total"] == 0, "a made-up denominator is a progress bar that lies"


def test_an_escalated_rung_adds_to_the_total_rather_than_restarting_it(wired):
    run, watch, progress, _ = wired
    progress.plan(rung="2a", partitions=159, components=569, relationships=5453)
    watch.tick()
    progress.plan(rung="2b", partitions=20, components=60, relationships=40)
    watch.tick()
    assert run.record["total"] == 6122
    assert watch.escalated == 100
    assert "escalated" in run.record["current"]


# --- the numerator ------------------------------------------------------------


def test_progress_counts_items_answered_not_calls_returned(wired):
    run, watch, progress, ledger = wired
    progress.plan(rung="2a", partitions=2, components=60, relationships=40)
    progress.unit_start(
        rung="2a", unit_id=0, label="cli/src/util +11", components=12, relationships=40
    )
    progress.unit_end(rung="2a", unit_id=0, ok=True, answered=52)
    _bill(ledger)
    watch.tick()
    assert run.record["completed"] == 52, "one call answered 52 items, not 1"
    assert watch.units_done == 1


def test_completed_never_exceeds_the_plan(wired):
    run, watch, progress, _ = wired
    progress.plan(rung="2a", partitions=1, components=5, relationships=0)
    progress.unit_end(rung="2a", unit_id=0, ok=True, answered=999)
    watch.tick()
    assert run.record["completed"] <= run.record["total"]


# --- the line -----------------------------------------------------------------


def test_the_line_names_what_is_being_worked_and_how_long(wired):
    run, watch, progress, _ = wired
    progress.plan(rung="2a", partitions=3, components=30, relationships=60)
    progress.unit_start(
        rung="2a", unit_id=0, label="cli/src/util +11", components=12, relationships=40
    )
    watch.tick()
    line = run.record["current"]
    assert "cli/src/util" in line, "a reader must see WHICH work is in flight"
    assert "rung 2a" in line
    assert "0/3 calls" in line
    assert "items" in line


def test_the_line_says_so_when_nothing_is_running(wired):
    run, watch, progress, _ = wired
    progress.plan(rung="2a", partitions=3, components=30, relationships=60)
    watch.tick()
    assert "no model call in flight" in run.record["current"]


def test_a_finished_unit_stops_being_reported_as_in_flight(wired):
    run, watch, progress, _ = wired
    progress.plan(rung="2a", partitions=2, components=20, relationships=20)
    progress.unit_start(rung="2a", unit_id=0, label="alpha", components=10, relationships=10)
    progress.unit_start(rung="2a", unit_id=1, label="beta", components=10, relationships=10)
    watch.tick()
    assert "alpha" in run.record["current"] and "beta" in run.record["current"]
    progress.unit_end(rung="2a", unit_id=0, ok=True, answered=20)
    watch.tick()
    assert "alpha" not in run.record["current"]
    assert "beta" in run.record["current"]


def test_ages_are_real_and_human_readable():
    assert _age(0) == "0s"
    assert _age(44) == "44s"
    assert _age(134) == "2m14s"
    assert _age(3780) == "1h03m"


def test_a_stalled_unit_still_reports_its_growing_age(wired):
    run, watch, progress, _ = wired
    progress.plan(rung="2a", partitions=1, components=10, relationships=10)
    progress.unit_start(
        rung="2a", unit_id=0, label="slow-one", components=10, relationships=10
    )
    watch.tick()
    first = run.record["current"]
    time.sleep(1.1)
    watch.tick()
    assert run.record["current"] != first, "a wedged call must look different over time"
    assert "slow-one" in run.record["current"]


# --- reporting must never break the run ---------------------------------------


def test_an_unwritable_stream_costs_reporting_not_the_run(tmp_path):
    stream = ProgressStream(tmp_path / "nope" / "deep" / "progress.jsonl")
    (tmp_path / "nope").write_text("I am a file, not a directory")
    # Every one of these must be a no-op rather than an exception.
    stream.plan(rung="2a", partitions=1, components=1, relationships=0)
    stream.unit_start(rung="2a", unit_id=0, label="x", components=1, relationships=0)
    stream.unit_end(rung="2a", unit_id=0, ok=True, answered=1)
    stream.note(message="still fine")
    stream.close()


def test_unserializable_fields_do_not_raise(tmp_path):
    stream = ProgressStream(tmp_path / "progress.jsonl")
    stream.note(message="odd", payload=object())
    assert (tmp_path / "progress.jsonl").exists()


def test_the_null_progress_has_the_same_surface():
    null = NullProgress()
    null.plan(rung="2a", partitions=1, components=1, relationships=1)
    null.rung_start(rung="2a", model="m", effort="low", items=1)
    null.unit_start(rung="2a", unit_id=0, label="x", components=1, relationships=0)
    null.unit_end(rung="2a", unit_id=0, ok=True, answered=1)
    null.note(message="x")
    null.close()


def test_a_partial_line_is_reread_next_tick(wired):
    """The stream is tailed by byte offset while it is being appended to."""
    run, watch, progress, _ = wired
    path = Path(progress._path)
    progress.plan(rung="2a", partitions=1, components=10, relationships=0)
    with open(path, "a") as stream:
        stream.write('{"event": "unit_start", "unit_id": 9, "label": "half')
    watch.tick()
    assert run.record["total"] == 10  # the complete line was still read
    with open(path, "a") as stream:
        stream.write('-written"}\n')
    watch.tick()
    assert "half-written" in run.record["current"]


# --- the run is more than its ladder ------------------------------------------


def test_a_phase_with_no_items_still_reports_itself(wired):
    """The gap the owner hit: the board froze on 'rung 2c 100%' for an hour.

    The ladder publishes rich per-unit progress. Adjudication, synthesis,
    determination and work orders publish no item-level story, so once the
    ladder finished the stream went quiet while roughly 40% of the run's work
    carried on. A watcher cannot tell that from a stall, and the whole point of
    this telemetry is that it never has to guess.
    """
    run, watch, progress, _ = wired
    progress.plan(rung="2a", partitions=1, components=5, relationships=5)
    progress.unit_end(rung="2a", unit_id=0, ok=True, answered=10)
    watch.tick()
    assert run.record["completed"] == 10 == run.record["total"]

    progress.phase_start(phase="p3_adjudication")
    watch.tick()
    assert "p3_adjudication" in run.record["current"], (
        "a working phase must name itself once the ladder is done"
    )

    progress.phase_end(phase="p3_adjudication", status="ok", spent_usd=11.8)
    progress.phase_start(phase="p5_determination")
    watch.tick()
    assert "p5_determination" in run.record["current"]
    assert "p3_adjudication" not in run.record["current"]


def test_a_long_phase_shows_its_age(wired):
    run, watch, progress, _ = wired
    progress.plan(rung="2a", partitions=1, components=1, relationships=0)
    progress.unit_end(rung="2a", unit_id=0, ok=True, answered=1)
    progress.phase_start(phase="p5_determination")
    watch.tick()
    first = run.record["current"]
    time.sleep(1.1)
    watch.tick()
    assert run.record["current"] != first, "a slow phase must look different over time"
