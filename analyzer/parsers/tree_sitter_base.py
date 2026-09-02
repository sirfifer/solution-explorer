"""Base class for tree-sitter parsers. There is no regex fallback.

This class used to answer every question twice: with tree-sitter if it could,
and with a regex parser if it could not. Both answers looked identical to
everything downstream, which is what made it dangerous. On 2026-08-24 a private large-repository validation corpus
regeneration ran without tree-sitter installed and produced 355,617 symbols
instead of 153,231, with 55 methods where there should have been 28,501, while
the analyzer reported 100% coverage and zero gaps throughout.

Now a missing grammar stops the run, and a file tree-sitter cannot read is
recorded as an unread file rather than answered badly. The regex modules survive
only as helpers each parser delegates to for framework and import sniffing,
which tree-sitter is not doing here; they are never a substitute for symbol
extraction again.
"""

import logging
from typing import Optional

from ..models import Symbol
from .base import BaseParser, NestedSymbol

logger = logging.getLogger(__name__)

# Token-stream normalization vocabulary (P5-6 clone detection). Kept
# language-agnostic: literal container/leaf types collapse to one placeholder
# and comment subtrees are dropped, across every tree-sitter grammar we load.
_COMMENT_TYPES = frozenset({"comment", "line_comment", "block_comment", "doc_comment"})
_LITERAL_TYPES = frozenset({
    "string", "integer", "float", "number", "true", "false", "none", "null",
    "nil", "boolean", "char", "character", "regex", "template_string",
    "concatenated_string", "raw_string", "byte", "rune",
})


class TreeSitterParser(BaseParser):
    """Base class for tree-sitter parsers.

    Subclasses set _language, _parser, _regex_parser, and _ts_available
    in __init__, then override _extract_symbols_ts and _extract_imports_ts.
    """

    _language = None
    _parser = None
    _regex_parser: BaseParser
    _ts_available: bool = False

    # Files tree-sitter could not read, across every parser in this process.
    # Module-level on purpose: the question "is this one odd file or a broken
    # parser" can only be answered by the total, not by any single failure.
    UNREADABLE: list[tuple[str, str, str]] = []

    # Past this many unread files, the explanation stopped being "the subject
    # contains something strange" and became "this parser does not work". A
    # handful of exotic files in a large repository is ordinary; fifty is a bug,
    # and continuing would quietly ship a projection missing whole regions.
    UNREADABLE_LIMIT = 50

    def _record_unreadable(self, file_path: str, exc: Exception) -> None:
        """Record a file that could not be read, and stop if there are too many.

        Never substitutes a weaker answer. The file contributes nothing rather
        than contributing something wrong, because a plausible wrong answer is
        indistinguishable downstream from a right one, which is the whole reason
        the fallback tier was removed.
        """
        from . import DegradedParserError

        entry = (type(self).__name__, file_path, f"{type(exc).__name__}: {exc}")
        TreeSitterParser.UNREADABLE.append(entry)
        logger.warning(
            "tree-sitter could not read %s with %s (%s); recorded as unread, "
            "not approximated", file_path, entry[0], entry[2],
        )
        if len(TreeSitterParser.UNREADABLE) > self.UNREADABLE_LIMIT:
            sample = "; ".join(f"{f} ({e})" for _, f, e in TreeSitterParser.UNREADABLE[:5])
            raise DegradedParserError(
                f"{len(TreeSitterParser.UNREADABLE)} files could not be read by "
                f"tree-sitter, which is past the point where this is a property of "
                f"the subject rather than of the parser. Stopping rather than "
                f"publishing a map with holes in it. First failures: {sample}"
            )

    def _refuse_without_grammar(self) -> None:
        """Stop the run rather than answer with a weaker parser."""
        if not self._ts_available:
            from . import DegradedParserError

            raise DegradedParserError(
                f"{type(self).__name__} has no tree-sitter grammar loaded, so this "
                f"file cannot be read properly. The run is stopping instead of "
                f"falling back to regex extraction, which would produce a "
                f"projection that looks complete and is not. Install the grammars "
                f"(pip install -e '.[treesitter]') and run again."
            )

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        self._refuse_without_grammar()
        try:
            return self._extract_symbols_ts(content, file_path)
        except Exception as exc:
            # One file tree-sitter cannot read is reported as an unread file, and
            # never as a regex approximation of one. The count is what decides
            # whether this is a strange file in the subject or a broken parser,
            # and _record_unreadable makes that call.
            self._record_unreadable(file_path, exc)
            return []

    def extract_imports(self, content: str) -> list[str]:
        self._refuse_without_grammar()
        try:
            return self._extract_imports_ts(content)
        except Exception as exc:
            self._record_unreadable("<imports>", exc)
            return []

    def extract_nested_symbols(self, content: str, file_path: str) -> list[NestedSymbol]:
        """Emit nested symbols (methods, inner types) with parent references.

        Tree-sitter gives exact node ranges, so the 500-line block-end bound of
        the regex path is dropped here (TARGET-ARCHITECTURE.md 4.1). A file that
        cannot be read is reported as unread, never approximated.
        """
        self._refuse_without_grammar()
        try:
            out: list[NestedSymbol] = []
            root = self._parse(content)
            self._extract_nested_ts(
                root, content, file_path, out, parent_index=None, path=()
            )
            return out
        except Exception as exc:
            self._record_unreadable(file_path, exc)
            return []

    # --- Token stream for clone fingerprinting (P5-6, additive) ----------

    def token_stream(self, content: str) -> Optional[list[tuple[int, str, str]]]:
        """Leaf tokens as ``(line, norm, raw)`` in source order, for clone
        detection (P5-6, LENS-DESIGN.md section 9). Returns ``None`` when
        tree-sitter is unavailable, so the caller skips the file (regex-only
        files never participate in clone clusters; recorded deviation).

        Normalization supports type-2 (renamed) clone matching: comments are
        dropped, string/number/boolean literals collapse to ``LIT`` and
        identifiers to ``ID`` (so renamed variables and changed constants still
        match), while operators, punctuation, and keywords keep their literal
        text (anonymous tree-sitter leaves whose type equals their source text),
        preserving structure. ``raw`` is the un-normalized token, which the
        caller hashes to tell an exact (type-1) clone from a renamed one.

        This method only reads the parsed tree; it does not touch the disk. It
        is called exclusively by P5-6 extraction and changes no existing path.
        """
        if not self._ts_available:
            return None
        try:
            root = self._parse(content)
        except Exception as exc:  # noqa: BLE001 - degrade to no tokens, never crash
            logger.debug(
                "tree-sitter tokenize failed (%s: %s)", type(exc).__name__, exc
            )
            return None

        out: list[tuple[int, str, str]] = []
        # Explicit stack, children pushed reversed so pops yield source order.
        # A plain recursion would risk RecursionError on deeply nested trees.
        stack = [root]
        while stack:
            node = stack.pop()
            ntype = node.type
            if ntype in _COMMENT_TYPES or "comment" in ntype:
                continue  # drop the whole comment subtree
            if ntype in _LITERAL_TYPES or ntype.endswith("_literal"):
                # Collapse the whole literal (including multi-child strings) to
                # one normalized placeholder token; do not descend into its
                # pieces. The raw token keeps the literal's actual text so an
                # exact (type-1) clone stays distinct from a renamed (type-2) one
                # where a constant value changed.
                out.append((
                    node.start_point[0] + 1, "LIT",
                    node.text.decode("utf-8", "replace"),
                ))
                continue
            if node.child_count == 0:
                line = node.start_point[0] + 1
                if node.is_named:
                    # A named leaf that is neither literal nor comment is an
                    # identifier-like token.
                    out.append((line, "ID", node.text.decode("utf-8", "replace")))
                else:
                    # Anonymous leaf: operator, punctuation, or keyword. Its type
                    # equals its source text, kept verbatim to preserve shape.
                    out.append((line, ntype, ntype))
                continue
            for child in reversed(node.children):
                stack.append(child)
        return out

    def _extract_nested_ts(self, root, content, file_path, out, parent_index, path) -> None:
        """Walk the tree-sitter tree appending NestedSymbol records.

        Subclasses override this. ``out`` is the flat per-file list; a symbol's
        ``parent_index`` points at its parent's position in ``out`` (or None at
        top level) and ``path`` is the enclosing descriptor chain.
        """
        raise NotImplementedError

    def _emit_nested(self, node, content, out, parent_index, path, name, kind,
                     visibility="internal", docstring=None) -> int:
        """Append one NestedSymbol built from a node and return its index."""
        idx = len(out)
        out.append(NestedSymbol(
            name=name,
            kind=kind,
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            visibility=visibility,
            docstring=docstring if docstring is not None
            else self._get_preceding_comment(node, content),
            code_preview=self._node_code_preview(node, content),
            parent_index=parent_index,
            path=tuple(path) + (name,),
        ))
        return idx

    # Delegate all regex-based methods to the underlying regex parser
    def detect_framework(self, content: str) -> Optional[str]:
        return self._regex_parser.detect_framework(content)

    def extract_file_doc(self, content: str) -> Optional[str]:
        return self._regex_parser.extract_file_doc(content)

    def extract_env_vars(self, content: str) -> list[str]:
        return self._regex_parser.extract_env_vars(content)

    def detect_ports(self, content: str) -> list[int]:
        return self._regex_parser.detect_ports(content)

    def detect_api_endpoints(self, content: str) -> list[dict]:
        return self._regex_parser.detect_api_endpoints(content)

    # --- Subclass hooks ---

    def _extract_symbols_ts(self, content: str, file_path: str) -> list[Symbol]:
        raise NotImplementedError

    def _extract_imports_ts(self, content: str) -> list[str]:
        raise NotImplementedError

    # --- Shared utilities ---

    def _parse(self, content: str):
        """Parse content and return the root node."""
        tree = self._parser.parse(bytes(content, "utf-8"))
        return tree.root_node

    def _node_text(self, node) -> str:
        """Get the decoded text of a node."""
        return node.text.decode("utf-8")

    def _find_child_by_type(self, node, type_name: str):
        """Find the first child with the given type."""
        for child in node.children:
            if child.type == type_name:
                return child
        return None

    def _find_children_by_type(self, node, type_name: str) -> list:
        """Find all children with the given type."""
        return [c for c in node.children if c.type == type_name]

    def _get_preceding_comment(self, node, content: str) -> Optional[str]:
        """Extract doc comment immediately before a node."""
        lines = content.split("\n")
        return self._extract_docstring_before(lines, node.start_point[0])

    def _node_code_preview(self, node, content: str, max_lines: int = 5) -> str:
        """Get a code preview for a node."""
        lines = content.split("\n")
        return self._get_code_preview(lines, node.start_point[0], max_lines)
