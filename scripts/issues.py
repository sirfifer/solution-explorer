#!/usr/bin/env python3
"""The issue ledger: every finding accounted for, once, and traceable to its run.

A run tells you what was wrong at one moment. It cannot tell you whether that
thing is new, whether anyone decided about it, or whether it has been wrong for
a fortnight. So findings accumulate here instead of scrolling away: one entry
per distinct problem, carrying every run that has ever seen it.

Three ideas do the work.

**Identity.** A finding's id is a fingerprint of the KIND of problem, not of one
sighting. The same broken id scheme seen in fifty components is one issue with
fifty instances, not fifty issues. That distinction is the difference between
"one thing to fix" and "a fortnight of work", and a ledger that cannot express
it is worse than no ledger.

**Nature, not just severity.** A failing check means something is not as it
should be, and that is NOT the same as something being broken. It might be a
genuine defect, or a surface we have not built yet, or a threshold set by
judgement that this subject legitimately exceeds. Calling all three "broken"
during active development is wrong and it trains people to ignore the board. So
every issue carries a nature, and the honest default is `unclassified`: nobody
has decided yet, and the ledger says so rather than guessing.

**Traceability.** Every issue records the run id that first saw it, the run id
that last saw it, and how many runs have seen it. Every run has an id already.
That pair, run id plus finding id, is the thread from a number on a dashboard
back to the exact check, the exact subject, and the exact moment.

Filing to GitHub is deliberately OPT IN and dry run by default. Issues are
outward facing and this is the owner's repository, so nothing leaves this
machine without `--file` being typed on purpose.

Usage:
    python3 scripts/issues.py sync                 # fold new run findings in
    python3 scripts/issues.py list [--open|--all]
    python3 scripts/issues.py classify <id> --nature defect --note "why"
    python3 scripts/issues.py file <id>            # DRY RUN unless --file
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.environ.get("TESTBOARD_DIR") or (REPO_ROOT / ".testboard" / "runs"))
LEDGER = RUNS_DIR.parent / "issues.json"

# What a finding IS, as opposed to how bad it is. Severity says how loud, nature
# says what kind of thing, and conflating them is what makes a board unreadable
# during active development.
NATURES = {
    "unclassified": (
        "Nobody has decided what this is yet. The honest default, and never a "
        "silent one: an unclassified issue is visible precisely so it gets "
        "looked at."
    ),
    "defect": (
        "Something is genuinely wrong and should be fixed. The product does not "
        "do what it claims."
    ),
    "unbuilt": (
        "Not broken, just not built yet. The check is correct and the surface it "
        "checks does not exist. Expected during active development, and it must "
        "not read as a defect."
    ),
    "threshold": (
        "The check fired because a judgement-set limit was exceeded, and the "
        "limit may be the thing that is wrong. Worth a decision about the "
        "threshold, not necessarily a fix."
    ),
    "subject": (
        "True of the subject rather than of our tool. Something in the analyzed "
        "codebase, not something we did. Often still worth reporting, rarely "
        "worth fixing here."
    ),
    "accepted": (
        "Understood, decided about, and deliberately left as it is. Closed by "
        "judgement rather than by a fix."
    ),
}


CLOSURE_REASONS = {
    "fixed": "Fixed: the underlying problem was corrected and the check now passes.",
    "accepted": (
        "Accepted: understood, decided about, and deliberately left as it is. "
        "Closed by judgement rather than by a fix."
    ),
    "not-reproducible": (
        "No longer reproduces: the finding stopped appearing without anyone "
        "fixing it. Worth suspicion, since a problem that vanished on its own "
        "can return on its own."
    ),
    "check-wrong": (
        "The check was wrong: the harness reported something that was not "
        "actually a problem, and the check itself was corrected."
    ),
    "duplicate": "Duplicate: the same problem is tracked under another issue.",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def load_ledger() -> dict:
    doc = _read_json(LEDGER)
    if not isinstance(doc, dict):
        return {"ledger_version": 1, "issues": {}}
    doc.setdefault("issues", {})
    return doc


def save_ledger(doc: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    doc["updated_at"] = _now()
    LEDGER.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def iter_run_findings():
    """Every finding every run has published, newest run first."""
    if not RUNS_DIR.is_dir():
        return
    for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
        record = _read_json(run_dir / "run.json")
        if not isinstance(record, dict):
            continue
        findings = record.get("findings")
        # A crawl publishes failures as cases rather than findings, so its
        # failing cases are folded in under the same model. One shape in, one
        # shape out; the ledger should not care which harness spoke.
        #
        # Restricted to harnesses that never publish findings. Applying it to
        # any record that merely LACKS them folded pre-change lint runs in under
        # a second identity, so one problem appeared twice in the ledger under
        # two ids. An identity scheme that can do that is not an identity
        # scheme.
        if not findings and (record.get("kind") or "") in ("crawl", "gui"):
            findings = [
                {
                    "id": f"{record.get('kind')}:{case.get('title')}",
                    "rule": case.get("title"),
                    "severity": "error" if case.get("status") == "failed" else "warn",
                    "title": case.get("message") or case.get("title"),
                    "instances": case.get("instances") or 1,
                    "examples": [case.get("message")] if case.get("message") else [],
                    "nature": "unclassified",
                }
                for case in record.get("cases") or []
                if case.get("status") in ("failed", "timedOut", "warned")
            ]
        for finding in findings or []:
            yield record, finding


def cmd_sync(args: argparse.Namespace) -> int:
    doc = load_ledger()
    issues = doc["issues"]
    new, updated = 0, 0

    for record, finding in iter_run_findings():
        fid = finding.get("id")
        if not fid:
            continue
        run_id = record.get("id")
        entry = issues.get(fid)
        if entry is None:
            issues[fid] = {
                "id": fid,
                "title": finding.get("title") or fid,
                "rule": finding.get("rule"),
                "severity": finding.get("severity", "error"),
                # Never inferred. A wrong classification is worse than none,
                # because it stops anyone looking again.
                "nature": finding.get("nature") or "unclassified",
                "state": "open",
                "subject": record.get("subject"),
                "kind": record.get("kind"),
                "first_seen_run": run_id,
                "last_seen_run": run_id,
                "first_seen_at": record.get("started_at"),
                "last_seen_at": record.get("started_at"),
                "runs_seen": [run_id],
                "max_instances": finding.get("instances", 1),
                "last_instances": finding.get("instances", 1),
                # The last few counts, so the board can say whether a problem is
                # getting better or worse. A single number cannot: "1,847
                # instances" reads the same whether it was 200 last week or
                # 3,000. Direction is what decides whether to escalate.
                "instance_history": [
                    {"run": run_id, "instances": finding.get("instances", 1)}
                ],
                "examples": finding.get("examples", [])[:5],
                # Who is on the hook. Never assigned automatically, because an
                # owner nobody agreed to is not an owner.
                "owner": None,
                "note": None,
                "github_issue": None,
                "case_title": finding.get("case_title") or finding.get("rule"),
                "closure_reason": None,
            }
            new += 1
        else:
            if run_id and run_id not in entry.get("runs_seen", []):
                entry.setdefault("runs_seen", []).append(run_id)
                entry["last_seen_run"] = run_id
                entry["last_seen_at"] = record.get("started_at")
                entry["last_instances"] = finding.get("instances", 1)
                entry["max_instances"] = max(
                    entry.get("max_instances", 0), finding.get("instances", 1)
                )
                history = entry.setdefault("instance_history", [])
                history.append({"run": run_id, "instances": finding.get("instances", 1)})
                del history[:-10]
                updated += 1

    runs_total = (
        sum(1 for d in RUNS_DIR.iterdir() if (d / "run.json").is_file())
        if RUNS_DIR.is_dir() else 0
    )
    doc["runs_total"] = runs_total
    for entry in issues.values():
        seen = len(entry.get("runs_seen", []))
        entry["runs_seen_count"] = seen
        entry["runs_total_at_sync"] = runs_total
        # "Seen in 3 runs" is meaningless without knowing whether there were 3
        # runs or 300. Intermittent is the one that wastes an afternoon, so it
        # must never look the same as permanent.
        entry["persistence"] = (
            "persistent" if runs_total and seen >= runs_total
            else "intermittent" if seen > 1
            else "once"
        )

    save_ledger(doc)
    print(f"issues: {len(issues)} total, {new} new, {updated} seen again "
          f"(across {runs_total} run records)")
    unclassified = sum(1 for i in issues.values() if i["nature"] == "unclassified")
    if unclassified:
        print(f"  {unclassified} still unclassified (nobody has decided what they are)")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    doc = load_ledger()
    issues = list(doc["issues"].values())
    if not args.all:
        issues = [i for i in issues if i["state"] == "open"]
    issues.sort(key=lambda i: (-i.get("max_instances", 0), i["id"]))
    if not issues:
        print("no issues recorded; run: python3 scripts/issues.py sync")
        return 0
    for issue in issues:
        seen = len(issue.get("runs_seen", []))
        print(f"[{issue['severity']:5}] [{issue['nature']:12}] {issue['id']}")
        print(f"    {issue['title'][:120]}")
        print(f"    {issue['max_instances']} instance(s) at most, seen in {seen} run(s), "
              f"subject {issue.get('subject')}")
        print(f"    first {issue.get('first_seen_run')}")
        if issue.get("note"):
            print(f"    note: {issue['note']}")
        if issue.get("github_issue"):
            print(f"    github: {issue['github_issue']}")
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    doc = load_ledger()
    issue = doc["issues"].get(args.id)
    if issue is None:
        print(f"error: no issue '{args.id}'", file=sys.stderr)
        return 1
    if args.nature not in NATURES:
        print(f"error: nature must be one of {', '.join(NATURES)}", file=sys.stderr)
        return 1
    issue["nature"] = args.nature
    if args.note:
        issue["note"] = args.note
    if args.owner:
        issue["owner"] = args.owner
    if args.closure_reason:
        if args.closure_reason not in CLOSURE_REASONS:
            print(f"error: closure reason must be one of {', '.join(CLOSURE_REASONS)}",
                  file=sys.stderr)
            return 1
        issue["closure_reason"] = args.closure_reason
    if args.state == "closed" and not issue.get("closure_reason"):
        print("error: closing an issue needs --closure-reason, since 'fixed', "
              "'accepted' and 'no longer reproduces' are different outcomes",
              file=sys.stderr)
        return 1
    if args.state:
        issue["state"] = args.state
    # A classification nobody can attribute is hard to challenge or to trust.
    issue["classified_at"] = _now()
    issue["classified_by"] = args.by or os.environ.get("USER") or "unknown"
    save_ledger(doc)
    print(f"{args.id}: nature={args.nature}" + (f", state={args.state}" if args.state else ""))
    return 0


def render_issue_body(issue: dict) -> str:
    """The narrative, written so someone who was not here can act on it."""
    lines = [
        f"**Finding id:** `{issue['id']}`",
        f"**Nature:** {issue['nature']}  ({NATURES.get(issue['nature'], '')})",
        f"**Severity:** {issue['severity']}",
        f"**Subject:** {issue.get('subject')}  (found by the `{issue.get('kind')}` harness)",
        "",
        "## What is wrong",
        "",
        issue["title"],
        "",
        "## Scale",
        "",
        f"Seen at most **{issue['max_instances']} time(s)** in a single run, "
        f"and in **{len(issue.get('runs_seen', []))} run(s)** so far.",
        "",
    ]
    if issue["max_instances"] > 1:
        lines += [
            "These are instances of ONE problem, not separate problems. The "
            "count is how often it occurs, which is a measure of blast radius "
            "rather than of how many things need fixing.",
            "",
        ]
    if issue.get("examples"):
        lines += ["## Examples", ""]
        lines += [f"- `{ex}`" for ex in issue["examples"]]
        lines += [""]
    lines += [
        "## Traceability",
        "",
        f"- First seen in run `{issue.get('first_seen_run')}` at {issue.get('first_seen_at')}",
        f"- Last seen in run `{issue.get('last_seen_run')}` at {issue.get('last_seen_at')}",
        "",
        "Run records live under `.testboard/runs/<run id>/`, and the testboard "
        "shows them at http://127.0.0.1:4200/.",
    ]
    if issue.get("note"):
        lines += ["", "## Note", "", issue["note"]]
    return "\n".join(lines)


def cmd_file(args: argparse.Namespace) -> int:
    doc = load_ledger()
    issue = doc["issues"].get(args.id)
    if issue is None:
        print(f"error: no issue '{args.id}'", file=sys.stderr)
        return 1
    title = f"[{issue['nature']}] {issue['title'][:90]}"
    body = render_issue_body(issue)

    if not args.file:
        # Dry run is the default because filing is outward facing and lands in
        # the owner's repository under his name.
        print("DRY RUN. Nothing was filed. This is what would be created:\n")
        print(f"title: {title}\n")
        print(body)
        print("\nRe-run with --file to actually create it.")
        return 0

    if issue.get("github_issue"):
        print(f"already filed: {issue['github_issue']}")
        return 0
    cmd = ["gh", "issue", "create", "--title", title, "--body", body]
    if args.label:
        for label in args.label:
            cmd += ["--label", label]
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        print(f"error: gh failed: {result.stderr.strip()}", file=sys.stderr)
        return 1
    url = result.stdout.strip()
    issue["github_issue"] = url
    issue["filed_at"] = _now()
    save_ledger(doc)
    print(f"filed: {url}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sync", help="fold every run's findings into the ledger").set_defaults(func=cmd_sync)

    p_list = sub.add_parser("list", help="show the ledger")
    p_list.add_argument("--all", action="store_true", help="include closed issues")
    p_list.set_defaults(func=cmd_list)

    p_class = sub.add_parser("classify", help="say what an issue actually is")
    p_class.add_argument("id")
    p_class.add_argument("--nature", required=True, choices=sorted(NATURES))
    p_class.add_argument("--note", default=None)
    p_class.add_argument("--owner", default=None, help="who is on the hook")
    p_class.add_argument("--by", default=None, help="who is making this call")
    p_class.add_argument("--closure-reason", dest="closure_reason",
                         choices=sorted(CLOSURE_REASONS), default=None)
    p_class.add_argument("--state", choices=("open", "closed"), default=None)
    p_class.set_defaults(func=cmd_classify)

    p_file = sub.add_parser("file", help="create a GitHub issue (dry run by default)")
    p_file.add_argument("id")
    p_file.add_argument("--file", action="store_true", help="actually create it")
    p_file.add_argument("--label", action="append")
    p_file.set_defaults(func=cmd_file)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
