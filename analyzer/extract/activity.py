"""Git-activity extraction: the data source for the Activity lens (L5).

This is an extraction-adjacent pass (TARGET-ARCHITECTURE.md 4.1, LENS-DESIGN.md
section 4 L5 and section 6). It reads ``git log``, not source files, so it does
not belong in the derive tier (whose zero-source-reads instrumentation guards
file opens) and does not violate that rule: git history is environment and
provenance, read once at extraction time, exactly as the projection tier is
allowed to read ``.git`` for the repo URL. It writes four git-activity tables
(schema v2, P5-4) plus a provenance block in ``meta``.

Design decisions (recorded in TASKS.md P5-4):

  - **One commit is the logical change unit.** git-native, deterministic, no
    timezone or day-boundary choice. Merge commits are excluded (``--no-merges``:
    ``git log --numstat`` emits no diff for merges anyway).
  - **Co-change coupling is capped.** A commit touching more than
    ``MAX_FILES_PER_COMMIT_FOR_COUPLING`` files is a bulk or mechanical change:
    it still counts toward churn and authorship but manufactures no O(n^2)
    coupling pairs (the CodeScene cap).
  - **Renames are followed.** ``-M`` reports renames in numstat's ``old => new``
    path form; historical paths canonicalize to their current name so activity
    accrues to the path that exists today.
  - **Cache by commit range (invariant I6).** ``meta.activity_head`` records the
    HEAD processed last. Unchanged HEAD processes zero commits. A fast-forward
    (old head is an ancestor of the new) processes only the new range and merges
    additively, migrating any in-range renames onto stored history so the result
    equals a full reprocess. A non-ancestor move (rebase, force-push, shallow
    boundary shift) clears and fully reprocesses, never a silent partial.
  - **Graceful absence.** A non-git root writes nothing and records
    ``activity_git=0``, no error. A shallow clone records ``activity_shallow=1``
    and its partial history is never presented as full.

The pass reads git, not source files, so it adds no coverage (file-disposition)
rows; it accounts for itself in the ``meta`` provenance block, which the
projection surfaces.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..store import FactStore

__all__ = ["extract_activity", "ActivityResult"]

# A commit touching more than this many files does not generate coupling pairs
# (bulk/mechanical change); it still counts toward churn and authorship.
MAX_FILES_PER_COMMIT_FOR_COUPLING = 30

# git log record layout: SOH starts a header line, US separates its fields.
# SOH (not NUL) because an embedded NUL cannot be passed as a git argv token,
# and neither byte can begin a numstat line (those start with a digit or "-").
_REC = "\x01"
_SEP = "\x1f"
_LOG_FORMAT = f"{_REC}%H{_SEP}%an{_SEP}%ae{_SEP}%aI"

_GIT_TIMEOUT = 120


@dataclass
class ActivityResult:
    """Summary of one activity-extraction pass, for tests and CLI reporting."""

    git: bool = False
    shallow: bool = False
    head: Optional[str] = None
    commits_processed: int = 0
    mode: str = "none"  # 'none' | 'full' | 'incremental' | 'unchanged'
    files_touched: int = field(default=0)


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------

def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, timeout=_GIT_TIMEOUT,
    )


def _is_git_repo(root: Path) -> bool:
    try:
        cp = _git(root, "rev-parse", "--is-inside-work-tree")
    except (OSError, subprocess.SubprocessError):
        return False
    return cp.returncode == 0 and cp.stdout.strip() == "true"


def _head_sha(root: Path) -> Optional[str]:
    try:
        cp = _git(root, "rev-parse", "HEAD")
    except (OSError, subprocess.SubprocessError):
        return None
    return cp.stdout.strip() if cp.returncode == 0 else None


def _is_shallow(root: Path) -> bool:
    try:
        cp = _git(root, "rev-parse", "--is-shallow-repository")
    except (OSError, subprocess.SubprocessError):
        return (root / ".git" / "shallow").exists()
    if cp.returncode == 0:
        return cp.stdout.strip() == "true"
    return (root / ".git" / "shallow").exists()


def _is_ancestor(root: Path, old: str, new: str) -> bool:
    try:
        cp = _git(root, "merge-base", "--is-ancestor", old, new)
    except (OSError, subprocess.SubprocessError):
        return False
    return cp.returncode == 0


# ---------------------------------------------------------------------------
# rename-aware numstat path parsing
# ---------------------------------------------------------------------------

_MULTI_SLASH = re.compile(r"/+")


def _norm(p: str) -> str:
    return _MULTI_SLASH.sub("/", p).strip("/")


def _split_rename(path: str) -> tuple[str, str]:
    """Return (old_path, new_path) from a numstat path field.

    Handles the two rename encodings ``git log -M --numstat`` emits:
    ``old => new`` and the braced ``pre{old => new}post`` (including empty
    sides, e.g. ``dir/{ => sub}/f.py``). A non-rename path returns (p, p).
    """
    if "=>" not in path:
        return path, path
    if "{" in path and "}" in path:
        pre, rest = path.split("{", 1)
        mid, post = rest.split("}", 1)
        old_mid, _, new_mid = mid.partition("=>")
        old = _norm(pre + old_mid.strip() + post)
        new = _norm(pre + new_mid.strip() + post)
        return old, new
    old, _, new = path.partition("=>")
    return _norm(old.strip()), _norm(new.strip())


def _parse_int(token: str) -> int:
    # numstat uses "-" for binary files.
    return int(token) if token.isdigit() else 0


# ---------------------------------------------------------------------------
# accumulation
# ---------------------------------------------------------------------------

class _Accumulator:
    """Folds parsed commits into per-path activity, author, and pair deltas."""

    def __init__(self) -> None:
        # path -> [commits, added, removed, first_seen, last_modified]
        self.activity: dict[str, list] = {}
        # (path, period) -> [commits, added, removed]
        self.periods: dict[tuple[str, str], list[int]] = {}
        # (path, author_key) -> [name, commits, added, removed]
        self.authors: dict[tuple[str, str], list] = {}
        # (a, b) with a < b -> cochange count
        self.pairs: dict[tuple[str, str], int] = {}
        # old -> current-name, discovered from in-range renames
        self.renames: dict[str, str] = {}
        self.commits = 0

    def _canonical(self, p: str) -> str:
        seen = set()
        while p in self.renames and p not in seen:
            seen.add(p)
            p = self.renames[p]
        return p

    def add_commit(
        self, date_iso: str, author_key: str, author_name: str,
        entries: list[tuple[int, int, str, str]],
    ) -> None:
        """entries: (added, removed, old_path, new_path) already canonicalized."""
        self.commits += 1
        period = date_iso[:7]  # YYYY-MM
        touched: set[str] = set()
        for added, removed, _old, path in entries:
            touched.add(path)
            a = self.activity.get(path)
            if a is None:
                self.activity[path] = [1, added, removed, date_iso, date_iso]
            else:
                a[0] += 1
                a[1] += added
                a[2] += removed
                if date_iso < a[3]:
                    a[3] = date_iso
                if date_iso > a[4]:
                    a[4] = date_iso
            pk = (path, period)
            pr = self.periods.get(pk)
            if pr is None:
                self.periods[pk] = [1, added, removed]
            else:
                pr[0] += 1
                pr[1] += added
                pr[2] += removed
            ak = (path, author_key)
            au = self.authors.get(ak)
            if au is None:
                self.authors[ak] = [author_name, 1, added, removed]
            else:
                au[0] = author_name
                au[1] += 1
                au[2] += added
                au[3] += removed
        # co-change pairs (capped)
        if 2 <= len(touched) <= MAX_FILES_PER_COMMIT_FOR_COUPLING:
            ordered = sorted(touched)
            for i in range(len(ordered)):
                for j in range(i + 1, len(ordered)):
                    key = (ordered[i], ordered[j])
                    self.pairs[key] = self.pairs.get(key, 0) + 1


def _parse_log(text: str, acc: _Accumulator) -> None:
    """Parse ``git log`` output (newest-first) into the accumulator.

    Renames are resolved as they are encountered: because the log is
    newest-first, the rename commit is seen before the older commits that used
    the old name, so ``acc.renames[old] = canonical(new)`` is recorded before
    any older reference resolves.
    """
    lines = text.split("\n")
    cur_date = cur_key = cur_name = None
    entries: list[tuple[int, int, str, str]] = []

    def flush() -> None:
        if cur_date is not None:
            acc.add_commit(cur_date, cur_key, cur_name, entries)

    for line in lines:
        if line.startswith(_REC):
            flush()
            entries = []
            _, _, rest = line.partition(_REC)
            parts = rest.split(_SEP)
            if len(parts) >= 4:
                _sha, cur_name, ae, cur_date = parts[0], parts[1], parts[2], parts[3]
                cur_key = ae.strip().lower()
            continue
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) < 3:
            continue
        added = _parse_int(cols[0])
        removed = _parse_int(cols[1])
        raw_path = "\t".join(cols[2:])
        old, new = _split_rename(raw_path)
        if old != new:
            # After this (newer) commit the file is 'new'; older commits that
            # reference 'old' must resolve forward to the canonical current name.
            acc.renames[old] = acc._canonical(new)
        canon = acc._canonical(new)
        entries.append((added, removed, old, canon))
    flush()


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def extract_activity(root, store: FactStore) -> ActivityResult:
    """Extract git activity under ``root`` into ``store`` (P5-4).

    Idempotent and cached by commit range: unchanged HEAD is a no-op, a
    fast-forward processes only the new commits, a history rewrite reprocesses
    fully. A non-git root writes nothing and returns ``git=False``.
    """
    root = Path(root)
    result = ActivityResult()

    if not _is_git_repo(root):
        store.set_meta("activity_git", "0")
        store.commit()
        return result

    head = _head_sha(root)
    if head is None:
        # A repo with no commits yet: git is present but there is no history.
        store.set_meta("activity_git", "1")
        store.set_meta("activity_head", "")
        store.commit()
        result.git = True
        result.mode = "full"
        return result

    result.git = True
    result.head = head
    result.shallow = _is_shallow(root)

    prev_head = store.get_meta("activity_head")
    prev_shallow = store.get_meta("activity_shallow") == "1"

    # The prior pass is only COMPLETE (safe to trust as-is on an unchanged HEAD)
    # when it recorded activity AND was not shallow. A shallow pass recorded only
    # partial history behind the clone's shallow boundary; the clone may since
    # have been deepened or unshallowed (a common CI pattern: build the store in a
    # depth-1 checkout, reuse it in a fuller one), revealing ancestor commits that
    # were never processed even though HEAD did not move. Treating that as
    # "unchanged" strands the newly available history, so a prior shallow pass is
    # never trusted as complete (D11).
    prior_complete = store.has_activity() and not prev_shallow

    if prev_head == head and prior_complete:
        # Nothing changed since the last pass: process zero commits (I6).
        store.set_meta("activity_shallow", "1" if result.shallow else "0")
        store.commit()
        result.mode = "unchanged"
        result.commits_processed = 0
        return result

    # A fast-forward incremental extends a COMPLETE prior pass over the new range.
    # An incomplete (shallow) prior pass cannot be extended additively: the range
    # ``prev_head..head`` would be empty on an unchanged HEAD while leaving the
    # partial history unrepaired, so it is rebuilt in full instead (D11).
    incremental = (
        bool(prev_head)
        and prev_head != head
        and prior_complete
        and _is_ancestor(root, prev_head, head)
    )
    log_args = ["log", "--no-merges", "-M", "--numstat", f"--format={_LOG_FORMAT}"]
    if incremental:
        log_args.append(f"{prev_head}..{head}")
        result.mode = "incremental"
    else:
        # Cold, or a history rewrite: clear any prior activity and reprocess all.
        store.clear_activity()
        result.mode = "full"

    log_args.append("--")  # everything, all paths
    cp = _git(root, "-c", "core.quotePath=false", *log_args)
    if cp.returncode != 0:
        # git failed for this range; record availability but do not pretend.
        store.set_meta("activity_git", "1")
        store.set_meta("activity_shallow", "1" if result.shallow else "0")
        store.commit()
        return result

    acc = _Accumulator()
    _parse_log(cp.stdout, acc)

    if incremental and acc.renames:
        # Move history accumulated under an old name onto its current name so an
        # incremental run equals a full reprocess across a rename.
        store.apply_activity_renames({o: acc._canonical(o) for o in acc.renames})

    store.merge_file_activity(
        (p, v[0], v[1], v[2], v[3], v[4]) for p, v in acc.activity.items()
    )
    store.merge_file_activity_periods(
        (pk[0], pk[1], v[0], v[1], v[2]) for pk, v in acc.periods.items()
    )
    store.merge_file_authors(
        (ak[0], ak[1], v[0], v[1], v[2], v[3]) for ak, v in acc.authors.items()
    )
    store.merge_cochange_pairs(
        (a, b, n) for (a, b), n in acc.pairs.items()
    )

    # Provenance block (the pass accounts for itself; no coverage rows).
    store.set_meta("activity_git", "1")
    store.set_meta("activity_shallow", "1" if result.shallow else "0")
    store.set_meta("activity_head", head)
    fa = store.file_activity()
    total_commits = int(store.get_meta("activity_commits") or 0) + acc.commits
    store.set_meta("activity_commits", str(total_commits))
    if fa:
        first = min(r["first_seen"] for r in fa if r["first_seen"])
        last = max(r["last_modified"] for r in fa if r["last_modified"])
        store.set_meta("activity_first_commit", first)
        store.set_meta("activity_last_commit", last)
    store.commit()

    result.commits_processed = acc.commits
    result.files_touched = len(acc.activity)
    return result
