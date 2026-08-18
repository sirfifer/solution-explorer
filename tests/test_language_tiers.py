"""The documented language tiers must match what the parsers actually do.

Both README.md and PROJECT-OVERVIEW.md listed Java, C# and C/C++ as
"detection + metrics only" while `analyzer/parsers/` carried full regex AND
tree-sitter parsers for all three, the treesitter extra pulled their grammars,
and all three were registered. On the repo's own fixtures they produce typed
symbols, framework detection, API endpoints and relationships.

For a product being sold, a capability table that undersells the product is a
defect: "no Java" is what a buyer checks first. This test keeps the tables and
the parsers honest with each other.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from analyzer.parsers import PARSERS

REPO_ROOT = Path(__file__).resolve().parent.parent

# Languages the docs claim full parsing for, keyed by the name used in the
# tables. Kept explicit so adding a language means updating both sides on
# purpose rather than by accident.
FULL_PARSE_LANGS = {
    "Swift": "swift", "Python": "python", "Rust": "rust",
    "TypeScript/JavaScript": "typescript", "Go": "go", "Ruby": "ruby",
    "Java": "java", "C#": "csharp", "C/C++": "cpp",
}


@pytest.mark.parametrize("label,key", sorted(FULL_PARSE_LANGS.items()))
def test_every_documented_full_parse_language_has_a_real_parser(label, key):
    parser = PARSERS.get(key)
    assert parser is not None, f"{label} is documented as full parsing but has no parser"
    for capability in ("extract_symbols", "extract_imports"):
        assert callable(getattr(parser, capability, None)), (
            f"{label} is documented as full parsing but its parser has no {capability}"
        )


@pytest.mark.parametrize("doc", ["README.md", "PROJECT-OVERVIEW.md"])
def test_the_tables_do_not_undersell_a_language_that_is_fully_parsed(doc):
    text = (REPO_ROOT / doc).read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines() if ln.startswith("| **Detection + metrics**")]
    assert rows, f"{doc} has no detection-only row to check"
    for row in rows:
        for label in FULL_PARSE_LANGS:
            # Word-boundary match so "C#" does not trip on "C/C++" and vice versa.
            assert not re.search(rf"(?<![\w/#+]){re.escape(label)}(?![\w/#+])", row), (
                f"{doc} lists {label} as detection-only, but it has a full parser"
            )


@pytest.mark.parametrize("doc", ["README.md", "PROJECT-OVERVIEW.md"])
def test_the_tables_claim_every_language_that_is_fully_parsed(doc):
    text = (REPO_ROOT / doc).read_text(encoding="utf-8")
    rows = [ln for ln in text.splitlines() if ln.startswith("| **Full parsing")]
    assert rows, f"{doc} has no full-parsing row to check"
    claimed = " ".join(rows)
    for label in FULL_PARSE_LANGS:
        assert label in claimed, f"{doc} does not claim {label}, which is fully parsed"
