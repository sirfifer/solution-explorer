"""Clone-fragment fingerprinting for Tier 1 (P5-6, LENS-DESIGN.md section 9).

Near-duplicate detection needs per-fragment token fingerprints, and Tier 3
derivation must not re-read source (TARGET-ARCHITECTURE.md 4.3), so the
fingerprints are computed here, at extraction time, and cached with the rest of
a file's facts (content-addressed, invariant I6). A "fragment" is one
function/method symbol: the natural clone unit, and fragmenting per callable
avoids double-counting a class body against its own methods.

For each fragment above a minimum normalized-token length the extractor emits a
``clone_fragment`` signal carrying the fragment's line range, token count, a
whole-fragment normalized hash and raw hash (to tell a type-1 exact clone from a
type-2 renamed one), and a winnowing fingerprint set over normalized K-grams
(for type-3 near-duplicate overlap). Winnowing keeps roughly ``2 / (W + 1)`` of
the k-grams while guaranteeing that any shared run of at least ``K + W - 1``
tokens shares a fingerprint (Schleimer, Wilkerson, Aiken 2003). All hashing is
blake2b, never Python ``hash`` (which is PYTHONHASHSEED-salted), so fingerprints
are byte-stable across processes and runs (invariant I4).

Regex-only files (no tree-sitter tokens) produce no fragments and never
participate in clone clusters; this is a recorded scope bound, not a silent
skip (every tree-sitter language we load exposes tokens).
"""

from __future__ import annotations

import hashlib

from .facts import SignalRecord

__all__ = ["extract_clone_signals", "MIN_FRAGMENT_TOKENS", "KGRAM", "WINDOW"]

# Thresholds (recorded in the P5-6 card and proven by the noise test). A
# fragment below MIN_FRAGMENT_TOKENS normalized tokens is dropped so trivial
# getters, boilerplate, and short idioms never enter the cluster search.
MIN_FRAGMENT_TOKENS = 50
KGRAM = 5   # k-gram (shingle) length in normalized tokens
WINDOW = 4  # winnowing window over the k-gram hash sequence

# Symbol kinds that are fragmentable callables. Containers (class, struct,
# module, extension, protocol, impl, type) are skipped: their methods are
# fragmented individually, so a container body never double-counts.
_FRAGMENT_KINDS = frozenset({"function", "method"})


def _hash_int(text: str) -> int:
    """Stable 64-bit fingerprint of a k-gram (never Python ``hash``)."""
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big")


def _hash_hex(tokens: list[str]) -> str:
    """Stable digest of a whole token sequence (norm or raw)."""
    joined = "\x1f".join(tokens)
    return hashlib.blake2b(joined.encode("utf-8"), digest_size=16).hexdigest()


def _fingerprints(norm_tokens: list[str]) -> list[int]:
    """Winnowing fingerprints over the normalized K-gram hash sequence.

    Returns a sorted, de-duplicated fingerprint list. Linear in the token
    count. Set-based (positions are not retained) because downstream similarity
    is fingerprint-set Jaccard, for which the window minima suffice.
    """
    n = len(norm_tokens)
    if n < KGRAM:
        return []
    grams = [
        _hash_int("\x1f".join(norm_tokens[i:i + KGRAM]))
        for i in range(n - KGRAM + 1)
    ]
    if len(grams) <= WINDOW:
        return [min(grams)]
    selected: set[int] = set()
    for i in range(len(grams) - WINDOW + 1):
        selected.add(min(grams[i:i + WINDOW]))
    return sorted(selected)


def extract_clone_signals(content: str, language: str, parser, symbols) -> list[SignalRecord]:
    """Emit ``clone_fragment`` signals for one file (P5-6).

    ``parser`` is the language parser; ``symbols`` are the nested symbols the
    runner already extracted. Returns an empty list when the parser exposes no
    token stream (regex-only files) or the file has no fragmentable callable of
    sufficient length. Deterministic: fragments are emitted in source order and
    every fingerprint list is sorted.
    """
    token_stream = getattr(parser, "token_stream", None)
    if token_stream is None:
        return []
    tokens = token_stream(content)
    if not tokens:
        return []

    # Bucket tokens by line once, so each fragment slice is a range scan.
    by_line: dict[int, list[tuple[str, str]]] = {}
    for line, norm, raw in tokens:
        by_line.setdefault(line, []).append((norm, raw))

    out: list[SignalRecord] = []
    for sym in symbols:
        if sym.kind not in _FRAGMENT_KINDS:
            continue
        start, end = sym.line, sym.end_line
        if not start or not end or end < start:
            continue
        norm_seq: list[str] = []
        raw_seq: list[str] = []
        for ln in range(start, end + 1):
            for norm, raw in by_line.get(ln, ()):  # source order preserved
                norm_seq.append(norm)
                raw_seq.append(raw)
        if len(norm_seq) < MIN_FRAGMENT_TOKENS:
            continue
        out.append(SignalRecord(
            "clone_fragment",
            {
                "symbol": sym.name,
                "line": start,
                "end_line": end,
                "ntokens": len(norm_seq),
                "norm_hash": _hash_hex(norm_seq),
                "raw_hash": _hash_hex(raw_seq),
                "fps": _fingerprints(norm_seq),
            },
            start,
        ))
    return out
