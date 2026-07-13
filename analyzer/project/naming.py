"""Filename-safe component id escaping for projection shards.

This is the fourth peer of the ``safe_component_id`` / ``safeComponentId``
triple-implementation (F-CRIT-5). It MUST stay in sync with:

  - analyzer/cli.py ``safe_component_id`` (the old-engine split writer)
  - viewer/src/utils/componentId.ts ``safeComponentId`` (the viewer loader)
  - infrastructure/cloudflare/worker/src/componentId.ts (the ingest cleanup)

The projection tier defines its own copy rather than importing analyzer.cli so
the Tier 4 code stays independent of the old engine (scanner.py), which is
deleted at the P4-7 cutover. tests/test_project.py cross-checks this against
analyzer.cli.safe_component_id and the P0-3 fixture ids so drift fails CI.

Escaping table (identical to the three peers):
  ``/`` -> ``--``   (path separators, unsafe in artifact filenames)
  ``:`` -> ``__``   (multi-repo ids like ``repo:unamentis``; ``:`` is NTFS-illegal)
"""

from __future__ import annotations

__all__ = ["safe_component_id"]


def safe_component_id(comp_id: str) -> str:
    """Make a component id safe for use as a shard filename.

    GitHub's actions/upload-artifact rejects filenames containing any of
    ``" : < > | * ? \\r \\n`` (NTFS-incompatible). Component ids like
    ``repo:unamentis`` (multi-repo mode) or ``viewer/src`` (nested modules)
    hit this. The viewer's ``loadComponentDetail`` applies the same escape.
    """
    return comp_id.replace("/", "--").replace(":", "__")
