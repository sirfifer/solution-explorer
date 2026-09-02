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

Fault isolation (card R1 wave 2). Each emitter runs under a per-unit
:class:`~analyzer.contracts.Isolator`: a sidecar emitter that raises (SBOM, CRA,
coverage, activity, search shards, the AI front door) records a deterministic
honest gap and is simply absent, never fracturing the run. The main projection
writer (the manifest in split mode, ``architecture.json`` in monolith mode) is
written LAST so it carries every project-tier gap on its additive ``gaps`` key,
and it degrades to a minimal but well-formed skeleton on its own failure rather
than crashing. A clean run records no gaps and adds no ``gaps`` key, so its byte
output is identical to the pre-isolation behavior (the golden gate and the
full-vs-incremental byte-parity suites depend on this).
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..contracts import Isolator, finalize_gaps
from ..enrich import apply_enrichment_overlay, apply_verdict_overlay
from ..features import DEFAULT_CHANNEL, gate_provenance
from .activity import activity_manifest_summary, build_activity
from .ai_surface import emit_ai_surface
from .changelog import apply_changelog
from .coverage import build_coverage, coverage_manifest_summary
from .cra_emit import emit_cra_readiness
from .design import emit_design_signals
from .frontdoor import write_front_door
from .gitinfo import apply_info_plist_names, read_git_info
from .human_views import (
    ORIENTATION_FILENAME,
    SECURITY_FILENAME,
    SUPPORT_FILENAME,
    build_orientation,
    build_security_view,
    build_support_view,
    write_human_view,
)
from .manifest import write_manifest_and_details
from .monolith import write_monolith
from .sbom_emit import emit_sbom
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
    sbom_path: Optional[Path] = None
    cra_path: Optional[Path] = None
    search_manifest_path: Optional[Path] = None
    ai_json_path: Optional[Path] = None
    llms_txt_path: Optional[Path] = None
    orientation_path: Optional[Path] = None
    support_path: Optional[Path] = None
    security_path: Optional[Path] = None
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
    channel: str = DEFAULT_CHANNEL,
    isolator: Optional[Isolator] = None,
) -> dict:
    """Return a copy of ``arch`` with environment fields filled in.

    Fills ``generated_at``, ``analyzer_version``, ``root_path``, and (when
    ``root`` points at a git working tree) the credential-stripped repository
    URL and default branch. Info.plist app names are resolved from disk. The
    input dict is not mutated.

    Maturity gating (card R3): when ``channel`` activates one or more non-stable
    gates, a deterministic ``gate_provenance`` stamp is added so the non-default
    output is self-explaining. On the default ``stable`` channel (and any channel
    that activates no non-stable gate) the stamp is ``None`` and NOTHING is added,
    so the output is byte-identical to a run built before the mechanism existed.

    When an ``isolator`` is supplied (the projection drivers pass theirs), the
    two environment reads that touch disk (``read_git_info`` and
    ``apply_info_plist_names``) run under isolation, so a failing read degrades
    to an honest gap and the safe defaults (no repository URL, ``main`` branch)
    instead of crashing the projection. A healthy read is a transparent
    pass-through, so byte parity holds. Direct callers pass no isolator and get
    the original raise-on-failure behavior unchanged.
    """
    prepared = copy.deepcopy(arch)
    if generated_at is not None:
        prepared["generated_at"] = generated_at
    if analyzer_version is not None:
        prepared["analyzer_version"] = analyzer_version
    provenance = gate_provenance(channel)
    if provenance is not None:
        prepared["gate_provenance"] = provenance
    if root is not None:
        prepared["root_path"] = str(root)
        if isolator is None:
            repository, default_branch = read_git_info(root)
            apply_info_plist_names(prepared.get("components", []), root)
        else:
            repository, default_branch = isolator.run(
                "project.gitinfo", read_git_info, root, default=(None, "main")
            )
            isolator.run(
                "project.info-plist-names", apply_info_plist_names,
                prepared.get("components", []), root,
            )
        if repository is not None:
            prepared["repository"] = repository
        prepared["default_branch"] = default_branch
    return prepared


def _merge_cra_findings(prepared: dict, findings: list[dict]) -> None:
    """Merge the CRA gap findings into ``prepared['findings']`` in place (P10-4).

    The absent-item findings join the existing ranked findings surface (no new
    view). The combined list is re-sorted by rank_score desc then id so the
    "already ranked" contract the ai.json front door advertises stays true. A
    no-op when there are no gap findings, so a fully-ready repo's projection is
    byte-identical to one without the CRA pass.
    """
    if not findings:
        return
    merged = list(prepared.get("findings") or []) + findings
    merged.sort(key=lambda f: (-float(f.get("rank_score", 0.0)), f.get("id", "")))
    prepared["findings"] = merged


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


# ---------------------------------------------------------------------------
# honest-gap plumbing for the projection tier (card R1 wave 2)
# ---------------------------------------------------------------------------


def _apply_project_gaps(prepared: dict, derive_gaps: list, project_gaps: list) -> None:
    """Attach the combined honest gaps to ``prepared['gaps']`` in place.

    ``derive_gaps`` are the gaps the derive tier already left on the arch
    (captured before any projection work, dicts); ``project_gaps`` are the
    gaps this projection recorded (ProducerGap objects). Called once, right
    before the main writer serializes ``prepared``, so a successful main write
    carries every gap on its additive ``gaps`` key.

    Byte-safe: when the projection recorded NO gaps this is a no-op, so a clean
    run (and a derive-gaps-only run, where the derive gaps already sit on
    ``prepared['gaps']`` untouched) is byte-identical to the pre-isolation
    output. When the projection did record gaps, the two sources are combined
    and re-finalized (deterministically sorted), never double-counted.
    """
    if not project_gaps:
        return
    prepared["gaps"] = finalize_gaps(list(derive_gaps) + list(project_gaps))


def _json_scalar(value, fallback=""):
    """Coerce an identity field to a JSON-safe scalar for the skeleton.

    A well-formed arch carries plain strings (or None for ``repository``) in
    these fields. If an upstream bug left a non-scalar here, and it is the very
    thing that made the main writer fail, embedding it verbatim would make the
    skeleton fail too. ``json.dump(default=str)`` does not save us against a
    CIRCULAR object (circularity is detected before ``default`` is consulted), so
    stringify eagerly: ``str`` breaks circular references (Python renders them as
    ``{...}``), so the skeleton always serializes and the run always ships an
    artifact that carries the gaps.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - extremely defensive; never let a repr crash the skeleton
        return fallback


def _empty_arch_doc(prepared: dict) -> dict:
    """A minimal, guaranteed-serializable arch skeleton for a main-writer failure.

    Mirrors ``derive.pipeline._skeleton_arch``: the identity fields are carried
    through (coerced to JSON-safe scalars via ``_json_scalar`` so even a
    pathological non-serializable identity field cannot make the skeleton fail),
    every collection is empty, and the stats totals are zero and self-consistent.
    Built from scratch (never the possibly-unserializable real collections that
    made the writer fail), so it always serializes. It is the honest "the
    projection could not assemble the full document" fallback, paired with the
    failing writer's gap.
    """
    return {
        "name": _json_scalar(prepared.get("name", "")),
        "description": _json_scalar(prepared.get("description", "")),
        "repository": _json_scalar(prepared.get("repository"), None),
        "default_branch": _json_scalar(prepared.get("default_branch", "main"), "main"),
        "generated_at": _json_scalar(prepared.get("generated_at", "")),
        "analyzer_version": _json_scalar(prepared.get("analyzer_version", "")),
        "root_path": _json_scalar(prepared.get("root_path", "")),
        "components": [],
        "relationships": [],
        "capabilities": [],
        "data_entities": [],
        "entity_access": [],
        "rules": [],
        "concerns": [],
        "findings": [],
        "repositories": [],
        "stats": {
            "total_files": 0,
            "total_lines": 0,
            "total_size_bytes": 0,
            "languages": {},
            "total_symbols": 0,
            "total_symbols_detected": 0,
            "total_components": 0,
            "total_relationships": 0,
        },
    }


def _write_skeleton_manifest(
    output_dir: Path,
    prepared: dict,
    coverage: Optional[dict],
    activity: Optional[dict],
    derive_gaps: list,
    project_gaps: list,
    indent,
) -> Path:
    """Write a minimal but well-formed ``manifest.json`` after a manifest failure.

    The manifest writer is the split-mode main artifact: the run must always
    ship a viewer-loadable manifest that accounts for what failed. This carries
    the identity fields, empty collections, an empty detail index, the coverage
    and activity summaries (cheap, already built), and every gap including the
    manifest writer's own failure.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = _empty_arch_doc(prepared)
    doc["component_detail_index"] = {}
    doc["gaps"] = finalize_gaps(list(derive_gaps) + list(project_gaps))
    summary = coverage_manifest_summary(coverage)
    if summary is not None:
        doc["coverage"] = summary
    activity_summary = activity_manifest_summary(activity)
    if activity_summary is not None:
        doc["activity"] = activity_summary
    path = output_dir / "manifest.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=indent, default=str, sort_keys=True)
    # The skeleton declares an empty detail index, so any detail shards a partial
    # write_manifest_and_details already wrote are orphans inconsistent with it.
    # Best-effort prune so the shipped tree matches the manifest it advertises.
    data_dir = output_dir / "data"
    if data_dir.is_dir():
        for stale in data_dir.glob("detail-*.json"):
            try:
                stale.unlink()
            except OSError:
                pass
    return path


def _write_skeleton_monolith(
    output_path: Path,
    prepared: dict,
    coverage: Optional[dict],
    activity: Optional[dict],
    derive_gaps: list,
    project_gaps: list,
    indent,
) -> Path:
    """Write a minimal but well-formed ``architecture.json`` after a write failure.

    The monolith is the monolith-mode main artifact; same contract as the
    manifest skeleton. Carries empty ``symbols`` / ``files`` arrays (the
    monolith inlines them), the full coverage and activity when present, and
    every gap including the monolith writer's own failure.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = _empty_arch_doc(prepared)
    doc["symbols"] = []
    doc["files"] = []
    doc["gaps"] = finalize_gaps(list(derive_gaps) + list(project_gaps))
    if coverage is not None:
        doc["coverage"] = coverage
    if activity is not None:
        doc["activity"] = activity
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=indent, default=str, sort_keys=True)
    return output_path


def _dump_json(path: Path, obj, indent) -> Path:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=indent, default=str, sort_keys=True)
    return path


def _empty_search_manifest(shard_size: int) -> dict:
    """A well-formed empty search manifest for the search-shard failure default.

    The front door and the ProjectionResult read ``total`` and ``shards`` off
    this, so the degraded value must be shaped like a real search manifest, just
    empty. The search index is simply absent on disk; its gap is recorded.
    """
    return {
        "version": 1,
        "shard_size": shard_size,
        "total": 0,
        "by_kind": {},
        "fields": ["ref_kind", "ref_id", "name", "path", "component", "text"],
        "shards": [],
    }


def _emit_human_views(
    prepared: dict,
    output_dir: Path,
    coverage: Optional[dict],
    iso: Isolator,
    indent,
    *,
    store=None,
) -> tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """Build and write the three bounded human-entry sidecars.

    Builders and writers are isolated independently: a failed view cannot
    fracture the main projection, and the writer's producer gap is available to
    the manifest/monolith written after these sidecars.  Successful sections
    also ride in the main artifact so monolith and split consumers share one
    schema and an old client can ignore them safely.
    """
    support = iso.run(
        "project.support-view", build_support_view, prepared, default=None
    )
    support_path = None
    if support is not None:
        prepared["support"] = support
        support_path = iso.run(
            "project.support-json",
            write_human_view,
            support,
            output_dir / SUPPORT_FILENAME,
            indent=indent,
            default=None,
        )

    signals_by_path: dict[str, list[dict]] = {}
    if store is not None:
        file_paths = {row["id"]: row["path"] for row in store.files()}
        for signal in store.signals():
            path = file_paths.get(signal.get("file_id"))
            if path:
                signals_by_path.setdefault(path, []).append(signal)

    security = iso.run(
        "project.security-view",
        build_security_view,
        prepared,
        signals_by_path=signals_by_path,
        default=None,
    )
    security_path = None
    if security is not None:
        prepared["security"] = security
        security_path = iso.run(
            "project.security-json",
            write_human_view,
            security,
            output_dir / SECURITY_FILENAME,
            indent=indent,
            default=None,
        )

    orientation = iso.run(
        "project.orientation-view",
        build_orientation,
        prepared,
        coverage=coverage,
        support=support,
        security=security,
        default=None,
    )
    orientation_path = None
    if orientation is not None:
        prepared["orientation"] = orientation
        orientation_path = iso.run(
            "project.orientation-json",
            write_human_view,
            orientation,
            output_dir / ORIENTATION_FILENAME,
            indent=indent,
            default=None,
        )

    return orientation_path, support_path, security_path


def project_split(
    arch: dict,
    output_dir,
    *,
    store=None,
    root=None,
    generated_at: Optional[str] = None,
    analyzer_version: Optional[str] = None,
    channel: str = DEFAULT_CHANNEL,
    previous: Optional[dict] = None,
    commit_sha: str = "",
    now: Optional[datetime] = None,
    shard_size: int = DEFAULT_SHARD_SIZE,
    design_signals: bool = False,
    indent=2,
) -> ProjectionResult:
    """Write the split projection (manifest + details + coverage + search).

    Every emitter runs under a per-unit isolator (card R1 wave 2): a sidecar
    that raises records a deterministic honest gap and is absent, never
    fracturing the run. The manifest (the main artifact) is written LAST so it
    carries every gap, and it degrades to a skeleton on its own failure.

    ``channel`` is the resolved maturity channel (card R3); it stamps a
    deterministic ``gate_provenance`` on a non-default run and is a no-op on the
    default ``stable`` channel.

    ``design_signals`` is the D3 opt-in. Default off, and with it off nothing in
    the design path runs and the bytes are unchanged.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    gaps: list = []
    iso = Isolator("project", gaps)

    prepared = prepare_arch(
        arch, root=root, generated_at=generated_at,
        analyzer_version=analyzer_version, channel=channel, isolator=iso,
    )
    # Gaps the derive tier already recorded on the arch (dicts). Captured before
    # any projection work so the final merge combines the two sources without
    # double-counting.
    derive_gaps = list(prepared.get("gaps", []))

    # Store enrichment is canonical: overlay it (with staleness markers) before
    # the changelog, manifest, and search shards read the arch (I5). No-op when
    # the store carries no enrichment, so non-enriched projections are unchanged.
    iso.run("project.enrichment-overlay", apply_enrichment_overlay, prepared, store)
    # Phase 7 verdicts and names (P7-3/P7-4): edge verdicts, concern names, and
    # finding verification statuses, plus AI intent-violation findings. No-op when
    # the store carries none of these enrichment kinds (parity-safe).
    iso.run("project.verdict-overlay", apply_verdict_overlay, prepared, store)
    coverage = iso.run("project.coverage", build_coverage, store, root=root, default=None)
    activity = iso.run("project.activity", build_activity, store, default=None)
    # SBOM and supply chain (P10-1): parse the repo's manifests deterministically,
    # write a CycloneDX sbom.json beside the manifest, and stamp the compact
    # supply_chain section onto the arch so it rides in the manifest. No-op (None)
    # when there is no scan root or the repo carries no manifests, so unaffected
    # projections are byte-identical. Done before the changelog so a new or
    # changed dependency set is a recorded change.
    sbom_section = iso.run(
        "project.sbom", emit_sbom, prepared, output_dir, root=root,
        coverage=coverage, generated_at=generated_at, indent=indent, default=None,
    )
    if sbom_section is not None:
        prepared["supply_chain"] = sbom_section
    # CRA readiness (P10-4, Option C): write cra-readiness.json beside sbom.json
    # and merge the ABSENT-item findings into the existing findings surface (no
    # new view). Done after the SBOM (the SBOM-present check reads the section)
    # and before the changelog so a newly-missing SECURITY.md is a recorded
    # change. No-op (None) without a scan root, so unaffected projections are
    # byte-identical.
    cra_result = iso.run(
        "project.cra", emit_cra_readiness, output_dir, root=root,
        supply_chain=sbom_section, indent=indent, default=None,
    )
    if cra_result is not None:
        _merge_cra_findings(prepared, cra_result.findings)
    # AI surface (P10-5): what in this codebase talks to, routes, or is AI.
    # Deterministic: catalog-matched dependencies (reusing the SBOM's parsed
    # rows), imports, bounded content signatures, and artifact filenames, all
    # from the store. After the SBOM because it reuses that parse; before the
    # changelog so a changed AI surface is a recorded change, matching the
    # SBOM's placement and rationale.
    ai_items = iso.run(
        "project.ai-surface", emit_ai_surface, prepared, store,
        supply_chain=sbom_section, root=root, default=None,
    )
    if ai_items is not None:
        prepared["ai_surface"] = ai_items
    # Design signals (D3): per-component metrics and architecture-level findings,
    # opt-in via --design-signals and a strict no-op when off, so both golden
    # corpora stay still. Before the changelog so a newly appeared dependency
    # cycle is a recorded change, matching the SBOM's placement and rationale.
    design_section = iso.run(
        "project.design-signals", emit_design_signals, prepared, store,
        enabled=design_signals, default=None,
    )
    if design_section is not None:
        prepared["design_signals"] = design_section
    serial = iso.run(
        "project.changelog", _finish_changelog, prepared, previous,
        output_dir / "manifest.json", commit_sha=commit_sha, now=now, default=0,
    )

    # Search shards, the sidecar coverage/activity JSON, and the AI front door
    # all run BEFORE the manifest so any gap they record rides on the manifest
    # that is written last. Their file bytes are independent of write order, so a
    # clean run is byte-identical to the pre-isolation ordering.
    n_gaps = len(gaps)
    search_manifest = iso.run(
        "project.search-shards", write_search_shards, prepared, output_dir,
        store=store, shard_size=shard_size, indent=indent,
        default_factory=lambda: _empty_search_manifest(shard_size),
    )
    # A failed search write yields the empty-manifest default (a truthy dict), so
    # the front door must NOT be told search is present, or ai.json / llms.txt
    # would advertise a search index that was never written (a lying contract the
    # front door explicitly guards against). Distinguish a real empty index (no
    # gap) from a failed write (a gap was recorded) and pass None on failure so
    # the front door emits its honest search-absent fallback.
    search_ok = len(gaps) == n_gaps

    coverage_path = None
    if coverage is not None:
        coverage_path = output_dir / "coverage.json"
        iso.run("project.coverage-json", _dump_json, coverage_path, coverage, indent)

    activity_path = None
    if activity is not None:
        activity_path = output_dir / "activity.json"
        iso.run("project.activity-json", _dump_json, activity_path, activity, indent)

    orientation_path, support_path, security_path = _emit_human_views(
        prepared, output_dir, coverage, iso, indent, store=store
    )

    ai_json_path, llms_txt_path = iso.run(
        "project.frontdoor", write_front_door, prepared, output_dir, mode="split",
        coverage=coverage, activity=activity,
        search_manifest=(search_manifest if search_ok else None),
        supply_chain=sbom_section, cra_present=cra_result is not None, indent=indent,
        default=(None, None),
    )

    # The manifest is the split-mode main artifact: written last, carrying every
    # project-tier gap, and degrading to a well-formed skeleton on its own
    # failure. The skeleton reads the live gaps list, so it accounts for the
    # manifest writer's own failure too.
    _apply_project_gaps(prepared, derive_gaps, gaps)
    manifest_path = iso.run(
        "project.manifest", write_manifest_and_details, prepared, output_dir,
        coverage=coverage, activity=activity, indent=indent,
        default_factory=lambda: _write_skeleton_manifest(
            output_dir, prepared, coverage, activity, derive_gaps, gaps, indent
        ),
    )

    return ProjectionResult(
        mode="split",
        output_dir=output_dir,
        manifest_path=manifest_path,
        coverage_path=coverage_path,
        activity_path=activity_path,
        sbom_path=(output_dir / "sbom.json") if sbom_section is not None else None,
        cra_path=cra_result.artifact_path if cra_result is not None else None,
        search_manifest_path=output_dir / "search" / "manifest.json",
        ai_json_path=ai_json_path,
        llms_txt_path=llms_txt_path,
        orientation_path=orientation_path,
        support_path=support_path,
        security_path=security_path,
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
    channel: str = DEFAULT_CHANNEL,
    previous: Optional[dict] = None,
    commit_sha: str = "",
    now: Optional[datetime] = None,
    design_signals: bool = False,
    indent=2,
) -> ProjectionResult:
    """Write the monolithic ``architecture.json`` projection.

    Isolated exactly like ``project_split``: sidecars that raise record honest
    gaps and are absent; ``architecture.json`` (the main artifact) is written
    last carrying every gap, and degrades to a skeleton on its own failure.

    ``channel`` is the resolved maturity channel (card R3); it stamps a
    deterministic ``gate_provenance`` on a non-default run and is a no-op on the
    default ``stable`` channel.

    ``design_signals`` is the D3 opt-in. Default off, and with it off nothing in
    the design path runs and the bytes are unchanged.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gaps: list = []
    iso = Isolator("project", gaps)

    prepared = prepare_arch(
        arch, root=root, generated_at=generated_at,
        analyzer_version=analyzer_version, channel=channel, isolator=iso,
    )
    derive_gaps = list(prepared.get("gaps", []))

    # Store enrichment is canonical: overlay it (with staleness markers) before
    # the changelog and monolith read the arch (I5). No-op when the store carries
    # no enrichment, so non-enriched projections are unchanged.
    iso.run("project.enrichment-overlay", apply_enrichment_overlay, prepared, store)
    iso.run("project.verdict-overlay", apply_verdict_overlay, prepared, store)
    coverage = iso.run("project.coverage", build_coverage, store, root=root, default=None)
    activity = iso.run("project.activity", build_activity, store, default=None)
    # SBOM and supply chain (P10-1): sbom.json lands beside the single
    # architecture.json, and the supply_chain section rides in the monolith
    # (write_monolith copies every arch key). See project_split for the rationale.
    sbom_section = iso.run(
        "project.sbom", emit_sbom, prepared, output_path.parent, root=root,
        coverage=coverage, generated_at=generated_at, indent=indent, default=None,
    )
    if sbom_section is not None:
        prepared["supply_chain"] = sbom_section
    # CRA readiness (P10-4, Option C): cra-readiness.json lands beside the single
    # architecture.json, and the gap findings ride in the monolith .findings. See
    # project_split for the ordering rationale.
    cra_result = iso.run(
        "project.cra", emit_cra_readiness, output_path.parent, root=root,
        supply_chain=sbom_section, indent=indent, default=None,
    )
    if cra_result is not None:
        _merge_cra_findings(prepared, cra_result.findings)
    # Design signals (D3): rides in the monolith (write_monolith copies every
    # arch key). See project_split for the placement rationale.
    design_section = iso.run(
        "project.design-signals", emit_design_signals, prepared, store,
        enabled=design_signals, default=None,
    )
    if design_section is not None:
        prepared["design_signals"] = design_section
    serial = iso.run(
        "project.changelog", _finish_changelog, prepared, previous,
        output_path, commit_sha=commit_sha, now=now, default=0,
    )

    # AI front door (P8-3): emitted beside the single architecture.json, with the
    # endpoint map pointing at that one file (no shards in monolith mode). Runs
    # before the monolith write so its gap, if any, rides on the monolith.
    orientation_path, support_path, security_path = _emit_human_views(
        prepared, output_path.parent, coverage, iso, indent, store=store
    )

    ai_json_path, llms_txt_path = iso.run(
        "project.frontdoor", write_front_door, prepared, output_path.parent,
        mode="monolith", coverage=coverage, activity=activity,
        supply_chain=sbom_section, cra_present=cra_result is not None,
        monolith_filename=output_path.name, indent=indent, default=(None, None),
    )

    _apply_project_gaps(prepared, derive_gaps, gaps)
    monolith_path = iso.run(
        "project.monolith", write_monolith, prepared, output_path,
        coverage=coverage, activity=activity, indent=indent,
        default_factory=lambda: _write_skeleton_monolith(
            output_path, prepared, coverage, activity, derive_gaps, gaps, indent
        ),
    )

    return ProjectionResult(
        mode="monolith",
        monolith_path=monolith_path,
        ai_json_path=ai_json_path,
        llms_txt_path=llms_txt_path,
        orientation_path=orientation_path,
        support_path=support_path,
        security_path=security_path,
        sbom_path=(output_path.parent / "sbom.json") if sbom_section is not None else None,
        cra_path=cra_result.artifact_path if cra_result is not None else None,
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
