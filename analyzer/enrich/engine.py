"""Headless enrichment engine: the industrialized DPEA pipeline over the store.

This is the machine form of the `/ai-assist` ritual (SKILL.md). It reads a v2
fact store, plans partitions deterministically, builds per-partition prompts from
store facts, invokes Claude headlessly (one call per partition, bounded
parallel), validates each response against the payload schema, retries a failed
partition once with the validator feedback, writes provenance-stamped enrichment
rows via the P7-1 helpers (never junk: a partition that fails validation twice is
recorded failed and its targets stay unenriched), then runs the existing quality
scorer as a gate. --update scopes work to stale/missing targets plus their
architectural neighbours using the P7-1 staleness model.

Invariants: AI writes only the enrichment overlay (I1); every row carries its
digest and commit (I5); no LLM calls happen at query time (I9) because all model
work is here, at enrichment time. No hardcoded paths: the scorer and store are
located from the repo root and store-path arguments.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from ..contracts import gap_from_exception

if TYPE_CHECKING:
    # Type-only import: avoids a runtime circular import (retry imports from
    # engine). The annotation is a string under `from __future__ import
    # annotations`, so RetryPolicy is never needed at runtime here.
    from .retry import RetryPolicy
from ..derive import derive_all
from ..store import FactStore
from .digest import ARCH_TARGET_ID, DigestIndex
from .overlay import apply_enrichment_overlay
from .partition import Partition, PartitionPlan, flatten_components, plan_partitions
from .prompts import StoreFacts, build_architecture_prompt, build_partition_prompt
from .provenance import Clock, current_commit_sha, iso_now, stamp_enrichment
from .staleness import enrichment_staleness

__all__ = [
    "EnhanceConfig",
    "InvokeResult",
    "Invoker",
    "ClaudeCliInvoker",
    "PartitionOutcome",
    "EnhanceReport",
    "run_enhance",
    "load_scorer",
    "DEFAULT_MODEL",
    "DEFAULT_MAX_PARALLEL",
    "DEFAULT_MAX_COST_USD",
]

DEFAULT_MODEL = "sonnet"
DEFAULT_MAX_PARALLEL = 4


# --- scorer wiring (single source of truth: the existing gate script) --------

_SCORER_CACHE: Any = None


def _repo_root() -> Path:
    # analyzer/enrich/engine.py -> parents[2] is the repo root.
    return Path(__file__).resolve().parents[2]


def scorer_path() -> Path:
    return _repo_root() / "scripts" / "score-ai-enhancement-quality.py"


def load_scorer() -> Any:
    """Import the quality scorer script as a module (wire, do not rewrite).

    The engine reuses the scorer's own validators for per-response schema
    validation so partition-time validation and the final gate share one rule
    set. The scorer is a hyphenated script, not an importable package, so it is
    loaded by file path relative to the repo root (no hardcoded absolute path).
    """
    global _SCORER_CACHE
    if _SCORER_CACHE is None:
        path = scorer_path()
        spec = importlib.util.spec_from_file_location("_ai_quality_scorer", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load scorer from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SCORER_CACHE = module
    return _SCORER_CACHE


# --- invocation --------------------------------------------------------------


@dataclass
class InvokeResult:
    """One headless model call result.

    ``status_code`` carries the CLI envelope's ``api_error_status`` when the call
    failed with a structured API error (for example 429 rate limit, 529 overloaded,
    404 model-not-found). It is the primary signal the R2 transport-retry layer
    uses to classify a failure as transient versus deterministic; it is None for a
    success, a spawn failure, a subprocess timeout, or a parse failure.
    """

    ok: bool
    text: str
    cost_usd: float = 0.0
    usage: dict = field(default_factory=dict)
    error: Optional[str] = None
    status_code: Optional[int] = None


# An invoker takes a prompt and returns an InvokeResult. Injectable so tests can
# mock the model without shelling out.
Invoker = Callable[[str], InvokeResult]


class ClaudeCliInvoker:
    """Invoke Claude headlessly via the `claude` CLI (the installed mechanism).

    Runs ``claude -p --output-format json --model <model>`` with the prompt on
    stdin (stdin avoids ARG_MAX limits on large partition prompts), then parses
    the JSON envelope's ``result`` (model text), ``total_cost_usd``, and
    ``usage``. The Python Agent SDK is not installed in this environment; the CLI
    is the simplest available headless path and reports cost per call.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        *,
        claude_bin: str = "claude",
        timeout: int = 600,
    ):
        self.model = model
        self.claude_bin = claude_bin
        self.timeout = timeout

    def __call__(self, prompt: str) -> InvokeResult:
        try:
            proc = subprocess.run(
                [
                    self.claude_bin, "-p",
                    "--output-format", "json",
                    "--model", self.model,
                ],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            # Spawn failure or subprocess timeout: a bounded transient (R2).
            return InvokeResult(ok=False, text="", error=f"invocation failed: {exc}")
        if proc.returncode != 0:
            # A nonzero exit can still carry a structured JSON error envelope on
            # stdout: a real claude CLI run returns exit 1 for an API error WITH
            # is_error/api_error_status in the envelope (for example a 429 rate
            # limit or a 404 model-not-found). Surface that status so the R2
            # retry layer can tell a transient (429/5xx) from a deterministic
            # (4xx) failure; fall back to stderr only when there is no envelope.
            status, detail = _envelope_error(proc.stdout)
            if status is not None or detail is not None:
                return InvokeResult(
                    ok=False,
                    text=detail or "",
                    error=f"claude exited {proc.returncode}: {(detail or proc.stderr).strip()[:400]}",
                    status_code=status,
                )
            return InvokeResult(
                ok=False, text="",
                error=f"claude exited {proc.returncode}: {proc.stderr.strip()[:400]}",
            )
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            # Well-formed run (exit 0) that returned non-JSON: a deterministic
            # parse failure. NEVER retried at the transport layer (R2).
            return InvokeResult(ok=False, text="", error=f"unparseable envelope: {exc}")
        if envelope.get("is_error"):
            return InvokeResult(
                ok=False, text=str(envelope.get("result", "")),
                cost_usd=float(envelope.get("total_cost_usd", 0.0) or 0.0),
                usage=envelope.get("usage", {}) or {},
                error="model reported error",
                status_code=_coerce_status(envelope.get("api_error_status")),
            )
        return InvokeResult(
            ok=True,
            text=str(envelope.get("result", "")),
            cost_usd=float(envelope.get("total_cost_usd", 0.0) or 0.0),
            usage=envelope.get("usage", {}) or {},
        )


def _coerce_status(value: Any) -> Optional[int]:
    """Coerce a CLI ``api_error_status`` to an int, tolerating a digit string.

    The observed CLI reports an integer, but a version that emitted ``"500"`` as a
    string would otherwise read as no-status and misclassify a transient 5xx as
    deterministic. Accepts an int or a digit string; rejects bool (a subclass of
    int) and anything else, returning None so the caller falls back cleanly.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _envelope_error(stdout: str) -> tuple[Optional[int], Optional[str]]:
    """Extract (api_error_status, result-detail) from a CLI JSON envelope.

    Returns (None, None) when stdout is not a JSON object, so the caller can fall
    back to stderr. Kept tiny and pure so the nonzero-exit path stays legible.
    """
    try:
        env = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return None, None
    if not isinstance(env, dict):
        return None, None
    detail = env.get("result")
    return (
        _coerce_status(env.get("api_error_status")),
        str(detail) if detail is not None else None,
    )


# --- config and report -------------------------------------------------------

# Default per-run cost ceiling (USD) for an enrichment run. Generous by design:
# the known enrichment targets (the ~190-component iOS demo and this self-repo
# dogfood) each cost well under a dollar in practice, so this ceiling never
# truncates a legitimate run, while it bounds a pathological runaway (a flaky
# dependency causing repeated paid retries, or an accidentally huge input). When
# the ceiling is reached the run stops LAUNCHING new partitions, lets in-flight
# ones finish, records the rest honestly as skipped, and exits successfully with
# the partial state reported. Operators with genuinely larger runs raise it with
# --max-cost-usd. This bounds enrichment only (a real-API, explicitly-invoked
# path); it does not touch the deterministic analyzer output or the golden legs.
DEFAULT_MAX_COST_USD = 10.0


@dataclass
class EnhanceConfig:
    store_path: Path
    root: Path
    update: bool = False
    max_partitions: Optional[int] = None
    max_parallel: int = DEFAULT_MAX_PARALLEL
    model: str = DEFAULT_MODEL
    dry_run: bool = False
    threshold: float = 85.0
    report_path: Optional[Path] = None
    max_lines: int = 50_000
    max_components: int = 30
    min_components: int = 5
    # R2 controls. ``max_cost_usd`` caps total reported cost across ALL attempts
    # (retries count); None disables the ceiling. ``retry_policy`` is the
    # injectable transport-retry policy applied to the DEFAULT invoker (an
    # explicitly injected invoker is used as-is, so tests wrap their own).
    max_cost_usd: Optional[float] = DEFAULT_MAX_COST_USD
    retry_policy: Optional[RetryPolicy] = None


@dataclass
class PartitionOutcome:
    id: int
    component_ids: list[str]
    relationship_keys: list[str]
    status: str  # "enriched" | "failed" | "skipped"
    attempts: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


@dataclass
class EnhanceReport:
    mode: str
    dry_run: bool
    partition_count: int
    partitions: list[PartitionOutcome] = field(default_factory=list)
    components_enriched: int = 0
    relationships_enriched: int = 0
    architecture_enriched: bool = False
    total_cost_usd: float = 0.0
    scorer_pass: Optional[bool] = None
    scorer_summary: Optional[str] = None
    plan_preview: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def failed_partitions(self) -> list[int]:
        return [p.id for p in self.partitions if p.status == "failed"]

    @property
    def ok(self) -> bool:
        """True when nothing failed and (if a gate ran) the gate passed."""
        if self.failed_partitions:
            return False
        if self.scorer_pass is False:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "dry_run": self.dry_run,
            "partition_count": self.partition_count,
            "components_enriched": self.components_enriched,
            "relationships_enriched": self.relationships_enriched,
            "architecture_enriched": self.architecture_enriched,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "scorer_pass": self.scorer_pass,
            "scorer_summary": self.scorer_summary,
            "failed_partitions": self.failed_partitions,
            "notes": self.notes,
            "partitions": [
                {
                    "id": p.id,
                    "status": p.status,
                    "attempts": p.attempts,
                    "components": p.component_ids,
                    "relationships": p.relationship_keys,
                    "cost_usd": round(p.cost_usd, 6),
                    "errors": p.errors,
                }
                for p in self.partitions
            ],
            "plan_preview": self.plan_preview,
        }


# --- response parsing, cleaning, validation ----------------------------------


def _parse_json_object(text: str) -> Optional[dict]:
    """Parse a JSON object from model text, tolerating markdown fences."""
    s = text.strip()
    if s.startswith("```"):
        # Strip a leading ```json / ``` fence and the trailing fence.
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.rstrip().endswith("```"):
            s = s.rsplit("```", 1)[0]
    s = s.strip()
    # Fall back to the first {...} span if there is leading/trailing chatter.
    if not s.startswith("{"):
        start = s.find("{")
        end = s.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        s = s[start : end + 1]
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _clean_component_payload(scorer: Any, ai: dict, clock: Clock) -> dict:
    """Keep only schema keys, then stamp engine-owned metadata."""
    allowed = scorer.REQUIRED_COMPONENT_FIELDS | scorer.OPTIONAL_COMPONENT_FIELDS
    out = {k: v for k, v in ai.items() if k in allowed}
    out["ai_enhanced_at"] = clock()
    out["ai_enhance_version"] = 2
    return out


def _clean_relationship_payload(scorer: Any, ai: dict, clock: Clock) -> dict:
    allowed = scorer.REQUIRED_RELATIONSHIP_FIELDS | scorer.OPTIONAL_RELATIONSHIP_FIELDS
    out = {k: v for k, v in ai.items() if k in allowed}
    if not out.get("ai_discovered"):
        out["ai_enhanced_at"] = clock()
    return out


_ARCH_ALLOWED = frozenset({
    "summary", "data_flow_narrative", "component_groups", "recent_changes_summary",
    "observations", "tech_diversity", "test_health_summary",
    "ai_enhanced_at", "ai_enhance_version",
})


def _clean_architecture_payload(ai: dict, clock: Clock) -> dict:
    out = {k: v for k, v in ai.items() if k in _ARCH_ALLOWED}
    out["ai_enhanced_at"] = clock()
    out["ai_enhance_version"] = 2
    return out


def _validate_architecture_payload(scorer: Any, ai: dict) -> list[str]:
    errors = []
    for field_name in ("summary", "data_flow_narrative"):
        if not ai.get(field_name):
            errors.append(f"Root ai_enhance: missing '{field_name}'")
    for idx, obs in enumerate(ai.get("observations", []) or []):
        errors.extend(scorer.validate_observation(obs, idx))
    return errors


# --- the engine --------------------------------------------------------------


def _select_update_targets(
    store: FactStore, arch: dict, index: DigestIndex
) -> tuple[set[str], bool]:
    """Return (component target set, regenerate-architecture flag) for --update.

    Targets are components whose enrichment is stale or missing, expanded to
    their architectural neighbours (undirected, all edge types). The architecture
    narrative is regenerated when its own digest row is stale or missing, or when
    any component target is in scope: a no-change update leaves it fresh and
    touches nothing (its provenance proves it, I5).
    """
    all_ids = {c["id"] for c in flatten_components(arch.get("components", []))}
    rows = enrichment_staleness(store, index)
    have_component_row = {
        r["target_id"] for r in rows if r["target_kind"] == "component"
    }
    stale_component = {
        r["target_id"]
        for r in rows
        if r["target_kind"] == "component" and r.get("stale") is True
    }
    missing = all_ids - have_component_row
    core = (stale_component | missing) & all_ids

    # Expand to architectural neighbours (any edge type, undirected).
    neighbours: set[str] = set()
    for rel in arch.get("relationships", []):
        s, t = rel.get("source", ""), rel.get("target", "")
        if s in core and t:
            neighbours.add(t)
        if t in core and s:
            neighbours.add(s)
    targets = (core | neighbours) & all_ids

    arch_row = next(
        (r for r in rows if r["target_kind"] == "architecture"), None
    )
    arch_stale = arch_row is None or arch_row.get("stale") is not False
    regenerate_arch = bool(targets) or arch_stale
    return targets, regenerate_arch


def _enhance_partition(
    partition: Partition,
    facts: StoreFacts,
    scorer: Any,
    invoker: Invoker,
    clock: Clock,
) -> tuple[PartitionOutcome, Optional[dict]]:
    """Invoke, validate, and (on success) return cleaned payloads for a partition.

    Returns (outcome, payloads) where payloads is None on failure. All-or-nothing:
    every component and relationship in the partition must validate, else the
    partition is retried once and, on a second failure, recorded failed with no
    payloads written (never junk).
    """
    prompt = build_partition_prompt(partition, facts)
    outcome = PartitionOutcome(
        id=partition.id,
        component_ids=list(partition.component_ids),
        relationship_keys=list(partition.relationship_keys),
        status="failed",
    )
    feedback = ""
    for attempt in range(1, 3):
        outcome.attempts = attempt
        result = invoker(prompt + feedback)
        outcome.cost_usd += result.cost_usd
        if not result.ok:
            outcome.errors = [result.error or "invocation failed"]
            feedback = f"\n\nPREVIOUS ATTEMPT FAILED: {result.error}. Return valid JSON."
            continue

        obj = _parse_json_object(result.text)
        if obj is None:
            outcome.errors = ["response was not a parseable JSON object"]
            feedback = "\n\nPREVIOUS ATTEMPT was not valid JSON. Return ONLY a JSON object."
            continue

        comp_payloads: dict[str, dict] = {}
        rel_payloads: dict[str, dict] = {}
        errors: list[str] = []
        comp_index = facts.component_index

        for cid in partition.component_ids:
            ai = (obj.get("components") or {}).get(cid)
            if not isinstance(ai, dict):
                errors.append(f"Component '{cid}': no ai_enhance in response")
                continue
            cleaned = _clean_component_payload(scorer, ai, clock)
            errs = scorer.validate_component_ai_enhance(
                cid, cleaned, comp_index.get(cid, {})
            )
            if errs:
                errors.extend(errs)
            else:
                comp_payloads[cid] = cleaned

        for key in partition.relationship_keys:
            ai = (obj.get("relationships") or {}).get(key)
            if not isinstance(ai, dict):
                errors.append(f"Relationship '{key}': no ai_enhance in response")
                continue
            cleaned = _clean_relationship_payload(scorer, ai, clock)
            parts = key.split("|")
            errs = scorer.validate_relationship_ai_enhance(tuple(parts), cleaned)
            if errs:
                errors.extend(errs)
            else:
                rel_payloads[key] = cleaned

        if errors:
            outcome.errors = errors
            feedback = (
                "\n\nPREVIOUS ATTEMPT had these schema errors, fix them:\n"
                + "\n".join(f"- {e}" for e in errors[:30])
            )
            continue

        outcome.status = "enriched"
        outcome.errors = []
        return outcome, {"components": comp_payloads, "relationships": rel_payloads}

    return outcome, None


def run_enhance(
    config: EnhanceConfig,
    *,
    invoker: Optional[Invoker] = None,
    clock: Clock = iso_now,
) -> EnhanceReport:
    """Run the enrichment pipeline for one store. Returns an EnhanceReport."""
    scorer = load_scorer()
    if invoker is None:
        # Wrap the DEFAULT invoker with R2 transport retry (transient-only,
        # full-jitter, bounded, per-invoke time budget). An explicitly injected
        # invoker is used as-is, so tests wrap their own for deterministic seams.
        from .retry import RetryingInvoker, RetryPolicy

        policy = config.retry_policy or RetryPolicy()
        invoker = RetryingInvoker(ClaudeCliInvoker(model=config.model), policy=policy)

    store = FactStore(str(config.store_path))
    try:
        # Derive to get the projected arch tree (rich fields) and keep the store's
        # derived tables current for the digest index. Derivation reads the store
        # only (no source), so this is cheap and idempotent.
        _, arch = derive_all(store, config.root.name, root_path=str(config.root))
        index = DigestIndex.from_store(store)
        facts = StoreFacts(
            arch,
            store.capabilities(),
            store.data_entities(),
            store.rules(),
            arch.get("relationships", []),
        )

        include_ids: Optional[set[str]] = None
        regenerate_arch = True
        mode = "full"
        report_notes: list[str] = []
        if config.update:
            mode = "update"
            include_ids, regenerate_arch = _select_update_targets(store, arch, index)
            report_notes.append(
                f"update scope: {len(include_ids)} component target(s) "
                f"(stale/missing + neighbours)"
            )
            if not include_ids and not regenerate_arch:
                report_notes.append(
                    "no stale or missing targets and architecture digest fresh; "
                    "nothing to enhance"
                )

        plan: PartitionPlan = plan_partitions(
            arch.get("components", []),
            arch.get("relationships", []),
            max_lines=config.max_lines,
            max_components=config.max_components,
            min_components=config.min_components,
            include_ids=include_ids,
        )
        partitions = list(plan.partitions)
        if config.max_partitions is not None:
            partitions = partitions[: config.max_partitions]

        report = EnhanceReport(
            mode=mode,
            dry_run=config.dry_run,
            partition_count=len(partitions),
        )
        report.notes = report_notes

        # Dry run: print the plan and prompt sizes, invoke nothing.
        if config.dry_run:
            for p in partitions:
                prompt = build_partition_prompt(p, facts)
                report.plan_preview.append({
                    "id": p.id,
                    "components": list(p.component_ids),
                    "relationships": list(p.relationship_keys),
                    "prompt_chars": len(prompt),
                    "prompt_tokens_est": len(prompt) // 4,
                })
            if regenerate_arch:
                aprompt = build_architecture_prompt(facts)
                report.plan_preview.append({
                    "id": "architecture",
                    "prompt_chars": len(aprompt),
                    "prompt_tokens_est": len(aprompt) // 4,
                })
            return report

        # Enhance partitions (bounded parallel) under a per-run COST CEILING (R2).
        # Partitions are submitted INCREMENTALLY, not all at once, so that once the
        # summed reported cost across all attempts (retries counted, since the
        # RetryingInvoker returns the accumulated cost) reaches config.max_cost_usd
        # we STOP launching new partitions, let the in-flight batch finish, and
        # record the rest honestly as skipped. All-or-nothing per partition is
        # preserved: a skipped partition is never half-stamped, and the run still
        # exits successfully with the partial state reported (skipped != failed).
        # The ceiling is soft: the in-flight batch at the moment it is reached runs
        # to completion, so total cost can exceed the ceiling by up to one batch;
        # new partitions are not launched.
        outcomes: list[PartitionOutcome] = []
        payloads_by_partition: dict[int, dict] = {}
        ceiling = config.max_cost_usd
        running_cost = 0.0
        ceiling_hit = False
        pending: list[Partition] = list(partitions)

        def _under_ceiling() -> bool:
            return ceiling is None or running_cost < ceiling

        if partitions:
            workers = max(1, min(config.max_parallel, len(partitions)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                in_flight: dict = {}
                while pending and len(in_flight) < workers and _under_ceiling():
                    part = pending.pop(0)
                    in_flight[
                        pool.submit(_enhance_partition, part, facts, scorer, invoker, clock)
                    ] = part
                while in_flight:
                    done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                    for fut in done:
                        part = in_flight.pop(fut)
                        try:
                            outcome, payloads = fut.result()
                        except Exception as exc:  # noqa: BLE001 - per-partition bulkhead (R1 wave 3)
                            # An UNEXPECTED exception inside _enhance_partition (a
                            # bug, not a handled invoke/validation failure, which
                            # already degrade in-band) previously re-raised through
                            # fut.result() and crashed the whole enrichment run.
                            # Isolate it per partition: record a deterministic
                            # failed outcome so one bad partition degrades and the
                            # rest of the run still enriches. Reason scrubbed via the
                            # honest-gap backbone (deterministic, no traceback).
                            reason = gap_from_exception("enrich.partition", "enrich", exc).reason
                            outcome = PartitionOutcome(
                                id=part.id,
                                component_ids=list(part.component_ids),
                                relationship_keys=list(part.relationship_keys),
                                status="failed",
                                errors=[f"partition raised an unexpected error: {reason}"],
                            )
                            payloads = None
                        outcomes.append(outcome)
                        if payloads is not None:
                            payloads_by_partition[outcome.id] = payloads
                        running_cost += outcome.cost_usd
                    # Top up only while under the ceiling; once reached, drain.
                    while pending and len(in_flight) < workers and _under_ceiling():
                        part = pending.pop(0)
                        in_flight[
                            pool.submit(_enhance_partition, part, facts, scorer, invoker, clock)
                        ] = part
            # Partitions never launched because the ceiling was reached: record
            # them honestly as skipped (never half-stamped, all-or-nothing).
            for part in pending:
                ceiling_hit = True
                outcomes.append(PartitionOutcome(
                    id=part.id,
                    component_ids=list(part.component_ids),
                    relationship_keys=list(part.relationship_keys),
                    status="skipped",
                    errors=[f"not enriched: cost ceiling reached (${ceiling:.2f} USD)"],
                ))
        if ceiling_hit:
            report.notes.append(
                f"cost ceiling reached (${ceiling:.2f} USD): "
                f"{sum(1 for o in outcomes if o.status == 'skipped')} partition(s) "
                f"not enriched; partial state reported honestly"
            )
        outcomes.sort(key=lambda o: o.id)
        report.partitions = outcomes
        report.total_cost_usd = sum(o.cost_usd for o in outcomes)

        # Architecture-level narrative (its own validation unit). It is a peer
        # producer to the partitions, so an UNEXPECTED exception here must degrade
        # the same way instead of crashing the run (adversarial review of PR #75,
        # finding 2): the narrative is left unenriched with a recorded note, and
        # the partitions that already succeeded still stamp. _enhance_architecture
        # already handles invoke/validation failures in-band (returns None); this
        # only adds the bulkhead for an unexpected raise. Retry/cost untouched.
        commit_sha = current_commit_sha(str(config.root))
        arch_payload: Optional[dict] = None
        if regenerate_arch and ceiling is not None and running_cost >= ceiling:
            # The ceiling was reached during the partitions; the architecture
            # narrative is a peer producer, so do not launch it either. Recorded
            # honestly, consistent with the skipped partitions.
            report.notes.append(
                f"architecture narrative not generated: cost ceiling reached "
                f"(${ceiling:.2f} USD)"
            )
        elif regenerate_arch:
            try:
                arch_payload, arch_cost, arch_errs = _enhance_architecture(
                    facts, scorer, invoker, clock
                )
                report.total_cost_usd += arch_cost
                if arch_payload is None:
                    report.notes.append(
                        "architecture narrative failed schema validation: "
                        + "; ".join(arch_errs[:5])
                    )
            except Exception as exc:  # noqa: BLE001 - arch-producer bulkhead (R1 wave 3)
                arch_payload = None
                reason = gap_from_exception("enrich.architecture", "enrich", exc).reason
                report.notes.append(
                    f"architecture narrative raised an unexpected error: {reason}"
                )

        # Stamp valid payloads (all-or-nothing per partition already enforced).
        for payloads in payloads_by_partition.values():
            for cid, ai in payloads["components"].items():
                stamp_enrichment(
                    store, "component", cid, ai,
                    digest_index=index, commit_sha=commit_sha, clock=clock,
                )
                report.components_enriched += 1
            for key, ai in payloads["relationships"].items():
                stamp_enrichment(
                    store, "relationship", key, ai,
                    digest_index=index, commit_sha=commit_sha, clock=clock,
                )
                report.relationships_enriched += 1
        if arch_payload is not None:
            stamp_enrichment(
                store, "architecture", ARCH_TARGET_ID, arch_payload,
                digest_index=index, commit_sha=commit_sha, clock=clock,
            )
            report.architecture_enriched = True
        store.commit()

        # Gate: project the store overlay onto the arch and run the quality
        # scorer. Skip only when nothing was enhanced at all (a no-op update).
        if report.components_enriched or report.architecture_enriched or store.enrichment():
            scorer_pass, summary = _run_scorer_gate(
                store, arch, index, config.threshold
            )
            report.scorer_pass = scorer_pass
            report.scorer_summary = summary

        if config.report_path is not None:
            config.report_path.parent.mkdir(parents=True, exist_ok=True)
            config.report_path.write_text(
                json.dumps(report.to_dict(), indent=2), encoding="utf-8"
            )
        return report
    finally:
        store.close()


def _enhance_architecture(
    facts: StoreFacts, scorer: Any, invoker: Invoker, clock: Clock
) -> tuple[Optional[dict], float, list[str]]:
    prompt = build_architecture_prompt(facts)
    cost = 0.0
    errors: list[str] = ["not attempted"]
    feedback = ""
    for _ in range(2):
        result = invoker(prompt + feedback)
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
        cleaned = _clean_architecture_payload(obj, clock)
        errs = _validate_architecture_payload(scorer, cleaned)
        if errs:
            errors = errs
            feedback = (
                "\n\nPREVIOUS ATTEMPT had these errors, fix them:\n"
                + "\n".join(f"- {e}" for e in errs)
            )
            continue
        return cleaned, cost, []
    return None, cost, errors


def _run_scorer_gate(
    store: FactStore, arch: dict, index: DigestIndex, threshold: float
) -> tuple[bool, str]:
    """Apply the store overlay to a copy of arch, write it, and run the scorer.

    Returns (passed, summary line). Runs the actual gate script as a subprocess
    (wire, do not rewrite) so the CI gate and the engine share one verdict.
    """
    overlaid = apply_enrichment_overlay(copy.deepcopy(arch), store, digest_index=index)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    ) as tf:
        json.dump(overlaid, tf, default=str)
        tmp_path = tf.name
    try:
        proc = subprocess.run(
            [
                sys.executable, str(scorer_path()),
                "--architecture", tmp_path,
                "--threshold", str(threshold),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    passed = proc.returncode == 0
    # The scorer prints a report; keep the informative lines for the run report.
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    summary = " | ".join(lines[1:6]) if len(lines) > 1 else proc.stdout.strip()[:400]
    return passed, summary
