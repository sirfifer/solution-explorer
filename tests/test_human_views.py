"""Contracts for the bounded human-entry projection sidecars."""

from __future__ import annotations

import json
from copy import deepcopy

from analyzer.project import (
    build_orientation,
    build_security_view,
    build_support_view,
    project_monolith,
    project_split,
)
from analyzer.project import pipeline as pipe


def _architecture() -> dict:
    return {
        "name": "Transit Desk",
        "description": "Coordinates dispatch and rider status.",
        "generated_at": "2026-08-31T00:00:00Z",
        "analyzer_version": "2.0.0",
        "components": [{
            "id": "web",
            "name": "Rider web",
            "type": "web-client",
            "path": "apps/web",
            "docs": {"env_vars": ["PUBLIC_API_URL"]},
            "children": [],
        }, {
            "id": "api",
            "name": "Dispatch API",
            "type": "api-server",
            "path": "services/api",
            "docs": {"env_vars": ["DATABASE_URL", "STRIPE_API_KEY"]},
            "config_files": [{"path": "services/api/config.toml"}],
            "external_services": [{
                "name": "Stripe", "category": "payments", "protocol": "https",
                "port": 443, "authentication": "not_observable",
                "evidence": {"file": "services/api/payments.py", "line": 8},
            }],
            "children": [],
        }, {
            "id": "models",
            "name": "Trip models",
            "type": "module",
            "path": "services/api/models",
            "children": [],
        }],
        "relationships": [{
            "source": "web",
            "target": "api",
            "type": "http",
            "protocol": "https",
            "authentication": "bearer token",
        }, {
            "source": "api",
            "target": "models",
            "type": "data_access",
        }],
        "capabilities": [{
            "id": "cap:dispatch",
            "name": "Dispatch a trip",
            "kind": "api",
            "component_id": "api",
            "confidence": "certain",
            "evidence": [{"file": "services/api/routes.py", "line": 12}],
        }],
        "data_entities": [{
            "id": "entity:trip",
            "name": "Trip",
            "kind": "table",
            "component_id": "models",
            "fields": [{"name": "user_email"}, {"name": "pickup_location"}],
            "evidence": [{"file": "services/api/models.py", "line": 4}],
        }],
        "findings": [{
            "id": "finding:auth",
            "kind": "security",
            "summary": "Authentication policy needs verification",
            "verification_status": "unverified",
        }],
        "tours": [{"id": "tour:rider", "name": "Rider journey"}],
        "stats": {"total_components": 3, "total_relationships": 2},
    }


def test_human_view_builders_are_deterministic_and_evidence_honest():
    arch = _architecture()
    support_a = build_support_view(arch)
    support_b = build_support_view(arch)
    security_a = build_security_view(arch)
    security_b = build_security_view(arch)
    orientation_a = build_orientation(
        arch,
        coverage={"summary": {"parsed": 9, "failed": 1}},
        support=support_a,
        security=security_a,
    )
    orientation_b = build_orientation(
        arch,
        coverage={"summary": {"parsed": 9, "failed": 1}},
        support=support_b,
        security=security_b,
    )

    assert support_a == support_b
    assert security_a == security_b
    assert orientation_a == orientation_b
    assert support_a["attention"][0]["component_id"] == "api"
    assert "not incident probability" in support_a["method_caveat"]
    assert security_a["credential_configuration"][0]["key"] == "STRIPE_API_KEY"
    web_boundary = next(
        row for row in security_a["communication_boundaries"]
        if row["source"] == "web" and row["target"] == "api"
    )
    assert web_boundary["transport_state"] == "encrypted_observed"
    assert "not a security audit" in security_a["method_caveat"]
    assert security_a["findings"][0]["verification_status"] == "unverified"
    stripe = next(row for row in security_a["communication_boundaries"] if row["target"] == "external:Stripe")
    assert stripe["protocol"] == "https" and stripe["port"] == 443
    assert stripe["authentication"] == "not_observable"
    assert orientation_a["trust"]["source_coverage"]["percent"] == 90.0
    assert orientation_a["trust"]["findings"] == {
        "total": 1, "unverified": 1, "refuted": 0,
    }
    assert len(orientation_a["portrait"]["nodes"]) == 3


def test_security_view_detects_platform_local_keychain_mechanism():
    arch = deepcopy(_architecture())
    arch["components"][0]["files"] = [{
        "path": "apps/web/APIKeyManager.swift",
        "imports": ["Foundation", "Security"],
        "symbols": ["APIKeyManager", "saveToKeychain"],
        "module_doc": "Secure API key management using Keychain",
    }]
    security = build_security_view(arch)
    assert any(row["mechanism"] == "iOS Keychain" for row in security["mechanisms"])
    assert any(row["key"] == "API keys" for row in security["credential_configuration"])


def test_security_view_joins_top_level_file_facts_to_component_paths():
    arch = deepcopy(_architecture())
    arch["components"][0]["path"] = "apps/web"
    arch["components"][0]["files"] = ["apps/web/APIKeyManager.swift"]
    arch["files"] = [{
        "path": "apps/web/APIKeyManager.swift",
        "imports": ["Foundation", "Security"],
        "symbols": ["APIKeyManager", "saveToKeychain"],
        "module_doc": "Secure API key management using Keychain",
    }]
    security = build_security_view(arch)
    assert any(row["mechanism"] == "iOS Keychain" for row in security["mechanisms"])


def test_security_view_prefers_source_symbol_evidence_over_documentation():
    arch = deepcopy(_architecture())
    arch["components"][0]["files"] = [
        "PRE_BETA_AUDIT.md",
        "apps/web/PersistenceController.swift",
    ]
    arch["files"] = [{
        "path": "PRE_BETA_AUDIT.md",
        "imports": [],
        "symbols": [],
        "module_doc": "The application enables file protection.",
    }, {
        "path": "apps/web/PersistenceController.swift",
        "imports": ["CoreData"],
        "symbols": ["PersistenceController"],
        "module_doc": "Core Data stack",
    }]
    security = build_security_view(arch, signals_by_path={
        "apps/web/PersistenceController.swift": [{
            "kind": "symbol_reference",
            "value": {"name": "FileProtectionType"},
            "line": 101,
        }],
    })

    mechanism = next(
        row for row in security["mechanisms"]
        if row["mechanism"] == "iOS file protection"
    )
    assert mechanism["evidence"] == {
        "file": "apps/web/PersistenceController.swift",
        "line": 101,
        "signal": "FileProtectionType / NSPersistentStoreFileProtectionKey symbol reference",
    }


def test_refuted_relationships_do_not_become_security_facts_or_portrait_edges():
    arch = deepcopy(_architecture())
    arch["relationships"] = [{
        "source": "web",
        "target": "api",
        "type": "http",
        "protocol": "http",
        "authentication": "jwt",
        "verdict": {"status": "refuted", "reason": "test literal"},
    }]

    security = build_security_view(arch)
    assert not any(row.get("mechanism") == "jwt" for row in security["mechanisms"])
    assert not any(
        row["source"] == "web" and row["target"] == "api"
        for row in security["communication_boundaries"]
    )
    assert build_orientation(arch)["portrait"]["edges"] == []


def test_portrait_groups_from_structural_identity_and_folds_singleton_service_at_scale():
    arch = _architecture()
    arch["components"] = [{
        "id": f"core/{index}",
        "name": f"Core {index}",
        "path": f"src/core/{index}",
        "description": "Models editor behavior without persisting data.",
        "type": "module",
        "children": [],
    } for index in range(50)] + [{
        "id": "agent-host",
        "name": "Agent host",
        "path": "src/agentHost",
        "type": "service",
        "children": [],
    }]
    arch["relationships"] = []

    nodes = {row["id"]: row for row in build_orientation(arch)["portrait"]["nodes"]}
    assert "orientation:data" not in nodes
    assert "orientation:services" not in nodes
    assert nodes["orientation:core"]["member_count"] == 51


def test_deployment_provider_label_and_evidence_come_from_same_component():
    arch = _architecture()
    arch["components"][0]["external_services"] = [{
        "name": "GitHub",
        "evidence": {"component_id": "web", "file": "apps/web/github.ts"},
    }]
    arch["components"][1]["external_services"] = [{
        "name": "OpenAI",
        "evidence": {"component_id": "api", "file": "services/api/openai.py"},
    }, {
        "name": "Anthropic",
        "evidence": {"component_id": "api", "file": "services/api/anthropic.py"},
    }]

    posture = build_orientation(arch)["deployment_posture"]
    provider = next(row for row in posture["items"] if row["id"] == "direct-provider")
    assert provider["detail"] == "Anthropic, OpenAI"
    assert provider["evidence"]["component_id"] == "api"


def test_orientation_exposes_interpreted_deployment_posture():
    arch = _architecture()
    arch["components"][0]["docs"] = {
        "claude_md": (
            "This is a standalone mobile app. It communicates with the Transit "
                "server via HTTP REST APIs (port 8766). On-device models are supported. "
                "It has zero source-level dependencies on server code. "
                "The device connects directly to the provider."
        )
    }
    orientation = build_orientation(arch)
    posture = orientation["deployment_posture"]
    assert posture["status"] == "evidence_tiered"
    assert {row["posture"] for row in posture["items"]} == {
        "standalone", "optional", "on_device", "direct_to_provider",
    }
    assert all(row["statement_kind"] == "repository_claim" for row in posture["items"])
    assert all(row["evidence"]["source"].endswith("claude_md") for row in posture["items"])


def test_orientation_marks_stale_architecture_interpretation_in_trust():
    arch = _architecture()
    arch["ai_enhance"] = {
        "summary": "Old measured prose across 751 files.",
        "stale": True,
        "derived_from_commit": "old-commit",
    }
    orientation = build_orientation(arch)

    assert orientation["orientation"]["interpreted_statement"]["provenance"] == {
        "derived_from_commit": "old-commit",
        "stale": True,
    }
    assert orientation["trust"]["interpretation"]["status"] == "stale"


def test_orientation_prefers_credible_area_entry_targets():
    arch = _architecture()
    arch["components"] = [{
        "id": "root",
        "name": "Product",
        "type": "package",
        "children": [{
            "id": "server/importers/output",
            "name": "Generated output",
            "type": "web-client",
            "children": [],
        }, {
            "id": "ios-app",
            "name": "Product iOS",
            "type": "ios-client",
            "children": [{
                "id": "ios-app/home",
                "name": "Home",
                "type": "screen",
                "children": [],
            }],
        }, {
            "id": "server",
            "name": "Server",
            "type": "module",
            "children": [],
        }],
    }]
    orientation = build_orientation(arch)
    nodes = {row["id"]: row for row in orientation["portrait"]["nodes"]}

    assert nodes["orientation:experience"]["stable_targets"][0] == "ios-app"
    assert nodes["orientation:core"]["stable_targets"][0] == "server"


def test_empty_architecture_emits_explicit_empty_views():
    arch = {"name": "Empty", "components": [], "relationships": []}
    support = build_support_view(arch)
    security = build_security_view(arch)
    orientation = build_orientation(arch, support=support, security=security)

    assert support["counts"] == {
        "configuration": 0,
        "external_dependencies": 0,
        "entry_points": 0,
        "data_entities": 0,
        "attention_components": 0,
    }
    assert security["counts"]["mechanisms"] == 0
    assert security["not_observable"]
    assert orientation["portrait"]["nodes"] == []
    assert orientation["trust"]["source_coverage"]["status"] == "unavailable"
    availability = {row["id"]: row["available"] for row in orientation["question_routes"]}
    assert availability["support"] is False
    assert availability["security"] is False


def test_split_and_monolith_emit_sidecars_and_embed_sections(tmp_path):
    split = project_split(_architecture(), tmp_path / "split")
    for path in (split.orientation_path, split.support_path, split.security_path):
        assert path is not None and path.is_file()
    manifest = json.loads(split.manifest_path.read_text())
    assert manifest["orientation"] == json.loads(split.orientation_path.read_text())
    assert manifest["support"] == json.loads(split.support_path.read_text())
    assert manifest["security"] == json.loads(split.security_path.read_text())

    monolith_path = tmp_path / "mono" / "architecture.json"
    monolith = project_monolith(_architecture(), monolith_path)
    for path in (monolith.orientation_path, monolith.support_path, monolith.security_path):
        assert path is not None and path.is_file()
    document = json.loads(monolith_path.read_text())
    assert document["orientation"]["schema"] == "syscorpus.orientation/v1"
    assert document["support"]["schema"] == "syscorpus.support/v1"
    assert document["security"]["schema"] == "syscorpus.security/v1"


def test_failed_human_sidecar_is_an_honest_gap(tmp_path, monkeypatch):
    real_writer = pipe.write_human_view

    def fail_support(document, path, *, indent=2):
        if path.name == "support.json":
            raise RuntimeError("injected support sidecar fault")
        return real_writer(document, path, indent=indent)

    monkeypatch.setattr(pipe, "write_human_view", fail_support)
    result = project_split(_architecture(), tmp_path / "split")
    manifest = json.loads(result.manifest_path.read_text())

    assert result.support_path is None
    assert not (tmp_path / "split" / "support.json").exists()
    assert (tmp_path / "split" / "orientation.json").is_file()
    assert (tmp_path / "split" / "security.json").is_file()
    gap = next(
        row for row in manifest["gaps"]
        if row["producer"] == "project.support-json"
    )
    assert gap["reason"] == "RuntimeError: injected support sidecar fault"


def test_orientation_flow_route_names_a_lens_the_viewer_can_offer():
    """The Flow lens exists only for subjects with UI navigation data. For any
    other subject the flow question routes to the first tour on Structure,
    because naming a lens the viewer cannot offer lands the reader on
    Structure unexplained (GUI crawl 2026-09-02, overview.route_wrong_target)."""
    arch = _architecture()
    arch["tours"] = [{"id": "spine", "title": "The spine", "steps": []}]
    arch["relationships"] = [{"source": "web", "target": "api", "type": "http"}]
    orientation = build_orientation(arch)
    flow = next(row for row in orientation["question_routes"] if row["id"] == "flow")
    assert flow["target"] == {"lens": "structure", "tour_id": "spine"}
    assert flow["available"] is True
    # The id is the contract the viewer routes on and never changes; the label
    # is what a reader is promised, and without a Flow lens the honest promise
    # is about the code, not "the core experience" (UG-2, spec 3.3).
    assert flow["id"] == "flow"
    assert flow["label"] == "How does the code fit together?"

    no_tours = _architecture()
    no_tours["tours"] = []
    no_tours["relationships"] = [{"source": "web", "target": "api", "type": "http"}]
    flow = next(row for row in build_orientation(no_tours)["question_routes"] if row["id"] == "flow")
    assert flow["available"] is False

    with_screens = _architecture()
    with_screens["components"][0]["children"] = [{
        "id": "web/home", "name": "Home", "type": "screen", "path": "apps/web/home", "children": [],
    }]
    flow = next(row for row in build_orientation(with_screens)["question_routes"] if row["id"] == "flow")
    assert flow["target"]["lens"] == "flow"
    assert flow["available"] is True
    assert flow["label"] == "How does the core experience work?"


# ---------------------------------------------------------------------------
# The identity front door (UG-1, UG-2): what the system is, to a person
# ---------------------------------------------------------------------------

def _vscode_identity() -> dict:
    return {
        "primary": "desktop-app",
        "form_factors": [
            {"kind": "desktop-app", "label": "Desktop application",
             "platforms": ["macos", "windows", "linux"], "platforms_assumed": False,
             "how_met": "installed and opened on a computer", "component_id": "root",
             "evidence": [{"file": "product.json", "line": 30,
                           "marker": "darwinBundleIdentifier"}],
             "statement_kind": "observed_source_reference", "weight": 15204},
            {"kind": "plugin-host", "label": "Extensible by plug-ins", "platforms": [],
             "platforms_assumed": False, "how_met": "extended by plug-ins",
             "component_id": "extensions",
             "evidence": [{"file": "extensions/git/package.json", "marker": "contributes"}],
             "statement_kind": "observed_source_reference", "weight": 5145},
            {"kind": "web-app", "label": "Web application", "platforms": ["browser"],
             "platforms_assumed": False, "how_met": "opened in a web browser",
             "component_id": "src/vs/workbench",
             "evidence": [{"file": "src/vs/code/browser/workbench/workbench.html",
                           "marker": "html entry"}],
             "statement_kind": "observed_source_reference", "weight": 4281},
            {"kind": "cli", "label": "Command-line tool", "platforms": [],
             "platforms_assumed": False, "how_met": "run from a terminal",
             "component_id": "cli",
             "evidence": [{"file": "cli/Cargo.toml", "line": 12, "marker": "[[bin]]"}],
             "statement_kind": "observed_source_reference", "weight": 87},
        ],
        "authors_claim": {"text": "This repository is where we develop it.",
                          "source": "README.md", "line": 8,
                          "statement_kind": "repository_claim"},
        "languages": [{"language": "typescript", "share": 0.86},
                      {"language": "rust", "share": 0.11}],
        "external_services": [],
        "truncated": False,
    }


def test_identity_statement_reads_as_one_plain_sentence_about_vs_code():
    arch = _architecture()
    arch["name"] = "Visual Studio Code"
    arch["identity"] = _vscode_identity()
    orientation = build_orientation(arch)
    assert orientation["identity"]["statement"] == (
        "Visual Studio Code is a desktop application for macOS, Windows and Linux, "
        "that also runs in a web browser, is driven from a terminal by a "
        "command-line tool, and is extended by plug-ins. It is written mostly in "
        "TypeScript, with Rust."
    )
    assert orientation["identity"]["statement_kind"] == "deterministic_composition"
    assert orientation["identity"]["primary"] == "desktop-app"
    assert orientation["identity"]["authors_claim"]["statement_kind"] == "repository_claim"


def test_identity_statement_never_repeats_a_platform_the_noun_already_names():
    arch = _architecture()
    arch["name"] = "UnaMentis"
    arch["identity"] = {
        "primary": "ios-app",
        "form_factors": [
            {"kind": "ios-app", "label": "iOS app", "platforms": ["ios"],
             "platforms_assumed": False,
             "how_met": "installed from the App Store on a phone or tablet",
             "component_id": "unamentis",
             "evidence": [{"file": "UnaMentis/Info.plist", "marker": "component typed ios-client"}],
             "statement_kind": "observed_source_reference", "weight": 900},
            {"kind": "watch-app", "label": "Watch app", "platforms": ["watchos"],
             "platforms_assumed": False, "how_met": "installed on a watch",
             "component_id": "unamentis-watch-app",
             "evidence": [{"file": "UnaMentis Watch App/Info.plist",
                           "marker": "component typed watch-app"}],
             "statement_kind": "observed_source_reference", "weight": 40},
        ],
        "authors_claim": None,
        "languages": [{"language": "swift", "share": 0.95}],
        "external_services": [],
        "truncated": False,
    }
    orientation = build_orientation(arch)
    assert orientation["identity"]["statement"] == (
        "UnaMentis is an iOS app, that also has a watchOS app. "
        "It is written mostly in Swift."
    )


def test_identity_is_null_when_the_derive_pass_recorded_nothing():
    arch = _architecture()
    assert "identity" not in arch
    orientation = build_orientation(arch)
    assert orientation["identity"] is None
    # The rest of the document still builds.
    assert orientation["portrait"]["nodes"]
    assert any(row["id"] == "flow" for row in orientation["question_routes"])

    empty = _architecture()
    empty["identity"] = {"form_factors": [], "primary": None, "authors_claim": None,
                         "languages": [], "external_services": [], "truncated": False}
    built = build_orientation(empty)
    assert built["identity"]["statement"] is None
    assert built["identity"]["statement_kind"] is None


def test_identity_statement_names_the_external_services_it_was_given():
    arch = _architecture()
    arch["name"] = "Visual Studio Code"
    identity = _vscode_identity()
    identity["external_services"] = [
        {"name": "GitHub", "component_id": "extensions/copilot"},
        {"name": "OpenAI", "component_id": "extensions/copilot"},
    ]
    arch["identity"] = identity
    statement = build_orientation(arch)["identity"]["statement"]
    assert statement.endswith("It calls GitHub and OpenAI.")


def test_form_factor_order_matches_the_derive_pass():
    from analyzer.derive.identity import KIND_ORDER
    from analyzer.project.human_views import _FORM_FACTOR_ORDER

    assert _FORM_FACTOR_ORDER == KIND_ORDER


# ---------------------------------------------------------------------------
# Portrait v2: a typed parent speaks for its subtree
# ---------------------------------------------------------------------------

def _nested_workbench_architecture() -> dict:
    arch = _architecture()
    workbench_children = [{
        "id": f"src/vs/workbench/part{index}",
        "name": f"part{index}",
        "path": f"src/vs/workbench/part{index}",
        "type": "module",
        "files": [f"src/vs/workbench/part{index}/a.ts"],
        "children": [],
    } for index in range(20)]
    workbench_children[0]["children"] = [{
        "id": "src/vs/workbench/part0/home",
        "name": "Home",
        "path": "src/vs/workbench/part0/home",
        "type": "screen",
        "files": ["src/vs/workbench/part0/home/home.ts"],
        "children": [],
    }]
    arch["components"] = [{
        "id": "root",
        "name": "Code",
        "path": "",
        "type": "package",
        "files": ["package.json"],
        "children": [{
            "id": "src/vs/workbench",
            "name": "workbench",
            "path": "src/vs/workbench",
            "type": "web-client",
            "description": "Workbench: the desktop-editor UI shell. It also bridges extensions.",
            "ai_enhance": {
                "description": "Workbench: the desktop-editor UI shell. It also bridges extensions.",
            },
            "files": ["src/vs/workbench/workbench.ts"],
            "children": workbench_children,
        }, {
            "id": "src/vs/base",
            "name": "base",
            "path": "src/vs/base",
            "type": "module",
            "description": "Shared utilities.",
            "files": ["src/vs/base/base.ts"],
            "children": [],
        }],
    }]
    arch["relationships"] = []
    arch["tours"] = []
    return arch


def test_a_typed_user_interface_parent_carries_its_neutral_subtree():
    arch = _nested_workbench_architecture()
    orientation = build_orientation(arch)
    nodes = {row["id"]: row for row in orientation["portrait"]["nodes"]}
    # workbench plus its 20 neutral descendants plus the screen inside one of
    # them, and the root, which is typed package and so is neutral.
    assert nodes["orientation:experience"]["member_count"] == 22
    assert "orientation:core" in nodes
    assert nodes["orientation:core"]["member_count"] == 2  # root and src/vs/base


def test_a_neutral_sibling_outside_the_interface_stays_in_the_inner_workings():
    arch = _nested_workbench_architecture()
    orientation = build_orientation(arch)
    core = next(
        row for row in orientation["portrait"]["nodes"] if row["id"] == "orientation:core"
    )
    assert "src/vs/base" in core["stable_targets"]


def test_portrait_shares_account_for_every_mapped_file():
    arch = _nested_workbench_architecture()
    nodes = build_orientation(arch)["portrait"]["nodes"]
    assert abs(sum(row["share"] for row in nodes) - 1.0) <= 0.01
    for row in nodes:
        assert set(row["representative"]) >= {"id", "name", "description_kind"}


def test_portrait_representative_says_where_its_sentence_came_from():
    arch = _nested_workbench_architecture()
    nodes = {row["id"]: row for row in build_orientation(arch)["portrait"]["nodes"]}
    experience = nodes["orientation:experience"]["representative"]
    assert experience["id"] == "src/vs/workbench"
    assert experience["description"] == "Workbench: the desktop-editor UI shell."
    assert experience["description_kind"] == "interpreted"

    arch["components"][0]["children"][0].pop("ai_enhance")
    nodes = {row["id"]: row for row in build_orientation(arch)["portrait"]["nodes"]}
    assert nodes["orientation:experience"]["representative"]["description_kind"] == "deterministic"

    arch["components"][0]["children"][0].pop("description")
    nodes = {row["id"]: row for row in build_orientation(arch)["portrait"]["nodes"]}
    representative = nodes["orientation:experience"]["representative"]
    assert representative["description_kind"] == "unavailable"
    assert "description" not in representative


def test_portrait_labels_are_plain_language_and_ids_are_unchanged():
    arch = _nested_workbench_architecture()
    nodes = build_orientation(arch)["portrait"]["nodes"]
    labels = {row["id"]: row["label"] for row in nodes}
    assert labels["orientation:experience"] == "User interface"
    assert labels["orientation:core"] == "Inner workings"
    assert build_orientation(arch)["portrait"]["method"] == (
        "component type and path grouping, with nested components counted under "
        "their nearest typed parent"
    )


# ---------------------------------------------------------------------------
# The recommended path is the broadest one, and it says why
# ---------------------------------------------------------------------------

def _tour_ranking_architecture() -> dict:
    narrow = [{
        "id": f"narrow/{index}",
        "name": f"narrow{index}",
        "path": f"narrow/{index}",
        "type": "module",
        "files": [f"narrow/{index}/f{n}.ts" for n in range(5)],
        "children": [],
    } for index in range(2)]
    broad = [{
        "id": f"broad/{index}",
        "name": f"broad{index}",
        "path": f"broad/{index}",
        "type": "module",
        "files": [f"broad/{index}/f{n}.ts" for n in range(100)],
        "children": [],
    } for index in range(5)]
    return {
        "name": "Ranked",
        "components": narrow + broad,
        "relationships": [],
        "tours": [
            {"id": "narrow-tour", "steps": [
                {"evidence": {"file": "narrow/0/f0.ts"}},
                {"evidence": {"file": "narrow/1/f0.ts"}},
            ]},
            {"id": "broad-tour", "steps": [
                {"evidence": {"file": f"broad/{index}/f0.ts"}} for index in range(5)
            ]},
        ],
        "stats": {"total_components": 7, "total_relationships": 0},
    }


def test_the_recommended_path_is_the_broadest_tour_not_the_first_authored():
    orientation = build_orientation(_tour_ranking_architecture())
    default_path = orientation["orientation"]["default_path"]
    assert default_path["kind"] == "tour"
    assert default_path["id"] == "broad-tour"
    assert default_path["reason"] == (
        "broadest guided path: touches 5 components holding 98% of mapped files"
    )
    flow = next(row for row in orientation["question_routes"] if row["id"] == "flow")
    assert flow["target"]["tour_id"] == "broad-tour"


def test_with_no_tours_the_default_path_is_still_the_organization_question():
    arch = _tour_ranking_architecture()
    arch["tours"] = []
    default_path = build_orientation(arch)["orientation"]["default_path"]
    assert default_path == {"kind": "question", "id": "organization"}


def test_the_flow_question_is_renamed_when_there_is_no_flow_lens():
    arch = _architecture()
    arch["tours"] = [{"id": "spine", "title": "The spine", "steps": []}]
    arch["relationships"] = [{"source": "web", "target": "api", "type": "http"}]
    flow = next(
        row for row in build_orientation(arch)["question_routes"] if row["id"] == "flow"
    )
    assert flow["id"] == "flow"
    assert flow["label"] == "How does the code fit together?"

    with_screens = _architecture()
    with_screens["components"][0]["children"] = [{
        "id": "web/home", "name": "Home", "type": "screen", "path": "apps/web/home",
        "children": [],
    }]
    flow = next(
        row for row in build_orientation(with_screens)["question_routes"]
        if row["id"] == "flow"
    )
    assert flow["label"] == "How does the core experience work?"


def test_identity_and_portrait_additions_are_deterministic():
    arch = _nested_workbench_architecture()
    arch["identity"] = _vscode_identity()
    first = build_orientation(arch)
    second = build_orientation(arch)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_the_summary_is_the_statement_without_the_subject_clause():
    """The front door titles the page with the name, so the subtitle must not
    say it again. Both forms are composed here, from the same records, so they
    can never drift apart about the facts."""
    arch = _architecture()
    arch["name"] = "Visual Studio Code"
    arch["identity"] = _vscode_identity()
    identity = build_orientation(arch)["identity"]
    assert identity["summary"] == (
        "A desktop application for macOS, Windows and Linux, that also runs in a "
        "web browser, is driven from a terminal by a command-line tool, and is "
        "extended by plug-ins. It is written mostly in TypeScript, with Rust."
    )
    assert not identity["summary"].startswith("Visual Studio Code")
    # Everything after the opening clause is identical in both forms.
    assert identity["statement"].split(". ", 1)[1] == identity["summary"].split(". ", 1)[1]


def test_the_summary_takes_the_article_the_noun_needs():
    arch = _architecture()
    arch["name"] = "UnaMentis"
    arch["identity"] = {
        "primary": "ios-app",
        "form_factors": [
            {"kind": "ios-app", "label": "iOS app", "platforms": ["ios"],
             "platforms_assumed": False, "how_met": "installed from the App Store",
             "component_id": "unamentis",
             "evidence": [{"file": "UnaMentis/Info.plist", "marker": "component typed ios-client"}],
             "statement_kind": "observed_source_reference", "weight": 900},
        ],
        "authors_claim": None,
        "languages": [{"language": "swift", "share": 0.95}],
        "external_services": [],
        "truncated": False,
    }
    assert build_orientation(arch)["identity"]["summary"] == (
        "An iOS app. It is written mostly in Swift."
    )


def test_there_is_no_summary_when_there_is_no_statement():
    arch = _architecture()
    arch["identity"] = {"form_factors": [], "primary": None, "authors_claim": None,
                        "languages": [], "external_services": [], "truncated": False}
    identity = build_orientation(arch)["identity"]
    assert identity["statement"] is None
    assert identity["summary"] is None
