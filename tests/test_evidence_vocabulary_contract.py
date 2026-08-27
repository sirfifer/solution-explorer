"""The evidence vocabulary is one contract shared by three roles.

The generator is taught the citation forms, the validator checks them, and the
adjudicator judges them. The 2026-08-26 effort proved what happens when the
copies drift: the fact citation kind was added to the generator and validator
while the adjudicator's digest stripped the fields the judge needed, so an $85
build measured a judge that was never shown the evidence.

These six checks make that drift a build failure instead of a discovery
(IMPLEMENTATION-DELTA-PROMPT.md section 5.3):

    T1  validator closure: every kind validates and fails with a reason
    T2  wire round-trip: every compact form expands to a kind that validates
    T3  prompt closure: every prompt names every form its reader must know
    T4  digest closure: the digest keeps every kind's payload keys
    T5  the wiring regression: a fact citation survives the whole pipeline
    T6  emission closure: every citable fact is a key the fact block emits
"""

from __future__ import annotations

import os

import pytest

from analyzer.derive import derive_all
from analyzer.enrich.adjudicate import build_digest
from analyzer.enrich.compact import _component_evidence, normalize_compact_response
from analyzer.enrich.contract import TRIGGERS, ContractState
from analyzer.enrich.evidence import CITABLE_FACTS, EVIDENCE_KINDS, EvidenceValidator
from analyzer.enrich.prompts import (
    _COMPACT_COMPONENT_PREFIX,
    _COMPACT_ESCALATION_PREFIX,
    StoreFacts,
    build_grounding_spotcheck_prompt,
)
from analyzer.extract import extract_repo
from analyzer.store import FactStore

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
POLYGLOT = os.path.join(FIXTURES, "polyglot")


@pytest.fixture(scope="module")
def fixture_store(tmp_path_factory):
    db = tmp_path_factory.mktemp("vocab") / "index.db"
    store = FactStore(str(db))
    extract_repo(POLYGLOT, store)
    derive_all(store, "polyglot", root_path=POLYGLOT)
    store.commit()
    yield store
    store.close()


@pytest.fixture(scope="module")
def validator(fixture_store):
    v = EvidenceValidator(fixture_store, root=POLYGLOT)
    v.attach_facts({"svc": {"inbound_edges": 6, "file_count": 4}})
    return v


@pytest.fixture(scope="module")
def real_file(fixture_store):
    by_id = {f["id"]: f for f in fixture_store.files()}
    for sym in fixture_store.symbols():
        f = by_id.get(sym["file_id"])
        if f and f.get("lines") and sym.get("name"):
            return f["path"], int(f["lines"]), sym["name"]
    raise AssertionError("polyglot fixture should have a file with symbols")


@pytest.fixture(scope="module")
def real_edge(fixture_store):
    edges = fixture_store.edges()
    src = {c["id"] for c in fixture_store.components()}
    for e in edges:
        if e.get("source_id") in src and e.get("target_id") in src:
            return e["source_id"], e["target_id"], e.get("type")
    pytest.skip("polyglot fixture derived no component edges")


# --- T1: validator closure -----------------------------------------------------


def _valid_citation(kind, real_file, real_edge):
    path, lines, symbol = real_file
    return {
        "file": {"kind": "file", "path": path, "line": min(1, lines)},
        "symbol": {"kind": "symbol", "path": path, "symbol": symbol},
        "edge": {"kind": "edge", "source": real_edge[0], "target": real_edge[1]},
        "manifest": {"kind": "manifest", "path": path},
        "doc": {"kind": "doc", "path": path},
        "fact": {"kind": "fact", "component": "svc", "field": "inbound_edges"},
    }[kind]


def _invalid_citation(kind):
    return {
        "file": {"kind": "file", "path": "no/such/file.xyz"},
        "symbol": {"kind": "symbol", "path": "no/such/file.xyz", "symbol": "Ghost"},
        "edge": {"kind": "edge", "source": "ghost-a", "target": "ghost-b"},
        "manifest": {"kind": "manifest"},
        "doc": {"kind": "doc", "path": "../../outside/root.md"},
        "fact": {"kind": "fact", "component": "svc", "field": "not_a_fact"},
    }[kind]


def test_t1_every_kind_validates_and_fails_with_a_reason(validator, real_file, real_edge):
    for kind in EVIDENCE_KINDS:
        ok = validator.check(_valid_citation(kind, real_file, real_edge))
        assert ok.ok, f"valid {kind} citation rejected: {ok.reason}"
        bad = validator.check(_invalid_citation(kind))
        assert not bad.ok, f"invalid {kind} citation accepted"
        assert bad.reason, f"invalid {kind} citation failed without a reason"


# --- T2: wire round-trip -------------------------------------------------------


class _StubFacts:
    """The minimal facts surface the compact expander reads."""

    def __init__(self, files, edges):
        self._files = files
        self._edges = edges

    def component_facts(self, cid):
        return {"files": self._files}

    def component_edge_menu(self, cid):
        return self._edges


def test_t2_every_wire_form_expands_into_the_vocabulary(validator, real_file, real_edge):
    path, lines, symbol = real_file
    facts = _StubFacts(
        [path], [{"source": real_edge[0], "target": real_edge[1], "type": real_edge[2]}]
    )
    wire_forms = [
        (0, "file"),
        ([0, symbol], "symbol"),
        ([0, 1], "file"),
        ("E0", "edge"),
        (["F", "inbound_edges"], "fact"),
        ({"kind": "fact", "component": "svc", "field": "file_count"}, "fact"),
    ]
    for raw, expected_kind in wire_forms:
        expanded = _component_evidence(raw, "svc", facts)
        assert expanded.get("kind") == expected_kind, (raw, expanded)
        assert expanded.get("kind") in EVIDENCE_KINDS
        check = validator.check(expanded)
        assert check.ok, f"expanded {raw!r} rejected: {check.reason}"
    # Malformed forms fail CLOSED with the reason preserved through E2.
    for raw in [99, "E99", ["F", "not_a_fact"], [0, None], True, "banana"]:
        expanded = _component_evidence(raw, "svc", facts)
        check = validator.check(expanded)
        assert not check.ok, f"malformed {raw!r} was accepted: {expanded}"
        assert check.reason


# --- T3: prompt closure --------------------------------------------------------


def test_t3_component_prefix_names_every_wire_form_and_citable_fact():
    for marker in ('[2,"Symbol"]', "[2,120]", '"E3"', '["F","inbound_edges"]'):
        assert marker in _COMPACT_COMPONENT_PREFIX, f"prefix lost the {marker} form"
    for fact in CITABLE_FACTS:
        assert fact in _COMPACT_COMPONENT_PREFIX, (
            f"citable fact {fact!r} missing from the component prefix; a model "
            "cannot cite a fact it was never told exists"
        )


def test_t3_repair_prefix_names_every_trigger_code():
    for trigger in TRIGGERS:
        assert trigger in _COMPACT_ESCALATION_PREFIX, (
            f"trigger {trigger} missing from the repair prefix"
        )


def test_t3_spotcheck_prompt_names_every_evidence_kind():
    prompt = build_grounding_spotcheck_prompt(
        {"target_kind": "component", "target_id": "svc",
         "grounded_at_rung": "sonnet", "claims": []}
    )
    for kind in EVIDENCE_KINDS:
        assert kind in prompt, (
            f"evidence kind {kind!r} is not described to the adjudicator; "
            "a judge scoring citations it was never taught is the f766208 bug"
        )


# --- T4: digest closure --------------------------------------------------------


def test_t4_digest_keeps_every_kinds_payload_keys():
    state = ContractState(target_kind="component", target_id="svc", state="grounded")
    answers = {
        "place": {
            "status": "answered",
            "claim": "svc has 6 inbound edges",
            "evidence": [
                {"kind": "fact", "component": "svc", "field": "inbound_edges"},
                {"kind": "edge", "source": "a", "target": "b", "edge_type": "uses"},
                {"kind": "symbol", "path": "x.py", "symbol": "Svc", "line": 3},
            ],
        }
    }
    digest = build_digest(state, answers, facts={"inbound_edges": 6})
    evidence = digest["claims"][0]["evidence"]
    fact = next(e for e in evidence if e["kind"] == "fact")
    # This is the assertion that would have failed the f766208 build: the
    # judge was promised the field and the value, and the digest stripped both.
    assert fact["component"] == "svc"
    assert fact["field"] == "inbound_edges"
    assert fact["value"] == 6
    edge = next(e for e in evidence if e["kind"] == "edge")
    assert edge["source"] == "a" and edge["target"] == "b"
    symbol = next(e for e in evidence if e["kind"] == "symbol")
    assert symbol["symbol"] == "Svc" and symbol["line"] == 3


# --- T5: the wiring regression -------------------------------------------------


def test_t5_a_fact_citation_survives_normalize_and_validate(validator, real_file, real_edge):
    """Pins the validator-attached-the-wrong-dictionary bug (8df5965) forever."""
    path, _, _ = real_file
    facts = _StubFacts([path], [])
    wire = {
        "components": [{
            "i": "svc",
            "label": "the service under test",
            "purpose": {"t": "It routes requests.", "e": [0]},
            "mechanism": {"t": "It dispatches handlers.", "e": [0]},
            "place": {"t": "It has 6 inbound edges.", "e": [["F", "inbound_edges"]]},
            "why_matters": "Everything else calls it.",
            "data": "requests",
            "criticality": "critical",
        }],
        "relationships": [],
    }
    obj = normalize_compact_response(wire, facts=facts, component_ids=["svc"], relationship_keys=[])
    answer = obj["components"]["svc"]["contract"]["answers"]["place"]
    citation = answer["evidence"][0]
    assert citation == {"kind": "fact", "component": "svc", "field": "inbound_edges"}
    check = validator.check(citation)
    assert check.ok, f"the fact citation failed validation: {check.reason}"
    assert check.detail["value"] == 6


# --- T6: emission closure ------------------------------------------------------


def test_t6_every_citable_fact_is_a_key_the_fact_block_can_emit():
    """A model may only cite fact names the block it was handed actually shows.

    T3 proves the prompt names every citable fact; this proves the fact block
    can emit each one, so the two halves of the contract cannot drift apart.
    The allow-list said "line_count" while the block emits "lines", and every
    claim following the prompt failed validation mechanically: the v2 build
    measured 8 terminal failures in exactly that class.

    The component here is deliberately maximal, because most of these keys are
    conditional. A component without a port, testing data, actions, external
    services, capabilities, entities or an AI surface emits none of those keys,
    and a thinner fixture would pass this test while the contract was broken.
    """
    component = {
        "id": "the-id", "name": "The Component", "type": "service",
        "path": "src/the", "language": "Python", "framework": "FastAPI",
        "metrics": {"lines": 10}, "files": ["a.py"],
        "description": "It does the thing.", "port": 8080,
        "testing": {"framework": "pytest"},
        "actions": [{"name": "run"}],
        "external_services": ["stripe"],
    }
    facts = StoreFacts(
        {
            "components": [component],
            "ai_surface": [{
                "component_id": "the-id", "kind": "model-call", "name": "claude",
                "confidence": "high", "instance_count": 2,
            }],
        },
        capabilities=[{
            "component_id": "the-id", "kind": "api", "name": "create account",
            "detail": "POST /accounts",
        }],
        data_entities=[{"component_id": "the-id", "name": "Account", "kind": "table"}],
        rules=[{"component_id": "the-id", "kind": "validation", "summary": "ids are uuids"}],
        relationships=[],
    )

    facts_block = facts.component_facts("the-id")
    missing = sorted(set(CITABLE_FACTS) - set(facts_block))
    assert not missing, (
        f"citable facts the fact block never emits: {missing}; a claim citing "
        "one of these fails validation no matter how true it is"
    )
