"""C++ language parser (regex tier).

Conservative by design: on the regex tier precision beats recall. Type
declarations (class, struct, union, enum, namespace) are matched reliably;
function and method definitions are matched only when they carry a body (an
opening brace on the signature line), so a bare prototype in a header is not
mistaken for a definition and control-flow statements are excluded by an
explicit keyword blacklist. The tree-sitter tier (cpp_ts.py) is the real
workhorse and is used by default; this tier is the fallback when the grammar
wheel is unavailable.
"""

import re
from typing import Optional

from ..models import Symbol
from .base import BaseParser

# A leading `template<...>` clause may sit on the same line as the declaration.
_TEMPLATE = r"(?:template\s*<[^;{}]*>\s*)?"

# Names that begin a statement shaped like `keyword ( ... ) {` but are not
# function definitions. Excluded so the function matcher never captures them.
_STMT_KEYWORDS = frozenset({
    "if", "for", "while", "switch", "catch", "return", "else", "do",
    "namespace", "class", "struct", "union", "enum", "template", "sizeof",
    "static_assert", "decltype", "typedef", "using", "case", "default",
})


class CppParser(BaseParser):
    """Parser for C++ source and header files."""

    INCLUDE_PATTERN = re.compile(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', re.MULTILINE)

    _TYPE_RE = re.compile(
        rf'^\s*{_TEMPLATE}(class|struct|union)\s+(\w+)\s*(?:final\b\s*)?(?:[:{{]|$)'
    )
    _ENUM_RE = re.compile(
        r'^\s*enum\s+(?:class\s+|struct\s+)?(\w+)\s*(?::\s*[\w:]+\s*)?(?:[{]|$)'
    )
    _NAMESPACE_RE = re.compile(r'^\s*namespace\s+([\w:]+)\s*(?:[{]|$)')
    # A function or method DEFINITION: at least one return-type token, then the
    # (optionally qualified) name, a parameter list, optional trailing qualifiers,
    # and an opening brace on the same line. Bare prototypes (ending in `;`) are
    # intentionally not matched.
    _FUNC_RE = re.compile(
        r'^\s*'
        r'(?:[\w:<>,\*&\[\]~]+[\s\*&]+)+'
        r'(~?\w+(?:::~?\w+)*)\s*'
        r'\([^;{}]*\)\s*'
        r'(?:(?:const|noexcept|override|final|mutable)\b\s*|->\s*[\w:<>\*&\s]+)*'
        r'\{'
    )

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        symbols: list[Symbol] = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            m = self._TYPE_RE.match(line)
            if m:
                kind, name = m.group(1), m.group(2)
                self._append(symbols, file_path, lines, i, name, kind, "public")
                continue

            m = self._ENUM_RE.match(line)
            if m:
                self._append(symbols, file_path, lines, i, m.group(1), "enum", "public")
                continue

            m = self._NAMESPACE_RE.match(line)
            if m:
                self._append(
                    symbols, file_path, lines, i, m.group(1), "namespace", "public"
                )
                continue

            m = self._FUNC_RE.match(line)
            if m:
                qualified = m.group(1)
                name = qualified.split("::")[-1]
                if name in _STMT_KEYWORDS or qualified.split("::")[0] in _STMT_KEYWORDS:
                    continue
                kind = "method" if "::" in qualified else "function"
                self._append(symbols, file_path, lines, i, name, kind, "public")
        return symbols

    def _append(self, symbols, file_path, lines, i, name, kind, vis):
        end = self._find_closing_brace(lines, i)
        symbols.append(Symbol(
            id=self._make_symbol_id(file_path, name, i + 1),
            name=name, kind=kind, file=file_path,
            line=i + 1, end_line=end + 1,
            code_preview=self._get_code_preview(lines, i),
            visibility=vis,
            docstring=self._extract_docstring_before(lines, i),
        ))

    def extract_imports(self, content: str) -> list[str]:
        return [m.group(1) for m in self.INCLUDE_PATTERN.finditer(content)]

    def extract_file_doc(self, content: str) -> Optional[str]:
        """Extract a C++ file header comment (leading // or /* */ lines)."""
        lines = content.split("\n")
        doc_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("//"):
                text = stripped.lstrip("/").strip()
                # Skip filename-only headers and pragma-once style lines.
                if text and not re.match(r'^[\w.]+\.(?:h|hpp|hh|cpp|cc|cxx)$', text):
                    doc_lines.append(text)
            elif stripped.startswith("/*"):
                text = re.sub(r'^/\*+', '', stripped)
                text = re.sub(r'\*+/$', '', text).strip()
                if text:
                    doc_lines.append(text)
                if stripped.endswith("*/"):
                    if doc_lines:
                        break
            elif stripped == "" or stripped.startswith("*"):
                if doc_lines and stripped == "":
                    break
                continue
            elif stripped.startswith("#") or stripped.startswith("#pragma"):
                if doc_lines:
                    break
                continue
            else:
                break
        return "\n".join(doc_lines) if doc_lines else None

    def detect_framework(self, content: str) -> Optional[str]:
        # Qt is the one dominant, cheaply detectable C++ application framework.
        # Anchor on a Qt include or the QObject macro so an unrelated identifier
        # never trips it. No web framework dominates C++, so nothing else here.
        if re.search(r'#\s*include\s*[<"]Q[A-Za-z]+[">/]', content):
            return "Qt"
        if "Q_OBJECT" in content:
            return "Qt"
        return None

    def _find_closing_brace(self, lines: list[str], start: int) -> int:
        depth = 0
        seen_open = False
        for i in range(start, min(start + 500, len(lines))):
            for ch in lines[i]:
                if ch == "{":
                    depth += 1
                    seen_open = True
                elif ch == "}":
                    depth -= 1
                    if seen_open and depth == 0:
                        return i
        return min(start + 10, len(lines) - 1)
