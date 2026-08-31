"""Deterministic contracts for the compact enrichment wire boundary."""

from __future__ import annotations

import json

import pytest

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


def test_malformed_compact_citation_preserves_raw_bytes_for_replay():
    facts = _facts()
    malformed = [99, {"unexpected": "shape"}]
    normalized = normalize_compact_response(
        {"components": [{
            "i": "api",
            "purpose": {"t": "Handles requests.", "e": [malformed]},
        }], "relationships": []},
        facts=facts, component_ids=["api"],
    )
    evidence = normalized["components"]["api"]["contract"]["answers"][
        "purpose"
    ]["evidence"][0]
    assert evidence["kind"] == "compact-invalid"
    assert evidence["raw_citation"] == malformed
    assert evidence["reason"]


def test_word_one_uniqueness_claim_gets_the_global_count_atom():
    facts = _facts()
    obj = {"components": [{
        "i": "api", "q": {"purpose": {
            "t": "Provides the fixture's one real cross-component relationship.",
            "e": ["E0"],
        }},
    }], "relationships": []}

    answer = normalize_compact_response(
        obj, facts=facts, component_ids=["api"]
    )["components"]["api"]["contract"]["answers"]["purpose"]

    assert {
        "kind": "fact", "component": "api",
        "field": "system_relationship_count", "scope": "global",
    } in answer["evidence"]


def test_child_can_cite_the_complete_relevant_root_documentation_section():
    facts = StoreFacts(
        {"components": [{
            "id": "root", "name": "Fixture", "files": ["README.md"],
            "docs": {"readme": (
                    "# Fixture\n\n"
                    "A parser fixture used to verify language coverage. It exists "
                    "to exercise every tree-sitter language.\n\n"
                    "Layout:\n- services/api is the Python API and uses a\n"
                    "  Postgres driver.\n"
                    "- services/web is the TypeScript client.\n"
                    "- unrelated/tool is a build helper."
            )},
            "children": [{
                "id": "services/api", "name": "api", "path": "services/api",
                "type": "api-server", "language": "python",
                "files": ["services/api/server.py"],
            }],
        }]},
        capabilities=[], data_entities=[], rules=[], relationships=[],
    )
    block = facts.component_facts("services/api")
    excerpt = block["subject_documentation"]["readme_excerpt"]
    assert "parser fixture" in excerpt
    assert "exercise every tree-sitter language" in excerpt
    assert "services/api is the Python API" in excerpt
    assert "Postgres driver" in excerpt
    assert "unrelated/tool" in excerpt, (
        "the containing layout section is the evidence unit; trimming it to one "
        "bullet makes true sibling placement claims impossible to adjudicate"
    )
    assert excerpt.count("services/api is the Python API") == 1, (
        "a matching indented continuation line must resolve to the same list "
        "rather than append a malformed overlapping excerpt"
    )

    obj = {"components": [{
        "i": "services/api", "q": {"purpose": {
            "t": "Exists to verify the fixture's Python parser coverage.",
            "e": [["F", "subject_documentation"]],
        }},
    }], "relationships": []}
    answer = normalize_compact_response(
        obj, facts=facts, component_ids=["services/api"]
    )["components"]["services/api"]["contract"]["answers"]["purpose"]
    assert {
        "kind": "fact", "component": "services/api",
        "field": "subject_documentation", "scope": "global",
    } in answer["evidence"]


def test_component_facts_supply_bounded_source_declarations():
    facts = StoreFacts(
        {"components": [{
            "id": "core/session", "name": "Session", "type": "module",
            "files": ["SessionManager.swift"],
        }], "symbols": [{
            "file": "SessionManager.swift", "line": 12, "end_line": 80,
            "name": "SessionManager", "kind": "actor", "visibility": "public",
            "annotations": ["MainActor"],
            "code_preview": "@MainActor public actor SessionManager {" + "x" * 2_000,
        }]},
        capabilities=[], data_entities=[], rules=[], relationships=[],
    )

    declarations = facts.component_facts("core/session")["source_declarations"]
    assert declarations[0]["name"] == "SessionManager"
    assert declarations[0]["annotations"] == ["MainActor"]
    assert len(declarations[0]["code_preview"]) <= 600


def test_local_target_declaration_supplies_behavior_beyond_five_line_preview(tmp_path):
    source = tmp_path / "DashboardView.swift"
    source.write_text("\n".join([
        "struct DashboardView: View {",
        "    @State private var showingSettings = false",
        "    var body: some View {",
        "        NavigationStack {",
        "            Button(\"Settings\") { showingSettings = true }",
        "        }",
        "        .sheet(isPresented: $showingSettings) { SettingsView() }",
        "    }",
        "}",
    ]))
    facts = StoreFacts(
        {"components": [{
            "id": "ui/dashboardview", "name": "Dashboard View", "type": "screen",
            "files": ["DashboardView.swift"],
        }], "symbols": [
            {
                "file": "DashboardView.swift", "line": 1, "end_line": 9,
                "name": "DashboardView", "kind": "struct",
                "code_preview": "struct DashboardView: View {\n    @State private var showingSettings",
            },
            {
                "file": "DashboardView.swift", "line": 5, "end_line": 7,
                "name": "showSettings", "kind": "method",
                "parent": ". ui DashboardView.swift DashboardView",
                "code_preview": "func showSettings()",
            },
        ]},
        capabilities=[], data_entities=[], rules=[], relationships=[], root=tmp_path,
    )

    declarations = facts.component_facts("ui/dashboardview")["source_declarations"]
    declaration = declarations[0]
    assert ".sheet(isPresented:" in declaration["code_preview"]
    assert "SettingsView()" in declaration["code_preview"]
    assert declarations[1]["name"] == "showSettings"
    assert "Button(\"Settings\")" in declarations[1]["code_preview"]

    context = facts.evidence_source_context("ui/dashboardview", {
        "kind": "symbol", "path": "DashboardView.swift", "symbol": "DashboardView",
    })
    assert context is not None
    assert ".sheet(isPresented:" in context["code_preview"]


def test_component_facts_supply_caller_handoff_and_called_method(tmp_path):
    source = tmp_path / "CurriculumView.swift"
    source.write_text("\n".join([
        "struct ServerBrowser: View {",
        "    var body: some View {",
        "        CurriculumDownloadFlowView(onDownload: { ids in",
        "            await downloadCurriculum(ids)",
        "        })",
        "    }",
        "    private func downloadCurriculum(_ ids: Set<String>) async {",
        "        let imported = try await DownloadManager.shared.download(ids)",
        "        onDownload(imported)",
        "    }",
        "}",
        "struct CurriculumDownloadFlowView: View {",
        "    let onDownload: (Set<String>) async -> Void",
        "    var body: some View { Text(\"Download\") }",
        "}",
        "actor DownloadManager {",
        "    static let shared = DownloadManager()",
        "    func download(_ ids: Set<String>) async throws -> Curriculum {",
        "        // Import to Core Data",
        "        let result = try Parser.importDocument(ids)",
        "        try result.managedObjectContext?.save()",
        "        return result",
        "    }",
        "}",
    ]))
    facts = StoreFacts(
        {"components": [{
            "id": "ui/curriculumdownloadflowview",
            "name": "Curriculum Download Flow", "type": "screen",
            "files": ["CurriculumView.swift"],
        }], "symbols": [
            {"file": "CurriculumView.swift", "line": 1, "end_line": 11,
             "name": "ServerBrowser", "kind": "struct"},
            {"file": "CurriculumView.swift", "line": 7, "end_line": 10,
             "name": "downloadCurriculum", "kind": "method",
             "parent": ". ui CurriculumView.swift ServerBrowser"},
            {"file": "CurriculumView.swift", "line": 12, "end_line": 15,
             "name": "CurriculumDownloadFlowView", "kind": "struct"},
            {"file": "CurriculumView.swift", "line": 16, "end_line": 24,
             "name": "DownloadManager", "kind": "actor"},
            {"file": "CurriculumView.swift", "line": 18, "end_line": 23,
             "name": "download", "kind": "method",
             "parent": ". services CurriculumView.swift DownloadManager"},
        ]},
        capabilities=[], data_entities=[], rules=[], relationships=[], root=tmp_path,
    )

    references = facts.component_facts(
        "ui/curriculumdownloadflowview"
    )["source_references"]
    assert references[0]["caller_symbol"] == "ServerBrowser"
    assert "await downloadCurriculum(ids)" in references[0]["code_preview"]
    assert references[0]["related_declarations"][0]["name"] == "downloadCurriculum"
    assert "DownloadManager.shared.download" in (
        references[0]["related_declarations"][0]["code_preview"]
    )
    assert "DownloadManager.shared.download" in references[0]["handoff_preview"]
    assert "onDownload(imported)" in references[0]["handoff_preview"]
    downstream = references[0]["downstream_declarations"][0]
    assert downstream["owner"] == "DownloadManager"
    assert "Import to Core Data" in downstream["code_preview"]
    assert "managedObjectContext?.save" in downstream["code_preview"]


def test_high_degree_component_gets_every_bounded_dependency_callsite():
    relationships = [
        {
            "source": "app", "target": f"services/service-{index}",
            "type": "uses", "label": f"uses Service{index}",
            "evidence": [{
                "file": "App.swift", "line": index + 1,
                "snippet": f"Service{index}",
            }],
        }
        for index in range(9)
    ]
    facts = StoreFacts(
        {"components": [{
            "id": "app", "name": "App", "type": "application", "files": [],
        }]},
        capabilities=[], data_entities=[], rules=[], relationships=relationships,
    )

    dependencies = facts.component_facts("app")["outbound_dependency_evidence"]
    assert len(dependencies) == 9
    assert dependencies[-1] == {
        "target": "services/service-8", "type": "uses",
        "label": "uses Service8",
        "evidence": [{"file": "App.swift", "line": 9, "snippet": "Service8"}],
    }


def test_unique_supplied_declaration_repairs_a_misread_file_index():
    facts = StoreFacts(
        {"components": [{
            "id": "ui/dashboard", "name": "Dashboard", "type": "screen",
            "files": ["Dashboard.swift"],
        }], "symbols": [{
            "file": "Dashboard.swift", "line": 12, "end_line": 80,
            "name": "DashboardView", "kind": "struct",
            "code_preview": "struct DashboardView: View {",
        }]},
        capabilities=[], data_entities=[], rules=[], relationships=[],
    )
    wire = {"components": [{
        "i": "ui/dashboard",
        "purpose": {"t": "Shows the dashboard.", "e": [[2, "DashboardView"]]},
    }], "relationships": []}

    answer = normalize_compact_response(
        wire, facts=facts, component_ids=["ui/dashboard"]
    )["components"]["ui/dashboard"]["contract"]["answers"]["purpose"]

    assert answer["evidence"] == [{
        "kind": "symbol", "path": "Dashboard.swift",
        "symbol": "DashboardView", "line": 12,
    }]


@pytest.mark.parametrize(
    "citation",
    ["symbol:DashboardView", ["source_declarations", "DashboardView"]],
)
def test_closed_declaration_shorthands_resolve_to_the_supplied_symbol(citation):
    facts = StoreFacts(
        {"components": [{
            "id": "ui/dashboard", "name": "Dashboard", "type": "screen",
            "files": ["Dashboard.swift"],
        }], "symbols": [{
            "file": "Dashboard.swift", "line": 12, "end_line": 80,
            "name": "DashboardView", "kind": "struct",
            "code_preview": "struct DashboardView: View {",
        }]},
        capabilities=[], data_entities=[], rules=[], relationships=[],
    )
    wire = {"components": [{
        "i": "ui/dashboard",
        "mechanism": {
            "t": "DashboardView renders the dashboard.", "e": [citation],
        },
    }], "relationships": []}

    answer = normalize_compact_response(
        wire, facts=facts, component_ids=["ui/dashboard"],
    )["components"]["ui/dashboard"]["contract"]["answers"]["mechanism"]
    assert answer["evidence"] == [{
        "kind": "symbol", "path": "Dashboard.swift", "symbol": "DashboardView",
    }]


@pytest.mark.parametrize(
    "citation",
    [
        ["source_declaration", "DashboardView"],
        ["S", "DashboardView"],
        ["F", "DashboardView"],
    ],
)
def test_live_declaration_aliases_resolve_only_to_an_exact_supplied_symbol(citation):
    facts = StoreFacts(
        {"components": [{
            "id": "ui/dashboard", "name": "Dashboard", "type": "screen",
            "files": ["Dashboard.swift"],
        }], "symbols": [{
            "file": "Dashboard.swift", "line": 12, "end_line": 80,
            "name": "DashboardView", "kind": "struct",
            "code_preview": "struct DashboardView: View {",
        }]},
        capabilities=[], data_entities=[], rules=[], relationships=[],
    )
    wire = {"components": [{
        "i": "ui/dashboard",
        "mechanism": {"t": "DashboardView renders the dashboard.", "e": [citation]},
    }], "relationships": []}

    evidence = normalize_compact_response(
        wire, facts=facts, component_ids=["ui/dashboard"],
    )["components"]["ui/dashboard"]["contract"]["answers"]["mechanism"]["evidence"]
    assert len(evidence) == 1
    assert {
        key: evidence[0][key] for key in ("kind", "path", "symbol")
    } == {
        "kind": "symbol", "path": "Dashboard.swift", "symbol": "DashboardView",
    }


def test_flattened_single_symbol_citation_is_not_split_into_invalid_strings():
    facts = StoreFacts(
        {"components": [{
            "id": "ui/dashboard", "name": "Dashboard", "type": "screen",
            "files": ["Dashboard.swift"],
        }], "symbols": [{
            "file": "Dashboard.swift", "line": 12, "end_line": 80,
            "name": "DashboardView", "kind": "struct",
            "code_preview": "struct DashboardView: View {",
        }]},
        capabilities=[], data_entities=[], rules=[], relationships=[],
    )
    wire = {"components": [{
        "i": "ui/dashboard",
        "mechanism": {
            "t": "DashboardView renders the dashboard.",
            "e": ["S", "DashboardView"],
        },
    }], "relationships": []}

    evidence = normalize_compact_response(
        wire, facts=facts, component_ids=["ui/dashboard"],
    )["components"]["ui/dashboard"]["contract"]["answers"]["mechanism"]["evidence"]
    assert len(evidence) == 1
    assert {key: evidence[0][key] for key in ("kind", "path", "symbol")} == {
        "kind": "symbol", "path": "Dashboard.swift", "symbol": "DashboardView",
    }
    assert evidence[0]["line"] == 12


def test_relationship_facts_include_bounded_endpoint_declaration_context():
    key = "api|db|queries"
    facts = StoreFacts(
        {"components": [
            {"id": "api", "name": "API", "files": ["api.py"]},
            {"id": "db", "name": "Database", "files": ["db.py"]},
        ], "symbols": [
            {"file": "api.py", "line": 1, "end_line": 5,
             "name": "API", "kind": "class", "code_preview": "class API:"},
            {"file": "db.py", "line": 1, "end_line": 5,
             "name": "Database", "kind": "class", "code_preview": "class Database:"},
        ]},
        capabilities=[], data_entities=[], rules=[], relationships=[{
            "source": "api", "target": "db", "type": "queries",
            "evidence": [{"kind": "file", "path": "api.py", "line": 3}],
        }],
    )

    block = facts.relationship_facts(key)
    assert {row["component"] for row in block["source_declarations"]} == {"api", "db"}
    assert {row["endpoint"] for row in block["source_declarations"]} == {
        "source", "target",
    }


def test_parent_child_symbol_pair_resolves_the_exact_supplied_method():
    facts = StoreFacts(
        {"components": [{
            "id": "ui/pack", "name": "Pack View", "type": "screen",
            "files": ["PackView.swift"],
        }], "symbols": [
            {
                "file": "PackView.swift", "line": 1, "end_line": 80,
                "name": "PackView", "kind": "struct", "code_preview": "struct PackView",
            },
            {
                "file": "PackView.swift", "line": 50, "end_line": 60,
                "name": "createPack", "kind": "method",
                "parent": ". ui PackView.swift PackView",
                "code_preview": "func createPack()",
            },
        ]},
        capabilities=[], data_entities=[], rules=[], relationships=[],
    )
    wire = {"components": [{
        "i": "ui/pack", "mechanism": {
            "t": "PackView creates a pack.",
            "e": [["symbol:PackView", "createPack"]],
        },
    }], "relationships": []}

    evidence = normalize_compact_response(
        wire, facts=facts, component_ids=["ui/pack"],
    )["components"]["ui/pack"]["contract"]["answers"]["mechanism"]["evidence"]
    assert evidence == [{
        "kind": "symbol", "path": "PackView.swift",
        "symbol": "createPack", "line": 50,
    }]


def test_same_file_type_referenced_by_target_is_prioritized_with_its_method(tmp_path):
    source = tmp_path / "OralView.swift"
    source.write_text("\n".join([
        "struct OralView: View {",
        "    @StateObject var model: OralViewModel",
        "    var body: some View { Text(\"oral\") }",
        "}",
        "final class OralViewModel: ObservableObject {",
        "    let tts = OnDeviceTTS()",
        "    func prepareServices() { tts.prewarm() }",
        "}",
    ]))
    symbols = [
        {"file": "OralView.swift", "line": 1, "end_line": 4,
         "name": "OralView", "kind": "struct", "code_preview": "struct OralView"},
        {"file": "OralView.swift", "line": 5, "end_line": 8,
         "name": "OralViewModel", "kind": "class", "code_preview": "class OralViewModel"},
        {"file": "OralView.swift", "line": 7, "end_line": 7,
         "name": "prepareServices", "kind": "method",
         "parent": ". ui OralView.swift OralViewModel",
         "code_preview": "func prepareServices()"},
    ]
    symbols.extend({
        "file": "OralView.swift", "line": 3, "end_line": 3,
        "name": f"targetHelper{index}", "kind": "method",
        "parent": ". ui OralView.swift OralView", "code_preview": "func helper()",
    } for index in range(8))
    facts = StoreFacts(
        {"components": [{
            "id": "ui/oralview", "name": "Oral View", "type": "screen",
            "files": ["OralView.swift"],
        }], "symbols": symbols},
        capabilities=[], data_entities=[], rules=[], relationships=[], root=tmp_path,
    )

    declarations = facts.component_facts("ui/oralview")["source_declarations"]
    assert [item["name"] for item in declarations[:3]] == [
        "OralView", "OralViewModel", "prepareServices",
    ]
    assert "OnDeviceTTS" in declarations[1]["code_preview"]
    assert "prewarm" in declarations[2]["code_preview"]


def test_short_compose_service_name_gets_its_documented_layout_section_and_peer():
    facts = StoreFacts(
        {"components": [{
            "id": "root", "files": ["README.md"],
            "docs": {"readme": (
                "A parser fixture.\n\nLayout:\n"
                "- `services/api` Python service.\n"
                "- `docker-compose.yml` infrastructure: db and cache services."
            )},
        }, {
            "id": "compose/db", "name": "db", "type": "database",
            "config_files": [{
                "path": "docker-compose.yml", "type": "docker-compose-service",
                "services": ["db"],
            }],
        }, {
            "id": "compose/cache", "name": "cache", "type": "cache",
            "config_files": [{
                "path": "docker-compose.yml", "type": "docker-compose-service",
                "services": ["cache"],
            }],
        }]},
        capabilities=[], data_entities=[], rules=[], relationships=[],
    )

    block = facts.component_facts("compose/db")
    assert "infrastructure: db and cache services" in (
        block["subject_documentation"]["readme_excerpt"]
    )
    assert block["peer_components"] == [{
        "id": "compose/cache", "name": "cache", "type": "cache",
    }]

    normalized = normalize_compact_response(
        {"components": [{
            "i": "compose/db", "q": {"next_step": {
                "t": "Compare the peer compose/cache service next.",
                "e": [["F", "peer_components"]],
            }},
        }], "relationships": []},
        facts=facts, component_ids=["compose/db"],
    )
    evidence = normalized["components"]["compose/db"]["contract"]["answers"][
        "next_step"
    ]["evidence"]
    assert {
        "kind": "fact", "component": "compose/db",
        "field": "peer_components", "scope": "global",
    } in evidence


def test_documented_intent_and_deterministic_absence_get_exact_auto_citations():
    facts = StoreFacts(
        {"components": [{
            "id": "root", "files": ["README.md"],
            "docs": {"readme": (
                "A parser fixture used to verify every language and relationship.\n\n"
                "- services/api is the Python API."
            )},
            "children": [{
                "id": "services/api", "path": "services/api",
                "language": "python", "files": ["services/api/server.py"],
            }],
        }]},
        capabilities=[], data_entities=[], rules=[], relationships=[{
            "source": "services/api", "target": "root", "type": "reports",
            "evidence": [{"kind": "file", "path": "services/api/server.py"}],
        }],
    )
    obj = {"components": [{
        "i": "services/api", "q": {
            "purpose": {
                "t": "This fixture component exists to verify Python parser coverage.",
                "e": [0],
            },
            "mechanism": {
                "t": "It has no internal capabilities or data entities detected.",
                "e": [0],
            },
        },
    }], "relationships": []}

    answers = normalize_compact_response(
        obj, facts=facts, component_ids=["services/api"]
    )["components"]["services/api"]["contract"]["answers"]
    purpose_fields = {item.get("field") for item in answers["purpose"]["evidence"]}
    mechanism_fields = {item.get("field") for item in answers["mechanism"]["evidence"]}
    assert "subject_documentation" in purpose_fields
    assert {"capability_count", "data_entity_count"} <= mechanism_fields


def test_relationship_intent_gets_subject_documentation_and_global_count_facts():
    key = "api|db|queries"
    facts = StoreFacts(
        {"components": [{
            "id": "root", "files": ["README.md"],
            "docs": {"readme": "A fixture built to verify relationship detection."},
        }, {"id": "api"}, {"id": "db"}]},
        capabilities=[], data_entities=[], rules=[], relationships=[{
            "source": "api", "target": "db", "type": "queries",
            "evidence": [{"kind": "file", "path": "src/api.py"}],
        }],
    )
    normalized = normalize_compact_response(
        {"components": [], "relationships": [{
            "k": key,
            "flow": {"t": "api queries db.", "e": [0]},
            "why": {
                "t": "The fixture's one relationship was built to verify detection.",
                "e": [0],
            },
        }]},
        facts=facts, relationship_keys=[key],
    )
    evidence = normalized["relationships"][key]["contract"]["answers"]["why"]["evidence"]
    assert {
        "kind": "fact", "component": key,
        "field": "system_relationship_count", "scope": "global",
    } in evidence
    assert {
        "kind": "fact", "component": key,
        "field": "subject_documentation", "scope": "global",
    } in evidence


def test_relationship_facts_include_bounded_source_context_around_callsite(tmp_path):
    source = tmp_path / "Dashboard.swift"
    source.write_text("\n".join([
        "struct Dashboard: View {",
        "    @State private var showingOral = false",
        "    var body: some View {",
        "        Button(\"Oral practice\") { showingOral = true }",
        "        EmptyView()",
        "            .navigationDestination(isPresented: $showingOral) {",
        "                OralSessionView()",
        "            }",
        "    }",
        "}",
    ]))
    key = "dashboard|oral|navigation"
    facts = StoreFacts(
        {"components": [{"id": "dashboard"}, {"id": "oral"}]},
        capabilities=[], data_entities=[], rules=[], root=tmp_path,
        relationships=[{
            "source": "dashboard", "target": "oral", "type": "navigation",
            "evidence": [{
                "file": "Dashboard.swift", "line": 7,
                "snippet": "OralSessionView",
            }],
        }],
    )

    evidence = facts.relationship_facts(key)["evidence"][0]
    assert evidence["snippet"] == "OralSessionView"
    assert "Button(\"Oral practice\")" in evidence["context"]
    assert ".navigationDestination(isPresented: $showingOral)" in evidence["context"]


def test_conjoined_zero_edges_and_compose_prose_get_both_exact_fact_types():
    facts = StoreFacts(
        {"components": [{
            "id": "cache", "type": "cache", "files": [],
            "config_files": [{
                "path": "docker-compose.yml", "type": "docker-compose-service",
            }],
        }]},
        capabilities=[], data_entities=[], rules=[], relationships=[],
    )
    obj = {"components": [{
        "i": "cache", "q": {
            "place": {
                "t": "It has zero inbound and outbound edges.", "e": [],
            },
            "mechanism": {
                "t": "It comes from compose service configuration.", "e": [],
            },
        },
    }], "relationships": []}
    answers = normalize_compact_response(
        obj, facts=facts, component_ids=["cache"]
    )["components"]["cache"]["contract"]["answers"]
    edge_fields = {item.get("field") for item in answers["place"]["evidence"]}
    config_fields = {item.get("field") for item in answers["mechanism"]["evidence"]}
    assert {"inbound_edges", "outbound_edges"} <= edge_fields
    assert "config_files" in config_fields


def test_compose_declaration_and_documented_parsing_intent_get_exact_facts():
    facts = StoreFacts(
        {"components": [{
            "id": "root", "files": ["README.md"],
            "docs": {"readme": "A tiny fixture used to exercise analyzer parsing."},
            "children": [{
                "id": "compose/cache", "type": "cache", "files": [],
                "config_files": [{
                    "path": "docker-compose.yml",
                    "type": "docker-compose-service",
                }],
            }],
        }]},
        capabilities=[], data_entities=[], rules=[], relationships=[],
    )
    normalized = normalize_compact_response(
        {"components": [{
            "i": "compose/cache", "q": {
                "data_handled": {
                    "t": "No data entities; it is a service declaration, not code.",
                    "e": [],
                },
                "purpose": {
                    "t": "A compose cache service used to exercise parsing.",
                    "e": [],
                },
            },
        }], "relationships": []},
        facts=facts, component_ids=["compose/cache"],
    )
    answers = normalized["components"]["compose/cache"]["contract"]["answers"]
    data_fields = {item.get("field") for item in answers["data_handled"]["evidence"]}
    purpose_fields = {item.get("field") for item in answers["purpose"]["evidence"]}

    assert {"data_entity_count", "file_count", "config_files"} <= data_fields
    assert {"config_files", "subject_documentation"} <= purpose_fields


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

    assert "A system relationship count proves how many edges exist" in prefix
    assert "Prefer a supported parent component" in prefix
    assert 'not {"t","e"} evidence objects' in prefix
    assert "testing_maturity is exactly" in prefix
    assert "key_user_flows is an array of at most five strings" in prefix

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


def test_escalation_claims_keep_the_quality_complete_answer_boundary():
    prompt = build_compact_escalation_prompt(
        [{"target_kind": "component", "target_id": "api", "todo": ["place"]}],
        terminal=False,
    )
    prefix, user = split_cached_prompt(prompt)
    schema = compact_json_schema(prefix, user)
    answer = schema["properties"]["components"]["items"]["properties"]["q"][
        "properties"
    ]["place"]
    assert answer["oneOf"][0]["maxLength"] == 640
    assert answer["oneOf"][1]["properties"]["t"]["maxLength"] == 640
    assert answer["oneOf"][1]["properties"]["e"]["maxItems"] == 12
    assert "structural maximum is twelve" in prefix
    assert "never omit needed meaning to hit a" in prefix
    assert "A relationship count does not identify endpoints" in prefix
    assert "prefer a supported parent over an uncited child path" in prefix


def test_more_than_four_exact_citations_survive_the_compact_boundary():
    prompt = build_compact_escalation_prompt(
        [{"target_kind": "component", "target_id": "api", "todo": ["place"]}],
        terminal=False,
    )
    prefix, user = split_cached_prompt(prompt)
    response = {
        "components": [{
            "i": "api",
            "q": {"place": {"t": "Compound supported claim.", "e": [
                ["F", "documentation"],
                ["F", "language"],
                ["F", "inbound_edges"],
                ["F", "outbound_edges"],
                ["F", "peer_components"],
            ]}},
        }],
        "relationships": [],
    }

    sanitized, errors, stripped = validate_compact_response(
        response, prefix=prefix, user=user,
    )

    assert errors == []
    assert stripped == []
    assert len(sanitized["components"][0]["q"]["place"]["e"]) == 5


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


def test_five_citations_are_not_silently_trimmed_before_adjudication():
    prompt = build_compact_escalation_prompt(
        [{"target_kind": "component", "target_id": "api", "todo": ["mechanism"]}],
        terminal=False,
    )
    prefix, user = split_cached_prompt(prompt)
    obj = {
        "components": [{
            "i": "api", "q": {"mechanism": {
                "t": "A bounded claim.",
                "e": [0, [0, 12], [0, "Symbol"], "F.language", "F.type"],
            }},
        }],
        "relationships": [],
    }
    cleaned, errors, stripped = validate_compact_response(
        obj, prefix=prefix, user=user
    )
    assert errors == []
    assert cleaned["components"][0]["q"]["mechanism"]["e"] == [
        0, [0, 12], [0, "Symbol"], "F.language", "F.type",
    ]
    assert stripped == []


def test_redundant_file_index_path_symbol_citation_is_normalized():
    prompt = build_compact_component_prompt(
        Partition(0, ("api",), (), True), _facts(),
    )
    prefix, user = split_cached_prompt(prompt)
    obj = {
        "components": [{
            "i": "api", "label": "API",
            "purpose": {"t": "Accepts requests.", "e": [0]},
            "mechanism": {
                "t": "Defines the request reader.",
                "e": [[0, "src/api.py", "read_user"]],
            },
            "place": {"t": "At the request boundary.", "e": ["E0"]},
            "next": {"t": "Inspect the database.", "e": ["E0"]},
            "why_matters": {"t": "It owns request ingress.", "e": [0]},
            "data": {"t": "Request payloads.", "e": [0]},
            "criticality": "critical",
        }],
        "relationships": [],
    }

    cleaned, errors, stripped = validate_compact_response(
        obj, prefix=prefix, user=user
    )

    assert errors == []
    assert cleaned["components"][0]["mechanism"]["e"] == [
        ["src/api.py", "read_user"]
    ]
    assert any("redundant file index" in path for path in stripped)


def test_redundant_self_id_fact_reference_is_resolved():
    obj = {"components": [{
        "i": "api", "q": {"mechanism": {
            "t": "The analyzer records Python.",
            "e": [["api", "language"]],
        }},
    }], "relationships": []}

    normalized = normalize_compact_response(
        obj, facts=_facts(), component_ids=["api"]
    )

    assert normalized["components"]["api"]["contract"]["answers"][
        "mechanism"
    ]["evidence"] == [{
        "kind": "fact", "component": "api", "field": "language",
    }]


def test_second_evidence_alias_and_fact_component_are_preserved():
    prompt = build_compact_escalation_prompt(
        [{"target_kind": "component", "target_id": "api", "todo": ["mechanism"]}],
        terminal=False,
    )
    prefix, user = split_cached_prompt(prompt)
    obj = {"components": [{
        "i": "api", "q": {"mechanism": {
            "t": "Routes requests using Python.",
            "e": [{"kind": "fact", "component": "api", "field": "language"}],
            "e2": [0],
        }},
    }], "relationships": []}

    cleaned, errors, stripped = validate_compact_response(
        obj, prefix=prefix, user=user
    )

    assert errors == []
    evidence = cleaned["components"][0]["q"]["mechanism"]["e"]
    assert evidence == [
        {"kind": "fact", "component": "api", "field": "language"},
        0,
    ]
    assert not any(path.endswith(".component") for path in stripped)
