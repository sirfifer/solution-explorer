from __future__ import annotations

import hashlib
import json

import pytest

from analyzer.project.review import apply_review_corrections


def _write_fixture(tmp_path):
    projection = tmp_path / "architecture"
    projection.mkdir()
    manifest = {
        "repository": "https://example.com/acme/app",
        "components": [{
            "id": "audio",
            "children": [],
            "ai_enhance": {"help_text": "Old help"},
        }],
        "tours": [{
            "id": "walk",
            "title": "Old title",
            "description": "",
            "provenance": {"derived_from_commit": "abc123"},
            "steps": [{"title": "A step", "narration": "Old narration"}],
        }],
    }
    (projection / "manifest.json").write_text(json.dumps(manifest))
    corrections = tmp_path / "review.json"
    corrections.write_text(json.dumps({
        "schema": "syscorpus.review-corrections/v1",
        "subject": {"repository": "https://example.com/acme/app", "commit": "abc123"},
        "manifest_edits": [{
            "field_path": "ai_enhance.summary",
            "expected": "Old summary",
            "replacement": "Reviewed summary",
        }],
        "component_edits": [{
            "component_id": "audio",
            "field_path": "ai_enhance.help_text",
            "expected_sha256": hashlib.sha256(b"Old help").hexdigest(),
            "replacement": "Reviewed help",
        }],
        "tour_edits": [{
            "tour_id": "walk", "step_title": "A step", "field": "narration",
            "expected": "Old narration", "replacement": "Reviewed narration",
        }],
    }))
    manifest["ai_enhance"] = {"summary": "Old summary"}
    (projection / "manifest.json").write_text(json.dumps(manifest))
    return projection, corrections


def test_review_correction_is_exact_auditable_and_commit_bound(tmp_path):
    projection, corrections = _write_fixture(tmp_path)
    result = apply_review_corrections(projection, corrections)
    manifest = json.loads((projection / "manifest.json").read_text())
    assert manifest["ai_enhance"]["summary"] == "Reviewed summary"
    assert manifest["tours"][0]["steps"][0]["narration"] == "Reviewed narration"
    assert manifest["components"][0]["ai_enhance"]["help_text"] == "Reviewed help"
    assert result["commit"] == "abc123"
    assert result["applied"] == [
        "manifest.ai_enhance.summary",
        "tour:walk/step:A step.narration",
        "component:audio.ai_enhance.help_text",
    ]


def test_stale_review_correction_fails_loudly(tmp_path):
    projection, corrections = _write_fixture(tmp_path)
    apply_review_corrections(projection, corrections)
    with pytest.raises(ValueError, match="stale"):
        apply_review_corrections(projection, corrections)
