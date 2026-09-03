"""Regression coverage for canonical-projection viewer assembly."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_assembler():
    script = REPO_ROOT / "scripts" / "assemble-serve.py"
    spec = importlib.util.spec_from_file_location("assemble_serve", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_assembly_links_canonical_data_and_derives_missing_human_views(
    tmp_path: Path,
) -> None:
    assembler = _load_assembler()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("viewer", encoding="utf-8")
    (dist / "architecture").mkdir()
    (dist / "architecture" / "manifest.json").write_text(
        '{"name":"stale"}', encoding="utf-8"
    )
    for name in ("architecture.json", "ai.json", "llms.txt"):
        (dist / name).write_text("stale", encoding="utf-8")

    projection = tmp_path / "canonical" / "architecture"
    (projection / "data").mkdir(parents=True)
    manifest = {
        "name": "unamentis-ios",
        "repository": "https://github.com/UnaMentis/unamentis-ios",
        "description": "Canonical fixture",
        "generated_at": "2026-08-31T05:50:03.252151+00:00",
        "analyzer_version": "1.2.0",
        "components": [
            {
                "id": "app",
                "name": "App",
                "path": "App",
                "type": "ios-client",
                "children": [],
                "docs": {"env_vars": ["API_TOKEN"]},
                "config_files": [],
                "external_services": [{"name": "OpenAI"}],
            }
        ],
        "relationships": [
            {"source": "app", "target": "service", "type": "http", "protocol": "https"}
        ],
        "tours": [{"id": "tour:one"}],
        "stats": {"total_relationships": 1},
        "component_detail_index": {"app": "data/detail-app.json"},
    }
    manifest_path = projection / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    (projection / "data" / "detail-app.json").write_text("{}", encoding="utf-8")
    canonical_hash = _sha256(manifest_path)

    assembler.DIST = dist
    assembler.SERVE_ROOT = tmp_path / "serve"
    assembler.DERIVED_ROOT = tmp_path / "derived"

    serve = assembler.assemble("unamentis-ios", projection, build=False)
    served_projection = serve / "architecture"
    overlay = assembler.DERIVED_ROOT / "unamentis-ios" / "architecture"

    assert served_projection.is_symlink()
    assert served_projection.resolve() == overlay.resolve()
    assert (overlay / "manifest.json").is_symlink()
    assert (overlay / "manifest.json").resolve() == manifest_path.resolve()
    assert _sha256(served_projection / "manifest.json") == canonical_hash
    assert _sha256(manifest_path) == canonical_hash
    assert not (projection / "orientation.json").exists()
    assert not (projection / "support.json").exists()
    assert not (projection / "security.json").exists()

    sidecar_hashes = {}
    for name in ("orientation.json", "support.json", "security.json"):
        sidecar = served_projection / name
        assert sidecar.is_file()
        sidecar_hashes[name] = _sha256(sidecar)

    assert not (serve / "architecture.json").exists()
    assert not (serve / "ai.json").exists()
    assert not (serve / "llms.txt").exists()
    assert json.loads((served_projection / "manifest.json").read_text())["repository"] == manifest["repository"]

    assembler.assemble("unamentis-ios", projection, build=False)
    assert {
        name: _sha256(assembler.SERVE_ROOT / "unamentis-ios" / "architecture" / name)
        for name in sidecar_hashes
    } == sidecar_hashes
    assert _sha256(manifest_path) == canonical_hash


def test_assembly_applies_review_correction_only_to_derived_overlay(
    tmp_path: Path,
) -> None:
    assembler = _load_assembler()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("viewer", encoding="utf-8")

    projection = tmp_path / "canonical" / "architecture"
    projection.mkdir(parents=True)
    manifest = {
        "name": "vscode",
        "repository": "https://github.com/microsoft/vscode",
        "description": "Canonical fixture",
        "ai_enhance": {"summary": "This is a fork of code-oss-dev."},
        "components": [],
        "relationships": [],
        "tours": [{
            "id": "tour:one",
            "provenance": {"derived_from_commit": "abc123"},
            "steps": [],
        }],
        "stats": {"total_relationships": 0},
        "component_detail_index": {},
    }
    manifest_path = projection / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    canonical_hash = _sha256(manifest_path)
    corrections = tmp_path / "vscode-corrections.json"
    corrections.write_text(json.dumps({
        "schema": "syscorpus.review-corrections/v1",
        "subject": {
            "repository": "https://github.com/microsoft/vscode",
            "commit": "abc123",
        },
        "manifest_edits": [{
            "field_path": "ai_enhance.summary",
            "expected": "This is a fork of code-oss-dev.",
            "replacement": "This is the Visual Studio Code source snapshot.",
        }],
    }), encoding="utf-8")

    assembler.DIST = dist
    assembler.SERVE_ROOT = tmp_path / "serve"
    assembler.DERIVED_ROOT = tmp_path / "derived"

    serve = assembler.assemble(
        "vscode", projection, build=False, corrections=corrections
    )
    overlay = assembler.DERIVED_ROOT / "vscode" / "architecture"

    assert (serve / "architecture").resolve() == overlay.resolve()
    assert not (overlay / "manifest.json").is_symlink()
    assert json.loads((overlay / "manifest.json").read_text())["ai_enhance"]["summary"] == (
        "This is the Visual Studio Code source snapshot."
    )
    assert "Visual Studio Code source snapshot" in json.loads(
        (overlay / "orientation.json").read_text()
    )["orientation"]["interpreted_statement"]["text"]
    assert _sha256(manifest_path) == canonical_hash


def test_assembly_can_scrub_activity_and_ship_publication_obligations(tmp_path: Path) -> None:
    assembler = _load_assembler()
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("viewer", encoding="utf-8")
    projection = tmp_path / "canonical" / "architecture"
    projection.mkdir(parents=True)
    (projection / "manifest.json").write_text(json.dumps({
        "name": "subject", "components": [], "relationships": [],
        "component_detail_index": {},
    }))
    activity = {
        "files": {"a.py": {"authors": [{"author_key": "Person@Example.com", "author_name": "person@example.com"}]}},
        "components": [{"authors": [{"author_key": "person@example.com", "author_name": "Person"}]}],
    }
    (projection / "activity.json").write_text(json.dumps(activity))
    publication = tmp_path / "publication.json"
    publication.write_text('{"publication_version":1}')
    subject = tmp_path / "subject"
    subject.mkdir()
    (subject / "LICENSE.txt").write_text("license")
    (subject / "ThirdPartyNotices.txt").write_text("notices")

    assembler.DIST = dist
    assembler.SERVE_ROOT = tmp_path / "serve"
    assembler.DERIVED_ROOT = tmp_path / "derived"
    serve = assembler.assemble(
        "subject", projection, build=False, publication=publication,
        upstream_source=subject, scrub_activity=True,
    )
    served = serve / "architecture"
    scrubbed = json.loads((served / "activity.json").read_text())
    file_key = scrubbed["files"]["a.py"]["authors"][0]["author_key"]
    component_key = scrubbed["components"][0]["authors"][0]["author_key"]
    assert file_key == component_key
    assert file_key.startswith("contributor-") and "@" not in file_key
    assert scrubbed["files"]["a.py"]["authors"][0]["author_name"] == file_key
    assert scrubbed["components"][0]["authors"][0]["author_name"] == "Person"
    assert (served / "publication.json").read_bytes() == publication.read_bytes()
    assert (served / "UPSTREAM-LICENSE.txt").read_text() == "license"
    assert (served / "ThirdPartyNotices.txt").read_text() == "notices"
