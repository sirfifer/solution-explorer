"""P2, the enrichment ladder: one contract, three rungs, and an honest terminal.

``ENRICHMENT-ENGINE.md`` section 2 and section 4. Rung 2a writes everything on
the cheapest tier, weighted by navigation importance. Rung 2b takes only the
items the contract failed, receives what 2a already wrote plus the specific
named gaps, and closes those. Rung 2c takes what two rungs could not ground and
either resolves it or declares an **honest gap**, a visible "this could not be
established, and here is why" in the product itself.

Four properties this module exists to guarantee, each of which has a test:

1. **The ladder never redoes work that succeeded.** A higher rung receives the
   lower rung's attempt plus the failed questions, never a blank assignment.
   That is a property of the prompt, so it is asserted against the prompt.

2. **Climbing can only add or correct, never delete.** A higher rung's payload
   is merged OVER the lower rung's rather than replacing it. Without the merge, a
   rung that answered three questions well and returned a thinner block on the
   next pass would silently lose the two good answers it was never asked about,
   which would make climbing a risk rather than an improvement.

3. **The ladder terminates.** There is no fourth rung and no loop. What Fable
   cannot ground becomes an honest gap in the product, never a faked answer.

4. **Importance decides who goes first.** Under a cost ceiling this is what
   separates a partial run that covered the components a reader needs from one
   that covered whatever the partitioner happened to emit first.

Everything here runs against the injectable invoker seam. No phase in this module
knows what a model is beyond "something that turns a prompt into text".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from ..derive.importance import ImportanceRanking, rank_components, store_ranking
from .contract import (
    Census,
    ContractState,
    build_census,
    split_contract_payload,
    state_from_block,
)
from .engine import _clean_component_payload, _clean_relationship_payload, _parse_json_object
from .evidence import EvidenceValidator
from .partition import Partition, flatten_components, plan_partitions
from .pipeline import PhaseResult, RunContext
from .prompts import build_contract_partition_prompt
from .provenance import stamp_enrichment

__all__ = [
    "CONTRACT_TARGET_KIND",
    "LadderPhase",
    "LadderOutcome",
    "escalation_assignment",
    "build_escalation_prompt",
    "merge_payloads",
    "order_partitions",
]

# Contract states live as their own enrichment rows so they reach the store and
# the Run Report without ever touching the product payload.
CONTRACT_TARGET_KIND = "contract-state"

# How many escalated items share one higher-rung call. Escalations are few by
# design, and a per-item call would pay the full context overhead for each. Five
# amortizes that without diluting attention across a crowd of unrelated gaps.
DEFAULT_ESCALATION_BATCH = 5


@dataclass
class LadderOutcome:
    """What the ladder did, in the shape the Run Report and P5 consume."""

    census: Census = field(default_factory=Census)
    states: dict[tuple[str, str], ContractState] = field(default_factory=dict)
    payloads: dict[tuple[str, str], dict] = field(default_factory=dict)
    ranking: Optional[ImportanceRanking] = None
    escalated: list[str] = field(default_factory=list)
    residue: list[str] = field(default_factory=list)
    honest_gaps: list[ContractState] = field(default_factory=list)
    parser_findings: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    rung_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "census": self.census.to_dict(),
            "escalated": list(self.escalated),
            "residue": list(self.residue),
            "honest_gaps": [s.to_dict() for s in self.honest_gaps],
            "parser_findings": list(self.parser_findings),
            "rung_counts": dict(self.rung_counts),
            "notes": list(self.notes),
        }


def merge_payloads(lower: Optional[dict], higher: Optional[dict]) -> dict:
    """Merge a higher rung's payload over a lower rung's. Additive, never lossy.

    A key the higher rung did not speak to keeps the lower rung's value. This is
    what makes rule 8 real: rewriting success is waste, and silently dropping it
    is worse than waste.
    """
    out = dict(lower or {})
    for key, value in (higher or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        out[key] = value
    return out


def _merge_contract_blocks(lower: dict, higher: dict) -> dict:
    """Merge contract blocks so an unanswered question keeps its earlier answer."""
    out = dict(lower or {})
    higher = higher or {}
    answers = dict((lower or {}).get("answers") or {})
    for question, answer in (higher.get("answers") or {}).items():
        answers[question] = answer
    out.update({k: v for k, v in higher.items() if k != "answers"})
    out["answers"] = answers
    # Parser-first findings accumulate across rungs: each rung asks the question
    # independently and a later answer does not retract an earlier one.
    findings = list((lower or {}).get("parser_first") or [])
    for item in higher.get("parser_first") or []:
        if item not in findings:
            findings.append(item)
    out["parser_first"] = findings
    return out


def escalation_assignment(rung: str, terminal: bool = False) -> str:
    """The opening instruction for a higher rung. Never a blank assignment."""
    if terminal:
        return (
            "You are the LAST rung of an enrichment ladder. Two tiers before you "
            "attempted these items and could not ground them; their attempts and "
            "the specific questions they failed are below.\n\n"
            "For each item, do one of exactly two things:\n"
            "  1. GROUND IT. Answer the named questions with evidence you can "
            "cite, using the deeper reading the previous rungs did not do.\n"
            "  2. DECLARE AN HONEST GAP. Say plainly that it could not be "
            "established, and why, in the 'honest_gaps' key: a list of "
            "{\"question\": \"...\", \"why\": \"...\"} entries. The 'why' is shown "
            "to readers of the map, so write it for them: what specifically "
            "defeated three attempts, in one sentence.\n\n"
            "There is no rung after you and there is no loop. A gap you declare "
            "honestly becomes a visible part of an honest map, which is the "
            "correct outcome. A gap you paper over with a plausible sentence "
            "becomes a lie the map tells with confidence. Declare the gap."
        )
    return (
        "You are a HIGHER RUNG of an enrichment ladder. A previous tier already "
        "worked these items. Its attempt and the specific questions it failed are "
        "below.\n\n"
        "For each item, in this order:\n"
        "  1. ADJUDICATE what the previous rung wrote. Where you agree, keep it "
        "as it is: repeat it back unchanged. Do not rewrite an answer that was "
        "already right, and do not reword it to sound like yours.\n"
        "  2. CORRECT anything that is wrong, and say so.\n"
        "  3. CLOSE the named failed questions, which is why the item reached "
        "you. Each closure needs evidence you can cite.\n\n"
        "You are not starting over. Work that succeeded below you is finished "
        "work, and redoing it spends the run's budget on something it already has."
    )


def build_escalation_prompt(
    items: list[dict],
    *,
    rung: str,
    terminal: bool = False,
    brief: Optional[dict] = None,
) -> str:
    """Build one higher-rung prompt over a batch of escalated items.

    Each item carries: the previous attempt (product payload plus contract
    answers), the failed questions with their triggers and notes, and the target's
    facts. The attempt is what makes this an escalation rather than a re-run.
    """
    from .prompts import _CONTRACT_SCHEMA, _GROUNDING_RULE, _PARSER_FIRST_INSTRUCTION

    parts = [
        escalation_assignment(rung, terminal=terminal),
        "",
        _PARSER_FIRST_INSTRUCTION,
        "",
        _GROUNDING_RULE,
        "",
        _CONTRACT_SCHEMA,
        "",
    ]
    if terminal:
        parts += [
            'HONEST GAPS. When you cannot ground a question, add it to the item\'s '
            '"honest_gaps" list in the ai_enhance block:\n'
            '  "honest_gaps": [{"question": "mechanism", "why": "the dispatch '
            'table is generated at build time and no source file contains it"}]\n'
            "Set that answer's status to \"dropped\" with the same reason. An item "
            "with honest gaps is a completed item, not a failed one.",
            "",
        ]
    if brief:
        parts += [
            "SUBJECT BRIEF (what this system is and what its idioms are):",
            json.dumps(brief, indent=2, default=str),
            "",
        ]
    parts += [
        "ITEMS THAT REACHED THIS RUNG. For each, 'previous_attempt' is what the "
        "rung below you wrote and 'failed_questions' is exactly why it climbed:",
        json.dumps(items, indent=2, default=str),
        "",
        "Return a single JSON object shaped "
        '{"components": {"<id>": {...}}, "relationships": {"<key>": {...}}}, '
        "carrying an entry for every item above, each with its contract block. "
        "Return the JSON object now.",
    ]
    return "\n".join(parts)


def order_partitions(
    partitions: Any, ranking: ImportanceRanking
) -> list[Partition]:
    """Order partitions by the importance of the most important component in each.

    Under a cost ceiling this decides what a partial run actually covered: the
    components a reader needs, or whatever the partitioner happened to emit
    first. A partition is ranked by its BEST component rather than its average,
    because one critical component makes a partition worth running even when the
    rest of it is quiet, and averaging would let a crowd of trivia outvote it.

    The tie-break is partition id, so the order stays total and deterministic
    when two partitions carry equally important work.
    """
    return sorted(
        partitions,
        key=lambda p: (
            -max((ranking.score_for(cid) for cid in p.component_ids), default=0.0),
            p.id,
        ),
    )


class LadderPhase:
    """P2: rung 2a over everything, then 2b over the escalations, then 2c."""

    name = "p2_ladder"

    def __init__(self, *, escalation_batch: int = DEFAULT_ESCALATION_BATCH) -> None:
        self.escalation_batch = max(1, escalation_batch)

    # --- entry ---------------------------------------------------------------

    def run(self, ctx: RunContext) -> PhaseResult:
        outcome = LadderOutcome()
        validator = EvidenceValidator(ctx.store, root=ctx.root)
        ranking = rank_components(ctx.store)
        store_ranking(ctx.store, ranking)
        outcome.ranking = ranking

        brief = (ctx.phase_data("p1_orientation") or {}).get("brief")
        components = ctx.arch.get("components", [])
        relationships = ctx.arch.get("relationships", [])
        facts_by_id = {
            c["id"]: c for c in flatten_components(components) if c.get("id")
        }

        partitions = self._ordered_partitions(ctx, components, relationships, ranking)
        if ctx.dry_run:
            return self._plan_only(ctx, partitions, brief, outcome)

        self._rung_2a(ctx, partitions, validator, facts_by_id, brief, outcome)
        self._rung_escalated(
            ctx, validator, facts_by_id, brief, outcome,
            rung="opus", key="p2b_escalated", terminal=False,
        )
        self._rung_escalated(
            ctx, validator, facts_by_id, brief, outcome,
            rung="fable", key="p2c_residue", terminal=True,
        )
        self._finalize(ctx, outcome)

        status = "ok"
        if not outcome.states:
            status = "failed"
            outcome.notes.append("the ladder produced no contract states at all")
        return PhaseResult(
            name=self.name,
            status=status,
            notes=list(outcome.notes),
            data={"ladder": outcome, "census": outcome.census},
        )

    # --- planning ------------------------------------------------------------

    def _ordered_partitions(
        self, ctx: RunContext, components: list, relationships: list,
        ranking: ImportanceRanking,
    ) -> list[Partition]:
        plan = plan_partitions(
            components, relationships,
            max_lines=50_000, max_components=30, min_components=5,
        )
        return order_partitions(plan.partitions, ranking)

    def _plan_only(
        self, ctx: RunContext, partitions: list[Partition], brief, outcome: LadderOutcome
    ) -> PhaseResult:
        preview = []
        for part in partitions:
            prompt = build_contract_partition_prompt(part, ctx.facts, brief=brief)
            preview.append({
                "id": part.id,
                "components": list(part.component_ids),
                "prompt_chars": len(prompt),
                "prompt_tokens_est": len(prompt) // 4,
            })
        outcome.notes.append(
            f"dry run: {len(partitions)} partition(s) planned for rung 2a, "
            "nothing invoked. Rungs 2b and 2c depend on 2a's outcome and cannot "
            "be planned without it."
        )
        return PhaseResult(
            name=self.name, status="ok", notes=list(outcome.notes),
            data={"ladder": outcome, "plan_preview": preview},
        )

    # --- rung 2a -------------------------------------------------------------

    def _rung_2a(
        self, ctx: RunContext, partitions: list[Partition],
        validator: EvidenceValidator, facts_by_id: dict, brief, outcome: LadderOutcome,
    ) -> None:
        invoker = ctx.invoker("p2a_bulk", phase=self.name, rung="2a")
        skipped = 0
        for part in partitions:
            if not ctx.budget.under():
                skipped += 1
                continue
            prompt = build_contract_partition_prompt(part, ctx.facts, brief=brief)
            invoker.targets = len(part.component_ids)
            result = invoker(prompt)
            if not result.ok:
                outcome.notes.append(
                    f"rung 2a partition {part.id} did not return: {result.error}"
                )
                continue
            obj = _parse_json_object(result.text)
            if obj is None:
                outcome.notes.append(
                    f"rung 2a partition {part.id} returned unparseable text"
                )
                continue
            self._absorb(
                ctx, obj, validator, facts_by_id, outcome,
                rung="sonnet",
                component_ids=list(part.component_ids),
                relationship_keys=list(part.relationship_keys),
            )
        if skipped:
            outcome.notes.append(
                f"rung 2a: {skipped} partition(s) not launched, run cost ceiling "
                "reached; the most important partitions ran first"
            )

    # --- rungs 2b and 2c -----------------------------------------------------

    def _rung_escalated(
        self, ctx: RunContext, validator: EvidenceValidator, facts_by_id: dict,
        brief, outcome: LadderOutcome, *, rung: str, key: str, terminal: bool,
    ) -> None:
        pending = [
            state for state in outcome.states.values() if state.state == "escalate"
        ]
        pending.sort(key=lambda s: (s.target_kind, s.target_id))
        if not pending:
            return
        label = [s.target_id for s in pending]
        if terminal:
            outcome.residue = label
        else:
            outcome.escalated = label

        invoker = ctx.invoker(key, phase=self.name, rung=rung)
        for start in range(0, len(pending), self.escalation_batch):
            batch = pending[start : start + self.escalation_batch]
            if not ctx.budget.under():
                outcome.notes.append(
                    f"rung {rung}: {len(pending) - start} item(s) not attempted, "
                    "run cost ceiling reached"
                )
                break
            items = [
                self._escalation_item(ctx, state, facts_by_id, outcome)
                for state in batch
            ]
            prompt = build_escalation_prompt(
                items, rung=rung, terminal=terminal, brief=brief
            )
            invoker.targets = len(batch)
            result = invoker(prompt)
            if not result.ok:
                outcome.notes.append(f"rung {rung} batch did not return: {result.error}")
                continue
            obj = _parse_json_object(result.text)
            if obj is None:
                outcome.notes.append(f"rung {rung} batch returned unparseable text")
                continue
            self._absorb(
                ctx, obj, validator, facts_by_id, outcome,
                rung=rung,
                component_ids=[s.target_id for s in batch if s.target_kind == "component"],
                relationship_keys=[
                    s.target_id for s in batch if s.target_kind == "relationship"
                ],
                terminal=terminal,
            )

        if terminal:
            # Anything still asking to climb after the last rung is an honest gap
            # by construction: there is nowhere left to send it, and the design
            # forbids both a fake answer and an infinite loop.
            for state in outcome.states.values():
                if state.state == "escalate":
                    state.state = "honest_gap"
                    state.rung = "fable"
                    self._write_honest_gaps(ctx, state, outcome)

    def _escalation_item(
        self, ctx: RunContext, state: ContractState, facts_by_id: dict,
        outcome: LadderOutcome,
    ) -> dict:
        """One escalated item: its facts, the previous attempt, and the named gaps."""
        key = (state.target_kind, state.target_id)
        attempt = outcome.payloads.get(key, {})
        if state.target_kind == "component":
            facts = ctx.facts.component_facts(state.target_id)
        else:
            facts = ctx.facts.relationship_facts(state.target_id)
        return {
            "target_kind": state.target_kind,
            "target_id": state.target_id,
            "facts": facts,
            "previous_attempt": {
                "rung": state.rung,
                "ai_enhance": {
                    k: v for k, v in attempt.items() if k != "contract"
                },
                "contract_answers": (attempt.get("contract") or {}).get("answers", {}),
                "self_declared_state": state.self_declared,
                "declared_confusion": state.declared_confusion,
            },
            "failed_questions": [f.to_dict() for f in state.failed],
        }

    # --- absorbing a response ------------------------------------------------

    def _absorb(
        self, ctx: RunContext, obj: dict, validator: EvidenceValidator,
        facts_by_id: dict, outcome: LadderOutcome, *, rung: str,
        component_ids: list[str], relationship_keys: list[str],
        terminal: bool = False,
    ) -> None:
        """Stamp the product payload and recompute the contract state, per target."""
        comps = obj.get("components") if isinstance(obj.get("components"), dict) else {}
        rels = obj.get("relationships") if isinstance(obj.get("relationships"), dict) else {}

        for target_kind, ids, block in (
            ("component", component_ids, comps),
            ("relationship", relationship_keys, rels),
        ):
            for target_id in ids:
                raw = block.get(target_id)
                if not isinstance(raw, dict):
                    continue
                self._absorb_one(
                    ctx, validator, facts_by_id, outcome,
                    rung=rung, target_kind=target_kind, target_id=target_id,
                    raw=raw, terminal=terminal,
                )

    def _absorb_one(
        self, ctx: RunContext, validator: EvidenceValidator, facts_by_id: dict,
        outcome: LadderOutcome, *, rung: str, target_kind: str, target_id: str,
        raw: dict, terminal: bool,
    ) -> None:
        key = (target_kind, target_id)
        previous_state = outcome.states.get(key)
        previous_payload = outcome.payloads.get(key, {})

        product, contract_block = split_contract_payload(raw)
        merged_product = merge_payloads(
            {k: v for k, v in previous_payload.items() if k != "contract"}, product
        )
        merged_contract = _merge_contract_blocks(
            previous_payload.get("contract") or {}, contract_block
        )

        facts = (
            facts_by_id.get(target_id, {}) if target_kind == "component" else {}
        )
        state = state_from_block(
            target_kind=target_kind,
            target_id=target_id,
            rung=rung,
            block=merged_contract,
            facts=facts,
            validator=validator,
            previous=previous_state,
        )

        # The terminal rung's declared honest gaps close the questions they name,
        # so an item that honestly cannot answer is finished rather than stuck.
        declared_gaps = merged_product.get("honest_gaps")
        if terminal and isinstance(declared_gaps, list) and declared_gaps:
            named = {
                str(g.get("question"))
                for g in declared_gaps
                if isinstance(g, dict) and g.get("question")
            }
            state.failed = [f for f in state.failed if f.question not in named]
            state.state = "honest_gap" if not state.failed else "escalate"
            if not state.failed:
                state.rung = "fable"

        outcome.payloads[key] = dict(merged_product, contract=merged_contract)
        outcome.states[key] = state
        outcome.rung_counts[rung] = outcome.rung_counts.get(rung, 0) + 1

        for finding in state.parser_first:
            entry = {
                "target_kind": target_kind, "target_id": target_id,
                "rung": rung, "finding": finding,
            }
            if entry not in outcome.parser_findings:
                outcome.parser_findings.append(entry)

        self._stamp(ctx, target_kind, target_id, merged_product, state)

    def _write_honest_gaps(
        self, ctx: RunContext, state: ContractState, outcome: LadderOutcome
    ) -> None:
        """Make an unresolved item's gaps visible in the product, with reasons.

        This is the no-theater rule made concrete: the map says what it could not
        establish instead of quietly omitting the question.
        """
        key = (state.target_kind, state.target_id)
        payload = outcome.payloads.get(key)
        if payload is None:
            return
        gaps = [
            {
                "question": f.question,
                "why": f.note or "three rungs could not ground this claim",
            }
            for f in state.failed
        ]
        if not gaps:
            return
        existing = payload.get("honest_gaps")
        payload["honest_gaps"] = (existing if isinstance(existing, list) else []) + gaps
        self._stamp(ctx, state.target_kind, state.target_id, payload, state)

    def _stamp(
        self, ctx: RunContext, target_kind: str, target_id: str,
        payload: dict, state: ContractState,
    ) -> None:
        """Write the product row and the contract-state row. Two rows, never one.

        The product row goes through the SAME cleaner the bulk pass uses, which is
        what keeps the answer scaffolding out of the product: 'contract' is
        deliberately not in the allowlist that cleaner derives.
        """
        product = {k: v for k, v in payload.items() if k != "contract"}
        if target_kind == "component":
            cleaned = _clean_component_payload(ctx.scorer, product, ctx.clock)
            gaps = product.get("honest_gaps")
            if isinstance(gaps, list) and gaps:
                cleaned["honest_gaps"] = gaps
        else:
            cleaned = _clean_relationship_payload(ctx.scorer, product, ctx.clock)
        stamp_enrichment(
            ctx.store, target_kind, target_id, cleaned,
            digest_index=ctx.index, commit_sha=ctx.commit_sha, clock=ctx.clock,
        )
        contract_row = dict(state.to_dict())
        contract_row["answers"] = (payload.get("contract") or {}).get("answers", {})
        stamp_enrichment(
            ctx.store, CONTRACT_TARGET_KIND, f"{target_kind}:{target_id}", contract_row,
            digest_index=ctx.index, commit_sha=ctx.commit_sha, clock=ctx.clock,
        )

    # --- finish --------------------------------------------------------------

    def _finalize(self, ctx: RunContext, outcome: LadderOutcome) -> None:
        outcome.census = build_census(list(outcome.states.values()))
        outcome.honest_gaps = outcome.census.honest_gaps
        ctx.store.commit()
        counts = ", ".join(
            f"{state}={count}" for state, count in outcome.census.by_state.items()
        )
        outcome.notes.append(f"census: {counts or 'nothing enriched'}")
        if outcome.census.unresolved:
            outcome.notes.append(
                f"{len(outcome.census.unresolved)} item(s) still asking to climb "
                "after the last rung; recorded as unresolved, not as grounded"
            )
