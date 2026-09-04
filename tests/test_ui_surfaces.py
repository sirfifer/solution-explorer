"""Trust-boundary tests for UI capture packages."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from analyzer.project.ui_surfaces import (
    UISurfaceValidationError,
    load_and_validate_ui_surfaces,
    validate_ui_surface_evidence,
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _package(tmp_path: Path, *, match: str = "exact", runtime_commit: str = "abc123") -> Path:
    package = tmp_path / "capture-package"
    asset = package / "ui-surfaces" / "main.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(PNG_1X1)
    document = {
        "schema": "syscorpus.ui-surfaces/v1",
        "subject": {"repository": "https://example.test/repo", "commit": "abc123"},
        "clients": [{
            "id": "desktop", "label": "Desktop", "kind": "desktop-app",
            "platforms": ["macos"], "primary": True, "coverage": "captured",
        }],
        "screens": [{
            "id": "desktop:main", "client_id": "desktop", "label": "Main",
            "role": "primary",
            "image": {
                "path": "ui-surfaces/main.png",
                "sha256": hashlib.sha256(PNG_1X1).hexdigest(),
                "width": 1, "height": 1,
            },
            "capture": {
                "captured_at": "2026-09-04T00:00:00Z", "method": "playwright-electron",
                "runtime_name": "Fixture", "runtime_version": "1", "runtime_commit": runtime_commit,
                "source_match": match, "sanitized": True,
            },
            "hotspots": [{
                "id": "editor", "label": "Editor", "kind": "region",
                "rect": {"x": 0, "y": 0, "width": 1, "height": 1},
                "evidence": {"component_id": "workbench", "file": "src/editor.ts", "line": 7},
                "action": {"kind": "open_source"},
            }],
        }],
    }
    (package / "ui-surfaces.json").write_text(json.dumps(document), encoding="utf-8")
    return package


def test_valid_capture_checks_asset_identity_and_projection_evidence(tmp_path: Path) -> None:
    package = _package(tmp_path)
    document = load_and_validate_ui_surfaces(
        package,
        expected_repository="https://example.test/repo",
        expected_commit="abc123",
    )
    validate_ui_surface_evidence(document, {
        "components": [{"id": "workbench", "files": ["src/editor.ts"], "children": []}],
    })


def test_representative_capture_may_name_a_different_runtime_commit(tmp_path: Path) -> None:
    package = _package(tmp_path, match="representative", runtime_commit="older")
    assert load_and_validate_ui_surfaces(package)["screens"][0]["capture"]["source_match"] == "representative"


def test_exact_capture_cannot_name_a_different_runtime_commit(tmp_path: Path) -> None:
    package = _package(tmp_path, match="exact", runtime_commit="older")
    with pytest.raises(UISurfaceValidationError, match="exact capture from a different commit"):
        load_and_validate_ui_surfaces(package)


def test_capture_rejects_changed_image_bytes(tmp_path: Path) -> None:
    package = _package(tmp_path)
    (package / "ui-surfaces" / "main.png").write_bytes(PNG_1X1 + b"changed")
    with pytest.raises(UISurfaceValidationError, match="sha256"):
        load_and_validate_ui_surfaces(package)


def test_hotspot_must_target_a_file_owned_by_its_component(tmp_path: Path) -> None:
    document = load_and_validate_ui_surfaces(_package(tmp_path))
    with pytest.raises(UISurfaceValidationError, match="not owned"):
        validate_ui_surface_evidence(document, {
            "components": [{"id": "workbench", "files": ["src/other.ts"], "children": []}],
        })
