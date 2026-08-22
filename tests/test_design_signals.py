"""D1: the design-signals metrics core. Deterministic, no AI, not projected.

Contracts under test:

  1. THE ARITHMETIC IS RIGHT. Fan-in, fan-out, instability, abstractness and
     distance from the main sequence compute what the literature says they
     compute, on graphs small enough to verify by hand.
  2. BLAST RADIUS IS TRANSITIVE, AND SURVIVES CYCLES. A component inside a
     cycle is not counted as its own dependent.
  3. UNDEFINED IS NULL, NOT ZERO. The edge cases the plan names (no dependents,
     no type symbols, isolated components) report None rather than a number
     nobody measured. Fail-before contrast: reporting 0.0 would file a
     load-bearing Python module into the zone of pain.
  4. ABSTRACTNESS IS ONLY MEASURED WHERE IT CAN BE SEEN. The language gate
     holds, and the constant that encodes it agrees with what the parsers
     actually emit.
  5. DETERMINISTIC AND STABLE. The same store derives identically every time,
     and equal metric values always land in equal bands.
  6. IT IS NOT IN THE PROJECTION. Deriving over a real store leaves the
     projected architecture byte-identical, which is what keeps both golden
     corpora still.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile

from analyzer.derive import derive_all
from analyzer.derive.design_signals import (
    ABSTRACT_TYPE_KINDS,
    ABSTRACTION_CAPABLE_LANGUAGES,
    BOUNDARY_ORDER,
    FINDING_KINDS,
    MAX_FINDINGS_PER_KIND,
    META_KEY,
    METHOD_CAVEAT,
    MIN_COCHANGE_SUPPORT,
    TERMS,
    TYPE_DECLARATION_KINDS,
    boundary_strength_for,
    derive_design_signals,
    pair_key,
    store_design_signals,
    strongly_connected_components,
)
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")


# --- synthetic store ----------------------------------------------------------


def _store_with(components, edges=(), files=(), symbols=(), activity=()):
    """Build an in-memory store with exactly the facts a case needs.

    ``files`` entries are ``path`` or ``(path, language)``; ``symbols`` entries
    are ``(path, kind, name)``. Mirrors the helper in
    ``tests/test_importance_ranking.py``, the sibling derive-tier module.
    """
    store = FactStore(":memory:")
    path_to_id = {}
    for entry in files:
        path, language = entry if isinstance(entry, tuple) else (entry, "typescript")
        path_to_id[path] = store.add_file(
            path=path, language=language, lines=10, size_bytes=100
        )
    for comp in components:
        store.add_component(
            component_id=comp["id"],
            name=comp.get("name", comp["id"]),
            type=comp.get("type", "module"),
            path=comp.get("path", comp["id"]),
            parent_id=None,
            role=comp.get("type", "module"),
            meta=comp.get("meta", {}),
        )
        for path in comp.get("files", []):
            if path in path_to_id:
                store.link_component_file(comp["id"], path_to_id[path])
    for entry in edges:
        source, target, kind = entry[:3]
        confidence = entry[3] if len(entry) > 3 else "certain"
        store.add_edge(
            source_id=source, target_id=target, type=kind, evidence=[], confidence=confidence
        )
    for index, (path, kind, name) in enumerate(symbols):
        store.add_symbol(
            symbol_id=f"sym-{index}",
            file_id=path_to_id[path],
            name=name,
            kind=kind,
            line=1,
        )
    if activity:
        store.merge_file_activity(activity)
    store.commit()
    return store


def _plain(cid, **kw):
    return {"id": cid, "meta": {"metrics": {"lines": 10}}, **kw}


# --- 1. the arithmetic --------------------------------------------------------


def test_fan_in_and_fan_out_count_distinct_partners():
    """Two edges between the same pair are one dependency, matching importance.py."""
    store = _store_with(
        components=[_plain("hub"), _plain("x"), _plain("y"), _plain("chatty")],
        edges=[
            ("x", "hub", "import"),
            ("y", "hub", "import"),
            ("chatty", "hub", "import"),
            ("chatty", "hub", "http"),
            ("chatty", "hub", "database"),
            ("hub", "x", "import"),
        ],
    )
    try:
        by_id = derive_design_signals(store).by_id
        assert by_id["hub"].fan_in == 3
        assert by_id["hub"].fan_out == 1
        assert by_id["chatty"].fan_out == 1
    finally:
        store.close()


def test_instability_is_efferent_over_total_coupling():
    """I = Ce / (Ca + Ce). A pure consumer is 1.0, a pure dependency is 0.0."""
    store = _store_with(
        components=[_plain("consumer"), _plain("middle"), _plain("bedrock")],
        edges=[("consumer", "middle", "import"), ("middle", "bedrock", "import")],
    )
    try:
        by_id = derive_design_signals(store).by_id
        assert by_id["consumer"].instability == 1.0
        assert by_id["bedrock"].instability == 0.0
        assert by_id["middle"].instability == 0.5
    finally:
        store.close()


def test_abstractness_is_abstract_types_over_all_types():
    store = _store_with(
        components=[
            _plain("abstracted", files=["a.ts"]),
            _plain("concrete", files=["c.ts"]),
        ],
        files=[("a.ts", "typescript"), ("c.ts", "typescript")],
        symbols=[
            ("a.ts", "interface", "Reader"),
            ("a.ts", "interface", "Writer"),
            ("a.ts", "class", "Impl"),
            ("a.ts", "class", "Other"),
            ("c.ts", "class", "OnlyConcrete"),
        ],
    )
    try:
        by_id = derive_design_signals(store).by_id
        assert by_id["abstracted"].abstractness == 0.5
        assert by_id["abstracted"].type_symbols == 4
        assert by_id["abstracted"].abstract_symbols == 2
        assert by_id["concrete"].abstractness == 0.0
    finally:
        store.close()


def test_functions_and_methods_are_not_type_declarations():
    """A module of free functions declares no types; it is not thereby concrete."""
    store = _store_with(
        components=[_plain("funcs", files=["f.ts"])],
        files=[("f.ts", "typescript")],
        symbols=[
            ("f.ts", "function", "one"),
            ("f.ts", "function", "two"),
            ("f.ts", "method", "three"),
            ("f.ts", "constant", "FOUR"),
        ],
    )
    try:
        item = derive_design_signals(store).by_id["funcs"]
        assert item.type_symbols == 0
        assert item.abstractness is None
        assert item.distance_main_sequence is None
    finally:
        store.close()


def test_distance_from_the_main_sequence():
    """D = |A + I - 1|. On the sequence is 0; the two corners are 1."""
    store = _store_with(
        components=[
            # Ca=2, Ce=0 -> I=0. All interfaces -> A=1. On the main sequence.
            _plain("on_sequence", files=["s.ts"]),
            # Ca=2, Ce=0 -> I=0. All classes -> A=0. D=1, the zone of pain.
            _plain("painful", files=["p.ts"]),
            _plain("x"),
            _plain("y"),
        ],
        files=[("s.ts", "typescript"), ("p.ts", "typescript")],
        symbols=[("s.ts", "interface", "I1"), ("p.ts", "class", "C1")],
        edges=[
            ("x", "on_sequence", "import"),
            ("y", "on_sequence", "import"),
            ("x", "painful", "import"),
            ("y", "painful", "import"),
        ],
    )
    try:
        by_id = derive_design_signals(store).by_id
        assert by_id["on_sequence"].instability == 0.0
        assert by_id["on_sequence"].abstractness == 1.0
        assert by_id["on_sequence"].distance_main_sequence == 0.0
        assert by_id["painful"].distance_main_sequence == 1.0
    finally:
        store.close()


# --- 2. blast radius ----------------------------------------------------------


def test_blast_radius_is_transitive():
    """A chain d -> c -> b -> a means three components ride on a."""
    store = _store_with(
        components=[_plain("a"), _plain("b"), _plain("c"), _plain("d")],
        edges=[("b", "a", "import"), ("c", "b", "import"), ("d", "c", "import")],
    )
    try:
        by_id = derive_design_signals(store).by_id
        assert by_id["a"].blast_radius == 3
        assert by_id["b"].blast_radius == 2
        assert by_id["c"].blast_radius == 1
        assert by_id["d"].blast_radius == 0
    finally:
        store.close()


def test_blast_radius_terminates_on_a_cycle_and_excludes_self():
    """A component in a cycle reaches itself; it is still not its own dependent."""
    store = _store_with(
        components=[_plain("a"), _plain("b"), _plain("c"), _plain("outside")],
        edges=[
            ("a", "b", "import"),
            ("b", "c", "import"),
            ("c", "a", "import"),
            ("outside", "a", "import"),
        ],
    )
    try:
        by_id = derive_design_signals(store).by_id
        # a is depended on by c (direct), b and outside (transitive). Not itself.
        assert by_id["a"].blast_radius == 3
        assert by_id["outside"].blast_radius == 0
    finally:
        store.close()


def test_no_dependents_is_a_blast_radius_of_zero():
    store = _store_with(
        components=[_plain("leaf"), _plain("dep")],
        edges=[("leaf", "dep", "import")],
    )
    try:
        assert derive_design_signals(store).by_id["leaf"].blast_radius == 0
    finally:
        store.close()


# --- 3. undefined is null, not zero -------------------------------------------


def test_an_isolated_component_has_no_instability_and_no_distance():
    """Nothing depends on it and it depends on nothing, so there is no answer."""
    store = _store_with(components=[_plain("island", files=["i.ts"])],
                        files=[("i.ts", "typescript")],
                        symbols=[("i.ts", "class", "C")])
    try:
        item = derive_design_signals(store).by_id["island"]
        assert item.fan_in == 0
        assert item.fan_out == 0
        assert item.instability is None
        # Abstractness IS known here: it declares a type in a capable language.
        assert item.abstractness == 0.0
        # But distance needs both, so it stays unknown.
        assert item.distance_main_sequence is None
    finally:
        store.close()


def test_a_component_with_no_type_symbols_has_no_abstractness():
    store = _store_with(
        components=[_plain("empty"), _plain("other")],
        edges=[("empty", "other", "import")],
    )
    try:
        item = derive_design_signals(store).by_id["empty"]
        assert item.instability == 1.0
        assert item.abstractness is None
        assert item.distance_main_sequence is None
    finally:
        store.close()


def test_the_store_document_preserves_null_rather_than_coercing_to_zero():
    """The JSON round trip must not turn "unknown" into "zero" on the way out."""
    store = _store_with(components=[_plain("island")])
    try:
        signals = derive_design_signals(store)
        store_design_signals(store, signals)
        raw = json.loads(store.get_meta(META_KEY))
        record = raw["items"][0]
        assert record["instability"] is None
        assert record["abstractness"] is None
        assert record["distance_main_sequence"] is None
        assert raw["zone_thresholds"]["zone_of_pain_max_sum"] == 0.5
    finally:
        store.close()


# --- 4. abstractness is only measured where it can be seen --------------------


def test_python_components_report_unknown_abstractness_not_zero():
    """The gate that stops a load-bearing Python core being called painful.

    Fail-before contrast: without the language gate this component computes
    A=0.0, and with I=0.0 that gives D=1.0, the worst possible distance. It
    would be reported in the zone of pain purely because the Python extractor
    cannot see an ABC.
    """
    store = _store_with(
        components=[_plain("core", files=["core.py"]), _plain("x"), _plain("y")],
        files=[("core.py", "python")],
        symbols=[("core.py", "class", "Repo"), ("core.py", "class", "Impl")],
        edges=[("x", "core", "import"), ("y", "core", "import")],
    )
    try:
        item = derive_design_signals(store).by_id["core"]
        assert item.instability == 0.0
        assert item.type_symbols == 0, "python types must not enter the denominator"
        assert item.abstractness is None
        assert item.distance_main_sequence is None
    finally:
        store.close()


def test_mixed_language_component_measures_only_the_capable_files():
    store = _store_with(
        components=[_plain("mixed", files=["a.ts", "b.py"])],
        files=[("a.ts", "typescript"), ("b.py", "python")],
        symbols=[
            ("a.ts", "interface", "I"),
            ("a.ts", "class", "C"),
            ("b.py", "class", "PyOne"),
            ("b.py", "class", "PyTwo"),
        ],
    )
    try:
        item = derive_design_signals(store).by_id["mixed"]
        assert item.type_symbols == 2, "only the TypeScript declarations count"
        assert item.abstract_symbols == 1
        assert item.abstractness == 0.5
    finally:
        store.close()


def test_the_language_capability_constant_matches_what_the_parsers_emit():
    """Guard: if a parser learns a new abstract kind, this constant must move.

    Runs the real extractors over one probe file per language and asserts that
    a language emits an abstract type kind if and only if it is listed in
    ABSTRACTION_CAPABLE_LANGUAGES. This is what stops the gate rotting silently
    into a lie after someone teaches the Python parser about typing.Protocol.
    """
    probes = {
        "a.go": "package m\ntype R interface { Get() int }\ntype C struct{}\n",
        "B.java": "public interface B { int get(); }\npublic class D {}\n",
        "C.cs": "public interface IC { int Get(); }\npublic class C {}\n",
        "d.rs": "pub trait D { fn get(&self) -> i32; }\npub struct E;\n",
        "E.swift": "protocol P { func get() -> Int }\nclass K {}\n",
        "f.cpp": "class F { public: virtual int get() = 0; };\nstruct G {};\n",
        "g.rb": "module M\n  def get; end\nend\nclass H\nend\n",
        "h.py": "from abc import ABC, abstractmethod\n\n\nclass Z(ABC):\n    @abstractmethod\n    def q(self): ...\n",
        "i.ts": "export interface I { a: string }\nexport class J {}\n",
        "j.js": "export class E {}\n",
    }
    with tempfile.TemporaryDirectory() as tmp:
        for name, body in probes.items():
            with open(os.path.join(tmp, name), "w") as handle:
                handle.write(body)
        store = FactStore(":memory:")
        try:
            extract_repo(tmp, store)
            language_by_file = {row["id"]: (row.get("language") or "") for row in store.files()}
            emits_abstract: dict[str, bool] = {
                lang: False for lang in language_by_file.values() if lang
            }
            for symbol in store.symbols():
                language = language_by_file.get(symbol.get("file_id")) or ""
                if not language:
                    continue
                if (symbol.get("kind") or "") in ABSTRACT_TYPE_KINDS:
                    emits_abstract[language] = True
            assert emits_abstract, "the probe produced no parsed languages"
            for language, emits in sorted(emits_abstract.items()):
                assert emits == (language in ABSTRACTION_CAPABLE_LANGUAGES), (
                    f"{language} emits_abstract={emits} but "
                    f"ABSTRACTION_CAPABLE_LANGUAGES membership is "
                    f"{language in ABSTRACTION_CAPABLE_LANGUAGES}. Update the constant."
                )
        finally:
            store.close()


# --- boundary strength --------------------------------------------------------


def test_boundary_strength_spans_the_anatomy_spectrum():
    assert boundary_strength_for("import") == "source"
    assert boundary_strength_for("ffi") == "deployment"
    assert boundary_strength_for("docker") == "deployment"
    assert boundary_strength_for("file") == "process"
    assert boundary_strength_for("http") == "service"
    assert boundary_strength_for("grpc") == "service"
    # An unknown term degrades to the weakest claim available, not a crash.
    assert boundary_strength_for("something-new") == "source"
    assert boundary_strength_for(None) == "source"
    assert set(BOUNDARY_ORDER) >= {"source", "deployment", "process", "service"}


def test_a_pair_is_summarized_by_its_strongest_separation():
    """Two components joined by an import and an HTTP call are separated by both.

    The summary that survives is the strongest actually present, because
    claiming "convention only" about a pair that also talks over HTTP would
    understate the isolation that exists.
    """
    store = _store_with(
        components=[_plain("a"), _plain("b")],
        edges=[("a", "b", "import"), ("a", "b", "http")],
    )
    try:
        signals = derive_design_signals(store)
        assert signals.boundaries[pair_key("a", "b")] == "service"
    finally:
        store.close()


# --- 5. determinism and bands -------------------------------------------------


def test_derivation_is_stable_under_re_run():
    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c", "d", "e")],
        edges=[("b", "a", "import"), ("c", "a", "import"), ("d", "b", "import"),
               ("e", "d", "import"), ("a", "e", "import")],
    )
    try:
        first = json.dumps(derive_design_signals(store).to_dict(), sort_keys=True)
        second = json.dumps(derive_design_signals(store).to_dict(), sort_keys=True)
        assert first == second
    finally:
        store.close()


def test_equal_values_always_land_in_equal_bands():
    """Value-based quintiles, not position-based.

    Fail-before contrast: a position-based cut (what importance.py uses for its
    continuous score) would split these identical fan-in values across
    different bands on an id tiebreak, and the band is a user-visible claim.
    """
    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c", "d", "e", "f", "g", "h")],
        edges=[("h", "g", "import")],
    )
    try:
        items = derive_design_signals(store).items
        zero_fan_in = {i.bands["fan_in"] for i in items if i.fan_in == 0}
        assert len(zero_fan_in) == 1, f"identical fan_in split across bands: {zero_fan_in}"
        assert zero_fan_in == {"q1"}
        assert next(i for i in items if i.component_id == "g").bands["fan_in"] == "q5"
    finally:
        store.close()


def test_the_churn_band_is_absent_without_activity_facts():
    store = _store_with(
        components=[_plain("a", files=["a.ts"])], files=[("a.ts", "typescript")]
    )
    try:
        signals = derive_design_signals(store)
        assert signals.has_activity is False
        assert "churn" not in signals.by_id["a"].bands
    finally:
        store.close()


def test_the_churn_band_appears_with_activity_facts():
    """Five components with distinct churn span the full q1 to q5 spread."""
    names = ["c1", "c2", "c3", "c4", "c5"]
    commits = [1, 5, 20, 80, 400]
    store = _store_with(
        components=[_plain(n, files=[f"{n}.ts"]) for n in names],
        files=[(f"{n}.ts", "typescript") for n in names],
        activity=[
            (f"{n}.ts", c, 10, 0, "2020-01-01", "2026-01-01")
            for n, c in zip(names, commits)
        ],
    )
    try:
        signals = derive_design_signals(store)
        assert signals.has_activity is True
        assert signals.by_id["c5"].churn == 400
        assert [signals.by_id[n].bands["churn"] for n in names] == [
            "q1", "q2", "q3", "q4", "q5",
        ]
    finally:
        store.close()


def test_bands_cannot_span_quintiles_on_a_tiny_component_set():
    """Documented consequence of the quintile cut, matching importance.py.

    With two components the top one reports q3, not q5, because only half the
    set sits below it. This is recorded as a test rather than left as a
    surprise: a two-component repository has no meaningful quintiles, and the
    arithmetic says so instead of inventing a spread.
    """
    store = _store_with(
        components=[_plain("a"), _plain("b")], edges=[("a", "b", "import")]
    )
    try:
        by_id = derive_design_signals(store).by_id
        assert by_id["a"].bands["fan_in"] == "q1"
        assert by_id["b"].bands["fan_in"] == "q3"
    finally:
        store.close()


def test_an_empty_store_derives_nothing_without_raising():
    store = FactStore(":memory:")
    try:
        signals = derive_design_signals(store)
        assert len(signals) == 0
        assert signals.boundaries == {}
    finally:
        store.close()


def test_edges_to_unknown_components_are_ignored():
    """Edge endpoints are soft ids, so an edge can point outside the component set."""
    store = _store_with(
        components=[_plain("a")],
        edges=[("a", "not-a-component", "import"), ("ghost", "a", "import")],
    )
    try:
        item = derive_design_signals(store).by_id["a"]
        assert item.fan_in == 0
        assert item.fan_out == 0
        assert item.instability is None
    finally:
        store.close()


def test_self_edges_do_not_inflate_coupling():
    store = _store_with(components=[_plain("a")], edges=[("a", "a", "import")])
    try:
        item = derive_design_signals(store).by_id["a"]
        assert item.fan_in == 0
        assert item.fan_out == 0
        assert item.blast_radius == 0
    finally:
        store.close()


# --- 6. it is not in the projection -------------------------------------------


def test_the_method_caveat_is_carried_by_the_payload():
    """The caveat is data, not something a rendering surface invents."""
    store = _store_with(components=[_plain("a")])
    try:
        store_design_signals(store, derive_design_signals(store))
        document = json.loads(store.get_meta(META_KEY))
        assert document["method_caveat"] == METHOD_CAVEAT
        assert "reflection" in METHOD_CAVEAT
        assert "dependency injection" in METHOD_CAVEAT
        assert "dynamic dispatch" in METHOD_CAVEAT
    finally:
        store.close()


def test_deriving_signals_does_not_move_the_projection():
    """The proof that both golden corpora stay still: this is store-only work."""
    store = FactStore(":memory:")
    try:
        extract_repo(POLYGLOT, store)
        _, arch = derive_all(store, "polyglot", root_path=POLYGLOT)
        before = copy.deepcopy(arch)

        signals = derive_design_signals(store)
        store_design_signals(store, signals)
        assert len(signals) > 0, "the fixture must exercise the derivation"

        _, after = derive_all(store, "polyglot", root_path=POLYGLOT)
        assert json.dumps(after, sort_keys=True, default=str) == json.dumps(
            before, sort_keys=True, default=str
        )
        snapshot = json.dumps(after, default=str)
        assert META_KEY not in snapshot
        assert "distance_main_sequence" not in snapshot
    finally:
        store.close()


def test_the_type_kind_vocabulary_is_a_subset_of_the_model_enum():
    """The kinds this module keys on must be kinds the extractors can emit."""
    from analyzer.models import SymbolKind

    known = {k.value for k in SymbolKind}
    assert TYPE_DECLARATION_KINDS <= known, TYPE_DECLARATION_KINDS - known
    assert ABSTRACT_TYPE_KINDS <= TYPE_DECLARATION_KINDS


# ==============================================================================
# D2: findings
#
# Contracts under test:
#
#   7. CYCLES ARE FOUND, AND ONLY REAL ONES. Strongly connected components with
#      deterministic member ordering; a DAG produces none.
#   8. EVERY FINDING SPEAKS TO BOTH AUDIENCES. Lead first in plain language,
#      canonical term second, method naming the epistemic class.
#   9. DECLINE-TO-CLAIM IS ENFORCED. No severity, no global score, no
#      cross-kind rank, and no claim a component's facts cannot support.
#  10. CITATIONS ARE CHECKABLE. Every finding's evidence passes the no-AI
#      evidence validator against the real store.
# ==============================================================================


# --- 7. cycles ----------------------------------------------------------------


def test_a_cycle_is_found_with_its_members_and_its_loop_edges():
    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c", "solo")],
        edges=[
            ("a", "b", "import"),
            ("b", "c", "import"),
            ("c", "a", "import"),
            ("solo", "a", "import"),
        ],
    )
    try:
        cycles = derive_design_signals(store).findings_of_kind("cycle")
        assert len(cycles) == 1
        finding = cycles[0]
        assert finding.targets == ["a", "b", "c"], "members are sorted by id"
        assert finding.edges == [["a", "b"], ["b", "c"], ["c", "a"]]
        assert "solo" not in finding.targets
        assert finding.rank_within_kind == 1
        assert finding.id == "cycle-001"
    finally:
        store.close()


def test_a_directed_acyclic_graph_produces_no_cycle_findings():
    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c", "d")],
        edges=[("a", "b", "import"), ("b", "c", "import"), ("a", "c", "import"),
               ("c", "d", "import")],
    )
    try:
        assert derive_design_signals(store).findings_of_kind("cycle") == []
    finally:
        store.close()


def test_cycles_are_ranked_largest_first_and_kept_separate():
    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c", "d", "x", "y")],
        edges=[
            # a four-member cycle
            ("a", "b", "import"), ("b", "c", "import"),
            ("c", "d", "import"), ("d", "a", "import"),
            # and a separate two-member cycle
            ("x", "y", "import"), ("y", "x", "import"),
        ],
    )
    try:
        cycles = derive_design_signals(store).findings_of_kind("cycle")
        assert [len(c.targets) for c in cycles] == [4, 2]
        assert [c.rank_within_kind for c in cycles] == [1, 2]
        assert cycles[0].targets == ["a", "b", "c", "d"]
        assert cycles[1].targets == ["x", "y"]
        assert "These 4 parts are locked together" in cycles[0].lead
        assert "These 2 parts are locked together" in cycles[1].lead
    finally:
        store.close()


def test_scc_handles_a_deep_chain_without_recursion_limits():
    """A 3000-node chain must not blow the stack; the traversal is iterative."""
    depth = 3000
    nodes = [f"n{i:05d}" for i in range(depth)]
    outbound = {nodes[i]: {nodes[i + 1]} for i in range(depth - 1)}
    assert strongly_connected_components(nodes, outbound) == []
    # Close the chain into one giant cycle and it must be found, once.
    outbound[nodes[-1]] = {nodes[0]}
    found = strongly_connected_components(nodes, outbound)
    assert len(found) == 1
    assert len(found[0]) == depth


def test_scc_ignores_a_lone_self_edge():
    assert strongly_connected_components(["a"], {"a": {"a"}}) == []


# --- 8. the two-audience rule --------------------------------------------------


def test_every_finding_leads_in_plain_language_and_follows_with_the_term():
    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c")],
        edges=[("a", "b", "import"), ("b", "c", "import"), ("c", "a", "import")],
    )
    try:
        findings = derive_design_signals(store).findings
        assert findings, "the fixture must produce findings"
        for finding in findings:
            assert finding.lead
            # A lead is a sentence, so it opens with a capital or with the count
            # it is reporting, and it closes with a period.
            assert finding.lead[0].isupper() or finding.lead[0].isdigit(), finding.lead
            assert finding.lead.endswith(".")
            assert finding.term, finding.id
            # The lead is the plain-language consequence, so the canonical term
            # must not be what the reader meets first.
            assert not finding.lead.startswith(finding.term), finding.id
            assert finding.method in (
                "static-graph", "git-history", "static-graph+git-history"
            ), finding.method
            assert finding.kind in FINDING_KINDS
    finally:
        store.close()


def test_the_terms_come_from_the_research_translation_table():
    """Guard against a divergent phrasing being invented later."""
    assert TERMS["cycle"][0] == "Dependency cycle"
    assert TERMS["zone_of_pain"][0] == "Zone of pain"
    assert TERMS["zone_of_uselessness"][0] == "Zone of uselessness"
    assert TERMS["stability_inversion"][0] == "Stability inversion"
    assert TERMS["change_coupling"][0] == "Cross-boundary change coupling"
    assert set(TERMS) == set(FINDING_KINDS)


def test_zone_of_pain_is_found_for_a_concrete_load_bearing_component():
    store = _store_with(
        components=[
            _plain("core", files=["core.ts"]),
            _plain("x"), _plain("y"), _plain("z"),
        ],
        files=[("core.ts", "typescript")],
        symbols=[("core.ts", "class", "C1"), ("core.ts", "class", "C2")],
        edges=[("x", "core", "import"), ("y", "core", "import"), ("z", "core", "import")],
    )
    try:
        found = derive_design_signals(store).findings_of_kind("zone_of_pain")
        assert len(found) == 1
        assert found[0].targets == ["core"]
        assert found[0].lead == (
            "This is load-bearing: 3 parts lean on it. It has no flexibility built in."
        )
        assert found[0].method == "static-graph"
        assert found[0].evidence == [
            {"kind": "file", "path": "core.ts", "line": None, "symbol": None}
        ]
    finally:
        store.close()


def test_the_churn_clause_is_only_said_when_history_supports_it():
    """The mixed claim carries a mixed method chip, not the flattering half."""
    names = ["core", "f1", "f2", "f3", "f4"]
    store = _store_with(
        components=(
            [_plain("core", files=["core.ts"])]
            + [_plain(n, files=[f"{n}.ts"]) for n in names[1:]]
        ),
        files=[(f"{n}.ts", "typescript") for n in names],
        symbols=[("core.ts", "class", "C1")],
        edges=[(n, "core", "import") for n in names[1:]],
        activity=[("core.ts", 500, 10, 0, "2020-01-01", "2026-01-01")]
        + [(f"{n}.ts", 1, 1, 0, "2020-01-01", "2020-01-02") for n in names[1:]],
    )
    try:
        found = derive_design_signals(store).findings_of_kind("zone_of_pain")
        assert len(found) == 1
        assert found[0].lead.endswith("and it keeps being changed anyway.")
        assert found[0].method == "static-graph+git-history"
    finally:
        store.close()


def test_zone_of_uselessness_needs_abstract_and_unused():
    store = _store_with(
        components=[_plain("speculative", files=["s.ts"]), _plain("other")],
        files=[("s.ts", "typescript")],
        symbols=[("s.ts", "interface", "I1"), ("s.ts", "interface", "I2")],
        edges=[("speculative", "other", "import")],
    )
    try:
        found = derive_design_signals(store).findings_of_kind("zone_of_uselessness")
        assert len(found) == 1
        assert found[0].targets == ["speculative"]
        assert found[0].lead == (
            "This flexibility was built for consumers that never arrived. "
            "Nothing uses it."
        )
    finally:
        store.close()


def test_a_used_abstraction_is_not_called_useless():
    """"Nothing uses it" must be false before the finding is withheld."""
    store = _store_with(
        components=[_plain("iface", files=["i.ts"]), _plain("user")],
        files=[("i.ts", "typescript")],
        symbols=[("i.ts", "interface", "I1")],
        edges=[("user", "iface", "import")],
    )
    try:
        assert derive_design_signals(store).findings_of_kind("zone_of_uselessness") == []
    finally:
        store.close()


def test_a_stability_inversion_is_a_stable_thing_standing_on_a_volatile_one():
    store = _store_with(
        components=[_plain(c) for c in ("bedrock", "volatile", "u1", "u2", "d1", "d2")],
        edges=[
            # bedrock is depended on by two things and depends on volatile.
            ("u1", "bedrock", "import"),
            ("u2", "bedrock", "import"),
            ("bedrock", "volatile", "import"),
            # volatile depends on two things and nothing depends on it but bedrock.
            ("volatile", "d1", "import"),
            ("volatile", "d2", "import"),
        ],
    )
    try:
        signals = derive_design_signals(store)
        assert signals.by_id["bedrock"].instability < 0.5
        assert signals.by_id["volatile"].instability > 0.5
        found = signals.findings_of_kind("stability_inversion")
        assert len(found) == 1
        assert found[0].targets == ["bedrock", "volatile"]
        assert found[0].edges == [["bedrock", "volatile"]]
    finally:
        store.close()


def test_a_dependency_pointing_toward_stability_is_not_a_violation():
    """The healthy direction must produce nothing. Fail-before for the operator."""
    store = _store_with(
        components=[_plain(c) for c in ("bedrock", "volatile", "u1", "u2", "d1", "d2")],
        edges=[
            ("u1", "bedrock", "import"),
            ("u2", "bedrock", "import"),
            ("volatile", "bedrock", "import"),
            ("volatile", "d1", "import"),
            ("volatile", "d2", "import"),
        ],
    )
    try:
        assert derive_design_signals(store).findings_of_kind("stability_inversion") == []
    finally:
        store.close()


def test_change_coupling_lifts_file_pairs_to_components():
    store = _store_with(
        components=[_plain("alpha", files=["a.ts"]), _plain("beta", files=["b.ts"])],
        files=[("a.ts", "typescript"), ("b.ts", "typescript")],
        activity=[
            ("a.ts", 30, 10, 0, "2020-01-01", "2026-01-01"),
            ("b.ts", 30, 10, 0, "2020-01-01", "2026-01-01"),
        ],
    )
    store.merge_cochange_pairs([("a.ts", "b.ts", 23)])
    store.commit()
    try:
        found = derive_design_signals(store).findings_of_kind("change_coupling")
        assert len(found) == 1
        assert found[0].targets == ["alpha", "beta"]
        assert found[0].method == "git-history"
        assert {e["path"] for e in found[0].evidence} == {"a.ts", "b.ts"}
    finally:
        store.close()


def test_change_coupling_is_absent_without_git_history():
    """A store with no activity cannot make a history claim, so it makes none."""
    store = _store_with(
        components=[_plain("alpha", files=["a.ts"]), _plain("beta", files=["b.ts"])],
        files=[("a.ts", "typescript"), ("b.ts", "typescript")],
    )
    try:
        signals = derive_design_signals(store)
        assert signals.has_activity is False
        assert signals.findings_of_kind("change_coupling") == []
    finally:
        store.close()


def test_co_change_inside_one_component_is_not_cross_boundary():
    store = _store_with(
        components=[_plain("solo", files=["a.ts", "b.ts"])],
        files=[("a.ts", "typescript"), ("b.ts", "typescript")],
        activity=[("a.ts", 5, 1, 0, "2020-01-01", "2026-01-01")],
    )
    store.merge_cochange_pairs([("a.ts", "b.ts", 40)])
    store.commit()
    try:
        assert derive_design_signals(store).findings_of_kind("change_coupling") == []
    finally:
        store.close()


def test_boundary_strength_is_one_summary_not_one_row_per_import():
    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c", "d")],
        edges=[
            ("a", "b", "import"),
            ("a", "c", "import"),
            ("b", "c", "import"),
            ("c", "d", "http"),
        ],
    )
    try:
        found = derive_design_signals(store).findings_of_kind("boundary_strength")
        assert len(found) == 1, "a summary, not an accusation per seam"
        assert found[0].lead == (
            "3 of the 4 seams between parts are separated by convention only; "
            "1 is separated by a real contract."
        )
    finally:
        store.close()


# --- 9. decline to claim -------------------------------------------------------


def test_no_finding_carries_a_severity_or_a_cross_kind_rank():
    """Part 4: rankings within a finding type are fine, a global grade is not."""
    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c")],
        edges=[("a", "b", "import"), ("b", "c", "import"), ("c", "a", "import")],
    )
    try:
        signals = derive_design_signals(store)
        document = signals.to_dict()
        blob = json.dumps(document)
        for banned in ("severity", "score", "grade", "rating", "health_score"):
            assert banned not in blob, f"{banned!r} leaked into the payload"
        # rank_within_kind restarts at 1 for each kind, so the numbers cannot be
        # read as an ordering across kinds.
        by_kind: dict[str, list[int]] = {}
        for finding in signals.findings:
            by_kind.setdefault(finding.kind, []).append(finding.rank_within_kind)
        for kind, ranks in by_kind.items():
            assert ranks == list(range(1, len(ranks) + 1)), (kind, ranks)
    finally:
        store.close()


def test_a_component_with_unknown_abstractness_never_enters_a_zone():
    """The language gate must reach all the way through to the findings."""
    store = _store_with(
        components=[_plain("core", files=["core.py"]), _plain("x"), _plain("y")],
        files=[("core.py", "python")],
        symbols=[("core.py", "class", "Repo")],
        edges=[("x", "core", "import"), ("y", "core", "import")],
    )
    try:
        signals = derive_design_signals(store)
        assert signals.findings_of_kind("zone_of_pain") == []
        assert signals.findings_of_kind("zone_of_uselessness") == []
    finally:
        store.close()


def test_findings_are_capped_per_kind():
    """A pathological subject cannot produce an unbounded payload."""
    # Two components per cycle, and twenty more cycles than the cap allows.
    cycle_count = MAX_FINDINGS_PER_KIND + 20
    names = [f"c{i:04d}" for i in range(cycle_count * 2)]
    edges = []
    for i in range(0, len(names), 2):
        edges.append((names[i], names[i + 1], "import"))
        edges.append((names[i + 1], names[i], "import"))
    store = _store_with(components=[_plain(n) for n in names], edges=edges)
    try:
        cycles = derive_design_signals(store).findings_of_kind("cycle")
        assert len(cycles) == MAX_FINDINGS_PER_KIND
        assert cycles[-1].rank_within_kind == MAX_FINDINGS_PER_KIND
    finally:
        store.close()


def test_findings_are_stable_under_re_run():
    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c", "d", "e")],
        edges=[("a", "b", "import"), ("b", "c", "import"), ("c", "a", "import"),
               ("d", "a", "import"), ("e", "d", "import")],
    )
    try:
        first = json.dumps(derive_design_signals(store).to_dict(), sort_keys=True)
        second = json.dumps(derive_design_signals(store).to_dict(), sort_keys=True)
        assert first == second
    finally:
        store.close()


def test_findings_survive_the_store_round_trip():
    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c")],
        edges=[("a", "b", "import"), ("b", "c", "import"), ("c", "a", "import")],
    )
    try:
        signals = derive_design_signals(store)
        store_design_signals(store, signals)
        raw = json.loads(store.get_meta(META_KEY))
        assert raw["findings"] == [f.to_dict() for f in signals.findings]
    finally:
        store.close()


# --- 10. citations are checkable ----------------------------------------------


def test_every_finding_citation_passes_the_no_ai_evidence_validator():
    """The point of reusing the contract's evidence schema, proven end to end."""
    from analyzer.enrich.evidence import EvidenceValidator

    store = FactStore(":memory:")
    try:
        extract_repo(POLYGLOT, store)
        derive_all(store, "polyglot", root_path=POLYGLOT)
        signals = derive_design_signals(store)
        assert signals.findings, "the fixture must produce findings to check"

        validator = EvidenceValidator(store, root=POLYGLOT)
        for finding in signals.findings:
            for item in finding.evidence:
                check = validator.check(item)
                assert check.ok, f"{finding.id}: {check.reason} ({item})"
    finally:
        store.close()


def test_edge_evidence_names_a_real_edge_the_validator_can_find():
    """Fail-before: the plan's all-null edge citation is rejected by design."""
    from analyzer.enrich.evidence import EvidenceValidator

    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c")],
        edges=[("a", "b", "import"), ("b", "c", "import"), ("c", "a", "import")],
    )
    try:
        validator = EvidenceValidator(store, root=None)
        cycle = derive_design_signals(store).findings_of_kind("cycle")[0]
        assert cycle.evidence
        for item in cycle.evidence:
            assert item["kind"] == "edge"
            assert item["source"] and item["target"]
            assert validator.check(item).ok
        # The shape the plan documented is still a subset of what ships.
        assert set(cycle.evidence[0]) >= {"kind", "path", "line", "symbol"}
        # And the all-null form really is rejected, which is why it is not used.
        assert not validator.check(
            {"kind": "edge", "path": None, "line": None, "symbol": None}
        ).ok
    finally:
        store.close()


# --- 11. the dependency graph admits only what the caveat promises ------------


def test_inferred_imports_and_uses_edges_do_not_feed_the_metrics():
    """The method caveat made executable.

    The caveat promises "static import and declared communication edges only".
    On the VS Code vet run (2026-08-21), name-matched edges (a TypeScript
    import of ``util`` resolved to the Rust CLI's util component; npm package
    names resolved to unrelated local components) merged three real cycles of
    119, 23 and 20 members into one reported 209-member cycle. Edges of that
    class must not feed a headline finding.
    """
    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c")],
        edges=[
            ("a", "b", "import"),                       # certain: counts
            ("b", "c", "import", "inferred"),           # name-matched: excluded
            ("c", "a", "uses", "inferred"),             # always inferred: excluded
        ],
    )
    try:
        signals = derive_design_signals(store)
        assert signals.by_id["b"].fan_in == 1
        assert signals.by_id["c"].fan_in == 0
        assert signals.by_id["a"].fan_in == 0
        assert signals.findings_of_kind("cycle") == []
        # Every seam is still classified: exclusion from the metrics does not
        # hide the boundary.
        assert len(signals.boundaries) == 3
    finally:
        store.close()


def test_communication_edges_feed_the_metrics_whatever_their_confidence():
    store = _store_with(
        components=[_plain(c) for c in ("api", "worker")],
        edges=[("api", "worker", "http", "inferred")],
    )
    try:
        signals = derive_design_signals(store)
        assert signals.by_id["worker"].fan_in == 1
    finally:
        store.close()


def test_the_mcp_adjacency_is_the_metrics_adjacency():
    """One graph, two consumers: the shared helper and the derivation agree."""
    from analyzer.derive.design_signals import dependency_adjacency

    store = _store_with(
        components=[_plain(c) for c in ("a", "b", "c")],
        edges=[
            ("a", "b", "import"),
            ("b", "c", "import", "inferred"),
            ("a", "c", "websocket", "inferred"),
        ],
    )
    try:
        inbound, outbound = dependency_adjacency(store)
        signals = derive_design_signals(store)
        for item in signals.items:
            assert item.fan_in == len(inbound[item.component_id])
            assert item.fan_out == len(outbound[item.component_id])
    finally:
        store.close()


def test_cycle_membership_is_uncapped_unlike_the_findings_list():
    """A component in the 51st cycle is still in a cycle.

    The findings list caps cycles at MAX_FINDINGS_PER_KIND for payload
    discipline; the membership map answers "is THIS component in a cycle" and
    must not inherit the cap, because the MCP blast-radius tool gates
    parallel-edit safety on it.
    """
    pairs = []
    comps = []
    for index in range(MAX_FINDINGS_PER_KIND + 5):
        left, right = f"l{index:03d}", f"r{index:03d}"
        comps += [_plain(left), _plain(right)]
        pairs += [(left, right, "import"), (right, left, "import")]
    store = _store_with(components=comps, edges=pairs)
    try:
        signals = derive_design_signals(store)
        assert len(signals.findings_of_kind("cycle")) == MAX_FINDINGS_PER_KIND
        # Every member of every cycle is in the map, including the dropped tail.
        assert len(signals.cycle_membership) == 2 * (MAX_FINDINGS_PER_KIND + 5)
    finally:
        store.close()


def test_the_cochange_threshold_matches_the_activity_lens():
    """The Activity lens ranks coupling from the same table.

    The constant is duplicated (derive must not import from project), so this
    test is the guard that keeps the two surfaces naming the same coupled
    pairs. If this fails, one threshold changed without the other.
    """
    from analyzer.project.activity import MIN_COCHANGE_SUPPORT as ACTIVITY_SUPPORT

    assert MIN_COCHANGE_SUPPORT == ACTIVITY_SUPPORT
