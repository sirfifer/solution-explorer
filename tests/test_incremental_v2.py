"""Tests for the incremental v2 engine (P4-6).

The v2 engine is incremental by construction: a persistent fact store is the
baseline, the content-hash extraction cache re-parses only changed files, and
derivation re-runs in full over the (cheap) store. These tests drive the REAL
pipeline (``extract_repo`` -> ``derive_all`` -> ``project_split``) against a
mutated copy of the committed polyglot fixture and assert observable behavior:

  * touch one file and only that file re-parses (extraction instrumentation);
  * a full rescan (fresh store, cold parse) and an incremental run (warm store,
    cached parse) over the same tree project BYTE-IDENTICALLY across a scripted
    change sequence, including the P2-1 new-root-file and new-directory cases;
  * consecutive incremental runs produce correct changelog serials and entries;
  * the v2 path never reads or writes the old ``.arch-baseline`` caches;
  * warm derivation still reads zero source files.

Nothing is mocked or reimplemented. The full-vs-incremental parity test is the
core proof: the only difference between the two runs is whether the store is
reused (warm) or fresh (cold); byte-identical projections prove the warm cache
introduces no drift, no stale rows, and no dropped data.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from analyzer.derive import derive_all
from analyzer.derive.instrumentation import source_read_audit
from analyzer.extract import extract_repo
from analyzer.parsers import PARSERS
from analyzer.project import project_split
from analyzer.project.run import default_store_path
from analyzer.store import FactStore

FIXTURES = Path(__file__).parent / "fixtures"
POLYGLOT = FIXTURES / "polyglot"

_PARITY_LANGS = ("python", "swift", "rust", "typescript", "javascript", "go", "ruby")
_TS = all(getattr(PARSERS.get(x), "_ts_available", False) for x in _PARITY_LANGS)
requires_ts = pytest.mark.skipif(
    not _TS, reason="fixtures are pinned to the tree-sitter tier")

FIXED_TS = "2020-01-01T00:00:00Z"
FIXED_NOW = datetime(2020, 1, 1, tzinfo=timezone.utc)
REPO_NAME = "polyglot"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _copy_fixture(dest: Path) -> Path:
    shutil.copytree(POLYGLOT, dest)
    return dest


def _project_run(root: Path, store: FactStore, out: Path) -> dict:
    """Extract -> derive -> project_split into ``out`` with a fixed clock.

    ``previous=None`` makes the projection load the previous manifest from
    ``out`` itself, so consecutive runs into the same dir accumulate the
    changelog (the store-vs-previous-projection diff). Returns the manifest.
    """
    extract_repo(root, store)
    _, arch = derive_all(store, REPO_NAME, root_path=str(root))
    project_split(
        arch, out, store=store, root=root, previous=None,
        generated_at=FIXED_TS, analyzer_version="1.2.0", now=FIXED_NOW,
    )
    return json.loads((out / "manifest.json").read_text())


def _dir_bytes(d: Path) -> dict[str, bytes]:
    """Map every file under ``d`` to its bytes, keyed by POSIX relative path."""
    out: dict[str, bytes] = {}
    for p in sorted(d.rglob("*")):
        if p.is_file():
            out[p.relative_to(d).as_posix()] = p.read_bytes()
    return out


def _assert_dirs_identical(a: Path, b: Path, label: str) -> None:
    da, db = _dir_bytes(a), _dir_bytes(b)
    assert set(da) == set(db), (
        f"[{label}] artifact set differs: "
        f"only-in-incremental={sorted(set(da) - set(db))} "
        f"only-in-full={sorted(set(db) - set(da))}"
    )
    for rel in da:
        assert da[rel] == db[rel], f"[{label}] bytes differ for {rel}"


# ---------------------------------------------------------------------------
# scripted change sequence (absorbs P2-1: new root file, new directory)
# ---------------------------------------------------------------------------

def _seq_steps() -> list[tuple[str, object]]:
    """Ordered (label, mutation) steps. Each mutation edits the tree in place."""

    def add_file(root: Path) -> None:
        (root / "services/api/api/extra.py").write_text(
            "class Extra:\n    def run(self):\n        return 1\n"
        )

    def modify_file(root: Path) -> None:
        f = root / "services/api/api/server.py"
        f.write_text(f.read_text() + "\n# modified in the incremental sequence\n")

    def delete_file(root: Path) -> None:
        (root / "services/web/src/format.js").unlink()

    def rename_file(root: Path) -> None:
        src = root / "libs/rubylib/lib/parser.rb"
        dst = root / "libs/rubylib/lib/renamed_parser.rb"
        dst.write_text(src.read_text())
        src.unlink()

    def new_directory(root: Path) -> None:
        d = root / "services/api/api/handlers"
        d.mkdir(parents=True)
        (d / "handler.py").write_text(
            "def handle(request):\n    return {'ok': True}\n"
        )

    def new_root_file(root: Path) -> None:
        (root / "toplevel.py").write_text(
            "def main():\n    print('root level module')\n"
        )

    def marker_change(root: Path) -> None:
        # A new marker file creates a new component (a new sub-package).
        d = root / "tools/widget"
        d.mkdir(parents=True)
        (d / "package.json").write_text(
            '{"name": "widget", "version": "0.0.1"}\n'
        )
        (d / "index.js").write_text(
            "export function widget() { return 42; }\n"
        )

    return [
        ("baseline", lambda root: None),
        ("add_file", add_file),
        ("modify_file", modify_file),
        ("delete_file", delete_file),
        ("rename_file", rename_file),
        ("new_directory", new_directory),
        ("new_root_file", new_root_file),
        ("marker_file_change", marker_change),
    ]


@requires_ts
def test_full_rescan_byte_identical_to_incremental_across_sequence(tmp_path):
    """The core parity proof (P4-6 item 3, acceptance 1).

    Run the scripted sequence in lockstep. The incremental lane reuses ONE
    persistent (warm) store; the full lane uses a FRESH store every step (cold
    parse). Both project into their own accumulating output dirs with a fixed
    clock. After every step the two output trees must be byte-identical,
    including the changelog. The only difference between the lanes is the warm
    cache, so any drift, stale row, or dropped file surfaces as a byte diff.
    """
    root = _copy_fixture(tmp_path / "repo")
    incr_store_path = tmp_path / "incr" / "index.db"
    incr_store_path.parent.mkdir(parents=True)
    out_incr = tmp_path / "out_incr"
    out_full = tmp_path / "out_full"

    incr_store = FactStore(str(incr_store_path))
    try:
        for label, mutate in _seq_steps():
            mutate(root)

            # Incremental lane: warm, persistent store.
            _project_run(root, incr_store, out_incr)

            # Full lane: fresh store each step (genuine cold rescan).
            with FactStore(":memory:") as full_store:
                _project_run(root, full_store, out_full)

            _assert_dirs_identical(out_incr, out_full, label)
    finally:
        incr_store.close()


@requires_ts
def test_new_root_file_and_new_directory_absorbed(tmp_path):
    """P2-1 mandatory: a new root-level file and a new directory are included.

    Drives the warm incremental path (the store already holds the baseline),
    then asserts both the new root file and the new directory's file land in
    the projection (coverage ledger and files), not silently dropped.
    """
    root = _copy_fixture(tmp_path / "repo")
    store_path = tmp_path / "index.db"
    out = tmp_path / "out"

    store = FactStore(str(store_path))
    try:
        _project_run(root, store, out)  # cold baseline

        (root / "brandnew_root.py").write_text("def r():\n    return 'root'\n")
        newdir = root / "services/api/api/newpkg"
        newdir.mkdir(parents=True)
        (newdir / "mod.py").write_text("def n():\n    return 'dir'\n")

        _project_run(root, store, out)  # warm incremental
    finally:
        store.close()

    coverage = json.loads((out / "coverage.json").read_text())
    parsed = {r["path"] for r in coverage["rows"] if r["disposition"] == "parsed"}
    assert "brandnew_root.py" in parsed, "new root-level file was dropped"
    assert "services/api/api/newpkg/mod.py" in parsed, "new-directory file was dropped"

    # The new-directory file also reaches a component's detail shard (not lost
    # between the store and the viewer artifacts).
    all_shard_files: set[str] = set()
    for shard in (out / "data").glob("detail-*.json"):
        detail = json.loads(shard.read_text())
        all_shard_files.update(f["path"] for f in detail["files"])
    assert "services/api/api/newpkg/mod.py" in all_shard_files
    assert "brandnew_root.py" in all_shard_files


@requires_ts
def test_touch_one_file_reparses_only_that_file(tmp_path):
    """Acceptance 2: on a warm store only the changed file re-parses.

    The affected scope at the tier that actually costs (parsing) is exactly the
    changed file; every other file is served from the content-hash cache.
    """
    root = _copy_fixture(tmp_path / "repo")
    store_path = tmp_path / "index.db"

    with FactStore(str(store_path)) as store:
        cold = extract_repo(root, store)
        assert cold.files_parsed > 0 and cold.files_cached == 0

    with FactStore(str(store_path)) as store:
        warm = extract_repo(root, store)
        assert warm.files_parsed == 0, "warm re-run with no change re-parsed files"
        assert warm.files_cached == cold.files_parsed

    f = root / "services/api/api/server.py"
    f.write_text(f.read_text() + "\n# touched\n")
    with FactStore(str(store_path)) as store:
        after = extract_repo(root, store)
        assert after.files_parsed == 1, "touching one file re-parsed more than one"
        assert after.files_cached == cold.files_parsed - 1


@requires_ts
def test_changelog_serials_and_entries_across_sequence(tmp_path):
    """P4-6 item 5: consecutive incremental runs produce correct serials.

    Serials increment by one per run (P4-5 proved single-step equivalence; this
    proves the sequence), and structural steps emit the expected change entries
    while a no-op re-run appends no new entry.
    """
    root = _copy_fixture(tmp_path / "repo")
    store_path = tmp_path / "index.db"
    out = tmp_path / "out"

    store = FactStore(str(store_path))
    serials: list[int] = []
    try:
        for _label, mutate in _seq_steps():
            mutate(root)
            manifest = _project_run(root, store, out)
            serials.append(manifest["changelog_serial"])

        # A no-op re-run: serial still advances, but no new entry is appended.
        before_entries = len(manifest["changelog"])
        manifest2 = _project_run(root, store, out)
    finally:
        store.close()

    assert serials == list(range(1, len(serials) + 1)), (
        f"serials not consecutive from 1: {serials}"
    )
    assert manifest2["changelog_serial"] == serials[-1] + 1
    assert len(manifest2["changelog"]) == before_entries, (
        "a no-op re-run appended a changelog entry"
    )

    # The marker-file step created a new component: a component_added entry
    # exists somewhere in the accumulated changelog.
    kinds = {
        c["kind"]
        for entry in manifest2["changelog"]
        for c in entry.get("changes", [])
    }
    assert "component_added" in kinds, "new-marker component_added not recorded"


@requires_ts
def test_v2_never_writes_arch_baseline_caches(tmp_path):
    """P4-6 item 4: the store is the baseline; no .arch-baseline on the v2 path.

    Runs the real CLI (``analyze.py --engine v2``) cold then warm and asserts
    the old engine's ``.arch-baseline/file-index.json`` / ``import-graph.json``
    caches are never created under the scanned root.
    """
    root = _copy_fixture(tmp_path / "repo")
    out = tmp_path / "out"
    store_path = tmp_path / "index.db"
    repo_root = Path(__file__).resolve().parent.parent

    def run() -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "analyze.py", str(root), "-o", str(out),
             "--split", "--engine", "v2", "--store", str(store_path)],
            cwd=repo_root, capture_output=True, text=True, timeout=180,
        )

    r1 = run()
    assert r1.returncode == 0, f"cold v2 run failed: {r1.stderr}"
    r2 = run()
    assert r2.returncode == 0, f"warm v2 run failed: {r2.stderr}"

    baseline = root / ".arch-baseline"
    assert not baseline.exists(), ".arch-baseline was created on the v2 path"
    assert not (root / ".arch-baseline" / "file-index.json").exists()
    assert not (root / ".arch-baseline" / "import-graph.json").exists()
    # The store is the baseline and it persists.
    assert store_path.exists() and store_path.stat().st_size > 0
    # Warm run reports the cache hit (cost tracks change size).
    assert "cached" in r2.stdout


@requires_ts
def test_cli_engine_v2_incremental_flags_accepted(tmp_path):
    """P4-6 item 2 / acceptance 3: legacy incremental flags are no-op-accepted.

    ``--engine v2 --incremental --base-sha ... --split`` must run to completion
    (v1 rejects --incremental with --split; v2 accepts it) and produce output.
    """
    root = _copy_fixture(tmp_path / "repo")
    out = tmp_path / "out"
    repo_root = Path(__file__).resolve().parent.parent

    r = subprocess.run(
        [sys.executable, "analyze.py", str(root), "-o", str(out), "--split",
         "--engine", "v2", "--incremental", "--base-sha", "deadbeef",
         "--store", str(tmp_path / "index.db")],
        cwd=repo_root, capture_output=True, text=True, timeout=180,
    )
    assert r.returncode == 0, f"v2 --incremental was rejected: {r.stderr}"
    assert (out / "manifest.json").is_file()
    assert "incremental by construction" in r.stdout


@requires_ts
def test_default_store_under_root_cold_warm_parity(tmp_path):
    """The default store location (<root>/.solution-explorer) is parity-safe.

    Cold and warm runs against the default store project byte-identically. The
    store lives in a dot-directory that extraction prunes as one ledger row, and
    the directory is created before enumeration, so the row is present on both
    runs (no coverage drift). This exercises the default path the CLI uses.
    """
    root = _copy_fixture(tmp_path / "repo")
    store_path = default_store_path(root)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    out_cold = tmp_path / "out_cold"
    out_warm = tmp_path / "out_warm"

    # Cold: fresh store at the default location.
    with FactStore(str(store_path)) as store:
        m_cold = _project_run(root, store, out_cold)
    # Warm: reopen the same store.
    with FactStore(str(store_path)) as store:
        _project_run(root, store, out_warm)

    # The .solution-explorer directory is accounted for exactly once as an
    # excluded directory (honest, not silent) in both runs.
    assert m_cold["coverage"]["summary"].get("excluded:skipped_directory", 0) >= 1
    cov_rows = {
        r["path"]: r["reason"]
        for r in json.loads((out_cold / "coverage.json").read_text())["rows"]
    }
    assert cov_rows.get(".solution-explorer") == ".solution-explorer"

    _assert_dirs_identical(out_warm, out_cold, "default-store-cold-warm")


@requires_ts
def test_warm_derivation_reads_zero_source_files(tmp_path):
    """Derivation reads only the store, warm or cold (P4-3 invariant holds).

    On a warm store the content join comes from the extraction cache, not the
    disk, so a warm re-derive must still open zero source files.
    """
    root = _copy_fixture(tmp_path / "repo")
    store_path = tmp_path / "index.db"

    with FactStore(str(store_path)) as store:
        extract_repo(root, store)
        derive_all(store, REPO_NAME, root_path=str(root))

    with FactStore(str(store_path)) as store:
        extract_repo(root, store)  # warm: parses nothing
        with source_read_audit() as audit:
            derive_all(store, REPO_NAME, root_path=str(root))
    assert audit.count == 0, f"warm derivation read source files: {audit.paths}"
