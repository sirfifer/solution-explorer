"""Tier bindings: which source, and which model on that source, runs each rung.

The ladder is a structure, not a vendor. Its rungs are defined by the KIND of
work they do (bulk writing, escalated reasoning, a deep read of the residue), and
today they are bound to Claude models running through the `claude` CLI on the
owner's subscription. That binding is a configuration fact, not an architectural
one, and this module is where it lives so it never has to be true anywhere else.

**A binding is a source plus a model, and the model may be absent.** Absent is
not a missing value: it means "let the source route this call", which is a real
and interesting option rather than a degenerate one. A routing source picking its
own model per call is a legitimate experiment to run against the ladder, and the
ladder should be able to express it without any code change. The same option
exists on the provider we run on today, where an unpinned binding simply omits
the model flag and lets the CLI choose.

**Providers are registered, not hardcoded.** :func:`register_provider` maps a
source name to a builder that turns a :class:`ModelSpec` into an
:class:`~analyzer.enrich.engine.Invoker`. One provider ships today, the `claude`
CLI, because that is what the owner's account runs and no real invocation is
made against anything else. Adding a lab or an aggregator is a registration, not
a refactor: nothing above this module knows a vendor name.

**An unknown source fails at configuration time, not at invocation time.** A typo
in a source name that surfaced only when a rung tried to invoke would waste the
whole run up to that point and land in the Run Report as a phase failure rather
than as the configuration error it is.

Cost figures every provider reports are API-equivalent units, and on the source
that ships today they meter against the owner's Claude Max subscription rather
than a billed API key. See ``ENRICHMENT-ENGINE.md`` section 2.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from .engine import DEFAULT_EFFORT, KNOWN_EFFORTS, ClaudeCliInvoker, Invoker

__all__ = [
    "ModelSpec",
    "InvokerBuilder",
    "register_provider",
    "known_sources",
    "build_invoker",
    "DEFAULT_SOURCE",
    "ANTHROPIC_CLAUDE_CLI",
    "UNPINNED",
]

# The source that ships. Named for the transport, not just the lab, because the
# same lab reached through a different transport is a different binding with
# different auth, different cost reporting and different available models.
ANTHROPIC_CLAUDE_CLI = "anthropic-claude-cli"
DEFAULT_SOURCE = ANTHROPIC_CLAUDE_CLI

# The token that means "do not pin a model; let the source route this call".
UNPINNED = "auto"


# Reasoning effort is a property of the TIER, not of the machine the run
# happens to start on. The 2026-08-25 run inherited "xhigh" from the operator's
# interactive settings: 67.8% of every billed output token was thinking, the
# answer ran out of room inside the shared max_tokens budget, and 35% of
# completed partitions truncated mid-JSON. A tier therefore always carries an
# effort, and DEFAULT_EFFORT is what an unstated binding means. Measured across
# four real prompts replayed at each level: low produced 73% fewer output
# tokens, zero overflows, and equal or better coverage. Effort buys citation
# count and prose length, not answers.


@dataclass(frozen=True)
class ModelSpec:
    """One tier binding: a source, a pinned model, and the effort it runs at."""

    source: str = DEFAULT_SOURCE
    model: Optional[str] = None
    effort: str = DEFAULT_EFFORT

    @property
    def pinned(self) -> bool:
        return self.model is not None

    @property
    def label(self) -> str:
        """The stable string a ledger row and a Run Report record."""
        return f"{self.source}:{self.model or UNPINNED}"

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "model": self.model,
            "pinned": self.pinned,
            "effort": self.effort,
        }

    @classmethod
    def parse(cls, raw: Any, *, default_source: str = DEFAULT_SOURCE) -> ModelSpec:
        """Parse a binding from a string or an object, tolerantly but not silently.

        Accepted forms, in the order a human is likely to write them::

            "sonnet"                     the default source, pinned to sonnet
            "sonnet@low"                 the same, at an explicit effort
            "anthropic-claude-cli:opus"  an explicit source, pinned
            "openrouter:auto"            an explicit source, unpinned, it routes
            {"source": "...", "model": "..."}   the registry form
            {"source": "...", "model": null}    the registry form, unpinned
            {"source": "...", "model": "...", "effort": "low"}

        A bare model name keeps working because that is what every existing
        caller, flag and registry entry writes today, and changing their meaning
        would silently repoint work at a different source. An unstated effort
        reads as :data:`DEFAULT_EFFORT` rather than as "whatever the machine is
        set to", which is the whole point: see the module comment above.
        """
        if isinstance(raw, ModelSpec):
            return raw
        if isinstance(raw, dict):
            source = str(raw.get("source") or default_source).strip() or default_source
            effort = cls._parse_effort(raw.get("effort"))
            model = raw.get("model")
            if model is None or str(model).strip().lower() in ("", UNPINNED, "null", "none"):
                return cls(source=source, model=None, effort=effort)
            model, at_effort = cls._split_effort(str(model).strip())
            return cls(source=source, model=model, effort=at_effort or effort)
        text = str(raw or "").strip()
        if not text:
            return cls(source=default_source, model=None)
        text, at_effort = cls._split_effort(text)
        effort = at_effort or DEFAULT_EFFORT
        if ":" in text:
            source, _, model = text.partition(":")
            source = source.strip() or default_source
            model = model.strip()
            if not model or model.lower() == UNPINNED:
                return cls(source=source, model=None, effort=effort)
            return cls(source=source, model=model, effort=effort)
        return cls(source=default_source, model=text, effort=effort)

    @staticmethod
    def _split_effort(text: str) -> tuple[str, Optional[str]]:
        """Split a trailing ``@effort`` suffix off a binding string."""
        if "@" not in text:
            return text, None
        head, _, tail = text.rpartition("@")
        effort = tail.strip().lower()
        if not head.strip() or effort not in KNOWN_EFFORTS:
            return text, None
        return head.strip(), effort

    @staticmethod
    def _parse_effort(raw: Any) -> str:
        """An unrecognised effort is refused, never silently downgraded."""
        if raw is None:
            return DEFAULT_EFFORT
        text = str(raw).strip().lower()
        if not text:
            return DEFAULT_EFFORT
        if text not in KNOWN_EFFORTS:
            raise ValueError(
                f"unknown effort {raw!r}; expected one of " + ", ".join(KNOWN_EFFORTS)
            )
        return text


# An invoker builder turns a binding into something the ladder can call.
InvokerBuilder = Callable[["ModelSpec"], Invoker]

_PROVIDERS: dict[str, InvokerBuilder] = {}


def register_provider(source: str, builder: InvokerBuilder) -> None:
    """Register the invoker builder for a source name."""
    _PROVIDERS[source] = builder


def known_sources() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))


def build_invoker(
    spec: Any, *, retry_policy: Any = None, timeout_s: Optional[int] = None
) -> Invoker:
    """Build the invoker for a binding, wrapped in transport retry.

    Retry is applied here rather than inside each provider so every source gets
    the same transient-only, bounded, full-jitter behaviour and the same accrued
    cost accounting, which is what makes ledger rows comparable across sources.

    ``timeout_s`` overrides the provider invoker's per-attempt subprocess
    timeout where the invoker exposes one (duck-typed on a ``timeout``
    attribute, which the CLI invoker does). Providers whose transport has no
    such knob simply ignore it, which is the correct degradation: the retry
    policy still bounds the logical invoke.
    """
    resolved = ModelSpec.parse(spec)
    builder = _PROVIDERS.get(resolved.source)
    if builder is None:
        raise ValueError(
            f"unknown model source {resolved.source!r}; registered sources are "
            + (", ".join(known_sources()) or "(none)")
        )
    from .retry import RetryingInvoker, RetryPolicy

    inner = builder(resolved)
    if timeout_s is not None and hasattr(inner, "timeout"):
        inner.timeout = int(timeout_s)
    return RetryingInvoker(inner, policy=retry_policy or RetryPolicy())


def _claude_cli_builder(spec: ModelSpec) -> Invoker:
    """The source that ships: the `claude` CLI on the owner's subscription.

    An unpinned binding omits the model flag, so the CLI routes the call the way
    a routing aggregator would. Cost comes back as the API-equivalent figure the
    CLI reports. Effort is always passed explicitly, so the call never inherits
    the reasoning budget of whatever machine launched it.
    """
    return ClaudeCliInvoker(model=spec.model, effort=spec.effort)


register_provider(ANTHROPIC_CLAUDE_CLI, _claude_cli_builder)
