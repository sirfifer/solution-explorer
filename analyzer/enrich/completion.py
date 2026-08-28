"""Shared completion semantics for the ladder CLI, report, and audit gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Optional


def evaluate_completion(result: Any, *, audit: Optional[dict] = None) -> tuple[str, list[str]]:
    """Return a quality status and exact reasons it is not publishable.

    Operational success is intentionally separate: a process can run every
    phase and still produce a map the adjudicator would not stand behind.
    """
    issues: list[str] = []
    if result.failed_phases:
        issues.append("operational phase failure: " + ", ".join(result.failed_phases))

    determination = None
    adjudication = None
    for phase in result.phases:
        if phase.name == "p5_determination":
            determination = (phase.data or {}).get("determination")
        elif phase.name == "p3_adjudication":
            adjudication = (phase.data or {}).get("adjudication")
    if determination is None:
        return ("failed" if result.failed_phases else "not-evaluated"), issues

    if determination.verdict != "done":
        issues.append(f"determination verdict is {determination.verdict!r}, not 'done'")
    non_met = [
        f"{verdict.criterion_id}:{verdict.verdict}"
        for verdict in determination.verdicts
        if verdict.verdict != "met"
    ]
    if non_met:
        issues.append("criteria not met: " + ", ".join(non_met))
    if adjudication is None or adjudication.disagreement_rate() is None:
        issues.append("adjudication disagreement is unmeasured")
    elif adjudication.disagreement_rate() > 0.20:
        issues.append(
            f"adjudication disagreement {adjudication.disagreement_rate():.1%} "
            "exceeds the 20% completion ceiling"
        )
    failed_calls = [row for row in result.ledger if not row.ok]
    if failed_calls:
        issues.append(f"{len(failed_calls)} model invocation(s) failed")
    if any(row.output_budget_ok is False for row in result.ledger):
        issues.append("one or more compact calls exceeded the delivered-byte budget")
    if any("agentic drift:" in note for note in result.notes):
        issues.append("one or more invocations used an external agent loop")
    cost_ceiling = getattr(result, "cost_ceiling_usd", None)
    if (
        cost_ceiling is not None
        and result.total_cost_usd > float(cost_ceiling) + 1e-9
    ):
        issues.append(
            f"measured cost ${result.total_cost_usd:.6f} exceeded the configured "
            f"${float(cost_ceiling):.6f} ceiling"
        )

    if audit is not None and audit.get("verdict") != "pass":
        issues.append(f"enrichment audit verdict is {audit.get('verdict', 'missing')!r}")
    if issues:
        return ("failed" if result.failed_phases else "incomplete"), issues
    if audit is None:
        return "pending-audit", []
    return "complete", []


def audit_run(run_dir: Path, *, store_path: Path) -> dict:
    """Load the repository's adversarial audit and run it in-process."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "enrichment-audit.py"
    spec = importlib.util.spec_from_file_location("_enrichment_audit", script)
    if spec is None or spec.loader is None:
        return {
            "verdict": "fail",
            "findings": [{"level": "fail", "check": "audit-load", "detail": str(script)}],
        }
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.audit(Path(run_dir), store_path=Path(store_path))
