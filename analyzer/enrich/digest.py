"""Content digests for enrichment provenance (the FROZEN definition in __init__).

Every function here is a pure, store-only computation over facts already in the
store's tables. blake2b is keyless and unsalted, so digests are byte-stable
across runs and across PYTHONHASHSEED (invariant I4). See the package docstring
for the frozen definition of each digest.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from ..store import FactStore

__all__ = [
    "ARCH_TARGET_ID",
    "component_digest",
    "symbol_digest",
    "endpoint_stub_digest",
    "relationship_digest",
    "architecture_digest",
    "relationship_target_id",
    "DigestIndex",
]

# The fixed sentinel target id for architecture-level enrichment.
ARCH_TARGET_ID = "@architecture"

_DIGEST_SIZE = 32  # blake2b-256


def _h() -> hashlib._Hash:
    return hashlib.blake2b(digest_size=_DIGEST_SIZE)


def component_digest(members: Iterable[tuple[str, str]]) -> str:
    """Digest of a component's member files (definition 1).

    ``members`` is an iterable of ``(path, content_hash)`` pairs. They are
    sorted by path here, so the caller need not pre-sort. An empty component
    hashes the empty input to a fixed, stable digest.
    """
    h = _h()
    for path, content_hash in sorted(members):
        h.update(path.encode("utf-8"))
        h.update(b"\x00")
        h.update((content_hash or "").encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def symbol_digest(file_content_hash: str, symbol_id: str) -> str:
    """Digest of a symbol: its file content hash plus its span-normalized id (definition 2)."""
    h = _h()
    h.update((file_content_hash or "").encode("utf-8"))
    h.update(b"\x00")
    h.update(symbol_id.encode("utf-8"))
    return h.hexdigest()


def endpoint_stub_digest(endpoint_id: str) -> str:
    """Stable stand-in digest for a relationship endpoint that is not a component."""
    h = _h()
    h.update(b"id:")
    h.update(endpoint_id.encode("utf-8"))
    return h.hexdigest()


def relationship_digest(source_digest: str, target_digest: str, type: str) -> str:
    """Digest of a relationship: the two endpoint digests plus the type (definition 3)."""
    h = _h()
    h.update(source_digest.encode("utf-8"))
    h.update(b"\x00")
    h.update(target_digest.encode("utf-8"))
    h.update(b"\x00")
    h.update(type.encode("utf-8"))
    return h.hexdigest()


def architecture_digest(component_digests: Iterable[tuple[str, str]]) -> str:
    """Digest of the whole architecture: the ordered component-digest list (definition 4).

    ``component_digests`` is an iterable of ``(component_id, digest)`` pairs;
    they are sorted by component id here.
    """
    h = _h()
    for component_id, digest in sorted(component_digests):
        h.update(component_id.encode("utf-8"))
        h.update(b"\x00")
        h.update(digest.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def relationship_target_id(source: str, target: str, type: str) -> str:
    """The ``enrichment.target_id`` string for a relationship (see package docstring)."""
    return f"{source}|{target}|{type}"


class DigestIndex:
    """All current digests for a store, computed once and looked up by target.

    Built from the store's own tables (components, component_files, files,
    symbols, edges). Every digest follows the frozen definition in the package
    docstring. Use :meth:`for_target` to get the current digest for an
    enrichment row's ``(target_kind, target_id)``; returns ``None`` when the
    target no longer exists in the store (an orphaned enrichment row).
    """

    def __init__(
        self,
        component: dict[str, str],
        symbol: dict[str, str],
        relationship: dict[str, str],
        architecture: str,
    ):
        self.component = component
        self.symbol = symbol
        self.relationship = relationship  # keyed by relationship_target_id string
        self.architecture = architecture

    @classmethod
    def from_store(cls, store: FactStore) -> DigestIndex:
        files = store.files()
        hash_by_file_id: dict[int, str] = {f["id"]: (f["content_hash"] or "") for f in files}

        # Component member (path, content_hash) pairs.
        hash_by_path: dict[str, str] = {f["path"]: (f["content_hash"] or "") for f in files}
        members_by_component: dict[str, list[tuple[str, str]]] = {}
        for row in store.component_files():
            cid = row["component_id"]
            path = row["path"]
            members_by_component.setdefault(cid, []).append((path, hash_by_path.get(path, "")))

        component: dict[str, str] = {}
        for comp in store.components():
            cid = comp["id"]
            component[cid] = component_digest(members_by_component.get(cid, []))

        # Symbols.
        symbol: dict[str, str] = {}
        for sym in store.symbols():
            symbol[sym["id"]] = symbol_digest(
                hash_by_file_id.get(sym["file_id"], ""), sym["id"]
            )

        # Relationships. An endpoint that is a component uses its component
        # digest; otherwise a stable stand-in.
        def endpoint_digest(node_id: str) -> str:
            d = component.get(node_id)
            return d if d is not None else endpoint_stub_digest(node_id)

        relationship: dict[str, str] = {}
        for edge in store.edges():
            src, tgt, typ = edge["source_id"], edge["target_id"], edge["type"]
            key = relationship_target_id(src, tgt, typ)
            relationship[key] = relationship_digest(
                endpoint_digest(src), endpoint_digest(tgt), typ
            )

        architecture = architecture_digest(component.items())

        return cls(component, symbol, relationship, architecture)

    def for_target(self, target_kind: str, target_id: str) -> str | None:
        """Current digest for an enrichment target, or None if it no longer exists."""
        if target_kind == "component":
            return self.component.get(target_id)
        if target_kind == "symbol":
            return self.symbol.get(target_id)
        if target_kind == "relationship":
            return self.relationship.get(target_id)
        if target_kind == "architecture":
            return self.architecture
        return None
