#!/usr/bin/env python3
"""Benchmark the v2 index engine (and optionally compare v1) on real repos.

Measures, per repo, for the v2 engine:
  - cold wall time (fresh fact store) and warm wall time (unchanged, cache hot)
  - peak resident memory (RUSAGE_SELF for the parent, plus the largest
    ProcessPool worker via RUSAGE_CHILDREN; reported peak is the max of the two)
  - fact-store size on disk
  - coverage-ledger completeness (every file under the root accounted for
    exactly once: its own ledger row, or exactly one excluded-directory row)

With --compare-v1 it also times the legacy v1 scanner on the same repo (bounded
by --timeout); v1 that fails or times out is reported as "did not complete".

Each measured analysis runs in a fresh subprocess (this same script in an
internal ``--_run`` mode) so wall time and peak RSS are isolated per run and the
v2 ProcessPool workers are captured via RUSAGE_CHILDREN.

Usage:
    python3 scripts/benchmark-engine.py . /path/to/other/repo --compare-v1
    python3 scripts/benchmark-engine.py <repo> --json results.json
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ru_maxrss is bytes on macOS (Darwin) and kilobytes on Linux.
_MAXRSS_TO_BYTES = 1 if sys.platform == "darwin" else 1024


def _maxrss_bytes() -> int:
    self_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    child_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return max(self_rss, child_rss) * _MAXRSS_TO_BYTES


def _human_bytes(n: int) -> str:
    step = 1024.0
    val = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if val < step or unit == "GB":
            return f"{val:.1f} {unit}"
        val /= step
    return f"{val:.1f} GB"


# ---------------------------------------------------------------------------
# Internal single-run mode (executed as a fresh subprocess)
# ---------------------------------------------------------------------------

def _run_once(engine: str, repo: Path, out: Path, store: Path | None) -> dict:
    """Run one analysis in-process and return timing + memory + counts."""
    result: dict = {"engine": engine, "files_parsed": None, "files_cached": None}

    if engine == "v2":
        from analyzer.derive import derive_all
        from analyzer.extract import extract_repo
        from analyzer.project.pipeline import project_split
        from analyzer.store import FactStore

        assert store is not None
        store.parent.mkdir(parents=True, exist_ok=True)
        fs = FactStore(str(store))
        t0 = time.perf_counter()
        extraction = extract_repo(repo, fs, max_file_size=None)
        _, arch = derive_all(fs, repo.name, root_path=str(repo))
        project_split(
            arch, out, store=fs, root=repo,
            generated_at=datetime.now(timezone.utc).isoformat(),
            analyzer_version="bench", indent=None,
        )
        wall = time.perf_counter() - t0
        fs.close()
        result["files_parsed"] = extraction.files_parsed
        result["files_cached"] = extraction.files_cached
    elif engine == "v1":
        from analyzer.models import to_dict
        from analyzer.scanner import ArchitectureScanner

        t0 = time.perf_counter()
        scanner = ArchitectureScanner(repo, max_symbols=0)
        arch = scanner.scan()
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(to_dict(arch), f, default=str)
        wall = time.perf_counter() - t0
    else:  # pragma: no cover - guarded by argparse choices
        raise ValueError(engine)

    result["wall_s"] = wall
    result["peak_rss_bytes"] = _maxrss_bytes()
    return result


# ---------------------------------------------------------------------------
# Ledger completeness
# ---------------------------------------------------------------------------

def _ledger_report(store_path: Path, root: Path) -> dict:
    """Verify every file under root is accounted for exactly once in the ledger."""
    from analyzer.store import FactStore

    fs = FactStore(str(store_path))
    coverage = fs.coverage()
    summary = fs.coverage_summary()
    fs.close()

    dir_rows = sorted(
        row["path"] for row in coverage
        if row["disposition"].startswith("excluded:skipped_directory")
        or row["disposition"].startswith("excluded:vendored_repo")
    )
    file_rows = {
        row["path"] for row in coverage
        if row["path"] not in dir_rows
    }

    def _under_excluded_dir(rel: str) -> bool:
        return any(rel == d or rel.startswith(d + "/") for d in dir_rows)

    walked = 0
    unaccounted = 0
    examples: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            abs_p = Path(dirpath) / fn
            try:
                rel = abs_p.relative_to(root).as_posix()
            except ValueError:
                continue
            walked += 1
            if rel in file_rows or _under_excluded_dir(rel):
                continue
            unaccounted += 1
            if len(examples) < 5:
                examples.append(rel)

    return {
        "files_walked": walked,
        "unaccounted": unaccounted,
        "complete": unaccounted == 0,
        "examples": examples,
        "parsed": summary.get("parsed", 0),
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _measure(engine: str, repo: Path, out: Path, store: Path | None,
             timeout: float | None) -> dict:
    """Run one analysis as a fresh subprocess and parse its JSON result line."""
    cmd = [
        sys.executable, str(Path(__file__).resolve()),
        "--_run", "--engine", engine, "--repo", str(repo), "--out", str(out),
    ]
    if store is not None:
        cmd += ["--store", str(store)]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        return {"engine": engine, "completed": False,
                "reason": f"timed out after {timeout:.0f}s"}
    outer_wall = time.perf_counter() - t0
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
        return {"engine": engine, "completed": False,
                "reason": f"exit {proc.returncode}: {' | '.join(tail)}"}
    line = proc.stdout.strip().splitlines()[-1]
    data = json.loads(line)
    data["completed"] = True
    data["outer_wall_s"] = outer_wall
    return data


def benchmark_repo(repo: Path, compare_v1: bool, timeout: float) -> dict:
    repo = repo.resolve()
    row: dict = {"repo": str(repo), "name": repo.name}

    work = Path(tempfile.mkdtemp(prefix="se-bench-"))
    store = work / "index.db"
    out = work / "site"
    try:
        # v2 cold (fresh store)
        cold = _measure("v2", repo, out, store, timeout)
        row["v2_cold"] = cold
        if cold.get("completed"):
            row["store_bytes"] = store.stat().st_size if store.exists() else 0
            row["ledger"] = _ledger_report(store, repo)
            # v2 warm (unchanged tree, hot cache)
            warm = _measure("v2", repo, out, store, timeout)
            row["v2_warm"] = warm

        if compare_v1:
            v1_out = work / "v1.json"
            row["v1"] = _measure("v1", repo, v1_out, None, timeout)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return row


def _print_report(rows: list[dict]) -> None:
    print("\n" + "=" * 78)
    print("BENCHMARK RESULTS")
    uname = os.uname()
    print(f"Machine: {uname.sysname} {uname.release} {uname.machine}, "
          f"{os.cpu_count()} cores, Python {sys.version.split()[0]}")
    print("=" * 78)
    header = ("Repo", "v2 cold", "v2 warm", "peak mem", "store", "ledger", "v1")
    print("{:<16}{:>10}{:>10}{:>11}{:>10}{:>16}{:>12}".format(*header))
    for r in rows:
        cold = r.get("v2_cold", {})
        warm = r.get("v2_warm", {})
        led = r.get("ledger", {})
        v1 = r.get("v1", {})
        cold_s = f"{cold['wall_s']:.2f}s" if cold.get("completed") else "FAIL"
        warm_s = f"{warm['wall_s']:.2f}s" if warm.get("completed") else "-"
        mem = _human_bytes(cold["peak_rss_bytes"]) if cold.get("completed") else "-"
        store = _human_bytes(r["store_bytes"]) if "store_bytes" in r else "-"
        if led:
            ledger = f"{led['parsed']}p {'OK' if led['complete'] else 'GAP'}"
        else:
            ledger = "-"
        if not v1:
            v1s = "n/a"
        elif v1.get("completed"):
            v1s = f"{v1['wall_s']:.2f}s"
        else:
            v1s = "DNF"
        print("{:<16}{:>10}{:>10}{:>11}{:>10}{:>16}{:>12}".format(
            r["name"][:16], cold_s, warm_s, mem, store, ledger, v1s))
    print("=" * 78)
    for r in rows:
        led = r.get("ledger", {})
        if led and not led["complete"]:
            print(f"WARNING: {r['name']} ledger has {led['unaccounted']} "
                  f"unaccounted files, e.g. {led['examples']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repos", nargs="*", help="repository roots to benchmark")
    ap.add_argument("--compare-v1", action="store_true",
                    help="also time the legacy v1 scanner on each repo")
    ap.add_argument("--timeout", type=float, default=1800.0,
                    help="per-run timeout in seconds (default: 1800)")
    ap.add_argument("--json", default=None, help="write full results as JSON here")
    # Internal single-run mode.
    ap.add_argument("--_run", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--engine", choices=("v1", "v2"), help=argparse.SUPPRESS)
    ap.add_argument("--repo", help=argparse.SUPPRESS)
    ap.add_argument("--out", help=argparse.SUPPRESS)
    ap.add_argument("--store", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args._run:
        res = _run_once(
            args.engine, Path(args.repo), Path(args.out),
            Path(args.store) if args.store else None,
        )
        print(json.dumps(res))
        return

    if not args.repos:
        ap.error("at least one repository path is required")

    rows = [benchmark_repo(Path(r), args.compare_v1, args.timeout) for r in args.repos]
    _print_report(rows)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"\nFull results: {args.json}")


if __name__ == "__main__":
    main()
