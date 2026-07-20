"""Symbol-reference extraction for Tier 1 (D5, P9-0 gate defect wave B).

The gate found code-level relationship extraction far too sparse: the iOS
projection carried 93 edges for 190 components, nearly all UI navigation, and
intra-module type usage produced nothing, so core engines read as orphans (D4).

This module closes that gap at extraction time. For each supported language it
scans a file's content for the NAMES of type-like symbols it references (type
usages, constructor calls, conformances, casts, generics) and emits one
``symbol_reference`` signal per distinct referenced name, carrying the
first-seen line and a reference count. Tier 3 derivation
(:mod:`analyzer.derive.relationships`) resolves those names against the store's
own symbol table and draws component-to-component ``uses`` edges. This is a
NAME-based join, deliberately KISS (invariant I1: mechanical, no type inference,
no call-graph): a referenced name that matches no local type definition simply
resolves to nothing (stdlib and framework names harmlessly drop out), and an
ambiguous name that resolves to several components is dropped at derive time
rather than guessed.

Only reference candidates whose START is real code are kept: a name appearing
inside a string literal or a ``#`` comment is not a usage, so the shared
:class:`~analyzer.extract.frameworks.StringMask` filters them. Extraction is
deterministic (invariant I4): names are emitted in first-occurrence order and
the per-file candidate scan is capped (:data:`MAX_REFERENCE_NAMES`) so a
pathological generated file cannot blow up signal volume.

Extractor maturity is honest and per-language (:data:`REFERENCE_LANGUAGES`).
Swift, Python, TypeScript, and JavaScript have reference extractors here; Go,
Rust, and Ruby do not yet, and the D4 orphan reframing consults this set so it
never asserts "unreferenced" about a substantial component whose language we
barely scan for references.
"""

from __future__ import annotations

import re

from .facts import SignalRecord
from .frameworks import StringMask

__all__ = ["REFERENCE_LANGUAGES", "MAX_REFERENCE_NAMES", "extract_reference_signals"]

# Languages with a symbol-reference extractor below. The D4 orphan reframing
# treats every OTHER language as a "weak" reference extractor (honest maturity).
REFERENCE_LANGUAGES = frozenset({"swift", "python", "typescript", "javascript"})

# Cap on distinct referenced names emitted per file. A generated or minified
# file can name thousands of identifiers; beyond this the marginal edge value is
# nil and the scan cost is not worth it. Recorded scale guard (D5).
MAX_REFERENCE_NAMES = 400

# A referenced type-like name: an uppercase-initial identifier. group(1) is the
# name in every pattern. These are intentionally simple anchors; precision comes
# from resolving against real local type definitions at derive time, not from
# the regex. Constructor/call `Name(` is common to all four languages.
_CTOR = r"\b([A-Z]\w+)\s*\("
_ANNOT = r":\s*([A-Z]\w+)"          # `: Type` annotation / conformance
_RETURN = r"->\s*([A-Z]\w+)"        # `-> Type` return type

_REFERENCE_RULES: dict[str, list[re.Pattern]] = {
    "swift": [
        re.compile(_CTOR),
        re.compile(_ANNOT),
        re.compile(_RETURN),
        re.compile(r"\b(?:as[?!]?|is)\s+([A-Z]\w+)"),   # casts: `as Foo`, `is Foo`
        re.compile(r"<\s*([A-Z]\w+)"),                   # generic argument
    ],
    "python": [
        re.compile(_CTOR),
        re.compile(_ANNOT),
        re.compile(_RETURN),
        re.compile(r"\bclass\s+\w+\s*\(\s*([A-Z]\w+)"),  # base class
    ],
    "typescript": [
        re.compile(r"\bnew\s+([A-Z]\w+)"),
        re.compile(_ANNOT),
        re.compile(r"\bextends\s+([A-Z]\w+)"),
        re.compile(r"\bimplements\s+([A-Z]\w+)"),
        re.compile(r"<\s*([A-Z]\w+)"),                   # generic / JSX open
    ],
    "javascript": [
        re.compile(r"\bnew\s+([A-Z]\w+)"),
        re.compile(r"\bextends\s+([A-Z]\w+)"),
        re.compile(r"<\s*([A-Z]\w+)"),                   # JSX open tag
    ],
}


def _line_of(content: str, pos: int) -> int:
    return content.count("\n", 0, pos) + 1


def extract_reference_signals(
    content: str, language: str, mask: StringMask
) -> list[SignalRecord]:
    """Emit ``symbol_reference`` signals for one file (D5).

    Each signal value is ``{"name": <referenced type name>, "count": <n>}`` with
    the 1-based line of the first occurrence. Names are emitted in
    first-occurrence order (deterministic, invariant I4). ``mask`` is the shared
    :class:`StringMask` so a name inside a string or ``#`` comment is not counted
    as a reference.
    """
    rules = _REFERENCE_RULES.get(language)
    if not rules:
        return []
    # name -> [first_pos, count]. Insertion order is first-occurrence order once
    # candidates are processed in position order, so sort matches by start.
    candidates: list[tuple[int, str]] = []
    for pat in rules:
        for m in pat.finditer(content):
            start = m.start(1)
            if mask.in_string(start):
                continue  # inside a string literal or comment, not a reference
            candidates.append((start, m.group(1)))
    candidates.sort()

    agg: dict[str, list[int]] = {}
    for start, name in candidates:
        entry = agg.get(name)
        if entry is None:
            if len(agg) >= MAX_REFERENCE_NAMES:
                continue  # scale guard: stop taking new distinct names
            agg[name] = [start, 1]
        else:
            entry[1] += 1

    ordered = sorted(agg.items(), key=lambda kv: (kv[1][0], kv[0]))
    return [
        SignalRecord("symbol_reference", {"name": name, "count": count},
                     _line_of(content, first_pos))
        for name, (first_pos, count) in ordered
    ]
