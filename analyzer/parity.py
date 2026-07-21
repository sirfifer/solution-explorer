"""Shared projection-parity normalization (card G4).

The full-vs-incremental byte-parity contract (ROBUSTNESS-STRATEGY.md, "The parity
contract") says a warm incremental run must produce the same projection as a cold
full run. The per-commit byte-parity tests prove it on fixtures; G4 proves it on
a frozen real-world corpus at scale.

Two projections of the same tree differ only in a small set of fields that are
NOT code facts: the wall-clock ``generated_at``, the machine ``root_path``, the
``analyzer_version``, and the store-vs-previous ``changelog`` / ``changelog_serial``
(which depends on whatever projection happened to be on disk before). Everything
else is a pure function of the source, so once those volatile fields are stripped
the two projections must be BYTE-identical, which is a stronger check than the G1
semantic diff (it also catches list-order drift, which a semantic diff by id
would miss).

This module is the single source of the volatile-field allowlist. The
engine-parity test (``tests/test_engine_parity.py``) reuses it so the fixture
guard and the golden-corpus parity check agree on exactly what is volatile,
rather than each maintaining its own list.

Note on list order: ``normalize_for_parity`` deliberately does NOT sort list
values. The v2 engine emits every list in a deterministic order (invariant I4),
so a warm and a cold run produce identical order; sorting would MASK a real
ordering regression between them. (The engine-parity fixture guard sorts lists
for a different reason, to compare the OLD v1 engine whose set-iteration order
varies by PYTHONHASHSEED; that is its own concern and stays in that test.)
"""

from __future__ import annotations

import copy
import json

# The fields that legitimately differ between two projections of the SAME source
# tree. Anything not in this list is a code fact and must match byte-for-byte.
VOLATILE_KEYS: tuple[str, ...] = (
    "generated_at",
    "root_path",
    "analyzer_version",
    "changelog",
    "changelog_serial",
)


def strip_volatile(projection: dict) -> dict:
    """Return a deep copy of ``projection`` with the volatile top-level keys removed."""
    stripped = copy.deepcopy(projection)
    for key in VOLATILE_KEYS:
        stripped.pop(key, None)
    return stripped


def canonical(projection: dict) -> str:
    """Deterministically serialize a projection: sorted KEYS, preserved LIST order.

    ``sort_keys=True`` makes dict key order irrelevant; list order is preserved so
    a real ordering drift is not hidden. ``default=str`` mirrors the projection
    writers so any stray non-JSON scalar serializes the same way.
    """
    return json.dumps(projection, sort_keys=True, indent=2, default=str) + "\n"


def normalize_for_parity(projection: dict) -> str:
    """Strip volatile fields and canonically serialize for a byte-parity compare."""
    return canonical(strip_volatile(projection))
