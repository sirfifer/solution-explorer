"""Security regression tests for credential handling (F-CRIT-3).

Two leak paths are covered:
1. The scanner reads a clone URL from .git/config; a private-repo clone URL
   carries an x-access-token:<GITHUB_TOKEN>@ credential that must never reach
   the architecture output.
2. On clone failure, git echoes the credentialed URL in its stderr, which the
   multi-repo orchestrator prints; the token must be redacted first.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from analyzer.models import to_dict
from analyzer.multi_repo import MultiRepoOrchestrator
from analyzer.scanner import ArchitectureScanner, _strip_url_credentials

FAKE_TOKEN = "FAKEtoken1234567890abcdef"


def _make_repo_with_git_config(root: Path, url: str):
    """Create a minimal scannable repo whose .git/config carries the given url."""
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("def main():\n    return 1\n")
    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text(
        '[core]\n'
        '\trepositoryformatversion = 0\n'
        '[remote "origin"]\n'
        f'\turl = {url}\n'
        '\tfetch = +refs/heads/*:refs/remotes/origin/*\n'
    )
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n")


def test_strip_url_credentials_removes_userinfo():
    assert _strip_url_credentials(
        f"https://x-access-token:{FAKE_TOKEN}@github.com/org/repo"
    ) == "https://github.com/org/repo"
    # user:password form
    assert _strip_url_credentials(
        "https://user:pass@example.com/a/b"
    ) == "https://example.com/a/b"
    # No credentials: unchanged.
    assert _strip_url_credentials(
        "https://github.com/org/repo"
    ) == "https://github.com/org/repo"
    # scp-like SSH remote: no password to strip, left as-is.
    assert _strip_url_credentials("git@github.com:org/repo.git") == "git@github.com:org/repo.git"


def test_token_in_git_config_never_reaches_output(tmp_path):
    """A tokenized clone URL in .git/config must not appear anywhere in output."""
    repo = tmp_path / "repo"
    repo.mkdir()
    tokenized = f"https://x-access-token:{FAKE_TOKEN}@github.com/org/private-repo.git"
    _make_repo_with_git_config(repo, tokenized)

    scanner = ArchitectureScanner(repo)
    arch = scanner.scan()

    # Stored repository field is the clean host URL.
    assert arch.repository == "https://github.com/org/private-repo"

    # Grep the entire serialized analyzer output for the token: must be empty.
    full_output = json.dumps(to_dict(arch))
    assert FAKE_TOKEN not in full_output
    assert "x-access-token" not in full_output


def test_clone_failure_redacts_token_in_stderr(tmp_path, monkeypatch, capsys):
    """A failed clone must print a redacted URL, never the token (F-CRIT-3)."""
    config_path = tmp_path / "solution-explorer.json"
    config_path.write_text(json.dumps({
        "solution": "Test",
        "repositories": [
            {"name": "priv", "url": "https://github.com/org/private-repo.git"},
        ],
    }))
    orch = MultiRepoOrchestrator(config_path)

    monkeypatch.setenv("GITHUB_TOKEN", FAKE_TOKEN)

    # Simulate git clone failing with the credentialed URL echoed in stderr,
    # exactly as real git does, without hitting the network.
    class _FakeResult:
        returncode = 1
        stderr = (
            "Cloning into '/tmp/x'...\n"
            f"fatal: unable to access "
            f"'https://x-access-token:{FAKE_TOKEN}@github.com/org/private-repo.git/': "
            "The requested URL returned error: 403\n"
        )

    def _fake_run(*args, **kwargs):
        return _FakeResult()

    monkeypatch.setattr("analyzer.multi_repo.subprocess.run", _fake_run)

    with pytest.raises(SystemExit) as exc:
        orch._resolve_repo(
            {"name": "priv", "url": "https://github.com/org/private-repo.git"},
            [],
        )
    assert exc.value.code == 1

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert FAKE_TOKEN not in combined
    assert "***" in captured.err  # token replaced with redaction marker
