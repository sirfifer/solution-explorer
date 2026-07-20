"""C# tree-sitter parser with regex fallback."""

from typing import Optional

from ..models import Symbol
from .csharp import CSharpParser
from .tree_sitter_base import TreeSitterParser

try:
    import tree_sitter_c_sharp as tscsharp
    from tree_sitter import Language, Parser

    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False

# tree-sitter-c-sharp declaration node type -> emitted symbol kind.
_TYPE_DECL_KINDS = {
    "class_declaration": "class",
    "struct_declaration": "struct",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "record_struct_declaration": "record",
}

# Members emitted inside a type body, with their kind.
_MEMBER_DECL_KINDS = {
    "method_declaration": "method",
    "constructor_declaration": "method",
    "property_declaration": "property",
}

# Nodes that hold a type's member declarations.
_BODY_TYPES = ("declaration_list", "enum_member_declaration_list")

# Nodes that introduce a namespace scope (block form and file-scoped form).
_NAMESPACE_TYPES = ("namespace_declaration", "file_scoped_namespace_declaration")

_ACCESS = {"public", "private", "protected", "internal"}


class CSharpTreeSitterParser(TreeSitterParser):
    """C# parser using tree-sitter with regex fallback."""

    def __init__(self):
        self._regex_parser = CSharpParser()
        self._ts_available = _TS_AVAILABLE
        if _TS_AVAILABLE:
            self._language = Language(tscsharp.language())
            self._parser = Parser(self._language)

    def _extract_symbols_ts(self, content: str, file_path: str) -> list[Symbol]:
        root = self._parse(content)
        symbols: list[Symbol] = []
        self._collect_types(root, content, file_path, symbols)
        return symbols

    def _collect_types(self, node, content, file_path, symbols):
        """Walk into namespaces and emit every type and its members (flat)."""
        for child in node.children:
            if child.type in _NAMESPACE_TYPES:
                body = self._find_child_by_type(child, "declaration_list")
                if body is not None:
                    self._collect_types(body, content, file_path, symbols)
                else:
                    # File-scoped namespace: its types are later siblings, so
                    # keep scanning the same parent for them.
                    self._collect_types(child, content, file_path, symbols)
            elif child.type in _TYPE_DECL_KINDS:
                name = self._get_name(child)
                if not name:
                    continue
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, child.start_point[0] + 1),
                    name=name,
                    kind=_TYPE_DECL_KINDS[child.type],
                    file=file_path,
                    line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    code_preview=self._node_code_preview(child, content),
                    visibility=self._get_visibility(child),
                    docstring=self._get_preceding_comment(child, content),
                ))
                self._collect_members(child, content, file_path, symbols)

    def _collect_members(self, type_node, content, file_path, symbols):
        """Emit methods, constructors, and properties inside a type body."""
        for body_type in _BODY_TYPES:
            body = self._find_child_by_type(type_node, body_type)
            if body is None:
                continue
            for member in body.children:
                kind = _MEMBER_DECL_KINDS.get(member.type)
                if not kind:
                    continue
                name = self._get_name(member)
                if not name:
                    continue
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, member.start_point[0] + 1),
                    name=name,
                    kind=kind,
                    file=file_path,
                    line=member.start_point[0] + 1,
                    end_line=member.end_point[0] + 1,
                    code_preview=self._node_code_preview(member, content),
                    visibility=self._get_visibility(member),
                    docstring=self._get_preceding_comment(member, content),
                ))

    def _extract_nested_ts(self, node, content, file_path, out, parent_index, path) -> None:
        """Emit C# types and their members with parent references."""
        for child in node.children:
            if child.type in _NAMESPACE_TYPES:
                body = self._find_child_by_type(child, "declaration_list")
                target = body if body is not None else child
                self._extract_nested_ts(
                    target, content, file_path, out, parent_index, path
                )
            elif child.type in _TYPE_DECL_KINDS:
                name = self._get_name(child)
                if not name:
                    continue
                idx = self._emit_nested(
                    child, content, out, parent_index, path, name,
                    _TYPE_DECL_KINDS[child.type],
                    visibility=self._get_visibility(child),
                )
                self._emit_members(child, content, out, idx, tuple(path) + (name,))

    def _emit_members(self, type_node, content, out, parent_index, path) -> None:
        """Emit a type's members as nested symbols under the type."""
        for body_type in _BODY_TYPES:
            body = self._find_child_by_type(type_node, body_type)
            if body is None:
                continue
            for member in body.children:
                kind = _MEMBER_DECL_KINDS.get(member.type)
                if not kind:
                    continue
                name = self._get_name(member)
                if not name:
                    continue
                self._emit_nested(
                    member, content, out, parent_index, path, name, kind,
                    visibility=self._get_visibility(member),
                )

    def _extract_imports_ts(self, content: str) -> list[str]:
        root = self._parse(content)
        imports = []
        for node in root.children:
            if node.type == "using_directive":
                name = self._using_target(node)
                if name:
                    imports.append(name)
        return imports

    def _using_target(self, node) -> Optional[str]:
        """The namespace/type a using directive names, ignoring alias and static."""
        for child in node.children:
            if child.type in ("qualified_name", "identifier"):
                return self._node_text(child)
        return None

    def _get_name(self, node) -> Optional[str]:
        name = node.child_by_field_name("name")
        return self._node_text(name) if name is not None else None

    def _get_visibility(self, node) -> str:
        for child in node.children:
            if child.type == "modifier":
                text = self._node_text(child).strip()
                if text in _ACCESS:
                    return text
        return "internal"
