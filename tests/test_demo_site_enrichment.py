"""T11: the harness carries the ladder, and the gate reads the truth instrument.

The form scorer measured 83 of 99 calibration components at exactly 85.0 while
nothing checked whether one claim was true. A gate that reads only that number
certifies shape and calls it quality, so the gate now reads the census and the
adjudication verdicts, and keeps the form scorer as a floor.

The NOT_IMPLEMENTED discipline is the sharp edge here: a ladder run whose
adjudication sampled nothing has no truth instrument, and PASS would be a green
light with nothing behind it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "scripts" / "demo-site.py"


def _load_module():
    """Register before executing: dataclasses introspection needs sys.modules."""
    spec = importlib.util.spec_from_file_location("demo_site_enrichment", HARNESS)
    module = importlib.util.module_from_spec(spec)
    sys.modules["demo_site_enrichment"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def ds():
    return _load_module()


# --- the registry block --------------------------------------------------------


def test_the_vscode_entry_carries_the_wave_one_forced_iteration_decision(ds):
    entry = ds.load_registry("vscode")
    enrichment = entry["enrichment"]
    assert enrichment["pipeline"] == "ladder"
    assert enrichment["iteration"]["min_rounds"] == 1, (
        "Wave 1 forces at least one improvement round"
    )
    assert enrichment["iteration"]["max_rounds"] == 2
    assert ds.validate_registry(entry) == []


def test_the_registry_bindings_resolve_to_real_tier_bindings(ds):
    from analyzer.enrich.pipeline import DEFAULT_MODELS, resolve_models

    entry = ds.load_registry("vscode")
    models = resolve_models(entry["enrichment"]["models"])
    assert set(models) >= set(DEFAULT_MODELS)
    assert models["p2a_bulk"].label == "anthropic-claude-cli:sonnet"
    assert models["p2b_escalated"].label == "anthropic-claude-cli:opus"
    assert models["p3_adjudication"].label == "anthropic-claude-cli:opus"
    assert all(spec.pinned for spec in models.values()), (
        "every Wave 1 binding is pinned; nothing routes by accident"
    )


def test_an_entry_with_no_enrichment_block_is_still_valid(ds):
    """The block is optional: an older entry runs the classic bulk pass."""
    entry = ds.load_registry("vscode")
    del entry["enrichment"]
    assert ds.validate_registry(entry) == []


def test_a_malformed_enrichment_block_is_rejected_before_the_run(ds):
    """A typo discovered mid-run has already spent most of the budget."""
    assert ds._enrichment_errors({"pipeline": "laddr"})
    assert ds._enrichment_errors({"models": "not an object"})
    assert ds._enrichment_errors({"iteration": {"min_rounds": -1}})
    errors = ds._enrichment_errors({"iteration": {"min_rounds": 3, "max_rounds": 1}})
    assert errors and "could never be reached" in errors[0]


# --- the plumbing ---------------------------------------------------------------


def _capture_cmd(ds, monkeypatch, corpus, tmp_path):
    captured = {}

    class FakeResult:
        returncode = 0

    def fake_run(cmd, *args, **kwargs):
        captured["cmd"] = cmd
        return FakeResult()

    monkeypatch.setattr(ds.subprocess, "run", fake_run)
    store = ds._store_path(corpus["slug"], tmp_path)
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text("")
    ds.run_enhance(corpus, tmp_path)
    return captured["cmd"]


def test_a_ladder_registry_entry_runs_the_ladder_with_its_own_bindings(
    ds, monkeypatch, tmp_path
):
    corpus = ds.load_registry("vscode")
    cmd = _capture_cmd(ds, monkeypatch, corpus, tmp_path)

    assert "--ladder" in cmd
    assert "--run-dir" in cmd
    run_dir = cmd[cmd.index("--run-dir") + 1]
    assert run_dir.endswith("enrichment"), (
        "the Run Report lands in the run directory beside the rest of the refresh"
    )
    assert "--min-rounds" in cmd and cmd[cmd.index("--min-rounds") + 1] == "1"
    assert "--max-rounds" in cmd and cmd[cmd.index("--max-rounds") + 1] == "2"

    bindings = [
        cmd[i + 1] for i, token in enumerate(cmd) if token == "--phase-model"
    ]
    assert "p2b_escalated=anthropic-claude-cli:opus" in bindings
    assert len(bindings) == len(corpus["enrichment"]["models"])
    # The registry's ceiling still applies to the whole ladder.
    assert "--max-cost-usd" in cmd
    assert cmd[cmd.index("--max-cost-usd") + 1] == str(corpus["budget"]["max_cost_usd"])


def test_an_entry_without_the_block_runs_the_classic_pass_untouched(
    ds, monkeypatch, tmp_path
):
    corpus = ds.load_registry("vscode")
    del corpus["enrichment"]
    cmd = _capture_cmd(ds, monkeypatch, corpus, tmp_path)
    assert "--ladder" not in cmd
    assert "--phase-model" not in cmd
    assert "--run-dir" not in cmd
    assert "--update" in cmd


# --- the gate reads the truth instrument ----------------------------------------


def _run_report(**overrides):
    report = {
        "identity": {"dry_run": False},
        "census": {
            "total": 100, "grounded": 92, "grounded_fraction": 0.92,
            "unresolved": [], "by_state": {"grounded@sonnet": 92, "honest-gap": 8},
        },
        "adjudication": {
            "checked": 10, "unsupported": 1, "disagreement_rate": 0.1,
            "identity": {"verdicts": {"confirmed": 40}},
        },
        "criteria": [{"criterion_id": "u1", "verdict": "met"}],
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(report.get(key), dict):
            report[key] = {**report[key], **value}
        else:
            report[key] = value
    return report


def _gate(ds, tmp_path, report, monkeypatch):
    run_dir = tmp_path / "enrichment"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(json.dumps(report))
    monkeypatch.setattr(ds, "enrichment_run_dir", lambda slug, **kw: run_dir)
    return ds.gate_enrichment_quality("vscode", tmp_path, {"min_enrichment_score": 85})


def test_a_healthy_ladder_run_passes_on_census_and_disagreement(ds, tmp_path, monkeypatch):
    result = _gate(ds, tmp_path, _run_report(), monkeypatch)
    assert result.state == "PASS"
    assert "92/100 grounded" in result.detail
    assert "disagreement 10.0%" in result.detail


def test_a_run_that_sampled_nothing_is_not_implemented_not_pass(ds, tmp_path, monkeypatch):
    """The sharp edge: PASS here would be a green light with nothing behind it."""
    report = _run_report(adjudication={"checked": 0, "disagreement_rate": None})
    result = _gate(ds, tmp_path, report, monkeypatch)
    assert result.state == "NOT_IMPLEMENTED"
    assert "undefined rather than zero" in result.detail
    assert "floor, not a quality verdict" in result.detail


def test_an_item_still_asking_to_climb_fails_the_gate(ds, tmp_path, monkeypatch):
    report = _run_report(census={"unresolved": ["services/api", "libs/core"]})
    result = _gate(ds, tmp_path, report, monkeypatch)
    assert result.state == "FAIL"
    assert "still asking to climb" in result.detail
    assert "unfinished work, not an honest gap" in result.detail


def test_too_much_disagreement_fails_the_gate(ds, tmp_path, monkeypatch):
    report = _run_report(adjudication={"checked": 20, "disagreement_rate": 0.45})
    result = _gate(ds, tmp_path, report, monkeypatch)
    assert result.state == "FAIL"
    assert "would not stand behind 45.0%" in result.detail


def test_too_little_grounding_fails_the_gate(ds, tmp_path, monkeypatch):
    report = _run_report(census={"grounded": 40, "grounded_fraction": 0.4})
    result = _gate(ds, tmp_path, report, monkeypatch)
    assert result.state == "FAIL"
    assert "only 40.0% of items grounded" in result.detail


def test_an_unmet_criterion_fails_the_gate(ds, tmp_path, monkeypatch):
    """The determination already answered these; the gate reads them back.

    Recomputing them here would let the gate and the Run Report disagree about
    the same run, which is the cross-surface contradiction class the handoff
    names as one of the run's deepest defects.
    """
    report = _run_report(criteria=[
        {"criterion_id": "u1", "verdict": "met"},
        {"criterion_id": "u3", "verdict": "unmet"},
    ])
    result = _gate(ds, tmp_path, report, monkeypatch)
    assert result.state == "FAIL"
    assert "criteria not met: u3" in result.detail


def test_an_empty_census_is_not_implemented(ds, tmp_path, monkeypatch):
    report = _run_report(census={"total": 0, "grounded": 0, "grounded_fraction": 0.0})
    result = _gate(ds, tmp_path, report, monkeypatch)
    assert result.state == "NOT_IMPLEMENTED"
    assert "nothing to read" in result.detail
    assert "rather than passed on the form floor" in result.detail


def test_a_dry_run_report_skips_rather_than_passing(ds, tmp_path, monkeypatch):
    report = _run_report(identity={"dry_run": True})
    result = _gate(ds, tmp_path, report, monkeypatch)
    assert result.state == "SKIP"
    assert "no model was invoked" in result.detail


def test_a_corrupt_run_report_fails_loudly(ds, tmp_path, monkeypatch):
    run_dir = tmp_path / "enrichment"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text("{not json")
    monkeypatch.setattr(ds, "enrichment_run_dir", lambda slug, **kw: run_dir)
    result = ds.gate_enrichment_quality("vscode", tmp_path, {"min_enrichment_score": 85})
    assert result.state == "FAIL"
    assert "not valid JSON" in result.detail


def test_without_a_ladder_report_the_classic_gate_still_works(ds, tmp_path, monkeypatch):
    """A registry entry with no ladder must behave exactly as it did before."""
    monkeypatch.setattr(ds, "enrichment_run_dir", lambda slug, **kw: tmp_path / "absent")
    out = ds._out_dir("vscode", tmp_path)
    out.mkdir(parents=True, exist_ok=True)
    (out / "enhance-report.json").write_text(json.dumps({
        "failed_partitions": [], "scorer_pass": True, "scorer_summary": "score 91.0",
    }))
    result = ds.gate_enrichment_quality("vscode", tmp_path, {"min_enrichment_score": 85})
    assert result.state == "PASS"
    assert "score 91.0" in result.detail


def test_the_truth_bounds_are_stated_in_one_arguable_place(ds):
    """What 'good enough to publish' means should be arguable, not buried."""
    assert ds.MIN_GROUNDED_FRACTION == 0.80
    assert ds.MAX_DISAGREEMENT_RATE == 0.20
