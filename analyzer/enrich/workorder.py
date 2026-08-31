"""The work order: one shape for every piece of work that descends the ladder.

``ENRICHMENT-ENGINE.md`` section 4.6. P4 issues one when a discovered lens is
worth digging into; P5 issues one when the determination says "not done" and
knows what would close the gap. Both use the same shape, both are executed the
same way, and both send their results back through the same contract and the same
adjudication the work would have faced the first time.

**An order must be designed to change the result.** "Not done" is only legal with
instructions that would change something, never "look again". The
``expected_effect`` field is what enforces that: it names which instrument should
move (form, truth or utility), so an order that cannot say what it would change
is visibly not an order.

**One level of federation, capped, logged.** An order cannot spawn another order.
Without that rule a determination that keeps finding more to do would recurse
until the budget stopped it, and a budget is a bad place to discover a design
does not terminate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = [
    "WorkOrder",
    "WorkOrderOutcome",
    "EXPECTED_EFFECTS",
    "parse_work_orders",
    "execute_work_order",
    "make_descender",
    "WORK_ORDER_ASSIGNMENT",
]

# The three instruments a change can claim to move (design section 6). Any claim
# that a change "worked" must name one of these.
EXPECTED_EFFECTS = ("form", "truth", "utility")

# A repair prompt carries the original product, contract answers, independent
# failures, and the deterministic evidence envelope for every target.  It is
# materially denser than a bulk 2a prompt, so reuse the ladder's measured
# higher-rung batch of five rather than allowing the ordinary partitioner's
# 30-component/40-relationship shape.  The 2026-08-27 UnaMentis canary proved
# the distinction: a 24-target order produced an unparseable response and its
# retry repurchased the same oversized prompt.  This is a quality bulkhead, not
# an output ceiling; every target is still attempted in a smaller call.
WORK_ORDER_TARGET_BATCH = 5


@dataclass
class WorkOrder:
    """A scoped, bounded assignment sent back down the ladder."""

    scope: list[str] = field(default_factory=list)
    lens: str = ""
    criteria: str = ""
    expected_effect: str = ""
    budget: dict = field(default_factory=lambda: {"max_cost_usd": 0.0, "max_targets": 0})
    issued_by: str = "P5"
    outcome: Optional[dict] = None

    @property
    def instrument(self) -> Optional[str]:
        """Which of the three instruments this order claims it would move."""
        head = self.expected_effect.split(":", 1)[0].strip().lower()
        return head if head in EXPECTED_EFFECTS else None

    def problems(self) -> list[str]:
        """Why this order is not executable, if it is not. Empty means valid.

        Validated rather than trusted, because an order is the mechanism by which
        a run spends more of the owner's budget. An order that cannot say what it
        would change is the exact thing the "never look again" rule forbids.
        """
        problems: list[str] = []
        if not self.scope:
            problems.append("no scope: an order must name the targets it covers")
        if not self.lens.strip():
            problems.append("no lens: an order must say what angle to look from")
        if not self.criteria.strip():
            problems.append("no criteria: an order must say what would satisfy it")
        if self.instrument is None:
            problems.append(
                "expected_effect must name which instrument moves "
                f"({', '.join(EXPECTED_EFFECTS)}), so 'look again' cannot pass as work"
            )
        if self.max_targets <= 0:
            problems.append("budget.max_targets must be a positive number of targets")
        return problems

    @property
    def valid(self) -> bool:
        return not self.problems()

    @property
    def max_targets(self) -> int:
        try:
            return int(self.budget.get("max_targets") or 0)
        except (TypeError, ValueError):
            return 0

    @property
    def max_cost_usd(self) -> float:
        try:
            return float(self.budget.get("max_cost_usd") or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def to_dict(self) -> dict:
        return {
            "scope": list(self.scope),
            "lens": self.lens,
            "criteria": self.criteria,
            "expected_effect": self.expected_effect,
            "budget": dict(self.budget),
            "issued_by": self.issued_by,
            "outcome": self.outcome,
        }

    @classmethod
    def from_dict(cls, data: Any, *, issued_by: str = "P5") -> WorkOrder:
        data = data if isinstance(data, dict) else {}
        scope = data.get("scope")
        budget = data.get("budget")
        return cls(
            scope=[str(x) for x in scope] if isinstance(scope, list) else [],
            lens=str(data.get("lens") or "").strip(),
            criteria=str(data.get("criteria") or "").strip(),
            expected_effect=str(data.get("expected_effect") or "").strip(),
            budget=budget if isinstance(budget, dict) else {
                "max_cost_usd": 0.0, "max_targets": 0
            },
            issued_by=str(data.get("issued_by") or issued_by),
            outcome=data.get("outcome"),
        )


@dataclass
class WorkOrderOutcome:
    """What executing one order actually did."""

    order: WorkOrder
    executed: bool = False
    targets_attempted: int = 0
    state_changes: dict = field(default_factory=dict)
    payload_changes: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def changed_anything(self) -> bool:
        return bool(self.state_changes or self.payload_changes)

    def to_dict(self) -> dict:
        return {
            **self.order.to_dict(),
            "outcome": {
                "executed": self.executed,
                "targets_attempted": self.targets_attempted,
                "state_changes": dict(self.state_changes),
                "payload_changes": list(self.payload_changes),
                "cost_usd": round(self.cost_usd, 6),
                "changed_anything": self.changed_anything,
                "notes": list(self.notes),
            },
        }


def parse_work_orders(
    raw: Any, *, issued_by: str, cap: int
) -> tuple[list[WorkOrder], list[str]]:
    """Parse and validate a list of orders, capped. Returns (valid, rejections).

    Rejections are returned rather than swallowed: an order the run refused to
    execute is something the Run Report should say, because silently dropping it
    looks identical to never having issued it.
    """
    if not isinstance(raw, list):
        return [], []
    orders: list[WorkOrder] = []
    rejected: list[str] = []
    for index, item in enumerate(raw):
        order = WorkOrder.from_dict(item, issued_by=issued_by)
        problems = order.problems()
        if problems:
            label = order.lens or f"order {index + 1}"
            rejected.append(f"{label}: " + "; ".join(problems))
            continue
        orders.append(order)
    if len(orders) > cap:
        for order in orders[cap:]:
            rejected.append(
                f"{order.lens}: not issued, the per-phase cap of {cap} work "
                "order(s) was already reached"
            )
        orders = orders[:cap]
    return orders, rejected


# --- execution ----------------------------------------------------------------
#
# An order is executed as an ordinary scoped enrichment pass. It is not a special
# path with its own rules: the partitioner's ``include_ids`` filter exists for
# exactly this, the results are absorbed by the same ladder code that absorbed
# the first attempt, and the contract is recomputed the same way. That is what
# "results re-enter through the same contract and the same adjudication they
# would have faced the first time" means in practice.


WORK_ORDER_ASSIGNMENT = """\
You are executing a SCOPED WORK ORDER against a map that has already been
enriched and adjudicated. This is not a re-run and it is not a general pass. You
have been sent back for one reason, stated below, and the map already contains
what the earlier rungs established.

THE LENS: {lens}
WHAT WOULD SATISFY THIS: {criteria}
WHAT SHOULD MEASURABLY CHANGE: {expected_effect}

Answer the completeness contract for each component or relationship in scope,
THROUGH THIS LENS. Return one entry for EVERY target ID in scope, in its matching
components or relationships array. A target whose `failed` list is non-empty
MUST return a changed answer for every question in `todo`; an empty entry for a
named failure is invalid. Only a target with no named failure may return its ID
with no changed fields. Never omit the ID itself.
An order is not a licence to redo finished work. Return only changed fields or
answers for this lens.

Do NOT propose further work orders. This is the only level of follow-up there is,
and anything you would want a second order for belongs in your answers here.

You have no file-reading or repository tools. The supplied facts are the whole
evidence envelope. `source_declarations` contains bounded parser-owned symbol
previews when they exist. Never claim that you read a path merely because an
order asks you to; if the needed declaration or line is absent, preserve the
supported part and record an honest uncertain answer naming the missing fact.
"""


def execute_work_order(
    ctx,
    order: WorkOrder,
    *,
    ladder_outcome=None,
) -> WorkOrderOutcome:
    """Run one order as a scoped pass and report what it actually changed.

    Returns an outcome whose ``state_changes`` is the honest before-and-after of
    the census for the targets in scope. An order that ran and changed nothing is
    recorded as exactly that, because "we did more work" is not the same claim as
    "the map got better", and a determination that cannot tell them apart will
    keep buying rounds that do nothing.
    """
    from .compact import (
        coverage_issues,
        escalation_response_budget_bytes,
        normalize_compact_response,
    )
    from .evidence import EvidenceValidator
    from .ladder import LadderOutcome, LadderPhase
    from .partition import flatten_components
    from .prompts import build_compact_escalation_prompt

    outcome = WorkOrderOutcome(order=order)
    problems = order.problems()
    if problems:
        outcome.notes.append("not executed: " + "; ".join(problems))
        return outcome
    if not ctx.budget.under():
        outcome.notes.append("not executed: run cost ceiling reached")
        return outcome

    scope = list(dict.fromkeys(order.scope))[: order.max_targets]
    if not scope:
        outcome.notes.append("not executed: scope was empty after de-duplication")
        return outcome

    phase = LadderPhase()
    shared = ladder_outcome if ladder_outcome is not None else LadderOutcome()
    if ladder_outcome is not None and shared.states:
        attempted_ids = {target_id for _, target_id in shared.states}
        outside = [target_id for target_id in scope if target_id not in attempted_ids]
        scope = [target_id for target_id in scope if target_id in attempted_ids]
        if outside:
            outcome.notes.append(
                "rejected targets outside the attempted ladder census: "
                + json.dumps(outside)
            )
        if not scope:
            outcome.notes.append(
                "not executed: no work-order target belonged to the attempted "
                "ladder census"
            )
            return outcome
        # Re-adjudication consumes the outcome's order scope. Record the exact
        # effective scope rather than retaining IDs this executor refused.
        outcome.order.scope = list(scope)
    validator = EvidenceValidator(ctx.store, root=ctx.root)
    facts_by_id = {
        c["id"]: c
        for c in flatten_components(ctx.arch.get("components", []))
        if c.get("id")
    }
    # A fact citation validates against the SAME blocks the prompt shows, which
    # are StoreFacts.component_facts(), never the raw arch dicts (the 8df5965
    # lesson). This validator lacked the attachment entirely, so a correct
    # compact fact citation produced during a work order failed closed as
    # "no component in the analyzed set". Found by the cross-session review;
    # present in both working trees until now.
    relationship_keys = {
        f"{row.get('source', '')}|{row.get('target', '')}|{row.get('type', '')}"
        for row in ctx.arch.get("relationships", [])
    }
    validator.attach_facts({
        **{cid: ctx.facts.component_facts(cid) for cid in facts_by_id},
        **{key: ctx.facts.relationship_facts(key) for key in relationship_keys},
    })
    scope_set = set(scope)
    adjudication = (
        (ctx.phase_data("p3_adjudication") or {}).get("adjudication")
    )
    unsupported_by_target: dict[str, list] = {}
    for check in getattr(adjudication, "unsupported", []) or []:
        target_id = str(getattr(check, "target_id", "") or "")
        if target_id in scope_set:
            unsupported_by_target.setdefault(target_id, []).append(check)
    before = {
        key: {"state": state.state, "terminal": state.terminal}
        for key, state in shared.states.items()
        if key[1] in scope_set
    }
    before_payloads = {
        key: json.dumps(value, sort_keys=True, default=str)
        for key, value in shared.payloads.items()
        if key[1] in scope_set
    }

    # Work-order items are self-contained evidence envelopes. Repartitioning
    # them by architecture boundary before batching defeated the measured
    # five-target quality bulkhead: a 17-target live repair became 17 separate
    # calls, each repaying provider reasoning and the stable contract. Preserve
    # the issued scope order and batch those exact targets directly.
    ordered_targets: list[tuple[str, str]] = []
    unknown_targets: list[str] = []
    for target_id in scope:
        if target_id in facts_by_id:
            ordered_targets.append(("component", target_id))
        elif target_id in relationship_keys:
            ordered_targets.append(("relationship", target_id))
        else:
            unknown_targets.append(target_id)
    if unknown_targets:
        outcome.notes.append(
            "work-order targets absent from the derived map: "
            + json.dumps(unknown_targets)
        )
    if not ordered_targets:
        outcome.notes.append("not executed: nothing in scope matched the derived map")
        return outcome

    assignment = WORK_ORDER_ASSIGNMENT.format(
        lens=order.lens, criteria=order.criteria,
        expected_effect=order.expected_effect,
    )
    # The contract state's rung records WHICH TIER grounded an item, so a work
    # order stamps the tier that actually executed it, not the phase that issued
    # it. Recording "p5" there would claim the determination phase did enrichment
    # work it never did, and would make the census unreadable.
    executing_rung = ctx.policy.model_for("workorder").model or "workorder"
    spent_before = ctx.budget.spent

    target_batches: list[tuple[list[str], list[str]]] = []
    for start in range(0, len(ordered_targets), WORK_ORDER_TARGET_BATCH):
        batch = ordered_targets[start:start + WORK_ORDER_TARGET_BATCH]
        target_batches.append((
            [target_id for kind, target_id in batch if kind == "component"],
            [target_id for kind, target_id in batch if kind == "relationship"],
        ))

    for component_ids, partition_relationship_keys in target_batches:
        if not ctx.budget.under():
            outcome.notes.append("stopped early: run cost ceiling reached")
            break
        if not component_ids and not partition_relationship_keys:
            continue
        pending_components = component_ids
        pending_relationships = partition_relationship_keys
        for coverage_attempt in range(2):
            items = []
            pending_targets = [
                *(('component', cid) for cid in pending_components),
                *(('relationship', key) for key in pending_relationships),
            ]
            for target_kind, target_id in pending_targets:
                payload = shared.payloads.get((target_kind, target_id), {})
                contract = payload.get("contract") if isinstance(payload, dict) else {}
                answers = (contract or {}).get("answers", {})
                current_state = shared.states.get((target_kind, target_id))
                failed = []
                failed_questions: set[str] = set()
                # Honest gaps are terminal for the ordinary ladder, not dead
                # data.  P5 may issue a deliberately richer repair order for
                # them, and that order must receive the exact failed questions
                # just as an unresolved/escalating item does.  Restricting this
                # to ``escalate`` turned a five-question honest gap into the
                # generic "apply the lens" fallback, so the provider could
                # return one field and silently leave four failures untouched.
                if current_state is not None and current_state.state in {
                    "escalate", "honest_gap",
                }:
                    for failure in current_state.failed:
                        question = str(failure.question or "")
                        if not question or question in failed_questions:
                            continue
                        answer = answers.get(question, {}) if isinstance(answers, dict) else {}
                        failed.append({
                            "question": question,
                            "trigger": str(failure.trigger or "E2"),
                            "claim": str(answer.get("claim") or "")
                            if isinstance(answer, dict) else "",
                            "evidence": list(answer.get("evidence") or [])
                            if isinstance(answer, dict) else [],
                            "note": str(failure.note or ""),
                        })
                        failed_questions.add(question)
                for check in unsupported_by_target.get(target_id, []):
                    question = str(getattr(check, "question", "") or "")
                    if not question or question in failed_questions:
                        continue
                    answer = answers.get(question, {}) if isinstance(answers, dict) else {}
                    failed.append({
                        "question": question,
                        "trigger": "E2",
                        "claim": str(getattr(check, "claim", "") or ""),
                        "evidence": (
                            list(answer.get("evidence") or [])
                            if isinstance(answer, dict) else []
                        ),
                        "note": str(getattr(check, "reason", "") or ""),
                    })
                    failed_questions.add(question)
                established = {
                    question: {
                        "claim": value.get("claim"),
                        "cited": [
                            phase._evidence_reference(item)
                            for item in (value.get("evidence") or [])[:3]
                            if isinstance(item, dict)
                        ],
                    }
                    for question, value in answers.items()
                    if isinstance(value, dict) and question not in failed_questions
                } if isinstance(answers, dict) else {}
                items.append({
                    "wire": "work-order/v1",
                    "target_kind": target_kind,
                    "target_id": target_id,
                    "facts": (
                        ctx.facts.component_facts(target_id)
                        if target_kind == "component"
                        else ctx.facts.relationship_facts(target_id)
                    ),
                    "current_product": {
                        k: v for k, v in payload.items() if k != "contract"
                    } if isinstance(payload, dict) else {},
                    "established": established,
                    "failed": failed,
                    "todo": (
                        [item["question"] for item in failed]
                        if failed else
                        ["apply the scoped lens; emit only changed fields or answers"]
                    ),
                })
            attempt_assignment = assignment
            if coverage_attempt:
                attempt_assignment += (
                    "\nCOVERAGE CORRECTION: the prior response did not complete these exact "
                    f"target IDs: {json.dumps([target_id for _, target_id in pending_targets])}. "
                    "Return each ID exactly once in its matching components or "
                    "relationships array, with a changed answer for every listed "
                    "failed question. Do not repeat any target already banked."
                )
            prompt = build_compact_escalation_prompt(
                items, terminal=False, assignment=attempt_assignment
            )
            output_budget = escalation_response_budget_bytes(
                components=len(pending_components),
                relationships=len(pending_relationships),
            )
            invoker = ctx.invoker(
                "workorder", phase="work_order", rung=order.issued_by,
                targets=len(pending_targets), output_budget_bytes=output_budget,
            )
            result = invoker(prompt)
            outcome.targets_attempted += len(pending_targets)
            if not result.ok:
                outcome.notes.append(f"partition did not return: {result.error}")
                break
            from .engine import _parse_json_object

            obj = _parse_json_object(result.text)
            if obj is None:
                outcome.notes.append("partition returned unparseable text")
                break
            response_bytes = len(result.text.encode("utf-8"))
            if response_bytes > output_budget:
                outcome.notes.append(
                    f"partition response exceeded compact budget: "
                    f"{response_bytes} > {output_budget} UTF-8 bytes"
                )
                break
            # Canonical object maps remain the compatibility seam for injected
            # providers and stored replays. Live compact arrays receive the same
            # field-level validation and sibling salvage as the ordinary ladder.
            if not (
                isinstance(obj.get("components"), dict)
                or isinstance(obj.get("relationships"), dict)
            ):
                from .compact import salvage_compact_response, validate_compact_response
                from .prompts import split_cached_prompt

                prefix, user = split_cached_prompt(prompt)
                obj, schema_errors, stripped = validate_compact_response(
                    obj, prefix=prefix, user=user
                )
                if schema_errors:
                    salvaged, rejected = salvage_compact_response(
                        obj, prefix=prefix, user=user
                    )
                    if salvaged is None:
                        outcome.notes.append(
                            "compact schema rejected the work-order response: "
                            + "; ".join(schema_errors[:8])
                        )
                        break
                    obj = salvaged
                    outcome.notes.append(
                        "salvaged valid work-order siblings; rejected "
                        + ", ".join(rejected[:8])
                    )
                elif stripped:
                    outcome.notes.append(
                        "stripped unknown compact fields: "
                        + ", ".join(stripped[:8])
                    )
            issues = coverage_issues(
                obj,
                component_ids=pending_components,
                relationship_keys=pending_relationships,
            )
            obj = normalize_compact_response(
                obj,
                facts=ctx.facts,
                component_ids=pending_components,
                relationship_keys=pending_relationships,
            )
            for cid in issues["duplicate_components"]:
                (obj.get("components") or {}).pop(cid, None)
            for key in issues["duplicate_relationships"]:
                (obj.get("relationships") or {}).pop(key, None)
            # Exact ID coverage is necessary but not sufficient for a repair.
            # A live provider returned all nine requested IDs while seven were
            # empty objects, so the old check called the response complete and
            # silently banked seven known failures unchanged.  When P3 supplied
            # a named failure, require an actual product or answer delta and
            # retry only the semantically empty siblings.
            incomplete_components = []
            incomplete_relationships = []
            incomplete_questions: dict[str, list[str]] = {}
            for target_kind, target_id in pending_targets:
                branch = (
                    obj.get("components")
                    if target_kind == "component"
                    else obj.get("relationships")
                ) or {}
                block = branch.get(target_id) if isinstance(branch, dict) else None
                contract = block.get("contract") if isinstance(block, dict) else None
                answers = contract.get("answers") if isinstance(contract, dict) else None
                required_questions = {
                    str(item.get("question") or "")
                    for item in next(
                        (
                            prompt_item.get("failed") or []
                            for prompt_item in items
                            if prompt_item.get("target_id") == target_id
                        ),
                        [],
                    )
                    if isinstance(item, dict) and item.get("question")
                }
                answered_questions = {
                    question
                    for question, answer in (answers or {}).items()
                    if isinstance(answer, dict) and (
                        (
                            str(answer.get("status") or "answered") == "answered"
                            and bool(str(answer.get("claim") or "").strip())
                        )
                        or (
                            str(answer.get("status") or "") in {"uncertain", "dropped"}
                            and bool(str(answer.get("reason") or "").strip())
                            and str(answer.get("reason") or "").strip().lower()
                            != "no answer was produced for a required question"
                        )
                    )
                } if isinstance(answers, dict) else set()
                missing_questions = sorted(required_questions - answered_questions)
                product_delta = {
                    key: value for key, value in (block or {}).items()
                    if key != "contract" and value not in (None, "", [], {})
                } if isinstance(block, dict) else {}
                if required_questions and not missing_questions:
                    continue
                if not required_questions and (
                    (isinstance(answers, dict) and answers) or product_delta
                ):
                    continue
                branch.pop(target_id, None)
                if missing_questions:
                    incomplete_questions[target_id] = missing_questions
                if target_kind == "component":
                    incomplete_components.append(target_id)
                else:
                    incomplete_relationships.append(target_id)
            if incomplete_components or incomplete_relationships:
                outcome.notes.append(
                    "work-order targets did not repair every named question: "
                    + json.dumps({
                        target_id: incomplete_questions.get(target_id, [])
                        for target_id in sorted([
                            *incomplete_components, *incomplete_relationships,
                        ])
                    }, sort_keys=True)
                )
            if any(issues.values()):
                outcome.notes.append(
                    "compact coverage violation: " + json.dumps(issues, sort_keys=True)
                )
            # One level of federation, enforced structurally: the absorber reads
            # components and relationships and nothing else, so a response that
            # proposes further orders has proposed them into a void.
            # An ordinary scoped lens cannot demote a previously grounded
            # answer. An independently rejected P3 claim is different: keeping
            # the old claim after the repair honestly says "uncertain" is the
            # quality failure. Absorb each target separately so only named P3
            # failures may become terminal honest gaps; unrelated answers keep
            # the no-demotion protection.
            for target_kind, target_id in pending_targets:
                independently_failed = bool(unsupported_by_target.get(target_id))
                prior_state = before.get((target_kind, target_id), {}).get("state")
                terminal_repair = independently_failed or prior_state in {
                    "escalate", "honest_gap",
                }
                phase._absorb(
                    ctx, obj, validator, facts_by_id, shared,
                    rung=executing_rung,
                    component_ids=[target_id] if target_kind == "component" else [],
                    relationship_keys=[target_id] if target_kind == "relationship" else [],
                    terminal=terminal_repair,
                    reject_demotion=not terminal_repair,
                )
            outcome.executed = True
            ctx.store.commit()
            pending_components = sorted(set(
                issues["missing_components"] + issues["duplicate_components"]
                + incomplete_components
            ))
            pending_relationships = sorted(set(
                issues["missing_relationships"] + issues["duplicate_relationships"]
                + incomplete_relationships
            ))
            if not pending_components and not pending_relationships:
                break
            if coverage_attempt == 0:
                outcome.notes.append(
                    "retrying only omitted/duplicate work-order targets; "
                    "valid siblings remain banked"
                )

    after = {
        key: {"state": state.state, "terminal": state.terminal}
        for key, state in shared.states.items()
        if key[1] in scope_set
    }
    # Changed means the CONTRACT STATE moved. An item re-grounded by an order
    # carries the executing tier's rung, and counting that relabel as a change
    # would let an order that improved nothing report that it improved something.
    outcome.state_changes = {
        key[1]: {
            "before": (before.get(key) or {}).get("terminal"),
            "after": value["terminal"],
        }
        for key, value in sorted(after.items())
        if (before.get(key) or {}).get("state") != value["state"]
    }
    outcome.payload_changes = sorted(
        key[1]
        for key, value in shared.payloads.items()
        if key[1] in scope_set
        and json.dumps(value, sort_keys=True, default=str)
        != before_payloads.get(key)
    )
    outcome.cost_usd = ctx.budget.spent - spent_before
    if outcome.executed and not outcome.changed_anything:
        outcome.notes.append(
            "executed and changed neither contract state nor payload; the order "
            "cost budget and moved nothing"
        )
    ctx.store.commit()
    order.outcome = outcome.to_dict()["outcome"]
    return outcome


def make_descender(ctx, ladder_outcome=None):
    """Build the descent seam the pipeline hands to P4 and P5.

    Returns a callable taking a sequence of orders and returning their outcomes.
    Orders execute in issue order and each one sees the state the previous one
    left, because two orders touching the same component must not both believe
    they are the one that changed it.
    """

    def descend(orders):
        return [
            execute_work_order(ctx, order, ladder_outcome=ladder_outcome)
            for order in orders
        ]

    return descend
