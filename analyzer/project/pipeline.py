"""Tier 4 orchestrator: assemble the delivery artifacts from the store (4.4).

The projection tier reads the store-derived architecture (the dict
``derive.pipeline.derive_all`` returns, which is itself a pure store read) plus
the store's coverage ledger and enrichment overlay, fills the environment fields
that are not code facts (git remote, default branch, Info.plist app names,
generated_at, analyzer_version), diffs against the previous projection for the
changelog, and writes:

  - split mode: ``manifest.json`` + ``data/detail-*.json`` + ``coverage.json``
    + ``search/`` shards (the windowed-loading format the viewer already loads);
  - monolith mode: a single ``architecture.json`` for small repos and backward
    compatibility.

Determinism (invariant I4): given the same store and the same injected
``generated_at`` / ``now`` / ``commit_sha``, the byte output is identical across
runs and across PYTHONHASHSEED. The only non-store inputs are those injected
clock/version values.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..enrich import apply_enrichment_overlay, apply_verdict_overlay
from .activity import build_activity
from .changelog import apply_changelog
from .coverage import build_coverage
from .gitinfo import apply_info_plist_names, read_git_info
from .manifest import write_manifest_and_details
from .monolith import write_monolith
from .search_shards import DEFAULT_SHARD_SIZE, write_search_shards

__all__ = ["ProjectionResult", "prepare_arch", "project_split", "project_monolith", "project_all"]


@dataclass
class ProjectionResult:
    """Paths and counts from a projection run, for tests and CLI reporting."""

    mode: str = "split"
    output_dir: Optional[Path] = None
    manifest_path: Optional[Path] = None
    monolith_path: Optional[Path] = None
    coverage_path: Optional[Path] = None
    activity_path: Optional[Path] = None
    search_manifest_path: Optional[Path] = None
    detail_count: int = 0
    search_total: int = 0
    changelog_serial: int = 0
    coverage: Optional[dict] = field(default=None)
    activity: Optional[dict] = field(default=None)


def prepare_arch(
    arch: dict,
    *,
    root=None,
    generated_at: Optional[str] = None,
    analyzer_version: Optional[str] = None,
) -> dict:
    """Return a copy of ``arch`` with environment fields filled in.

    Fills ``generated_at``, ``analyzer_version``, ``root_path``, and (when
    ``root`` points at a git working tree) the credential-stripped repository
    URL and default branch. Info.plist app names are resolved from disk. The
    input dict is not mutated.
    """
    prepared = copy.deepcopy(arch)
    if generated_at is not None:
        prepared["generated_at"] = generated_at
    if analyzer_version is not None:
        prepared["analyzer_version"] = analyzer_version
    if root is not None:
        prepared["root_path"] = str(root)
        repository, default_branch = read_git_info(root)
        if repository is not None:
            prepared["repository"] = repository
        prepared["default_branch"] = default_branch
        apply_info_plist_names(prepared.get("components", []), root)
    return prepared


def _load_previous(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def _finish_changelog(
    prepared: dict,
    previous: Optional[dict],
    previous_path: Path,
    *,
    commit_sha: str,
    now: Optional[datetime],
) -> int:
    if previous is None:
        previous = _load_previous(previous_path)
    apply_changelog(prepared, previous, commit_sha=commit_sha, now=now)
    return prepared.get("changelog_serial", 0)


def project_split(
    arch: dict,
    output_dir,
    *,
    store=None,
    root=None,
    generated_at: Optional[str] = None,
    analyzer_version: Optional[str] = None,
    previous: Optional[dict] = None,
    commit_sha: str = "",
    now: Optional[datetime] = None,
    shard_size: int = DEFAULT_SHARD_SIZE,
    indent=2,
) -> ProjectionResult:
    """Write the split projection (manifest + details + coverage + search)."""
    output_dir = Path(output_dir)
    prepared = prepare_arch(
        arch, root=root, generated_at=generated_at, analyzer_version=analyzer_version
    )
    # Store enrichment is canonical: overlay it (with staleness markers) before
    # the changelog, manifest, and search shards read the arch (I5). No-op when
    # the store carries no enrichment, so non-enriched projections are unchanged.
    apply_enrichment_overlay(prepared, store)
    # Phase 7 verdicts and names (P7-3/P7-4): edge verdicts, concern names, and
    # finding verification statuses, plus AI intent-violation findings. No-op when
    # the store carries none of these enrichment kinds (parity-safe).
    apply_verdict_overlay(prepared, store)
    coverage = build_coverage(store)
    activity = build_activity(store)
    serial = _finish_changelog(
        prepared, previous, output_dir / "manifest.json",
        commit_sha=commit_sha, now=now,
    )

    manifest_path = write_manifest_and_details(
        prepared, output_dir, coverage=coverage, activity=activity, indent=indent
    )
    search_manifest = write_search_shards(
        prepared, output_dir, store=store, shard_size=shard_size, indent=indent
    )

    coverage_path = None
    if coverage is not None:
        coverage_path = output_dir / "coverage.json"
        with open(coverage_path, "w", encoding="utf-8") as fh:
            json.dump(coverage, fh, indent=indent, default=str, sort_keys=True)

    activity_path = None
    if activity is not None:
        activity_path = output_dir / "activity.json"
        with open(activity_path, "w", encoding="utf-8") as fh:
            json.dump(activity, fh, indent=indent, default=str, sort_keys=True)

    return ProjectionResult(
        mode="split",
        output_dir=output_dir,
        manifest_path=manifest_path,
        coverage_path=coverage_path,
        activity_path=activity_path,
        search_manifest_path=output_dir / "search" / "manifest.json",
        detail_count=len(prepared.get("component_detail_index", {}))
        or _count_components(prepared.get("components", [])),
        search_total=search_manifest["total"],
        changelog_serial=serial,
        coverage=coverage,
        activity=activity,
    )


def project_monolith(
    arch: dict,
    output_path,
    *,
    store=None,
    root=None,
    generated_at: Optional[str] = None,
    analyzer_version: Optional[str] = None,
    previous: Optional[dict] = None,
    commit_sha: str = "",
    now: Optional[datetime] = None,
    indent=2,
) -> ProjectionResult:
    """Write the monolithic ``architecture.json`` projection."""
    output_path = Path(output_path)
    prepared = prepare_arch(
        arch, root=root, generated_at=generated_at, analyzer_version=analyzer_version
    )
    # Store enrichment is canonical: overlay it (with staleness markers) before
    # the changelog and monolith read the arch (I5). No-op when the store carries
    # no enrichment, so non-enriched projections are unchanged.
    apply_enrichment_overlay(prepared, store)
    apply_verdict_overlay(prepared, store)
    coverage = build_coverage(store)
    activity = build_activity(store)
    serial = _finish_changelog(
        prepared, previous, output_path, commit_sha=commit_sha, now=now
    )
    write_monolith(prepared, output_path, coverage=coverage, activity=activity, indent=indent)
    return ProjectionResult(
        mode="monolith",
        monolith_path=output_path,
        changelog_serial=serial,
        coverage=coverage,
        activity=activity,
    )


def project_all(
    arch: dict,
    output,
    *,
    split: bool = True,
    **kwargs,
) -> ProjectionResult:
    """Convenience entry: split projection into a dir, or monolith into a file."""
    if split:
        return project_split(arch, output, **kwargs)
    return project_monolith(arch, output, **kwargs)


def _count_components(components: list) -> int:
    n = 0
    for comp in components:
        n += 1 + _count_components(comp.get("children", []))
    return n
