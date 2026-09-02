"""Tests for the C++ parser (regex + tree-sitter) and its end-to-end wiring.

Two layers, mirroring the project's other language tests:

* A parity snapshot over ``tests/fixtures/cpp``, pinned to the tree-sitter tier
  (the regex fallback legitimately emits different symbols), frozen in
  ``tests/fixtures/parity/cpp.snapshot.json`` with a perturbation guard that
  proves the snapshot can fail. Regenerate intentionally with
  ``SE_REGEN_PARITY=1 python -m pytest tests/test_cpp.py``.
* Tier-agnostic functional tests (run whichever parser the registry resolved)
  plus tree-sitter-specific tests for the constructs only the grammar reaches
  (methods, templates, nested namespaces, out-of-line definitions, export-macro
  recovery, visibility sections).
"""

import copy
import json
import os
from pathlib import Path

import pytest

from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.models import to_dict
from analyzer.parsers import PARSERS
from analyzer.parsers.cpp import CppParser
from analyzer.scanner import ArchitectureScanner
from analyzer.store import FactStore

FIXTURES = Path(__file__).parent / "fixtures"
SNAPSHOTS = FIXTURES / "parity"
CPP_FIXTURE = FIXTURES / "cpp"

_CPP_PARSER = PARSERS["cpp"]
_TS_ACTIVE = getattr(_CPP_PARSER, "_ts_available", False)

requires_tree_sitter_tier = pytest.mark.skipif(
    not _TS_ACTIVE,
    reason=(
        "the cpp parity snapshot is pinned to the tree-sitter tier; this "
        "environment resolved C++ to the regex fallback"
    ),
)


@pytest.fixture
def cpp_ts():
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_cpp")
    from analyzer.parsers.cpp_ts import CppTreeSitterParser
    return CppTreeSitterParser()


# ===================================================================
# Parity snapshot
# ===================================================================

_VOLATILE_KEYS = (
    "generated_at", "root_path", "analyzer_version", "changelog",
    "changelog_serial",
)


def _deep_sort(obj):
    if isinstance(obj, dict):
        return {k: _deep_sort(v) for k, v in obj.items()}
    if isinstance(obj, list):
        items = [_deep_sort(x) for x in obj]
        items.sort(key=lambda x: json.dumps(x, sort_keys=True, default=str))
        return items
    return obj


def _normalize(arch_dict: dict) -> dict:
    d = copy.deepcopy(arch_dict)
    for key in _VOLATILE_KEYS:
        d.pop(key, None)
    return _deep_sort(d)


def _canonical(d: dict) -> str:
    return json.dumps(d, sort_keys=True, indent=2, default=str) + "\n"


def _run_cpp() -> dict:
    return _normalize(to_dict(ArchitectureScanner(CPP_FIXTURE).scan()))


def _snapshot_path() -> Path:
    return SNAPSHOTS / "cpp.snapshot.json"


@requires_tree_sitter_tier
def test_cpp_matches_snapshot():
    produced = _canonical(_run_cpp())
    path = _snapshot_path()
    if os.environ.get("SE_REGEN_PARITY") == "1":
        SNAPSHOTS.mkdir(parents=True, exist_ok=True)
        path.write_text(produced, encoding="utf-8")
        pytest.skip(f"regenerated parity snapshot {path.name}")
    assert path.exists(), (
        f"missing parity snapshot {path}; regenerate with "
        f"SE_REGEN_PARITY=1 python -m pytest {__file__}"
    )
    assert produced == path.read_text(encoding="utf-8"), (
        "cpp engine output drifted from the committed snapshot. If intended, "
        "regenerate with SE_REGEN_PARITY=1 and review the diff."
    )


@requires_tree_sitter_tier
def test_cpp_output_is_deterministic():
    assert _canonical(_run_cpp()) == _canonical(_run_cpp())


def test_cpp_snapshot_committed_and_nonempty():
    path = _snapshot_path()
    assert path.exists(), f"parity snapshot {path} is not committed"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["components"], "cpp snapshot has no components"
    assert data["files"], "cpp snapshot has no files"
    assert data["symbols"], "cpp snapshot has no symbols"


@requires_tree_sitter_tier
def test_cpp_guard_detects_a_perturbed_snapshot():
    committed = _snapshot_path().read_text(encoding="utf-8")
    baseline = _canonical(_run_cpp())
    assert baseline == committed  # sanity: unperturbed matches
    perturbed = _run_cpp()
    assert perturbed["symbols"], "fixture must have symbols to perturb"
    perturbed["symbols"][0]["name"] = perturbed["symbols"][0]["name"] + "_PERTURBED"
    assert _canonical(perturbed) != committed, (
        "the parity guard failed to detect a perturbed snapshot"
    )


# ===================================================================
# Tier-agnostic functional tests (pass on both parser tiers)
# ===================================================================

_TYPES_CODE = (
    "#include <string>\n"
    '#include "core/logger.hpp"\n'
    "\n"
    "namespace core {\n"
    "\n"
    "class Widget {\n"
    "public:\n"
    "    int size() const { return 3; }\n"
    "};\n"
    "\n"
    "struct Point { int x; int y; };\n"
    "\n"
    "enum class Color { Red, Green };\n"
    "\n"
    "union Value { int i; float f; };\n"
    "\n"
    "}\n"
)


def test_types_and_namespace_found_any_tier():
    symbols = _CPP_PARSER.extract_symbols(_TYPES_CODE, "t.cpp")
    by_name = {s.name: s.kind for s in symbols}
    assert by_name.get("Widget") == "class"
    assert by_name.get("Point") == "struct"
    assert by_name.get("Color") == "enum"
    assert by_name.get("Value") == "union"
    assert by_name.get("core") == "namespace"


def test_includes_angle_and_quoted_any_tier():
    imports = _CPP_PARSER.extract_imports(_TYPES_CODE)
    assert "string" in imports          # <string>
    assert "core/logger.hpp" in imports  # "core/logger.hpp"


def test_forward_declaration_is_not_a_definition_any_tier():
    # `class Foo;` names no definition; neither tier should emit a symbol for it.
    symbols = _CPP_PARSER.extract_symbols("class Forward;\n", "t.cpp")
    assert [s for s in symbols if s.name == "Forward"] == []


def test_qt_framework_detection_any_tier():
    code = '#include <QtWidgets/QApplication>\nclass MainWindow { Q_OBJECT };\n'
    assert _CPP_PARSER.detect_framework(code) == "Qt"


# ===================================================================
# Tree-sitter-specific tests
# ===================================================================

class TestCppTreeSitter:

    def test_class_with_inline_and_prototype_methods(self, cpp_ts):
        code = (
            "class Manager {\n"
            "public:\n"
            "    void start();\n"
            "    int compute(int x) { return x; }\n"
            "};\n"
        )
        names = {s.name for s in cpp_ts.extract_symbols(code, "t.cpp")}
        assert {"Manager", "start", "compute"} <= names

    def test_visibility_sections(self, cpp_ts):
        code = (
            "class C {\n"
            "public:\n"
            "    void pub() {}\n"
            "private:\n"
            "    void priv() {}\n"
            "};\n"
        )
        by_name = {s.name: s for s in cpp_ts.extract_symbols(code, "t.cpp")}
        assert by_name["pub"].visibility == "public"
        assert by_name["priv"].visibility == "private"

    def test_out_of_line_method_definition(self, cpp_ts):
        code = (
            "namespace core {\n"
            "class Logger { public: void info(); };\n"
            "}\n"
            "void core::Logger::info() {}\n"
        )
        methods = [s for s in cpp_ts.extract_symbols(code, "t.cpp")
                   if s.kind == "method" and s.name == "info"]
        assert methods, "out-of-line method definition should be extracted"

    def test_nested_namespace(self, cpp_ts):
        code = "namespace app::ui {\nclass Panel {};\n}\n"
        symbols = cpp_ts.extract_symbols(code, "t.cpp")
        ns = [s for s in symbols if s.kind == "namespace"]
        assert any(s.name == "app::ui" for s in ns)

    def test_templated_class(self, cpp_ts):
        code = (
            "template<typename T>\n"
            "class Box {\n"
            "public:\n"
            "    T get() const;\n"
            "};\n"
        )
        names = {s.name for s in cpp_ts.extract_symbols(code, "t.cpp")}
        assert "Box" in names
        assert "get" in names

    def test_export_macro_class_recovery(self, cpp_ts):
        # `class SPDLOG_API registry { ... }`: the macro cannot be expanded, so
        # tree-sitter mis-parses it. The parser recovers the real name and body.
        code = (
            "class SPDLOG_API registry : public base {\n"
            "public:\n"
            "    void reg();\n"
            "private:\n"
            "    int n_;\n"
            "};\n"
        )
        symbols = cpp_ts.extract_symbols(code, "t.cpp")
        by_name = {s.name: s for s in symbols}
        assert by_name.get("registry") and by_name["registry"].kind == "class"
        assert "reg" in by_name

    def test_elaborated_type_variable_is_not_a_type(self, cpp_ts):
        # `struct Foo bar;` uses Foo, it does not define it: no symbol emitted.
        symbols = cpp_ts.extract_symbols("struct Foo bar;\n", "t.cpp")
        assert [s for s in symbols if s.name in ("Foo", "bar")] == []

    def test_imports_angle_vs_quoted(self, cpp_ts):
        code = '#include <vector>\n#include "a/b.hpp"\n'
        imports = cpp_ts.extract_imports(code)
        assert "vector" in imports
        assert "a/b.hpp" in imports

    def test_include_behind_guard(self, cpp_ts):
        code = (
            "#ifndef GUARD_H\n#define GUARD_H\n"
            "namespace n { class Guarded {}; }\n"
            "#endif\n"
        )
        names = {s.name for s in cpp_ts.extract_symbols(code, "t.hpp")}
        assert "Guarded" in names
        assert "n" in names

    def test_nested_symbol_parents(self, cpp_ts):
        code = "namespace ns {\nclass Outer { void m() {} };\n}\n"
        nested = cpp_ts.extract_nested_symbols(code, "t.cpp")
        by_path = {"/".join(n.path): n for n in nested}
        assert "ns" in by_path
        assert "ns/Outer" in by_path
        assert "ns/Outer/m" in by_path

    def test_parity_with_regex(self, cpp_ts):
        # Tree-sitter must find at least the type-level symbols the regex tier does.
        regex_names = {s.name for s in CppParser().extract_symbols(_TYPES_CODE, "t.cpp")}
        ts_names = {s.name for s in cpp_ts.extract_symbols(_TYPES_CODE, "t.cpp")}
        assert regex_names <= ts_names


# ===================================================================
# Fallback behavior
# ===================================================================

def test_cpp_without_a_grammar_refuses_instead_of_falling_back():
    """No grammar means no answer, not a worse answer.

    This test asserted the opposite until 2026-08-24, when a private large-repository validation corpus run without
    tree-sitter installed produced a projection with 355,617 symbols instead of
    153,231 and 55 methods instead of 28,501, while reporting 100% coverage. A
    degraded answer is indistinguishable downstream from a good one, so there is
    no longer a tier that produces it.
    """
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_cpp")
    from analyzer.parsers import DegradedParserError
    from analyzer.parsers.cpp_ts import CppTreeSitterParser
    parser = CppTreeSitterParser()
    parser._ts_available = False
    code = "namespace n {\nclass Foo {\n    void m() {}\n};\n}\n"
    with pytest.raises(DegradedParserError):
        parser.extract_symbols(code, "t.cpp")


# ===================================================================
# End-to-end: extract -> derive draws a cross-component uses edge
# ===================================================================

def _derive_fixture():
    store = FactStore(":memory:")
    extract_repo(str(CPP_FIXTURE), store)
    return derive_all(store, CPP_FIXTURE.name, root_path=str(CPP_FIXTURE))


def test_cpp_cross_component_uses_edge_with_evidence():
    _d, arch = _derive_fixture()
    uses = [r for r in arch["relationships"] if r["type"] == "uses"]
    edge = [r for r in uses if r["source"] == "app" and r["target"] == "core"]
    assert len(edge) == 1, f"expected one app->core uses edge, got: {uses}"
    ev = edge[0]["evidence"]
    assert any(e["file"] and e["line"] for e in ev), ev
    assert any(e["snippet"] == "Logger" for e in ev), ev
    assert edge[0]["confidence"] == "inferred"


def test_cpp_include_edge_and_symbols():
    _d, arch = _derive_fixture()
    imports = [r for r in arch["relationships"] if r["type"] == "import"]
    assert any(r["source"] == "app" and r["target"] == "core" for r in imports)
    # Logger is defined in the header and picked up as a class definition.
    logger = [s for s in arch["symbols"]
              if s["name"] == "Logger" and s["kind"] == "class"]
    assert logger, "class Logger should be extracted from the header"


def test_cpp_fixture_fully_parsed():
    _d, arch = _derive_fixture()
    cpp_files = [f for f in arch["files"] if f["language"] == "cpp"]
    assert len(cpp_files) == 4, [f["path"] for f in cpp_files]
