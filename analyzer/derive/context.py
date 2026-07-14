"""Shared derivation state, ported from the scanner's instance model.

A :class:`Deriver` holds the working set a run of Tier 3 passes mutates:
the component map, the file list rebuilt from the store, per-file symbol counts,
and the signal index. It mirrors the parts of ``ArchitectureScanner`` the
derivation passes need, but every field read comes from a :class:`StoreView`
and every content read goes through its :class:`StoreFS` shim, so the passes
touch zero source files (TARGET-ARCHITECTURE.md 4.3).

The passes live in components.py, roles.py, relationships.py, docs.py,
testing.py and flow.py and operate on a Deriver instance; pipeline.py sequences
them and flushes the result to the store.
"""

from __future__ import annotations

import os
from collections import defaultdict
from typing import Optional

from ..models import Component, FileInfo, Symbol
from .storeview import StoreView


class Deriver:
    """Working state for a single-repo derivation over the store."""

    def __init__(self, view: StoreView, root_name: str, repo: str = "."):
        self.view = view
        self.root_name = root_name
        self.repo = repo
        self.root = view.fs.root  # a StorePath; stands in for scanner's self.root

        self._component_map: dict[str, Component] = {}
        self._all_files: list[FileInfo] = []
        self._all_symbols: list[Symbol] = []
        self._vendored_paths: set[str] = set()
        self._language_counts: dict[str, int] = defaultdict(int)
        self._total_lines = 0
        self._total_size = 0
        self._ui_relationships: list = []
        self._ui_edge_evidence: dict = {}
        self.relationships: list = []
        self._rel_evidence: dict = {}
        self._rel_confidence: dict = {}
        self._rel_origin: dict = {}

        # Capabilities derived by the capabilities pass (P5-1). ``capabilities``
        # is the flat, id-sorted index; ``_capabilities_by_component`` maps an
        # owning component id to its capability dicts.
        self.capabilities: list[dict] = []
        self._capabilities_by_component: dict[str, list[dict]] = {}

        # Data entities and access edges derived by the entities pass (P5-2).
        # ``data_entities``/``entity_access`` are flat, sorted indexes;
        # ``_entities_by_component`` maps an owning component id to its entities.
        self.data_entities: list[dict] = []
        self.entity_access: list[dict] = []
        self._entities_by_component: dict[str, list[dict]] = {}

        # Rules derived by the rules pass (P5-5). ``rules`` is the flat,
        # id-sorted index; ``_rules_by_component`` maps an owning component id to
        # its rule dicts.
        self.rules: list[dict] = []
        self._rules_by_component: dict[str, list[dict]] = {}

        # Per-file symbol ids from the store, so metrics and file records match
        # the nested-symbol reality (grammar ids, methods included).
        self._symbol_ids_by_file: dict[str, list[str]] = defaultdict(list)
        id_to_path = {f["id"]: f["path"] for f in view.files}
        # Build Symbol objects from the store for the top-level symbol array.
        for s in view.symbols:
            fpath = id_to_path.get(s.get("file_id"))
            if fpath is None:
                continue
            self._symbol_ids_by_file[fpath].append(s["id"])
            self._all_symbols.append(Symbol(
                id=s["id"], name=s["name"], kind=s.get("kind") or "",
                file=fpath, line=s.get("line") or 0, end_line=s.get("end_line") or 0,
                code_preview=s.get("code_preview") or "",
                visibility=s.get("visibility") or "internal",
                docstring=s.get("docstring"),
                parent=s.get("parent_id"),
            ))

    # -- id + parent helpers (identical semantics to the scanner) ----------

    def _make_component_id(self, rel_path: str) -> str:
        if not rel_path:
            return "root"
        return rel_path.replace(os.sep, "/").replace(" ", "-").lower()

    def _find_parent_component(self, rel_path: str) -> Optional[str]:
        if not rel_path:
            return None
        parts = rel_path.split(os.sep)
        for i in range(len(parts) - 1, -1, -1):
            parent = os.sep.join(parts[:i])
            if not parent:
                parent = ""
            if parent in self._component_map and parent != rel_path:
                return parent
        return "" if "" in self._component_map else None

    def _find_component_for_file(self, file_path: str) -> Optional[Component]:
        parts = file_path.split(os.sep)
        for i in range(len(parts) - 1, -1, -1):
            dir_path = os.sep.join(parts[:i])
            if not dir_path:
                dir_path = ""
            if dir_path in self._component_map:
                return self._component_map[dir_path]
        return self._component_map.get("")

    def _is_under_vendored(self, rel_path: str) -> bool:
        for vp in self._vendored_paths:
            if rel_path.startswith(vp + os.sep):
                return True
        return False

    # -- directory model reconstructed from the store ---------------------

    def files_in_dir(self, rel_dir: str) -> list[str]:
        """Filenames directly inside ``rel_dir`` (not recursive)."""
        out = []
        for p in self.view.all_paths:
            if os.path.dirname(p) == rel_dir:
                out.append(os.path.basename(p))
        return sorted(out)

    def child_dirs(self, rel_dir: str) -> list[str]:
        prefix = f"{rel_dir}/" if rel_dir else ""
        seen: set[str] = set()
        for d in self.view.dir_paths:
            if d == rel_dir or not d:
                continue
            if prefix and not d.startswith(prefix):
                continue
            rest = d[len(prefix):]
            if "/" not in rest:
                seen.add(rest)
        return sorted(seen)

    def all_dirs_sorted(self) -> list[str]:
        return sorted(self.view.dir_paths)
