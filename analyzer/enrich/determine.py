"""P5, determination: is this good enough, or is there room it knows how to close?

``ENRICHMENT-ENGINE.md`` section 3. The only loop in the system, and the only way
a run exits.

It works from the item census, the verdict census, the criteria, the story and
the lenses. Not from a re-walk of every component: re-reading 570 components to
decide whether 570 components were read well is both the expensive way and the
unreliable way to answer the question.

Three rules give this phase its shape.

**"Not done" is only legal with work orders designed to change the result.**
"Look again" is not an instruction, it is a wish. An order that cannot name which
instrument would move is rejected, and a determination of "not done" with no
executable order is downgraded to a done-with-reservations verdict that says so.
Otherwise a run could refuse to finish forever while doing nothing.

**Forced iteration, early.** On the first Wave 1 subjects the determination must
run at least one improvement round even when it believes the map is done, and
that round has to carry a genuine reasoned target rather than a checkbox. A
forced round with no target is not run, and the report says why. "No measurable
gain from the forced round" is itself the finding that earns dialling the policy
back later.

**Measured and perceived deltas are different things and are labelled as such.**
The measured delta is the census moving. The perceived delta is a judgment, is
recorded as a judgment, and never stands in for the measurement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from .engine import _parse_json_object
from .orientation import (
    Criterion,
    CriterionVerdict,
    _collect_readme,
    universal_criteria,
)
from .pipeline import PhaseResult, RunContext
from .prompts import _cached_prompt
from .workorder import WorkOrder, WorkOrderOutcome, make_descender, parse_work_orders

__all__ = [
    "DeterminationOutcome",
    "DeterminationPhase",
    "IterationRound",
    "build_determination_prompt",
    "evaluate_universal",
]

VERDICTS = ("done", "done-with-reservations", "not-done", "unknown")


@dataclass
class IterationRound:
    """One improvement round, forced or determined."""

    number: int
    forced: bool
    target: str = ""
    orders: list[WorkOrder] = field(default_factory=list)
    outcomes: list[WorkOrderOutcome] = field(default_factory=list)
    measured_delta: dict = field(default_factory=dict)
    perceived_delta: str = ""
    ran: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def gained(self) -> bool:
        """Did any recorded state, tier, or independent quality measure improve?"""
        if (
            self.measured_delta.get("changed")
            or self.measured_delta.get("rung_moves")
            or self.measured_delta.get("payload_changes")
        ):
            return True
        before = self.measured_delta.get("adjudication_disagreement_before")
        after = self.measured_delta.get("adjudication_disagreement_after")
        return (
            isinstance(before, (int, float))
            and isinstance(after, (int, float))
            and after < before
        )

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "forced": self.forced,
            "target": self.target,
            "ran": self.ran,
            "work_orders": [o.to_dict() for o in self.outcomes],
            "measured_delta": dict(self.measured_delta),
            "perceived_delta": self.perceived_delta,
            "perceived_delta_is_judgment": True,
            "gained": self.gained,
            "notes": list(self.notes),
        }


@dataclass
class DeterminationOutcome:
    verdict: str = "unknown"
    reasoning: str = ""
    verdicts: list[CriterionVerdict] = field(default_factory=list)
    rounds: list[IterationRound] = field(default_factory=list)
    pending_orders: list[WorkOrder] = field(default_factory=list)
    rejected_orders: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    run_analysis: dict = field(default_factory=dict)

    def work_order_dicts(self) -> list[dict]:
        out = []
        for round_ in self.rounds:
            out.extend(o.to_dict() for o in round_.outcomes)
        out.extend(o.to_dict() for o in self.pending_orders)
        return out

    def verdict_dict(self, result=None) -> dict:
        return {
            "verdict": self.verdict,
            "reasoning": self.reasoning,
            "rounds_run": sum(1 for r in self.rounds if r.ran),
            "rounds_recorded": len(self.rounds),
            "criteria_met": sum(1 for v in self.verdicts if v.verdict == "met"),
            "criteria_unmet": sum(1 for v in self.verdicts if v.verdict == "unmet"),
            "criteria_unknown": sum(1 for v in self.verdicts if v.verdict == "unknown"),
            "notes": list(self.notes),
        }


# --- universal criteria, answered mechanically --------------------------------


def evaluate_universal(
    criterion: Criterion, *, census: Any, adjudication: Any
) -> Optional[CriterionVerdict]:
    """Answer a universal gate from the census and the verdicts, with no model.

    These three are checkable by code, so they are checked by code. Asking a
    model whether every item reached a terminal state, when a counter can answer
    it exactly, spends budget to get a less reliable answer.
    """
    verdict = CriterionVerdict(criterion_id=criterion.id, statement=criterion.statement)
    if census is None:
        verdict.verdict = "unknown"
        verdict.reasoning = "no census was produced, so this gate cannot be answered"
        return verdict

    if criterion.id == "u1":
        unresolved = census.unresolved
        verdict.verdict = "met" if not unresolved else "unmet"
        verdict.evidence = [f"{len(unresolved)} item(s) still in the escalate state"]
        verdict.reasoning = (
            "every enrichment target reached a terminal contract state"
            if not unresolved
            else f"{len(unresolved)} item(s) were still asking to climb when the "
            "ladder stopped, which is unfinished work rather than a gap"
        )
        return verdict

    if criterion.id == "u2":
        fraction = census.grounded_fraction()
        rate = adjudication.disagreement_rate() if adjudication is not None else None
        verdict.evidence = [f"grounded fraction {fraction:.1%}"]
        if rate is None:
            verdict.verdict = "unknown"
            verdict.reasoning = (
                f"{fraction:.1%} of items grounded, but nothing was spot-checked, "
                "so whether the evidence supports the claims is unmeasured. That is "
                "not the same as agreement"
            )
            return verdict
        verdict.evidence.append(f"adjudication disagreement rate {rate:.1%}")
        verdict.verdict = "met" if (fraction >= 0.8 and rate <= 0.2) else "unmet"
        verdict.reasoning = (
            f"{fraction:.1%} of items grounded; adjudication would not stand behind "
            f"{rate:.1%} of the claims it sampled"
        )
        return verdict

    if criterion.id == "u3":
        gaps = census.honest_gaps
        generic_reason = "no answer was produced for a required question"
        without_reason = [
            (s.target_id, f.question) for s in gaps for f in s.failed
            if not (f.note or "").strip()
            or (f.note or "").strip().lower() == generic_reason
        ]
        verdict.evidence = [f"{len(gaps)} honest gap(s)"]
        verdict.verdict = "met" if not without_reason else "unmet"
        verdict.reasoning = (
            f"all {len(gaps)} honest gap(s) carry a reason a reader can act on"
            if not without_reason
            else f"{len(without_reason)} honest-gap question(s) carry no specific "
            "reason, which is silence dressed as a disclosure"
        )
        return verdict

    return None


# --- the prompt ----------------------------------------------------------------


_DETERMINATION_CONTRACT = """\
Return ONLY a single JSON object, no prose and no fences:

{
  "verdict": "done" | "not-done",
  "reasoning": "your full reasoning, several sentences. Say what this map now \
supports a reader doing, and what it does not.",
  "criteria": [
    {"criterion_id": "s1", "verdict": "met" | "unmet" | "unknown",
     "evidence": ["what in the census or the verdicts shows this"],
     "reasoning": "one or two sentences"}
  ],
  "work_orders": [
    {"scope": ["component ids"], "lens": "what to look at",
     "criteria": "what would satisfy this",
     "expected_effect": "form|truth|utility: what should measurably move",
     "budget": {"max_cost_usd": 1.0, "max_targets": 8}}
  ],
  "run_analysis": {
    "summary": "two to four sentences about how the run worked, not a restatement of the map",
    "deterministic_transfers": [
      {"finding": "what model work may be mechanically derivable",
       "basis": "the measured parser-first or failure evidence",
       "validation": "the test needed before moving it"}
    ],
    "improvements": [
      {"area": "context|prompt|routing|parser|adjudication|synthesis|operations",
       "recommendation": "a concrete change worth evaluating",
       "basis": "the measured run evidence that motivated it"}
    ],
    "watch_next_run": ["a specific quality or efficiency signal to compare"]
  },
  "improvement_target": "if another round should run, the ONE thing it should \
change, stated so that afterwards anyone could tell whether it happened"
}

"not-done" is only a legal verdict if you can attach a work order whose
instructions would CHANGE the result. "look again", "be more thorough" and "add
more detail" are not work orders: nothing about them predicts a different
outcome. If you cannot name what would change, the honest verdict is "done" with
the limitation stated in your reasoning.

Answer every criterion you were given, including the ones you would rather not.
"unknown" is a legitimate verdict when the census cannot settle it, and is far
better than a confident "met" that nothing supports.
Before proposing general polish, cover every subject criterion you mark
"unmet" or "unknown". If changing in-census enrichment claims could settle it,
issue an executable work order naming the exact component/relationship IDs and
claim questions that must change. An aggregate disagreement rate below its gate
does not excuse a known criterion gap. If enrichment cannot settle it, name the
deterministic or external blocker in run_analysis rather than buying another
identical pass.

Work from what you are given below. Do not ask for a re-read of the components:
the census is the record of what was established about them, and it is what you
are judging.

The run_analysis is the learning channel, not filler. Use only measurements in
the operations digest and findings in the supplied evidence. Empty arrays are
correct when the run established no recommendation. Never propose moving an
interpretive judgment to deterministic code merely because it was expensive;
name a transfer only when a parser-first finding or repeatable mechanical rule
supports it. Keep at most five non-duplicate entries in each list. The complete
ledger remains authoritative; your job is to explain what its measurements mean
and what should be tested next.

A work order can repair or sharpen enrichment claims for its scoped components
and relationships. It cannot change parser facts or the independent identity,
edge, or finding verifier verdicts: those require deterministic parser work or
a separately scheduled verification pass. Never issue a work order that merely
asks the enrichment ladder to re-verify one of those independent verdicts.
"""


def build_determination_prompt(
    *,
    criteria: list[Criterion],
    census: dict,
    adjudication: Optional[dict],
    synthesis: Optional[dict],
    brief: Optional[dict],
    forced_round: bool,
    rounds_so_far: list[dict],
    budget_note: str,
    mechanical_map: Optional[dict] = None,
    scope_note: Optional[str] = None,
    operations: Optional[dict] = None,
) -> str:
    # The prompt splits at the stable/variable seam. Everything identical
    # across a run's determination calls (instructions, contract, brief,
    # criteria, adjudication and synthesis) renders FIRST and travels as the
    # cacheable prefix. The census is deliberately in the user tail: work
    # orders can change it between judgments, and putting it in the prefix
    # invalidated the whole cache while claiming the boundary was stable.
    # Everything round-specific renders in that same tail. The v2 run's three p5
    # calls shipped a near-identical body at the 2x write rate three times
    # because the forced-round block sat at position 3 and broke byte
    # stability between call 1 and the rest (IMPLEMENTATION-DELTA-ORCH.md
    # section 1.1 A3, step 3).
    prefix_parts = [
        "You are deciding whether an automated map of a software system is good "
        "enough to publish, or whether there is room you know how to close.",
        "",
        _DETERMINATION_CONTRACT,
        "",
    ]
    if brief:
        prefix_parts += ["THE SUBJECT BRIEF:", json.dumps(brief, indent=2, default=str), ""]
    if scope_note:
        prefix_parts += ["RUN SCOPE:", scope_note, ""]
    prefix_parts += [
        "THE CRITERIA YOU MUST ANSWER (set by the orientation pass before any "
        "enrichment ran, so they are not shaped by what happened to be easy):",
        json.dumps([c.to_dict() for c in criteria], indent=2, default=str),
        "",
    ]
    if mechanical_map:
        prefix_parts += [
            "THE MECHANICAL MAP INVENTORY (parser-owned evidence for criteria "
            "about coverage, language, type, ports, and declared edges):",
            json.dumps(mechanical_map, separators=(",", ":"), default=str),
            "",
        ]
    if synthesis:
        prefix_parts += [
            "THE STORY AND THE LENSES:",
            json.dumps(synthesis, indent=2, default=str),
            "",
        ]
    tail_parts = [
        "THE CURRENT ITEM CENSUS (what is established now):",
        json.dumps(census, separators=(",", ":"), default=str),
        "",
    ]
    if adjudication:
        # Work-order rechecks change this evidence between determinations. It
        # belongs beside the changing census, not in the cacheable prefix; the
        # live pilot otherwise cold-wrote the P5 block again precisely when a
        # repair round had done useful work.
        tail_parts += [
            "WHAT INDEPENDENT ADJUDICATION FOUND:",
            json.dumps(adjudication, separators=(",", ":"), default=str),
            "",
        ]
    if operations:
        # This digest changes as repair rounds add calls. It belongs in the
        # uncached tail. The stable contract above tells Fable how to consume it;
        # the raw append-only ledger remains in the final report for audit.
        tail_parts += [
            "MEASURED RUN OPERATIONS THROUGH THE PREVIOUS PHASE (the final "
            "report mechanically adds this determination call and its audit):",
            json.dumps(operations, separators=(",", ":"), default=str),
            "",
        ]
    if forced_round:
        tail_parts += [
            "POLICY: this run must carry out at least one improvement round even "
            "if you judge the map done. That is deliberate, and it is how the "
            "tuning that later decides 'iterate or not' gets learned. So give a "
            "REAL improvement_target and a real work order: name the thing you "
            "would most want better, not the cheapest thing to say. A round with "
            "no genuine target is worse than no round, because it teaches nothing "
            "and still costs the run.",
            "",
        ]
    if rounds_so_far:
        tail_parts += [
            "IMPROVEMENT ROUNDS ALREADY RUN, and what they actually changed. A "
            "round that changed nothing is evidence about the next one:",
            json.dumps(_rounds_digest(rounds_so_far), separators=(",", ":"), default=str),
            "",
        ]
    tail_parts += [budget_note, "", "Return the JSON object now."]
    return _cached_prompt("\n".join(prefix_parts), "\n".join(tail_parts))


def _operations_digest(ctx: RunContext, ladder: Any = None) -> dict:
    """Compact measured inputs for Fable's exit analysis.

    P5 cannot analyze logistics it never sees. Conversely, replaying the full
    ledger in its prompt would rebuild the output-waste problem. This digest
    carries exact totals and phase/model buckets, plus a bounded sample of
    distinct parser-first capability cards. The final report retains every raw
    row and every card, so sampling here never destroys the audit record.
    """
    rows = list(ctx.ledger or [])

    def bucketed(field: str) -> list[dict]:
        buckets: dict[str, dict] = {}
        for row in rows:
            key = str(getattr(row, field, None) or "unknown")
            bucket = buckets.setdefault(key, {
                field: key, "calls": 0, "targets": 0, "tokens_in": 0,
                "tokens_cached": 0, "tokens_cache_write": 0,
                "tokens_out": 0, "response_bytes": 0, "cost_usd": 0.0,
                "wall_seconds": 0.0, "retries": 0, "failures": 0,
            })
            bucket["calls"] += 1
            bucket["targets"] += int(row.targets or 0)
            bucket["tokens_in"] += int(row.tokens_in or 0)
            bucket["tokens_cached"] += int(row.tokens_cached or 0)
            bucket["tokens_cache_write"] += int(row.tokens_cache_write or 0)
            bucket["tokens_out"] += int(row.tokens_out or 0)
            bucket["response_bytes"] += int(row.response_bytes or 0)
            bucket["cost_usd"] += float(row.cost_usd or 0.0)
            bucket["wall_seconds"] += float(row.wall_seconds or 0.0)
            bucket["retries"] += int(row.retries or 0)
            bucket["failures"] += int(not row.ok)
        for bucket in buckets.values():
            bucket["cost_usd"] = round(bucket["cost_usd"], 6)
            bucket["wall_seconds"] = round(bucket["wall_seconds"], 3)
        return [buckets[key] for key in sorted(buckets)]

    totals = {
        "calls": len(rows),
        "targets": sum(int(row.targets or 0) for row in rows),
        "tokens_in": sum(int(row.tokens_in or 0) for row in rows),
        "tokens_cached": sum(int(row.tokens_cached or 0) for row in rows),
        "tokens_cache_write": sum(int(row.tokens_cache_write or 0) for row in rows),
        "tokens_out": sum(int(row.tokens_out or 0) for row in rows),
        "response_bytes": sum(int(row.response_bytes or 0) for row in rows),
        "cost_usd": round(sum(float(row.cost_usd or 0.0) for row in rows), 6),
        "wall_seconds": round(sum(float(row.wall_seconds or 0.0) for row in rows), 3),
        "retries": sum(int(row.retries or 0) for row in rows),
        "failures": sum(int(not row.ok) for row in rows),
        "output_budget_violations": sum(row.output_budget_ok is False for row in rows),
    }
    writes = totals["tokens_cache_write"]
    totals["cache_read_write_ratio"] = round(
        totals["tokens_cached"] / writes, 4
    ) if writes else None

    trigger_counts: dict[str, int] = {}
    climbed: set[tuple[str, str]] = set()
    if ladder is not None:
        for event in list(getattr(ladder, "transitions", None) or []):
            if event.get("state") not in ("escalate", "honest_gap"):
                continue
            climbed.add((str(event.get("target_kind")), str(event.get("target_id"))))
            for failed in event.get("failed") or []:
                trigger = str(failed.get("trigger") or "unknown")
                trigger_counts[trigger] = trigger_counts.get(trigger, 0) + 1

    distinct_findings: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    if ladder is not None:
        for item in list(getattr(ladder, "parser_findings", None) or []):
            key = (
                str(item.get("target_kind") or ""),
                str(item.get("target_id") or ""),
                str(item.get("finding") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            distinct_findings.append({
                "target_kind": key[0], "target_id": key[1], "finding": key[2],
            })

    return {
        "totals": totals,
        "by_phase": bucketed("phase"),
        "by_model": bucketed("model"),
        "escalation": {
            "climbed_targets": len(climbed),
            "failure_records_by_trigger": dict(sorted(trigger_counts.items())),
        },
        "parser_first": {
            "distinct_count": len(distinct_findings),
            "examples": distinct_findings[:40],
            "examples_are_bounded": len(distinct_findings) > 40,
        },
    }


def _normalize_run_analysis(value: Any) -> dict:
    """Keep the learning channel useful, bounded and structurally predictable."""
    value = value if isinstance(value, dict) else {}

    def text_value(raw: Any, cap: int) -> str:
        return str(raw or "").strip()[:cap]

    def object_list(name: str, fields: tuple[str, ...]) -> list[dict]:
        out = []
        for item in value.get(name) or []:
            if not isinstance(item, dict):
                continue
            normalized = {
                field: text_value(item.get(field), 800)
                for field in fields if text_value(item.get(field), 800)
            }
            if normalized:
                out.append(normalized)
            if len(out) == 5:
                break
        return out

    watch = [
        text_value(item, 800) for item in (value.get("watch_next_run") or [])
        if text_value(item, 800)
    ][:5]
    return {
        "status": "model-analyzed" if value else "missing",
        "summary": text_value(value.get("summary"), 2_400),
        "deterministic_transfers": object_list(
            "deterministic_transfers", ("finding", "basis", "validation")
        ),
        "improvements": object_list(
            "improvements", ("area", "recommendation", "basis")
        ),
        "watch_next_run": watch,
    }


def _rounds_digest(rounds: list[dict]) -> list[dict]:
    """Carry measured deltas, not the full prose already judged last round."""
    out = []
    for round_ in rounds:
        if not isinstance(round_, dict):
            continue
        orders = []
        for order in round_.get("work_orders") or []:
            if not isinstance(order, dict):
                continue
            result = order.get("outcome") if isinstance(order.get("outcome"), dict) else {}
            orders.append({
                "scope": order.get("scope"),
                "expected_effect": order.get("expected_effect"),
                "executed": result.get("executed"),
                "state_changes": result.get("state_changes"),
                "changed_anything": result.get("changed_anything"),
                "cost_usd": result.get("cost_usd"),
                "notes": result.get("notes"),
            })
        out.append({
            "number": round_.get("number"),
            "forced": round_.get("forced"),
            "target": round_.get("target"),
            "ran": round_.get("ran"),
            "measured_delta": round_.get("measured_delta"),
            "orders": orders,
            "notes": round_.get("notes"),
        })
    return out


def _census_digest(census: dict) -> dict:
    """Counts plus actionable exceptions, never every successful target."""
    items = census.get("items") if isinstance(census, dict) else []
    exceptions = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        state = str(item.get("state") or "")
        if state == "grounded":
            continue
        exceptions.append({
            "target_kind": item.get("target_kind"),
            "target_id": item.get("target_id"),
            "state": state,
            "rung": item.get("rung"),
            "failed": [
                {"question": f.get("question"), "trigger": f.get("trigger"),
                 "note": str(f.get("note") or "")[:240]}
                for f in (item.get("failed") or []) if isinstance(f, dict)
            ],
        })
    return {
        "by_state": census.get("by_state", {}),
        "total": census.get("total", 0),
        "grounded": census.get("grounded", 0),
        "grounded_fraction": census.get("grounded_fraction", 0.0),
        "trigger_counts": census.get("trigger_counts", {}),
        "exceptions": exceptions,
    }


def _adjudication_digest(adjudication: Optional[dict]) -> Optional[dict]:
    if not isinstance(adjudication, dict):
        return None

    def pass_summary(value: Any) -> dict:
        value = value if isinstance(value, dict) else {}
        summary = {
            key: value.get(key) for key in
            ("pass", "target_count", "done", "failed", "verdicts", "total_cost_usd")
            if key in value
        }
        # Aggregate counts hide the exact deterministic verdict a subject
        # criterion may name. A live criterion named an edge verify-edges had
        # refuted, but P5 saw only "2 refuted" and repeatedly tried to enrich a
        # rationale for the bad edge. Preserve the bounded per-target verdicts.
        summary["outcomes"] = [
            {
                key: item.get(key) for key in ("id", "status", "verdict", "errors")
                if item.get(key) not in (None, "", [])
            }
            for item in (value.get("outcomes") or [])[:200]
            if isinstance(item, dict)
        ]
        return summary

    unsupported = [
        item for item in (adjudication.get("spot_checks") or [])
        if isinstance(item, dict) and not item.get("supported", True)
    ][:20]
    substitutions = [
        item for item in (adjudication.get("substitution_checks") or [])
        if isinstance(item, dict) and item.get("confirmed_failure")
    ][:20]
    # P5 judges subject criteria against what the map actually says, not only
    # against failures. Canary 13 had a supported API claim explicitly naming
    # its Postgres driver, but the former failure-only digest hid that claim and
    # forced the corresponding criterion to UNKNOWN. The spot-check quota
    # already bounds this collection; cap each claim and the total as a second
    # deterministic guard against rebuilding the product inside the report.
    checked_claims = [
        {
            "target_kind": item.get("target_kind"),
            "target_id": item.get("target_id"),
            "question": item.get("question"),
            "claim": str(item.get("claim") or "")[:400],
            "supported": bool(item.get("supported")),
        }
        for item in (adjudication.get("spot_checks") or [])
        if isinstance(item, dict)
    ][:200]
    return {
        "checked": adjudication.get("checked"),
        "unsupported": adjudication.get("unsupported"),
        "disagreement_rate": adjudication.get("disagreement_rate"),
        "substitution_failure_rate": adjudication.get("substitution_failure_rate"),
        "verification": {
            name: pass_summary(adjudication.get(name))
            for name in ("identity", "edges", "findings")
        },
        "unsupported_examples": unsupported,
        "checked_claims": checked_claims,
        "substitution_failures": substitutions,
    }


def _synthesis_digest(synthesis: Optional[dict]) -> Optional[dict]:
    """Synthesis ships IN FULL, never digested.

    The measured design is explicit (IMPLEMENTATION-DELTA-ORCH.md section
    2.1): the recorded determination verdicts quote the tours by name and
    content, so cutting tour prose would cut evidence the output demonstrably
    uses. Synthesis is about 24k chars on the v2 subject and the p5 input
    ceiling of 35,000 tokens already prices it in; the census and
    adjudication digests carry the whole reduction. An earlier revision
    trimmed tours to titles here, which the final QA pass flagged as a
    story-versus-code contradiction in the quality-risk direction.
    """
    if not isinstance(synthesis, dict):
        return None
    return dict(synthesis)


def _mechanical_map_digest(ctx: RunContext, ladder=None) -> dict:
    """Exact, compact evidence for subject criteria that the census cannot answer.

    The census intentionally says whether enrichment grounded; it does not carry
    parser identity or an inventory roll-call.  P1 is allowed to set bars about
    those facts, so withholding them from P5 forced the judge to return unknown
    even when the deterministic map already knew the answer.
    """
    attempted = set(ladder.states) if ladder is not None else None
    component_scope = (
        {target_id for kind, target_id in attempted if kind == "component"}
        if attempted is not None else None
    )
    relationship_scope = (
        {target_id for kind, target_id in attempted if kind == "relationship"}
        if attempted is not None else None
    )
    components: list[dict] = []

    def walk(items: list) -> None:
        for component in items:
            if component_scope is None or component.get("id") in component_scope:
                components.append({
                    key: component.get(key)
                    for key in ("id", "name", "type", "language", "framework", "port")
                    if component.get(key) not in (None, "")
                })
            walk(component.get("children") or [])

    walk(ctx.arch.get("components") or [])
    relationships = [
        {
            key: row.get(key)
            for key in ("source", "target", "type", "protocol", "port")
            if row.get(key) not in (None, "")
        }
        for row in (ctx.arch.get("relationships") or [])
        if relationship_scope is None or (
            f"{row.get('source', '')}|{row.get('target', '')}|{row.get('type', '')}"
            in relationship_scope
        )
    ]
    language_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for component in components:
        language = str(component.get("language") or "").strip().lower()
        component_type = str(component.get("type") or "").strip().lower()
        if language:
            language_counts[language] = language_counts.get(language, 0) + 1
        if component_type:
            type_counts[component_type] = type_counts.get(component_type, 0) + 1
    return {
        "scope": "attempted-targets" if attempted is not None else "full-repository",
        "stats": {
            "total_components": len(components),
            "total_relationships": len(relationships),
            "languages": language_counts,
            "component_types": type_counts,
        },
        "components": components,
        "relationships": relationships,
        "readme": _collect_readme(ctx.arch, ctx.root)[:6_000],
    }


# --- the phase -----------------------------------------------------------------


class DeterminationPhase:
    """P5: the verdict, the bounded loop, and the criteria answered."""

    name = "p5_determination"

    def run(self, ctx: RunContext) -> PhaseResult:
        outcome = DeterminationOutcome()
        census = self._census(ctx)
        adjudication = (ctx.phase_data("p3_adjudication") or {}).get("adjudication")
        synthesis = (ctx.phase_data("p4_synthesis") or {}).get("synthesis")
        ladder = (ctx.phase_data("p2_ladder") or {}).get("ladder")
        brief = self._brief(ctx)
        criteria = self._criteria(ctx, brief)

        if ctx.dry_run:
            outcome.notes.append(
                f"dry run: {len(criteria)} criteria would be answered, "
                f"{ctx.policy.iteration.min_rounds} forced round(s) would run"
            )
            return PhaseResult(name=self.name, status="ok", notes=outcome.notes,
                               data={"determination": outcome})

        # The three universal gates are answered by code before anything is
        # asked of a model, so their verdicts cannot be talked out of.
        mechanical = self._mechanical(criteria, census, adjudication)

        policy = ctx.policy.iteration.normalized()
        ctx.descend = make_descender(ctx, ladder)

        round_number = 0
        judged = self._judge(
            ctx, outcome, criteria, census, adjudication, synthesis, brief,
            forced_round=policy.min_rounds > 0,
        )
        self._merge_verdicts(outcome, criteria, mechanical, judged)
        self._ensure_adjudication_repair(outcome, adjudication, ctx)

        while round_number < policy.max_rounds:
            forced = round_number < policy.min_rounds
            # A model saying "done" cannot end the loop while one of the
            # predeclared criteria is still unmet or unknown. If it supplied a
            # repair order, use the remaining bounded round; if it did not,
            # _run_round records that no executable path was named and settle()
            # truthfully qualifies the final verdict.
            wants_more = outcome.verdict == "not-done" or any(
                verdict.verdict != "met" for verdict in outcome.verdicts
            )
            if not forced and not wants_more:
                break
            if not ctx.budget.under():
                outcome.notes.append(
                    f"round {round_number + 1} not run: run cost ceiling reached"
                )
                break
            round_number += 1
            disagreement_before = (
                adjudication.disagreement_rate()
                if adjudication is not None else None
            )
            round_ = self._run_round(
                ctx, outcome, ladder, census, judged, number=round_number, forced=forced
            )
            outcome.rounds.append(round_)
            if not round_.ran:
                break
            recheck_ids = {
                target_id
                for result in round_.outcomes if result.executed
                for target_id in result.order.scope[: result.order.max_targets]
            }
            if recheck_ids:
                from .adjudicate import AdjudicationPhase

                recheck_spent_before = ctx.budget.spent
                adjudication = AdjudicationPhase().recheck(ctx, recheck_ids)
                recheck_cost = ctx.budget.spent - recheck_spent_before
                round_.measured_delta["adjudication_cost_usd"] = round(
                    recheck_cost, 6
                )
                round_.measured_delta["cost_usd"] = round(
                    float(round_.measured_delta.get("cost_usd") or 0.0)
                    + recheck_cost,
                    6,
                )
                disagreement_after = adjudication.disagreement_rate()
                if disagreement_before is not None and disagreement_after is not None:
                    round_.measured_delta["adjudication_disagreement_before"] = round(
                        disagreement_before, 6
                    )
                    round_.measured_delta["adjudication_disagreement_after"] = round(
                        disagreement_after, 6
                    )
                # _run_round records its no-gain note before the independent
                # recheck exists. Reconcile that provisional statement now that
                # the quality instrument has reported.
                if round_.gained:
                    no_gain = "This round produced no measurable gain."
                    round_.notes = [
                        note for note in round_.notes if not note.startswith(no_gain)
                    ]
                    outcome.notes = [
                        note for note in outcome.notes
                        if note != f"round {round_number} produced no measurable change to the census"
                    ]
            census = self._census(ctx, ladder=ladder)
            if ladder is not None:
                ladder.census = census
            mechanical = self._mechanical(criteria, census, adjudication)
            judged = self._judge(
                ctx, outcome, criteria, census, adjudication, synthesis, brief,
                forced_round=False,
                rounds_so_far=[r.to_dict() for r in outcome.rounds],
            )
            self._merge_verdicts(outcome, criteria, mechanical, judged)
            self._ensure_adjudication_repair(outcome, adjudication, ctx)

        # The round bound limits generative iteration; it must not authorize
        # publication of claims the final independent check has already found
        # unsupported. Quarantine only those exact question/target pairs,
        # remeasure the resulting map, and ask for the actual final verdict.
        # This closes the live canary defect where a repair order created after
        # round 2 sat unexecuted while eight known-bad clauses remained visible.
        remaining_unsupported = list(
            getattr(adjudication, "unsupported", []) or []
        ) if adjudication is not None else []
        if remaining_unsupported and ladder is not None:
            from .adjudicate import AdjudicationPhase
            from .ladder import LadderPhase

            quarantined_targets: set[str] = set()
            quarantined_claims = 0
            seen_rejections: set[tuple[tuple[str, str, str, str], ...]] = set()
            # Rechecking a mixed honest-gap item can expose a different,
            # previously sampled sibling claim after the first rejected claim
            # is removed.  Iterate to a fixed point: every pass strictly
            # removes at least one answered atom, so this is bounded by the
            # finite contract rather than an arbitrary retry count.  Judge P5
            # only once after the evidence surface is stable.
            while remaining_unsupported:
                fingerprint = tuple(sorted(
                    (
                        str(getattr(check, "target_kind", "") or ""),
                        str(getattr(check, "target_id", "") or ""),
                        str(getattr(check, "question", "") or ""),
                        str(getattr(check, "claim", "") or ""),
                    )
                    for check in remaining_unsupported
                ))
                if fingerprint in seen_rejections:
                    outcome.notes.append(
                        "adjudication quarantine stopped because the identical "
                        "rejection set recurred; completion remains gated"
                    )
                    break
                seen_rejections.add(fingerprint)
                quarantined = LadderPhase().quarantine_unsupported(
                    ctx, ladder, remaining_unsupported
                )
                if not quarantined:
                    break
                quarantined_targets.update(quarantined)
                quarantined_claims += len(remaining_unsupported)
                adjudication = AdjudicationPhase().recheck(ctx, quarantined)
                remaining_unsupported = list(
                    getattr(adjudication, "unsupported", []) or []
                )
            if quarantined_targets:
                outcome.notes.append(
                    "after the bounded improvement rounds, deterministically "
                    f"quarantined {quarantined_claims} independently "
                    f"unsupported claim(s) on {len(quarantined_targets)} target(s) "
                    "to an adjudication fixed point; "
                    "supported sibling answers were preserved"
                )
                census = self._census(ctx, ladder=ladder)
                ladder.census = census
                mechanical = self._mechanical(criteria, census, adjudication)
                judged = self._judge(
                    ctx, outcome, criteria, census, adjudication, synthesis, brief,
                    forced_round=False,
                    rounds_so_far=[r.to_dict() for r in outcome.rounds],
                )
                self._merge_verdicts(outcome, criteria, mechanical, judged)
                # A final judgment may describe future improvement, but there is
                # no hidden executable order after the declared round bound.
                outcome.pending_orders = []

        self._settle(outcome, census)
        return PhaseResult(
            name=self.name,
            status="ok" if outcome.verdict != "unknown" else "failed",
            notes=list(outcome.notes),
            data={"determination": outcome},
        )

    # --- inputs ---------------------------------------------------------------

    def _census(self, ctx: RunContext, ladder=None):
        if ladder is not None:
            from .contract import build_census

            return build_census(list(ladder.states.values()))
        return (ctx.phase_data("p2_ladder") or {}).get("census")

    def _brief(self, ctx: RunContext):
        return (ctx.phase_data("p1_orientation") or {}).get("brief")

    def _criteria(self, ctx: RunContext, brief) -> list[Criterion]:
        """The criteria P1 set, or the universal floor when P1 produced none.

        The determination never invents its own bar. It answers the questions
        orientation asked, which is what stops a run from grading itself against
        whatever it happened to do well.
        """
        if brief is not None and brief.criteria:
            return list(brief.criteria)
        return universal_criteria()

    def _mechanical(self, criteria, census, adjudication) -> dict:
        out: dict[str, CriterionVerdict] = {}
        for criterion in criteria:
            if not criterion.universal:
                continue
            verdict = evaluate_universal(
                criterion, census=census, adjudication=adjudication
            )
            if verdict is not None:
                out[criterion.id] = verdict
        return out

    # --- judging ---------------------------------------------------------------

    def _judge(
        self, ctx: RunContext, outcome: DeterminationOutcome,
        criteria: list[Criterion], census, adjudication, synthesis, brief,
        *, forced_round: bool, rounds_so_far: Optional[list[dict]] = None,
    ) -> dict:
        if not ctx.budget.under():
            outcome.notes.append("determination not judged: run cost ceiling reached")
            return {}
        ceiling = ctx.policy.max_cost_usd
        remaining = ctx.budget.remaining()
        budget_note = (
            "BUDGET: this run has no cost ceiling."
            if ceiling is None
            else f"BUDGET: ${remaining:.2f} of ${ceiling:.2f} API-equivalent remains. "
            "Scope any work order you issue to fit inside it."
        )
        prompt = build_determination_prompt(
            criteria=criteria,
            census=_census_digest(census.to_dict() if census is not None else {}),
            adjudication=_adjudication_digest(
                adjudication.to_dict() if adjudication is not None else None
            ),
            synthesis=_synthesis_digest(
                synthesis.to_dict() if synthesis is not None else None
            ),
            brief=brief.to_dict() if brief is not None else None,
            forced_round=forced_round,
            rounds_so_far=rounds_so_far or [],
            budget_note=budget_note,
            mechanical_map=_mechanical_map_digest(
                ctx, (ctx.phase_data("p2_ladder") or {}).get("ladder")
            ),
            operations=_operations_digest(
                ctx, (ctx.phase_data("p2_ladder") or {}).get("ladder")
            ),
            scope_note=(
                "This is a bounded validation canary over only the selected "
                f"{ctx.max_partitions} most important planned partition(s). Judge "
                "whether that attempted slice meets the full quality bar. Do not "
                "fail it merely because unselected code was intentionally not "
                "attempted, and do not claim the full repository is complete."
                if ctx.max_partitions is not None
                else None
            ),
        )
        invoker = ctx.invoker(
            "p5_determination", phase=self.name, targets=1,
            # The learning analysis is deliberately allowed meaningful room.
            # Canary 16's determination used 5.6k bytes before this channel;
            # 20k is a runaway tripwire, not a target or a terse-answer dial.
            output_budget_bytes=20_000,
        )
        result = invoker(prompt)
        if not result.ok:
            outcome.notes.append(f"determination did not return: {result.error}")
            return {}
        obj = _parse_json_object(
            result.text, expect_keys=("verdict", "criteria", "run_analysis")
        )
        if obj is None:
            outcome.notes.append("determination returned unparseable text")
            return {}
        verdict = str(obj.get("verdict") or "").strip().lower()
        if verdict in ("done", "not-done"):
            outcome.verdict = verdict
        outcome.reasoning = str(obj.get("reasoning") or "").strip()
        outcome.run_analysis = _normalize_run_analysis(obj.get("run_analysis"))
        orders, rejected = parse_work_orders(
            obj.get("work_orders"), issued_by="P5", cap=ctx.policy.max_work_orders
        )
        outcome.pending_orders = orders
        outcome.rejected_orders = rejected
        for rejection in rejected:
            outcome.notes.append(f"work order rejected: {rejection}")
        return obj

    def _merge_verdicts(
        self, outcome: DeterminationOutcome, criteria: list[Criterion],
        mechanical: dict, judged: dict,
    ) -> None:
        """Mechanical gates win; the model answers the rest."""
        model_verdicts: dict[str, dict] = {}
        for item in (judged.get("criteria") or []):
            if isinstance(item, dict) and item.get("criterion_id"):
                model_verdicts[str(item["criterion_id"])] = item

        merged: list[CriterionVerdict] = []
        for criterion in criteria:
            if criterion.id in mechanical:
                merged.append(mechanical[criterion.id])
                continue
            raw = model_verdicts.get(criterion.id)
            if raw is None:
                merged.append(CriterionVerdict(
                    criterion_id=criterion.id, statement=criterion.statement,
                    verdict="unknown",
                    reasoning="the determination did not answer this criterion",
                ))
                continue
            verdict = str(raw.get("verdict") or "unknown").strip().lower()
            evidence = raw.get("evidence")
            merged.append(CriterionVerdict(
                criterion_id=criterion.id,
                statement=criterion.statement,
                verdict=verdict if verdict in ("met", "unmet", "unknown") else "unknown",
                evidence=[str(e) for e in evidence] if isinstance(evidence, list) else [],
                reasoning=str(raw.get("reasoning") or ""),
            ))
        outcome.verdicts = merged

    # --- rounds ----------------------------------------------------------------

    def _ensure_adjudication_repair(
        self, outcome: DeterminationOutcome, adjudication, ctx: RunContext
    ) -> None:
        """Make independently rejected claims part of the next repair order.

        Independent adjudication has already identified exact target/question
        pairs whose claims outrun their citations. Narrowing those claims is an
        executable enrichment repair, not an open-ended judgment. The model may
        choose a better order, but it cannot omit a named failed claim from a
        forced round. If it already supplied an order, augment that order rather
        than purchasing a second pass over the same target.
        """
        if adjudication is None:
            return
        unsupported = list(getattr(adjudication, "unsupported", []) or [])
        if not unsupported:
            return
        grouped: dict[str, list[str]] = {}
        for check in unsupported:
            target_id = str(getattr(check, "target_id", "") or "")
            question = str(getattr(check, "question", "") or "")
            if target_id and question:
                grouped.setdefault(target_id, []).append(question)
        scope = sorted(grouped)[: max(1, ctx.policy.max_work_orders * 8)]
        if not scope:
            return
        pairs = ", ".join(
            f"{target}:" + "/".join(sorted(set(grouped[target])))
            for target in scope
        )
        repair_lens = (
                "Repair only the independently unsupported claims. Narrow each "
                "claim until every clause is carried by this target's supplied "
                "evidence; do not add replacement detail. The replacement must "
                "not repeat any phrase the independent judge explicitly named "
                "unsupported unless you attach the exact missing evidence. For "
                "an unsupported "
                "negative or uniqueness clause (no, none, only, sole), remove "
                "that clause unless a supplied deterministic fact directly "
                f"establishes it. Targets/questions: {pairs}"
        )
        repair_criteria = (
                "Re-adjudication marks every named target/question supported, "
                "with no regression in the other established answers."
        )
        repair_effect = (
                "truth: the unsupported-claim count for the scoped targets "
                "decreases to zero"
        )
        if outcome.pending_orders:
            order = outcome.pending_orders[0]
            order.scope = sorted(set(order.scope) | set(scope))
            order.lens = order.lens.rstrip() + " " + repair_lens
            order.criteria = order.criteria.rstrip() + " " + repair_criteria
            order.expected_effect = repair_effect
            order.budget = {
                **order.budget,
                "max_cost_usd": max(order.max_cost_usd, 2.0),
                "max_targets": len(order.scope),
            }
            note = (
                "P5's work order omitted independently unsupported claims; "
                "expanded its first-round scope to include every named failure"
            )
            if note not in outcome.notes:
                outcome.notes.append(note)
        else:
            outcome.pending_orders = [WorkOrder(
                scope=scope,
                lens=repair_lens,
                criteria=repair_criteria,
                expected_effect=repair_effect,
                budget={"max_cost_usd": 2.0, "max_targets": len(scope)},
                issued_by="P5-deterministic-repair",
            )]
            outcome.notes.append(
                "P5 named no executable repair despite independently unsupported "
                "claims; issued one deterministic claim-narrowing work order"
            )

    def _run_round(
        self, ctx: RunContext, outcome: DeterminationOutcome, ladder,
        census, judged: dict, *, number: int, forced: bool,
    ) -> IterationRound:
        target = str(judged.get("improvement_target") or "").strip()
        round_ = IterationRound(number=number, forced=forced, target=target)

        if forced and not target:
            # A forced round must carry a reasoned target. Running one without a
            # target spends the owner's budget on a checkbox and teaches nothing,
            # which is the exact outcome the forced-iteration policy exists to
            # avoid.
            round_.notes.append(
                "NOT RUN: a forced improvement round must carry a reasoned target, "
                "and the determination named none. A round with no target is a "
                "checkbox, and the policy exists to prevent exactly that."
            )
            outcome.notes.append(round_.notes[0])
            return round_

        orders = list(outcome.pending_orders)
        if not orders:
            round_.notes.append(
                "NOT RUN: no executable work order was issued. 'Not done' without "
                "an order that would change the result is not a round, it is a "
                "refusal to finish."
            )
            outcome.notes.append(round_.notes[0])
            return round_

        before = self._state_snapshot(ladder)
        round_.orders = orders
        round_.outcomes = ctx.descend(orders) if ctx.descend else []
        round_.ran = any(o.executed for o in round_.outcomes)
        after = self._state_snapshot(ladder)

        # State and rung are distinct instruments. A state transition measures
        # completion/truth posture; a rung move measures that the same terminal
        # answer was regenerated at a different tier. The latter is a real,
        # reportable economics change, not a perceived prose improvement.
        changed = {
            key: {"before": before.get(key, {}).get("state"),
                  "after": value.get("state")}
            for key, value in after.items()
            if before.get(key, {}).get("state") != value.get("state")
        }
        rung_moves = sorted(
            key for key, value in after.items()
            if before.get(key, {}).get("state") == value.get("state")
            and before.get(key, {}).get("rung") != value.get("rung")
        )
        payload_changes = sorted({
            target_id
            for result in round_.outcomes
            for target_id in result.payload_changes
        })
        round_.measured_delta = {
            "changed": len(changed),
            "targets": sorted(changed),
            "state_changes": changed,
            "rung_moves": rung_moves,
            "payload_changes": payload_changes,
            "grounded_before": sum(
                1 for v in before.values() if v.get("state") == "grounded"
            ),
            "grounded_after": sum(
                1 for v in after.values() if v.get("state") == "grounded"
            ),
            "cost_usd": round(sum(o.cost_usd for o in round_.outcomes), 6),
        }
        round_.perceived_delta = str(judged.get("improvement_target") or "")
        if not round_.gained:
            round_.notes.append(
                "This round produced no measurable gain. Recorded as exactly that: "
                "it is the finding that earns dialling the forced-iteration policy "
                "back, not a failure to hide."
            )
            outcome.notes.append(
                f"round {number} produced no measurable change to the census"
            )
        # The orders have been executed; they must not be re-issued next round.
        outcome.pending_orders = []
        return round_

    def _state_snapshot(self, ladder) -> dict:
        """State and rung per target, the two contract-side change instruments."""
        if ladder is None:
            return {}
        return {
            key[1]: {"state": state.state, "rung": state.rung}
            for key, state in ladder.states.items()
        }

    # --- settle ----------------------------------------------------------------

    def _settle(self, outcome: DeterminationOutcome, census) -> None:
        """Reconcile the verdict with what the criteria and the rounds actually say."""
        unsettled = [v for v in outcome.verdicts if v.verdict != "met"]

        # The predeclared criteria are the publication contract. Once a real
        # improvement round has run and every criterion is met, a model may
        # still be able to name another useful edit; that belongs in the exit
        # learning channel, not in an endless refusal to finish. The live
        # canary reached 9.7% disagreement (well inside u2's 20% gate), met all
        # eight criteria, and nevertheless said not-done because six more
        # sentences could be polished. Resolve that boundary deterministically
        # while retaining its pending orders in the report as follow-up data.
        if (
            outcome.verdict == "not-done"
            and not unsettled
            and any(round_.ran for round_ in outcome.rounds)
        ):
            outcome.verdict = "done"
            outcome.notes.append(
                "verdict settled to 'done': every predeclared criterion is met "
                "after a measured improvement round; additional executable "
                "orders remain recorded as exit-learning opportunities"
            )

        if outcome.verdict == "not-done":
            executable = any(r.ran for r in outcome.rounds) or outcome.pending_orders
            if not executable:
                outcome.verdict = "done-with-reservations"
                outcome.notes.append(
                    "verdict downgraded from 'not-done' to "
                    "'done-with-reservations': nothing was issued that would "
                    "change the result, and a run cannot refuse to finish without "
                    "naming what would finish it"
                )
        if outcome.verdict == "done" and unsettled:
            outcome.verdict = "done-with-reservations"
            outcome.notes.append(
                f"verdict qualified: {len(unsettled)} criterion/criteria were "
                "not conclusively met ("
                + ", ".join(
                    f"{v.criterion_id}:{v.verdict}" for v in unsettled
                )
                + ")"
            )
        if not outcome.reasoning:
            outcome.reasoning = (
                "No reasoning was recorded for this determination. The verdict "
                "above rests on the criteria table and the census, not on a "
                "narrative judgment."
            )
