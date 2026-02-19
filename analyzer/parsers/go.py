"""Go language parser."""

import re
from typing import Optional

from ..models import Symbol
from .base import BaseParser


class GoParser(BaseParser):
    """Parser for Go source files."""

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

    def detect_framework(self, content: str) -> Optional[str]:
        # Server frameworks (most specific first)
        if "github.com/gin-gonic/gin" in content:
            return "Gin"
        if "github.com/labstack/echo" in content:
            return "Echo"
        if "github.com/gofiber/fiber" in content:
            return "Fiber"
        if "github.com/go-chi/chi" in content:
            return "Chi"
        if "github.com/gorilla/mux" in content:
            return "Gorilla"
        if "github.com/beego/" in content or "github.com/astaxie/beego" in content:
            return "Beego"
        # net/http is used for both clients and servers; only classify as a
        # server framework when server-specific patterns are present.
        if '"net/http"' in content:
            server_patterns = (
                "http.ListenAndServe", "http.Handle", "http.HandleFunc",
                "http.ServeMux", "http.Server{",
            )
            if any(p in content for p in server_patterns):
                return "net/http"
        return None

    def extract_file_doc(self, content: str) -> Optional[str]:
        """Extract Go file-level package comment (// comments before package)."""
        lines = content.split("\n")
        doc_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("//"):
                text = stripped[2:].strip()
                if text and not text.startswith("+build") and not text.startswith("go:"):
                    doc_lines.append(text)
            elif stripped == "" and not doc_lines:
                continue
            elif stripped.startswith("package "):
                break
            else:
                # Non-comment, non-blank before package: reset
                doc_lines = []
        return "\n".join(doc_lines) if doc_lines else None

    def detect_api_endpoints(self, content: str) -> list[dict]:
        endpoints = []
        # Gin/Echo/Fiber-style: router.GET("/path", handler)
        for m in re.finditer(
            r'\.\s*(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s*\(\s*["\']([^"\']+)',
            content,
        ):
            endpoints.append({"method": m.group(1).upper(), "path": m.group(2)})
        # Chi-style: r.Get("/path", handler)
        for m in re.finditer(
            r'\.\s*(Get|Post|Put|Delete|Patch|Head|Options)\s*\(\s*["\']([^"\']+)',
            content,
        ):
            endpoints.append({"method": m.group(1).upper(), "path": m.group(2)})
        # Gorilla/net/http: .HandleFunc("/path", handler).Methods("GET")
        for m in re.finditer(
            r'\.HandleFunc\(\s*["\']([^"\']+)',
            content,
        ):
            endpoints.append({"method": "ANY", "path": m.group(1)})
        # http.Handle("/path", ...)
        for m in re.finditer(
            r'http\.Handle(?:Func)?\(\s*["\']([^"\']+)',
            content,
        ):
            endpoints.append({"method": "ANY", "path": m.group(1)})
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
