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
import os
import re
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Sequence
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
from .subject_identity import (
    SUBJECT_IDENTITY_CONTRACT_VERSION,
    build_subject_identity,
    subject_identity_errors,
)

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
    "DEFAULT_EFFORT",
    "KNOWN_EFFORTS",
    "DEFAULT_MAX_PARALLEL",
    "DEFAULT_MAX_COST_USD",
    "CACHE_POLICIES",
]

DEFAULT_MODEL = "sonnet"
DEFAULT_MAX_PARALLEL = 4

# Reasoning effort lives here, beside the model, because both are properties of
# how a call is made rather than of what it asks. See ClaudeCliInvoker for why
# the flag is never omitted. models.ModelSpec re-exports these as the tier-level
# binding; the import runs that way round because models imports the invoker.
DEFAULT_EFFORT = "low"
KNOWN_EFFORTS = ("low", "medium", "high", "xhigh")


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
    # The transport's own identifier for this call. Recorded so a ledger row can
    # be joined to its transcript later without guessing from timestamps: the
    # 2026-08-25 forensics had to match sessions on token triples because no row
    # carried one, and a phrase-based match collided with the operator's own
    # interactive session.
    session_id: Optional[str] = None
    # Which model the rung BOUND. Not the same thing as what answered.
    model: Optional[str] = None
    # What actually answered, from the CLI's own `modelUsage` map: canonical
    # model name -> tokens and cost. Load bearing, because the bound model is not
    # the whole story. A call pinned to sonnet was measured billing
    # claude-haiku-4-5 alongside claude-sonnet-5, so attributing a whole
    # invocation to its binding puts tokens in the wrong weekly bucket, and on a
    # Max plan the Sonnet and Opus buckets are separate. This is ground truth
    # from the process that did the metering; the binding is only our intent.
    model_usage: dict = field(default_factory=dict)
    # Historical transport marker. New compact calls validate in-process so a
    # CLI-side schema rejection cannot destroy paid output; old run artifacts
    # retain this bit so their two-turn StructuredOutput handoff is auditable.
    structured_output_enforced: bool = False
    # Characters of the cacheable prefix this call actually sent as an appended
    # system prompt; 0 when the prompt carried no marker and the legacy argv
    # ran. The ledger turns it into a token estimate so the cache audit can
    # require a warm call to read back at least its own prefix. Counting
    # zero-read calls alone passes a call that read some small unrelated entry.
    prefix_chars: int = 0


# An invoker takes a prompt and returns an InvokeResult. Injectable so tests can
# mock the model without shelling out.
Invoker = Callable[[str], InvokeResult]


def _recover_transcript_usage(session_id: str) -> tuple[dict, dict]:
    """Best-effort usage recovery when the CLI exits without an envelope.

    Claude's transcript repeats one assistant message as its content evolves
    (thinking, then tool handoff), so message ids are deduplicated before token
    counts are summed. Raw transcript content never leaves the provider-owned
    directory and is never copied into a run artifact.
    """
    usage = {
        "input_tokens": 0, "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0, "output_tokens": 0,
        "cache_creation": {
            "ephemeral_1h_input_tokens": 0,
            "ephemeral_5m_input_tokens": 0,
        },
    }
    by_model: dict[str, dict] = {}
    try:
        matches = list(
            (Path.home() / ".claude" / "projects").glob(f"*/{session_id}.jsonl")
        )
        if not matches:
            return {}, {}
        seen: set[str] = set()
        turns = 0
        stop_reason = None
        for line in matches[0].read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = record.get("message") or {}
            if record.get("type") != "assistant" or not isinstance(message, dict):
                continue
            message_id = str(message.get("id") or record.get("uuid") or "")
            if not message_id or message_id in seen:
                continue
            seen.add(message_id)
            turns += 1
            block = message.get("usage") or {}
            model = str(message.get("model") or "unknown")
            model_block = by_model.setdefault(model, {
                "inputTokens": 0, "cacheCreationInputTokens": 0,
                "cacheReadInputTokens": 0, "outputTokens": 0,
            })
            for source, aggregate, model_key in (
                ("input_tokens", "input_tokens", "inputTokens"),
                ("cache_creation_input_tokens", "cache_creation_input_tokens", "cacheCreationInputTokens"),
                ("cache_read_input_tokens", "cache_read_input_tokens", "cacheReadInputTokens"),
                ("output_tokens", "output_tokens", "outputTokens"),
            ):
                value = int(block.get(source) or 0)
                usage[aggregate] += value
                model_block[model_key] += value
            creation = block.get("cache_creation") or {}
            if isinstance(creation, dict):
                for ttl_key in (
                    "ephemeral_1h_input_tokens",
                    "ephemeral_5m_input_tokens",
                ):
                    try:
                        usage["cache_creation"][ttl_key] += int(
                            creation.get(ttl_key) or 0
                        )
                    except (TypeError, ValueError):
                        pass
            stop_reason = message.get("stop_reason") or stop_reason
        if not seen:
            return {}, {}
        usage["num_turns"] = turns
        usage["stop_reason"] = stop_reason
        return usage, by_model
    except (OSError, TypeError, ValueError):
        return {}, {}


class ClaudeCliInvoker:
    """Invoke Claude headlessly via the `claude` CLI (the installed mechanism).

    Runs ``claude -p --output-format json [--model <model>]`` with the prompt on
    stdin (stdin avoids ARG_MAX limits on large partition prompts), then parses
    the JSON envelope's ``result`` (model text), ``total_cost_usd``, and
    ``usage``. The Python Agent SDK is not installed in this environment; the CLI
    is the simplest available headless path and reports cost per call.

    Compact JSON is deliberately not forced with the CLI's ``--json-schema``:
    the ladder validates the same bounded schema after delivery and can repair
    or salvage a malformed item without discarding the whole response.

    ``model`` is optional. A model name pins the call to that model, which is
    what every caller does today. ``model=None`` OMITS the flag entirely and lets
    the CLI route the call itself, which is the unpinned half of a tier binding
    (see :mod:`analyzer.enrich.models`). Both forms are exercised by tests that
    assert the exact argv, because argv construction is where a routing change
    would otherwise be invisible.
    """

    def __init__(
        self,
        model: Optional[str] = DEFAULT_MODEL,
        *,
        claude_bin: str = "claude",
        timeout: int = 600,
        effort: str = DEFAULT_EFFORT,
        max_budget_usd: Optional[float] = None,
        cache_policy: str = "provider-default",
    ):
        self.model = model
        self.claude_bin = claude_bin
        self.timeout = timeout
        self.effort = effort
        self.max_budget_usd = max_budget_usd
        self.set_cache_policy(cache_policy)

    def set_cache_policy(self, value: str) -> None:
        """Select a deterministic Claude Code prompt-cache policy.

        The policy is applied to the child environment for every attempt.  It
        never mutates ``os.environ`` and therefore cannot leak from a probe into
        the operator's shell or a concurrent session.
        """
        policy = str(value or "provider-default").strip().lower()
        if policy not in CACHE_POLICIES:
            raise ValueError(
                f"unknown cache policy {value!r}; expected one of "
                + ", ".join(sorted(CACHE_POLICIES))
            )
        self.cache_policy = policy

    def _child_env(self) -> dict[str, str]:
        env = dict(os.environ)
        for key in _CACHE_ENV_KEYS:
            env.pop(key, None)
        if self.cache_policy == "5m":
            env["FORCE_PROMPT_CACHING_5M"] = "1"
        elif self.cache_policy == "1h":
            env["ENABLE_PROMPT_CACHING_1H"] = "1"
        elif self.cache_policy == "off":
            env["DISABLE_PROMPT_CACHING"] = "1"
        return env

    def set_max_budget_usd(self, value: Optional[float]) -> None:
        """Set the CLI's best-effort allowance for the next invocation.

        The shared run meter assigns this immediately before launch.  Keeping
        it mutable avoids rebuilding the provider stack for every call while
        still letting each call see the run's exact remaining reservation. The
        CLI may exceed this value for a single response, so callers must treat
        it as a launch allowance and validate measured cost afterwards.
        """
        self.max_budget_usd = value

    def __call__(self, prompt: str) -> InvokeResult:
        structured_output_enforced = False
        prefix_chars = 0
        # Allocate the id before spawning. A CLI-side validation or transport
        # failure can exit without an envelope, which used to leave the ledger
        # with no way to locate the provider transcript.
        session_id = str(uuid.uuid4())
        try:
            # A None model omits the flag entirely, which lets the CLI route the
            # call itself instead of being pinned to one model. That is the
            # "unpinned" half of a tier binding (see enrich/models.py): the same
            # option a routing provider offers, expressed on the provider we
            # actually run on today.
            # Pure single-turn inference, pinned explicitly. Without these
            # flags the CLI runs its full agentic loop from whatever cwd the
            # caller happens to have: on the 2026-08-22 smoke run the model
            # toured the repository with tools across multiple turns instead
            # of answering, multiplying a 13k-token prompt into 193k input
            # tokens and returning prose instead of the JSON object.
            # --tools "" disables every tool; --setting-sources user keeps
            # the project's .claude settings out of a call that must not
            # depend on which directory launched it.
            #
            # --effort is passed ALWAYS and explicitly. --setting-sources user
            # was keeping project settings out while still letting the user's
            # own settings.json decide the reasoning budget: on 2026-08-25 that
            # meant every call in a 173-partition run inherited "xhigh" from an
            # interactive session, spent two thirds of each response on
            # thinking, and truncated the answer at the shared output ceiling.
            # An unstated effort is a decision nobody made, so there is no code
            # path here that omits the flag.
            argv = [
                self.claude_bin, "-p", "--output-format", "json",
                "--tools", "", "--setting-sources", "user",
                "--effort", self.effort,
                "--session-id", session_id,
            ]
            if self.model:
                argv += ["--model", self.model]
            if self.max_budget_usd is not None:
                argv += ["--max-budget-usd", f"{max(0.01, self.max_budget_usd):.6f}"]
            # Compact ladder prompts mark a byte-stable instruction prefix.
            # Put that prefix in the CLI's appended system prompt and send only
            # facts on stdin.  Repeated calls can now read the same provider
            # cache entry instead of writing every unique full prompt at the 1h
            # creation rate.  Unmarked callers retain the exact legacy argv.
            from .prompts import split_cached_prompt

            prefix, user_prompt = split_cached_prompt(prompt)
            child_env = self._child_env()
            if prefix is None:
                proc = subprocess.run(
                    argv, input=user_prompt, capture_output=True, text=True,
                    timeout=self.timeout, env=child_env,
                )
            else:
                prefix_chars = len(prefix)
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", suffix=".prompt", delete=True
                ) as prefix_file:
                    prefix_file.write(prefix)
                    prefix_file.flush()
                    proc = subprocess.run(
                        [
                            *argv,
                            # Verified by the F-9 live probe: without this flag
                            # cwd/git/environment text changes ahead of the
                            # appended prefix, so every otherwise identical call
                            # writes a new cache entry.  Relocating those dynamic
                            # sections makes the base+prefix byte-stable; later
                            # calls then read the full entry at cache-read rates.
                            "--exclude-dynamic-system-prompt-sections",
                            "--append-system-prompt-file", prefix_file.name,
                            "--max-turns", "1",
                        ],
                        input=user_prompt, capture_output=True, text=True,
                        timeout=self.timeout, env=child_env,
                    )
        except (OSError, subprocess.SubprocessError) as exc:
            # Spawn failure or subprocess timeout: a bounded transient (R2).
            return InvokeResult(
                ok=False, text="", error=f"invocation failed: {exc}",
                session_id=session_id,
            )
        if proc.returncode != 0:
            # A nonzero exit can still carry a structured JSON error envelope on
            # stdout: a real claude CLI run returns exit 1 for an API error WITH
            # is_error/api_error_status in the envelope (for example a 429 rate
            # limit or a 404 model-not-found). Surface that status so the R2
            # retry layer can tell a transient (429/5xx) from a deterministic
            # (4xx) failure; fall back to stderr only when there is no envelope.
            status, detail = _envelope_error(proc.stdout)
            recovered_usage, recovered_models = _recover_transcript_usage(session_id)
            try:
                error_envelope = json.loads(proc.stdout)
                if not isinstance(error_envelope, dict):
                    error_envelope = {}
            except (json.JSONDecodeError, TypeError):
                error_envelope = {}
            envelope_usage = error_envelope.get("usage") or recovered_usage
            envelope_models = error_envelope.get("modelUsage") or recovered_models
            envelope_cost = float(error_envelope.get("total_cost_usd", 0.0) or 0.0)
            if status is not None or detail is not None:
                return InvokeResult(
                    ok=False,
                    text=proc.stdout or proc.stderr or detail or "",
                    cost_usd=envelope_cost,
                    error=f"claude exited {proc.returncode}: {(detail or proc.stderr).strip()[:400]}",
                    status_code=status,
                    session_id=session_id,
                    usage=envelope_usage,
                    model_usage=envelope_models,
                    model=self.model,
                )
            return InvokeResult(
                ok=False, text=proc.stdout or proc.stderr or "",
                cost_usd=envelope_cost,
                error=f"claude exited {proc.returncode}: {proc.stderr.strip()[:400]}",
                session_id=session_id,
                usage=envelope_usage,
                model_usage=envelope_models,
                model=self.model,
            )
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            # Well-formed run (exit 0) that returned non-JSON: a deterministic
            # parse failure. NEVER retried at the transport layer (R2).
            return InvokeResult(
                ok=False, text=proc.stdout,
                error=f"unparseable envelope: {exc}", session_id=session_id,
            )
        if envelope.get("is_error"):
            return InvokeResult(
                ok=False, text=str(envelope.get("result", "")),
                cost_usd=float(envelope.get("total_cost_usd", 0.0) or 0.0),
                usage=dict(
                    envelope.get("usage", {}) or {},
                    num_turns=envelope.get("num_turns", 1),
                ),
                error="model reported error",
                status_code=_coerce_status(envelope.get("api_error_status")),
                model=self.model,
                model_usage=envelope.get("modelUsage", {}) or {},
                session_id=envelope.get("session_id") or session_id,
            )
        # The success path carries the envelope's own account of HOW the answer
        # was produced, not just the answer. num_turns feeds the agentic-drift
        # alarm in MeteredInvoker, which was built, wired and then starved: it
        # never fired across twelve multi-turn calls in the 2026-08-25 run
        # because this branch returned the bare usage block while only the
        # is_error branch folded the field in. stop_reason is how a truncated
        # response announces itself; discarding it is what let 35% of that run's
        # partitions overflow the output ceiling silently, get auto-continued,
        # and bill the re-ingested text at the 2x cache-creation rate.
        return InvokeResult(
            ok=True,
            text=str(envelope.get("result", "")),
            cost_usd=float(envelope.get("total_cost_usd", 0.0) or 0.0),
            usage=dict(
                envelope.get("usage", {}) or {},
                num_turns=envelope.get("num_turns", 1),
                stop_reason=envelope.get("stop_reason"),
            ),
            model=self.model,
            model_usage=envelope.get("modelUsage", {}) or {},
            session_id=envelope.get("session_id") or session_id,
            structured_output_enforced=structured_output_enforced,
            prefix_chars=prefix_chars,
        )


def _accumulate_usage(into: dict, result: InvokeResult) -> None:
    """Fold one call's token usage into a per-model tally.

    Kept separate from cost because they answer different questions. The CLI's
    dollar figure is an API-EQUIVALENT price for work that was actually metered
    against a Claude subscription, so it is useful for comparing runs and
    useless for answering "how much of this week did that just spend". Tokens
    per model are the measurement that survives a pricing change and can be
    weighed against a subscription allowance.

    Field names follow the CLI envelope, which reports cache reads and writes
    separately; they are kept apart because a cache read is roughly a tenth of
    the price of the same tokens read fresh, and folding them together would
    overstate a cache-heavy run by an order of magnitude.
    """
    # The CLI's modelUsage map is the truth when present: it names every model
    # that actually billed on this call, which a single binding cannot.
    if result.model_usage:
        for name, measured in result.model_usage.items():
            canonical = measured.get("canonicalModel") or name
            bucket = into.setdefault(canonical, {
                "calls": 0, "input_tokens": 0, "output_tokens": 0,
                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
                "cost_usd": 0.0,
            })
            bucket["calls"] += 1
            bucket["cost_usd"] += float(measured.get("costUSD", 0.0) or 0.0)
            bucket["input_tokens"] += int(measured.get("inputTokens", 0) or 0)
            bucket["output_tokens"] += int(measured.get("outputTokens", 0) or 0)
            bucket["cache_read_input_tokens"] += int(measured.get("cacheReadInputTokens", 0) or 0)
            bucket["cache_creation_input_tokens"] += int(
                measured.get("cacheCreationInputTokens", 0) or 0
            )
        return

    model = result.model or "unknown"
    usage = result.usage or {}
    bucket = into.setdefault(model, {
        "calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cost_usd": 0.0,
    })
    bucket["calls"] += 1
    bucket["cost_usd"] += float(result.cost_usd or 0.0)
    for field_name in (
        "input_tokens", "output_tokens",
        "cache_read_input_tokens", "cache_creation_input_tokens",
    ):
        value = usage.get(field_name)
        if isinstance(value, (int, float)):
            bucket[field_name] += int(value)


def _merge_usage(into: dict, other: dict) -> None:
    """Fold one per-model tally into another, for run-level totals."""
    for model, bucket in (other or {}).items():
        target = into.setdefault(model, {
            "calls": 0, "input_tokens": 0, "output_tokens": 0,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
            "cost_usd": 0.0,
        })
        for key, value in bucket.items():
            target[key] = target.get(key, 0) + value


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

# Prompt-cache policy is an invocation property, not a machine setting.  The
# enrichment runner creates hundreds of independent CLI processes; inheriting a
# user's cache environment would make two nominally identical runs bill
# differently.  ``provider-default`` deliberately clears every known override
# and lets Claude Code choose from the authentication mode.  The ladder's
# higher-level ``adaptive`` policy resolves to one of these concrete values
# before an invoker is built.
CACHE_POLICIES = frozenset({"provider-default", "1h", "5m", "off"})
_CACHE_ENV_KEYS = (
    "FORCE_PROMPT_CACHING_5M",
    "ENABLE_PROMPT_CACHING_1H",
    "CLAUDE_CODE_PROMPT_CACHE_TTL",
    "DISABLE_PROMPT_CACHING",
    "DISABLE_PROMPT_CACHING_HAIKU",
    "DISABLE_PROMPT_CACHING_SONNET",
    "DISABLE_PROMPT_CACHING_OPUS",
    "DISABLE_PROMPT_CACHING_FABLE",
)


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
    # Classic enhancement consists of independent one-shot partitions.  Under
    # ``adaptive`` those calls run uncached; explicit values exist for the same
    # controlled A/B probes as the ladder CLI.
    cache_policy: str = "adaptive"


@dataclass
class PartitionOutcome:
    id: int
    component_ids: list[str]
    relationship_keys: list[str]
    status: str  # "enriched" | "failed" | "skipped"
    attempts: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)
    # model -> {"input_tokens": n, "output_tokens": n, "calls": n, ...}. The
    # dollar figure the CLI reports is an API-equivalent price, and this account
    # is metered against a Claude subscription rather than an API bill, so the
    # tokens are the durable measurement and the dollars are a derived one.
    usage_by_model: dict = field(default_factory=dict)


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
    # The run's whole token account, by model. This is what a usage budget is
    # actually spent in; see scripts/usage-budget.py.
    usage_by_model: dict = field(default_factory=dict)
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
            "usage_by_model": self.usage_by_model,
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
                    "usage_by_model": p.usage_by_model,
                    "errors": p.errors,
                }
                for p in self.partitions
            ],
            "plan_preview": self.plan_preview,
        }


# --- response parsing, cleaning, validation ----------------------------------


_FENCE_RE = re.compile(r"^[ \t]*```[A-Za-z0-9_+-]*[ \t]*\r?\n?", re.MULTILINE)


def _strip_fences(text: str) -> str:
    """Remove markdown fences ANYWHERE, taking each fence's own newline with it.

    A fence is not always at the edges. When a response overflows the output
    ceiling the transport continues it, and the continuation frequently reopens
    a ```json fence in the middle of the object it was halfway through writing.
    Stripping only a leading and trailing fence leaves those in place and the
    parse fails on text that is otherwise complete.

    Taking the trailing newline with the fence matters and is not cosmetic: a
    line-based strip that leaves the blank line behind recovers 7 of the 10
    discarded partitions from the 2026-08-25 run, while this recovers 10.
    """
    return _FENCE_RE.sub("", text)


def _brace_span(text: str) -> Optional[str]:
    """The outermost ``{...}`` span, ignoring leading and trailing chatter."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _repair_truncated(text: str) -> Optional[dict]:
    """Salvage the complete entries out of an object that stops mid-write.

    A response cut off at the output ceiling is not worthless: it is a valid
    object followed by a partial one. Walking back to the last balanced point
    and closing the structure there keeps the blocks that finished. On the
    2026-08-25 run the alternative was throwing away whole partitions, which is
    how $18.82 of $40.43 was paid for and then discarded.

    Deliberately conservative: it only ever CLOSES open structures, never
    invents a value, so a salvaged object contains nothing the model did not
    actually write.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    # The last index at which the object can be closed WITHOUT keeping a
    # half-written entry. Only a closer that returns to depth 2 or shallower
    # qualifies, which for the response shape {"components": {...}} means the
    # cut lands where a whole component block just ended. Allowing deeper cut
    # points salvages a block that has a description but never got its
    # contract, and a half-block absorbed as if whole is worse than a dropped
    # one: it records an answer nobody gave.
    safe_end: Optional[int] = None
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth <= 0:
                break
            if depth <= 2:
                safe_end = i
        elif ch == "," and 0 < depth <= 2:
            safe_end = i - 1
    if safe_end is None:
        return None
    candidate = text[start : safe_end + 1]
    # Close whatever is still open, innermost first. Which closer to use is
    # decided by the actual unclosed openers, not guessed.
    openers: list[str] = []
    in_string = False
    escaped = False
    for ch in candidate:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            openers.append(ch)
        elif ch in "}]":
            if openers:
                openers.pop()
    if in_string:
        return None
    closed = candidate + "".join("}" if c == "{" else "]" for c in reversed(openers))
    try:
        obj = json.loads(closed, strict=False)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _parse_json_object(
    text: str, *, expect_keys: Sequence[str] = ()
) -> Optional[dict]:
    """Parse a JSON object from model text, tolerating fences and truncation.

    Three escalating attempts, each strictly more forgiving than the last and
    none of them inventing content: parse it, parse its brace span with fences
    removed, then salvage the complete entries out of a truncated object.

    ``expect_keys`` is a shape guard, and salvage without one is dangerous. A
    response that begins mid-object, which is exactly what the transport
    returns when it hands back only the final turn of a continued overflow,
    has its first ``{`` somewhere deep inside a nested value. Repairing from
    there yields a perfectly valid object that happens to be a single evidence
    item, and absorbing it would record a partition as answered while storing
    nothing. When ``expect_keys`` is given, a salvaged object must carry at
    least one of them or it is treated as the failure it is.
    """
    s = _strip_fences(text).strip()
    span = s if s.startswith("{") else _brace_span(s)
    if span is None:
        return None
    try:
        # strict=False permits literal control characters INSIDE string values,
        # which is not laxness about structure: a model writing multi-line prose
        # emits a real newline inside a help_text rather than the \n escape,
        # and strict JSON then rejects an otherwise perfect 114KB response over
        # one character. That cost a whole partition (22 components and 40
        # relationships) on the 2026-08-26 full build before it was found.
        # Structure is still parsed strictly; only the character class inside
        # strings is relaxed.
        obj = json.loads(span, strict=False)
    except json.JSONDecodeError:
        # Models occasionally emit otherwise-complete JSON with a comma after
        # the final array/object member. The live UnaMentis P5 response did
        # exactly this after spending 4,471 output tokens; treating it as an
        # unparseable determination skipped both quality-improvement rounds.
        # Delete only commas that are structurally followed by a closer while
        # outside a string. This invents no value and cannot alter prose.
        repaired = _remove_trailing_commas(span)
        try:
            obj = json.loads(repaired, strict=False)
        except json.JSONDecodeError:
            obj = _repair_truncated(repaired)
    if not isinstance(obj, dict):
        return None
    if expect_keys and not any(key in obj for key in expect_keys):
        return None
    return obj


def _remove_trailing_commas(text: str) -> str:
    """Remove JSON trailing commas outside strings, and nothing else."""
    out: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            index += 1
            continue
        if char == ",":
            following = index + 1
            while following < len(text) and text[following].isspace():
                following += 1
            previous = index - 1
            while previous >= 0 and text[previous].isspace():
                previous -= 1
            if (
                previous >= 0
                and text[previous] not in "{[:,"
                and following < len(text)
                and text[following] in "]}"
            ):
                index += 1
                continue
        out.append(char)
        index += 1
    return "".join(out)


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
    "ai_enhanced_at", "ai_enhance_version", "subject_identity_contract_version",
})


def _clean_architecture_payload(ai: dict, clock: Clock) -> dict:
    out = {k: v for k, v in ai.items() if k in _ARCH_ALLOWED}
    out["ai_enhanced_at"] = clock()
    out["ai_enhance_version"] = 2
    out["subject_identity_contract_version"] = SUBJECT_IDENTITY_CONTRACT_VERSION
    return out


def _validate_architecture_payload(
    scorer: Any, ai: dict, *, subject_identity: Optional[dict] = None
) -> list[str]:
    errors = []
    for field_name in ("summary", "data_flow_narrative"):
        if not ai.get(field_name):
            errors.append(f"Root ai_enhance: missing '{field_name}'")
    for idx, obs in enumerate(ai.get("observations", []) or []):
        errors.extend(scorer.validate_observation(obs, idx))
    if subject_identity is not None:
        errors.extend(subject_identity_errors(ai, subject_identity))
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
    if arch_row is not None:
        payload = arch_row.get("payload") or {}
        identity = build_subject_identity(arch)
        if (
            payload.get("subject_identity_contract_version")
            != SUBJECT_IDENTITY_CONTRACT_VERSION
            or subject_identity_errors(payload, identity)
        ):
            arch_stale = True
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
        _accumulate_usage(outcome.usage_by_model, result)
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
        concrete_cache_policy = (
            "off" if config.cache_policy == "adaptive" else config.cache_policy
        )
        invoker = RetryingInvoker(
            ClaudeCliInvoker(
                model=config.model, cache_policy=concrete_cache_policy
            ),
            policy=policy,
        )

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
            root=config.root,
        )
        commit_sha = current_commit_sha(str(config.root))
        subject_identity = build_subject_identity(
            arch, root=config.root, commit_sha=commit_sha
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
                aprompt = build_architecture_prompt(
                    facts, subject_identity=subject_identity
                )
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
        for outcome in outcomes:
            _merge_usage(report.usage_by_model, outcome.usage_by_model)

        # Architecture-level narrative (its own validation unit). It is a peer
        # producer to the partitions, so an UNEXPECTED exception here must degrade
        # the same way instead of crashing the run (adversarial review of PR #75,
        # finding 2): the narrative is left unenriched with a recorded note, and
        # the partitions that already succeeded still stamp. _enhance_architecture
        # already handles invoke/validation failures in-band (returns None); this
        # only adds the bulkhead for an unexpected raise. Retry/cost untouched.
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
                    facts, scorer, invoker, clock,
                    subject_identity=subject_identity,
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
    facts: StoreFacts,
    scorer: Any,
    invoker: Invoker,
    clock: Clock,
    *,
    subject_identity: Optional[dict] = None,
) -> tuple[Optional[dict], float, list[str]]:
    identity = subject_identity or build_subject_identity(facts.arch)
    prompt = build_architecture_prompt(facts, subject_identity=identity)
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
        errs = _validate_architecture_payload(
            scorer, cleaned, subject_identity=identity
        )
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
