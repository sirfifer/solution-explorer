#!/usr/bin/env python3
"""The control plane: one process that runs the board and drives every job.

Before this there were several ways to start work and none of them guaranteed
anyone could see it. A run started from a terminal was visible only in that
terminal. A run started by an agent was visible only in that session. The
dashboard could show a run, but only if somebody had happened to start the
dashboard first, and nothing made that true.

So this is the single front door. Start it and you get, in one process:

  the dashboard      served, always, because a run that nobody can watch is the
                     thing we are trying to stop happening
  a REST API         so a person, an agent, a script or a cron can start the
                     same job the same way and it lands on the same board
  a job runner       that supervises those jobs as child processes and knows
                     what is running, what is queued, and what just finished

The design rule is that the board is never optional. Every path into work goes
through here, and here always has the board up. That is the whole point: you
cannot accidentally run something unobserved.

## Why the jobs are subprocesses

Each harness already publishes its own run record to `.testboard/runs/` as it
executes (the crawl through its Playwright reporter, the linter through
`--testboard`, the pipeline through `scripts/testboard_emit.py`). The control
plane deliberately does NOT re-implement any of that. It starts a process,
watches it live or die, and lets the harness speak for itself. That keeps one
honest source of truth for what happened, and it means a job run by hand from a
terminal is indistinguishable on the board from one started through the API.

## The enrichment exception

Enrichment is the one job this will not start. It runs against the owner's
Claude subscription through the `claude` CLI and spends real usage, so it has
to be initiated deliberately from a Claude Code session rather than by anything
that can be triggered over HTTP. Asking for it returns 409 with the exact
command to run, which is more useful than a refusal and keeps the rule
explicit rather than implied by omission.

Stdlib only, same as the board. No framework, no daemon to install.

Usage:
    python3 scripts/control.py                      # board plus API, the default
    python3 scripts/control.py --port 4200 --open
    python3 scripts/control.py run lint --slug large-repository-validation      # start a job, watch it
    python3 scripts/control.py jobs                        # what can be run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from collections.abc import Callable
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse

SCRIPTS = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import testboard  # noqa: E402  (path set above, deliberately)

VIEWER = REPO_ROOT / "viewer"
CRAWL_CONFIG = "tests/crawl/playwright.config.ts"

# The one job that must never start from an HTTP request. Enrichment spends the
# owner's Claude subscription, so the decision to spend it stays a deliberate
# human act inside a Claude Code session. Named here rather than handled by an
# absence, so the rule is visible in the job table itself.
CLAUDE_GATED = {
    "enhance": (
        "Enrichment runs against the owner's Claude subscription through the "
        "`claude` CLI and spends real usage, so it is started deliberately from "
        "a Claude Code session, never over HTTP."
    ),
}


def _python() -> str:
    """The interpreter to run children with.

    Prefers the current one, which is the venv when the control plane was
    started from it. Running the analyzer under a python without tree-sitter
    silently falls back to regex parsers and produces a quietly wrong map, a
    trap this repo has already paid for once.
    """
    return sys.executable or "python3"


class Job:
    """A named, runnable unit of work."""

    def __init__(
        self,
        name: str,
        summary: str,
        build: Callable[[dict], list[str]],
        cwd: Path = REPO_ROOT,
        env: Optional[Callable[[dict], dict]] = None,
        needs_slug: bool = False,
        validate: Optional[Callable[[dict], Optional[str]]] = None,
    ) -> None:
        self.name = name
        self.summary = summary
        self.build = build
        self.cwd = cwd
        self.env = env
        self.needs_slug = needs_slug
        # Extra param validation beyond the slug check, for a job whose params
        # need more than "is it present": crawl's slug-or-url either/or, for
        # instance. Returns an error string, or None when params are fine.
        self.validate = validate

    def describe(self) -> dict:
        return {
            "name": self.name,
            "summary": self.summary,
            "needs_slug": self.needs_slug,
            "claude_gated": self.name in CLAUDE_GATED,
            "gate_reason": CLAUDE_GATED.get(self.name),
        }


# A slug names one entry in demos/registry/, and every job that takes one
# interpolates it into a filesystem path. The API accepts jobs over HTTP, so the
# value can arrive from outside this process: "../../.." would walk out of the
# corpus directory and a slug carrying a separator would quietly land the work
# somewhere nobody looks for it. An allowlist rather than a blocklist, because
# the character nobody thought to ban is the one that turns up.
_SLUG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,191}")


def _arch_dir_for(slug: str) -> Path:
    corpus = testboard._corpus_dir()
    return corpus / "_out" / slug / "architecture"


def _src_dir_for(slug: str) -> Path:
    return testboard._corpus_dir() / slug


def _serve_dir_for(slug: str) -> Path:
    """Where a crawl-ready bundle for this subject is assembled."""
    return REPO_ROOT / ".testboard" / "serve" / slug


def _validate_crawl(params: dict) -> Optional[str]:
    """crawl takes a slug OR a url, never neither, and a url must be http(s).

    Every other job in this file needs a slug unconditionally (needs_slug on
    the Job). crawl is the one exception: GUI-CRAWL-DESIGN.md added the
    ability to point the crawl at a published origin directly, which has no
    local slug at all. So crawl carries needs_slug=False and validates its
    own either/or here instead.
    """
    url = params.get("url")
    slug = params.get("slug")
    if url:
        parsed = urlparse(str(url))
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return f"'{url}' is not a usable url; it must start with http:// or https://"
    elif not slug:
        return "job 'crawl' needs a slug or a url"
    elif not _SLUG_RE.fullmatch(slug):
        return (
            f"'{slug}' is not a usable slug. A slug names a registry "
            "entry, so it may hold letters, digits, dots, dashes and "
            "underscores and nothing else."
        )

    profile = params.get("profile")
    if profile and profile not in ("quick", "full"):
        return f"'{profile}' is not a usable profile; it must be 'quick' or 'full'"
    return None


def _mobile_disabled(params: dict) -> bool:
    """Whether the mobile Playwright project should be switched off.

    Mobile defaults to on (GUI-CRAWL-DESIGN.md's mobile project runs unless
    told not to), so this only ever returns True on an explicit opt-out. A
    JSON body carries a real bool; `--param mobile=false` from the CLI
    carries a string, so both spellings are read.
    """
    value = params.get("mobile")
    if value is None:
        return False
    if isinstance(value, bool):
        return not value
    return str(value).strip().lower() in ("0", "false", "no", "off")


def _validate_params(job: "Job", params: dict) -> Optional[str]:
    """The one place slug and job-specific validation happen.

    Shared between JobRunner.start() (the HTTP path) and the CLI's --dry-run,
    so the two never drift apart on what counts as a usable set of params.
    """
    if job.needs_slug:
        slug = params.get("slug")
        if not slug:
            return f"job '{job.name}' needs a slug"
        if not _SLUG_RE.fullmatch(slug):
            return (
                f"'{slug}' is not a usable slug. A slug names a registry "
                "entry, so it may hold letters, digits, dots, dashes and "
                "underscores and nothing else."
            )
    if job.validate:
        return job.validate(params)
    return None


JOBS: dict[str, Job] = {
    "lint": Job(
        "lint",
        "Lint a projected dataset for integrity, accusability and completeness. "
        "Deterministic, no model, seconds to minutes depending on subject size.",
        needs_slug=True,
        build=lambda p: [
            _python(), str(SCRIPTS / "lint-projection.py"),
            str(_arch_dir_for(p["slug"])),
            "--src", str(_src_dir_for(p["slug"])),
            "--testboard",
            *(["--profile", p["profile"]] if p.get("profile") else []),
            *(["--content-sample", str(p["content_sample"])] if p.get("content_sample") else []),
        ],
    ),
    "assemble": Job(
        "assemble",
        "Build the viewer and stage it beside a subject's projection so the "
        "crawl has something to point at. `projection` overrides the "
        "projection directory (default: the corpus output for this slug). "
        "Cheap, and the crawl needs it first.",
        needs_slug=True,
        build=lambda p: [
            _python(), str(SCRIPTS / "assemble-serve.py"), p["slug"],
            *(["--projection", p["projection"]] if p.get("projection") else []),
            *(["--no-build"] if p.get("no_build") else []),
        ],
    ),
    "crawl": Job(
        "crawl",
        "Drive a real browser over a served build, or a remote origin, and "
        "prove everything in the data is reachable and renders. `slug` "
        "crawls a locally assembled subject (needs `assemble` to have run "
        "first); `url` crawls a remote origin instead and needs no slug. "
        "`profile` is `quick` (bounded sweeps, both projects, the default) "
        "or `full` (no budget, hour-scale). `mobile` defaults to on; pass "
        "false to run the desktop project alone. Minutes to hours by subject "
        "size and profile.",
        needs_slug=False,
        cwd=VIEWER,
        validate=_validate_crawl,
        build=lambda p: [
            "npx", "playwright", "test", "-c", CRAWL_CONFIG,
            *(["-g", p["grep"]] if p.get("grep") else []),
        ],
        env=lambda p: {
            **(
                {"CRAWL_BASE_URL": p["url"]}
                if p.get("url")
                else {
                    "CRAWL_SERVE_DIR": str(_serve_dir_for(p["slug"])),
                    "CRAWL_BASE_URL": p.get("base_url") or "http://127.0.0.1:4310",
                }
            ),
            "CRAWL_PROFILE": p.get("profile") or "quick",
            **({"CRAWL_MAX_COMPONENTS": str(p["max_components"])} if p.get("max_components") else {}),
            **({"CRAWL_MOBILE": "0"} if _mobile_disabled(p) else {}),
        },
    ),
    "fetch": Job(
        "fetch",
        "Clone or update a subject in the corpus and resolve its commit.",
        needs_slug=True,
        build=lambda p: [
            _python(), str(SCRIPTS / "demo-site.py"), "fetch", p["slug"],
            *(["--force"] if p.get("force") else []),
        ],
    ),
    "analyze": Job(
        "analyze",
        "Run the deterministic engine over a fetched subject and write the "
        "split projection. Processing time only, no model, no cost.",
        needs_slug=True,
        build=lambda p: [_python(), str(SCRIPTS / "demo-site.py"), "analyze", p["slug"]],
    ),
    "validate": Job(
        "validate",
        "Run the publication gates against a built demo bundle.",
        needs_slug=True,
        build=lambda p: [
            _python(), str(SCRIPTS / "demo-site.py"), "validate", p["slug"],
            *(["--allow-unimplemented"] if p.get("allow_unimplemented") else []),
        ],
    ),
    "enhance": Job(
        "enhance",
        "The enrichment ladder. Started only from a Claude Code session, never "
        "from here: it spends the owner's Claude subscription.",
        needs_slug=True,
        build=lambda p: [
            _python(), str(SCRIPTS / "demo-site.py"), "enhance", p["slug"],
            *(["--dry-run"] if p.get("dry_run") else []),
        ],
    ),
}


class RunningJob:
    def __init__(self, job_id: str, name: str, params: dict, proc: subprocess.Popen, log: Path):
        self.id = job_id
        self.name = name
        self.params = params
        self.proc = proc
        self.log = log
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.started_monotonic = time.time()
        self.returncode: Optional[int] = None
        self.cancelled = False

    def describe(self) -> dict:
        alive = self.proc.poll() is None
        return {
            "id": self.id,
            "job": self.name,
            "params": self.params,
            "state": "running" if alive else ("cancelled" if self.cancelled else "finished"),
            "returncode": self.returncode,
            "started_at": self.started_at,
            "elapsed_s": round(time.time() - self.started_monotonic, 1),
            "log": str(self.log),
            "pid": self.proc.pid,
        }


class JobRunner:
    """Starts jobs, keeps their handles, and never loses track of one.

    Deliberately serial by default. The heavy jobs, an analyze of a large
    subject and a browser crawl, both saturate the machine, and running them
    together makes each one's timings meaningless. Meaningless timings are
    worse than slow ones, because the board's whole job is to tell "slow" from
    "stuck".
    """

    def __init__(self, max_concurrent: int = 1) -> None:
        self.max_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._running: dict[str, RunningJob] = {}
        self._history: list[dict] = []
        self.log_dir = REPO_ROOT / ".testboard" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _reap(self) -> None:
        for job_id, run in list(self._running.items()):
            code = run.proc.poll()
            if code is not None:
                run.returncode = code
                self._history.insert(0, {**run.describe(), "state": "finished"})
                del self._running[job_id]
        del self._history[50:]

    def start(self, name: str, params: dict) -> dict:
        job = JOBS.get(name)
        if job is None:
            return {"error": f"unknown job '{name}'", "status": 404}
        if name in CLAUDE_GATED:
            command = " ".join(shlex.quote(c) for c in job.build(params))
            return {
                "error": CLAUDE_GATED[name],
                "status": 409,
                "run_it_yourself": command,
            }
        err = _validate_params(job, params)
        if err:
            return {"error": err, "status": 400}

        with self._lock:
            self._reap()
            if len(self._running) >= self.max_concurrent:
                busy = ", ".join(r.name for r in self._running.values())
                return {
                    "error": f"already running: {busy}. The runner is serial so timings stay meaningful.",
                    "status": 409,
                }

            job_id = f"{name}-{uuid.uuid4().hex[:8]}"
            log_path = self.log_dir / f"{job_id}.log"
            env = dict(os.environ)
            if job.env:
                env.update(job.env(params))
            # Children publish to the same board this process reads.
            env.setdefault("TESTBOARD_DIR", str(testboard.RUNS_DIR))

            try:
                command = job.build(params)
            except Exception as exc:
                return {"error": f"could not build the command: {exc}", "status": 400}

            log = open(log_path, "w", encoding="utf-8")
            log.write(f"$ {' '.join(shlex.quote(c) for c in command)}\n\n")
            log.flush()
            try:
                proc = subprocess.Popen(
                    command, cwd=str(job.cwd), env=env,
                    stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            except OSError as exc:
                log.close()
                return {"error": f"could not start: {exc}", "status": 500}

            run = RunningJob(job_id, name, params, proc, log_path)
            self._running[job_id] = run
            return {"status": 202, **run.describe(),
                    "command": " ".join(shlex.quote(c) for c in command)}

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            run = self._running.get(job_id)
            if run is None:
                return {"error": f"no running job '{job_id}'", "status": 404}
            run.cancelled = True
            try:
                # The whole process group: a playwright run spawns a browser and
                # a static server, and killing only the parent orphans both.
                os.killpg(os.getpgid(run.proc.pid), 15)
            except (OSError, ProcessLookupError) as exc:
                return {"error": f"could not signal: {exc}", "status": 500}
            return {"status": 202, "cancelled": job_id}

    def snapshot(self) -> dict:
        with self._lock:
            self._reap()
            return {
                "running": [r.describe() for r in self._running.values()],
                "recent": self._history[:20],
                "max_concurrent": self.max_concurrent,
                "catalog": [j.describe() for j in JOBS.values()],
            }


RUNNER = JobRunner()


def _atomic_json(path: Path, payload: dict) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def enrichment_control(run_id: str, action: str, params: dict) -> dict:
    """Apply one owner decision to a dashboard-published enrichment run."""
    if not _RUN_ID_RE.fullmatch(run_id):
        return {"status": 400, "error": "invalid run id"}
    record_path = testboard.RUNS_DIR / run_id / "run.json"
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("kind") != "enhance":
            raise ValueError("not an enrichment run")
        advertised = (record.get("enrichment_control") or {}).get("path")
        control_path = Path(str(advertised)).resolve()
        control = json.loads(control_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {
            "status": 404,
            "error": f"run '{run_id}' has no live enrichment control record",
        }
    if control_path.name != "control.json" or not isinstance(control, dict):
        return {"status": 400, "error": "invalid enrichment control record"}

    now = time.time()
    if action == "resume":
        raw = params.get("pause_at_usd")
        try:
            checkpoint = float(raw)
        except (TypeError, ValueError):
            return {
                "status": 400,
                "error": "resume requires a numeric pause_at_usd checkpoint",
            }
        committed = float(control.get("spent_usd") or 0) + float(
            control.get("reserved_usd") or 0
        )
        if checkpoint <= committed:
            return {
                "status": 400,
                "error": (
                    f"new checkpoint ${checkpoint:.2f} must exceed the "
                    f"${committed:.2f} already spent or reserved"
                ),
            }
        control.update({
            "state": "running",
            "pause_at_usd": checkpoint,
            "reason": f"operator resumed with a ${checkpoint:.2f} checkpoint",
            "recommendation": "No action required; the run is proceeding.",
        })
    elif action == "cancel":
        control.update({
            "state": "cancelled",
            "reason": "operator cancelled after reviewing the decision packet",
            "recommendation": "The engine will bank completed calls and publish an honest partial report.",
        })
    elif action == "pause":
        control.update({
            "state": "paused",
            "reason": "operator requested a manual pause",
            "recommendation": "Review live telemetry, then resume with a higher checkpoint or cancel.",
        })
    else:
        return {"status": 404, "error": f"unknown enrichment action '{action}'"}
    control["revision"] = int(control.get("revision") or 0) + 1
    control["updated_at"] = now
    try:
        _atomic_json(control_path, control)
    except OSError as exc:
        return {"status": 500, "error": f"could not persist decision: {exc}"}
    return {"status": 202, "run_id": run_id, "control": control}


class ControlHandler(testboard.Handler):
    """The board's read endpoints, plus the job control surface."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/jobs"):
            self._json({"status": 200, **RUNNER.snapshot()})
        elif self.path.startswith("/api/health"):
            self._json({
                "status": 200,
                "ok": True,
                "runs_dir": str(testboard.RUNS_DIR),
                "repo": str(REPO_ROOT),
            })
        elif self.path.startswith("/api/state"):
            state = testboard.build_state()
            # The board and the runner are two views of the same moment, so they
            # are served together. A job the runner started that has not yet
            # written its record would otherwise be invisible in the gap.
            state["jobs"] = RUNNER.snapshot()
            self._json(state)
        else:
            super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            params = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json({"status": 400, "error": "body must be JSON"})
            return
        if not isinstance(params, dict):
            self._json({"status": 400, "error": "body must be a JSON object"})
            return

        parts = [p for p in self.path.split("?")[0].strip("/").split("/") if p]
        # /api/enrichment/<testboard-run-id>/<pause|resume|cancel>
        if len(parts) == 4 and parts[:2] == ["api", "enrichment"]:
            self._json(enrichment_control(parts[2], parts[3], params))
            return
        # /api/jobs/<name>            start
        # /api/jobs/<id>/cancel       stop
        if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "cancel":
            self._json(RUNNER.cancel(parts[2]))
            return
        if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
            self._json(RUNNER.start(parts[2], params))
            return
        self._json({"status": 404, "error": f"no such endpoint: {self.path}"})

    def _json(self, payload: dict) -> None:
        code = payload.get("status", 200)
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code if isinstance(code, int) else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def cmd_serve(args: argparse.Namespace) -> int:
    testboard.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    RUNNER.max_concurrent = args.concurrency
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ControlHandler)
    url = f"http://127.0.0.1:{args.port}/"
    print("solution-explorer control plane")
    print(f"  dashboard  {url}")
    print(f"  api        {url}api/state, {url}api/jobs, {url}api/health")
    print(f"  runs       {testboard.RUNS_DIR}")
    print(f"  logs       {RUNNER.log_dir}")
    print(f"  jobs       {', '.join(sorted(JOBS))}")
    print("  ctrl-c to stop")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ncontrol plane: stopping")
        for run in list(RUNNER._running.values()):
            print(f"  killing {run.name} ({run.id})")
            RUNNER.cancel(run.id)
    return 0


def _post(url: str, payload: dict) -> dict:
    req = urlrequest.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urlerror.HTTPError as exc:
        try:
            return json.loads(exc.read())
        except Exception:
            return {"error": str(exc), "status": exc.code}
    except OSError as exc:
        return {"error": f"no control plane reachable at {url}: {exc}", "status": 503}


def _run_params(args: argparse.Namespace) -> dict:
    """Assemble a job's params from the run subcommand's flags.

    Only includes a key when the matching flag was actually given, so a job's
    own default (e.g. crawl's `profile` defaulting to "quick" in its env
    lambda) is what applies, not an accidental None sent over the wire.
    """
    params: dict = {}
    if args.slug:
        params["slug"] = args.slug
    if getattr(args, "url", None):
        params["url"] = args.url
    if getattr(args, "projection", None):
        params["projection"] = args.projection
    if getattr(args, "profile", None):
        params["profile"] = args.profile
    if getattr(args, "no_mobile", False):
        params["mobile"] = False
    for extra in args.param or []:
        if "=" in extra:
            key, value = extra.split("=", 1)
            params[key] = value
    return params


def _wait_for_job(base: str, job_id: str) -> None:
    """Block until job_id is no longer in the runner's running list.

    Only the CLI's `run crawl` path waits like this (see cmd_run); the HTTP
    API stays fire-and-forget, same as every other job. There is no timeout:
    a `full` profile crawl is hour-scale by design (GUI-CRAWL-DESIGN.md), so
    bounding this wait would just mean guessing wrong on some subject's size.
    A heartbeat prints every 30s so a long wait still looks alive rather than
    hung.
    """
    last_print = 0.0
    while True:
        try:
            with urlrequest.urlopen(f"{base}/api/jobs", timeout=10) as resp:
                snap = json.loads(resp.read())
        except OSError as exc:
            print(f"  (lost contact with the control plane while waiting: {exc})",
                  file=sys.stderr)
            return
        running = {r["id"]: r for r in snap.get("running", [])}
        run = running.get(job_id)
        if run is None:
            return
        now = time.time()
        if now - last_print >= 30:
            print(f"  ...still running, {run['elapsed_s']}s elapsed")
            last_print = now
        time.sleep(5)


def cmd_run(args: argparse.Namespace) -> int:
    """Ask a running control plane to start a job.

    Deliberately does NOT fall back to running the job locally when no control
    plane answers. That fallback is exactly how work ends up unobserved again,
    which is the problem this exists to solve. It says how to start one instead.

    --dry-run is the one path that never contacts the control plane at all: it
    builds the same command and environment JobRunner.start() would and prints
    them, so a slug/url/profile combination can be checked before anything
    actually runs a browser.
    """
    base = f"http://127.0.0.1:{args.port}"
    job = JOBS[args.job]  # argparse's choices=sorted(JOBS) guarantees this exists
    params = _run_params(args)

    if args.dry_run:
        err = _validate_params(job, params)
        if err:
            print(f"error: {err}", file=sys.stderr)
            return 1
        if args.job in CLAUDE_GATED:
            print(f"[dry-run] {args.job} is claude-gated: {CLAUDE_GATED[args.job]}")
        command = job.build(params)
        env_overrides = job.env(params) if job.env else {}
        print(f"[dry-run] {args.job} (nothing started; no control plane contacted)")
        print(f"  cwd      {job.cwd}")
        print(f"  command  {' '.join(shlex.quote(c) for c in command)}")
        if env_overrides:
            print("  env")
            for key, value in sorted(env_overrides.items()):
                print(f"    {key}={value}")
        else:
            print("  env      (no overrides beyond the inherited environment)")
        return 0

    result = _post(f"{base}/api/jobs/{args.job}", params)

    if result.get("status") == 503:
        print(result["error"], file=sys.stderr)
        print(f"\nStart one first:\n  {_python()} scripts/control.py --port {args.port}",
              file=sys.stderr)
        return 3
    if result.get("status") == 409 and result.get("run_it_yourself"):
        print(result["error"], file=sys.stderr)
        print(f"\nRun it yourself, from a Claude Code session:\n  {result['run_it_yourself']}",
              file=sys.stderr)
        return 4
    if result.get("error"):
        print(f"error: {result['error']}", file=sys.stderr)
        return 1

    print(f"started {result['job']} as {result['id']}")
    print(f"  watch   {base}/")
    print(f"  log     {result['log']}")

    if args.job == "crawl":
        # Documented follow-up, CLI-only (see docs/testing/DETERMINISTIC-CHECKS.md
        # and GUI-CRAWL-DESIGN.md): the job runner itself stays fire-and-forget,
        # so this waits here instead of inside JobRunner, then renders the
        # finished run's REPORT.md via scripts/crawl-report.py. The HTTP API
        # does not do this; only `control.py run crawl` from a terminal does.
        print("  the CLI now waits for this crawl to finish so it can render "
              "REPORT.md (scripts/crawl-report.py); Ctrl-C to stop waiting, the "
              "crawl itself keeps running either way")
        _wait_for_job(base, result["id"])
        report_rc = subprocess.run(
            [_python(), str(SCRIPTS / "crawl-report.py"), "--latest"]
        ).returncode
        if report_rc != 0:
            print(f"warning: crawl-report.py exited {report_rc}", file=sys.stderr)
    return 0


def cmd_jobs(args: argparse.Namespace) -> int:
    base = f"http://127.0.0.1:{args.port}"
    try:
        with urlrequest.urlopen(f"{base}/api/jobs", timeout=5) as resp:
            snap = json.loads(resp.read())
    except OSError:
        snap = RUNNER.snapshot()
        print("(no control plane running; showing the local catalog)\n")
    for job in snap["catalog"]:
        gate = "  [claude-gated]" if job["claude_gated"] else ""
        print(f"{job['name']}{gate}")
        print(f"    {job['summary']}")
        if job["gate_reason"]:
            print(f"    {job['gate_reason']}")
    for run in snap.get("running", []):
        print(f"\nRUNNING {run['job']} ({run['id']}) for {run['elapsed_s']}s")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=4200)
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="start a job on the control plane")
    p_run.add_argument("job", choices=sorted(JOBS))
    p_run.add_argument("--slug", default=None)
    p_run.add_argument("--url", default=None,
                        help="crawl only: a remote origin to crawl instead of --slug")
    p_run.add_argument("--projection", default=None,
                        help="assemble only: projection directory (default: this slug's corpus output)")
    p_run.add_argument("--profile", choices=["quick", "full"], default=None,
                        help="crawl only: quick (bounded, default) or full (no budget, hour-scale)")
    p_run.add_argument("--no-mobile", action="store_true",
                        help="crawl only: disable the mobile Playwright project (CRAWL_MOBILE=0)")
    p_run.add_argument("--param", action="append", help="extra key=value for the job")
    p_run.add_argument("--dry-run", action="store_true",
                        help="print the command and environment without starting anything")
    p_run.set_defaults(func=cmd_run)

    sub.add_parser("jobs", help="list what can be run").set_defaults(func=cmd_jobs)

    p_serve = sub.add_parser("serve", help="board plus API (the default)")
    p_serve.add_argument("--open", action="store_true")
    p_serve.add_argument("--concurrency", type=int, default=1)
    p_serve.set_defaults(func=cmd_serve)

    parser.add_argument("--open", action="store_true", help="open a browser (serve mode)")
    parser.add_argument("--concurrency", type=int, default=1)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        args.func = cmd_serve  # serving is the default, because the board is never optional
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
