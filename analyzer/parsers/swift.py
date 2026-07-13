"""Swift language parser."""

import re
from typing import Optional

from ..models import Symbol
from ..utils import _is_conditional_import
from .base import BaseParser


class SwiftParser(BaseParser):
    """Parser for Swift source files."""

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
        # Platform-specific frameworks take priority over cross-platform ones.
        # AppKit = macOS only, UIKit = iOS only, SwiftUI = cross-platform.
        # Vapor is server-side Swift.
        # Important: skip imports inside #if os() conditional compilation blocks,
        # as those are cross-platform compatibility shims, not the primary platform.
        if "import Vapor" in content:
            return "Vapor"
        if "import AppKit" in content and not _is_conditional_import(content, "AppKit"):
            return "AppKit"
        if "import UIKit" in content:
            return "UIKit"
        if "import SwiftUI" in content:
            return "SwiftUI"
        return None

    def detect_api_endpoints(self, content: str) -> list[dict]:
        endpoints = []
        # Vapor route registration: app.get("path") { ... }
        # or router.get("path") { ... } / routes.get("path") { ... }
        for m in re.finditer(
            r'\.\s*(get|post|put|delete|patch)\s*\(\s*"([^"]+)"',
            content,
        ):
            endpoints.append({"method": m.group(1).upper(), "path": m.group(2)})
        # Vapor grouped routes: group("api") { ... }
        for m in re.finditer(
            r'\.group\(\s*"([^"]+)"',
            content,
        ):
            endpoints.append({"method": "GROUP", "path": m.group(1)})
        return endpoints

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
