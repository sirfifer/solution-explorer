"""Maturity-channel gating for the analyzer (card R3).

The gating model from ROBUSTNESS-STRATEGY.md ("Maturity gating (readiness), not
boolean flags") is the large-infrastructure / Rust maturity model, not a SaaS feature-flag
platform. It is in-repo and server-free: a small module that resolves a channel
and decides which gated features are active, plus a deterministic provenance
stamp that makes any non-default output self-explaining.

The three-line contract:

  - Each gateable feature declares a stability: ``stable``, ``beta``, or
    ``experimental``. A resolved channel (default ``stable``) decides what is
    active. A channel activates every feature at or below its own instability
    level, exactly like a Rust toolchain: a stable toolchain enables only stable
    features; a nightly toolchain also enables experimental ones. So on the
    default ``stable`` channel, ``beta`` and ``experimental`` features are OFF,
    which is the no-theater rule expressed as release management (an alpha
    feature that is off, or on-but-labeled, is honest; a half-built feature that
    looks done is theater).

  - DETERMINISM (the load-bearing rule). An experimental feature that is off is a
    TRUE no-op, so a default run stays byte-identical to today. The active gates
    are stamped into the projection provenance ONLY when a non-default gate is
    actually active. A default (stable-channel) run, and any non-default channel
    that happens to activate no non-stable gate, produce NOTHING new: no
    ``channel: stable`` is written into every projection. The stamp is what makes
    a genuinely non-default output self-explaining; default output carries
    nothing new, so the golden gate and the byte-parity suites still hold.

  - GOVERNANCE is the load-bearing part. Every gate carries a maturity, an owner,
    and a graduation-or-removal expectation (:class:`Gate`), recorded in the
    TASKS.md Gate Inventory. The recurring dogfood gate reviews the inventory and
    forces each stale gate to graduate or die. Fowler's rule verbatim: a feature
    is not done until its release gate is archived.

Prefer the keystone pattern to a gate when possible (build the feature fully but
wire the last user-visible connection in the final commit, so it is dark until it
works, with no gate machinery). Reach for a gate only when a feature must be
partially visible before it is done. Nothing in the analyzer needs that today, so
:data:`REGISTERED_GATES` is EMPTY by design; the mechanism, its tests, and the
governance are in place for the first feature that genuinely needs it.

Pure stdlib (invariant I7, local-first): no third-party import, no environment
read at import time (callers pass the env value in, so tests stay hermetic).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

__all__ = [
    "STABLE",
    "BETA",
    "EXPERIMENTAL",
    "CHANNELS",
    "DEFAULT_CHANNEL",
    "ENV_VAR",
    "Gate",
    "REGISTERED_GATES",
    "channel_level",
    "resolve_channel",
    "is_active",
    "active_gates",
    "gate_provenance",
]

# The three stability levels, ordered from most stable (index 0) to least stable.
# A channel's level is its index here; a feature is active when the channel's
# level is at least the feature's level (Rust-toolchain semantics).
STABLE = "stable"
BETA = "beta"
EXPERIMENTAL = "experimental"
CHANNELS: tuple[str, ...] = (STABLE, BETA, EXPERIMENTAL)

# The default channel. A run that names no channel resolves to this, and this
# channel never stamps anything, so its output is byte-identical to a run built
# before the gating mechanism existed.
DEFAULT_CHANNEL = STABLE

# The environment variable a caller may read and pass to :func:`resolve_channel`
# as the ``env_channel`` argument. This module never reads the environment itself
# (hermetic tests, no import-time side effect); the CLI does the ``os.environ``
# read and hands the value in.
ENV_VAR = "SOLUTION_EXPLORER_CHANNEL"


@dataclass(frozen=True)
class Gate:
    """A gated feature declaration: maturity plus its governance metadata.

    A real gate is ``beta`` or ``experimental`` (a ``stable`` feature is just
    part of the tool and needs no gate). ``owner`` and ``expires`` are the
    governance contract: who is accountable for graduating or removing it, and
    the date by which that decision is due. The same three facts are mirrored in
    the TASKS.md Gate Inventory so the recurring dogfood gate can review them.
    """

    id: str
    stability: str
    owner: str
    expires: str  # YYYY-MM-DD graduation-or-removal expectation
    summary: str

    def __post_init__(self) -> None:
        # Fail loud at construction, not at run time. A mistyped stability
        # (``"experimentl"``) would otherwise pass silently and only blow up when
        # ``is_active`` calls ``channel_level`` on a non-stable channel, aborting
        # a real run. Validating here means a bad gate is rejected the moment it
        # is registered (import time), which is where the no-silent-surprise rule
        # wants it.
        if self.stability not in CHANNELS:
            raise ValueError(
                f"invalid gate stability {self.stability!r} for gate "
                f"{self.id!r}; expected one of {', '.join(CHANNELS)}"
            )


# The production gate registry. EMPTY BY DESIGN: no analyzer feature currently
# needs partial visibility before it is done, and inventing a gate for show would
# be theater (VISION.md). A new gate is appended here AND recorded in the TASKS.md
# Gate Inventory with an owner and an expiry. The stamping and filtering
# machinery is exercised end to end by tests/test_features_gating.py, which
# register their own gates rather than relying on any live one.
REGISTERED_GATES: tuple[Gate, ...] = ()


def channel_level(channel: str) -> int:
    """The instability level of ``channel`` (its index in :data:`CHANNELS`).

    Raises ``ValueError`` for an unknown channel, so a typo fails loudly rather
    than silently resolving to a wrong level.
    """
    try:
        return CHANNELS.index(channel)
    except ValueError:
        raise ValueError(
            f"unknown channel {channel!r}; expected one of {', '.join(CHANNELS)}"
        ) from None


def resolve_channel(
    cli_channel: Optional[str] = None, env_channel: Optional[str] = None
) -> str:
    """Resolve the active channel with precedence CLI > env > default.

    A ``None`` or empty value at either source is treated as absent (so an unset
    env var and an omitted flag both fall through). A present-but-invalid value
    at either source raises ``ValueError`` naming the offending source, because a
    silently-ignored channel request is exactly the kind of surprise the
    no-theater rule forbids.
    """
    if cli_channel:
        if cli_channel not in CHANNELS:
            raise ValueError(
                f"invalid --channel {cli_channel!r}; expected one of "
                f"{', '.join(CHANNELS)}"
            )
        return cli_channel
    if env_channel:
        if env_channel not in CHANNELS:
            raise ValueError(
                f"invalid {ENV_VAR}={env_channel!r}; expected one of "
                f"{', '.join(CHANNELS)}"
            )
        return env_channel
    return DEFAULT_CHANNEL


def is_active(stability: str, channel: str) -> bool:
    """Whether a feature of the given ``stability`` is active on ``channel``.

    Rust-toolchain semantics: active when the channel is at least as unstable as
    the feature. So a ``stable`` feature is always active, and an
    ``experimental`` feature is active only on the ``experimental`` channel.
    """
    return channel_level(channel) >= channel_level(stability)


def active_gates(
    channel: str, gates: Optional[Iterable[Gate]] = None
) -> list[Gate]:
    """The NON-STABLE gates that ``channel`` activates, sorted by id.

    Stable gates are excluded on purpose: a stable feature is part of the tool
    and is never stamped. The result is what makes a non-default run
    self-explaining; on the default channel it is always empty (no non-stable
    feature is active), which is what preserves byte parity.

    ``gates`` defaults to :data:`REGISTERED_GATES`, read at call time (not bound
    at definition), so a test that registers its own gate list stays effective
    without rebinding a default.
    """
    if gates is None:
        gates = REGISTERED_GATES
    return sorted(
        (
            g
            for g in gates
            if g.stability != STABLE and is_active(g.stability, channel)
        ),
        key=lambda g: g.id,
    )


def gate_provenance(
    channel: str, gates: Optional[Iterable[Gate]] = None
) -> Optional[dict]:
    """The deterministic gate-provenance stamp for a run, or ``None``.

    Returns ``None`` on the default channel and whenever no non-stable gate is
    active, so a byte-identical default run adds nothing. Otherwise returns a
    small, sorted, deterministic dict naming the resolved channel and each active
    non-stable gate (id + stability only, no owner/expiry: the stamp is a
    self-explaining marker, not the governance record). Callers attach it to the
    projection ONLY when it is not ``None``.
    """
    if channel == DEFAULT_CHANNEL:
        return None
    active = active_gates(channel, gates)
    if not active:
        return None
    return {
        "channel": channel,
        "active_gates": [
            {"id": g.id, "stability": g.stability} for g in active
        ],
    }
