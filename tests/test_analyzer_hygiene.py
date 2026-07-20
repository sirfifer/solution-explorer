"""Analyzer honesty: gitignore honoring, empty-file and tool-state accounting.

Three recorded items, one wave (TASKS.md Discovered 2026-07-18 gitignore gap and
2026-07-19 Campaign dogfood empty-file / tool-state classes):

  1. The v2 enumerator consults .gitignore. Ignored DIRECTORIES prune to one
     ``excluded:gitignored`` row (like .git), ignored FILES get one per-file row,
     and both land in the ``workstation_ignored`` inventory group. Fresh clones
     contain no ignored files, so CI output is byte-identical.
  2. An empty file is accounted as ``excluded:empty_file`` and classified into the
     dedicated ``empty_files`` group instead of falling through path rules to the
     loud ``unknown`` bucket.
  3. The tool's own ``.solution-explorer`` state directory is accounted as one
     ``excluded:tool_state`` row and never walked, while the committed
     ``rules/inventory.yml`` under it is still read by the rules loader (which
     opens it by path, not through enumeration).

Every fixture is a real tree with a real .gitignore under tmp_path. No mocks.
"""

from __future__ import annotations

from pathlib import Path

from analyzer.extract import extract_repo
from analyzer.project.coverage import build_coverage, coverage_families
from analyzer.project.inventory import (
    NON_SOURCE_DISPOSITIONS,
    classify_row,
)
from analyzer.project.rules import PROJECT_RULES_RELPATH, load_rule_set
from analyzer.store import FactStore
from analyzer.utils import GitignoreMatcher


def _dispositions(store: FactStore) -> dict[str, str]:
    """path -> disposition for every ledger row."""
    return {r["path"]: r["disposition"] for r in store.coverage()}


def _reasons(store: FactStore) -> dict[str, str]:
    return {r["path"]: r.get("reason") for r in store.coverage()}


# ---------------------------------------------------------------------------
# GitignoreMatcher unit behavior (nested files, dir-only, negation, anchoring)
# ---------------------------------------------------------------------------

def test_matcher_common_forms(tmp_path):
    (tmp_path / ".gitignore").write_text(
        "*.log\n"          # extension glob at any depth
        "build/\n"          # directory-only
        "!keep.log\n"       # negation (same file, last match wins)
        "/root_only.txt\n"  # anchored to the repo root
        "TestResults.xcresult/\n",
        encoding="utf-8",
    )
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
    m = GitignoreMatcher(tmp_path)

    assert m.match("a.log", is_dir=False) == "*.log"
    assert m.match("deep/nested/a.log", is_dir=False) == "*.log"
    assert m.match("keep.log", is_dir=False) is None  # negation wins
    assert m.match("build", is_dir=True) == "build/"
    assert m.match("build", is_dir=False) is None      # dir-only never ignores a file
    assert m.match("root_only.txt", is_dir=False) == "/root_only.txt"
    assert m.match("sub/root_only.txt", is_dir=False) is None  # anchored to root only
    assert m.match("TestResults.xcresult", is_dir=True) == "TestResults.xcresult/"
    # A per-directory .gitignore applies to its own subtree.
    assert m.match("sub/secret.txt", is_dir=False) == "secret.txt"
    assert m.match("sub/other.txt", is_dir=False) is None
    assert m.match("src/main.py", is_dir=False) is None


def test_matcher_negation_across_extension_family(tmp_path):
    (tmp_path / ".gitignore").write_text("*.tmp\n!important.tmp\n", encoding="utf-8")
    m = GitignoreMatcher(tmp_path)
    assert m.match("scratch.tmp", is_dir=False) == "*.tmp"
    assert m.match("important.tmp", is_dir=False) is None


# ---------------------------------------------------------------------------
# Item 1: gitignore honoring end to end (the xcresult fail-before shape)
# ---------------------------------------------------------------------------

def test_gitignored_directory_prunes_to_one_row_not_thousands(tmp_path):
    # Fail-before shape: a gitignored directory with many files inside must yield
    # ONE pruned ledger row, not one binary row per contained file (the
    # unamentis-ios 5,970-row TestResults.xcresult case).
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    xc = tmp_path / "TestResults.xcresult" / "Data"
    xc.mkdir(parents=True)
    for i in range(200):
        (xc / f"blob{i}.bin").write_bytes(b"\x00\x01\x02\x03")
    (tmp_path / ".gitignore").write_text("TestResults.xcresult/\n", encoding="utf-8")

    store = FactStore(":memory:")
    extract_repo(tmp_path, store)
    disp = _dispositions(store)

    # Exactly one row for the whole bundle, and nothing beneath it enumerated.
    assert disp.get("TestResults.xcresult") == "excluded:gitignored"
    inside = [p for p in disp if p.startswith("TestResults.xcresult/")]
    assert inside == [], f"gitignored bundle leaked per-file rows: {inside[:5]}"
    # The real source is unaffected.
    assert disp.get("src/app.py") == "parsed"


def test_gitignored_file_gets_one_row(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "debug.log").write_text("noise\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")

    store = FactStore(":memory:")
    extract_repo(tmp_path, store)
    disp = _dispositions(store)
    assert disp.get("debug.log") == "excluded:gitignored"
    assert _reasons(store).get("debug.log") == "*.log"


def test_gitignored_rows_are_non_source_never_a_coverage_gap(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "debug.log").write_text("noise\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    store = FactStore(":memory:")
    extract_repo(tmp_path, store)

    fam = coverage_families(store.coverage_summary())
    # The gitignored file is non-source, so it is NEVER in the percent denominator.
    assert fam["nonsource"] >= 1
    assert fam["gap"] == 0
    assert fam["source_total"] == fam["analyzed"]


def test_fresh_clone_parity_no_gitignore_no_change(tmp_path):
    # A clone contains no ignored files. With a .gitignore present but nothing it
    # matches on disk, enumeration output is identical to having no .gitignore.
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# hi\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("build/\n*.log\n", encoding="utf-8")
    store = FactStore(":memory:")
    extract_repo(tmp_path, store)
    disp = _dispositions(store)
    assert "excluded:gitignored" not in set(disp.values())


# ---------------------------------------------------------------------------
# Item 2: empty files get their own category (the tests/__init__.py fail-before)
# ---------------------------------------------------------------------------

def test_empty_file_classifies_as_empty_files_not_unknown(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    store = FactStore(":memory:")
    extract_repo(tmp_path, store)

    disp = _dispositions(store)
    assert disp.get("tests/__init__.py") == "excluded:empty_file"

    inv = build_coverage(store, root=tmp_path)["inventory"]
    ids = {g["id"] for g in inv["groups"]}
    assert "empty_files" in ids
    assert "unknown" not in ids


def test_empty_file_classifier_fail_before_was_unknown():
    # Directly: the disposition-based rule beats the extension fall-through that
    # used to drop an empty .py into unknown.
    assert classify_row("tests/__init__.py", "excluded:empty_file", None) == "empty_files"
    assert classify_row("pkg/__init__.py", "excluded:empty_file", None) == "empty_files"


# ---------------------------------------------------------------------------
# Item 3: the tool's own state directory is accounted, never scanned as source
# ---------------------------------------------------------------------------

def _make_repo_with_tool_state(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    state = tmp_path / ".solution-explorer"
    (state / "rules").mkdir(parents=True)
    # A committed rule file the loader must still read by path.
    (state / "rules" / "inventory.yml").write_text(
        "rules:\n"
        "  - id: local-widgets\n"
        "    pattern: '*.widget'\n"
        "    category: config\n"
        "    source: human\n",
        encoding="utf-8",
    )
    # A local-only store and a python file that must NEVER be parsed as source.
    (state / "index.db").write_bytes(b"SQLite format 3\x00")
    (state / "notatarget.py").write_text("import os\n", encoding="utf-8")
    return tmp_path


def test_tool_state_dir_is_one_pruned_row_never_parsed(tmp_path):
    root = _make_repo_with_tool_state(tmp_path)
    store = FactStore(":memory:")
    extract_repo(root, store)
    disp = _dispositions(store)

    assert disp.get(".solution-explorer") == "excluded:tool_state"
    assert _reasons(store).get(".solution-explorer") == "solution-explorer tool state"
    # Nothing under it is enumerated: no per-file rows and, crucially, no parsed
    # source (the stray notatarget.py inside must not become a symbol source).
    inside = [p for p in disp if p.startswith(".solution-explorer/") or p.startswith(".solution-explorer\\")]
    assert inside == [], f"tool-state contents leaked into the ledger: {inside}"
    file_paths = {f["path"] for f in store.files()}
    assert not any(p.startswith(".solution-explorer") for p in file_paths)

    inv = build_coverage(store, root=root)["inventory"]
    ids = {g["id"] for g in inv["groups"]}
    assert "tool_state" in ids
    assert "unknown" not in ids


def test_tool_state_pruned_but_rules_loader_still_reads_the_rule_file(tmp_path):
    # The pruning is enumeration-only. The rules loader opens
    # .solution-explorer/rules/inventory.yml directly by path, so the learned
    # project rule still loads and applies even though the directory is never
    # walked by the enumerator.
    root = _make_repo_with_tool_state(tmp_path)
    store = FactStore(":memory:")
    extract_repo(root, store)

    # The file exists at the frozen relpath the loader consults.
    assert (root / PROJECT_RULES_RELPATH).is_file()
    ruleset = load_rule_set(root)
    assert not ruleset.is_empty()
    matched = ruleset.match_project("assets/foo.widget")
    assert matched is not None and matched.id == "local-widgets"

    # And end to end through the inventory: the rule reclassifies a .widget file.
    (root / "thing.widget").write_text("data\n", encoding="utf-8")
    store2 = FactStore(":memory:")
    extract_repo(root, store2)
    inv = build_coverage(store2, root=root)["inventory"]
    widget_group = [g for g in inv["groups"] if any(s == "thing.widget" for s in g["samples"])]
    assert widget_group and widget_group[0]["id"] == "config"


# ---------------------------------------------------------------------------
# EXTRACT_TIER / warm-store transition: a previously-parsed file that becomes
# gitignored before a warm re-run ledgers excluded:gitignored with no stale rows.
# ---------------------------------------------------------------------------

def test_warm_store_gitignore_transition_leaves_no_stale_symbol_rows(tmp_path):
    (tmp_path / "src").mkdir()
    target = tmp_path / "src" / "mod.py"
    target.write_text("def alpha():\n    return 1\n\ndef beta():\n    return 2\n", encoding="utf-8")

    store = FactStore(":memory:")  # one store reused across runs = warm cache
    extract_repo(tmp_path, store)

    # Run 1: the file is parsed and contributes symbols.
    disp1 = _dispositions(store)
    assert disp1.get("src/mod.py") == "parsed"
    sym_files_1 = {f["path"] for f in store.files()}
    assert "src/mod.py" in sym_files_1
    assert any(s["name"] in {"alpha", "beta"} for s in store.symbols())

    # Gitignore it, then re-run against the WARM store (cache retained).
    (tmp_path / ".gitignore").write_text("src/mod.py\n", encoding="utf-8")
    extract_repo(tmp_path, store)

    disp2 = _dispositions(store)
    assert disp2.get("src/mod.py") == "excluded:gitignored"
    # clear_extraction_facts rebuilds the file/symbol/coverage rows every run, so
    # the now-ignored file leaves NO stale file row and NO stale symbol rows.
    assert "src/mod.py" not in {f["path"] for f in store.files()}
    assert not any(s["name"] in {"alpha", "beta"} for s in store.symbols())


# ---------------------------------------------------------------------------
# Cross-mirror sync: the analyzer set and the CLI coverage mirror agree, and all
# three new dispositions are non-source in both.
# ---------------------------------------------------------------------------

def test_new_dispositions_are_non_source_in_every_mirror():
    for disp in ("excluded:gitignored", "excluded:tool_state", "excluded:empty_file"):
        assert disp in NON_SOURCE_DISPOSITIONS
    # coverage_families imports the same frozenset, so a summary of only the new
    # dispositions has zero source and zero gap: pure non-source.
    fam = coverage_families({
        "excluded:gitignored": 3,
        "excluded:tool_state": 1,
        "excluded:empty_file": 2,
    })
    assert fam["gap"] == 0
    assert fam["analyzed"] == 0
    assert fam["nonsource"] == 6
    assert fam["source_total"] == 0
