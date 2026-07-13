"""In-memory read model over the fact store, plus a content-backed FS shim.

Tier 3 derivation reads only the store (TARGET-ARCHITECTURE.md 4.3). This
module loads the extraction facts a derivation pass needs (files, per-file
content and imports from the extraction cache, symbols, and signals) into a
:class:`StoreView`, and exposes a :class:`StoreFS` that mimics the small slice
of ``pathlib.Path`` behaviour the reused helpers (``config_parsers``,
``SwiftUIFlowDetector``, ``UIActionDetector``) call. The shim serves file
content from the store instead of the disk, so those helpers run unchanged and
still touch zero source files (see instrumentation.py).

The file universe comes from the coverage ledger (every enumerated file, so a
marker or config file that was excluded from parsing still ``exists()``); file
*content* is available only for files the extraction tier cached (parsed
files). A read of an uncached file raises ``OSError``, exactly as an absent
file would on disk, so the reused helpers degrade identically.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from ..store import FactStore

_DIR_DISPOSITIONS = ("excluded:skipped_directory", "excluded:vendored_repo")


@dataclass
class StoreView:
    """Everything a derivation pass reads, loaded once from the store."""

    files: list[dict]
    symbols: list[dict]
    content_by_path: dict[str, str]
    imports_by_path: dict[str, list[str]]
    module_doc_by_path: dict[str, Optional[str]]
    signals_by_path: dict[str, list[dict]]
    all_paths: list[str]           # every enumerated file (from the ledger)
    dir_paths: set[str]            # directories inferred from file paths
    vendored_dirs: set[str]        # dirs the extraction tier marked vendored
    _fs: StoreFS = field(init=False)

    def __post_init__(self) -> None:
        self._fs = StoreFS(self)

    @property
    def fs(self) -> StoreFS:
        return self._fs

    def content(self, path: str) -> Optional[str]:
        return self.content_by_path.get(path)

    def imports(self, path: str) -> list[str]:
        return self.imports_by_path.get(path, [])

    def signals(self, path: str) -> list[dict]:
        return self.signals_by_path.get(path, [])

    @classmethod
    def load(cls, store: FactStore) -> StoreView:
        files = store.files()
        symbols = store.symbols()
        id_to_path = {f["id"]: f["path"] for f in files}

        facts_by_hash = store.cached_facts_by_hash()
        content_by_path: dict[str, str] = {}
        imports_by_path: dict[str, list[str]] = {}
        module_doc_by_path: dict[str, Optional[str]] = {}
        for f in files:
            facts = facts_by_hash.get(f["content_hash"])
            if facts is None:
                continue
            if facts.get("content") is not None:
                content_by_path[f["path"]] = facts["content"]
            imports_by_path[f["path"]] = list(facts.get("imports", []))
            module_doc_by_path[f["path"]] = facts.get("module_doc")

        signals_by_path: dict[str, list[dict]] = {}
        for sig in store.signals():
            path = id_to_path.get(sig["file_id"])
            if path is not None:
                signals_by_path.setdefault(path, []).append(sig)

        # The full enumerated-file universe (parsed + excluded + binary +
        # failed), so existence checks on non-parsed marker/config files work.
        all_paths = [
            c["path"] for c in store.coverage()
            if c["disposition"] not in _DIR_DISPOSITIONS
        ]
        dir_paths: set[str] = {""}
        for p in list(all_paths) + list(content_by_path):
            d = os.path.dirname(p)
            while d:
                dir_paths.add(d)
                d = os.path.dirname(d)
        # Excluded directory rows are real directories too.
        vendored_dirs: set[str] = set()
        for c in store.coverage():
            if c["disposition"] in _DIR_DISPOSITIONS:
                dir_paths.add(c["path"])
            if c["disposition"] == "excluded:vendored_repo":
                vendored_dirs.add(c["path"])

        return cls(
            files=files,
            symbols=symbols,
            content_by_path=content_by_path,
            imports_by_path=imports_by_path,
            module_doc_by_path=module_doc_by_path,
            signals_by_path=signals_by_path,
            all_paths=sorted(set(all_paths)),
            dir_paths=dir_paths,
            vendored_dirs=vendored_dirs,
        )


class StorePath:
    """A ``pathlib.Path``-like view of one store path, backed by StoreView.

    Only the operations the reused helpers call are implemented. ``read_text``
    / ``read_bytes`` serve cached content and raise ``OSError`` when a path has
    no cached content, mirroring an absent or unreadable file on disk.
    """

    __slots__ = ("_view", "_rel")

    def __init__(self, view: StoreView, rel: str):
        self._view = view
        self._rel = rel.strip("/") if rel not in ("", ".") else ""

    # -- joining / naming --------------------------------------------------

    def __truediv__(self, other: str) -> StorePath:
        other = str(other).strip("/")
        joined = f"{self._rel}/{other}" if self._rel else other
        return StorePath(self._view, joined)

    @property
    def parent(self) -> StorePath:
        return StorePath(self._view, os.path.dirname(self._rel))

    @property
    def name(self) -> str:
        return os.path.basename(self._rel)

    @property
    def suffix(self) -> str:
        base = os.path.basename(self._rel)
        _, dot, ext = base.rpartition(".")
        return f".{ext}" if dot else ""

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(p for p in self._rel.split("/") if p)

    def __str__(self) -> str:
        return self._rel

    def __repr__(self) -> str:
        return f"StorePath({self._rel!r})"

    # -- existence ---------------------------------------------------------

    def exists(self) -> bool:
        return self.is_file() or self.is_dir()

    def is_file(self) -> bool:
        return self._rel in self._view.content_by_path or (
            self._rel in set(self._view.all_paths)
        )

    def is_dir(self) -> bool:
        return self._rel in self._view.dir_paths

    def iterdir(self):
        prefix = f"{self._rel}/" if self._rel else ""
        seen: set[str] = set()
        for p in self._view.all_paths:
            if prefix and not p.startswith(prefix):
                continue
            if not prefix and "/" in p:
                child = p.split("/", 1)[0]
            else:
                rest = p[len(prefix):]
                child = rest.split("/", 1)[0] if "/" in rest else rest
            if child and child not in seen:
                seen.add(child)
                yield self / child

    def rglob(self, pattern: str):
        # Only "*" is used by the callers (test-dir sweeps).
        prefix = f"{self._rel}/" if self._rel else ""
        for p in self._view.all_paths:
            if prefix and p.startswith(prefix):
                yield StorePath(self._view, p)

    # -- reads (from the store cache, never the disk) ----------------------

    def read_text(self, encoding: str = "utf-8", errors: str = "strict") -> str:
        content = self._view.content_by_path.get(self._rel)
        if content is None:
            raise OSError(f"no cached content for {self._rel!r}")
        return content

    def read_bytes(self) -> bytes:
        return self.read_text(errors="replace").encode("utf-8")


class StoreFS:
    """Factory for :class:`StorePath` objects rooted at the store's repo root."""

    def __init__(self, view: StoreView):
        self._view = view

    @property
    def root(self) -> StorePath:
        return StorePath(self._view, "")

    def path(self, rel: str) -> StorePath:
        return StorePath(self._view, rel)

    def __truediv__(self, other: str) -> StorePath:
        return self.root / other
