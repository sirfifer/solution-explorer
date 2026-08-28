"""P3, final adjudication: check the ladder's work without rewriting any of it.

``ENRICHMENT-ENGINE.md`` section 3. Input-rate, near-zero output, and it runs
after the ladder is quiet. Four things happen here:

* **The Phase 7 verify passes run at last.** ``verify_edges``,
  ``verify_findings`` and ``verify_identity`` have existed, been tested, and
  never been invoked by anything. P3 wires them in rather than reimplementing
  them, so the CI gate and the ladder share one verdict.
* **Grounding spot-checks** ask the question the mechanical validator cannot: the
  citation is real, but does it actually SUPPORT the claim? Sufficiency is
  judgment and the design says so; this is where that judgment is applied and
  counted.
* **The substitution spot-check** applies the E4 test independently. The bulk
  rung self-applies it, and a self-assessment of distinctiveness is exactly the
  assessment a tier has no incentive to fail.
* **The disagreement rate is recorded** as a run metric. If adjudication keeps
  disagreeing with a rung's self-assessment, the contract's questions or that
  rung's instructions need work, and the Run Report says so.

**It rewrites nothing.** P3 writes verdict rows and its own findings. It never
edits a payload the ladder produced. A phase that both judges the work and fixes
it cannot be trusted to report how bad the work was.

**The asymmetry that makes this affordable:** checking a citation costs far less
than producing one. That holds even for what the top of the ladder wrote, which
is why the top of the ladder does not escape verification.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from ..derive.importance import BAND_COUNT, ImportanceRanking, rank_components
from .contract import ContractState
from .engine import _parse_json_object
from .ladder import CONTRACT_TARGET_KIND
from .partition import flatten_components
from .passes import VerifyConfig, verify_edges, verify_findings, verify_identity
from .pipeline import PhaseResult, RunContext
from .prompts import build_grounding_spotcheck_prompt, build_substitution_prompt
from .provenance import stamp_enrichment

__all__ = [
    "GROUNDING_TARGET_KIND",
    "AdjudicationOutcome",
    "AdjudicationPhase",
    "sample_by_importance",
    "build_digest",
]

GROUNDING_TARGET_KIND = "grounding-verdict"

# How the spot-check quota is spread across importance bands. Band 1 carries the
# most weight because a wrong claim about a component everything depends on costs
# a reader more than a wrong claim about a leaf. The tail is deliberately not
# zero: a sample drawn only from the top would never discover that the ladder is
# weakest exactly where nobody is looking.
BAND_WEIGHTS = {1: 0.40, 2: 0.25, 3: 0.15, 4: 0.12, 5: 0.08}

# How many candidates the substitution test offers, including the real one.
SUBSTITUTION_CANDIDATES = 4


@dataclass
class SpotCheck:
    """One grounding spot-check: what was asked, and what came back."""

    target_kind: str
    target_id: str
    question: str
    claim: str
    supported: bool = True
    confidence: str = "medium"
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "question": self.question,
            "claim": self.claim[:280],
            "supported": self.supported,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass
class SubstitutionCheck:
    """One independent E4 test."""

    target_id: str
    distinctive: bool = True
    chose: Optional[str] = None
    reason: str = ""

    @property
    def confirmed_failure(self) -> bool:
        """True when the description did not identify its own subject."""
        return (not self.distinctive) or (self.chose != self.target_id)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "distinctive": self.distinctive,
            "chose": self.chose,
            "confirmed_failure": self.confirmed_failure,
            "reason": self.reason,
        }


@dataclass
class AdjudicationOutcome:
    """Everything P3 concluded, in the shape the Run Report and P5 consume."""

    identity: dict = field(default_factory=dict)
    edges: dict = field(default_factory=dict)
    findings: dict = field(default_factory=dict)
    spot_checks: list[SpotCheck] = field(default_factory=list)
    substitution_checks: list[SubstitutionCheck] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    plan_preview: list[dict] = field(default_factory=list)

    @property
    def checked(self) -> int:
        return len(self.spot_checks)

    @property
    def unsupported(self) -> list[SpotCheck]:
        return [c for c in self.spot_checks if not c.supported]

    def disagreement_rate(self) -> Optional[float]:
        """Fraction of spot-checked claims adjudication would not stand behind.

        None when nothing was sampled, which is different from zero and must not
        be reported as agreement. A run that checked nothing agreed about
        nothing.
        """
        if not self.spot_checks:
            return None
        return len(self.unsupported) / len(self.spot_checks)

    def substitution_failure_rate(self) -> Optional[float]:
        if not self.substitution_checks:
            return None
        failures = sum(1 for c in self.substitution_checks if c.confirmed_failure)
        return failures / len(self.substitution_checks)

    def to_dict(self) -> dict:
        rate = self.disagreement_rate()
        sub_rate = self.substitution_failure_rate()
        return {
            "identity": dict(self.identity),
            "edges": dict(self.edges),
            "findings": dict(self.findings),
            "spot_checks": [c.to_dict() for c in self.spot_checks],
            "substitution_checks": [c.to_dict() for c in self.substitution_checks],
            "checked": self.checked,
            "unsupported": len(self.unsupported),
            "disagreement_rate": None if rate is None else round(rate, 4),
            "substitution_failure_rate": (
                None if sub_rate is None else round(sub_rate, 4)
            ),
            "notes": list(self.notes),
        }


# --- sampling -----------------------------------------------------------------


def sample_by_importance(
    states: list[ContractState], ranking: ImportanceRanking, quota: int
) -> list[ContractState]:
    """Pick which grounded items to spot-check, weighted by importance.

    Deterministic rather than random: the same run must be reproducible, and a
    seeded shuffle buys nothing here that a stated weighting does not.

    Stratified rather than top-N. Checking only the most important items would
    make the disagreement rate a statement about the top of the ranking, and the
    interesting failure is the opposite one: a ladder that is weakest exactly
    where nobody is looking. Every band gets a share, and the top gets the
    largest.
    """
    if quota <= 0 or not states:
        return []
    by_band: dict[int, list[ContractState]] = {b: [] for b in range(1, BAND_COUNT + 1)}
    for state in states:
        band = (
            ranking.band_for(state.target_id)
            if state.target_kind == "component"
            else BAND_COUNT
        )
        by_band.setdefault(band, []).append(state)
    for items in by_band.values():
        items.sort(key=lambda s: (-ranking.score_for(s.target_id), s.target_id))

    picked: list[ContractState] = []
    for band in range(1, BAND_COUNT + 1):
        share = int(quota * BAND_WEIGHTS.get(band, 0.0))
        picked.extend(by_band.get(band, [])[:share])
    # Top up from the most important unpicked items, so integer truncation in the
    # shares does not quietly under-sample the whole run.
    if len(picked) < quota:
        chosen = {(s.target_kind, s.target_id) for s in picked}
        rest = [s for s in states if (s.target_kind, s.target_id) not in chosen]
        rest.sort(key=lambda s: (-ranking.score_for(s.target_id), s.target_id))
        picked.extend(rest[: quota - len(picked)])
    picked.sort(key=lambda s: (s.target_kind, s.target_id))
    return picked[:quota]


def _bounded_evidence_value(value, *, chars: int = 4_000):
    """Keep adjudication evidence useful without duplicating runaway fact values."""
    if isinstance(value, str):
        if len(value) <= chars:
            return value
        return value[:chars] + f"... [+{len(value) - chars} chars omitted]"
    if isinstance(value, list):
        out = []
        for item in value:
            candidate = _bounded_evidence_value(item, chars=max(400, chars // 2))
            if len(json.dumps([*out, candidate], default=str)) > chars and out:
                break
            out.append(candidate)
        if len(out) < len(value):
            out.append(f"[{len(value) - len(out)} more entries omitted]")
        return out
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            candidate = _bounded_evidence_value(item, chars=max(400, chars // 2))
            if len(json.dumps({**out, key: candidate}, default=str)) > chars and out:
                out["_omitted"] = "further fields omitted"
                break
            out[key] = candidate
        return out
    return value


def _judge_source_context(item: dict, facts: Optional[dict]) -> Optional[dict]:
    """Recover the parser-owned excerpt behind a source citation.

    Mechanical validation proves that a symbol or line exists, but the
    independent judge must see the supplied source excerpt to decide whether it
    carries the claim.  The 2026-08-27 UnaMentis canary exposed the missing
    hand-off: 66% of claims were rejected while the judge saw only
    ``{"kind":"symbol","path":...,"symbol":...}``, even though the producer
    had been shown the declaration preview.  This joins the same bounded facts
    already present in the producer envelope; it does not read source files or
    invent new evidence.
    """
    if not isinstance(facts, dict):
        return None
    path = str(item.get("path") or "")
    kind = str(item.get("kind") or "")
    symbol = str(item.get("symbol") or "")
    try:
        line = int(item.get("line")) if item.get("line") is not None else None
    except (TypeError, ValueError):
        line = None

    if kind == "symbol" and path and symbol:
        for declaration in facts.get("source_declarations") or []:
            if not isinstance(declaration, dict):
                continue
            if (str(declaration.get("file") or "") == path
                    and str(declaration.get("name") or "") == symbol):
                return _bounded_evidence_value({
                    key: declaration.get(key)
                    for key in (
                        "line", "end_line", "kind", "visibility",
                        "annotations", "code_preview",
                    )
                    if declaration.get(key) not in (None, "", [])
                }, chars=1_600)

    if kind == "file" and path and line is not None:
        # Relationship extraction owns exact call-site snippets. Prefer that
        # narrow evidence over a broader declaration containing the line.
        for source in facts.get("evidence") or []:
            if not isinstance(source, dict):
                continue
            try:
                source_line = int(source.get("line"))
            except (TypeError, ValueError):
                continue
            if (str(source.get("file") or source.get("path") or "") == path
                    and source_line == line and source.get("snippet")):
                return {
                    "line": line,
                    "code_preview": str(
                        source.get("context") or source["snippet"]
                    )[:1_600],
                }
        for declaration in facts.get("source_declarations") or []:
            if not isinstance(declaration, dict):
                continue
            try:
                start = int(declaration.get("line"))
                end = int(declaration.get("end_line") or start)
            except (TypeError, ValueError):
                continue
            if (str(declaration.get("file") or "") == path
                    and start <= line <= end and declaration.get("code_preview")):
                return _bounded_evidence_value({
                    "line": start,
                    "end_line": end,
                    "symbol": declaration.get("name"),
                    "code_preview": declaration.get("code_preview"),
                }, chars=1_600)
    return None


def build_digest(
    state: ContractState,
    answers: dict,
    facts: Optional[dict] = None,
    source_context_resolver=None,
) -> dict:
    """A compact digest: labels and evidence pointers, never the narrative payload.

    Sending the prose would invite grading the writing instead of the grounding,
    and it would cost input tokens on text nobody is being asked about.

    A fact citation must reach the judge WITH its field and the analyzer's
    value. The spot-check prompt promises the judge "a real field of the
    analyzer's own output with the value shown"; the old key filter stripped a
    fact citation down to a bare {"kind": "fact"}, which made commit f766208's
    adjudicator fix inert for the exact evidence kind it described, and left
    the 53.2% disagreement rate measuring a judge that was never shown the
    evidence. ``facts`` is the same block the validator checks against.
    """
    claims = []
    evidence_menu: list[dict] = []
    evidence_index: dict[str, int] = {}
    for question, answer in sorted((answers or {}).items()):
        if not isinstance(answer, dict):
            continue
        if answer.get("status") != "answered":
            continue
        evidence_refs = []
        for item in answer.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            kept = {k: v for k, v in item.items() if k in
                    ("kind", "path", "line", "symbol", "source", "target",
                     "edge_type", "component", "field", "scope")}
            if "value" in item:
                kept["value"] = item["value"]
            if item.get("kind") == "fact" and isinstance(facts, dict):
                field_name = item.get("field")
                if field_name in facts:
                    kept["value"] = _bounded_evidence_value(
                        facts[field_name],
                        chars=(
                            8_000 if field_name in {
                                "source_references", "outbound_dependency_evidence",
                            } else 4_000
                        ),
                    )
            source_context = (
                source_context_resolver(item)
                if source_context_resolver is not None else None
            ) or _judge_source_context(item, facts)
            if source_context:
                kept["source_context"] = source_context
            canonical = json.dumps(kept, sort_keys=True, separators=(",", ":"), default=str)
            if canonical not in evidence_index:
                evidence_index[canonical] = len(evidence_menu)
                evidence_menu.append(kept)
            evidence_refs.append(evidence_index[canonical])
        claims.append({
            "question": question,
            "claim": str(answer.get("claim") or "")[:400],
            "evidence_refs": evidence_refs,
        })
    return {
        "target_kind": state.target_kind,
        "target_id": state.target_id,
        "grounded_at_rung": state.rung,
        "evidence_menu": evidence_menu,
        "claims": claims,
    }


# --- the phase ----------------------------------------------------------------


class AdjudicationPhase:
    """P3: verdicts and verification. Writes verdicts, rewrites nothing."""

    name = "p3_adjudication"

    def run(self, ctx: RunContext) -> PhaseResult:
        outcome = AdjudicationOutcome()
        ranking = rank_components(ctx.store)
        states = self._grounded_states(ctx)

        if ctx.dry_run:
            return self._plan(ctx, outcome, states, ranking)

        # The ladder's writes must be visible to the verify passes, which open
        # their own connection to the same store file.
        ctx.store.commit()

        self._run_verify_passes(ctx, outcome)
        self._spot_check_grounding(ctx, outcome, states, ranking)
        self._spot_check_substitution(ctx, outcome, states, ranking)
        self._record(ctx, outcome)

        return PhaseResult(
            name=self.name,
            status="ok",
            notes=list(outcome.notes),
            data={"adjudication": outcome},
        )

    def recheck(self, ctx: RunContext, target_ids: set[str]) -> AdjudicationOutcome:
        """Re-adjudicate only targets an executed work order could change."""
        outcome = (ctx.phase_data(self.name) or {}).get("adjudication")
        if outcome is None:
            outcome = AdjudicationOutcome()
        target_ids = {str(value) for value in target_ids if value}
        outcome.spot_checks = [
            check for check in outcome.spot_checks
            if check.target_id not in target_ids
        ]
        outcome.substitution_checks = [
            check for check in outcome.substitution_checks
            if check.target_id not in target_ids
        ]
        states = [
            pair for pair in self._grounded_states(ctx)
            if pair[0].target_id in target_ids
        ]
        ranking = rank_components(ctx.store)
        self._spot_check_grounding(
            ctx, outcome, states, ranking, force_all=True
        )
        self._spot_check_substitution(
            ctx, outcome, states, ranking, force_all=True
        )
        self._record(ctx, outcome)
        return outcome

    # --- inputs --------------------------------------------------------------

    def _grounded_states(self, ctx: RunContext) -> list[tuple[ContractState, dict]]:
        """Every terminal item carrying answered atoms worth adjudicating.

        Read back from the store rather than taken from the ladder's in-memory
        result, so adjudication checks what was actually written. A phase that
        audits a predecessor's memory rather than its output cannot catch a
        write that went wrong. An honest-gap item can still contain several
        supported sibling answers; omitting those made the final judge blind to
        useful, grounded facts merely because one unrelated question remained
        open.
        """
        ladder = (ctx.phase_data("p2_ladder") or {}).get("ladder")
        attempted = set(ladder.states) if ladder is not None else None
        out: list[tuple[ContractState, dict]] = []
        for row in ctx.store.enrichment():
            if row.get("target_kind") != CONTRACT_TARGET_KIND:
                continue
            payload = row.get("payload") or {}
            state = ContractState.from_dict(payload)
            if attempted is not None and (state.target_kind, state.target_id) not in attempted:
                continue
            if state.state not in {"grounded", "honest_gap"}:
                continue
            answers = payload.get("answers") or {}
            if not any(
                isinstance(answer, dict)
                and str(answer.get("status") or "answered") == "answered"
                and str(answer.get("claim") or "").strip()
                for answer in answers.values()
            ):
                continue
            out.append((state, answers))
        out.sort(key=lambda pair: (pair[0].target_kind, pair[0].target_id))
        return out

    # --- the Phase 7 passes, wired at last -----------------------------------

    def _run_verify_passes(self, ctx: RunContext, outcome: AdjudicationOutcome) -> None:
        """Run verify all: identity, edges, findings.

        Each pass gets a metered invoker, so its spend lands on the shared budget
        and every call it makes appears in the Run Report ledger. That is the
        whole reason these are wired rather than shelled out to.
        """
        ladder = (ctx.phase_data("p2_ladder") or {}).get("ladder")
        component_scope = (
            frozenset(
                target_id for (kind, target_id) in ladder.states
                if kind == "component"
            ) if ladder is not None else None
        )
        relationship_scope = (
            frozenset(
                target_id for (kind, target_id) in ladder.states
                if kind == "relationship"
            ) if ladder is not None else None
        )
        passes = (
            ("identity", verify_identity, "identity"),
            ("edges", verify_edges, "edges"),
            ("findings", verify_findings, "findings"),
        )
        for label, fn, attr in passes:
            if not ctx.budget.under():
                outcome.notes.append(
                    f"verify {label} not run: run cost ceiling reached"
                )
                continue
            config = VerifyConfig(
                store_path=ctx.store_path, root=ctx.root, dry_run=False,
                component_scope=component_scope,
                relationship_scope=relationship_scope,
            )
            invoker = ctx.invoker(
                "p3_adjudication", phase=self.name, rung=f"verify-{label}",
                output_budget_bytes={
                    "identity": 26_000, "edges": 15_000, "findings": 20_000,
                }[label],
            )
            try:
                report = fn(config, invoker=invoker, clock=ctx.clock)
            except Exception as exc:  # noqa: BLE001 - one pass must not sink P3
                from ..contracts import gap_from_exception

                reason = gap_from_exception(f"enrich.verify.{label}", "enrich", exc).reason
                outcome.notes.append(f"verify {label} raised and was skipped: {reason}")
                continue
            setattr(outcome, attr, report.to_dict())
            tally = report.tally()
            outcome.notes.append(
                f"verify {label}: {report.done} verified, "
                + (", ".join(f"{k}={v}" for k, v in sorted(tally.items())) or "no verdicts")
            )

    # --- grounding spot-checks ------------------------------------------------

    def _quota(self, ctx: RunContext, population: int) -> int:
        fraction = max(0.0, float(ctx.policy.spot_check_fraction or 0.0))
        quota = int(round(population * fraction))
        if population and quota == 0:
            # A run that grounded anything at all checks at least one claim.
            # Reporting a disagreement rate of "nothing sampled" on a small
            # subject is honest but useless.
            quota = 1
        return min(quota, int(ctx.policy.max_spot_checks or 0) or quota)

    @staticmethod
    def _criterion_priority_ids(
        ctx: RunContext, states: list[tuple[ContractState, dict]],
    ) -> set[tuple[str, str]]:
        """Targets named by predeclared criteria get first use of the sample.

        A canary criterion can name a low-ranked settings edge while structural
        sampling spends its cap on high-ranked shells.  P5 then has to call the
        criterion unknown even though the target was in the attempted census.
        Match only exact deterministic IDs (or every endpoint slug of an edge)
        in the criterion text; this reorders the existing quota and does not
        expand it or infer semantic relevance from generic words.
        """
        from .orientation import load_brief

        phase_brief = (ctx.phase_data("p1_orientation") or {}).get("brief")
        brief = phase_brief or load_brief(ctx.store)
        if brief is None:
            return set()
        text = " ".join(
            value
            for criterion in brief.subject_criteria
            for value in (
                criterion.statement, criterion.why, criterion.how_to_check,
            )
            if value
        ).lower()
        compact_text = re.sub(r"[^a-z0-9]+", "", text)
        prioritized: set[tuple[str, str]] = set()
        for state, _answers in states:
            target_id = state.target_id.lower()
            if target_id in text:
                prioritized.add((state.target_kind, state.target_id))
                continue
            if state.target_kind == "relationship":
                endpoints = target_id.split("|", 2)[:2]
                slugs = [
                    re.sub(r"[^a-z0-9]+", "", endpoint.rsplit("/", 1)[-1])
                    for endpoint in endpoints
                ]
                if slugs and all(slug and slug in compact_text for slug in slugs):
                    prioritized.add((state.target_kind, state.target_id))
            else:
                slug = re.sub(r"[^a-z0-9]+", "", target_id.rsplit("/", 1)[-1])
                if slug and slug in compact_text:
                    prioritized.add((state.target_kind, state.target_id))
        return prioritized

    def _spot_check_grounding(
        self, ctx: RunContext, outcome: AdjudicationOutcome,
        states: list[tuple[ContractState, dict]], ranking: ImportanceRanking,
        *, force_all: bool = False,
    ) -> None:
        if not states:
            outcome.notes.append(
                "no grounded items to spot-check; the disagreement rate is not "
                "zero, it is undefined"
            )
            return
        answers_by_key = {(s.target_kind, s.target_id): a for s, a in states}
        quota = len(states) if force_all else self._quota(ctx, len(states))
        all_states = [s for s, _ in states]
        if force_all:
            sampled = sample_by_importance(all_states, ranking, quota)
        else:
            priority_ids = self._criterion_priority_ids(ctx, states)
            priority = [
                state for state in all_states
                if (state.target_kind, state.target_id) in priority_ids
            ]
            prioritized = sample_by_importance(priority, ranking, min(quota, len(priority)))
            chosen = {(state.target_kind, state.target_id) for state in prioritized}
            remainder = [
                state for state in all_states
                if (state.target_kind, state.target_id) not in chosen
            ]
            sampled = prioritized + sample_by_importance(
                remainder, ranking, max(0, quota - len(prioritized))
            )
        invoker = ctx.invoker(
            "p3_adjudication", phase=self.name, rung="grounding-spot-check",
            output_budget_bytes=8_000,
        )
        for state in sampled:
            if not ctx.budget.under():
                outcome.notes.append(
                    "grounding spot-checks stopped early: run cost ceiling reached"
                )
                break
            answers = answers_by_key.get((state.target_kind, state.target_id), {})
            invoker.set_targets(1)
            facts = (
                ctx.facts.component_facts(state.target_id)
                if state.target_kind == "component"
                else ctx.facts.relationship_facts(state.target_id)
            )
            source_context_resolver = None
            if state.target_kind == "component":
                def source_context_resolver(
                    item, target_id=state.target_id
                ):
                    return ctx.facts.evidence_source_context(target_id, item)
            digest = build_digest(
                state, answers, facts=facts,
                source_context_resolver=source_context_resolver,
            )
            if not digest["claims"]:
                continue
            result = invoker(build_grounding_spotcheck_prompt(digest))
            if not result.ok:
                outcome.notes.append(
                    f"spot-check of {state.target_id} did not return: {result.error}"
                )
                continue
            obj = _parse_json_object(result.text)
            if obj is None or not isinstance(obj.get("checks"), list):
                outcome.notes.append(
                    f"spot-check of {state.target_id} returned an unusable shape"
                )
                continue
            claims_by_q = {c["question"]: c["claim"] for c in digest["claims"]}
            for check in obj["checks"]:
                if not isinstance(check, dict):
                    continue
                question = str(check.get("question") or "")
                outcome.spot_checks.append(SpotCheck(
                    target_kind=state.target_kind,
                    target_id=state.target_id,
                    question=question,
                    claim=claims_by_q.get(question, ""),
                    supported=bool(check.get("supported", True)),
                    confidence=str(check.get("confidence") or "medium"),
                    reason=str(check.get("reason") or ""),
                ))
        rate = outcome.disagreement_rate()
        if rate is not None:
            outcome.notes.append(
                f"grounding spot-checks: {len(outcome.unsupported)} of "
                f"{outcome.checked} claims not supported by their own evidence "
                f"(disagreement rate {rate:.1%})"
            )

    # --- the substitution test, applied independently -------------------------

    def _spot_check_substitution(
        self, ctx: RunContext, outcome: AdjudicationOutcome,
        states: list[tuple[ContractState, dict]], ranking: ImportanceRanking,
        *, force_all: bool = False,
    ) -> None:
        components = [
            c for c in flatten_components(ctx.arch.get("components", []))
            if c.get("id")
        ]
        if len(components) < 2:
            return
        by_id = {c["id"]: c for c in components}
        payloads = {
            row["target_id"]: row.get("payload") or {}
            for row in ctx.store.enrichment()
            if row.get("target_kind") == "component"
        }
        candidates_pool = [c["id"] for c in components]

        component_states = [
            s for s, _ in states if s.target_kind == "component" and s.target_id in by_id
        ]
        quota = (
            len(component_states)
            if force_all else
            (max(1, self._quota(ctx, len(component_states)) // 2)
             if component_states else 0)
        )
        sampled = sample_by_importance(component_states, ranking, quota)
        invoker = ctx.invoker(
            "p3_adjudication", phase=self.name, rung="substitution-check",
            output_budget_bytes=2_000,
        )
        for state in sampled:
            if not ctx.budget.under():
                outcome.notes.append(
                    "substitution checks stopped early: run cost ceiling reached"
                )
                break
            payload = payloads.get(state.target_id) or {}
            invoker.set_targets(1)
            description = str(payload.get("help_text") or payload.get("description") or "")
            if not description.strip():
                continue
            siblings = self._siblings(state.target_id, by_id, candidates_pool)
            if len(siblings) < 2:
                continue
            candidates = [
                {"id": cid, "name": by_id.get(cid, {}).get("name"),
                 "type": by_id.get(cid, {}).get("type")}
                for cid in siblings
            ]
            result = invoker(build_substitution_prompt(description, candidates))
            if not result.ok:
                continue
            obj = _parse_json_object(result.text)
            if obj is None:
                continue
            outcome.substitution_checks.append(SubstitutionCheck(
                target_id=state.target_id,
                distinctive=bool(obj.get("distinctive", True)),
                chose=(str(obj["choice"]) if obj.get("choice") else None),
                reason=str(obj.get("reason") or ""),
            ))
        sub_rate = outcome.substitution_failure_rate()
        if sub_rate is not None:
            failures = sum(1 for c in outcome.substitution_checks if c.confirmed_failure)
            outcome.notes.append(
                f"substitution checks: {failures} of "
                f"{len(outcome.substitution_checks)} descriptions did not identify "
                f"their own subject ({sub_rate:.1%})"
            )

    def _siblings(
        self, target_id: str, by_id: dict, pool: list[str]
    ) -> list[str]:
        """The real component plus its nearest neighbours, deterministically.

        Nearest means "shares a parent path", because a description that cannot
        be told apart from an unrelated component in another subsystem is a much
        weaker finding than one that cannot be told apart from its own siblings.
        """
        prefix = target_id.rsplit("/", 1)[0] if "/" in target_id else ""
        siblings = [
            cid for cid in pool
            if cid != target_id and (cid.rsplit("/", 1)[0] if "/" in cid else "") == prefix
        ]
        if len(siblings) < SUBSTITUTION_CANDIDATES - 1:
            siblings += [
                cid for cid in pool if cid != target_id and cid not in siblings
            ]
        chosen = sorted(siblings)[: SUBSTITUTION_CANDIDATES - 1]
        return sorted([target_id, *chosen])

    # --- record ---------------------------------------------------------------

    def _plan(
        self, ctx: RunContext, outcome: AdjudicationOutcome,
        states: list[tuple[ContractState, dict]], ranking: ImportanceRanking,
    ) -> PhaseResult:
        quota = self._quota(ctx, len(states))
        sampled = sample_by_importance([s for s, _ in states], ranking, quota)
        for state in sampled:
            outcome.plan_preview.append({
                "target_kind": state.target_kind, "target_id": state.target_id,
                "band": ranking.band_for(state.target_id),
            })
        outcome.notes.append(
            f"dry run: {len(states)} grounded item(s), {len(sampled)} would be "
            "spot-checked; the verify passes would run in full. Nothing invoked."
        )
        return PhaseResult(
            name=self.name, status="ok", notes=list(outcome.notes),
            data={"adjudication": outcome},
        )

    def _record(self, ctx: RunContext, outcome: AdjudicationOutcome) -> None:
        """Store the adjudication verdicts. Verdict rows only, no payload edits."""
        stamp_enrichment(
            ctx.store, GROUNDING_TARGET_KIND, "run", outcome.to_dict(),
            digest_index=ctx.index, commit_sha=ctx.commit_sha, clock=ctx.clock,
        )
        ctx.store.commit()
        try:
            ctx.run_path("adjudication.json").write_text(
                json.dumps(outcome.to_dict(), indent=2), encoding="utf-8"
            )
        except OSError as exc:  # pragma: no cover - filesystem edge
            ctx.notes.append(f"adjudication file not written: {exc}")
