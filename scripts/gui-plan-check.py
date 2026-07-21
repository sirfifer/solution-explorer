#!/usr/bin/env python3
"""Two-tier completeness check for the GUI regression plan.

Design authority: docs/testing/GUI-REGRESSION-STRATEGY.md (Maintainability).
Mechanized honesty in the coverage-ledger spirit: silence is the only failure
mode this tool tolerates. It cannot judge whether a case tests a surface WELL;
it makes it impossible for a surface to have no recorded disposition at all.

Tier one statically enumerates the surfaces that ARE extractable from source:
  - registered lens ids and their question (sub-view) ids from
    viewer/src/lenses/*.ts,
  - DetailPanel tab keys from the TAB_KEYS array,
  - EDGE_STYLES relationship types from viewer/src/utils/layout.ts.
Any enumerated surface with zero plan references fails the check. An
enumerator that parses NOTHING from a source file also fails: a source-style
drift must break the check loudly, never rot it quietly.

Tier two covers what source cannot enumerate: the hand-maintained manifest
viewer/tests/gui/surface.yaml is cross-checked against the plan in both
directions (a manifest surface no case covers fails; a plan token naming a
component absent from the manifest fails), and every *.tsx file under
viewer/src/components/ must appear in the manifest or its ignore list, so a
new surface cannot land invisibly.

Plan references are explicit `covers:` tokens on cases:
  lens:<id>   subview:<lens>/<qid>   tab:<key>   edge:<type>   component:<Name>
A surface no dataset can exercise is not silently skipped: it gets an entry in
viewer/tests/gui/plan/waivers.yaml with a reason. Waivers satisfy coverage but
are printed on every run, so they stay visible decisions, never invisible gaps.

Exit codes: 0 clean, 1 findings, 2 usage/parse error.
`--bootstrap-ok` downgrades the no-plan-files-at-all state to a loud exit 0;
it exists only for the window between the harness PR and the plan PR and is
removed from CI when the plan lands.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VIEWPORTS = {"desktop", "mobile", "mobile-landscape"}
EVIDENCE_KINDS = {"screenshot", "screenshot+console", "trace"}
# The closed action vocabulary (design doc, plan format). A step must begin
# with one of these verbs; extending the vocabulary means extending this list
# in the same PR as the case that needs it.
ACTION_VERBS = (
    "load",
    "click",
    "open",
    "type",
    "scroll to",
    "press and hold",
    "switch viewport orientation",
    "reload",
)
CASE_ID_RE = re.compile(r"^V\d+\.\d+$")
QUOTED_ID_RE = re.compile(r'^\s*id:\s*"([a-z0-9-]+)"\s*,?\s*$')
TAB_KEYS_RE = re.compile(r"const TAB_KEYS[^=]*=\s*\[([^\]]*)\]")
QUOTED_STR_RE = re.compile(r'"([a-z0-9_-]+)"')
EDGE_KEY_RE = re.compile(r"^\s*([a-z_]+):\s*\{")


def _load_yaml(path: Path):
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML is required (part of the repo's [dev] extras).")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# --- Tier one enumerators ---------------------------------------------------


def enumerate_lenses(lenses_dir: Path, findings: list[str]) -> dict[str, list[str]]:
    """Map lens id -> question ids, parsed from the lens definition files.

    Each lens file must yield exactly one lens id (a quoted `id:` followed
    within two lines by `label:`) and at least one question id (a quoted `id:`
    followed within two lines by `question:`). Anything else is a loud parse
    failure, not a silent shrug.
    """
    lenses: dict[str, list[str]] = {}
    files = sorted(
        f
        for f in lenses_dir.glob("*.ts")
        if f.name not in ("registry.ts", "index.ts") and not f.name.endswith(".test.ts")
    )
    if not files:
        findings.append(f"tier1: no lens definition files found in {lenses_dir}")
        return lenses
    for f in files:
        lines = f.read_text(encoding="utf-8").splitlines()
        lens_ids: list[str] = []
        question_ids: list[str] = []
        for i, line in enumerate(lines):
            m = QUOTED_ID_RE.match(line)
            if not m:
                continue
            lookahead = " ".join(lines[i + 1 : i + 3])
            if "question:" in lookahead:
                question_ids.append(m.group(1))
            elif "label:" in lookahead:
                lens_ids.append(m.group(1))
        if len(lens_ids) != 1 or not question_ids:
            findings.append(
                f"tier1: enumerator could not parse {f.name}: expected exactly "
                f"one lens id and at least one question id, got lens ids "
                f"{lens_ids} and {len(question_ids)} question ids. If the lens "
                f"source style changed, update gui-plan-check.py in the same PR."
            )
            continue
        lenses[lens_ids[0]] = question_ids
    return lenses


def enumerate_tabs(detail_panel: Path, findings: list[str]) -> list[str]:
    m = TAB_KEYS_RE.search(detail_panel.read_text(encoding="utf-8"))
    tabs = QUOTED_STR_RE.findall(m.group(1)) if m else []
    if not tabs:
        findings.append(
            f"tier1: could not parse TAB_KEYS from {detail_panel.name}; update "
            "gui-plan-check.py alongside the source change."
        )
    return tabs


def enumerate_edge_types(layout: Path, findings: list[str]) -> list[str]:
    types: list[str] = []
    inside = False
    for line in layout.read_text(encoding="utf-8").splitlines():
        if "const EDGE_STYLES" in line:
            inside = True
            continue
        if inside:
            if line.strip().startswith("}"):
                break
            m = EDGE_KEY_RE.match(line)
            if m:
                types.append(m.group(1))
    if not types:
        findings.append(
            f"tier1: could not parse EDGE_STYLES from {layout.name}; update "
            "gui-plan-check.py alongside the source change."
        )
    return types


# --- Plan loading -----------------------------------------------------------


def load_plan(plan_dir: Path, dataset_keys: set[str], findings: list[str]):
    """Load plan case files; validate case shape; return (cases, covers)."""
    cases: list[dict] = []
    case_files = sorted(plan_dir.glob("V*.yaml"))
    for f in case_files:
        content = _load_yaml(f)
        if not isinstance(content, list):
            findings.append(f"plan: {f.name} is not a YAML list of cases")
            continue
        for case in content:
            case["_file"] = f.name
            cases.append(case)
    seen_ids: set[str] = set()
    covers: set[str] = set()
    for case in cases:
        cid = str(case.get("id", "<missing id>"))
        where = f"{case.get('_file')}:{cid}"
        if not CASE_ID_RE.match(cid):
            findings.append(f"plan: {where}: id must match V<n>.<n>")
        if cid in seen_ids:
            findings.append(f"plan: duplicate case id {cid}")
        seen_ids.add(cid)
        if case.get("viewport") not in VIEWPORTS:
            findings.append(f"plan: {where}: viewport must be one of {sorted(VIEWPORTS)}")
        if dataset_keys and case.get("dataset") not in dataset_keys:
            findings.append(
                f"plan: {where}: dataset '{case.get('dataset')}' not in datasets.yaml"
            )
        steps = case.get("steps")
        if not isinstance(steps, list) or not steps:
            findings.append(f"plan: {where}: steps must be a non-empty list")
            steps = []
        for n, step in enumerate(steps, 1):
            text = str(step).strip().lower()
            if not text.startswith(ACTION_VERBS):
                findings.append(
                    f"plan: {where}: step {n} does not begin with a closed-"
                    f"vocabulary verb {ACTION_VERBS}: {str(step)[:80]!r}"
                )
        if not isinstance(case.get("pass_when"), list) or not case.get("pass_when"):
            findings.append(f"plan: {where}: pass_when must be a non-empty list")
        if case.get("evidence") not in EVIDENCE_KINDS:
            findings.append(
                f"plan: {where}: evidence must be one of {sorted(EVIDENCE_KINDS)}"
            )
        for token in case.get("covers") or []:
            covers.add(str(token))
    return cases, covers


def load_waivers(plan_dir: Path, findings: list[str]) -> dict[str, str]:
    path = plan_dir / "waivers.yaml"
    if not path.exists():
        return {}
    content = _load_yaml(path) or []
    waivers: dict[str, str] = {}
    if not isinstance(content, list):
        findings.append("plan: waivers.yaml is not a YAML list")
        return waivers
    for entry in content:
        token = str(entry.get("token", ""))
        reason = str(entry.get("reason", "")).strip()
        if not token or not reason:
            findings.append(f"plan: waivers.yaml entry missing token or reason: {entry}")
            continue
        waivers[token] = reason
    return waivers


# --- The check --------------------------------------------------------------


def run_check(repo_root: Path, bootstrap_ok: bool, list_only: bool) -> int:
    viewer = repo_root / "viewer"
    gui = viewer / "tests" / "gui"
    plan_dir = gui / "plan"
    components_dir = viewer / "src" / "components"
    findings: list[str] = []

    lenses = enumerate_lenses(viewer / "src" / "lenses", findings)
    tabs = enumerate_tabs(components_dir / "DetailPanel.tsx", findings)
    edge_types = enumerate_edge_types(viewer / "src" / "utils" / "layout.ts", findings)

    tier1: set[str] = set()
    for lens_id, question_ids in lenses.items():
        tier1.add(f"lens:{lens_id}")
        for qid in question_ids:
            tier1.add(f"subview:{lens_id}/{qid}")
    tier1.update(f"tab:{t}" for t in tabs)
    tier1.update(f"edge:{t}" for t in edge_types)

    datasets_yaml = gui / "datasets.yaml"
    dataset_keys = set()
    if datasets_yaml.exists():
        dataset_keys = set((_load_yaml(datasets_yaml).get("datasets") or {}).keys())
    else:
        findings.append(f"missing {datasets_yaml.relative_to(repo_root)}")

    surface_yaml = gui / "surface.yaml"
    surfaces: dict[str, str] = {}
    ignored_files: dict[str, str] = {}
    if surface_yaml.exists():
        manifest = _load_yaml(surface_yaml) or {}
        for entry in manifest.get("surfaces") or []:
            surfaces[str(entry["component"])] = str(entry["file"])
        for entry in manifest.get("ignore") or []:
            ignored_files[str(entry["file"])] = str(entry.get("reason", ""))
    else:
        findings.append(f"missing {surface_yaml.relative_to(repo_root)}")

    if list_only:
        for token in sorted(tier1):
            print(token)
        for name in sorted(surfaces):
            print(f"component:{name}")
        return 0

    case_files = sorted(plan_dir.glob("V*.yaml")) if plan_dir.is_dir() else []
    if not case_files:
        banner = (
            "gui-plan-check: NO PLAN CASE FILES under viewer/tests/gui/plan/. "
            "Every enumerated surface is uncovered."
        )
        if bootstrap_ok:
            print(f"{banner}\nBOOTSTRAP MODE (--bootstrap-ok): passing anyway. "
                  "This flag must be removed from CI in the PR that lands the plan.")
            return 0
        print(banner)
        return 1

    cases, covers = load_plan(plan_dir, dataset_keys, findings)
    waivers = load_waivers(plan_dir, findings)

    # Tier one: every enumerated surface referenced or explicitly waived.
    for token in sorted(tier1):
        if token not in covers and token not in waivers:
            findings.append(f"tier1: no plan reference or waiver for {token}")
    # Phantom references and waivers (typo protection): every tier-1-shaped
    # token used anywhere must exist in the enumeration.
    for token in sorted(covers | set(waivers)):
        kind = token.split(":", 1)[0]
        if kind in ("lens", "subview", "tab", "edge") and token not in tier1:
            findings.append(f"tier1: token {token} does not match any enumerated surface")

    # Tier two: manifest vs plan, both directions.
    for name in sorted(surfaces):
        token = f"component:{name}"
        if token not in covers and token not in waivers:
            findings.append(f"tier2: surface {name} has no plan reference or waiver")
    for token in sorted(covers | set(waivers)):
        if token.startswith("component:") and token.split(":", 1)[1] not in surfaces:
            findings.append(
                f"tier2: token {token} names a component absent from surface.yaml"
            )

    # Tier two: the file sweep. Every component file is in the manifest or the
    # ignore list; every manifest/ignore path exists; no file is in both.
    actual_files = {
        str(p.relative_to(components_dir))
        for p in components_dir.rglob("*.tsx")
    }
    manifest_files = set(surfaces.values())
    for rel in sorted(actual_files):
        if rel not in manifest_files and rel not in ignored_files:
            findings.append(
                f"tier2: {rel} is in neither surface.yaml nor its ignore list "
                "(a new surface cannot land invisibly)"
            )
    for rel in sorted(manifest_files | set(ignored_files)):
        if rel not in actual_files:
            findings.append(f"tier2: surface.yaml references missing file {rel}")
    for rel in sorted(manifest_files & set(ignored_files)):
        findings.append(f"tier2: {rel} is in both surfaces and ignore")

    # Stale waivers: a waived token that is also covered should drop the waiver.
    for token in sorted(set(waivers) & covers):
        findings.append(f"waiver: {token} is waived but also covered; remove the waiver")

    for token, reason in sorted(waivers.items()):
        print(f"WAIVED (visible decision, not a gap): {token}: {reason}")

    if findings:
        print(f"\ngui-plan-check: {len(findings)} finding(s):")
        for finding in findings:
            print(f"  - {finding}")
        return 1

    n_cases = len(cases)
    print(
        f"gui-plan-check: clean. {len(tier1)} tier-1 surfaces, "
        f"{len(surfaces)} manifest surfaces, {len(ignored_files)} ignored files, "
        f"{n_cases} plan cases, {len(waivers)} waivers."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--bootstrap-ok",
        action="store_true",
        help="Exit 0 when no plan case files exist yet (harness-PR window only).",
    )
    parser.add_argument(
        "--list", action="store_true", help="Print enumerated surface tokens and exit."
    )
    args = parser.parse_args(argv)
    return run_check(args.repo_root.resolve(), args.bootstrap_ok, args.list)


if __name__ == "__main__":
    sys.exit(main())
