"""TypeScript/JavaScript tree-sitter parser with regex fallback."""

from typing import Optional

from ..models import Symbol
from .tree_sitter_base import TreeSitterParser
from .typescript import TypeScriptParser

try:
    import tree_sitter_typescript as ts_typescript
    from tree_sitter import Language, Parser

    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False

_TYPE_NODES = {
    "class_declaration": "class",
    "abstract_class_declaration": "class",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
}


class TypeScriptTreeSitterParser(TreeSitterParser):
    """TypeScript/JavaScript parser using tree-sitter with regex fallback."""

    def __init__(self):
        self._regex_parser = TypeScriptParser()
        self._ts_available = _TS_AVAILABLE
        if _TS_AVAILABLE:
            # TSX grammar is a superset that handles .ts/.tsx/.js/.jsx
            self._language = Language(ts_typescript.language_tsx())
            self._parser = Parser(self._language)

    def _extract_symbols_ts(self, content: str, file_path: str) -> list[Symbol]:
        root = self._parse(content)
        symbols = []
        self._walk_top_level(root, content, file_path, symbols, exported=False)
        return symbols

    def _walk_top_level(self, node, content, file_path, symbols, exported):
        """Walk top-level nodes extracting symbols."""
        for child in node.children:
            # export_statement wraps a declaration
            if child.type == "export_statement":
                self._walk_top_level(child, content, file_path, symbols, exported=True)
                continue

            vis = "public" if exported else "internal"

            if child.type in _TYPE_NODES:
                kind = _TYPE_NODES[child.type]
                name = self._get_name(child)
                if not name:
                    continue
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, child.start_point[0] + 1),
                    name=name, kind=kind, file=file_path,
                    line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    code_preview=self._node_code_preview(child, content),
                    visibility=vis,
                    docstring=self._get_preceding_comment(child, content),
                ))

            elif child.type == "function_declaration":
                name = self._get_name(child)
                if not name:
                    continue
                kind = self._classify_function(name, content, file_path)
                symbols.append(Symbol(
                    id=self._make_symbol_id(file_path, name, child.start_point[0] + 1),
                    name=name, kind=kind, file=file_path,
                    line=child.start_point[0] + 1,
                    end_line=child.end_point[0] + 1,
                    code_preview=self._node_code_preview(child, content),
                    visibility=vis,
                    docstring=self._get_preceding_comment(child, content),
                ))

            elif child.type == "lexical_declaration":
                # const Foo = () => { ... }
                for declarator in self._find_children_by_type(child, "variable_declarator"):
                    name_node = self._find_child_by_type(declarator, "identifier")
                    if not name_node:
                        continue
                    name = self._node_text(name_node)
                    kind = self._classify_function(name, content, file_path)
                    symbols.append(Symbol(
                        id=self._make_symbol_id(file_path, name, child.start_point[0] + 1),
                        name=name, kind=kind, file=file_path,
                        line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        code_preview=self._node_code_preview(child, content),
                        visibility=vis,
                        docstring=self._get_preceding_comment(child, content),
                    ))

    def _extract_nested_ts(self, node, content, file_path, out, parent_index, path,
                           exported=False) -> None:
        """Emit types, functions, and class methods with parent references."""
        for child in node.children:
            if child.type == "export_statement":
                self._extract_nested_ts(
                    child, content, file_path, out, parent_index, path, exported=True
                )
                continue

            vis = "public" if exported else "internal"

            if child.type in _TYPE_NODES:
                name = self._get_name(child)
                if not name:
                    continue
                idx = self._emit_nested(
                    child, content, out, parent_index, path, name,
                    _TYPE_NODES[child.type], visibility=vis,
                )
                body = self._find_child_by_type(child, "class_body")
                if body is not None:
                    self._extract_nested_class_body(
                        body, content, out, idx, tuple(path) + (name,)
                    )

            elif child.type == "function_declaration":
                name = self._get_name(child)
                if not name:
                    continue
                self._emit_nested(
                    child, content, out, parent_index, path, name,
                    self._classify_function(name, content, file_path), visibility=vis,
                )

            elif child.type == "lexical_declaration":
                for declarator in self._find_children_by_type(child, "variable_declarator"):
                    name_node = self._find_child_by_type(declarator, "identifier")
                    if not name_node:
                        continue
                    name = self._node_text(name_node)
                    self._emit_nested(
                        child, content, out, parent_index, path, name,
                        self._classify_function(name, content, file_path), visibility=vis,
                    )

    def _extract_nested_class_body(self, body, content, out, parent_index, path) -> None:
        """Emit method definitions inside a class body with the class as parent."""
        for member in body.children:
            if member.type == "method_definition":
                name_node = self._find_child_by_type(member, "property_identifier")
                if name_node is None:
                    name_node = self._find_child_by_type(member, "identifier")
                if name_node is None:
                    continue
                name = self._node_text(name_node)
                vis = "private" if name.startswith("_") or name.startswith("#") else "public"
                self._emit_nested(
                    member, content, out, parent_index, path, name,
                    "method", visibility=vis,
                )

    def _extract_imports_ts(self, content: str) -> list[str]:
        root = self._parse(content)
        imports = set()
        for node in root.children:
            if node.type == "import_statement":
                source = self._find_child_by_type(node, "string")
                if source:
                    mod = self._node_text(source).strip("'\"")
                    if mod.startswith("."):
                        imports.add(mod)
                    else:
                        parts = mod.split("/")
                        if parts[0].startswith("@") and len(parts) > 1:
                            imports.add(f"{parts[0]}/{parts[1]}")
                        else:
                            imports.add(parts[0])
        return sorted(imports)

    def _get_name(self, node) -> Optional[str]:
        """Get name from a declaration node."""
        for child in node.children:
            if child.type in ("type_identifier", "identifier"):
                return self._node_text(child)
        return None

    def _classify_function(self, name: str, content: str, file_path: str) -> str:
        """Determine if a function/const is a React component."""
        if name[0].isupper() and (
            "React" in content[:500] or "jsx" in file_path or "tsx" in file_path
        ):
            return "component"
        return "function"
