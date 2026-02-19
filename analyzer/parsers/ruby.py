"""Ruby language parser."""

import re
from typing import Optional

from ..models import Symbol
from .base import BaseParser


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
