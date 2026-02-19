"""Rust language parser."""

import re
from typing import Optional

from ..models import Symbol
from .base import BaseParser


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
