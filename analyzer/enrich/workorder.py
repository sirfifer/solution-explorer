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
    cost_usd: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def changed_anything(self) -> bool:
        return any(self.state_changes.values())

    def to_dict(self) -> dict:
        return {
            **self.order.to_dict(),
            "outcome": {
                "executed": self.executed,
                "targets_attempted": self.targets_attempted,
                "state_changes": dict(self.state_changes),
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

Answer the completeness contract for each component in scope, THROUGH THIS LENS.
Where the existing answers already satisfy the order, omit them:
an order is not a licence to redo finished work. Return only changed fields or answers for
this lens.

Do NOT propose further work orders. This is the only level of follow-up there is,
and anything you would want a second order for belongs in your answers here.
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
    from .compact import normalize_compact_response, response_budget_bytes
    from .evidence import EvidenceValidator
    from .ladder import LadderOutcome, LadderPhase
    from .partition import flatten_components, plan_partitions
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
    validator.attach_facts({
        cid: ctx.facts.component_facts(cid) for cid in facts_by_id
    })
    scope_set = set(scope)
    before = {
        key: {"state": state.state, "terminal": state.terminal}
        for key, state in shared.states.items()
        if key[1] in scope_set
    }

    plan = plan_partitions(
        ctx.arch.get("components", []),
        ctx.arch.get("relationships", []),
        include_ids=scope,
    )
    if not plan.partitions:
        outcome.notes.append("not executed: nothing in scope survived partitioning")
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

    for partition in plan.partitions:
        if not ctx.budget.under():
            outcome.notes.append("stopped early: run cost ceiling reached")
            break
        component_ids = [c for c in partition.answered_component_ids if c in scope_set]
        if not component_ids:
            continue
        items = []
        for cid in component_ids:
            payload = shared.payloads.get(("component", cid), {})
            contract = payload.get("contract") if isinstance(payload, dict) else {}
            items.append({
                "wire": "work-order/v1",
                "target_kind": "component",
                "target_id": cid,
                "facts": ctx.facts.component_facts(cid),
                "current_product": {
                    k: v for k, v in payload.items() if k != "contract"
                } if isinstance(payload, dict) else {},
                "established": (contract or {}).get("answers", {}),
                "todo": ["apply the scoped lens; emit only changed fields or answers"],
            })
        prompt = build_compact_escalation_prompt(
            items, terminal=False, assignment=assignment
        )
        output_budget = response_budget_bytes(components=len(component_ids))
        invoker = ctx.invoker(
            "workorder", phase="work_order", rung=order.issued_by,
            targets=len(component_ids), output_budget_bytes=output_budget,
        )
        result = invoker(prompt)
        outcome.targets_attempted += len(component_ids)
        if not result.ok:
            outcome.notes.append(f"partition did not return: {result.error}")
            continue
        from .engine import _parse_json_object

        obj = _parse_json_object(result.text)
        if obj is None:
            outcome.notes.append("partition returned unparseable text")
            continue
        response_bytes = len(result.text.encode("utf-8"))
        if response_bytes > output_budget:
            outcome.notes.append(
                f"partition response exceeded compact budget: "
                f"{response_bytes} > {output_budget} UTF-8 bytes"
            )
            continue
        obj = normalize_compact_response(
            obj, facts=ctx.facts, component_ids=component_ids,
        )
        # One level of federation, enforced structurally: the absorber reads
        # components and relationships and nothing else, so a response that
        # proposes further orders has proposed them into a void.
        phase._absorb(
            ctx, obj, validator, facts_by_id, shared,
            rung=executing_rung,
            component_ids=component_ids,
            relationship_keys=[],
        )
        outcome.executed = True
        ctx.store.commit()

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
    outcome.cost_usd = ctx.budget.spent - spent_before
    if outcome.executed and not outcome.state_changes:
        outcome.notes.append(
            "executed and changed no contract state; the order cost budget and "
            "moved nothing"
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
