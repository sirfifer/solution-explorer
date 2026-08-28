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

from .contract import TRIGGERS, trigger_class

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
    "run_analysis",
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
        "identity_flags": _identity_flags(ladder),
        "criteria": _criteria(determination, brief),
        "determination": _determination(determination, result),
        "run_analysis": _run_analysis(determination),
        "lessons": _lessons(ladder, adjudication, determination),
        "phases": [p.to_dict() for p in (result.phases or [])],
        "adjudication": adjudication.to_dict() if adjudication is not None else None,
        "synthesis": synthesis.to_dict() if synthesis is not None else None,
        "accounting": _accounting(ctx, result),
        "escalation_economics": _escalation_economics(ctx, result),
        "cost_note": COST_NOTE,
        "quality": {
            "status": result.quality_status,
            "complete": result.quality_ok,
            "issues": list(result.quality_issues),
        },
        "audit": result.audit,
    }
    missing = [key for key in REQUIRED_SECTIONS if key not in report]
    if missing:  # pragma: no cover - guards a future edit, not a runtime path
        raise AssertionError(f"Run Report is missing required sections: {missing}")
    return report


def _escalation_economics(ctx, result) -> dict:
    """What the ladder spent climbing, and what would stop it climbing next time.

    An escalation tree is only worth having if every climb teaches something. The
    tree's value is not that a harder model eventually answers; it is that the
    CHEAPEST rung is handed context good enough to succeed, and each escalation
    is evidence that some particular context was missing.

    So this section asks, per trigger, the question the owner wants asked every
    time: how could sonnet have succeeded here? It does not try to answer it
    mid-run. It records the shape of the failure and what it cost, so the answer
    can be worked out deliberately afterwards.

    Three classes of opportunity, because they have completely different fixes:

      deterministic  the tier declared the question was one the PARSER should
                     have answered (parser_first). This is the best kind of
                     finding: moving it costs a model call nothing and makes the
                     input better for everything downstream, so the enrichment
                     has more to work with rather than less.
      context        the tier had the facts and still could not ground, cite or
                     reconcile them. The prompt, not the model, is the suspect.
      reasoning      genuine difficulty. Escalation is doing its job.

    The cost side matters more than a flat count because Sonnet and Opus draw
    from SEPARATE weekly buckets on a Max plan. Work moved down the ladder does
    not just cost less, it stops consuming the scarcer bucket, so an escalation
    avoided is worth more than its dollar figure suggests.
    """
    ladder = _phase_data(ctx, "p2_ladder", "ladder")
    if ladder is None:
        return {"climbed": 0, "by_trigger": [], "deterministic_opportunities": [], "note":
                "the ladder did not run, so there is nothing to learn from it"}

    transitions = list(getattr(ladder, "transitions", None) or [])
    climbed_keys = {
        (str(event.get("target_kind")), str(event.get("target_id")))
        for event in transitions
        if event.get("state") in ("escalate", "honest_gap")
    }
    # Backward compatibility for reports loaded from runs created before the
    # append-only transition ledger existed.
    climbed_states = [
        st for st in ladder.states.values()
        if any(":escalate" in entry for entry in st.history) or st.state == "honest_gap"
    ]
    if not climbed_keys:
        climbed_keys = {(st.target_kind, st.target_id) for st in climbed_states}

    by_trigger: dict[str, dict] = {}
    parser_first_targets: dict[str, set[tuple[str, str]]] = {}
    trigger_targets: dict[str, set[tuple[str, str]]] = {}
    attempts = transitions or [
        {
            "target_kind": st.target_kind,
            "target_id": st.target_id,
            "state": st.state,
            "failed": [failed.to_dict() for failed in st.failed],
            "parser_first": list(st.parser_first),
        }
        for st in climbed_states
    ]
    for attempt in attempts:
        if attempt.get("state") not in ("escalate", "honest_gap"):
            continue
        target_key = (str(attempt.get("target_kind")), str(attempt.get("target_id")))
        for failed in attempt.get("failed") or []:
            trig = str(failed.get("trigger") or "unknown")
            bucket = by_trigger.setdefault(trig, {
                "trigger": trig,
                "meaning": TRIGGERS.get(trig, "unrecorded trigger"),
                "items": 0,
                "questions": {},
                "_classes": {"context": 0, "reasoning": 0},
                "_lacked_used": 0,
                "_fallback_used": 0,
            })
            trigger_targets.setdefault(trig, set()).add(target_key)
            question = str(failed.get("question") or "unknown")
            bucket["questions"][question] = (
                bucket["questions"].get(question, 0) + 1
            )
            # The recorded lacked self-report is the primary class basis; the
            # trigger map is the fallback for records without one. A tier
            # saying "I lacked a fact" is a context failure whatever trigger
            # fired, and "judgment" is reasoning.
            lacked = failed.get("lacked")
            if lacked == "fact":
                bucket["_classes"]["context"] += 1
                bucket["_lacked_used"] += 1
            elif lacked == "judgment":
                bucket["_classes"]["reasoning"] += 1
                bucket["_lacked_used"] += 1
            else:
                fallback = trigger_class([trig])
                bucket["_classes"][
                    "context" if fallback == "context" else "reasoning"
                ] += 1
                bucket["_fallback_used"] += 1
        for question in attempt.get("parser_first") or []:
            parser_first_targets.setdefault(str(question), set()).add(target_key)
    for trigger, targets in trigger_targets.items():
        by_trigger[trigger]["items"] = len(targets)

    # What the climbing itself consumed. Ledger rows carry their rung, so the
    # rungs above the bulk tier are exactly the cost of escalation.
    bulk_rung = "2a"
    escalated_cost = 0.0
    escalated_tokens = 0
    for row in (result.ledger or []):
        if row.rung and row.rung != bulk_rung and row.phase == "p2_ladder":
            escalated_cost += float(row.cost_usd or 0.0)
            escalated_tokens += (row.tokens_in or 0) + (row.tokens_out or 0)

    triggers = sorted(by_trigger.values(), key=lambda b: b["items"], reverse=True)
    for bucket in triggers:
        bucket["questions"] = sorted(
            ({"question": q, "items": n} for q, n in bucket["questions"].items()),
            key=lambda r: r["items"], reverse=True,
        )
        # One vocabulary for router and report; a local copy of this map is
        # how the three-role drift happens (contract.py owns it). The class
        # is the majority of per-record classifications, lacked-first with
        # trigger fallback, and the basis says how much of each was used.
        classes = bucket.pop("_classes")
        lacked_used = bucket.pop("_lacked_used")
        fallback_used = bucket.pop("_fallback_used")
        if classes["context"] > classes["reasoning"]:
            bucket["class"] = "context"
        elif classes["reasoning"] > classes["context"]:
            bucket["class"] = "reasoning"
        else:
            bucket["class"] = trigger_class([bucket["trigger"]])
        bucket["class_basis"] = f"lacked:{lacked_used}/trigger:{fallback_used}"

    return {
        "climbed": len(climbed_keys),
        "escalated_cost_usd": round(escalated_cost, 6),
        "escalated_tokens": escalated_tokens,
        "cost_per_climb_usd": (
            round(escalated_cost / len(climbed_keys), 6) if climbed_keys else 0.0
        ),
        "by_trigger": triggers,
        "deterministic_opportunities": sorted(
            (
                {"question": question, "items": len(targets)}
                for question, targets in parser_first_targets.items()
            ),
            key=lambda r: r["items"], reverse=True,
        ),
    }


def _accounting(ctx, result) -> dict:
    """Who did how much of the work, and what that costs the account.

    The Run Report already said what the run PRODUCED. It never said what the run
    CONSUMED, beyond one API-equivalent dollar figure that is not what a Claude
    subscription is actually metered in. That number cannot answer the question
    that governs a week: if this runs four times, is Tuesday gone or is the week
    gone.

    So this section splits the work by model. It matters because the rungs bind
    different models and their rates differ tenfold, and because on Max plans
    Sonnet and Opus draw from SEPARATE weekly buckets: a run that is heavy on
    Opus and a run that is heavy on Sonnet exhaust different things, and a single
    total hides which.

    Everything here is measured from the ledger, which records one row per
    logical invocation with its model, targets, tokens and wall time. Nothing is
    estimated.
    """
    rows = list(result.ledger or [])
    by_model: dict[str, dict] = {}
    for row in rows:
        bucket = by_model.setdefault(row.model or "unknown", {
            "model": row.model or "unknown",
            "invocations": 0,
            "targets": 0,
            "tokens_in": 0,
            "tokens_cached": 0,
            "tokens_cache_write": 0,
            "tokens_out": 0,
            "response_bytes": 0,
            "output_budget_violations": 0,
            "cost_usd": 0.0,
            "wall_seconds": 0.0,
            "retries": 0,
            "failures": 0,
            "phases": set(),
        })
        bucket["invocations"] += 1
        bucket["targets"] += row.targets or 0
        bucket["tokens_in"] += row.tokens_in or 0
        bucket["tokens_cached"] += row.tokens_cached or 0
        bucket["tokens_cache_write"] += row.tokens_cache_write or 0
        bucket["tokens_out"] += row.tokens_out or 0
        bucket["response_bytes"] += row.response_bytes or 0
        if row.output_budget_ok is False:
            bucket["output_budget_violations"] += 1
        bucket["cost_usd"] += float(row.cost_usd or 0.0)
        bucket["wall_seconds"] += float(row.wall_seconds or 0.0)
        bucket["retries"] += row.retries or 0
        if not row.ok:
            bucket["failures"] += 1
        if row.rung:
            bucket["phases"].add(f"{row.phase}:{row.rung}")
        else:
            bucket["phases"].add(row.phase)

    models = []
    for bucket in by_model.values():
        bucket["phases"] = sorted(bucket["phases"])
        bucket["tokens_total"] = (
            bucket["tokens_in"] + bucket["tokens_cached"] + bucket["tokens_out"]
        )
        bucket["cost_usd"] = round(bucket["cost_usd"], 6)
        bucket["wall_seconds"] = round(bucket["wall_seconds"], 1)
        models.append(bucket)
    models.sort(key=lambda b: b["tokens_total"], reverse=True)

    grand_tokens = sum(b["tokens_total"] for b in models)
    grand_cost = sum(b["cost_usd"] for b in models)
    for bucket in models:
        bucket["token_share"] = (
            round(bucket["tokens_total"] / grand_tokens, 4) if grand_tokens else 0.0
        )
        bucket["cost_share"] = (
            round(bucket["cost_usd"] / grand_cost, 4) if grand_cost else 0.0
        )

    return {
        "by_model": models,
        "totals": {
            "invocations": len(rows),
            "tokens_total": grand_tokens,
            "tokens_in": sum(b["tokens_in"] for b in models),
            "tokens_cached": sum(b["tokens_cached"] for b in models),
            "tokens_cache_write": sum(b["tokens_cache_write"] for b in models),
            "tokens_out": sum(b["tokens_out"] for b in models),
            "response_bytes": sum(b["response_bytes"] for b in models),
            "output_budget_violations": sum(
                b["output_budget_violations"] for b in models
            ),
            "cost_usd": round(grand_cost, 6),
            "wall_seconds": round(sum(b["wall_seconds"] for b in models), 1),
        },
        "output_efficiency": {
            "billed_output_tokens": sum(b["tokens_out"] for b in models),
            "delivered_response_bytes": sum(b["response_bytes"] for b in models),
            "compact_budgeted_calls": sum(
                1 for row in rows if row.output_budget_ok is not None
            ),
            "compact_budget_violations": sum(
                1 for row in rows if row.output_budget_ok is False
            ),
            "note": (
                "Delivered JSON is schema- and byte-bounded. Billed output also "
                "includes hidden reasoning; the Claude CLI exposes no per-call "
                "max_tokens below its provider ceiling, so billed-token reduction "
                "is measured and gated against the baseline, not falsely called "
                "a transport guarantee."
            ),
        },
        "cache_efficiency": {
            "writes": sum(b["tokens_cache_write"] for b in models),
            "reads": sum(b["tokens_cached"] for b in models),
            "read_write_ratio": round(
                sum(b["tokens_cached"] for b in models)
                / max(1, sum(b["tokens_cache_write"] for b in models)), 4
            ),
            "prefix_hashes": sorted({
                row.prefix_hash for row in rows if row.prefix_hash
            }),
            "mechanism_verified": True,
            "budgeted_as_saving": any(b["tokens_cached"] for b in models),
            "note": (
                "The F-9 live probe verified that the stable appended prefix is "
                "cache-read only when dynamic system sections are excluded. "
                "This report books no hypothetical saving: only cache reads "
                "measured in this run count."
            ),
        },
        # Filled in by hand after an isolated run. There is no API that reports
        # Claude subscription usage (Claude Code exposes it only through /usage
        # and /status in a live session), so the only hard measurement available
        # is the difference between two readings taken either side of a run that
        # had the account to itself.
        "account_delta": None,
        "calibration_note": (
            "To turn this into a share of the weekly allowance: take a /usage "
            "reading immediately before the run, keep hands off the account for "
            "its duration, take a second reading immediately after, and record "
            "the difference with scripts/usage-budget.py calibrate. Nothing else "
            "measures a subscription; the dollar figures here are API-equivalent "
            "prices for work that was never billed at API rates."
        ),
    }


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
            "pause_at_cost_usd": policy.pause_at_cost_usd,
            "spot_check_fraction": policy.spot_check_fraction,
            "max_work_orders": policy.max_work_orders,
        },
        "totals": {
            "invocations": len(result.ledger or []),
            "cost_usd": round(result.total_cost_usd, 6),
            "cost_ceiling_usd": result.cost_ceiling_usd,
            "cost_ceiling_exceeded": (
                result.cost_ceiling_usd is not None
                and result.total_cost_usd > result.cost_ceiling_usd + 1e-9
            ),
            "ceiling_hit": result.ceiling_hit,
            "failed_phases": result.failed_phases,
        },
        "dry_run": ctx.dry_run,
    }


def _census(census, ladder) -> dict:
    if ladder is not None:
        # Work orders mutate the shared ladder after P2's original PhaseResult
        # was recorded. Rebuild from current states so the published census
        # cannot disagree with the determination that just judged it.
        from .contract import build_census

        census = build_census(list(ladder.states.values()))
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


def _identity_flags(ladder) -> list[dict]:
    """Every identity disagreement a tier raised against a parser-owned value.

    Identity restatement is dead by contract: a tier emits identity ONLY when
    it disagrees with the parser (the UIKit-versus-SwiftUI catch, the
    misnamed nested view). Those catches are the enhancement's most
    transferable output, and until this section existed they had no reader:
    a channel nobody reads is a channel that dies.
    """
    if ladder is None:
        return []
    flags = []
    for (target_kind, target_id), payload in sorted(ladder.payloads.items()):
        answers = ((payload or {}).get("contract") or {}).get("answers") or {}
        for question, answer in sorted(answers.items()):
            if not str(question).startswith("identity.") or not isinstance(answer, dict):
                continue
            flags.append({
                "target_kind": target_kind,
                "target_id": target_id,
                "field": str(question).split(".", 1)[1],
                "claim": answer.get("claim"),
                "reason": answer.get("reason"),
                "evidence_count": len(answer.get("evidence") or []),
                "card": "is the parser wrong here, and can extraction learn the rule?",
            })
    return flags


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


def _run_analysis(determination) -> dict:
    """Fable's evidence-bound interpretation of measured run operations.

    Accounting and the raw ledger remain deterministic. This section records
    what the terminal model concluded from their compact pre-exit digest, so the
    process can improve without asking the model to regenerate the measurements.
    """
    if determination is None:
        return {
            "status": "unavailable",
            "summary": "P5 did not run, so no model analyzed the run logistics.",
            "deterministic_transfers": [],
            "improvements": [],
            "watch_next_run": [],
        }
    analysis = getattr(determination, "run_analysis", None)
    if isinstance(analysis, dict) and analysis:
        return dict(analysis)
    return {
        "status": "missing",
        "summary": "P5 returned no run analysis; the deterministic accounting remains available.",
        "deterministic_transfers": [],
        "improvements": [],
        "watch_next_run": [],
    }


def _lessons(ladder, adjudication, determination) -> list[dict]:
    """Scrub-safe abstractions for the licensed phone-home.

    Abstractions, never content: a lesson names a PATTERN the run hit, with
    counts, and never a path, an identifier or a line of the subject's code. The
    licence permits sending what we learned about the process, not what we
    learned about the subject.
    """
    lessons: list[dict] = []
    if ladder is not None and ladder.census.total:
        transitions = list(getattr(ladder, "transitions", None) or [])
        trigger_targets: dict[str, set[tuple[str, str]]] = {}
        for event in transitions:
            if event.get("state") not in ("escalate", "honest_gap"):
                continue
            target = (
                str(event.get("target_kind") or ""),
                str(event.get("target_id") or ""),
            )
            for failure in event.get("failed") or []:
                if not isinstance(failure, dict):
                    continue
                trigger = str(failure.get("trigger") or "unknown")
                trigger_targets.setdefault(trigger, set()).add(target)
        counts = (
            {trigger: len(targets) for trigger, targets in trigger_targets.items()}
            or ladder.census.trigger_counts()
        )
        for trigger, count in sorted(counts.items()):
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


def _escalation_economics_section(report: dict) -> list:
    """The improvement section: every climb is a question about the rung below.

    Written to be acted on rather than admired, so it leads with the cheapest
    class of fix (something the parser could have answered outright) and ends
    with the one that is nobody's fault.
    """
    econ = report.get("escalation_economics") or {}
    if econ.get("note"):
        return ["## What the climbing cost", "", f"_{econ['note']}._", ""]
    climbed = econ.get("climbed", 0)
    if not climbed:
        return [
            "## What the climbing cost",
            "",
            "Nothing escalated. The bulk rung answered everything it was asked, "
            "which is the cheapest possible outcome and worth noticing.",
            "",
        ]

    lines = [
        "## What the climbing cost",
        "",
        f"{climbed} item(s) climbed past the bulk rung, consuming "
        f"{econ.get('escalated_tokens', 0):,} tokens and "
        f"${econ.get('escalated_cost_usd', 0.0):.2f} API-equivalent above it, "
        f"roughly ${econ.get('cost_per_climb_usd', 0.0):.3f} per climb.",
        "",
        "On a Max plan Sonnet and Opus draw from **separate** weekly buckets, so "
        "an escalation avoided is worth more than its price: it stops consuming "
        "the scarcer of the two.",
        "",
    ]

    deterministic = econ.get("deterministic_opportunities") or []
    if deterministic:
        lines += [
            "### Questions the parser should have answered",
            "",
            "The best kind of finding here. These are not model problems: the tier "
            "itself declared that a deterministic fact would have settled the "
            "question. Moving one of these costs no model call at all, and it "
            "improves the input to every later stage rather than only this one.",
            "",
        ]
        lines += _table(
            [[row["question"], str(row["items"])] for row in deterministic[:15]],
            ["Question a parser could settle", "Items"],
        )
        lines += [""]

    lines += [
        "### Why the rest climbed",
        "",
        "For each trigger, the question worth asking before the next run is not "
        "\"was the harder model right\" but **what would the cheaper rung have "
        "needed to get this right**. That is a context question far more often "
        "than it is a capability question.",
        "",
    ]

    lines += _table(
        [
            [
                b["trigger"],
                b["meaning"],
                b["class"],
                str(b["items"]),
                (b["questions"][0]["question"] if b.get("questions") else ""),
            ]
            for b in (econ.get("by_trigger") or [])
        ],
        ["Trigger", "Meaning", "Suspect", "Items", "Most frequent question"],
    )
    lines += [
        "",
        "`context` means the tier had the facts and still could not ground, cite "
        "or reconcile them, so the prompt is the suspect before the model is. "
        "`reasoning` means the difficulty looks real and escalation did its job.",
        "",
    ]
    return lines


def _accounting_section(report: dict) -> list:
    """Who did the work, in the terms a subscription is actually spent in.

    Written to be read by a person deciding whether to run this again this week,
    so it leads with the split by model rather than with a total. The total is
    the least useful number on the page: Sonnet and Opus come out of different
    weekly buckets on a Max plan, so two runs with identical totals can leave the
    account in very different states.
    """
    acct = report.get("accounting") or {}
    models = acct.get("by_model") or []
    totals = acct.get("totals") or {}
    if not models:
        return [
            "## Who did the work",
            "",
            "_No invocations were recorded, so there is nothing to account for._",
            "",
        ]

    lines = ["## Who did the work", ""]
    lines += _table(
        [
            [
                m["model"],
                str(m["invocations"]),
                f"{m['targets']:,}",
                f"{m['tokens_in']:,}",
                f"{m['tokens_cached']:,}",
                f"{m['tokens_out']:,}",
                f"{m['token_share']:.0%}",
                f"{m['wall_seconds'] / 60:.1f}m",
                f"${m['cost_usd']:.2f}",
            ]
            for m in models
        ],
        ["Model", "Calls", "Targets", "Fresh in", "Cached in", "Out",
         "Share", "Wall", "API-equiv"],
    )
    lines += [
        "",
        f"{totals.get('invocations', 0)} invocation(s) moved "
        f"{totals.get('tokens_total', 0):,} tokens in "
        f"{totals.get('wall_seconds', 0.0) / 60:.1f} minutes of model time.",
        "",
    ]

    output = acct.get("output_efficiency") or {}
    cache = acct.get("cache_efficiency") or {}
    lines += [
        f"Delivered response payload: {output.get('delivered_response_bytes', 0):,} "
        "UTF-8 bytes total. "
        f"{output.get('compact_budgeted_calls', 0)} call(s) exercised the compact "
        f"transport gate, with {output.get('compact_budget_violations', 0)} "
        "violation(s).",
        "",
        f"Prompt cache: {cache.get('reads', 0):,} tokens read and "
        f"{cache.get('writes', 0):,} written "
        f"(read/write {cache.get('read_write_ratio', 0.0):.2f}). "
        "Only measured reads are counted as savings.",
        "",
        output.get("note", ""),
        "",
    ]

    heaviest = models[0]
    lines += [
        f"**{heaviest['model']}** did the most of it, "
        f"{heaviest['token_share']:.0%} of all tokens across "
        f"{', '.join(heaviest['phases'])}.",
        "",
    ]

    failed = [m for m in models if m.get("failures")]
    if failed:
        lines += [
            "Failed invocations by model: "
            + ", ".join(f"{m['model']} ({m['failures']})" for m in failed)
            + ". These consumed allowance and produced nothing.",
            "",
        ]
    retried = [m for m in models if m.get("retries")]
    if retried:
        lines += [
            "Transport retries: "
            + ", ".join(f"{m['model']} ({m['retries']})" for m in retried)
            + ". Retries are paid for twice and are worth watching if the count grows.",
            "",
        ]

    lines += [
        "### What this costs the account",
        "",
        "The dollar column above is an API-equivalent price. No card was charged: "
        "this work was metered against a Claude subscription, and a subscription "
        "is an allowance that refills weekly, not a balance. On Max plans Sonnet "
        "and Opus draw from **separate** weekly buckets, so the split above "
        "matters more than the total.",
        "",
    ]
    delta = acct.get("account_delta")
    if delta:
        lines += [
            f"Measured against the account: {delta}",
            "",
        ]
    else:
        lines += [
            "_This run has not been measured against the account._ "
            + str(acct.get("calibration_note") or ""),
            "",
        ]
    return lines


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
    if totals.get("cost_ceiling_exceeded"):
        lines += [
            "**The provider exceeded the configured run allowance.** Measured "
            "cost is above the requested ceiling; this run is not publishable.",
            "",
        ]
    if totals.get("failed_phases"):
        lines += [
            "**Failed phases:** " + ", ".join(totals["failed_phases"]) + ". "
            "This report is written on partial output.",
            "",
        ]

    lines += _accounting_section(report)
    lines += _escalation_economics_section(report)

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

    # Identity flags: places a tier disagreed with a parser-owned value.
    flags = report.get("identity_flags") or []
    lines += ["## Identity flags", ""]
    if flags:
        lines.append(
            f"{len(flags)} disagreement(s) with parser-owned identity values. "
            "Each is a candidate extraction fix; a flag with evidence "
            "outranks the parser until extraction learns the rule."
        )
        lines.append("")
        for flag in flags[:40]:
            reason = flag.get("reason") or ""
            lines.append(
                f"- `{flag.get('target_id')}` {flag.get('field')}: "
                f"{flag.get('claim')}" + (f" ({reason})" if reason else "")
            )
        if len(flags) > 40:
            lines.append(f"- _{len(flags) - 40} more in report.json._")
    else:
        lines.append(
            "_No identity flags: the tiers found no parser-owned value worth "
            "disputing._"
        )
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

    # Fable's exit analysis. Measurements stay in accounting/the ledger; this
    # section explains what they imply and what should be validated next.
    analysis = report.get("run_analysis") or {}
    lines += ["## Run analysis", ""]
    lines.append(f"**Status:** {analysis.get('status') or 'missing'}")
    lines.append("")
    lines.append(analysis.get("summary") or "_No analysis summary was returned._")
    lines.append("")
    for title, key in (
        ("Deterministic-transfer candidates", "deterministic_transfers"),
        ("Process improvements", "improvements"),
        ("Watch on the next run", "watch_next_run"),
    ):
        lines += [f"### {title}", ""]
        items = analysis.get(key) or []
        if not items:
            lines.append("_None established._")
            lines.append("")
            continue
        for item in items:
            if isinstance(item, dict):
                detail = "; ".join(
                    f"{name}: {value}" for name, value in item.items() if value
                )
            else:
                detail = str(item)
            lines.append(f"- {detail}")
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
