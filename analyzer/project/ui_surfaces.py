"""Validation and attachment helpers for first-class UI surface captures.

UI captures are evidence attached to a projection, not analyzer output.  The
package is deliberately self-contained and content-addressed so assembly can
verify it without mutating the canonical projection or enrichment store.
"""

from __future__ import annotations

import hashlib
import json
import struct
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

UI_SURFACES_FILENAME = "ui-surfaces.json"
UI_SURFACES_SCHEMA = "syscorpus.ui-surfaces/v1"


class UISurfaceValidationError(ValueError):
    """Raised when a UI surface package cannot be trusted."""


def _fail(message: str) -> None:
    raise UISurfaceValidationError(message)


def _safe_asset(package: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        _fail("screen image.path must be a non-empty string")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        _fail(f"screen image path escapes its package: {value!r}")
    if not relative.parts or relative.parts[0] != "ui-surfaces":
        _fail("screen images must live under the reserved ui-surfaces/ directory")
    target = (package / Path(*relative.parts)).resolve()
    try:
        target.relative_to(package.resolve())
    except ValueError:
        _fail(f"screen image path escapes its package: {value!r}")
    if not target.is_file():
        _fail(f"screen image does not exist: {value}")
    return target


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        _fail(f"only verified PNG captures are supported: {path.name}")
    return struct.unpack(">II", header[16:24])


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label} must be a non-empty string")
    return value


def load_and_validate_ui_surfaces(
    package: Path,
    *,
    expected_repository: str | None = None,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    """Load a capture package and verify identity, assets, and hotspot geometry."""
    package = package.resolve()
    manifest_path = package / UI_SURFACES_FILENAME
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"cannot read {manifest_path}: {exc}")
    if not isinstance(document, dict) or document.get("schema") != UI_SURFACES_SCHEMA:
        _fail(f"{UI_SURFACES_FILENAME} must use {UI_SURFACES_SCHEMA}")

    subject = document.get("subject")
    if not isinstance(subject, dict):
        _fail("subject must be an object")
    repository = _require_string(subject.get("repository"), "subject.repository")
    commit = _require_string(subject.get("commit"), "subject.commit")
    if expected_repository and repository.rstrip("/") != expected_repository.rstrip("/"):
        _fail(f"capture subject repository {repository!r} does not match {expected_repository!r}")
    if expected_commit and commit != expected_commit:
        _fail(f"capture subject commit {commit!r} does not match {expected_commit!r}")

    clients = document.get("clients")
    screens = document.get("screens")
    if not isinstance(clients, list) or not clients:
        _fail("clients must be a non-empty array")
    if not isinstance(screens, list) or not screens:
        _fail("screens must be a non-empty array")
    client_ids: set[str] = set()
    primary_clients = 0
    primary_client_id: str | None = None
    client_coverage: dict[str, str] = {}
    for client in clients:
        if not isinstance(client, dict):
            _fail("every client must be an object")
        client_id = _require_string(client.get("id"), "client.id")
        if client_id in client_ids:
            _fail(f"duplicate client id: {client_id}")
        client_ids.add(client_id)
        _require_string(client.get("label"), f"client {client_id}.label")
        _require_string(client.get("kind"), f"client {client_id}.kind")
        coverage = client.get("coverage")
        if coverage not in {"captured", "shared", "missing", "unavailable"}:
            _fail(f"client {client_id}.coverage is invalid")
        client_coverage[client_id] = coverage
        platforms = client.get("platforms")
        if not isinstance(platforms, list) or any(not isinstance(platform, str) or not platform for platform in platforms):
            _fail(f"client {client_id}.platforms must be an array of strings")
        if not isinstance(client.get("primary"), bool):
            _fail(f"client {client_id}.primary must be a boolean")
        if client.get("primary") is True:
            primary_clients += 1
            primary_client_id = client_id
    if primary_clients != 1:
        _fail("exactly one client must be primary")

    screen_ids: set[str] = set()
    screen_client_ids: set[str] = set()
    primary_screen_counts: dict[str, int] = {}
    for screen in screens:
        if not isinstance(screen, dict):
            _fail("every screen must be an object")
        screen_id = _require_string(screen.get("id"), "screen.id")
        if screen_id in screen_ids:
            _fail(f"duplicate screen id: {screen_id}")
        screen_ids.add(screen_id)
        if screen.get("client_id") not in client_ids:
            _fail(f"screen {screen_id} references an unknown client")
        client_id = screen["client_id"]
        screen_client_ids.add(client_id)
        if client_coverage[client_id] not in {"captured", "shared"}:
            _fail(f"screen {screen_id} belongs to a client marked {client_coverage[client_id]}")
        _require_string(screen.get("label"), f"screen {screen_id}.label")
        if screen.get("role") not in {"primary", "secondary"}:
            _fail(f"screen {screen_id}.role is invalid")
        if screen.get("role") == "primary":
            primary_screen_counts[client_id] = primary_screen_counts.get(client_id, 0) + 1
        image = screen.get("image")
        capture = screen.get("capture")
        if not isinstance(image, dict) or not isinstance(capture, dict):
            _fail(f"screen {screen_id} requires image and capture objects")
        asset = _safe_asset(package, image.get("path"))
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()
        if image.get("sha256") != digest:
            _fail(f"screen {screen_id} image sha256 does not match {asset.name}")
        width, height = _png_size(asset)
        if image.get("width") != width or image.get("height") != height:
            _fail(f"screen {screen_id} image dimensions do not match {asset.name}")
        match = capture.get("source_match")
        if match not in {"exact", "representative"}:
            _fail(f"screen {screen_id} capture.source_match is invalid")
        runtime_commit = _require_string(capture.get("runtime_commit"), f"screen {screen_id} capture.runtime_commit")
        _require_string(capture.get("method"), f"screen {screen_id} capture.method")
        _require_string(capture.get("runtime_name"), f"screen {screen_id} capture.runtime_name")
        _require_string(capture.get("runtime_version"), f"screen {screen_id} capture.runtime_version")
        captured_at = _require_string(capture.get("captured_at"), f"screen {screen_id} capture.captured_at")
        try:
            datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError:
            _fail(f"screen {screen_id} capture.captured_at is not an ISO timestamp")
        if match == "exact" and runtime_commit != commit:
            _fail(f"screen {screen_id} claims an exact capture from a different commit")
        if capture.get("sanitized") is not True:
            _fail(f"screen {screen_id} must explicitly record sanitized: true")

        hotspot_ids: set[str] = set()
        hotspots = screen.get("hotspots")
        if not isinstance(hotspots, list) or not hotspots:
            _fail(f"screen {screen_id} must have at least one hotspot")
        for hotspot in hotspots:
            if not isinstance(hotspot, dict):
                _fail(f"screen {screen_id} has a non-object hotspot")
            hotspot_id = _require_string(hotspot.get("id"), "hotspot.id")
            if hotspot_id in hotspot_ids:
                _fail(f"duplicate hotspot id in {screen_id}: {hotspot_id}")
            hotspot_ids.add(hotspot_id)
            _require_string(hotspot.get("label"), f"hotspot {hotspot_id}.label")
            _require_string(hotspot.get("kind"), f"hotspot {hotspot_id}.kind")
            rect = hotspot.get("rect")
            if not isinstance(rect, dict):
                _fail(f"hotspot {hotspot_id}.rect must be an object")
            values = [rect.get(key) for key in ("x", "y", "width", "height")]
            if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in values):
                _fail(f"hotspot {hotspot_id}.rect must contain numeric normalized coordinates")
            x, y, rect_width, rect_height = values
            if x < 0 or y < 0 or rect_width <= 0 or rect_height <= 0 or x + rect_width > 1.000001 or y + rect_height > 1.000001:
                _fail(f"hotspot {hotspot_id}.rect falls outside the normalized image")
            evidence = hotspot.get("evidence")
            if not isinstance(evidence, dict):
                _fail(f"hotspot {hotspot_id}.evidence must be an object")
            _require_string(evidence.get("component_id"), f"hotspot {hotspot_id}.evidence.component_id")
            file_name = _require_string(evidence.get("file"), f"hotspot {hotspot_id}.evidence.file")
            file_path = PurePosixPath(file_name)
            if file_path.is_absolute() or ".." in file_path.parts:
                _fail(f"hotspot {hotspot_id} evidence file is not repository-relative")
            line = evidence.get("line")
            if not isinstance(line, int) or isinstance(line, bool) or line < 1:
                _fail(f"hotspot {hotspot_id}.evidence.line must be positive")
            action = hotspot.get("action")
            if not isinstance(action, dict) or action.get("kind") != "open_source":
                _fail(f"hotspot {hotspot_id}.action must be open_source")
    if primary_client_id not in screen_client_ids:
        _fail("the primary client must have at least one captured screen")
    for client_id in screen_client_ids:
        if primary_screen_counts.get(client_id) != 1:
            _fail(f"client {client_id} must have exactly one primary screen")
    return document


def validate_ui_surface_evidence(document: dict[str, Any], architecture: dict[str, Any]) -> None:
    """Ensure every hotspot hands off to a component/file in this projection."""
    components: dict[str, dict[str, Any]] = {}

    def visit(rows: list[dict[str, Any]]) -> None:
        for component in rows:
            components[component.get("id", "")] = component
            visit(component.get("children") or [])

    visit(architecture.get("components") or [])
    for screen in document["screens"]:
        for hotspot in screen["hotspots"]:
            evidence = hotspot["evidence"]
            component = components.get(evidence["component_id"])
            if component is None:
                _fail(f"hotspot {hotspot['id']} references unknown component {evidence['component_id']}")
            files = component.get("files") or []
            owned_paths = {item if isinstance(item, str) else item.get("path") for item in files}
            if evidence["file"] not in owned_paths:
                _fail(f"hotspot {hotspot['id']} file is not owned by component {evidence['component_id']}")
