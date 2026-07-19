"""Tests for the Tier 1 parallel extraction tier (P4-2).

These assert observable behavior of the real runner against the committed
fixture repos and constructed temp repos, never a reimplementation. The store
is the in-memory FactStore; parsers are the real tree-sitter parsers.

The nested-symbol and determinism guards are regression tests by construction:
each asserts a property that the pre-P4-2 world (top-level-only symbols, no
content-hash cache, no parser tier in the cache key) could not satisfy. See the
card Evidence for the stash/bypass proofs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from analyzer.extract import extract_repo
from analyzer.extract.runner import EXTRACT_TIER, parser_version
from analyzer.parsers import PARSERS
from analyzer.store import FactStore, parse_symbol_id

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "polyglot")

# The seven tree-sitter languages and a fixture file extension for each.
TS_LANGS = {
    "python": ".py",
    "typescript": ".ts",
    "javascript": ".js",
    "go": ".go",
    "rust": ".rs",
    "ruby": ".rb",
    "swift": ".swift",
}

_TS_AVAILABLE = all(
    getattr(PARSERS.get(lang), "_ts_available", False) for lang in TS_LANGS
)
requires_ts = pytest.mark.skipif(
    not _TS_AVAILABLE,
    reason="tree-sitter parsers unavailable; nested-symbol facts need the ts tier",
)


def _store_and_extract(root, **kw):
    store = FactStore(":memory:")
    result = extract_repo(root, store, **kw)
    return store, result


# ---------------------------------------------------------------------------
# Nested symbols with parent references, all seven languages
# ---------------------------------------------------------------------------

@requires_ts
def test_methods_have_parents_for_every_ts_language():
    store, _ = _store_and_extract(FIXTURE)
    symbols = store.symbols()

    # Bucket symbols by the language of their (grammar-ID) file segment.
    ext_to_lang = {ext: lang for lang, ext in TS_LANGS.items()}
    by_lang: dict[str, list[dict]] = {}
    for sym in symbols:
        sid = parse_symbol_id(sym["id"])
        ext = "." + sid.file.rsplit(".", 1)[-1]
        lang = ext_to_lang.get(ext)
        if lang:
            by_lang.setdefault(lang, []).append(sym)

    for lang in TS_LANGS:
        rows = by_lang.get(lang, [])
        assert rows, f"no symbols extracted for {lang}"
        with_parent = [r for r in rows if r["parent_id"]]
        assert with_parent, f"{lang}: no symbol carries a parent reference"
        # Every parent_id must resolve to a real symbol in the store.
        ids = {r["id"] for r in symbols}
        for r in with_parent:
            assert r["parent_id"] in ids, f"{lang}: dangling parent_id"


@requires_ts
def test_symbol_ids_are_grammar_ids_not_legacy_strings():
    store, _ = _store_and_extract(FIXTURE)
    for sym in store.symbols():
        # Legacy IDs were "file:name:line"; grammar IDs are 4 space-separated
        # segments and round-trip through parse_symbol_id.
        parsed = parse_symbol_id(sym["id"])
        assert parsed.file
        assert parsed.path
        assert sym["id"] == parsed.encode()


@requires_ts
def test_exact_ranges_from_tree_sitter_nodes():
    # Tree-sitter gives exact node ranges. Assert every symbol reports a real
    # span (end_line >= line) and that a lexically nested child sits inside its
    # parent's span. Go methods are semantically (not lexically) parented to
    # their receiver type, so containment is asserted only when the child
    # actually starts inside the parent's span.
    store, _ = _store_and_extract(FIXTURE)
    rows = {r["id"]: r for r in store.symbols()}
    saw_multiline = False
    for r in rows.values():
        assert r["end_line"] >= r["line"]
        if r["end_line"] > r["line"]:
            saw_multiline = True
        if r["parent_id"]:
            parent = rows[r["parent_id"]]
            if parent["line"] <= r["line"] <= parent["end_line"]:
                assert r["end_line"] <= parent["end_line"]
    assert saw_multiline, "no multi-line symbol ranges extracted"


# ---------------------------------------------------------------------------
# Content-hash cache (invariant I6)
# ---------------------------------------------------------------------------

def test_warm_rerun_parses_zero_files():
    store = FactStore(":memory:")
    r1 = extract_repo(FIXTURE, store)
    assert r1.files_parsed > 0
    r2 = extract_repo(FIXTURE, store)
    assert r2.files_parsed == 0
    assert r2.parse_queue_size == 0
    assert r2.files_cached == r1.files_parsed
    # The store is rebuilt, not duplicated.
    assert len(store.files()) == len(FactStore(":memory:").files()) + r1.files_parsed


def test_touching_one_file_reparses_exactly_one(tmp_path):
    import shutil

    dst = tmp_path / "poly"
    shutil.copytree(FIXTURE, dst)
    store = FactStore(":memory:")
    extract_repo(dst, store)

    target = dst / "services" / "api" / "api" / "server.py"
    target.write_text(target.read_text() + "\n# touch\n")

    r = extract_repo(dst, store)
    assert r.files_parsed == 1
    assert r.files_cached >= 1


def test_parser_tier_is_encoded_in_parser_version():
    p = PARSERS["python"]
    orig = p._ts_available
    try:
        p._ts_available = True
        ts_v = parser_version("python", p)
        p._ts_available = False
        rx_v = parser_version("python", p)
    finally:
        p._ts_available = orig
    assert ts_v != rx_v
    assert ts_v.startswith(EXTRACT_TIER)
    assert ":ts" in ts_v and ":regex" in rx_v


def test_regex_fallback_marks_symbols_and_keeps_top_level(tmp_path):
    # Force the regex tier for python and confirm facts are marked via_regex
    # and carry no parent references (the pre-P4-2 top-level-only behavior).
    p = PARSERS["python"]
    content = "class Foo:\n    def bar(self):\n        pass\n"
    orig = p._ts_available
    try:
        p._ts_available = False
        syms = p.extract_nested_symbols(content, "m.py")
    finally:
        p._ts_available = orig
    assert syms, "regex fallback produced no symbols"
    assert all(s.via_regex for s in syms)
    assert all(s.parent_index is None for s in syms)


# ---------------------------------------------------------------------------
# Coverage ledger (invariant I2)
# ---------------------------------------------------------------------------

def test_ledger_accounts_for_every_enumerated_file():
    store, result = _store_and_extract(FIXTURE)
    coverage = store.coverage()
    # Every ledger row for a file (excluding pruned-directory rows) is unique.
    file_rows = [
        c for c in coverage
        if not c["disposition"].startswith("excluded:skipped_directory")
        and not c["disposition"].startswith("excluded:vendored_repo")
    ]
    paths = [c["path"] for c in file_rows]
    assert len(paths) == len(set(paths)), "duplicate ledger rows"

    # parsed count in the ledger equals the files table count (invariant I2).
    parsed = [c for c in coverage if c["disposition"] == "parsed"]
    assert len(parsed) == len(store.files())
    assert len(parsed) == result.files_parsed + result.files_cached

    # Ledger file-row count equals the number of files under the root (the
    # fixture has no pruned directories), i.e. no file is silently dropped.
    actual_files = sum(len(fs) for _, _, fs in os.walk(FIXTURE))
    assert len(file_rows) == actual_files


def test_max_file_size_is_opt_in_and_lands_in_the_ledger(tmp_path):
    (tmp_path / "big.py").write_text("x = 1\n" * 5000)
    (tmp_path / "small.py").write_text("y = 2\n")

    # Default: no bound, the big file is parsed (no silent skip).
    store, _ = _store_and_extract(tmp_path)
    disp = {c["path"]: c["disposition"] for c in store.coverage()}
    assert disp["big.py"] == "parsed"

    # Opt-in bound: the big file is excluded with a visible ledger disposition.
    store2, _ = _store_and_extract(tmp_path, max_file_size=100)
    disp2 = {c["path"]: c["disposition"] for c in store2.coverage()}
    assert disp2["big.py"] == "excluded:max_file_size"
    assert disp2["small.py"] == "parsed"


def test_unreadable_file_lands_as_failed_not_silent(tmp_path, monkeypatch):
    # A read error must surface as a failed:<error> ledger row, never a silent
    # drop. Simulate by making one file's read_bytes raise.
    (tmp_path / "ok.py").write_text("a = 1\n")
    bad = tmp_path / "bad.py"
    bad.write_text("b = 2\n")

    import pathlib

    real_read_bytes = pathlib.Path.read_bytes

    def flaky_read_bytes(self):
        if self.name == "bad.py":
            raise OSError("permission denied")
        return real_read_bytes(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", flaky_read_bytes)
    store, _ = _store_and_extract(tmp_path)
    disp = {c["path"]: c["disposition"] for c in store.coverage()}
    assert disp["bad.py"] == "failed"
    assert disp["ok.py"] == "parsed"


def test_binary_file_lands_as_binary(tmp_path):
    (tmp_path / "data.py").write_bytes(b"print('hi')\x00\x01binary\n")
    (tmp_path / "clean.py").write_text("print('hi')\n")
    store, _ = _store_and_extract(tmp_path)
    disp = {c["path"]: c["disposition"] for c in store.coverage()}
    assert disp["data.py"] == "binary"
    assert disp["clean.py"] == "parsed"


# ---------------------------------------------------------------------------
# Signals (single read per file; TARGET 4.1)
# ---------------------------------------------------------------------------

def test_signal_kinds_extracted_on_fixtures():
    store, _ = _store_and_extract(FIXTURE)
    kinds = {s["kind"] for s in store.signals()}
    # The polyglot fixture exercises a server, a client, and infra, so these
    # signal kinds must appear.
    for expected in ("port", "endpoint", "framework", "url_reference"):
        assert expected in kinds, f"missing signal kind: {expected}"
    # Every signal carries a kind and a JSON-serializable value.
    for s in store.signals():
        assert s["kind"]
        json.dumps(s["value"])


def test_signals_carry_line_numbers_where_locatable():
    store, _ = _store_and_extract(FIXTURE)
    located = [s for s in store.signals() if s["line"] is not None]
    assert located, "no signal recorded a line number"
    for s in located:
        assert s["line"] >= 1


# ---------------------------------------------------------------------------
# Determinism (invariant I4)
# ---------------------------------------------------------------------------

def _dump(root) -> str:
    store = FactStore(":memory:")
    extract_repo(root, store)
    return json.dumps(
        {
            "files": store.files(),
            "symbols": store.symbols(),
            "signals": store.signals(),
            "coverage": store.coverage(),
        },
        sort_keys=True,
        default=str,
    )


def test_two_cold_runs_produce_identical_store_contents():
    assert _dump(FIXTURE) == _dump(FIXTURE)


def test_determinism_across_process_hash_seeds():
    # The old engine's set-derived lists were PYTHONHASHSEED-dependent across
    # processes (TASKS.md Discovered 2026-07-13). Run the extraction in two
    # fresh processes under different seeds and diff the store dump.
    script = (
        "import json,sys;"
        "from analyzer.store import FactStore;"
        "from analyzer.extract import extract_repo;"
        "s=FactStore(':memory:');"
        f"extract_repo({FIXTURE!r}, s);"
        "print(json.dumps({'f':s.files(),'y':s.symbols(),"
        "'g':s.signals(),'c':s.coverage()},sort_keys=True,default=str))"
    )
    repo_root = os.path.dirname(os.path.dirname(__file__))

    def run(seed):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        out = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True,
            env=env, cwd=repo_root, check=True,
        )
        return out.stdout

    assert run("0") == run("1") == run("12345")


# ---------------------------------------------------------------------------
# In-run retry for transient failures (P4-8)
# ---------------------------------------------------------------------------
#
# These inject failures through the REAL worker function on a REAL store and
# real temp files. The small temp repos stay under INLINE_THRESHOLD so the
# runner parses inline, which means monkeypatching the module-level worker in
# the parent process reaches the code path the run actually executes (the pool
# path runs the worker in child processes, out of monkeypatch reach; it has its
# own pool-death test below that forces the pool branch with a stub executor).

from concurrent.futures.process import BrokenProcessPool  # noqa: E402

from analyzer.extract import runner as _runner  # noqa: E402
from analyzer.extract.runner import INLINE_THRESHOLD  # noqa: E402


def _dump_store(store) -> str:
    return json.dumps(
        {
            "files": store.files(),
            "symbols": store.symbols(),
            "signals": store.signals(),
            "coverage": store.coverage(),
        },
        sort_keys=True,
        default=str,
    )


def test_transient_failure_is_retried_then_parsed(tmp_path, monkeypatch):
    # A worker that crashes once on flaky.py (transient OSError) then succeeds.
    # Pre-fix (no retry) this file lands failed; post-fix it lands parsed.
    (tmp_path / "steady.py").write_text("a = 1\n")
    (tmp_path / "flaky.py").write_text("b = 2\n")

    real = _runner._parse_worker
    calls: dict[str, int] = {}

    def flaky(task):
        rel = task[0]
        if rel == "flaky.py":
            calls[rel] = calls.get(rel, 0) + 1
            if calls[rel] == 1:
                return (rel, "failed", "OSError: transient worker crash")
        return real(task)

    monkeypatch.setattr(_runner, "_parse_worker", flaky)
    store = FactStore(":memory:")
    result = extract_repo(tmp_path, store)

    disp = {c["path"]: c["disposition"] for c in store.coverage()}
    assert disp["flaky.py"] == "parsed"
    assert disp["steady.py"] == "parsed"
    assert calls["flaky.py"] == 2  # failed once, retried once, then succeeded
    assert result.files_failed == 0


def test_retried_success_is_identical_to_first_try_success(tmp_path, monkeypatch):
    # A file that succeeds on a retry must be byte-indistinguishable in the store
    # from one that succeeded on the first try (invariant I4; parity).
    (tmp_path / "steady.py").write_text("a = 1\n")
    (tmp_path / "flaky.py").write_text("b = 2\n")

    clean = FactStore(":memory:")
    extract_repo(tmp_path, clean)
    clean_dump = _dump_store(clean)

    real = _runner._parse_worker
    calls: dict[str, int] = {}

    def flaky(task):
        rel = task[0]
        if rel == "flaky.py":
            calls[rel] = calls.get(rel, 0) + 1
            if calls[rel] == 1:
                return (rel, "failed", "MemoryError: transient")
        return real(task)

    monkeypatch.setattr(_runner, "_parse_worker", flaky)
    retried = FactStore(":memory:")
    extract_repo(tmp_path, retried)

    assert _dump_store(retried) == clean_dump


def test_deterministic_failure_stands_with_attempts_recorded(tmp_path, monkeypatch):
    # A parser exception on stable input is deterministic: retried once (2 total
    # attempts) then it stands, with the attempt count in the ledger reason.
    (tmp_path / "bad.py").write_text("x = 1\n")

    def always_syntax(task):
        return (task[0], "failed", "SyntaxError: unbalanced parens")

    monkeypatch.setattr(_runner, "_parse_worker", always_syntax)
    store = FactStore(":memory:")
    result = extract_repo(tmp_path, store)

    row = {c["path"]: c for c in store.coverage()}["bad.py"]
    assert row["disposition"] == "failed"
    assert "failed after 2 attempts" in row["reason"]
    assert "SyntaxError" in row["reason"]
    assert result.files_failed == 1


def test_permanent_transient_failure_exhausts_the_budget(tmp_path, monkeypatch):
    # A transient candidate that never recovers is tried the full 3 times and
    # then lands failed with all attempts recorded.
    (tmp_path / "gone.py").write_text("y = 2\n")

    def always_oserror(task):
        return (task[0], "failed", "OSError: disk vanished")

    monkeypatch.setattr(_runner, "_parse_worker", always_oserror)
    store = FactStore(":memory:")
    extract_repo(tmp_path, store)

    row = {c["path"]: c for c in store.coverage()}["gone.py"]
    assert row["disposition"] == "failed"
    assert "failed after 3 attempts" in row["reason"]
    assert "OSError" in row["reason"]


@pytest.mark.skipif(
    (os.cpu_count() or 1) < 2,
    reason="pool path needs more than one worker; single-CPU host parses inline",
)
def test_pool_death_is_rebuilt_not_aborted(tmp_path, monkeypatch):
    # If the pool itself dies (BrokenProcessPool while draining the map), the run
    # rebuilds the pool for the retry pass rather than aborting. Force the pool
    # path with enough files, then stub the executor so its first map dies and
    # its second succeeds.
    for i in range(INLINE_THRESHOLD + 2):
        (tmp_path / f"m{i}.py").write_text(f"v{i} = {i}\n")

    real = _runner._parse_worker
    state = {"n": 0}

    class OneDeathPool:
        def __init__(self, max_workers=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def map(self, fn, tasks):
            state["n"] += 1
            if state["n"] == 1:
                raise BrokenProcessPool("a worker segfaulted")
            return [real(t) for t in tasks]

    monkeypatch.setattr(_runner, "ProcessPoolExecutor", OneDeathPool)
    store = FactStore(":memory:")
    result = extract_repo(tmp_path, store, max_workers=4)

    disp = {c["path"]: c["disposition"] for c in store.coverage()}
    assert all(d == "parsed" for d in disp.values())
    assert result.files_failed == 0
    assert state["n"] == 2  # pool died once, was rebuilt, then succeeded
