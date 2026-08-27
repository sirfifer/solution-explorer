"""Deterministic contracts for the compact enrichment wire boundary."""

from __future__ import annotations

import json

from analyzer.enrich.compact import (
    compact_json_schema,
    coverage_issues,
    normalize_compact_response,
    response_budget_bytes,
)
from analyzer.enrich.determine import build_determination_prompt
from analyzer.enrich.engine import ClaudeCliInvoker
from analyzer.enrich.partition import Partition
from analyzer.enrich.prompts import (
    StoreFacts,
    build_compact_component_prompt,
    build_compact_escalation_prompt,
    split_cached_prompt,
)


def _facts() -> StoreFacts:
    relationships = [{
        "source": "api", "target": "db", "type": "queries",
        "evidence": [{"kind": "file", "path": "src/api.py", "line": 12}],
    }]
    return StoreFacts(
        {"components": [{
            "id": "api", "name": "API", "type": "service",
            "language": "Python", "files": ["src/api.py"],
        }, {
            "id": "db", "name": "Database", "type": "database",
            "files": ["schema.sql"],
        }]},
        capabilities=[], data_entities=[], rules=[], relationships=relationships,
    )


def test_semantic_atoms_are_generated_once_and_expand_to_product_and_contract():
    facts = _facts()
    purpose = "Accepts account requests for the application."
    mechanism = "Dispatches validated requests through route handlers."
    place = "Sits between the client and the database."
    obj = {
        "components": [{
            "i": "api", "label": "Account request API",
            "purpose": {"t": purpose, "e": [0]},
            "mechanism": {"t": mechanism, "e": [[0, 12]]},
            "place": {"t": place, "e": ["E0"]},
            "next": {"t": "Inspect the database schema next.", "e": [0]},
            "why_matters": "It owns the public request boundary.",
            "data": "Account identifiers and request payloads",
            "criticality": "critical",
        }],
        "relationships": [],
    }

    normalized = normalize_compact_response(obj, facts=facts, component_ids=["api"])
    block = normalized["components"]["api"]
    answers = block["contract"]["answers"]

    assert answers["purpose"]["claim"] == purpose
    assert answers["mechanism"]["claim"] == mechanism
    assert answers["place"]["claim"] == place
    assert block["help_text"].count(purpose) == 1
    assert block["help_text"].count(mechanism) == 1
    assert answers["purpose"]["evidence"] == [
        {"kind": "file", "path": "src/api.py"}
    ]
    assert answers["mechanism"]["evidence"] == [
        {"kind": "file", "path": "src/api.py", "line": 12}
    ]
    assert answers["place"]["evidence"] == [
        {"kind": "edge", "source": "api", "target": "db", "edge_type": "queries"}
    ]


def test_relationship_claims_require_explicit_citations():
    facts = _facts()
    key = "api|db|queries"
    normalized = normalize_compact_response(
        {"components": [], "relationships": [{
            "k": key, "imp": "primary",
            "flow": {"t": "Account identifiers cross this edge."},
            "why": {"t": "The API persists account state."},
        }]},
        facts=facts, relationship_keys=[key],
    )

    answers = normalized["relationships"][key]["contract"]["answers"]
    assert answers["flow"]["evidence"] == []
    assert answers["why"]["evidence"] == []
    assert normalized["relationships"][key]["data_flow_description"] == answers["flow"]["claim"]


def test_exact_coverage_reports_missing_extra_and_duplicate_targets():
    issues = coverage_issues(
        {
            "components": [{"i": "a"}, {"i": "a"}, {"i": "extra"}],
            "relationships": [{"k": "x"}],
        },
        component_ids=["a", "b"], relationship_keys=["x", "y"],
    )
    assert issues == {
        "missing_components": ["b"],
        "extra_components": ["extra"],
        "duplicate_components": ["a"],
        "missing_relationships": ["y"],
        "extra_relationships": [],
        "duplicate_relationships": [],
    }


def test_schema_and_byte_budget_are_exact_for_the_requested_call_shape():
    facts = _facts()
    prompt = build_compact_component_prompt(
        Partition(0, ("api",), (), True), facts,
    )
    prefix, user = split_cached_prompt(prompt)
    schema = compact_json_schema(prefix, user)

    assert response_budget_bytes(components=1) == int((512 + 3600) * 1.08)
    # Array bounds are the RUNG caps, not this call's counts: the schema text
    # is part of the cached entry, so a per-call bound cold-writes the whole
    # stable block. Exact per-call id sets stay with coverage_issues.
    assert schema["properties"]["components"]["minItems"] == 0
    assert schema["properties"]["components"]["maxItems"] == 21
    assert schema["properties"]["relationships"]["maxItems"] == 0
    component = schema["properties"]["components"]["items"]
    assert component["additionalProperties"] is False
    assert "q" not in component["properties"]
    assert component["properties"]["label"]["maxLength"] == 240


def _through_the_cli(monkeypatch, prompt: str):
    """Run one prompt through the real transport with subprocess.run captured.

    Returns (seen, result), where seen carries the argv, the stdin text, and the
    appended prefix file's contents exactly as the CLI would have received them.
    The injected-invoker suites never reach this code, so argv construction is
    only ever observable here.
    """
    seen: dict = {}

    class FakeProc:
        returncode = 0
        stdout = json.dumps({
            "result": json.dumps({"components": [], "relationships": []}),
            "total_cost_usd": 0.0,
            "usage": {},
        })
        stderr = ""

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["input"] = kwargs["input"]
        if "--append-system-prompt-file" in argv:
            prefix_path = argv[argv.index("--append-system-prompt-file") + 1]
            with open(prefix_path, encoding="utf-8") as handle:
                seen["prefix"] = handle.read()
        return FakeProc()

    monkeypatch.setattr("analyzer.enrich.engine.subprocess.run", fake_run)
    return seen, ClaudeCliInvoker(model="sonnet")(prompt)


def test_compact_transport_uses_the_verified_cache_boundary_and_json_schema(monkeypatch):
    facts = _facts()
    prompt = build_compact_component_prompt(
        Partition(0, ("api",), (), True), facts,
    )
    expected_prefix, expected_user = split_cached_prompt(prompt)

    seen, result = _through_the_cli(monkeypatch, prompt)

    assert result.ok
    assert result.structured_output_enforced is True
    assert result.prefix_chars == len(expected_prefix)
    assert seen["input"] == expected_user
    assert seen["prefix"] == expected_prefix
    assert "--exclude-dynamic-system-prompt-sections" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--max-turns") + 1] == "1"
    serialized = seen["argv"][seen["argv"].index("--json-schema") + 1]
    schema = json.loads(serialized)
    assert schema["properties"]["components"]["minItems"] == 0
    assert schema["properties"]["components"]["maxItems"] == 21
    # The schema travels inside the cached entry. A live probe measured an
    # identical schema keeping the 0.1x prefix read and a schema differing by
    # one byte forcing the whole stable block back to a 2x cold write (rows
    # J1-J4, docs/quality/rearchitecture/data/f9-cache-probe-2026-08-26.md), so
    # two calls at the same rung must serialize the same bytes whatever they
    # ask about. A per-call schema would destroy the cache win silently.
    two = build_compact_component_prompt(
        Partition(1, ("api", "db"), (), True), facts,
    )
    two_prefix, two_user = split_cached_prompt(two)
    assert json.dumps(
        compact_json_schema(two_prefix, two_user),
        separators=(",", ":"), sort_keys=True,
    ) == serialized


def test_a_cacheable_non_ladder_prompt_gets_no_compact_schema(monkeypatch):
    """A cacheable prefix is not a licence to impose the ladder schema.

    p5 determination marks a stable prefix for the same cache boundary and then
    answers in its own verdict shape. The ladder schema pins a response to
    components/relationships arrays, which structurally forbids that verdict: a
    run so constrained cannot conclude at all. Only the transport builds the
    schema, so no injected-invoker suite can see this seam.
    """
    prompt = build_determination_prompt(
        criteria=[], census={}, adjudication=None, synthesis=None, brief=None,
        forced_round=False, rounds_so_far=[], budget_note="BUDGET: none.",
    )
    expected_prefix, expected_user = split_cached_prompt(prompt)

    seen, result = _through_the_cli(monkeypatch, prompt)

    assert "--append-system-prompt-file" in seen["argv"]
    assert "--exclude-dynamic-system-prompt-sections" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--max-turns") + 1] == "1"
    assert "--json-schema" not in seen["argv"]
    assert result.structured_output_enforced is False
    assert seen["input"] == expected_user
    assert seen["prefix"] == expected_prefix


def test_an_escalation_prompt_gets_the_items_schema(monkeypatch):
    prompt = build_compact_escalation_prompt(
        [{"target_kind": "component", "target_id": "c1", "todo": ["mechanism"]}],
        terminal=False,
    )

    seen, _ = _through_the_cli(monkeypatch, prompt)

    schema = json.loads(seen["argv"][seen["argv"].index("--json-schema") + 1])
    # An escalation batch may carry either kind, so both arrays are bounded by
    # the escalation cap rather than by this batch's own counts.
    assert schema["properties"]["components"]["minItems"] == 0
    assert schema["properties"]["components"]["maxItems"] == 40
    assert schema["properties"]["relationships"]["maxItems"] == 40
