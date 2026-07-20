"""P9-0 gate defect D7: enrichment role and description reach the viewer.

The gate found the iOS enrichment rendered blank role badges and blank
description lines on an enriched dataset. This test locks the two halves of the
fix, using a real FactStore built from the polyglot fixture through the real
extractor and the real enrichment writer (no mocks):

1. role: the enhance pass writes ``architectural_role`` and the projection must
   carry it under the exact key the viewer reads
   (viewer/src/types.ts ComponentAIEnhance.architectural_role). This was already
   wired end to end; the assertion is a regression lock so a future rename at the
   projection boundary fails loudly.
2. description: the enhance pass now emits a one-line ``description`` in the
   payload, and the projection copies it up to the top-level
   ``component.description`` (the field the tree and detail panel render) when the
   mechanical description is empty. ``test_description_not_surfaced_before_fix``
   is the fail-before: without the overlay copy-up the description stays inside
   ai_enhance and never reaches the field the viewer renders.
"""

from __future__ import annotations

import os
import shutil

from analyzer.derive import derive_all
from analyzer.enrich import (
    DigestIndex,
    apply_enrichment_overlay,
    stamp_enrichment,
)
from analyzer.enrich.engine import _clean_component_payload, load_scorer
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")

FIXED_CLOCK = lambda: "2026-07-19T00:00:00+00:00"  # noqa: E731


# The exact keys the viewer reads. architectural_role: ComponentNode.tsx and
# DetailPanel.tsx read component.ai_enhance.architectural_role. description: the
# tree/detail render the top-level component.description. Kept literal so a drift
# in the viewer contract (types.ts) is caught here.
VIEWER_AI_ROLE_KEY = "architectural_role"
VIEWER_COMPONENT_DESCRIPTION_KEY = "description"


def _find(components: list, cid: str) -> dict | None:
    for comp in components:
        if comp.get("id") == cid:
            return comp
        hit = _find(comp.get("children", []), cid)
        if hit:
            return hit
    return None


def _iter(components: list):
    for comp in components:
        yield comp
        yield from _iter(comp.get("children", []))


def _real_store(tmp_path) -> FactStore:
    """A real store from the polyglot fixture (extractor + deriver, no mocks)."""
    work = tmp_path / "repo"
    shutil.copytree(POLYGLOT, work)
    store = FactStore(":memory:")
    extract_repo(work, store)
    derive_all(store, "polyglot")
    return store


def _pick_blank_description_component(store: FactStore) -> str:
    """Return a derived component id whose mechanical description is empty, so the
    AI one-liner is the only thing that could fill the tree's summary line."""
    _, arch = derive_all(store, "polyglot")
    for comp in _iter(arch["components"]):
        if comp.get("id") and not (comp.get("description") or "").strip():
            return comp["id"]
    raise AssertionError("fixture has no component with an empty description")


def test_enhance_payload_schema_keeps_role_and_description():
    """The scorer's payload cleaner must retain both fields (not strip them)."""
    scorer = load_scorer()
    raw = {
        "help_text": "long form help text spanning several sentences here.",
        "description": "A backend service that handles requests.",
        "architectural_role": "business-logic",
        "criticality": "important",
        "data_handled": "request payloads, response envelopes",
        "bogus_field": "should be dropped",
    }
    cleaned = _clean_component_payload(scorer, raw, FIXED_CLOCK)
    assert cleaned["description"] == "A backend service that handles requests."
    assert cleaned["architectural_role"] == "business-logic"
    assert "bogus_field" not in cleaned
    # And the scorer's own validator accepts description (not an unexpected key).
    errors = scorer.validate_component_ai_enhance("svc", cleaned)
    assert errors == [], errors


def test_role_and_description_reach_the_viewer_via_projection(tmp_path):
    """Round trip: write through the real writer, project, assert viewer keys."""
    store = _real_store(tmp_path)
    cid = _pick_blank_description_component(store)
    index = DigestIndex.from_store(store)
    payload = {
        "help_text": "This component is the primary request handler. It fans out "
        "to workers and persists results. Without it the API cannot serve traffic.",
        "description": "Primary backend request handler for the service.",
        "architectural_role": "business-logic",
        "criticality": "critical",
        "data_handled": "request payloads, worker jobs, persisted results",
        "ai_enhance_version": 2,
    }
    stamp_enrichment(
        store, "component", cid, payload,
        digest_index=index, clock=FIXED_CLOCK,
    )
    store.commit()

    _, arch = derive_all(store, "polyglot")
    apply_enrichment_overlay(arch, store)

    comp = _find(arch["components"], cid)
    assert comp is not None
    ai = comp.get("ai_enhance") or {}
    # Half 1: role reaches the exact key the viewer reads.
    assert ai.get(VIEWER_AI_ROLE_KEY) == "business-logic"
    # Half 2: the one-line description reaches the top-level field the tree renders.
    assert comp.get(VIEWER_COMPONENT_DESCRIPTION_KEY) == (
        "Primary backend request handler for the service."
    )
    store.close()


def test_description_not_surfaced_before_fix(tmp_path):
    """Fail-before: the AI one-liner lives ONLY inside ai_enhance until the
    overlay copies it up. Pre-fix, the top-level component.description (the field
    the viewer tree renders) stayed blank, so an enriched component showed no
    summary line. The final assertion is exactly the D7 fix.
    """
    store = _real_store(tmp_path)
    cid = _pick_blank_description_component(store)
    index = DigestIndex.from_store(store)
    stamp_enrichment(
        store, "component", cid,
        {"help_text": "help", "description": "One line summary."},
        digest_index=index, clock=FIXED_CLOCK,
    )
    store.commit()

    _, arch = derive_all(store, "polyglot")
    comp_before = _find(arch["components"], cid)
    # Pre-overlay the component has no description (mechanical projection left it
    # empty for this component), so the viewer would render a blank line.
    assert not (comp_before.get("description") or "").strip()

    apply_enrichment_overlay(arch, store)
    comp_after = _find(arch["components"], cid)
    # The fix makes the AI one-liner visible on the exact field the tree reads.
    assert comp_after.get("description") == "One line summary."
    store.close()


def test_overlay_never_overwrites_a_mechanical_description(tmp_path):
    """A component that already carries a mechanical description keeps it; the AI
    one-liner does not clobber an existing summary."""
    store = _real_store(tmp_path)
    cid = _pick_blank_description_component(store)
    index = DigestIndex.from_store(store)
    stamp_enrichment(
        store, "component", cid,
        {"help_text": "help", "description": "AI one-liner."},
        digest_index=index, clock=FIXED_CLOCK,
    )
    store.commit()

    _, arch = derive_all(store, "polyglot")
    comp = _find(arch["components"], cid)
    comp["description"] = "Mechanical description from derivation."
    apply_enrichment_overlay(arch, store)
    comp = _find(arch["components"], cid)
    assert comp["description"] == "Mechanical description from derivation."
    store.close()


def test_overlay_leaves_description_blank_when_enrichment_omits_it(tmp_path):
    """Older rows predate the description field; the projection must not invent
    one. An enrichment payload without a description leaves the field blank."""
    store = _real_store(tmp_path)
    cid = _pick_blank_description_component(store)
    index = DigestIndex.from_store(store)
    stamp_enrichment(
        store, "component", cid,
        {"help_text": "help only, no description key"},
        digest_index=index, clock=FIXED_CLOCK,
    )
    store.commit()

    _, arch = derive_all(store, "polyglot")
    apply_enrichment_overlay(arch, store)
    comp = _find(arch["components"], cid)
    assert not (comp.get("description") or "").strip()
    store.close()

def test_merge_script_carries_description_to_the_top_level(tmp_path):
    # Review finding on this PR: the drift-tolerant merge copied ai_enhance
    # but left the top-level description blank, so merge-path builds (preview
    # and fallback deploys) re-blanked the summary line. The merge now mirrors
    # the overlay copy-up with the same never-overwrite rule.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "merge_ai", "scripts/merge-ai-enhancements.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    baseline = {"components": [{
        "id": "app", "name": "app", "description": "AI one liner",
        "ai_enhance": {"help_text": "long", "description": "AI one liner"},
    }]}
    target = {"components": [{"id": "app", "name": "app", "description": ""}]}
    mod.merge(baseline, target)
    comp = target["components"][0]
    assert comp["description"] == "AI one liner"

    # Never overwrite a non-empty mechanical description.
    target2 = {"components": [{"id": "app", "name": "app",
                               "description": "mechanical"}]}
    mod.merge(baseline, target2)
    assert target2["components"][0]["description"] == "mechanical"
