"""Tests for analyzer utility functions and config parsers."""

import json
import plistlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from analyzer.config_parsers import (
    _extract_ruby_app_name,
    parse_cargo_toml,
    parse_docker_compose,
    parse_gemfile,
    parse_info_plist,
    parse_package_json,
    parse_pyproject_toml,
    parse_sam_template,
    parse_serverless_yml,
)
from analyzer.utils import (
    _extract_brace_body,
    _framework_priority,
    _is_conditional_import,
    _is_vendored_repo,
    _name_from_server_script,
    _should_skip_dir,
)

# ---------------------------------------------------------------------------
# _should_skip_dir
# ---------------------------------------------------------------------------

class TestShouldSkipDir:
    """Tests for _should_skip_dir."""

    @pytest.mark.parametrize("dirname", [
        "node_modules", ".git", "__pycache__", "build", "dist",
        "DerivedData", "Pods", "vendor", "coverage", "venv",
        ".mypy_cache", ".pytest_cache", ".ruff_cache", "target",
        ".next", ".nuxt", ".output", ".vercel", ".turbo",
        ".swiftpm", ".sass-cache", ".gradle", ".idea", ".vscode",
        ".venv", "env", ".tox", "egg-info", ".eggs", ".cache",
        ".build", "htmlcov",
    ])
    def test_known_skip_dirs(self, dirname):
        """Every entry in SKIP_DIRS should be skipped."""
        assert _should_skip_dir(dirname) is True

    @pytest.mark.parametrize("dirname", [
        ".hidden", ".secret", ".config", ".env_stuff",
    ])
    def test_dot_prefixed_dirs_skipped(self, dirname):
        """Directories starting with '.' should be skipped."""
        assert _should_skip_dir(dirname) is True

    @pytest.mark.parametrize("dirname,suffix", [
        ("Foo.xcframework", ".xcframework"),
        ("Bar.framework", ".framework"),
        ("MyApp.dSYM", ".dSYM"),
    ])
    def test_framework_suffix_skipped(self, dirname, suffix):
        """Directories ending with SKIP_DIR_SUFFIXES should be skipped."""
        assert _should_skip_dir(dirname) is True

    @pytest.mark.parametrize("dirname", [
        "src", "lib", "app", "features", "components", "utils",
        "my_module", "server", "tests",
    ])
    def test_normal_dirs_not_skipped(self, dirname):
        """Regular project directories should not be skipped."""
        assert _should_skip_dir(dirname) is False

    def test_similar_name_not_in_skip_dirs(self):
        """A name that resembles but is not in SKIP_DIRS should pass."""
        assert _should_skip_dir("node_modules2") is False
        assert _should_skip_dir("builds") is False

    def test_case_sensitive(self):
        """Skip-dir matching is case-sensitive."""
        assert _should_skip_dir("Node_modules") is False
        assert _should_skip_dir("BUILD") is False


# ---------------------------------------------------------------------------
# _is_vendored_repo
# ---------------------------------------------------------------------------

class TestIsVendoredRepo:
    """Tests for _is_vendored_repo."""

    def _make_vendored(self, tmp_path, build_file="Makefile", license_name="LICENSE"):
        """Helper: create a directory that looks like a vendored repo."""
        (tmp_path / build_file).write_text("all:\n\tbuild")
        (tmp_path / license_name).write_text("MIT License")
        for i in range(6):
            (tmp_path / f"subdir_{i}").mkdir()

    def test_vendored_with_makefile_and_license(self, tmp_path):
        """Dir with Makefile + LICENSE + 5+ subdirs is vendored."""
        self._make_vendored(tmp_path)
        assert _is_vendored_repo(str(tmp_path)) is True

    def test_vendored_with_cmake_and_license(self, tmp_path):
        """Dir with CMakeLists.txt + LICENSE + 5+ subdirs is vendored."""
        self._make_vendored(tmp_path, build_file="CMakeLists.txt")
        assert _is_vendored_repo(str(tmp_path)) is True

    def test_vendored_with_license_md(self, tmp_path):
        """Dir with Makefile + LICENSE.md + 5+ subdirs is vendored."""
        self._make_vendored(tmp_path, license_name="LICENSE.md")
        assert _is_vendored_repo(str(tmp_path)) is True

    def test_not_vendored_without_license(self, tmp_path):
        """Dir with Makefile but no LICENSE is not vendored."""
        (tmp_path / "Makefile").write_text("all:")
        for i in range(6):
            (tmp_path / f"subdir_{i}").mkdir()
        assert _is_vendored_repo(str(tmp_path)) is False

    def test_not_vendored_without_build_system(self, tmp_path):
        """Dir with LICENSE but no build file is not vendored."""
        (tmp_path / "LICENSE").write_text("MIT")
        for i in range(6):
            (tmp_path / f"subdir_{i}").mkdir()
        assert _is_vendored_repo(str(tmp_path)) is False

    def test_not_vendored_too_few_subdirs(self, tmp_path):
        """Dir with Makefile + LICENSE but fewer than 5 subdirs is not vendored."""
        (tmp_path / "Makefile").write_text("all:")
        (tmp_path / "LICENSE").write_text("MIT")
        for i in range(4):
            (tmp_path / f"subdir_{i}").mkdir()
        assert _is_vendored_repo(str(tmp_path)) is False

    def test_skip_dirs_not_counted(self, tmp_path):
        """Subdirs that match SKIP_DIRS should not count toward the threshold."""
        (tmp_path / "Makefile").write_text("all:")
        (tmp_path / "LICENSE").write_text("MIT")
        # Create 4 real subdirs (not enough) + skip-dirs
        for i in range(4):
            (tmp_path / f"subdir_{i}").mkdir()
        for skip_name in ["node_modules", ".git", "build"]:
            (tmp_path / skip_name).mkdir()
        assert _is_vendored_repo(str(tmp_path)) is False

    def test_empty_directory(self, tmp_path):
        """An empty directory is not vendored."""
        assert _is_vendored_repo(str(tmp_path)) is False


# ---------------------------------------------------------------------------
# _is_conditional_import
# ---------------------------------------------------------------------------

class TestIsConditionalImport:
    """Tests for _is_conditional_import."""

    def test_unconditional_import(self):
        """Import outside any #if block is unconditional."""
        content = "import UIKit\nimport Foundation\n"
        assert _is_conditional_import(content, "UIKit") is False

    def test_conditional_import(self):
        """Import inside #if block is conditional."""
        content = (
            "#if canImport(UIKit)\n"
            "import UIKit\n"
            "#endif\n"
        )
        assert _is_conditional_import(content, "UIKit") is True

    def test_nested_conditional(self):
        """Import inside nested #if blocks is conditional."""
        content = (
            "#if os(iOS)\n"
            "#if canImport(UIKit)\n"
            "import UIKit\n"
            "#endif\n"
            "#endif\n"
        )
        assert _is_conditional_import(content, "UIKit") is True

    def test_mixed_conditional_and_unconditional(self):
        """One unconditional import makes the whole thing unconditional."""
        content = (
            "#if canImport(UIKit)\n"
            "import UIKit\n"
            "#endif\n"
            "import UIKit\n"
        )
        assert _is_conditional_import(content, "UIKit") is False

    def test_framework_not_imported_at_all(self):
        """If the framework is never imported, returns True (vacuously true)."""
        content = "import Foundation\nimport SwiftUI\n"
        assert _is_conditional_import(content, "UIKit") is True

    def test_different_framework_unconditional(self):
        """A different framework's unconditional import doesn't affect the target."""
        content = (
            "import Foundation\n"
            "#if canImport(UIKit)\n"
            "import UIKit\n"
            "#endif\n"
        )
        assert _is_conditional_import(content, "UIKit") is True
        assert _is_conditional_import(content, "Foundation") is False

    def test_empty_content(self):
        """Empty content is vacuously True."""
        assert _is_conditional_import("", "UIKit") is True

    def test_endif_without_matching_if(self):
        """Unmatched #endif should not underflow the counter."""
        content = (
            "#endif\n"
            "import UIKit\n"
        )
        # The #endif decrements to 0 (clamped), then import at depth 0 is unconditional
        assert _is_conditional_import(content, "UIKit") is False


# ---------------------------------------------------------------------------
# _framework_priority
# ---------------------------------------------------------------------------

class TestFrameworkPriority:
    """Tests for _framework_priority."""

    def test_known_frameworks(self):
        """Known frameworks return their configured priority."""
        assert _framework_priority("SwiftUI") == 1
        assert _framework_priority("UIKit") == 2
        assert _framework_priority("Vapor") == 3
        assert _framework_priority("Next.js") == 2
        assert _framework_priority("Django") == 2
        assert _framework_priority("Gin") == 3
        assert _framework_priority("Rails") == 3

    def test_unknown_framework(self):
        """Unknown frameworks default to priority 1."""
        assert _framework_priority("UnknownFramework") == 1
        assert _framework_priority("") == 1

    def test_case_sensitive(self):
        """Priority lookup is case-sensitive."""
        assert _framework_priority("swiftui") == 1  # not in dict
        assert _framework_priority("DJANGO") == 1   # not in dict


# ---------------------------------------------------------------------------
# _name_from_server_script
# ---------------------------------------------------------------------------

class TestNameFromServerScript:
    """Tests for _name_from_server_script."""

    def test_docstring_extraction(self):
        """Name extracted from module docstring."""
        content = '"""Remote Log Server"""\nimport http.server\n'
        assert _name_from_server_script("log_server.py", content) == "Remote Log Server"

    def test_single_quote_docstring(self):
        """Single-quoted docstrings are also handled."""
        content = "'''Auth Service'''\nimport flask\n"
        assert _name_from_server_script("auth.py", content) == "Auth Service"

    def test_prefix_stripping(self):
        """Known project prefixes are stripped from docstring names."""
        content = '"""UnaMentis Remote Log Server"""\n'
        result = _name_from_server_script("log_server.py", content)
        assert result == "Remote Log Server"

    def test_prefix_stripping_case_insensitive(self):
        """Prefix stripping works regardless of case in docstring."""
        content = '"""una-mentis Auth API"""\n'
        result = _name_from_server_script("auth.py", content)
        assert result == "Auth API"

    def test_trailing_qualifier_stripped(self):
        """Trailing qualifiers like 'with Web Interface' are stripped."""
        content = '"""Upload Service with Web Interface"""\n'
        result = _name_from_server_script("upload.py", content)
        assert result == "Upload Service"

    def test_trailing_for_stripped(self):
        """Trailing 'for XYZ' is stripped when core name is long enough."""
        content = '"""Analytics Server for Production"""\n'
        result = _name_from_server_script("analytics.py", content)
        assert result == "Analytics Server"

    def test_short_name_keeps_qualifier(self):
        """Qualifiers after very short names (<=5 chars) are kept."""
        content = '"""API for Production"""\n'
        result = _name_from_server_script("api.py", content)
        # "API" is only 3 chars before " for ", but idx=3 which is not > 5
        # so the separator is not found at idx > 5, keeps full string
        assert "API" in result

    def test_truncation(self):
        """Names longer than 30 characters are truncated at word boundary."""
        content = '"""Very Long Service Name That Goes On And On Forever"""\n'
        result = _name_from_server_script("long.py", content)
        assert len(result) <= 30

    def test_too_short_docstring_falls_back(self):
        """Docstring names 3 chars or shorter fall back to filename."""
        content = '"""OK"""\n'
        result = _name_from_server_script("my_server.py", content)
        assert result == "My Server"

    def test_filename_fallback(self):
        """Without a docstring, name comes from the filename."""
        content = "import flask\napp = flask.Flask(__name__)\n"
        assert _name_from_server_script("log_server.py", content) == "Log Server"

    def test_filename_with_dashes(self):
        """Dashes in filename are converted to spaces and title-cased."""
        content = "# no docstring\n"
        assert _name_from_server_script("my-api-service.py", content) == "My Api Service"

    def test_filename_strips_py_extension(self):
        """The .py extension is removed from the filename."""
        content = ""
        result = _name_from_server_script("worker.py", content)
        assert result == "Worker"

    def test_comments_before_docstring(self):
        """Hash comments before the docstring are handled."""
        content = '#!/usr/bin/env python\n# -*- coding: utf-8 -*-\n"""Data Pipeline"""\n'
        result = _name_from_server_script("pipeline.py", content)
        assert result == "Data Pipeline"

    def test_multiline_docstring_first_line(self):
        """Only the first line of a multiline docstring is used."""
        content = '"""Auth Service\n\nProvides authentication and authorization.\n"""\n'
        result = _name_from_server_script("auth.py", content)
        assert result == "Auth Service"


# ---------------------------------------------------------------------------
# _extract_brace_body
# ---------------------------------------------------------------------------

class TestExtractBraceBody:
    """Tests for _extract_brace_body."""

    def test_simple_braces(self):
        """Extract a simple brace-delimited body."""
        content = "struct Foo { var x: Int }"
        result = _extract_brace_body(content, 0)
        assert result == "{ var x: Int }"

    def test_nested_braces(self):
        """Nested braces are correctly matched."""
        content = "func f() { if true { print() } }"
        result = _extract_brace_body(content, 0)
        assert result == "{ if true { print() } }"

    def test_deeply_nested(self):
        """Deeply nested braces are handled."""
        content = "a { b { c { d } } }"
        result = _extract_brace_body(content, 0)
        assert result == "{ b { c { d } } }"

    def test_start_at_brace(self):
        """When start points directly at the opening brace."""
        content = "{ body }"
        result = _extract_brace_body(content, 0)
        assert result == "{ body }"

    def test_start_before_brace(self):
        """When start is before the first brace."""
        content = "prefix { body }"
        result = _extract_brace_body(content, 0)
        assert result == "{ body }"

    def test_no_brace(self):
        """When there is no opening brace, returns empty string."""
        content = "no braces here"
        result = _extract_brace_body(content, 0)
        assert result == ""

    def test_unclosed_brace(self):
        """When braces are not closed, returns from opening brace to end."""
        content = "struct { var x"
        result = _extract_brace_body(content, 0)
        assert result == "{ var x"

    def test_start_offset(self):
        """Start offset skips earlier braces."""
        content = "{ first } { second }"
        result = _extract_brace_body(content, 10)
        assert result == "{ second }"

    def test_empty_braces(self):
        """Empty braces are handled."""
        content = "struct Empty {}"
        result = _extract_brace_body(content, 0)
        assert result == "{}"

    def test_multiline(self):
        """Multiline content is handled."""
        content = "struct Foo {\n    var x: Int\n    var y: Int\n}"
        result = _extract_brace_body(content, 0)
        assert result == "{\n    var x: Int\n    var y: Int\n}"


# ---------------------------------------------------------------------------
# parse_package_json
# ---------------------------------------------------------------------------

class TestParsePackageJson:
    """Tests for parse_package_json."""

    def test_full_package_json(self, tmp_path):
        """Parse a complete package.json with all fields."""
        pkg = {
            "name": "my-app",
            "description": "A test application",
            "version": "1.2.3",
            "dependencies": {"react": "^18.0.0", "axios": "^1.0.0"},
            "devDependencies": {"jest": "^29.0.0", "typescript": "^5.0.0"},
            "scripts": {"build": "tsc", "test": "jest"},
        }
        f = tmp_path / "package.json"
        f.write_text(json.dumps(pkg))
        result = parse_package_json(f)
        assert result["name"] == "my-app"
        assert result["description"] == "A test application"
        assert result["version"] == "1.2.3"
        assert sorted(result["dependencies"]) == ["axios", "jest", "react", "typescript"]
        assert sorted(result["scripts"]) == ["build", "test"]

    def test_minimal_package_json(self, tmp_path):
        """Parse a minimal package.json with only a name."""
        f = tmp_path / "package.json"
        f.write_text(json.dumps({"name": "minimal"}))
        result = parse_package_json(f)
        assert result["name"] == "minimal"
        assert result["dependencies"] == []
        assert result["scripts"] == []
        assert result["description"] == ""
        assert result["version"] == ""

    def test_no_name_falls_back_to_dirname(self, tmp_path):
        """When name field is missing, parent dir name is used."""
        f = tmp_path / "package.json"
        f.write_text(json.dumps({"version": "0.1.0"}))
        result = parse_package_json(f)
        assert result["name"] == tmp_path.name

    def test_malformed_json(self, tmp_path):
        """Malformed JSON returns empty dict."""
        f = tmp_path / "package.json"
        f.write_text("{not valid json!!!")
        result = parse_package_json(f)
        assert result == {}

    def test_empty_file(self, tmp_path):
        """Empty file returns empty dict (invalid JSON)."""
        f = tmp_path / "package.json"
        f.write_text("")
        result = parse_package_json(f)
        assert result == {}

    def test_nonexistent_file(self, tmp_path):
        """Nonexistent file returns empty dict."""
        f = tmp_path / "nonexistent.json"
        result = parse_package_json(f)
        assert result == {}

    def test_deps_are_sorted_and_deduplicated(self, tmp_path):
        """Dependencies from deps and devDeps are merged, sorted, deduplicated."""
        pkg = {
            "name": "test",
            "dependencies": {"zlib": "1.0", "alpha": "2.0"},
            "devDependencies": {"alpha": "2.0", "beta": "3.0"},
        }
        f = tmp_path / "package.json"
        f.write_text(json.dumps(pkg))
        result = parse_package_json(f)
        assert result["dependencies"] == ["alpha", "beta", "zlib"]


# ---------------------------------------------------------------------------
# parse_cargo_toml
# ---------------------------------------------------------------------------

class TestParseCargoToml:
    """Tests for parse_cargo_toml."""

    def test_basic_cargo_toml(self, tmp_path):
        """Parse a standard Cargo.toml with package name and deps."""
        content = (
            "[package]\n"
            'name = "my-crate"\n'
            'version = "0.1.0"\n'
            "\n"
            "[dependencies]\n"
            'serde = "1.0"\n'
            'tokio = { version = "1", features = ["full"] }\n'
        )
        f = tmp_path / "Cargo.toml"
        f.write_text(content)
        result = parse_cargo_toml(f)
        assert result["name"] == "my-crate"
        assert "serde" in result["dependencies"]
        assert "tokio" in result["dependencies"]

    def test_dev_dependencies(self, tmp_path):
        """Dev-dependencies section is also parsed."""
        content = (
            "[package]\n"
            'name = "test-crate"\n'
            "\n"
            "[dependencies]\n"
            'log = "0.4"\n'
            "\n"
            "[dev-dependencies]\n"
            'mockall = "0.11"\n'
        )
        f = tmp_path / "Cargo.toml"
        f.write_text(content)
        result = parse_cargo_toml(f)
        assert "log" in result["dependencies"]
        assert "mockall" in result["dependencies"]

    def test_workspace_deps(self, tmp_path):
        """Workspace dependencies section is parsed."""
        content = (
            "[package]\n"
            'name = "workspace-crate"\n'
            "\n"
            "[workspace.dependencies]\n"
            'anyhow = "1"\n'
            'thiserror = "1"\n'
        )
        f = tmp_path / "Cargo.toml"
        f.write_text(content)
        result = parse_cargo_toml(f)
        assert "anyhow" in result["dependencies"]
        assert "thiserror" in result["dependencies"]

    def test_no_package_section(self, tmp_path):
        """Cargo.toml without [package] section has empty name."""
        content = "[dependencies]\nserde = \"1\"\n"
        f = tmp_path / "Cargo.toml"
        f.write_text(content)
        result = parse_cargo_toml(f)
        assert result["name"] == ""
        assert "serde" in result["dependencies"]

    def test_empty_file(self, tmp_path):
        """Empty Cargo.toml returns defaults."""
        f = tmp_path / "Cargo.toml"
        f.write_text("")
        result = parse_cargo_toml(f)
        assert result["name"] == ""
        assert result["dependencies"] == []

    def test_nonexistent_file(self, tmp_path):
        """Nonexistent file returns empty dict."""
        f = tmp_path / "nonexistent.toml"
        result = parse_cargo_toml(f)
        assert result == {}

    def test_multiple_dependency_sections(self, tmp_path):
        """Multiple dependency sections are all captured."""
        content = (
            "[package]\n"
            'name = "multi"\n'
            "\n"
            "[dependencies]\n"
            'alpha = "1"\n'
            "\n"
            "[build-dependencies]\n"
            'cc = "1"\n'
            "\n"
            "[dev-dependencies]\n"
            'proptest = "1"\n'
        )
        f = tmp_path / "Cargo.toml"
        f.write_text(content)
        result = parse_cargo_toml(f)
        assert "alpha" in result["dependencies"]
        assert "cc" in result["dependencies"]
        assert "proptest" in result["dependencies"]


# ---------------------------------------------------------------------------
# parse_pyproject_toml
# ---------------------------------------------------------------------------

class TestParsePyprojectToml:
    """Tests for parse_pyproject_toml."""

    def test_basic_pyproject(self, tmp_path):
        """Parse a standard pyproject.toml."""
        content = (
            '[project]\n'
            'name = "my-project"\n'
            'dependencies = [\n'
            '    "flask>=2.0",\n'
            '    "sqlalchemy>=1.4",\n'
            ']\n'
        )
        f = tmp_path / "pyproject.toml"
        f.write_text(content)
        result = parse_pyproject_toml(f)
        assert result["name"] == "my-project"
        assert "flask" in result["dependencies"]
        assert "sqlalchemy" in result["dependencies"]

    def test_python_excluded(self, tmp_path):
        """The 'python' dependency is excluded from results."""
        content = (
            '[project]\n'
            'name = "test"\n'
            'requires-python = ">=3.8"\n'
            'dependencies = [\n'
            '    "python>=3.8",\n'
            '    "requests>=2.0",\n'
            ']\n'
        )
        f = tmp_path / "pyproject.toml"
        f.write_text(content)
        result = parse_pyproject_toml(f)
        assert "python" not in result["dependencies"]
        assert "requests" in result["dependencies"]

    def test_no_name(self, tmp_path):
        """pyproject.toml without name has empty name."""
        content = "[tool.black]\nline-length = 88\n"
        f = tmp_path / "pyproject.toml"
        f.write_text(content)
        result = parse_pyproject_toml(f)
        assert result["name"] == ""

    def test_empty_file(self, tmp_path):
        """Empty file returns defaults."""
        f = tmp_path / "pyproject.toml"
        f.write_text("")
        result = parse_pyproject_toml(f)
        assert result["name"] == ""
        assert result["dependencies"] == []

    def test_nonexistent_file(self, tmp_path):
        """Nonexistent file returns empty dict."""
        f = tmp_path / "nonexistent.toml"
        result = parse_pyproject_toml(f)
        assert result == {}


# ---------------------------------------------------------------------------
# parse_info_plist
# ---------------------------------------------------------------------------

class TestParseInfoPlist:
    """Tests for parse_info_plist."""

    def _write_plist(self, path, data):
        """Write a binary plist file."""
        with open(path, "wb") as f:
            plistlib.dump(data, f)

    def test_display_name(self, tmp_path):
        """CFBundleDisplayName is preferred for name."""
        f = tmp_path / "Info.plist"
        self._write_plist(f, {
            "CFBundleDisplayName": "My App",
            "CFBundleName": "MyApp",
            "CFBundleIdentifier": "com.example.myapp",
        })
        result = parse_info_plist(f)
        assert result["name"] == "My App"
        assert result["bundle_id"] == "com.example.myapp"

    def test_bundle_name_fallback(self, tmp_path):
        """CFBundleName is used when CFBundleDisplayName is absent."""
        f = tmp_path / "Info.plist"
        self._write_plist(f, {
            "CFBundleName": "FallbackName",
            "CFBundleIdentifier": "com.example.fb",
        })
        result = parse_info_plist(f)
        assert result["name"] == "FallbackName"

    def test_variable_placeholder_rejected(self, tmp_path):
        """Build-time variable placeholders like $(PRODUCT_NAME) are rejected."""
        f = tmp_path / "Info.plist"
        self._write_plist(f, {
            "CFBundleDisplayName": "$(PRODUCT_NAME)",
            "CFBundleIdentifier": "com.example.app",
        })
        result = parse_info_plist(f)
        assert result["name"] == ""

    def test_variable_placeholder_curly(self, tmp_path):
        """Build-time placeholders with ${...} are also rejected."""
        f = tmp_path / "Info.plist"
        self._write_plist(f, {
            "CFBundleName": "${PRODUCT_NAME}",
            "CFBundleIdentifier": "com.example.app",
        })
        result = parse_info_plist(f)
        assert result["name"] == ""

    def test_no_name_fields(self, tmp_path):
        """Plist without name fields returns empty name."""
        f = tmp_path / "Info.plist"
        self._write_plist(f, {
            "CFBundleIdentifier": "com.example.noname",
        })
        result = parse_info_plist(f)
        assert result["name"] == ""
        assert result["bundle_id"] == "com.example.noname"

    def test_invalid_plist(self, tmp_path):
        """Invalid plist file returns empty dict."""
        f = tmp_path / "Info.plist"
        f.write_text("this is not a plist")
        result = parse_info_plist(f)
        assert result == {}

    def test_nonexistent_file(self, tmp_path):
        """Nonexistent plist returns empty dict."""
        f = tmp_path / "nonexistent.plist"
        result = parse_info_plist(f)
        assert result == {}


# ---------------------------------------------------------------------------
# _extract_ruby_app_name
# ---------------------------------------------------------------------------

class TestExtractRubyAppName:
    """Tests for _extract_ruby_app_name."""

    def test_rails_application_rb(self, tmp_path):
        """Extract name from Rails config/application.rb."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "application.rb").write_text(
            "require_relative 'boot'\n"
            "module MyRailsApp\n"
            "  class Application < Rails::Application\n"
            "  end\n"
            "end\n"
        )
        result = _extract_ruby_app_name(tmp_path)
        assert result == "My Rails App"

    def test_config_ru(self, tmp_path):
        """Extract name from config.ru (Rack convention)."""
        (tmp_path / "config.ru").write_text(
            "require ::File.expand_path('../config/environment', __FILE__)\n"
            "run BlogEngine::Application\n"
        )
        result = _extract_ruby_app_name(tmp_path)
        assert result == "Blog Engine"

    def test_rakefile(self, tmp_path):
        """Extract name from Rakefile."""
        (tmp_path / "Rakefile").write_text(
            "require_relative 'config/application'\n"
            "ShopFront::Application.load_tasks\n"
        )
        result = _extract_ruby_app_name(tmp_path)
        assert result == "Shop Front"

    def test_priority_order(self, tmp_path):
        """config/application.rb takes priority over config.ru and Rakefile."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "application.rb").write_text("module PrimaryApp\nend\n")
        (tmp_path / "config.ru").write_text("run SecondaryApp::Application\n")
        (tmp_path / "Rakefile").write_text("TertiaryApp::Application.load_tasks\n")
        result = _extract_ruby_app_name(tmp_path)
        assert result == "Primary App"

    def test_no_ruby_files(self, tmp_path):
        """Returns empty string when no Ruby app files exist."""
        result = _extract_ruby_app_name(tmp_path)
        assert result == ""

    def test_camel_case_splitting(self, tmp_path):
        """CamelCase module names are split into words."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "application.rb").write_text("module MyBigAppName\nend\n")
        result = _extract_ruby_app_name(tmp_path)
        assert result == "My Big App Name"


# ---------------------------------------------------------------------------
# parse_gemfile
# ---------------------------------------------------------------------------

class TestParseGemfile:
    """Tests for parse_gemfile."""

    def test_basic_gemfile(self, tmp_path):
        """Parse a Gemfile with multiple gems."""
        f = tmp_path / "Gemfile"
        f.write_text(
            "source 'https://rubygems.org'\n"
            "gem 'rails', '~> 7.0'\n"
            "gem 'puma'\n"
            'gem "pg"\n'
        )
        result = parse_gemfile(f)
        assert "rails" in result["dependencies"]
        assert "puma" in result["dependencies"]
        assert "pg" in result["dependencies"]

    def test_gemfile_with_rails_app_name(self, tmp_path):
        """Gemfile extracts app name from config/application.rb."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "application.rb").write_text("module TestApp\nend\n")
        f = tmp_path / "Gemfile"
        f.write_text("gem 'rails'\n")
        result = parse_gemfile(f)
        assert result["name"] == "Test App"
        assert "rails" in result["dependencies"]

    def test_empty_gemfile(self, tmp_path):
        """Empty Gemfile returns empty deps and no app name."""
        f = tmp_path / "Gemfile"
        f.write_text("")
        result = parse_gemfile(f)
        assert result["dependencies"] == []
        assert result["name"] == ""

    def test_nonexistent_file(self, tmp_path):
        """Nonexistent Gemfile returns empty dict."""
        f = tmp_path / "nonexistent_Gemfile"
        result = parse_gemfile(f)
        assert result == {}


# ---------------------------------------------------------------------------
# parse_docker_compose
# ---------------------------------------------------------------------------

class TestParseDockerCompose:
    """Tests for parse_docker_compose."""

    def test_multiple_services(self, tmp_path):
        """Parse docker-compose with multiple services and ports."""
        content = (
            "version: '3'\n"
            "services:\n"
            "  web:\n"
            "    build: .\n"
            "    ports:\n"
            "      - 8080:80\n"
            "      - 8443:443\n"
            "  db:\n"
            "    image: postgres:15\n"
            "    ports:\n"
            "      - 5432:5432\n"
            "  redis:\n"
            "    image: redis:7\n"
        )
        f = tmp_path / "docker-compose.yml"
        f.write_text(content)
        result = parse_docker_compose(f)
        assert result["services"] == ["web", "db", "redis"]
        assert len(result["ports"]) == 3
        assert result["ports"][0] == {"service": "web", "host": 8080, "container": 80}
        assert result["ports"][1] == {"service": "web", "host": 8443, "container": 443}
        assert result["ports"][2] == {"service": "db", "host": 5432, "container": 5432}

    def test_no_ports(self, tmp_path):
        """Services without ports are still listed."""
        content = (
            "services:\n"
            "  worker:\n"
            "    build: ./worker\n"
        )
        f = tmp_path / "docker-compose.yml"
        f.write_text(content)
        result = parse_docker_compose(f)
        assert result["services"] == ["worker"]
        assert result["ports"] == []

    def test_empty_file(self, tmp_path):
        """Empty file returns empty services and ports."""
        f = tmp_path / "docker-compose.yml"
        f.write_text("")
        result = parse_docker_compose(f)
        assert result["services"] == []
        assert result["ports"] == []

    def test_nonexistent_file(self, tmp_path):
        """Nonexistent file returns empty dict."""
        f = tmp_path / "nonexistent.yml"
        result = parse_docker_compose(f)
        assert result == {}

    def test_services_section_ends_at_new_top_level(self, tmp_path):
        """Services section ends when a new top-level key appears."""
        content = (
            "services:\n"
            "  app:\n"
            "    build: .\n"
            "volumes:\n"
            "  data:\n"
        )
        f = tmp_path / "docker-compose.yml"
        f.write_text(content)
        result = parse_docker_compose(f)
        assert result["services"] == ["app"]

    def test_quoted_ports(self, tmp_path):
        """Port mappings with quotes are parsed."""
        content = (
            "services:\n"
            "  api:\n"
            "    ports:\n"
            '      - "3000:3000"\n'
        )
        f = tmp_path / "docker-compose.yml"
        f.write_text(content)
        result = parse_docker_compose(f)
        assert result["ports"] == [{"service": "api", "host": 3000, "container": 3000}]


# ---------------------------------------------------------------------------
# parse_sam_template
# ---------------------------------------------------------------------------

class TestParseSamTemplate:
    """Tests for parse_sam_template."""

    def test_single_function(self, tmp_path):
        """Parse a SAM template with a single Lambda function."""
        content = (
            "AWSTemplateFormatVersion: '2010-09-09'\n"
            "Transform: AWS::Serverless-2016-10-31\n"
            "Resources:\n"
            "  HelloFunction:\n"
            "    Type: AWS::Serverless::Function\n"
            "    Properties:\n"
            "      Handler: app.handler\n"
            "      Runtime: python3.9\n"
            "      CodeUri: hello/\n"
        )
        f = tmp_path / "template.yaml"
        f.write_text(content)
        result = parse_sam_template(f)
        assert len(result["functions"]) == 1
        fn = result["functions"][0]
        assert fn["name"] == "HelloFunction"
        assert fn["handler"] == "app.handler"
        assert fn["runtime"] == "python3.9"
        assert fn["code_uri"] == "hello/"
        assert result["type"] == "sam"

    def test_multiple_functions(self, tmp_path):
        """Parse a SAM template with multiple Lambda functions."""
        content = (
            "Resources:\n"
            "  GetItems:\n"
            "    Type: AWS::Serverless::Function\n"
            "    Properties:\n"
            "      Handler: get.handler\n"
            "      Runtime: nodejs18.x\n"
            "      CodeUri: src/get/\n"
            "  PutItems:\n"
            "    Type: AWS::Serverless::Function\n"
            "    Properties:\n"
            "      Handler: put.handler\n"
            "      Runtime: nodejs18.x\n"
            "      CodeUri: src/put/\n"
        )
        f = tmp_path / "template.yaml"
        f.write_text(content)
        result = parse_sam_template(f)
        assert len(result["functions"]) == 2
        names = [fn["name"] for fn in result["functions"]]
        assert "GetItems" in names
        assert "PutItems" in names

    def test_api_gateway_detection(self, tmp_path):
        """API Gateway resources are detected."""
        content = (
            "Resources:\n"
            "  ApiGateway:\n"
            "    Type: AWS::Serverless::Api\n"
            "    Properties:\n"
            "      StageName: prod\n"
            "  MyFunc:\n"
            "    Type: AWS::Serverless::Function\n"
            "    Properties:\n"
            "      Handler: index.handler\n"
            "      Runtime: python3.9\n"
        )
        f = tmp_path / "template.yaml"
        f.write_text(content)
        result = parse_sam_template(f)
        assert result["has_api_gateway"] is True

    def test_no_api_gateway(self, tmp_path):
        """Template without API Gateway resource."""
        content = (
            "Resources:\n"
            "  MyFunc:\n"
            "    Type: AWS::Serverless::Function\n"
            "    Properties:\n"
            "      Handler: index.handler\n"
            "      Runtime: python3.9\n"
        )
        f = tmp_path / "template.yaml"
        f.write_text(content)
        result = parse_sam_template(f)
        assert result["has_api_gateway"] is False

    def test_non_function_resources_ignored(self, tmp_path):
        """Non-function resources (e.g., DynamoDB table) are not in functions list."""
        content = (
            "Resources:\n"
            "  ItemsTable:\n"
            "    Type: AWS::DynamoDB::Table\n"
            "    Properties:\n"
            "      TableName: items\n"
            "  MyFunc:\n"
            "    Type: AWS::Serverless::Function\n"
            "    Properties:\n"
            "      Handler: app.handler\n"
            "      Runtime: python3.9\n"
        )
        f = tmp_path / "template.yaml"
        f.write_text(content)
        result = parse_sam_template(f)
        assert len(result["functions"]) == 1
        assert result["functions"][0]["name"] == "MyFunc"

    def test_empty_file(self, tmp_path):
        """Empty SAM template returns empty functions."""
        f = tmp_path / "template.yaml"
        f.write_text("")
        result = parse_sam_template(f)
        assert result["functions"] == []
        assert result["has_api_gateway"] is False

    def test_nonexistent_file(self, tmp_path):
        """Nonexistent file returns empty dict."""
        f = tmp_path / "nonexistent.yaml"
        result = parse_sam_template(f)
        assert result == {}

    def test_comments_and_blank_lines(self, tmp_path):
        """Comments and blank lines are skipped."""
        content = (
            "# This is a comment\n"
            "\n"
            "Resources:\n"
            "  # Another comment\n"
            "\n"
            "  MyFunc:\n"
            "    Type: AWS::Serverless::Function\n"
            "    Properties:\n"
            "      Handler: main.handler\n"
            "      Runtime: go1.x\n"
        )
        f = tmp_path / "template.yaml"
        f.write_text(content)
        result = parse_sam_template(f)
        assert len(result["functions"]) == 1

    def test_function_missing_optional_fields(self, tmp_path):
        """Function with missing handler/runtime/codeuri defaults to empty string."""
        content = (
            "Resources:\n"
            "  MinimalFunc:\n"
            "    Type: AWS::Serverless::Function\n"
        )
        f = tmp_path / "template.yaml"
        f.write_text(content)
        result = parse_sam_template(f)
        assert len(result["functions"]) == 1
        fn = result["functions"][0]
        assert fn["name"] == "MinimalFunc"
        assert fn["handler"] == ""
        assert fn["runtime"] == ""
        assert fn["code_uri"] == ""

    def test_resources_section_ends_at_new_top_level(self, tmp_path):
        """Resources section ends when a new top-level key appears."""
        content = (
            "Resources:\n"
            "  MyFunc:\n"
            "    Type: AWS::Serverless::Function\n"
            "    Properties:\n"
            "      Handler: app.handler\n"
            "      Runtime: python3.9\n"
            "Outputs:\n"
            "  ApiUrl:\n"
            "    Value: !Sub https://example.com\n"
        )
        f = tmp_path / "template.yaml"
        f.write_text(content)
        result = parse_sam_template(f)
        assert len(result["functions"]) == 1


# ---------------------------------------------------------------------------
# parse_serverless_yml
# ---------------------------------------------------------------------------

class TestParseServerlessYml:
    """Tests for parse_serverless_yml."""

    def test_basic_serverless(self, tmp_path):
        """Parse a basic serverless.yml with functions and provider."""
        content = (
            "service: my-service\n"
            "provider:\n"
            "  name: aws\n"
            "  runtime: nodejs18.x\n"
            "functions:\n"
            "  hello:\n"
            "    handler: handler.hello\n"
            "  goodbye:\n"
            "    handler: handler.goodbye\n"
        )
        f = tmp_path / "serverless.yml"
        f.write_text(content)
        result = parse_serverless_yml(f)
        assert result["provider"] == "aws"
        assert len(result["functions"]) == 2
        names = [fn["name"] for fn in result["functions"]]
        assert "hello" in names
        assert "goodbye" in names
        assert result["type"] == "serverless"

    def test_no_provider(self, tmp_path):
        """Serverless file without provider returns empty string."""
        content = (
            "functions:\n"
            "  myFunc:\n"
            "    handler: index.handler\n"
        )
        f = tmp_path / "serverless.yml"
        f.write_text(content)
        result = parse_serverless_yml(f)
        assert result["provider"] == ""
        assert len(result["functions"]) == 1

    def test_no_functions(self, tmp_path):
        """Serverless file without functions section returns empty list."""
        content = (
            "service: my-service\n"
            "provider:\n"
            "  name: gcp\n"
        )
        f = tmp_path / "serverless.yml"
        f.write_text(content)
        result = parse_serverless_yml(f)
        assert result["functions"] == []
        assert result["provider"] == "gcp"

    def test_functions_section_ends_at_new_top_level(self, tmp_path):
        """Functions section ends when a new top-level key appears."""
        content = (
            "functions:\n"
            "  alpha:\n"
            "    handler: alpha.handler\n"
            "resources:\n"
            "  Resources:\n"
            "    MyTable:\n"
            "      Type: AWS::DynamoDB::Table\n"
        )
        f = tmp_path / "serverless.yml"
        f.write_text(content)
        result = parse_serverless_yml(f)
        assert len(result["functions"]) == 1
        assert result["functions"][0]["name"] == "alpha"

    def test_empty_file(self, tmp_path):
        """Empty serverless file returns empty functions and provider."""
        f = tmp_path / "serverless.yml"
        f.write_text("")
        result = parse_serverless_yml(f)
        assert result["functions"] == []
        assert result["provider"] == ""

    def test_nonexistent_file(self, tmp_path):
        """Nonexistent file returns empty dict."""
        f = tmp_path / "nonexistent.yml"
        result = parse_serverless_yml(f)
        assert result == {}

    def test_multiple_functions(self, tmp_path):
        """Parse serverless.yml with many functions."""
        content = (
            "provider:\n"
            "  name: aws\n"
            "functions:\n"
            "  createUser:\n"
            "    handler: create.handler\n"
            "  getUser:\n"
            "    handler: get.handler\n"
            "  updateUser:\n"
            "    handler: update.handler\n"
            "  deleteUser:\n"
            "    handler: delete.handler\n"
        )
        f = tmp_path / "serverless.yml"
        f.write_text(content)
        result = parse_serverless_yml(f)
        assert len(result["functions"]) == 4
        names = [fn["name"] for fn in result["functions"]]
        assert names == ["createUser", "getUser", "updateUser", "deleteUser"]
