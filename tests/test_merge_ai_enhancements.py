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


def _run_merge(baseline_path, target_path, *extra_args):
    return subprocess.run(
        [
            sys.executable,
            str(MERGE_SCRIPT),
            "--baseline",
            str(baseline_path),
            "--target",
            str(target_path),
            *extra_args,
        ],
        capture_output=True,
        text=True,
    )


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _component(comp_id, *, ai=False, children=None, name=None, ctype=None, path=None):
    comp = {"id": comp_id, "name": name if name is not None else comp_id}
    if ctype is not None:
        comp["type"] = ctype
    if path is not None:
        comp["path"] = path
    comp["children"] = children or []
    if ai:
        comp["ai_enhance"] = {"description": f"AI note for {comp_id}"}
    return comp


def _count_ai(components):
    """Count components (recursively) that carry ai_enhance."""
    n = 0
    for c in components:
        if "ai_enhance" in c:
            n += 1
        n += _count_ai(c.get("children", []))
    return n


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


# ---------------------------------------------------------------------------
# Drift-tolerant matching (P3-3)
# ---------------------------------------------------------------------------


def _unamentis_like_ids():
    """A realistic spread of UnaMentis component IDs (unprefixed baseline form).

    Modeled on the production failure of 2026-07-11: the baseline had 251
    AI-enhanced components with unprefixed IDs such as ``curriculum`` and
    ``curriculum/examples/knowledge-bowl``.
    """
    tops = [
        "curriculum",
        "curriculum/examples",
        "curriculum/examples/knowledge-bowl",
        "curriculum/examples/sat-prep",
        "curriculum/importers",
        "curriculum/spec",
        "server",
        "server/api",
        "server/db",
        "Shared",
        "Shared/Models",
        "UnaMentis",
        "UnaMentis/Views",
        "models",
        "demo",
        "scripts",
    ]
    ids = list(tops)
    # Pad out to 251 with deterministic nested IDs across a few roots.
    roots = ["curriculum", "server", "Shared", "UnaMentis", "models"]
    i = 0
    while len(ids) < 251:
        root = roots[i % len(roots)]
        ids.append(f"{root}/gen/mod{i:03d}")
        i += 1
    assert len(ids) == 251
    return ids


def test_repo_prefix_drift_preserves_all(tmp_path):
    """The production drift: unprefixed baseline vs repo-prefixed target.

    Baseline IDs like ``curriculum``; target IDs like ``unamentis/curriculum``
    plus a new ``repo:unamentis`` grouping node with no baseline counterpart.
    All 251 enhancements must survive, entirely via the prefix/suffix strategy.
    """
    ids = _unamentis_like_ids()
    baseline = {
        "ai_enhance": {"summary": "arch-level AI"},
        "components": [
            _component(cid, ai=True, ctype="module", path=cid) for cid in ids
        ],
        "relationships": [
            {
                "source": "server/api",
                "target": "server/db",
                "type": "database",
                "ai_enhance": {"data_flow_description": "API reads the DB"},
            }
        ],
    }
    # Target: repo prefix added to every ID and path, plus a repo grouping node.
    target_components = [_component("repo:unamentis", ctype="repo", path="")]
    target_components += [
        _component(
            f"unamentis/{cid}", ctype="module", path=f"unamentis/{cid}"
        )
        for cid in ids
    ]
    target = {
        "components": target_components,
        "relationships": [
            {
                "source": "unamentis/server/api",
                "target": "unamentis/server/db",
                "type": "database",
            }
        ],
    }
    baseline_path = tmp_path / "baseline.json"
    target_path = tmp_path / "target.json"
    _write(baseline_path, baseline)
    _write(target_path, target)

    result = _run_merge(baseline_path, target_path)

    assert result.returncode == 0, result.stderr
    merged = json.loads(target_path.read_text())
    # Every one of the 251 baseline enhancements landed on a target component.
    assert _count_ai(merged["components"]) == 251
    # And landed on the PREFIXED ids specifically.
    by_id = {c["id"]: c for c in merged["components"]}
    assert by_id["unamentis/curriculum"]["ai_enhance"] == {
        "description": "AI note for curriculum"
    }
    # The repo grouping node stays un-enhanced.
    assert "ai_enhance" not in by_id["repo:unamentis"]
    # Per-strategy report: all via prefix/suffix, nothing exact, none lost.
    assert "prefix/suffix=251" in result.stdout
    assert "exact=0" in result.stdout
    assert "removed=0" in result.stdout
    assert "unmatched=0" in result.stdout
    assert "251/251 enhanced components preserved" in result.stdout
    # Relationship endpoints translated through the component mapping.
    merged_rel = merged["relationships"][0]
    assert merged_rel["ai_enhance"] == {"data_flow_description": "API reads the DB"}
    # Architecture-level AI carried too.
    assert merged["ai_enhance"] == {"summary": "arch-level AI"}


def test_renamed_id_same_path_preserved(tmp_path):
    """ID changed but file path did not: matched by path, enhancement kept."""
    baseline = {
        "components": [
            _component(
                "legacy-name", ai=True, ctype="package", path="src/module", name="module"
            )
        ],
        "relationships": [],
    }
    target = {
        "components": [
            _component("fresh-name", ctype="package", path="src/module", name="module")
        ],
        "relationships": [],
    }
    baseline_path = tmp_path / "baseline.json"
    target_path = tmp_path / "target.json"
    _write(baseline_path, baseline)
    _write(target_path, target)

    result = _run_merge(baseline_path, target_path)

    assert result.returncode == 0, result.stderr
    merged = json.loads(target_path.read_text())
    by_id = {c["id"]: c for c in merged["components"]}
    assert by_id["fresh-name"]["ai_enhance"] == {"description": "AI note for legacy-name"}
    assert "path=1" in result.stdout
    assert "1/1 enhanced components preserved" in result.stdout


def test_true_removal_not_counted_against_threshold(tmp_path):
    """A genuinely deleted component is not preserved and is excluded from the ratio.

    Baseline has two enhanced components; one (``gone``) has no counterpart in
    the target under any strategy. With one of two preserved the naive ratio is
    50%, but ``gone`` is a real removal, so the effective ratio is 1/1 = 100%
    and --strict at the default threshold still passes.
    """
    baseline = {
        "components": [
            _component("keep", ai=True, ctype="module", path="keep", name="keep"),
            _component("gone", ai=True, ctype="module", path="old/gone", name="gone"),
        ],
        "relationships": [],
    }
    target = {
        "components": [
            _component("keep", ctype="module", path="keep", name="keep"),
        ],
        "relationships": [],
    }
    baseline_path = tmp_path / "baseline.json"
    target_path = tmp_path / "target.json"
    _write(baseline_path, baseline)
    _write(target_path, target)

    result = _run_merge(baseline_path, target_path, "--strict")

    assert result.returncode == 0, result.stderr
    merged = json.loads(target_path.read_text())
    by_id = {c["id"]: c for c in merged["components"]}
    assert by_id["keep"]["ai_enhance"] == {"description": "AI note for keep"}
    assert "removed=1" in result.stdout
    # 100% of still-present enhancements preserved despite the raw 1/2.
    assert "100.0% of still-present" in result.stdout


def test_ambiguous_match_is_not_guessed(tmp_path):
    """When two targets could claim one baseline entry, it stays unmatched.

    Baseline ``shared`` (path ``shared``) is a suffix of both ``a/shared`` and
    ``b/shared`` in the target. The matcher must refuse to guess: neither target
    receives the enhancement, and the ambiguity is reported.
    """
    baseline = {
        "components": [
            _component("keep", ai=True, ctype="module", path="keep", name="keep"),
            _component("shared", ai=True, ctype="module", path="shared", name="shared"),
        ],
        "relationships": [],
    }
    target = {
        "components": [
            _component("keep", ctype="module", path="keep", name="keep"),
            _component("a/shared", ctype="module", path="a/shared", name="shared-a"),
            _component("b/shared", ctype="module", path="b/shared", name="shared-b"),
        ],
        "relationships": [],
    }
    baseline_path = tmp_path / "baseline.json"
    target_path = tmp_path / "target.json"
    _write(baseline_path, baseline)
    _write(target_path, target)

    # Non-strict: partial preservation still writes and exits 0.
    result = _run_merge(baseline_path, target_path)

    assert result.returncode == 0, result.stderr
    merged = json.loads(target_path.read_text())
    by_id = {c["id"]: c for c in merged["components"]}
    # Neither ambiguous candidate was guessed.
    assert "ai_enhance" not in by_id["a/shared"]
    assert "ai_enhance" not in by_id["b/shared"]
    # The unambiguous one still matched.
    assert by_id["keep"]["ai_enhance"] == {"description": "AI note for keep"}
    assert "unmatched=1" in result.stdout
    assert "ambiguous" in result.stderr.lower()
    assert "shared" in result.stderr


def test_strict_threshold_failure_exits_nonzero_target_untouched(tmp_path):
    """Below the strict threshold: exit nonzero, target byte-for-byte unchanged.

    Two of ten baseline enhancements match exactly; the other eight each hit two
    same-name/type target candidates and stay ambiguous. Ratio 2/10 = 20% is far
    below the default 90%, so --strict fails without touching the target. The
    same run WITHOUT --strict would write (proving the guard, not the matcher,
    is what blocks the write).
    """
    baseline_comps = []
    for i in range(10):
        baseline_comps.append(
            _component(
                f"x{i}", ai=True, ctype="module", path=f"p{i}", name=f"n{i}"
            )
        )
    baseline = {"components": baseline_comps, "relationships": []}

    target_comps = [
        _component("x0", ctype="module", path="p0", name="n0"),
        _component("x1", ctype="module", path="p1", name="n1"),
    ]
    # For x2..x9, create two same-(name,type) candidates each, with IDs/paths
    # that do NOT exact/path/suffix match, so only the name+type wave applies
    # and it is ambiguous.
    for i in range(2, 10):
        target_comps.append(
            _component(f"alpha/dup{i}", ctype="module", path=f"alpha/dup{i}", name=f"n{i}")
        )
        target_comps.append(
            _component(f"beta/dup{i}", ctype="module", path=f"beta/dup{i}", name=f"n{i}")
        )
    target = {"components": target_comps, "relationships": []}

    baseline_path = tmp_path / "baseline.json"
    target_path = tmp_path / "target.json"
    _write(baseline_path, baseline)
    _write(target_path, target)

    target_bytes_before = target_path.read_bytes()

    result = _run_merge(baseline_path, target_path, "--strict")

    assert result.returncode != 0
    assert "below the --strict threshold" in result.stderr
    assert target_path.read_bytes() == target_bytes_before

    # Custom lower threshold accepts the same 20% preservation and writes.
    result_ok = _run_merge(
        baseline_path, target_path, "--strict", "--strict-threshold", "0.1"
    )
    assert result_ok.returncode == 0, result_ok.stderr
    assert target_path.read_bytes() != target_bytes_before

    # And a plain (non-strict) run always writes regardless of ratio.
    _write(target_path, target)
    target_bytes_reset = target_path.read_bytes()
    result_plain = _run_merge(baseline_path, target_path)
    assert result_plain.returncode == 0, result_plain.stderr
    assert target_path.read_bytes() != target_bytes_reset
