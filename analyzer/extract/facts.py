"""Fact records: the per-file, component-agnostic output of Tier 1.

A :class:`FileFacts` is exactly what depends on file content plus parser
version, so it is the unit cached in ``extraction_cache`` keyed by
(content_hash, parser_version). It deliberately excludes anything that depends
on the rest of the repository (component membership, cross-file edges): those
are derived later (Tier 3) and would poison a content-addressed cache.

Every list on a fact record is stored in a deterministic order by the runner
so two cold runs produce byte-identical store contents (invariant I4; the
PYTHONHASHSEED ordering hazard recorded in TASKS.md Discovered 2026-07-13).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from ..parsers.base import NestedSymbol


@dataclass
class SignalRecord:
    """A raw observation extracted from a single file (TARGET 4.1).

    ``kind`` is the signal type (for example ``port``, ``url_reference``,
    ``db_driver``, ``endpoint``, ``cli_command``, ``ui_action``, ``env_var``,
    ``framework``). ``value`` is a JSON-serializable structured payload.
    ``line`` is 1-based where locatable, else None.
    """

    kind: str
    value: Any = None
    line: Optional[int] = None

    def to_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value, "line": self.line}

    @classmethod
    def from_dict(cls, d: dict) -> SignalRecord:
        return cls(kind=d["kind"], value=d.get("value"), line=d.get("line"))


def _symbol_to_dict(s: NestedSymbol) -> dict:
    d = asdict(s)
    # tuples round-trip through JSON as lists; keep as list for the cache.
    d["path"] = list(s.path)
    return d


def _symbol_from_dict(d: dict) -> NestedSymbol:
    return NestedSymbol(
        name=d["name"],
        kind=d["kind"],
        line=d["line"],
        end_line=d["end_line"],
        visibility=d.get("visibility", "internal"),
        docstring=d.get("docstring"),
        code_preview=d.get("code_preview", ""),
        parent_index=d.get("parent_index"),
        path=tuple(d.get("path", (d["name"],))),
        via_regex=d.get("via_regex", False),
    )


@dataclass
class FileFacts:
    """The cached extraction result for one file."""

    path: str
    language: str
    content_hash: str
    parser_version: str
    lines: int
    size_bytes: int
    parse_status: str = "parsed"
    symbols: list[NestedSymbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    module_doc: Optional[str] = None
    signals: list[SignalRecord] = field(default_factory=list)
    # Raw decoded file text, cached so Tier 3 derivation (config parsing, docs,
    # testing, SwiftUI flow) reads content from the store instead of the disk
    # (TARGET-ARCHITECTURE.md 4.3: "reading cached content, not the disk").
    # Content is content-addressed, so identical-content files share it safely;
    # only ``path`` is per-file and is overridden by the runner on a cache hit.
    content: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "language": self.language,
            "content_hash": self.content_hash,
            "parser_version": self.parser_version,
            "lines": self.lines,
            "size_bytes": self.size_bytes,
            "parse_status": self.parse_status,
            "symbols": [_symbol_to_dict(s) for s in self.symbols],
            "imports": list(self.imports),
            "module_doc": self.module_doc,
            "signals": [s.to_dict() for s in self.signals],
            "content": self.content,
        }

    @classmethod
    def from_dict(cls, d: dict) -> FileFacts:
        return cls(
            path=d["path"],
            language=d["language"],
            content_hash=d["content_hash"],
            parser_version=d["parser_version"],
            lines=d["lines"],
            size_bytes=d["size_bytes"],
            parse_status=d.get("parse_status", "parsed"),
            symbols=[_symbol_from_dict(s) for s in d.get("symbols", [])],
            imports=list(d.get("imports", [])),
            module_doc=d.get("module_doc"),
            signals=[SignalRecord.from_dict(s) for s in d.get("signals", [])],
            content=d.get("content"),
        )
