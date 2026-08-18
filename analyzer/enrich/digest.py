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
    "membership_digest",
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


def membership_digest(kind: str, member_component_digests: Iterable[str]) -> str:
    """Digest for a concern or finding, over its member components' digests.

    A concern and a finding are both membership sets over components; their
    enrichment (a domain name for a concern, an adversarial verdict for a
    finding) is *about* the code those members contain, so the digest absorbs the
    kind plus each member component's own digest, sorted for order-independence.
    A membership set whose member components' code is unchanged keeps its digest;
    when any member's code changes (its component digest moves) the enrichment
    goes stale (I5). Members with no resolvable component digest (a component that
    left the store) contribute a stable stand-in so the digest stays computable.
    """
    h = _h()
    h.update(kind.encode("utf-8"))
    h.update(b"\x00")
    for d in sorted(member_component_digests):
        h.update(d.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


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
        concern: dict[str, str] | None = None,
        finding: dict[str, str] | None = None,
    ):
        self.component = component
        self.symbol = symbol
        self.relationship = relationship  # keyed by relationship_target_id string
        self.architecture = architecture
        self.concern = concern or {}      # keyed by concern id (P7-4)
        self.finding = finding or {}      # keyed by finding id (P7-4)

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

        # Concern and finding digests (P7-4): each membership set absorbs its
        # member components' digests, so an AI name/verdict goes stale when a
        # member's code changes. A missing member component falls back to a
        # stable stand-in so the digest stays computable store-only.
        def member_component_digests(members: object) -> list[str]:
            out: list[str] = []
            for m in members or []:
                if not isinstance(m, dict):
                    continue
                cid = m.get("component_id")
                if not cid:
                    continue
                out.append(component.get(cid) or endpoint_stub_digest(cid))
            return out

        concern: dict[str, str] = {}
        for c in store.concerns():
            concern[c["id"]] = membership_digest(
                c.get("kind", ""), member_component_digests(c.get("members"))
            )

        finding: dict[str, str] = {}
        for f in store.findings():
            finding[f["id"]] = membership_digest(
                f.get("kind", ""), member_component_digests(f.get("members"))
            )

        return cls(component, symbol, relationship, architecture, concern, finding)

    def membership_digest_for(self, kind: str, members: object) -> str:
        """Compute a membership digest for a (kind, members) set, resolving each
        member's component_id to its current component digest.

        Used for AI-generated findings (intent-violations, P7-4) that are not in
        the deterministic findings table but still need a content digest for
        provenance and staleness.
        """
        digs: list[str] = []
        for m in members or []:
            if not isinstance(m, dict):
                continue
            cid = m.get("component_id")
            if not cid:
                continue
            digs.append(self.component.get(cid) or endpoint_stub_digest(cid))
        return membership_digest(kind, digs)

    def register_finding(self, finding_id: str, kind: str, members: object) -> str:
        """Register (and return) the digest of an AI-generated finding so
        ``for_target('finding'|'finding-verdict', finding_id)`` resolves it."""
        d = self.membership_digest_for(kind, members)
        self.finding[finding_id] = d
        return d

    def for_target(self, target_kind: str, target_id: str) -> str | None:
        """Current digest for an enrichment target, or None if it no longer exists.

        The four frozen kinds (component, symbol, relationship, architecture) are
        defined in the package docstring. Three additive verdict/name kinds reuse
        those digests so their provenance and staleness follow the same content
        (they do not redefine any frozen digest, invariant I5):

            edge-verdict  -> the relationship digest of the same edge (P7-3): a
                             verdict goes stale when either endpoint's code
                             changes or the edge is retyped.
            concern       -> the concern digest (P7-4): a name goes stale when
                             the concern's member components' code changes.
            finding       -> the finding digest (P7-4), also used by
            finding-verdict  the finding-verdict kind: a finding and its
                             adversarial verdict go stale when a member
                             component's code changes.
        """
        if target_kind == "component":
            return self.component.get(target_id)
        if target_kind == "symbol":
            return self.symbol.get(target_id)
        if target_kind == "relationship":
            return self.relationship.get(target_id)
        if target_kind == "edge-verdict":
            return self.relationship.get(target_id)
        if target_kind == "architecture":
            return self.architecture
        if target_kind == "concern":
            return self.concern.get(target_id)
        if target_kind in ("finding", "finding-verdict"):
            return self.finding.get(target_id)
        if target_kind == "identity-verdict":
            # Reuses the component digest (invariant I5): an identity verdict
            # goes stale when the component's own content changes.
            return self.component.get(target_id)
        return None
