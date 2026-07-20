"""Java language parser."""

import re
from typing import Optional

from ..models import Symbol
from .base import BaseParser

# Type declaration keywords mapped to the symbol kind we emit. ``@interface`` is
# handled separately because the ``@`` prefix is not a plain word boundary.
_TYPE_KEYWORDS = {
    "class": "class",
    "interface": "interface",
    "enum": "enum",
    "record": "record",
}

# Access modifiers that can precede a declaration. Java's default (none of
# these) is package-private, which we report as "package".
_VISIBILITY = {"public", "private", "protected"}


class JavaParser(BaseParser):
    """Parser for Java source files."""

    PACKAGE_PATTERN = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)
    # An import names a single type (or a wildcard). We keep the fully qualified
    # name so derive-time resolution can match a package segment to a component
    # directory. ``static`` imports are captured too.
    IMPORT_PATTERN = re.compile(
        r'^\s*import\s+(?:static\s+)?([\w.]+(?:\.\*)?)\s*;', re.MULTILINE
    )
    TYPE_PATTERN = re.compile(
        r'^\s*((?:(?:public|private|protected|abstract|final|static|sealed|'
        r'non-sealed|strictfp)\s+)*)'
        r'(class|interface|enum|record)\s+(\w+)'
    )
    ANNOTATION_TYPE_PATTERN = re.compile(
        r'^\s*((?:(?:public|private|protected|abstract|final|static)\s+)*)'
        r'@interface\s+(\w+)'
    )
    # A method or constructor: modifiers, an optional generic parameter section,
    # a return type for methods, then ``name(``. Constructors have no return
    # type; we treat both as kind "method".
    METHOD_PATTERN = re.compile(
        r'^(\s*)((?:(?:public|private|protected|abstract|final|static|'
        r'synchronized|native|default|strictfp)\s+)*)'
        r'(?:<[^>]+>\s*)?'
        r'(?:[\w.$<>\[\],?\s]+?\s+)?'
        r'(\w+)\s*\('
    )

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        symbols = []
        lines = content.split("\n")
        for i, line in enumerate(lines):
            m = self.TYPE_PATTERN.match(line)
            if m:
                vis = self._visibility_from_modifiers(m.group(1))
                kind = _TYPE_KEYWORDS[m.group(2)]
                name = m.group(3)
                end = self._find_closing_brace(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name,
                    kind=kind,
                    file=file_path,
                    line=i + 1,
                    end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    visibility=vis,
                    docstring=self._extract_docstring_before(lines, i),
                ))
                continue

            m = self.ANNOTATION_TYPE_PATTERN.match(line)
            if m:
                vis = self._visibility_from_modifiers(m.group(1))
                name = m.group(2)
                end = self._find_closing_brace(lines, i)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, i + 1),
                    name=name,
                    kind="annotation",
                    file=file_path,
                    line=i + 1,
                    end_line=end + 1,
                    code_preview=self._get_code_preview(lines, i),
                    visibility=vis,
                    docstring=self._extract_docstring_before(lines, i),
                ))
                continue

            m = self.METHOD_PATTERN.match(line)
            if m and self._is_method_line(line, m.group(3)):
                indent = len(m.group(1))
                if indent <= 8:  # a type-level member, not a deeply nested block
                    vis = self._visibility_from_modifiers(m.group(2))
                    name = m.group(3)
                    end = self._find_closing_brace(lines, i)
                    symbols.append(Symbol(
                        id=self._make_symbol_id(file_path, name, i + 1),
                        name=name,
                        kind="method",
                        file=file_path,
                        line=i + 1,
                        end_line=end + 1,
                        code_preview=self._get_code_preview(lines, i),
                        visibility=vis,
                        docstring=self._extract_docstring_before(lines, i),
                    ))
        return symbols

    def extract_file_doc(self, content: str) -> Optional[str]:
        """Extract the Javadoc/block comment that heads the file, if any."""
        lines = content.split("\n")
        doc_lines: list[str] = []
        in_block = False
        for line in lines:
            stripped = line.strip()
            if not in_block:
                if stripped.startswith("/*"):
                    in_block = True
                    text = re.sub(r'^/\*+', '', stripped).strip()
                    if text.endswith("*/"):
                        text = text[:-2].strip()
                        in_block = False
                    if text:
                        doc_lines.append(text)
                    if not in_block:
                        break
                elif stripped == "" or stripped.startswith("package") \
                        or stripped.startswith("//"):
                    continue
                else:
                    break
            else:
                if stripped.endswith("*/"):
                    text = re.sub(r'\*/$', '', stripped).lstrip("*").strip()
                    if text:
                        doc_lines.append(text)
                    break
                text = stripped.lstrip("*").strip()
                if text:
                    doc_lines.append(text)
        return "\n".join(doc_lines) if doc_lines else None

    def extract_imports(self, content: str) -> list[str]:
        return [m.group(1) for m in self.IMPORT_PATTERN.finditer(content)]

    def detect_framework(self, content: str) -> Optional[str]:
        # Spring is the most common and most specific. Jakarta EE and the older
        # Java EE (javax) namespaces come next.
        if _has_spring(content):
            return "Spring"
        if "jakarta." in content:
            return "Jakarta EE"
        if "javax.ws.rs" in content or "javax.ejb" in content \
                or "javax.servlet" in content or "javax.persistence" in content:
            return "Java EE"
        return None

    def detect_api_endpoints(self, content: str) -> list[dict]:
        # Reference implementation for the v1 engine. The precise, route-shape
        # guarded version used by the v2 capability tier lives in
        # analyzer/extract/frameworks.py and keeps its own tests.
        if not (_has_spring(content) or "ws.rs" in content or "@Path" in content):
            return []
        endpoints = []
        for m in _SPRING_MAPPING.finditer(content):
            verb = m.group(1)
            args = m.group(2) or ""
            method = _spring_method(verb, args)
            path = _mapping_path(args)
            if path:
                endpoints.append({"method": method, "path": _norm_path(path)})
        return endpoints

    def _visibility_from_modifiers(self, modifiers: str) -> str:
        for token in (modifiers or "").split():
            if token in _VISIBILITY:
                return token
        return "package"

    def _is_method_line(self, line: str, name: str) -> bool:
        """Reject control-flow keywords that also read as ``name(``.

        ``if (``, ``while (``, ``for (``, ``switch (``, ``catch (`` and friends
        match the generic method shape but are not declarations.
        """
        if name in {
            "if", "for", "while", "switch", "catch", "return", "new",
            "synchronized", "super", "this", "assert", "throw", "else",
        }:
            return False
        # A real declaration ends its signature with ``)`` optionally followed by
        # ``throws ...`` then ``{`` or ``;`` (abstract/interface method). A plain
        # call such as ``foo();`` has no leading modifier or return type, so we
        # require the line to not simply be an invocation statement.
        stripped = line.strip()
        return not stripped.endswith(");") or "=" in stripped.split("(")[0]

    def _find_closing_brace(self, lines: list[str], start: int) -> int:
        depth = 0
        started = False
        for i in range(start, min(start + 500, len(lines))):
            for ch in lines[i]:
                if ch == "{":
                    depth += 1
                    started = True
                elif ch == "}":
                    depth -= 1
                    if started and depth == 0:
                        return i
            # An abstract/interface method or a field has no body; it ends at the
            # first ``;`` before any brace opens.
            if not started and ";" in lines[i]:
                return i
        return min(start + 10, len(lines) - 1)


def _has_spring(content: str) -> bool:
    return (
        "org.springframework" in content
        or "@RestController" in content
        or "@SpringBootApplication" in content
        or "@Controller" in content
        or "@RequestMapping" in content
        or "@GetMapping" in content
        or "@PostMapping" in content
    )


_SPRING_MAPPING = re.compile(
    r'@(Get|Post|Put|Delete|Patch|Request)Mapping\s*(?:\(\s*([^)]*)\))?'
)
_MAPPING_VALUE = re.compile(r'(?:value|path)\s*=\s*["\']([^"\']+)["\']')
_MAPPING_BARE = re.compile(r'["\']([^"\']+)["\']')
_MAPPING_METHOD = re.compile(r'method\s*=\s*(?:RequestMethod\.)?(\w+)')

_SPRING_VERBS = {
    "Get": "GET", "Post": "POST", "Put": "PUT",
    "Delete": "DELETE", "Patch": "PATCH",
}


def _spring_method(verb: str, args: str) -> str:
    if verb in _SPRING_VERBS:
        return _SPRING_VERBS[verb]
    m = _MAPPING_METHOD.search(args)
    return m.group(1).upper() if m else "ANY"


def _mapping_path(args: str) -> Optional[str]:
    m = _MAPPING_VALUE.search(args)
    if m:
        return m.group(1)
    m = _MAPPING_BARE.search(args)
    return m.group(1) if m else None


def _norm_path(path: str) -> str:
    return path if path.startswith("/") else "/" + path
