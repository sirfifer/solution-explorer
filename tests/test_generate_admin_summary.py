"""Regression tests for scripts/generate-admin-summary.py's component count.

Background (comprehension-study defect): a live install served two documents
that disagreed about the same repository's component count three minutes
apart: architecture/manifest.json said stats.total_components == 254, while
admin-summary.json said repos[0].component_count == 251. The root cause was
that count_components() re-walked the component tree independently instead
of reading the analyzer's own authoritative stats.total_components, so on an
older-schema architecture.json (whose own stats.total_components was
computed under a narrower, now-superseded rule) the two numbers silently
disagreed with each other -- and admin-summary.json's number even disagreed
with the very file it was computed from.

These tests exercise count_components() directly (imported the same way
test_dpea.py imports merge-ai-enhancements.py, since the filename has a
hyphen) rather than via subprocess, since the defect is in the counting rule
itself, not in argument handling or I/O.
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "generate_admin_summary", SCRIPTS_DIR / "generate-admin-summary.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gas = _load_module()


def _component(comp_id, children=None):
    return {"id": comp_id, "name": comp_id, "children": children or []}


class TestCountComponents:
    def test_prefers_stats_total_components_when_present(self):
        """The common, well-formed case: stats.total_components is trusted
        as-is rather than recomputed, so this agrees by construction with
        whatever else in the product reads the same field (e.g. architecture/
        manifest.json)."""
        arch = {
            "stats": {"total_components": 254},
            "components": [_component("repo:unamentis", children=[_component("a")])],
        }
        assert gas.count_components(arch) == 254

    def test_trusts_stats_even_when_tree_walk_would_disagree(self):
        """Reproduces the actual defect: an older-schema architecture.json
        whose stats.total_components (173) was computed under a narrower rule
        than a raw recursive walk of the same tree would produce (251, using
        the fixture's own numbers). Before the fix, count_components() did
        the independent walk and returned a number that matched neither the
        file's own declared total nor architecture/manifest.json's fresh
        254. The fix makes admin-summary.json honestly report what this
        file's own stats claim, instead of silently contradicting it."""
        # Build a tree whose raw node count is deliberately larger than the
        # declared stats.total_components, mirroring the real stale file
        # (recursive walk 251 vs its own stats.total_components 173).
        children = [_component(f"child-{i}") for i in range(50)]
        arch = {
            "stats": {"total_components": 173},
            "components": [_component("root", children=children)],
        }
        raw_walk = 1 + len(children)  # 51, deliberately != 173
        assert raw_walk != 173
        assert gas.count_components(arch) == 173

    def test_falls_back_to_tree_walk_when_stats_missing(self):
        arch = {
            "components": [
                _component("a"),
                _component("b", children=[_component("b1"), _component("b2")]),
            ]
        }
        # a, b, b1, b2 = 4
        assert gas.count_components(arch) == 4

    def test_falls_back_to_tree_walk_when_total_components_not_an_int(self):
        arch = {
            "stats": {"total_components": "unknown"},
            "components": [_component("a"), _component("b")],
        }
        assert gas.count_components(arch) == 2

    def test_falls_back_to_tree_walk_when_stats_not_a_dict(self):
        arch = {
            "stats": None,
            "components": [_component("a"), _component("b"), _component("c")],
        }
        assert gas.count_components(arch) == 3

    def test_agrees_with_recursive_walk_on_a_contract_valid_tree(self):
        """For any current-schema architecture.json, the analyzer guarantees
        stats.total_components equals the distinct tree-node count (derive
        pipeline's total_components-equality contract). This test pins that
        the fixed function's fast path and the fallback walk produce the same
        answer on such a tree, i.e. the fix is a no-op for well-formed data."""
        children = [_component("child-1"), _component("child-2")]
        arch = {
            "stats": {"total_components": 3},
            "components": [_component("root", children=children)],
        }
        with_stats = gas.count_components(arch)
        without_stats = gas.count_components({"components": arch["components"]})
        assert with_stats == without_stats == 3
