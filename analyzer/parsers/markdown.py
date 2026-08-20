"""Markdown content extraction for the search index (P7/doc-search fix).

Markdown files carry no code-language parser (``PARSERS`` in
``analyzer/parsers/__init__.py`` registers only code-language extractors), so
``PARSERS.get("markdown")`` is always ``None``. Both extraction tiers gate
their entire per-language pipeline (symbols, imports, framework/port
detection, and in the v2 engine the whole regex signal pipeline in
``analyzer/extract/signals.py``) behind ``if parser:``. Registering a real
``BaseParser`` subclass for "markdown" in that shared registry would silently
turn all of that on for the 233+ markdown files in a typical repo: URL, HTTP
client, DB/queue/websocket/gRPC driver, endpoint, CLI-command, job, UI-action,
and framework signals would all start mining prose for matches that were never
part of this fix's scope, and could pollute the derived architecture graph
with signals mined from documentation text rather than code.

So this module is deliberately NOT registered in ``PARSERS``. It is a plain
function, called explicitly at the two places that build a file's
``module_doc`` (``analyzer/scanner.py`` for the v1 engine,
``analyzer/extract/runner.py`` for the default v2 engine) only when the
file's language is "markdown" and no code parser claimed it. Every other code
path keyed off ``PARSERS.get(lang)`` is untouched for markdown files, exactly
as it was before this fix.
"""

from __future__ import annotations

import re

__all__ = ["extract_markdown_text"]

# A fenced code block, ``` or ~~~, opened and closed by a matching marker.
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

# Markdown line-level markers whose text content, not the marker, is what
# search should match: ATX headings, blockquotes, and list items.
_ATX_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*")
_BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>+\s?")
_UL_ITEM_RE = re.compile(r"^\s*[-*+]\s+")
_OL_ITEM_RE = re.compile(r"^\s*\d+[.)]\s+")

# Pure-punctuation lines that carry no prose: horizontal rules and markdown
# table separator rows (``|---|---|`` / ``| :-- | --: |``).
_HR_RE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]+\|?\s*$")

# Inline markers. Applied after line-level stripping so a heading/list marker
# at the start of a line is already gone before these run.
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)|(?<!_)_([^_\n]+)_(?!_)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def extract_markdown_text(content: str) -> str:
    """Strip markdown syntax noise, keeping the readable prose.

    Headings, list items, and table cells keep their TEXT (the fact-bearing
    content search needs to match) while the syntax markers that spell them
    (``#``, ``-``, ``|``, ``**``) are removed so they do not dilute matches or
    burn the text budget. Links and images keep their visible text and drop
    the URL. Inline code spans keep their content (short identifiers/paths are
    often exactly what search should find).

    Fenced code blocks (both ``` and ~~~) are dropped entirely, deliberately.
    They are usually command transcripts or config/source snippets, not
    natural-language prose a search phrase is likely to match, and keeping
    them would spend a large share of the doc-text budget (``_MAX_DOC_TEXT``
    in ``analyzer/project/search_shards.py``) on syntax and identifiers instead
    of the sentences search is meant to find.

    Table rows are not reconstructed into a structured shape; cell text is
    kept in reading order with pipes turned into spaces, which is enough for
    substring/keyword search even though it loses column alignment.

    Returns a plain string (never None); the caller is responsible for
    whitespace normalization and length capping (``search_shards._clean``).
    """
    lines = content.split("\n")
    out_lines: list[str] = []
    in_fence = False
    fence_marker: str | None = None

    for line in lines:
        m = _FENCE_RE.match(line)
        if m:
            marker = m.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue

        if _HR_RE.match(line) or _TABLE_SEP_RE.match(line):
            continue

        s = line
        s = _ATX_HEADING_RE.sub("", s, count=1)
        s = _BLOCKQUOTE_RE.sub("", s, count=1)
        s = _UL_ITEM_RE.sub("", s, count=1)
        s = _OL_ITEM_RE.sub("", s, count=1)

        s = _IMAGE_RE.sub(lambda mo: mo.group(1), s)
        s = _LINK_RE.sub(lambda mo: mo.group(1), s)
        s = _CODE_SPAN_RE.sub(lambda mo: mo.group(1), s)
        s = _BOLD_RE.sub(lambda mo: mo.group(1) or mo.group(2) or "", s)
        s = _ITALIC_RE.sub(lambda mo: mo.group(1) or mo.group(2) or "", s)
        s = _HTML_TAG_RE.sub("", s)
        s = s.replace("|", " ")

        out_lines.append(s)

    return "\n".join(out_lines)
