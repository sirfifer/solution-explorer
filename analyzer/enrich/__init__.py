"""Enrichment provenance and staleness (TARGET-ARCHITECTURE.md section 6, invariant I5).

This package is the structural end of the F-CRIT-6 story. AI enrichment is an
overlay on the deterministic skeleton (I1); every enrichment record carries the
content digest and commit it was derived from, and staleness is *computed at
read time*, never stored. Stale enrichment is served with a marker, never
silently dropped (I5). Provenance makes the interim drift-tolerant merge script
(scripts/merge-ai-enhancements.py, shipped as P3-3) unnecessary, because
identity plus digest travel with the enrichment; that path retires from CI only
after a parallel-run validation period (P7-1 does not remove it).

The package depends only on the store (analyzer.store) and the standard library.
It must not import from scanner.py or incremental.py.

======================================================================
FROZEN DIGEST DEFINITION (P7-1, the deferred decision of
TARGET-ARCHITECTURE.md section 12; frozen once merged)
======================================================================

``derived_from_hash`` is a content digest computed store-only, so it is stable
across runs and across PYTHONHASHSEED (blake2b is keyless and unsalted, unlike
Python's ``hash``). Every digest is a blake2b-256 hex string. The digest of a
target depends only on facts already in the store's own tables, so it can be
recomputed at any later read without re-reading source.

1. COMPONENT digest. An ordered blake2b over the component's member files'
   ``(path, content_hash)`` pairs, sorted by path. For each member file, in
   ascending path order, the running hash absorbs::

       path.encode() + b"\\x00" + content_hash.encode() + b"\\n"

   The member set and each file's ``content_hash`` come from the store's
   ``component_files`` join and ``files`` table (``content_hash`` is the
   sha256 of the file bytes the extraction tier recorded). A component with no
   member files hashes the empty input to a fixed, stable digest. Because the
   pairs are path-sorted and content-addressed, the digest changes exactly when
   a member file's content changes, a file joins, or a file leaves, and never
   because of extraction order or file-id reassignment (I4).

2. SYMBOL digest. blake2b over the symbol's file ``content_hash`` plus the
   symbol's span-normalized identity::

       file_content_hash.encode() + b"\\x00" + symbol_id.encode()

   The symbol id (analyzer.store.ids grammar) is span-normalized by
   construction: it carries no line number, so the digest is stable when
   unrelated code shifts the symbol's lines and changes only when the symbol's
   defining file content or the symbol's identity changes.

3. RELATIONSHIP digest. blake2b over the pair of endpoint COMPONENT digests
   plus the edge type::

       source_digest.encode() + b"\\x00" + target_digest.encode()
       + b"\\x00" + type.encode()

   An endpoint that is a known component contributes its component digest
   (definition 1); an endpoint that is not a component (an external service or
   infrastructure id with no member files) contributes a stable stand-in,
   ``blake2b("id:" + endpoint_id)``, so the relationship digest is always
   computable store-only. The relationship digest therefore goes stale when
   either endpoint's code changes or the edge is retyped.

4. ARCHITECTURE digest. blake2b over the ordered list of every component
   digest, in ascending component-id order::

       component_id.encode() + b"\\x00" + component_digest.encode() + b"\\n"

   The architecture-level enrichment (the top-level ``ai_enhance`` summary) goes
   stale when any component's digest changes, i.e. whenever the codebase's
   structure or content shifts.

Target-id conventions (the string stored in ``enrichment.target_id``):

    component     -> the component id verbatim
    symbol        -> the symbol id verbatim
    relationship  -> "<source>|<target>|<type>" (see ``relationship_target_id``)
    architecture  -> the fixed sentinel ``@architecture``

These definitions are FROZEN. Changing any of them requires a recorded decision
and a re-stamp of existing enrichment (the digest is provenance, so a redefined
digest invalidates every stored ``derived_from_hash``).
"""

from __future__ import annotations

from .digest import (
    ARCH_TARGET_ID,
    DigestIndex,
    architecture_digest,
    component_digest,
    endpoint_stub_digest,
    relationship_digest,
    relationship_target_id,
    symbol_digest,
)
from .importer import ImportResult, import_ai_baseline
from .overlay import apply_enrichment_overlay
from .provenance import current_commit_sha, iso_now, stamp_enrichment
from .staleness import enrichment_staleness

__all__ = [
    "ARCH_TARGET_ID",
    "DigestIndex",
    "architecture_digest",
    "component_digest",
    "endpoint_stub_digest",
    "relationship_digest",
    "relationship_target_id",
    "symbol_digest",
    "ImportResult",
    "import_ai_baseline",
    "apply_enrichment_overlay",
    "current_commit_sha",
    "iso_now",
    "stamp_enrichment",
    "enrichment_staleness",
]
