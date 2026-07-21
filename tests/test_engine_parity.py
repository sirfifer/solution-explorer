"""Parity guard: freeze the CURRENT engine's output on the fixture repos.

This is the P4-1 baseline that the P4-7 cutover diffs against. It runs the
current engine (ArchitectureScanner for the single repo, MultiRepoOrchestrator
for the multi-repo config) on the committed fixtures, normalizes away
timestamps, machine paths, and version strings, and compares against a
committed snapshot. When the new engine lands, P4-3/P4-7 diff its output
against these same snapshots and must enumerate every intended difference.

Regenerate the snapshots intentionally with::

    SE_REGEN_PARITY=1 python -m pytest tests/test_engine_parity.py

Regeneration is never automatic; a silent snapshot refresh would defeat the
guard (WORK-PLAN.md section 2, principle 4).
"""

import copy
import json
import os
from pathlib import Path

import pytest

from analyzer.models import to_dict
from analyzer.multi_repo import MultiRepoOrchestrator
from analyzer.parity import VOLATILE_KEYS as _VOLATILE_KEYS
from analyzer.parsers import PARSERS
from analyzer.scanner import ArchitectureScanner

FIXTURES = Path(__file__).parent / "fixtures"
SNAPSHOTS = FIXTURES / "parity"

# The snapshots are pinned to the tree-sitter parser tier: regex-fallback
# parsers legitimately emit different symbols (visibility, docstrings, exact
# ranges), so comparing them against a tree-sitter baseline is meaningless.
# CI runs both tiers (ci.yml installs .[all,dev]; architecture-viz.yml
# installs only pytest+ruff), so the guard executes in the tree-sitter lane
# and skips loudly in the regex lane instead of failing on tier drift.
_PARITY_LANGS = ("python", "swift", "rust", "typescript", "javascript", "go", "ruby")
# The *TreeSitterParser wrappers import cleanly even without the native
# grammar wheels and fall back to regex per call, so the class name lies
# about the tier (proven on PR #12 CI). The `_ts_available` flag is the
# runtime truth that TreeSitterParser.extract_symbols itself consults;
# regex baseline parsers lack the attribute, so getattr defaults to False.
_TREE_SITTER_ACTIVE = all(
    getattr(PARSERS[lang], "_ts_available", False) for lang in _PARITY_LANGS
)
requires_tree_sitter_tier = pytest.mark.skipif(
    not _TREE_SITTER_ACTIVE,
    reason=(
        "parity snapshots are pinned to the tree-sitter parser tier; this "
        "environment resolved at least one language to the regex fallback"
    ),
)

# Top-level keys stripped before comparison: timestamps, absolute machine
# paths, the analyzer version, and the changelog (which embeds timestamps and
# depends on prior output). Sourced from analyzer.parity (imported at the top) so
# this fixture guard and the golden-corpus parity check (G4) share ONE
# volatile-field allowlist rather than each maintaining its own.


def _deep_sort(obj):
    """Recursively sort every list by canonical element form.

    The current engine builds some lists (imports, tech_stack, external
    services) from Python sets, so their order varies with PYTHONHASHSEED
    across processes. Sorting every list makes the snapshot order-independent,
    which is the "strip any ordering nondeterminism" the P4-1 card requires.
    The new engine sorts deterministically (invariant I4), so P4-7 compares the
    same normalized form.
    """
    if isinstance(obj, dict):
        return {k: _deep_sort(v) for k, v in obj.items()}
    if isinstance(obj, list):
        items = [_deep_sort(x) for x in obj]
        items.sort(key=lambda x: json.dumps(x, sort_keys=True, default=str))
        return items
    return obj


def normalize(arch_dict: dict) -> dict:
    """Strip volatile fields and canonicalize list order for a stable snapshot."""
    d = copy.deepcopy(arch_dict)
    for key in _VOLATILE_KEYS:
        d.pop(key, None)
    return _deep_sort(d)


def canonical(d: dict) -> str:
    """Deterministic serialization: sorted keys, stable indentation."""
    return json.dumps(d, sort_keys=True, indent=2, default=str) + "\n"


def _run_polyglot() -> dict:
    scanner = ArchitectureScanner(FIXTURES / "polyglot")
    return normalize(to_dict(scanner.scan()))


def _run_multi() -> dict:
    orchestrator = MultiRepoOrchestrator(FIXTURES / "multi" / "solution.json")
    return normalize(to_dict(orchestrator.run()))


PARITY_TARGETS = {
    "polyglot": _run_polyglot,
    "multi": _run_multi,
}


def _snapshot_path(name: str) -> Path:
    return SNAPSHOTS / f"{name}.snapshot.json"


def _regen_requested() -> bool:
    return os.environ.get("SE_REGEN_PARITY") == "1"


@requires_tree_sitter_tier
@pytest.mark.parametrize("name", sorted(PARITY_TARGETS))
def test_current_engine_matches_snapshot(name):
    produced = canonical(PARITY_TARGETS[name]())
    path = _snapshot_path(name)

    if _regen_requested():
        SNAPSHOTS.mkdir(parents=True, exist_ok=True)
        path.write_text(produced, encoding="utf-8")
        pytest.skip(f"regenerated parity snapshot {path.name}")

    assert path.exists(), (
        f"missing parity snapshot {path}; regenerate with "
        f"SE_REGEN_PARITY=1 python -m pytest {__file__}"
    )
    expected = path.read_text(encoding="utf-8")
    assert produced == expected, (
        f"current engine output drifted from the committed {name} parity "
        f"snapshot. If this change is intended, regenerate with "
        f"SE_REGEN_PARITY=1 and review the diff."
    )


@requires_tree_sitter_tier
@pytest.mark.parametrize("name", sorted(PARITY_TARGETS))
def test_engine_output_is_deterministic(name):
    # Two runs of the current engine on the same fixture must be identical,
    # which is what makes the snapshot a meaningful guard (I4).
    assert canonical(PARITY_TARGETS[name]()) == canonical(PARITY_TARGETS[name]())


def test_snapshots_are_committed_and_nonempty():
    for name in PARITY_TARGETS:
        path = _snapshot_path(name)
        assert path.exists(), f"parity snapshot {path} is not committed"
        data = json.loads(path.read_text(encoding="utf-8"))
        # A real freeze: components, files, and symbols are all present.
        assert data["components"], f"{name} snapshot has no components"
        assert data["files"], f"{name} snapshot has no files"
        assert data["symbols"], f"{name} snapshot has no symbols"


@requires_tree_sitter_tier
def test_guard_detects_a_perturbed_snapshot():
    """Regression-proof: the guard must FAIL when the frozen output changes.

    A snapshot test that cannot fail is worthless (WORK-PLAN.md section 2,
    principle 2). Here we perturb the produced output by one symbol name and
    confirm the byte comparison rejects it.
    """
    name = "polyglot"
    baseline = canonical(PARITY_TARGETS[name]())
    committed = _snapshot_path(name).read_text(encoding="utf-8")
    assert baseline == committed  # sanity: unperturbed matches

    perturbed = PARITY_TARGETS[name]()
    assert perturbed["symbols"], "fixture must have symbols to perturb"
    perturbed["symbols"][0]["name"] = perturbed["symbols"][0]["name"] + "_PERTURBED"

    assert canonical(perturbed) != committed, (
        "the parity guard failed to detect a perturbed snapshot"
    )
