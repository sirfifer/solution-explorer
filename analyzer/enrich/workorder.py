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

__all__ = ["WorkOrder", "WorkOrderOutcome", "EXPECTED_EFFECTS", "parse_work_orders"]

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
