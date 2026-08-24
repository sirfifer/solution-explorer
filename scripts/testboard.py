#!/usr/bin/env python3
"""The testboard: live observability for this project's harnesses and demo fleet.

The problem it solves is narrow and real. Our checks are deterministic scripts,
so anyone can run them: the owner from a terminal, an agent from a session, CI
from a workflow. But a running suite was a black box. You either watched the
process you started, or you had no idea whether anything was happening, how far
along it was, or what it had already found. And separately, nobody could answer
"which demo is live, and was it built with the current code" without opening
files by hand.

Two questions, one board:

  Runs   what is executing right now, how far in, what has passed and failed,
         and what earlier runs concluded. Fed by run records that each harness
         writes as it goes (viewer/tests/crawl/testboard-reporter.ts for the
         crawl, --testboard on scripts/lint-projection.py for the linter), so a
         run is observable regardless of who launched it.
  Fleet  what demos exist, what subject commit each was built from, which tool
         versions produced them, and whether that has drifted behind the
         checkout. Drift is the question that keeps biting: code moves, a demo
         does not get regenerated, and the deployed map quietly represents an
         older tool than the one we are talking about.

Deliberately small. Stdlib only, one file plus one HTML page, no build step, no
database, no daemon to install. It reads state that already exists on disk and
renders it. Nothing here can affect a run: the board is a reader, and a harness
that cannot write its record still runs fine.

Usage:
    python3 scripts/testboard.py serve [--port 4200] [--open]
    python3 scripts/testboard.py state          # one-shot JSON, for scripting
    python3 scripts/testboard.py runs           # one-shot text summary
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.environ.get("TESTBOARD_DIR") or (REPO_ROOT / ".testboard" / "runs"))
DASHBOARD = Path(__file__).resolve().parent / "testboard" / "dashboard.html"
REGISTRY_DIR = REPO_ROOT / "demos" / "registry"

# A run whose record still says "running" but whose files have not been touched
# in this long is presumed dead: a killed process, a closed laptop, a crashed
# browser. Presumed, and labelled as such, never silently rewritten, because the
# difference between "still working" and "died quietly" is exactly what the
# owner said he could not tell from the outside.
STALE_AFTER_SECONDS = 180

# How many finished runs to carry in the state payload. The board is for "what
# is happening and what just happened", not an archive.
RECENT_RUNS = 25

# What kind of work a run represents. These are genuinely different activities
# and the board keeps them apart, because reading them in one list makes both
# unreadable: a test tells you whether the product is correct, while a
# processing run tells you whether the product got BUILT. A red test and a
# failed analyze demand completely different responses.
#
#   test        the deterministic harnesses that check an artifact or the UI
#   processing  the pipeline that actually produces a demo, fetch through deploy
#
# A kind nobody has classified lands in "other" rather than being silently
# filed as a test, so an unrecognised harness is visible instead of miscounted.
RUN_CATEGORIES = {
    "crawl": "test",
    "lint": "test",
    "gui": "test",
    "fetch": "processing",
    "analyze": "processing",
    "enhance": "processing",
    "validate": "processing",
    "diff": "processing",
    "bundle": "processing",
    "assemble": "processing",
    "deploy": "processing",
    "refresh": "processing",
    "report": "processing",
}


def categorize(kind: Optional[str]) -> str:
    """Which of the board's three worlds a run belongs to."""
    return RUN_CATEGORIES.get((kind or "").lower(), "other")


# What every value the board publishes actually MEANS.
#
# Shipped in the payload rather than hardcoded in the page, because the producer
# is the only thing that knows. A reader looking at the word "crawl" in a column
# can guess, and guessing is exactly the failure: the board is supposed to
# remove uncertainty, not relocate it. So each value carries its own definition
# and the page tooltips whatever it renders.
#
# The rule for maintaining this: a new run kind, status or fleet field is not
# finished until it has an entry here. A value with no definition renders with
# no explanation, which is visible, and that is deliberate. Silent ignorance is
# the thing being designed out.
ISSUE_CLOSURE_REASONS = {
    "fixed": "Fixed: the underlying problem was corrected and the check now passes.",
    "accepted": "Accepted: understood, decided about, and deliberately left as it is. Closed by judgement rather than by a fix.",
    "not-reproducible": "No longer reproduces: the finding stopped appearing without anyone fixing it. Worth suspicion, since a problem that vanished on its own can return on its own.",
    "check-wrong": "The check was wrong: the harness reported something that was not actually a problem, and the check itself was corrected.",
    "duplicate": "Duplicate: the same problem is tracked under another issue."
}

ISSUE_NATURES = {
    "unclassified": "Nobody has decided what this is yet. The honest default, and never a silent one: an unclassified issue is visible precisely so it gets looked at.",
    "defect": "Something is genuinely wrong and should be fixed. The product does not do what it claims.",
    "unbuilt": "Not broken, just not built yet. The check is correct and the surface it checks does not exist. Expected during active development, and it must not read as a defect.",
    "threshold": "The check fired because a judgement-set limit was exceeded, and the limit may be the thing that is wrong. Worth a decision about the threshold, not necessarily a fix.",
    "subject": "True of the subject rather than of our tool. Something in the analyzed codebase, not something we did. Often still worth reporting, rarely worth fixing here.",
    "accepted": "Understood, decided about, and deliberately left as it is. Closed by judgement rather than by a fix."
}


GLOSSARY: dict[str, dict[str, str]] = {
    "kind": {
        "crawl": (
            "Crawl: drives a real browser over a served build of a dataset and "
            "proves that everything the data holds is reachable in the UI and "
            "renders without erroring. It discovers the shape of each subject "
            "from the manifest rather than from fixed test cases, so it adapts "
            "to any codebase. Minutes to hours depending on subject size."
        ),
        "lint": (
            "Lint: reads a finished projection end to end and checks that it is "
            "internally whole and that every claim in it points at something "
            "real. Structure, referential integrity, self-consistent counts, "
            "every cited file and line checked against the actual source, plus "
            "completeness heuristics. No browser, no model, seconds to minutes."
        ),
        "gui": (
            "GUI: the AI-operated vector regression plan, where an agent drives "
            "the browser and judges whether surfaces read correctly to a human. "
            "Answers a different question from the crawl: taste rather than "
            "coverage. Hours, and agent attended."
        ),
        "fetch": (
            "Fetch: clones or updates a subject repository in the corpus and "
            "resolves the exact commit that will be analyzed."
        ),
        "analyze": (
            "Analyze: runs the deterministic engine over a fetched subject and "
            "writes the split projection, the manifest plus per component detail "
            "shards. Pure processing, no model and no cost, so it can be re-run "
            "freely."
        ),
        "enhance": (
            "Enhance: the enrichment ladder, which sends parts of the map to a "
            "model to add description and judgement. This is the one job that "
            "spends real Claude subscription usage, so it is started only from a "
            "Claude Code session and never over the API."
        ),
        "validate": (
            "Validate: runs the publication gates against a built bundle. These "
            "are the obligations of publishing (licensing, disclaimers, the "
            "front door agreeing with the manifest) rather than data quality."
        ),
        "bundle": "Bundle: assembles the deployable static site for a demo.",
        "assemble": (
            "Assemble: builds the viewer and stages it beside a subject's "
            "projection, so a crawl has a single origin serving both the app "
            "and the data it should load. The projection is symlinked rather "
            "than copied, since a large one runs to hundreds of megabytes."
        ),
        "deploy": "Deploy: pushes an assembled bundle to its hosting project.",
        "diff": (
            "Diff: compares a new projection against the previous one for a "
            "subject and reports what changed."
        ),
        "refresh": (
            "Refresh: the whole pipeline for one demo end to end, fetch through "
            "report."
        ),
        "report": "Report: writes the run record for a demo refresh.",
        "housekeeping": (
            "Housekeeping: routine machine maintenance, unrelated to building or "
            "checking a demo. It appears here only because it published a run "
            "record, and lands under 'other' rather than being counted as a test."
        ),
    },
    "status": {
        "passed": "Passed: every case succeeded and nothing reported a failure.",
        "failed": (
            "Failed: at least one case reported a failure. For a test that means "
            "the product is wrong. For a processing run it means the work did "
            "not complete."
        ),
        "warned": (
            "Warned: something worth knowing was reported, but nothing that "
            "blocks. Warnings are kept distinct from failures on purpose, since "
            "treating advisories as defects is the fastest way to teach people "
            "to ignore the board."
        ),
        "skipped": (
            "Skipped: the check did not run and therefore did not pass. It is "
            "shown rather than hidden so an untested area is never mistaken for "
            "a clean one."
        ),
        "running": "Running: in flight right now, and updating its record.",
        "timedOut": (
            "Timed out: the case exceeded its time budget and was stopped. It is "
            "not the same as a failed assertion. Something was too slow, or hung, "
            "and a bounded harness chose to report that rather than wait forever."
        ),
        "interrupted": (
            "Interrupted: the case was stopped before it could finish, usually "
            "because the run itself was cancelled or an earlier failure aborted "
            "the suite. It reached no verdict, so it proves nothing either way."
        ),
        "stalled": (
            "Stalled: this run last said it was still working, but its record "
            "has not been touched for over three minutes, so the process has "
            "probably died. It is not marked failed because nothing ever "
            "reported a failure. The board infers this from file timestamps, "
            "since a dead process cannot update its own status."
        ),
    },
    "category": {
        "test": (
            "Test: checks whether what we built is correct. A red test means the "
            "product is wrong."
        ),
        "processing": (
            "Processing: the pipeline that actually produces a demo. A red "
            "processing run means the product did not get built at all. Kept "
            "separate from tests because the two demand completely different "
            "responses."
        ),
        "other": (
            "Other: a run whose kind the board does not recognise. It lands here "
            "rather than being filed as a test, so an unclassified harness is "
            "visible instead of quietly miscounted."
        ),
    },
    "fleet": {
        "track": (
            "Track: whether this demo is published to the public site or kept "
            "local. Published demos must fairly represent their subject."
        ),
        "cadence": "Cadence: how often this demo is scheduled to be refreshed.",
        "analyzed": (
            "Analyzed: a projection exists on disk for this subject, meaning the "
            "deterministic engine has run and produced a manifest."
        ),
        "bundle_built": (
            "Bundle built: a deployable static site has been assembled from the "
            "projection. Built is not the same as deployed."
        ),
        "subject_sha": (
            "Subject SHA: the exact commit of the analyzed repository this map "
            "was built from, recorded at fetch time in fetch-state.json. This is "
            "the subject's commit, not ours."
        ),
        "head_at_analysis": (
            "Head at analysis: the commit the analyzer actually saw when it "
            "walked the tree, read from the projection itself. It should match "
            "the subject SHA; a difference means the working copy moved between "
            "fetch and analysis."
        ),
        "built_with_analyzer": (
            "Built with: the analyzer version that produced this projection, "
            "stamped into the manifest at generation time."
        ),
        "analyzer_drift": (
            "Drift: this demo was built by an older analyzer than the current "
            "checkout, so the deployed map may not reflect the tool we are "
            "talking about today. Drift does not always require a rebuild, but "
            "nobody should have to discover it by reading JSON."
        ),
        "enriched": (
            "Enriched: the projection carries model-written enrichment. "
            "Deterministic means it was produced by the engine alone, which is "
            "the cheaper and fully reproducible state."
        ),
        "components": (
            "Components: how many nodes the projection holds. This is the "
            "structure a reader navigates."
        ),
        "files": "Files: how many source files the projection accounts for.",
        "symbols": (
            "Symbols: how many functions, classes and other named definitions "
            "the parsers extracted across the whole subject."
        ),
        "relationships": (
            "Relationships: how many edges between components were inferred, for "
            "example imports and calls. These are what the graph draws."
        ),
        "fetched_at": (
            "Fetched: when the subject repository was last cloned or updated. "
            "The map can be no fresher than this."
        ),
        "generated_at": (
            "Generated: when the analyzer produced this projection. A gap between "
            "fetched and generated means the working copy sat before it was read."
        ),
        "url": (
            "Hosted at: where this demo is published. A URL here does not prove "
            "the current build is deployed there, only where it belongs."
        ),
        "slug": (
            "Slug: the short identifier for this demo, used in the registry, on "
            "disk, and in every run that names it."
        ),
        "last_run": (
            "Last run: the most recent recorded run against this subject, "
            "matched by name or by the directory the run read."
        ),
    },
    "nature": ISSUE_NATURES,
    "closure_reason": ISSUE_CLOSURE_REASONS,
    "severity": {
        "error": (
            "Error: a check that must hold did not. For a projection this means "
            "the artifact is wrong, not merely thin."
        ),
        "warn": (
            "Warning: worth knowing, but not blocking. Kept distinct from errors "
            "deliberately, since treating advisories as defects teaches people to "
            "ignore the board."
        ),
    },
    "state": {
        "open": "Open: still present, or never decided about.",
        "closed": (
            "Closed: dealt with. The closure reason says how, since fixed, "
            "accepted and no longer reproduces are different outcomes."
        ),
    },
    "persistence": {
        "persistent": (
            "Persistent: seen in every run on record, so it reproduces reliably "
            "and can be worked on with confidence."
        ),
        "intermittent": (
            "Intermittent: seen in some runs but not all. The expensive kind, "
            "because a fix cannot be confirmed by one green run."
        ),
        "once": "Seen once: only one run has ever reported it.",
    },
    "field": {
        "budget": (
            "Budget: what limit the run was given. A capped run covers only part "
            "of the subject, so a green result means less than a full sweep does. "
            "This is free text today and cannot be read programmatically."
        ),
        "coverage": (
            "Coverage: what the run itself reports it actually exercised, in its "
            "own words. This is what turns a green tick into a claim you can "
            "check, and it is where a silently budgeted run admits it was "
            "budgeted."
        ),
        "seconds_since_update": (
            "Silent for: how long since this run last wrote to its record. The "
            "board uses this, not the run's own claim, to decide whether anyone "
            "is still home."
        ),
        "data_dir": "Data directory: the projection this run read.",
        "total": "Total: how many cases this run intended to execute.",
        "completed": "Completed: how many cases have finished, passed or not.",
        "percent": (
            "Percent: completed divided by total. It measures cases, not work, so "
            "it moves unevenly when cases differ wildly in size."
        ),
        "passed": "Passed: cases that finished with no failure reported.",
        "failed": "Failed: cases that reported at least one failure.",
        "warned": "Warned: cases that reported something advisory but not blocking.",
        "skipped": (
            "Skipped: cases that did not run. Shown rather than hidden, so an "
            "unchecked area is never mistaken for a clean one."
        ),
        "started_at": "Started: when this run began.",
        "ended_at": "Ended: when this run finished. Absent while it is still going.",
        "duration_ms": "Duration: wall clock time from start to finish.",
        "source_checked": (
            "Source checked: the working copy of the subject that every cited "
            "file and line was verified against. Absent means that whole band was "
            "skipped, and the map's citations were not checked against reality."
        ),
        "analyzer_version": (
            "Analyzer version: which build of our engine produced this "
            "projection, stamped in at generation time."
        ),
        "instances": (
            "Instances: how many times a problem was seen. This measures blast "
            "radius, not how many things need fixing."
        ),
        "distinct": (
            "Distinct: how many SEPARATE problems were found. Read this next to "
            "instances: fifty instances of one problem and fifty separate "
            "problems are completely different situations."
        ),
        "finding_totals": (
            "Findings: what the run actually discovered, as opposed to how many "
            "cases it ran. A single failing case can carry thousands of "
            "instances, so the case tally alone describes almost nothing."
        ),
        "base_url": "Base URL: the origin the browser was pointed at.",
    },
}


def _read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        # UnicodeDecodeError belongs here with the rest: a process killed
        # mid-write leaves a torn multi-byte sequence, and a board built to
        # survive dead processes cannot itself die reading their leftovers.
        return None


def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _corpus_dir() -> Path:
    """Where demo-site.py keeps fetched subjects and their output."""
    override = os.environ.get("DEMO_CORPUS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / "dev" / ".demo-corpus"


def current_versions() -> dict:
    """What the checkout is right now, to compare every artifact against."""
    analyzer_version = None
    init = REPO_ROOT / "analyzer" / "__init__.py"
    if init.is_file():
        for line in init.read_text(encoding="utf-8").splitlines():
            if line.startswith("__version__"):
                analyzer_version = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    pkg = _read_json(REPO_ROOT / "viewer" / "package.json") or {}
    head = _git("rev-parse", "HEAD")
    return {
        "analyzer_version": analyzer_version,
        "viewer_version": pkg.get("version"),
        "git_sha": head,
        "git_short": head[:9] if head else None,
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
    }


def _age_seconds(path: Path) -> Optional[float]:
    try:
        return (datetime.now(timezone.utc) - datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        )).total_seconds()
    except OSError:
        return None


def load_runs() -> list[dict]:
    """Every run record on disk, newest first, with liveness resolved."""
    if not RUNS_DIR.is_dir():
        return []
    runs: list[dict] = []
    for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
        record = _read_json(run_dir / "run.json")
        if not isinstance(record, dict):
            continue
        record["dir"] = str(run_dir)
        # Derived here rather than demanded of each harness, so a harness that
        # predates this taxonomy still lands in the right tab. A record may
        # override it by carrying its own category.
        record.setdefault("category", categorize(record.get("kind")))

        # Liveness is derived here rather than trusted from the record, because
        # a process that died cannot update its own status. The record says what
        # it last knew; the board says whether anyone is still home.
        if record.get("status") == "running":
            age = _age_seconds(run_dir / "run.json")
            record["seconds_since_update"] = round(age) if age is not None else None
            record["live"] = age is not None and age < STALE_AFTER_SECONDS
            if not record["live"]:
                record["status"] = "stalled"
        else:
            record["live"] = False

        total = record.get("total") or 0
        completed = record.get("completed") or 0
        record["percent"] = round(100 * completed / total) if total else 0
        runs.append(record)

    # Stalled runs ride with the live ones, never with the truncated history.
    # "Your run died quietly" is the signal this board exists to deliver, so it
    # is the last thing that should be allowed to fall off the end of a list.
    live = [r for r in runs if r.get("live")]
    stalled = [r for r in runs if not r.get("live") and r.get("status") == "stalled"]
    done = [r for r in runs if not r.get("live") and r.get("status") != "stalled"]
    return live + stalled + done[:RECENT_RUNS]


def tail_events(run_dir: Path, limit: int = 40) -> list[dict]:
    path = run_dir / "events.jsonl"
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def load_fleet(versions: dict) -> list[dict]:
    """One row per registered demo: what it is, and whether it is current."""
    if not REGISTRY_DIR.is_dir():
        return []
    corpus = _corpus_dir()
    fleet: list[dict] = []

    for reg_path in sorted(REGISTRY_DIR.glob("*.json")):
        reg = _read_json(reg_path)
        if not isinstance(reg, dict):
            continue
        slug = reg.get("slug") or reg_path.stem
        out_dir = corpus / "_out" / slug
        arch_dir = out_dir / "architecture"
        manifest = _read_json(arch_dir / "manifest.json")
        fetch_state = _read_json(out_dir / "fetch-state.json") or {}

        row: dict[str, Any] = {
            "slug": slug,
            "subject": (reg.get("subject") or {}).get("name") or slug,
            "track": reg.get("track"),
            "cadence": reg.get("cadence"),
            "url": (reg.get("hosting") or {}).get("url"),
            "analyzed": bool(manifest),
            "bundle_built": (out_dir / "bundle" / "index.html").is_file(),
            "subject_sha": fetch_state.get("resolved_sha"),
            "fetched_at": fetch_state.get("fetched_at"),
        }

        if manifest:
            stats = manifest.get("stats") or {}
            provenance = (manifest.get("activity") or {}).get("provenance") or {}
            enriched = bool(manifest.get("ai_enhance")) or any(
                c.get("ai_enhance") for c in _iter_components(manifest.get("components"))
            )
            row.update(
                {
                    "generated_at": manifest.get("generated_at"),
                    "built_with_analyzer": manifest.get("analyzer_version"),
                    "components": stats.get("total_components"),
                    "files": stats.get("total_files"),
                    "symbols": stats.get("total_symbols"),
                    "relationships": stats.get("total_relationships"),
                    "enriched": enriched,
                    "head_at_analysis": provenance.get("head"),
                }
            )
            # The drift question, stated plainly. A demo built by an older
            # analyzer than the checkout does not necessarily need rebuilding,
            # but nobody should have to discover that fact by reading JSON.
            built = manifest.get("analyzer_version")
            current = versions.get("analyzer_version")
            row["analyzer_drift"] = bool(built and current and built != current)
        else:
            row["analyzer_drift"] = False

        # Which runs have exercised this subject, and how they went. This is the
        # join that makes the board more than two lists side by side.
        fleet.append(row)
    return fleet


def _iter_components(nodes):
    for node in nodes or []:
        if isinstance(node, dict):
            yield node
            yield from _iter_components(node.get("children"))


def load_issues() -> dict:
    """The issue ledger, if scripts/issues.py has ever been synced.

    Findings scroll away with their run; issues do not. This is what turns "a
    run failed" into "this specific problem has been open for four runs and
    nobody has decided what it is yet".
    """
    doc = _read_json(RUNS_DIR.parent / "issues.json")
    if not isinstance(doc, dict):
        return {"issues": [], "totals": {"open": 0, "unclassified": 0, "total": 0}}
    issues = list((doc.get("issues") or {}).values())
    issues.sort(key=lambda i: (i.get("state") != "open", -(i.get("max_instances") or 0), i.get("id", "")))
    return {
        "issues": issues,
        "natures": ISSUE_NATURES,
        "updated_at": doc.get("updated_at"),
        "totals": {
            "total": len(issues),
            "open": sum(1 for i in issues if i.get("state") == "open"),
            "unclassified": sum(
                1 for i in issues if i.get("state") == "open" and i.get("nature") == "unclassified"
            ),
            "errors": sum(
                1 for i in issues if i.get("state") == "open" and i.get("severity") == "error"
            ),
            "instances": sum(i.get("max_instances") or 0 for i in issues if i.get("state") == "open"),
        },
    }


def _contention(runs: list[dict]) -> Optional[dict]:
    """Warn when more than one heavy run is live at once."""
    live = [r for r in runs if r.get("live")]
    heavy = [r for r in live if (r.get("kind") or "") in ("crawl", "analyze", "enhance", "gui")]
    if len(heavy) < 2:
        return None
    return {
        "count": len(heavy),
        "runs": [{"id": r.get("id"), "kind": r.get("kind"), "subject": r.get("subject")}
                 for r in heavy],
        "message": (
            f"{len(heavy)} heavy runs are executing at the same time. Their "
            f"timings are competing for the same machine, so durations, "
            f"throughput and any stall suspicion on this board are unreliable "
            f"until one finishes. Start jobs through scripts/control.py, which "
            f"runs them one at a time for exactly this reason."
        ),
    }


def build_state() -> dict:
    versions = current_versions()
    runs = load_runs()
    for run in runs:
        # Live runs need the tail to animate. Failed and stalled runs need it
        # for the opposite reason: it is the only record of what happened
        # before things went wrong, and dropping it left the runs people most
        # want to read back with nothing to read.
        if run.get("live") or run.get("status") in ("failed", "stalled"):
            run["events"] = tail_events(Path(run["dir"]))

    fleet = load_fleet(versions)
    # Attach each demo's most recent run, by subject name. Cheap, and it answers
    # "has anyone checked this demo since it was built" at a glance.
    def _summary(run: dict) -> dict:
        return {
            "id": run.get("id"),
            "kind": run.get("kind"),
            "status": run.get("status"),
            "started_at": run.get("started_at"),
            "passed": run.get("passed"),
            "warned": run.get("warned"),
            "failed": run.get("failed"),
        }

    # Runs are keyed by every name they can honestly be known by. A registry
    # calls the demo "Visual Studio Code" while a harness records the manifest
    # name "vscode", so a subject-only join quietly reported "never checked" for
    # a demo that had in fact just been checked. The data_dir is the one
    # unambiguous link, since it is the very directory the run read.
    by_key: dict[str, dict] = {}
    for run in runs:
        keys = [run.get("subject")]
        data_dir = run.get("data_dir")
        if isinstance(data_dir, str):
            keys.append(data_dir)
        for key in keys:
            if key and key not in by_key:
                by_key[key] = _summary(run)

    for row in fleet:
        row["last_run"] = (
            by_key.get(row["slug"])
            or by_key.get(row["subject"])
            or next(
                (v for k, v in by_key.items() if f"/{row['slug']}/" in k or k.endswith(f"/{row['slug']}")),
                None,
            )
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "runs_dir": str(RUNS_DIR),
        "versions": versions,
        "runs": runs,
        "fleet": fleet,
        # Every value the board renders carries its own definition, so the page
        # never hardcodes what a word means and an unrecognised value is
        # visibly undefined rather than silently unexplained.
        "glossary": GLOSSARY,
        "issues": load_issues(),
        "live_count": sum(1 for r in runs if r.get("live")),
        # Concurrent heavy runs make every timing on this board unreliable, and
        # the board had the information to say so while saying nothing. A crawl
        # and an analyze competing for the same cores turn "slow" and "stuck"
        # into the same reading, which is precisely the distinction the board
        # exists to make. Reported rather than prevented, since the board is a
        # reader; scripts/control.py is what actually serialises jobs.
        "contention": _contention(runs),
        "categories": {
            category: {
                "total": sum(1 for r in runs if r.get("category") == category),
                "live": sum(
                    1 for r in runs if r.get("category") == category and r.get("live")
                ),
                "failing": sum(
                    1
                    for r in runs
                    if r.get("category") == category
                    and r.get("status") in ("failed", "stalled")
                ),
            }
            for category in ("test", "processing", "other")
        },
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path.startswith("/api/state"):
            self._json(build_state())
        elif self.path in ("/", "/index.html"):
            self._html()
        else:
            self.send_error(404)

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self) -> None:
        if not DASHBOARD.is_file():
            self.send_error(500, "dashboard.html is missing")
            return
        body = DASHBOARD.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        """Silent. The board's own request log is noise in every context."""


def cmd_serve(args: argparse.Namespace) -> int:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"testboard: {url}")
    print(f"  runs:   {RUNS_DIR}")
    print("  ctrl-c to stop")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ntestboard: stopped")
    return 0


def cmd_state(args: argparse.Namespace) -> int:
    print(json.dumps(build_state(), indent=2))
    return 0


def cmd_runs(args: argparse.Namespace) -> int:
    state = build_state()
    v = state["versions"]
    dirty = " (dirty)" if v["git_dirty"] else ""
    print(f"checkout: analyzer {v['analyzer_version']}, viewer {v['viewer_version']}, "
          f"{v['git_branch']}@{v['git_short']}{dirty}")
    print()
    if not state["runs"]:
        print("no runs recorded yet")
    for run in state["runs"]:
        marker = "LIVE" if run.get("live") else (run.get("status") or "?").upper()
        print(f"[{marker:>7}] {run.get('id')}")
        tallies = [f"{run.get('passed', 0)} passed", f"{run.get('failed', 0)} failed"]
        if run.get("warned"):
            tallies.insert(1, f"{run['warned']} warned")
        if run.get("skipped"):
            tallies.append(f"{run['skipped']} skipped")
        print(f"          {run.get('kind')} on {run.get('subject')}: "
              f"{run.get('completed')}/{run.get('total')} ({', '.join(tallies)})")
        if run.get("current"):
            print(f"          now: {run['current']}")
        # "warned" is its own outcome, not a quiet failure. Collapsing the two
        # would make every advisory look like a defect, which is the fastest way
        # to teach people to ignore the board.
        labels = {"failed": "FAIL", "warned": "WARN", "timedOut": "TIMEOUT"}
        for case in run.get("cases", []):
            label = labels.get(case.get("status"))
            if label:
                print(f"          {label} {case.get('title')}: {case.get('message')}")
    print()
    for row in state["fleet"]:
        drift = "  DRIFT" if row.get("analyzer_drift") else ""
        state_word = "analyzed" if row.get("analyzed") else "not analyzed"
        print(f"demo {row['slug']}: {state_word}, {row.get('components')} components, "
              f"built with analyzer {row.get('built_with_analyzer')}{drift}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="run the dashboard")
    p_serve.add_argument("--port", type=int, default=4200)
    p_serve.add_argument("--open", action="store_true", help="open a browser at it")
    p_serve.set_defaults(func=cmd_serve)

    sub.add_parser("state", help="print the state payload as JSON").set_defaults(func=cmd_state)
    sub.add_parser("runs", help="print a text summary").set_defaults(func=cmd_runs)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
