"""Python tree-sitter parser with regex fallback."""

from typing import Optional

from ..models import Symbol
from .python_lang import PythonParser
from .tree_sitter_base import TreeSitterParser

try:
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False


class PythonTreeSitterParser(TreeSitterParser):
    """Python parser using tree-sitter with regex fallback."""

    def __init__(self):
        self._regex_parser = PythonParser()
        self._ts_available = _TS_AVAILABLE
        if _TS_AVAILABLE:
            self._language = Language(tspython.language())
            self._parser = Parser(self._language)

    def _extract_symbols_ts(self, content: str, file_path: str) -> list[Symbol]:
        root = self._parse(content)
        symbols = []
        for node in root.children:
            self._process_node(node, content, file_path, symbols)
        return symbols

    def _process_node(self, node, content, file_path, symbols):
        """Process a top-level node, handling decorated definitions."""
        target = node
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type in ("class_definition", "function_definition"):
                    target = child
                    break
            else:
                return

        if target.type == "class_definition":
            name = self._get_py_name(target)
            if not name:
                return
            symbols.append(Symbol(
                id=self._make_symbol_id(file_path, name, node.start_point[0] + 1),
                name=name, kind="class", file=file_path,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                code_preview=self._node_code_preview(node, content),
                visibility="private" if name.startswith("_") else "public",
                docstring=self._get_python_docstring(target),
            ))

        elif target.type == "function_definition":
            name = self._get_py_name(target)
            if not name:
                return
            symbols.append(Symbol(
                id=self._make_symbol_id(file_path, name, node.start_point[0] + 1),
                name=name, kind="function", file=file_path,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                code_preview=self._node_code_preview(node, content),
                visibility="private" if name.startswith("_") else "public",
                docstring=self._get_python_docstring(target),
            ))

    def _extract_imports_ts(self, content: str) -> list[str]:
        root = self._parse(content)
        imports = set()
        for node in root.children:
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        mod = self._node_text(child).split(".")[0]
                        imports.add(mod)
            elif node.type == "import_from_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        mod = self._node_text(child).split(".")[0]
                        imports.add(mod)
                        break  # first dotted_name is the module
        return list(imports)

    def _get_py_name(self, node) -> Optional[str]:
        for child in node.children:
            if child.type == "identifier":
                return self._node_text(child)
        return None

    def _get_python_docstring(self, node) -> Optional[str]:
        """Extract docstring from inside a class/function body."""
        body = self._find_child_by_type(node, "block")
        if not body or not body.children:
            return None
        first = body.children[0]
        if first.type == "expression_statement":
            for child in first.children:
                if child.type == "string":
                    text = self._node_text(child)
                    for q in ('"""', "'''"):
                        if text.startswith(q) and text.endswith(q):
                            return text[3:-3].strip()
                    if text.startswith(("'", '"')):
                        return text[1:-1].strip()
        return None
