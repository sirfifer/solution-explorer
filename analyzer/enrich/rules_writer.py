"""Write learned inventory rules to the project knowledge layer (P6-12).

When the enrichment pass identifies an unknown non-source artifact, this module
appends a validated rule to ``<root>/.solution-explorer/rules/inventory.yml`` with
source ``ai-enrichment``, the evidence paths that motivated it, and the current
date. The write is deterministic and idempotent:

  - dedupe on ``(pattern, category)``: a rule already present is not re-added;
  - NEVER overwrite or edit a rule with source ``human``: existing entries are
    kept verbatim (loaded raw, not re-derived), and a proposed rule that would
    contradict a human rule's pattern is skipped and reported;
  - every proposed rule is validated (known category, compilable glob, required
    fields) before it is written, so the writer only ever produces a file the
    loader accepts (round-trip guaranteed).

This is a PURE function over real files: it takes proposed rule dicts and a repo
root, and it is unit-tested directly on disk (no model, no mocks). The AI part
(turning unknown paths into proposals) lives in ``identify.py`` behind the
injectable invoker seam; this module never calls a model.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..project.inventory import CATEGORY_META
from ..project.rules import (
    PROJECT_RULES_RELPATH,
    compile_glob,
    load_repo_rules_raw,
)

try:  # PyYAML is optional for the read/parse path but REQUIRED to write.
    import yaml as _yaml
except ImportError:  # pragma: no cover - covered via monkeypatch in tests
    _yaml = None

__all__ = ["WriteResult", "write_inventory_rules"]

# The field order every written rule uses, so the file is stable and diff-friendly.
_RULE_KEY_ORDER = [
    "id",
    "pattern",
    "category",
    "label",
    "explanation",
    "recommendation",
    "flags",
    "source",
    "added",
    "evidence",
    "contribute",
]


@dataclass
class WriteResult:
    """Outcome of one write. Lists carry ids/patterns for a readable report."""

    path: Path
    written: list[str] = field(default_factory=list)  # new rule ids
    skipped_duplicate: list[str] = field(default_factory=list)  # "(pattern, category)"
    skipped_human: list[str] = field(default_factory=list)  # pattern protected by a human rule
    rejected: list[str] = field(default_factory=list)  # "pattern: reason"
    changed: bool = False


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "rule"


def _unique_id(base: str, taken: set) -> str:
    """A stable, collision-free rule id derived from the base slug."""
    candidate = base
    n = 2
    while candidate in taken:
        candidate = f"{base}-{n}"
        n += 1
    taken.add(candidate)
    return candidate


def _raw_entries(path: Path) -> list[dict]:
    """The existing rule entries loaded RAW (verbatim), for exact preservation.

    Human rules keep every field exactly as written; we never re-derive them from
    the validated model. Returns [] when the file is absent or empty.
    """
    if not path.is_file() or _yaml is None:
        return []
    raw = _yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    if isinstance(raw, dict):
        entries = raw.get("rules", [])
    elif isinstance(raw, list):
        entries = raw
    else:
        entries = []
    return [e for e in entries if isinstance(e, dict)]


def _validate_proposed(entry: dict) -> Optional[str]:
    """Return an error string if the proposed rule is invalid, else None."""
    pattern = entry.get("pattern")
    if not pattern or not isinstance(pattern, str):
        return "missing a non-empty string 'pattern'"
    category = entry.get("category")
    if category not in CATEGORY_META:
        return f"unknown category '{category}'"
    try:
        compile_glob(pattern)
    except ValueError as exc:
        return f"invalid glob: {exc}"
    return None


def write_inventory_rules(
    root: Path,
    proposed: list[dict],
    *,
    added: Optional[str] = None,
    source: str = "ai-enrichment",
    warn: Callable[[str], None] = lambda m: print(f"WARNING: {m}", file=sys.stderr),
) -> WriteResult:
    """Append validated ``proposed`` rules to the repo rule file. Pure over disk.

    ``proposed`` items are dicts with at least ``pattern`` and ``category`` and
    optionally ``label``, ``explanation``, ``recommendation``, ``flags``,
    ``evidence``, ``contribute``, ``id``. Returns a WriteResult; the file is only
    rewritten when at least one rule is actually added (``changed``).
    """
    path = Path(root) / PROJECT_RULES_RELPATH
    result = WriteResult(path=path)

    if _yaml is None:
        warn(
            "cannot write project rules: PyYAML is not installed. Install the "
            "package with its dependencies to let enrichment teach the project."
        )
        return result

    existing_raw = _raw_entries(path)
    existing_rules = load_repo_rules_raw(root, warn=warn)
    dedupe_keys = {(r.pattern, r.category) for r in existing_rules}
    human_patterns = {r.pattern for r in existing_rules if r.source == "human"}
    taken_ids = {r.id for r in existing_rules}

    new_entries: list[dict] = []
    for entry in proposed:
        error = _validate_proposed(entry)
        if error is not None:
            result.rejected.append(f"{entry.get('pattern')!r}: {error}")
            continue
        pattern = entry["pattern"]
        category = entry["category"]
        if (pattern, category) in dedupe_keys:
            result.skipped_duplicate.append(f"({pattern}, {category})")
            continue
        if pattern in human_patterns:
            # A human already ruled on this pattern; never contradict them.
            result.skipped_human.append(pattern)
            continue
        rid = entry.get("id") or _unique_id(_slugify(f"ai-{category}-{pattern}"), taken_ids)
        if entry.get("id"):
            taken_ids.add(rid)
        rule_entry = {
            "id": rid,
            "pattern": pattern,
            "category": category,
            "source": source,
        }
        for opt in ("label", "explanation", "recommendation"):
            if entry.get(opt):
                rule_entry[opt] = str(entry[opt])
        if isinstance(entry.get("flags"), dict) and entry["flags"]:
            rule_entry["flags"] = entry["flags"]
        if added:
            rule_entry["added"] = added
        evidence = entry.get("evidence") or []
        if isinstance(evidence, list) and evidence:
            rule_entry["evidence"] = [str(p) for p in evidence]
        if entry.get("contribute"):
            rule_entry["contribute"] = True
        new_entries.append(_ordered(rule_entry))
        dedupe_keys.add((pattern, category))
        result.written.append(rid)

    if not new_entries:
        return result

    all_entries = list(existing_raw) + new_entries
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Project knowledge layer (P6-12): learned non-source inventory rules.\n"
        "# Rules are data; no AI runs at parse or query time. Rules with\n"
        "# source: human are authored by people and never edited by enrichment.\n"
    )
    body = _yaml.safe_dump(
        {"rules": all_entries}, sort_keys=False, default_flow_style=False, allow_unicode=True
    )
    path.write_text(header + body, encoding="utf-8")
    result.changed = True
    return result


def _ordered(entry: dict) -> dict:
    """Reorder a rule mapping to the canonical key order for a stable file."""
    ordered = {k: entry[k] for k in _RULE_KEY_ORDER if k in entry}
    # Preserve any unexpected keys at the end rather than dropping them.
    for k, v in entry.items():
        if k not in ordered:
            ordered[k] = v
    return ordered
