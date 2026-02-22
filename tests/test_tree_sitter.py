"""Tests for tree-sitter parsers.

All tests skip automatically when tree-sitter packages are not installed.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer.parsers.swift import SwiftParser
from analyzer.parsers.typescript import TypeScriptParser
from analyzer.parsers.rust import RustParser
from analyzer.parsers.python_lang import PythonParser
from analyzer.parsers.go import GoParser
from analyzer.parsers.ruby import RubyParser


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def swift_ts():
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_swift")
    from analyzer.parsers.swift_ts import SwiftTreeSitterParser
    return SwiftTreeSitterParser()


@pytest.fixture
def ts_ts():
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_typescript")
    from analyzer.parsers.typescript_ts import TypeScriptTreeSitterParser
    return TypeScriptTreeSitterParser()


@pytest.fixture
def rust_ts():
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_rust")
    from analyzer.parsers.rust_ts import RustTreeSitterParser
    return RustTreeSitterParser()


@pytest.fixture
def python_ts():
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_python")
    from analyzer.parsers.python_ts import PythonTreeSitterParser
    return PythonTreeSitterParser()


@pytest.fixture
def go_ts():
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_go")
    from analyzer.parsers.go_ts import GoTreeSitterParser
    return GoTreeSitterParser()


@pytest.fixture
def ruby_ts():
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_ruby")
    from analyzer.parsers.ruby_ts import RubyTreeSitterParser
    return RubyTreeSitterParser()


# ===================================================================
# Swift Tests
# ===================================================================

class TestSwiftTreeSitter:

    def test_class_struct_enum_protocol(self, swift_ts):
        code = (
            "public class NetworkManager {\n"
            "    func fetch() { }\n"
            "}\n"
            "\n"
            "struct UserModel {\n"
            "    let id: String\n"
            "}\n"
            "\n"
            "enum Status {\n"
            "    case active\n"
            "}\n"
            "\n"
            "protocol DataSource {\n"
            "    func fetchItems()\n"
            "}\n"
        )
        symbols = swift_ts.extract_symbols(code, "test.swift")
        names = {s.name for s in symbols}
        assert "NetworkManager" in names
        assert "UserModel" in names
        assert "Status" in names
        assert "DataSource" in names

    def test_visibility(self, swift_ts):
        code = "public class Pub {}\nprivate class Priv {}\nclass Internal {}\n"
        symbols = swift_ts.extract_symbols(code, "test.swift")
        by_name = {s.name: s for s in symbols}
        assert by_name["Pub"].visibility == "public"
        assert by_name["Priv"].visibility == "private"
        assert by_name["Internal"].visibility == "internal"

    def test_imports(self, swift_ts):
        code = "import Foundation\nimport UIKit\n"
        imports = swift_ts.extract_imports(code)
        assert "Foundation" in imports
        assert "UIKit" in imports

    def test_extension(self, swift_ts):
        code = "extension String {\n    func hello() { }\n}\n"
        symbols = swift_ts.extract_symbols(code, "test.swift")
        ext_symbols = [s for s in symbols if s.kind == "extension"]
        assert len(ext_symbols) == 1
        assert "String" in ext_symbols[0].name

    def test_end_line_accuracy(self, swift_ts):
        code = (
            "struct Foo {\n"
            "    var x: Int\n"
            "    var y: Int\n"
            "}\n"
        )
        symbols = swift_ts.extract_symbols(code, "test.swift")
        foo = [s for s in symbols if s.name == "Foo"][0]
        assert foo.line == 1
        assert foo.end_line == 4

    def test_nested_functions(self, swift_ts):
        code = (
            "class Manager {\n"
            "    public func doWork() { }\n"
            "    private func helper() { }\n"
            "}\n"
        )
        symbols = swift_ts.extract_symbols(code, "test.swift")
        names = {s.name for s in symbols}
        assert "Manager" in names
        assert "doWork" in names
        assert "helper" in names

    def test_parity_with_regex(self, swift_ts):
        """Tree-sitter should find at least the same top-level symbols as regex."""
        code = (
            "import SwiftUI\n"
            "\n"
            "public class Manager {\n"
            "    func doWork() {}\n"
            "}\n"
            "\n"
            "struct Config {\n"
            "    let port: Int\n"
            "}\n"
            "\n"
            "extension Config {\n"
            "    func validate() { }\n"
            "}\n"
        )
        regex_parser = SwiftParser()
        regex_names = {s.name for s in regex_parser.extract_symbols(code, "t.swift")}
        ts_names = {s.name for s in swift_ts.extract_symbols(code, "t.swift")}
        assert regex_names.issubset(ts_names)

    def test_framework_delegates_to_regex(self, swift_ts):
        code = "import SwiftUI\nstruct ContentView: View { }\n"
        assert swift_ts.detect_framework(code) == "SwiftUI"


# ===================================================================
# TypeScript Tests
# ===================================================================

class TestTypeScriptTreeSitter:

    def test_class_and_interface(self, ts_ts):
        code = (
            "export class UserService {\n"
            "    getUser() { return null; }\n"
            "}\n"
            "\n"
            "export interface User {\n"
            "    id: string;\n"
            "}\n"
        )
        symbols = ts_ts.extract_symbols(code, "test.ts")
        names = {s.name for s in symbols}
        assert "UserService" in names
        assert "User" in names

    def test_export_visibility(self, ts_ts):
        code = (
            "export function pub() {}\n"
            "function internal_fn() {}\n"
        )
        symbols = ts_ts.extract_symbols(code, "test.ts")
        by_name = {s.name: s for s in symbols}
        assert by_name["pub"].visibility == "public"
        assert by_name["internal_fn"].visibility == "internal"

    def test_type_alias(self, ts_ts):
        code = "export type UserId = string;\n"
        symbols = ts_ts.extract_symbols(code, "test.ts")
        assert any(s.name == "UserId" and s.kind == "type" for s in symbols)

    def test_const_arrow_function(self, ts_ts):
        code = "export const fetchData = () => {};\n"
        symbols = ts_ts.extract_symbols(code, "test.ts")
        assert any(s.name == "fetchData" for s in symbols)

    def test_react_component_detection(self, ts_ts):
        code = "export const MyComponent = () => { return null; };\n"
        symbols = ts_ts.extract_symbols(code, "test.tsx")
        comp = [s for s in symbols if s.name == "MyComponent"]
        assert len(comp) == 1
        assert comp[0].kind == "component"

    def test_imports(self, ts_ts):
        code = (
            'import React from "react";\n'
            'import { useState } from "react";\n'
            'import type { User } from "./types";\n'
        )
        imports = ts_ts.extract_imports(code)
        assert "react" in imports
        assert "./types" in imports

    def test_parity_with_regex(self, ts_ts):
        code = (
            "export class Service {}\n"
            "export interface IService {}\n"
            "export function helper() {}\n"
        )
        regex_parser = TypeScriptParser()
        regex_names = {s.name for s in regex_parser.extract_symbols(code, "t.ts")}
        ts_names = {s.name for s in ts_ts.extract_symbols(code, "t.ts")}
        assert regex_names.issubset(ts_names)

    def test_framework_delegates_to_regex(self, ts_ts):
        code = 'import express from "express";\n'
        assert ts_ts.detect_framework(code) == "Express"


# ===================================================================
# Rust Tests
# ===================================================================

class TestRustTreeSitter:

    def test_struct_enum_trait(self, rust_ts):
        code = (
            "pub struct Config {\n"
            "    pub port: u16,\n"
            "}\n"
            "\n"
            "enum Status {\n"
            "    Active,\n"
            "    Inactive,\n"
            "}\n"
            "\n"
            "pub trait Handler {\n"
            "    fn handle(&self);\n"
            "}\n"
        )
        symbols = rust_ts.extract_symbols(code, "lib.rs")
        names = {s.name for s in symbols}
        assert "Config" in names
        assert "Status" in names
        assert "Handler" in names

    def test_pub_crate_visibility(self, rust_ts):
        code = (
            "pub(crate) struct Internal {}\n"
            "pub struct Public {}\n"
            "struct Private {}\n"
        )
        symbols = rust_ts.extract_symbols(code, "lib.rs")
        by_name = {s.name: s for s in symbols}
        assert by_name["Internal"].visibility == "internal"
        assert by_name["Public"].visibility == "public"
        assert by_name["Private"].visibility == "private"

    def test_impl_block(self, rust_ts):
        code = (
            "struct Foo {}\n"
            "impl Foo {\n"
            "    pub fn new() -> Self { Foo {} }\n"
            "}\n"
        )
        symbols = rust_ts.extract_symbols(code, "lib.rs")
        assert any(s.kind == "impl" and "Foo" in s.name for s in symbols)

    def test_functions(self, rust_ts):
        code = "pub fn main() { }\nfn private_fn() { }\n"
        symbols = rust_ts.extract_symbols(code, "main.rs")
        by_name = {s.name: s for s in symbols}
        assert by_name["main"].visibility == "public"
        assert by_name["private_fn"].visibility == "private"

    def test_imports(self, rust_ts):
        code = "use std::collections::HashMap;\nuse tokio::runtime;\n"
        imports = rust_ts.extract_imports(code)
        assert "std" in imports
        assert "tokio" in imports

    def test_parity_with_regex(self, rust_ts):
        code = (
            "pub struct Config {}\n"
            "enum Status { A }\n"
            "pub fn main() {}\n"
        )
        regex_parser = RustParser()
        regex_names = {s.name for s in regex_parser.extract_symbols(code, "lib.rs")}
        ts_names = {s.name for s in rust_ts.extract_symbols(code, "lib.rs")}
        assert regex_names.issubset(ts_names)


# ===================================================================
# Python Tests
# ===================================================================

class TestPythonTreeSitter:

    def test_class_and_function(self, python_ts):
        code = (
            'class MyClass:\n'
            '    """A class."""\n'
            '    def method(self):\n'
            '        pass\n'
            '\n'
            'def public_func():\n'
            '    """Docstring."""\n'
            '    pass\n'
        )
        symbols = python_ts.extract_symbols(code, "test.py")
        names = {s.name for s in symbols}
        assert "MyClass" in names
        assert "public_func" in names

    def test_visibility(self, python_ts):
        code = "def public() -> None: pass\ndef _private() -> None: pass\n"
        symbols = python_ts.extract_symbols(code, "test.py")
        by_name = {s.name: s for s in symbols}
        assert by_name["public"].visibility == "public"
        assert by_name["_private"].visibility == "private"

    def test_docstring_extraction(self, python_ts):
        code = (
            'class Foo:\n'
            '    """Foo docstring."""\n'
            '    pass\n'
        )
        symbols = python_ts.extract_symbols(code, "test.py")
        foo = [s for s in symbols if s.name == "Foo"][0]
        assert foo.docstring == "Foo docstring."

    def test_decorated_definition(self, python_ts):
        code = "@decorator\nclass Decorated:\n    pass\n"
        symbols = python_ts.extract_symbols(code, "test.py")
        assert any(s.name == "Decorated" for s in symbols)

    def test_imports(self, python_ts):
        code = "import os\nfrom pathlib import Path\n"
        imports = python_ts.extract_imports(code)
        assert "os" in imports
        assert "pathlib" in imports

    def test_parity_with_regex(self, python_ts):
        code = (
            "class Foo:\n    pass\n\n"
            "def bar():\n    pass\n"
        )
        regex_parser = PythonParser()
        regex_names = {s.name for s in regex_parser.extract_symbols(code, "t.py")}
        ts_names = {s.name for s in python_ts.extract_symbols(code, "t.py")}
        assert regex_names.issubset(ts_names)


# ===================================================================
# Go Tests
# ===================================================================

class TestGoTreeSitter:

    def test_struct_and_interface(self, go_ts):
        code = (
            "package main\n"
            "\n"
            "type Config struct {\n"
            "    Port int\n"
            "}\n"
            "\n"
            "type Handler interface {\n"
            "    Handle()\n"
            "}\n"
        )
        symbols = go_ts.extract_symbols(code, "main.go")
        names = {s.name for s in symbols}
        assert "Config" in names
        assert "Handler" in names
        config = [s for s in symbols if s.name == "Config"][0]
        handler = [s for s in symbols if s.name == "Handler"][0]
        assert config.kind == "struct"
        assert handler.kind == "interface"

    def test_visibility_by_case(self, go_ts):
        code = (
            "package main\n"
            "type Exported struct{}\n"
            "type unexported struct{}\n"
        )
        symbols = go_ts.extract_symbols(code, "main.go")
        by_name = {s.name: s for s in symbols}
        assert by_name["Exported"].visibility == "public"
        assert by_name["unexported"].visibility == "private"

    def test_functions_and_methods(self, go_ts):
        code = (
            "package main\n"
            "func Main() {}\n"
            "func helper() {}\n"
        )
        symbols = go_ts.extract_symbols(code, "main.go")
        names = {s.name for s in symbols}
        assert "Main" in names
        assert "helper" in names

    def test_imports(self, go_ts):
        code = (
            'package main\n'
            'import (\n'
            '    "fmt"\n'
            '    "net/http"\n'
            ')\n'
        )
        imports = go_ts.extract_imports(code)
        assert "fmt" in imports
        assert "http" in imports


# ===================================================================
# Ruby Tests
# ===================================================================

class TestRubyTreeSitter:

    def test_class_and_module(self, ruby_ts):
        code = (
            "class UserService\n"
            "  def initialize(name)\n"
            "    @name = name\n"
            "  end\n"
            "end\n"
            "\n"
            "module Api\n"
            "end\n"
        )
        symbols = ruby_ts.extract_symbols(code, "test.rb")
        names = {s.name for s in symbols}
        assert "UserService" in names
        assert "Api" in names

    def test_methods(self, ruby_ts):
        code = (
            "class Foo\n"
            "  def bar\n"
            "  end\n"
            "\n"
            "  def self.create\n"
            "  end\n"
            "end\n"
        )
        symbols = ruby_ts.extract_symbols(code, "test.rb")
        names = {s.name for s in symbols}
        assert "bar" in names
        assert "self.create" in names

    def test_imports_delegates_to_regex(self, ruby_ts):
        code = 'require "json"\nrequire_relative "helper"\n'
        imports = ruby_ts.extract_imports(code)
        assert "json" in imports


# ===================================================================
# Fallback Tests
# ===================================================================

class TestFallback:
    """Verify that parsers degrade gracefully when tree-sitter is disabled."""

    def test_swift_fallback(self):
        pytest.importorskip("tree_sitter")
        pytest.importorskip("tree_sitter_swift")
        from analyzer.parsers.swift_ts import SwiftTreeSitterParser
        parser = SwiftTreeSitterParser()
        parser._ts_available = False
        code = "public class Foo {}\n"
        symbols = parser.extract_symbols(code, "test.swift")
        assert any(s.name == "Foo" for s in symbols)

    def test_typescript_fallback(self):
        pytest.importorskip("tree_sitter")
        pytest.importorskip("tree_sitter_typescript")
        from analyzer.parsers.typescript_ts import TypeScriptTreeSitterParser
        parser = TypeScriptTreeSitterParser()
        parser._ts_available = False
        code = "export class Bar {}\n"
        symbols = parser.extract_symbols(code, "test.ts")
        assert any(s.name == "Bar" for s in symbols)

    def test_rust_fallback(self):
        pytest.importorskip("tree_sitter")
        pytest.importorskip("tree_sitter_rust")
        from analyzer.parsers.rust_ts import RustTreeSitterParser
        parser = RustTreeSitterParser()
        parser._ts_available = False
        code = "pub struct Baz {}\n"
        symbols = parser.extract_symbols(code, "lib.rs")
        assert any(s.name == "Baz" for s in symbols)

    def test_python_fallback(self):
        pytest.importorskip("tree_sitter")
        pytest.importorskip("tree_sitter_python")
        from analyzer.parsers.python_ts import PythonTreeSitterParser
        parser = PythonTreeSitterParser()
        parser._ts_available = False
        code = "class Qux:\n    pass\n"
        symbols = parser.extract_symbols(code, "test.py")
        assert any(s.name == "Qux" for s in symbols)


# ===================================================================
# Registry Tests
# ===================================================================

class TestRegistry:
    """Test that the parser registry loads correctly."""

    def test_parsers_dict_has_all_languages(self):
        from analyzer.parsers import PARSERS
        for lang in ("swift", "typescript", "javascript", "rust", "python", "go", "ruby"):
            assert lang in PARSERS

    def test_parsers_implement_base_interface(self):
        from analyzer.parsers import PARSERS
        for lang, parser in PARSERS.items():
            assert hasattr(parser, "extract_symbols")
            assert hasattr(parser, "extract_imports")
            assert hasattr(parser, "detect_framework")
            assert hasattr(parser, "extract_file_doc")
            assert hasattr(parser, "detect_ports")
            assert hasattr(parser, "detect_api_endpoints")

    def test_tree_sitter_parsers_used_when_available(self):
        """If tree-sitter is installed, PARSERS should use tree-sitter parsers."""
        try:
            import tree_sitter
            import tree_sitter_swift
        except ImportError:
            pytest.skip("tree-sitter-swift not installed")
        from analyzer.parsers import PARSERS
        from analyzer.parsers.tree_sitter_base import TreeSitterParser
        assert isinstance(PARSERS["swift"], TreeSitterParser)
