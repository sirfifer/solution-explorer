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
from .orientation import Criterion, CriterionVerdict, universal_criteria
from .pipeline import PhaseResult, RunContext
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
        """Did anything measurably change? Judgment does not get a vote here."""
        return bool(self.measured_delta.get("changed"))

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
        without_reason = [
            s.target_id for s in gaps
            if not any((f.note or "").strip() for f in s.failed)
        ]
        verdict.evidence = [f"{len(gaps)} honest gap(s)"]
        verdict.verdict = "met" if not without_reason else "unmet"
        verdict.reasoning = (
            f"all {len(gaps)} honest gap(s) carry a reason a reader can act on"
            if not without_reason
            else f"{len(without_reason)} honest gap(s) carry no reason, which is a "
            "silence dressed as a disclosure"
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

Work from what you are given below. Do not ask for a re-read of the components:
the census is the record of what was established about them, and it is what you
are judging.
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
) -> str:
    parts = [
        "You are deciding whether an automated map of a software system is good "
        "enough to publish, or whether there is room you know how to close.",
        "",
        _DETERMINATION_CONTRACT,
        "",
    ]
    if forced_round:
        parts += [
            "POLICY: this run must carry out at least one improvement round even "
            "if you judge the map done. That is deliberate, and it is how the "
            "tuning that later decides 'iterate or not' gets learned. So give a "
            "REAL improvement_target and a real work order: name the thing you "
            "would most want better, not the cheapest thing to say. A round with "
            "no genuine target is worse than no round, because it teaches nothing "
            "and still costs the run.",
            "",
        ]
    if brief:
        parts += ["THE SUBJECT BRIEF:", json.dumps(brief, indent=2, default=str), ""]
    parts += [
        "THE CRITERIA YOU MUST ANSWER (set by the orientation pass before any "
        "enrichment ran, so they are not shaped by what happened to be easy):",
        json.dumps([c.to_dict() for c in criteria], indent=2, default=str),
        "",
        "THE ITEM CENSUS (what was actually established, per target):",
        json.dumps(census, indent=2, default=str),
        "",
    ]
    if adjudication:
        parts += [
            "WHAT INDEPENDENT ADJUDICATION FOUND:",
            json.dumps(adjudication, indent=2, default=str),
            "",
        ]
    if synthesis:
        parts += [
            "THE STORY AND THE LENSES:",
            json.dumps(synthesis, indent=2, default=str),
            "",
        ]
    if rounds_so_far:
        parts += [
            "IMPROVEMENT ROUNDS ALREADY RUN, and what they actually changed. A "
            "round that changed nothing is evidence about the next one:",
            json.dumps(rounds_so_far, indent=2, default=str),
            "",
        ]
    parts += [budget_note, "", "Return the JSON object now."]
    return "\n".join(parts)


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
        mechanical: dict[str, CriterionVerdict] = {}
        for criterion in criteria:
            if criterion.universal:
                verdict = evaluate_universal(
                    criterion, census=census, adjudication=adjudication
                )
                if verdict is not None:
                    mechanical[criterion.id] = verdict

        policy = ctx.policy.iteration.normalized()
        ctx.descend = make_descender(ctx, ladder)

        round_number = 0
        judged = self._judge(
            ctx, outcome, criteria, census, adjudication, synthesis, brief,
            forced_round=policy.min_rounds > 0,
        )
        self._merge_verdicts(outcome, criteria, mechanical, judged)

        while round_number < policy.max_rounds:
            forced = round_number < policy.min_rounds
            wants_more = outcome.verdict == "not-done"
            if not forced and not wants_more:
                break
            if not ctx.budget.under():
                outcome.notes.append(
                    f"round {round_number + 1} not run: run cost ceiling reached"
                )
                break
            round_number += 1
            round_ = self._run_round(
                ctx, outcome, ladder, census, judged, number=round_number, forced=forced
            )
            outcome.rounds.append(round_)
            if not round_.ran:
                break
            census = self._census(ctx, ladder=ladder)
            judged = self._judge(
                ctx, outcome, criteria, census, adjudication, synthesis, brief,
                forced_round=False,
                rounds_so_far=[r.to_dict() for r in outcome.rounds],
            )
            self._merge_verdicts(outcome, criteria, mechanical, judged)

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
            census=census.to_dict() if census is not None else {},
            adjudication=adjudication.to_dict() if adjudication is not None else None,
            synthesis=synthesis.to_dict() if synthesis is not None else None,
            brief=brief.to_dict() if brief is not None else None,
            forced_round=forced_round,
            rounds_so_far=rounds_so_far or [],
            budget_note=budget_note,
        )
        invoker = ctx.invoker("p5_determination", phase=self.name, targets=1)
        result = invoker(prompt)
        if not result.ok:
            outcome.notes.append(f"determination did not return: {result.error}")
            return {}
        obj = _parse_json_object(result.text)
        if obj is None:
            outcome.notes.append("determination returned unparseable text")
            return {}
        verdict = str(obj.get("verdict") or "").strip().lower()
        if verdict in ("done", "not-done"):
            outcome.verdict = verdict
        outcome.reasoning = str(obj.get("reasoning") or "").strip()
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

        # Compare the contract STATE, not the terminal key. An item re-grounded
        # by a work order changes rung, and counting that as a measured gain
        # would let a round that improved nothing claim it improved something,
        # which is precisely the false positive the no-gain record exists to
        # prevent.
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
        round_.measured_delta = {
            "changed": len(changed),
            "targets": sorted(changed),
            "state_changes": changed,
            "rung_moves": rung_moves,
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
        """State and rung per target. Only the state decides whether a round gained."""
        if ladder is None:
            return {}
        return {
            key[1]: {"state": state.state, "rung": state.rung}
            for key, state in ladder.states.items()
        }

    # --- settle ----------------------------------------------------------------

    def _settle(self, outcome: DeterminationOutcome, census) -> None:
        """Reconcile the verdict with what the criteria and the rounds actually say."""
        unmet = [v for v in outcome.verdicts if v.verdict == "unmet"]

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
        if outcome.verdict == "done" and unmet:
            outcome.verdict = "done-with-reservations"
            outcome.notes.append(
                f"verdict qualified: {len(unmet)} criterion/criteria were not met "
                + "(" + ", ".join(v.criterion_id for v in unmet) + ")"
            )
        if not outcome.reasoning:
            outcome.reasoning = (
                "No reasoning was recorded for this determination. The verdict "
                "above rests on the criteria table and the census, not on a "
                "narrative judgment."
            )
