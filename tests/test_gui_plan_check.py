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
    allow_errors:
      - path: "/live-config.json"
        reason: "probe"
probe_inventory:
  - match: '"./live-config.json"'
    source: hooks/useLiveMonitor.ts
    fires: every boot
    allow_path: "/live-config.json"
    can_404_on: [monolith]
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
    - "Click the button labeled 'Skip' in the welcome dialog"
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
    (root / "viewer" / "src" / "hooks").mkdir(parents=True)
    (root / "viewer" / "tests" / "gui" / "plan").mkdir(parents=True)
    (root / "viewer" / "src" / "hooks" / "useLiveMonitor.ts").write_text(
        'const res = await fetch("./live-config.json");\n'
    )
    (root / "viewer" / "src" / "lenses" / "index.ts").write_text(
        'import "./structure";\nexport * from "./registry";\n'
    )
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


# --- Anti-rot: silent enumerator drops become loud findings (adversarial
# review of PR #82, findings 2 and 3). Each test was run against the
# pre-fix check and passed silently; after the fix each fails loudly. ---


def test_camelcase_question_id_fails_loudly_not_silently(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    lens = root / "viewer" / "src" / "lenses" / "structure.ts"
    lens.write_text(
        LENS_TS.replace(
            'id: "locate",',
            'id: "locate",\n    question: "?",\n    gesture: "g",\n  },\n  {\n    id: "whoReads",',
        )
    )
    assert _run(root) == 1
    assert "whoReads" in capsys.readouterr().out


def test_new_digit_edge_key_is_enumerated_and_demands_coverage(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    layout = root / "viewer" / "src" / "utils" / "layout.ts"
    layout.write_text(
        LAYOUT_TS.replace(
            'http:      { color: "#3B82F6" },',
            'http:      { color: "#3B82F6" },\n  http2:     { color: "#000000" },',
        )
    )
    assert _run(root) == 1
    assert "edge:http2" in capsys.readouterr().out


def test_single_quoted_tab_key_is_enumerated(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    panel = root / "viewer" / "src" / "components" / "DetailPanel.tsx"
    panel.write_text(
        DETAIL_PANEL_TSX.replace(
            '["overview", "files"]', '["overview", "files", \'secret\']'
        )
    )
    assert _run(root) == 1
    assert "tab:secret" in capsys.readouterr().out


def test_multiline_tab_keys_are_enumerated(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    panel = root / "viewer" / "src" / "components" / "DetailPanel.tsx"
    panel.write_text(
        'type Tab = "overview" | "files" | "extra";\n'
        "const TAB_KEYS: Tab[] = [\n"
        '  "overview",\n  "files",\n  "extra",\n];\n'
    )
    assert _run(root) == 1
    assert "tab:extra" in capsys.readouterr().out


def test_multiline_edge_styles_value_does_not_truncate_enumeration(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    layout = root / "viewer" / "src" / "utils" / "layout.ts"
    layout.write_text(
        LAYOUT_TS.replace(
            'http:      { color: "#3B82F6" },',
            'http: {\n    color: "#3B82F6",\n  },\n  gravity: { color: "#111111" },',
        )
    )
    assert _run(root) == 1
    assert "edge:gravity" in capsys.readouterr().out


def test_unregistered_lens_file_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "src" / "lenses" / "deadlens.ts").write_text(LENS_TS)
    assert _run(root) == 1
    assert "deadlens" in capsys.readouterr().out


def test_bootstrap_still_fails_on_structural_findings(tmp_path, capsys):
    root = _make_tree(tmp_path)
    # No plan files at all, AND a component file in neither manifest list: the
    # bootstrap flag may downgrade only the no-plan finding, never this one.
    (root / "viewer" / "src" / "components" / "NewSurface.tsx").write_text("x")
    assert _run(root, "--bootstrap-ok") == 1
    assert "NewSurface.tsx" in capsys.readouterr().out


def test_duplicate_surface_entry_cannot_swallow_missing_file(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "tests" / "gui" / "surface.yaml").write_text(
        SURFACE_YAML.replace(
            "surfaces:\n  - component: SearchOverlay\n    file: SearchOverlay.tsx",
            "surfaces:\n  - component: SearchOverlay\n    file: Ghost.tsx\n"
            "  - component: SearchOverlay\n    file: SearchOverlay.tsx",
        )
    )
    assert _run(root) == 1
    out = capsys.readouterr().out
    assert "duplicate surface component SearchOverlay" in out


def test_covers_as_string_reports_finding(tmp_path, capsys):
    root = _make_tree(tmp_path)
    plan = FULL_PLAN.split("  covers:")[0] + '  covers: "component:SearchOverlay"\n'
    _write_plan(root, plan)
    assert _run(root) == 1
    assert "covers must be a list" in capsys.readouterr().out


def test_unknown_token_kind_reports_finding(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN.replace("- lens:structure", "- lense:structure"))
    assert _run(root) == 1
    assert "lense:structure" in capsys.readouterr().out


def test_case_id_in_wrong_vector_file_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN.replace("id: V1.1", "id: V2.1"), name="V1.yaml")
    assert _run(root) == 1
    assert "wrong shard" in capsys.readouterr().out


def test_malformed_case_entry_reports_finding_not_traceback(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, '- "just a string"\n')
    assert _run(root) == 1
    assert "not a mapping" in capsys.readouterr().out


def test_malformed_waiver_entry_reports_finding_not_traceback(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    _write_plan(root, '- "just a string"\n', name="waivers.yaml")
    assert _run(root) == 1
    assert "not a mapping" in capsys.readouterr().out


def test_broken_yaml_exits_2(tmp_path):
    import pytest

    root = _make_tree(tmp_path)
    _write_plan(root, "- id: V1.1\n  steps: [unclosed\n")
    with pytest.raises(SystemExit) as exc_info:
        _run(root)
    assert exc_info.value.code == 2


# --- Probe inventory (adjustment from the first Phase 2 run: an undeclared
# search-index probe failed both search cases; the inventory makes that a CI
# failure instead of a run-time surprise). ---


def test_undeclared_fetch_call_site_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "src" / "utils" / "search.ts").write_text(
        "const r = await fetch(`${baseUrl}/manifest.json`);\n"
    )
    assert _run(root) == 1
    assert "not in the probe_inventory" in capsys.readouterr().out


def test_stale_inventory_entry_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "tests" / "gui" / "datasets.yaml").write_text(
        DATASETS_YAML
        + "  - match: 'dataUrl(\"ghost.json\")'\n"
        + "    source: nowhere.ts\n"
        + "    fires: never\n"
        + "    can_404_on: []\n"
    )
    assert _run(root) == 1
    assert "matches no fetch call site" in capsys.readouterr().out


def test_same_arg_text_in_different_file_is_not_wildcarded(tmp_path, capsys):
    # Adversarial review F1: a bare-identifier match like 'url' must not
    # accept a same-text fetch in a DIFFERENT source file.
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "tests" / "gui" / "datasets.yaml").write_text(
        DATASETS_YAML
        + "  - match: 'url'\n    source: hooks/useAdminData.ts\n"
        + "    fires: admin\n    can_404_on: []\n"
    )
    (root / "viewer" / "src" / "hooks" / "useAdminData.ts").write_text(
        "const r = await fetch(url);\n"
    )
    # Declared call site passes; an undeclared same-text fetch elsewhere fails.
    assert _run(root) == 0
    (root / "viewer" / "src" / "utils" / "evil.ts").write_text(
        "const r = await fetch(url);\n"
    )
    assert _run(root) == 1
    assert "evil.ts" in capsys.readouterr().out


def test_commented_out_fetch_is_not_a_call_site(tmp_path):
    # Adversarial review F3: a commented-out fetch must not trip the check.
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "src" / "utils" / "legacy.ts").write_text(
        '// old: const r = await fetch("gone.json");\n'
        '/* also fetch("blk.json") */\n'
        'const s = "not a fetch(\\"str.json\\") call";\n'
    )
    assert _run(root) == 0


def test_comma_inside_url_literal_is_not_a_boundary(tmp_path):
    # Adversarial review F2: a comma inside the URL string must not truncate
    # the extracted argument.
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "src" / "hooks" / "useLiveMonitor.ts").write_text(
        'const res = await fetch("a,b.json");\n'
    )
    (root / "viewer" / "tests" / "gui" / "datasets.yaml").write_text(
        DATASETS_YAML.replace(
            "match: '\"./live-config.json\"'", "match: '\"a,b.json\"'"
        )
    )
    assert _run(root) == 0


def test_dismissal_after_first_interaction_fails(tmp_path, capsys):
    # Adversarial review F5: the dismissal must precede the first app click.
    root = _make_tree(tmp_path)
    _write_plan(
        root,
        FULL_PLAN.replace(
            '  steps:\n    - "Load the app and wait for the graph to render"\n'
            "    - \"Click the button labeled 'Skip' in the welcome dialog\"\n",
            '  steps:\n    - "Load the app and wait for the graph to render"\n'
            '    - "Click the component node titled analyzer"\n'
            "    - \"Click the button labeled 'Skip' in the welcome dialog\"\n",
        ),
    )
    assert _run(root) == 1
    assert "before dismissing the welcome dialog" in capsys.readouterr().out


def test_first_load_variant_phrasing_in_later_case_fails(tmp_path, capsys):
    # Adversarial review F4: a first-load assertion phrased as 'initial render'
    # in a non-first case must still be caught.
    root = _make_tree(tmp_path)
    base = _two_case_plan(
        second_steps='    - "Load the app and wait for the graph to render"\n'
    )
    head, _, tail = base.rpartition('    - "the graph renders at least one node"')
    plan = head + '    - "on initial render a badge is shown"' + tail
    _write_plan(root, plan)
    assert _run(root) == 1
    assert "asserts a first-load state" in capsys.readouterr().out


def test_out_of_order_yaml_still_linted_by_id(tmp_path, capsys):
    # Adversarial review F6: physical YAML order must not decide "first"; id
    # order does (matching runner execution).
    root = _make_tree(tmp_path)
    # V1.2 physically first, but V1.1 is the id-first case and carries the
    # dismissal; ordering by id must find no shard-order fault.
    second = (
        "- id: V1.2\n  vector: boot-and-render\n  viewport: desktop\n"
        "  dataset: dogfood\n  steps:\n    - \"Reload the page\"\n"
        '  pass_when:\n    - "the graph renders at least one node"\n'
        "  evidence: screenshot\n"
    )
    _write_plan(root, second + FULL_PLAN)
    assert _run(root) == 0


def test_nested_call_argument_is_not_truncated(tmp_path, capsys):
    # Regression: a naive regex truncated dataUrl("x.json") at the inner close
    # paren, misreporting declared probes as undeclared.
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "src" / "hooks" / "useLiveMonitor.ts").write_text(
        'const res = await fetch(dataUrl("manifest.json"), { headers });\n'
    )
    (root / "viewer" / "tests" / "gui" / "datasets.yaml").write_text(
        DATASETS_YAML.replace(
            "match: '\"./live-config.json\"'", "match: 'dataUrl(\"manifest.json\")'"
        )
    )
    assert _run(root) == 0


def test_missing_allowlist_for_404_probe_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "tests" / "gui" / "datasets.yaml").write_text(
        DATASETS_YAML.replace(
            '    allow_errors:\n      - path: "/live-config.json"\n        reason: "probe"\n',
            "    allow_errors: []\n",
        )
    )
    assert _run(root) == 1
    assert "does not allowlist /live-config.json" in capsys.readouterr().out


# A helper that loads several files through one parameterized fetch is ONE
# inventory entry (entries are keyed by source and argument text), so its
# allow_path carries the list of paths it can request. Every one of them is
# still enforced against the allowlists.
_LIST_ALLOW_DATASETS = """
datasets:
  dogfood:
    layout: monolith
    generate: []
    allow_errors:
      - path: "/live-config.json"
        reason: "probe"
      - path: "/a.json"
        reason: "optional sidecar"
      - path: "/b.json"
        reason: "optional sidecar"
probe_inventory:
  - match: 'dataUrl(path)'
    source: hooks/useLiveMonitor.ts
    fires: every boot, once per sidecar
    allow_path:
      - "/a.json"
      - "/b.json"
    can_404_on: [monolith]
"""


def test_list_allow_path_is_accepted_when_every_path_is_allowlisted(tmp_path):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "src" / "hooks" / "useLiveMonitor.ts").write_text(
        "const res = await fetch(dataUrl(path));\n"
    )
    (root / "viewer" / "tests" / "gui" / "datasets.yaml").write_text(_LIST_ALLOW_DATASETS)
    assert _run(root) == 0


def test_list_allow_path_fails_when_one_path_is_not_allowlisted(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(root, FULL_PLAN)
    (root / "viewer" / "src" / "hooks" / "useLiveMonitor.ts").write_text(
        "const res = await fetch(dataUrl(path));\n"
    )
    (root / "viewer" / "tests" / "gui" / "datasets.yaml").write_text(
        _LIST_ALLOW_DATASETS.replace(
            '      - path: "/b.json"\n        reason: "optional sidecar"\n', ""
        )
    )
    assert _run(root) == 1
    assert "does not allowlist /b.json" in capsys.readouterr().out


# --- Shard-order convention lint (adjustment from the first run's review:
# the welcome-dialog and first-load semantics cost a review cycle as prose;
# now they are findings). ---


def _two_case_plan(first_extra: str = "", second_steps: str = "") -> str:
    second = second_steps or '    - "Reload the page"\n'
    return (
        FULL_PLAN
        + first_extra
        + "\n- id: V1.2\n  vector: boot-and-render\n  viewport: desktop\n"
        + "  dataset: dogfood\n  steps:\n"
        + second
        + '  pass_when:\n    - "the graph renders at least one node"\n'
        + "  evidence: screenshot\n"
    )


def test_first_case_without_dismissal_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(
        root,
        FULL_PLAN.replace(
            "    - \"Click the button labeled 'Skip' in the welcome dialog\"\n", ""
        ),
    )
    assert _run(root) == 1
    assert "no welcome-dialog dismissal" in capsys.readouterr().out


def test_later_case_re_dismissing_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    _write_plan(
        root,
        _two_case_plan(
            second_steps='    - "Load the app and wait for the graph to render"\n'
            "    - \"Click the button labeled 'Skip' in the welcome dialog\"\n"
        ),
    )
    assert _run(root) == 1
    assert "re-dismisses the welcome dialog" in capsys.readouterr().out


def test_first_load_assertion_in_later_case_fails(tmp_path, capsys):
    root = _make_tree(tmp_path)
    base = _two_case_plan(
        second_steps='    - "Load the app and wait for the graph to render"\n'
    )
    # Swap only the SECOND case's assertion (rpartition targets the last
    # occurrence, which belongs to V1.2).
    head, _, tail = base.rpartition('    - "the graph renders at least one node"')
    plan = head + '    - "on this first load of the origin, a badge is shown"' + tail
    _write_plan(root, plan)
    assert _run(root) == 1
    assert "asserts a first-load state" in capsys.readouterr().out


def test_no_welcome_dataset_must_not_dismiss(tmp_path, capsys):
    root = _make_tree(tmp_path)
    (root / "viewer" / "tests" / "gui" / "datasets.yaml").write_text(
        DATASETS_YAML.replace(
            "    layout: monolith\n",
            "    layout: monolith\n    first_load_shows_welcome: false\n",
        )
    )
    _write_plan(root, FULL_PLAN)  # still contains the Skip step
    assert _run(root) == 1
    assert "declares it never appears" in capsys.readouterr().out
