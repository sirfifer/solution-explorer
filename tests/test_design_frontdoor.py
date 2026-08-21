"""D6: the machine front door serves the same design facts, term-first.

The research document's Part 3 inversion: the human surfaces lead with the
plain-language consequence and carry the canonical term as a chip; the machine
front door flips it, because the term is the compact, unambiguous key an agent
maps to the literature and acts on. Same facts, two projections, each ordered
for its reader, and the numbers must agree between them.

Contracts under test:

  1. THE ADVERTISEMENT IS TERM-FIRST, AND ONLY WHEN THE DATA EXISTS. ai.json
     names the canonical terms and the real field names, and it advertises the
     design walk order only on a dataset that carries design signals. A recipe
     for an absent section is a lying contract.
  2. THE MCP TOOLS INVERT THE ORDER. `term` is the key, the plain sentence is
     the `description`.
  3. THE TWO SURFACES AGREE BY CONSTRUCTION. Every number the MCP tools report
     equals the number the viewer's projected payload carries, because both
     come from one derivation over one store. This is the assertion D6 asks for.
  4. THE CAVEAT AND THE NULL RULE TRAVEL WITH THE MACHINE PAYLOAD. An agent that
     reports these findings onward must be able to carry what the method cannot
     see, and must not read a null ratio as a zero.
  5. NO GLOBAL SCORE IS OFFERED TO A MACHINE EITHER. The decline-to-claim rule
     is not a UI convention.
"""

from __future__ import annotations

import json
import os

from analyzer.derive import derive_all
from analyzer.derive.design_signals import METHOD_CAVEAT
from analyzer.extract import extract_repo
from analyzer.mcp.context import StoreContext
from analyzer.mcp.tools import TOOLS, TOOLS_BY_NAME, call_tool
from analyzer.project.design import emit_design_signals
from analyzer.project.frontdoor import build_front_door
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")

DESIGN_TOOLS = ("se_design", "se_design_component", "se_blast_radius")


def _subject():
    store = FactStore(":memory:")
    extract_repo(POLYGLOT, store)
    _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
    section = emit_design_signals(arch, store, enabled=True)
    return store, arch, section


# --- 1. the advertisement --------------------------------------------------------


def test_the_design_walk_order_appears_only_when_the_data_does():
    bare = {"name": "d", "generated_at": "2025-01-01T00:00:00Z", "analyzer_version": "1.2.0"}
    ai_json, _ = build_front_door(bare, mode="monolith", monolith_filename="architecture.json")
    questions = [o["question"] for o in ai_json["walk_orders"]]
    assert not any("architecture weak" in q for q in questions), questions

    withdata = dict(bare, design_signals={"version": 1, "findings": [], "method_caveat": METHOD_CAVEAT})
    ai_json2, _ = build_front_door(withdata, mode="monolith", monolith_filename="architecture.json")
    questions2 = [o["question"] for o in ai_json2["walk_orders"]]
    assert any("architecture weak" in q for q in questions2), questions2


def test_the_manifest_section_is_advertised_and_marked_absent_when_absent():
    bare = {"name": "d", "generated_at": "2025-01-01T00:00:00Z", "analyzer_version": "1.2.0"}
    ai_json, _ = build_front_door(bare, mode="monolith", monolith_filename="architecture.json")
    section = next(s for s in ai_json["manifest_sections"] if s["key"] == "design_signals")
    assert section["present"] is False
    assert section["pointer"] == ".design_signals"


def test_the_advertisement_leads_with_canonical_terms():
    """Term-first: the inversion the research document asks for."""
    arch = {
        "name": "d", "generated_at": "2025-01-01T00:00:00Z", "analyzer_version": "1.2.0",
        "design_signals": {"version": 1, "findings": [], "method_caveat": METHOD_CAVEAT},
    }
    ai_json, _ = build_front_door(arch, mode="monolith", monolith_filename="architecture.json")
    blob = json.dumps(ai_json)
    # The canonical vocabulary an agent maps to the literature.
    for term in (
        "afferent coupling", "efferent coupling", "instability", "abstractness",
        "Dependency cycle", "Zone of pain", "Stability inversion",
        "Cross-boundary change coupling", "Boundary strength",
    ):
        assert term in blob, f"{term!r} missing from the machine advertisement"


def test_the_advertisement_names_only_real_fields():
    """The guard that exists because an agent once filtered on invented fields."""
    store, arch, section = _subject()
    try:
        arch["design_signals"] = section
        ai_json, _ = build_front_door(arch, mode="monolith", monolith_filename="architecture.json")
        advertised = next(
            s for s in ai_json["manifest_sections"] if s["key"] == "design_signals"
        )["contains"]
        real_top = set(section)
        for named in ("findings", "boundaries", "finding_counts", "method_caveat"):
            assert named in advertised
            assert named in real_top, f"advertised {named!r} is not a real key"
        real_finding = set(section["findings"][0])
        for named in ("term", "lead", "method", "targets", "edges", "evidence", "rank_within_kind"):
            assert f"`{named}`" in advertised or named in advertised
            assert named in real_finding, f"advertised finding field {named!r} is not real"
    finally:
        store.close()


# --- 2. the MCP tools invert the order --------------------------------------------


def test_the_three_design_tools_are_registered():
    names = {t.name for t in TOOLS}
    for name in DESIGN_TOOLS:
        assert name in names
        spec = TOOLS_BY_NAME[name]
        assert spec.input_schema["type"] == "object"
        assert "json" in spec.input_schema["properties"]


def test_the_machine_payload_puts_the_term_first_and_the_sentence_as_description():
    store, _arch, _section = _subject()
    try:
        ctx = StoreContext(store)
        result = call_tool(ctx, "se_design", {})
        findings = result.data["findings"]
        assert findings, "the fixture must produce findings"
        for finding in findings:
            # The inversion, asserted on the actual key order of the payload.
            keys = list(finding)
            assert keys[0] == "term", keys
            assert keys.index("term") < keys.index("description"), keys
            assert finding["term"]
            assert finding["description"]
            assert finding["term"] != finding["description"]
    finally:
        store.close()


def test_the_tool_descriptions_lead_with_the_canonical_terms():
    description = TOOLS_BY_NAME["se_design"].description
    for term in ("Dependency cycle", "Zone of pain", "Stability inversion"):
        assert term in description


def test_the_blast_radius_tool_reports_both_directions_and_cycle_membership():
    store, _arch, _section = _subject()
    try:
        ctx = StoreContext(store)
        target = ctx.components[0]["id"]
        data = call_tool(ctx, "se_blast_radius", {"id": target}).data
        assert data["id"] == target
        assert isinstance(data["blast_radius"], int)
        assert isinstance(data["depends_on_count"], int)
        assert isinstance(data["in_cycle"], bool)
        assert target not in data["dependents"], "a component is not its own dependent"
        assert target not in data["depends_on"]
        assert "parallel_safety_note" in data
    finally:
        store.close()


def test_the_design_tools_reject_an_unknown_component():
    from analyzer.mcp.tools import ToolError

    store, _arch, _section = _subject()
    try:
        ctx = StoreContext(store)
        for name in ("se_design_component", "se_blast_radius"):
            try:
                call_tool(ctx, name, {"id": "no-such-component"})
            except ToolError:
                pass
            else:
                raise AssertionError(f"{name} accepted an unknown id")
    finally:
        store.close()


# --- 3. the two surfaces agree by construction ------------------------------------


def test_every_number_the_mcp_reports_equals_the_projected_number():
    """The assertion D6 asks for: same store, same derivation, no drift.

    The viewer reads the PROJECTED payload; the MCP tools derive from the store.
    If those two ever came from different computations they could disagree, and
    a reader comparing the lens to an agent's answer would be told two different
    things about the same system. They are compared field by field here.
    """
    store, _arch, section = _subject()
    try:
        ctx = StoreContext(store)

        # Architecture level.
        overview = call_tool(ctx, "se_design", {"limit": 500}).data
        assert overview["component_count"] == section["component_count"]
        assert overview["finding_counts"] == section["finding_counts"]
        assert overview["method_caveat"] == section["method_caveat"]
        assert overview["has_git_history"] == section["has_activity"]

        # Finding for finding, the same facts under the two orderings.
        projected = {f["id"]: f for f in section["findings"]}
        machine = {f["id"]: f for f in overview["findings"]}
        assert set(projected) == set(machine)
        for fid, viewer_side in projected.items():
            agent_side = machine[fid]
            assert agent_side["term"] == viewer_side["term"]
            # The viewer's lead IS the machine's description. One string, two
            # positions in the reading order.
            assert agent_side["description"] == viewer_side["lead"]
            assert agent_side["method"] == viewer_side["method"]
            assert agent_side["targets"] == viewer_side["targets"]
            assert agent_side["edges"] == viewer_side["edges"]
            assert agent_side["rank_within_kind"] == viewer_side["rank_within_kind"]

        # Component level, for every component the projection carried.
        def walk(components):
            for comp in components:
                yield comp
                yield from walk(comp.get("children") or [])

        checked = 0
        for comp in walk(_arch.get("components") or []):
            block = comp.get("design")
            if block is None:
                continue
            data = call_tool(ctx, "se_design_component", {"id": comp["id"]}).data
            assert data["available"] is True, comp["id"]
            assert data["metrics"] == block, comp["id"]
            checked += 1
        assert checked > 0, "the fixture must carry per-component design blocks"

        # And blast radius, the number that appears on the viewer's card.
        for comp in walk(_arch.get("components") or []):
            block = comp.get("design")
            if block is None:
                continue
            data = call_tool(ctx, "se_blast_radius", {"id": comp["id"], "limit": 500}).data
            assert data["blast_radius"] == block["blast_radius"], comp["id"]
    finally:
        store.close()


# --- 4. the caveat and the null rule travel ----------------------------------------


def test_the_caveat_rides_on_every_design_tool_payload():
    store, _arch, _section = _subject()
    try:
        ctx = StoreContext(store)
        target = ctx.components[0]["id"]
        for name, args in (
            ("se_design", {}),
            ("se_design_component", {"id": target}),
            ("se_blast_radius", {"id": target}),
        ):
            data = call_tool(ctx, name, args).data
            assert data.get("method_caveat") == METHOD_CAVEAT, name
    finally:
        store.close()


def test_the_null_rule_is_stated_to_the_machine_reader():
    """A null ratio read as zero is the failure mode; say so, in the payload."""
    store, _arch, _section = _subject()
    try:
        ctx = StoreContext(store)
        data = call_tool(ctx, "se_design_component", {"id": ctx.components[0]["id"]}).data
        note = data.get("null_note", "")
        assert "not measurable" in note.lower() or "never zero" in note.lower(), note
        assert "metric_terms" in data
    finally:
        store.close()


def test_a_null_ratio_survives_the_tool_payload_as_null():
    store, _arch, _section = _subject()
    try:
        ctx = StoreContext(store)
        # The polyglot fixture is not all abstraction-capable, so at least one
        # component must report an unmeasurable ratio rather than a zero.
        nulls = 0
        for comp in ctx.components:
            data = call_tool(ctx, "se_design_component", {"id": comp["id"]}).data
            if not data.get("available"):
                continue
            if data["metrics"]["abstractness"] is None:
                nulls += 1
        assert nulls > 0, "expected at least one unmeasurable abstractness in the fixture"
    finally:
        store.close()


# --- 5. no global score for machines either ------------------------------------------


def test_no_global_score_is_offered_to_a_machine():
    store, _arch, _section = _subject()
    try:
        ctx = StoreContext(store)
        target = ctx.components[0]["id"]
        for name, args in (
            ("se_design", {}),
            ("se_design_component", {"id": target}),
            ("se_blast_radius", {"id": target}),
        ):
            blob = json.dumps(call_tool(ctx, name, args).data)
            for banned in ("architecture_score", "design_score", "overall_score", "grade"):
                assert banned not in blob, f"{banned!r} leaked into {name}"
        # And the overview says out loud that one must not be synthesized.
        note = call_tool(ctx, "se_design", {}).data["ranking_note"]
        assert "own kind only" in note
        assert "do not synthesize" in note
    finally:
        store.close()
