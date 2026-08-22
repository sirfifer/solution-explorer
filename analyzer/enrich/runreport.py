"""The Run Report: part invoice, part bill of materials, part verdict with reasons.

``ENRICHMENT-ENGINE.md`` section 5. An artifact separate from the product, in
machine JSON plus a human rendering, **written even on partial failure**. That
last clause is the whole design constraint: a report that only appears when
everything worked is a report nobody can use to find out why something did not.

So the report is assembled from whatever the run actually produced. A phase that
never ran, failed, or was skipped past the cost ceiling appears in the report
saying so. Nothing here raises on a missing input; a missing section is rendered
as missing rather than omitted, because an omitted section and a section with
nothing in it look identical to a reader and mean very different things.

**Cost is denominated in API-equivalent units.** Every dollar figure is what the
CLI reported for the work performed, metered against the owner's subscription.
It is a truthful meter of how much subscription usage a run consumed, and the
unit the ceilings meter against. It is never money spent, and the rendered report
says so on the page rather than in a footnote nobody reads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "REQUIRED_SECTIONS",
    "build_report",
    "render_markdown",
    "write_run_report",
    "COST_NOTE",
]

# Every top-level key the design requires. Presence is asserted at build time so
# a section cannot quietly go missing as the phases change.
REQUIRED_SECTIONS = (
    "identity",
    "ledger",
    "census",
    "escalations",
    "work_orders",
    "iterations",
    "parser_findings",
    "criteria",
    "determination",
    "lessons",
)

COST_NOTE = (
    "Costs are API-equivalent units reported by the `claude` CLI, metered "
    "against the owner's Claude Max subscription. They are a truthful measure of "
    "how much subscription usage this run consumed. They are not money spent."
)


def _phase_data(ctx, name: str, key: str) -> Any:
    try:
        return (ctx.phase_data(name) or {}).get(key)
    except Exception:  # noqa: BLE001 - the report must never be the thing that fails
        return None


def build_report(ctx, result, *, engine_version: str = "1") -> dict:
    """Assemble the Run Report from whatever the run produced.

    Deliberately tolerant. Each section is derived independently, so one phase
    that failed costs the report that section and nothing else.
    """
    ladder = _phase_data(ctx, "p2_ladder", "ladder")
    census = _phase_data(ctx, "p2_ladder", "census")
    adjudication = _phase_data(ctx, "p3_adjudication", "adjudication")
    synthesis = _phase_data(ctx, "p4_synthesis", "synthesis")
    determination = _phase_data(ctx, "p5_determination", "determination")
    brief = _phase_data(ctx, "p1_orientation", "brief")

    report: dict = {
        "identity": _identity(ctx, result, engine_version),
        "ledger": [row.to_dict() for row in (result.ledger or [])],
        "census": _census(census, ladder),
        "escalations": _escalations(ladder),
        "work_orders": _work_orders(synthesis, determination),
        "iterations": _iterations(determination),
        "parser_findings": _parser_findings(ladder),
        "criteria": _criteria(determination, brief),
        "determination": _determination(determination, result),
        "lessons": _lessons(ladder, adjudication, determination),
        "phases": [p.to_dict() for p in (result.phases or [])],
        "adjudication": adjudication.to_dict() if adjudication is not None else None,
        "synthesis": synthesis.to_dict() if synthesis is not None else None,
        "cost_note": COST_NOTE,
    }
    missing = [key for key in REQUIRED_SECTIONS if key not in report]
    if missing:  # pragma: no cover - guards a future edit, not a runtime path
        raise AssertionError(f"Run Report is missing required sections: {missing}")
    return report


def _identity(ctx, result, engine_version: str) -> dict:
    policy = ctx.policy
    return {
        "subject": (ctx.arch or {}).get("name") or ctx.root.name,
        "root": str(ctx.root),
        "commit": ctx.commit_sha,
        "snapshot_date": ctx.clock(),
        "analyzer_version": (ctx.arch or {}).get("analyzer_version"),
        "engine_version": engine_version,
        "policy": {
            "models": {
                key: spec.to_dict() if hasattr(spec, "to_dict") else str(spec)
                for key, spec in (policy.models or {}).items()
            },
            "iteration": {
                "min_rounds": policy.iteration.min_rounds,
                "max_rounds": policy.iteration.max_rounds,
            },
            "max_cost_usd": policy.max_cost_usd,
            "spot_check_fraction": policy.spot_check_fraction,
            "max_work_orders": policy.max_work_orders,
        },
        "totals": {
            "invocations": len(result.ledger or []),
            "cost_usd": round(result.total_cost_usd, 6),
            "ceiling_hit": result.ceiling_hit,
            "failed_phases": result.failed_phases,
        },
        "dry_run": ctx.dry_run,
    }


def _census(census, ladder) -> dict:
    if census is None and ladder is not None:
        census = ladder.census
    if census is None:
        return {
            "by_state": {},
            "items": [],
            "total": 0,
            "note": "the ladder produced no census; enrichment did not run",
        }
    data = census.to_dict()
    return {
        "by_state": data.get("by_state", {}),
        "items": data.get("items", []),
        "total": data.get("total", 0),
        "grounded": data.get("grounded", 0),
        "grounded_fraction": data.get("grounded_fraction", 0.0),
        "trigger_counts": data.get("trigger_counts", {}),
        "unresolved": [s.target_id for s in census.unresolved],
    }


def _escalations(ladder) -> list[dict]:
    """Every item that CLIMBED, the trigger, and what the higher rung did with it.

    Climbed means the item was in the escalate state at some point, or ended as
    an honest gap. Having a history entry is not the same thing: an item touched
    twice by a work order accumulates history while never having escalated, and
    listing it here would report ordinary re-enrichment as an escalation and
    inflate the number a reader uses to judge how much the bulk rung struggled.
    """
    if ladder is None:
        return []
    out = []
    for state in sorted(ladder.states.values(), key=lambda s: (s.target_kind, s.target_id)):
        climbed = any(":escalate" in entry for entry in state.history)
        if not climbed and state.state != "honest_gap":
            continue
        out.append({
            "target_kind": state.target_kind,
            "target_id": state.target_id,
            "climbed_from": state.history,
            "resolved_at": state.rung,
            "terminal": state.terminal,
            "triggers": state.triggers,
            "failed_questions": [f.to_dict() for f in state.failed],
        })
    return out


def _work_orders(synthesis, determination) -> list[dict]:
    """Every order issued, marked with whether it was actually executed.

    An order that was issued and never run is real information: it says the run
    knew what would help and did not do it, usually because the round budget or
    the cost ceiling ran out. Listing it indistinguishably from an executed order
    would make the report claim work that never happened.
    """
    orders: list[dict] = []
    if synthesis is not None:
        for order in synthesis.work_orders:
            data = order.to_dict()
            data["executed"] = bool((data.get("outcome") or {}).get("executed"))
            orders.append(data)
    if determination is not None:
        for data in determination.work_order_dicts():
            data["executed"] = bool((data.get("outcome") or {}).get("executed"))
            orders.append(data)
    return orders


def _iterations(determination) -> list[dict]:
    if determination is None:
        return []
    return [round_.to_dict() for round_ in determination.rounds]


def _parser_findings(ladder) -> list[dict]:
    """Every parser-first answer filed, as capability cards.

    The design calls these capability cards because that is what they are for:
    each one is a claim that deterministic processing could have gotten this
    right, and the point of collecting them is that the parser improves.
    """
    if ladder is None:
        return []
    # One card per distinct finding, naming every rung that raised it. Each rung
    # asks the parser-first question independently, so the same observation
    # arrives up to three times; listing it three times would inflate the count a
    # reader uses to judge how much the parser is actually missing.
    cards: dict[tuple, dict] = {}
    for finding in ladder.parser_findings:
        key = (finding.get("target_kind"), finding.get("target_id"), finding.get("finding"))
        card = cards.setdefault(key, {
            "target_kind": finding.get("target_kind"),
            "target_id": finding.get("target_id"),
            "finding": finding.get("finding"),
            "raised_at_rungs": [],
            "card": "how could deterministic processing have gotten this right?",
        })
        rung = finding.get("rung")
        if rung and rung not in card["raised_at_rungs"]:
            card["raised_at_rungs"].append(rung)
    return list(cards.values())


def _criteria(determination, brief) -> list[dict]:
    if determination is not None and determination.verdicts:
        return [v.to_dict() for v in determination.verdicts]
    # No determination: the criteria are still reported, unanswered, so a reader
    # sees what the run was supposed to be judged against and that nothing
    # judged it.
    if brief is None:
        return []
    return [
        {
            "criterion_id": c.id,
            "statement": c.statement,
            "verdict": "unknown",
            "evidence": [],
            "reasoning": "no determination ran, so this criterion was not answered",
        }
        for c in brief.criteria
    ]


def _determination(determination, result) -> dict:
    if determination is None:
        return {
            "verdict": "unknown",
            "reasoning": "P5 did not run or produced no verdict, so this run has "
            "no determination. That is not the same as 'not done': nothing "
            "judged it.",
            "rounds_run": 0,
        }
    return determination.verdict_dict(result)


def _lessons(ladder, adjudication, determination) -> list[dict]:
    """Scrub-safe abstractions for the licensed phone-home.

    Abstractions, never content: a lesson names a PATTERN the run hit, with
    counts, and never a path, an identifier or a line of the subject's code. The
    licence permits sending what we learned about the process, not what we
    learned about the subject.
    """
    lessons: list[dict] = []
    if ladder is not None and ladder.census.total:
        counts = ladder.census.trigger_counts()
        for trigger, count in counts.items():
            lessons.append({
                "kind": "escalation-trigger",
                "pattern": trigger,
                "count": count,
                "of_total": ladder.census.total,
            })
        if ladder.parser_findings:
            lessons.append({
                "kind": "parser-first",
                "pattern": "deterministic processing could have answered this",
                "count": len(ladder.parser_findings),
                "of_total": ladder.census.total,
            })
    if adjudication is not None:
        rate = adjudication.disagreement_rate()
        if rate is not None:
            lessons.append({
                "kind": "inter-tier-disagreement",
                "pattern": "claims adjudication would not stand behind",
                "rate": round(rate, 4),
                "sampled": adjudication.checked,
            })
    if determination is not None:
        for round_ in determination.rounds:
            if round_.forced and not round_.gained:
                lessons.append({
                    "kind": "forced-iteration",
                    "pattern": "a forced improvement round produced no measurable gain",
                    "round": round_.number,
                })
    return lessons


# --- rendering ----------------------------------------------------------------


def _table(rows: list[list[str]], headers: list[str]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return out


def render_markdown(report: dict) -> str:
    """Render the Run Report for a human. Same content, different audience."""
    identity = report.get("identity") or {}
    totals = identity.get("totals") or {}
    census = report.get("census") or {}
    determination = report.get("determination") or {}

    lines: list[str] = [
        f"# Enrichment Run Report: {identity.get('subject', 'unknown subject')}",
        "",
        f"Commit `{identity.get('commit') or 'unknown'}`, "
        f"snapshot {identity.get('snapshot_date', 'unknown')}, "
        f"engine version {identity.get('engine_version', 'unknown')}.",
        "",
        f"**Determination: {str(determination.get('verdict', 'unknown')).upper()}**",
        "",
        determination.get("reasoning") or "_No reasoning recorded._",
        "",
        "## What this run cost",
        "",
        f"{totals.get('invocations', 0)} model invocation(s), "
        f"${totals.get('cost_usd', 0.0):.4f} API-equivalent.",
        "",
        f"> {COST_NOTE}",
        "",
    ]
    if totals.get("ceiling_hit"):
        lines += [
            "**The run cost ceiling was reached.** Work below was left undone and "
            "is recorded as skipped, not as complete.",
            "",
        ]
    if totals.get("failed_phases"):
        lines += [
            "**Failed phases:** " + ", ".join(totals["failed_phases"]) + ". "
            "This report is written on partial output.",
            "",
        ]

    # Item census, the backbone of the determination.
    lines += ["## Item census", ""]
    by_state = census.get("by_state") or {}
    if by_state:
        lines += _table(
            [[state, str(count)] for state, count in sorted(by_state.items())],
            ["Terminal state", "Items"],
        )
        lines += [
            "",
            f"{census.get('grounded', 0)} of {census.get('total', 0)} items grounded "
            f"({census.get('grounded_fraction', 0.0):.1%}).",
        ]
        unresolved = census.get("unresolved") or []
        if unresolved:
            lines += [
                "",
                f"**{len(unresolved)} item(s) were still asking to climb when the "
                "ladder stopped.** They are not grounded and are not honest gaps: "
                "they are unfinished.",
            ]
    else:
        lines.append("_No census: the ladder did not produce contract states._")
    lines.append("")

    # Criteria, each with verdict and evidence.
    lines += ["## Criteria", ""]
    criteria = report.get("criteria") or []
    if criteria:
        lines += _table(
            [
                [
                    c.get("criterion_id", ""),
                    str(c.get("verdict", "unknown")).upper(),
                    (c.get("statement") or "").replace("|", "/"),
                    (c.get("reasoning") or "").replace("|", "/")[:200],
                ]
                for c in criteria
            ],
            ["Id", "Verdict", "Criterion", "Reasoning"],
        )
    else:
        lines.append("_No criteria were set, so nothing subject-specific was judged._")
    lines.append("")

    # Escalations.
    escalations = report.get("escalations") or []
    lines += ["## Escalations", ""]
    if escalations:
        lines += _table(
            [
                [
                    e.get("target_id", ""),
                    " -> ".join(e.get("climbed_from") or []) + f" -> {e.get('resolved_at')}",
                    ", ".join(e.get("triggers") or []),
                    e.get("terminal", ""),
                ]
                for e in escalations[:60]
            ],
            ["Target", "Climbed", "Triggers", "Terminal"],
        )
        if len(escalations) > 60:
            lines += ["", f"_{len(escalations) - 60} further escalation(s) in report.json._"]
    else:
        lines.append("_Nothing escalated._")
    lines.append("")

    # Iterations, with the honest no-gain record.
    iterations = report.get("iterations") or []
    lines += ["## Iterations", ""]
    if iterations:
        for round_ in iterations:
            kind = "forced" if round_.get("forced") else "determined"
            lines += [
                f"### Round {round_.get('number')} ({kind})",
                "",
                f"**Target:** {round_.get('target') or '_none recorded_'}",
                "",
                f"**Measured delta:** {json.dumps(round_.get('measured_delta') or {})}",
                "",
                f"**Perceived delta (judgment, not measurement):** "
                f"{round_.get('perceived_delta') or '_none recorded_'}",
                "",
            ]
            if not round_.get("gained"):
                lines += [
                    "This round produced **no measurable gain**. Recorded as such "
                    "rather than as work done.",
                    "",
                ]
    else:
        lines.append("_No improvement rounds ran._")
    lines.append("")

    # Work orders.
    orders = report.get("work_orders") or []
    lines += ["## Work orders", ""]
    if orders:
        lines += _table(
            [
                [
                    o.get("issued_by", ""),
                    (o.get("lens") or "").replace("|", "/")[:80],
                    (o.get("expected_effect") or "").replace("|", "/")[:60],
                    str(len(o.get("scope") or [])),
                    "yes" if o.get("executed") else "no",
                    "yes" if ((o.get("outcome") or {}) or {}).get("changed_anything")
                    else "no",
                ]
                for o in orders
            ],
            ["Issued by", "Lens", "Expected effect", "Scope", "Executed",
             "Changed anything"],
        )
    else:
        lines.append("_No work orders were issued._")
    lines.append("")

    # Parser findings.
    findings = report.get("parser_findings") or []
    lines += ["## Parser-first findings", ""]
    if findings:
        lines.append(
            f"{len(findings)} observation(s) that deterministic processing could "
            "have answered without a model. Each is a capability card."
        )
        lines.append("")
        for finding in findings[:40]:
            lines.append(f"- `{finding.get('target_id')}`: {finding.get('finding')}")
        if len(findings) > 40:
            lines.append(f"- _{len(findings) - 40} more in report.json._")
    else:
        lines.append("_No parser-first findings were raised._")
    lines.append("")

    # Work ledger.
    ledger = report.get("ledger") or []
    lines += ["## Work ledger", ""]
    if ledger:
        lines += _table(
            [
                [
                    row.get("phase", ""),
                    row.get("rung") or "",
                    row.get("model", ""),
                    str(row.get("targets", 0)),
                    str(row.get("tokens_in", 0)),
                    str(row.get("tokens_out", 0)),
                    f"{row.get('cost_usd', 0.0):.4f}",
                    f"{row.get('wall_seconds', 0.0):.1f}",
                    str(row.get("retries", 0)),
                ]
                for row in ledger
            ],
            ["Phase", "Rung", "Binding", "Targets", "Tokens in", "Tokens out",
             "Cost", "Wall s", "Retries"],
        )
    else:
        lines.append("_Nothing was invoked._")
    lines.append("")

    # Lessons.
    lessons = report.get("lessons") or []
    lines += ["## Lessons", ""]
    if lessons:
        lines.append(
            "Scrub-safe abstractions only: patterns and counts, never the "
            "subject's paths, identifiers or code."
        )
        lines.append("")
        for lesson in lessons:
            detail = ", ".join(
                f"{k}={v}" for k, v in sorted(lesson.items()) if k not in ("kind", "pattern")
            )
            lines.append(f"- **{lesson.get('kind')}**: {lesson.get('pattern')} ({detail})")
    else:
        lines.append("_No lessons recorded._")
    lines.append("")

    return "\n".join(lines) + "\n"


def write_run_report(
    ctx, result, *, run_dir: Optional[Path] = None, engine_version: str = "1"
) -> Optional[dict]:
    """Build and write report.json and REPORT.md. Never raises.

    Called by the top-level runner rather than by P5, so the report still gets
    written when P5 itself is the phase that failed. A run with no report is a
    run nobody can audit, and that is the one outcome this must not produce.
    """
    try:
        report = build_report(ctx, result, engine_version=engine_version)
    except Exception as exc:  # noqa: BLE001 - a report failure must degrade
        from ..contracts import gap_from_exception

        reason = gap_from_exception("enrich.runreport", "enrich", exc).reason
        ctx.notes.append(f"Run Report could not be assembled: {reason}")
        return None

    directory = Path(run_dir) if run_dir is not None else Path(ctx.run_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "report.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        (directory / "REPORT.md").write_text(render_markdown(report), encoding="utf-8")
    except OSError as exc:
        ctx.notes.append(f"Run Report could not be written to {directory}: {exc}")
    return report
