"""Tests for the architecture analyzer."""

import json
import sys
from pathlib import Path

import pytest

# Add project root to path so we can import analyze
sys.path.insert(0, str(Path(__file__).parent.parent))
from analyze import (
    Architecture,
    ArchitectureScanner,
    GoParser,
    MultiRepoOrchestrator,
    PythonParser,
    RustParser,
    SwiftParser,
    TypeScriptParser,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_repo(tmp_path):
    """Create a minimal repo structure for testing."""
    # Root package.json
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "test-project",
        "description": "A test project",
    }))

    # A source file
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.ts").write_text(
        'import { helper } from "./utils";\n'
        "\n"
        "export function main(): void {\n"
        '  console.log("hello");\n'
        "}\n"
    )
    (src / "utils.ts").write_text(
        "export function helper(): string {\n"
        '  return "help";\n'
        "}\n"
    )

    return tmp_path


@pytest.fixture
def temp_python_repo(tmp_path):
    """Create a minimal Python repo."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "test-pkg"\ndescription = "A test package"\n'
    )
    (tmp_path / "main.py").write_text(
        'import os\n'
        '\n'
        'class MyApp:\n'
        '    """Main application class."""\n'
        '    def run(self):\n'
        '        port = int(os.environ.get("PORT", 8080))\n'
        '        print(f"Running on {port}")\n'
    )
    return tmp_path


@pytest.fixture
def temp_multi_repo(tmp_path):
    """Create two repos and a config file for multi-repo testing."""
    # Repo A (local)
    repo_a = tmp_path / "repo-a"
    repo_a.mkdir()
    (repo_a / "package.json").write_text(json.dumps({
        "name": "backend",
        "description": "Backend service",
    }))
    src_a = repo_a / "src"
    src_a.mkdir()
    (src_a / "server.ts").write_text(
        "export function startServer(port: number): void {\n"
        "  console.log(`Listening on ${port}`);\n"
        "}\n"
    )

    # Repo B (local)
    repo_b = tmp_path / "repo-b"
    repo_b.mkdir()
    (repo_b / "package.json").write_text(json.dumps({
        "name": "frontend",
        "description": "Frontend app",
    }))
    src_b = repo_b / "src"
    src_b.mkdir()
    (src_b / "app.ts").write_text(
        'import { api } from "./api";\n'
        "\n"
        "export function renderApp(): void {\n"
        '  console.log("rendering");\n'
        "}\n"
    )

    # Config
    config = {
        "solution": "Test Platform",
        "description": "Backend and frontend",
        "repositories": [
            {"name": "backend", "path": str(repo_a)},
            {"name": "frontend", "path": str(repo_b)},
        ],
        "cross_repo_relationships": [
            {
                "source_repo": "frontend",
                "target_repo": "backend",
                "type": "http",
                "label": "REST API",
            }
        ],
    }
    config_path = tmp_path / "solution-explorer.json"
    config_path.write_text(json.dumps(config))

    return tmp_path, config_path


# ---------------------------------------------------------------------------
# Scanner Tests
# ---------------------------------------------------------------------------


class TestArchitectureScanner:
    def test_scan_produces_architecture(self, temp_repo):
        scanner = ArchitectureScanner(temp_repo)
        arch = scanner.scan()

        assert isinstance(arch, Architecture)
        assert arch.name == temp_repo.name
        assert arch.stats["total_files"] > 0
        assert arch.stats["total_lines"] > 0

    def test_scan_detects_components(self, temp_repo):
        scanner = ArchitectureScanner(temp_repo)
        arch = scanner.scan()

        assert arch.stats["total_components"] >= 1

    def test_scan_extracts_symbols(self, temp_repo):
        scanner = ArchitectureScanner(temp_repo)
        arch = scanner.scan()

        assert arch.stats["total_symbols"] > 0
        # After scan(), symbols/files are dicts (from asdict conversion)
        symbol_names = [s["name"] if isinstance(s, dict) else s.name for s in arch.symbols]
        assert "main" in symbol_names

    def test_scan_detects_languages(self, temp_repo):
        scanner = ArchitectureScanner(temp_repo)
        arch = scanner.scan()

        assert "typescript" in arch.stats["languages"]

    def test_scan_detects_files(self, temp_repo):
        scanner = ArchitectureScanner(temp_repo)
        arch = scanner.scan()

        file_paths = [f["path"] if isinstance(f, dict) else f.path for f in arch.files]
        assert any("index.ts" in p for p in file_paths)
        assert any("utils.ts" in p for p in file_paths)

    def test_scan_python_repo(self, temp_python_repo):
        scanner = ArchitectureScanner(temp_python_repo)
        arch = scanner.scan()

        assert "python" in arch.stats["languages"]
        symbol_names = [s["name"] if isinstance(s, dict) else s.name for s in arch.symbols]
        assert "MyApp" in symbol_names

    def test_max_file_size_skips_large_files(self, tmp_path):
        (tmp_path / "package.json").write_text('{"name":"test"}')
        (tmp_path / "big.ts").write_text("x" * 1000)
        (tmp_path / "small.ts").write_text("const x = 1;\n")

        scanner = ArchitectureScanner(tmp_path, max_file_size=500)
        arch = scanner.scan()

        file_paths = [f["path"] if isinstance(f, dict) else f.path for f in arch.files]
        assert any("small.ts" in p for p in file_paths)
        assert not any("big.ts" in p for p in file_paths)

    def test_output_serializable(self, temp_repo):
        """Architecture output must be JSON-serializable."""
        from dataclasses import asdict

        scanner = ArchitectureScanner(temp_repo)
        arch = scanner.scan()

        # Should not raise
        result = json.dumps(asdict(arch), default=str)
        parsed = json.loads(result)
        assert parsed["name"] == temp_repo.name


# ---------------------------------------------------------------------------
# Multi-Repo Orchestrator Tests
# ---------------------------------------------------------------------------


class TestMultiRepoOrchestrator:
    def test_merge_produces_combined_architecture(self, temp_multi_repo):
        _, config_path = temp_multi_repo
        orch = MultiRepoOrchestrator(config_path)
        arch = orch.run()

        assert arch.name == "Test Platform"
        assert arch.description == "Backend and frontend"
        assert len(arch.repositories) == 2

    def test_merge_creates_repository_components(self, temp_multi_repo):
        _, config_path = temp_multi_repo
        orch = MultiRepoOrchestrator(config_path)
        arch = orch.run()

        # Top-level components should be repository type
        repo_names = [c["name"] for c in arch.components]
        assert "backend" in repo_names
        assert "frontend" in repo_names

        for comp in arch.components:
            assert comp["type"] == "repository"
            assert comp["id"].startswith("repo:")

    def test_merge_prefixes_ids(self, temp_multi_repo):
        _, config_path = temp_multi_repo
        orch = MultiRepoOrchestrator(config_path)
        arch = orch.run()

        # All symbols should be prefixed with repo name
        for sym in arch.symbols:
            s = sym if isinstance(sym, dict) else sym.__dict__
            sid = s["id"] if isinstance(s, dict) else s.id
            assert sid.startswith("backend/") or sid.startswith("frontend/")

        # All files should be prefixed
        for fi in arch.files:
            f = fi if isinstance(fi, dict) else fi.__dict__
            fpath = f["path"] if isinstance(f, dict) else f.path
            assert fpath.startswith("backend/") or fpath.startswith("frontend/")

    def test_merge_includes_cross_repo_relationships(self, temp_multi_repo):
        _, config_path = temp_multi_repo
        orch = MultiRepoOrchestrator(config_path)
        arch = orch.run()

        cross_rels = [
            r for r in arch.relationships
            if r.get("source", "").startswith("repo:") and r.get("target", "").startswith("repo:")
        ]
        assert len(cross_rels) == 1
        assert cross_rels[0]["source"] == "repo:frontend"
        assert cross_rels[0]["target"] == "repo:backend"
        assert cross_rels[0]["type"] == "http"

    def test_merge_sums_stats(self, temp_multi_repo):
        _, config_path = temp_multi_repo
        orch = MultiRepoOrchestrator(config_path)
        arch = orch.run()

        assert arch.stats["total_files"] > 0
        assert arch.stats["total_components"] >= 2  # at least the 2 repo nodes

    def test_merge_output_serializable(self, temp_multi_repo):
        """Merged output must be JSON-serializable."""
        _, config_path = temp_multi_repo
        orch = MultiRepoOrchestrator(config_path)
        arch = orch.run()

        from dataclasses import asdict
        result = json.dumps(asdict(arch), default=str)
        parsed = json.loads(result)
        assert parsed["name"] == "Test Platform"
        assert len(parsed["repositories"]) == 2

    def test_config_missing_repos_exits(self, tmp_path):
        config = {"solution": "Empty", "repositories": []}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))

        with pytest.raises(SystemExit):
            orch = MultiRepoOrchestrator(config_path)
            orch.run()

    def test_config_bad_path_exits(self, tmp_path):
        config = {
            "solution": "Bad",
            "repositories": [{"name": "missing", "path": "/nonexistent/path"}],
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))

        with pytest.raises(SystemExit):
            orch = MultiRepoOrchestrator(config_path)
            orch.run()


# ---------------------------------------------------------------------------
# Parser Tests
# ---------------------------------------------------------------------------


class TestPythonParser:
    def test_extract_classes(self):
        parser = PythonParser()
        code = (
            "class MyClass:\n"
            '    """A test class."""\n'
            "    pass\n"
        )
        symbols = parser.extract_symbols(code, "test.py")
        names = [s.name for s in symbols]
        assert "MyClass" in names

    def test_extract_functions(self):
        parser = PythonParser()
        code = (
            "def my_function(x: int) -> str:\n"
            '    return str(x)\n'
        )
        symbols = parser.extract_symbols(code, "test.py")
        names = [s.name for s in symbols]
        assert "my_function" in names

    def test_extract_imports(self):
        parser = PythonParser()
        code = (
            "import os\n"
            "from pathlib import Path\n"
            "from .utils import helper\n"
        )
        imports = parser.extract_imports(code)
        assert "os" in imports
        assert "pathlib" in imports

    def test_detect_flask_framework(self):
        parser = PythonParser()
        code = "from flask import Flask\napp = Flask(__name__)\n"
        assert parser.detect_framework(code) == "Flask"

    def test_detect_django_framework(self):
        parser = PythonParser()
        code = "from django.db import models\n"
        assert parser.detect_framework(code) == "Django"

    def test_extract_api_endpoints(self):
        parser = PythonParser()
        code = (
            '@app.route("/users", methods=["GET"])\n'
            "def get_users():\n"
            "    pass\n"
            '\n'
            '@app.post("/users")\n'
            "def create_user():\n"
            "    pass\n"
        )
        endpoints = parser.detect_api_endpoints(code)
        paths = [ep["path"] for ep in endpoints]
        assert "/users" in paths


class TestTypeScriptParser:
    def test_extract_functions(self):
        parser = TypeScriptParser()
        code = (
            "export function greet(name: string): string {\n"
            "  return `Hello ${name}`;\n"
            "}\n"
        )
        symbols = parser.extract_symbols(code, "test.ts")
        names = [s.name for s in symbols]
        assert "greet" in names

    def test_extract_classes(self):
        parser = TypeScriptParser()
        code = (
            "export class UserService {\n"
            "  getUser(id: string): User {\n"
            "    return db.find(id);\n"
            "  }\n"
            "}\n"
        )
        symbols = parser.extract_symbols(code, "test.ts")
        names = [s.name for s in symbols]
        assert "UserService" in names

    def test_extract_react_components(self):
        parser = TypeScriptParser()
        code = (
            "export function MyComponent({ name }: Props) {\n"
            "  return <div>{name}</div>;\n"
            "}\n"
        )
        symbols = parser.extract_symbols(code, "test.tsx")
        names = [s.name for s in symbols]
        assert "MyComponent" in names

    def test_extract_interfaces(self):
        parser = TypeScriptParser()
        code = (
            "export interface User {\n"
            "  id: string;\n"
            "  name: string;\n"
            "}\n"
        )
        symbols = parser.extract_symbols(code, "test.ts")
        names = [s.name for s in symbols]
        assert "User" in names

    def test_extract_imports(self):
        parser = TypeScriptParser()
        code = (
            'import React from "react";\n'
            'import { useState } from "react";\n'
            'import type { User } from "./types";\n'
        )
        imports = parser.extract_imports(code)
        assert "react" in imports

    def test_detect_react_framework(self):
        parser = TypeScriptParser()
        code = 'import React from "react";\n'
        assert parser.detect_framework(code) == "React"

    def test_detect_express_endpoints(self):
        parser = TypeScriptParser()
        code = (
            'app.get("/api/users", handler);\n'
            'router.post("/api/users", createUser);\n'
        )
        endpoints = parser.detect_api_endpoints(code)
        paths = [ep["path"] for ep in endpoints]
        assert "/api/users" in paths


class TestSwiftParser:
    def test_extract_classes(self):
        parser = SwiftParser()
        code = (
            "public class NetworkManager {\n"
            "    func fetch() { }\n"
            "}\n"
        )
        symbols = parser.extract_symbols(code, "test.swift")
        names = [s.name for s in symbols]
        assert "NetworkManager" in names

    def test_extract_structs(self):
        parser = SwiftParser()
        code = (
            "struct UserModel {\n"
            "    let id: String\n"
            "    let name: String\n"
            "}\n"
        )
        symbols = parser.extract_symbols(code, "test.swift")
        names = [s.name for s in symbols]
        assert "UserModel" in names

    def test_extract_protocols(self):
        parser = SwiftParser()
        code = (
            "protocol DataSource {\n"
            "    func fetchItems() -> [Item]\n"
            "}\n"
        )
        symbols = parser.extract_symbols(code, "test.swift")
        names = [s.name for s in symbols]
        assert "DataSource" in names

    def test_detect_swiftui(self):
        parser = SwiftParser()
        code = "import SwiftUI\nstruct ContentView: View { }\n"
        assert parser.detect_framework(code) == "SwiftUI"

    def test_extract_imports(self):
        parser = SwiftParser()
        code = "import Foundation\nimport UIKit\n"
        imports = parser.extract_imports(code)
        assert "Foundation" in imports
        assert "UIKit" in imports


class TestGoParser:
    def test_extract_structs(self):
        parser = GoParser()
        code = (
            "type Server struct {\n"
            "    port int\n"
            "}\n"
        )
        symbols = parser.extract_symbols(code, "main.go")
        names = [s.name for s in symbols]
        assert "Server" in names

    def test_extract_functions(self):
        parser = GoParser()
        code = (
            "func HandleRequest(w http.ResponseWriter, r *http.Request) {\n"
            "}\n"
        )
        symbols = parser.extract_symbols(code, "main.go")
        names = [s.name for s in symbols]
        assert "HandleRequest" in names

    def test_extract_imports(self):
        parser = GoParser()
        code = (
            'import (\n'
            '    "fmt"\n'
            '    "net/http"\n'
            ')\n'
        )
        imports = parser.extract_imports(code)
        assert "fmt" in imports
        # Go parser extracts last segment of import path
        assert "http" in imports


class TestRustParser:
    def test_extract_structs(self):
        parser = RustParser()
        code = (
            "pub struct Config {\n"
            "    pub port: u16,\n"
            "}\n"
        )
        symbols = parser.extract_symbols(code, "lib.rs")
        names = [s.name for s in symbols]
        assert "Config" in names

    def test_extract_functions(self):
        parser = RustParser()
        code = (
            "pub fn process(input: &str) -> Result<(), Error> {\n"
            "    Ok(())\n"
            "}\n"
        )
        symbols = parser.extract_symbols(code, "lib.rs")
        names = [s.name for s in symbols]
        assert "process" in names

    def test_extract_imports(self):
        parser = RustParser()
        code = (
            "use std::collections::HashMap;\n"
            "use tokio::runtime;\n"
        )
        imports = parser.extract_imports(code)
        # Rust parser extracts crate-level names
        assert "std" in imports
        assert "tokio" in imports


# ---------------------------------------------------------------------------
# Base Parser Utility Tests
# ---------------------------------------------------------------------------


class TestBaseParserUtilities:
    def test_extract_env_vars(self):
        from analyze import BaseParser
        parser = BaseParser()

        code = (
            'os.environ["DATABASE_URL"]\n'
            "os.getenv('SECRET_KEY')\n"
            "process.env.NODE_ENV\n"
        )
        env_vars = parser.extract_env_vars(code)
        assert "DATABASE_URL" in env_vars
        assert "SECRET_KEY" in env_vars
        assert "NODE_ENV" in env_vars

    def test_detect_ports(self):
        from analyze import BaseParser
        parser = BaseParser()

        code = (
            "PORT = 8080\n"
            "localhost:3000\n"
            "listen(4000)\n"
        )
        ports = parser.detect_ports(code)
        assert 8080 in ports
        assert 3000 in ports
        assert 4000 in ports

    def test_detect_ports_ignores_invalid(self):
        from analyze import BaseParser
        parser = BaseParser()

        code = "port = 42\n"  # below 80, should be ignored
        ports = parser.detect_ports(code)
        assert 42 not in ports
