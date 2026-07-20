"""Java tree-sitter parser with regex fallback."""

from typing import Optional

from ..models import Symbol
from .java import JavaParser
from .tree_sitter_base import TreeSitterParser

try:
    import tree_sitter_java as tsjava
    from tree_sitter import Language, Parser

    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False

# Tree-sitter-java declaration node types mapped to the symbol kind we emit.
_TYPE_DECL_KINDS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "record",
    "annotation_type_declaration": "annotation",
}

# Body node types that hold a type's members, keyed nowhere specific: we scan
# any child body for nested members.
_BODY_TYPES = frozenset({
    "class_body", "interface_body", "enum_body", "annotation_type_body",
})

_ACCESS_MODIFIERS = frozenset({"public", "private", "protected"})


class JavaTreeSitterParser(TreeSitterParser):
    """Java parser using tree-sitter with regex fallback."""

    def __init__(self):
        self._regex_parser = JavaParser()
        self._ts_available = _TS_AVAILABLE
        if _TS_AVAILABLE:
            self._language = Language(tsjava.language())
            self._parser = Parser(self._language)

    def _extract_symbols_ts(self, content: str, file_path: str) -> list[Symbol]:
        root = self._parse(content)
        symbols: list[Symbol] = []
        self._collect_types(root, content, file_path, symbols)
        return symbols

    def _collect_types(self, node, content, file_path, symbols) -> None:
        """Emit every type declaration and its direct methods, recursively.

        Java nests types inside types, so a flat list still walks the whole tree,
        recording each type and the methods declared directly in its body.
        """
        for child in node.children:
            kind = _TYPE_DECL_KINDS.get(child.type)
            if kind:
                name = self._get_type_name(child)
                if name:
                    symbols.append(Symbol(
                        id=self._make_symbol_id(file_path, name, child.start_point[0] + 1),
                        name=name,
                        kind=kind,
                        file=file_path,
                        line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        code_preview=self._node_code_preview(child, content),
                        visibility=self._get_visibility(child),
                        docstring=self._get_preceding_comment(child, content),
                    ))
                    self._emit_methods_flat(child, content, file_path, symbols)
                # Recurse so nested types are recorded too.
                self._collect_types(child, content, file_path, symbols)
            elif child.type in _BODY_TYPES:
                self._collect_types(child, content, file_path, symbols)

    def _emit_methods_flat(self, type_node, content, file_path, symbols) -> None:
        body = self._type_body(type_node)
        if body is None:
            return
        for member in body.children:
            if member.type in ("method_declaration", "constructor_declaration"):
                name = self._get_member_name(member)
                if not name:
                    continue
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, member.start_point[0] + 1),
                    name=name,
                    kind="method",
                    file=file_path,
                    line=member.start_point[0] + 1,
                    end_line=member.end_point[0] + 1,
                    code_preview=self._node_code_preview(member, content),
                    visibility=self._get_visibility(member),
                    docstring=self._get_preceding_comment(member, content),
                ))

    def _extract_nested_ts(self, node, content, file_path, out, parent_index, path) -> None:
        """Emit Java types with true nesting plus each type's members.

        A type's methods, constructors, fields, and inner types are attached to
        it via ``parent_index`` and a descriptor ``path`` (outermost first), so a
        method reads as ``Outer/Inner/method`` in the symbol path.
        """
        for child in node.children:
            kind = _TYPE_DECL_KINDS.get(child.type)
            if kind:
                name = self._get_type_name(child)
                if not name:
                    continue
                idx = self._emit_nested(
                    child, content, out, parent_index, path, name, kind,
                    visibility=self._get_visibility(child),
                )
                self._emit_members(child, content, file_path, out, idx,
                                   tuple(path) + (name,))
            elif child.type in _BODY_TYPES:
                self._extract_nested_ts(child, content, file_path, out,
                                        parent_index, path)

    def _emit_members(self, type_node, content, file_path, out, parent_index, path) -> None:
        body = self._type_body(type_node)
        if body is None:
            return
        for member in body.children:
            if member.type in ("method_declaration", "constructor_declaration"):
                name = self._get_member_name(member)
                if name:
                    self._emit_nested(
                        member, content, out, parent_index, path, name, "method",
                        visibility=self._get_visibility(member),
                    )
            elif member.type == "field_declaration":
                for name in self._field_names(member):
                    self._emit_nested(
                        member, content, out, parent_index, path, name, "field",
                        visibility=self._get_visibility(member),
                    )
            elif member.type in _TYPE_DECL_KINDS:
                nested_name = self._get_type_name(member)
                if not nested_name:
                    continue
                nidx = self._emit_nested(
                    member, content, out, parent_index, path, nested_name,
                    _TYPE_DECL_KINDS[member.type],
                    visibility=self._get_visibility(member),
                )
                self._emit_members(member, content, file_path, out, nidx,
                                   tuple(path) + (nested_name,))

    def _extract_imports_ts(self, content: str) -> list[str]:
        root = self._parse(content)
        imports: list[str] = []
        for node in root.children:
            if node.type == "import_declaration":
                fqn = self._import_fqn(node)
                if fqn:
                    imports.append(fqn)
        return imports

    # --- node helpers ---

    def _type_body(self, type_node):
        for child in type_node.children:
            if child.type in _BODY_TYPES:
                return child
        return None

    def _get_type_name(self, node) -> Optional[str]:
        ident = self._find_child_by_type(node, "identifier")
        return self._node_text(ident) if ident else None

    def _get_member_name(self, node) -> Optional[str]:
        ident = self._find_child_by_type(node, "identifier")
        return self._node_text(ident) if ident else None

    def _field_names(self, field_node) -> list[str]:
        names = []
        for declarator in self._find_children_by_type(field_node, "variable_declarator"):
            ident = self._find_child_by_type(declarator, "identifier")
            if ident:
                names.append(self._node_text(ident))
        return names

    def _get_visibility(self, node) -> str:
        mods = self._find_child_by_type(node, "modifiers")
        if mods:
            for child in mods.children:
                if child.type in _ACCESS_MODIFIERS:
                    return child.type
        return "package"

    def _import_fqn(self, node) -> Optional[str]:
        """Return the fully qualified imported name, appending ``.*`` for a
        wildcard import. ``static`` imports resolve to the same dotted name.
        """
        parts = []
        wildcard = False
        for child in node.children:
            if child.type in ("scoped_identifier", "identifier"):
                parts.append(self._node_text(child))
            elif child.type == "asterisk":
                wildcard = True
        if not parts:
            return None
        fqn = parts[-1]
        if wildcard:
            fqn = fqn + ".*"
        return fqn
