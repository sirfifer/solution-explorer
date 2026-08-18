#!/usr/bin/env python3
"""Score a Comprehension Review run, and compare it with a previous one.

Design authority: docs/quality/COMPREHENSION-REVIEW.md.

The review used to produce a letter ("B+ from all three personas"), which is not
comparable, not trackable, and cannot tell an improvement in the product from an
easier subject. This turns a run into numbers with the rules that make them mean
something:

  - Scores are comparable only WITHIN a charter version. Comparing across
    versions without a recorded offset is refused, not warned about.
  - The result of a run is the SET of three persona scores, never their average,
    because the personas measure different things and an average hides the one
    that failed.
  - Trust incidents and blocked paths are counted, never scored away. A run can
    score well and still have shipped a lie.

Usage:
    comprehension-score.py score <run-dir>
    comprehension-score.py compare <run-dir> <baseline-run-dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "docs" / "quality" / "scorecard.schema.json"

DIMENSIONS = [
    "orientation", "model_accuracy", "navigation_efficiency",
    "trust", "unaided_recovery", "advertised_paths",
]
MAX_PER_DIMENSION = 4
MAX_TOTAL = len(DIMENSIONS) * MAX_PER_DIMENSION
PERSONAS = ["P1", "P2", "P3"]
PERSONA_NAMES = {
    "P1": "senior engineer, unfamiliar language",
    "P2": "non-coding executive",
    "P3": "staff engineer, AI power user",
}


class ScoreError(Exception):
    pass


def _validate(card: dict, path: Path) -> None:
    """Structural checks, plus full schema validation where jsonschema exists."""
    required = [
        "charter_version", "subject", "run_date", "persona",
        "dimensions", "trust_incidents", "blocked_paths", "battery",
    ]
    for key in required:
        if key not in card:
            raise ScoreError(f"{path.name}: missing required key {key!r}")
    if card["persona"] not in PERSONAS:
        raise ScoreError(f"{path.name}: persona must be one of {PERSONAS}")
    for dim in DIMENSIONS:
        node = card["dimensions"].get(dim)
        if node is None:
            raise ScoreError(f"{path.name}: missing dimension {dim!r}")
        score = node.get("score")
        if not isinstance(score, int) or not 0 <= score <= MAX_PER_DIMENSION:
            raise ScoreError(f"{path.name}: {dim}.score must be an integer 0 to {MAX_PER_DIMENSION}")
        # A score with no evidence is an opinion, and the whole point of this
        # instrument is that it is not one.
        if not str(node.get("evidence") or "").strip():
            raise ScoreError(f"{path.name}: {dim} has a score but no evidence")
    if len(card["battery"]) != 5:
        raise ScoreError(f"{path.name}: the battery is five questions, got {len(card['battery'])}")

    try:
        import jsonschema  # type: ignore
    except Exception:
        return
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(
        jsonschema.Draft7Validator(schema).iter_errors(card),
        key=lambda e: list(e.absolute_path),
    )
    if errors:
        joined = "; ".join(
            f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in errors
        )
        raise ScoreError(f"{path.name}: schema: {joined}")


def load_run(run_dir: Path) -> dict:
    """Every scorecard in a run directory, keyed by persona."""
    cards: dict[str, dict] = {}
    versions: set[str] = set()
    subjects: set[str] = set()
    for path in sorted(run_dir.glob("*.json")):
        if path.name.startswith("PROFILE"):
            continue
        card = json.loads(path.read_text(encoding="utf-8"))
        if "persona" not in card:
            continue
        _validate(card, path)
        if card["persona"] in cards:
            raise ScoreError(f"two scorecards for persona {card['persona']}")
        cards[card["persona"]] = card
        versions.add(card["charter_version"])
        subjects.add(card["subject"])
    if not cards:
        raise ScoreError(f"no scorecards found in {run_dir}")
    if len(versions) > 1:
        raise ScoreError(f"a run mixes charter versions: {sorted(versions)}")
    if len(subjects) > 1:
        raise ScoreError(f"a run mixes subjects: {sorted(subjects)}")
    missing = [p for p in PERSONAS if p not in cards]
    profile_path = run_dir / "PROFILE.json"
    return {
        "cards": cards,
        "charter_version": versions.pop(),
        "subject": subjects.pop(),
        "missing_personas": missing,
        "profile": json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else None,
    }


def total(card: dict) -> int:
    return sum(card["dimensions"][d]["score"] for d in DIMENSIONS)


def summarize(run: dict) -> dict:
    cards = run["cards"]
    return {
        "subject": run["subject"],
        "charter_version": run["charter_version"],
        "scores": {p: total(c) for p, c in cards.items()},
        "trust_incidents": {p: len(c["trust_incidents"]) for p, c in cards.items()},
        "high_severity_incidents": {
            p: sum(1 for i in c["trust_incidents"] if i.get("severity") == "high")
            for p, c in cards.items()
        },
        "blocked_paths": {p: len(c["blocked_paths"]) for p, c in cards.items()},
        "battery": {
            p: {v: sum(1 for q in c["battery"] if q["verdict"] == v)
                for v in ("correct", "partial", "wrong", "unscoreable")}
            for p, c in cards.items()
        },
        "missing_personas": run["missing_personas"],
    }


def render(summary: dict, run: dict) -> str:
    lines: list[str] = []
    lines.append(f"Comprehension Review: {summary['subject']} ({summary['charter_version']})")
    lines.append("")
    lines.append(f"{'Persona':<40} {'Score':>7} {'Battery':>22} {'Trust':>7} {'Blocked':>8}")
    for p in PERSONAS:
        if p not in summary["scores"]:
            lines.append(f"{p + ' ' + PERSONA_NAMES[p]:<40} {'MISSING':>7}")
            continue
        b = summary["battery"][p]
        battery = f"{b['correct']}c/{b['partial']}p/{b['wrong']}w/{b['unscoreable']}u"
        high = summary["high_severity_incidents"][p]
        trust = f"{summary['trust_incidents'][p]}" + (f" ({high} high)" if high else "")
        lines.append(
            f"{p + ' ' + PERSONA_NAMES[p]:<40} "
            f"{str(total(run['cards'][p])) + '/' + str(MAX_TOTAL):>7} "
            f"{battery:>22} {trust:>7} {summary['blocked_paths'][p]:>8}"
        )
    lines.append("")
    # The set, never the average. Stated so nobody is tempted to average it later.
    lines.append("Reported as the SET of persona scores. An average would hide the one that failed.")
    if summary["missing_personas"]:
        lines.append(f"INCOMPLETE RUN: no scorecard for {', '.join(summary['missing_personas'])}")
    if run.get("profile") is None:
        lines.append(
            "NO PROFILE.json: without a subject-difficulty profile this score "
            "cannot be compared with a different subject."
        )
    return "\n".join(lines)


def compare(run: dict, baseline: dict) -> tuple[str, bool]:
    """Rendered comparison, plus whether comparing is legitimate at all."""
    lines: list[str] = []
    legitimate = True
    if run["charter_version"] != baseline["charter_version"]:
        lines.append(
            f"REFUSED: charter versions differ ({baseline['charter_version']} then "
            f"{run['charter_version']}). Re-run the previous subject on the new "
            f"version to establish the offset first; otherwise an instrument "
            f"change is indistinguishable from a product regression."
        )
        return "\n".join(lines), False
    same_subject = run["subject"] == baseline["subject"]
    lines.append(
        f"{baseline['subject']} -> {run['subject']} ({run['charter_version']})"
        + ("" if same_subject else "   DIFFERENT SUBJECTS")
    )
    if not same_subject:
        lines.append(
            "Different subjects: a delta here mixes the product changing with "
            "the subject being harder. Read it against PROFILE.json, not alone."
        )
        legitimate = False
    lines.append("")
    for p in PERSONAS:
        if p not in run["cards"] or p not in baseline["cards"]:
            lines.append(f"{p}: not comparable (missing on one side)")
            continue
        before, after = total(baseline["cards"][p]), total(run["cards"][p])
        delta = after - before
        arrow = "same" if delta == 0 else (f"+{delta}" if delta > 0 else str(delta))
        worse = [
            d for d in DIMENSIONS
            if run["cards"][p]["dimensions"][d]["score"] < baseline["cards"][p]["dimensions"][d]["score"]
        ]
        line = f"{p} {PERSONA_NAMES[p]:<38} {before}/{MAX_TOTAL} -> {after}/{MAX_TOTAL}  ({arrow})"
        if worse:
            line += f"   REGRESSED: {', '.join(worse)}"
        lines.append(line)
    tb = sum(len(c["trust_incidents"]) for c in baseline["cards"].values())
    tr = sum(len(c["trust_incidents"]) for c in run["cards"].values())
    lines.append("")
    lines.append(f"Trust incidents: {tb} -> {tr}")
    return "\n".join(lines), legitimate


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score", help="score one run directory")
    s.add_argument("run_dir")
    s.add_argument("--json", action="store_true", help="emit the summary as JSON")
    c = sub.add_parser("compare", help="compare a run against a baseline run")
    c.add_argument("run_dir")
    c.add_argument("baseline_dir")
    args = parser.parse_args(argv)

    try:
        run = load_run(Path(args.run_dir))
        if args.cmd == "score":
            summary = summarize(run)
            print(json.dumps(summary, indent=2) if args.json else render(summary, run))
            return 1 if summary["missing_personas"] else 0
        baseline = load_run(Path(args.baseline_dir))
        text, legitimate = compare(run, baseline)
        print(text)
        return 0 if legitimate else 1
    except (ScoreError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
