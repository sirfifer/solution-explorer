"""Ruby tree-sitter parser with regex fallback."""

from typing import Optional

from ..models import Symbol
from .ruby import RubyParser
from .tree_sitter_base import TreeSitterParser

try:
    import tree_sitter_ruby as tsruby
    from tree_sitter import Language, Parser

    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False


class RubyTreeSitterParser(TreeSitterParser):
    """Ruby parser using tree-sitter with regex fallback."""

    def __init__(self):
        self._regex_parser = RubyParser()
        self._ts_available = _TS_AVAILABLE
        if _TS_AVAILABLE:
            self._language = Language(tsruby.language())
            self._parser = Parser(self._language)

    def _extract_symbols_ts(self, content: str, file_path: str) -> list[Symbol]:
        root = self._parse(content)
        symbols = []
        self._walk_ruby(root, content, file_path, symbols)
        return symbols

    def _walk_ruby(self, node, content, file_path, symbols):
        """Recursively walk nodes extracting class/module/method symbols."""
        for child in node.children:
            if child.type == "class":
                name = self._get_ruby_name(child)
                if name:
                    symbols.append(Symbol(
                        id=self._make_symbol_id(file_path, name, child.start_point[0] + 1),
                        name=name, kind="class", file=file_path,
                        line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        code_preview=self._node_code_preview(child, content),
                        visibility="public",
                        docstring=self._get_preceding_comment(child, content),
                    ))
                body = self._find_child_by_type(child, "body_statement")
                if body:
                    self._walk_ruby(body, content, file_path, symbols)

            elif child.type == "module":
                name = self._get_ruby_name(child)
                if name:
                    symbols.append(Symbol(
                        id=self._make_symbol_id(file_path, name, child.start_point[0] + 1),
                        name=name, kind="module", file=file_path,
                        line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        code_preview=self._node_code_preview(child, content),
                        visibility="public",
                        docstring=self._get_preceding_comment(child, content),
                    ))
                body = self._find_child_by_type(child, "body_statement")
                if body:
                    self._walk_ruby(body, content, file_path, symbols)

            elif child.type == "method":
                name_node = self._find_child_by_type(child, "identifier")
                if name_node:
                    name = self._node_text(name_node)
                    symbols.append(Symbol(
                        id=self._make_symbol_id(file_path, name, child.start_point[0] + 1),
                        name=name, kind="function", file=file_path,
                        line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        code_preview=self._node_code_preview(child, content),
                        visibility="private" if name.startswith("_") else "public",
                        docstring=self._get_preceding_comment(child, content),
                    ))

            elif child.type == "singleton_method":
                name_node = self._find_child_by_type(child, "identifier")
                if name_node:
                    name = f"self.{self._node_text(name_node)}"
                    symbols.append(Symbol(
                        id=self._make_symbol_id(file_path, name, child.start_point[0] + 1),
                        name=name, kind="function", file=file_path,
                        line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        code_preview=self._node_code_preview(child, content),
                        visibility="public",
                        docstring=self._get_preceding_comment(child, content),
                    ))

    def _extract_imports_ts(self, content: str) -> list[str]:
        # Ruby imports (require/require_relative) are function calls,
        # not syntactic imports. Regex handles them just as well.
        return self._regex_parser.extract_imports(content)

    def _get_ruby_name(self, node) -> Optional[str]:
        """Get name from a class or module node."""
        for child in node.children:
            if child.type == "constant":
                return self._node_text(child)
            if child.type == "scope_resolution":
                return self._node_text(child)
        return None
