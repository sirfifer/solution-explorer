"""C++ tree-sitter parser with regex fallback.

Handles namespaces (including nested ``a::b`` form), classes, structs, unions,
enums, templates (the wrapping ``template<...>`` is transparent), inline and
out-of-line method definitions, method prototypes, nested types, and ``#include``
directives (angle vs quoted). Falls back to the regex parser when the
tree-sitter-cpp grammar wheel is unavailable.
"""

from typing import Optional

from ..models import Symbol
from .cpp import CppParser
from .tree_sitter_base import TreeSitterParser

try:
    import tree_sitter_cpp as tscpp
    from tree_sitter import Language, Parser

    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False

_TYPE_SPECIFIERS = {
    "class_specifier": "class",
    "struct_specifier": "struct",
    "union_specifier": "union",
    "enum_specifier": "enum",
}

# Default access of a member before any access-specifier section: private in a
# class, public in a struct or union.
_DEFAULT_MEMBER_VIS = {
    "class_specifier": "private",
    "struct_specifier": "public",
    "union_specifier": "public",
}


class CppTreeSitterParser(TreeSitterParser):
    """C++ parser using tree-sitter with regex fallback."""

    def __init__(self):
        self._regex_parser = CppParser()
        self._ts_available = _TS_AVAILABLE
        if _TS_AVAILABLE:
            self._language = Language(tscpp.language())
            self._parser = Parser(self._language)

    # --- symbols ---------------------------------------------------------

    def _extract_symbols_ts(self, content: str, file_path: str) -> list[Symbol]:
        # The nested walker is the single source of truth for structure; the flat
        # list is derived from it so the two tiers never drift.
        out: list = []
        root = self._parse(content)
        self._walk(root, content, out, parent_index=None, path=())
        return [
            Symbol(
                id=self._make_symbol_id(file_path, ns.name, ns.line),
                name=ns.name, kind=ns.kind, file=file_path,
                line=ns.line, end_line=ns.end_line,
                code_preview=ns.code_preview, visibility=ns.visibility,
                docstring=ns.docstring,
            )
            for ns in out
        ]

    def _extract_nested_ts(self, root, content, file_path, out, parent_index, path) -> None:
        self._walk(root, content, out, parent_index, path)

    def _walk(self, node, content, out, parent_index, path) -> None:
        """Emit declarations that are direct members of a container node."""
        for child in node.children:
            t = child.type
            if t == "template_declaration":
                self._walk(child, content, out, parent_index, path)
            elif t.startswith("preproc_if") or t.startswith("preproc_el"):
                # Include guards and #if/#ifdef/#ifndef blocks wrap real
                # declarations; descend so a header behind an include guard still
                # yields its symbols.
                self._walk(child, content, out, parent_index, path)
            elif t == "linkage_specification":
                dl = self._find_child_by_type(child, "declaration_list")
                if dl is not None:
                    self._walk(dl, content, out, parent_index, path)
            elif t == "namespace_definition":
                self._emit_namespace(child, content, out, parent_index, path)
            elif t in _TYPE_SPECIFIERS:
                self._emit_type(child, content, out, parent_index, path)
            elif t == "function_definition":
                if not self._emit_macro_type(child, content, out, parent_index, path):
                    self._emit_free_function(child, content, out, parent_index, path)
            elif t == "declaration":
                if not self._emit_macro_type(child, content, out, parent_index, path):
                    self._emit_declaration(child, content, out, parent_index, path)

    def _emit_namespace(self, node, content, out, parent_index, path) -> None:
        name = self._namespace_name(node)
        dl = self._find_child_by_type(node, "declaration_list")
        if name:
            idx = self._emit_nested(
                node, content, out, parent_index, path, name, "namespace",
                visibility="public",
            )
            if dl is not None:
                self._walk(dl, content, out, idx, tuple(path) + (name,))
        elif dl is not None:
            # Anonymous namespace: transparent, its members keep the outer scope.
            self._walk(dl, content, out, parent_index, path)

    def _emit_type(self, spec, content, out, parent_index, path) -> None:
        name = self._type_name(spec)
        if not name:
            return  # anonymous struct/union/enum
        body = self._find_child_by_type(spec, "field_declaration_list")
        if spec.type == "enum_specifier":
            has_def = self._find_child_by_type(spec, "enumerator_list") is not None
        else:
            has_def = body is not None
        if not has_def:
            # A body-less specifier is a forward declaration (`class Foo;`) or an
            # elaborated-type usage (`struct Foo bar;`), not a definition. The
            # real definition supplies the symbol; emitting here would fabricate
            # a duplicate and, for the usage form, a wrong one. Skip (matches the
            # regex tier, which also ignores forward declarations).
            return
        kind = _TYPE_SPECIFIERS[spec.type]
        idx = self._emit_nested(
            spec, content, out, parent_index, path, name, kind, visibility="public",
        )
        if body is None:
            return
        default_vis = _DEFAULT_MEMBER_VIS.get(spec.type, "public")
        self._walk_members(body, content, out, idx, tuple(path) + (name,), default_vis)

    def _walk_members(self, body, content, out, parent_index, path, vis) -> None:
        current = vis
        for m in body.children:
            t = m.type
            if t == "access_specifier":
                kw = self._access_keyword(m)
                if kw:
                    current = kw
            elif t in _TYPE_SPECIFIERS:
                self._emit_type(m, content, out, parent_index, path)
            elif t == "function_definition":
                if not self._emit_macro_type(m, content, out, parent_index, path):
                    self._emit_member_function(m, content, out, parent_index, path, current)
            elif t in ("field_declaration", "declaration"):
                if self._emit_macro_type(m, content, out, parent_index, path):
                    continue
                spec = self._first_type_specifier(m)
                if spec is not None:
                    self._emit_type(spec, content, out, parent_index, path)
                    continue
                fd = self._find_function_declarator(m)
                if fd is not None:
                    name = self._declarator_name(fd)
                    if name:
                        self._emit_nested(
                            m, content, out, parent_index, path, name, "method",
                            visibility=current,
                        )

    def _emit_free_function(self, node, content, out, parent_index, path) -> None:
        fd = self._find_function_declarator(node)
        if fd is None:
            return
        name = self._declarator_name(fd)
        if not name:
            return
        kind = "method" if self._is_qualified(fd) else "function"
        self._emit_nested(
            node, content, out, parent_index, path, name, kind, visibility="public",
        )

    def _emit_member_function(self, node, content, out, parent_index, path, vis) -> None:
        fd = self._find_function_declarator(node)
        if fd is None:
            return
        name = self._declarator_name(fd)
        if name:
            self._emit_nested(
                node, content, out, parent_index, path, name, "method", visibility=vis,
            )

    def _emit_declaration(self, node, content, out, parent_index, path) -> None:
        spec = self._first_type_specifier(node)
        if spec is not None:
            self._emit_type(spec, content, out, parent_index, path)
            return
        fd = self._find_function_declarator(node)
        if fd is not None:
            name = self._declarator_name(fd)
            if name:
                kind = "method" if self._is_qualified(fd) else "function"
                self._emit_nested(
                    node, content, out, parent_index, path, name, kind,
                    visibility="public",
                )

    # --- export-macro recovery -------------------------------------------

    def _macro_type_specifier(self, node):
        """Recover a class/struct/union hidden behind an export/visibility macro.

        `class SPDLOG_API registry { ... }` cannot be parsed cleanly without
        expanding the macro, so tree-sitter mistakes the macro for the type name
        and detaches the body. The mis-parse is recognizable: the node's first
        child is a body-less class/struct/union specifier (the macro taken as the
        name), the REAL name follows as a bare ``identifier`` sibling, and the
        members sit in a sibling ``compound_statement``. Requiring the
        compound_statement is what keeps this from firing on an elaborated-type
        variable (`struct Foo bar;`), which has no body. Returns
        ``(kind, name, body)`` or None.
        """
        if not node.children:
            return None
        first = node.children[0]
        if first.type not in _TYPE_SPECIFIERS:
            return None
        if self._find_child_by_type(first, "field_declaration_list") is not None:
            return None  # a well-formed type, not the mangled case
        body = self._find_child_by_type(node, "compound_statement")
        if body is None:
            return None  # no body: a forward decl or elaborated-type variable
        name = None
        for c in node.children[1:]:
            if c is body:
                break
            if c.type in ("identifier", "type_identifier"):
                name = self._node_text(c)
                break
        if not name:
            return None
        return (_TYPE_SPECIFIERS[first.type], name, body)

    def _emit_macro_type(self, node, content, out, parent_index, path) -> bool:
        info = self._macro_type_specifier(node)
        if info is None:
            return False
        kind, name, body = info
        idx = self._emit_nested(
            node, content, out, parent_index, path, name, kind, visibility="public",
        )
        default_vis = "public" if kind in ("struct", "union") else "private"
        self._walk_mangled_members(
            body, content, out, idx, tuple(path) + (name,), default_vis,
        )
        return True

    def _walk_mangled_members(self, body, content, out, parent_index, path, vis) -> None:
        """Extract members from the detached body of an export-macro type.

        After the mis-parse the body is a ``compound_statement`` whose access
        sections appear as ``labeled_statement`` (``public:``) and whose members
        are ``declaration`` / ``function_definition`` nodes.
        """
        current = vis
        for m in body.children:
            if m.type == "labeled_statement":
                si = self._find_child_by_type(m, "statement_identifier")
                if si is not None:
                    kw = self._node_text(si)
                    if kw in ("public", "private", "protected"):
                        current = kw
                for inner in m.children:
                    if inner.type in ("declaration", "field_declaration",
                                      "function_definition"):
                        self._emit_mangled_member(
                            inner, content, out, parent_index, path, current,
                        )
            elif m.type in ("declaration", "field_declaration", "function_definition"):
                self._emit_mangled_member(m, content, out, parent_index, path, current)
            elif m.type in _TYPE_SPECIFIERS:
                self._emit_type(m, content, out, parent_index, path)

    def _emit_mangled_member(self, m, content, out, parent_index, path, vis) -> None:
        spec = self._first_type_specifier(m)
        if spec is not None and self._find_child_by_type(
                spec, "field_declaration_list") is not None:
            self._emit_type(spec, content, out, parent_index, path)
            return
        if self._emit_macro_type(m, content, out, parent_index, path):
            return
        fd = self._find_function_declarator(m)
        if fd is not None:
            name = self._declarator_name(fd)
            if name:
                self._emit_nested(
                    m, content, out, parent_index, path, name, "method",
                    visibility=vis,
                )

    # --- imports ---------------------------------------------------------

    def _extract_imports_ts(self, content: str) -> list[str]:
        root = self._parse(content)
        imports: list[str] = []
        self._collect_includes(root, imports)
        return imports

    def _collect_includes(self, node, imports) -> None:
        for child in node.children:
            if child.type == "preproc_include":
                sysstr = self._find_child_by_type(child, "system_lib_string")
                if sysstr is not None:
                    imports.append(self._node_text(sysstr).strip("<>"))
                    continue
                strlit = self._find_child_by_type(child, "string_literal")
                if strlit is not None:
                    sc = self._find_child_by_type(strlit, "string_content")
                    if sc is not None:
                        imports.append(self._node_text(sc))
            elif child.type == "translation_unit" or child.type.startswith("preproc_"):
                # Includes may sit inside #if / #ifdef guards.
                self._collect_includes(child, imports)

    # --- helpers ---------------------------------------------------------

    def _type_name(self, node) -> Optional[str]:
        ti = self._find_child_by_type(node, "type_identifier")
        return self._node_text(ti) if ti is not None else None

    def _namespace_name(self, node) -> Optional[str]:
        ni = self._find_child_by_type(node, "namespace_identifier")
        if ni is not None:
            return self._node_text(ni)
        nested = self._find_child_by_type(node, "nested_namespace_specifier")
        if nested is not None:
            parts = [
                self._node_text(c)
                for c in nested.children
                if c.type == "namespace_identifier"
            ]
            return "::".join(parts) if parts else None
        return None

    def _first_type_specifier(self, node):
        for c in node.children:
            if c.type in _TYPE_SPECIFIERS:
                return c
        return None

    def _find_function_declarator(self, node):
        for c in node.children:
            if c.type == "function_declarator":
                return c
            if c.type in ("pointer_declarator", "reference_declarator",
                          "parenthesized_declarator"):
                fd = self._find_function_declarator(c)
                if fd is not None:
                    return fd
        return None

    def _is_qualified(self, fd) -> bool:
        return self._find_child_by_type(fd, "qualified_identifier") is not None

    def _declarator_name(self, fd) -> Optional[str]:
        for c in fd.children:
            if c.type in ("identifier", "field_identifier", "destructor_name",
                          "operator_name"):
                return self._node_text(c)
            if c.type == "qualified_identifier":
                return self._qualified_terminal(c)
            if c.type == "template_function":
                for gc in c.children:
                    if gc.type in ("identifier", "field_identifier"):
                        return self._node_text(gc)
        return None

    def _qualified_terminal(self, node) -> Optional[str]:
        inner = self._find_child_by_type(node, "qualified_identifier")
        if inner is not None:
            return self._qualified_terminal(inner)
        for c in node.children:
            if c.type in ("identifier", "field_identifier", "destructor_name",
                          "operator_name"):
                return self._node_text(c)
        return None

    def _access_keyword(self, node) -> Optional[str]:
        for c in node.children:
            if c.type in ("public", "private", "protected"):
                return c.type
        text = self._node_text(node).replace(":", "").strip()
        return text if text in ("public", "private", "protected") else None
