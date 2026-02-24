"""Tests for test coverage detection in the ArchitectureScanner."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from analyzer.scanner import ArchitectureScanner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_component(arch, **kwargs):
    """Find a component dict anywhere in the tree matching all kwargs."""
    def _search(comps):
        for c in comps:
            if all(c.get(k) == v for k, v in kwargs.items()):
                return c
            found = _search(c.get("children", []))
            if found:
                return found
        return None
    return _search(arch.components)


def _scan(tmp_path):
    scanner = ArchitectureScanner(tmp_path)
    return scanner.scan()


# ---------------------------------------------------------------------------
# Test file detection
# ---------------------------------------------------------------------------

class TestTestFileDetection:
    """Test that test files are identified by naming conventions."""

    def test_python_test_files(self, tmp_path):
        """Python test_*.py and *_test.py files are detected."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\n')
        (tmp_path / "app.py").write_text("def main():\n    pass\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_app.py").write_text(
            "def test_one():\n    pass\n\ndef test_two():\n    pass\n"
        )
        (tmp_path / "tests" / "test_utils.py").write_text(
            "def test_helper():\n    pass\n"
        )

        arch = _scan(tmp_path)
        comp = _find_component(arch, type="package")
        assert comp is not None
        testing = comp.get("testing", {})
        assert testing.get("test_files", 0) >= 2
        assert testing.get("unit_tests", 0) >= 3

    def test_javascript_test_files(self, tmp_path):
        """JS .test.js and .spec.js files are detected."""
        (tmp_path / "package.json").write_text(json.dumps({
            "name": "myapp",
            "devDependencies": {"jest": "^29.0.0"}
        }))
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.js").write_text("export function hello() {}\n")
        (tmp_path / "src" / "index.test.js").write_text(
            "test('hello works', () => {});\ntest('bye works', () => {});\n"
        )

        arch = _scan(tmp_path)
        # Test files live in src/ which may be a separate module component.
        # Walk all components to find the one with test data.
        all_testing = []
        def _walk(comps):
            for c in comps:
                t = c.get("testing", {})
                if t.get("test_files", 0) > 0:
                    all_testing.append(t)
                _walk(c.get("children", []))
        _walk(arch.components)
        assert len(all_testing) >= 1
        t = all_testing[0]
        assert t["test_files"] >= 1
        assert t["unit_tests"] >= 2
        # Jest should be detected on the package component
        pkg = _find_component(arch, type="package")
        assert pkg is not None
        assert "Jest" in pkg.get("testing", {}).get("test_frameworks", [])

    def test_go_test_files(self, tmp_path):
        """Go _test.go files are detected."""
        (tmp_path / "go.mod").write_text("module example.com/app\ngo 1.21\n")
        (tmp_path / "main.go").write_text('package main\nfunc main() {}\n')
        (tmp_path / "main_test.go").write_text(
            'package main\nimport "testing"\n'
            "func TestMain(t *testing.T) {}\n"
            "func TestOther(t *testing.T) {}\n"
        )

        arch = _scan(tmp_path)
        comp = _find_component(arch, type="module")
        assert comp is not None
        testing = comp.get("testing", {})
        assert testing.get("test_files", 0) >= 1
        assert testing.get("unit_tests", 0) >= 2
        assert "Go testing" in testing.get("test_frameworks", [])


# ---------------------------------------------------------------------------
# Test function counting
# ---------------------------------------------------------------------------

class TestTestFunctionCounting:
    """Test that individual test functions are counted correctly."""

    def test_python_async_tests(self, tmp_path):
        """Async pytest functions are counted."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\n')
        (tmp_path / "app.py").write_text("def main():\n    pass\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_async.py").write_text(
            "async def test_async_one():\n    pass\n\n"
            "async def test_async_two():\n    pass\n\n"
            "def test_sync():\n    pass\n"
        )

        arch = _scan(tmp_path)
        comp = _find_component(arch, type="package")
        testing = comp.get("testing", {})
        assert testing.get("unit_tests", 0) >= 3


# ---------------------------------------------------------------------------
# Test category classification
# ---------------------------------------------------------------------------

class TestTestCategoryClassification:
    """Test that tests are classified into unit, integration, e2e."""

    def test_e2e_directory(self, tmp_path):
        """Tests in e2e/ directory are classified as e2e."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "myapp"}))
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.ts").write_text("export const app = 1;\n")
        (tmp_path / "e2e").mkdir()
        (tmp_path / "e2e" / "login.spec.ts").write_text(
            "test('login flow', () => {});\n"
            "test('logout flow', () => {});\n"
        )

        arch = _scan(tmp_path)
        comp = _find_component(arch, type="package")
        testing = comp.get("testing", {})
        assert testing.get("e2e_tests", 0) >= 2

    def test_integration_directory(self, tmp_path):
        """Tests in integration/ directory are classified as integration."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\n')
        (tmp_path / "app.py").write_text("def main():\n    pass\n")
        (tmp_path / "integration").mkdir()
        (tmp_path / "integration" / "test_db.py").write_text(
            "def test_db_connection():\n    pass\n"
        )

        arch = _scan(tmp_path)
        comp = _find_component(arch, type="package")
        testing = comp.get("testing", {})
        assert testing.get("integration_tests", 0) >= 1


# ---------------------------------------------------------------------------
# Coverage report parsing
# ---------------------------------------------------------------------------

class TestCoverageReportParsing:
    """Test coverage report file parsing."""

    def test_lcov_report(self, tmp_path):
        """LCOV format coverage report is parsed."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\n')
        (tmp_path / "app.py").write_text("def main():\n    pass\n")
        (tmp_path / "lcov.info").write_text(
            "SF:app.py\nDA:1,1\nDA:2,1\nDA:3,0\nDA:4,0\n"
            "LF:4\nLH:2\nend_of_record\n"
        )

        arch = _scan(tmp_path)
        comp = _find_component(arch, type="package")
        testing = comp.get("testing", {})
        assert testing.get("coverage_percent") is not None
        assert abs(testing["coverage_percent"] - 50.0) < 0.1

    def test_istanbul_report(self, tmp_path):
        """Istanbul JSON coverage report is parsed."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "myapp"}))
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.js").write_text("export const x = 1;\n")
        (tmp_path / "coverage-summary.json").write_text(json.dumps({
            "total": {
                "lines": {"total": 100, "covered": 85, "pct": 85.0}
            }
        }))

        arch = _scan(tmp_path)
        comp = _find_component(arch, type="package")
        testing = comp.get("testing", {})
        assert testing.get("coverage_percent") is not None
        assert abs(testing["coverage_percent"] - 85.0) < 0.1

    def test_cobertura_report(self, tmp_path):
        """Cobertura XML coverage report is parsed."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\n')
        (tmp_path / "app.py").write_text("def main():\n    pass\n")
        (tmp_path / "coverage.xml").write_text(
            '<?xml version="1.0"?>\n'
            '<coverage line-rate="0.72" branch-rate="0.5" version="5.5">\n'
            "</coverage>\n"
        )

        arch = _scan(tmp_path)
        comp = _find_component(arch, type="package")
        testing = comp.get("testing", {})
        assert testing.get("coverage_percent") is not None
        assert abs(testing["coverage_percent"] - 72.0) < 0.1


# ---------------------------------------------------------------------------
# Framework detection
# ---------------------------------------------------------------------------

class TestFrameworkDetection:
    """Test framework detection from config files and dependencies."""

    def test_pytest_from_conftest(self, tmp_path):
        """pytest detected via conftest.py."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\n')
        (tmp_path / "app.py").write_text("def main():\n    pass\n")
        (tmp_path / "conftest.py").write_text("import pytest\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    pass\n")

        arch = _scan(tmp_path)
        comp = _find_component(arch, type="package")
        testing = comp.get("testing", {})
        assert "pytest" in testing.get("test_frameworks", [])

    def test_vitest_from_config(self, tmp_path):
        """Vitest detected via vitest.config.ts."""
        (tmp_path / "package.json").write_text(json.dumps({
            "name": "myapp",
            "devDependencies": {"vitest": "^1.0.0"}
        }))
        (tmp_path / "vitest.config.ts").write_text("export default {}\n")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.ts").write_text("export const x = 1;\n")

        arch = _scan(tmp_path)
        comp = _find_component(arch, type="package")
        testing = comp.get("testing", {})
        assert "Vitest" in testing.get("test_frameworks", [])


# ---------------------------------------------------------------------------
# CI test detection
# ---------------------------------------------------------------------------

class TestCIDetection:
    """Test CI configuration detection."""

    def test_github_actions_with_pytest(self, tmp_path):
        """GitHub Actions workflow with pytest is detected."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\n')
        (tmp_path / "app.py").write_text("def main():\n    pass\n")
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text(
            "name: CI\non: push\njobs:\n  test:\n    steps:\n"
            "      - run: pytest tests/\n"
        )
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    pass\n")

        arch = _scan(tmp_path)
        comp = _find_component(arch, type="package")
        testing = comp.get("testing", {})
        assert testing.get("has_ci_tests") is True


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Test that components without test data still work."""

    def test_no_tests_empty_testing(self, tmp_path):
        """Components without tests have empty testing dict."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "myapp"\n')
        (tmp_path / "app.py").write_text("def main():\n    pass\n")

        arch = _scan(tmp_path)
        comp = _find_component(arch, type="package")
        assert comp is not None
        # testing should be empty dict (not present or empty)
        testing = comp.get("testing", {})
        assert testing.get("test_files", 0) == 0 or testing == {}
