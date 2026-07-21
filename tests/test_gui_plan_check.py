"""Hermetic tests for scripts/gui-plan-check.py (GUI plan completeness check).

These build a miniature repo tree (lens sources, DetailPanel, layout, plan,
surface manifest) in tmp_path and drive the real check against it, so they are
deterministic and offline. The contract under test is mechanized honesty
(GUI-REGRESSION-STRATEGY.md, Maintainability): silence is the only failure the
check tolerates. Fail-before framing: each test writes the silent-gap state
first and asserts the check REFUSES it; the passing states are the same trees
with the gap dispositioned.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gui-plan-check.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("_gui_plan_check", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECK = _load_module()

LENS_TS = '''
const questions = [
  {
    id: "identity",
    question: "What is this?",
    gesture: "Click it",
  },
  {
    id: "locate",
    question: "Where is it?",
    gesture: "Look",
  },
];
export const structureLens = {
  id: "structure",
  label: "Structure",
};
'''

DETAIL_PANEL_TSX = '''
type Tab = "overview" | "files";
const TAB_KEYS: Tab[] = ["overview", "files"];
'''

LAYOUT_TS = '''
const EDGE_STYLES: Record<string, object> = {
  import:    { color: "#6B7280" },
  http:      { color: "#3B82F6" },
};
export function getEdgeStyle(type: string) {
  return EDGE_STYLES[type] || EDGE_STYLES.import;
}
'''

DATASETS_YAML = """
datasets:
  dogfood:
    layout: monolith
    generate: []
    allow_errors: []
"""

SURFACE_YAML = """
surfaces:
  - component: SearchOverlay
    file: SearchOverlay.tsx
ignore:
  - file: Tooltip.tsx
    reason: "Presentational wrapper, exercised implicitly."
  - file: DetailPanel.tsx
    reason: "Miniature-tree stand-in; the real DetailPanel is a surface."
"""

# One case covering every enumerated surface in the miniature tree.
FULL_PLAN = """
- id: V1.1
  vector: boot-and-render
  viewport: desktop
  dataset: dogfood
  steps:
    - "Load the app and wait for the graph to render"
  pass_when:
    - "the graph renders at least one node"
  evidence: screenshot
  covers:
    - lens:structure
    - subview:structure/identity
    - subview:structure/locate
    - tab:overview
    - tab:files
    - edge:import
    - edge:http
    - component:SearchOverlay
"""


def _make_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "viewer" / "src" / "lenses").mkdir(parents=True)
    (root / "viewer" / "src" / "components").mkdir(parents=True)
    (root / "viewer" / "src" / "utils").mkdir(parents=True)
    (root / "viewer" / "tests" / "gui" / "plan").mkdir(parents=True)
    (root / "viewer" / "src" / "lenses" / "structure.ts").write_text(LENS_TS)
    (root / "viewer" / "src" / "components" / "DetailPanel.tsx").write_text(
        DETAIL_PANEL_TSX
    )
    (root / "viewer" / "src" / "components" / "SearchOverlay.tsx").write_text("x")
    (root / "viewer" / "src" / "components" / "Tooltip.tsx").write_text("x")
    (root / "viewer" / "src" / "utils" / "layout.ts").write_text(LAYOUT_TS)
    (root / "viewer" / "tests" / "gui" / "datasets.yaml").write_text(DATASETS_YAML)
    (root / "viewer" / "tests" / "gui" / "surface.yaml").write_text(SURFACE_YAML)
    return root


def _run(root: Path, *extra: str) -> int:
    return CHECK.main(["--repo-root", str(root), *extra])


def _write_plan(root: Path, content: str, name: str = "V1.yaml") -> None:
    (root / "viewer" / "tests" / "gui" / "plan" / name).write_text(content)


def test_full_coverage_is_clean(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    assert _run(root) == 0
    out = capsys.readouterr().out
    assert "clean" in out


def test_missing_plan_files_fail_without_bootstrap_flag(tmp_path):
    root = _make_tree(tmp_path)
    assert _run(root) == 1
    assert _run(root, "--bootstrap-ok") == 0


def test_uncovered_tier1_surface_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN.replace("    - edge:http\n", ""))
    assert _run(root) == 1
    assert "edge:http" in capsys.readouterr().out


def test_uncovered_subview_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN.replace("    - subview:structure/locate\n", ""))
    assert _run(root) == 1
    assert "subview:structure/locate" in capsys.readouterr().out


def test_waiver_satisfies_but_stays_visible(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN.replace("    - edge:http\n", ""))
    _write_plan(
        root,
        '- token: edge:http\n  reason: "No http edge in any Phase 1 dataset."\n',
        name="waivers.yaml",
    )
    assert _run(root) == 0
    out = capsys.readouterr().out
    assert "WAIVED" in out and "edge:http" in out


def test_stale_waiver_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)  # edge:http covered
    _write_plan(
        root,
        '- token: edge:http\n  reason: "Stale."\n',
        name="waivers.yaml",
    )
    assert _run(root) == 1
    assert "waived but also covered" in capsys.readouterr().out


def test_phantom_token_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN.replace("edge:http", "edge:carrier-pigeon"))
    assert _run(root) == 1
    out = capsys.readouterr().out
    assert "edge:carrier-pigeon" in out


def test_uncovered_manifest_surface_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN.replace("    - component:SearchOverlay\n", ""))
    assert _run(root) == 1
    assert "SearchOverlay" in capsys.readouterr().out


def test_plan_component_absent_from_manifest_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(
        root, FULL_PLAN.replace("component:SearchOverlay", "component:GhostPanel")
    )
    assert _run(root) == 1
    assert "GhostPanel" in capsys.readouterr().out


def test_new_component_file_in_neither_list_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "src" / "components" / "NewSurface.tsx").write_text("x")
    assert _run(root) == 1
    assert "NewSurface.tsx" in capsys.readouterr().out


def test_new_component_file_in_subdirectory_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    sub = root / "viewer" / "src" / "components" / "admin"
    sub.mkdir()
    (sub / "NewTab.tsx").write_text("x")
    assert _run(root) == 1
    assert "admin/NewTab.tsx" in capsys.readouterr().out


def test_manifest_entry_for_missing_file_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "src" / "components" / "SearchOverlay.tsx").unlink()
    assert _run(root) == 1
    assert "missing file SearchOverlay.tsx" in capsys.readouterr().out


def test_lens_source_style_drift_fails_loudly(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    # A refactor that renames `label:` breaks the enumerator's anchor; the
    # check must fail loudly rather than enumerate nothing and pass.
    lens = root / "viewer" / "src" / "lenses" / "structure.ts"
    lens.write_text(LENS_TS.replace('label: "Structure"', 'title: "Structure"'))
    assert _run(root) == 1
    assert "could not parse structure.ts" in capsys.readouterr().out


def test_out_of_vocabulary_step_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(
        root,
        FULL_PLAN.replace(
            '"Load the app and wait for the graph to render"',
            '"Drag the node to the corner"',
        ),
    )
    assert _run(root) == 1
    assert "closed-" in capsys.readouterr().out


def test_duplicate_case_id_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN + FULL_PLAN.replace("covers:", "covers:"))
    assert _run(root) == 1
    assert "duplicate case id V1.1" in capsys.readouterr().out


def test_unknown_dataset_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN.replace("dataset: dogfood", "dataset: ghost"))
    assert _run(root) == 1
    assert "ghost" in capsys.readouterr().out
