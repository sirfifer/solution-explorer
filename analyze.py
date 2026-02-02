#!/usr/bin/env python3
"""
Architecture Analyzer - Extracts architecture from any codebase.

Zero external dependencies (Python stdlib only).
Outputs a hierarchical architecture.json for the interactive viewer.

Usage:
    python analyze.py /path/to/repo -o architecture.json
    python analyze.py .  # analyze current directory
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Directories to always skip
SKIP_DIRS = {
    ".git", "node_modules", ".build", "build", "dist", "DerivedData",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "target", ".next", ".nuxt", ".output", ".vercel", ".turbo",
    "vendor", "Pods", ".swiftpm", ".sass-cache", "coverage",
    ".gradle", ".idea", ".vscode", "venv", ".venv", "env",
    ".tox", "egg-info", ".eggs", ".cache",
}

# File extensions to skip
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".avif",
    ".mp3", ".mp4", ".wav", ".ogg", ".webm", ".mov",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".lock", ".sum", ".resolved",
    ".DS_Store", ".pyc", ".pyo", ".class", ".o", ".a", ".so", ".dylib",
    ".bin", ".dat", ".db", ".sqlite", ".sqlite3",
    ".gguf", ".mlmodel", ".mlmodelc", ".mlpackage",
    ".xcworkspace",  # directory-like
}

LANGUAGE_MAP = {
    ".swift": "swift",
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".dart": "dart",
    ".vue": "vue",
    ".svelte": "svelte",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".md": "markdown",
    ".mdx": "markdown",
}

# Marker files that indicate a component boundary
COMPONENT_MARKERS = {
    "Package.swift": ("swift", "package"),
    "Cargo.toml": ("rust", "package"),
    "package.json": ("typescript", "package"),
    "pyproject.toml": ("python", "package"),
    "setup.py": ("python", "package"),
    "setup.cfg": ("python", "package"),
    "go.mod": ("go", "module"),
    "Gemfile": ("ruby", "package"),
    "build.gradle": ("java", "package"),
    "build.gradle.kts": ("kotlin", "package"),
    "pom.xml": ("java", "package"),
    "pubspec.yaml": ("dart", "package"),
    "Makefile": (None, "module"),
    "Dockerfile": (None, "service"),
    "docker-compose.yml": (None, "infrastructure"),
    "docker-compose.yaml": (None, "infrastructure"),
    "template.yaml": (None, "infrastructure"),   # AWS SAM
    "template.yml": (None, "infrastructure"),     # AWS SAM
    "serverless.yml": (None, "infrastructure"),   # Serverless Framework
    "serverless.yaml": (None, "infrastructure"),  # Serverless Framework
    "Info.plist": ("swift", "application"),
}

# Directory names that suggest content-only (non-architectural) directories
CONTENT_DIR_NAMES = {
    "wiki", "wiki-content", "docs", "doc", "documentation",
    "curriculum", "prompts", "prompt-templates",
    "assets", "resources", "fixtures", "samples", "examples",
    "models", "data", "migrations",
}

# File extensions considered "content" (not code)
CONTENT_EXTENSIONS = {
    ".md", ".mdx", ".txt", ".rst", ".json", ".yaml", ".yml",
    ".csv", ".tsv", ".xml",
}

# Languages considered actual code (for port detection and relationship scanning).
# Excludes markup, config, and content languages that can contain port-like numbers.
CODE_LANGUAGES = {
    "swift", "python", "rust", "typescript", "javascript",
    "go", "java", "kotlin", "ruby", "cpp", "c", "csharp", "dart",
    "vue", "svelte", "shell",
}

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class Symbol:
    id: str
    name: str
    kind: str  # class, struct, enum, function, protocol, trait, interface, type
    file: str
    line: int
    end_line: int
    code_preview: str  # first few lines of the declaration
    visibility: str = "internal"  # public, internal, private, fileprivate
    docstring: Optional[str] = None
    parent: Optional[str] = None  # parent symbol id
    dependencies: list = field(default_factory=list)
    annotations: list = field(default_factory=list)  # @attributes, decorators


@dataclass
class FileInfo:
    path: str
    language: str
    lines: int
    size_bytes: int
    symbols: list = field(default_factory=list)  # list of symbol ids
    imports: list = field(default_factory=list)
    exports: list = field(default_factory=list)
    module_doc: Optional[str] = None  # file-level docstring / header comment


@dataclass
class ComponentDoc:
    """Rich documentation extracted for a component."""
    readme: Optional[str] = None          # README.md content (markdown)
    claude_md: Optional[str] = None       # CLAUDE.md content (AI instructions)
    changelog: Optional[str] = None       # CHANGELOG.md content
    api_docs: Optional[str] = None        # API documentation if found
    architecture_notes: Optional[str] = None  # extracted from docs/ or inline
    purpose: Optional[str] = None         # one-line purpose from package metadata
    key_decisions: list = field(default_factory=list)  # architectural decisions
    patterns: list = field(default_factory=list)        # detected patterns
    tech_stack: list = field(default_factory=list)      # technologies used
    env_vars: list = field(default_factory=list)        # environment variables
    api_endpoints: list = field(default_factory=list)   # detected API routes


@dataclass
class Component:
    id: str
    name: str
    type: str  # application, service, library, module, package, infrastructure
    path: str
    language: Optional[str] = None
    framework: Optional[str] = None
    description: Optional[str] = None
    port: Optional[int] = None
    children: list = field(default_factory=list)
    files: list = field(default_factory=list)
    entry_points: list = field(default_factory=list)
    config_files: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    docs: dict = field(default_factory=dict)  # ComponentDoc as dict


@dataclass
class Relationship:
    source: str
    target: str
    type: str  # import, http, websocket, grpc, ffi, database, file
    label: Optional[str] = None
    protocol: Optional[str] = None
    port: Optional[int] = None
    bidirectional: bool = False


@dataclass
class Architecture:
    name: str
    description: str
    repository: Optional[str] = None
    generated_at: str = ""
    analyzer_version: str = "1.0.0"
    root_path: str = ""
    components: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    symbols: list = field(default_factory=list)
    files: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    repositories: list = field(default_factory=list)  # multi-repo: [{name, url, ref}]


# ---------------------------------------------------------------------------
# Language Parsers
# ---------------------------------------------------------------------------


class BaseParser:
    """Base class for language-specific parsers."""

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        return []

    def extract_imports(self, content: str) -> list[str]:
        return []

    def detect_framework(self, content: str) -> Optional[str]:
        return None

    def extract_file_doc(self, content: str) -> Optional[str]:
        """Extract file-level documentation comment."""
        return None

    def extract_env_vars(self, content: str) -> list[str]:
        """Extract environment variable references."""
        env_vars = set()
        # os.environ / os.getenv / process.env / std::env
        for m in re.finditer(r'(?:environ|getenv|env)\[?\(?\s*["\'](\w+)["\']', content):
            env_vars.add(m.group(1))
        for m in re.finditer(r'process\.env\.(\w+)', content):
            env_vars.add(m.group(1))
        for m in re.finditer(r'env::var\(\s*"(\w+)"', content):
            env_vars.add(m.group(1))
        return sorted(env_vars)

    def detect_ports(self, content: str) -> list[int]:
        """Extract port numbers from code."""
        ports = set()
        # Common port assignment patterns
        patterns = [
            r'(?:port|PORT)\s*[=:]\s*(\d{2,5})',
            r'localhost:(\d{2,5})',
            r'127\.0\.0\.1:(\d{2,5})',
            r'0\.0\.0\.0:(\d{2,5})',
            r'listen\w*\(.*?(\d{4,5})',
        ]
        for pat in patterns:
            for m in re.finditer(pat, content):
                p = int(m.group(1))
                if 80 <= p <= 65535:
                    ports.add(p)
        return sorted(ports)

    def detect_api_endpoints(self, content: str) -> list[dict]:
        """Extract API route definitions."""
        return []

    def _extract_docstring_before(self, lines: list[str], line_idx: int) -> Optional[str]:
        """Extract documentation comment immediately before a line."""
        if line_idx <= 0:
            return None

        doc_lines = []
        i = line_idx - 1

        # Swift/Rust/TS/JS: /// or /** */ block comments
        # Check for /** ... */ block
        if i >= 0 and lines[i].strip().endswith("*/"):
            end = i
            while i >= 0 and "/*" not in lines[i]:
                i -= 1
            if i >= 0:
                block = lines[i:end + 1]
                cleaned = []
                for bl in block:
                    bl = bl.strip()
                    bl = re.sub(r'^/\*\*?\s?', '', bl)
                    bl = re.sub(r'\s?\*/$', '', bl)
                    bl = re.sub(r'^\*\s?', '', bl)
                    if bl:
                        cleaned.append(bl)
                if cleaned:
                    return "\n".join(cleaned)

        # /// single-line doc comments
        while i >= 0 and lines[i].strip().startswith("///"):
            doc_lines.insert(0, lines[i].strip().lstrip("/").strip())
            i -= 1
        if doc_lines:
            return "\n".join(doc_lines)

        # # Python-style comments above a def/class
        while i >= 0 and lines[i].strip().startswith("#") and not lines[i].strip().startswith("#!"):
            doc_lines.insert(0, lines[i].strip().lstrip("#").strip())
            i -= 1
        if doc_lines:
            return "\n".join(doc_lines)

        return None

    def _extract_python_docstring(self, lines: list[str], start_line: int) -> Optional[str]:
        """Extract Python docstring from the line after a def/class declaration."""
        # Look for triple-quoted string on the next non-empty line
        for i in range(start_line + 1, min(start_line + 5, len(lines))):
            stripped = lines[i].strip()
            if not stripped:
                continue
            if stripped.startswith('"""') or stripped.startswith("'''"):
                quote = stripped[:3]
                if stripped.count(quote) >= 2 and stripped.endswith(quote) and len(stripped) > 6:
                    return stripped[3:-3].strip()
                # Multi-line docstring
                doc_lines = [stripped[3:]]
                for j in range(i + 1, min(i + 30, len(lines))):
                    if quote in lines[j]:
                        doc_lines.append(lines[j].strip().replace(quote, ""))
                        return "\n".join(dl.strip() for dl in doc_lines if dl.strip())
                    doc_lines.append(lines[j].strip())
                return "\n".join(dl.strip() for dl in doc_lines if dl.strip())
            break
        return None

    def _make_symbol_id(self, file_path: str, name: str, line: int) -> str:
        return f"{file_path}:{name}:{line}"

    def _get_code_preview(self, lines: list[str], start: int, max_lines: int = 5) -> str:
        """Get a code preview from line number (0-indexed)."""
        end = min(start + max_lines, len(lines))
        preview = "\n".join(lines[start:end])
        if end < len(lines) and not preview.rstrip().endswith("}"):
            preview += "\n    ..."
        return preview


class SwiftParser(BaseParser):
    SYMBOL_PATTERNS = [
        (r'^\s*(public|open|internal|private|fileprivate)?\s*(final\s+)?(class|struct|enum|protocol|actor)\s+(\w+)', "type"),
        (r'^\s*(public|open|internal|private|fileprivate)?\s*(static\s+|class\s+)?(func)\s+(\w+)', "function"),
        (r'^\s*(public|open|internal|private|fileprivate)?\s*(static\s+|class\s+)?(var|let)\s+(\w+)\s*[=:]', "property"),
        (r'^\s*extension\s+(\w+)', "extension"),
    ]

    IMPORT_PATTERN = re.compile(r'^\s*import\s+(\w+(?:\.\w+)*)', re.MULTILINE)

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        symbols = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            # Type declarations
            m = re.match(
                r'^\s*(public|open|internal|private|fileprivate)?\s*'
                r'(final\s+)?'
                r'(class|struct|enum|protocol|actor)\s+(\w+)',
                line
            )
            if m:
                vis = m.group(1) or "internal"
                kind = m.group(3)
                name = m.group(4)
                end = self._find_closing_brace(lines, i)
                doc = self._extract_docstring_before(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name,
                    kind=kind,
                    file=file_path,
                    line=i + 1,
                    end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    visibility=vis,
                    docstring=doc,
                ))
                continue

            # Function declarations (only top-level or type-level, not nested)
            m = re.match(
                r'^(\s*)(public|open|internal|private|fileprivate)?\s*'
                r'(?:static\s+|class\s+|@\w+\s+)*'
                r'func\s+(\w+)',
                line
            )
            if m:
                indent = len(m.group(1))
                if indent <= 4:  # top-level or one nesting
                    vis = m.group(2) or "internal"
                    name = m.group(3)
                    end = self._find_closing_brace(lines, i)
                    doc = self._extract_docstring_before(lines, i)
                    symbols.append(Symbol(
                        id=self._make_symbol_id(file_path, name, i + 1),
                        name=name,
                        kind="function",
                        file=file_path,
                        line=i + 1,
                        end_line=end + 1,
                        code_preview=self._get_code_preview(lines, i),
                        visibility=vis,
                        docstring=doc,
                    ))

            # Extensions
            m = re.match(r'^\s*extension\s+(\w+)', line)
            if m:
                name = m.group(1)
                end = self._find_closing_brace(lines, i)
                doc = self._extract_docstring_before(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, f"ext_{name}", i + 1),
                    name=f"extension {name}",
                    kind="extension",
                    file=file_path,
                    line=i + 1,
                    end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    docstring=doc,
                ))
        return symbols

    def extract_file_doc(self, content: str) -> Optional[str]:
        """Extract Swift file header comment."""
        lines = content.split("\n")
        doc_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("//"):
                text = stripped.lstrip("/").strip()
                # Skip file-name-only headers and copyright
                if text and not re.match(r'^[\w]+\.swift$', text):
                    doc_lines.append(text)
            elif stripped.startswith("import") or stripped == "":
                if doc_lines:
                    break
                continue
            else:
                break
        return "\n".join(doc_lines) if doc_lines else None

    def extract_imports(self, content: str) -> list[str]:
        return [m.group(1) for m in self.IMPORT_PATTERN.finditer(content)]

    def detect_framework(self, content: str) -> Optional[str]:
        if "import SwiftUI" in content:
            return "SwiftUI"
        if "import UIKit" in content:
            return "UIKit"
        if "import AppKit" in content:
            return "AppKit"
        if "import Vapor" in content:
            return "Vapor"
        return None

    def _find_closing_brace(self, lines: list[str], start: int) -> int:
        depth = 0
        for i in range(start, min(start + 500, len(lines))):
            for ch in lines[i]:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i
        return min(start + 10, len(lines) - 1)


class PythonParser(BaseParser):
    IMPORT_PATTERN = re.compile(
        r'^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))', re.MULTILINE
    )

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        symbols = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            # Class definitions
            m = re.match(r'^class\s+(\w+)', line)
            if m:
                name = m.group(1)
                end = self._find_python_block_end(lines, i)
                doc = self._extract_python_docstring(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name,
                    kind="class",
                    file=file_path,
                    line=i + 1,
                    end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    visibility="public" if not name.startswith("_") else "private",
                    docstring=doc,
                ))
                continue

            # Top-level function definitions
            m = re.match(r'^(async\s+)?def\s+(\w+)', line)
            if m:
                name = m.group(2)
                end = self._find_python_block_end(lines, i)
                doc = self._extract_python_docstring(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name,
                    kind="function",
                    file=file_path,
                    line=i + 1,
                    end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    visibility="public" if not name.startswith("_") else "private",
                    docstring=doc,
                ))
        return symbols

    def extract_file_doc(self, content: str) -> Optional[str]:
        """Extract Python module-level docstring."""
        lines = content.split("\n")
        # Look for module docstring at the top
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith('"""') or stripped.startswith("'''"):
                return self._extract_python_docstring(lines, i - 1)
            break
        return None

    def extract_imports(self, content: str) -> list[str]:
        imports = []
        for m in self.IMPORT_PATTERN.finditer(content):
            mod = m.group(1) or m.group(2)
            if mod:
                imports.append(mod.split(".")[0])
        return list(set(imports))

    def detect_framework(self, content: str) -> Optional[str]:
        frameworks = {
            "flask": "Flask", "django": "Django", "fastapi": "FastAPI",
            "aiohttp": "aiohttp", "tornado": "Tornado", "starlette": "Starlette",
            "pytest": "pytest", "click": "Click",
        }
        for key, name in frameworks.items():
            if f"import {key}" in content or f"from {key}" in content:
                return name
        return None

    def detect_api_endpoints(self, content: str) -> list[dict]:
        endpoints = []
        # Flask/FastAPI decorators
        for m in re.finditer(
            r'@\w+\.(get|post|put|delete|patch|route)\(\s*["\']([^"\']+)',
            content
        ):
            endpoints.append({"method": m.group(1).upper(), "path": m.group(2)})
        # aiohttp routes
        for m in re.finditer(
            r'router\.add_(get|post|put|delete)\(\s*["\']([^"\']+)',
            content
        ):
            endpoints.append({"method": m.group(1).upper(), "path": m.group(2)})
        # aiohttp web.* routes
        for m in re.finditer(
            r'web\.(get|post|put|delete)\(\s*["\']([^"\']+)',
            content
        ):
            endpoints.append({"method": m.group(1).upper(), "path": m.group(2)})
        return endpoints

    def _find_python_block_end(self, lines: list[str], start: int) -> int:
        if start >= len(lines):
            return start
        base_indent = len(lines[start]) - len(lines[start].lstrip())
        for i in range(start + 1, min(start + 500, len(lines))):
            stripped = lines[i].strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(lines[i]) - len(lines[i].lstrip())
            if indent <= base_indent:
                return i - 1
        return min(start + 10, len(lines) - 1)


class RustParser(BaseParser):
    IMPORT_PATTERN = re.compile(r'^\s*use\s+([\w:]+)', re.MULTILINE)

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        symbols = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            # Struct, enum, trait
            m = re.match(
                r'^\s*(pub(?:\([\w]+\))?\s+)?(struct|enum|trait|union)\s+(\w+)',
                line
            )
            if m:
                vis = "public" if m.group(1) and "pub" in m.group(1) else "private"
                kind = m.group(2)
                name = m.group(3)
                end = self._find_closing_brace(lines, i)
                doc = self._extract_docstring_before(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name, kind=kind, file=file_path,
                    line=i + 1, end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    visibility=vis, docstring=doc,
                ))
                continue

            # Impl blocks
            m = re.match(r'^\s*impl(?:<[^>]+>)?\s+(\w+)', line)
            if m:
                name = m.group(1)
                end = self._find_closing_brace(lines, i)
                doc = self._extract_docstring_before(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, f"impl_{name}", i + 1),
                    name=f"impl {name}", kind="impl", file=file_path,
                    line=i + 1, end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    docstring=doc,
                ))
                continue

            # Functions
            m = re.match(
                r'^(\s*)(pub(?:\([\w]+\))?\s+)?(async\s+)?fn\s+(\w+)',
                line
            )
            if m:
                indent = len(m.group(1))
                if indent <= 4:
                    vis = "public" if m.group(2) and "pub" in m.group(2) else "private"
                    name = m.group(4)
                    end = self._find_closing_brace(lines, i)
                    doc = self._extract_docstring_before(lines, i)
                    symbols.append(Symbol(
                        id=self._make_symbol_id(file_path, name, i + 1),
                        name=name, kind="function", file=file_path,
                        line=i + 1, end_line=end + 1,
                        code_preview=self._get_code_preview(lines, i),
                        visibility=vis, docstring=doc,
                    ))
        return symbols

    def extract_file_doc(self, content: str) -> Optional[str]:
        """Extract Rust file-level //! documentation."""
        lines = content.split("\n")
        doc_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("//!"):
                doc_lines.append(stripped[3:].strip())
            elif stripped.startswith("//") or not stripped:
                continue
            else:
                break
        return "\n".join(doc_lines) if doc_lines else None

    def extract_imports(self, content: str) -> list[str]:
        imports = []
        for m in self.IMPORT_PATTERN.finditer(content):
            crate = m.group(1).split("::")[0]
            if crate not in ("self", "super", "crate"):
                imports.append(crate)
        return list(set(imports))

    def detect_framework(self, content: str) -> Optional[str]:
        if "use axum" in content:
            return "Axum"
        if "use actix" in content:
            return "Actix"
        if "use rocket" in content:
            return "Rocket"
        if "use tokio" in content:
            return "Tokio"
        if "use warp" in content:
            return "Warp"
        return None

    def detect_api_endpoints(self, content: str) -> list[dict]:
        endpoints = []
        for m in re.finditer(
            r'\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)',
            content
        ):
            endpoints.append({"method": m.group(1).upper(), "path": m.group(2)})
        return endpoints

    def _find_closing_brace(self, lines, start):
        depth = 0
        for i in range(start, min(start + 500, len(lines))):
            for ch in lines[i]:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i
        return min(start + 10, len(lines) - 1)


class TypeScriptParser(BaseParser):
    IMPORT_PATTERN = re.compile(
        r'''^\s*import\s+(?:(?:[\w{},\s*]+)\s+from\s+)?['"]([@\w/.\-]+)['"]''',
        re.MULTILINE
    )
    REQUIRE_PATTERN = re.compile(
        r'''require\(\s*['"]([@\w/.\-]+)['"]\s*\)'''
    )

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        symbols = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            # Class/interface
            m = re.match(
                r'^\s*(export\s+)?(default\s+)?(abstract\s+)?'
                r'(class|interface)\s+(\w+)',
                line
            )
            if m:
                vis = "public" if m.group(1) else "internal"
                kind = m.group(4)
                name = m.group(5)
                end = self._find_closing_brace(lines, i)
                doc = self._extract_docstring_before(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name, kind=kind, file=file_path,
                    line=i + 1, end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    visibility=vis, docstring=doc,
                ))
                continue

            # Type alias
            m = re.match(r'^\s*(export\s+)?type\s+(\w+)', line)
            if m:
                vis = "public" if m.group(1) else "internal"
                name = m.group(2)
                doc = self._extract_docstring_before(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name, kind="type", file=file_path,
                    line=i + 1, end_line=i + 1,
                    code_preview=self._get_code_preview(lines, i, 3),
                    visibility=vis, docstring=doc,
                ))
                continue

            # Function/const component
            m = re.match(
                r'^\s*(export\s+)?(default\s+)?'
                r'(?:async\s+)?(?:function|const)\s+(\w+)',
                line
            )
            if m:
                vis = "public" if m.group(1) else "internal"
                name = m.group(3)
                # Detect React components
                kind = "component" if name[0].isupper() and (
                    "React" in content[:500] or "jsx" in file_path or "tsx" in file_path
                ) else "function"
                end = self._find_closing_brace(lines, i)
                doc = self._extract_docstring_before(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name, kind=kind, file=file_path,
                    line=i + 1, end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    visibility=vis, docstring=doc,
                ))
        return symbols

    def extract_file_doc(self, content: str) -> Optional[str]:
        """Extract TS/JS file-level JSDoc or header comment."""
        lines = content.split("\n")
        doc_lines = []
        in_block = False
        for line in lines:
            stripped = line.strip()
            # JSDoc block at top of file
            if stripped.startswith("/**") and not in_block:
                in_block = True
                text = re.sub(r'^/\*\*\s?', '', stripped)
                text = re.sub(r'\s?\*/$', '', text)
                if text.strip():
                    doc_lines.append(text.strip())
                if stripped.endswith("*/"):
                    in_block = False
                continue
            if in_block:
                if stripped.endswith("*/"):
                    text = re.sub(r'\s?\*/$', '', stripped)
                    text = re.sub(r'^\*\s?', '', text)
                    if text.strip():
                        doc_lines.append(text.strip())
                    break
                text = re.sub(r'^\*\s?', '', stripped)
                if text.strip():
                    doc_lines.append(text.strip())
                continue
            # Single-line // comments at top
            if stripped.startswith("//") and not stripped.startswith("///"):
                text = stripped[2:].strip()
                if text and not text.startswith("@ts-") and not text.startswith("eslint"):
                    doc_lines.append(text)
                continue
            if stripped == "" or stripped.startswith("'use ") or stripped.startswith('"use '):
                if doc_lines:
                    break
                continue
            if stripped.startswith("import") or stripped.startswith("export"):
                break
            break
        return "\n".join(doc_lines) if doc_lines else None

    def extract_imports(self, content: str) -> list[str]:
        imports = set()
        for m in self.IMPORT_PATTERN.finditer(content):
            mod = m.group(1)
            if mod.startswith("."):
                imports.add(mod)
            else:
                # Get package name (handle @scope/package)
                parts = mod.split("/")
                if parts[0].startswith("@") and len(parts) > 1:
                    imports.add(f"{parts[0]}/{parts[1]}")
                else:
                    imports.add(parts[0])
        for m in self.REQUIRE_PATTERN.finditer(content):
            imports.add(m.group(1).split("/")[0])
        return sorted(imports)

    def detect_framework(self, content: str) -> Optional[str]:
        if "'next" in content or '"next' in content:
            return "Next.js"
        if "'react" in content or '"react' in content:
            return "React"
        if "'vue" in content or '"vue' in content:
            return "Vue"
        if "'svelte" in content or '"svelte' in content:
            return "Svelte"
        if "'express" in content or '"express' in content:
            return "Express"
        if "'@angular" in content or '"@angular' in content:
            return "Angular"
        return None

    def detect_api_endpoints(self, content: str) -> list[dict]:
        endpoints = []
        # Express-style
        for m in re.finditer(
            r'\w+\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)',
            content
        ):
            endpoints.append({"method": m.group(1).upper(), "path": m.group(2)})
        # Next.js API routes (file-based)
        for m in re.finditer(
            r'export\s+(?:async\s+)?function\s+(GET|POST|PUT|DELETE|PATCH)\b',
            content
        ):
            endpoints.append({"method": m.group(1), "path": "(file-based)"})
        return endpoints

    def _find_closing_brace(self, lines, start):
        depth = 0
        for i in range(start, min(start + 500, len(lines))):
            line = lines[i]
            # Skip template literals and strings (simplified)
            in_string = False
            for j, ch in enumerate(line):
                if ch in ('"', "'", "`") and (j == 0 or line[j-1] != "\\"):
                    in_string = not in_string
                if not in_string:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            return i
        return min(start + 10, len(lines) - 1)


class GoParser(BaseParser):
    IMPORT_PATTERN = re.compile(r'"([\w./\-]+)"')

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        symbols = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            # Type declarations
            m = re.match(r'^type\s+(\w+)\s+(struct|interface)', line)
            if m:
                name, kind = m.group(1), m.group(2)
                end = self._find_closing_brace(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name, kind=kind, file=file_path,
                    line=i + 1, end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    visibility="public" if name[0].isupper() else "private",
                ))
                continue

            # Functions
            m = re.match(r'^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)', line)
            if m:
                name = m.group(1)
                end = self._find_closing_brace(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name, kind="function", file=file_path,
                    line=i + 1, end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    visibility="public" if name[0].isupper() else "private",
                ))
        return symbols

    def extract_imports(self, content: str) -> list[str]:
        return list(set(
            m.group(1).split("/")[-1]
            for m in self.IMPORT_PATTERN.finditer(content)
        ))

    def _find_closing_brace(self, lines, start):
        depth = 0
        for i in range(start, min(start + 500, len(lines))):
            for ch in lines[i]:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i
        return min(start + 10, len(lines) - 1)


class RubyParser(BaseParser):
    """Parser for Ruby source files."""

    SYMBOL_PATTERNS = [
        (r'^\s*(class|module)\s+([A-Z]\w*(?:::[A-Z]\w*)*)', "type"),
        (r'^\s*def\s+(self\.)?(\w+[?!=]?)', "function"),
    ]

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        symbols = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            # Class / module
            m = re.match(r'^\s*(class|module)\s+([A-Z]\w*(?:::[A-Z]\w*)*)', line)
            if m:
                kind = m.group(1)
                name = m.group(2)
                end = self._find_ruby_end(lines, i)
                vis = "public"
                docstring = self._extract_docstring_before(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name, kind=kind, file=file_path,
                    line=i + 1, end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    visibility=vis,
                    docstring=docstring,
                ))
                continue

            # Methods
            m = re.match(r'^\s*def\s+(self\.)?(\w+[?!=]?)', line)
            if m:
                name = m.group(2)
                if m.group(1):
                    name = f"self.{name}"
                end = self._find_ruby_end(lines, i)
                docstring = self._extract_docstring_before(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name, kind="function", file=file_path,
                    line=i + 1, end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    visibility="public" if not name.startswith("_") else "private",
                    docstring=docstring,
                ))
        return symbols

    def extract_imports(self, content: str) -> list[str]:
        imports = set()
        for m in re.finditer(r"""require\s+['"]([^'"]+)['"]""", content):
            imports.add(m.group(1).split("/")[0])
        for m in re.finditer(r"""require_relative\s+['"]([^'"]+)['"]""", content):
            imports.add(m.group(1).split("/")[0])
        return sorted(imports)

    def detect_framework(self, content: str) -> Optional[str]:
        if "Rails" in content or "ActiveRecord" in content or "ActionController" in content:
            return "Rails"
        if "Sinatra" in content or "Sinatra::Base" in content:
            return "Sinatra"
        if "Grape::API" in content:
            return "Grape"
        if "Hanami" in content:
            return "Hanami"
        return None

    def detect_api_endpoints(self, content: str) -> list[dict]:
        endpoints = []
        # Rails-style routes
        for m in re.finditer(
            r'(?:get|post|put|patch|delete)\s+["\']([^"\']+)',
            content,
        ):
            method = "GET"
            line = content[:m.start()].split("\n")[-1]
            for verb in ("post", "put", "patch", "delete"):
                if verb in line.lower():
                    method = verb.upper()
                    break
            endpoints.append({"method": method, "path": m.group(1)})
        # Sinatra-style
        for m in re.finditer(
            r'(get|post|put|patch|delete)\s+["\']([^"\']+)',
            content,
        ):
            endpoints.append({"method": m.group(1).upper(), "path": m.group(2)})
        return endpoints

    def _find_ruby_end(self, lines, start):
        depth = 0
        block_keywords = re.compile(
            r'^\s*(?:class|module|def|do|if|unless|case|while|until|for|begin)\b'
        )
        for i in range(start, min(start + 500, len(lines))):
            stripped = lines[i].strip()
            if block_keywords.match(lines[i]) or stripped.endswith(" do"):
                depth += 1
            if stripped == "end" or stripped.startswith("end ") or stripped.startswith("end;"):
                depth -= 1
                if depth == 0:
                    return i
        return min(start + 10, len(lines) - 1)


# Map language to parser
PARSERS = {
    "swift": SwiftParser(),
    "python": PythonParser(),
    "rust": RustParser(),
    "typescript": TypeScriptParser(),
    "javascript": TypeScriptParser(),
    "go": GoParser(),
    "ruby": RubyParser(),
}


# ---------------------------------------------------------------------------
# Config File Parsers
# ---------------------------------------------------------------------------


def parse_package_json(path: Path) -> dict:
    """Extract metadata from package.json."""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return {
            "name": data.get("name", path.parent.name),
            "description": data.get("description", ""),
            "version": data.get("version", ""),
            "dependencies": sorted(set(
                list(data.get("dependencies", {}).keys()) +
                list(data.get("devDependencies", {}).keys())
            )),
            "scripts": list(data.get("scripts", {}).keys()),
        }
    except (json.JSONDecodeError, OSError):
        return {}


def parse_cargo_toml(path: Path) -> dict:
    """Extract metadata from Cargo.toml (basic TOML parsing)."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        info = {"name": "", "description": "", "dependencies": []}

        # Extract package name
        m = re.search(r'^\[package\]\s*\n(?:.*\n)*?name\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if m:
            info["name"] = m.group(1)

        # Extract dependencies
        in_deps = False
        for line in content.split("\n"):
            if re.match(r'\[(?:.*)?dependencies(?:\.\w+)?\]', line):
                in_deps = True
                continue
            if line.startswith("[") and in_deps:
                in_deps = False
            if in_deps:
                m = re.match(r'(\w[\w-]*)\s*=', line)
                if m:
                    info["dependencies"].append(m.group(1))
        return info
    except OSError:
        return {}


def parse_pyproject_toml(path: Path) -> dict:
    """Extract metadata from pyproject.toml."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        info = {"name": "", "description": "", "dependencies": []}
        m = re.search(r'name\s*=\s*"([^"]+)"', content)
        if m:
            info["name"] = m.group(1)
        # Extract deps
        for m in re.finditer(r'"([\w-]+)(?:[><=!~]|$)', content):
            dep = m.group(1)
            if dep not in ("python",):
                info["dependencies"].append(dep)
        return info
    except OSError:
        return {}


def parse_info_plist(path: Path) -> dict:
    """Parse Info.plist for app metadata using stdlib plistlib."""
    try:
        import plistlib
        with open(path, "rb") as f:
            plist = plistlib.load(f)
        name = plist.get("CFBundleDisplayName") or plist.get("CFBundleName") or ""
        # Reject build-time variable placeholders like $(PRODUCT_NAME)
        if name and ("$(" in name or "${" in name):
            name = ""
        return {
            "name": name,
            "bundle_id": plist.get("CFBundleIdentifier", ""),
        }
    except Exception:
        return {}


def _extract_ruby_app_name(base_dir: Path) -> str:
    """Try multiple strategies to find a Ruby/Rails app name from a directory."""
    # Strategy 1: config/application.rb (Rails convention)
    app_rb = base_dir / "config" / "application.rb"
    if app_rb.exists():
        try:
            content = app_rb.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'module\s+(\w+)', content)
            if m:
                return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', m.group(1))
        except OSError:
            pass

    # Strategy 2: config.ru (Rack convention: run AppName::Application)
    config_ru = base_dir / "config.ru"
    if config_ru.exists():
        try:
            content = config_ru.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'run\s+(\w+)::Application', content)
            if m:
                return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', m.group(1))
        except OSError:
            pass

    # Strategy 3: bin/rails or Rakefile mentioning the app
    rakefile = base_dir / "Rakefile"
    if rakefile.exists():
        try:
            content = rakefile.read_text(encoding="utf-8", errors="replace")
            m = re.search(r'(\w+)::Application\.load_tasks', content)
            if m:
                return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', m.group(1))
        except OSError:
            pass

    return ""


def parse_gemfile(path: Path) -> dict:
    """Parse Gemfile for Ruby dependencies and app name."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        gems = set()
        for m in re.finditer(r"""gem\s+['"]([^'"]+)['"]""", content):
            gems.add(m.group(1))
        name = _extract_ruby_app_name(path.parent)
        return {"name": name, "dependencies": list(gems)}
    except Exception:
        return {}


def parse_docker_compose(path: Path) -> dict:
    """Extract services from docker-compose.yml (basic YAML parsing)."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        services = []
        ports = []
        current_service = None
        in_services = False
        in_ports = False

        for line in content.split("\n"):
            if line.strip() == "services:":
                in_services = True
                continue
            if in_services and not line.startswith(" ") and line.strip() and not line.startswith("#"):
                in_services = False

            if in_services:
                # Service name (2-space indent)
                m = re.match(r'^  (\w[\w-]*):', line)
                if m:
                    current_service = m.group(1)
                    services.append(current_service)
                    in_ports = False

                if "ports:" in line:
                    in_ports = True
                    continue
                if in_ports and line.strip().startswith("-"):
                    port_match = re.search(r'(\d+):(\d+)', line)
                    if port_match:
                        ports.append({
                            "service": current_service,
                            "host": int(port_match.group(1)),
                            "container": int(port_match.group(2)),
                        })
                elif in_ports and not line.strip().startswith("-"):
                    in_ports = False

        return {"services": services, "ports": ports}
    except OSError:
        return {}


def parse_sam_template(path: Path) -> dict:
    """Extract Lambda functions and API info from AWS SAM template.yaml.

    Uses basic YAML line parsing (no external deps) to find
    AWS::Serverless::Function resources and their properties.
    """
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        functions = []
        current_resource = None
        current_type = None
        current_handler = None
        current_runtime = None
        current_code_uri = None
        in_resources = False

        for line in content.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped == "Resources:":
                in_resources = True
                continue

            if in_resources and not line.startswith(" ") and stripped.endswith(":"):
                # New top-level section, end of Resources
                in_resources = False
                continue

            if not in_resources:
                continue

            # Resource name (2-space indent under Resources)
            m = re.match(r'^  (\w[\w-]*):', line)
            if m:
                # Save previous resource if it was a Lambda function
                if current_resource and current_type and "Function" in current_type:
                    functions.append({
                        "name": current_resource,
                        "runtime": current_runtime or "",
                        "handler": current_handler or "",
                        "code_uri": current_code_uri or "",
                    })
                current_resource = m.group(1)
                current_type = None
                current_handler = None
                current_runtime = None
                current_code_uri = None
                continue

            if "Type:" in stripped:
                m = re.search(r'Type:\s*(.+)', stripped)
                if m:
                    current_type = m.group(1).strip()

            if "Handler:" in stripped:
                m = re.search(r'Handler:\s*(.+)', stripped)
                if m:
                    current_handler = m.group(1).strip()

            if "Runtime:" in stripped:
                m = re.search(r'Runtime:\s*(.+)', stripped)
                if m:
                    current_runtime = m.group(1).strip()

            if "CodeUri:" in stripped:
                m = re.search(r'CodeUri:\s*(.+)', stripped)
                if m:
                    current_code_uri = m.group(1).strip()

        # Save last resource
        if current_resource and current_type and "Function" in current_type:
            functions.append({
                "name": current_resource,
                "runtime": current_runtime or "",
                "handler": current_handler or "",
                "code_uri": current_code_uri or "",
            })

        # Detect API Gateway
        has_api = bool(re.search(r'AWS::Serverless::Api|AWS::ApiGateway', content))

        return {
            "functions": functions,
            "has_api_gateway": has_api,
            "type": "sam",
        }
    except OSError:
        return {}


def parse_serverless_yml(path: Path) -> dict:
    """Extract function info from serverless.yml (Serverless Framework)."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        functions = []
        in_functions = False
        current_fn = None

        for line in content.split("\n"):
            stripped = line.strip()
            if stripped == "functions:":
                in_functions = True
                continue
            if in_functions and not line.startswith(" ") and stripped.endswith(":"):
                in_functions = False
                continue
            if not in_functions:
                continue
            m = re.match(r'^  (\w[\w-]*):', line)
            if m:
                current_fn = m.group(1)
                functions.append({"name": current_fn})

        provider = ""
        m = re.search(r'provider:\s*\n\s+name:\s*(\w+)', content)
        if m:
            provider = m.group(1)

        return {"functions": functions, "provider": provider, "type": "serverless"}
    except OSError:
        return {}


# ---------------------------------------------------------------------------
# Core Scanner
# ---------------------------------------------------------------------------


class ArchitectureScanner:
    def __init__(self, root: Path, max_file_size: int = 500_000,
                 max_symbols: int = 5000, preview_lines: int = 5):
        self.root = root.resolve()
        self.max_file_size = max_file_size
        self.max_symbols = max_symbols
        self.preview_lines = preview_lines
        self.architecture = Architecture(
            name=self.root.name,
            description="",
            root_path=str(self.root),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        self._all_files: list[FileInfo] = []
        self._all_symbols: list[Symbol] = []
        self._component_map: dict[str, Component] = {}
        self._language_counts: dict[str, int] = defaultdict(int)
        self._total_lines = 0
        self._total_size = 0

    def scan(self) -> Architecture:
        """Run the full scan pipeline."""
        # Phase 1: Discover components
        self._discover_components()

        # Phase 2: Scan files and extract symbols
        self._scan_files()

        # Phase 2.5: Promote generic types to architectural roles
        self._promote_component_types()

        # Phase 2.6: Improve component names after type promotion
        self._improve_component_names()

        # Phase 3: Detect relationships
        self._detect_relationships()

        # Phase 4: Compute metrics
        self._compute_metrics()

        # Phase 5: Detect project-level info
        self._detect_project_info()

        # Phase 6: Extract documentation for every component
        self._extract_component_docs()

        # Assemble
        self.architecture.components = self._build_component_tree()
        self.architecture.files = [asdict(f) for f in self._all_files]

        # Limit symbols if needed, prioritizing public types
        symbols = self._all_symbols
        if self.max_symbols > 0 and len(symbols) > self.max_symbols:
            # Prioritize: public types > private types > functions
            priority = {"class": 0, "struct": 0, "enum": 0, "protocol": 0,
                        "trait": 0, "interface": 0, "actor": 0,
                        "type": 1, "component": 1, "impl": 2, "extension": 2,
                        "function": 3}
            symbols = sorted(symbols, key=lambda s: (
                priority.get(s.kind, 5),
                0 if s.visibility == "public" else 1,
                s.file,
            ))[:self.max_symbols]
        self.architecture.symbols = [asdict(s) for s in symbols]
        self.architecture.stats = {
            "total_files": len(self._all_files),
            "total_lines": self._total_lines,
            "total_size_bytes": self._total_size,
            "languages": dict(self._language_counts),
            "total_symbols": len(self._all_symbols),
            "total_components": len(self._component_map),
            "total_relationships": len(self.architecture.relationships),
        }

        return self.architecture

    def _should_skip(self, path: Path) -> bool:
        """Check if a path should be skipped."""
        if path.name in SKIP_DIRS:
            return True
        if path.suffix.lower() in SKIP_EXTENSIONS:
            return True
        if path.name.startswith(".") and path.is_dir():
            return True
        return False

    def _discover_components(self):
        """Walk the tree and identify component boundaries."""
        # Root is always a component
        root_comp = Component(
            id=self._make_component_id(""),
            name=self.root.name,
            type="project",
            path="",
        )
        self._component_map[""] = root_comp

        for dirpath, dirnames, filenames in os.walk(self.root):
            # Filter directories
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

            rel = os.path.relpath(dirpath, self.root)
            if rel == ".":
                rel = ""

            for marker, (lang, comp_type) in COMPONENT_MARKERS.items():
                if marker in filenames:
                    comp_id = self._make_component_id(rel)
                    if comp_id not in self._component_map:
                        name = os.path.basename(dirpath) if rel else self.root.name
                        comp = Component(
                            id=comp_id,
                            name=name,
                            type=comp_type,
                            path=rel,
                            language=lang,
                        )
                        # Parse config files for metadata
                        marker_path = Path(dirpath) / marker
                        if marker == "package.json":
                            info = parse_package_json(marker_path)
                            comp.name = info.get("name", comp.name)
                            comp.description = info.get("description", "")
                            comp.config_files.append({"type": "package.json", "path": os.path.join(rel, marker)})
                        elif marker == "Cargo.toml":
                            info = parse_cargo_toml(marker_path)
                            comp.name = info.get("name", comp.name) or comp.name
                            comp.config_files.append({"type": "Cargo.toml", "path": os.path.join(rel, marker)})
                        elif marker == "pyproject.toml":
                            info = parse_pyproject_toml(marker_path)
                            comp.name = info.get("name", comp.name) or comp.name
                            comp.config_files.append({"type": "pyproject.toml", "path": os.path.join(rel, marker)})
                        elif marker in ("docker-compose.yml", "docker-compose.yaml"):
                            info = parse_docker_compose(marker_path)
                            # Use service names for a better component description
                            svc_names = info.get("services", [])
                            if svc_names:
                                comp.description = f"Services: {', '.join(svc_names)}"
                            comp.config_files.append({"type": "docker-compose", "path": os.path.join(rel, marker), **info})
                        elif marker == "Info.plist":
                            comp.type = "application"
                            info = parse_info_plist(marker_path)
                            if info.get("name"):
                                comp.name = info["name"]
                            comp.config_files.append({"type": "Info.plist", "path": os.path.join(rel, marker)})
                        elif marker == "Gemfile":
                            info = parse_gemfile(marker_path)
                            if info.get("name"):
                                comp.name = info["name"]
                            comp.config_files.append({"type": "Gemfile", "path": os.path.join(rel, marker)})
                        elif marker in ("template.yaml", "template.yml"):
                            info = parse_sam_template(marker_path)
                            if info.get("functions"):
                                comp.type = "api-server"
                                fn_names = [f["name"] for f in info["functions"]]
                                comp.description = f"AWS SAM: {', '.join(fn_names)}"
                                # Derive a name from the directory or function names
                                if len(fn_names) == 1:
                                    comp.name = fn_names[0]
                            comp.config_files.append({"type": "sam-template", "path": os.path.join(rel, marker), **info})
                        elif marker in ("serverless.yml", "serverless.yaml"):
                            info = parse_serverless_yml(marker_path)
                            if info.get("functions"):
                                comp.type = "api-server"
                                fn_names = [f["name"] for f in info["functions"]]
                                comp.description = f"Serverless: {', '.join(fn_names)}"
                            comp.config_files.append({"type": "serverless", "path": os.path.join(rel, marker), **info})

                        self._component_map[rel] = comp
                        break

        # Also create intermediate directory components for significant directories
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            rel = os.path.relpath(dirpath, self.root)
            if rel == ".":
                rel = ""

            # Count code files in this directory
            code_files = [f for f in filenames if Path(f).suffix.lower() in LANGUAGE_MAP]
            if len(code_files) >= 2 and rel and rel not in self._component_map:
                # Check depth - only create for meaningful groupings
                depth = rel.count(os.sep)
                if depth <= 4:
                    parent_id = self._find_parent_component(rel)
                    if parent_id is not None:
                        self._component_map[rel] = Component(
                            id=self._make_component_id(rel),
                            name=os.path.basename(rel),
                            type="module",
                            path=rel,
                        )

    def _scan_files(self):
        """Scan all code files and extract symbols."""
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]

            for fname in sorted(filenames):
                fpath = Path(dirpath) / fname
                if self._should_skip(fpath):
                    continue

                ext = fpath.suffix.lower()
                lang = LANGUAGE_MAP.get(ext)
                if not lang:
                    continue

                try:
                    stat = fpath.stat()
                    if stat.st_size > self.max_file_size:
                        continue
                    if stat.st_size == 0:
                        continue
                except OSError:
                    continue

                rel = os.path.relpath(fpath, self.root)
                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                lines = content.count("\n") + 1
                self._total_lines += lines
                self._total_size += stat.st_size
                self._language_counts[lang] += lines

                # Parse symbols
                parser = PARSERS.get(lang)
                symbols = []
                imports = []
                if parser:
                    symbols = parser.extract_symbols(content, rel)
                    imports = parser.extract_imports(content)

                    # Detect framework at file level
                    fw = parser.detect_framework(content)
                    if fw:
                        comp = self._find_component_for_file(rel)
                        if comp and not comp.framework:
                            comp.framework = fw

                    # Detect ports (only in code files, not docs/config)
                    if lang in CODE_LANGUAGES:
                        ports = parser.detect_ports(content)
                        if ports:
                            comp = self._find_component_for_file(rel)
                            if comp and not comp.port:
                                comp.port = ports[0]

                # Extract file-level documentation
                module_doc = None
                if parser:
                    module_doc = parser.extract_file_doc(content)

                file_info = FileInfo(
                    path=rel,
                    language=lang,
                    lines=lines,
                    size_bytes=stat.st_size,
                    symbols=[s.id for s in symbols],
                    imports=imports,
                    module_doc=module_doc,
                )

                self._all_files.append(file_info)
                self._all_symbols.extend(symbols)

                # Associate file with component
                comp = self._find_component_for_file(rel)
                if comp:
                    comp.files.append(rel)

    # ------------------------------------------------------------------
    # Phase 2.5: Promote generic types to architectural roles
    # ------------------------------------------------------------------

    def _promote_component_types(self):
        """Promote generic component types (package, module) to specific
        architectural roles (mobile-client, api-server, etc.) using
        framework detection, dependency analysis, and directory heuristics."""
        for rel_path, comp in self._component_map.items():
            # Skip root for content detection but still promote its type
            if rel_path:
                if self._is_content_only(comp, rel_path):
                    comp.type = "content"
                    continue
            promoted = self._classify_architectural_role(comp, rel_path)
            if promoted:
                comp.type = promoted

    def _is_content_only(self, comp: Component, rel_path: str) -> bool:
        """Determine if a component is a content-only directory."""
        dir_name = os.path.basename(rel_path).lower()

        if dir_name in CONTENT_DIR_NAMES:
            code_exts = set(LANGUAGE_MAP.keys()) - CONTENT_EXTENSIONS
            code_files = [f for f in comp.files
                          if Path(f).suffix.lower() in code_exts]
            total = len(comp.files)
            if total == 0 or len(code_files) / max(total, 1) < 0.2:
                return True

        if comp.files:
            content_count = sum(
                1 for f in comp.files
                if Path(f).suffix.lower() in CONTENT_EXTENSIONS
            )
            if content_count / len(comp.files) > 0.8:
                return True

        return False

    def _classify_architectural_role(self, comp: Component, rel_path: str) -> Optional[str]:
        """Classify a component into a specific architectural role."""
        framework = (comp.framework or "").lower()
        comp_dir = self.root / rel_path
        dir_name = os.path.basename(rel_path).lower()

        # Gather marker file signals
        has_info_plist = (comp_dir / "Info.plist").exists()
        has_xcodeproj = any(
            p.suffix == ".xcodeproj" for p in comp_dir.iterdir() if p.is_dir()
        ) if comp_dir.is_dir() else False
        # Also check parent for .xcodeproj (common iOS layout)
        if not has_xcodeproj:
            has_xcodeproj = any(
                p.suffix == ".xcodeproj" for p in self.root.iterdir() if p.is_dir()
            ) if comp.language == "swift" else False
        has_android_manifest = (
            (comp_dir / "AndroidManifest.xml").exists()
            or (comp_dir / "src" / "main" / "AndroidManifest.xml").exists()
        )
        has_build_gradle = (
            (comp_dir / "build.gradle").exists()
            or (comp_dir / "build.gradle.kts").exists()
        )
        has_package_json = (comp_dir / "package.json").exists()
        has_cargo_toml = (comp_dir / "Cargo.toml").exists()
        has_pubspec = (comp_dir / "pubspec.yaml").exists()

        # Read dependency lists from config files
        pkg_deps: set[str] = set()
        if has_package_json:
            info = parse_package_json(comp_dir / "package.json")
            pkg_deps = set(info.get("dependencies", []))

        cargo_deps: set[str] = set()
        if has_cargo_toml:
            info = parse_cargo_toml(comp_dir / "Cargo.toml")
            cargo_deps = set(info.get("dependencies", []))

        # --- Watch app ---
        if "watch" in dir_name:
            if comp.language == "swift" or framework in ("swiftui", "watchkit"):
                return "watch-app"

        # --- iOS client ---
        if framework in ("swiftui", "uikit"):
            if has_info_plist or has_xcodeproj or comp.type == "application":
                return "ios-client"

        # --- Android client ---
        if has_android_manifest:
            return "android-client"
        if has_build_gradle and comp.language in ("java", "kotlin"):
            if has_android_manifest or "android" in dir_name:
                return "android-client"

        # --- Mobile client: React Native (cross-platform) ---
        if "react-native" in pkg_deps:
            return "mobile-client"

        # --- Mobile client: Flutter (cross-platform) ---
        if has_pubspec:
            try:
                content = (comp_dir / "pubspec.yaml").read_text(errors="replace")
                if "flutter:" in content:
                    return "mobile-client"
            except OSError:
                pass

        # --- Desktop app ---
        if framework in ("appkit", "electron"):
            return "desktop-app"
        if "electron" in pkg_deps:
            return "desktop-app"

        # --- API server: framework detection ---
        server_frameworks = {
            "axum", "actix", "rocket", "warp", "vapor",
            "express", "fastify", "hono", "koa", "nestjs",
            "flask", "django", "fastapi", "starlette", "aiohttp",
            "tornado", "gin", "echo", "fiber",
            "rails", "sinatra", "grape", "hanami",
        }
        if framework in server_frameworks:
            return "api-server"

        # --- API server: JS/TS deps (pure server, no client framework) ---
        pure_server_deps = {
            "express", "fastify", "hono", "koa", "@nestjs/core",
        }
        client_deps = {"react", "vue", "svelte", "@angular/core"}
        if pkg_deps & pure_server_deps and not (pkg_deps & client_deps):
            return "api-server"

        # --- API server: Rust deps ---
        rust_server_deps = {"axum", "actix-web", "rocket", "warp"}
        if cargo_deps & rust_server_deps:
            return "api-server"

        # --- API server: Ruby deps ---
        has_gemfile = (comp_dir / "Gemfile").exists()
        if has_gemfile:
            gem_info = parse_gemfile(comp_dir / "Gemfile")
            ruby_deps = set(gem_info.get("dependencies", []))
            ruby_server_deps = {"rails", "sinatra", "grape", "hanami", "roda"}
            if ruby_deps & ruby_server_deps:
                return "api-server"

        # --- Service: standalone server scripts ---
        # Detect directories containing explicitly-named server files (e.g.,
        # log_server.py, gateway.py) that import HTTP server modules, even in
        # utility directories that would otherwise be excluded.
        if comp.language == "python" or (not comp.language and comp.files):
            server_file_patterns = re.compile(
                r'(?:^|/)(?:.*server.*|.*gateway.*|.*daemon.*)\.py$', re.I)
            server_imports = {
                "http.server", "aiohttp", "flask", "fastapi", "tornado",
                "uvicorn", "gunicorn", "starlette", "socketserver",
            }
            for fpath in comp.files:
                if server_file_patterns.search(fpath):
                    try:
                        content = (self.root / fpath).read_text(
                            encoding="utf-8", errors="replace")
                        for srv_import in server_imports:
                            if (f"import {srv_import}" in content
                                    or f"from {srv_import}" in content):
                                return "service"
                    except OSError:
                        pass

        # --- API server: port + server language + no client signals ---
        # Only for languages that are typically server-side. Swift/Kotlin/Java
        # mobile code often references ports as API clients, not servers.
        # Also exclude utility/build directories that may reference ports in scripts.
        utility_dir_names = {"scripts", "bin", "tools", "utils", "ci", "build", "devops", "deploy"}
        server_languages = {"python", "rust", "go", "ruby", "typescript", "javascript"}
        if (comp.port and comp.language in server_languages
                and not (pkg_deps & client_deps)
                and dir_name not in utility_dir_names):
            return "api-server"

        # --- Web client ---
        web_client_frameworks = {
            "react", "next.js", "vue", "nuxt", "svelte",
            "sveltekit", "angular",
        }
        if framework in web_client_frameworks:
            return "web-client"

        web_client_deps = {
            "react", "vue", "svelte", "@angular/core",
            "next", "nuxt", "@sveltejs/kit",
        }
        if pkg_deps & web_client_deps:
            return "web-client"

        # --- CLI tool ---
        if comp.language == "python" and framework in ("click", "typer"):
            return "cli-tool"
        rust_cli_deps = {"clap"}
        if cargo_deps & rust_cli_deps and not (cargo_deps & rust_server_deps):
            return "cli-tool"

        return None

    def _improve_component_names(self):
        """Improve component names after type promotion.

        Some components get generic folder-based names during discovery because
        their marker files don't provide names (e.g., Makefile, Dockerfile).
        After type promotion identifies the architectural role, we can try
        harder to find a meaningful name.
        """
        for rel_path, comp in self._component_map.items():
            if not rel_path:
                continue
            folder_name = os.path.basename(rel_path)
            # Only improve if the name is still the generic folder name
            if comp.name != folder_name:
                continue

            comp_dir = self.root / rel_path

            # Ruby/Rails apps: try to find the real app name
            if comp.language == "ruby" or (comp.framework and comp.framework.lower() in ("rails", "sinatra", "grape")):
                name = _extract_ruby_app_name(comp_dir)
                if name:
                    comp.name = name
                    continue

            # Python apps: try pyproject.toml or setup.cfg in subtree
            if comp.language == "python":
                for cfg_name in ("pyproject.toml", "setup.cfg", "setup.py"):
                    cfg_path = comp_dir / cfg_name
                    if cfg_path.exists():
                        if cfg_name == "pyproject.toml":
                            info = parse_pyproject_toml(cfg_path)
                        else:
                            continue
                        if info.get("name"):
                            comp.name = info["name"]
                            break

    def _detect_relationships(self):
        """Detect inter-component relationships."""
        relationships = []
        seen = set()

        # Content components should not participate in relationships
        content_ids = {comp.id for comp in self._component_map.values()
                       if comp.type == "content"}

        # Build a map of component paths to IDs
        comp_by_path = {}
        for path, comp in self._component_map.items():
            comp_by_path[path] = comp.id

        # Import-based relationships
        for file_info in self._all_files:
            source_comp = self._find_component_for_file(file_info.path)
            if not source_comp or source_comp.id in content_ids:
                continue

            for imp in file_info.imports:
                # Try to resolve import to a component
                target_comp = self._resolve_import_to_component(imp, file_info.path)
                if (target_comp and target_comp.id != source_comp.id
                        and target_comp.id not in content_ids):
                    key = (source_comp.id, target_comp.id, "import")
                    if key not in seen:
                        seen.add(key)
                        relationships.append(Relationship(
                            source=source_comp.id,
                            target=target_comp.id,
                            type="import",
                            label=imp,
                        ))

        # Port-based relationships (service A calls service B's port)
        port_map = {}  # port -> component
        for comp in self._component_map.values():
            if comp.port and comp.id not in content_ids:
                port_map[comp.port] = comp

        for file_info in self._all_files:
            # Only scan code files for port references, not docs/config
            if file_info.language not in CODE_LANGUAGES:
                continue
            source_comp = self._find_component_for_file(file_info.path)
            if not source_comp or source_comp.id in content_ids:
                continue

            try:
                fpath = self.root / file_info.path
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Look for references to other services' ports
            for port, target_comp in port_map.items():
                if target_comp.id == source_comp.id:
                    continue
                port_str = str(port)
                if port_str in content:
                    # Verify it's actually a port reference with tight patterns
                    patterns = [
                        rf"localhost:{port_str}\b",
                        rf"127\.0\.0\.1:{port_str}\b",
                        rf"0\.0\.0\.0:{port_str}\b",
                        rf"""[\"']https?://[^\"']*:{port_str}\b""",
                        rf"(?:PORT|port)\s*[=:]\s*{port_str}\b",
                    ]
                    for pat in patterns:
                        if re.search(pat, content):
                            key = (source_comp.id, target_comp.id, "http")
                            if key not in seen:
                                seen.add(key)
                                relationships.append(Relationship(
                                    source=source_comp.id,
                                    target=target_comp.id,
                                    type="http",
                                    port=port,
                                    protocol="REST",
                                    label=f"port {port}",
                                ))
                            break

        # Watch app -> iOS client companion relationship
        watch_apps = [c for c in self._component_map.values() if c.type == "watch-app"]
        ios_clients = [c for c in self._component_map.values() if c.type == "ios-client"]
        if watch_apps and ios_clients:
            # Pair each watch app with the most likely iOS companion
            # (same project, closest shared parent, or just the first iOS client)
            for watch in watch_apps:
                best_ios = ios_clients[0]
                # Prefer an iOS client in the same parent directory
                watch_parent = os.path.dirname(watch.path) if watch.path else ""
                for ios in ios_clients:
                    ios_parent = os.path.dirname(ios.path) if ios.path else ""
                    if watch_parent == ios_parent or watch.name.lower().replace(" watch", "").replace("watch", "").strip() in ios.name.lower():
                        best_ios = ios
                        break
                key = (watch.id, best_ios.id, "import")
                if key not in seen:
                    seen.add(key)
                    relationships.append(Relationship(
                        source=watch.id,
                        target=best_ios.id,
                        type="import",
                        label="companion app",
                    ))

        # Docker-compose service relationships
        for comp in self._component_map.values():
            for config in comp.config_files:
                if config.get("type") == "docker-compose":
                    for _port_info in config.get("ports", []):
                        # Create infrastructure relationships
                        pass

        self.architecture.relationships = [asdict(r) for r in relationships]

    def _compute_metrics(self):
        """Compute metrics for each component."""
        for comp in self._component_map.values():
            file_count = len(comp.files)
            total_lines = 0
            total_size = 0
            lang_counts = defaultdict(int)
            symbol_count = 0

            for fpath in comp.files:
                for fi in self._all_files:
                    if fi.path == fpath:
                        total_lines += fi.lines
                        total_size += fi.size_bytes
                        lang_counts[fi.language] += fi.lines
                        symbol_count += len(fi.symbols)
                        break

            comp.metrics = {
                "files": file_count,
                "lines": total_lines,
                "size_bytes": total_size,
                "symbols": symbol_count,
                "languages": dict(lang_counts),
            }

            # Determine primary language
            if lang_counts and not comp.language:
                comp.language = max(lang_counts, key=lang_counts.get)

    def _extract_component_docs(self):
        """Extract rich documentation for every component."""
        for rel_path, comp in self._component_map.items():
            comp_dir = self.root / rel_path if rel_path else self.root
            if not comp_dir.is_dir():
                continue

            doc = ComponentDoc()

            # --- Read documentation files ---
            doc_file_map = {
                "readme": ("README.md", "README.rst", "README.txt", "README"),
                "claude_md": ("CLAUDE.md",),
                "changelog": ("CHANGELOG.md", "CHANGES.md", "HISTORY.md"),
            }
            for field_name, candidates in doc_file_map.items():
                for fname in candidates:
                    fpath = comp_dir / fname
                    if fpath.exists():
                        try:
                            content = fpath.read_text(encoding="utf-8", errors="replace")
                            # Truncate very large docs to keep JSON manageable
                            if len(content) > 8000:
                                content = content[:8000] + "\n\n... (truncated)"
                            setattr(doc, field_name, content)
                        except OSError:
                            pass
                        break

            # --- Scan docs/ directory for architecture notes ---
            docs_dir = comp_dir / "docs"
            if not docs_dir.is_dir():
                docs_dir = comp_dir / "doc"
            if docs_dir.is_dir():
                arch_notes = []
                for fname in sorted(os.listdir(docs_dir)):
                    if not fname.endswith((".md", ".txt", ".rst")):
                        continue
                    fpath = docs_dir / fname
                    if not fpath.is_file():
                        continue
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="replace")
                        # Extract first heading and first paragraph as summary
                        heading = ""
                        summary_lines = []
                        for line in content.split("\n"):
                            stripped = line.strip()
                            if stripped.startswith("#") and not heading:
                                heading = stripped.lstrip("#").strip()
                            elif heading and stripped:
                                summary_lines.append(stripped)
                                if len(summary_lines) >= 3:
                                    break
                            elif heading and not stripped and summary_lines:
                                break
                        if heading:
                            arch_notes.append(f"**{heading}** ({fname}): {' '.join(summary_lines)}")
                    except OSError:
                        pass
                if arch_notes:
                    doc.architecture_notes = "\n\n".join(arch_notes[:20])

            # --- Extract purpose from package metadata ---
            for cfg in comp.config_files:
                cfg_path = cfg.get("path", "") if isinstance(cfg, dict) else ""
                if not cfg_path:
                    continue
                full_path = self.root / cfg_path
                if not full_path.exists():
                    continue
                try:
                    cfg_content = full_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue

                basename = os.path.basename(cfg_path)
                if basename == "package.json":
                    try:
                        data = json.loads(cfg_content)
                        desc = data.get("description", "")
                        if desc:
                            doc.purpose = desc
                    except json.JSONDecodeError:
                        pass
                elif basename == "Cargo.toml":
                    m = re.search(r'description\s*=\s*"([^"]+)"', cfg_content)
                    if m:
                        doc.purpose = m.group(1)
                elif basename in ("pyproject.toml", "setup.cfg"):
                    m = re.search(r'description\s*=\s*"([^"]+)"', cfg_content)
                    if m:
                        doc.purpose = m.group(1)

            # --- Collect env vars and API endpoints from files ---
            for file_path in comp.files[:100]:  # limit to prevent slowdown
                full_path = self.root / file_path
                if not full_path.exists():
                    continue
                ext = full_path.suffix.lower()
                lang = LANGUAGE_MAP.get(ext)
                parser = PARSERS.get(lang) if lang else None
                if not parser:
                    continue
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                env_vars = parser.extract_env_vars(content)
                doc.env_vars.extend(v for v in env_vars if v not in doc.env_vars)

                if hasattr(parser, 'detect_api_endpoints'):
                    endpoints = parser.detect_api_endpoints(content)
                    for ep in endpoints:
                        ep_str = f"{ep['method']} {ep['path']}"
                        if ep_str not in [f"{e['method']} {e['path']}" for e in doc.api_endpoints]:
                            doc.api_endpoints.append(ep)

            # --- Detect architectural patterns ---
            patterns = self._detect_patterns(comp)
            doc.patterns = patterns

            # --- Determine tech stack ---
            tech = []
            if comp.framework:
                tech.append(comp.framework)
            if comp.language:
                tech.append(comp.language.capitalize())
            # Check config for additional tech
            for file_path in comp.files[:50]:
                basename = os.path.basename(file_path).lower()
                if basename == "tailwind.config.js" or basename == "tailwind.config.ts":
                    tech.append("TailwindCSS")
                elif basename == "tsconfig.json":
                    tech.append("TypeScript")
                elif basename == ".eslintrc" or basename == "eslint.config.js":
                    tech.append("ESLint")
                elif basename == "jest.config.js" or basename == "jest.config.ts":
                    tech.append("Jest")
                elif basename == "vitest.config.ts":
                    tech.append("Vitest")
                elif basename == "webpack.config.js":
                    tech.append("Webpack")
                elif basename == "vite.config.ts" or basename == "vite.config.js":
                    tech.append("Vite")
            doc.tech_stack = sorted(set(tech))

            comp.docs = asdict(doc)

    def _detect_patterns(self, comp: Component) -> list[str]:
        """Detect architectural patterns in a component."""
        patterns = []
        file_names = [os.path.basename(f).lower() for f in comp.files]

        # MVC / MVVM / MVP
        has_view = any("view" in f for f in file_names)
        has_model = any("model" in f for f in file_names)
        has_controller = any("controller" in f for f in file_names)
        has_viewmodel = any("viewmodel" in f or "view_model" in f for f in file_names)
        has_presenter = any("presenter" in f for f in file_names)

        if has_view and has_model and has_viewmodel:
            patterns.append("MVVM")
        elif has_view and has_model and has_controller:
            patterns.append("MVC")
        elif has_view and has_model and has_presenter:
            patterns.append("MVP")

        # Repository pattern
        if any("repository" in f or "repo" in f for f in file_names):
            patterns.append("Repository Pattern")

        # Service layer
        if any("service" in f for f in file_names) and comp.type != "service":
            patterns.append("Service Layer")

        # Observer / Pub-Sub
        if any("observer" in f or "subscriber" in f or "publisher" in f for f in file_names):
            patterns.append("Observer/Pub-Sub")

        # Store / State Management
        if any("store" in f or "reducer" in f or "slice" in f for f in file_names):
            patterns.append("State Management")

        # Middleware
        if any("middleware" in f for f in file_names):
            patterns.append("Middleware")

        # Plugin/Extension
        if any("plugin" in f or "extension" in f for f in file_names):
            patterns.append("Plugin Architecture")

        # Factory
        if any("factory" in f for f in file_names):
            patterns.append("Factory Pattern")

        # Dependency Injection
        if any("container" in f or "injector" in f or "provider" in f for f in file_names):
            patterns.append("Dependency Injection")

        # API layer
        if any("api" in f or "endpoint" in f or "route" in f for f in file_names):
            patterns.append("API Layer")

        # Test structure
        test_files = [f for f in file_names if "test" in f or "spec" in f]
        if test_files:
            ratio = len(test_files) / max(len(file_names), 1)
            if ratio > 0.3:
                patterns.append("Well-Tested")
            patterns.append(f"Tests ({len(test_files)} files)")

        return patterns

    def _detect_project_info(self):
        """Detect project-level information."""
        # Try to find README
        for name in ("README.md", "README.rst", "README.txt", "README"):
            readme = self.root / name
            if readme.exists():
                try:
                    content = readme.read_text(encoding="utf-8", errors="replace")
                    # First non-empty, non-heading line as description
                    for line in content.split("\n"):
                        line = line.strip()
                        if line and not line.startswith("#") and not line.startswith("="):
                            self.architecture.description = line[:200]
                            break
                except OSError:
                    pass
                break

        # Try to detect git remote
        git_config = self.root / ".git" / "config"
        if git_config.exists():
            try:
                content = git_config.read_text(encoding="utf-8", errors="replace")
                m = re.search(r'url\s*=\s*(.+)', content)
                if m:
                    url = m.group(1).strip()
                    # Convert SSH to HTTPS
                    url = re.sub(r'git@github\.com:', 'https://github.com/', url)
                    url = re.sub(r'\.git$', '', url)
                    self.architecture.repository = url
            except OSError:
                pass

    def _build_component_tree(self) -> list[dict]:
        """Build a hierarchical tree of components."""
        # Build parent-child mapping first (paths only)
        children_map: dict[str, list[str]] = defaultdict(list)
        root_paths = []

        for path in self._component_map:
            parent_path = self._find_parent_component(path)
            if parent_path is None or path == "":
                root_paths.append(path)
            else:
                children_map[parent_path].append(path)

        # Recursively serialize
        def serialize(path: str) -> dict:
            comp = self._component_map[path]
            d = asdict(comp)
            # Replace children with recursively built children
            d["children"] = [serialize(cp) for cp in sorted(children_map.get(path, []))]
            return d

        roots = [serialize(p) for p in sorted(root_paths)]

        # If single root project, keep it but ensure children are populated
        return roots

    def _make_component_id(self, rel_path: str) -> str:
        """Create a stable component ID from relative path."""
        if not rel_path:
            return "root"
        return rel_path.replace(os.sep, "/").replace(" ", "-").lower()

    def _find_parent_component(self, rel_path: str) -> Optional[str]:
        """Find the nearest parent component for a path."""
        if not rel_path:
            return None

        parts = rel_path.split(os.sep)
        for i in range(len(parts) - 1, -1, -1):
            parent = os.sep.join(parts[:i])
            if not parent:
                parent = ""
            if parent in self._component_map and parent != rel_path:
                return parent
        return "" if "" in self._component_map else None

    def _find_component_for_file(self, file_path: str) -> Optional[Component]:
        """Find the deepest component that contains this file."""
        parts = file_path.split(os.sep)
        for i in range(len(parts) - 1, -1, -1):
            dir_path = os.sep.join(parts[:i])
            if not dir_path:
                dir_path = ""
            if dir_path in self._component_map:
                return self._component_map[dir_path]
        return self._component_map.get("")

    def _resolve_import_to_component(self, import_name: str, source_file: str) -> Optional[Component]:
        """Try to resolve an import to a component."""
        # For relative imports, try to find the target file/directory
        if import_name.startswith("."):
            source_dir = os.path.dirname(source_file)
            # Resolve relative path
            parts = import_name.split("/")
            current = source_dir
            for part in parts:
                if part == ".":
                    continue
                elif part == "..":
                    current = os.path.dirname(current)
                else:
                    current = os.path.join(current, part)
            return self._find_component_for_file(current)

        # For absolute imports, try to match against component names/paths
        import_lower = import_name.lower()
        for path, comp in self._component_map.items():
            comp_name = comp.name.lower().replace("-", "").replace("_", "")
            if import_lower.replace("-", "").replace("_", "") == comp_name:
                return comp
            # Check if import matches a directory name in the component
            if path and os.path.basename(path).lower() == import_lower:
                return comp

        return None


# ---------------------------------------------------------------------------
# Multi-Repo Orchestrator
# ---------------------------------------------------------------------------


class MultiRepoOrchestrator:
    """Orchestrates analysis across multiple repositories defined in a config file."""

    def __init__(self, config_path: Path, max_file_size: int = 500_000,
                 max_symbols: int = 5000, preview_lines: int = 5):
        self.config_path = config_path.resolve()
        self.config_dir = self.config_path.parent
        self.max_file_size = max_file_size
        self.max_symbols = max_symbols
        self.preview_lines = preview_lines

        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

    def run(self) -> Architecture:
        """Analyze all repositories and merge into a single Architecture."""
        solution_name = self.config.get("solution", "Solution")
        description = self.config.get("description", "")
        repos = self.config.get("repositories", [])

        if not repos:
            print("Error: No repositories defined in config", file=sys.stderr)
            sys.exit(1)

        architectures: list[tuple[str, Architecture]] = []
        temp_dirs: list[tempfile.TemporaryDirectory] = []

        try:
            for repo_def in repos:
                name = repo_def["name"]
                repo_path = self._resolve_repo(repo_def, temp_dirs)
                print(f"\nAnalyzing repository: {name} ({repo_path})")

                scanner = ArchitectureScanner(
                    repo_path,
                    max_file_size=self.max_file_size,
                    max_symbols=self.max_symbols,
                    preview_lines=self.preview_lines,
                )
                arch = scanner.scan()
                architectures.append((name, arch))
        finally:
            for td in temp_dirs:
                td.cleanup()

        return self._merge(solution_name, description, architectures)

    def _resolve_repo(self, repo_def: dict,
                      temp_dirs: list) -> Path:
        """Resolve a repository definition to a local path."""
        if "path" in repo_def:
            p = Path(repo_def["path"])
            if not p.is_absolute():
                p = (self.config_dir / p).resolve()
            if not p.is_dir():
                print(f"Error: Repository path does not exist: {p}", file=sys.stderr)
                sys.exit(1)
            return p

        url = repo_def.get("url", "")
        ref = repo_def.get("ref", "HEAD")

        if not url:
            print(f"Error: Repository '{repo_def.get('name', '?')}' has no path or url",
                  file=sys.stderr)
            sys.exit(1)

        td = tempfile.TemporaryDirectory(prefix="solution-explorer-")
        temp_dirs.append(td)
        clone_path = Path(td.name)

        # Support private repos via GITHUB_TOKEN env var
        clone_url = url
        token = os.environ.get("GITHUB_TOKEN")
        if token and "github.com" in url:
            clone_url = re.sub(
                r'https://github\.com/',
                f'https://x-access-token:{token}@github.com/',
                url,
            )

        cmd = ["git", "clone", "--depth", "1"]
        if ref and ref != "HEAD":
            cmd.extend(["--branch", ref])
        cmd.extend([clone_url, str(clone_path)])

        print(f"  Cloning {url} (ref={ref})...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error cloning {url}: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        return clone_path

    def _merge(self, solution_name: str, description: str,
               architectures: list[tuple[str, Architecture]]) -> Architecture:
        """Merge multiple Architecture results into one."""
        merged = Architecture(
            name=solution_name,
            description=description,
            generated_at=datetime.now(timezone.utc).isoformat(),
            repositories=[],
        )

        all_components = []
        all_relationships = []
        all_symbols = []
        all_files = []
        total_stats: dict = {
            "total_files": 0,
            "total_lines": 0,
            "total_size_bytes": 0,
            "total_symbols": 0,
            "total_components": 0,
            "total_relationships": 0,
            "languages": {},
        }

        for repo_name, arch in architectures:
            prefix = f"{repo_name}/"

            # Record repository metadata
            repo_info = {"name": repo_name, "repository": arch.repository}
            merged.repositories.append(repo_info)

            # Prefix all IDs to avoid collisions
            prefixed_components = self._prefix_components(arch.components, prefix)
            prefixed_relationships = self._prefix_relationships(arch.relationships, prefix)
            prefixed_symbols = self._prefix_symbols(arch.symbols, prefix)
            prefixed_files = self._prefix_files(arch.files, prefix)

            # Wrap in a repository-level component
            repo_component = {
                "id": f"repo:{repo_name}",
                "name": repo_name,
                "type": "repository",
                "path": f"@{repo_name}",
                "language": self._primary_language(arch.stats.get("languages", {})),
                "framework": None,
                "description": arch.description or None,
                "port": None,
                "children": prefixed_components,
                "files": [],
                "entry_points": [],
                "config_files": [],
                "metrics": {
                    "files": arch.stats.get("total_files", 0),
                    "lines": arch.stats.get("total_lines", 0),
                    "size_bytes": arch.stats.get("total_size_bytes", 0),
                    "symbols": arch.stats.get("total_symbols", 0),
                    "languages": arch.stats.get("languages", {}),
                },
                "docs": {
                    "readme": None, "claude_md": None, "changelog": None,
                    "api_docs": None, "architecture_notes": None,
                    "purpose": arch.description or None,
                    "key_decisions": [], "patterns": [], "tech_stack": [],
                    "env_vars": [], "api_endpoints": [],
                },
            }
            all_components.append(repo_component)
            all_relationships.extend(prefixed_relationships)
            all_symbols.extend(prefixed_symbols)
            all_files.extend(prefixed_files)

            # Merge stats
            stats = arch.stats or {}
            total_stats["total_files"] += stats.get("total_files", 0)
            total_stats["total_lines"] += stats.get("total_lines", 0)
            total_stats["total_size_bytes"] += stats.get("total_size_bytes", 0)
            total_stats["total_symbols"] += stats.get("total_symbols", 0)
            total_stats["total_components"] += stats.get("total_components", 0)
            total_stats["total_relationships"] += stats.get("total_relationships", 0)
            for lang, lines in stats.get("languages", {}).items():
                total_stats["languages"][lang] = total_stats["languages"].get(lang, 0) + lines

        # Add explicit cross-repo relationships from config
        for rel_def in self.config.get("cross_repo_relationships", []):
            source_repo = rel_def.get("source_repo", "")
            target_repo = rel_def.get("target_repo", "")
            all_relationships.append({
                "source": f"repo:{source_repo}",
                "target": f"repo:{target_repo}",
                "type": rel_def.get("type", "http"),
                "label": rel_def.get("label"),
                "protocol": rel_def.get("type"),
                "port": rel_def.get("port"),
                "bidirectional": rel_def.get("bidirectional", False),
            })
            total_stats["total_relationships"] += 1

        total_stats["total_components"] += len(architectures)  # count repo nodes
        merged.components = all_components
        merged.relationships = all_relationships
        merged.symbols = all_symbols
        merged.files = all_files
        merged.stats = total_stats

        return merged

    def _prefix_components(self, components: list, prefix: str) -> list:
        """Recursively prefix all component IDs."""
        result = []
        for comp in components:
            c = dict(comp) if isinstance(comp, dict) else asdict(comp)
            c["id"] = prefix + c["id"]
            c["path"] = prefix + c["path"]
            c["files"] = [prefix + f for f in c.get("files", [])]
            c["children"] = self._prefix_components(c.get("children", []), prefix)
            result.append(c)
        return result

    def _prefix_relationships(self, relationships: list, prefix: str) -> list:
        result = []
        for rel in relationships:
            r = dict(rel) if isinstance(rel, dict) else asdict(rel)
            r["source"] = prefix + r["source"]
            r["target"] = prefix + r["target"]
            result.append(r)
        return result

    def _prefix_symbols(self, symbols: list, prefix: str) -> list:
        result = []
        for sym in symbols:
            s = dict(sym) if isinstance(sym, dict) else asdict(sym)
            s["id"] = prefix + s["id"]
            s["file"] = prefix + s["file"]
            if s.get("parent"):
                s["parent"] = prefix + s["parent"]
            result.append(s)
        return result

    def _prefix_files(self, files: list, prefix: str) -> list:
        result = []
        for fi in files:
            f = dict(fi) if isinstance(fi, dict) else asdict(fi)
            f["path"] = prefix + f["path"]
            f["symbols"] = [prefix + s for s in f.get("symbols", [])]
            result.append(f)
        return result

    def _primary_language(self, languages: dict) -> Optional[str]:
        if not languages:
            return None
        return max(languages, key=languages.get)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Analyze codebase architecture and generate interactive visualization data."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Path to the repository root (default: current directory)",
    )
    parser.add_argument(
        "-o", "--output",
        default="architecture.json",
        help="Output JSON file path (default: architecture.json)",
    )
    parser.add_argument(
        "--max-file-size",
        type=int,
        default=500_000,
        help="Maximum file size to analyze in bytes (default: 500KB)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=True,
        help="Pretty-print JSON output (default: true)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Compact JSON output (overrides --pretty)",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=5000,
        help="Maximum number of symbols to include (default: 5000, 0=unlimited)",
    )
    parser.add_argument(
        "--preview-lines",
        type=int,
        default=5,
        help="Max lines for code previews (default: 5)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to solution-explorer.json for multi-repo analysis",
    )

    args = parser.parse_args()

    if args.config:
        config_path = Path(args.config).resolve()
        if not config_path.exists():
            print(f"Error: Config file not found: {config_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Multi-repo mode: {config_path}")
        orchestrator = MultiRepoOrchestrator(
            config_path,
            max_file_size=args.max_file_size,
            max_symbols=args.max_symbols,
            preview_lines=args.preview_lines,
        )
        arch = orchestrator.run()
    else:
        root = Path(args.path).resolve()
        if not root.is_dir():
            print(f"Error: {root} is not a directory", file=sys.stderr)
            sys.exit(1)

        print(f"Scanning {root}...")
        scanner = ArchitectureScanner(
            root,
            max_file_size=args.max_file_size,
            max_symbols=args.max_symbols,
            preview_lines=args.preview_lines,
        )
        arch = scanner.scan()

    # Write output
    indent = None if args.compact else 2
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asdict(arch), f, indent=indent, default=str)

    stats = arch.stats
    print("\nAnalysis complete:")
    print(f"  Components: {stats['total_components']}")
    print(f"  Files: {stats['total_files']}")
    print(f"  Lines: {stats['total_lines']:,}")
    print(f"  Symbols: {stats['total_symbols']}")
    print(f"  Relationships: {stats['total_relationships']}")
    print(f"  Languages: {', '.join(f'{k} ({v:,} lines)' for k, v in sorted(stats['languages'].items(), key=lambda x: -x[1]))}")
    print(f"\nOutput: {output_path}")


if __name__ == "__main__":
    main()
