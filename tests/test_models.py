"""Tests for analyzer.models (enums, Pydantic/dataclass models, to_dict, validation)."""

import json

import pytest

from analyzer.models import (
    Architecture,
    Component,
    ComponentDoc,
    ComponentType,
    FileInfo,
    Relationship,
    RelationshipType,
    Symbol,
    SymbolKind,
    Visibility,
    _PYDANTIC,
    to_dict,
)


# ---------------------------------------------------------------------------
# Enum tests (always run, no pydantic dependency)
# ---------------------------------------------------------------------------

class TestEnums:
    def test_symbol_kind_values(self):
        assert SymbolKind.CLASS == "class"
        assert SymbolKind.FUNCTION == "function"
        assert SymbolKind("struct") == SymbolKind.STRUCT

    def test_symbol_kind_is_str(self):
        assert isinstance(SymbolKind.CLASS, str)

    def test_visibility_values(self):
        assert Visibility.PUBLIC == "public"
        assert Visibility.INTERNAL == "internal"
        assert Visibility("fileprivate") == Visibility.FILEPRIVATE

    def test_component_type_values(self):
        assert ComponentType.APPLICATION == "application"
        assert ComponentType.API_SERVER == "api-server"
        assert ComponentType("screen") == ComponentType.SCREEN

    def test_relationship_type_values(self):
        assert RelationshipType.IMPORT == "import"
        assert RelationshipType.NAVIGATION == "navigation"
        assert RelationshipType("embed") == RelationshipType.EMBED

    def test_invalid_enum_raises(self):
        with pytest.raises(ValueError):
            SymbolKind("nonexistent")


# ---------------------------------------------------------------------------
# to_dict tests (always run)
# ---------------------------------------------------------------------------

class TestToDict:
    def test_dict_passthrough(self):
        d = {"a": 1, "b": 2}
        assert to_dict(d) is d

    def test_symbol_to_dict(self):
        sym = Symbol(
            id="f.py:Foo:1", name="Foo", kind="class", file="f.py",
            line=1, end_line=10, code_preview="class Foo:",
        )
        result = to_dict(sym)
        assert isinstance(result, dict)
        assert result["id"] == "f.py:Foo:1"
        assert result["name"] == "Foo"
        assert result["kind"] == "class"
        assert result["visibility"] == "internal"

    def test_fileinfo_to_dict(self):
        fi = FileInfo(path="src/main.py", language="python", lines=100, size_bytes=2048)
        result = to_dict(fi)
        assert result["path"] == "src/main.py"
        assert result["lines"] == 100

    def test_component_to_dict(self):
        comp = Component(id="app", name="App", type="application", path=".")
        result = to_dict(comp)
        assert result["id"] == "app"
        assert result["type"] == "application"
        assert result["children"] == []

    def test_relationship_to_dict(self):
        rel = Relationship(source="a", target="b", type="import")
        result = to_dict(rel)
        assert result["source"] == "a"
        assert result["target"] == "b"

    def test_architecture_to_dict(self):
        arch = Architecture(name="test", description="desc")
        result = to_dict(arch)
        assert result["name"] == "test"
        assert result["components"] == []

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            to_dict(42)

    def test_component_doc_to_dict(self):
        doc = ComponentDoc(purpose="A test component")
        result = to_dict(doc)
        assert result["purpose"] == "A test component"
        assert result["key_decisions"] == []


# ---------------------------------------------------------------------------
# JSON round-trip tests
# ---------------------------------------------------------------------------

class TestJsonRoundTrip:
    def test_symbol_json_roundtrip(self):
        sym = Symbol(
            id="f.py:Foo:1", name="Foo", kind="class", file="f.py",
            line=1, end_line=10, code_preview="class Foo:",
        )
        text = json.dumps(to_dict(sym), default=str)
        loaded = json.loads(text)
        assert loaded["id"] == "f.py:Foo:1"
        assert loaded["kind"] == "class"

    def test_architecture_json_roundtrip(self):
        arch = Architecture(
            name="test", description="desc",
            components=[
                to_dict(Component(id="a", name="A", type="service", path="/a")),
            ],
            relationships=[
                to_dict(Relationship(source="a", target="b", type="http")),
            ],
        )
        text = json.dumps(to_dict(arch), default=str)
        loaded = json.loads(text)
        assert loaded["name"] == "test"
        assert len(loaded["components"]) == 1
        assert loaded["components"][0]["id"] == "a"


# ---------------------------------------------------------------------------
# Cross-reference validation tests
# ---------------------------------------------------------------------------

class TestValidateCrossReferences:
    def _make_arch(self, components, relationships):
        return Architecture(
            name="test", description="test",
            components=components,
            relationships=relationships,
        )

    def test_valid_refs(self):
        arch = self._make_arch(
            components=[{"id": "a", "children": []}, {"id": "b", "children": []}],
            relationships=[{"source": "a", "target": "b", "type": "import"}],
        )
        errors = arch.validate_cross_references()
        assert errors == []

    def test_missing_source(self):
        arch = self._make_arch(
            components=[{"id": "b", "children": []}],
            relationships=[{"source": "a", "target": "b", "type": "http"}],
        )
        errors = arch.validate_cross_references()
        assert len(errors) == 1
        assert "source 'a' not found" in errors[0]

    def test_missing_target(self):
        arch = self._make_arch(
            components=[{"id": "a", "children": []}],
            relationships=[{"source": "a", "target": "b", "type": "http"}],
        )
        errors = arch.validate_cross_references()
        assert len(errors) == 1
        assert "target 'b' not found" in errors[0]

    def test_nested_children(self):
        arch = self._make_arch(
            components=[{"id": "root", "children": [{"id": "child", "children": []}]}],
            relationships=[{"source": "root", "target": "child", "type": "embed"}],
        )
        errors = arch.validate_cross_references()
        assert errors == []

    def test_empty_architecture(self):
        arch = self._make_arch(components=[], relationships=[])
        errors = arch.validate_cross_references()
        assert errors == []

    def test_not_called_on_construction(self):
        """Verify that creating an Architecture with broken refs does not raise."""
        arch = self._make_arch(
            components=[],
            relationships=[{"source": "x", "target": "y", "type": "http"}],
        )
        assert isinstance(arch, Architecture)


# ---------------------------------------------------------------------------
# Pydantic-specific validation tests (skipped when pydantic not installed)
# ---------------------------------------------------------------------------

needs_pydantic = pytest.mark.skipif(not _PYDANTIC, reason="pydantic not installed")


@needs_pydantic
class TestPydanticValidation:
    def test_symbol_negative_line(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Symbol(
                id="x", name="X", kind="class", file="f.py",
                line=-1, end_line=10, code_preview="",
            )

    def test_symbol_empty_name(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Symbol(
                id="x", name="", kind="class", file="f.py",
                line=1, end_line=10, code_preview="",
            )

    def test_fileinfo_empty_path(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            FileInfo(path="", language="python", lines=10, size_bytes=100)

    def test_fileinfo_negative_lines(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            FileInfo(path="f.py", language="python", lines=-5, size_bytes=100)

    def test_component_empty_id(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Component(id="", name="X", type="service", path=".")

    def test_component_invalid_port(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Component(id="x", name="X", type="service", path=".", port=99999)

    def test_component_port_zero(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Component(id="x", name="X", type="service", path=".", port=0)

    def test_component_valid_port(self):
        comp = Component(id="x", name="X", type="service", path=".", port=8080)
        assert comp.port == 8080

    def test_relationship_empty_source(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Relationship(source="", target="b", type="http")

    def test_relationship_empty_target(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Relationship(source="a", target="", type="http")

    def test_relationship_invalid_port(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Relationship(source="a", target="b", type="http", port=70000)

    def test_symbol_accepts_any_kind_string(self):
        """Enum validation is not enforced on construction, only plain str."""
        sym = Symbol(
            id="x", name="X", kind="unknown_kind", file="f.py",
            line=1, end_line=10, code_preview="",
        )
        assert sym.kind == "unknown_kind"

    def test_component_accepts_any_type_string(self):
        comp = Component(id="x", name="X", type="custom-type", path=".")
        assert comp.type == "custom-type"
