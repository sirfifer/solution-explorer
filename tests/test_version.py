"""Version coherence regression tests (P1-1, findings F-CRIT-1, F-AN-12).

These tests lock the single-source-of-truth version contract in place so the
`analyzer_version` stamped into generated output can never again drift from the
package version (the audit found a hardcoded "1.0.0" literal in models.py while
the package declared 0.3.0). They also assert the npm and Python version sources
stay aligned.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import analyzer
from analyzer.cli import main
from analyzer.models import Architecture, to_dict

REPO_ROOT = Path(__file__).parent.parent


def test_model_default_analyzer_version_matches_package_version():
    """The Architecture default analyzer_version derives from analyzer.__version__.

    Fails on the pre-fix code, which hardcoded "1.0.0" in both the pydantic and
    dataclass Architecture definitions in analyzer/models.py.
    """
    arch = Architecture(name="x", description="y")
    assert to_dict(arch)["analyzer_version"] == analyzer.__version__


def test_generated_output_stamps_current_analyzer_version(monkeypatch, tmp_path):
    """A real scan writes analyzer_version equal to analyzer.__version__.

    This drives the real CLI code path (main -> scanner -> serialize) rather than
    the model default in isolation, so it catches the actual value that ships in
    architecture.json.
    """
    repo = tmp_path / "proj"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps({"name": "verproj", "description": "version test project"})
    )
    src = repo / "src"
    src.mkdir()
    (src / "index.ts").write_text("export function greet(): string {\n  return \"hi\";\n}\n")

    out = tmp_path / "out.json"
    monkeypatch.setattr("sys.argv", ["analyze", str(repo), "-o", str(out)])
    main()

    data = json.loads(out.read_text())
    assert data["analyzer_version"] == analyzer.__version__


def test_python_and_npm_version_sources_are_aligned():
    """analyzer/__init__.py, packages/cli/package.json, and viewer/package.json agree.

    pyproject.toml reads the version dynamically from analyzer.__version__, so it is
    covered transitively. This guards against a future partial bump.
    """
    cli_pkg = json.loads((REPO_ROOT / "packages" / "cli" / "package.json").read_text())
    viewer_pkg = json.loads((REPO_ROOT / "viewer" / "package.json").read_text())

    assert cli_pkg["version"] == analyzer.__version__
    assert viewer_pkg["version"] == analyzer.__version__


def test_no_hardcoded_analyzer_version_literal_in_models():
    """models.py must not reintroduce a hardcoded analyzer_version literal.

    The field default must reference __version__, not a string literal, so the
    F-AN-12 drift cannot recur.
    """
    models_src = (REPO_ROOT / "analyzer" / "models.py").read_text()
    version_defaults = re.findall(
        r"^\s*analyzer_version\s*:\s*str\s*=\s*(.+?)\s*$", models_src, re.MULTILINE
    )
    assert version_defaults, "models.py must declare analyzer_version defaults"
    for default in version_defaults:
        assert default == "__version__", (
            f"analyzer_version default must be __version__, found {default!r}. "
            "A literal here reintroduces the F-AN-12 drift."
        )
