"""Shared pytest fixtures and guards for the analyzer test suite.

The repo-root ``architecture.json`` is a committed AI-enhancement baseline that
the deploy pipeline merges from. A test that calls the CLI without ``-o`` writes
the analyzer's default output (``architecture.json`` in the current working
directory), silently clobbering that baseline (finding F-CRIT-7). The autouse
guard below fails the offending test immediately so the leak can never recur
unnoticed.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARDED_FILE = REPO_ROOT / "architecture.json"
GUARDED_SPLIT_DIR = REPO_ROOT / "architecture"


def _signature(path: Path):
    """Return a cheap change-detection signature, or None if the path is absent."""
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (st.st_size, st.st_mtime_ns)


@pytest.fixture(autouse=True)
def _guard_repo_root_architecture_baseline():
    """Fail any test that creates or modifies the repo-root architecture baseline.

    Checks both the single-file baseline ``architecture.json`` and the split-mode
    default output directory ``architecture/``, either of which a stray CLI call
    with no ``-o`` would write into the repo root.
    """
    before_file = _signature(GUARDED_FILE)
    split_existed_before = GUARDED_SPLIT_DIR.exists()

    yield

    after_file = _signature(GUARDED_FILE)
    if after_file != before_file:
        if before_file is None:
            reason = f"created repo-root {GUARDED_FILE.name}"
        else:
            reason = f"modified repo-root {GUARDED_FILE.name}"
        pytest.fail(
            f"Test {reason}. A CLI test likely ran main() without -o and "
            "clobbered the committed AI baseline (F-CRIT-7). Pass "
            "-o <tmp_path> to the analyzer in this test."
        )

    if GUARDED_SPLIT_DIR.exists() and not split_existed_before:
        pytest.fail(
            f"Test created repo-root {GUARDED_SPLIT_DIR.name}/ directory. A CLI "
            "test likely ran main() with --split and no -o. Pass -o <tmp_path>."
        )
