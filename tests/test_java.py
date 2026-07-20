"""Java parser: parity snapshot plus tier-agnostic functional tests.

The parity block mirrors tests/test_engine_parity.py: it freezes the current
engine's normalized output on the committed Java fixture and is pinned to the
tree-sitter parser tier (regex-fallback symbols legitimately differ, so the
snapshot is meaningless there and skips loudly). The functional block asserts
behaviors that hold on BOTH tiers by driving the regex parser and the extraction
helpers directly, so it runs everywhere.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer.extract.frameworks import StringMask, extract_endpoints
from analyzer.extract.references import (
    PER_NAME_IMPORT_LANGUAGES,
    REFERENCE_LANGUAGES,
    extract_reference_signals,
)
from analyzer.models import to_dict
from analyzer.parsers import PARSERS
from analyzer.parsers.java import JavaParser
from analyzer.scanner import ArchitectureScanner
from tests.test_engine_parity import canonical, normalize

FIXTURES = Path(__file__).parent / "fixtures"
JAVA_FIXTURE = FIXTURES / "java"
SNAPSHOT = FIXTURES / "parity" / "java.snapshot.json"


# ===========================================================================
# Parity snapshot (tree-sitter-tier pinned, with perturbation guard)
# ===========================================================================

_JAVA_TS_ACTIVE = getattr(PARSERS.get("java"), "_ts_available", False)
requires_java_tree_sitter = pytest.mark.skipif(
    not _JAVA_TS_ACTIVE,
    reason=(
        "the Java parity snapshot is pinned to the tree-sitter parser tier; "
        "this environment resolved Java to the regex fallback"
    ),
)


def _run_java() -> dict:
    scanner = ArchitectureScanner(JAVA_FIXTURE)
    return normalize(to_dict(scanner.scan()))


@requires_java_tree_sitter
def test_java_matches_snapshot():
    produced = canonical(_run_java())
    assert SNAPSHOT.exists(), (
        f"missing Java parity snapshot {SNAPSHOT}; regenerate with "
        f"SE_REGEN_PARITY=1 python -m pytest {__file__}"
    )
    expected = SNAPSHOT.read_text(encoding="utf-8")
    assert produced == expected, (
        "Java engine output drifted from the committed parity snapshot. If "
        "intended, regenerate with SE_REGEN_PARITY=1 and review the diff."
    )


@requires_java_tree_sitter
def test_java_output_is_deterministic():
    assert canonical(_run_java()) == canonical(_run_java())


@requires_java_tree_sitter
def test_java_guard_detects_a_perturbed_snapshot():
    baseline = canonical(_run_java())
    committed = SNAPSHOT.read_text(encoding="utf-8")
    assert baseline == committed  # sanity: unperturbed matches
    perturbed = _run_java()
    assert perturbed["symbols"], "fixture must have symbols to perturb"
    perturbed["symbols"][0]["name"] = perturbed["symbols"][0]["name"] + "_PERTURBED"
    assert canonical(perturbed) != committed, (
        "the Java parity guard failed to detect a perturbed snapshot"
    )


def test_java_snapshot_is_committed_and_nonempty():
    assert SNAPSHOT.exists(), f"Java parity snapshot {SNAPSHOT} is not committed"
    import json
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert data["components"], "Java snapshot has no components"
    assert data["files"], "Java snapshot has no files"
    assert data["symbols"], "Java snapshot has no symbols"


def _maybe_regen():
    import os
    if os.environ.get("SE_REGEN_PARITY") == "1" and _JAVA_TS_ACTIVE:
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(canonical(_run_java()), encoding="utf-8")


_maybe_regen()


# ===========================================================================
# Functional tests (tier-agnostic: driven through the regex parser and the
# regex-based extraction helpers, so they pass on both parser tiers)
# ===========================================================================

CONTROLLER = """package com.example.web;

import com.example.service.User;
import com.example.service.UserService;
import static java.lang.Math.max;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** REST endpoints for users. */
@RestController
@RequestMapping("/api")
public class UserController {
    private final UserService service;

    public UserController(UserService service) {
        this.service = service;
    }

    @GetMapping("/users/{id}")
    public User getUser(long id) {
        return service.find(id);
    }

    interface Callback { void run(); }
    enum Status { ACTIVE, INACTIVE }
    record Point(int x, int y) {}
    @interface Marker {}
}
"""


@pytest.fixture
def java():
    return JavaParser()


class TestJavaSymbols:
    def test_class_declaration(self, java):
        syms = java.extract_symbols(CONTROLLER, "web/UserController.java")
        classes = [s for s in syms if s.kind == "class"]
        assert [c.name for c in classes] == ["UserController"]
        assert classes[0].visibility == "public"
        assert classes[0].line == 13

    def test_interface_enum_record_annotation_kinds(self, java):
        syms = java.extract_symbols(CONTROLLER, "web/UserController.java")
        kinds = {s.name: s.kind for s in syms}
        assert kinds["Callback"] == "interface"
        assert kinds["Status"] == "enum"
        assert kinds["Point"] == "record"
        assert kinds["Marker"] == "annotation"

    def test_methods_extracted(self, java):
        syms = java.extract_symbols(CONTROLLER, "web/UserController.java")
        methods = {s.name for s in syms if s.kind == "method"}
        assert "getUser" in methods
        assert "UserController" in methods  # constructor

    def test_default_visibility_is_package(self, java):
        content = "class Plain {\n    void go() {}\n}\n"
        syms = java.extract_symbols(content, "Plain.java")
        assert syms[0].visibility == "package"


class TestJavaImports:
    def test_imports_are_fully_qualified(self, java):
        imports = java.extract_imports(CONTROLLER)
        assert "com.example.service.UserService" in imports
        assert "com.example.service.User" in imports

    def test_static_import_captured(self, java):
        imports = java.extract_imports(CONTROLLER)
        assert "java.lang.Math.max" in imports

    def test_wildcard_import(self, java):
        imports = java.extract_imports("package a;\nimport java.util.*;\n")
        assert "java.util.*" in imports


class TestJavaFramework:
    def test_spring_detected(self, java):
        assert java.detect_framework(CONTROLLER) == "Spring"

    def test_jakarta_detected(self, java):
        content = "package a;\nimport jakarta.ws.rs.Path;\n"
        assert java.detect_framework(content) == "Jakarta EE"

    def test_javaee_detected(self, java):
        content = "package a;\nimport javax.ws.rs.GET;\n"
        assert java.detect_framework(content) == "Java EE"

    def test_plain_java_has_no_framework(self, java):
        assert java.detect_framework("class Plain {}\n") is None


class TestJavaEndpoints:
    def test_spring_mvc_endpoints(self):
        eps = extract_endpoints(CONTROLLER, "java")
        found = {(v["method"], v["path"]) for v, _ in eps}
        assert ("GET", "/users/{id}") in found
        assert all(v["framework"] == "spring" for v, _ in eps)

    def test_jaxrs_endpoints_gated_and_detected(self):
        jaxrs = (
            "package com.example.api;\n"
            "import javax.ws.rs.GET;\n"
            "import javax.ws.rs.Path;\n"
            '@Path("/orders")\n'
            "public class OrderResource {\n"
            "    @GET\n"
            "    public String list() { return \"[]\"; }\n"
            "}\n"
        )
        eps = extract_endpoints(jaxrs, "java")
        assert eps, "JAX-RS endpoints should be detected behind a ws.rs marker"
        assert all(v["framework"] == "jaxrs" for v, _ in eps)

    def test_no_endpoints_without_framework_marker(self):
        plain = (
            "package a;\n"
            "public class Thing {\n"
            '    void get() { call("/not-a-route"); }\n'
            "}\n"
        )
        assert extract_endpoints(plain, "java") == []


class TestJavaReferences:
    def test_java_is_a_reference_language(self):
        assert "java" in REFERENCE_LANGUAGES

    def test_java_uses_per_name_import_resolution(self):
        # Java imports name a single type, so single-definer resolution requires
        # import evidence (documented decision in references.py).
        assert "java" in PER_NAME_IMPORT_LANGUAGES

    def test_type_references_extracted(self):
        mask = StringMask(CONTROLLER, "java")
        names = {s.value["name"] for s in extract_reference_signals(CONTROLLER, "java", mask)}
        assert "UserService" in names
        assert "User" in names

    def test_qualified_access_is_not_a_reference(self):
        content = (
            "package a;\n"
            "public class C {\n"
            "    void m() { service.find(id); this.value = 1; }\n"
            "}\n"
        )
        mask = StringMask(content, "java")
        names = {s.value["name"] for s in extract_reference_signals(content, "java", mask)}
        # `find` and `value` are members of a qualifier's namespace, not local
        # type references, and are lowercase besides.
        assert "find" not in names and "value" not in names


def test_java_parser_registered():
    assert "java" in PARSERS
    assert PARSERS["java"].extract_symbols("class A {}\n", "A.java")
