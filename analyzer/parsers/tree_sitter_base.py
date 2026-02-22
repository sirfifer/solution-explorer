"""Base class for tree-sitter-based parsers with regex fallback."""

from typing import Optional

from ..models import Symbol
from .base import BaseParser


class TreeSitterParser(BaseParser):
    """Base class for tree-sitter parsers.

    Subclasses set _language, _parser, _regex_parser, and _ts_available
    in __init__, then override _extract_symbols_ts and _extract_imports_ts.
    """

    _language = None
    _parser = None
    _regex_parser: BaseParser
    _ts_available: bool = False

    def extract_symbols(self, content: str, file_path: str) -> list[Symbol]:
        if self._ts_available:
            try:
                return self._extract_symbols_ts(content, file_path)
            except Exception:
                pass
        return self._regex_parser.extract_symbols(content, file_path)

    def extract_imports(self, content: str) -> list[str]:
        if self._ts_available:
            try:
                return self._extract_imports_ts(content)
            except Exception:
                pass
        return self._regex_parser.extract_imports(content)

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
