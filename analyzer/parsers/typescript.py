"""TypeScript and JavaScript language parser."""

import re
from typing import Optional

from ..models import Symbol
from .base import BaseParser


class TypeScriptParser(BaseParser):
    """Parser for TypeScript and JavaScript source files."""

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
