"""P4, synthesis: the story spine, the lenses, and the tours that were never fed.

``ENRICHMENT-ENGINE.md`` section 3. This runs AFTER adjudication, deliberately:
a story told over unverified labels narrates mistakes persuasively, and the
narrative is the part a reader is most likely to believe without checking.

Three outputs:

* **Tours.** The viewer's tour player and its ``Tour`` contract are built,
  tested, advertised, and have never been fed anything. P4 authors code-anchored
  walkthroughs into that contract. Every step's evidence goes through the same
  no-AI validator the enrichment claims do, before the tour is written, because
  a walkthrough that jumps to a line that does not exist is worse than no
  walkthrough: it breaks in front of the reader.
* **The architecture narrative**, reusing the existing architecture pass rather
  than a second one that could drift from it.
* **Lenses.** The angle nothing else caught, dug into just enough to confirm. A
  confirmed lens becomes a work order, capped and logged.

**Honest gaps are material here, not embarrassment.** What even the deep read
could not settle is part of an honest map's story, and the synthesis prompt is
told so explicitly. A narrative that quietly routes around the gaps produces
exactly the confident, seamless map the whole design is trying not to build.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .contract import ContractState
from .engine import _enhance_architecture, _parse_json_object
from .evidence import EvidenceValidator, normalize_path
from .ladder import CONTRACT_TARGET_KIND
from .partition import flatten_components
from .pipeline import PhaseResult, RunContext
from .provenance import stamp_enrichment
from .workorder import WorkOrder, parse_work_orders

__all__ = [
    "TOUR_TARGET_KIND",
    "SynthesisOutcome",
    "SynthesisPhase",
    "validate_tour",
    "build_synthesis_prompt",
]

TOUR_TARGET_KIND = "tour"

# A tour with one step is not a walkthrough, and a tour with twenty is a
# document. Both bounds are enforced at write time rather than suggested.
MIN_TOUR_STEPS = 2
MAX_TOUR_STEPS = 12
MAX_TOURS = 5

_ID_SAFE = re.compile(r"[^a-z0-9-]+")


def _slug(text: str, fallback: str) -> str:
    slug = _ID_SAFE.sub("-", str(text or "").strip().lower()).strip("-")
    return slug or fallback


def validate_tour(
    raw: Any, *, known_targets: set[str], validator: Optional[EvidenceValidator],
    index: int = 0,
) -> tuple[Optional[dict], list[str]]:
    """Validate one tour against the viewer contract. Returns (tour, problems).

    Validated at write time, never at read time. The viewer's ``Tour`` interface
    (``viewer/src/types.ts``) is the contract, and a tour that does not match it
    is not written at all: a malformed tour reaching the product would break the
    player for the reader rather than for us.

    Every step's evidence is checked by the same no-AI validator the enrichment
    claims go through. A step that jumps to a line past the end of a file is
    worse than a missing step, because it fails visibly in front of the reader.
    """
    problems: list[str] = []
    if not isinstance(raw, dict):
        return None, [f"tour {index + 1}: not an object"]

    title = str(raw.get("title") or "").strip()
    description = str(raw.get("description") or "").strip()
    if not title:
        problems.append(f"tour {index + 1}: no title")
    if not description:
        problems.append(f"tour {index + 1}: no description")

    raw_steps = raw.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        problems.append(f"tour {index + 1}: no steps")
        raw_steps = []

    steps: list[dict] = []
    for position, raw_step in enumerate(raw_steps):
        label = f"tour {index + 1} step {position + 1}"
        if not isinstance(raw_step, dict):
            problems.append(f"{label}: not an object")
            continue
        target = str(raw_step.get("target") or "").strip()
        step_title = str(raw_step.get("title") or "").strip()
        narration = str(raw_step.get("narration") or "").strip()
        if not target:
            problems.append(f"{label}: no target")
            continue
        if known_targets and target not in known_targets:
            problems.append(
                f"{label}: target {target!r} is not a component in this map"
            )
            continue
        if not step_title or not narration:
            problems.append(f"{label}: a step needs both a title and narration")
            continue

        step: dict = {"target": target, "title": step_title, "narration": narration}
        raw_evidence = raw_step.get("evidence")
        if isinstance(raw_evidence, dict) and raw_evidence.get("file"):
            path = normalize_path(raw_evidence.get("file"))
            line = raw_evidence.get("line")
            if validator is not None:
                check = validator.check(
                    {"kind": "file", "path": path, "line": line}
                )
                if not check.ok:
                    problems.append(f"{label}: evidence does not check out, {check.reason}")
                    continue
            step["evidence"] = {"file": path, "line": line if line is not None else None}
        steps.append(step)

    if len(steps) < MIN_TOUR_STEPS:
        problems.append(
            f"tour {index + 1}: {len(steps)} valid step(s); a walkthrough needs at "
            f"least {MIN_TOUR_STEPS}"
        )
        return None, problems
    if len(steps) > MAX_TOUR_STEPS:
        steps = steps[:MAX_TOUR_STEPS]
        problems.append(
            f"tour {index + 1}: truncated to {MAX_TOUR_STEPS} steps; a longer "
            "walkthrough is a document, not a tour"
        )
    if not title or not description:
        return None, problems

    tour = {
        "id": str(raw.get("id") or "").strip() or _slug(title, f"tour-{index + 1}"),
        "title": title,
        "description": description,
        "steps": steps,
    }
    return tour, problems


_SYNTHESIS_CONTRACT = """\
Return ONLY a single JSON object, no prose and no fences:

{
  "tours": [
    {"id": "kebab-case-id",
     "title": "short name for the walkthrough",
     "description": "one or two sentences on what a reader learns by taking it",
     "steps": [
       {"target": "<an exact component id from the map>",
        "title": "short label for this stop",
        "narration": "what the reader should understand here, and why it comes \
after the last stop",
        "evidence": {"file": "<a real path from that component's files>", "line": 12}}
     ]}
  ],
  "lenses": [
    {"name": "the angle",
     "observation": "what you noticed that nothing else surfaced",
     "why_it_matters": "for the reader named in the brief",
     "confidence": "high | medium | low",
     "work_order": {
       "scope": ["component ids the follow-up would cover"],
       "lens": "what to look at, specifically",
       "criteria": "what would satisfy this",
       "expected_effect": "form|truth|utility: what should measurably move",
       "budget": {"max_cost_usd": 1.0, "max_targets": 8}}}
  ]
}

TOURS. Between 2 and 5 of them, each 2 to 12 steps. A tour is an ORDER, not a
list: each step should make sense because of the one before it. Anchor every step
to a component id that exists in the map and, wherever you can, to a real file
and line from that component's own files. Every anchor is checked mechanically
before the tour is written, and a step whose anchor does not check out is dropped.

LENSES. The angle nothing else caught. Not a summary of what the enrichment
already says: something a reader would not have found by walking the tree. If you
have none, return an empty list. A lens you cannot state a criterion for is not a
lens yet.

A work_order is only worth issuing if its instructions would CHANGE the result.
"look again" is not a work order. expected_effect must name which instrument
moves, and criteria must say what would satisfy it.
"""


def build_synthesis_prompt(
    *,
    brief: Optional[dict],
    components: list[dict],
    census: dict,
    honest_gaps: list[dict],
    adjudication: Optional[dict],
) -> str:
    parts = [
        "You are writing the story spine for a map of a software system. Everything "
        "below has already been enriched and independently adjudicated, so you are "
        "building on checked claims rather than raw code.",
        "",
        _SYNTHESIS_CONTRACT,
        "",
    ]
    if brief:
        parts += [
            "THE SUBJECT BRIEF (what this is, who reads the map, what matters):",
            json.dumps(brief, indent=2, default=str),
            "",
        ]
    parts += [
        "COMPONENTS, most navigationally important first, with the files you may "
        "anchor steps to:",
        json.dumps(components, indent=2, default=str),
        "",
        "WHAT THE ENRICHMENT ACTUALLY ESTABLISHED (the contract census):",
        json.dumps(census, default=str),
        "",
    ]
    if honest_gaps:
        parts += [
            "WHAT COULD NOT BE ESTABLISHED, even after the deepest read. This is "
            "MATERIAL, not embarrassment: a map that quietly routes around its own "
            "gaps is exactly the confident, seamless map we are trying not to "
            "build. Where a gap sits on the path a tour takes, say so in the "
            "narration.",
            json.dumps(honest_gaps, indent=2, default=str),
            "",
        ]
    if adjudication:
        parts += [
            "WHAT ADJUDICATION DISPUTED. Claims here were checked and found not to "
            "be supported by their own evidence. Do not build a tour step on one:",
            json.dumps(adjudication, indent=2, default=str),
            "",
        ]
    parts.append("Return the JSON object now.")
    return "\n".join(parts)


@dataclass
class SynthesisOutcome:
    """What P4 produced."""

    tours: list[dict] = field(default_factory=list)
    lenses: list[dict] = field(default_factory=list)
    work_orders: list[WorkOrder] = field(default_factory=list)
    rejected_orders: list[str] = field(default_factory=list)
    narrative_written: bool = False
    rejected_tours: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tours": [dict(t) for t in self.tours],
            "lenses": [dict(item) for item in self.lenses],
            "work_orders": [o.to_dict() for o in self.work_orders],
            "rejected_orders": list(self.rejected_orders),
            "rejected_tours": list(self.rejected_tours),
            "narrative_written": self.narrative_written,
            "notes": list(self.notes),
        }


class SynthesisPhase:
    """P4: tours, narrative, lenses, and the work orders a lens earns."""

    name = "p4_synthesis"

    def run(self, ctx: RunContext) -> PhaseResult:
        outcome = SynthesisOutcome()
        validator = EvidenceValidator(ctx.store, root=ctx.root)
        components = self._component_digests(ctx)
        known_targets = {c["id"] for c in components}
        census, honest_gaps = self._census_inputs(ctx)
        adjudication = self._disputed(ctx)
        brief = self._brief(ctx)

        prompt = build_synthesis_prompt(
            brief=brief, components=components, census=census,
            honest_gaps=honest_gaps, adjudication=adjudication,
        )

        if ctx.dry_run:
            return PhaseResult(
                name=self.name, status="ok",
                notes=[f"dry run: synthesis prompt is ~{len(prompt) // 4} tokens"],
                data={"synthesis": outcome, "prompt_chars": len(prompt)},
            )

        self._write_narrative(ctx, outcome)
        self._author_tours_and_lenses(ctx, outcome, prompt, known_targets, validator)
        self._record(ctx, outcome)

        status = "ok"
        if not outcome.tours and not outcome.narrative_written:
            status = "failed"
            outcome.notes.append("synthesis produced neither a narrative nor a tour")
        return PhaseResult(
            name=self.name, status=status, notes=list(outcome.notes),
            data={"synthesis": outcome},
        )

    # --- inputs --------------------------------------------------------------

    def _brief(self, ctx: RunContext) -> Optional[dict]:
        brief = (ctx.phase_data("p1_orientation") or {}).get("brief")
        if brief is None:
            return None
        data = brief.to_dict() if hasattr(brief, "to_dict") else dict(brief)
        return data if data.get("generated") else None

    def _component_digests(self, ctx: RunContext) -> list[dict]:
        from ..derive.importance import rank_components

        ranking = rank_components(ctx.store)
        index = {
            c["id"]: c
            for c in flatten_components(ctx.arch.get("components", []))
            if c.get("id")
        }
        payloads = {
            row["target_id"]: row.get("payload") or {}
            for row in ctx.store.enrichment()
            if row.get("target_kind") == "component"
        }
        out = []
        for item in ranking:
            comp = index.get(item.component_id)
            if comp is None:
                continue
            payload = payloads.get(item.component_id, {})
            out.append({
                "id": item.component_id,
                "name": comp.get("name"),
                "type": comp.get("type"),
                "language": comp.get("language"),
                "importance_band": item.band,
                "depended_on_by": item.fan_in,
                "files": (comp.get("files") or [])[:6],
                "description": payload.get("description") or comp.get("description"),
                "summary": str(payload.get("help_text") or "")[:400],
            })
        return out

    def _census_inputs(self, ctx: RunContext) -> tuple[dict, list[dict]]:
        census = ctx.phase_data("p2_ladder").get("census")
        if census is not None:
            gaps = [
                {"target_id": s.target_id,
                 "questions": [f.question for f in s.failed]}
                for s in census.honest_gaps
            ]
            return census.to_dict().get("by_state", {}), gaps

        # The ladder did not run in this pipeline; read what is in the store.
        by_state: dict[str, int] = {}
        gaps: list[dict] = []
        for row in ctx.store.enrichment():
            if row.get("target_kind") != CONTRACT_TARGET_KIND:
                continue
            state = ContractState.from_dict(row.get("payload") or {})
            by_state[state.terminal] = by_state.get(state.terminal, 0) + 1
            if state.state == "honest_gap":
                gaps.append({
                    "target_id": state.target_id,
                    "questions": [f.question for f in state.failed],
                })
        return by_state, gaps

    def _disputed(self, ctx: RunContext) -> Optional[dict]:
        adjudication = ctx.phase_data("p3_adjudication").get("adjudication")
        if adjudication is None:
            return None
        unsupported = [c.to_dict() for c in adjudication.unsupported]
        if not unsupported:
            return None
        return {"unsupported_claims": unsupported[:25]}

    # --- outputs -------------------------------------------------------------

    def _write_narrative(self, ctx: RunContext, outcome: SynthesisOutcome) -> None:
        """Reuse the existing architecture pass rather than a second one.

        A parallel narrative writer would drift from the one the rest of the
        product already renders, and the two would disagree without either being
        wrong.
        """
        if not ctx.budget.under():
            outcome.notes.append("architecture narrative not written: cost ceiling")
            return
        invoker = ctx.invoker("p4_synthesis", phase=self.name, rung="narrative", targets=1)
        payload, _cost, errors = _enhance_architecture(
            ctx.facts, ctx.scorer, invoker, ctx.clock
        )
        if payload is None:
            outcome.notes.append(
                "architecture narrative failed validation: " + "; ".join(errors[:3])
            )
            return
        from .digest import ARCH_TARGET_ID

        stamp_enrichment(
            ctx.store, "architecture", ARCH_TARGET_ID, payload,
            digest_index=ctx.index, commit_sha=ctx.commit_sha, clock=ctx.clock,
        )
        outcome.narrative_written = True

    def _author_tours_and_lenses(
        self, ctx: RunContext, outcome: SynthesisOutcome, prompt: str,
        known_targets: set[str], validator: EvidenceValidator,
    ) -> None:
        if not ctx.budget.under():
            outcome.notes.append("tours and lenses not authored: cost ceiling")
            return
        invoker = ctx.invoker("p4_synthesis", phase=self.name, rung="spine")
        result = invoker(prompt)
        if not result.ok:
            outcome.notes.append(f"synthesis did not return: {result.error}")
            return
        obj = _parse_json_object(result.text)
        if obj is None:
            outcome.notes.append("synthesis returned unparseable text")
            return

        for index, raw in enumerate(obj.get("tours") or []):
            tour, problems = validate_tour(
                raw, known_targets=known_targets, validator=validator, index=index
            )
            outcome.rejected_tours.extend(problems)
            if tour is not None:
                outcome.tours.append(tour)
        if len(outcome.tours) > MAX_TOURS:
            outcome.rejected_tours.append(
                f"{len(outcome.tours) - MAX_TOURS} tour(s) beyond the cap of "
                f"{MAX_TOURS} were not written"
            )
            outcome.tours = outcome.tours[:MAX_TOURS]
        self._write_tours(ctx, outcome)

        lenses = obj.get("lenses")
        if isinstance(lenses, list):
            outcome.lenses = [item for item in lenses if isinstance(item, dict)]
        raw_orders = [
            lens.get("work_order")
            for lens in outcome.lenses
            if isinstance(lens.get("work_order"), dict)
        ]
        orders, rejected = parse_work_orders(
            raw_orders, issued_by="P4", cap=ctx.policy.max_work_orders
        )
        outcome.work_orders = orders
        outcome.rejected_orders = rejected

        outcome.notes.append(
            f"{len(outcome.tours)} tour(s) written, {len(outcome.lenses)} lens(es) "
            f"discovered, {len(orders)} work order(s) issued"
        )
        for rejection in outcome.rejected_tours[:5]:
            outcome.notes.append(f"tour rejected: {rejection}")
        for rejection in rejected[:5]:
            outcome.notes.append(f"work order rejected: {rejection}")

    def _write_tours(self, ctx: RunContext, outcome: SynthesisOutcome) -> None:
        """One enrichment row per tour, so the overlay can find them."""
        for tour in outcome.tours:
            stamp_enrichment(
                ctx.store, TOUR_TARGET_KIND, tour["id"], tour,
                digest_index=ctx.index, commit_sha=ctx.commit_sha, clock=ctx.clock,
            )
        ctx.store.commit()

    def _record(self, ctx: RunContext, outcome: SynthesisOutcome) -> None:
        ctx.store.commit()
        try:
            ctx.run_path("synthesis.json").write_text(
                json.dumps(outcome.to_dict(), indent=2), encoding="utf-8"
            )
        except OSError as exc:  # pragma: no cover - filesystem edge
            ctx.notes.append(f"synthesis file not written: {exc}")
