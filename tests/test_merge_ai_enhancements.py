"""Regression tests for scripts/merge-ai-enhancements.py (F-CRIT-6).

Covers the crash-and-write-then-fail behavior: the diagnostic used to
reference an unassigned ``baseline_index`` (UnboundLocalError) in exactly the
scenario it was meant to diagnose, and the target file was written before the
crash, corrupting curated AI work. These tests exercise the real script via
subprocess so exit codes and the on-disk target are asserted end to end.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MERGE_SCRIPT = REPO_ROOT / "scripts" / "merge-ai-enhancements.py"


def _run_merge(baseline_path, target_path):
    return subprocess.run(
        [
            sys.executable,
            str(MERGE_SCRIPT),
            "--baseline",
            str(baseline_path),
            "--target",
            str(target_path),
        ],
        capture_output=True,
        text=True,
    )


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _component(comp_id, *, ai=False, children=None):
    comp = {"id": comp_id, "name": comp_id, "children": children or []}
    if ai:
        comp["ai_enhance"] = {"description": f"AI note for {comp_id}"}
    return comp


def test_normal_merge_preserves_data(tmp_path):
    """Matching component IDs get their ai_enhance restored; exit 0."""
    baseline = {
        "ai_enhance": {"summary": "arch-level AI"},
        "components": [_component("app/core", ai=True), _component("app/api", ai=True)],
        "relationships": [],
    }
    target = {
        "components": [_component("app/core"), _component("app/api")],
        "relationships": [],
    }
    baseline_path = tmp_path / "baseline.json"
    target_path = tmp_path / "target.json"
    _write(baseline_path, baseline)
    _write(target_path, target)

    result = _run_merge(baseline_path, target_path)

    assert result.returncode == 0, result.stderr
    merged = json.loads(target_path.read_text())
    ids_to_ai = {c["id"]: c.get("ai_enhance") for c in merged["components"]}
    assert ids_to_ai["app/core"] == {"description": "AI note for app/core"}
    assert ids_to_ai["app/api"] == {"description": "AI note for app/api"}
    # Architecture-level AI carried too.
    assert merged["ai_enhance"] == {"summary": "arch-level AI"}


def test_drifted_ids_exit_nonzero_and_leave_target_unchanged(tmp_path):
    """The audit reproduction: AI-enhanced baseline, fully drifted target IDs.

    Must exit nonzero with a readable diagnostic and NOT touch the target file.
    Pre-fix this raised UnboundLocalError (because baseline_index was never
    assigned when the baseline had architecture-level ai_enhance) AND had
    already overwritten the target before crashing.
    """
    baseline = {
        # Architecture-level ai_enhance is what /ai-assist always writes; this
        # is precisely what triggered the pre-fix UnboundLocalError.
        "ai_enhance": {"summary": "arch-level AI"},
        "components": [
            _component("repo:unamentis/core", ai=True),
            _component("repo:unamentis/api", ai=True),
        ],
        "relationships": [],
    }
    # Target IDs fully drifted (repo prefix removed), so nothing matches.
    target = {
        "components": [_component("core"), _component("api")],
        "relationships": [],
    }
    baseline_path = tmp_path / "baseline.json"
    target_path = tmp_path / "target.json"
    _write(baseline_path, baseline)
    _write(target_path, target)

    target_bytes_before = target_path.read_bytes()

    result = _run_merge(baseline_path, target_path)

    # Exit nonzero.
    assert result.returncode != 0
    # Readable diagnostic, not a Python traceback.
    assert "Traceback" not in result.stderr
    assert "UnboundLocalError" not in result.stderr
    assert "NONE matched" in result.stderr
    # Target file left byte-for-byte unchanged.
    assert target_path.read_bytes() == target_bytes_before


def test_non_enhanced_baseline_passes_through(tmp_path):
    """A baseline with no ai_enhance anywhere exits 0 and leaves target alone."""
    baseline = {
        "components": [_component("app/core"), _component("app/api")],
        "relationships": [],
    }
    target = {
        "components": [_component("app/core"), _component("app/api")],
        "relationships": [],
    }
    baseline_path = tmp_path / "baseline.json"
    target_path = tmp_path / "target.json"
    _write(baseline_path, baseline)
    _write(target_path, target)

    target_bytes_before = target_path.read_bytes()

    result = _run_merge(baseline_path, target_path)

    assert result.returncode == 0, result.stderr
    assert "nothing to merge" in result.stdout.lower()
    assert target_path.read_bytes() == target_bytes_before


def test_partial_match_still_writes_and_succeeds(tmp_path):
    """When at least one component matches, the merge writes and exits 0."""
    baseline = {
        "ai_enhance": {"summary": "arch-level AI"},
        "components": [_component("app/core", ai=True), _component("app/api", ai=True)],
        "relationships": [],
    }
    # Only app/core survives; app/api was renamed. preserved > 0, so no drift error.
    target = {
        "components": [_component("app/core"), _component("app/api-v2")],
        "relationships": [],
    }
    baseline_path = tmp_path / "baseline.json"
    target_path = tmp_path / "target.json"
    _write(baseline_path, baseline)
    _write(target_path, target)

    result = _run_merge(baseline_path, target_path)

    assert result.returncode == 0, result.stderr
    merged = json.loads(target_path.read_text())
    ids_to_ai = {c["id"]: c.get("ai_enhance") for c in merged["components"]}
    assert ids_to_ai["app/core"] == {"description": "AI note for app/core"}
    assert ids_to_ai.get("app/api-v2") is None
