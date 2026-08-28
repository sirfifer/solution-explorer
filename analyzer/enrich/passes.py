"""Phase 7 verification and naming passes over the store (P7-3, P7-4).

Four passes share one harness (invoker, provenance stamping, staleness scoping,
projection-overlay storage, cost controls, dry-run, exit codes), exactly the
P7-2 pattern:

    verify_edges     (P7-3)        verdict per inferred edge.
    name_concerns    (P7-4 sub 1)  domain-language name per concern.
    check_intents    (P7-4 sub 2)  declared-intent conformance -> violation
                                    findings; optional candidate proposals.
    verify_findings  (P7-4 sub 3)  adversarial refutation of every finding.

All model output lands as provenance-stamped enrichment rows (see verdicts.py for
the target kinds and the projection overlay). Nothing is written unless it
validates (never junk). Refuted edges and findings are marked and de-emphasized,
never deleted (the Phase 7 gate line; LENS-DESIGN.md I15).
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
from .intents import IntentFileError, find_intents_file, load_intents
from .overlay import apply_enrichment_overlay
from .partition import flatten_components
from .prompts import (
    build_concern_name_prompt,
    build_edge_verify_batch_prompt,
    build_edge_verify_prompt,
    build_finding_verify_batch_prompt,
    build_finding_verify_prompt,
    build_identity_verify_batch_prompt,
    build_identity_verify_prompt,
    build_intent_conformance_prompt,
    build_intent_proposal_prompt,
)
from .provenance import Clock, current_commit_sha, iso_now, stamp_enrichment
from .staleness import staleness_of

__all__ = [
    "VerifyConfig",
    "TargetOutcome",
    "PassReport",
    "verify_edges",
    "name_concerns",
    "check_intents",
    "verify_findings",
]

_EDGE_STATUSES = frozenset({"confirmed", "refuted", "uncertain"})
_FINDING_VERDICTS = frozenset({"verified", "refuted", "uncertain"})


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
    # How many independent verdicts share one call. A verify answer is a status
    # and one sentence, so a per-item call spends nearly all of its cost on the
    # prompt it repeats: measured on 2026-08-25, 754 per-edge calls cost $10.50
    # and returned 21 output tokens each. Batching amortizes the fixed overhead
    # across items that were always judged independently anyway.
    verify_batch: int = 25
    # Exact bounded-run scope. max_targets merely truncates the global list and
    # can verify unrelated rows from a pre-existing store; these sets name the
    # targets the current ladder actually attempted.
    component_scope: Optional[frozenset[str]] = None
    relationship_scope: Optional[frozenset[str]] = None
    finding_scope: Optional[frozenset[str]] = None


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


# A verify batch is bounded by BYTES as well as by count. Counting items alone
# is the same mistake the fact blocks made: one oversized member makes the whole
# request impossible. A batch of twelve identity payloads exceeded the context
# window on the 2026-08-26 rebuild and the pass failed twice before giving up.
MAX_VERIFY_BATCH_CHARS = 200_000


def _batches(items: list, size: int, sizer=None) -> list[list]:
    """Split items into batches bounded by count AND serialized size.

    An item larger than the whole budget still gets its own batch rather than
    being dropped: a target that cannot be batched is still a target that must
    be verified.
    """
    out: list[list] = []
    current: list = []
    used = 0
    for item in items:
        cost = len(json.dumps(sizer(item) if sizer else item, default=str))
        if current and (len(current) >= size or used + cost > MAX_VERIFY_BATCH_CHARS):
            out.append(current)
            current, used = [], 0
        current.append(item)
        used += cost
    if current:
        out.append(current)
    return out


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

    Overlaying existing enrichment gives endpoint summaries and finding context
    the AI help text where it exists (richer grounding). Derivation reads the
    store only.
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
            if config.relationship_scope is not None and key not in config.relationship_scope:
                continue
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

        def validate_batch(obj: dict) -> list[str]:
            verdicts = obj.get("verdicts")
            if not isinstance(verdicts, dict) or not verdicts:
                return ["verdicts must be a non-empty object keyed by edge id"]
            return []

        batch_size = max(1, int(getattr(config, "verify_batch", 25) or 1))
        for chunk in _batches(targets, batch_size, sizer=lambda t: t[1]):
            if hasattr(invoker, "set_targets"):
                invoker.set_targets(len(chunk))
            prompt = build_edge_verify_batch_prompt([
                {
                    "id": key,
                    "edge": rel,
                    "source": _endpoint_summary(comp_index, rel.get("source", "")),
                    "target": _endpoint_summary(comp_index, rel.get("target", "")),
                }
                for key, rel in chunk
            ])
            obj, cost, errs = _invoke_json(invoker, prompt, validate_batch)
            verdicts = (obj or {}).get("verdicts") or {}
            # Cost is attributed evenly across the batch so per-target
            # accounting stays meaningful; the batch is one billable call.
            share = cost / max(1, len(chunk))
            for key, _rel in chunk:
                outcome = TargetOutcome(id=key, status="failed", cost_usd=share)
                entry = verdicts.get(key) if isinstance(verdicts, dict) else None
                # An edge the model did not answer for stays unverified. It is
                # never given a neighbour's verdict, and never defaulted to
                # confirmed: an unasked question has no answer.
                if not isinstance(entry, dict):
                    outcome.errors = errs or [
                        "no verdict returned for this edge in its batch"
                    ]
                elif entry.get("status") not in _EDGE_STATUSES:
                    outcome.errors = [
                        f"status must be one of {sorted(_EDGE_STATUSES)}"
                    ]
                elif not str(entry.get("reason") or "").strip():
                    outcome.errors = ["reason must be a non-empty sentence"]
                else:
                    payload = {
                        "status": entry["status"],
                        "reason": str(entry["reason"]).strip(),
                    }
                    stamp_enrichment(
                        store, "edge-verdict", key, payload,
                        digest_index=index, commit_sha=commit_sha, clock=clock,
                    )
                    outcome.status = "done"
                    outcome.verdict = entry["status"]
                report.outcomes.append(outcome)
        report.total_cost_usd = sum(o.cost_usd for o in report.outcomes)
        store.commit()
        return _finalize(report, config)
    finally:
        store.close()


# --- P7-4 sub-pass 1: concern naming -----------------------------------------


def name_concerns(
    config: VerifyConfig, *, invoker: Optional[Invoker] = None, clock: Clock = iso_now
) -> PassReport:
    """Give each mechanical concern a domain-language name and description (P7-4)."""
    if invoker is None:
        invoker = ClaudeCliInvoker(model=config.model)
    store = FactStore(str(config.store_path))
    try:
        arch, index = _prepare(store, config)
        comp_index = _component_index(arch)
        commit_sha = current_commit_sha(str(config.root))

        concerns = sorted(arch.get("concerns", []) or [], key=lambda c: c.get("id", ""))
        mode = "update" if config.update else "full"
        targets = [
            c for c in concerns
            if not (config.update and not _missing_or_stale(store, index, "concern", c["id"]))
        ]
        if config.max_targets is not None:
            targets = targets[: config.max_targets]

        report = PassReport(
            pass_name="name-concerns", mode=mode, dry_run=config.dry_run,
            target_count=len(targets),
        )
        report.notes.append(f"{len(concerns)} concern(s); {len(targets)} to name")

        def member_facts(concern: dict) -> list[dict]:
            facts = []
            for m in concern.get("members", []) or []:
                cid = m.get("component_id")
                comp = comp_index.get(cid, {})
                facts.append({
                    "component_id": cid,
                    "name": comp.get("name"),
                    "type": comp.get("type"),
                    "language": comp.get("language"),
                    "files": (m.get("files") or [])[:5],
                    "evidence": (m.get("evidence") or [])[:3],
                })
            return facts

        def validate(obj: dict) -> list[str]:
            if not (obj.get("name") or "").strip():
                return ["name must be a non-empty domain-language label"]
            return []

        if config.dry_run:
            for c in targets:
                prompt = build_concern_name_prompt(c, member_facts(c))
                report.plan_preview.append({"id": c["id"], "prompt_chars": len(prompt)})
            return _finalize(report, config)

        for c in targets:
            prompt = build_concern_name_prompt(c, member_facts(c))
            obj, cost, errs = _invoke_json(invoker, prompt, validate)
            outcome = TargetOutcome(id=c["id"], status="failed", cost_usd=cost)
            if obj is None:
                outcome.errors = errs
            else:
                payload = {
                    "name": obj["name"].strip(),
                    "description": (obj.get("description") or "").strip(),
                }
                stamp_enrichment(
                    store, "concern", c["id"], payload,
                    digest_index=index, commit_sha=commit_sha, clock=clock,
                )
                outcome.status = "done"
                outcome.verdict = "named"
            report.outcomes.append(outcome)
        report.total_cost_usd = sum(o.cost_usd for o in report.outcomes)
        store.commit()
        return _finalize(report, config)
    finally:
        store.close()


# --- P7-4 sub-pass 2: intent conformance -------------------------------------


def _intent_scope_facts(intent: dict, arch: dict, comp_index: dict[str, dict]) -> dict:
    """Select the store facts relevant to one intent (its scope slice).

    Scope hints (component-id substrings, concern kinds, or keywords) select
    matching components; when no hint matches, the whole (bounded) model is sent
    so the intent is still evaluable. Concerns, capabilities, entities, and edges
    are filtered to the selected components.
    """
    hints = [h.lower() for h in (intent.get("scope") or [])]

    def matches(comp: dict) -> bool:
        if not hints:
            return True
        hay = " ".join(str(comp.get(k, "")) for k in ("id", "name", "type", "language", "description")).lower()
        return any(h in hay for h in hints)

    selected = [c for c in comp_index.values() if matches(c)]
    if not selected:
        selected = list(comp_index.values())
    selected_ids = {c["id"] for c in selected}
    # Bound the payload.
    selected = sorted(selected, key=lambda c: c["id"])[:60]

    concerns = [
        {"id": c.get("id"), "kind": c.get("kind"),
         "members": [m.get("component_id") for m in (c.get("members") or [])]}
        for c in (arch.get("concerns") or [])
        if (not hints) or any(h in (c.get("kind") or "").lower() for h in hints)
        or any(m.get("component_id") in selected_ids for m in (c.get("members") or []))
    ]
    capabilities = [
        {"kind": c.get("kind"), "name": c.get("name"), "component_id": c.get("component_id")}
        for c in (arch.get("capabilities") or [])
        if c.get("component_id") in selected_ids
    ][:60]
    entities = [
        {"name": e.get("name"), "kind": e.get("kind"), "component_id": e.get("component_id")}
        for e in (arch.get("data_entities") or [])
        if e.get("component_id") in selected_ids
    ][:60]
    edges = [
        {"source": r.get("source"), "target": r.get("target"), "type": r.get("type")}
        for r in (arch.get("relationships") or [])
        if r.get("source") in selected_ids or r.get("target") in selected_ids
    ][:80]
    return {
        "components": [
            {"id": c["id"], "name": c.get("name"), "type": c.get("type"),
             "language": c.get("language"), "description": c.get("description") or None}
            for c in selected
        ],
        "concerns": concerns,
        "capabilities": capabilities,
        "data_entities": entities,
        "edges": edges,
    }


def _intent_violation_id(intent_id: str) -> str:
    return f"finding:intent-violation:{intent_id}"


def check_intents(
    config: VerifyConfig, *, invoker: Optional[Invoker] = None, clock: Clock = iso_now
) -> PassReport:
    """Evaluate declared intents against the model; emit violation findings (P7-4).

    A satisfied intent removes any prior violation finding for it (no stale data).
    A violated intent emits a ``finding`` enrichment row (kind intent-violation)
    with the violating members and evidence, marked unverified for sub-pass 3.
    """
    if invoker is None:
        invoker = ClaudeCliInvoker(model=config.model)
    store = FactStore(str(config.store_path))
    try:
        arch, index = _prepare(store, config)
        comp_index = _component_index(arch)
        commit_sha = current_commit_sha(str(config.root))

        report = PassReport(
            pass_name="check-intents", mode="update" if config.update else "full",
            dry_run=config.dry_run, target_count=0,
        )

        intents_file = find_intents_file(config.root, config.intents_path)
        if config.intents_path is not None and not config.intents_path.is_file():
            report.notes.append(f"intents file not found: {config.intents_path}")
            return _finalize(report, config)
        intents: list = []
        if intents_file is not None:
            try:
                intents = load_intents(intents_file)
            except IntentFileError as exc:
                report.notes.append(f"intents file error: {exc}")
                report.outcomes.append(TargetOutcome(id=str(intents_file), status="failed", errors=[str(exc)]))
                return _finalize(report, config)
            report.notes.append(f"{len(intents)} declared intent(s) from {intents_file.name}")
        else:
            report.notes.append("no declared-intents file; nothing to check")
        report.target_count = len(intents)

        def validate(obj: dict) -> list[str]:
            if not isinstance(obj.get("satisfied"), bool):
                return ["'satisfied' must be a boolean"]
            if not (obj.get("reason") or "").strip():
                return ["reason must be non-empty"]
            return []

        # Optional proposal pass (advisory; never auto-adopted).
        if config.propose_intents and not config.dry_run:
            observed = {
                "name": arch.get("name"),
                "description": arch.get("description"),
                "components": [
                    {"id": c["id"], "name": c.get("name"), "type": c.get("type"),
                     "description": c.get("description") or None}
                    for c in sorted(comp_index.values(), key=lambda c: c["id"])[:80]
                ],
                "concerns": [{"id": c.get("id"), "kind": c.get("kind")} for c in (arch.get("concerns") or [])],
            }
            pobj, pcost, _ = _invoke_json(
                invoker, build_intent_proposal_prompt(observed),
                lambda o: [] if isinstance(o.get("candidates"), list) else ["'candidates' must be a list"],
            )
            report.total_cost_usd += pcost
            report.extra["proposed_intents"] = (pobj or {}).get("candidates", [])

        if config.dry_run:
            for intent in intents:
                prompt = build_intent_conformance_prompt(
                    intent, _intent_scope_facts(intent, arch, comp_index)
                )
                report.plan_preview.append({"id": intent.id, "prompt_chars": len(prompt)})
            return _finalize(report, config)

        for intent in intents:
            scope = _intent_scope_facts(intent, arch, comp_index)
            prompt = build_intent_conformance_prompt(intent, scope)
            obj, cost, errs = _invoke_json(invoker, prompt, validate)
            outcome = TargetOutcome(id=intent.id, status="failed", cost_usd=cost)
            vid = _intent_violation_id(intent.id)
            if obj is None:
                outcome.errors = errs
                report.outcomes.append(outcome)
                continue
            if obj["satisfied"]:
                # Remove any prior violation finding (and its verdict) for this intent.
                store.delete_enrichment("finding", vid)
                store.delete_enrichment("finding-verdict", vid)
                outcome.status = "done"
                outcome.verdict = "satisfied"
            else:
                members = []
                for vm in obj.get("violating_members", []) or []:
                    if isinstance(vm, dict) and vm.get("component_id"):
                        members.append({
                            "kind": "component", "id": vm["component_id"],
                            "component_id": vm["component_id"], "why": vm.get("why"),
                        })
                record = {
                    "id": vid,
                    "kind": "intent-violation",
                    "summary": obj["reason"].strip(),
                    "members": members,
                    "evidence": [
                        {"intent": intent.statement},
                        {"reason": obj["reason"].strip()},
                    ],
                    "confidence": obj.get("confidence", "medium"),
                    "verification_status": "unverified",
                    "rank_score": 50.0 + float(len(members)),
                    "intent_id": intent.id,
                }
                index.register_finding(vid, "intent-violation", members)
                stamp_enrichment(
                    store, "finding", vid, record,
                    digest_index=index, commit_sha=commit_sha, clock=clock,
                )
                outcome.status = "done"
                outcome.verdict = "violation"
            report.outcomes.append(outcome)
        report.total_cost_usd += sum(o.cost_usd for o in report.outcomes)
        store.commit()
        return _finalize(report, config)
    finally:
        store.close()


# --- P7-4 sub-pass 3: finding verification -----------------------------------


def _all_findings(store: FactStore) -> list[dict]:
    """Deterministic findings (findings table) plus AI intent-violation findings
    (enrichment 'finding' rows). Deterministic order by id."""
    out: list[dict] = list(store.findings())
    seen = {f.get("id") for f in out}
    for row in store.enrichment():
        if row["target_kind"] == "finding":
            payload = row.get("payload") or {}
            fid = payload.get("id") or row["target_id"]
            if fid not in seen:
                rec = dict(payload)
                rec.setdefault("id", fid)
                out.append(rec)
                seen.add(fid)
    out.sort(key=lambda f: f.get("id") or "")
    return out


def verify_findings(
    config: VerifyConfig, *, invoker: Optional[Invoker] = None, clock: Clock = iso_now
) -> PassReport:
    """Adversarially verify every finding against its own evidence (P7-4 sub 3)."""
    if invoker is None:
        invoker = ClaudeCliInvoker(model=config.model)
    store = FactStore(str(config.store_path))
    try:
        arch, index = _prepare(store, config)
        # Register AI-finding digests so their verdicts can be stamped/staleness-checked.
        for f in _all_findings(store):
            if f.get("kind") == "intent-violation":
                index.register_finding(f["id"], f.get("kind", ""), f.get("members"))
        commit_sha = current_commit_sha(str(config.root))

        findings = _all_findings(store)
        mode = "update" if config.update else "full"
        targets = [
            f for f in findings
            if _missing_or_stale(store, index, "finding-verdict", f["id"])
        ]
        if config.finding_scope is not None:
            targets = [f for f in targets if f.get("id") in config.finding_scope]
        elif config.component_scope is not None:
            def _member_ids(finding: dict) -> set[str]:
                out = set()
                for member in finding.get("members") or []:
                    if isinstance(member, str):
                        out.add(member)
                    elif isinstance(member, dict):
                        value = member.get("component_id") or member.get("id")
                        if value:
                            out.add(str(value))
                return out

            targets = [
                f for f in targets if _member_ids(f) & set(config.component_scope)
            ]
        # On a full run, verify every finding lacking a verdict; on --update also
        # re-verify stale ones (both captured by _missing_or_stale, which returns
        # True for missing always and for stale only matters when a row exists).
        if config.max_targets is not None:
            targets = targets[: config.max_targets]

        report = PassReport(
            pass_name="verify-findings", mode=mode, dry_run=config.dry_run,
            target_count=len(targets),
        )
        report.notes.append(f"{len(findings)} finding(s); {len(targets)} to verify")

        def validate(obj: dict) -> list[str]:
            if obj.get("verdict") not in _FINDING_VERDICTS:
                return [f"verdict must be one of {sorted(_FINDING_VERDICTS)}"]
            if not (obj.get("reason") or "").strip():
                return ["reason must be non-empty"]
            return []

        if config.dry_run:
            for f in targets:
                report.plan_preview.append(
                    {"id": f["id"], "prompt_chars": len(build_finding_verify_prompt(f))}
                )
            return _finalize(report, config)

        status_map = {"verified": "verified", "refuted": "refuted", "uncertain": "unverified"}

        def validate_batch(obj: dict) -> list[str]:
            verdicts = obj.get("verdicts")
            if not isinstance(verdicts, dict) or not verdicts:
                return ["verdicts must be a non-empty object keyed by finding id"]
            return []

        batch_size = max(1, int(getattr(config, "verify_batch", 25) or 1))
        for chunk in _batches(targets, batch_size):
            if hasattr(invoker, "set_targets"):
                invoker.set_targets(len(chunk))
            prompt = build_finding_verify_batch_prompt(chunk)
            batch_obj, cost, errs = _invoke_json(invoker, prompt, validate_batch)
            verdicts = (batch_obj or {}).get("verdicts") or {}
            share = cost / max(1, len(chunk))
            for f in chunk:
                obj = verdicts.get(f["id"]) if isinstance(verdicts, dict) else None
                outcome = TargetOutcome(id=f["id"], status="failed", cost_usd=share)
                # A finding with no verdict stays unverified. It is never marked
                # verified by omission: the whole point of this pass is that only
                # findings which SURVIVE a refutation attempt pass it.
                problems = (
                    [errs and errs[0] or "no verdict returned for this finding in its batch"]
                    if not isinstance(obj, dict)
                    else validate(obj)
                )
                if problems:
                    outcome.errors = problems
                    report.outcomes.append(outcome)
                    continue
                verdict = obj["verdict"]
                new_status = status_map[verdict]
                payload = {"verification_status": new_status, "reason": obj["reason"].strip()}
                stamp_enrichment(
                    store, "finding-verdict", f["id"], payload,
                    digest_index=index, commit_sha=commit_sha, clock=clock,
                )
                # Same-session convenience: reflect the verdict on the findings
                # table for a deterministic finding (a re-derive resets it; the
                # enrichment overlay is the durable, authoritative record).
                store.set_finding_verification(f["id"], new_status)
                outcome.status = "done"
                outcome.verdict = verdict
                report.outcomes.append(outcome)
        report.total_cost_usd = sum(o.cost_usd for o in report.outcomes)
        store.commit()
        return _finalize(report, config)
    finally:
        store.close()


# --- S2 identity gate: verify published component identity --------------------

_IDENTITY_FIELDS = ("name", "type", "framework", "port")
_IDENTITY_STATUSES = frozenset({"confirmed", "corrected", "uncertain"})
# Hero types plus infrastructure: the identities whose wrongness misleads a
# newcomer hardest, and the promotion outputs the S2 guards cannot judge
# statically. Components without any of the promotion signals are skipped: a
# plain module named after its directory has nothing to get wrong.
_IDENTITY_TARGET_TYPES = frozenset({
    "ios-client", "android-client", "mobile-client", "web-client",
    "api-server", "watch-app", "desktop-app", "cli-tool", "service",
    "infrastructure",
})


def _identity_targets(comp_index: dict[str, dict]) -> list[dict]:
    """Components whose published identity carries verifiable claims."""
    out = []
    for comp_id in sorted(comp_index):
        comp = comp_index[comp_id]
        docs = comp.get("docs") or {}
        if (
            comp.get("type") in _IDENTITY_TARGET_TYPES
            or comp.get("port")
            or comp.get("framework")
            or docs.get("api_endpoints")
        ):
            out.append(comp)
    return out


def _framework_evidence(store: FactStore) -> dict[str, dict]:
    """Per-component framework signals: name, file count, one path exemplar.

    The v2 run's identity pass returned uncertain for 98 of 99 components, 97
    of them on the framework field alone, and the judge's own reasons said the
    same thing every time: no framework evidence in the supplied facts. The
    store held 101 framework signal rows the prompt never shipped. This is
    that evidence, aggregated small (about 300 chars per component), built
    once per run (IMPLEMENTATION-DELTA-ORCH.md section 2.3).
    """
    paths = {row["id"]: row["path"] for row in store.files()}
    path_components: dict[str, list[str]] = {}
    for row in store.component_files():
        path_components.setdefault(row["path"], []).append(row["component_id"])
    out: dict[str, dict] = {}
    for signal in store.signals():
        if signal.get("kind") != "framework":
            continue
        name = (signal.get("value") or {}).get("name")
        path = paths.get(signal.get("file_id"))
        if not name or not path:
            continue
        for comp_id in path_components.get(path, []):
            per_name = out.setdefault(comp_id, {}).setdefault(
                name, {"files": 0, "example": path}
            )
            per_name["files"] += 1
    return out


def _identity_facts(comp: dict, framework_evidence: Optional[dict] = None) -> dict:
    """Compact evidence block for the identity prompt, from projected facts."""
    docs = comp.get("docs") or {}
    ai = comp.get("ai_enhance") or {}
    endpoints = docs.get("api_endpoints") or []
    return {
        "file_sample": (comp.get("files") or [])[:15],
        "file_count": len(comp.get("files") or []),
        "config_files": comp.get("config_files") or [],
        "endpoint_count": len(endpoints),
        "endpoint_sample": endpoints[:5],
        "env_vars": (docs.get("env_vars") or [])[:10],
        "purpose": docs.get("purpose") or None,
        "patterns": docs.get("patterns") or [],
        "framework_signals": (framework_evidence or {}).get(comp.get("id"), {}),
        "prose": {
            "help_text": ai.get("help_text"),
            "description": ai.get("description"),
        },
    }


def _validate_identity(obj: dict) -> list[str]:
    fields = obj.get("fields")
    if not isinstance(fields, dict):
        return ['"fields" must be an object']
    errs: list[str] = []
    for fname in _IDENTITY_FIELDS:
        entry = fields.get(fname)
        if not isinstance(entry, dict):
            errs.append(f'fields.{fname} is required')
            continue
        status = entry.get("status")
        if status not in _IDENTITY_STATUSES:
            errs.append(
                f"fields.{fname}.status must be one of {sorted(_IDENTITY_STATUSES)}"
            )
            continue
        if status == "corrected":
            if entry.get("value") in (None, ""):
                errs.append(f"fields.{fname}: corrected requires a value")
            if not (entry.get("reason") or "").strip():
                errs.append(f"fields.{fname}: corrected requires a reason")
            evidence = entry.get("evidence")
            if not (isinstance(evidence, dict) and evidence.get("file")):
                errs.append(f"fields.{fname}: corrected requires evidence.file")
        if status == "uncertain" and not (entry.get("reason") or "").strip():
            errs.append(f"fields.{fname}: uncertain requires a reason")
    extra = set(fields) - set(_IDENTITY_FIELDS)
    if extra:
        errs.append(f"unknown fields: {sorted(extra)}")
    prose = obj.get("prose_issues")
    if prose is not None:
        if not isinstance(prose, list):
            errs.append('"prose_issues" must be a list')
        else:
            for i, issue in enumerate(prose):
                if not (
                    isinstance(issue, dict)
                    and (issue.get("claim") or "").strip()
                    and (issue.get("fact") or "").strip()
                ):
                    errs.append(f"prose_issues[{i}] needs claim and fact")
    return errs


def verify_identity(
    config: VerifyConfig, *, invoker: Optional[Invoker] = None, clock: Clock = iso_now
) -> PassReport:
    """Verify published component identities against store facts (S2 gate).

    The owner's ruling (2026-08-17): identity is resolved or flagged, never
    published as a guess. Confirmations stamp a verdict row; corrections carry
    the corrected value with cited evidence and are applied at projection with
    an ``identity_corrections`` provenance marker; uncertains become honest-gap
    entries at projection. Prose contradictions (numbers in enrichment prose
    that disagree with analyzer facts) ride the same row for the re-enrichment
    loop.
    """
    if invoker is None:
        invoker = ClaudeCliInvoker(model=config.model)
    store = FactStore(str(config.store_path))
    try:
        arch, index = _prepare(store, config)
        comp_index = _component_index(arch)
        commit_sha = current_commit_sha(str(config.root))

        framework_evidence = _framework_evidence(store)
        candidates = _identity_targets(comp_index)
        mode = "update" if config.update else "full"
        targets = [
            comp for comp in candidates
            if _missing_or_stale(store, index, "identity-verdict", comp["id"])
        ]
        if config.component_scope is not None:
            targets = [comp for comp in targets if comp["id"] in config.component_scope]
        if config.max_targets is not None:
            targets = targets[: config.max_targets]

        report = PassReport(
            pass_name="verify-identity", mode=mode, dry_run=config.dry_run,
            target_count=len(targets),
        )
        report.notes.append(
            f"{len(candidates)} identity-bearing component(s); "
            f"{len(targets)} to verify"
        )

        if config.dry_run:
            for comp in targets:
                prompt = build_identity_verify_prompt(comp, _identity_facts(comp, framework_evidence))
                report.plan_preview.append(
                    {"id": comp["id"], "prompt_chars": len(prompt)}
                )
            return _finalize(report, config)

        def _validate_identity_batch(obj: dict) -> list[str]:
            comps = obj.get("components")
            if not isinstance(comps, dict) or not comps:
                return ["components must be a non-empty object keyed by component id"]
            return []

        # Identity answers are ~14x larger per item than an edge verdict, so
        # they take a smaller batch. Still one call for a dozen components
        # instead of a dozen calls.
        batch_size = max(1, int(getattr(config, "verify_batch", 25) or 1) // 2)
        for chunk in _batches(
            targets, batch_size,
            sizer=lambda c: _identity_facts(c, framework_evidence),
        ):
            if hasattr(invoker, "set_targets"):
                invoker.set_targets(len(chunk))
            prompt = build_identity_verify_batch_prompt([
                {
                    "id": comp["id"],
                    "component": comp,
                    "facts": _identity_facts(comp, framework_evidence),
                }
                for comp in chunk
            ])
            obj, cost, errs = _invoke_json(invoker, prompt, _validate_identity_batch)
            answers = (obj or {}).get("components") or {}
            share = cost / max(1, len(chunk))
            for comp in chunk:
                entry = answers.get(comp["id"]) if isinstance(answers, dict) else None
                outcome = TargetOutcome(id=comp["id"], status="failed", cost_usd=share)
                # A component the model skipped stays unverified. Identity is a
                # published claim; leaving it unchecked is honest, inventing a
                # confirmation is not.
                if not isinstance(entry, dict):
                    outcome.errors = errs or [
                        "no verdict returned for this component in its batch"
                    ]
                    report.outcomes.append(outcome)
                    continue
                field_errors = _validate_identity(entry)
                if field_errors:
                    outcome.errors = field_errors
                    report.outcomes.append(outcome)
                    continue
                obj = entry
                payload = {
                    "fields": obj["fields"],
                    "prose_issues": obj.get("prose_issues") or [],
                }
                stamp_enrichment(
                    store, "identity-verdict", comp["id"], payload,
                    digest_index=index, commit_sha=commit_sha, clock=clock,
                )
                statuses = {
                    f: (obj["fields"].get(f) or {}).get("status")
                    for f in _IDENTITY_FIELDS
                }
                if "corrected" in statuses.values():
                    outcome.verdict = "corrected"
                elif "uncertain" in statuses.values():
                    outcome.verdict = "uncertain"
                else:
                    outcome.verdict = "confirmed"
                outcome.status = "done"
                report.outcomes.append(outcome)
        report.total_cost_usd = sum(o.cost_usd for o in report.outcomes)
        store.commit()
        return _finalize(report, config)
    finally:
        store.close()
