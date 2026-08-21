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
    META_KEY,
    METHOD_CAVEAT,
    TYPE_DECLARATION_KINDS,
    boundary_strength_for,
    derive_design_signals,
    load_design_signals,
    pair_key,
    store_design_signals,
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
    for source, target, kind in edges:
        store.add_edge(
            source_id=source, target_id=target, type=kind, evidence=[], confidence="inferred"
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
        reloaded = load_design_signals(store)
        assert reloaded.by_id["island"].instability is None
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
