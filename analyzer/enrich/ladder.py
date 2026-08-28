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
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any, Optional

from ..derive.importance import ImportanceRanking, rank_components, store_ranking
from .compact import (
    COMPONENT_CALL_CAP,
    RELATIONSHIP_CALL_CAP,
    coverage_issues,
    normalize_compact_response,
    response_budget_bytes,
)
from .contract import (
    Census,
    ContractState,
    FailedQuestion,
    build_census,
    split_contract_payload,
    state_from_block,
)
from .engine import _clean_component_payload, _clean_relationship_payload, _parse_json_object
from .evidence import EvidenceValidator
from .partition import Partition, flatten_components
from .pipeline import PhaseResult, RunContext
from .prompts import (
    build_compact_component_prompt,
    build_compact_escalation_prompt,
    build_compact_relationship_prompt,
)
from .provenance import stamp_enrichment

__all__ = [
    "CONTRACT_TARGET_KIND",
    "LadderPhase",
    "LadderOutcome",
    "escalation_assignment",
    "build_escalation_prompt",
    "merge_payloads",
    "order_partitions",
    "plan_compact_chunks",
]

# Contract states live as their own enrichment rows so they reach the store and
# the Run Report without ever touching the product payload.
CONTRACT_TARGET_KIND = "contract-state"

# The top-level keys a contract response must carry. Passed to the parser as a
# shape guard so a salvaged fragment can never be mistaken for an answer: text
# that begins mid-object parses into some inner evidence item otherwise, and
# absorbing that would record a partition as answered while storing nothing.
PARTITION_KEYS = ("components", "relationships")


# The ladder's ``rung`` value is the TIER that answered ("sonnet", "opus",
# "fable"), which is what a contract state and the determination's
# "raised_at_rungs" mean by it. That is the wrong name to show a human watching
# a run: "rung opus" says nothing about where in the ladder the work is, and it
# would read "rung fable" for the residue rung, which sounds like a different
# model tier rather than the last step. Progress events carry the ladder
# POSITION instead, derived from the phase key that selected the tier.
_RUNG_DISPLAY = {
    "p2a_bulk": "2a",
    "p2b_escalated": "2b",
    "p2c_residue": "2c",
}


def _rung_label(key: str, fallback: str) -> str:
    """The ladder position a reader recognises, e.g. 2b, not the model name."""
    return _RUNG_DISPLAY.get(key, fallback)

# How many escalated items share one higher-rung call. Escalations are few by
# design, and a per-item call would pay the full context overhead for each. Five
# amortizes that without diluting attention across a crowd of unrelated gaps.
DEFAULT_ESCALATION_BATCH = 5

# The cap-21 rule binds regardless of partition size: the G2 output arithmetic
# both rearchitecture specs adopted prices a component call at targets x
# central block x dispersion against the output ceiling, and 21 is the largest
# count that clears it at the 1.90 dispersion default. Relationships chunk at
# 80. Menus are per target, so chunking cannot disturb them
# (IMPLEMENTATION-DELTA-PROMPT.md section 2.4). The constants live in
# compact.py because the byte-constant JSON schema is bounded by them,
# and are imported at the top of this module.


def plan_compact_chunks(partitions: list[Partition]) -> list[tuple[str, Partition]]:
    """The 2a call plan: (kind, chunk) pairs in dispatch order.

    One function feeds the live rung, the dry-run preview, and the zero-cost
    replay preflight, so the three views of "what will this run ask" cannot
    drift apart. Chunk ids are placeholders; the caller assigns real job ids.
    """
    out: list[tuple[str, Partition]] = []
    for part in partitions:
        component_ids = list(part.answered_component_ids)
        for start in range(0, len(component_ids), COMPONENT_CALL_CAP):
            chunk = component_ids[start : start + COMPONENT_CALL_CAP]
            out.append((
                "component",
                Partition(
                    id=0, component_ids=tuple(chunk),
                    relationship_keys=(), answers_components=True,
                ),
            ))
        relationship_keys = list(part.relationship_keys)
        for start in range(0, len(relationship_keys), RELATIONSHIP_CALL_CAP):
            chunk = relationship_keys[start : start + RELATIONSHIP_CALL_CAP]
            out.append((
                "relationship",
                Partition(
                    id=0, component_ids=part.component_ids,
                    relationship_keys=tuple(chunk), answers_components=False,
                ),
            ))
    return out


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
    # Append-only attempt history.  ``ContractState`` is intentionally the
    # latest verdict, so it cannot also be the forensic record of why an item
    # climbed.  Keeping attempts here preserves those causes after a later rung
    # succeeds and gives the exit report something actionable to learn from.
    transitions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "census": self.census.to_dict(),
            "escalated": list(self.escalated),
            "residue": list(self.residue),
            "honest_gaps": [s.to_dict() for s in self.honest_gaps],
            "parser_findings": list(self.parser_findings),
            "rung_counts": dict(self.rung_counts),
            "transitions": list(self.transitions),
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


def _project_audited_answers(
    target_kind: str, product: dict, contract: dict, state: ContractState,
) -> dict:
    """Make the reader payload an exact projection of its audited atoms.

    Models never get to keep a second, unaudited version of a meaning in the
    product. This matters most at a terminal boundary: a repair may return a
    polished ``help_text`` while honestly marking one of the atoms inside it
    uncertain. Keeping both would publish prose the contract explicitly says
    it cannot support. Supported sibling atoms remain reader-visible, and the
    exact terminal gaps replace any stale gaps from an earlier attempt.
    """
    projected = dict(product)
    answers = contract.get("answers") if isinstance(contract, dict) else {}
    answers = answers if isinstance(answers, dict) else {}

    def answered_claim(question: str) -> str:
        answer = answers.get(question)
        if not isinstance(answer, dict):
            return ""
        if str(answer.get("status") or "answered") != "answered":
            return ""
        return str(answer.get("claim") or "").strip()

    if target_kind == "component":
        audited_prose = ("purpose", "mechanism", "place", "why_matters")
        if any(question in answers for question in audited_prose):
            claims = [answered_claim(question) for question in audited_prose]
            help_text = " ".join(claim for claim in claims if claim)
            if help_text:
                projected["help_text"] = help_text
            else:
                projected.pop("help_text", None)
        if "data_handled" in answers:
            data_handled = answered_claim("data_handled")
            if data_handled:
                projected["data_handled"] = data_handled
            else:
                projected.pop("data_handled", None)
    elif "flow" in answers:
        flow = answered_claim("flow")
        if flow:
            projected["data_flow_description"] = flow
        else:
            projected.pop("data_flow_description", None)

    if state.state == "grounded":
        projected.pop("honest_gaps", None)
    elif state.state == "honest_gap":
        projected["honest_gaps"] = [
            {
                "question": failure.question,
                "why": failure.note
                or "the terminal repair could not validate this claim",
            }
            for failure in state.failed
        ]
    return projected


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
            "You have NO tools: you cannot read files, run commands, or "
            "browse the repository. Everything you may use is already in this "
            "prompt. Do not narrate an intention to go look at anything.\n\n"
            "For each item, do one of exactly two things:\n"
            "  1. GROUND IT. Answer the named questions with evidence you can "
            "cite from the material below.\n"
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
        "below. You have NO tools: you cannot read files or browse the "
        "repository; everything you may use is already in this prompt.\n\n"
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


def _brief_dict(ctx: RunContext) -> Optional[dict]:
    """The P1 brief as plain data, or None when orientation produced nothing.

    Only the parts a rung can act on are passed down. The criteria belong to P5
    and would be noise in a per-partition prompt; the identity, the audience and
    above all the idiom warnings are what change how a rung reads the code.
    """
    brief = (ctx.phase_data("p1_orientation") or {}).get("brief")
    if brief is None:
        return None
    data = brief.to_dict() if hasattr(brief, "to_dict") else dict(brief)
    if not data.get("generated"):
        return None
    return {
        "identity": data.get("identity"),
        "audience": data.get("audience"),
        "what_matters": data.get("what_matters") or [],
        "idiom_warnings": data.get("idiom_warnings") or [],
        "weighting_adjustments": data.get("weighting_adjustments") or [],
    }


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

        brief = _brief_dict(ctx)
        components = ctx.arch.get("components", [])
        relationships = ctx.arch.get("relationships", [])
        facts_by_id = {
            c["id"]: c for c in flatten_components(components) if c.get("id")
        }

        partitions = self._ordered_partitions(ctx, components, relationships, ranking)
        if ctx.max_partitions is not None and len(partitions) > ctx.max_partitions:
            # The smoke-run bound. Ordering is by importance, so the cap keeps
            # the partitions that matter most. Declared loudly: a bounded run
            # must never read as full coverage, and unattempted items appear in
            # no census state at all rather than in a fabricated one.
            outcome.notes.append(
                f"rung 2a: capped to the {ctx.max_partitions} most important "
                f"partition(s) of {len(partitions)} planned (max_partitions); "
                "items in the other partitions were not attempted and appear "
                "in no census state"
            )
            partitions = partitions[: ctx.max_partitions]
        if ctx.dry_run:
            return self._plan_only(ctx, partitions, brief, outcome)

        # The validator must check a "fact" citation against THE SAME blocks the
        # prompt showed the model, which are StoreFacts.component_facts(), not
        # the raw arch component dicts. They are not interchangeable: the fact
        # block carries computed fields (inbound_edges, outbound_edges,
        # file_count) that the arch dict never had. Attaching the arch dicts
        # made every citation of a computed field fail as "the analyzer
        # produced no 'inbound_edges'", which turned correct answers into E2
        # failures, escalated them, and left 94 false honest gaps on the
        # `place` question alone in the 2026-08-26 full build.
        validator.attach_facts({
            **{cid: ctx.facts.component_facts(cid) for cid in facts_by_id},
            **{
                key: ctx.facts.relationship_facts(key)
                for key in (
                    f"{row.get('source', '')}|{row.get('target', '')}|{row.get('type', '')}"
                    for row in relationships
                )
            },
        })
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
        elif any(row.phase == self.name and not row.ok for row in ctx.ledger):
            status = "degraded"
            outcome.notes.append(
                "one or more model calls failed; fallback output was retained but "
                "the phase is degraded, not clean"
            )
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
        # RunContext owns the immutable plan so orientation, the ladder and
        # determination cannot silently reason about different canary slices.
        # Keep the parameters in the signature because this seam is exercised
        # directly by tests and documents what the plan is over.
        del components, relationships, ranking
        return list(ctx.planned_partitions())

    def _plan_only(
        self, ctx: RunContext, partitions: list[Partition], brief, outcome: LadderOutcome
    ) -> PhaseResult:
        # The preview builds the SAME compact prompts the live rung sends
        # (plan_compact_chunks feeds both), so a dry run's sizes are the run's
        # sizes rather than a legacy estimate.
        preview = []
        for index, (kind, part) in enumerate(plan_compact_chunks(partitions)):
            if kind == "component":
                prompt = build_compact_component_prompt(part, ctx.facts, brief=brief)
            else:
                prompt = build_compact_relationship_prompt(part, ctx.facts, brief=brief)
            preview.append({
                "id": index,
                "kind": kind,
                "components": list(part.answered_component_ids),
                "relationships": list(part.relationship_keys),
                "prompt_chars": len(prompt),
                "prompt_tokens_est": len(prompt) // 4,
            })
        outcome.notes.append(
            f"dry run: {len(partitions)} partition(s) planned for rung 2a, "
            "nothing invoked. Rungs 2b and 2c depend on 2a's outcome and cannot "
            "be planned without it."
        )
        # What pulling the trigger translates to, so the launch decision is
        # informed rather than discovered at runtime. The per-call estimate is
        # the first real run's measured 2a average (554s of wall per call);
        # 2b/2c/adjudication/synthesis are unplannable before 2a, so this is a
        # floor and says so.
        measured_call_s = 554
        workers = max(1, int(ctx.policy.max_parallel))
        projected_s = (len(partitions) * measured_call_s) / workers
        limits = [
            f"cost ceiling ${ctx.budget.ceiling:.2f}" if ctx.budget.ceiling is not None else "no cost ceiling",
            (
                f"wall ceiling {ctx.policy.max_wall_minutes:.0f} min"
                if ctx.policy.max_wall_minutes is not None
                else "no wall ceiling"
            ),
            f"max_parallel {workers}",
            f"invoke timeout {ctx.policy.invoke_timeout_s}s",
        ]
        outcome.notes.append(
            f"projection: rung 2a alone is ~{projected_s / 3600:.1f}h of wall at "
            f"{workers} worker(s) (measured 554s per call); later phases add to "
            f"this and cannot be planned before 2a. Armed limits: {', '.join(limits)}. "
            f"Watch the run live: {ctx.run_dir / 'ledger.jsonl'}"
        )
        return PhaseResult(
            name=self.name, status="ok", notes=list(outcome.notes),
            data={"ladder": outcome, "plan_preview": preview},
        )

    # --- rung 2a -------------------------------------------------------------


    # --- bounded-parallel invocation ------------------------------------------

    def _invoke_parallel(
        self, ctx: RunContext, jobs: list[tuple], *,
        invoker_key: str, rung: str,
        on_result: Optional[Callable[[int, Optional[dict], Optional[str]], None]] = None,
        describe: Optional[Callable[[int], dict]] = None,
        rung_label: Optional[str] = None,
    ) -> tuple[dict[int, Optional[dict]], dict[int, str], int]:
        """Run independent prompts through a bounded pool, deterministically.

        ``jobs`` is ``(job_id, prompt, target_count, output_budget_bytes)``.
        The fourth item is optional for non-compact callers. Returns parsed payloads
        by job id (None for a failed or unparseable job), error text by job id,
        and how many jobs were never launched because a ceiling tripped.

        The coordinator owns all shared state: workers only invoke and parse.
        Results are collected and the caller absorbs them in job order after
        the pool drains, so a run's stores, census and report are identical
        whatever order the network returned things in; parallelism buys wall
        time, never a different answer.

        The pattern (incremental submission, drain on first-completed, ceiling
        checks at top-up, per-job bulkhead, honest skip accounting) is the
        engine's R2 partition loop, applied to the ladder that had quietly
        dropped it: the first real run executed 76 calls strictly one at a
        time for 10.8 hours.

        ``warm_first`` runs the first job alone before fanning out, so the
        shared prompt prefix lands in the provider cache once instead of
        max_parallel times.
        """
        payloads: dict[int, Optional[dict]] = {}
        errors: dict[int, str] = {}
        pending = list(jobs)
        workers = max(1, min(int(ctx.policy.max_parallel), len(jobs) or 1))

        def _task(job):
            job_id, prompt, targets = job[:3]
            output_budget = int(job[3]) if len(job) > 3 and job[3] else None
            # Announce the unit as it goes in flight, not when it comes back.
            # A model call takes minutes; without this the board has nothing
            # true to say for the whole of that time.
            if describe is not None:
                try:
                    ctx.progress.unit_start(
                        rung=rung_label or rung, unit_id=job_id, **describe(job_id)
                    )
                except Exception:  # noqa: BLE001 - reporting never fails work
                    pass
            invoker = ctx.invoker(
                invoker_key, phase=self.name, rung=rung, targets=targets,
                partition_id=job_id,
                output_budget_bytes=output_budget,
            )
            attempt_prompt = prompt
            last_error = ""
            from .compact import salvage_compact_response, validate_compact_response
            from .prompts import split_cached_prompt

            compact_prefix, compact_user = split_cached_prompt(prompt)
            # A parse failure gets one corrective retry. A structurally valid
            # multi-target response with one malformed entry is different: bank
            # its valid siblings immediately and let only the rejected target
            # climb. Reissuing the whole prompt would repurchase finished work.
            for attempt in range(2):
                result = invoker(attempt_prompt)
                response_bytes = len(result.text.encode("utf-8"))
                parsed_candidate = _parse_json_object(
                    result.text, expect_keys=PARTITION_KEYS
                )
                transport_note = None
                if not result.ok:
                    if parsed_candidate is None:
                        return job_id, None, f"did not return: {result.error}"
                    # Some CLI-side failures occur after the model has authored
                    # usable JSON. Preserve and validate that paid payload while
                    # retaining the failed ledger row for honest completion and
                    # accounting.
                    transport_note = (
                        "recovered JSON payload from nonzero transport exit: "
                        f"{result.error}"
                    )
                if (
                    output_budget is not None
                    and response_bytes > output_budget
                ):
                    # Do not buy a second oversized response.  Shape drift is a
                    # hard efficiency failure, not a parse failure that more
                    # generation can repair.
                    return (
                        job_id, None,
                        f"response exceeded deterministic compact budget: "
                        f"{response_bytes:,} > {output_budget:,} UTF-8 bytes",
                    )
                obj = parsed_candidate
                if obj is not None:
                    # Canonical object maps remain a supported compatibility
                    # boundary for injected providers and stored replays. They
                    # still obey the unconditional call byte budget and exact
                    # coverage checks; compact list responses additionally use
                    # the field-level schema below.
                    if isinstance(obj.get("components"), dict) or isinstance(
                        obj.get("relationships"), dict
                    ):
                        return job_id, obj, transport_note
                    obj, schema_errors, stripped = validate_compact_response(
                        obj, prefix=compact_prefix, user=compact_user
                    )
                    if not schema_errors:
                        note = (
                            "stripped unknown compact fields: " + ", ".join(stripped[:8])
                            if stripped else None
                        )
                        if transport_note:
                            note = transport_note + ("; " + note if note else "")
                        return job_id, obj, note
                    last_error = "compact schema rejected: " + "; ".join(schema_errors[:8])
                    salvaged, rejected = salvage_compact_response(
                        obj, prefix=compact_prefix, user=compact_user
                    )
                    if salvaged is not None:
                        return (
                            job_id, salvaged,
                            f"{last_error}; salvaged valid siblings and rejected "
                            + ", ".join(rejected[:8]),
                        )
                else:
                    last_error = "returned unparseable text"
                if attempt == 0:
                    attempt_prompt = (
                        prompt
                        + "\n\nYour previous response failed deterministic validation: "
                        + last_error
                        + ". Return ONLY one corrected JSON object, starting with { "
                        "and ending with }, with no prose and no markdown fences."
                    )
            failure_path = ctx.run_path("failures", f"{rung}-job-{job_id}.txt")
            try:
                failure_path.write_text(result.text[:2_000_000])
            except OSError:
                pass
            return (
                job_id,
                None,
                f"{last_error} after a corrective retry "
                f"(raw response preserved at failures/{failure_path.name})",
            )

        def _drain(in_flight):
            done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for fut in done:
                job = in_flight.pop(fut)
                try:
                    job_id, obj, err = fut.result()
                except Exception as exc:  # noqa: BLE001 - per-job bulkhead
                    job_id, obj, err = job[0], None, f"raised unexpectedly: {exc}"
                payloads[job_id] = obj
                if err:
                    errors[job_id] = err
                # Bank the work NOW, in the coordinator thread, rather than
                # after the whole pool drains. The 2026-08-25 run held 173
                # partitions in memory and was killed at 31, so the store
                # ended with exactly one row and every completed call was
                # lost. Absorption is safe to do out of order because the
                # partitioner now gives each target exactly one writer per
                # rung, which makes it commutative; before that split a
                # component had 3.52 writers and order decided the answer.
                if on_result is not None:
                    on_result(job_id, obj, err)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            in_flight: dict = {}
            if pending and ctx.policy.warm_first and ctx.budget.under():
                job = pending.pop(0)
                in_flight[pool.submit(_task, job)] = job
                while in_flight:
                    _drain(in_flight)
            while pending and len(in_flight) < workers and ctx.budget.under():
                job = pending.pop(0)
                in_flight[pool.submit(_task, job)] = job
            while in_flight:
                _drain(in_flight)
                while pending and len(in_flight) < workers and ctx.budget.under():
                    job = pending.pop(0)
                    in_flight[pool.submit(_task, job)] = job

        return payloads, errors, len(pending)

    def _rung_2a(
        self, ctx: RunContext, partitions: list[Partition],
        validator: EvidenceValidator, facts_by_id: dict, brief, outcome: LadderOutcome,
    ) -> None:
        # Component and relationship work have different schemas and very
        # different output sizes.  Asking them together forces both through the
        # maximal contract and makes deterministic output budgeting impossible.
        job_meta: dict[int, tuple[str, Partition]] = {}
        component_jobs = []
        relationship_parts: list[tuple[int, Partition]] = []
        next_job = 0
        for kind, chunk_part in plan_compact_chunks(partitions):
            chunk_part = Partition(
                id=next_job, component_ids=chunk_part.component_ids,
                relationship_keys=chunk_part.relationship_keys,
                answers_components=chunk_part.answers_components,
            )
            if kind == "component":
                component_jobs.append((
                    next_job,
                    build_compact_component_prompt(chunk_part, ctx.facts, brief=brief),
                    len(chunk_part.answered_component_ids),
                    response_budget_bytes(
                        components=len(chunk_part.answered_component_ids)
                    ),
                ))
            else:
                # Relationship prompts are built only after every component
                # call has banked, so endpoint context uses the fresh one-line
                # descriptions.  A failed component call falls back
                # deterministically to parser identity; it never blocks the
                # relationship wave.
                relationship_parts.append((next_job, chunk_part))
            job_meta[next_job] = (kind, chunk_part)
            next_job += 1
        pending_notes: dict[int, str] = {}
        # The denominator, before any work starts. Rung 2a is the only rung
        # whose size is known up front; 2b and 2c publish theirs once the rung
        # below has decided what to escalate.
        ctx.progress.plan(
            rung="2a",
            partitions=len(component_jobs) + len(relationship_parts),
            components=sum(len(p.answered_component_ids) for p in partitions),
            relationships=sum(len(p.relationship_keys) for p in partitions),
        )

        def _bank(job_id: int, obj: Optional[dict], err: Optional[str]) -> None:
            """Absorb one partition the moment it lands, in the coordinator."""
            meta = job_meta.get(job_id)
            if meta is None:
                return
            kind, part = meta
            issues = None
            if isinstance(obj, dict):
                issues = coverage_issues(
                    obj,
                    component_ids=part.answered_component_ids,
                    relationship_keys=part.relationship_keys,
                )
                obj = normalize_compact_response(
                    obj, facts=ctx.facts,
                    component_ids=part.answered_component_ids,
                    relationship_keys=part.relationship_keys,
                )
                for cid in issues["duplicate_components"]:
                    (obj.get("components") or {}).pop(cid, None)
                for key in issues["duplicate_relationships"]:
                    (obj.get("relationships") or {}).pop(key, None)
                if any(issues.values()):
                    pending_notes[job_id] = (
                        f"rung 2a call {job_id} compact coverage violation: "
                        + json.dumps(issues, sort_keys=True)
                    )
                if kind == "component":
                    for cid, block in (obj.get("components") or {}).items():
                        if isinstance(block, dict):
                            ctx.facts.set_enriched_description(cid, block.get("description"))
            answered = 0
            if isinstance(obj, dict):
                answered = len(obj.get("components") or {}) + len(
                    obj.get("relationships") or {}
                )
            ctx.progress.unit_end(
                rung="2a", unit_id=job_id, ok=obj is not None,
                answered=answered, detail=err,
            )
            if err:
                pending_notes[job_id] = f"rung 2a partition {job_id} {err}"
            if obj is None:
                for cid in part.answered_component_ids:
                    self._absorb_one(
                        ctx, validator, facts_by_id, outcome,
                        rung="sonnet", target_kind="component", target_id=cid,
                        raw={"contract": {"answers": {}}}, terminal=False,
                    )
                for key in part.relationship_keys:
                    self._absorb_one(
                        ctx, validator, facts_by_id, outcome,
                        rung="sonnet", target_kind="relationship", target_id=key,
                        raw={"contract": {"answers": {}}}, terminal=False,
                    )
                ctx.store.commit()
                return
            self._absorb(
                ctx, obj, validator, facts_by_id, outcome,
                rung="sonnet",
                component_ids=(list(part.answered_component_ids) if kind == "component" else []),
                relationship_keys=(list(part.relationship_keys) if kind == "relationship" else []),
            )
            # Every requested target enters the census, including omissions and
            # duplicates.  Missing work becomes an explicit E1 escalation; it
            # can never vanish and make a partial run look complete.
            if issues:
                for cid in issues["missing_components"] + issues["duplicate_components"]:
                    self._absorb_one(
                        ctx, validator, facts_by_id, outcome,
                        rung="sonnet", target_kind="component", target_id=cid,
                        raw={"contract": {"answers": {}}}, terminal=False,
                    )
                for key in issues["missing_relationships"] + issues["duplicate_relationships"]:
                    self._absorb_one(
                        ctx, validator, facts_by_id, outcome,
                        rung="sonnet", target_kind="relationship", target_id=key,
                        raw={"contract": {"answers": {}}}, terminal=False,
                    )
            # Completion means durable completion.  A kill after this point may
            # lose in-flight calls, never a call the progress stream banked.
            ctx.store.commit()

        def _describe(job_id: int) -> dict:
            """What a reader needs to see while this unit is in flight."""
            kind, part = job_meta[job_id]
            names = [cid for cid in part.component_ids[:6]]
            label = (names[0] if names else f"partition {job_id}") + f" [{kind}]"
            extra = len(part.component_ids) - 1
            if extra > 0:
                label = f"{label} +{extra}"
            return {
                "label": label,
                "components": len(part.answered_component_ids),
                "relationships": len(part.relationship_keys),
                "sample": names,
            }

        _, _, skipped_components = self._invoke_parallel(
            ctx, component_jobs, invoker_key="p2a_bulk", rung="2a",
            on_result=_bank, describe=_describe, rung_label="2a",
        )
        relationship_jobs = [
            (
                job_id,
                build_compact_relationship_prompt(part, ctx.facts, brief=brief),
                len(part.relationship_keys),
                response_budget_bytes(relationships=len(part.relationship_keys)),
            )
            for job_id, part in relationship_parts
        ]
        _, _, skipped_relationships = self._invoke_parallel(
            ctx, relationship_jobs, invoker_key="p2a_bulk", rung="2a",
            on_result=_bank, describe=_describe, rung_label="2a",
        )
        all_jobs = [*component_jobs, *relationship_jobs]
        skipped = skipped_components + skipped_relationships
        # Notes are emitted in partition order even though the work was banked
        # in completion order, so the report reads the same whatever order the
        # network returned things in.
        for job_id, _, _, _ in all_jobs:
            note = pending_notes.get(job_id)
            if note:
                outcome.notes.append(note)
        if skipped:
            outcome.notes.append(
                f"rung 2a: {skipped} target-kind call(s) not launched, "
                f"{ctx.budget.stop_reason()}; the most important partitions "
                "ran first"
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

        # Batches and their prompts are assembled in the coordinator BEFORE the
        # pool runs, because building an escalation item reads outcome.states;
        # workers must never touch shared state. Batches are independent of one
        # another (each carries disjoint items), so they parallelize exactly
        # like 2a partitions, and absorption below runs in batch order.
        batches = [
            pending[start : start + self.escalation_batch]
            for start in range(0, len(pending), self.escalation_batch)
        ]
        jobs = []
        for index, batch in enumerate(batches):
            items = [
                self._escalation_item(ctx, state, facts_by_id, outcome)
                for state in batch
            ]
            prompt = build_compact_escalation_prompt(
                items, terminal=terminal, brief=brief
            )
            jobs.append((
                index, prompt, len(batch),
                response_budget_bytes(
                    components=sum(1 for s in batch if s.target_kind == "component"),
                    relationships=sum(1 for s in batch if s.target_kind == "relationship"),
                ),
            ))
        # An escalated rung only learns its own size once the rung below has
        # decided what to escalate, so its denominator is published here.
        display = _rung_label(key, rung)
        ctx.progress.plan(
            rung=display,
            partitions=len(batches),
            components=sum(1 for s in pending if s.target_kind == "component"),
            relationships=sum(1 for s in pending if s.target_kind != "component"),
        )

        def _describe_batch(index: int) -> dict:
            batch = batches[index]
            names = [s.target_id for s in batch[:6]]
            label = names[0] if names else f"batch {index}"
            if len(batch) > 1:
                label = f"{label} +{len(batch) - 1}"
            return {
                "label": label,
                "components": sum(1 for s in batch if s.target_kind == "component"),
                "relationships": sum(1 for s in batch if s.target_kind != "component"),
                "sample": names,
            }

        examined: set[tuple[str, str]] = set()
        batch_notes: dict[int, str] = {}

        def _report_batch(index: int, obj: Optional[dict], err: Optional[str]) -> None:
            batch = batches[index]
            answered = 0
            if isinstance(obj, dict):
                issues = coverage_issues(
                    obj,
                    component_ids=[s.target_id for s in batch if s.target_kind == "component"],
                    relationship_keys=[s.target_id for s in batch if s.target_kind == "relationship"],
                )
                obj = normalize_compact_response(
                    obj, facts=ctx.facts,
                    component_ids=[s.target_id for s in batch if s.target_kind == "component"],
                    relationship_keys=[s.target_id for s in batch if s.target_kind == "relationship"],
                )
                # A duplicate is not an answer. The compact wire uses arrays,
                # so normalization would otherwise turn a duplicate into a
                # silent last-write-wins value. Rung 2a already rejects this
                # ambiguity; repairs must obey the same exact-set contract.
                for cid in issues["duplicate_components"]:
                    (obj.get("components") or {}).pop(cid, None)
                for key in issues["duplicate_relationships"]:
                    (obj.get("relationships") or {}).pop(key, None)
                answered = len(obj.get("components") or {}) + len(obj.get("relationships") or {})
                examined.update((s.target_kind, s.target_id) for s in batch)
                self._absorb(
                    ctx, obj, validator, facts_by_id, outcome,
                    rung=rung,
                    component_ids=[s.target_id for s in batch if s.target_kind == "component"],
                    relationship_keys=[s.target_id for s in batch if s.target_kind == "relationship"],
                    terminal=terminal,
                )
                ctx.store.commit()
                if any(issues.values()):
                    batch_notes[index] = "compact coverage violation: " + json.dumps(issues, sort_keys=True)
            if err:
                batch_notes[index] = err
            ctx.progress.unit_end(
                rung=display, unit_id=index, ok=obj is not None,
                answered=answered, detail=err,
            )

        payloads, errors, skipped_batches = self._invoke_parallel(
            ctx, jobs, invoker_key=key, rung=rung,
            on_result=_report_batch, describe=_describe_batch,
            rung_label=display,
        )
        # Which items a model actually SAW: their batch call returned a payload.
        # Load-bearing for the terminal stamping below, and born from a real
        # incident: an OAuth expiry killed every terminal-rung call, no batch
        # returned, and 106 never-examined items were stamped honest_gap, which
        # reads as "we looked and could not establish this" when the truth was
        # "the call never happened". An honest gap is a claim about the CODE;
        # a failed call is a claim about the RUN, and they must never share a
        # label.
        for index, _batch in enumerate(batches):
            if index in batch_notes:
                outcome.notes.append(f"rung {rung} batch {batch_notes[index]}")
        if skipped_batches:
            unattempted = sum(len(b) for b in batches[-skipped_batches:])
            outcome.notes.append(
                f"rung {rung}: {unattempted} item(s) not attempted, "
                f"{ctx.budget.stop_reason()}"
            )

        if terminal:
            # A returned CALL is not proof that the model answered every item
            # and question inside it.  An explicit uncertain/dropped answer (or
            # declared gap) is handled by _absorb_one above and is a legitimate
            # honest gap about the code.  A silently omitted required answer is
            # instead a response-contract failure about the RUN.  Keep it in
            # ``escalate`` so P5 can repair it and the completion gate cannot
            # mistake provider silence for a researched conclusion.
            #
            # An item whose terminal call FAILED or was never launched stays in
            # the escalate state instead. That is already an honest terminal
            # census state meaning "unresolved", the determination already
            # refuses completeness while any item holds it, and a rerun with
            # --update re-targets it. Stamping it honest_gap would convert a
            # transport failure into a confident claim about the code.
            unexamined = 0
            omitted = 0
            for state in outcome.states.values():
                if state.state != "escalate":
                    continue
                if (state.target_kind, state.target_id) in examined:
                    omitted += 1
                else:
                    unexamined += 1
            if omitted:
                outcome.notes.append(
                    f"rung {rung}: {omitted} examined item(s) omitted one or "
                    "more required answers; left unresolved as response-contract "
                    "failures rather than mislabeled as code-level honest gaps"
                )
            if unexamined:
                outcome.notes.append(
                    f"rung {rung}: {unexamined} item(s) left in the escalate "
                    f"state because their terminal call failed or was never "
                    f"launched; NOT recorded as honest gaps, because no model "
                    f"examined them. They will be re-targeted by a rerun."
                )
            # Terminal conversions mutate and stamp state after the per-batch
            # commit.  Make those mutations durable too.
            ctx.store.commit()

    @staticmethod
    def _evidence_reference(item: dict) -> str:
        """One resolved citation as a short reference string, never the object."""
        kind = str(item.get("kind") or "?")
        locator = (
            item.get("symbol") or item.get("field") or item.get("path")
            or (f"{item.get('source')}->{item.get('target')}"
                if item.get("source") or item.get("target") else "")
        )
        return f"{kind}:{locator}" if locator else kind

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
        answers = (attempt.get("contract") or {}).get("answers", {})
        failed_questions = {failure.question for failure in state.failed}
        # Established answers travel as claims plus citation REFERENCES, never
        # expanded evidence objects. The receiving rung only needs to see that
        # a claim is grounded; re-shipping the resolved objects is the
        # transcription this architecture removes, and 95.6% of the v2
        # escalated rungs' output was exactly that class of re-emission
        # (IMPLEMENTATION-DELTA-PROMPT.md section 3.3).
        established = {
            question: {
                "claim": value.get("claim"),
                "cited": [
                    self._evidence_reference(item)
                    for item in (value.get("evidence") or [])[:3]
                    if isinstance(item, dict)
                ],
            }
            for question, value in answers.items()
            if question not in failed_questions and isinstance(value, dict)
        }
        failed = []
        for failure in state.failed:
            prior = answers.get(failure.question) if isinstance(answers, dict) else None
            prior = prior if isinstance(prior, dict) else {}
            failed.append({
                "question": failure.question,
                "trigger": failure.trigger,
                "attempt_claim": str(prior.get("claim") or "")[:300],
                "citations_tried": [
                    self._evidence_reference(item)
                    for item in (prior.get("evidence") or [])[:12]
                    if isinstance(item, dict)
                ],
                "lacked": prior.get("lacked") or "unknown",
                "need": prior.get("need"),
                "note": str(failure.note or "")[:240] or failure.note,
            })
        previous_product = {
            name: value for name, value in attempt.items()
            if name != "contract" and value not in (None, "", [], {})
        }
        return {
            "wire": "escalation/v1",
            "target_kind": state.target_kind,
            "target_id": state.target_id,
            "facts": facts,
            "previous_attempt": {
                "product": previous_product,
                "established": established,
            },
            "failed_questions": failed,
            "todo": sorted(failed_questions),
            "declared_confusion": state.declared_confusion,
        }

    # --- absorbing a response ------------------------------------------------

    def _absorb(
        self, ctx: RunContext, obj: dict, validator: EvidenceValidator,
        facts_by_id: dict, outcome: LadderOutcome, *, rung: str,
        component_ids: list[str], relationship_keys: list[str],
        terminal: bool = False,
        reject_demotion: bool = False,
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
                    raw=raw, terminal=terminal, reject_demotion=reject_demotion,
                )

    def quarantine_unsupported(
        self, ctx: RunContext, outcome: LadderOutcome, checks: list
    ) -> set[str]:
        """Remove claims the independent judge has explicitly rejected.

        Improvement rounds get the first chance to repair a claim with richer
        evidence. Once those bounded rounds are exhausted, retaining a sentence
        the final judge already found unsupported is never an acceptable form
        of "partial success". This deterministic last line rewrites only the
        named answer to an actionable uncertainty, preserves every supported
        sibling answer, and exposes the gap in the product. It performs no new
        generation and makes no new semantic judgment.
        """
        from .evidence import EvidenceValidator

        grouped: dict[tuple[str, str], dict[str, str]] = {}
        for check in checks or []:
            target_kind = str(getattr(check, "target_kind", "") or "")
            target_id = str(getattr(check, "target_id", "") or "")
            question = str(getattr(check, "question", "") or "")
            if target_kind not in {"component", "relationship"}:
                continue
            if not target_id or not question:
                continue
            grouped.setdefault((target_kind, target_id), {})[question] = str(
                getattr(check, "reason", "")
                or "independent adjudication found the claim unsupported"
            )
        if not grouped:
            return set()

        validator = EvidenceValidator(ctx.store, root=ctx.root)
        quarantined: set[str] = set()
        for (target_kind, target_id), failures in sorted(grouped.items()):
            facts = (
                ctx.facts.component_facts(target_id)
                if target_kind == "component"
                else ctx.facts.relationship_facts(target_id)
            )
            validator.attach_facts({target_id: facts})
            answer_delta = {
                question: {
                    "claim": "", "status": "uncertain", "reason": reason,
                    "evidence": [], "lacked": "judgment",
                }
                for question, reason in failures.items()
            }
            block = {
                "honest_gaps": [
                    {"question": question, "why": reason}
                    for question, reason in failures.items()
                ],
                "contract": {"answers": answer_delta},
            }
            obj = {
                "components": {target_id: block} if target_kind == "component" else {},
                "relationships": (
                    {target_id: block} if target_kind == "relationship" else {}
                ),
            }
            self._absorb(
                ctx, obj, validator, {target_id: facts}, outcome,
                rung="p5-adjudication-quarantine",
                component_ids=[target_id] if target_kind == "component" else [],
                relationship_keys=[target_id] if target_kind == "relationship" else [],
                terminal=True,
            )
            quarantined.add(target_id)
        ctx.store.commit()
        return quarantined

    def _absorb_one(
        self, ctx: RunContext, validator: EvidenceValidator, facts_by_id: dict,
        outcome: LadderOutcome, *, rung: str, target_kind: str, target_id: str,
        raw: dict, terminal: bool, reject_demotion: bool = False,
    ) -> None:
        key = (target_kind, target_id)
        previous_state = outcome.states.get(key)
        previous_payload = outcome.payloads.get(key, {})

        # Contract evaluation must see the same computed fact block as the
        # prompt and EvidenceValidator. Raw architecture components omit
        # file_count, edge counts, capabilities and corpus-wide counts; feeding
        # that thinner object to E3 made a correctly cited local singleton look
        # like an unsupported global uniqueness claim.
        facts = (
            ctx.facts.component_facts(target_id)
            if target_kind == "component"
            else ctx.facts.relationship_facts(target_id)
        )
        product, contract_block = split_contract_payload(raw)

        def candidate(product_delta: dict, contract_delta: dict):
            merged_product = merge_payloads(
                {k: v for k, v in previous_payload.items() if k != "contract"},
                product_delta,
            )
            merged_contract = _merge_contract_blocks(
                previous_payload.get("contract") or {}, contract_delta,
            )
            changed = (
                contract_delta.get("answers")
                if isinstance(contract_delta.get("answers"), dict)
                else {}
            )
            if target_kind == "component" and "data_handled" in changed:
                repaired_data = str(
                    (changed.get("data_handled") or {}).get("claim") or ""
                ).strip()
                if repaired_data:
                    merged_product["data_handled"] = repaired_data
            # Compact escalation/work-order responses are deltas. Their
            # semantic atoms intentionally omit a duplicate reader paragraph,
            # so rebuild that paragraph from the merged atom set.
            if (
                target_kind == "component"
                and previous_payload
                and not product_delta.get("help_text")
                and changed
            ):
                answers = merged_contract.get("answers") or {}
                prose = [
                    str((answers.get(question) or {}).get("claim") or "").strip()
                    for question in ("purpose", "mechanism", "place", "why_matters")
                ]
                rebuilt = " ".join(sentence for sentence in prose if sentence)
                if rebuilt:
                    merged_product["help_text"] = rebuilt
            state = state_from_block(
                target_kind=target_kind,
                target_id=target_id,
                rung=rung,
                block=merged_contract,
                facts=facts,
                validator=validator,
                previous=previous_state,
            )
            return merged_product, merged_contract, changed, state

        merged_product, merged_contract, changed_answers, state = candidate(
            product, contract_block,
        )

        # A scoped work order may repair several questions on one target while
        # honestly declining one. Do not let that one declined answer discard
        # its valid siblings. Bank only changed answers that still pass the
        # contract, retain the earlier answer for rejected questions, and then
        # re-evaluate the whole target. The prior all-or-nothing behavior was
        # observed live preserving prose P3 had already rejected even though the
        # same response contained valid repairs for its neighboring questions.
        if reject_demotion and previous_state is not None and changed_answers:
            rank = {"escalate": 0, "honest_gap": 1, "grounded": 2}
            if rank.get(state.state, -1) < rank.get(previous_state.state, -1):
                failed_changed = {
                    failure.question for failure in state.failed
                    if failure.question in changed_answers
                }
                accepted = {
                    question: answer
                    for question, answer in changed_answers.items()
                    if question not in failed_changed
                }
                if failed_changed and accepted:
                    partial_contract = dict(contract_block)
                    partial_contract["answers"] = accepted
                    partial_product = dict(product)
                    partial_product.pop("help_text", None)
                    if "data_handled" in failed_changed:
                        partial_product.pop("data_handled", None)
                    candidate_values = candidate(partial_product, partial_contract)
                    partial_state = candidate_values[3]
                    if (
                        rank.get(partial_state.state, -1)
                        >= rank.get(previous_state.state, -1)
                    ):
                        merged_product, merged_contract, changed_answers, state = (
                            candidate_values
                        )
                        outcome.transitions.append({
                            "target_kind": target_kind,
                            "target_id": target_id,
                            "rung": rung,
                            "from_state": previous_state.state,
                            "state": previous_state.state,
                            "failed": [
                                failure.to_dict() for failure in state.failed
                                if failure.question in failed_changed
                            ],
                            "parser_first": list(state.parser_first),
                            "resolution": (
                                "banked valid work-order answers; retained prior "
                                "answers for rejected questions: "
                                + ", ".join(sorted(failed_changed))
                            ),
                        })

        # A terminal repair has examined the named question. If its attempted
        # replacement still fails the mechanical contract, never publish that
        # known-invalid replacement and never leave the item asking for a rung
        # that does not exist. Preserve its useful siblings and turn only the
        # rejected answers into explicit, reasoned uncertainties. This is the
        # deterministic counterpart to an explicit compact ``s:u`` response.
        if terminal and state.failed and changed_answers:
            failures = {
                failure.question: failure
                for failure in state.failed
                if failure.question in changed_answers
            }
            if failures:
                terminal_answers = dict(merged_contract.get("answers") or {})
                for question, failure in failures.items():
                    attempted = terminal_answers.get(question) or {}
                    terminal_answers[question] = {
                        "claim": "",
                        "status": "uncertain",
                        "reason": str(failure.note or "the attempted repair did not validate"),
                        "evidence": [],
                        **({"lacked": attempted.get("lacked")}
                           if isinstance(attempted, dict) and attempted.get("lacked") else {}),
                        **({"need": attempted.get("need")}
                           if isinstance(attempted, dict) and attempted.get("need") else {}),
                    }
                merged_contract = dict(merged_contract)
                merged_contract["answers"] = terminal_answers
                if target_kind == "component":
                    if "data_handled" in failures:
                        merged_product.pop("data_handled", None)
                    prose = [
                        str((terminal_answers.get(question) or {}).get("claim") or "").strip()
                        for question in ("purpose", "mechanism", "place", "why_matters")
                        if (terminal_answers.get(question) or {}).get("status") == "answered"
                    ]
                    rebuilt = " ".join(text for text in prose if text)
                    if rebuilt:
                        merged_product["help_text"] = rebuilt
                    else:
                        merged_product.pop("help_text", None)
                elif "flow" in failures:
                    merged_product.pop("data_flow_description", None)
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
            # A declared gap CLOSES its question, but the reason stays on the
            # contract state rather than being dropped with it. The reason is the
            # whole value of an honest gap, and a state that discarded it would
            # look identical to a gap nobody could explain, which is the thing the
            # universal gate is meant to catch.
            why_by_question = {
                str(g.get("question")): str(g.get("why") or "").strip()
                for g in declared_gaps
                if isinstance(g, dict) and g.get("question")
            }
            closed: list[FailedQuestion] = []
            remaining: list[FailedQuestion] = []
            for failure in state.failed:
                if failure.question in why_by_question:
                    closed.append(FailedQuestion(
                        failure.question,
                        failure.trigger,
                        why_by_question[failure.question] or failure.note,
                    ))
                else:
                    remaining.append(failure)
            if closed and not remaining:
                state.state = "honest_gap"
                state.rung = "fable"
                state.failed = closed
            elif closed:
                state.state = "escalate"
                state.failed = remaining + closed

        # A final repair tier can also express the honest gap directly on the
        # named answer (compact ``s:u``).  Requiring a second duplicate `gaps`
        # array caused P5 to retain claims its independent judge had already
        # rejected: the repair correctly said "the evidence is absent", but the
        # target stayed grounded because the demotion guard restored the old
        # prose.  At a terminal boundary, explicit uncertain/dropped answers
        # close those exact failed questions as honest gaps; answered siblings
        # remain intact and the reasons stay in the contract state.
        if terminal and state.failed:
            merged_answers = merged_contract.get("answers") or {}
            terminal_questions = {
                failure.question for failure in state.failed
                if isinstance(merged_answers.get(failure.question), dict)
                and merged_answers[failure.question].get("status") in {
                    "uncertain", "dropped"
                }
            }
            if terminal_questions == {failure.question for failure in state.failed}:
                state.state = "honest_gap"
                state.rung = rung

        if terminal and state.state == "honest_gap":
            existing = merged_product.get("honest_gaps")
            gaps = list(existing) if isinstance(existing, list) else []
            known = {
                str(item.get("question") or "")
                for item in gaps if isinstance(item, dict)
            }
            for failure in state.failed:
                if failure.question not in known:
                    gaps.append({
                        "question": failure.question,
                        "why": failure.note or "the terminal repair could not validate this claim",
                    })
            if gaps:
                merged_product["honest_gaps"] = gaps

        if reject_demotion and previous_state is not None:
            rank = {"escalate": 0, "honest_gap": 1, "grounded": 2}
            if rank.get(state.state, -1) < rank.get(previous_state.state, -1):
                outcome.transitions.append({
                    "target_kind": target_kind,
                    "target_id": target_id,
                    "rung": rung,
                    "from_state": previous_state.state,
                    "state": previous_state.state,
                    "failed": [failure.to_dict() for failure in state.failed],
                    "parser_first": list(state.parser_first),
                    "resolution": (
                        "rejected work-order result: contract state would demote "
                        f"from {previous_state.state} to {state.state}"
                    ),
                })
                return

        # The routing record survives re-evaluation: class-at-entry is stamped
        # once, at the first escalate, and carried forward even after the item
        # grounds, so the run can measure its own routing populations (the v2
        # run could not; resolved items had cleared their triggers).
        if previous_state is not None:
            state.entry_triggers = list(previous_state.entry_triggers)
            state.entry_class = previous_state.entry_class
            state.entry_class_basis = previous_state.entry_class_basis
            state.repair_attempted = previous_state.repair_attempted
        state.record_entry_class()

        # The contract is the single source for audited reader meanings. Do
        # this after every terminal/demotion decision so model-supplied prose
        # and stale gap lists cannot disagree with the final state.
        merged_product = _project_audited_answers(
            target_kind, merged_product, merged_contract, state,
        )

        stored = dict(merged_product, contract=merged_contract)
        outcome.payloads[key] = stored
        outcome.states[key] = state
        outcome.rung_counts[rung] = outcome.rung_counts.get(rung, 0) + 1
        outcome.transitions.append({
            "target_kind": target_kind,
            "target_id": target_id,
            "rung": rung,
            "from_state": previous_state.state if previous_state is not None else None,
            "state": state.state,
            "failed": [failure.to_dict() for failure in state.failed],
            "parser_first": list(state.parser_first),
            "resolution": (
                "grounded" if state.state == "grounded" else
                "declared honest gap" if state.state == "honest_gap" else
                "requires escalation"
            ),
        })

        for finding in state.parser_first:
            entry = {
                "target_kind": target_kind, "target_id": target_id,
                "rung": rung, "finding": finding,
            }
            if entry not in outcome.parser_findings:
                outcome.parser_findings.append(entry)

        # The FULL payload, contract included: _stamp splits it into the product
        # row and the contract-state row. Passing the product-only copy here
        # wrote every contract row with an empty answers block, which read as
        # valid because the answers key was still present.
        self._stamp(ctx, target_kind, target_id, stored, state)

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
            gaps = product.get("honest_gaps")
            if isinstance(gaps, list) and gaps:
                cleaned["honest_gaps"] = gaps
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
        # Terminal truth reconciliation. State transitions that carry no new
        # payload never re-stamped their contract row: the honest-gap
        # conversion returns early when an item has no gap prose, and an item
        # grounded en route can leave its earlier escalate row standing. The
        # 2026-08-26 v2 store diverged from its own census this way: 47 stale
        # escalate rows and 88 stored honest gaps against the census's 0 and
        # 102. The census is derived from in-memory states, the store is what
        # every later phase and rerun reads, and they must agree (predicate P6).
        stored_states = {
            row["target_id"]: (row.get("payload") or {}).get("state")
            for row in ctx.store.enrichment()
            if row.get("target_kind") == CONTRACT_TARGET_KIND
        }
        restamped = 0
        for state in outcome.states.values():
            row_id = f"{state.target_kind}:{state.target_id}"
            if row_id in stored_states and stored_states[row_id] == state.state:
                continue
            key = (state.target_kind, state.target_id)
            payload = outcome.payloads.get(key) or {}
            self._stamp(ctx, state.target_kind, state.target_id, payload, state)
            restamped += 1
        if restamped:
            outcome.notes.append(
                f"finalize: re-stamped {restamped} contract row(s) whose stored "
                "state trailed the terminal census state"
            )
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
