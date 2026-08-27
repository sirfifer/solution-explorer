"""Deterministic contracts for the compact enrichment wire boundary."""

from __future__ import annotations

import json

from analyzer.enrich.compact import (
    compact_json_schema,
    coverage_issues,
    normalize_compact_response,
    response_budget_bytes,
    salvage_compact_response,
    validate_compact_response,
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


def test_exact_deterministic_file_edge_config_and_doc_facts_are_auto_cited():
    facts = StoreFacts(
        {"components": [{
            "id": "api", "name": "API", "type": "service",
            "language": "Python", "files": ["src/api.py"],
            "config_files": [{
                "path": "pyproject.toml", "kind": "python",
                "services": ["db", "cache"],
            }],
            "docs": {"purpose": "Public API", "readme": "API setup guide"},
        }, {"id": "db", "name": "DB", "type": "database"}]},
        capabilities=[], data_entities=[], rules=[], relationships=[{
            "source": "api", "target": "db", "type": "queries",
        }],
    )
    obj = {"components": [{
        "i": "api", "label": "API",
        "purpose": "The README describes the public API.",
        "mechanism": "api queries db.",
        "place": "pyproject.toml configures the Python service.",
        "next": "Inspect src/api.py.",
        "why_matters": "It declares db and cache services.",
        "data": "Requests.", "criticality": "important",
    }], "relationships": []}

    answers = normalize_compact_response(
        obj, facts=facts, component_ids=["api"]
    )["components"]["api"]["contract"]["answers"]

    assert any(e.get("field") == "documentation" for e in answers["purpose"]["evidence"])
    assert any(e.get("field") == "edges" for e in answers["mechanism"]["evidence"])
    assert any(e.get("field") == "config_files" for e in answers["place"]["evidence"])
    assert any(e.get("field") == "config_files" for e in answers["why_matters"]["evidence"])
    assert any(e.get("field") == "files" for e in answers["next_step"]["evidence"])


def test_bare_local_fact_and_filename_shorthand_are_resolved_deterministically():
    facts = _facts()
    obj = {"components": [{
        "i": "api", "label": "API",
        "purpose": {"t": "Accepts requests.", "e": [0]},
        "mechanism": {"t": "The api.py file defines it.", "e": [[0, "api.py"]]},
        "place": {
            "t": "It has 0 inbound and 1 outbound relationships.", "e": ["F"],
        },
        "why_matters": {"t": "It owns the request boundary.", "e": [0]},
        "next": {"t": "Inspect the database edge.", "e": ["E0"]},
        "data": {"t": "Request payloads.", "e": [0]},
        "criticality": "important",
    }], "relationships": []}
    block = normalize_compact_response(obj, facts=facts, component_ids=["api"])[
        "components"
    ]["api"]
    answers = block["contract"]["answers"]
    assert answers["mechanism"]["evidence"] == [{"kind": "file", "path": "src/api.py"}]
    assert answers["place"]["evidence"] == [
        {"kind": "fact", "component": "api", "field": "inbound_edges"},
        {"kind": "fact", "component": "api", "field": "outbound_edges"},
    ]
    assert answers["why_matters"]["claim"] == "It owns the request boundary."
    assert answers["data_handled"]["claim"] == "Request payloads."
    assert block["data_handled"] == "Request payloads."


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

    payload = json.loads(user.removeprefix("COMPONENTS:\n").split(
        "\nReturn the JSON object now.", 1
    )[0])
    atoms = {item["field"]: item for item in payload[0]["deterministic_atoms"]}
    assert atoms["inbound_edges"]["scope"] == "local"
    assert atoms["system_relationship_count"]["scope"] == "global"


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


def test_compact_transport_uses_cache_boundary_without_payload_destroying_schema(monkeypatch):
    facts = _facts()
    prompt = build_compact_component_prompt(
        Partition(0, ("api",), (), True), facts,
    )
    expected_prefix, expected_user = split_cached_prompt(prompt)

    seen, result = _through_the_cli(monkeypatch, prompt)

    assert result.ok
    assert result.structured_output_enforced is False
    assert result.prefix_chars == len(expected_prefix)
    assert seen["input"] == expected_user
    assert seen["prefix"] == expected_prefix
    assert "--exclude-dynamic-system-prompt-sections" in seen["argv"]
    assert seen["argv"][seen["argv"].index("--max-turns") + 1] == "1"
    assert "--json-schema" not in seen["argv"]
    assert "--session-id" in seen["argv"]
    assert result.session_id == seen["argv"][seen["argv"].index("--session-id") + 1]


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


def test_escalation_schema_is_enforced_in_process_not_by_cli(monkeypatch):
    prompt = build_compact_escalation_prompt(
        [{"target_kind": "component", "target_id": "c1", "todo": ["mechanism"]}],
        terminal=False,
    )

    seen, _ = _through_the_cli(monkeypatch, prompt)
    prefix, user = split_cached_prompt(prompt)
    schema = compact_json_schema(prefix, user)
    assert "--json-schema" not in seen["argv"]
    # An escalation batch may carry either kind, so both arrays are bounded by
    # the escalation cap rather than by this batch's own counts.
    assert schema["properties"]["components"]["minItems"] == 0
    assert schema["properties"]["components"]["maxItems"] == 40
    assert schema["properties"]["relationships"]["maxItems"] == 40


def test_scoped_assignment_changes_only_the_uncached_escalation_tail():
    items = [{"target_kind": "component", "target_id": "c1", "todo": ["mechanism"]}]
    first = build_compact_escalation_prompt(
        items, terminal=False, assignment="inspect routing",
    )
    second = build_compact_escalation_prompt(
        items, terminal=False, assignment="inspect storage",
    )
    first_prefix, first_tail = split_cached_prompt(first)
    second_prefix, second_tail = split_cached_prompt(second)

    assert first_prefix == second_prefix
    assert first_tail != second_tail
    assert "inspect routing" in first_tail
    assert "inspect storage" in second_tail


def test_in_process_validation_strips_cosmetic_alias_and_rejects_real_shape_error():
    prompt = build_compact_component_prompt(
        Partition(0, ("api",), (), True), _facts(),
    )
    prefix, user = split_cached_prompt(prompt)
    valid = {
        "components": [{
            "i": "api", "name": "cosmetic alias", "label": "API",
            "purpose": "Accepts requests.", "mechanism": "Routes requests.",
            "place": "At the boundary.", "next": "Inspect handlers.",
            "why_matters": "It is public.", "data": "Requests",
            "criticality": "critical",
        }],
        "relationships": [],
    }
    cleaned, errors, stripped = validate_compact_response(
        valid, prefix=prefix, user=user
    )
    assert errors == []
    assert stripped == ["$.components[0].name"]
    assert "name" not in cleaned["components"][0]

    invalid = {"placeholder": True}
    _, errors, _ = validate_compact_response(invalid, prefix=prefix, user=user)
    assert any("missing required property 'components'" in error for error in errors)


def test_relationship_file_alias_survives_closed_schema_stripping():
    prefix = "ENRICHMENT TASK: relationships."
    user = 'RELATIONSHIPS:\n[{"key":"a|b|http"}]'
    obj = {
        "components": [],
        "relationships": [{
            "k": "a|b|http", "imp": "internal",
            "flow": {"t": "requests cross the edge", "e": [
                {"file": "src/client.ts", "snippet": "fetch(...)"}
            ]},
            "why": {"t": "the caller needs the API", "e": [0]},
        }],
    }
    sanitized, errors, stripped = validate_compact_response(
        obj, prefix=prefix, user=user
    )
    evidence = sanitized["relationships"][0]["flow"]["e"][0]
    assert evidence == {"kind": "file", "path": "src/client.ts"}
    assert errors == []
    assert any(path.endswith(".snippet") for path in stripped)


def test_nonzero_cli_exit_keeps_session_raw_output_and_recovered_usage(monkeypatch):
    class FailedProc:
        returncode = 1
        stdout = "provider rejected payload"
        stderr = ""

    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return FailedProc()

    monkeypatch.setattr("analyzer.enrich.engine.subprocess.run", fake_run)
    monkeypatch.setattr(
        "analyzer.enrich.engine._recover_transcript_usage",
        lambda session_id: ({"output_tokens": 37, "num_turns": 1}, {}),
    )
    result = ClaudeCliInvoker(model="sonnet")("plain prompt")
    assert not result.ok
    assert result.text == "provider rejected payload"
    assert result.session_id
    assert result.usage["output_tokens"] == 37
    assert result.session_id == seen["argv"][seen["argv"].index("--session-id") + 1]


def test_salvage_keeps_valid_sibling_and_rejects_only_invalid_item():
    prompt = build_compact_component_prompt(
        Partition(0, ("api", "db"), (), True), _facts(),
    )
    prefix, user = split_cached_prompt(prompt)
    base = {
        "label": "API", "purpose": "Accepts requests.",
        "mechanism": "Routes requests.", "place": "At the boundary.",
        "next": "Inspect handlers.", "why_matters": "It is public.",
        "data": "Requests", "criticality": "critical",
    }
    obj = {
        "components": [dict(base, i="api"), dict(base, i="db", criticality="bogus")],
        "relationships": [],
    }
    salvaged, rejected = salvage_compact_response(obj, prefix=prefix, user=user)
    assert [entry["i"] for entry in salvaged["components"]] == ["api"]
    assert rejected == ["components[1]"]


def test_evidence_overflow_is_trimmed_without_regenerating_the_claim():
    prompt = build_compact_escalation_prompt(
        [{"target_kind": "component", "target_id": "api", "todo": ["mechanism"]}],
        terminal=False,
    )
    prefix, user = split_cached_prompt(prompt)
    obj = {
        "components": [{
            "i": "api", "q": {"mechanism": {
                "t": "A bounded claim.", "e": [0, [0, 12], [0, "Symbol"]],
            }},
        }],
        "relationships": [],
    }
    cleaned, errors, stripped = validate_compact_response(
        obj, prefix=prefix, user=user
    )
    assert errors == []
    assert cleaned["components"][0]["q"]["mechanism"]["e"] == [0, [0, 12]]
    assert stripped == ["$.components[0].q.mechanism.e[2:]"]
