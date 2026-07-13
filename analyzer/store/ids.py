"""Symbol identity grammar for the v2 fact store.

This module defines and FREEZES the symbol ID grammar for Program 2
(TARGET-ARCHITECTURE.md sections 4.2 and 6, invariant I4). The grammar is
SCIP-inspired: human-readable, globally unique, stable across runs, and
mergeable across repositories. Nothing in a later phase may change this
grammar without a recorded decision and a migration; every projection,
enrichment record, and annotation keys on these strings.

The store must never import from scanner.py or incremental.py; this module
depends only on the Python standard library.

======================================================================
FROZEN GRAMMAR
======================================================================

A symbol ID is four space-separated segments::

    <symbol-id> := <repo> SP <component> SP <file> SP <symbol-path>

    <repo>        := field        # "." means the local / current repo
    <component>   := field        # owning component id, "." means root
    <file>        := field        # repo-relative file path
    <symbol-path> := descriptor ( "/" descriptor )* ( "#" <digits> )?
    <descriptor>  := field        # one nested name (class, then method, ...)
    <field>       := bareword | quoted
    <bareword>    := one or more characters, none reserved at that level
    <quoted>      := "`" ( char | "``" )* "`"
    SP            := U+0020 (a single space)

Segment separator is a single space. Symbol-path nesting separator is "/"
(class then method then inner symbol). A trailing "#<digits>" on the
symbol-path is the collision disambiguator (see below); it is absent for the
common case of a uniquely named symbol.

Reserved characters, by level:

    | level                    | reserved (force quoting) |
    |--------------------------|--------------------------|
    | repo / component / file  | space, backtick          |
    | descriptor               | space, "/", "#", backtick |

"/" is a normal character inside the repo, component, and file segments (they
are paths), so paths render verbatim and stay readable. "/" is a separator
only inside the symbol-path, so a descriptor whose name contains "/" is
quoted. "#" is reserved only inside a descriptor so it can never be confused
with the disambiguator marker.

Escaping table (a token is quoted iff it is empty or contains a reserved
character or a backtick):

    | raw token          | encoded token         |
    |--------------------|-----------------------|
    | Foo                | Foo                   |
    | (empty string)     | ``  (two backticks)   |
    | a b   (has space)  | `a b`                 |
    | a/b as descriptor  | `a/b`                 |
    | a#b as descriptor  | `a#b`                 |
    | a`b  (has backtick)| `a``b`                |
    | `     (a backtick) | ````  (four backticks)|

Quoting is reversible: inside a quoted token every literal backtick is
doubled, so the closing backtick is always unambiguous.

Multi-repo prefixing: single-repo analysis uses repo "." (SCIP's "local"
convention). Multi-repo analysis sets the repo segment to the repo name, so
IDs from different repos never collide and per-repo stores merge cleanly.
This replaces the old ``repo_name/`` string-prefix hack, which mutated every
component, file, and symbol id in place.

Projection escaping stays out of the store. The component-id filename escapes
("/" -> "--", ":" -> "__") from analyzer/cli.py::safe_component_id are a
projection-layer concern for shard filenames on NTFS/GitHub artifacts. They
MUST NOT appear in store IDs. Store IDs carry raw component ids; the
projection layer escapes them when it writes files.

Collision behavior: repo, component, file, and symbol-path do not include a
line number, so IDs stay stable when unrelated code above a symbol shifts
lines (the old ``file:name:line`` scheme broke on every edit). Two sibling
symbols that share a fully qualified path (an overload, or two module-level
functions of the same name) would otherwise produce the same ID. The builder
resolves this deterministically: within one analysis, symbols are assigned in
source order; the first occurrence of a colliding path gets no disambiguator,
and each later occurrence gets "#2", "#3", ... appended to its symbol-path.
This favors stability for the common (unique) case while guaranteeing global
uniqueness. See :func:`assign_symbol_ids`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = [
    "LOCAL_REPO",
    "ROOT_COMPONENT",
    "SymbolId",
    "encode_token",
    "decode_token",
    "build_symbol_id",
    "parse_symbol_id",
    "assign_symbol_ids",
]

# Sentinels (convention, not grammar). The grammar round-trips any string.
LOCAL_REPO = "."
ROOT_COMPONENT = "."

_SEGMENT_RESERVED = " "        # space only; "/" is a legal path character here
_DESCRIPTOR_RESERVED = " /#"   # space, path separator, disambiguator marker
_BACKTICK = "`"

_DISAMBIGUATOR_RE = re.compile(r"#(\d+)$")


# ---------------------------------------------------------------------------
# Token encode / decode (the escaping primitive)
# ---------------------------------------------------------------------------

def encode_token(token: str, reserved: str = _SEGMENT_RESERVED) -> str:
    """Encode a single token, quoting it if it is empty or reserved.

    A token is emitted verbatim when it is non-empty and contains no reserved
    character and no backtick. Otherwise it is wrapped in backticks with every
    internal backtick doubled, which makes the closing backtick unambiguous.
    """
    if token != "" and _BACKTICK not in token and not any(c in reserved for c in token):
        return token
    return _BACKTICK + token.replace(_BACKTICK, _BACKTICK + _BACKTICK) + _BACKTICK


def decode_token(token: str) -> str:
    """Reverse :func:`encode_token` for one already-isolated token."""
    if len(token) >= 2 and token[0] == _BACKTICK and token[-1] == _BACKTICK:
        return token[1:-1].replace(_BACKTICK + _BACKTICK, _BACKTICK)
    return token


def _split_unquoted(s: str, sep: str) -> list[str]:
    """Split ``s`` on single-char ``sep`` outside backtick-quoted regions.

    Doubled backticks inside a quote are literal and do not toggle the quote
    state, so separators inside quoted tokens are preserved.
    """
    parts: list[str] = []
    buf: list[str] = []
    in_quote = False
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == _BACKTICK:
            if in_quote and i + 1 < n and s[i + 1] == _BACKTICK:
                buf.append(_BACKTICK + _BACKTICK)
                i += 2
                continue
            in_quote = not in_quote
            buf.append(c)
            i += 1
            continue
        if c == sep and not in_quote:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts


def _find_disambiguator(symbolpath: str) -> tuple[str, int]:
    """Strip a trailing ``#<digits>`` that sits outside any quoted region.

    Returns (symbolpath_without_disambiguator, disambiguator) where a
    disambiguator of 0 means none was present.
    """
    m = _DISAMBIGUATOR_RE.search(symbolpath)
    if not m:
        return symbolpath, 0
    # The "#" must be outside a quote to count as a disambiguator marker.
    hash_pos = m.start()
    in_quote = False
    i = 0
    while i < hash_pos:
        c = symbolpath[i]
        if c == _BACKTICK:
            if in_quote and i + 1 < hash_pos and symbolpath[i + 1] == _BACKTICK:
                i += 2
                continue
            in_quote = not in_quote
        i += 1
    if in_quote:
        return symbolpath, 0
    return symbolpath[:hash_pos], int(m.group(1))


# ---------------------------------------------------------------------------
# SymbolId value type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SymbolId:
    """A parsed, frozen symbol identity.

    ``path`` is the nested descriptor chain, outermost first, for example
    ``("Foo", "bar")`` for method ``bar`` inside class ``Foo``.
    ``disambiguator`` of 0 means none.
    """

    repo: str
    component: str
    file: str
    path: tuple[str, ...] = field(default_factory=tuple)
    disambiguator: int = 0

    def encode(self) -> str:
        return build_symbol_id(
            self.repo, self.component, self.file, self.path, self.disambiguator
        )

    def base(self) -> SymbolId:
        """Return the same identity with the disambiguator removed."""
        return SymbolId(self.repo, self.component, self.file, self.path, 0)


def build_symbol_id(
    repo: str,
    component: str,
    file: str,
    path,
    disambiguator: int = 0,
) -> str:
    """Encode the four segments into a frozen-grammar symbol ID string."""
    path = tuple(path)
    if not path:
        raise ValueError("symbol id requires at least one descriptor in the path")
    if disambiguator < 0:
        raise ValueError("disambiguator must be non-negative")
    repo_seg = encode_token(repo, _SEGMENT_RESERVED)
    comp_seg = encode_token(component, _SEGMENT_RESERVED)
    file_seg = encode_token(file, _SEGMENT_RESERVED)
    sym_seg = "/".join(encode_token(p, _DESCRIPTOR_RESERVED) for p in path)
    if disambiguator:
        sym_seg = f"{sym_seg}#{disambiguator}"
    return f"{repo_seg} {comp_seg} {file_seg} {sym_seg}"


def parse_symbol_id(s: str) -> SymbolId:
    """Parse a frozen-grammar symbol ID string back into a :class:`SymbolId`."""
    fields = _split_unquoted(s, " ")
    if len(fields) != 4:
        raise ValueError(
            f"symbol id must have 4 space-separated segments, got {len(fields)}: {s!r}"
        )
    repo_seg, comp_seg, file_seg, sym_seg = fields
    body, disambiguator = _find_disambiguator(sym_seg)
    descriptors = tuple(decode_token(d) for d in _split_unquoted(body, "/"))
    return SymbolId(
        repo=decode_token(repo_seg),
        component=decode_token(comp_seg),
        file=decode_token(file_seg),
        path=descriptors,
        disambiguator=disambiguator,
    )


def assign_symbol_ids(records) -> list[str]:
    """Assign globally unique IDs to an ordered batch, resolving collisions.

    ``records`` is an iterable of (repo, component, file, path) tuples in
    source order. The first occurrence of a colliding base identity keeps a
    bare ID; each later occurrence gets "#2", "#3", ... appended. Order in,
    order out.
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for repo, component, file, path in records:
        base = build_symbol_id(repo, component, file, path, 0)
        count = seen.get(base, 0) + 1
        seen[base] = count
        disambiguator = 0 if count == 1 else count
        out.append(build_symbol_id(repo, component, file, path, disambiguator))
    return out
