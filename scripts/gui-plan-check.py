#!/usr/bin/env python3
"""Two-tier completeness check for the GUI regression plan.

Design authority: docs/testing/GUI-REGRESSION-STRATEGY.md (Maintainability).
Mechanized honesty in the coverage-ledger spirit: silence is the only failure
mode this tool tolerates. It cannot judge whether a case tests a surface WELL;
it makes it impossible for a surface to have no recorded disposition at all.

Tier one statically enumerates the surfaces that ARE extractable from source:
  - registered lens ids and their question (sub-view) ids from
    viewer/src/lenses/*.ts (one definition file per lens; that convention is
    load-bearing here and is cross-checked against the side-effect imports in
    lenses/index.ts, so a lens registered without its own file, or a dead
    lens file that is never imported, fails loudly),
  - DetailPanel tab keys from the TAB_KEYS array,
  - EDGE_STYLES relationship types from viewer/src/utils/layout.ts.
Any enumerated surface with zero plan references fails the check. The
enumerators are anti-rot by construction: they capture BROADLY and then
validate what they captured, so an id they cannot canonicalize into a
coverage token is a loud finding, never a silent drop; an enumerator that
parses nothing is likewise a failure.

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

Exit codes: 0 clean, 1 findings, 2 usage or unreadable input.
`--bootstrap-ok` exists only for the window between the harness PR and the
plan PR: it downgrades exactly one finding (no plan case files exist yet) and
nothing else; every structural finding still fails. The plan PR removes the
flag from CI.
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
TOKEN_KINDS = ("lens", "subview", "tab", "edge", "component")
CASE_ID_RE = re.compile(r"^V(\d+)\.\d+$")
# Broad captures, then canonical validation: an id the enumerator cannot turn
# into a coverage token is a loud finding, never a silent drop.
BROAD_ID_RE = re.compile(r'^\s*id:\s*"([^"]*)"')
QUESTION_LINE_RE = re.compile(r"^\s*question:", re.MULTILINE)
CANONICAL_ID_RE = re.compile(r"^[a-z0-9-]+$")
TAB_KEYS_RE = re.compile(r"const TAB_KEYS[^=]*=\s*\[(.*?)\]", re.DOTALL)
QUOTED_STR_RE = re.compile(r"[\"']([^\"']+)[\"']")
EDGE_KEY_RE = re.compile(r"^\s*([A-Za-z0-9_$]+):")
CANONICAL_EDGE_RE = re.compile(r"^[a-z0-9_]+$")
SIDE_EFFECT_IMPORT_RE = re.compile(r'^import\s+"\./([A-Za-z0-9_-]+)";', re.MULTILINE)


def _load_yaml(path: Path):
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML is required (part of the repo's [dev] extras).")
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as exc:
        print(f"Unreadable YAML in {path}: {exc}", file=sys.stderr)
        sys.exit(2)


# --- Tier one enumerators ---------------------------------------------------


def enumerate_lenses(lenses_dir: Path, findings: list[str]) -> dict[str, list[str]]:
    """Map lens id -> question ids, parsed from the lens definition files.

    Anti-rot contract, three loud failure modes: (1) a definition file that
    does not yield exactly one lens id and at least one question id; (2) a
    question count that disagrees with an independent count of `question:`
    lines in the same file (a silently dropped sub-view); (3) a mismatch
    between the definition files and the side-effect imports in index.ts (a
    registered lens with no file, or a dead file never registered).
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
        text = f.read_text(encoding="utf-8")
        lines = text.splitlines()
        lens_ids: list[str] = []
        question_ids: list[str] = []
        for i, line in enumerate(lines):
            m = BROAD_ID_RE.match(line)
            if not m:
                continue
            captured = m.group(1)
            lookahead = " ".join(lines[i + 1 : i + 3])
            is_question = "question:" in lookahead
            is_lens = not is_question and "label:" in lookahead
            if not is_question and not is_lens:
                continue
            if not CANONICAL_ID_RE.match(captured):
                findings.append(
                    f"tier1: {f.name}: id \"{captured}\" cannot be canonicalized "
                    "into a coverage token (expected lowercase [a-z0-9-]); "
                    "update gui-plan-check.py or the source in the same PR."
                )
                continue
            (question_ids if is_question else lens_ids).append(captured)
        independent_question_count = len(QUESTION_LINE_RE.findall(text))
        if len(question_ids) != independent_question_count:
            findings.append(
                f"tier1: {f.name}: parsed {len(question_ids)} question ids but "
                f"the file has {independent_question_count} `question:` lines; "
                "an enumerated sub-view was silently dropped. Update "
                "gui-plan-check.py alongside the source change."
            )
        if len(lens_ids) != 1 or not question_ids:
            findings.append(
                f"tier1: enumerator could not parse {f.name}: expected exactly "
                f"one lens id and at least one question id, got lens ids "
                f"{lens_ids} and {len(question_ids)} question ids. If the lens "
                f"source style changed, update gui-plan-check.py in the same PR."
            )
            continue
        lenses[lens_ids[0]] = question_ids

    index_ts = lenses_dir / "index.ts"
    if index_ts.exists():
        imported = set(SIDE_EFFECT_IMPORT_RE.findall(index_ts.read_text(encoding="utf-8")))
        file_stems = {f.stem for f in files}
        for missing_file in sorted(imported - file_stems):
            findings.append(
                f"tier1: lenses/index.ts imports ./{missing_file} but no such "
                "definition file was enumerated (a lens registered outside the "
                "one-file-per-lens convention is invisible to this check)."
            )
        for dead_file in sorted(file_stems - imported):
            findings.append(
                f"tier1: lens file {dead_file}.ts is never imported by "
                "lenses/index.ts (a dead lens file would demand plan coverage "
                "falsely)."
            )
    else:
        findings.append("tier1: lenses/index.ts not found; registration cross-check impossible")
    return lenses


def enumerate_tabs(detail_panel: Path, findings: list[str]) -> list[str]:
    text = detail_panel.read_text(encoding="utf-8")
    m = TAB_KEYS_RE.search(text)
    if not m:
        findings.append(
            f"tier1: could not find the TAB_KEYS array in {detail_panel.name}; "
            "update gui-plan-check.py alongside the source change."
        )
        return []
    body = m.group(1)
    tabs = QUOTED_STR_RE.findall(body)
    independent_count = len([t for t in body.split(",") if t.strip()])
    if not tabs or len(tabs) != independent_count:
        findings.append(
            f"tier1: TAB_KEYS parse mismatch in {detail_panel.name}: "
            f"{len(tabs)} quoted keys vs {independent_count} comma-separated "
            "entries; a tab was silently dropped. Update gui-plan-check.py "
            "alongside the source change."
        )
    return tabs


def enumerate_edge_types(layout: Path, findings: list[str]) -> list[str]:
    """Brace-depth walk of the EDGE_STYLES object literal.

    Keys are captured broadly at depth one and validated; a key that cannot be
    canonicalized is a loud finding. Multi-line values are handled by the
    depth tracking, so a formatter rewrap cannot truncate the enumeration.
    """
    types: list[str] = []
    depth = 0
    started = False
    for line in layout.read_text(encoding="utf-8").splitlines():
        if not started:
            if "const EDGE_STYLES" in line:
                started = True
                depth = line.count("{") - line.count("}")
            continue
        stripped = line.strip()
        if depth == 1 and not stripped.startswith("//"):
            m = EDGE_KEY_RE.match(line)
            if m:
                key = m.group(1)
                if CANONICAL_EDGE_RE.match(key):
                    types.append(key)
                else:
                    findings.append(
                        f"tier1: EDGE_STYLES key \"{key}\" cannot be "
                        "canonicalized into a coverage token; update "
                        "gui-plan-check.py or the source in the same PR."
                    )
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            break
    if started and depth > 0:
        findings.append(
            f"tier1: EDGE_STYLES object in {layout.name} never closed at the "
            "tracked depth; enumeration may be truncated. Update "
            "gui-plan-check.py alongside the source change."
        )
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
    for f in sorted(plan_dir.glob("V*.yaml")):
        content = _load_yaml(f)
        if not isinstance(content, list):
            findings.append(f"plan: {f.name} is not a YAML list of cases")
            continue
        for case in content:
            if not isinstance(case, dict):
                findings.append(f"plan: {f.name}: case entry is not a mapping: {str(case)[:60]!r}")
                continue
            case["_file"] = f.name
            cases.append(case)
    seen_ids: set[str] = set()
    covers: set[str] = set()
    for case in cases:
        cid = str(case.get("id", "<missing id>"))
        fname = str(case.get("_file"))
        where = f"{fname}:{cid}"
        id_match = CASE_ID_RE.match(cid)
        if not id_match:
            findings.append(f"plan: {where}: id must match V<n>.<n>")
        else:
            file_vector = re.match(r"^V(\d+)\.yaml$", fname)
            if file_vector and file_vector.group(1) != id_match.group(1):
                findings.append(
                    f"plan: {where}: case id belongs to vector V{id_match.group(1)} "
                    f"but lives in {fname}; the runner shards by file, so this "
                    "case would execute in the wrong shard."
                )
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
        raw_covers = case.get("covers")
        if raw_covers is None:
            continue
        if not isinstance(raw_covers, list):
            findings.append(
                f"plan: {where}: covers must be a list of tokens, got "
                f"{type(raw_covers).__name__}"
            )
            continue
        for token in raw_covers:
            token = str(token).strip()
            kind = token.split(":", 1)[0] if ":" in token else ""
            if kind not in TOKEN_KINDS:
                findings.append(
                    f"plan: {where}: covers token {token!r} does not start "
                    f"with a known kind {TOKEN_KINDS}"
                )
                continue
            covers.add(token)
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
        if not isinstance(entry, dict):
            findings.append(f"plan: waivers.yaml entry is not a mapping: {str(entry)[:60]!r}")
            continue
        token = str(entry.get("token", "")).strip()
        reason = str(entry.get("reason", "")).strip()
        if not token or not reason:
            findings.append(f"plan: waivers.yaml entry missing token or reason: {entry}")
            continue
        kind = token.split(":", 1)[0] if ":" in token else ""
        if kind not in TOKEN_KINDS:
            findings.append(
                f"plan: waivers.yaml token {token!r} does not start with a "
                f"known kind {TOKEN_KINDS}"
            )
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
            name = str(entry["component"])
            file = str(entry["file"])
            if name in surfaces:
                findings.append(f"tier2: duplicate surface component {name} in surface.yaml")
            if file in surfaces.values():
                findings.append(f"tier2: duplicate surface file {file} in surface.yaml")
            surfaces[name] = file
        for entry in manifest.get("ignore") or []:
            file = str(entry["file"])
            if file in ignored_files:
                findings.append(f"tier2: duplicate ignore file {file} in surface.yaml")
            ignored_files[file] = str(entry.get("reason", ""))
    else:
        findings.append(f"missing {surface_yaml.relative_to(repo_root)}")

    if list_only:
        for token in sorted(tier1):
            print(token)
        for name in sorted(surfaces):
            print(f"component:{name}")
        return 0

    # Structural tier-two checks that do not depend on the plan: the file
    # sweep. These are evaluated in EVERY mode, including bootstrap.
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

    case_files = sorted(plan_dir.glob("V*.yaml")) if plan_dir.is_dir() else []
    no_plan = not case_files
    if no_plan:
        # The one finding --bootstrap-ok may downgrade. Coverage checks are
        # meaningless without a plan, but every structural finding above still
        # stands and still fails, so a broken enumerator or a deleted manifest
        # cannot hide behind the bootstrap window.
        if not bootstrap_ok:
            findings.append(
                "plan: NO PLAN CASE FILES under viewer/tests/gui/plan/; every "
                "enumerated surface is uncovered"
            )
        else:
            print(
                "gui-plan-check: BOOTSTRAP MODE (--bootstrap-ok): no plan case "
                "files yet; coverage checks skipped, structural checks still "
                "enforced. This flag must be removed from CI in the PR that "
                "lands the plan."
            )
    else:
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
                findings.append(
                    f"tier1: token {token} does not match any enumerated surface"
                )

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

        # Stale waivers: a waived token that is also covered should drop the waiver.
        for token in sorted(set(waivers) & covers):
            findings.append(
                f"waiver: {token} is waived but also covered; remove the waiver"
            )

        for token, reason in sorted(waivers.items()):
            print(f"WAIVED (visible decision, not a gap): {token}: {reason}")

    if findings:
        print(f"\ngui-plan-check: {len(findings)} finding(s):")
        for finding in findings:
            print(f"  - {finding}")
        return 1

    if no_plan:
        return 0
    print(
        f"gui-plan-check: clean. {len(tier1)} tier-1 surfaces, "
        f"{len(surfaces)} manifest surfaces, {len(ignored_files)} ignored files, "
        f"{len(cases)} plan cases, {len(waivers)} waivers."
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
        help="Downgrade only the no-plan-files-yet finding (harness-PR window).",
    )
    parser.add_argument(
        "--list", action="store_true", help="Print enumerated surface tokens and exit."
    )
    args = parser.parse_args(argv)
    return run_check(args.repo_root.resolve(), args.bootstrap_ok, args.list)


if __name__ == "__main__":
    sys.exit(main())
