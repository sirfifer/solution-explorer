"""Publication completion is separate from operational process success."""

from types import SimpleNamespace

from analyzer.enrich.completion import evaluate_completion
from analyzer.enrich.pipeline import LedgerRow, PhaseResult, PipelineResult


def _result(*, verdict="done", criterion="met", disagreement=0.0, ledger=None):
    determination = SimpleNamespace(
        verdict=verdict,
        verdicts=[SimpleNamespace(criterion_id="u1", verdict=criterion)],
    )
    adjudication = SimpleNamespace(disagreement_rate=lambda: disagreement)
    return PipelineResult(
        phases=[
            PhaseResult("p3_adjudication", "ok", data={"adjudication": adjudication}),
            PhaseResult("p5_determination", "ok", data={"determination": determination}),
        ],
        ledger=list(ledger or []),
    )


def test_done_every_criterion_and_clean_audit_is_publishable():
    status, issues = evaluate_completion(_result(), audit={"verdict": "pass"})
    assert status == "complete"
    assert issues == []


def test_operational_success_does_not_hide_quality_failure():
    result = _result(verdict="done-with-reservations", criterion="unmet", disagreement=0.75)
    assert result.ok
    status, issues = evaluate_completion(result, audit={"verdict": "fail"})
    assert status == "incomplete"
    assert any("not 'done'" in issue for issue in issues)
    assert any("75.0%" in issue for issue in issues)


def test_a_failed_fallback_call_blocks_publication():
    failed = LedgerRow(
        phase="p2_ladder", rung="2a", model="sonnet", ok=False, error="blank"
    )
    status, issues = evaluate_completion(
        _result(ledger=[failed]), audit={"verdict": "pass"}
    )
    assert status == "incomplete"
    assert "1 model invocation(s) failed" in issues


def test_measured_cost_overshoot_blocks_publication():
    result = _result()
    result.total_cost_usd = 2.72
    result.cost_ceiling_usd = 2.50
    status, issues = evaluate_completion(result, audit={"verdict": "pass"})
    assert status == "incomplete"
    assert any("exceeded the configured" in issue for issue in issues)
