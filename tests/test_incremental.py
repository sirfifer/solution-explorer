"""Tests for incremental analysis with diff metadata."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from analyzer import __version__
from analyzer.incremental import MARKER_FILES, IncrementalAnalyzer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_git_repo(tmp_path):
    """Create a minimal git repo with one commit."""
    subprocess.run(
        ["git", "init"], cwd=str(tmp_path),
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path), capture_output=True, check=True,
    )

    # Create initial files and commit
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "test-project",
        "description": "Test project",
    }))
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.ts").write_text(
        "export function main(): void {\n"
        '  console.log("hello");\n'
        "}\n"
    )

    subprocess.run(
        ["git", "add", "-A"], cwd=str(tmp_path),
        capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=str(tmp_path), capture_output=True, check=True,
    )
    return tmp_path


@pytest.fixture
def baseline_arch():
    """Build a minimal baseline architecture dict."""
    return {
        "name": "test-project",
        "analyzer_version": __version__,
        "components": [
            {
                "id": "root",
                "name": "test-project",
                "type": "project",
                "path": "",
                "files": ["src/index.ts", "src/utils.ts"],
                "children": [
                    {
                        "id": "src",
                        "name": "src",
                        "type": "module",
                        "path": "src",
                        "files": ["src/index.ts", "src/utils.ts"],
                        "children": [],
                        "metrics": {"files": 2, "lines": 10},
                    }
                ],
                "metrics": {"files": 2, "lines": 10},
            }
        ],
        "relationships": [
            {"source": "root", "target": "src", "type": "import"}
        ],
        "files": [
            {"path": "src/index.ts", "language": "typescript", "lines": 5},
            {"path": "src/utils.ts", "language": "typescript", "lines": 5},
        ],
        "stats": {"total_files": 2, "total_components": 2},
    }


@pytest.fixture
def saved_baseline(tmp_path, baseline_arch):
    """Write a baseline JSON file and return its path."""
    baseline_path = tmp_path / "baseline" / "architecture.json"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(baseline_arch))
    return baseline_path


# ---------------------------------------------------------------------------
# should_full_rescan Tests
# ---------------------------------------------------------------------------


class TestShouldFullRescan:
    """Tests for the should_full_rescan decision logic."""

    def test_true_when_no_base_sha(self, tmp_path, baseline_arch):
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="")
        assert analyzer.should_full_rescan([], baseline_arch) is True

    def test_true_when_no_baseline(self, tmp_path):
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="abc123")
        changed = [("M", "src/index.ts")]
        assert analyzer.should_full_rescan(changed, None) is True

    def test_true_when_version_mismatch(self, tmp_path):
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="abc123")
        baseline = {"analyzer_version": "0.9.0", "files": [{"path": "a.ts"}]}
        changed = [("M", "src/index.ts")]
        assert analyzer.should_full_rescan(changed, baseline) is True

    def test_true_when_marker_file_changed(self, tmp_path, baseline_arch):
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="abc123")
        changed = [("M", "package.json"), ("M", "src/index.ts")]
        assert analyzer.should_full_rescan(changed, baseline_arch) is True

    def test_true_when_over_50_percent_changed(self, tmp_path):
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="abc123")
        baseline = {
            "analyzer_version": __version__,
            "files": [{"path": f"file{i}.ts"} for i in range(10)],
        }
        changed = [("M", f"file{i}.ts") for i in range(6)]
        assert analyzer.should_full_rescan(changed, baseline) is True

    def test_true_when_no_changed_files(self, tmp_path, baseline_arch):
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="abc123")
        assert analyzer.should_full_rescan([], baseline_arch) is True

    def test_false_for_normal_changes(self, tmp_path, baseline_arch):
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="abc123")
        changed = [("M", "src/index.ts")]
        assert analyzer.should_full_rescan(changed, baseline_arch) is False

    @pytest.mark.parametrize("marker", sorted(MARKER_FILES))
    def test_each_marker_file_triggers_rescan(self, tmp_path, baseline_arch, marker):
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="abc123")
        changed = [("M", marker)]
        assert analyzer.should_full_rescan(changed, baseline_arch) is True


# ---------------------------------------------------------------------------
# map_files_to_components Tests
# ---------------------------------------------------------------------------


class TestMapFilesToComponents:
    """Tests for mapping changed file paths to component IDs."""

    def test_maps_known_files(self, tmp_path, baseline_arch):
        analyzer = IncrementalAnalyzer(tmp_path)
        changed = [("M", "src/index.ts")]
        result = analyzer.map_files_to_components(changed, baseline_arch)
        # src/index.ts is owned by both root and src components
        assert "root" in result or "src" in result

    def test_unknown_file_maps_to_nearest_component(self, tmp_path, baseline_arch):
        analyzer = IncrementalAnalyzer(tmp_path)
        changed = [("A", "src/new_file.ts")]
        result = analyzer.map_files_to_components(changed, baseline_arch)
        assert "src" in result

    def test_empty_changed_files(self, tmp_path, baseline_arch):
        analyzer = IncrementalAnalyzer(tmp_path)
        result = analyzer.map_files_to_components([], baseline_arch)
        assert result == set()


# ---------------------------------------------------------------------------
# compute_diff_summary Tests
# ---------------------------------------------------------------------------


class TestComputeDiffSummary:
    """Tests for diff summary computation."""

    def test_first_run_all_added(self, tmp_path):
        analyzer = IncrementalAnalyzer(tmp_path)
        new_arch = {
            "components": [
                {"id": "root", "children": [{"id": "src", "children": []}]}
            ],
            "relationships": [
                {"source": "root", "target": "src", "type": "import"}
            ],
            "files": [{"path": "a.ts"}],
        }
        diff = analyzer.compute_diff_summary(None, new_arch, changed_file_count=1)
        assert "root" in diff["components_added"]
        assert "src" in diff["components_added"]
        assert diff["components_removed"] == []
        assert diff["relationships_added"] == 1

    def test_component_added(self, tmp_path, baseline_arch):
        analyzer = IncrementalAnalyzer(tmp_path)
        new_arch = json.loads(json.dumps(baseline_arch))
        new_arch["components"][0]["children"].append({
            "id": "lib",
            "name": "lib",
            "type": "module",
            "path": "lib",
            "files": [],
            "children": [],
            "metrics": {"files": 0, "lines": 0},
        })
        diff = analyzer.compute_diff_summary(baseline_arch, new_arch)
        assert "lib" in diff["components_added"]

    def test_component_removed(self, tmp_path, baseline_arch):
        analyzer = IncrementalAnalyzer(tmp_path)
        new_arch = json.loads(json.dumps(baseline_arch))
        new_arch["components"][0]["children"] = []
        diff = analyzer.compute_diff_summary(baseline_arch, new_arch)
        assert "src" in diff["components_removed"]

    def test_component_modified(self, tmp_path, baseline_arch):
        analyzer = IncrementalAnalyzer(tmp_path)
        new_arch = json.loads(json.dumps(baseline_arch))
        new_arch["components"][0]["children"][0]["metrics"]["lines"] = 99
        diff = analyzer.compute_diff_summary(baseline_arch, new_arch)
        assert "src" in diff["components_modified"]

    def test_no_changes(self, tmp_path, baseline_arch):
        analyzer = IncrementalAnalyzer(tmp_path)
        diff = analyzer.compute_diff_summary(baseline_arch, baseline_arch)
        assert diff["components_added"] == []
        assert diff["components_removed"] == []
        assert diff["components_modified"] == []


# ---------------------------------------------------------------------------
# get_changed_files Tests
# ---------------------------------------------------------------------------


class TestGetChangedFiles:
    """Tests for git diff parsing."""

    def test_parses_git_diff_output(self, tmp_path):
        mock_output = "M\tsrc/index.ts\nA\tsrc/new.ts\nD\told.ts\n"
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="abc", head_sha="def")

        with patch("analyzer.incremental.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=mock_output, stderr=""
            )
            result = analyzer.get_changed_files()

        assert ("M", "src/index.ts") in result
        assert ("A", "src/new.ts") in result
        assert ("D", "old.ts") in result

    def test_empty_base_sha_returns_empty(self, tmp_path):
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="")
        result = analyzer.get_changed_files()
        assert result == []

    def test_git_not_available(self, tmp_path):
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="abc")
        with patch(
            "analyzer.incremental.subprocess.run",
            side_effect=FileNotFoundError,
        ):
            result = analyzer.get_changed_files()
        assert result == []

    def test_git_diff_failure(self, tmp_path):
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="abc")
        with patch("analyzer.incremental.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=128, stdout="", stderr="fatal: bad revision"
            )
            result = analyzer.get_changed_files()
        assert result == []

    def test_git_timeout(self, tmp_path):
        analyzer = IncrementalAnalyzer(tmp_path, base_sha="abc")
        with patch(
            "analyzer.incremental.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30),
        ):
            result = analyzer.get_changed_files()
        assert result == []


# ---------------------------------------------------------------------------
# load_baseline Tests
# ---------------------------------------------------------------------------


class TestLoadBaseline:
    """Tests for baseline loading."""

    def test_loads_valid_baseline(self, saved_baseline):
        analyzer = IncrementalAnalyzer(
            saved_baseline.parent.parent,
            baseline_path=saved_baseline,
        )
        result = analyzer.load_baseline()
        assert result is not None
        assert result["name"] == "test-project"

    def test_no_baseline_path(self, tmp_path):
        analyzer = IncrementalAnalyzer(tmp_path, baseline_path=None)
        assert analyzer.load_baseline() is None

    def test_missing_baseline_file(self, tmp_path):
        analyzer = IncrementalAnalyzer(
            tmp_path,
            baseline_path=tmp_path / "missing.json",
        )
        assert analyzer.load_baseline() is None

    def test_invalid_json_baseline(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json!!!")
        analyzer = IncrementalAnalyzer(tmp_path, baseline_path=bad)
        assert analyzer.load_baseline() is None

    def test_non_dict_baseline(self, tmp_path):
        arr = tmp_path / "array.json"
        arr.write_text("[1, 2, 3]")
        analyzer = IncrementalAnalyzer(tmp_path, baseline_path=arr)
        assert analyzer.load_baseline() is None


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestIncrementalIntegration:
    """Integration tests using real git repos."""

    def test_full_run_no_baseline(self, temp_git_repo):
        """First run with no baseline triggers full rescan."""
        analyzer = IncrementalAnalyzer(
            temp_git_repo,
            base_sha="",
            head_sha="HEAD",
        )
        result = analyzer.run()

        assert "incremental" in result
        assert result["incremental"]["full_rescan"] is True
        assert "components" in result
        assert "stats" in result

    def test_full_run_with_baseline(self, temp_git_repo, baseline_arch):
        """Run with baseline and a new commit produces diff metadata."""
        # Save baseline
        baseline_path = temp_git_repo / ".arch-baseline" / "architecture.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(baseline_arch))

        # Get initial commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(temp_git_repo),
            capture_output=True, text=True,
        )
        initial_sha = result.stdout.strip()

        # Make a change and commit
        (temp_git_repo / "src" / "new_file.ts").write_text(
            "export const x = 42;\n"
        )
        subprocess.run(
            ["git", "add", "-A"], cwd=str(temp_git_repo),
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add new file"],
            cwd=str(temp_git_repo), capture_output=True, check=True,
        )

        analyzer = IncrementalAnalyzer(
            temp_git_repo,
            base_sha=initial_sha,
            head_sha="HEAD",
            baseline_path=baseline_path,
        )
        output = analyzer.run()

        assert "incremental" in output
        incr = output["incremental"]
        assert incr["base_sha"] == initial_sha
        assert len(incr["changed_files"]) > 0

    def test_cli_incremental_flag(self, monkeypatch, temp_git_repo):
        """CLI --incremental flag runs the incremental analyzer."""
        from analyzer.cli import main

        out_file = temp_git_repo / "output" / "arch.json"
        monkeypatch.setattr("sys.argv", [
            "analyze",
            str(temp_git_repo),
            "--incremental",
            "--base-sha", "",
            "-o", str(out_file),
        ])
        main()

        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert "incremental" in data
        assert data["incremental"]["full_rescan"] is True

        # Baseline should be saved
        baseline = temp_git_repo / ".arch-baseline" / "architecture.json"
        assert baseline.exists()
