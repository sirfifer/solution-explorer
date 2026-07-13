"""Swift tree-sitter parser with regex fallback."""

from typing import Optional

from ..models import Symbol
from .swift import SwiftParser
from .tree_sitter_base import TreeSitterParser

try:
    import tree_sitter_swift as tsswift
    from tree_sitter import Language, Parser

    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False

# In tree-sitter-swift 0.0.1, class/struct/enum/extension all use
# class_declaration. The keyword child differentiates them.
_KEYWORD_TO_KIND = {
    "class": "class",
    "struct": "struct",
    "enum": "enum",
    "actor": "actor",
}


class SwiftTreeSitterParser(TreeSitterParser):
    """Swift parser using tree-sitter with regex fallback."""

    def __init__(self):
        self._regex_parser = SwiftParser()
        self._ts_available = _TS_AVAILABLE
        if _TS_AVAILABLE:
            self._language = Language(tsswift.language())
            self._parser = Parser(self._language)

    def _extract_symbols_ts(self, content: str, file_path: str) -> list[Symbol]:
        root = self._parse(content)
        symbols = []

        for node in root.children:
            if node.type == "class_declaration":
                kind = self._get_class_decl_kind(node)
                if kind == "extension":
                    self._handle_extension(node, content, file_path, symbols)
                elif kind:
                    name = self._get_type_name(node)
                    if not name:
                        continue
                    vis = self._get_visibility(node)
                    symbols.append(Symbol(
                        id=self._make_symbol_id(file_path, name, node.start_point[0] + 1),
                        name=name,
                        kind=kind,
                        file=file_path,
                        line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        code_preview=self._node_code_preview(node, content),
                        visibility=vis,
                        docstring=self._get_preceding_comment(node, content),
                    ))
                    self._extract_methods(node, content, file_path, symbols)

            elif node.type == "protocol_declaration":
                name = self._get_type_name(node)
                if not name:
                    continue
                vis = self._get_visibility(node)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, node.start_point[0] + 1),
                    name=name,
                    kind="protocol",
                    file=file_path,
                    line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    code_preview=self._node_code_preview(node, content),
                    visibility=vis,
                    docstring=self._get_preceding_comment(node, content),
                ))

            elif node.type == "function_declaration":
                name = self._get_func_name(node)
                if not name:
                    continue
                vis = self._get_visibility(node)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, node.start_point[0] + 1),
                    name=name,
                    kind="function",
                    file=file_path,
                    line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    code_preview=self._node_code_preview(node, content),
                    visibility=vis,
                    docstring=self._get_preceding_comment(node, content),
                ))

        return symbols

    def _handle_extension(self, node, content, file_path, symbols):
        """Handle an extension declaration."""
        name = self._get_extension_name(node)
        if not name:
            return
        symbols.append(Symbol(
            id=self._make_symbol_id(file_path, f"ext_{name}", node.start_point[0] + 1),
            name=f"extension {name}",
            kind="extension",
            file=file_path,
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            code_preview=self._node_code_preview(node, content),
            docstring=self._get_preceding_comment(node, content),
        ))
        self._extract_methods(node, content, file_path, symbols)

    def _extract_methods(self, parent_node, content, file_path, symbols):
        """Extract function declarations nested inside a type body."""
        for child in parent_node.children:
            if child.type in ("class_body", "enum_class_body", "protocol_body"):
                for member in child.children:
                    if member.type == "function_declaration":
                        name = self._get_func_name(member)
                        if not name:
                            continue
                        vis = self._get_visibility(member)
                        symbols.append(Symbol(
                            id=self._make_symbol_id(file_path, name, member.start_point[0] + 1),
                            name=name,
                            kind="function",
                            file=file_path,
                            line=member.start_point[0] + 1,
                            end_line=member.end_point[0] + 1,
                            code_preview=self._node_code_preview(member, content),
                            visibility=vis,
                            docstring=self._get_preceding_comment(member, content),
                        ))

    def _extract_nested_ts(self, node, content, file_path, out, parent_index, path) -> None:
        """Emit Swift types, protocols, extensions, and their methods."""
        for child in node.children:
            if child.type == "class_declaration":
                kind = self._get_class_decl_kind(child)
                if kind == "extension":
                    name = self._get_extension_name(child)
                    if not name:
                        continue
                    disp = f"extension {name}"
                    idx = self._emit_nested(
                        child, content, out, parent_index, path, disp, "extension",
                    )
                    self._emit_swift_methods(child, content, out, idx, tuple(path) + (disp,))
                elif kind:
                    name = self._get_type_name(child)
                    if not name:
                        continue
                    idx = self._emit_nested(
                        child, content, out, parent_index, path, name, kind,
                        visibility=self._get_visibility(child),
                    )
                    self._emit_swift_methods(child, content, out, idx, tuple(path) + (name,))

            elif child.type == "protocol_declaration":
                name = self._get_type_name(child)
                if not name:
                    continue
                idx = self._emit_nested(
                    child, content, out, parent_index, path, name, "protocol",
                    visibility=self._get_visibility(child),
                )
                self._emit_swift_methods(child, content, out, idx, tuple(path) + (name,))

            elif child.type == "function_declaration":
                name = self._get_func_name(child)
                if not name:
                    continue
                self._emit_nested(
                    child, content, out, parent_index, path, name, "function",
                    visibility=self._get_visibility(child),
                )

    def _emit_swift_methods(self, parent_node, content, out, parent_index, path) -> None:
        """Emit function declarations nested inside a Swift type body."""
        for child in parent_node.children:
            if child.type in ("class_body", "enum_class_body", "protocol_body"):
                for member in child.children:
                    if member.type == "function_declaration":
                        name = self._get_func_name(member)
                        if not name:
                            continue
                        self._emit_nested(
                            member, content, out, parent_index, path, name, "method",
                            visibility=self._get_visibility(member),
                        )

    def _extract_imports_ts(self, content: str) -> list[str]:
        root = self._parse(content)
        imports = []
        for node in root.children:
            if node.type == "import_declaration":
                ident = self._find_child_by_type(node, "identifier")
                if ident:
                    # identifier contains simple_identifier children
                    imports.append(self._node_text(ident))
        return imports

    def _get_class_decl_kind(self, node) -> Optional[str]:
        """Determine the kind of a class_declaration node by its keyword child."""
        for child in node.children:
            if child.type in _KEYWORD_TO_KIND:
                return _KEYWORD_TO_KIND[child.type]
            if child.type == "extension":
                return "extension"
        return None

    def _get_type_name(self, node) -> Optional[str]:
        """Get name from a type_identifier child."""
        for child in node.children:
            if child.type == "type_identifier":
                return self._node_text(child)
        return None

    def _get_extension_name(self, node) -> Optional[str]:
        """Get the extended type name (under user_type > type_identifier)."""
        for child in node.children:
            if child.type == "user_type":
                ti = self._find_child_by_type(child, "type_identifier")
                if ti:
                    return self._node_text(ti)
            if child.type == "type_identifier":
                return self._node_text(child)
        return None

    def _get_func_name(self, node) -> Optional[str]:
        """Get name from a function declaration."""
        for child in node.children:
            if child.type == "simple_identifier":
                return self._node_text(child)
        return None

    def _get_visibility(self, node) -> str:
        """Extract visibility modifier from a declaration."""
        mods = self._find_child_by_type(node, "modifiers")
        if mods:
            vis = self._find_child_by_type(mods, "visibility_modifier")
            if vis:
                text = self._node_text(vis)
                if text in ("public", "open", "private", "fileprivate", "internal"):
                    return text
        return "internal"
