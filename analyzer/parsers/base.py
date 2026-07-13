"""Base parser class for language-specific parsers."""

import re
from dataclasses import dataclass, field
from typing import Optional

from ..models import Symbol


@dataclass
class NestedSymbol:
    """A raw, component-agnostic symbol emitted by the v2 extraction tier.

    This is deliberately separate from ``models.Symbol``: it carries the
    nesting information the frozen symbol-ID grammar needs (``path`` and
    ``parent_index``) but never a resolved store ID, because the owning
    component is not known at extraction time (TARGET-ARCHITECTURE.md 4.1;
    IDs are assigned in the runner via analyzer/store/ids.py). ``path`` is the
    descriptor chain outermost first, for example ``("Foo", "bar")`` for method
    ``bar`` inside class ``Foo``. ``parent_index`` indexes the parent within
    the same file's flat symbol list, or is None for a top-level symbol.
    ``via_regex`` marks a fact produced by the regex fallback tier so the
    runner can record confidence and keep tier-tagged cache entries separate.
    """

    name: str
    kind: str
    line: int
    end_line: int
    visibility: str = "internal"
    docstring: Optional[str] = None
    code_preview: str = ""
    parent_index: Optional[int] = None
    path: tuple = field(default_factory=tuple)
    via_regex: bool = False


class BaseParser:
    """Base class for language-specific parsers."""

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        return []

    def extract_nested_symbols(self, content: str, file_path: str) -> list[NestedSymbol]:
        """Emit nested symbols for the v2 extraction tier.

        The base (regex) implementation has no reliable nesting information, so
        it flattens :meth:`extract_symbols` to top-level records marked
        ``via_regex``. Tree-sitter parsers override this to emit true nesting
        with parent references and exact ranges (analyzer/extract).
        """
        out: list[NestedSymbol] = []
        for s in self.extract_symbols(content, file_path):
            out.append(NestedSymbol(
                name=s.name, kind=s.kind, line=s.line, end_line=s.end_line,
                visibility=s.visibility, docstring=s.docstring,
                code_preview=s.code_preview, parent_index=None,
                path=(s.name,), via_regex=True,
            ))
        return out

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
        """Extract port numbers from server-side code (binding/listening patterns only).

        Only matches patterns that indicate this component SERVES on a port,
        not patterns that indicate it connects TO a port as a client.
        """
        ports = set()
        # Server-side port binding patterns (high confidence)
        server_patterns = [
            # Direct listen/bind/serve patterns
            r'\.listen\s*\(\s*(\d{4,5})',
            r'\.bind\s*\([^)]*:(\d{4,5})',
            r'\.serve\s*\([^)]*(\d{4,5})',
            r'TcpListener::bind\s*\([^)]*:(\d{4,5})',
            r'app\.run\s*\([^)]*port\s*=\s*(\d{4,5})',
            r'uvicorn\.run\s*\([^)]*port\s*=\s*(\d{4,5})',
            # Express/Node patterns
            r'app\.listen\s*\(\s*(\d{4,5})',
            r'server\.listen\s*\(\s*(\d{4,5})',
            r'createServer\s*\([^)]*\)\.listen\s*\(\s*(\d{4,5})',
            # Flask/Python patterns
            r'app\.run\s*\([^)]*port\s*=\s*(\d{4,5})',
            # Axum/Rust patterns
            r'axum::serve\s*\([^)]*bind\s*\([^)]*:(\d{4,5})',
            # Port constant definitions (for main server files)
            r'(?:SERVER_PORT|APP_PORT|HTTP_PORT|API_PORT|LISTEN_PORT)\s*[=:]\s*(\d{4,5})',
            # aiohttp pattern
            r'web\.run_app\s*\([^)]*port\s*=\s*(\d{4,5})',
            # Only match 0.0.0.0 binding (server-side), not localhost (often client-side)
            r'0\.0\.0\.0:(\d{4,5})',
            # Python constant definitions like PORT = 8766
            r'^PORT\s*=\s*(?:int\s*\([^)]*["\'])?(\d{4,5})',
            r'_PORT\s*[=,]\s*["\']?(\d{4,5})',
            # Environment variable defaults for ports
            r'\.get\s*\(\s*["\'].*PORT["\'].*["\'](\d{4,5})["\']',
            # Rust clap default_value for port arguments
            r'default_value\s*=\s*["\'](\d{4,5})["\']',
        ]
        for pat in server_patterns:
            for m in re.finditer(pat, content, re.MULTILINE):
                p = int(m.group(1))
                if 1024 <= p <= 65535:  # Skip privileged ports
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
