"""Coverage-ledger completeness invariant (P4-4; TARGET-ARCHITECTURE.md I2).

These tests encode the "shows you everything" invariant end to end, with the
pruned-directory disposition ruling adopted for the ledger:

  - An excluded DIRECTORY is a single ledger row whose rule explains everything
    beneath it (``excluded:skipped_directory`` / ``excluded:vendored_repo``).
    Enumerating every file inside ``node_modules`` / ``.git`` would defeat scale
    (invariant O5), so the directory row stands in for its contents.
  - ``failed``, ``binary``, and oversized (``excluded:max_file_size``) files are
    PER FILE: each gets its own row so nothing hides.

Accounting: every file under the scan root is accounted for exactly once, where
"accounted" means EITHER it has its own per-file ledger row, OR (when it has no
row of its own) it sits under exactly one excluded-directory row. A file with
its own row is accounted by that row even if it also happens to live under a
pruned directory (the CI-config rescue does exactly this), so the directory row
never double-counts it.

The invariant is asserted against the real extraction runner (the store ledger)
and against the projected ``coverage.json`` the viewer actually fetches, on the
committed fixtures and on a live scan of this repository.
"""

from __future__ import annotations

import json
import os
import pathlib
from pathlib import Path

import pytest

from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.project.pipeline import project_split
from analyzer.store import FactStore

REPO_ROOT = Path(__file__).resolve().parent.parent
POLYGLOT = REPO_ROOT / "tests" / "fixtures" / "polyglot"
MULTI = REPO_ROOT / "tests" / "fixtures" / "multi"

# Dispositions whose row is a DIRECTORY standing in for everything beneath it.
# ``excluded:tool_state`` is always the pruned ``.solution-explorer`` directory.
# ``excluded:gitignored`` is USUALLY a pruned directory but can also be a single
# gitignored file; a file row here only ever accounts for itself (its path equals
# the tested path), so treating it as subtree-standing is safe for the count.
DIR_DISPOSITIONS = {
    "excluded:skipped_directory",
    "excluded:vendored_repo",
    "excluded:tool_state",
    "excluded:gitignored",
}


def _extract(root: Path) -> FactStore:
    store = FactStore(":memory:")
    extract_repo(root, store)
    return store


def _real_files(root: Path) -> list[str]:
    """Every file physically under ``root``, as root-relative POSIX paths.

    Walks the tree WITHOUT the runner's pruning so the completeness check sees
    the files the ledger's directory rows are meant to account for.
    """
    out = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fname in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fname), root)
            out.append(rel.replace(os.sep, "/"))
    return out


def _is_under(dir_rel: str, file_rel: str) -> bool:
    dir_rel = dir_rel.replace(os.sep, "/")
    file_rel = file_rel.replace(os.sep, "/")
    return file_rel == dir_rel or file_rel.startswith(dir_rel + "/")


def _accounting_defects(root: Path, rows: list[dict]) -> list[str]:
    """Return a list of accounting violations; empty means the ledger is complete.

    Each real file must be accounted for exactly once per the pruned-directory
    ruling documented in this module's docstring.
    """
    file_row_paths = {
        r["path"].replace(os.sep, "/")
        for r in rows
        if r["disposition"] not in DIR_DISPOSITIONS
    }
    dir_rows = [
        r["path"].replace(os.sep, "/") for r in rows if r["disposition"] in DIR_DISPOSITIONS
    ]

    defects: list[str] = []
    for rel in _real_files(root):
        if rel in file_row_paths:
            # Accounted by its own per-file row. Even if it also lives under a
            # pruned directory (CI-config rescue), the per-file row is the single
            # accounting; the directory row does not double-count it.
            continue
        ancestors = [d for d in dir_rows if _is_under(d, rel)]
        if len(ancestors) == 0:
            defects.append(f"UNACCOUNTED: {rel} (no per-file row, no excluded-directory row)")
        elif len(ancestors) > 1:
            defects.append(f"MULTI-COUNTED: {rel} under {len(ancestors)} directory rows: {ancestors}")
    return defects


# ---------------------------------------------------------------------------
# Completeness: every file accounted for exactly once
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("root", [POLYGLOT, MULTI], ids=["polyglot", "multi"])
def test_ledger_accounts_for_every_file_on_fixtures(root):
    store = _extract(root)
    defects = _accounting_defects(root, store.coverage())
    assert defects == [], "\n".join(defects)


def test_ledger_accounts_for_every_file_on_this_repo():
    # The load-bearing case: this repo has pruned directories (.git,
    # node_modules, .pytest_cache, ...) whose single directory rows must account
    # for the (many) files beneath them, plus per-file failed/binary/oversize
    # rows. Every real file under the root must be accounted for exactly once.
    store = _extract(REPO_ROOT)
    defects = _accounting_defects(REPO_ROOT, store.coverage())
    assert defects == [], "\n".join(defects[:40])


def test_pruned_directory_row_stands_in_for_its_contents():
    # Directly assert the ruling: a pruned directory contributes ONE row, not one
    # per contained file, and that row's rule names the directory pruning cause.
    if not os.path.isdir(os.path.join(REPO_ROOT, ".git")):
        # In a linked git worktree .git is a pointer FILE, so the directory row
        # this test asserts on cannot exist. The assertion keeps its full
        # strength in the main checkout.
        pytest.skip(".git is not a directory here (linked worktree)")
    store = _extract(REPO_ROOT)
    rows = store.coverage()
    git_dir_rows = [
        r for r in rows if r["disposition"] in DIR_DISPOSITIONS and r["path"] == ".git"
    ]
    assert len(git_dir_rows) == 1, "the .git directory must be a single ledger row"
    assert git_dir_rows[0]["reason"], "a pruned-directory row must name its rule"
    # No file INSIDE .git gets its own row (the directory row stands in for them).
    inside_git = [r for r in rows if r["path"].startswith(".git/")]
    assert inside_git == [], f"pruned .git contents leaked into per-file rows: {inside_git[:5]}"


# ---------------------------------------------------------------------------
# parsed row count equals files-table count
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("root", [POLYGLOT, MULTI, REPO_ROOT], ids=["polyglot", "multi", "self"])
def test_parsed_row_count_equals_files_table_count(root):
    store = _extract(root)
    parsed = store.coverage_summary().get("parsed", 0)
    assert parsed == len(store.files()), (
        f"parsed ledger rows ({parsed}) != files-table rows ({len(store.files())})"
    )


# ---------------------------------------------------------------------------
# Disposition well-formedness: no bare "skipped", every rule named
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("root", [POLYGLOT, MULTI, REPO_ROOT], ids=["polyglot", "multi", "self"])
def test_no_bare_skipped_disposition_anywhere(root):
    store = _extract(root)
    for r in store.coverage():
        disp = r["disposition"]
        assert disp != "skipped", f"bare 'skipped' disposition on {r['path']}"
        assert disp != "excluded", f"bare 'excluded' with no rule on {r['path']}"
        if disp.startswith("excluded:"):
            rule = disp.split(":", 1)[1]
            assert rule, f"excluded disposition with empty rule on {r['path']}"
        # Every disposition is one of the sanctioned kinds (I2).
        assert (
            disp in ("parsed", "binary", "failed")
            or disp.startswith("excluded:")
            or disp.startswith("failed:")
        ), f"unrecognized disposition {disp!r} on {r['path']}"


# ---------------------------------------------------------------------------
# Per-file dispositions carry their evidence
# ---------------------------------------------------------------------------

def test_unreadable_file_lands_failed_with_its_error(tmp_path, monkeypatch):
    # A deliberately unreadable file must land as `failed` with the error in its
    # reason, never a silent drop.
    (tmp_path / "ok.py").write_text("a = 1\n")
    (tmp_path / "bad.py").write_text("b = 2\n")

    real_read_bytes = pathlib.Path.read_bytes

    def flaky_read_bytes(self):
        if self.name == "bad.py":
            raise OSError("permission denied")
        return real_read_bytes(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", flaky_read_bytes)
    store = _extract(tmp_path)
    rows = {r["path"]: r for r in store.coverage()}
    assert rows["bad.py"]["disposition"] == "failed"
    assert "permission denied" in (rows["bad.py"]["reason"] or ""), (
        "the failed row must carry the underlying error in its reason"
    )
    assert rows["ok.py"]["disposition"] == "parsed"


def test_excluded_rule_lands_with_its_rule_name(tmp_path):
    # An unsupported extension and an opt-in oversized file each land with a
    # disposition that names the excluding rule (no bare skip).
    (tmp_path / "keep.py").write_text("a = 1\n")
    (tmp_path / "notes.xyz").write_text("not a known language\n")
    (tmp_path / "big.py").write_text("x = 1\n" * 200)

    store = FactStore(":memory:")
    extract_repo(tmp_path, store, max_file_size=100)
    rows = {r["path"]: r for r in store.coverage()}

    assert rows["notes.xyz"]["disposition"] == "excluded:unsupported_extension"
    assert rows["notes.xyz"]["reason"], "the excluded row must name the offending extension"
    assert rows["big.py"]["disposition"] == "excluded:max_file_size"
    assert rows["big.py"]["reason"] == "100", "the oversize row must name the byte bound"
    assert rows["keep.py"]["disposition"] == "parsed"


# ---------------------------------------------------------------------------
# End to end: the coverage.json the viewer fetches is complete
# ---------------------------------------------------------------------------

def test_projected_coverage_json_is_complete_end_to_end(tmp_path):
    # Run the real v2 pipeline (extract -> derive -> project) on the polyglot
    # fixture and assert the emitted coverage.json (what the viewer's badge/panel
    # consume) accounts for every file and matches the store ledger exactly.
    store = FactStore(":memory:")
    extract_repo(POLYGLOT, store)
    _, arch = derive_all(store, POLYGLOT.name, root_path=str(POLYGLOT))

    out = tmp_path / "architecture"
    project_split(arch, out, store=store, root=POLYGLOT, generated_at="x", analyzer_version="test")

    coverage_path = out / "coverage.json"
    assert coverage_path.is_file(), "split projection must emit coverage.json"
    doc = json.loads(coverage_path.read_text())

    # The shard rows equal the store ledger, and they account for every file.
    assert doc["rows"] == store.coverage()
    assert doc["summary"] == store.coverage_summary()
    assert doc["parsed"] == len(store.files())
    defects = _accounting_defects(POLYGLOT, doc["rows"])
    assert defects == [], "\n".join(defects)

    # The manifest summary the badge reads matches the shard (no full rows there).
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["coverage"]["summary"] == doc["summary"]
    assert manifest["coverage"]["total"] == doc["total"]
    assert manifest["coverage"]["parsed"] == doc["parsed"]
    assert "rows" not in manifest["coverage"], "the manifest carries only the summary"
