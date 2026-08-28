"""The testboard, proved against the one thing it exists to decide.

The board reads state it did not write: run records that a harness appends to
while it works, and demo manifests that an analyzer produced hours or weeks
ago. Both can lie. A run record says "running" because that is the last thing
the process managed to write before it was killed, and a manifest says nothing
at all about whether the code that made it still matches the checkout. So the
tests below are weighted toward the two derivations the board performs rather
than reads: liveness, which turns a stale mtime into "stalled", and drift,
which turns a version mismatch into a flag.

Every test runs against a temporary runs directory, a temporary registry, and a
temporary corpus. Nothing here may touch the real .testboard/, the real
demos/registry/, or the real demo corpus, because the board's whole subject
matter is live machine state and a test that reads it is both flaky and, if it
ever writes, destructive.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "testboard.py"


def _load():
    spec = importlib.util.spec_from_file_location("testboard", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    # Registered before exec because @dataclass resolves its own module out of
    # sys.modules; a hyphenated script loaded by path is absent from it.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


tb = _load()


def _load_control():
    spec = importlib.util.spec_from_file_location(
        "control_for_test", REPO_ROOT / "scripts" / "control.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------- fixtures


VERSIONS = {
    "analyzer_version": "2.0.0",
    "viewer_version": "1.2.3",
    "git_sha": "abcdef0123456789",
    "git_short": "abcdef012",
    "git_branch": "main",
    "git_dirty": False,
}


@pytest.fixture
def runs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private runs directory, standing in for the repo's .testboard/runs."""
    d = tmp_path / "runs"
    d.mkdir()
    monkeypatch.setattr(tb, "RUNS_DIR", d)
    return d


@pytest.fixture
def registry_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private demo registry, standing in for demos/registry."""
    d = tmp_path / "registry"
    d.mkdir()
    monkeypatch.setattr(tb, "REGISTRY_DIR", d)
    return d


@pytest.fixture
def corpus_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private corpus. _corpus_dir is patched, not the environment, so no
    test can fall through to ~/dev/.demo-corpus even if the override is unset."""
    d = tmp_path / "corpus"
    d.mkdir()
    monkeypatch.setattr(tb, "_corpus_dir", lambda: d)
    return d


@pytest.fixture
def fixed_versions(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Freeze the checkout probe: build_state must not shell out to git here."""
    monkeypatch.setattr(tb, "current_versions", lambda: dict(VERSIONS))
    return dict(VERSIONS)


def _write_run(runs_dir: Path, name: str, record, age_seconds: float = 0.0) -> Path:
    """One run record on disk, with its mtime aged to whatever the test needs."""
    run_dir = runs_dir / name
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "run.json"
    if isinstance(record, str):
        path.write_text(record, encoding="utf-8")
    else:
        path.write_text(json.dumps(record), encoding="utf-8")
    if age_seconds:
        when = time.time() - age_seconds
        os.utime(path, (when, when))
    return run_dir


def _write_demo(
    registry_dir: Path,
    corpus_dir: Path,
    slug: str,
    registry: dict | None = None,
    manifest: dict | None = None,
    fetch_state: dict | None = None,
    bundle: bool = False,
) -> None:
    """A registered demo, optionally with analysis output beside it."""
    reg = {"slug": slug, "subject": {"name": slug}, "track": "flagship",
           "cadence": "weekly", "hosting": {"url": f"https://example.test/{slug}"}}
    reg.update(registry or {})
    (registry_dir / f"{slug}.json").write_text(json.dumps(reg), encoding="utf-8")

    out_dir = corpus_dir / "_out" / slug
    if manifest is not None:
        arch = out_dir / "architecture"
        arch.mkdir(parents=True, exist_ok=True)
        (arch / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if fetch_state is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "fetch-state.json").write_text(json.dumps(fetch_state), encoding="utf-8")
    if bundle:
        (out_dir / "bundle").mkdir(parents=True, exist_ok=True)
        (out_dir / "bundle" / "index.html").write_text("<html></html>", encoding="utf-8")


def _component(cid: str, enriched: bool = False, children=None) -> dict:
    node: dict = {"id": cid, "name": cid, "children": children or []}
    if enriched:
        node["ai_enhance"] = {"help_text": "explained"}
    return node


def _manifest(**kw) -> dict:
    doc = {
        "generated_at": "2026-08-23T00:00:00+00:00",
        "analyzer_version": "2.0.0",
        "components": [_component("root", children=[_component("alpha")])],
        "stats": {"total_components": 2, "total_files": 9, "total_symbols": 40,
                  "total_relationships": 3},
        "activity": {"provenance": {"head": "deadbeefcafe"}},
    }
    doc.update(kw)
    return doc


# -------------------------------------------------------------------- load_runs


def test_missing_runs_dir_is_empty_not_an_error(tmp_path: Path,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    """A board opened before the first run ever happened shows nothing, calmly."""
    monkeypatch.setattr(tb, "RUNS_DIR", tmp_path / "never-created")
    assert tb.load_runs() == []


def test_empty_runs_dir_is_empty(runs_dir: Path) -> None:
    assert tb.load_runs() == []


def test_a_finished_run_is_loaded_with_its_percent(runs_dir: Path) -> None:
    _write_run(runs_dir, "2026-08-23T00-00-00-crawl", {
        "id": "crawl-1", "kind": "crawl", "subject": "vscode", "status": "passed",
        "completed": 7, "total": 20, "passed": 7, "failed": 0,
    })
    runs = tb.load_runs()
    assert len(runs) == 1
    run = runs[0]
    assert run["id"] == "crawl-1"
    assert run["status"] == "passed"
    assert run["percent"] == 35
    assert run["live"] is False
    assert run["dir"].endswith("2026-08-23T00-00-00-crawl")


def test_a_run_with_no_total_does_not_divide_by_zero(runs_dir: Path) -> None:
    """A harness writes its record before it knows how much work there is."""
    _write_run(runs_dir, "starting", {"id": "r", "status": "passed", "total": 0,
                                      "completed": 0})
    assert tb.load_runs()[0]["percent"] == 0


def test_a_run_missing_its_counters_entirely_still_loads(runs_dir: Path) -> None:
    _write_run(runs_dir, "bare", {"id": "r", "status": "passed"})
    assert tb.load_runs()[0]["percent"] == 0


def test_unparseable_and_non_dict_records_are_skipped(runs_dir: Path) -> None:
    """One corrupt record must not blank the whole board."""
    _write_run(runs_dir, "a-broken", "{not json")
    _write_run(runs_dir, "b-a-list", [1, 2, 3])
    _write_run(runs_dir, "c-good", {"id": "survivor", "status": "passed"})
    (runs_dir / "d-empty").mkdir()
    runs = tb.load_runs()
    assert [r["id"] for r in runs] == ["survivor"]


# ------------------------------------------------------------------- liveness


def test_a_freshly_touched_running_record_is_live(runs_dir: Path) -> None:
    """The process is still writing, so the board says so and leaves it alone."""
    _write_run(runs_dir, "now", {"id": "r", "status": "running", "completed": 3,
                                 "total": 10})
    run = tb.load_runs()[0]
    assert run["live"] is True
    assert run["status"] == "running"
    assert run["seconds_since_update"] < tb.STALE_AFTER_SECONDS


def test_a_stale_running_record_becomes_stalled(runs_dir: Path) -> None:
    """The point of the board. A dead process cannot correct its own record, so
    "running" plus an untouched file is the signature of a run that died quietly,
    and the board must say stalled rather than repeat the record's last belief."""
    _write_run(runs_dir, "abandoned", {"id": "r", "status": "running",
                                       "completed": 3, "total": 10},
               age_seconds=tb.STALE_AFTER_SECONDS + 60)
    run = tb.load_runs()[0]
    assert run["live"] is False
    assert run["status"] == "stalled"
    assert run["seconds_since_update"] >= tb.STALE_AFTER_SECONDS


def test_the_staleness_boundary_is_the_declared_threshold(runs_dir: Path) -> None:
    """Just inside the window is still alive: the threshold is the only knob."""
    _write_run(runs_dir, "recent", {"id": "r", "status": "running"},
               age_seconds=tb.STALE_AFTER_SECONDS - 30)
    assert tb.load_runs()[0]["live"] is True


def test_a_finished_record_is_never_marked_live(runs_dir: Path) -> None:
    _write_run(runs_dir, "done", {"id": "r", "status": "failed"})
    run = tb.load_runs()[0]
    assert run["live"] is False
    assert run["status"] == "failed"
    assert "seconds_since_update" not in run


def test_live_runs_sort_ahead_of_finished_runs(runs_dir: Path) -> None:
    """Directory names sort newest-first, but a live run outranks that ordering:
    the name is chronology, liveness is urgency, and the board leads with urgency."""
    _write_run(runs_dir, "z-newest-but-done", {"id": "done", "status": "passed"})
    _write_run(runs_dir, "a-oldest-but-live", {"id": "live", "status": "running"})
    assert [r["id"] for r in tb.load_runs()] == ["live", "done"]


# ------------------------------------------------------------------ tail_events


def test_no_events_file_yields_no_events(tmp_path: Path) -> None:
    assert tb.tail_events(tmp_path) == []


def test_the_last_n_events_come_back_in_order(tmp_path: Path) -> None:
    lines = [json.dumps({"n": i}) for i in range(10)]
    (tmp_path / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert [e["n"] for e in tb.tail_events(tmp_path, limit=3)] == [7, 8, 9]


def test_a_torn_final_line_does_not_lose_the_rest(tmp_path: Path) -> None:
    """A harness killed mid-write leaves a half-line. The read must survive it."""
    (tmp_path / "events.jsonl").write_text(
        '{"n": 1}\nnot json at all\n{"n": 2}\n{"n": 3', encoding="utf-8")
    assert [e["n"] for e in tb.tail_events(tmp_path)] == [1, 2]


# ------------------------------------------------------------------ load_fleet


def test_missing_registry_yields_no_fleet(tmp_path: Path,
                                          monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tb, "REGISTRY_DIR", tmp_path / "no-registry")
    assert tb.load_fleet(dict(VERSIONS)) == []


def test_a_registered_demo_with_nothing_on_disk_is_reported_unanalyzed(
        registry_dir: Path, corpus_dir: Path) -> None:
    """Registration is a plan; analysis is a fact. A plan with no fact is a row,
    not a crash, because "registered but never built" is a state worth seeing."""
    _write_demo(registry_dir, corpus_dir, "ghost")
    rows = tb.load_fleet(dict(VERSIONS))
    assert len(rows) == 1
    row = rows[0]
    assert row["analyzed"] is False
    assert row["analyzer_drift"] is False
    assert row["bundle_built"] is False
    assert row["subject_sha"] is None
    assert "components" not in row


def test_an_analyzed_demo_reports_counts_sha_and_head(registry_dir: Path,
                                                      corpus_dir: Path) -> None:
    _write_demo(registry_dir, corpus_dir, "vscode",
                registry={"subject": {"name": "microsoft/vscode"}},
                manifest=_manifest(),
                fetch_state={"resolved_sha": "1234abcd", "fetched_at": "2026-08-22T10:00:00Z"},
                bundle=True)
    row = tb.load_fleet(dict(VERSIONS))[0]
    assert row["analyzed"] is True
    assert row["subject"] == "microsoft/vscode"
    assert row["url"] == "https://example.test/vscode"
    assert row["components"] == 2
    assert row["files"] == 9
    assert row["symbols"] == 40
    assert row["relationships"] == 3
    assert row["subject_sha"] == "1234abcd"
    assert row["fetched_at"] == "2026-08-22T10:00:00Z"
    assert row["head_at_analysis"] == "deadbeefcafe"
    assert row["bundle_built"] is True


def test_analyzer_drift_is_flagged_when_the_checkout_has_moved(
        registry_dir: Path, corpus_dir: Path) -> None:
    """The recurring bite: code ships, the demo does not get regenerated, and the
    deployed map quietly represents a tool nobody is talking about any more."""
    _write_demo(registry_dir, corpus_dir, "stale",
                manifest=_manifest(analyzer_version="1.0.0"))
    assert tb.load_fleet(dict(VERSIONS))[0]["analyzer_drift"] is True


def test_matching_analyzer_versions_are_not_drift(registry_dir: Path,
                                                  corpus_dir: Path) -> None:
    _write_demo(registry_dir, corpus_dir, "current",
                manifest=_manifest(analyzer_version="2.0.0"))
    assert tb.load_fleet(dict(VERSIONS))[0]["analyzer_drift"] is False


def test_an_unknown_version_on_either_side_is_not_called_drift(
        registry_dir: Path, corpus_dir: Path) -> None:
    """Absence is not evidence of a mismatch. Claiming drift from a missing
    version would train the owner to ignore the flag."""
    _write_demo(registry_dir, corpus_dir, "no-manifest-version",
                manifest=_manifest(analyzer_version=None))
    _write_demo(registry_dir, corpus_dir, "no-checkout-version",
                manifest=_manifest(analyzer_version="1.0.0"))
    rows = {r["slug"]: r for r in tb.load_fleet({"analyzer_version": None})}
    assert rows["no-manifest-version"]["analyzer_drift"] is False
    assert rows["no-checkout-version"]["analyzer_drift"] is False


def test_enrichment_is_found_however_deep_it_sits(registry_dir: Path,
                                                  corpus_dir: Path) -> None:
    """Enrichment attaches to whichever components earned it, which may be three
    levels down a tree. A shallow check would report an enriched demo as plain."""
    deep = _component("root", children=[
        _component("alpha", children=[
            _component("alpha.one"),
            _component("alpha.two", children=[_component("alpha.two.leaf", enriched=True)]),
        ]),
        _component("beta"),
    ])
    _write_demo(registry_dir, corpus_dir, "enriched", manifest=_manifest(components=[deep]))
    assert tb.load_fleet(dict(VERSIONS))[0]["enriched"] is True


def test_a_tree_with_no_enrichment_anywhere_is_reported_plain(registry_dir: Path,
                                                              corpus_dir: Path) -> None:
    plain = _component("root", children=[
        _component("alpha", children=[_component("alpha.one")]),
        _component("beta"),
    ])
    _write_demo(registry_dir, corpus_dir, "plain", manifest=_manifest(components=[plain]))
    assert tb.load_fleet(dict(VERSIONS))[0]["enriched"] is False


def test_a_corrupt_registry_entry_is_skipped(registry_dir: Path,
                                             corpus_dir: Path) -> None:
    (registry_dir / "broken.json").write_text("{not json", encoding="utf-8")
    _write_demo(registry_dir, corpus_dir, "good")
    assert [r["slug"] for r in tb.load_fleet(dict(VERSIONS))] == ["good"]


# ------------------------------------------------------------------ build_state


def test_the_state_payload_carries_versions_runs_fleet_and_a_live_count(
        runs_dir: Path, registry_dir: Path, corpus_dir: Path,
        fixed_versions: dict) -> None:
    _write_run(runs_dir, "a-live", {"id": "live-1", "status": "running"})
    _write_run(runs_dir, "b-live", {"id": "live-2", "status": "running"})
    _write_run(runs_dir, "c-dead", {"id": "dead", "status": "running"},
               age_seconds=tb.STALE_AFTER_SECONDS + 60)
    _write_run(runs_dir, "d-done", {"id": "done", "status": "passed"})
    _write_demo(registry_dir, corpus_dir, "vscode", manifest=_manifest())

    state = tb.build_state()
    assert state["versions"] == fixed_versions
    assert state["live_count"] == 2
    assert len(state["runs"]) == 4
    assert [r["slug"] for r in state["fleet"]] == ["vscode"]
    assert state["runs_dir"] == str(runs_dir)
    assert state["generated_at"]


def test_live_runs_carry_their_tailed_events(runs_dir: Path, registry_dir: Path,
                                             corpus_dir: Path, fixed_versions: dict) -> None:
    run_dir = _write_run(runs_dir, "live", {"id": "r", "status": "running"})
    (run_dir / "events.jsonl").write_text('{"msg": "one"}\n{"msg": "two"}\n',
                                          encoding="utf-8")
    _write_run(runs_dir, "done", {"id": "d", "status": "passed"})
    runs = {r["id"]: r for r in tb.build_state()["runs"]}
    assert [e["msg"] for e in runs["r"]["events"]] == ["one", "two"]
    assert "events" not in runs["d"]


def test_a_run_is_attached_to_the_demo_it_exercised(runs_dir: Path,
                                                    registry_dir: Path,
                                                    corpus_dir: Path,
                                                    fixed_versions: dict) -> None:
    """The join that makes this a board rather than two lists. A run names its
    subject the way a person would, so match on the slug or the subject name."""
    _write_run(runs_dir, "by-slug", {"id": "run-slug", "kind": "crawl",
                                     "subject": "vscode", "status": "passed",
                                     "passed": 12, "failed": 0})
    _write_run(runs_dir, "by-name", {"id": "run-name", "kind": "lint",
                                     "subject": "facebook/react", "status": "failed",
                                     "passed": 3, "failed": 1})
    _write_demo(registry_dir, corpus_dir, "vscode", manifest=_manifest())
    _write_demo(registry_dir, corpus_dir, "react",
                registry={"subject": {"name": "facebook/react"}}, manifest=_manifest())
    _write_demo(registry_dir, corpus_dir, "untouched", manifest=_manifest())

    rows = {r["slug"]: r for r in tb.build_state()["fleet"]}
    assert rows["vscode"]["last_run"]["id"] == "run-slug"
    assert rows["react"]["last_run"]["id"] == "run-name"
    assert rows["react"]["last_run"]["failed"] == 1
    assert rows["untouched"]["last_run"] is None


def test_the_payload_is_json_serializable(runs_dir: Path, registry_dir: Path,
                                          corpus_dir: Path, fixed_versions: dict) -> None:
    """The board serves this over HTTP. A Path leaking into the payload would
    only surface as a 500 on someone else's machine."""
    _write_run(runs_dir, "live", {"id": "r", "status": "running", "subject": "vscode"})
    _write_demo(registry_dir, corpus_dir, "vscode", manifest=_manifest(),
                fetch_state={"resolved_sha": "abc"}, bundle=True)
    json.dumps(tb.build_state())


# ------------------------------------------------------------------- the server


@pytest.fixture
def server(runs_dir: Path, registry_dir: Path, corpus_dir: Path,
           fixed_versions: dict, tmp_path: Path,
           monkeypatch: pytest.MonkeyPatch):
    """The real handler on a real socket, on whatever port the OS hands out.

    Port 0 rather than a chosen number: the board's own default port is often
    already serving on a developer's machine, and a test that fights it for a
    socket fails for a reason that has nothing to do with the board."""
    dashboard = tmp_path / "dashboard.html"
    dashboard.write_text("<!doctype html>\n<title>testboard</title>\n", encoding="utf-8")
    monkeypatch.setattr(tb, "DASHBOARD", dashboard)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), tb.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_the_state_endpoint_serves_the_payload(server: str, runs_dir: Path) -> None:
    _write_run(runs_dir, "live", {"id": "r", "status": "running"})
    with urllib.request.urlopen(f"{server}/api/state", timeout=10) as resp:
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "application/json"
        payload = json.loads(resp.read().decode("utf-8"))
    for key in ("generated_at", "repo_root", "runs_dir", "versions", "runs",
                "fleet", "live_count"):
        assert key in payload
    assert payload["live_count"] == 1


def test_the_state_endpoint_is_never_cached(server: str) -> None:
    """A cached board is a lie about the present, which is all the board is for."""
    with urllib.request.urlopen(f"{server}/api/state", timeout=10) as resp:
        assert resp.headers["Cache-Control"] == "no-store"


def test_the_root_path_serves_the_dashboard(server: str) -> None:
    for path in ("/", "/index.html"):
        with urllib.request.urlopen(f"{server}{path}", timeout=10) as resp:
            assert resp.status == 200
            assert resp.headers["Content-Type"] == "text/html; charset=utf-8"
            assert b"<!doctype html>" in resp.read()


def test_an_unknown_path_is_a_404(server: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(f"{server}/nope", timeout=10)
    assert excinfo.value.code == 404


def test_a_missing_dashboard_file_is_reported_as_a_server_error(
        server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """the dashboard file is absent, which is the path a stripped or partial checkout takes, so this is
    the path a fresh clone actually takes when someone opens the board."""
    monkeypatch.setattr(tb, "DASHBOARD", tmp_path / "absent.html")
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(f"{server}/", timeout=10)
    assert excinfo.value.code == 500


# ------------------------------------------------ enrichment owner control


def test_enrichment_resume_requires_and_persists_a_higher_checkpoint(
    runs_dir, tmp_path
):
    control_module = _load_control()
    control_module.testboard.RUNS_DIR = runs_dir
    run_id = "2026-08-27-enhance-unamentis"
    run_dir = runs_dir / run_id
    run_dir.mkdir()
    control_path = tmp_path / "control.json"
    control_path.write_text(json.dumps({
        "state": "paused", "spent_usd": 10.0, "reserved_usd": 2.0,
        "pause_at_usd": 10.0, "revision": 3,
    }))
    (run_dir / "run.json").write_text(json.dumps({
        "kind": "enhance",
        "enrichment_control": {"path": str(control_path)},
    }))

    refused = control_module.enrichment_control(
        run_id, "resume", {"pause_at_usd": 12.0}
    )
    assert refused["status"] == 400
    accepted = control_module.enrichment_control(
        run_id, "resume", {"pause_at_usd": 20.0}
    )
    assert accepted["status"] == 202
    persisted = json.loads(control_path.read_text())
    assert persisted["state"] == "running"
    assert persisted["pause_at_usd"] == 20.0
    assert persisted["revision"] == 4


def test_enrichment_cancel_is_persisted_for_the_engine_to_observe(runs_dir, tmp_path):
    control_module = _load_control()
    control_module.testboard.RUNS_DIR = runs_dir
    run_id = "2026-08-27-enhance-unamentis"
    run_dir = runs_dir / run_id
    run_dir.mkdir()
    control_path = tmp_path / "control.json"
    control_path.write_text(json.dumps({"state": "paused", "revision": 1}))
    (run_dir / "run.json").write_text(json.dumps({
        "kind": "enhance",
        "enrichment_control": {"path": str(control_path)},
    }))
    result = control_module.enrichment_control(run_id, "cancel", {})
    assert result["status"] == 202
    assert json.loads(control_path.read_text())["state"] == "cancelled"


# --------------------------------------------------------------- LedgerWatch


class TestLedgerWatch:
    """Live telemetry from real artifacts only.

    Born from an owner directive after a two-hour enrichment ran as one silent
    board step and the staleness inference called a healthy run stalled. Every
    assertion here is about the honesty rules: numbers come from the ledger and
    the process table, at most one event per tick, and a quiet tick says what
    is actually true instead of emitting a reassuring pulse.
    """

    @staticmethod
    def _emit_module():
        spec = importlib.util.spec_from_file_location(
            "testboard_emit", REPO_ROOT / "scripts" / "testboard_emit.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod

    def _watch(self, tmp_path, monkeypatch, ps=lambda: []):
        monkeypatch.setenv("TESTBOARD_DIR", str(tmp_path / "runs"))
        te = self._emit_module()

        run = te.ProcessingRun("enhance", slug="subj").__enter__()
        ledger = tmp_path / "ledger.jsonl"
        watch = te.LedgerWatch(run, ledger, child_pid=99999, ps_fn=ps)
        return run, ledger, watch

    def _events(self, run):
        import json as _json

        path = run.run_dir / "events.jsonl"
        return [_json.loads(line) for line in path.read_text().splitlines()]

    def test_a_tick_aggregates_real_rows_into_one_event(self, tmp_path, monkeypatch):
        run, ledger, watch = self._watch(tmp_path, monkeypatch)
        ledger.write_text(
            '{"phase": "p2_ladder", "rung": "2a", "ok": true, "cost_usd": 1.5}\n'
            '{"phase": "p2_ladder", "rung": "2a", "ok": true, "cost_usd": 0.5}\n'
            '{"phase": "p2_ladder", "rung": "2a", "ok": false, "cost_usd": 0.0}\n'
        )
        watch.tick()
        progress = [e for e in self._events(run) if e["type"] == "progress"]
        assert len(progress) == 1, "three rows must aggregate into ONE event"
        assert progress[0]["new_calls"] == 3
        assert progress[0]["calls_ok"] == 2
        assert progress[0]["calls_failed"] == 1
        assert progress[0]["spent_usd"] == 2.0
        assert "p2_ladder/2a" in run.record["current"]
        assert "$2.00" in run.record["current"]

    def test_a_quiet_tick_with_calls_in_flight_shows_their_real_ages(
        self, tmp_path, monkeypatch
    ):
        run, ledger, watch = self._watch(
            tmp_path, monkeypatch, ps=lambda: ["04:33", "02:10"]
        )
        watch.tick()  # ledger does not even exist yet
        progress = [e for e in self._events(run) if e["type"] == "progress"]
        assert not progress, "nothing completed, so no event: a pulse would be fake"
        assert "in flight: 2 (04:33, 02:10)" in run.record["current"]

    def test_a_dead_quiet_tick_says_so_instead_of_reassuring(
        self, tmp_path, monkeypatch
    ):
        run, ledger, watch = self._watch(tmp_path, monkeypatch)
        watch.tick()
        assert "no model call in flight" in run.record["current"]

    def test_a_partial_line_waits_and_a_malformed_line_is_skipped(
        self, tmp_path, monkeypatch
    ):
        run, ledger, watch = self._watch(tmp_path, monkeypatch)
        ledger.write_text(
            'not json at all\n'
            '{"phase": "p1", "ok": true, "cost_usd": 0.7}\n'
            '{"phase": "p2_ladder", "rung": "2a", "ok": true, "cost_'  # torn write
        )
        watch.tick()
        assert watch.calls_ok == 1, "the torn tail must not be consumed"
        ledger.write_text(
            ledger.read_text() + 'usd": 0.3}\n'
        )
        watch.tick()
        assert watch.calls_ok == 2, "the completed line lands on the next tick"
        assert watch.spent_usd == 1.0
