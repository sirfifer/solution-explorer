"""Compose a solution: run the v2 engine per member, emit a solution layer.

This is the heart of M1. For each RESOLVED member (one with a local path) it runs
the EXISTING single-repo v2 pipeline (extract -> derive -> project_split) exactly
as a standalone scan would, writing that member's unchanged split projection under
``members/<slug>/``. Byte-for-byte parity with a standalone scan is a tested
guarantee (tests/test_solution.py): the solution layer never touches member bytes.

On top of the member projections it writes a thin solution layer:

  - ``manifest.json``: kind ``solution-explorer-solution``, the solution name, the
    ordered member index (per-member slug, label, path/url, resolved flag,
    stats, and a per-member coverage summary), and a solution ``summary`` that
    sums files transparently and lists which members have gaps. NO blended
    coverage denominator, ever (MULTI-REPO-DESIGN.md decision 5).
  - ``ai.json`` / ``llms.txt``: a solution front door that teaches an agent to
    descend into ``members/<slug>/`` and read each member's own front door.

Determinism (invariant I4): one ``generated_at`` is minted once and injected into
every member projection and the solution layer, and members are emitted in
manifest order, so the composed output is byte-stable.

Per-member store: each member keeps its OWN persistent store under
``<member>/.solution-explorer/index.db`` (decision 1), so a solution rebuild
reuses warm member stores untouched (invariant I6), exactly like a standalone
incremental scan.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .. import __version__
from ..derive import derive_all
from ..extract import extract_activity, extract_repo
from ..project.coverage import coverage_families, format_source_percent
from ..project.pipeline import project_split
from ..project.run import default_store_path
from ..store import FactStore
from .frontdoor import write_solution_front_door
from .manifest import Solution, SolutionMember

__all__ = [
    "SOLUTION_KIND",
    "SolutionProjectionResult",
    "compose_solution",
]

# The manifest ``kind`` discriminator the viewer keys on to render the member
# index instead of the normal component view.
SOLUTION_KIND = "solution-explorer-solution"


@dataclass
class MemberProjection:
    """Per-member outcome of composition, for the manifest and CLI reporting."""

    member: SolutionMember
    projection_dir: Optional[Path] = None
    stats: dict = field(default_factory=dict)
    coverage_summary: Optional[dict] = None
    families: Optional[dict] = None
    source_percent: Optional[str] = None
    error: Optional[str] = None

    @property
    def has_gaps(self) -> bool:
        return bool(self.families and self.families.get("gap", 0) > 0)


@dataclass
class SolutionProjectionResult:
    """Paths and per-member outcomes from a composition run."""

    output_dir: Path
    manifest_path: Path
    ai_json_path: Path
    llms_txt_path: Path
    solution_name: str
    generated_at: str
    members: list[MemberProjection] = field(default_factory=list)

    @property
    def composed_members(self) -> list[MemberProjection]:
        return [m for m in self.members if m.error is None and m.projection_dir]


def _default_warn(message: str) -> None:
    print(f"WARNING: {message}", file=sys.stderr)


def _project_member(
    member: SolutionMember,
    base_dir: Path,
    members_root: Path,
    *,
    generated_at: str,
    analyzer_version: str,
    indent,
    now: Optional[datetime],
    warn: Callable[[str], None],
) -> MemberProjection:
    """Run the standalone v2 engine over one member into ``members/<slug>/``."""
    outcome = MemberProjection(member=member)

    # Member paths are relative to the MANIFEST directory, not the process cwd,
    # so a solution file is portable no matter where it is invoked from.
    member_root = (base_dir / member.path).resolve()
    if not member_root.is_dir():
        outcome.error = f"member path does not exist or is not a directory: {member_root}"
        warn(
            f"solution member '{member.slug}': {outcome.error}; skipping this "
            f"member, the rest of the solution still composes"
        )
        return outcome

    # Each member keeps its own persistent store under its own repo, warm and
    # incremental exactly as a standalone scan (decision 1 / invariant I6). Create
    # the store directory before enumeration so the excluded:skipped_directory
    # ledger row is present on both cold and warm runs (byte parity, P4-6).
    store_path = default_store_path(member_root)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store = FactStore(str(store_path))
    try:
        extract_repo(member_root, store)
        extract_activity(member_root, store)
        _, arch = derive_all(store, member_root.name, root_path=str(member_root))

        projection_dir = members_root / member.slug
        result = project_split(
            arch,
            projection_dir,
            store=store,
            root=member_root,
            generated_at=generated_at,
            analyzer_version=analyzer_version,
            now=now,
            indent=indent,
        )
    finally:
        store.close()

    outcome.projection_dir = projection_dir
    outcome.stats = arch.get("stats", {})
    if result.coverage is not None:
        summary = result.coverage["summary"]
        fam = coverage_families(summary)
        outcome.coverage_summary = summary
        outcome.families = fam
        outcome.source_percent = format_source_percent(fam)
    return outcome


def _member_index_entry(outcome: MemberProjection) -> dict:
    """The manifest member-index record for one member (JSON-shaped, sorted-safe)."""
    member = outcome.member
    entry: dict = {
        "slug": member.slug,
        "label": member.label,
        "resolved": member.resolved and outcome.error is None,
    }
    if member.path is not None:
        entry["path"] = member.path
    if member.url is not None:
        entry["url"] = member.url
    if member.ref is not None:
        entry["ref"] = member.ref

    if outcome.error is not None:
        entry["error"] = outcome.error
        return entry
    if not member.resolved:
        entry["unresolved_reason"] = member.unresolved_reason
        return entry

    # A resolved, successfully composed member: link + stats + coverage summary.
    entry["projection"] = f"members/{member.slug}/"
    entry["stats"] = {
        "total_components": outcome.stats.get("total_components", 0),
        "total_files": outcome.stats.get("total_files", 0),
        "total_lines": outcome.stats.get("total_lines", 0),
        "total_symbols": outcome.stats.get("total_symbols", 0),
        "total_relationships": outcome.stats.get("total_relationships", 0),
    }
    if outcome.families is not None:
        entry["coverage"] = {
            "summary": outcome.coverage_summary,
            "families": outcome.families,
            "source_percent": outcome.source_percent,
            "has_gaps": outcome.has_gaps,
        }
    return entry


def _solution_summary(outcomes: list[MemberProjection]) -> dict:
    """Transparent per-member roll-up. No blended denominator (decision 5).

    Files are SUMMED across composed members for a headline count, but coverage
    stays per member: a member with gaps is named, never diluted by a healthy one.
    """
    composed = [o for o in outcomes if o.error is None and o.member.resolved]
    total_source = sum((o.families or {}).get("source_total", 0) for o in composed)
    total_analyzed = sum((o.families or {}).get("analyzed", 0) for o in composed)
    total_nonsource = sum((o.families or {}).get("nonsource", 0) for o in composed)
    total_files = sum(o.stats.get("total_files", 0) for o in composed)
    total_lines = sum(o.stats.get("total_lines", 0) for o in composed)
    members_with_gaps = sorted(o.member.slug for o in composed if o.has_gaps)
    return {
        "member_count": len(outcomes),
        "composed_count": len(composed),
        "unresolved_count": sum(1 for o in outcomes if not o.member.resolved),
        "error_count": sum(1 for o in outcomes if o.error is not None),
        # Summed transparently for a headline; per-member coverage is the source
        # of truth in each member entry. There is deliberately no solution-wide
        # percent here (a blended denominator is forbidden by decision 5).
        "total_source_files": total_source,
        "total_source_analyzed": total_analyzed,
        "total_nonsource_files": total_nonsource,
        "total_files": total_files,
        "total_lines": total_lines,
        "members_with_gaps": members_with_gaps,
    }


def compose_solution(
    solution: Solution,
    output_dir,
    *,
    generated_at: Optional[str] = None,
    analyzer_version: str = __version__,
    now: Optional[datetime] = None,
    indent=2,
    warn: Callable[[str], None] = _default_warn,
) -> SolutionProjectionResult:
    """Compose ``solution`` into a composed projection at ``output_dir``.

    Runs the standalone engine per resolved member (manifest order), writes each
    member's unchanged split projection under ``members/<slug>/``, then the
    solution layer (manifest.json + ai.json + llms.txt). ``generated_at`` is
    minted once and shared by every member and the solution layer for
    byte-stable, deterministic output.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    members_root = output_dir / "members"
    members_root.mkdir(parents=True, exist_ok=True)

    if generated_at is None:
        from datetime import timezone

        generated_at = datetime.now(timezone.utc).isoformat()

    base_dir = (
        solution.manifest_path.parent if solution.manifest_path is not None else Path.cwd()
    )

    outcomes: list[MemberProjection] = []
    for member in solution.members:
        if not member.resolved:
            warn(
                f"solution member '{member.slug}' is a git URL member; parsed and "
                f"recorded in the member index but NOT analyzed in M1 (remote clone "
                f"out of scope)."
            )
            outcomes.append(MemberProjection(member=member))
            continue
        outcomes.append(
            _project_member(
                member,
                base_dir,
                members_root,
                generated_at=generated_at,
                analyzer_version=analyzer_version,
                indent=indent,
                now=now,
                warn=warn,
            )
        )

    member_index = [_member_index_entry(o) for o in outcomes]
    summary = _solution_summary(outcomes)

    manifest = {
        "schema": "solution-explorer.solution/v1",
        "kind": SOLUTION_KIND,
        "name": solution.name,
        "generated_at": generated_at,
        "analyzer_version": analyzer_version,
        "members": member_index,
        "summary": summary,
    }

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=indent, default=str)

    ai_json_path, llms_txt_path = write_solution_front_door(
        manifest, output_dir, indent=indent
    )

    return SolutionProjectionResult(
        output_dir=output_dir,
        manifest_path=manifest_path,
        ai_json_path=ai_json_path,
        llms_txt_path=llms_txt_path,
        solution_name=solution.name,
        generated_at=generated_at,
        members=outcomes,
    )
