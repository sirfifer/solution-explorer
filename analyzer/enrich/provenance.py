"""Enrichment write path: stamp a payload with digest, commit, and timestamp.

These helpers are the provenance-stamped replacement for the merge script's
inline ai_enhance path. They wrap the store's ``add_enrichment`` upsert, filling
``derived_from_hash`` from the frozen digest definition, ``commit_sha`` from git
when available (nullable), and ``created_at`` from an injectable clock so tests
are deterministic. The store table already fits the model (P4-1); this is an
additive helper layer, no schema change.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Optional

from ..store import FactStore
from .digest import DigestIndex

__all__ = ["iso_now", "current_commit_sha", "stamp_enrichment"]

Clock = Callable[[], str]


def iso_now() -> str:
    """Default clock: the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def current_commit_sha(root: str = ".") -> Optional[str]:
    """Return the current git HEAD sha for ``root``, or None when unavailable.

    Nullable by design (I5 permits a null commit): a run outside a git tree, a
    detached environment, or a missing git binary yields None rather than
    raising, and the enrichment still stamps a digest.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def stamp_enrichment(
    store: FactStore,
    target_kind: str,
    target_id: str,
    payload: Any,
    *,
    digest_index: DigestIndex,
    commit_sha: Optional[str] = None,
    clock: Clock = iso_now,
) -> Optional[str]:
    """Write one enrichment row, stamped with its current digest and provenance.

    ``digest_index`` supplies the current ``derived_from_hash`` for the target
    (per the frozen definition). ``commit_sha`` is recorded verbatim (pass the
    result of :func:`current_commit_sha` or None). ``clock`` is injectable so the
    ``created_at`` timestamp is deterministic in tests. Returns the digest that
    was stamped (None if the target is not in the store, an honest un-digestable
    stamp rather than a silent guess). The payload's ``help_text`` is forwarded
    to the store so the FTS overlay indexes it.
    """
    digest = digest_index.for_target(target_kind, target_id)
    help_text = payload.get("help_text") if isinstance(payload, dict) else None
    store.add_enrichment(
        target_kind,
        target_id,
        payload,
        derived_from_hash=digest,
        commit_sha=commit_sha,
        created_at=clock(),
        help_text=help_text,
    )
    return digest
