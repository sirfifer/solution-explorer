"""Go tree-sitter parser with regex fallback."""

from typing import Optional

from ..models import Symbol
from .go import GoParser
from .tree_sitter_base import TreeSitterParser

try:
    import tree_sitter_go as tsgo
    from tree_sitter import Language, Parser

    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False


class GoTreeSitterParser(TreeSitterParser):
    """Go parser using tree-sitter with regex fallback."""

    def __init__(self):
        self._regex_parser = GoParser()
        self._ts_available = _TS_AVAILABLE
        if _TS_AVAILABLE:
            self._language = Language(tsgo.language())
            self._parser = Parser(self._language)

    def _extract_symbols_ts(self, content: str, file_path: str) -> list[Symbol]:
        root = self._parse(content)
        symbols = []

        for node in root.children:
            if node.type == "type_declaration":
                for spec in self._find_children_by_type(node, "type_spec"):
                    name_node = self._find_child_by_type(spec, "type_identifier")
                    if not name_node:
                        continue
                    name = self._node_text(name_node)
                    kind = "struct"
                    if self._find_child_by_type(spec, "interface_type"):
                        kind = "interface"
                    symbols.append(Symbol(
                        id=self._make_symbol_id(file_path, name, node.start_point[0] + 1),
                        name=name, kind=kind, file=file_path,
                        line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        code_preview=self._node_code_preview(node, content),
                        visibility="public" if name[0].isupper() else "private",
                        docstring=self._get_preceding_comment(node, content),
                    ))

            elif node.type == "function_declaration":
                name_node = self._find_child_by_type(node, "identifier")
                if not name_node:
                    continue
                name = self._node_text(name_node)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, node.start_point[0] + 1),
                    name=name, kind="function", file=file_path,
                    line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    code_preview=self._node_code_preview(node, content),
                    visibility="public" if name[0].isupper() else "private",
                    docstring=self._get_preceding_comment(node, content),
                ))

            elif node.type == "method_declaration":
                name_node = self._find_child_by_type(node, "field_identifier")
                if not name_node:
                    continue
                name = self._node_text(name_node)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, node.start_point[0] + 1),
                    name=name, kind="function", file=file_path,
                    line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    code_preview=self._node_code_preview(node, content),
                    visibility="public" if name[0].isupper() else "private",
                    docstring=self._get_preceding_comment(node, content),
                ))

        return symbols

    def _extract_imports_ts(self, content: str) -> list[str]:
        root = self._parse(content)
        imports = set()
        for node in root.children:
            if node.type == "import_declaration":
                self._collect_imports(node, imports)
        return list(imports)

    def _collect_imports(self, node, imports):
        """Recursively collect import paths from import declarations."""
        for child in node.children:
            if child.type == "import_spec_list":
                for spec in child.children:
                    if spec.type == "import_spec":
                        self._extract_import_path(spec, imports)
            elif child.type == "import_spec":
                self._extract_import_path(child, imports)
            elif child.type == "interpreted_string_literal":
                path = self._node_text(child).strip('"')
                imports.add(path.split("/")[-1])

    def _extract_import_path(self, spec, imports):
        for child in spec.children:
            if child.type == "interpreted_string_literal":
                path = self._node_text(child).strip('"')
                imports.add(path.split("/")[-1])
