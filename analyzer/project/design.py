"""Project design signals into the architecture document, behind a flag.

Task D3 of ``docs/publication/DESIGN-SIGNALS-BUILD.md``. The derive tier
computes the signals and keeps them in the store
(:mod:`analyzer.derive.design_signals`); this module is the only thing that
puts them in front of a reader, and only when asked.

**Default off, and the off path does nothing at all.** ``--design-signals``
gates the whole module: with the flag absent, :func:`build_design_section`
returns ``None`` before it touches the store, no per-component key is attached,
no architecture key is stamped, and the projected bytes are exactly what they
were. Both golden corpora prove it at every task boundary.

**No-op when empty, the standing discipline.** With the flag on but a store
that carries no components, or a store the derivation finds nothing in, the
section is still ``None`` and no key appears. A component with no design
metrics carries no ``design`` key rather than an empty dict, matching the
``ai_enhance`` optional-key precedent that the whole projection follows.

**The method caveat travels with the payload.** ``design_signals.method_caveat``
is emitted as data. The viewer, ``ai.json`` and the MCP tools all render the
same sentence because they all read the same field, which is what stops three
surfaces drifting into three different accounts of what static analysis cannot
see. See :data:`analyzer.derive.design_signals.METHOD_CAVEAT`.

**What is deliberately absent.** There is no global architecture score, no
overall grade, and no cross-kind severity ordering, in this module or anywhere
else. Findings carry ``rank_within_kind`` and nothing more. Part 4 of
``docs/research/architecture-quality-signals.md`` rules those out, and a schema
that cannot express them is a stronger guarantee than a policy that says not
to.
"""

from __future__ import annotations

from typing import Optional

from ..derive.design_signals import (
    METHOD_CAVEAT,
    ZONE_OF_PAIN_MAX_SUM,
    ZONE_OF_USELESSNESS_MIN_SUM,
    DesignSignals,
    derive_design_signals,
    store_design_signals,
)

__all__ = [
    "emit_design_signals",
    "apply_design_overlay",
]


def emit_design_signals(
    arch: dict, store, *, enabled: bool = False, persist: bool = True
) -> Optional[dict]:
    """Attach per-component design metrics and return the architecture section.

    One call so there is one derivation per run and the component blocks and the
    findings can never come from two different computations of the same store.

    Returns ``None`` when the flag is off, when there is no store, or when the
    subject yields no components, and in every one of those cases ``arch`` is
    left exactly as it was found. ``None`` is the signal to the caller that no
    key should appear anywhere.

    ``persist`` also writes the signals into the store's meta table, so a run
    that projected the signals leaves a record of exactly what it projected.
    """
    if not enabled or store is None:
        return None
    signals = derive_design_signals(store)
    if not signals.items:
        return None
    if persist:
        store_design_signals(store, signals)
    apply_design_overlay(arch, signals)
    return _section(signals)


def _section(signals: DesignSignals) -> dict:
    """The architecture-level ``design_signals`` block."""
    return {
        "version": 1,
        # Data, not decoration. Every surface that renders these findings reads
        # this string rather than composing its own, and the same goes for the
        # zone thresholds: the viewer shades exactly the corners the findings
        # were computed against.
        "method_caveat": METHOD_CAVEAT,
        "has_activity": signals.has_activity,
        "component_count": len(signals.items),
        "zone_thresholds": {
            "zone_of_pain_max_sum": ZONE_OF_PAIN_MAX_SUM,
            "zone_of_uselessness_min_sum": ZONE_OF_USELESSNESS_MIN_SUM,
        },
        "finding_counts": signals.finding_counts(),
        "findings": [f.to_dict() for f in signals.findings],
        "boundaries": signals.boundary_list(),
    }


def apply_design_overlay(arch: dict, signals: DesignSignals) -> None:
    """Attach the per-component ``design`` metrics block in place.

    Recursive over the component tree, and strictly additive: a component the
    derivation has no record of keeps no key. Mirrors ``_attach_capabilities``
    in ``analyzer/derive/pipeline.py`` and the enrichment overlay's walk.
    """
    by_id = signals.by_id

    def walk(components: list) -> None:
        for comp in components:
            item = by_id.get(comp.get("id"))
            if item is not None:
                comp["design"] = item.to_dict()
            walk(comp.get("children") or [])

    walk(arch.get("components") or [])
