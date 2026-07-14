"""Tests for git-activity extraction and the Activity-lens projection (P5-4).

These drive the REAL pipeline: a synthetic git repo is built in a tmp dir with
scripted commits by two authors and fixed dates, then ``extract_activity`` reads
its ``git log`` into a fact store and ``build_activity`` aggregates to component
granularity. Nothing is mocked; the assertions are hand-computed from the
scripted history:

  * churn, author shares, knowledge islands, bus factor, and co-change pairs;
  * rename handling (history accrues to the current path);
  * shallow-clone marker (partial history is never presented as full);
  * cache-by-range (a re-run over an unchanged HEAD processes zero commits);
  * a fast-forward incremental run equals a full reprocess byte-for-byte,
    including across a rename;
  * graceful absence on a non-git root and backward-compatible projection.

The rename assertions are the fail-before guard for the canonicalization logic:
without it, a renamed file's history splits across the old and new names and the
``commit_count`` assertions fail.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from analyzer.extract.activity import _split_rename, extract_activity
from analyzer.project.activity import _bus_factor, build_activity
from analyzer.store import FactStore

ALICE = ("Alice", "alice@example.com")
BOB = ("Bob", "bob@example.com")


# ---------------------------------------------------------------------------
# synthetic-repo helpers (deterministic: fixed authors and dates)
# ---------------------------------------------------------------------------

def _run(root: Path, *args: str, env=None) -> str:
    cp = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, check=True, env=env,
    )
    return cp.stdout


def _init(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _run(root, "init", "-q")
    _run(root, "config", "commit.gpgsign", "false")


def _commit(root: Path, author, date: str, files: dict[str, str], *, rename=None) -> None:
    """Write ``files`` (path -> content), optionally ``git mv`` a rename, commit.

    ``author`` is (name, email); ``date`` is an ISO instant used for both the
    author and committer date so first_seen/last_modified/periods are fixed.
    """
    name, email = author
    if rename is not None:
        _run(root, "mv", rename[0], rename[1])
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    _run(root, "add", "-A")
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email,
        GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email,
        GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date,
    )
    _run(root, "commit", "-q", "-m", f"{name} {date}", env=env)


def _scripted_repo(root: Path) -> None:
    """Build the fixture history used by the exactness assertions.

    core.py is renamed to engine.py at the end, so its whole history must
    canonicalize to engine.py.

      c1 Alice 2020-01-15  core.py(10 lines) + util.py(5)     [co-change]
      c2 Alice 2020-01-20  core.py +3        + util.py +1     [co-change]
      c3 Bob   2020-02-10  core.py +2
      c4 Alice 2020-02-15  solo.py(4)                          [solo]
      c5 Bob   2020-03-05  rename core.py->engine.py, +1
    """
    _init(root)
    _commit(root, ALICE, "2020-01-15T12:00:00+00:00", {
        "core.py": "l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\nl10\n",
        "util.py": "u1\nu2\nu3\nu4\nu5\n",
    })
    _commit(root, ALICE, "2020-01-20T12:00:00+00:00", {
        "core.py": "l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\nl10\nn1\nn2\nn3\n",
        "util.py": "u1\nu2\nu3\nu4\nu5\nu6\n",
    })
    _commit(root, BOB, "2020-02-10T12:00:00+00:00", {
        "core.py": "l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\nl10\nn1\nn2\nn3\nb1\nb2\n",
    })
    _commit(root, ALICE, "2020-02-15T12:00:00+00:00", {
        "solo.py": "s1\ns2\ns3\ns4\n",
    })
    _commit(root, BOB, "2020-03-05T12:00:00+00:00", {
        "engine.py": "l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8\nl9\nl10\nn1\nn2\nn3\nb1\nb2\ne1\n",
    }, rename=("core.py", "engine.py"))


def _act(store: FactStore) -> dict[str, dict]:
    return {r["path"]: r for r in store.file_activity()}


def _authors(store: FactStore) -> dict[tuple, dict]:
    return {(r["path"], r["author_key"]): r for r in store.file_authors()}


# ---------------------------------------------------------------------------
# unit: rename path parsing and bus factor
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, old, new", [
    ("a.py", "a.py", "a.py"),
    ("old.py => new.py", "old.py", "new.py"),
    ("src/{old => new}/f.py", "src/old/f.py", "src/new/f.py"),
    ("src/{ => sub}/f.py", "src/f.py", "src/sub/f.py"),
    ("{old => new}/f.py", "old/f.py", "new/f.py"),
])
def test_split_rename(raw, old, new):
    assert _split_rename(raw) == (old, new)


@pytest.mark.parametrize("commits, total, expected", [
    ([], 0, 0),
    ([5], 5, 1),
    ([2, 2], 4, 1),          # top 2 of 4 reaches half
    ([3, 2, 2], 7, 2),       # need two to cross 3.5
    ([4, 3, 2, 1], 10, 2),   # 4 then 7 >= 5
    ([1, 1, 1, 1], 4, 2),    # 1 then 2 >= 2
])
def test_bus_factor(commits, total, expected):
    assert _bus_factor(commits, total) == expected


# ---------------------------------------------------------------------------
# core extraction exactness (two authors, churn, shares, rename, co-change)
# ---------------------------------------------------------------------------

def test_extraction_matches_scripted_history(tmp_path):
    root = tmp_path / "repo"
    _scripted_repo(root)
    store = FactStore(":memory:")
    result = extract_activity(root, store)

    assert result.git is True
    assert result.mode == "full"
    assert result.commits_processed == 5

    act = _act(store)
    # Rename: core.py's whole history accrued to engine.py; no core.py row.
    assert "core.py" not in act
    assert act["engine.py"]["commit_count"] == 4      # c1,c2,c3,c5
    assert act["engine.py"]["lines_added"] == 16      # 10+3+2+1
    assert act["engine.py"]["first_seen"] == "2020-01-15T12:00:00Z"
    assert act["engine.py"]["last_modified"] == "2020-03-05T12:00:00Z"
    assert act["util.py"]["commit_count"] == 2        # c1,c2
    assert act["util.py"]["lines_added"] == 6         # 5+1
    assert act["solo.py"]["commit_count"] == 1        # c4

    authors = _authors(store)
    # engine.py: Alice c1,c2 = 2; Bob c3,c5 = 2.
    assert authors[("engine.py", "alice@example.com")]["commit_count"] == 2
    assert authors[("engine.py", "bob@example.com")]["commit_count"] == 2
    # util.py: Alice only.
    assert authors[("util.py", "alice@example.com")]["commit_count"] == 2
    assert ("util.py", "bob@example.com") not in authors

    # Co-change: core(->engine) and util changed together in c1 and c2 only.
    pairs = store.cochange_pairs()
    assert pairs == [
        {"path_a": "engine.py", "path_b": "util.py", "cochange_count": 2}
    ]

    # Periods (calendar buckets), engine.py spans three months.
    periods = {(p["path"], p["period"]): p["commit_count"]
               for p in store.file_activity_periods()}
    assert periods[("engine.py", "2020-01")] == 2
    assert periods[("engine.py", "2020-02")] == 1
    assert periods[("engine.py", "2020-03")] == 1
    assert periods[("util.py", "2020-01")] == 2
    assert periods[("solo.py", "2020-02")] == 1


def test_projection_knowledge_island_and_bus_factor(tmp_path):
    root = tmp_path / "repo"
    _scripted_repo(root)
    store = FactStore(":memory:")
    extract_activity(root, store)

    # Wire components as derivation would: Core owns engine.py, Util owns util.py.
    fe = store.add_file("engine.py", "python", 16, 160, "he", "parsed")
    fu = store.add_file("util.py", "python", 6, 60, "hu", "parsed")
    fs = store.add_file("solo.py", "python", 4, 40, "hs", "parsed")
    store.add_component("comp:core", "Core", "service", ".", role="service")
    store.add_component("comp:util", "Util", "library", "util", role="library")
    store.link_component_file("comp:core", fe)
    store.link_component_file("comp:core", fs)
    store.link_component_file("comp:util", fu)
    store.commit()

    activity = build_activity(store)
    comps = {c["id"]: c for c in activity["components"]}

    core = comps["comp:core"]
    # Core: engine.py (Alice2,Bob2) + solo.py (Alice1) => Alice 3, Bob 2, total 5.
    assert core["commit_count"] == 5                  # 4 + 1
    assert core["author_count"] == 2
    assert core["top_author_share"] == pytest.approx(3 / 5)
    assert core["knowledge_island"] is False          # 0.6 < 0.95
    assert core["bus_factor"] == 1                     # Alice alone >= half

    util = comps["comp:util"]
    assert util["knowledge_island"] is True            # Alice holds 100%
    assert util["top_author_share"] == pytest.approx(1.0)

    # Hotspots ranked by change-frequency * size; Core (churny+large) leads.
    assert activity["components"][0]["id"] == "comp:core"
    assert core["hotspot_score"] == 4 * 16 + 1 * 4     # engine + solo


# ---------------------------------------------------------------------------
# cache by commit range (invariant I6)
# ---------------------------------------------------------------------------

def test_second_run_over_unchanged_head_processes_zero_commits(tmp_path):
    root = tmp_path / "repo"
    _scripted_repo(root)
    store = FactStore(":memory:")
    first = extract_activity(root, store)
    assert first.commits_processed == 5

    before = [dict(r) for r in store.file_activity()]
    second = extract_activity(root, store)
    assert second.mode == "unchanged"
    assert second.commits_processed == 0
    # Tables untouched: no double counting.
    assert [dict(r) for r in store.file_activity()] == before


def test_incremental_fast_forward_equals_full_reprocess_across_rename(tmp_path):
    """A store advanced commit-by-commit matches a single full run byte-for-byte,
    even when the advancing range contains the rename."""
    src = tmp_path / "src"
    _scripted_repo(src)

    def snapshot(store: FactStore):
        return (
            [tuple(r.values()) for r in store.file_activity()],
            [tuple(r.values()) for r in store.file_authors()],
            [tuple(r.values()) for r in store.file_activity_periods()],
            store.cochange_pairs(),
        )

    # Full run at HEAD.
    full_store = FactStore(":memory:")
    extract_activity(src, full_store)
    full = snapshot(full_store)

    # Incremental: a clone reset to the pre-rename commit, then advanced to HEAD.
    head = _run(src, "rev-parse", "HEAD").strip()
    prev = _run(src, "rev-parse", "HEAD~1").strip()   # c4, before the rename
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(src), str(clone)], check=True)
    inc_store = FactStore(":memory:")

    subprocess.run(["git", "-C", str(clone), "reset", "--hard", prev],
                   capture_output=True, check=True)
    extract_activity(clone, inc_store)
    subprocess.run(["git", "-C", str(clone), "reset", "--hard", head],
                   capture_output=True, check=True)
    r = extract_activity(clone, inc_store)
    assert r.mode == "incremental"

    assert snapshot(inc_store) == full


def test_cold_runs_are_deterministic(tmp_path):
    root = tmp_path / "repo"
    _scripted_repo(root)
    a, b = FactStore(":memory:"), FactStore(":memory:")
    extract_activity(root, a)
    extract_activity(root, b)
    assert build_activity(a) == build_activity(b)


# ---------------------------------------------------------------------------
# shallow clone: truthful partial data, never pretend-full
# ---------------------------------------------------------------------------

def test_shallow_clone_is_marked(tmp_path):
    src = tmp_path / "src"
    _scripted_repo(src)
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "--depth", "1", f"file://{src}", str(shallow)],
        capture_output=True, check=True,
    )
    store = FactStore(":memory:")
    result = extract_activity(shallow, store)
    assert result.git is True
    assert result.shallow is True
    assert store.get_meta("activity_shallow") == "1"
    activity = build_activity(store)
    assert activity["provenance"]["shallow"] is True
    # Only the tip commit is present, and it is not presented as full history.
    assert result.commits_processed == 1


# ---------------------------------------------------------------------------
# graceful absence + backward compatibility
# ---------------------------------------------------------------------------

def test_non_git_root_produces_no_activity_and_no_error(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    (root / "a.py").write_text("x = 1\n", encoding="utf-8")
    store = FactStore(":memory:")
    result = extract_activity(root, store)
    assert result.git is False
    assert store.get_meta("activity_git") == "0"
    assert store.has_activity() is False
    assert build_activity(store) is None


def test_projection_omits_activity_key_without_git(tmp_path):
    """Old datasets (no activity) project without an activity key, unchanged."""
    from datetime import datetime, timezone

    from analyzer.derive import derive_all
    from analyzer.extract import extract_activity, extract_repo
    from analyzer.project import project_split

    # A non-git source tree run through the full v2 pipeline.
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "mod.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    store = FactStore(":memory:")
    extract_repo(root, store)
    extract_activity(root, store)          # no-op: not a git repo
    _, arch = derive_all(store, "proj", root_path=str(root))

    out = tmp_path / "out"
    result = project_split(
        arch, out, store=store, root=root,
        generated_at=datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat(),
    )
    assert result.activity is None
    assert not (out / "activity.json").exists()

    import json
    manifest = json.loads((out / "manifest.json").read_text())
    assert "activity" not in manifest
