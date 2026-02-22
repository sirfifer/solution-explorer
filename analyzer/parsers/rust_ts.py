"""Rust tree-sitter parser with regex fallback."""

from typing import Optional

from ..models import Symbol
from .rust import RustParser
from .tree_sitter_base import TreeSitterParser

try:
    import tree_sitter_rust as tsrust
    from tree_sitter import Language, Parser

    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False

_TYPE_ITEMS = {
    "struct_item": "struct",
    "enum_item": "enum",
    "trait_item": "trait",
    "union_item": "struct",
}


class RustTreeSitterParser(TreeSitterParser):
    """Rust parser using tree-sitter with regex fallback."""

    def __init__(self):
        self._regex_parser = RustParser()
        self._ts_available = _TS_AVAILABLE
        if _TS_AVAILABLE:
            self._language = Language(tsrust.language())
            self._parser = Parser(self._language)

    def _extract_symbols_ts(self, content: str, file_path: str) -> list[Symbol]:
        root = self._parse(content)
        symbols = []

        for node in root.children:
            if node.type in _TYPE_ITEMS:
                kind = _TYPE_ITEMS[node.type]
                name = self._get_type_name(node)
                if not name:
                    continue
                vis = self._get_rust_visibility(node)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, node.start_point[0] + 1),
                    name=name, kind=kind, file=file_path,
                    line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    code_preview=self._node_code_preview(node, content),
                    visibility=vis,
                    docstring=self._get_preceding_comment(node, content),
                ))

            elif node.type == "impl_item":
                name = self._get_type_name(node)
                if not name:
                    continue
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, f"impl_{name}", node.start_point[0] + 1),
                    name=f"impl {name}", kind="impl", file=file_path,
                    line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    code_preview=self._node_code_preview(node, content),
                    docstring=self._get_preceding_comment(node, content),
                ))

            elif node.type == "function_item":
                name = self._get_func_name(node)
                if not name:
                    continue
                vis = self._get_rust_visibility(node)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, node.start_point[0] + 1),
                    name=name, kind="function", file=file_path,
                    line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    code_preview=self._node_code_preview(node, content),
                    visibility=vis,
                    docstring=self._get_preceding_comment(node, content),
                ))

        return symbols

    def _extract_imports_ts(self, content: str) -> list[str]:
        root = self._parse(content)
        imports = set()
        for node in root.children:
            if node.type == "use_declaration":
                crate = self._get_use_crate(node)
                if crate and crate not in ("self", "super", "crate"):
                    imports.add(crate)
        return list(imports)

    def _get_type_name(self, node) -> Optional[str]:
        for child in node.children:
            if child.type == "type_identifier":
                return self._node_text(child)
        return None

    def _get_func_name(self, node) -> Optional[str]:
        for child in node.children:
            if child.type == "identifier":
                return self._node_text(child)
        return None

    def _get_use_crate(self, node) -> Optional[str]:
        """Extract the top-level crate name from a use declaration."""
        for child in node.children:
            if child.type == "scoped_identifier":
                # Walk to the leftmost identifier
                current = child
                while True:
                    sub = self._find_child_by_type(current, "scoped_identifier")
                    if sub:
                        current = sub
                    else:
                        break
                ident = self._find_child_by_type(current, "identifier")
                if ident:
                    return self._node_text(ident)
            elif child.type == "identifier":
                return self._node_text(child)
            elif child.type == "use_list":
                # use {foo, bar} - rare at top level
                for sub in child.children:
                    if sub.type == "identifier":
                        return self._node_text(sub)
        return None

    def _get_rust_visibility(self, node) -> str:
        vis_mod = self._find_child_by_type(node, "visibility_modifier")
        if vis_mod:
            text = self._node_text(vis_mod)
            if text == "pub":
                return "public"
            if "crate" in text:
                return "internal"
            return "public"
        return "private"
