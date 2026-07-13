"""Go tree-sitter parser with regex fallback."""


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

    def _extract_nested_ts(self, node, content, file_path, out, parent_index, path) -> None:
        """Emit Go types, functions, and methods.

        Go has no lexical nesting of declarations, so types are emitted at the
        file's top level. A method is linked to its receiver type (its parent),
        so it reads as ``Type/Method`` in the symbol path with a real parent
        reference when the receiver type is declared in the same file.
        """
        type_index: dict[str, int] = {}
        for child in node.children:
            if child.type == "type_declaration":
                for spec in self._find_children_by_type(child, "type_spec"):
                    name_node = self._find_child_by_type(spec, "type_identifier")
                    if not name_node:
                        continue
                    name = self._node_text(name_node)
                    kind = "interface" if self._find_child_by_type(
                        spec, "interface_type") else "struct"
                    idx = self._emit_nested(
                        child, content, out, parent_index, path, name, kind,
                        visibility="public" if name[0].isupper() else "private",
                    )
                    type_index[name] = idx

            elif child.type == "function_declaration":
                name_node = self._find_child_by_type(child, "identifier")
                if not name_node:
                    continue
                name = self._node_text(name_node)
                self._emit_nested(
                    child, content, out, parent_index, path, name, "function",
                    visibility="public" if name[0].isupper() else "private",
                )

            elif child.type == "method_declaration":
                name_node = self._find_child_by_type(child, "field_identifier")
                if not name_node:
                    continue
                name = self._node_text(name_node)
                recv = self._method_receiver_type(child)
                if recv is not None and recv in type_index:
                    m_parent = type_index[recv]
                    m_path = tuple(out[m_parent].path)
                else:
                    m_parent = parent_index
                    m_path = tuple(path) + ((recv,) if recv else ())
                self._emit_nested(
                    child, content, out, m_parent, m_path, name, "method",
                    visibility="public" if name[0].isupper() else "private",
                )

    def _method_receiver_type(self, node):
        """Return the receiver type name of a Go method, or None."""
        recv = self._find_child_by_type(node, "parameter_list")
        if recv is None:
            return None
        for pd in self._find_children_by_type(recv, "parameter_declaration"):
            for c in pd.children:
                if c.type == "type_identifier":
                    return self._node_text(c)
                if c.type == "pointer_type":
                    ti = self._find_child_by_type(c, "type_identifier")
                    if ti:
                        return self._node_text(ti)
        return None

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
