"""Python language parser."""

import re
from typing import Optional

from ..models import Symbol
from .base import BaseParser


class PythonParser(BaseParser):
    """Parser for Python source files."""

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
                # Skip imports inside try/except blocks (optional deps)
                if self._is_try_except_import(content, key):
                    continue
                return name
        return None

    @staticmethod
    def _is_try_except_import(content: str, module: str) -> bool:
        """Check if an import only appears inside try/except blocks.

        Returns True if every occurrence of 'import <module>' is preceded
        by a 'try:' line, indicating it is an optional/fallback dependency.
        """
        lines = content.split("\n")
        in_try = False
        found_unconditional = False
        for line in lines:
            stripped = line.strip()
            if stripped == "try:":
                in_try = True
            elif stripped.startswith("except") and ":" in stripped:
                in_try = False
            elif (f"import {module}" in stripped or f"from {module}" in stripped):
                if not in_try:
                    found_unconditional = True
                    break
        return not found_unconditional

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
