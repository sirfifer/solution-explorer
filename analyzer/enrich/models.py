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

from .engine import ClaudeCliInvoker, Invoker

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


@dataclass(frozen=True)
class ModelSpec:
    """One tier binding: a source, and optionally a pinned model on that source."""

    source: str = DEFAULT_SOURCE
    model: Optional[str] = None

    @property
    def pinned(self) -> bool:
        return self.model is not None

    @property
    def label(self) -> str:
        """The stable string a ledger row and a Run Report record."""
        return f"{self.source}:{self.model or UNPINNED}"

    def to_dict(self) -> dict:
        return {"source": self.source, "model": self.model, "pinned": self.pinned}

    @classmethod
    def parse(cls, raw: Any, *, default_source: str = DEFAULT_SOURCE) -> ModelSpec:
        """Parse a binding from a string or an object, tolerantly but not silently.

        Accepted forms, in the order a human is likely to write them::

            "sonnet"                     the default source, pinned to sonnet
            "anthropic-claude-cli:opus"  an explicit source, pinned
            "openrouter:auto"            an explicit source, unpinned, it routes
            {"source": "...", "model": "..."}   the registry form
            {"source": "...", "model": null}    the registry form, unpinned

        A bare model name keeps working because that is what every existing
        caller, flag and registry entry writes today, and changing their meaning
        would silently repoint work at a different source.
        """
        if isinstance(raw, ModelSpec):
            return raw
        if isinstance(raw, dict):
            source = str(raw.get("source") or default_source).strip() or default_source
            model = raw.get("model")
            if model is None or str(model).strip().lower() in ("", UNPINNED, "null", "none"):
                return cls(source=source, model=None)
            return cls(source=source, model=str(model).strip())
        text = str(raw or "").strip()
        if not text:
            return cls(source=default_source, model=None)
        if ":" in text:
            source, _, model = text.partition(":")
            source = source.strip() or default_source
            model = model.strip()
            if not model or model.lower() == UNPINNED:
                return cls(source=source, model=None)
            return cls(source=source, model=model)
        return cls(source=default_source, model=text)


# An invoker builder turns a binding into something the ladder can call.
InvokerBuilder = Callable[["ModelSpec"], Invoker]

_PROVIDERS: dict[str, InvokerBuilder] = {}


def register_provider(source: str, builder: InvokerBuilder) -> None:
    """Register the invoker builder for a source name."""
    _PROVIDERS[source] = builder


def known_sources() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))


def build_invoker(spec: Any, *, retry_policy: Any = None) -> Invoker:
    """Build the invoker for a binding, wrapped in transport retry.

    Retry is applied here rather than inside each provider so every source gets
    the same transient-only, bounded, full-jitter behaviour and the same accrued
    cost accounting, which is what makes ledger rows comparable across sources.
    """
    resolved = ModelSpec.parse(spec)
    builder = _PROVIDERS.get(resolved.source)
    if builder is None:
        raise ValueError(
            f"unknown model source {resolved.source!r}; registered sources are "
            + (", ".join(known_sources()) or "(none)")
        )
    from .retry import RetryingInvoker, RetryPolicy

    return RetryingInvoker(builder(resolved), policy=retry_policy or RetryPolicy())


def _claude_cli_builder(spec: ModelSpec) -> Invoker:
    """The source that ships: the `claude` CLI on the owner's subscription.

    An unpinned binding omits the model flag, so the CLI routes the call the way
    a routing aggregator would. Cost comes back as the API-equivalent figure the
    CLI reports.
    """
    return ClaudeCliInvoker(model=spec.model)


register_provider(ANTHROPIC_CLAUDE_CLI, _claude_cli_builder)
