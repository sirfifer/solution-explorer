"""Tests for incremental analysis with diff metadata."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from analyzer import __version__
from analyzer.incremental import (
    MARKER_FILES,
    IncrementalAnalyzer,
    _affected_ids_to_paths,
    _recalculate_stats,
    build_component_dependency_graph,
    load_file_index,
    load_import_graph,
    save_baseline_cache,
)
from analyzer.models import to_dict
from analyzer.scanner import ArchitectureScanner

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
        "symbols": [],
        "stats": {"total_files": 2, "total_components": 2},
    }


@pytest.fixture
def multi_component_baseline():
    """Baseline with multiple components and import relationships."""
    return {
        "name": "multi-project",
        "analyzer_version": __version__,
        "components": [
            {
                "id": "root",
                "name": "multi-project",
                "type": "project",
                "path": "",
                "files": [],
                "children": [
                    {
                        "id": "app",
                        "name": "app",
                        "type": "module",
                        "path": "app",
                        "files": ["app/main.ts"],
                        "children": [],
                        "metrics": {"files": 1, "lines": 20},
                    },
                    {
                        "id": "lib",
                        "name": "lib",
                        "type": "module",
                        "path": "lib",
                        "files": ["lib/utils.ts"],
                        "children": [],
                        "metrics": {"files": 1, "lines": 15},
                    },
                    {
                        "id": "api",
                        "name": "api",
                        "type": "api-server",
                        "path": "api",
                        "port": 3000,
                        "files": ["api/server.ts"],
                        "children": [],
                        "metrics": {"files": 1, "lines": 30},
                    },
                ],
                "metrics": {"files": 3, "lines": 65},
            }
        ],
        "relationships": [
            {"source": "app", "target": "lib", "type": "import"},
            {"source": "api", "target": "lib", "type": "import"},
            {"source": "app", "target": "api", "type": "http"},
        ],
        "files": [
            {"path": "app/main.ts", "language": "typescript", "lines": 20,
             "imports": ["./lib/utils"]},
            {"path": "lib/utils.ts", "language": "typescript", "lines": 15,
             "imports": []},
            {"path": "api/server.ts", "language": "typescript", "lines": 30,
             "imports": ["./lib/utils"]},
        ],
        "symbols": [],
        "stats": {"total_files": 3, "total_components": 4},
    }


@pytest.fixture
def saved_baseline(tmp_path, baseline_arch):
    """Write a baseline JSON file and return its path."""
    baseline_path = tmp_path / "baseline" / "architecture.json"
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(baseline_arch))
    return baseline_path


# ---------------------------------------------------------------------------
# K.1: build_component_dependency_graph Tests
# ---------------------------------------------------------------------------


class TestBuildComponentDependencyGraph:
    """Tests for building the reverse dependency graph."""

    def test_builds_reverse_import_map(self, multi_component_baseline):
        graph = build_component_dependency_graph(multi_component_baseline)
        # lib is imported by app and api
        assert "lib" in graph
        assert graph["lib"] == {"app", "api"}

    def test_ignores_http_relationships(self, multi_component_baseline):
        graph = build_component_dependency_graph(multi_component_baseline)
        # app -> api is HTTP, so api should NOT have app as a dependent via this
        # (api is already in graph because it imports lib, but app->api HTTP should be ignored)
        if "api" in graph:
            assert "app" not in graph["api"]

    def test_ignores_self_references(self):
        baseline = {
            "relationships": [
                {"source": "a", "target": "a", "type": "import"},
            ]
        }
        graph = build_component_dependency_graph(baseline)
        assert graph == {}

    def test_empty_relationships(self):
        graph = build_component_dependency_graph({"relationships": []})
        assert graph == {}

    def test_no_relationships_key(self):
        graph = build_component_dependency_graph({})
        assert graph == {}

    def test_one_level_only(self):
        """Verify the graph only represents direct importers."""
        baseline = {
            "relationships": [
                {"source": "a", "target": "b", "type": "import"},
                {"source": "b", "target": "c", "type": "import"},
            ]
        }
        graph = build_component_dependency_graph(baseline)
        # c is imported by b, b is imported by a
        assert graph["c"] == {"b"}
        assert graph["b"] == {"a"}
        # Expanding c should give {c, b}, NOT {c, b, a}
        expanded = {"c"}
        expanded.update(graph.get("c", set()))
        assert expanded == {"c", "b"}
        assert "a" not in expanded


# ---------------------------------------------------------------------------
# K.5: Baseline caching Tests
# ---------------------------------------------------------------------------


class TestBaselineCaching:
    """Tests for baseline cache save/load."""

    def test_saves_all_cache_files(self, tmp_path, baseline_arch):
        cache_dir = tmp_path / ".arch-baseline"
        save_baseline_cache(baseline_arch, cache_dir, tmp_path)

        assert (cache_dir / "architecture.json").exists()
        assert (cache_dir / "file-index.json").exists()
        assert (cache_dir / "import-graph.json").exists()

    def test_loads_file_index(self, tmp_path, baseline_arch):
        cache_dir = tmp_path / ".arch-baseline"
        save_baseline_cache(baseline_arch, cache_dir, tmp_path)

        index = load_file_index(cache_dir)
        assert index is not None
        assert "src/index.ts" in index
        assert index["src/index.ts"]["lines"] == 5

    def test_loads_import_graph(self, tmp_path, baseline_arch):
        cache_dir = tmp_path / ".arch-baseline"
        save_baseline_cache(baseline_arch, cache_dir, tmp_path)

        graph = load_import_graph(cache_dir)
        assert graph is not None
        # root->src is import type, so src should have root as importer
        assert "src" in graph
        assert "root" in graph["src"]

    def test_load_missing_file_index_returns_none(self, tmp_path):
        assert load_file_index(tmp_path / "nonexistent") is None

    def test_load_missing_import_graph_returns_none(self, tmp_path):
        assert load_import_graph(tmp_path / "nonexistent") is None

    def test_file_index_has_component_ids(self, tmp_path, multi_component_baseline):
        cache_dir = tmp_path / ".arch-baseline"
        # Create the files so hashing works
        for f in multi_component_baseline.get("files", []):
            fpath = tmp_path / f["path"]
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text("// placeholder\n")

        save_baseline_cache(multi_component_baseline, cache_dir, tmp_path)

        index = load_file_index(cache_dir)
        assert index is not None
        assert index["app/main.ts"]["component_id"] == "app"
        assert index["lib/utils.ts"]["component_id"] == "lib"

    def test_file_index_has_content_hashes(self, tmp_path, baseline_arch):
        # Create the actual files
        src = tmp_path / "src"
        src.mkdir(exist_ok=True)
        (src / "index.ts").write_text("export const x = 1;\n")
        (src / "utils.ts").write_text("export const y = 2;\n")

        cache_dir = tmp_path / ".arch-baseline"
        save_baseline_cache(baseline_arch, cache_dir, tmp_path)

        index = load_file_index(cache_dir)
        assert index["src/index.ts"]["content_hash"].startswith("sha256:")


# ---------------------------------------------------------------------------
# Stats recalculation Tests
# ---------------------------------------------------------------------------


class TestRecalculateStats:
    """Tests for _recalculate_stats helper."""

    def test_correct_totals(self, baseline_arch):
        stats = _recalculate_stats(baseline_arch)
        assert stats["total_files"] == 2
        assert stats["total_lines"] == 10
        assert stats["total_components"] == 2
        assert stats["total_relationships"] == 1

    def test_counts_languages(self, baseline_arch):
        stats = _recalculate_stats(baseline_arch)
        assert "typescript" in stats["languages"]
        assert stats["languages"]["typescript"] == 10

    def test_empty_architecture(self):
        stats = _recalculate_stats({
            "files": [],
            "components": [],
            "relationships": [],
            "symbols": [],
        })
        assert stats["total_files"] == 0
        assert stats["total_lines"] == 0
        assert stats["total_components"] == 0


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
        # Save baseline (outside git tracking via .gitignore)
        baseline_path = temp_git_repo / ".arch-baseline" / "architecture.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(baseline_arch))
        (temp_git_repo / ".gitignore").write_text(".arch-baseline/\n")
        subprocess.run(
            ["git", "add", ".gitignore"], cwd=str(temp_git_repo),
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add gitignore"],
            cwd=str(temp_git_repo), capture_output=True, check=True,
        )

        # Get commit SHA after baseline is set up
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
            ["git", "add", "src/new_file.ts"], cwd=str(temp_git_repo),
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
        # Should use incremental path (not full rescan)
        assert incr["full_rescan"] is False
        assert len(incr["affected_components"]) > 0

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

        # Baseline cache files should be saved
        baseline_dir = temp_git_repo / ".arch-baseline"
        assert (baseline_dir / "architecture.json").exists()
        assert (baseline_dir / "file-index.json").exists()
        assert (baseline_dir / "import-graph.json").exists()

    def test_incremental_produces_valid_architecture(self, temp_git_repo, baseline_arch):
        """Incremental results have all required architecture fields."""
        baseline_path = temp_git_repo / ".arch-baseline" / "architecture.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(baseline_arch))

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(temp_git_repo), capture_output=True, text=True,
        )
        initial_sha = result.stdout.strip()

        (temp_git_repo / "src" / "extra.ts").write_text("const z = 3;\n")
        subprocess.run(
            ["git", "add", "-A"], cwd=str(temp_git_repo),
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add extra"],
            cwd=str(temp_git_repo), capture_output=True, check=True,
        )

        analyzer = IncrementalAnalyzer(
            temp_git_repo,
            base_sha=initial_sha,
            head_sha="HEAD",
            baseline_path=baseline_path,
        )
        output = analyzer.run()

        # Verify all required fields exist
        assert "components" in output
        assert "relationships" in output
        assert "files" in output
        assert "stats" in output
        assert "incremental" in output
        assert "analyzer_version" in output

    def test_dependency_expansion(self, temp_git_repo):
        """Verify dependency graph expands affected set to importers."""
        # Create a baseline where app imports lib
        baseline = {
            "name": "test",
            "analyzer_version": __version__,
            "components": [{
                "id": "root", "name": "test", "type": "project", "path": "",
                "files": [], "children": [
                    {"id": "app", "name": "app", "type": "module", "path": "app",
                     "files": ["app/main.ts"], "children": [],
                     "metrics": {"files": 1, "lines": 5}},
                    {"id": "lib", "name": "lib", "type": "module", "path": "lib",
                     "files": ["lib/utils.ts"], "children": [],
                     "metrics": {"files": 1, "lines": 5}},
                ],
                "metrics": {"files": 2, "lines": 10},
            }],
            "relationships": [
                {"source": "app", "target": "lib", "type": "import"},
            ],
            "files": [
                {"path": "app/main.ts", "language": "typescript", "lines": 5,
                 "imports": ["./lib/utils"]},
                {"path": "lib/utils.ts", "language": "typescript", "lines": 5,
                 "imports": []},
            ],
            "symbols": [],
            "stats": {"total_files": 2, "total_components": 3},
        }

        baseline_path = temp_git_repo / ".arch-baseline" / "architecture.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(baseline))

        # Create the directories and files
        app_dir = temp_git_repo / "app"
        app_dir.mkdir(exist_ok=True)
        (app_dir / "main.ts").write_text('import { x } from "../lib/utils";\n')
        lib_dir = temp_git_repo / "lib"
        lib_dir.mkdir(exist_ok=True)
        (lib_dir / "utils.ts").write_text("export const x = 1;\n")

        # Commit initial state
        subprocess.run(
            ["git", "add", "-A"], cwd=str(temp_git_repo),
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add app and lib"],
            cwd=str(temp_git_repo), capture_output=True, check=True,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(temp_git_repo), capture_output=True, text=True,
        )
        initial_sha = result.stdout.strip()

        # Change lib (which app depends on)
        (lib_dir / "utils.ts").write_text("export const x = 2;\nexport const y = 3;\n")
        subprocess.run(
            ["git", "add", "-A"], cwd=str(temp_git_repo),
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Update lib"],
            cwd=str(temp_git_repo), capture_output=True, check=True,
        )

        analyzer = IncrementalAnalyzer(
            temp_git_repo,
            base_sha=initial_sha,
            head_sha="HEAD",
            baseline_path=baseline_path,
        )
        output = analyzer.run()

        incr = output["incremental"]
        assert incr["full_rescan"] is False
        # lib was directly changed
        assert "lib" in incr["directly_affected_components"]
        # app imports lib, so it should be expanded
        assert "app" in incr["expanded_via_dependency"]
        assert "app" in incr["affected_components"]


# ---------------------------------------------------------------------------
# TestScopedScanner
# ---------------------------------------------------------------------------


class TestScopedScanner:
    """Tests for ArchitectureScanner with scope_paths/baseline parameters."""

    def test_scope_paths_without_baseline_raises(self, tmp_path):
        """scope_paths without baseline must raise ValueError."""
        with pytest.raises(ValueError, match="scope_paths requires a baseline"):
            ArchitectureScanner(tmp_path, scope_paths=["src"])

    def test_scope_paths_with_baseline_accepted(self, tmp_path):
        """scope_paths with a baseline dict should not raise."""
        baseline = {"components": [], "relationships": [], "files": [],
                    "symbols": [], "stats": {}}
        scanner = ArchitectureScanner(
            tmp_path, scope_paths=["src"], baseline=baseline,
        )
        assert scanner._scope_paths == ["src"]
        assert scanner._baseline is baseline

    def test_scoped_scan_only_processes_scope_paths(self, tmp_path):
        """Files outside scope_paths should come from baseline, not disk."""
        # Create two component directories with source files
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "package.json").write_text("{}")
        (tmp_path / "app" / "main.py").write_text(
            "import os\nprint('hello')\n"
        )
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "package.json").write_text("{}")
        (tmp_path / "lib" / "utils.py").write_text(
            "def helper(): pass\n"
        )

        # First do a full scan to get a valid baseline
        full_scanner = ArchitectureScanner(tmp_path)
        full_arch = full_scanner.scan()
        baseline = to_dict(full_arch)

        # Now modify only lib/utils.py
        (tmp_path / "lib" / "utils.py").write_text(
            "def helper(): pass\ndef new_func(): pass\n"
        )

        # Run scoped scan targeting only lib
        scoped_scanner = ArchitectureScanner(
            tmp_path, scope_paths=["lib"], baseline=baseline,
        )
        scoped_arch = scoped_scanner.scan()
        scoped_result = to_dict(scoped_arch)

        # Should have components from both app and lib
        all_ids = set()

        def collect_ids(comps):
            for c in comps:
                all_ids.add(c["id"])
                collect_ids(c.get("children", []))

        collect_ids(scoped_result.get("components", []))
        assert "lib" in all_ids
        assert "app" in all_ids

    def test_scoped_scan_preserves_unaffected_relationships(self, tmp_path):
        """Relationships between unaffected components survive scoped scan."""
        # Create three components
        for d in ["app", "lib", "api"]:
            (tmp_path / d).mkdir()
            (tmp_path / d / "package.json").write_text("{}")

        (tmp_path / "app" / "main.py").write_text("import lib.utils\n")
        (tmp_path / "lib" / "utils.py").write_text("def helper(): pass\n")
        (tmp_path / "api" / "server.py").write_text("import lib.utils\n")

        # Full scan
        full_scanner = ArchitectureScanner(tmp_path)
        baseline = to_dict(full_scanner.scan())

        # Find relationships involving api and lib in baseline
        baseline_rels = baseline.get("relationships", [])
        api_lib_rels = [
            r for r in baseline_rels
            if r["source"] == "api" and r["target"] == "lib"
        ]

        # Run scoped scan targeting only app (api and lib are unaffected)
        scoped_scanner = ArchitectureScanner(
            tmp_path, scope_paths=["app"], baseline=baseline,
        )
        scoped_result = to_dict(scoped_scanner.scan())

        # api->lib relationships should be preserved
        scoped_rels = scoped_result.get("relationships", [])
        scoped_api_lib = [
            r for r in scoped_rels
            if r["source"] == "api" and r["target"] == "lib"
        ]
        assert len(scoped_api_lib) == len(api_lib_rels)

    def test_scoped_scan_detects_new_file(self, tmp_path):
        """New files added within scope_paths should be picked up."""
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "package.json").write_text("{}")
        (tmp_path / "lib" / "utils.py").write_text("x = 1\n")

        # Full scan baseline
        baseline = to_dict(ArchitectureScanner(tmp_path).scan())
        baseline_file_count = len([
            f for f in baseline.get("files", [])
            if f["path"].startswith("lib/")
        ])

        # Add a new file
        (tmp_path / "lib" / "helpers.py").write_text("y = 2\n")

        # Scoped scan
        scoped = to_dict(ArchitectureScanner(
            tmp_path, scope_paths=["lib"], baseline=baseline,
        ).scan())

        scoped_file_count = len([
            f for f in scoped.get("files", [])
            if f["path"].startswith("lib/")
        ])
        assert scoped_file_count == baseline_file_count + 1

    def test_scoped_scan_handles_deleted_file(self, tmp_path):
        """Deleted files within scope_paths should disappear from output."""
        (tmp_path / "lib").mkdir()
        (tmp_path / "lib" / "package.json").write_text("{}")
        (tmp_path / "lib" / "utils.py").write_text("x = 1\n")
        (tmp_path / "lib" / "old.py").write_text("y = 2\n")

        baseline = to_dict(ArchitectureScanner(tmp_path).scan())
        baseline_file_count = len([
            f for f in baseline.get("files", [])
            if f["path"].startswith("lib/")
        ])

        # Delete a file
        (tmp_path / "lib" / "old.py").unlink()

        scoped = to_dict(ArchitectureScanner(
            tmp_path, scope_paths=["lib"], baseline=baseline,
        ).scan())

        scoped_file_count = len([
            f for f in scoped.get("files", [])
            if f["path"].startswith("lib/")
        ])
        assert scoped_file_count == baseline_file_count - 1

    def test_affected_ids_to_paths_basic(self):
        """_affected_ids_to_paths extracts correct directory paths."""
        baseline = {
            "components": [
                {
                    "id": "root", "path": "",
                    "children": [
                        {"id": "app", "path": "app", "children": []},
                        {"id": "lib", "path": "lib", "children": []},
                        {"id": "api", "path": "api", "children": []},
                    ],
                }
            ]
        }
        result = _affected_ids_to_paths({"app", "api"}, baseline)
        assert result == ["api", "app"]  # sorted

    def test_affected_ids_to_paths_nested(self):
        """_affected_ids_to_paths finds deeply nested components."""
        baseline = {
            "components": [
                {
                    "id": "root", "path": "",
                    "children": [
                        {
                            "id": "app", "path": "app",
                            "children": [
                                {"id": "app/ui", "path": "app/ui",
                                 "children": []},
                            ],
                        },
                    ],
                }
            ]
        }
        result = _affected_ids_to_paths({"app/ui"}, baseline)
        assert result == ["app/ui"]

    def test_affected_ids_to_paths_empty(self):
        """Empty affected set returns empty list."""
        baseline = {
            "components": [
                {"id": "root", "path": "", "children": []}
            ]
        }
        assert _affected_ids_to_paths(set(), baseline) == []

    def test_scoped_scan_unaffected_components_match_baseline(self, tmp_path):
        """Unaffected components in scoped scan match baseline exactly."""
        for d in ["app", "lib"]:
            (tmp_path / d).mkdir()
            (tmp_path / d / "package.json").write_text("{}")

        (tmp_path / "app" / "main.py").write_text("x = 1\n")
        (tmp_path / "lib" / "utils.py").write_text("y = 2\n")

        baseline = to_dict(ArchitectureScanner(tmp_path).scan())

        # Find lib component data in baseline
        def find_comp(comps, comp_id):
            for c in comps:
                if c["id"] == comp_id:
                    return c
                found = find_comp(c.get("children", []), comp_id)
                if found:
                    return found
            return None

        baseline_lib = find_comp(baseline["components"], "lib")

        # Scoped scan targeting only app (lib is unaffected)
        scoped = to_dict(ArchitectureScanner(
            tmp_path, scope_paths=["app"], baseline=baseline,
        ).scan())

        scoped_lib = find_comp(scoped["components"], "lib")

        # Files should match
        assert baseline_lib["files"] == scoped_lib["files"]


# ---------------------------------------------------------------------------
# TestUnmappedChangedFileFallback (F-CRIT-8)
# ---------------------------------------------------------------------------


def _git(repo, *args):
    subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, check=True,
    )


def _head_sha(repo):
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _flatten_output_files(output):
    """Collect every file path referenced by the analysis output."""
    paths = {f.get("path") for f in output.get("files", [])}

    def _walk(components):
        for comp in components:
            paths.update(comp.get("files", []))
            _walk(comp.get("children", []))

    _walk(output.get("components", []))
    return paths


class TestUnmappedChangedFileFallback:
    """A changed file that maps to no component must not be silently dropped.

    Regression tests for F-CRIT-8. The incremental path only rescans components
    reachable from the change set, so a new root-level file or a file in a
    brand-new directory maps to zero components and used to vanish from output.
    The fix falls back to a full rescan when any changed file is unmapped.
    """

    # A baseline whose file count is high enough that a single changed file is
    # well under the 50% full-rescan threshold, so the ONLY thing that can
    # trigger a full rescan in these tests is the unmapped-file fallback.
    def _baseline(self):
        return {
            "name": "test-project",
            "analyzer_version": __version__,
            "components": [{
                "id": "root", "name": "test-project", "type": "project",
                "path": "", "files": ["src/index.ts"],
                "children": [
                    {"id": "src", "name": "src", "type": "module", "path": "src",
                     "files": ["src/index.ts"], "children": [],
                     "metrics": {"files": 1, "lines": 3}},
                ],
                "metrics": {"files": 1, "lines": 3},
            }],
            "relationships": [],
            "files": [
                {"path": "src/index.ts", "language": "typescript", "lines": 3},
                {"path": "src/a.ts", "language": "typescript", "lines": 3},
                {"path": "src/b.ts", "language": "typescript", "lines": 3},
                {"path": "src/c.ts", "language": "typescript", "lines": 3},
            ],
            "symbols": [],
            "stats": {"total_files": 4, "total_components": 2},
        }

    def _write_baseline(self, repo):
        # Ignore the baseline cache and commit that first, so it never appears
        # in the diff (mirrors real usage where .arch-baseline/ is gitignored).
        (repo / ".gitignore").write_text(".arch-baseline/\n")
        _git(repo, "add", ".gitignore")
        _git(repo, "commit", "-m", "Ignore baseline cache")
        baseline_path = repo / ".arch-baseline" / "architecture.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(self._baseline()))
        return baseline_path

    def test_new_root_level_file_included_via_full_rescan(self, temp_git_repo):
        baseline_path = self._write_baseline(temp_git_repo)
        base_sha = _head_sha(temp_git_repo)

        # A new file at the repository root maps to no component under the
        # incremental directory walk (it has no parent directory to match).
        (temp_git_repo / "config.ts").write_text("export const flag = true;\n")
        _git(temp_git_repo, "add", "-A")
        _git(temp_git_repo, "commit", "-m", "Add root-level config")

        analyzer = IncrementalAnalyzer(
            temp_git_repo, base_sha=base_sha, head_sha="HEAD",
            baseline_path=baseline_path,
        )
        output = analyzer.run()

        incr = output["incremental"]
        # Falls back to a full rescan with a stated reason.
        assert incr["full_rescan"] is True
        assert "no known component" in incr["rescan_reason"]
        # The new root-level file appears in the merged output.
        assert "config.ts" in _flatten_output_files(output)

    def test_new_directory_included_via_full_rescan(self, temp_git_repo):
        baseline_path = self._write_baseline(temp_git_repo)
        base_sha = _head_sha(temp_git_repo)

        # A file in a brand-new directory has no matching component path.
        widgets = temp_git_repo / "widgets"
        widgets.mkdir()
        (widgets / "button.ts").write_text("export const Button = 1;\n")
        _git(temp_git_repo, "add", "-A")
        _git(temp_git_repo, "commit", "-m", "Add widgets directory")

        analyzer = IncrementalAnalyzer(
            temp_git_repo, base_sha=base_sha, head_sha="HEAD",
            baseline_path=baseline_path,
        )
        output = analyzer.run()

        incr = output["incremental"]
        assert incr["full_rescan"] is True
        assert "no known component" in incr["rescan_reason"]
        assert "widgets/button.ts" in _flatten_output_files(output)

    def test_change_to_known_component_stays_incremental(self, temp_git_repo):
        """A change under an existing component must NOT force a full rescan."""
        baseline_path = self._write_baseline(temp_git_repo)
        base_sha = _head_sha(temp_git_repo)

        # Modify a file inside the existing src/ component.
        (temp_git_repo / "src" / "index.ts").write_text(
            "export function main(): void {\n"
            '  console.log("changed");\n'
            "}\n"
        )
        _git(temp_git_repo, "add", "-A")
        _git(temp_git_repo, "commit", "-m", "Edit src/index.ts")

        analyzer = IncrementalAnalyzer(
            temp_git_repo, base_sha=base_sha, head_sha="HEAD",
            baseline_path=baseline_path,
        )
        output = analyzer.run()

        assert output["incremental"]["full_rescan"] is False
