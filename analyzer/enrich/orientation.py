"""P1, orientation: what is this thing, who reads the map, and what would matter.

``ENRICHMENT-ENGINE.md`` section 3. Read-heavy, tiny output. It reads the README,
the docs the derivation already extracted, the deterministic summary and the
navigation-importance ranking, and it writes one small document: the **subject
brief**.

The brief does two jobs that nothing else in the ladder can do.

**It sets the criteria the run will be judged against.** P5 does not invent its
own bar; it answers the questions P1 asked. That coupling is expressed in types
rather than in convention: P1 produces :class:`Criterion` objects, P5 consumes
those exact objects and produces :class:`CriterionVerdict` objects against them,
and a criterion with no verdict is therefore a structurally visible omission
rather than something a reader has to notice.

**It warns the ladder before the ladder starts.** A subject whose comments and
code diverge, or whose naming carries an idiom the reader will not share, is
declared up front so that 2a's confusion is expected rather than shameful and
escalation on it is cheap. The design is explicit that a foreign-team codebase is
a known case, not a failure, and the brief is where that gets said.

The brief is stored twice on purpose: as an enrichment row
(``target_kind="subject-brief"``) so it travels with the store, and as a JSON
file in the run directory so a human reading the Run Report can see what the run
believed it was mapping without opening a database.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..derive.importance import ImportanceRanking, rank_components
from .engine import _parse_json_object
from .pipeline import PhaseResult, RunContext
from .provenance import stamp_enrichment

__all__ = [
    "BRIEF_TARGET_KIND",
    "BRIEF_TARGET_ID",
    "Criterion",
    "CriterionVerdict",
    "SubjectBrief",
    "OrientationPhase",
    "build_orientation_prompt",
    "universal_criteria",
]

BRIEF_TARGET_KIND = "subject-brief"
BRIEF_TARGET_ID = "subject"

# How many ranked components the brief is shown. Enough to see the shape of the
# system, few enough that orientation stays a small read.
TOP_COMPONENTS_SHOWN = 25


@dataclass
class Criterion:
    """One subject-specific quality bar, set by P1 and answered by P5.

    ``how_to_check`` is required in spirit even when a model leaves it thin: a
    criterion nobody can check is a wish, and P5 answering a wish produces a
    verdict that means nothing. The determination records an unanswerable
    criterion as ``unknown`` rather than quietly passing it.
    """

    id: str
    statement: str
    why: str = ""
    how_to_check: str = ""
    universal: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "statement": self.statement,
            "why": self.why,
            "how_to_check": self.how_to_check,
            "universal": self.universal,
        }

    @classmethod
    def from_dict(cls, data: Any, *, index: int = 0, universal: bool = False) -> Criterion:
        if isinstance(data, str):
            return cls(id=f"c{index + 1}", statement=data.strip(), universal=universal)
        if not isinstance(data, dict):
            return cls(id=f"c{index + 1}", statement="", universal=universal)
        return cls(
            id=str(data.get("id") or f"c{index + 1}"),
            statement=str(data.get("statement") or "").strip(),
            why=str(data.get("why") or "").strip(),
            how_to_check=str(data.get("how_to_check") or "").strip(),
            universal=bool(data.get("universal", universal)),
        )


@dataclass
class CriterionVerdict:
    """P5's answer to one criterion. Produced against a :class:`Criterion`."""

    criterion_id: str
    statement: str
    verdict: str = "unknown"  # "met" | "unmet" | "unknown"
    evidence: list[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict:
        return {
            "criterion_id": self.criterion_id,
            "statement": self.statement,
            "verdict": self.verdict,
            "evidence": list(self.evidence),
            "reasoning": self.reasoning,
        }


def universal_criteria() -> list[Criterion]:
    """The gates every subject is held to, regardless of what it is.

    These are not the interesting criteria. They are the floor, and they exist so
    that a brief which fails to name anything subject-specific still leaves the
    determination something real to answer rather than nothing at all.
    """
    return [
        Criterion(
            id="u1",
            statement="Every enrichment target reached a terminal contract state.",
            why="An item still asking to climb is unfinished work, and a run that "
            "reports done over unfinished work is the failure mode the census exists "
            "to make visible.",
            how_to_check="The census has no items in the escalate state.",
            universal=True,
        ),
        Criterion(
            id="u2",
            statement="Claims are grounded in evidence that checks out.",
            why="A claim without evidence you can point at is not an answer, and a "
            "form scorer cannot tell the difference.",
            how_to_check="The grounded fraction of the census, and the adjudicator's "
            "spot-check disagreement rate.",
            universal=True,
        ),
        Criterion(
            id="u3",
            statement="What could not be established is visible as an honest gap, "
            "with a reason a reader can act on.",
            why="An honest map says what it does not know. A gap papered over with a "
            "plausible sentence is worse than a gap.",
            how_to_check="Every honest-gap item carries a non-empty reason.",
            universal=True,
        ),
    ]


@dataclass
class SubjectBrief:
    """What this subject is, who reads it, and what would make the map good."""

    identity: str = ""
    audience: str = ""
    what_matters: list[str] = field(default_factory=list)
    criteria: list[Criterion] = field(default_factory=list)
    weighting_adjustments: list[str] = field(default_factory=list)
    idiom_warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    generated: bool = False

    @property
    def subject_criteria(self) -> list[Criterion]:
        return [c for c in self.criteria if not c.universal]

    def to_dict(self) -> dict:
        return {
            "identity": self.identity,
            "audience": self.audience,
            "what_matters": list(self.what_matters),
            "criteria": [c.to_dict() for c in self.criteria],
            "weighting_adjustments": list(self.weighting_adjustments),
            "idiom_warnings": list(self.idiom_warnings),
            "notes": list(self.notes),
            "generated": self.generated,
        }

    @classmethod
    def from_dict(cls, data: Any) -> SubjectBrief:
        data = data if isinstance(data, dict) else {}
        criteria = [
            Criterion.from_dict(item, index=i)
            for i, item in enumerate(data.get("criteria") or [])
        ]
        return cls(
            identity=str(data.get("identity") or "").strip(),
            audience=str(data.get("audience") or "").strip(),
            what_matters=[str(x) for x in (data.get("what_matters") or [])],
            criteria=[c for c in criteria if c.statement],
            weighting_adjustments=[
                str(x) for x in (data.get("weighting_adjustments") or [])
            ],
            idiom_warnings=[str(x) for x in (data.get("idiom_warnings") or [])],
            notes=[str(x) for x in (data.get("notes") or [])],
            generated=bool(data.get("generated", False)),
        )

    @classmethod
    def fallback(cls, reason: str) -> SubjectBrief:
        """A brief that says it is not a brief.

        Orientation failing must not silently hand the ladder an empty document
        that reads like a real one. The universal criteria still apply, so the
        determination has a floor, and the note says plainly what is missing.
        """
        return cls(
            identity="",
            audience="",
            criteria=universal_criteria(),
            notes=[f"NO SUBJECT BRIEF: {reason}. Universal criteria only."],
            generated=False,
        )


# --- the prompt ---------------------------------------------------------------


_ORIENTATION_CONTRACT = """\
Return ONLY a single JSON object, no prose and no fences:

{
  "identity": "What is this system, in two or three sentences, in its own terms? \
Not what its name suggests: what it actually does and for whom.",
  "audience": "Who will read a map of this system, and what are they trying to do \
when they open it?",
  "what_matters": ["3 to 6 things that would matter most to that reader"],
  "criteria": [
    {"id": "s1",
     "statement": "a specific quality bar THIS subject's map must clear",
     "why": "why it matters for this subject in particular",
     "how_to_check": "what someone would look at to answer it"}
  ],
  "weighting_adjustments": ["where enrichment effort should go beyond what the \
mechanical importance ranking already says, and why"],
  "idiom_warnings": ["anything that will confuse a reader of the CODE: comments \
that disagree with behaviour, naming from a non-native idiom, a convention that \
looks like a mistake but is not"]
}

On criteria: write bars that could FAIL. "The map is accurate" is not a criterion,
because nothing could be shown to violate it. "Every service's inbound protocol is
named, because this system's failure modes are all at its boundaries" is one.
Three to six of them. Each needs a how_to_check that names what to look at.
Make each bar a test of whether the MAP faithfully explains the supplied code,
not an assertion that a behavior must exist. Do not require a named target to
share a property merely because its name or the README makes that plausible.
For example, require the map to distinguish latency-sensitive live audio from a
reference-recording/configuration surface; do not predeclare that both enter the
same latency path unless the selected-slice facts establish that. In a bounded
canary, name exact selected component IDs or relationship endpoint slugs in
how_to_check so the adjudicator can reserve part of its sample for the release
gate instead of leaving the criterion unmeasured.
Do not bake inventory counts into a criterion (for example "all 17 components").
The deterministic map owns counts and P5 receives the current inventory. Write
"all components" instead, so the bar remains exact without turning one model's
restatement of a parser fact into an executable source of truth.

On idiom_warnings: this is the single most valuable thing you can write here. A
later rung meeting an unexplained convention will burn an escalation on it and
may still get it wrong. If this codebase does something that will read as a
mistake and is not, say so now. An empty list is legitimate if nothing stands out.

Ground what you write in what you were given. If the documentation does not say
who the audience is, say what the code implies and note that you inferred it.
"""


def build_orientation_prompt(
    *,
    name: str,
    description: str,
    stats: dict,
    readme: str,
    top_components: list[dict],
    ranking_note: str,
    design: Optional[dict] = None,
    ai_surface_summary: Optional[dict] = None,
    scope_note: Optional[str] = None,
    selected_slice: Optional[dict] = None,
) -> str:
    parts = [
        "You are orienting an automated enrichment pipeline before it maps a "
        "software system. Everything below was derived mechanically. Your output "
        "sets what the rest of the run will be judged against, so be specific to "
        "THIS subject rather than to software in general.",
        "",
        _ORIENTATION_CONTRACT,
        "",
        f"SUBJECT: {name}",
        f"MECHANICAL DESCRIPTION: {description or '(none derived)'}",
        "",
    ]
    if scope_note:
        parts += ["RUN SCOPE:", scope_note, ""]
    if selected_slice:
        parts += [
            "EXACT SELECTED SLICE (the only targets this canary will enrich):",
            json.dumps(selected_slice, separators=(",", ":"), default=str),
            "Set subject criteria only where this inventory supplies a target. "
            "Repository documentation may explain the subject, but it does not "
            "expand the attempted scope.",
            "",
        ]
    parts += [
        "SCALE AND MIX: " + json.dumps(stats, default=str)[:2000],
        "",
        "MOST NAVIGATIONALLY IMPORTANT COMPONENTS (mechanical ranking: dependency "
        f"fan-in, git activity, entry points, size). {ranking_note}",
        json.dumps(top_components, indent=2, default=str),
        "",
    ]
    # D7: the design digest, offered as context, not woven through the contract.
    # Absent entirely when the subject yields no signals, so a prompt for a
    # subject this analysis cannot read carries no empty section.
    if design:
        parts += [
            "HOW THIS SYSTEM IS HELD TOGETHER (mechanical architecture quality "
            "signals, no AI). Use these to sharpen what matters for THIS subject; "
            "they are tensions to weigh, not defects to report.",
            json.dumps(design, indent=2, default=str),
            "",
        ]
    # The AI surface digest: a hint, not a briefing. The detector's full rows
    # travel with each partition's facts; orientation only needs the model to
    # EXPECT an AI surface in this subject, so its judgements about what to call
    # out are framed before the first partition arrives rather than improvised
    # when ai_surface facts appear from left field. Absent entirely when the
    # subject has no detectable AI surface, so a prompt for a plain codebase
    # carries no empty section and invites no invention.
    if ai_surface_summary:
        parts += [
            "AI SURFACE (mechanical detection, no inference). This subject "
            "contains the following AI-related machinery; expect ai_surface "
            "facts on the components involved and weigh what deserves calling "
            "out. Do not report AI involvement anywhere these facts do not "
            "support.",
            json.dumps(ai_surface_summary, indent=2, default=str),
            "",
        ]
    parts += [
        "README AND DOCUMENTATION (truncated):",
        readme[:12000] if readme else "(no readme found)",
        "",
        "Return the JSON object now.",
    ]
    return "\n".join(parts)


# --- inputs -------------------------------------------------------------------


def _ai_surface_summary(arch: dict) -> Optional[dict]:
    """A compact digest of the detector's findings, or None when there are none.

    Counts by kind plus the distinct names per kind, capped: enough for the
    orientation to expect the surface and shape its criteria, without spending
    partition-level token budget on rows the partitions will carry anyway.
    """
    items = arch.get("ai_surface") or []
    if not items:
        return None
    by_kind: dict[str, dict] = {}
    for item in items:
        kind = item.get("kind") or "unknown"
        bucket = by_kind.setdefault(kind, {"items": 0, "names": []})
        bucket["items"] += 1
        name = item.get("name")
        if name and name not in bucket["names"] and len(bucket["names"]) < 8:
            bucket["names"].append(name)
    return {"total_items": len(items), "by_kind": by_kind}


def _collect_readme(arch: dict, root: Path) -> str:
    """The subject's own words: the derived readme, or the file on disk.

    The derivation already extracts a readme per component, so that is preferred:
    it is what the rest of the pipeline sees. Falling back to the file keeps
    orientation useful on a subject whose readme the deriver did not attach.
    """
    chunks: list[str] = []

    def walk(components: list) -> None:
        for comp in components:
            docs = comp.get("docs") or {}
            readme = docs.get("readme")
            if isinstance(readme, str) and readme.strip():
                chunks.append(f"### {comp.get('id')}\n{readme.strip()}")
            walk(comp.get("children", []))

    walk(arch.get("components", []))
    if chunks:
        return "\n\n".join(chunks)
    for name in ("README.md", "README.rst", "README.txt", "README"):
        candidate = root / name
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return ""


def _top_components(arch: dict, ranking: ImportanceRanking, limit: int) -> list[dict]:
    index: dict[str, dict] = {}

    def walk(components: list) -> None:
        for comp in components:
            if comp.get("id"):
                index[comp["id"]] = comp
            walk(comp.get("children", []))

    walk(arch.get("components", []))
    out = []
    for item in ranking.top(limit):
        comp = index.get(item.component_id, {})
        out.append({
            "id": item.component_id,
            "name": comp.get("name"),
            "type": comp.get("type"),
            "language": comp.get("language"),
            "framework": comp.get("framework"),
            "importance_band": item.band,
            "depended_on_by": item.fan_in,
            "commits": item.commits,
            "entry_point_because": item.entry_reasons,
            "description": comp.get("description"),
        })
    return out


_INVENTORY_COUNT = re.compile(
    r"\b\d+\s+(components?|languages?|relationships?|files?|symbols?)\b",
    re.IGNORECASE,
)


def _without_inventory_counts(statement: str) -> str:
    """Keep an inventory coverage bar without trusting a model-copied count."""
    value = _INVENTORY_COUNT.sub(lambda match: match.group(1), statement)
    # The common quantified form becomes needlessly clumsy after the number is
    # removed.  This rewrite changes no scope: both forms mean every member of
    # the current deterministic inventory.
    value = re.sub(
        r"\b[Ee]very one of the (components?|languages?|relationships?|files?|symbols?)\b",
        lambda match: ("Every" if match.group(0)[0].isupper() else "every")
        + " " + match.group(1).rstrip("s"),
        value,
    )
    value = re.sub(
        r"\b([Ee]very\s+(?:component|language|relationship|file|symbol)\s+and\s+)"
        r"(components?|languages?|relationships?|files?|symbols?)\b",
        lambda match: match.group(1) + match.group(2).rstrip("s"),
        value,
    )
    return value


class OrientationPhase:
    """P1: read the subject, write the brief, set the criteria P5 will answer."""

    name = "p1_orientation"

    def run(self, ctx: RunContext) -> PhaseResult:
        ranking = rank_components(ctx.store)
        readme = _collect_readme(ctx.arch, ctx.root)
        selected_slice = None
        if ctx.max_partitions is not None:
            scope = ctx.attempted_scope()
            selected_slice = {
                "partition_count": min(
                    ctx.max_partitions, len(ctx.planned_partitions())
                ),
                "component_ids": list(scope["components"]),
                "relationship_keys": list(scope["relationships"]),
            }
        ranking_note = (
            "Git activity was available for this subject."
            if ranking.has_activity
            else "NOTE: this subject has no git activity data, so the ranking rests "
            "on structure and size alone."
        )
        prompt = build_orientation_prompt(
            name=ctx.arch.get("name") or ctx.root.name,
            description=ctx.arch.get("description") or "",
            stats=ctx.arch.get("stats") or {},
            readme=readme,
            top_components=_top_components(ctx.arch, ranking, TOP_COMPONENTS_SHOWN),
            ranking_note=ranking_note,
            design=ctx.design_digest(),
            ai_surface_summary=_ai_surface_summary(ctx.arch),
            scope_note=(
                "This is a bounded validation canary: enrichment will cover only "
                f"the {ctx.max_partitions} most important planned partition(s). "
                "Set criteria that judge the selected slice, not full-system "
                "coverage. Do not weaken evidence, grounding, specificity, or "
                "usefulness standards inside that slice. A successful canary is "
                "not evidence that unselected code was enriched."
                if ctx.max_partitions is not None
                else None
            ),
            selected_slice=selected_slice,
        )

        if ctx.dry_run:
            return PhaseResult(
                name=self.name, status="ok",
                notes=[f"dry run: orientation prompt is ~{len(prompt) // 4} tokens"],
                data={"brief": None, "prompt_chars": len(prompt)},
            )

        invoker = ctx.invoker(
            "p1_orientation", phase=self.name, targets=1,
            output_budget_bytes=12_000,
        )
        result = invoker(prompt)
        if not result.ok:
            return self._degraded(ctx, f"orientation did not return: {result.error}")
        obj = _parse_json_object(result.text)
        if obj is None:
            return self._degraded(ctx, "orientation returned unparseable text")

        brief = SubjectBrief.from_dict(obj)
        brief.generated = True
        if not brief.identity:
            return self._degraded(ctx, "orientation returned no subject identity")

        # Criteria are executable release gates, so a model-authored copy of a
        # parser-owned inventory count must never become their source of truth.
        # Keep the bar and remove only the copied number; P5 receives the exact
        # current inventory from the deterministic map.  This also prevents a
        # brief from going stale when the subject gains a component between
        # runs. Ports, versions, line references, and other subject semantics
        # are untouched because only countable map-inventory nouns match.
        normalized = 0
        for criterion in brief.subject_criteria:
            statement = _without_inventory_counts(criterion.statement)
            if statement != criterion.statement:
                criterion.statement = statement
                normalized += 1
        if normalized:
            brief.notes.append(
                f"normalized parser-owned inventory counts out of {normalized} "
                "criterion statement(s); determination uses the current map inventory"
            )

        # Universal gates are appended, never substituted for. A brief that names
        # good subject criteria still has to clear the floor.
        brief.criteria = brief.criteria + universal_criteria()
        self._persist(ctx, brief)
        notes = [
            f"subject brief written: {len(brief.subject_criteria)} subject "
            f"criteria plus {len(universal_criteria())} universal gates"
        ]
        if brief.idiom_warnings:
            notes.append(
                f"{len(brief.idiom_warnings)} idiom warning(s) declared up front, "
                "so confusion on them is expected rather than shameful"
            )
        return PhaseResult(
            name=self.name, status="ok", notes=notes, data={"brief": brief},
        )

    def _degraded(self, ctx: RunContext, reason: str) -> PhaseResult:
        """Fail visibly, and hand the ladder a brief that says it is not one."""
        brief = SubjectBrief.fallback(reason)
        self._persist(ctx, brief)
        return PhaseResult(
            name=self.name,
            status="failed",
            notes=[
                f"NOT ORIENTED: {reason}. The ladder runs without subject criteria "
                "and the determination falls back to the universal gates only."
            ],
            data={"brief": brief},
        )

    def _persist(self, ctx: RunContext, brief: SubjectBrief) -> None:
        payload = brief.to_dict()
        stamp_enrichment(
            ctx.store, BRIEF_TARGET_KIND, BRIEF_TARGET_ID, payload,
            digest_index=ctx.index, commit_sha=ctx.commit_sha, clock=ctx.clock,
        )
        ctx.store.commit()
        try:
            ctx.run_path("subject-brief.json").write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        except OSError as exc:  # pragma: no cover - filesystem edge
            ctx.notes.append(f"subject brief file not written: {exc}")


def load_brief(store) -> Optional[SubjectBrief]:
    """Read a previously written brief out of a store."""
    for row in store.enrichment():
        if row.get("target_kind") == BRIEF_TARGET_KIND:
            return SubjectBrief.from_dict(row.get("payload"))
    return None
