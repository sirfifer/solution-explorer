"""C# language parser."""

import re
from typing import Optional

from ..models import Symbol
from .base import BaseParser

# `using` directives name a namespace (or an aliased/static target). We keep the
# full dotted target so it doubles as import evidence and framework detection.
_USING_PATTERN = re.compile(
    r'^\s*(?:global\s+)?using\s+(?:static\s+)?'
    r'(?:[A-Za-z_]\w*\s*=\s*)?'          # optional alias: `using Foo = Bar;`
    r'([A-Za-z_][\w.]*)\s*;',
    re.MULTILINE,
)

# Access/other modifiers that may precede a type or member declaration.
_MODIFIERS = (
    r'(?:(?:public|private|protected|internal|static|sealed|abstract|'
    r'partial|readonly|virtual|override|async|new|unsafe|extern|ref)\s+)*'
)

_ACCESS = ("public", "private", "protected", "internal")


class CSharpParser(BaseParser):
    """Parser for C# source files."""

    TYPE_PATTERN = re.compile(
        r'^\s*(' + _MODIFIERS + r')'
        r'(class|struct|interface|enum|record)\s+(\w+)'
    )
    # A member whose declaration starts with an access modifier. Requiring the
    # modifier keeps the regex tier precise: it will not mistake a control-flow
    # keyword (`if (`, `while (`) or a local variable for a member. The
    # tree-sitter tier recovers the default-private members this misses.
    METHOD_PATTERN = re.compile(
        r'^(\s*)(' + _MODIFIERS + r')'
        r'(?:[\w.<>\[\],?]+\s+)+'          # return type (one or more tokens)
        r'(\w+)\s*\('                       # method name and open paren
    )
    PROPERTY_PATTERN = re.compile(
        r'^(\s*)(' + _MODIFIERS + r')'
        r'(?:[\w.<>\[\],?]+\s+)+'          # property type
        r'(\w+)\s*\{\s*(?:get|set|init)'    # name then accessor block
    )

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        symbols = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            m = self.TYPE_PATTERN.match(line)
            if m:
                vis = self._visibility(m.group(1))
                kind = m.group(2)
                name = m.group(3)
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

            m = self.PROPERTY_PATTERN.match(line)
            if m:
                self._append_member(m, "property", lines, i, file_path, symbols)
                continue

            m = self.METHOD_PATTERN.match(line)
            if m and not self._is_control_keyword(m.group(3)):
                self._append_member(m, "method", lines, i, file_path, symbols)
        return symbols

    def _append_member(self, m, kind, lines, i, file_path, symbols):
        vis = self._visibility(m.group(2))
        name = m.group(3)
        end = self._find_closing_brace(lines, i) if "{" in lines[i] else i
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

    def extract_file_doc(self, content: str) -> Optional[str]:
        """Extract a C# file header comment (// or /// lines)."""
        lines = content.split("\n")
        doc_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("//"):
                text = stripped.lstrip("/").strip()
                if text and not re.match(r'^[\w]+\.cs$', text):
                    doc_lines.append(text)
            elif stripped.startswith("using") or stripped == "":
                if doc_lines:
                    break
                continue
            else:
                break
        return "\n".join(doc_lines) if doc_lines else None

    def extract_imports(self, content: str) -> list[str]:
        return [m.group(1) for m in _USING_PATTERN.finditer(content)]

    def detect_framework(self, content: str) -> Optional[str]:
        # More specific frameworks take priority. ASP.NET Core and EF Core are
        # both built on .NET, so a plain System import is the generic fallback.
        if ("Microsoft.AspNetCore" in content or "ControllerBase" in content
                or "[ApiController]" in content or "WebApplication.Create" in content):
            return "ASP.NET Core"
        if ("Microsoft.EntityFrameworkCore" in content or "DbContext" in content
                or "DbSet<" in content):
            return "EF Core"
        if "using System" in content or "namespace " in content:
            return ".NET"
        return None

    def detect_api_endpoints(self, content: str) -> list[dict]:
        endpoints = []
        # ASP.NET Core minimal APIs: app.MapGet("/path", ...).
        for m in re.finditer(
            r'\.Map(Get|Post|Put|Delete|Patch)\s*\(\s*"([^"]+)"',
            content,
        ):
            endpoints.append({"method": m.group(1).upper(), "path": m.group(2)})
        # Controller attribute routes: [HttpGet("path")].
        for m in re.finditer(
            r'\[Http(Get|Post|Put|Delete|Patch)\s*\(\s*"([^"]+)"\s*\)\s*\]',
            content,
        ):
            endpoints.append({"method": m.group(1).upper(), "path": m.group(2)})
        return endpoints

    def _visibility(self, modifiers: str) -> str:
        for token in modifiers.split():
            if token in _ACCESS:
                return token
        return "internal"

    @staticmethod
    def _is_control_keyword(name: str) -> bool:
        return name in {
            "if", "for", "foreach", "while", "switch", "catch", "using",
            "lock", "fixed", "return", "throw", "yield",
        }

    def _find_closing_brace(self, lines: list[str], start: int) -> int:
        depth = 0
        seen = False
        for i in range(start, min(start + 500, len(lines))):
            for ch in lines[i]:
                if ch == "{":
                    depth += 1
                    seen = True
                elif ch == "}":
                    depth -= 1
                    if seen and depth == 0:
                        return i
        return min(start + 10, len(lines) - 1)
