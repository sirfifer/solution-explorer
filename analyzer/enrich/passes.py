"""Phase 7 verification passes over the store (P7-3; extended by P7-4).

The passes share one harness (invoker, provenance stamping, staleness scoping,
projection-overlay storage, cost controls, dry-run, exit codes), exactly the
P7-2 pattern. P7-3 ships the first pass:

    verify_edges     (P7-3)        verdict per inferred edge.

P7-4 adds name_concerns, check_intents, and verify_findings alongside it.

All model output lands as provenance-stamped enrichment rows (see verdicts.py for
the target kinds and the projection overlay). Nothing is written unless it
validates (never junk). Refuted edges are marked and de-emphasized, never deleted
(the Phase 7 gate line; LENS-DESIGN.md I15).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..derive import derive_all
from ..store import FactStore
from .digest import DigestIndex, relationship_target_id
from .engine import (
    DEFAULT_MODEL,
    ClaudeCliInvoker,
    Invoker,
    InvokeResult,
    _parse_json_object,
)
from .overlay import apply_enrichment_overlay
from .partition import flatten_components
from .prompts import build_edge_verify_prompt
from .provenance import Clock, current_commit_sha, iso_now, stamp_enrichment
from .staleness import staleness_of

__all__ = [
    "VerifyConfig",
    "TargetOutcome",
    "PassReport",
    "verify_edges",
]

_EDGE_STATUSES = frozenset({"confirmed", "refuted", "uncertain"})


@dataclass
class VerifyConfig:
    store_path: Path
    root: Path
    update: bool = False
    max_targets: Optional[int] = None
    max_parallel: int = 4
    model: str = DEFAULT_MODEL
    dry_run: bool = False
    report_path: Optional[Path] = None
    intents_path: Optional[Path] = None
    propose_intents: bool = False


@dataclass
class TargetOutcome:
    id: str
    status: str  # "done" | "failed" | "skipped"
    verdict: Optional[str] = None
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


@dataclass
class PassReport:
    pass_name: str
    mode: str
    dry_run: bool
    target_count: int
    outcomes: list[TargetOutcome] = field(default_factory=list)
    total_cost_usd: float = 0.0
    notes: list[str] = field(default_factory=list)
    plan_preview: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def failed(self) -> list[str]:
        return [o.id for o in self.outcomes if o.status == "failed"]

    @property
    def done(self) -> int:
        return sum(1 for o in self.outcomes if o.status == "done")

    @property
    def ok(self) -> bool:
        return not self.failed

    def tally(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for o in self.outcomes:
            if o.verdict:
                out[o.verdict] = out.get(o.verdict, 0) + 1
        return out

    def to_dict(self) -> dict:
        return {
            "pass": self.pass_name,
            "mode": self.mode,
            "dry_run": self.dry_run,
            "target_count": self.target_count,
            "done": self.done,
            "failed": self.failed,
            "verdicts": self.tally(),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "notes": self.notes,
            "plan_preview": self.plan_preview,
            "extra": self.extra,
            "outcomes": [
                {
                    "id": o.id,
                    "status": o.status,
                    "verdict": o.verdict,
                    "cost_usd": round(o.cost_usd, 6),
                    "errors": o.errors,
                }
                for o in self.outcomes
            ],
        }


# --- shared harness ----------------------------------------------------------


def _invoke_json(
    invoker: Invoker, prompt: str, validate: Callable[[dict], list[str]]
) -> tuple[Optional[dict], float, list[str]]:
    """Invoke once, retry once with feedback, parse+validate. Never raises.

    Returns (obj or None, cost, errors). ``validate`` returns a list of error
    strings (empty means valid).
    """
    cost = 0.0
    feedback = ""
    errors: list[str] = ["not attempted"]
    for _ in range(2):
        result: InvokeResult = invoker(prompt + feedback)
        cost += result.cost_usd
        if not result.ok:
            errors = [result.error or "invocation failed"]
            feedback = f"\n\nPREVIOUS ATTEMPT FAILED: {result.error}. Return valid JSON."
            continue
        obj = _parse_json_object(result.text)
        if obj is None:
            errors = ["response was not a parseable JSON object"]
            feedback = "\n\nPREVIOUS ATTEMPT was not valid JSON. Return ONLY a JSON object."
            continue
        errs = validate(obj)
        if errs:
            errors = errs
            feedback = (
                "\n\nPREVIOUS ATTEMPT had these problems, fix them:\n"
                + "\n".join(f"- {e}" for e in errs[:10])
            )
            continue
        return obj, cost, []
    return None, cost, errors


def _component_index(arch: dict) -> dict[str, dict]:
    return {c["id"]: c for c in flatten_components(arch.get("components", []))}


def _endpoint_summary(index: dict[str, dict], node_id: str) -> dict:
    comp = index.get(node_id)
    if comp is None:
        return {"id": node_id, "resolved": False}
    ai = comp.get("ai_enhance") or {}
    return {
        "id": node_id,
        "name": comp.get("name"),
        "type": comp.get("type"),
        "language": comp.get("language"),
        "description": comp.get("description") or None,
        "help_text": ai.get("help_text"),
    }


def _prepare(store: FactStore, config: VerifyConfig) -> tuple[dict, DigestIndex]:
    """Derive the arch, build the digest index, and overlay existing enrichment.

    Overlaying existing enrichment gives endpoint summaries the AI help text where
    it exists (richer grounding). Derivation reads the store only.
    """
    _, arch = derive_all(store, config.root.name, root_path=str(config.root))
    index = DigestIndex.from_store(store)
    apply_enrichment_overlay(arch, store, digest_index=index)
    return arch, index


def _missing_or_stale(
    store: FactStore, index: DigestIndex, target_kind: str, target_id: str
) -> bool:
    """True when there is no verdict row for the target, or (on --update) it is
    stale. Used to scope --update work to what actually needs re-verifying."""
    row = next(
        (
            r
            for r in store.enrichment()
            if r["target_kind"] == target_kind and r["target_id"] == target_id
        ),
        None,
    )
    if row is None:
        return True
    current = index.for_target(target_kind, target_id)
    return staleness_of(row.get("derived_from_hash"), current) is True


def _finalize(report: PassReport, config: VerifyConfig) -> PassReport:
    if config.report_path is not None:
        config.report_path.parent.mkdir(parents=True, exist_ok=True)
        config.report_path.write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )
    return report


# --- P7-3: edge verification -------------------------------------------------


def verify_edges(
    config: VerifyConfig, *, invoker: Optional[Invoker] = None, clock: Clock = iso_now
) -> PassReport:
    """Verify inferred-confidence edges against their evidence (P7-3)."""
    if invoker is None:
        invoker = ClaudeCliInvoker(model=config.model)
    store = FactStore(str(config.store_path))
    try:
        arch, index = _prepare(store, config)
        comp_index = _component_index(arch)
        commit_sha = current_commit_sha(str(config.root))

        inferred = [
            rel for rel in arch.get("relationships", [])
            if rel.get("confidence") == "inferred"
        ]
        # Deterministic order.
        inferred.sort(key=lambda r: relationship_target_id(
            r.get("source", ""), r.get("target", ""), r.get("type", "")
        ))

        mode = "update" if config.update else "full"
        targets = []
        for rel in inferred:
            key = relationship_target_id(
                rel.get("source", ""), rel.get("target", ""), rel.get("type", "")
            )
            if config.update and not _missing_or_stale(store, index, "edge-verdict", key):
                continue
            targets.append((key, rel))
        if config.max_targets is not None:
            targets = targets[: config.max_targets]

        report = PassReport(
            pass_name="verify-edges", mode=mode, dry_run=config.dry_run,
            target_count=len(targets),
        )
        report.notes.append(
            f"{len(inferred)} inferred edge(s); {len(targets)} to verify"
        )

        def validate(obj: dict) -> list[str]:
            if obj.get("status") not in _EDGE_STATUSES:
                return [f"status must be one of {sorted(_EDGE_STATUSES)}"]
            if not (obj.get("reason") or "").strip():
                return ["reason must be a non-empty sentence"]
            return []

        if config.dry_run:
            for key, rel in targets:
                prompt = build_edge_verify_prompt(
                    rel,
                    _endpoint_summary(comp_index, rel.get("source", "")),
                    _endpoint_summary(comp_index, rel.get("target", "")),
                )
                report.plan_preview.append({"id": key, "prompt_chars": len(prompt)})
            return _finalize(report, config)

        for key, rel in targets:
            prompt = build_edge_verify_prompt(
                rel,
                _endpoint_summary(comp_index, rel.get("source", "")),
                _endpoint_summary(comp_index, rel.get("target", "")),
            )
            obj, cost, errs = _invoke_json(invoker, prompt, validate)
            outcome = TargetOutcome(id=key, status="failed", cost_usd=cost)
            if obj is None:
                outcome.errors = errs
            else:
                payload = {"status": obj["status"], "reason": obj["reason"].strip()}
                stamp_enrichment(
                    store, "edge-verdict", key, payload,
                    digest_index=index, commit_sha=commit_sha, clock=clock,
                )
                outcome.status = "done"
                outcome.verdict = obj["status"]
            report.outcomes.append(outcome)
        report.total_cost_usd = sum(o.cost_usd for o in report.outcomes)
        store.commit()
        return _finalize(report, config)
    finally:
        store.close()
