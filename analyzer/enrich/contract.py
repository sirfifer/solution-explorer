"""The completeness contract: is this item's enrichment actually finished?

``ENRICHMENT-ENGINE.md`` section 4. The owner's challenge was to make "is this
item's enrichment complete" as deterministic as possible, with guidelines every
tier follows identically. The answer has three parts, and this module is all
three: the required questions (4.1), the grounding rule (4.2, enforced by
:mod:`analyzer.enrich.evidence`), and mechanical escalation triggers (4.3).

The measured reason it exists: 83 of 99 calibration components scored exactly
85.0 on the form scorer while nothing checked whether a single claim was true.
Form is a sanity floor. This is the truth instrument's contract half.

**Applicability is structural, not a judgment call.** A component with no
detected port cannot answer "what is this port for", and treating that as an
unanswered required question (E1) would escalate half a codebase to Opus for
having no ports. So the required question SET is computed per target from
deterministic facts: :func:`required_questions` returns only the questions that
target can be expected to answer. This is the design's own principle applied
(convert as much judgment as possible into checkable structure) and it keeps the
three answer statuses exactly as the canonical shape specifies, rather than
inventing a fourth for "not applicable".

**A tier's self-declared state is an input, never the verdict.** Rungs report
what they believe. :func:`evaluate` recomputes the contract state from the
answers and the evidence validator, so a tier claiming ``grounded`` over a
citation that points nowhere is still escalated. The self-declaration is kept
for the record because a tier that consistently overclaims is itself a finding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .evidence import EvidenceValidator

__all__ = [
    "COMPONENT_QUESTIONS",
    "RELATIONSHIP_QUESTIONS",
    "TRIGGERS",
    "TERMINAL_STATES",
    "RUNGS",
    "Answer",
    "ContractState",
    "FailedQuestion",
    "Census",
    "required_questions",
    "parse_answers",
    "evaluate",
    "terminal_key",
    "build_census",
    "split_contract_payload",
    "state_from_block",
    "CONTRACT_KEY",
]

# The five required questions (4.1). Identity is one question in prose and four
# individually-checkable claims in the data, exactly as the canonical shape's
# failed-question vocabulary spells them.
COMPONENT_QUESTIONS: tuple[str, ...] = (
    "purpose",
    "mechanism",
    "place",
    "identity.type",
    "identity.framework",
    "identity.port",
    "identity.language",
    "next_step",
)

# Relationships carry a reduced form: what flows, and why it exists (4.1).
RELATIONSHIP_QUESTIONS: tuple[str, ...] = ("flow", "why")

# Mechanical escalation triggers (4.3). The trigger travels with the item.
TRIGGERS: dict[str, str] = {
    "E1": "no-answer: a required question the tier could not answer at all",
    "E2": "ungrounded: an answer whose evidence the tier could not cite",
    "E3": "contradiction: evidence contradicts a deterministic fact or another claim",
    "E4": "substitution failure: the answer would fit a sibling component equally well",
    "E5": "declared confusion: the tier cannot reconcile the code with its comments, "
    "docs or naming",
}

# The trigger-class vocabulary: which failures mean "the tier lacked facts"
# (context) and which mean "the tier lacked capability" (reasoning). One
# import for the router and the run report; a second copy of this map is how
# the three-role drift happens. E2/E3/E4 are context because their failure
# mode is evidence that did not check out, contradicted, or could not
# distinguish a sibling; E1/E5 are reasoning. An item's recorded ``lacked``
# self-report refines this where present (fact -> context,
# judgment -> reasoning); the trigger map is the fallback.
CONTEXT_TRIGGERS: tuple[str, ...] = ("E2", "E3", "E4")
REASONING_TRIGGERS: tuple[str, ...] = ("E1", "E5")


def trigger_class(triggers) -> str:
    """Deterministic class of a failed-item's trigger set.

    Total over any iterable of trigger codes: pure context, pure reasoning,
    or mixed. Mixed climbs with the reasoning class because its
    reasoning-half needs the climb anyway and splitting one item across two
    calls would give it two writers per rung.
    """
    seen = {str(t) for t in triggers}
    if not seen:
        return "reasoning"
    if seen <= set(CONTEXT_TRIGGERS):
        return "context"
    if not (seen & set(CONTEXT_TRIGGERS)):
        return "reasoning"
    return "mixed"


# Terminal contract states (4.4).
TERMINAL_STATES: tuple[str, ...] = ("grounded", "escalate", "honest_gap")

# The ladder's rungs, in climbing order.
RUNGS: tuple[str, ...] = ("sonnet", "opus", "fable")

ANSWER_STATUSES: tuple[str, ...] = ("answered", "uncertain", "dropped")


# --- required question sets ---------------------------------------------------


def required_questions(target_kind: str, facts: Optional[dict] = None) -> tuple[str, ...]:
    """The questions this target can be expected to answer, from store facts alone.

    An identity sub-question is required only when the analyzer actually detected
    that attribute. A component with no framework is not hiding one; asking it to
    explain a framework it does not have would manufacture an E1 and escalate a
    perfectly well understood component to a more expensive rung.
    """
    if target_kind == "relationship":
        return RELATIONSHIP_QUESTIONS
    facts = facts if isinstance(facts, dict) else {}
    questions: list[str] = ["purpose", "mechanism", "place", "identity.type"]
    for attribute in ("framework", "port", "language"):
        value = facts.get(attribute)
        if value is not None and str(value).strip() not in ("", "None", "unknown"):
            questions.append(f"identity.{attribute}")
    questions.append("next_step")
    # Keep canonical order so a census is comparable across targets.
    order = {name: i for i, name in enumerate(COMPONENT_QUESTIONS)}
    return tuple(sorted(questions, key=lambda name: order.get(name, len(order))))


# --- shapes -------------------------------------------------------------------


@dataclass
class Answer:
    """One answer inside a target's contract block (canonical shape)."""

    claim: str = ""
    status: str = "answered"
    reason: Optional[str] = None
    evidence: list[dict] = field(default_factory=list)
    # The tier's self-report of WHAT it lacked, only meaningful on an
    # uncertain answer: "fact" (more deterministic context would settle it)
    # or "judgment" (genuine difficulty). Deliberately ignored when deciding
    # groundedness; consumed by routing classification and the exit report.
    lacked: Optional[str] = None
    need: Optional[str] = None

    def to_dict(self) -> dict:
        out = {
            "claim": self.claim,
            "status": self.status,
            "reason": self.reason,
            "evidence": [dict(item) for item in self.evidence],
        }
        if self.lacked:
            out["lacked"] = self.lacked
        if self.need:
            out["need"] = self.need
        return out

    @classmethod
    def from_any(cls, raw: Any) -> Answer:
        """Coerce whatever a tier returned into an Answer, never raising.

        A bare string is accepted as a claim with no evidence, because that is
        the shape a tier drifts into under pressure and the grounding rule
        already handles it correctly: no evidence means E2, which is the honest
        outcome rather than a parse crash that loses the whole partition.
        """
        if isinstance(raw, str):
            return cls(claim=raw.strip(), status="answered", evidence=[])
        if not isinstance(raw, dict):
            return cls(claim="", status="dropped", reason="answer was not an object")
        status = str(raw.get("status") or "answered").strip().lower()
        if status not in ANSWER_STATUSES:
            status = "answered"
        evidence = raw.get("evidence")
        lacked = raw.get("lacked")
        return cls(
            claim=str(raw.get("claim") or "").strip(),
            status=status,
            reason=(str(raw["reason"]).strip() if raw.get("reason") else None),
            evidence=[item for item in evidence if isinstance(item, dict)]
            if isinstance(evidence, list)
            else [],
            lacked=lacked if lacked in ("fact", "judgment") else None,
            need=(str(raw["need"]).strip() if raw.get("need") else None),
        )


@dataclass
class FailedQuestion:
    """One named gap that travels with an escalating item (4.3)."""

    question: str
    trigger: str
    note: str = ""
    # The failing answer's own lacked self-report, where it gave one. This is
    # what lets classification rest on what the tier SAID it was missing
    # rather than on the trigger heuristic alone.
    lacked: Optional[str] = None

    def to_dict(self) -> dict:
        out = {"question": self.question, "trigger": self.trigger, "note": self.note}
        if self.lacked:
            out["lacked"] = self.lacked
        return out

    @classmethod
    def from_dict(cls, data: dict) -> FailedQuestion:
        lacked = data.get("lacked")
        return cls(
            question=str(data.get("question") or ""),
            trigger=str(data.get("trigger") or ""),
            note=str(data.get("note") or ""),
            lacked=lacked if lacked in ("fact", "judgment") else None,
        )


@dataclass
class ContractState:
    """A target's contract state, which is also its escalation record (4.3, 4.4)."""

    target_kind: str
    target_id: str
    state: str = "escalate"
    rung: str = "sonnet"
    failed: list[FailedQuestion] = field(default_factory=list)
    attempt_ref: Optional[str] = None
    # Kept for the record: what the tier said about itself, and what it said
    # before this rung touched it. Neither is the verdict.
    self_declared: Optional[str] = None
    declared_confusion: Optional[str] = None
    parser_first: list[str] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    # The routing record, stamped the first time this item enters the escalate
    # state and never overwritten. The v2 run could not measure its own
    # routing populations because a resolved item clears its triggers, so
    # class-at-entry was unrecoverable post hoc (the 48%-to-66% bound in
    # IMPLEMENTATION-DELTA-ORCH.md section 3.4). These two fields make every
    # later run self-measuring, and `repair_attempted` is the one-shot bound
    # on the same-tier repair loop.
    entry_triggers: list[str] = field(default_factory=list)
    entry_class: Optional[str] = None
    entry_class_basis: Optional[str] = None
    repair_attempted: bool = False

    @property
    def terminal(self) -> str:
        """The census key: ``grounded@sonnet``, ``honest-gap``, and so on (4.4)."""
        return terminal_key(self.state, self.rung)

    @property
    def failed_questions(self) -> list[str]:
        return [f.question for f in self.failed]

    @property
    def triggers(self) -> list[str]:
        seen: list[str] = []
        for f in self.failed:
            if f.trigger not in seen:
                seen.append(f.trigger)
        return seen

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "rung": self.rung,
            "failed": [f.to_dict() for f in self.failed],
            "attempt_ref": self.attempt_ref,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "self_declared": self.self_declared,
            "declared_confusion": self.declared_confusion,
            "parser_first": list(self.parser_first),
            "history": list(self.history),
            "entry_triggers": list(self.entry_triggers),
            "entry_class": self.entry_class,
            "entry_class_basis": self.entry_class_basis,
            "repair_attempted": self.repair_attempted,
        }

    def record_entry_class(self) -> None:
        """Stamp class-at-entry once, at the moment the item first escalates.

        The recorded ``lacked`` self-report supersedes the trigger heuristic
        wherever a failing answer gave one: a tier saying "I lacked a fact"
        is context class regardless of which trigger fired, and "judgment"
        is reasoning class. Questions without a self-report fall back to the
        trigger map, and the basis records how much of each was used.
        """
        if self.entry_class is not None or self.state != "escalate":
            return
        self.entry_triggers = list(self.triggers)
        classes: list[str] = []
        lacked_used = 0
        for f in self.failed:
            if f.lacked == "fact":
                classes.append("context")
                lacked_used += 1
            elif f.lacked == "judgment":
                classes.append("reasoning")
                lacked_used += 1
            else:
                classes.append(trigger_class([f.trigger]))
        if all(c == "context" for c in classes):
            self.entry_class = "context"
        elif all(c == "reasoning" for c in classes):
            self.entry_class = "reasoning"
        else:
            self.entry_class = "mixed"
        self.entry_class_basis = (
            f"lacked:{lacked_used}/trigger:{len(classes) - lacked_used}"
        )

    @classmethod
    def from_dict(cls, data: dict) -> ContractState:
        return cls(
            target_kind=str(data.get("target_kind") or "component"),
            target_id=str(data.get("target_id") or ""),
            state=str(data.get("state") or "escalate"),
            rung=str(data.get("rung") or "sonnet"),
            failed=[
                FailedQuestion.from_dict(f)
                for f in (data.get("failed") or [])
                if isinstance(f, dict)
            ],
            attempt_ref=data.get("attempt_ref"),
            self_declared=data.get("self_declared"),
            declared_confusion=data.get("declared_confusion"),
            parser_first=list(data.get("parser_first") or []),
            history=list(data.get("history") or []),
            entry_triggers=list(data.get("entry_triggers") or []),
            entry_class=data.get("entry_class"),
            entry_class_basis=data.get("entry_class_basis"),
            repair_attempted=bool(data.get("repair_attempted", False)),
        )


def terminal_key(state: str, rung: str) -> str:
    """The 4.4 census key for a (state, rung) pair."""
    if state == "honest_gap":
        return "honest-gap"
    if state == "grounded":
        return f"grounded@{rung}"
    return f"escalate@{rung}"


# --- evaluation ---------------------------------------------------------------


def parse_answers(raw: Any) -> dict[str, Answer]:
    """Coerce a tier's answers block into ``{question: Answer}``, never raising."""
    if not isinstance(raw, dict):
        return {}
    return {str(key): Answer.from_any(value) for key, value in raw.items()}


def _contradiction_notes(facts: Optional[dict], answers: dict[str, Answer]) -> list[tuple[str, str]]:
    """Identity claims that contradict what the analyzer deterministically found.

    Only the four identity attributes are checked here, because they are the only
    claims with a deterministic counterpart to contradict. This is E3's mechanical
    half; the adjudicator finds the rest.
    """
    if not isinstance(facts, dict):
        return []
    out: list[tuple[str, str]] = []
    for attribute in ("type", "framework", "port", "language"):
        question = f"identity.{attribute}"
        answer = answers.get(question)
        if answer is None or answer.status != "answered" or not answer.claim:
            continue
        known = facts.get(attribute)
        if known is None or str(known).strip() in ("", "None"):
            continue
        # A claim contradicts only when it names a DIFFERENT concrete value for
        # the attribute, not when it merely fails to repeat the stored one. The
        # claim is prose ("a FastAPI service on port 8000"), so containment is
        # the honest test: absence of the known value is not evidence of a
        # competing one, and flagging it would make E3 fire on good prose.
        claim = answer.claim.lower()
        stored = str(known).strip().lower()
        if stored and stored not in claim:
            out.append((
                question,
                f"claim does not mention the detected {attribute} {known!r}",
            ))
    return out


def _parser_settles(question: str, facts: Optional[dict]) -> bool:
    """True when a required identity question is already answered by the parser.

    Only identity attributes qualify, and only when the store actually carries a
    concrete value. `purpose`, `mechanism`, `place` and `next_step` are never
    settled this way: no deterministic pass produces them, so a model failing
    one is a real gap and must still climb.
    """
    if not question.startswith("identity."):
        return False
    if not isinstance(facts, dict):
        return False
    attribute = question.split(".", 1)[1]
    if attribute not in ("type", "framework", "port", "language"):
        return False
    value = facts.get(attribute)
    return value is not None and str(value).strip() not in ("", "None", "unknown")


def evaluate(
    *,
    target_kind: str,
    target_id: str,
    rung: str,
    answers: Any,
    facts: Optional[dict] = None,
    validator: Optional[EvidenceValidator] = None,
    self_declared: Optional[str] = None,
    declared_confusion: Optional[str] = None,
    parser_first: Optional[list] = None,
    attempt_ref: Optional[str] = None,
    previous: Optional[ContractState] = None,
    strict_identity: bool = False,
) -> ContractState:
    """Recompute a target's contract state from its answers. The verdict, not a report.

    Every escalation trigger that fires is recorded with the question it fired on
    and a note, because the next rung starts from the named gap plus the attempt,
    never from a blank assignment (design section 1, rule 8).

    ``strict_identity`` turns the mechanical identity check into an E3. It is off
    by default: containment against prose produces false contradictions often
    enough that it belongs to adjudication, which can read the claim, rather than
    to a bulk rung that cannot.
    """
    parsed = parse_answers(answers)
    required = required_questions(target_kind, facts)
    failed: list[FailedQuestion] = []

    for question in required:
        # An identity attribute the PARSER already determined is settled before
        # a model is consulted. The question is only asked at all because the
        # analyzer detected the attribute, the prompt hands the detected value
        # over, and `strict_identity` is off by default so nothing ever checks
        # the model's restatement of it. Letting such a question fail therefore
        # escalates a fact we already hold to a more expensive tier to be
        # re-derived and then discarded: on the 2026-08-25 unamentis-ios run,
        # identity.framework climbed to Opus twice on exactly that path, at
        # roughly 17.5x the cost per item of the rung that already knew.
        #
        # Deterministic-first: where the parser has the answer, the parser IS
        # the answer, and the model's version cannot make it a gap.
        if _parser_settles(question, facts):
            continue
        answer = parsed.get(question)
        if answer is None or not answer.claim:
            failed.append(
                FailedQuestion(
                    question,
                    "E1",
                    "no answer was produced for a required question",
                )
            )
            continue
        if answer.status == "dropped":
            failed.append(
                FailedQuestion(
                    question,
                    "E1",
                    answer.reason or "the tier dropped this answer",
                )
            )
            continue
        if answer.status == "uncertain":
            failed.append(
                FailedQuestion(
                    question,
                    "E2",
                    answer.reason or "the tier marked this answer uncertain",
                    lacked=answer.lacked,
                )
            )
            continue
        # status == answered: the grounding rule applies. An answer that cannot
        # cite is ungrounded, which is how "I could not really tell" becomes a
        # structural fact instead of a confident sentence.
        if not answer.evidence:
            failed.append(
                FailedQuestion(question, "E2", "the answer cites no evidence")
            )
            continue
        if validator is not None and not validator.any_valid(answer.evidence):
            reasons = [check.reason for check in validator.failures(answer.evidence)]
            failed.append(
                FailedQuestion(
                    question,
                    "E2",
                    "no citation checked out: " + "; ".join(r for r in reasons if r)[:300],
                )
            )

    if strict_identity:
        for question, note in _contradiction_notes(facts, parsed):
            if question not in {f.question for f in failed}:
                failed.append(FailedQuestion(question, "E3", note))

    if declared_confusion:
        failed.append(
            FailedQuestion("purpose", "E5", str(declared_confusion)[:300])
        )

    state = "grounded" if not failed else "escalate"
    history = list(previous.history) if previous is not None else []
    if previous is not None:
        history.append(f"{previous.rung}:{previous.state}")

    return ContractState(
        target_kind=target_kind,
        target_id=target_id,
        state=state,
        rung=rung,
        failed=failed,
        attempt_ref=attempt_ref,
        self_declared=self_declared,
        declared_confusion=declared_confusion,
        parser_first=[str(p) for p in (parser_first or [])],
        history=history,
    )


# --- census -------------------------------------------------------------------


@dataclass
class Census:
    """The census of terminal states: the backbone of the P5 determination (4.4)."""

    by_state: dict[str, int] = field(default_factory=dict)
    items: list[ContractState] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def grounded(self) -> int:
        return sum(1 for item in self.items if item.state == "grounded")

    @property
    def honest_gaps(self) -> list[ContractState]:
        return [item for item in self.items if item.state == "honest_gap"]

    @property
    def unresolved(self) -> list[ContractState]:
        """Items still asking to climb when the ladder stopped.

        A non-empty list means the ladder terminated with work outstanding, which
        the determination has to see: it is a different product from one where
        everything either grounded or became an honest gap.
        """
        return [item for item in self.items if item.state == "escalate"]

    def grounded_fraction(self) -> float:
        return (self.grounded / self.total) if self.total else 0.0

    def trigger_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items:
            for trigger in item.triggers:
                counts[trigger] = counts.get(trigger, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict:
        return {
            "by_state": dict(self.by_state),
            "total": self.total,
            "grounded": self.grounded,
            "grounded_fraction": round(self.grounded_fraction(), 4),
            "trigger_counts": self.trigger_counts(),
            "items": [item.to_dict() for item in self.items],
        }


def build_census(states: list[ContractState]) -> Census:
    """Assemble the census from every target's terminal contract state."""
    ordered = sorted(states, key=lambda s: (s.target_kind, s.target_id))
    by_state: dict[str, int] = {}
    for item in ordered:
        by_state[item.terminal] = by_state.get(item.terminal, 0) + 1
    return Census(by_state=dict(sorted(by_state.items())), items=ordered)


# --- payload splitting --------------------------------------------------------
#
# A contract-aware response is a superset of the existing ai_enhance payload: the
# same product fields, plus one "contract" key. The engine stamps the product
# fields exactly as before, and the contract scaffolding goes to its own store row
# and the Run Report. That split is what keeps the promise in the build plan: the
# product receives what it receives today, plus tours, plus honest-gap markers,
# and never the answer scaffolding.

CONTRACT_KEY = "contract"


def split_contract_payload(payload: Any) -> tuple[dict, dict]:
    """Split a tier's per-target payload into (product fields, contract block).

    Returns two dicts. The first is what the existing cleaner and the scorer see,
    with the contract key removed; the second is the raw contract block, empty
    when the tier returned none. Neither raises: a malformed payload yields two
    empty dicts, because a broken response must degrade to "no contract answered"
    rather than take the partition down.
    """
    if not isinstance(payload, dict):
        return {}, {}
    product = {k: v for k, v in payload.items() if k != CONTRACT_KEY}
    block = payload.get(CONTRACT_KEY)
    return product, (block if isinstance(block, dict) else {})


def state_from_block(
    *,
    target_kind: str,
    target_id: str,
    rung: str,
    block: dict,
    facts: Optional[dict] = None,
    validator: Optional[EvidenceValidator] = None,
    attempt_ref: Optional[str] = None,
    previous: Optional[ContractState] = None,
) -> ContractState:
    """Evaluate a tier's raw contract block into a recomputed ContractState.

    The tier's ``self_state``, its declared confusion, its parser-first findings
    and its substitution check all travel through; only the state itself is
    recomputed rather than believed.
    """
    block = block if isinstance(block, dict) else {}
    substitution = block.get("substitution_check")
    parser_first = block.get("parser_first")
    state = evaluate(
        target_kind=target_kind,
        target_id=target_id,
        rung=rung,
        answers=block.get("answers"),
        facts=facts,
        validator=validator,
        self_declared=(
            str(block["self_state"]).strip() if block.get("self_state") else None
        ),
        declared_confusion=(
            str(block["confusion"]).strip() if block.get("confusion") else None
        ),
        parser_first=parser_first if isinstance(parser_first, list) else [],
        attempt_ref=attempt_ref,
        previous=previous,
    )
    # A tier that says its description would fit any sibling has self-reported the
    # substitution failure the design calls E4. Believing a self-reported FAILURE
    # is safe in a way believing a self-reported success is not: nothing is
    # gained by claiming to be interchangeable.
    if isinstance(substitution, str) and _is_substitution_failure(substitution):
        state.failed.append(
            FailedQuestion("purpose", "E4", substitution.strip()[:300])
        )
        state.state = "escalate"
    return state


_SUBSTITUTION_FAILURE_MARKERS = (
    "would fit any",
    "fits any",
    "fit any sibling",
    "nothing unique",
    "nothing distinctive",
    "could be any",
    "applies to all",
    "none",
)


def _is_substitution_failure(text: str) -> bool:
    """Did the tier admit its answers describe nothing in particular?"""
    lowered = text.strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in _SUBSTITUTION_FAILURE_MARKERS)
