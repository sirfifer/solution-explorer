"""Declared architectural intents: the human-authored input to conformance (P7-4).

An intent is a single declarative statement about the intended architecture (the
"intended" side of the software reflexion model), for example "a single audio
pipeline" or "all persistence goes through the repository layer". Intents are
authored by a human and checked continuously against the as-built model; the
enrichment pipeline may PROPOSE candidates from docs and observed architecture,
but proposals are advisory and adoption is a human editing this file (never
auto-adopted, LENS-DESIGN.md section 9).

FILE FORMAT (``solution-explorer-intents.json`` at the repo root, or ``--intents
<path>``). A JSON array of objects, each:

    {
      "id":        "single-audio-pipeline",   (required, unique, kebab-case)
      "statement": "The system has exactly one audio pipeline implementation.",
                                               (required, non-empty)
      "scope":     ["audio", "pipeline"]       (optional hints: component-id
                                               substrings, concern kinds, or free
                                               keywords used to select the store
                                               facts sent to the model)
    }

A top-level object with an ``intents`` array is also accepted. Unknown keys are
ignored (forward-compatible). A malformed file raises ``IntentFileError`` with a
readable message rather than silently yielding zero intents (no silent anything).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

__all__ = [
    "DEFAULT_INTENTS_FILENAME",
    "IntentFileError",
    "Intent",
    "load_intents",
    "find_intents_file",
]

DEFAULT_INTENTS_FILENAME = "solution-explorer-intents.json"


class IntentFileError(ValueError):
    """A declared-intents file exists but is malformed."""


class Intent(dict):
    """A declared intent (a plain dict with id, statement, and optional scope)."""

    @property
    def id(self) -> str:
        return self.get("id", "")

    @property
    def statement(self) -> str:
        return self.get("statement", "")

    @property
    def scope(self) -> list:
        return self.get("scope", []) or []


def find_intents_file(root: Path, explicit: Optional[Path] = None) -> Optional[Path]:
    """Return the intents file path to use, or None when none is declared.

    An explicit ``--intents`` path is honored (and must exist, else the caller
    reports it). Otherwise the default filename at the repo root is used when
    present.
    """
    if explicit is not None:
        return explicit
    candidate = root / DEFAULT_INTENTS_FILENAME
    return candidate if candidate.is_file() else None


def load_intents(path: Path) -> list[Intent]:
    """Load and validate declared intents from ``path``.

    Raises :class:`IntentFileError` on malformed content (bad JSON, wrong shape,
    missing id/statement, or duplicate ids) so a broken file fails loudly.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntentFileError(f"cannot read intents file {path}: {exc}") from exc

    if isinstance(raw, dict):
        raw = raw.get("intents", [])
    if not isinstance(raw, list):
        raise IntentFileError(
            f"intents file {path} must be a JSON array (or an object with an "
            f"'intents' array), got {type(raw).__name__}"
        )

    intents: list[Intent] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise IntentFileError(f"intents[{i}] must be an object, got {type(entry).__name__}")
        iid = entry.get("id")
        statement = entry.get("statement")
        if not iid or not isinstance(iid, str):
            raise IntentFileError(f"intents[{i}] is missing a non-empty string 'id'")
        if not statement or not isinstance(statement, str):
            raise IntentFileError(f"intent '{iid}' is missing a non-empty string 'statement'")
        if iid in seen:
            raise IntentFileError(f"duplicate intent id '{iid}'")
        seen.add(iid)
        scope = entry.get("scope") or []
        if scope and not isinstance(scope, list):
            raise IntentFileError(f"intent '{iid}' scope must be a list of hints")
        intents.append(Intent(id=iid, statement=statement, scope=list(scope)))
    # Deterministic order (I4): by id.
    intents.sort(key=lambda x: x.id)
    return intents
