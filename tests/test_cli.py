"""Tests for the CLI and split output."""

import json
import re
import sys
from pathlib import Path

import pytest

# Add project root to path so we can import the analyzer package
sys.path.insert(0, str(Path(__file__).parent.parent))
from analyzer.cli import main, safe_component_id, write_split
from analyzer.models import Architecture, Component, FileInfo, Symbol, to_dict

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_arch():
    """Build a minimal Architecture with 2 components, files, and symbols."""
    sym_a1 = Symbol(
        id="sym-a1",
        name="ClassA",
        kind="class",
        file="comp-a/main.py",
        line=1,
        end_line=10,
        code_preview="class ClassA:",
        visibility="public",
    )
    sym_a2 = Symbol(
        id="sym-a2",
        name="helper",
        kind="function",
        file="comp-a/utils.py",
        line=1,
        end_line=5,
        code_preview="def helper():",
        visibility="internal",
    )
    sym_b1 = Symbol(
        id="sym-b1",
        name="ServerApp",
        kind="class",
        file="comp-b/server.py",
        line=1,
        end_line=20,
        code_preview="class ServerApp:",
        visibility="public",
    )

    file_a1 = FileInfo(
        path="comp-a/main.py",
        language="python",
        lines=10,
        size_bytes=200,
        symbols=["sym-a1"],
        imports=["os"],
    )
    file_a2 = FileInfo(
        path="comp-a/utils.py",
        language="python",
        lines=5,
        size_bytes=80,
        symbols=["sym-a2"],
        imports=[],
    )
    file_b1 = FileInfo(
        path="comp-b/server.py",
        language="python",
        lines=20,
        size_bytes=400,
        symbols=["sym-b1"],
        imports=["flask"],
    )

    comp_a = Component(
        id="comp-a",
        name="Component A",
        type="module",
        path="comp-a",
        language="python",
        files=["comp-a/main.py", "comp-a/utils.py"],
    )
    comp_b = Component(
        id="comp-b",
        name="Component B",
        type="service",
        path="comp-b",
        language="python",
        framework="Flask",
        files=["comp-b/server.py"],
    )

    return to_dict(Architecture(
        name="test-project",
        description="A test project for CLI tests",
        components=[comp_a, comp_b],
        symbols=[sym_a1, sym_a2, sym_b1],
        files=[file_a1, file_a2, file_b1],
        stats={
            "total_components": 2,
            "total_files": 3,
            "total_lines": 35,
            "total_symbols": 3,
            "total_relationships": 0,
            "languages": {"python": 35},
        },
    ))


@pytest.fixture
def arch_with_slashes():
    """Architecture with component IDs containing slashes."""
    sym = Symbol(
        id="sym-vs",
        name="Layout",
        kind="function",
        file="viewer/src/layout.ts",
        line=1,
        end_line=8,
        code_preview="export function Layout() {",
    )
    file_info = FileInfo(
        path="viewer/src/layout.ts",
        language="typescript",
        lines=8,
        size_bytes=120,
        symbols=["sym-vs"],
    )
    comp = Component(
        id="viewer/src",
        name="Viewer Source",
        type="module",
        path="viewer/src",
        language="typescript",
        files=["viewer/src/layout.ts"],
    )
    return to_dict(Architecture(
        name="slash-project",
        description="Project with slash IDs",
        components=[comp],
        symbols=[sym],
        files=[file_info],
        stats={
            "total_components": 1,
            "total_files": 1,
            "total_lines": 8,
            "total_symbols": 1,
            "total_relationships": 0,
            "languages": {"typescript": 8},
        },
    ))


@pytest.fixture
def arch_with_children():
    """Architecture where a parent component has nested children."""
    sym_child = Symbol(
        id="sym-child",
        name="ChildClass",
        kind="class",
        file="parent/child/impl.py",
        line=1,
        end_line=5,
        code_preview="class ChildClass:",
    )
    sym_parent = Symbol(
        id="sym-parent",
        name="ParentInit",
        kind="function",
        file="parent/__init__.py",
        line=1,
        end_line=3,
        code_preview="def init():",
    )
    file_child = FileInfo(
        path="parent/child/impl.py",
        language="python",
        lines=5,
        size_bytes=60,
        symbols=["sym-child"],
    )
    file_parent = FileInfo(
        path="parent/__init__.py",
        language="python",
        lines=3,
        size_bytes=30,
        symbols=["sym-parent"],
    )
    child_comp = Component(
        id="parent/child",
        name="Child",
        type="module",
        path="parent/child",
        files=["parent/child/impl.py"],
    )
    parent_comp = Component(
        id="parent",
        name="Parent",
        type="package",
        path="parent",
        files=["parent/__init__.py"],
        children=[child_comp],
    )
    return to_dict(Architecture(
        name="nested-project",
        description="Project with nested children",
        components=[parent_comp],
        symbols=[sym_child, sym_parent],
        files=[file_child, file_parent],
        stats={
            "total_components": 2,
            "total_files": 2,
            "total_lines": 8,
            "total_symbols": 2,
            "total_relationships": 0,
            "languages": {"python": 8},
        },
    ))


@pytest.fixture
def arch_empty_component():
    """Architecture with a component that has no files or symbols."""
    comp = Component(
        id="empty-comp",
        name="Empty",
        type="module",
        path="empty",
        files=[],
    )
    return to_dict(Architecture(
        name="empty-project",
        description="Project with empty component",
        components=[comp],
        symbols=[],
        files=[],
        stats={
            "total_components": 1,
            "total_files": 0,
            "total_lines": 0,
            "total_symbols": 0,
            "total_relationships": 0,
            "languages": {},
        },
    ))


@pytest.fixture
def temp_repo(tmp_path):
    """Create a minimal repo on disk for integration tests."""
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "cli-test-project",
        "description": "Integration test project",
    }))
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.ts").write_text(
        "export function greet(): string {\n"
        '  return "hello";\n'
        "}\n"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# CLI Argument Parsing Tests
# ---------------------------------------------------------------------------


class TestCLIArgumentDefaults:
    """Tests for argparse default values and flag behavior."""

    def test_default_path_is_dot(self, monkeypatch, tmp_path, capsys):
        """Default path argument is '.' (current directory)."""
        # Point at a real directory to avoid the is_dir() check failing
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        (work_dir / "setup.py").write_text("# empty\n")
        monkeypatch.chdir(work_dir)
        monkeypatch.setattr("sys.argv", ["analyze", "-o", str(tmp_path / "out.json")])
        main()
        out = tmp_path / "out.json"
        assert out.exists()

    def test_default_output_is_architecture_json(self, monkeypatch, temp_repo, capsys):
        """Default output file is architecture.json."""
        monkeypatch.setattr("sys.argv", ["analyze", str(temp_repo)])
        monkeypatch.chdir(temp_repo)
        main()
        assert (temp_repo / "architecture.json").exists()

    def test_default_max_symbols_is_5000_single_file_mode(self, monkeypatch, temp_repo):
        """In single-file mode, max_symbols defaults to 5000."""
        captured_kwargs = {}
        from analyzer.scanner import ArchitectureScanner

        original_init = ArchitectureScanner.__init__

        def capture_init(self, *args, **kwargs):
            captured_kwargs.update(kwargs)
            return original_init(self, *args, **kwargs)

        monkeypatch.setattr(ArchitectureScanner, "__init__", capture_init)
        # Legacy v1 behavior: the symbol cap is a v1-only concept (v2 is uncapped
        # and covers everything via the ledger), so pin the engine to v1.
        monkeypatch.setattr("sys.argv", [
            "analyze", str(temp_repo), "--engine", "v1",
            "-o", str(temp_repo / "out.json"),
        ])
        main()
        assert captured_kwargs["max_symbols"] == 5000

    def test_split_flag_changes_max_symbols_default_to_zero(self, monkeypatch, temp_repo):
        """--split flag makes max_symbols default to 0 (unlimited)."""
        captured_kwargs = {}
        from analyzer.scanner import ArchitectureScanner

        original_init = ArchitectureScanner.__init__

        def capture_init(self, *args, **kwargs):
            captured_kwargs.update(kwargs)
            return original_init(self, *args, **kwargs)

        monkeypatch.setattr(ArchitectureScanner, "__init__", capture_init)
        # Legacy v1 behavior (v2 has no max_symbols concept). Pin to v1.
        monkeypatch.setattr("sys.argv", [
            "analyze", str(temp_repo), "--engine", "v1", "--split",
            "-o", str(temp_repo / "split-out"),
        ])
        main()
        assert captured_kwargs["max_symbols"] == 0

    def test_compact_flag_produces_compact_json(self, monkeypatch, temp_repo):
        """--compact flag produces JSON without indentation."""
        out_file = temp_repo / "compact.json"
        monkeypatch.setattr("sys.argv", [
            "analyze", str(temp_repo), "--compact", "-o", str(out_file),
        ])
        main()
        raw = out_file.read_text()
        # Compact JSON should not have leading whitespace on lines (no indentation)
        lines = raw.strip().splitlines()
        # A compact JSON is typically a single line or has no indented lines
        # At minimum, it should be valid JSON and noticeably shorter than pretty
        data = json.loads(raw)
        assert data["name"] is not None
        # Compact output should have few or no indented lines
        indented_lines = [line for line in lines if line.startswith("  ")]
        assert len(indented_lines) == 0

    def test_max_symbols_explicit_override(self, monkeypatch, temp_repo):
        """--max-symbols explicitly overrides the default."""
        captured_kwargs = {}
        from analyzer.scanner import ArchitectureScanner

        original_init = ArchitectureScanner.__init__

        def capture_init(self, *args, **kwargs):
            captured_kwargs.update(kwargs)
            return original_init(self, *args, **kwargs)

        monkeypatch.setattr(ArchitectureScanner, "__init__", capture_init)
        # Legacy v1 behavior (v2 has no max_symbols concept). Pin to v1.
        monkeypatch.setattr("sys.argv", [
            "analyze", str(temp_repo), "--engine", "v1", "--max-symbols", "100",
            "-o", str(temp_repo / "out.json"),
        ])
        main()
        assert captured_kwargs["max_symbols"] == 100

    def test_nonexistent_directory_exits(self, monkeypatch, tmp_path, capsys):
        """Passing a non-existent directory causes sys.exit(1)."""
        fake_path = tmp_path / "does-not-exist"
        monkeypatch.setattr("sys.argv", ["analyze", str(fake_path)])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "not a directory" in captured.err

    def test_config_nonexistent_file_exits(self, monkeypatch, tmp_path, capsys):
        """--config with a non-existent path causes sys.exit(1)."""
        monkeypatch.setattr("sys.argv", [
            "analyze", "--config", str(tmp_path / "missing.json"),
        ])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "Config file not found" in captured.err

    def test_custom_output_path(self, monkeypatch, temp_repo):
        """Custom -o path is respected."""
        out = temp_repo / "subdir" / "custom.json"
        monkeypatch.setattr("sys.argv", [
            "analyze", str(temp_repo), "-o", str(out),
        ])
        main()
        assert out.exists()
        data = json.loads(out.read_text())
        assert "components" in data

    def test_incremental_with_split_is_argparse_error(
        self, monkeypatch, temp_repo, capsys
    ):
        """--incremental --split is rejected, not silently downgraded (F-AN-9).

        This is a v1-only guard: v2 is incremental by construction and accepts
        --incremental --split, so pin the engine to v1.
        """
        monkeypatch.setattr("sys.argv", [
            "analyze", str(temp_repo), "--engine", "v1", "--incremental", "--split",
            "-o", str(temp_repo / "out"),
        ])
        with pytest.raises(SystemExit) as exc:
            main()
        # argparse.error exits with code 2.
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "--incremental" in err and "--split" in err

    def test_config_with_incremental_is_argparse_error(
        self, monkeypatch, tmp_path, capsys
    ):
        """--config --incremental is rejected, not silently one-wins (F-AN-9).

        This is a v1-only guard: v2 accepts --incremental as a no-op, so pin v1.
        """
        cfg = tmp_path / "solution-explorer.json"
        cfg.write_text(json.dumps({"solution": "S", "repositories": []}))
        monkeypatch.setattr("sys.argv", [
            "analyze", "--engine", "v1", "--config", str(cfg), "--incremental",
        ])
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "--config" in err and "--incremental" in err


# ---------------------------------------------------------------------------
# write_split() Unit Tests
# ---------------------------------------------------------------------------


class TestWriteSplit:
    """Tests for the write_split() function."""

    def test_creates_output_directory_structure(self, tmp_path, minimal_arch):
        """write_split creates output_dir, output_dir/data, and manifest.json."""
        out = tmp_path / "output"
        write_split(minimal_arch, out, indent=2)

        assert out.is_dir()
        assert (out / "data").is_dir()
        assert (out / "manifest.json").is_file()

    def test_manifest_excludes_symbols_and_files(self, tmp_path, minimal_arch):
        """Manifest contains components, relationships, stats but NOT symbols or files."""
        out = tmp_path / "output"
        write_split(minimal_arch, out, indent=2)

        manifest = json.loads((out / "manifest.json").read_text())
        assert "components" in manifest
        assert "relationships" in manifest
        assert "stats" in manifest
        assert "symbols" not in manifest
        assert "files" not in manifest

    def test_manifest_contains_component_detail_index(self, tmp_path, minimal_arch):
        """Manifest includes component_detail_index with correct component IDs."""
        out = tmp_path / "output"
        write_split(minimal_arch, out, indent=2)

        manifest = json.loads((out / "manifest.json").read_text())
        idx = manifest["component_detail_index"]
        assert "comp-a" in idx
        assert "comp-b" in idx

    def test_component_detail_index_counts_match(self, tmp_path, minimal_arch):
        """component_detail_index counts match actual detail file contents."""
        out = tmp_path / "output"
        write_split(minimal_arch, out, indent=2)

        manifest = json.loads((out / "manifest.json").read_text())
        idx = manifest["component_detail_index"]

        # Verify comp-a: should have 2 files (main.py, utils.py) and 2 symbols
        assert idx["comp-a"]["fileCount"] == 2
        assert idx["comp-a"]["symbolCount"] == 2

        # Verify from actual detail file
        detail_a = json.loads((out / "data" / "detail-comp-a.json").read_text())
        assert len(detail_a["files"]) == idx["comp-a"]["fileCount"]
        assert len(detail_a["symbols"]) == idx["comp-a"]["symbolCount"]

        # Verify comp-b: should have 1 file and 1 symbol
        assert idx["comp-b"]["fileCount"] == 1
        assert idx["comp-b"]["symbolCount"] == 1

        detail_b = json.loads((out / "data" / "detail-comp-b.json").read_text())
        assert len(detail_b["files"]) == idx["comp-b"]["fileCount"]
        assert len(detail_b["symbols"]) == idx["comp-b"]["symbolCount"]

    def test_detail_files_created_per_component(self, tmp_path, minimal_arch):
        """Each component gets its own detail-{safe_id}.json file."""
        out = tmp_path / "output"
        write_split(minimal_arch, out, indent=2)

        assert (out / "data" / "detail-comp-a.json").is_file()
        assert (out / "data" / "detail-comp-b.json").is_file()

    def test_detail_file_contains_correct_symbols(self, tmp_path, minimal_arch):
        """Detail file for a component contains only its symbols."""
        out = tmp_path / "output"
        write_split(minimal_arch, out, indent=2)

        detail_a = json.loads((out / "data" / "detail-comp-a.json").read_text())
        symbol_names = [s["name"] for s in detail_a["symbols"]]
        assert "ClassA" in symbol_names
        assert "helper" in symbol_names
        assert "ServerApp" not in symbol_names

        detail_b = json.loads((out / "data" / "detail-comp-b.json").read_text())
        symbol_names_b = [s["name"] for s in detail_b["symbols"]]
        assert "ServerApp" in symbol_names_b
        assert "ClassA" not in symbol_names_b

    def test_detail_file_contains_correct_files(self, tmp_path, minimal_arch):
        """Detail file for a component contains only its file infos."""
        out = tmp_path / "output"
        write_split(minimal_arch, out, indent=2)

        detail_a = json.loads((out / "data" / "detail-comp-a.json").read_text())
        file_paths = [f["path"] for f in detail_a["files"]]
        assert "comp-a/main.py" in file_paths
        assert "comp-a/utils.py" in file_paths
        assert "comp-b/server.py" not in file_paths

    def test_slash_ids_converted_to_double_dash(self, tmp_path, arch_with_slashes):
        """Component IDs with slashes are converted to -- in filenames."""
        out = tmp_path / "output"
        write_split(arch_with_slashes, out, indent=2)

        # viewer/src -> detail-viewer--src.json
        detail_path = out / "data" / "detail-viewer--src.json"
        assert detail_path.is_file()

        detail = json.loads(detail_path.read_text())
        assert len(detail["symbols"]) == 1
        assert detail["symbols"][0]["name"] == "Layout"

    def test_colon_ids_are_escaped(self, tmp_path):
        """Component IDs with colons (e.g. multi-repo 'repo:name') must be escaped.

        GitHub's actions/upload-artifact rejects colons in filenames to stay
        NTFS-compatible. Regression test for the 2026-04 deploy failure.
        """
        comp = Component(
            id="repo:unamentis",
            name="UnaMentis",
            type="repository",
            path=".",
            language=None,
            files=[],
        )
        arch = to_dict(Architecture(
            name="multi-repo",
            description="",
            components=[comp],
            symbols=[],
            files=[],
            stats={
                "total_components": 1,
                "total_files": 0,
                "total_lines": 0,
                "total_symbols": 0,
                "total_relationships": 0,
                "languages": {},
            },
        ))

        out = tmp_path / "output"
        write_split(arch, out, indent=2)

        # repo:unamentis -> detail-repo__unamentis.json
        detail_path = out / "data" / "detail-repo__unamentis.json"
        assert detail_path.is_file(), \
            f"expected {detail_path.name} but data dir contains: " \
            f"{[p.name for p in (out / 'data').iterdir()]}"

        # No file should ever be written with a colon in its name.
        for p in (out / "data").iterdir():
            assert ":" not in p.name, f"colon leaked into filename: {p.name}"


class TestSafeComponentId:
    """Unit tests for safe_component_id(). Must stay in sync with the
    viewer's loadComponentDetail() escape logic in viewer/src/store.ts."""

    def test_slash_becomes_double_dash(self):
        assert safe_component_id("viewer/src") == "viewer--src"

    def test_colon_becomes_double_underscore(self):
        assert safe_component_id("repo:unamentis") == "repo__unamentis"

    def test_slashes_and_colons_together(self):
        assert safe_component_id("repo:unamentis/viewer") == "repo__unamentis--viewer"

    def test_plain_id_unchanged(self):
        assert safe_component_id("plain-id") == "plain-id"

    def test_nested_children_get_detail_files(self, tmp_path, arch_with_children):
        """Nested children components each get their own detail files."""
        out = tmp_path / "output"
        write_split(arch_with_children, out, indent=2)

        # Parent component
        parent_detail = out / "data" / "detail-parent.json"
        assert parent_detail.is_file()

        # Child component (id=parent/child -> parent--child)
        child_detail = out / "data" / "detail-parent--child.json"
        assert child_detail.is_file()

        child_data = json.loads(child_detail.read_text())
        assert len(child_data["files"]) == 1
        assert child_data["files"][0]["path"] == "parent/child/impl.py"
        assert len(child_data["symbols"]) == 1
        assert child_data["symbols"][0]["name"] == "ChildClass"

    def test_nested_children_in_detail_index(self, tmp_path, arch_with_children):
        """component_detail_index includes both parent and nested child entries."""
        out = tmp_path / "output"
        write_split(arch_with_children, out, indent=2)

        manifest = json.loads((out / "manifest.json").read_text())
        idx = manifest["component_detail_index"]
        assert "parent" in idx
        assert "parent/child" in idx
        assert idx["parent"]["fileCount"] == 1
        assert idx["parent"]["symbolCount"] == 1
        assert idx["parent/child"]["fileCount"] == 1
        assert idx["parent/child"]["symbolCount"] == 1

    def test_empty_component_produces_empty_detail(self, tmp_path, arch_empty_component):
        """A component with no files produces a detail file with empty arrays."""
        out = tmp_path / "output"
        write_split(arch_empty_component, out, indent=2)

        detail = json.loads((out / "data" / "detail-empty-comp.json").read_text())
        assert detail["symbols"] == []
        assert detail["files"] == []

    def test_empty_component_index_counts_zero(self, tmp_path, arch_empty_component):
        """Empty component has symbolCount=0 and fileCount=0 in the index."""
        out = tmp_path / "output"
        write_split(arch_empty_component, out, indent=2)

        manifest = json.loads((out / "manifest.json").read_text())
        idx = manifest["component_detail_index"]
        assert idx["empty-comp"]["symbolCount"] == 0
        assert idx["empty-comp"]["fileCount"] == 0

    def test_compact_indent_none(self, tmp_path, minimal_arch):
        """When indent=None, output is compact (no indentation)."""
        out = tmp_path / "output"
        write_split(minimal_arch, out, indent=None)

        manifest_raw = (out / "manifest.json").read_text()
        lines = manifest_raw.strip().splitlines()
        # Compact JSON should be a single line
        assert len(lines) == 1

    def test_pretty_indent_two(self, tmp_path, minimal_arch):
        """When indent=2, output is pretty-printed with multiple lines."""
        out = tmp_path / "output"
        write_split(minimal_arch, out, indent=2)

        manifest_raw = (out / "manifest.json").read_text()
        lines = manifest_raw.strip().splitlines()
        # Pretty output should have many lines
        assert len(lines) > 5

    def test_manifest_preserves_other_fields(self, tmp_path, minimal_arch):
        """Manifest preserves name, description, and other top-level fields."""
        out = tmp_path / "output"
        write_split(minimal_arch, out, indent=2)

        manifest = json.loads((out / "manifest.json").read_text())
        assert manifest["name"] == "test-project"
        assert manifest["description"] == "A test project for CLI tests"
        assert manifest["stats"]["total_components"] == 2

    def test_manifest_preserves_relationships(self, tmp_path):
        """Manifest preserves the relationships array."""
        from analyzer.models import Relationship

        rel = Relationship(source="comp-a", target="comp-b", type="import", label="uses")
        arch = to_dict(Architecture(
            name="rel-test",
            description="Relationship test",
            components=[
                Component(id="comp-a", name="A", type="module", path="a"),
                Component(id="comp-b", name="B", type="module", path="b"),
            ],
            relationships=[rel],
            symbols=[],
            files=[],
            stats={
                "total_components": 2,
                "total_files": 0,
                "total_lines": 0,
                "total_symbols": 0,
                "total_relationships": 1,
                "languages": {},
            },
        ))

        out = tmp_path / "output"
        write_split(arch, out, indent=2)

        manifest = json.loads((out / "manifest.json").read_text())
        assert len(manifest["relationships"]) == 1
        assert manifest["relationships"][0]["source"] == "comp-a"
        assert manifest["relationships"][0]["target"] == "comp-b"
        assert manifest["relationships"][0]["type"] == "import"

    def test_detail_file_handles_missing_file_path(self, tmp_path):
        """If a component references a file path not in the files array, it is skipped."""
        comp = Component(
            id="orphan",
            name="Orphan",
            type="module",
            path="orphan",
            files=["nonexistent/file.py"],
        )
        arch = to_dict(Architecture(
            name="orphan-test",
            description="Missing file reference",
            components=[comp],
            symbols=[],
            files=[],
            stats={
                "total_components": 1,
                "total_files": 0,
                "total_lines": 0,
                "total_symbols": 0,
                "total_relationships": 0,
                "languages": {},
            },
        ))

        out = tmp_path / "output"
        write_split(arch, out, indent=2)

        detail = json.loads((out / "data" / "detail-orphan.json").read_text())
        assert detail["files"] == []
        assert detail["symbols"] == []

    def test_output_dir_created_recursively(self, tmp_path, arch_empty_component):
        """write_split creates nested output directories."""
        out = tmp_path / "deep" / "nested" / "output"
        write_split(arch_empty_component, out, indent=2)

        assert out.is_dir()
        assert (out / "manifest.json").is_file()

    def test_stale_detail_files_are_pruned(self, tmp_path, minimal_arch):
        """A detail file from a prior dataset not in the new manifest is removed (F-AN-10)."""
        out = tmp_path / "output"
        data_dir = out / "data"
        data_dir.mkdir(parents=True)

        # Simulate a previous run that wrote a component since removed.
        stale = data_dir / "detail-removed-comp.json"
        stale.write_text('{"symbols": [], "files": []}')

        write_split(minimal_arch, out, indent=2)

        # Current components survive; the stale one is gone.
        assert (data_dir / "detail-comp-a.json").is_file()
        assert (data_dir / "detail-comp-b.json").is_file()
        assert not stale.exists()

    def test_pruning_only_touches_detail_pattern_in_data_dir(self, tmp_path, minimal_arch):
        """Pruning never deletes non-detail files or files outside data/."""
        out = tmp_path / "output"
        data_dir = out / "data"
        data_dir.mkdir(parents=True)

        # A non-detail file inside data/ and an unrelated file beside it.
        keep_in_data = data_dir / "index.json"
        keep_in_data.write_text("{}")
        keep_outside = out / "detail-shouldstay.json"  # not in data/
        keep_outside.write_text("{}")

        write_split(minimal_arch, out, indent=2)

        # Neither the non-detail file nor the file outside data/ is touched.
        assert keep_in_data.exists()
        assert keep_outside.exists()


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestCLIIntegration:
    """Integration tests that run the full CLI pipeline."""

    def test_single_file_produces_valid_json(self, monkeypatch, temp_repo):
        """Single-file mode produces a valid, parseable JSON file."""
        out_file = temp_repo / "arch.json"
        monkeypatch.setattr("sys.argv", [
            "analyze", str(temp_repo), "-o", str(out_file),
        ])
        main()

        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert "components" in data
        assert "symbols" in data
        assert "files" in data
        assert "stats" in data
        assert data["stats"]["total_files"] > 0

    def test_split_mode_produces_manifest_and_details(self, monkeypatch, temp_repo):
        """Split mode produces manifest.json + per-component detail files."""
        out_dir = temp_repo / "split-output"
        monkeypatch.setattr("sys.argv", [
            "analyze", str(temp_repo), "--split", "-o", str(out_dir),
        ])
        main()

        assert (out_dir / "manifest.json").is_file()
        assert (out_dir / "data").is_dir()

        manifest = json.loads((out_dir / "manifest.json").read_text())
        assert "components" in manifest
        assert "component_detail_index" in manifest
        assert "symbols" not in manifest
        assert "files" not in manifest

        # There should be at least one detail file
        detail_files = list((out_dir / "data").glob("detail-*.json"))
        assert len(detail_files) >= 1

    def test_split_default_output_dir(self, monkeypatch, temp_repo):
        """With --split and no -o, output goes to 'architecture/' directory."""
        monkeypatch.chdir(temp_repo)
        monkeypatch.setattr("sys.argv", ["analyze", str(temp_repo), "--split"])
        main()

        arch_dir = temp_repo / "architecture"
        assert arch_dir.is_dir()
        assert (arch_dir / "manifest.json").is_file()

    def test_single_and_split_produce_same_components(self, monkeypatch, temp_repo):
        """Both modes produce identical component trees (just different packaging)."""
        single_out = temp_repo / "single.json"
        split_out = temp_repo / "split-out"

        # Single-file mode
        monkeypatch.setattr("sys.argv", [
            "analyze", str(temp_repo), "-o", str(single_out), "--max-symbols", "0",
        ])
        main()

        # Split mode
        monkeypatch.setattr("sys.argv", [
            "analyze", str(temp_repo), "--split", "-o", str(split_out),
        ])
        main()

        single_data = json.loads(single_out.read_text())
        manifest = json.loads((split_out / "manifest.json").read_text())

        # Component tree structure should match
        assert len(single_data["components"]) == len(manifest["components"])
        single_ids = sorted(self._collect_ids(single_data["components"]))
        manifest_ids = sorted(self._collect_ids(manifest["components"]))
        assert single_ids == manifest_ids

    def test_split_detail_file_count_matches_index(self, monkeypatch, temp_repo):
        """Number of detail files matches entries in component_detail_index."""
        out_dir = temp_repo / "count-check"
        monkeypatch.setattr("sys.argv", [
            "analyze", str(temp_repo), "--split", "-o", str(out_dir),
        ])
        main()

        manifest = json.loads((out_dir / "manifest.json").read_text())
        idx = manifest["component_detail_index"]
        detail_files = list((out_dir / "data").glob("detail-*.json"))
        assert len(detail_files) == len(idx)

    def test_cli_prints_stats_summary(self, monkeypatch, temp_repo, capsys):
        """CLI prints analysis summary with component and file counts."""
        monkeypatch.setattr("sys.argv", ["analyze", str(temp_repo)])
        monkeypatch.chdir(temp_repo)
        main()

        captured = capsys.readouterr()
        assert "Analysis complete" in captured.out
        assert "Components:" in captured.out
        assert "Files:" in captured.out
        assert "Output:" in captured.out

    @staticmethod
    def _collect_ids(components):
        """Recursively collect all component IDs from a component tree."""
        ids = []
        for comp in components:
            ids.append(comp["id"])
            ids.extend(TestCLIIntegration._collect_ids(comp.get("children", [])))
        return ids


# ---------------------------------------------------------------------------
# Truncation and skip warnings (F-AN-3 / P1-2)
# ---------------------------------------------------------------------------


def _multi_symbol_repo(tmp_path):
    """Create a repo whose single source file defines several top-level symbols."""
    (tmp_path / "package.json").write_text(json.dumps({"name": "trunc-test"}))
    src = tmp_path / "src"
    src.mkdir()
    (src / "lib.ts").write_text(
        "export function alpha(): number { return 1; }\n"
        "export function bravo(): number { return 2; }\n"
        "export function charlie(): number { return 3; }\n"
        "export function delta(): number { return 4; }\n"
        "export function echo(): number { return 5; }\n"
        "export function foxtrot(): number { return 6; }\n"
    )
    return tmp_path


class TestTruncationWarnings:
    """Single-file mode must warn loudly when it drops data, and its stats
    must agree with the emitted symbol array (F-AN-3).

    These are v1-engine (legacy) behaviors: the symbol cap and the oversized-file
    skip are v1-only, so every test here pins --engine v1. v2 is uncapped and
    accounts for every file in the coverage ledger instead of truncating.
    """

    def test_symbol_cap_warns_and_stats_match_array(self, monkeypatch, tmp_path, capsys):
        _multi_symbol_repo(tmp_path)
        out = tmp_path / "out.json"
        monkeypatch.setattr("sys.argv", [
            "analyze", str(tmp_path), "--engine", "v1",
            "--max-symbols", "2", "-o", str(out),
        ])
        main()

        captured = capsys.readouterr()
        # A prominent stderr warning names the dropped count and the flag that lifts the cap.
        assert "WARNING" in captured.err
        assert "symbol cap" in captured.err
        assert "--max-symbols" in captured.err

        data = json.loads(out.read_text())
        stats = data["stats"]
        # total_symbols equals the emitted array length; no disagreement with the data.
        assert stats["total_symbols"] == len(data["symbols"])
        assert stats["total_symbols"] == 2
        # The pre-truncation count is exposed separately and is larger.
        assert stats["total_symbols_detected"] > stats["total_symbols"]

    def test_no_warning_when_nothing_truncated(self, monkeypatch, tmp_path, capsys):
        _multi_symbol_repo(tmp_path)
        out = tmp_path / "out.json"
        monkeypatch.setattr("sys.argv", [
            "analyze", str(tmp_path), "--engine", "v1",
            "--max-symbols", "0", "-o", str(out),
        ])
        main()

        captured = capsys.readouterr()
        assert "symbol cap" not in captured.err
        data = json.loads(out.read_text())
        stats = data["stats"]
        assert stats["total_symbols"] == len(data["symbols"])
        assert stats["total_symbols_detected"] == stats["total_symbols"]

    def test_max_file_size_skip_warns(self, monkeypatch, tmp_path, capsys):
        (tmp_path / "package.json").write_text(json.dumps({"name": "big-file-test"}))
        src = tmp_path / "src"
        src.mkdir()
        # A valid but large source file that exceeds the tiny --max-file-size below.
        big = "export function keep(): number { return 0; }\n" + ("// pad\n" * 5000)
        (src / "big.ts").write_text(big)
        out = tmp_path / "out.json"
        monkeypatch.setattr("sys.argv", [
            "analyze", str(tmp_path), "--engine", "v1",
            "--max-file-size", "1000", "-o", str(out),
        ])
        main()

        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "skipped" in captured.err
        assert "--max-file-size" in captured.err
        assert "big.ts" in captured.err


# ---------------------------------------------------------------------------
# --max-file-size default semantics per engine (I2: v2 is unbounded by default)
# ---------------------------------------------------------------------------


def _repo_with_large_file(tmp_path, size_bytes=600_000):
    """A repo with one valid source file larger than the legacy v1 500KB default.

    The file defines a top-level symbol (``keep``) so a "was it analyzed?" check
    can look for the symbol as well as the coverage disposition.
    """
    (tmp_path / "package.json").write_text(json.dumps({"name": "big-cov-test"}))
    src = tmp_path / "src"
    src.mkdir()
    pad = "# pad line to grow the file past the legacy 500KB default\n"
    body = "def keep():\n    return 0\n" + pad * ((size_bytes // len(pad)) + 1)
    big = src / "big.py"
    big.write_text(body)
    assert big.stat().st_size > 500_000
    return tmp_path


class TestMaxFileSizeDefaultPerEngine:
    """The v2 engine analyzes 100 percent of source by default; any bound is an
    explicit opt-in exception, never a silent default (TARGET-ARCHITECTURE 4.1,
    invariant I2). The legacy v1 engine keeps its historical 500KB default.
    """

    def test_v2_default_parses_file_over_500kb(self, monkeypatch, tmp_path):
        # v2 is the DEFAULT engine. With no --max-file-size, a file larger than
        # the old 500KB default must be PARSED (unbounded), landing a `parsed`
        # coverage row. Fail-before: the pre-fix argparse default of 500_000 was
        # forwarded into the v2 path, excluding this file as excluded:max_file_size.
        _repo_with_large_file(tmp_path)
        out = tmp_path / "out.json"
        monkeypatch.setattr("sys.argv", ["analyze", str(tmp_path), "-o", str(out)])
        main()

        data = json.loads(out.read_text())
        rows = {r["path"]: r for r in data["coverage"]["rows"]}
        assert "src/big.py" in rows, "the large file must appear in the coverage ledger"
        assert rows["src/big.py"]["disposition"] == "parsed", (
            "v2 must parse the >500KB file by default (100 percent coverage), "
            f"got {rows['src/big.py']['disposition']!r}"
        )
        # No excluded:max_file_size disposition anywhere on a default v2 run.
        assert all(
            r["disposition"] != "excluded:max_file_size" for r in data["coverage"]["rows"]
        ), "a default v2 run must not exclude anything for size"

    def test_v1_default_still_excludes_file_over_500kb(self, monkeypatch, tmp_path, capsys):
        # v1 keeps its legacy 500KB default byte-for-byte: the >500KB file is
        # skipped and the loud stderr warning names the historical byte limit.
        _repo_with_large_file(tmp_path)
        out = tmp_path / "out.json"
        monkeypatch.setattr("sys.argv", [
            "analyze", str(tmp_path), "--engine", "v1", "-o", str(out),
        ])
        main()

        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "500,000 bytes" in captured.err, "v1 default bound is the historical 500KB"
        assert "big.py" in captured.err
        data = json.loads(out.read_text())
        assert not any(
            s.get("name") == "keep" for s in data.get("symbols", [])
        ), "v1 must not emit symbols from the skipped oversized file"

    def test_v2_explicit_max_file_size_excludes_with_ledger_row(self, monkeypatch, tmp_path):
        # An explicit --max-file-size is honored on v2 and lands as a visible
        # excluded:max_file_size ledger row carrying the byte bound as its reason
        # (opt-in exception, never silent).
        _repo_with_large_file(tmp_path)
        out = tmp_path / "out.json"
        monkeypatch.setattr("sys.argv", [
            "analyze", str(tmp_path), "--max-file-size", "1000", "-o", str(out),
        ])
        main()

        data = json.loads(out.read_text())
        rows = {r["path"]: r for r in data["coverage"]["rows"]}
        assert rows["src/big.py"]["disposition"] == "excluded:max_file_size"
        assert rows["src/big.py"]["reason"] == "1000", (
            "the excluded row must carry the opt-in byte bound as its reason"
        )

    def test_v2_explicit_zero_is_a_real_bound_not_unbounded(self, monkeypatch, tmp_path):
        # An explicit --max-file-size 0 is a real bound (every non-empty file
        # excluded), matching the v1 engine. It must never be conflated with
        # "not provided" (unbounded). Fail-before: the pre-fix v2 path used a
        # truthiness check (`args.max_file_size if args.max_file_size else None`),
        # so 0 silently meant unbounded and this file parsed.
        _repo_with_large_file(tmp_path)
        out = tmp_path / "out.json"
        monkeypatch.setattr("sys.argv", [
            "analyze", str(tmp_path), "--max-file-size", "0", "-o", str(out),
        ])
        main()

        data = json.loads(out.read_text())
        rows = {r["path"]: r for r in data["coverage"]["rows"]}
        assert rows["src/big.py"]["disposition"] == "excluded:max_file_size"
        assert rows["src/big.py"]["reason"] == "0", (
            "the excluded row must carry the explicit zero bound as its reason"
        )
        assert all(
            r["disposition"] != "parsed" for r in data["coverage"]["rows"]
        ), "no non-empty file may parse under an explicit zero bound"


# ---------------------------------------------------------------------------
# P6-11: the v2 stdout coverage line speaks three-family semantics, matching the
# viewer badge, not a raw parsed/total ratio.
# ---------------------------------------------------------------------------

# The retired wording was "Coverage: 651/712 parsed". This pattern matches that
# old N/M form so the fail-before check can assert it is gone in both scenarios.
_OLD_COVERAGE_RE = re.compile(r"\d+/\d+\s+parsed")


def _coverage_line(stdout: str) -> str:
    """Return the single ``Coverage:`` summary line from a v2 run's stdout."""
    for raw in stdout.splitlines():
        if raw.strip().startswith("Coverage:"):
            return raw.strip()
    raise AssertionError(f"no Coverage line in output:\n{stdout}")


class TestCoverageLineLanguage:
    """The v2 run summary reports percent-of-source analyzed plus a gap count and
    a non-source-accounted count, so a repo full of assets never reads as low
    coverage and a single real gap never rounds up to a bare 100.
    """

    def test_full_coverage_reads_as_100_percent_of_source(
        self, monkeypatch, tmp_path, capsys
    ):
        # A repo whose source all parses, plus a non-source asset. Coverage reads
        # "100% of source analyzed (... 0 gaps); N non-source accounted for".
        (tmp_path / "package.json").write_text(json.dumps({"name": "cov-lang"}))
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("def keep():\n    return 0\n")
        (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n")
        out = tmp_path / "out.json"
        monkeypatch.setattr("sys.argv", ["analyze", str(tmp_path), "-o", str(out)])
        main()

        line = _coverage_line(capsys.readouterr().out)
        assert "100% of source analyzed" in line
        assert "0 gaps" in line
        assert "non-source files accounted for" in line
        # Fail-before: the retired "N/M parsed" wording must be gone.
        assert not _OLD_COVERAGE_RE.search(line), line

    def test_a_real_gap_is_not_rounded_up_to_100(
        self, monkeypatch, tmp_path, capsys
    ):
        # One oversized file excluded by an explicit bound is a source gap. The
        # percent must drop below 100 (never round up while a gap exists) and the
        # gap noun is singular for a single gap.
        _repo_with_large_file(tmp_path)
        (tmp_path / "src" / "small.py").write_text("def ok():\n    return 1\n")
        out = tmp_path / "out.json"
        monkeypatch.setattr("sys.argv", [
            "analyze", str(tmp_path), "--max-file-size", "1000", "-o", str(out),
        ])
        main()

        line = _coverage_line(capsys.readouterr().out)
        assert "1 gap" in line and "1 gaps" not in line
        assert "100% of source analyzed" not in line
        assert "of source analyzed" in line
        # Exactly one non-source file in this fixture: the noun must be singular
        # (review finding on this PR: "1 non-source accounted for" read wrong).
        assert "1 non-source file accounted for" in line
        assert "non-source files" not in line
        assert not _OLD_COVERAGE_RE.search(line), line
