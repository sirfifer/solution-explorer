"""Deeper tests for the ArchitectureScanner.

Covers complex logic paths not exercised by the basic tests in test_analyzer.py:
component discovery (markers, vendored/content dirs), type promotion,
relationship detection, framework priority, metrics, symbol capping, and
edge cases (empty repos, binary files, oversized files).
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from analyzer.models import Architecture
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


def _all_components(arch):
    """Flatten the component tree into a list of dicts."""
    result = []
    def _walk(comps):
        for c in comps:
            result.append(c)
            _walk(c.get("children", []))
    _walk(arch.components)
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def swift_app(tmp_path):
    """Create a SwiftUI app with Package.swift."""
    pkg = tmp_path / "Package.swift"
    pkg.write_text(
        "// swift-tools-version:5.9\nimport PackageDescription\n"
    )
    src = tmp_path / "Sources"
    src.mkdir()
    (src / "ContentView.swift").write_text(
        "import SwiftUI\n\n"
        "struct ContentView: View {\n"
        "    var body: some View {\n"
        '        Text("Hello")\n'
        "    }\n"
        "}\n"
    )
    (src / "AppDelegate.swift").write_text(
        "import SwiftUI\n\n"
        "@main\n"
        "struct MyApp: App {\n"
        "    var body: some Scene {\n"
        "        WindowGroup { ContentView() }\n"
        "    }\n"
        "}\n"
    )
    return tmp_path


@pytest.fixture
def uikit_app(tmp_path):
    """Create a UIKit-based iOS app."""
    pkg = tmp_path / "Package.swift"
    pkg.write_text("// swift-tools-version:5.9\n")
    src = tmp_path / "Sources"
    src.mkdir()
    (src / "ViewController.swift").write_text(
        "import UIKit\n\n"
        "class ViewController: UIViewController {\n"
        "    override func viewDidLoad() {\n"
        "        super.viewDidLoad()\n"
        "    }\n"
        "}\n"
    )
    # Info.plist to trigger application type
    (tmp_path / "Info.plist").write_text(
        '<?xml version="1.0"?>\n<plist version="1.0"><dict>'
        "<key>CFBundleName</key><string>MyApp</string>"
        "</dict></plist>\n"
    )
    return tmp_path


@pytest.fixture
def flask_service(tmp_path):
    """Create a Flask service."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "api"\n'
    )
    (tmp_path / "app.py").write_text(
        "from flask import Flask\n"
        "app = Flask(__name__)\n\n"
        "@app.route('/users')\n"
        "def get_users():\n"
        "    return []\n"
    )
    return tmp_path


@pytest.fixture
def fastapi_service(tmp_path):
    """Create a FastAPI service."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fast-api"\n'
    )
    (tmp_path / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n\n"
        "@app.get('/items')\n"
        "def list_items():\n"
        "    return []\n"
    )
    return tmp_path


@pytest.fixture
def django_service(tmp_path):
    """Create a Django project."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "webapp"\n'
    )
    (tmp_path / "manage.py").write_text(
        "import django\nfrom django.core.management import execute_from_command_line\n"
    )
    (tmp_path / "views.py").write_text(
        "from django.http import JsonResponse\n"
        "def index(request):\n"
        "    return JsonResponse({'ok': True})\n"
    )
    return tmp_path


@pytest.fixture
def multi_component_repo(tmp_path):
    """Create a repo with frontend + backend components."""
    # Frontend
    fe = tmp_path / "frontend"
    fe.mkdir()
    (fe / "package.json").write_text(
        json.dumps({"name": "frontend", "dependencies": {"react": "^18.0"}})
    )
    (fe / "App.tsx").write_text(
        'import React from "react";\n'
        "export function App() { return <div/>; }\n"
    )

    # Backend
    be = tmp_path / "backend"
    be.mkdir()
    (be / "pyproject.toml").write_text('[project]\nname = "backend"\n')
    (be / "server.py").write_text(
        "from flask import Flask\n"
        "app = Flask(__name__)\n\n"
        "@app.route('/api/data')\n"
        "def data():\n"
        "    return {}\n"
    )

    return tmp_path


# ===================================================================
# Component Discovery
# ===================================================================


class TestComponentDiscovery:
    """Tests for component marker file detection."""

    def test_dockerfile_detected_as_service(self, tmp_path):
        """Dockerfile creates a component of type 'service'."""
        svc = tmp_path / "worker"
        svc.mkdir()
        (svc / "Dockerfile").write_text("FROM python:3.12\nCMD ['python', 'run.py']\n")
        (svc / "run.py").write_text("print('hello')\n")

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        comp = _find_component(arch, name="worker")
        assert comp is not None
        assert comp["type"] == "service"

    def test_docker_compose_detected_as_infrastructure(self, tmp_path):
        """docker-compose.yml creates a component of type 'infrastructure'."""
        (tmp_path / "docker-compose.yml").write_text(
            "version: '3'\nservices:\n  web:\n    build: .\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        # Root component should have a docker-compose config entry
        root = arch.components[0]
        config_types = [c.get("type") for c in root.get("config_files", [])]
        assert "docker-compose" in config_types

    def test_cargo_toml_detected_as_rust_package(self, tmp_path):
        """Cargo.toml creates a Rust package component."""
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "mylib"\nversion = "0.1.0"\n'
        )
        src = tmp_path / "src"
        src.mkdir()
        (src / "lib.rs").write_text("pub fn add(a: i32, b: i32) -> i32 { a + b }\n")

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["language"] == "rust"

    def test_go_mod_detected_as_go_module(self, tmp_path):
        """go.mod creates a Go module component."""
        (tmp_path / "go.mod").write_text("module example.com/mymod\ngo 1.21\n")
        (tmp_path / "main.go").write_text(
            "package main\nimport \"fmt\"\nfunc main() { fmt.Println(\"hi\") }\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["language"] == "go"

    def test_gemfile_detected_as_ruby_package(self, tmp_path):
        """Gemfile creates a Ruby package component."""
        (tmp_path / "Gemfile").write_text(
            "source 'https://rubygems.org'\ngem 'sinatra'\n"
        )
        (tmp_path / "app.rb").write_text(
            "require 'sinatra'\nget '/' do\n  'hello'\nend\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["language"] == "ruby"

    def test_skips_vendored_directories(self, tmp_path):
        """Vendored directories with their own build systems are collapsed."""
        # Create a vendored third-party repo with sufficient subdirectories
        vendor = tmp_path / "third_party" / "somelib"
        vendor.mkdir(parents=True)
        (vendor / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.0)\n")
        (vendor / "LICENSE").write_text("MIT License\n")
        # Need 5+ subdirectories to qualify as vendored
        for d in ("src", "include", "lib", "tests", "docs", "examples"):
            (vendor / d).mkdir()
            (vendor / d / "dummy.cpp").write_text("// code\n")

        # Main project
        (tmp_path / "package.json").write_text('{"name":"main"}')
        (tmp_path / "index.ts").write_text("const x = 1;\n")

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        # The vendored files should not be individually scanned
        all_files = [f["path"] for f in arch.files]
        vendored_files = [f for f in all_files if "somelib" in f and "dummy" in f]
        assert len(vendored_files) == 0

    def test_skips_content_only_directories(self, tmp_path):
        """Content-only directories (docs, wiki, assets) get type 'content'."""
        (tmp_path / "package.json").write_text('{"name":"proj"}')
        (tmp_path / "index.ts").write_text("const x = 1;\n")

        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text("# User Guide\nSome text.\n")
        (docs / "api.md").write_text("# API Docs\nMore text.\n")

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        docs_comp = _find_component(arch, name="docs")
        if docs_comp is not None:
            assert docs_comp["type"] == "content"

    def test_nested_component_markers(self, tmp_path):
        """Handles nested packages (package inside package)."""
        # Outer package
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "monorepo"})
        )

        # Inner package
        inner = tmp_path / "packages" / "core"
        inner.mkdir(parents=True)
        (inner / "package.json").write_text(
            json.dumps({"name": "@mono/core"})
        )
        (inner / "index.ts").write_text("export const VERSION = '1.0';\n")

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        core = _find_component(arch, name="@mono/core")
        assert core is not None


# ===================================================================
# Type Promotion
# ===================================================================


class TestTypePromotion:
    """Tests for component type promotion based on frameworks and signals."""

    def test_flask_service_promoted_to_api_server(self, flask_service):
        """Component with Flask framework gets promoted to api-server."""
        scanner = ArchitectureScanner(flask_service)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["type"] == "api-server"

    def test_fastapi_promoted_to_api_server(self, fastapi_service):
        """Component with FastAPI framework gets promoted to api-server."""
        scanner = ArchitectureScanner(fastapi_service)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["type"] == "api-server"

    def test_django_promoted_to_api_server(self, django_service):
        """Component with Django framework gets promoted to api-server."""
        scanner = ArchitectureScanner(django_service)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["type"] == "api-server"

    def test_express_deps_promoted_to_api_server(self, tmp_path):
        """Component with express dependency gets promoted to api-server."""
        (tmp_path / "package.json").write_text(
            json.dumps({
                "name": "api",
                "dependencies": {"express": "^4.18"},
            })
        )
        (tmp_path / "server.js").write_text(
            'const express = require("express");\n'
            "const app = express();\n"
            "app.listen(3000);\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["type"] == "api-server"

    def test_dockerfile_component_stays_service(self, tmp_path):
        """Component detected via Dockerfile retains 'service' type."""
        svc = tmp_path / "worker"
        svc.mkdir()
        (svc / "Dockerfile").write_text("FROM node:18\n")
        (svc / "index.js").write_text("console.log('worker');\n")

        # Root marker
        (tmp_path / "package.json").write_text('{"name":"proj"}')
        (tmp_path / "readme.md").write_text("# Project\n")

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        worker = _find_component(arch, name="worker")
        assert worker is not None
        assert worker["type"] == "service"

    def test_swiftui_app_promoted_to_ios_client(self, tmp_path):
        """SwiftUI component with Info.plist gets promoted to ios-client."""
        (tmp_path / "Package.swift").write_text("// swift-tools-version:5.9\n")
        (tmp_path / "Info.plist").write_text(
            '<?xml version="1.0"?>\n<plist version="1.0"><dict>'
            "<key>CFBundleName</key><string>TestApp</string>"
            "</dict></plist>\n"
        )
        src = tmp_path / "Sources"
        src.mkdir()
        (src / "App.swift").write_text(
            "import SwiftUI\n\n"
            "struct ContentView: View {\n"
            "    var body: some View { Text(\"Hi\") }\n"
            "}\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["type"] == "ios-client"

    def test_uikit_app_promoted_to_ios_client(self, uikit_app):
        """UIKit component with Info.plist gets promoted to ios-client."""
        scanner = ArchitectureScanner(uikit_app)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["type"] == "ios-client"

    def test_react_dep_promoted_to_web_client(self, tmp_path):
        """Component with React dependency gets promoted to web-client."""
        (tmp_path / "package.json").write_text(
            json.dumps({
                "name": "webapp",
                "dependencies": {"react": "^18.0", "react-dom": "^18.0"},
            })
        )
        (tmp_path / "App.tsx").write_text(
            'import React from "react";\n'
            "export default function App() { return <div/>; }\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["type"] == "web-client"

    def test_nextjs_promoted_to_web_client(self, tmp_path):
        """Component with Next.js dependency gets promoted to web-client."""
        (tmp_path / "package.json").write_text(
            json.dumps({
                "name": "website",
                "dependencies": {"next": "^14.0", "react": "^18.0"},
            })
        )
        (tmp_path / "page.tsx").write_text(
            'import React from "react";\n'
            "export default function Home() { return <h1>Hello</h1>; }\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["type"] == "web-client"


# ===================================================================
# Relationship Detection
# ===================================================================


class TestRelationshipDetection:
    """Tests for inter-component relationship discovery."""

    def test_import_based_relationship(self, tmp_path):
        """Detects import-based relationships between components."""
        # Component A imports component B by name
        comp_a = tmp_path / "client"
        comp_a.mkdir()
        (comp_a / "package.json").write_text(
            json.dumps({"name": "client", "dependencies": {"react": "^18"}})
        )
        (comp_a / "api.ts").write_text(
            'import { helper } from "shared";\n'
            "export const data = helper();\n"
        )

        comp_b = tmp_path / "shared"
        comp_b.mkdir()
        (comp_b / "package.json").write_text(
            json.dumps({"name": "shared"})
        )
        (comp_b / "index.ts").write_text("export function helper() { return 1; }\n")

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        # Should find an import relationship
        import_rels = [
            r for r in arch.relationships if r["type"] == "import"
        ]
        assert len(import_rels) > 0

    def test_http_client_pattern_detection(self, multi_component_repo):
        """Detects HTTP client patterns (fetch, requests, etc.)."""
        # Add a fetch call to the frontend
        fe = multi_component_repo / "frontend"
        (fe / "api.ts").write_text(
            "export async function fetchData() {\n"
            "  const res = await fetch('http://localhost:5000/api/data');\n"
            "  return res.json();\n"
            "}\n"
        )

        scanner = ArchitectureScanner(multi_component_repo)
        arch = scanner.scan()

        # Should detect HTTP relationship between frontend and backend
        http_rels = [r for r in arch.relationships if r["type"] == "http"]
        assert len(http_rels) > 0

    def test_shared_port_connection(self, tmp_path):
        """Detects when component A listens on a port and component B references it."""
        # Server component (listens on port 8080)
        server = tmp_path / "server"
        server.mkdir()
        (server / "pyproject.toml").write_text('[project]\nname = "server"\n')
        (server / "main.py").write_text(
            "from flask import Flask\n"
            "app = Flask(__name__)\n"
            "app.run(port=8080)\n"
        )

        # Client component (references port 8080)
        client = tmp_path / "client"
        client.mkdir()
        (client / "package.json").write_text(
            json.dumps({"name": "client", "dependencies": {"react": "^18"}})
        )
        (client / "config.ts").write_text(
            "export const API_URL = 'http://localhost:8080/api';\n"
        )
        (client / "api.ts").write_text(
            "export async function getData() {\n"
            "  return fetch('http://localhost:8080/data');\n"
            "}\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        # Should detect port-based HTTP relationship
        http_rels = [r for r in arch.relationships if r["type"] == "http"]
        assert len(http_rels) > 0

    def test_client_to_single_server_fallback(self, tmp_path):
        """When there is one client and one server with no explicit URL match,
        the scanner infers a connection (single-backend fallback)."""
        # Server
        be = tmp_path / "api"
        be.mkdir()
        (be / "pyproject.toml").write_text('[project]\nname = "api"\n')
        (be / "app.py").write_text(
            "from flask import Flask\n"
            "app = Flask(__name__)\n"
        )

        # Client with HTTP calls but no explicit URL to the server
        fe = tmp_path / "web"
        fe.mkdir()
        (fe / "package.json").write_text(
            json.dumps({"name": "web", "dependencies": {"react": "^18"}})
        )
        (fe / "hooks.ts").write_text(
            "export async function useFetch(path: string) {\n"
            "  return fetch(path);\n"
            "}\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        # Should detect an inferred HTTP relationship
        http_rels = [r for r in arch.relationships if r["type"] == "http"]
        assert len(http_rels) >= 1


# ===================================================================
# Framework Detection
# ===================================================================


class TestFrameworkDetection:
    """Tests for framework detection and priority."""

    def test_swift_detects_swiftui(self, swift_app):
        """Swift components detect SwiftUI framework."""
        scanner = ArchitectureScanner(swift_app)
        arch = scanner.scan()

        # The SwiftUI files are under Sources/, so the framework is set on the
        # child component that owns the .swift files, not necessarily the root.
        all_comps = _all_components(arch)
        frameworks = [c.get("framework") for c in all_comps if c.get("framework")]
        assert "SwiftUI" in frameworks

    def test_swift_detects_uikit(self, uikit_app):
        """Swift components detect UIKit framework."""
        scanner = ArchitectureScanner(uikit_app)
        arch = scanner.scan()

        root = arch.components[0]
        assert root.get("framework") == "UIKit"

    def test_typescript_detects_react(self, tmp_path):
        """TypeScript components detect React."""
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "app", "dependencies": {"react": "^18"}})
        )
        (tmp_path / "App.tsx").write_text(
            'import React from "react";\n'
            "export function App() { return <div/>; }\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        assert root.get("framework") == "React"

    def test_typescript_detects_nextjs_over_react(self, tmp_path):
        """Next.js is detected over React due to higher priority."""
        (tmp_path / "package.json").write_text(
            json.dumps({
                "name": "site",
                "dependencies": {"next": "^14", "react": "^18"},
            })
        )
        # One file imports react
        (tmp_path / "App.tsx").write_text(
            'import React from "react";\n'
            "export function App() { return <div/>; }\n"
        )
        # Another file imports next
        (tmp_path / "page.tsx").write_text(
            'import Link from "next/link";\n'
            "export default function Home() { return <Link href='/'>Home</Link>; }\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        # Next.js has higher priority than React
        assert root.get("framework") == "Next.js"

    def test_python_detects_flask(self, flask_service):
        """Python components detect Flask."""
        scanner = ArchitectureScanner(flask_service)
        arch = scanner.scan()

        root = arch.components[0]
        assert root.get("framework") == "Flask"

    def test_python_detects_fastapi(self, fastapi_service):
        """Python components detect FastAPI."""
        scanner = ArchitectureScanner(fastapi_service)
        arch = scanner.scan()

        root = arch.components[0]
        assert root.get("framework") == "FastAPI"

    def test_python_detects_django(self, django_service):
        """Python components detect Django."""
        scanner = ArchitectureScanner(django_service)
        arch = scanner.scan()

        root = arch.components[0]
        assert root.get("framework") == "Django"

    def test_framework_priority_more_specific_wins(self, tmp_path):
        """More specific framework (FastAPI) wins over less specific (Starlette)."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "app"\n')
        # One file uses starlette
        (tmp_path / "base.py").write_text(
            "from starlette.responses import JSONResponse\n"
            "def hello():\n"
            "    return JSONResponse({'ok': True})\n"
        )
        # Another file uses fastapi (which is built on starlette)
        (tmp_path / "main.py").write_text(
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        # FastAPI (priority 2) should win over Starlette (priority 1)
        assert root.get("framework") == "FastAPI"


# ===================================================================
# Metrics
# ===================================================================


class TestMetrics:
    """Tests for component metric computation."""

    def test_component_metrics_include_file_count(self, flask_service):
        """Component metrics include files count."""
        scanner = ArchitectureScanner(flask_service)
        arch = scanner.scan()

        root = arch.components[0]
        metrics = root.get("metrics", {})
        assert "files" in metrics
        assert metrics["files"] > 0

    def test_component_metrics_include_line_count(self, flask_service):
        """Component metrics include total lines."""
        scanner = ArchitectureScanner(flask_service)
        arch = scanner.scan()

        root = arch.components[0]
        metrics = root.get("metrics", {})
        assert "lines" in metrics
        assert metrics["lines"] > 0

    def test_component_metrics_include_size(self, flask_service):
        """Component metrics include total size in bytes."""
        scanner = ArchitectureScanner(flask_service)
        arch = scanner.scan()

        root = arch.components[0]
        metrics = root.get("metrics", {})
        assert "size_bytes" in metrics
        assert metrics["size_bytes"] > 0

    def test_component_metrics_include_symbol_count(self, flask_service):
        """Component metrics include symbol count."""
        scanner = ArchitectureScanner(flask_service)
        arch = scanner.scan()

        root = arch.components[0]
        metrics = root.get("metrics", {})
        assert "symbols" in metrics

    def test_language_counts_aggregated(self, multi_component_repo):
        """Language line counts are correctly aggregated across the project."""
        scanner = ArchitectureScanner(multi_component_repo)
        arch = scanner.scan()

        langs = arch.stats.get("languages", {})
        # Should have both TypeScript (frontend) and Python (backend)
        assert "typescript" in langs
        assert "python" in langs
        assert langs["typescript"] > 0
        assert langs["python"] > 0


# ===================================================================
# Symbol Cap
# ===================================================================


class TestSymbolCap:
    """Tests for the max_symbols truncation logic."""

    def test_max_symbols_zero_means_unlimited(self, tmp_path):
        """max_symbols=0 keeps all symbols."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "lib"\n')
        # Create many symbols
        code_lines = []
        for i in range(20):
            code_lines.append(f"def func_{i}():\n    pass\n")
        (tmp_path / "many.py").write_text("\n".join(code_lines))

        scanner = ArchitectureScanner(tmp_path, max_symbols=0)
        arch = scanner.scan()

        assert len(arch.symbols) >= 20

    def test_max_symbols_truncates_with_priority(self, tmp_path):
        """max_symbols=N truncates, keeping types before functions."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "lib"\n')

        # Create a mix of classes and functions
        code = (
            "class ImportantType:\n    pass\n\n"
            "class AnotherType:\n    pass\n\n"
        )
        for i in range(15):
            code += f"def helper_{i}():\n    pass\n\n"

        (tmp_path / "code.py").write_text(code)

        scanner = ArchitectureScanner(tmp_path, max_symbols=5)
        arch = scanner.scan()

        assert len(arch.symbols) <= 5

        # Types (classes) should be prioritized over functions
        symbol_kinds = [s["kind"] for s in arch.symbols]
        class_syms = [k for k in symbol_kinds if k == "class"]
        assert len(class_syms) >= 2  # Both classes should survive the cap


# ===================================================================
# Edge Cases
# ===================================================================


class TestEdgeCases:
    """Tests for edge cases and unusual repository structures."""

    def test_empty_repository(self, tmp_path):
        """Empty repository (no code files) produces valid Architecture."""
        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        assert isinstance(arch, Architecture)
        assert arch.stats["total_files"] == 0
        assert arch.stats["total_lines"] == 0

    def test_repo_with_only_config_files(self, tmp_path):
        """Repository with only config/marker files and no code."""
        (tmp_path / "package.json").write_text('{"name":"config-only"}')
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions":{}}')
        (tmp_path / ".eslintrc").write_text("{}")

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        assert isinstance(arch, Architecture)
        # JSON files are scanned since .json is in LANGUAGE_MAP
        assert arch.stats["total_components"] >= 1

    def test_binary_files_are_skipped(self, tmp_path):
        """Binary files (images, compiled) are skipped during scanning."""
        (tmp_path / "package.json").write_text('{"name":"proj"}')
        (tmp_path / "index.ts").write_text("export const x = 1;\n")
        # Binary files
        (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        (tmp_path / "app.o").write_bytes(b"\x7fELF" + b"\x00" * 100)
        (tmp_path / "data.sqlite").write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        file_paths = [f["path"] for f in arch.files]
        assert not any(p.endswith(".png") for p in file_paths)
        assert not any(p.endswith(".o") for p in file_paths)
        assert not any(p.endswith(".sqlite") for p in file_paths)

    def test_large_files_beyond_max_file_size_skipped(self, tmp_path):
        """Files exceeding max_file_size are skipped."""
        (tmp_path / "package.json").write_text('{"name":"proj"}')
        (tmp_path / "small.ts").write_text("export const x = 1;\n")
        # Create a file just over the limit
        (tmp_path / "huge.ts").write_text("x" * 2000)

        scanner = ArchitectureScanner(tmp_path, max_file_size=1000)
        arch = scanner.scan()

        file_paths = [f["path"] for f in arch.files]
        assert any("small.ts" in p for p in file_paths)
        assert not any("huge.ts" in p for p in file_paths)

    def test_hidden_directories_skipped(self, tmp_path):
        """Hidden directories (starting with .) are skipped."""
        (tmp_path / "package.json").write_text('{"name":"proj"}')
        (tmp_path / "index.ts").write_text("export const x = 1;\n")

        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.ts").write_text("const secret = 'password';\n")

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        file_paths = [f["path"] for f in arch.files]
        assert not any("secret.ts" in p for p in file_paths)

    def test_node_modules_skipped(self, tmp_path):
        """node_modules directory is skipped."""
        (tmp_path / "package.json").write_text('{"name":"proj"}')
        (tmp_path / "index.ts").write_text("export const x = 1;\n")

        nm = tmp_path / "node_modules" / "lodash"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {};\n")

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        file_paths = [f["path"] for f in arch.files]
        assert not any("node_modules" in p for p in file_paths)

    def test_empty_files_skipped(self, tmp_path):
        """Empty files (0 bytes) are skipped."""
        (tmp_path / "package.json").write_text('{"name":"proj"}')
        (tmp_path / "real.ts").write_text("export const x = 1;\n")
        (tmp_path / "empty.ts").write_text("")

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        file_paths = [f["path"] for f in arch.files]
        assert any("real.ts" in p for p in file_paths)
        assert not any(p.endswith("empty.ts") for p in file_paths)

    def test_output_is_json_serializable(self, multi_component_repo):
        """Full scan output is JSON-serializable with no errors."""
        scanner = ArchitectureScanner(multi_component_repo)
        arch = scanner.scan()

        result = json.dumps(asdict(arch), default=str)
        parsed = json.loads(result)
        assert parsed["name"] == multi_component_repo.name


# ===================================================================
# Rust Server Detection
# ===================================================================


class TestRustServerDetection:
    """Tests for Rust server framework detection via Cargo.toml dependencies."""

    def test_axum_dependency_promotes_to_api_server(self, tmp_path):
        """Cargo.toml with axum dependency promotes component to api-server."""
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "my-api"\nversion = "0.1.0"\n\n'
            '[dependencies]\naxum = "0.7"\ntokio = { version = "1", features = ["full"] }\n'
        )
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.rs").write_text(
            "use axum::{Router, routing::get};\n\n"
            "async fn hello() -> &'static str { \"hello\" }\n\n"
            "#[tokio::main]\n"
            "async fn main() {\n"
            "    let app = Router::new().route(\"/\", get(hello));\n"
            '    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await.unwrap();\n'
            "    axum::serve(listener, app).await.unwrap();\n"
            "}\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["type"] == "api-server"

    def test_clap_without_server_promotes_to_cli_tool(self, tmp_path):
        """Cargo.toml with clap but no server framework promotes to cli-tool."""
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "my-cli"\nversion = "0.1.0"\n\n'
            '[dependencies]\nclap = { version = "4", features = ["derive"] }\n'
        )
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.rs").write_text(
            "use clap::Parser;\n\n"
            "#[derive(Parser)]\n"
            "struct Args { #[arg(short)] name: String }\n\n"
            "fn main() {\n"
            "    let args = Args::parse();\n"
            '    println!("Hello, {}!", args.name);\n'
            "}\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        assert root["type"] == "cli-tool"


# ===================================================================
# Go Framework Detection
# ===================================================================


class TestGoFrameworkDetection:
    """Tests for Go framework and server detection."""

    def test_gin_module_detected(self, tmp_path):
        """Go module using gin framework detects the framework."""
        (tmp_path / "go.mod").write_text(
            "module example.com/api\ngo 1.21\n\n"
            "require github.com/gin-gonic/gin v1.9.1\n"
        )
        (tmp_path / "main.go").write_text(
            'package main\n\n'
            'import "github.com/gin-gonic/gin"\n\n'
            "func main() {\n"
            "    r := gin.Default()\n"
            '    r.GET("/ping", func(c *gin.Context) {\n'
            '        c.JSON(200, gin.H{"message": "pong"})\n'
            "    })\n"
            '    r.Run(":8080")\n'
            "}\n"
        )

        scanner = ArchitectureScanner(tmp_path)
        arch = scanner.scan()

        root = arch.components[0]
        assert root.get("framework") == "Gin"


# ===================================================================
# Stats Integrity
# ===================================================================


class TestStatsIntegrity:
    """Tests for overall stats accuracy."""

    def test_stats_total_components(self, multi_component_repo):
        """total_components reflects all discovered components."""
        scanner = ArchitectureScanner(multi_component_repo)
        arch = scanner.scan()

        # Root + frontend + backend = at least 3
        assert arch.stats["total_components"] >= 3

    def test_stats_total_files(self, multi_component_repo):
        """total_files reflects all scanned files."""
        scanner = ArchitectureScanner(multi_component_repo)
        arch = scanner.scan()

        assert arch.stats["total_files"] == len(arch.files)

    def test_stats_total_symbols(self, multi_component_repo):
        """total_symbols reflects all extracted symbols."""
        scanner = ArchitectureScanner(multi_component_repo)
        arch = scanner.scan()

        assert arch.stats["total_symbols"] == len(arch.symbols)

    def test_stats_total_relationships(self, multi_component_repo):
        """total_relationships reflects all detected relationships."""
        scanner = ArchitectureScanner(multi_component_repo)
        arch = scanner.scan()

        assert arch.stats["total_relationships"] == len(arch.relationships)
