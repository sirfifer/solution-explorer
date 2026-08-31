"""The run audit's output and accounting gates are executable contracts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _audit_module():
    path = Path(__file__).parents[1] / "scripts" / "enrichment-audit.py"
    spec = importlib.util.spec_from_file_location("enrichment_audit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_dir(
    tmp_path: Path, *, output: int, budget_ok=True, rung="2a", targets=10,
) -> Path:
    run = tmp_path / "run"
    run.mkdir(parents=True)
    row = {
        "rung": rung, "phase": "p2_ladder", "effort": "low",
        "tokens_out": output, "cost_usd": 1.0, "ok": True,
        "num_turns": 1, "targets": targets,
        "output_budget_bytes": 1000, "output_budget_ok": budget_ok,
    }
    (run / "ledger.jsonl").write_text(json.dumps(row) + "\n")
    (run / "progress.jsonl").write_text(json.dumps({
        "event": "plan", "rung": "2a", "targets": targets,
    }) + "\n")
    (run / "report.json").write_text(json.dumps({"census": {"total": targets}}))
    return run


def test_same_corpus_output_gate_has_a_narrow_inclusive_boundary(tmp_path):
    audit = _audit_module().audit
    at_limit = audit(
        _run_dir(tmp_path, output=300),
        baseline_output_tokens=1000, target_ratio=0.30,
    )
    assert not any(f["check"] == "output-reduction" for f in at_limit["findings"])

    over = audit(
        _run_dir(tmp_path / "over", output=301),
        baseline_output_tokens=1000, target_ratio=0.30,
    )
    assert any(
        f["level"] == "fail" and f["check"] == "output-reduction"
        for f in over["findings"]
    )


def test_compact_byte_violation_fails_the_run(tmp_path):
    report = _audit_module().audit(_run_dir(tmp_path, output=10, budget_ok=False))
    assert report["output_gate"]["compact_budget_violations"] == 1
    assert any(
        f["level"] == "fail" and f["check"] == "compact-output"
        for f in report["findings"]
    )


def test_measured_cost_above_configured_ceiling_fails_the_run(tmp_path):
    run = _run_dir(tmp_path, output=10)
    report_path = run / "report.json"
    report = json.loads(report_path.read_text())
    report["identity"] = {"policy": {"max_cost_usd": 0.50}}
    report_path.write_text(json.dumps(report))

    audited = _audit_module().audit(run)
    assert any(
        f["level"] == "fail" and f["check"] == "cost-ceiling-overshoot"
        for f in audited["findings"]
    )


def test_real_escalation_rung_names_are_included_in_cost(tmp_path):
    report = _audit_module().audit(
        _run_dir(tmp_path, output=10, rung="opus")
    )
    assert any(f["check"] == "escalation" for f in report["findings"])


def test_escalation_density_needs_a_real_sample_but_keeps_the_same_ceiling(tmp_path):
    tiny = _audit_module().audit(
        _run_dir(tmp_path, output=600, rung="opus", targets=2)
    )
    density = next(
        finding for finding in tiny["findings"]
        if finding["check"] == "escalation-output-density"
    )
    assert density["level"] == "info"
    assert "INCONCLUSIVE" in density["detail"]
    assert tiny["output_gate"]["escalation_release_sample_min"] == 10

    enough = _audit_module().audit(
        _run_dir(tmp_path / "enough", output=2751, rung="opus", targets=10)
    )
    density = next(
        finding for finding in enough["findings"]
        if finding["check"] == "escalation-output-density"
    )
    assert density["level"] == "fail"
    assert enough["verdict"] == "fail"


def test_work_order_density_cannot_hide_outside_the_ladder_gate(tmp_path):
    run = _run_dir(tmp_path, output=10, targets=10)
    repair = {
        "rung": "P5", "phase": "work_order", "effort": "low",
        "tokens_out": 5_201, "cost_usd": 1.0, "ok": True,
        "num_turns": 1, "targets": 10,
        "output_budget_bytes": 20_000, "output_budget_ok": True,
    }
    with (run / "ledger.jsonl").open("a") as fh:
        fh.write(json.dumps(repair) + "\n")

    report = _audit_module().audit(run)

    assert report["output_gate"]["work_order_tokens_per_attempt"] == 520.1
    assert report["output_gate"]["work_order_attempts"] == 10
    assert any(
        finding["level"] == "fail"
        and finding["check"] == "work-order-output-density"
        for finding in report["findings"]
    )


def test_cache_disabled_prefixes_are_not_expected_to_hit(tmp_path):
    run = _run_dir(tmp_path, output=10, targets=5)
    rows = [
        {
            "phase": "p2_ladder", "rung": "2a", "model": "sonnet",
            "effort": "low", "ok": True, "num_turns": 1, "targets": 1,
            "tokens_out": 1, "cost_usd": 0.01, "prefix_hash": "stable",
            "prefix_tokens_est": 4_000, "tokens_cached": 0,
            "tokens_cache_write": 0, "tokens_cache_write_1h": 0,
            "tokens_cache_write_5m": 0, "tokens_cache_write_unknown": 0,
            "cache_policy": "off",
        }
        for _ in range(2)
    ]
    (run / "ledger.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n"
    )
    report = _audit_module().audit(run)
    assert report["output_gate"]["non_warm_cache_misses"] == 0
    assert not any(f["check"] == "cache-boundary" for f in report["findings"])


def test_cache_policy_ttl_mismatch_and_net_loss_fail_release_sample(tmp_path):
    run = _run_dir(tmp_path, output=10, targets=5)
    rows = []
    for _ in range(5):
        rows.append({
            "phase": "p3_adjudication", "rung": "substitution-check",
            "model": "opus", "effort": "low", "ok": True,
            "num_turns": 1, "targets": 1, "tokens_out": 1,
            "cost_usd": 0.01, "cache_policy": "5m",
            "tokens_cache_write": 1_000, "tokens_cache_write_1h": 1_000,
            "tokens_cache_write_5m": 0, "tokens_cache_write_unknown": 0,
            "tokens_cached": 100,
        })
    (run / "ledger.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n"
    )
    report = _audit_module().audit(run)
    checks = {f["check"] for f in report["findings"] if f["level"] == "fail"}
    assert "cache-policy" in checks
    assert "cache-net-economics" in checks


def test_honest_gap_quality_reads_contract_reasons_from_the_census(tmp_path):
    run = _run_dir(tmp_path, output=10, targets=1)
    report_path = run / "report.json"
    report = json.loads(report_path.read_text())
    report["census"] = {
        "total": 1,
        "items": [{
            "target_kind": "component", "target_id": "voice-screen",
            "state": "honest_gap",
            "failed": [{
                "question": "purpose", "trigger": "E1",
                "note": "no answer was produced for a required question",
            }],
        }],
    }
    # The presentation-oriented escalation row has no duplicate failed list;
    # that must not make the audit conclude there were no gaps to inspect.
    report["escalations"] = [{
        "target_id": "voice-screen", "terminal": "honest-gap",
    }]
    report_path.write_text(json.dumps(report))

    audited = _audit_module().audit(run)

    assert any(
        finding["level"] == "fail"
        and finding["check"] == "honest-gap-quality"
        for finding in audited["findings"]
    )


def test_bulk_density_uses_unique_plan_so_retries_cannot_hide_waste(tmp_path):
    run = _run_dir(tmp_path, output=3_000, targets=10)
    duplicate = {
        "rung": "2a", "phase": "p2_ladder", "effort": "low",
        "tokens_out": 3_000, "cost_usd": 1.0, "ok": True,
        "num_turns": 1, "targets": 10,
        "output_budget_bytes": 20_000, "output_budget_ok": True,
    }
    with (run / "ledger.jsonl").open("a") as fh:
        fh.write(json.dumps(duplicate) + "\n")

    report = _audit_module().audit(run)

    assert report["work"]["bulk_attempted_targets"] == 20
    assert report["work"]["bulk_unique_targets"] == 10
    assert report["output_gate"]["bulk_tokens_per_target"] == 600.0
    assert any(
        finding["level"] == "fail"
        and finding["check"] == "bulk-output-density"
        for finding in report["findings"]
    )


def test_all_per_target_economics_keep_the_planned_denominator_on_scope_drift(tmp_path):
    run = _run_dir(tmp_path, output=1_000, targets=10)
    report_path = run / "report.json"
    report_path.write_text(json.dumps({"census": {"total": 13}}))

    audited = _audit_module().audit(run)

    assert any(f["check"] == "target-conservation" for f in audited["findings"])
    assert audited["work"]["usd_per_target"] == 0.1
    assert audited["work"]["out_tokens_per_target"] == 100.0
    assert audited["output_gate"]["ladder_tokens_per_unique_target"] == 100.0


def test_the_cache_read_floor_catches_a_small_unrelated_read(tmp_path):
    """A non-warm call must read at least its own prefix, not merely nonzero.

    The zero-read rule alone let a 120-token incidental read stand in for a
    5,000-token prefix; the stable block had been rewritten at the 2x rate and
    the audit called it healthy. Rows without a prefix estimate (older
    ledgers) stay governed by the zero-read rule so historical runs remain
    auditable.
    """
    run = tmp_path / "run"
    run.mkdir(parents=True)
    common = {
        "rung": "2a", "phase": "p2_ladder", "effort": "low", "ok": True,
        "num_turns": 1, "targets": 1, "cost_usd": 0.1, "tokens_out": 100,
        "output_budget_bytes": 1000, "output_budget_ok": True,
        "structured_output_enforced": True, "prefix_hash": "abc",
        "model": "sonnet", "prefix_tokens_est": 5000,
    }
    rows = [
        dict(common, tokens_cached=0),      # the permitted cold writer
        dict(common, tokens_cached=120),    # a shortfall: read < its prefix
        dict(common, tokens_cached=5200),   # healthy: read covers the prefix
    ]
    (run / "ledger.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n"
    )
    (run / "progress.jsonl").write_text(json.dumps({
        "event": "plan", "rung": "2a", "targets": 3,
    }) + "\n")
    (run / "report.json").write_text(json.dumps({"census": {"total": 3}}))

    report = _audit_module().audit(run)
    assert report["output_gate"]["prefix_read_shortfalls"] == 1
    assert any(
        f["level"] == "fail" and f["check"] == "cache-boundary"
        and "fewer cached tokens than their own prefix" in f["detail"]
        for f in report["findings"]
    )

    # Legacy rows without the estimate keep the old behaviour: one cold
    # writer is permitted and a second zero-read call still fails.
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    old = {k: v for k, v in common.items() if k != "prefix_tokens_est"}
    (legacy / "ledger.jsonl").write_text(
        "\n".join(json.dumps(dict(old, tokens_cached=n)) for n in (0, 120)) + "\n"
    )
    (legacy / "progress.jsonl").write_text(json.dumps({
        "event": "plan", "rung": "2a", "targets": 2,
    }) + "\n")
    (legacy / "report.json").write_text(json.dumps({"census": {"total": 2}}))
    legacy_report = _audit_module().audit(legacy)
    assert legacy_report["output_gate"]["prefix_read_shortfalls"] == 0


def test_cache_read_within_the_narrow_tokenizer_estimate_envelope_passes(tmp_path):
    run = tmp_path / "run"
    run.mkdir(parents=True)
    common = {
        "rung": "p5", "phase": "p5_determination", "effort": "low",
        "ok": True, "num_turns": 1, "targets": 1, "cost_usd": 0.1,
        "tokens_out": 100, "prefix_hash": "stable", "model": "fable",
        "prefix_tokens_est": 12_335,
    }
    rows = [
        dict(common, tokens_cached=0),
        dict(common, tokens_cached=12_306),  # observed live: 0.24% under estimate
    ]
    (run / "ledger.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n"
    )
    (run / "progress.jsonl").write_text("")
    (run / "report.json").write_text(json.dumps({"census": {"total": 0}}))

    report = _audit_module().audit(run)
    assert report["output_gate"]["prefix_read_shortfalls"] == 0
    assert not any(
        finding["check"] == "cache-boundary"
        for finding in report["findings"]
    )


def test_cache_boundary_also_covers_non_schema_phases(tmp_path):
    """A cacheable P5-style prefix is audited even without a compact schema."""
    run = tmp_path / "run"
    run.mkdir(parents=True)
    common = {
        "rung": "p5", "phase": "p5_determination", "effort": "low",
        "ok": True, "num_turns": 1, "targets": 1, "cost_usd": 0.1,
        "tokens_out": 100, "structured_output_enforced": False,
        "prefix_hash": "stable-p5", "model": "sonnet",
        "prefix_tokens_est": 4000,
    }
    rows = [dict(common, tokens_cached=0), dict(common, tokens_cached=80)]
    (run / "ledger.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n"
    )
    (run / "progress.jsonl").write_text("")
    (run / "report.json").write_text(json.dumps({"census": {"total": 0}}))

    report = _audit_module().audit(run)
    assert report["output_gate"]["prefix_read_shortfalls"] == 1
    assert any(
        finding["check"] == "cache-boundary"
        for finding in report["findings"]
    )


def test_p5_input_guard_allows_measured_quality_context_but_flags_runaway(tmp_path):
    def write_run(name, tokens):
        run = tmp_path / name
        run.mkdir()
        (run / "ledger.jsonl").write_text(json.dumps({
            "phase": "p5_determination", "ok": True, "targets": 1,
            "tokens_fresh_in": 0, "tokens_cache_write": tokens,
            "tokens_cached": 0, "tokens_out": 100, "cost_usd": 0.1,
        }) + "\n")
        (run / "progress.jsonl").write_text("")
        (run / "report.json").write_text(json.dumps({"census": {"total": 0}}))
        return _audit_module().audit(run)

    measured = write_run("measured", 43_453)
    assert not any(
        item["check"] == "input-ceiling" for item in measured["findings"]
    )

    runaway = write_run("runaway", 70_001)
    assert any(
        item["level"] == "fail" and item["check"] == "input-ceiling"
        for item in runaway["findings"]
    )


def test_two_cold_p5_prefixes_fail_even_though_each_hash_is_a_singleton(tmp_path):
    run = tmp_path / "run"
    run.mkdir(parents=True)
    common = {
        "phase": "p5_determination", "effort": "low", "ok": True,
        "num_turns": 1, "targets": 1, "cost_usd": 0.1,
        "tokens_out": 100, "model": "fable", "tokens_cached": 0,
    }
    rows = [
        dict(common, prefix_hash="p5-before"),
        dict(common, prefix_hash="p5-after"),
    ]
    (run / "ledger.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n"
    )
    (run / "progress.jsonl").write_text("")
    (run / "report.json").write_text(json.dumps({"census": {"total": 0}}))

    report = _audit_module().audit(run)
    assert report["output_gate"]["stable_prefix_fragmentations"] == 1
    assert any(
        finding["check"] == "cache-boundary"
        and "leaked into" in finding["detail"]
        for finding in report["findings"]
    )
