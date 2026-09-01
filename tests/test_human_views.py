"""Contracts for the bounded human-entry projection sidecars."""

from __future__ import annotations

import json

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
            "external_services": [{"name": "Stripe", "category": "payments"}],
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
    assert orientation_a["trust"]["source_coverage"]["percent"] == 90.0
    assert len(orientation_a["portrait"]["nodes"]) == 3


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
