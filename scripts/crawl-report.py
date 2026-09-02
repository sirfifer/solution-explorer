#!/usr/bin/env python3
"""Render a crawl run's run.json into a plain-English REPORT.md.

The crawl (viewer/tests/crawl/) already writes a full machine record to
run.json as it runs (viewer/tests/crawl/testboard-reporter.ts). This script
does not run anything; it reads that record after the fact and writes a
report a person can act on without opening JSON. The design authority is
docs/testing/GUI-CRAWL-DESIGN.md, which specifies the contract this follows:

  One plain paragraph first, readable by someone who is not an engineer: what
  is solid, what is broken, whether the product is demoable today. Then the
  findings, grouped by rule id, with severity, instance counts and up to five
  examples each. Then the coverage lines the suite reported about its own
  reach. Then a per-case table. Counts are stated plainly ("13 of 13 cases
  passed"), never rounded up. A run still in progress is reported as
  unfinished, not as a result.

Usage:
    python3 scripts/crawl-report.py <run-dir>
    python3 scripts/crawl-report.py --latest

<run-dir> is a directory under .testboard/runs containing run.json.
--latest picks the newest directory (by name, which sorts chronologically
because the reporter stamps it with an ISO timestamp) whose name contains
"-crawl-". Writes <run-dir>/REPORT.md and prints it to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent

# The GUI regression strategy's banned phrases, restated here so a bug in this
# renderer cannot quietly reintroduce them. Checked, not just avoided: see
# _assert_no_rounding_up below.
BANNED_PHRASES = ("mostly working", "minor issues remain")

SEVERITY_RANK = {"error": 2, "warn": 1}


def _runs_root() -> Path:
    return Path(os.environ.get("TESTBOARD_DIR") or (REPO_ROOT / ".testboard" / "runs"))


def find_latest(runs_root: Path) -> Path:
    """The newest directory under runs_root that looks like a crawl run.

    Directory names are `<ISO-stamp>-crawl-<subject>`, colons and dots
    replaced with "-" (testboard-reporter.ts's pathSafe/stamp), so sorting by
    name gives chronological order without needing to touch mtimes.
    """
    if not runs_root.is_dir():
        sys.exit(f"error: no runs directory at {runs_root}")
    candidates = sorted(
        (p for p in runs_root.iterdir() if p.is_dir() and "-crawl-" in p.name),
        key=lambda p: p.name,
    )
    if not candidates:
        sys.exit(f"error: no run directory containing '-crawl-' under {runs_root}")
    return candidates[-1]


def load_record(run_dir: Path) -> dict:
    record_path = run_dir / "run.json"
    if not record_path.is_file():
        sys.exit(f"error: no run.json at {record_path}")
    try:
        return json.loads(record_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"error: {record_path} is not valid JSON: {exc}")


def _fmt_duration_ms(ms: Optional[float]) -> str:
    if ms is None:
        return "-"
    try:
        return f"{float(ms) / 1000:.1f}s"
    except (TypeError, ValueError):
        return "-"


def _is_remote(record: dict) -> bool:
    """Whether this run targeted the published site rather than a local serve root.

    Best-effort: the reporter records base_url and data_dir but has no
    explicit "remote" flag, so this reads the two signals the design doc
    defines: a base_url that is not a loopback origin, or a data_dir under
    the remote-data cache the crawl's globalSetup writes for remote targets.
    """
    base_url = str(record.get("base_url") or "")
    data_dir = str(record.get("data_dir") or "")
    if "remote-data" in data_dir:
        return True
    if base_url and not (
        base_url.startswith("http://127.0.0.1")
        or base_url.startswith("http://localhost")
        or base_url.startswith("https://127.0.0.1")
        or base_url.startswith("https://localhost")
    ):
        return True
    return False


def _profile_label(record: dict) -> str:
    """Best-effort profile/budget label.

    If the reporter records an explicit "profile" field, use it verbatim.
    Otherwise infer from the budget field it has always recorded: the quick
    profile sets CRAWL_MAX_COMPONENTS, the full profile leaves it unset, and
    the reporter's own default for "unset" is the literal string
    "0 (full sweep)".
    """
    profile = record.get("profile")
    budget = record.get("budget")
    budget_text = "unknown" if budget is None else str(budget)
    if profile:
        return f"{profile} (budget: {budget_text})"
    if budget_text in ("0 (full sweep)", "0", "unknown"):
        return f"full, no component budget (budget: {budget_text})"
    return f"quick, inferred from budget (budget: {budget_text})"


def _derive_project(case: dict) -> Optional[str]:
    """The Playwright project a case ran under.

    Preferred: a "project" key the reporter records directly. Failing that,
    two fallbacks over the case title, since the reporter joins only the
    last two titlePath segments (describe + test) today: a leading
    "<project> › ..." prefix if a future reporter widens that join, or an
    "@mobile" / "@desktop" tag Playwright test titles carry by convention
    (GUI-CRAWL-DESIGN.md: "every test tags itself @desktop, @mobile, or
    both"). Returns None, rendered as "-", when nothing says.
    """
    project = case.get("project")
    if project:
        return str(project)
    title = case.get("title") or ""
    parts = title.split(" › ")
    if len(parts) >= 3 and parts[0].strip().lower() in ("desktop", "mobile"):
        return parts[0].strip()
    for tag in ("mobile", "desktop"):
        if f"@{tag}" in title:
            return tag
    return None


def _group_findings(findings: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for f in findings or []:
        rule = f.get("rule") or f.get("id") or "unknown"
        groups[rule].append(f)

    rows = []
    for rule, items in groups.items():
        severity = "warn"
        for item in items:
            if SEVERITY_RANK.get(item.get("severity"), 0) > SEVERITY_RANK.get(severity, 0):
                severity = item.get("severity") or severity
        title = next((i.get("title") for i in items if i.get("title")), rule)
        instances = sum(int(i.get("instances") or 0) for i in items)
        examples: list[str] = []
        for item in items:
            for ex in item.get("examples") or []:
                ex_text = str(ex)
                if ex_text not in examples:
                    examples.append(ex_text)
        rows.append({
            "rule": rule,
            "severity": severity,
            "title": title,
            "instances": instances,
            "distinct": len(items),
            "examples": examples[:5],
        })
    rows.sort(key=lambda r: (-SEVERITY_RANK.get(r["severity"], 0), r["rule"]))
    return rows


def _verdict_paragraph(record: dict) -> str:
    status = record.get("status")
    total = record.get("total") or 0
    completed = record.get("completed") or 0

    if status == "running":
        return (
            f"This crawl run has not finished. {completed} of {total} cases have "
            "completed so far. What follows is a snapshot of a run in progress, "
            "not a result: rerun this report after the run ends before drawing "
            "any conclusion from it."
        )

    passed = record.get("passed") or 0
    failed = record.get("failed") or 0
    skipped = record.get("skipped") or 0
    ft = record.get("finding_totals") or {}
    errors = int(ft.get("errors") or 0)
    error_instances = int(ft.get("error_instances") or 0)
    warnings = int(ft.get("warnings") or 0)
    warning_instances = int(ft.get("warning_instances") or 0)

    sentences = [f"{passed} of {total} cases passed."]
    if failed:
        sentences.append(f"{failed} of {total} cases failed.")
    if skipped:
        sentences.append(f"{skipped} of {total} cases were skipped.")

    if errors:
        sentences.append(
            f"{errors} distinct error-level finding(s) were recorded, "
            f"{error_instances} instance(s) in total."
        )
    else:
        sentences.append("No error-level findings were recorded.")

    if warnings:
        sentences.append(
            f"{warnings} distinct warning-level finding(s) were recorded, "
            f"{warning_instances} instance(s) in total."
        )
    elif errors == 0:
        sentences.append("No warnings were recorded either.")

    if failed == 0 and errors == 0:
        if warnings:
            sentences.append(
                "Nothing failed and no errors were found; the warnings above are "
                "the only open items, and the product is demoable today."
            )
        else:
            sentences.append("The product is demoable today.")
    else:
        broken = []
        if failed:
            broken.append(f"{failed} failing case(s)")
        if errors:
            broken.append(f"{errors} error-level finding(s)")
        sentences.append(
            f"The product is not demoable today: {' and '.join(broken)} need to "
            "be fixed first."
        )

    return " ".join(sentences)


def _assert_no_rounding_up(text: str) -> None:
    lowered = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered:
            raise AssertionError(
                f"crawl-report.py generated a banned phrase ({phrase!r}); this "
                "is a bug in the renderer, not something to patch around"
            )


def build_report(record: dict, run_dir: Path) -> str:
    status = record.get("status") or "unknown"
    subject = record.get("subject") or "unknown"
    unfinished = status == "running"

    lines: list[str] = []
    title_suffix = " (UNFINISHED, still running)" if unfinished else ""
    lines.append(f"# Crawl report: {subject}{title_suffix}")
    lines.append("")
    lines.append(_verdict_paragraph(record))
    lines.append("")

    lines.append("## Run")
    lines.append("")
    versions = record.get("versions") or {}
    dataset = versions.get("dataset") or {}
    remote = _is_remote(record)
    lines.append(f"- Run id: {record.get('id') or run_dir.name}")
    lines.append(f"- Status: {status}{' (unfinished)' if unfinished else ''}")
    lines.append(f"- Subject: {subject}")
    lines.append(f"- Started: {record.get('started_at') or '-'}")
    lines.append(f"- Ended: {record.get('ended_at') or ('still running' if unfinished else '-')}")
    lines.append(f"- Duration: {_fmt_duration_ms(record.get('duration_ms'))}")
    lines.append(f"- Base URL: {record.get('base_url') or '-'}")
    lines.append(f"- Remote target: {'yes' if remote else 'no'}")
    lines.append(f"- Profile / budget: {_profile_label(record)}")
    lines.append(f"- Viewer version: {versions.get('viewer_version') or '-'}")
    lines.append(f"- Analyzer version: {versions.get('analyzer_version') or '-'}")
    if dataset:
        lines.append(
            f"- Dataset: {dataset.get('name') or '-'}, generated "
            f"{dataset.get('generated_at') or '-'}, subject sha "
            f"{(dataset.get('subject_sha') or '-')[:12]}, "
            f"{dataset.get('components') if dataset.get('components') is not None else '-'} components"
        )
    lines.append("")

    lines.append("## Findings")
    lines.append("")
    groups = _group_findings(record.get("findings") or [])
    if not groups:
        lines.append("No findings were recorded.")
    else:
        for g in groups:
            lines.append(
                f"### `{g['rule']}` ({g['severity']}, {g['instances']} instance(s) "
                f"across {g['distinct']} case(s))"
            )
            lines.append("")
            lines.append(g["title"])
            if g["examples"]:
                lines.append("")
                lines.append("Examples:")
                for ex in g["examples"]:
                    lines.append(f"- {ex}")
            lines.append("")
    lines.append("")

    lines.append("## Coverage")
    lines.append("")
    coverage = record.get("coverage") or []
    if not coverage:
        lines.append("No coverage lines were recorded.")
    else:
        for line in coverage:
            lines.append(f"- {line}")
    lines.append("")

    cases = record.get("cases") or []
    passed = record.get("passed") or 0
    total_cases = record.get("total") or len(cases)
    lines.append(f"## Cases ({passed} of {total_cases} passed)")
    lines.append("")
    if not cases:
        lines.append("No cases have completed yet." if unfinished else "No cases were recorded.")
    else:
        lines.append("| Title | Project | Status | Duration | Message |")
        lines.append("|---|---|---|---|---|")
        for case in cases:
            project = _derive_project(case) or "-"
            message = (case.get("message") or "").replace("\n", " ").replace("|", "\\|")
            title = str(case.get("title") or "").replace("|", "\\|")
            lines.append(
                f"| {title} | {project} | {case.get('status') or '-'} | "
                f"{_fmt_duration_ms(case.get('duration_ms'))} | {message} |"
            )
    lines.append("")

    text = "\n".join(lines) + "\n"
    _assert_no_rounding_up(text)
    return text


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", nargs="?", default=None,
                        help="a directory under .testboard/runs containing run.json")
    parser.add_argument("--latest", action="store_true",
                        help="use the newest run directory whose name contains '-crawl-'")
    parser.add_argument("--runs-root", default=None,
                        help="override the directory --latest searches "
                             "(default: $TESTBOARD_DIR or .testboard/runs)")
    args = parser.parse_args(argv)

    if not args.run_dir and not args.latest:
        parser.error("pass a run directory, or --latest")
    if args.run_dir and args.latest:
        parser.error("pass a run directory OR --latest, not both")

    if args.latest:
        runs_root = Path(args.runs_root).expanduser().resolve() if args.runs_root else _runs_root()
        run_dir = find_latest(runs_root)
    else:
        run_dir = Path(args.run_dir).expanduser().resolve()
        if not run_dir.is_dir():
            sys.exit(f"error: no directory at {run_dir}")

    record = load_record(run_dir)
    report = build_report(record, run_dir)
    (run_dir / "REPORT.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
