"""Identify unknown non-source files and teach the project (P6-12).

The enrichment pass that closes the loop: it reads the store's coverage ledger,
finds the non-source files the deterministic classifier still calls ``unknown``
(after applying any rules the project already learned), asks the model to name
them as gitignore-style rules, validates the proposals, and writes them to the
repo rule file via the pure ``rules_writer``. A second projection then classifies
those files deterministically with zero AI (invariant I9): the unknown bucket
trends to zero per project without any core-product change.

It reuses the Phase 7 machinery: the injectable ``Invoker`` seam (so tests drive
a canned response with no shell-out), the retry-with-feedback ``_invoke_json``
helper, cost controls (``--max-targets``, ``--dry-run``), and honest exit codes.
Nothing is written unless it validates.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..project.inventory import (
    CATEGORY_META,
    NON_SOURCE_DISPOSITIONS,
    _classify_with_provenance,
)
from ..project.rules import load_rule_set
from ..store import FactStore
from .engine import DEFAULT_MODEL, ClaudeCliInvoker, Invoker
from .passes import _invoke_json
from .prompts import build_identify_unknowns_prompt
from .provenance import iso_now
from .rules_writer import write_inventory_rules

__all__ = [
    "IdentifyConfig",
    "IdentifyReport",
    "collect_unknowns",
    "identify_unknowns",
]


@dataclass
class IdentifyConfig:
    store_path: Path
    root: Path
    max_targets: Optional[int] = None
    model: str = DEFAULT_MODEL
    dry_run: bool = False
    report_path: Optional[Path] = None
    added: Optional[str] = None  # injectable date for deterministic tests


@dataclass
class IdentifyReport:
    mode: str = "identify"
    dry_run: bool = False
    unknown_count: int = 0
    considered: int = 0
    written: list[str] = field(default_factory=list)
    skipped_duplicate: list[str] = field(default_factory=list)
    skipped_human: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        # A run with no proposals to write is a clean success; only invocation or
        # write failures (surfaced as notes with 'error') are not ok.
        return not any(n.startswith("error") for n in self.notes)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "dry_run": self.dry_run,
            "unknown_count": self.unknown_count,
            "considered": self.considered,
            "written": self.written,
            "skipped_duplicate": self.skipped_duplicate,
            "skipped_human": self.skipped_human,
            "rejected": self.rejected,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "notes": self.notes,
        }


def collect_unknowns(store: FactStore, root: Path, ruleset=None) -> list[str]:
    """Deterministic set of paths that still classify to ``unknown``.

    Applies the current project rules and gitattributes first, so a file the
    project already learned about is NOT re-proposed. Returns a sorted, unique
    list (the ledger is already path-sorted; sorting again is cheap and explicit).
    """
    if ruleset is None:
        ruleset = load_rule_set(root)
    unknown: list[str] = []
    for row in store.coverage():
        disposition = row.get("disposition", "")
        if disposition == "parsed" or disposition not in NON_SOURCE_DISPOSITIONS:
            continue
        path = row.get("path", "")
        category, _prov, _rule = _classify_with_provenance(
            path, disposition, row.get("reason"), ruleset
        )
        if category == "unknown":
            unknown.append(path)
    return sorted(set(unknown))


def _category_vocabulary() -> list[dict]:
    """The category ids the model may choose from, each with its explanation.

    ``unknown`` is excluded: the whole point is to move OUT of it.
    """
    return [
        {"id": cid, "means": meta["explanation"]}
        for cid, meta in CATEGORY_META.items()
        if cid != "unknown"
    ]


def _finalize(report: IdentifyReport, config: IdentifyConfig) -> IdentifyReport:
    if config.report_path is not None:
        config.report_path.parent.mkdir(parents=True, exist_ok=True)
        config.report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return report


def identify_unknowns(
    config: IdentifyConfig,
    *,
    invoker: Optional[Invoker] = None,
    clock: Callable[[], str] = iso_now,
) -> IdentifyReport:
    """Identify unknown non-source files and write learned rules (P6-12)."""
    if invoker is None:
        invoker = ClaudeCliInvoker(model=config.model)
    store = FactStore(str(config.store_path))
    try:
        ruleset = load_rule_set(config.root)
        unknowns = collect_unknowns(store, config.root, ruleset)
        report = IdentifyReport(dry_run=config.dry_run, unknown_count=len(unknowns))
        if not unknowns:
            report.notes.append("no unknown non-source files; nothing to identify")
            return _finalize(report, config)

        considered = unknowns
        if config.max_targets is not None:
            considered = considered[: config.max_targets]
        report.considered = len(considered)
        report.notes.append(
            f"{len(unknowns)} unknown path(s); {len(considered)} sent to the model"
        )

        vocabulary = _category_vocabulary()
        prompt = build_identify_unknowns_prompt(considered, vocabulary)

        if config.dry_run:
            report.notes.append(f"dry run: no model invoked; prompt is {len(prompt)} chars")
            return _finalize(report, config)

        def validate(obj: dict) -> list[str]:
            rules = obj.get("rules")
            if not isinstance(rules, list):
                return ["'rules' must be a list of rule objects"]
            return []

        obj, cost, errs = _invoke_json(invoker, prompt, validate)
        report.total_cost_usd += cost
        if obj is None:
            report.notes.append(f"error: model did not return usable rules: {errs}")
            return _finalize(report, config)

        proposals = [r for r in obj["rules"] if isinstance(r, dict)]
        write_result = write_inventory_rules(
            config.root,
            proposals,
            added=config.added or clock()[:10],
            source="ai-enrichment",
        )
        report.written = write_result.written
        report.skipped_duplicate = write_result.skipped_duplicate
        report.skipped_human = write_result.skipped_human
        report.rejected = write_result.rejected
        if write_result.changed:
            report.notes.append(f"wrote {len(write_result.written)} rule(s) to {write_result.path}")
        else:
            report.notes.append("no new rules written (all duplicates, protected, or rejected)")
        store.commit()
        return _finalize(report, config)
    finally:
        store.close()
