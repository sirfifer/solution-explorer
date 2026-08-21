"""Changelog as a store-vs-previous-projection diff (TARGET-ARCHITECTURE.md 4.4).

The old engine computes the changelog by diffing the previous output file
against the new architecture (analyzer/cli.py ``_apply_changelog`` delegating to
``IncrementalAnalyzer``). The projection tier owns this on the new path: it
diffs the previous projection (a manifest or monolith dict, which carries
``components``, ``relationships``, ``changelog`` and ``changelog_serial``)
against the freshly derived arch dict.

The diff logic is ported here faithfully so the new engine does not import the
old one (incremental.py is deleted at the P4-7 cutover, which re-expresses this
as a store-vs-store diff). ``tests/test_project.py`` proves entry-for-entry
equivalence against ``IncrementalAnalyzer`` on a scripted change sequence, so
any drift from current behavior fails CI. To keep that equivalence,
``analyzer/incremental.py`` delegates its ``compute_diff_summary`` and
``build_changelog_entry`` methods to the module-level functions here rather
than keeping a second copy of the diff logic.

Serials are preserved: each entry carries ``previous_serial + 1`` and the entry
is only appended when it has changes, matching the old ``_append_changelog``.
The timestamp and commit sha are injectable so projection output is
byte-deterministic (invariant I4); left to their defaults they reproduce the
old behavior (wall-clock timestamp, empty commit sha).

Composed (multi-repo) projections prefix every component id with
``<repo_name>/`` (see ``analyzer/derive/multi.py::merge_architectures`` and
``analyzer/multi_repo.py``). A plain set difference on ids would then treat
every component as removed-and-re-added the moment a projection switches
composition, even though nothing about the component changed. Before diffing,
ids are normalized through ``analyzer/project/id_normalization.py``:
composition changes are read structurally off the ``repositories`` metadata
(deterministic, not inferred), and any still-unmatched pairs get one
ambiguity-guarded residual match attempt on ``(name, type)``. See that
module's docstring for the full rationale. When repository composition is
unchanged, normalization is a no-op and output is byte-identical to before
this was added.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .id_normalization import composition_transform, infer_reidentification_matches

__all__ = ["apply_changelog", "compute_diff_summary", "build_changelog_entry"]


# ---------------------------------------------------------------------------
# tree walkers (ported verbatim from IncrementalAnalyzer for equivalence)
# ---------------------------------------------------------------------------

def _collect_component_ids(components: list) -> list[str]:
    ids: list[str] = []
    for comp in components:
        ids.append(comp.get("id", ""))
        ids.extend(_collect_component_ids(comp.get("children", [])))
    return ids


def _collect_component_metrics(components: list) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for comp in components:
        result[comp.get("id", "")] = comp.get("metrics", {})
        result.update(_collect_component_metrics(comp.get("children", [])))
    return result


def _build_component_info_map(components: list) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}

    def walk(comps: list) -> None:
        for comp in comps:
            cid = comp.get("id", "")
            result[cid] = {
                "name": comp.get("name", cid),
                "type": comp.get("type", "module"),
            }
            walk(comp.get("children", []))

    walk(components)
    return result


def _collect_component_files(components: list) -> dict[str, list]:
    result: dict[str, list] = {}
    for comp in components:
        result[comp.get("id", "")] = comp.get("files", [])
        result.update(_collect_component_files(comp.get("children", [])))
    return result


# ---------------------------------------------------------------------------
# diff + entry construction
# ---------------------------------------------------------------------------

def _empty_reidentification_bucket() -> dict:
    return {"deterministic": 0, "inferred": 0}


def compute_diff_summary(
    old_baseline: Optional[dict], new_arch: dict, changed_file_count: int = 0
) -> dict:
    """Summarize component/relationship changes between two projections.

    Component and relationship ids are normalized first (see
    ``id_normalization.py``) so a repository-composition change (a projection
    switching between the plain and composed multi-repo shape) is not
    misreported as every component being removed and re-added. When
    composition is unchanged the normalization is a no-op and this reproduces
    the pre-normalization behavior exactly.
    """
    new_ids = set(_collect_component_ids(new_arch.get("components", [])))

    if old_baseline is None:
        all_rels = {
            (r.get("source"), r.get("target"), r.get("type"))
            for r in new_arch.get("relationships", [])
        }
        return {
            "components_added": sorted(new_ids),
            "components_removed": [],
            "components_modified": [],
            "components_reidentified": [],
            "components_reidentified_folded": _empty_reidentification_bucket(),
            "components_infrastructure_added": [],
            "components_infrastructure_removed": [],
            "relationships_added": len(all_rels),
            "relationships_removed": 0,
            "relationships_added_tuples": sorted(all_rels),
            "relationships_removed_tuples": [],
            "files_changed": changed_file_count,
        }

    old_ids = set(_collect_component_ids(old_baseline.get("components", [])))

    transform = composition_transform(old_baseline, new_arch)
    if transform is None:
        old_key = new_key = lambda cid: cid  # noqa: E731 - trivial identity, no-op fast path
        wrapper_ids_added: frozenset = frozenset()
        wrapper_ids_removed: frozenset = frozenset()
    else:
        old_key, new_key = transform.old_key, transform.new_key
        wrapper_ids_added = transform.wrapper_ids_added
        wrapper_ids_removed = transform.wrapper_ids_removed

    old_metrics = _collect_component_metrics(old_baseline.get("components", []))
    new_metrics = _collect_component_metrics(new_arch.get("components", []))
    old_info = _build_component_info_map(old_baseline.get("components", []))
    new_info = _build_component_info_map(new_arch.get("components", []))
    old_files = _collect_component_files(old_baseline.get("components", []))
    new_files = _collect_component_files(new_arch.get("components", []))

    # Canonical-key -> raw-id maps, so we can report using each side's own raw
    # id (matching the existing convention: added reports the new-side id,
    # removed reports the old-side id) while comparing on the normalized key.
    old_by_key: dict[str, str] = {old_key(cid): cid for cid in old_ids}
    new_by_key: dict[str, str] = {new_key(cid): cid for cid in new_ids}

    common_keys = set(old_by_key) & set(new_by_key)
    added_keys = set(new_by_key) - set(old_by_key)
    removed_keys = set(old_by_key) - set(new_by_key)

    reidentified: list[dict] = []
    folded = _empty_reidentification_bucket()

    def _classify_pair(old_id: str, new_id: str, confidence: str) -> None:
        oi = old_info.get(old_id, {"name": old_id, "type": "module"})
        ni = new_info.get(new_id, {"name": new_id, "type": "module"})
        same_name = oi["name"] == ni["name"]
        same_type = oi["type"] == ni["type"]
        same_metrics = old_metrics.get(old_id, {}) == new_metrics.get(new_id, {})
        if old_id == new_id:
            return  # identity unchanged; handled by the ordinary modified check below
        if same_name and same_type and same_metrics:
            folded[confidence] += 1
            return
        reidentified.append({
            "old_id": old_id, "new_id": new_id,
            "old_name": oi["name"], "new_name": ni["name"],
            "old_type": oi["type"], "new_type": ni["type"],
            "confidence": confidence,
        })

    modified: list[str] = []
    for key in common_keys:
        oid, nid = old_by_key[key], new_by_key[key]
        if oid == nid:
            if old_metrics.get(oid, {}) != new_metrics.get(nid, {}):
                modified.append(oid)
            continue
        _classify_pair(oid, nid, "deterministic")

    real_removed_ids = {old_by_key[k] for k in removed_keys} - wrapper_ids_removed
    real_added_ids = {new_by_key[k] for k in added_keys} - wrapper_ids_added

    # Step 3 (residual inference) only runs when a composition change was
    # actually detected. Without one, this reproduces the pre-normalization
    # behavior exactly: an unrelated rename in an ordinary single-repo scan
    # stays a plain add + remove, not a guessed re-identification.
    if transform is not None and real_removed_ids and real_added_ids:
        matches, matched_removed, matched_added = infer_reidentification_matches(
            sorted(real_removed_ids), sorted(real_added_ids),
            old_info, new_info, old_metrics, new_metrics, old_files, new_files,
        )
        for m in matches:
            _classify_pair(m.old_id, m.new_id, "inferred")
        real_removed_ids -= matched_removed
        real_added_ids -= matched_added

    infra_added = sorted({new_by_key[k] for k in added_keys} & wrapper_ids_added)
    infra_removed = sorted({old_by_key[k] for k in removed_keys} & wrapper_ids_removed)

    added = sorted(real_added_ids)
    removed = sorted(real_removed_ids)
    modified = sorted(modified)
    reidentified.sort(key=lambda r: (r["old_id"], r["new_id"]))

    old_rels_raw = [
        (r.get("source"), r.get("target"), r.get("type"))
        for r in old_baseline.get("relationships", [])
    ]
    new_rels_raw = [
        (r.get("source"), r.get("target"), r.get("type"))
        for r in new_arch.get("relationships", [])
    ]
    old_rel_by_key: dict[tuple, tuple] = {}
    for s, t, ty in old_rels_raw:
        old_rel_by_key.setdefault((old_key(s), old_key(t), ty), (s, t, ty))
    new_rel_by_key: dict[tuple, tuple] = {}
    for s, t, ty in new_rels_raw:
        new_rel_by_key.setdefault((new_key(s), new_key(t), ty), (s, t, ty))

    rel_added_keys = set(new_rel_by_key) - set(old_rel_by_key)
    rel_removed_keys = set(old_rel_by_key) - set(new_rel_by_key)
    relationships_added_tuples = sorted(new_rel_by_key[k] for k in rel_added_keys)
    relationships_removed_tuples = sorted(old_rel_by_key[k] for k in rel_removed_keys)

    return {
        "components_added": added,
        "components_removed": removed,
        "components_modified": modified,
        "components_reidentified": reidentified,
        "components_reidentified_folded": folded,
        "components_infrastructure_added": infra_added,
        "components_infrastructure_removed": infra_removed,
        "relationships_added": len(relationships_added_tuples),
        "relationships_removed": len(relationships_removed_tuples),
        "relationships_added_tuples": relationships_added_tuples,
        "relationships_removed_tuples": relationships_removed_tuples,
        "files_changed": changed_file_count,
    }


def build_changelog_entry(
    diff_summary: dict,
    old_arch: Optional[dict],
    new_arch: dict,
    scan_type: str,
    serial: int,
    *,
    commit_sha: str = "",
    timestamp: Optional[str] = None,
) -> dict:
    """Turn a diff summary into a structured changelog entry."""
    info = _build_component_info_map(new_arch.get("components", []))
    if old_arch:
        for cid, cinfo in _build_component_info_map(old_arch.get("components", [])).items():
            if cid not in info:
                info[cid] = cinfo

    changes: list[dict] = []

    for cid in diff_summary.get("components_added", []):
        ci = info.get(cid, {"name": cid, "type": "module"})
        changes.append({
            "kind": "component_added", "target_id": cid,
            "target_name": ci["name"], "target_type": ci["type"],
            "detail": "New component discovered",
        })
    for cid in diff_summary.get("components_removed", []):
        ci = info.get(cid, {"name": cid, "type": "module"})
        changes.append({
            "kind": "component_removed", "target_id": cid,
            "target_name": ci["name"], "target_type": ci["type"],
            "detail": "Component no longer detected",
        })
    for cid in diff_summary.get("components_modified", []):
        ci = info.get(cid, {"name": cid, "type": "module"})
        changes.append({
            "kind": "component_modified", "target_id": cid,
            "target_name": ci["name"], "target_type": ci["type"],
            "detail": "Component structure changed",
        })

    for cid in diff_summary.get("components_infrastructure_added", []):
        ci = info.get(cid, {"name": cid, "type": "repository"})
        changes.append({
            "kind": "component_infrastructure_added", "target_id": cid,
            "target_name": ci["name"], "target_type": ci.get("type", "repository"),
            "detail": (
                f"Composition wrapper added for repository '{ci['name']}' "
                "(not a component of the analysed codebase)"
            ),
        })
    for cid in diff_summary.get("components_infrastructure_removed", []):
        ci = info.get(cid, {"name": cid, "type": "repository"})
        changes.append({
            "kind": "component_infrastructure_removed", "target_id": cid,
            "target_name": ci["name"], "target_type": ci.get("type", "repository"),
            "detail": (
                f"Composition wrapper removed for repository '{ci['name']}' "
                "(not a component of the analysed codebase)"
            ),
        })

    for r in diff_summary.get("components_reidentified", []):
        what_changed = []
        if r["old_name"] != r["new_name"]:
            what_changed.append(f"name '{r['old_name']}' -> '{r['new_name']}'")
        if r["old_type"] != r["new_type"]:
            what_changed.append(f"type '{r['old_type']}' -> '{r['new_type']}'")
        suffix = f"; {', '.join(what_changed)}" if what_changed else ""
        confidence_note = (
            "" if r["confidence"] == "deterministic"
            else " (inferred match, not structurally certain)"
        )
        changes.append({
            "kind": "component_reidentified",
            "target_id": r["new_id"],
            "target_name": r["new_name"], "target_type": r["new_type"],
            "old_id": r["old_id"], "new_id": r["new_id"],
            "confidence": r["confidence"],
            "detail": (
                f"Re-identified from '{r['old_id']}' to '{r['new_id']}'"
                f"{suffix}{confidence_note}"
            ),
        })

    folded = diff_summary.get("components_reidentified_folded", {}) or {}
    for confidence, count in (("deterministic", folded.get("deterministic", 0)),
                              ("inferred", folded.get("inferred", 0))):
        if not count:
            continue
        confidence_note = (
            "" if confidence == "deterministic"
            else " (inferred matches, not structurally certain)"
        )
        changes.append({
            "kind": "component_reidentified_bulk",
            "target_id": "", "target_name": "", "target_type": "",
            "count": count,
            "confidence": confidence,
            "detail": (
                f"{count} component{'s' if count != 1 else ''} re-identified "
                f"under a new namespace{confidence_note}"
            ),
        })

    for src, tgt, rtype in diff_summary.get("relationships_added_tuples", []):
        src_info = info.get(src, {"name": src})
        tgt_info = info.get(tgt, {"name": tgt})
        changes.append({
            "kind": "relationship_added", "target_id": f"{src}->{tgt}",
            "target_name": f"{src_info['name']} -> {tgt_info['name']}",
            "target_type": rtype or "dependency",
            "source_id": src, "source_name": src_info["name"],
            "dest_id": tgt, "dest_name": tgt_info["name"],
            "detail": f"{rtype or 'dependency'} connection",
        })
    for src, tgt, rtype in diff_summary.get("relationships_removed_tuples", []):
        src_info = info.get(src, {"name": src})
        tgt_info = info.get(tgt, {"name": tgt})
        changes.append({
            "kind": "relationship_removed", "target_id": f"{src}->{tgt}",
            "target_name": f"{src_info['name']} -> {tgt_info['name']}",
            "target_type": rtype or "dependency",
            "source_id": src, "source_name": src_info["name"],
            "dest_id": tgt, "dest_name": tgt_info["name"],
            "detail": f"{rtype or 'dependency'} connection removed",
        })

    parts = []
    added = len(diff_summary.get("components_added", []))
    removed = len(diff_summary.get("components_removed", []))
    modified = len(diff_summary.get("components_modified", []))
    reidentified_count = len(diff_summary.get("components_reidentified", []))
    folded = diff_summary.get("components_reidentified_folded", {}) or {}
    folded_total = folded.get("deterministic", 0) + folded.get("inferred", 0)
    infra_added = len(diff_summary.get("components_infrastructure_added", []))
    infra_removed = len(diff_summary.get("components_infrastructure_removed", []))
    rel_added = diff_summary.get("relationships_added", 0)
    rel_removed = diff_summary.get("relationships_removed", 0)
    if added:
        parts.append(f"{added} component{'s' if added != 1 else ''} added")
    if modified:
        parts.append(f"{modified} component{'s' if modified != 1 else ''} modified")
    if removed:
        parts.append(f"{removed} component{'s' if removed != 1 else ''} removed")
    if reidentified_count:
        parts.append(
            f"{reidentified_count} component{'s' if reidentified_count != 1 else ''} reclassified under a new id"
        )
    if folded_total:
        parts.append(
            f"{folded_total} component{'s' if folded_total != 1 else ''} re-identified under a new namespace"
        )
    if infra_added:
        parts.append(f"{infra_added} composition wrapper{'s' if infra_added != 1 else ''} added")
    if infra_removed:
        parts.append(f"{infra_removed} composition wrapper{'s' if infra_removed != 1 else ''} removed")
    if rel_added:
        parts.append(f"{rel_added} relationship{'s' if rel_added != 1 else ''} added")
    if rel_removed:
        parts.append(f"{rel_removed} relationship{'s' if rel_removed != 1 else ''} removed")
    summary = ", ".join(parts) if parts else "No structural changes"

    ts = timestamp if timestamp is not None else datetime.now(timezone.utc).isoformat()
    return {
        "serial": serial,
        "timestamp": ts,
        "commit_sha": commit_sha or "",
        "scan_type": scan_type,
        "summary": summary,
        "changes": changes,
    }


def _append_changelog(
    arch_dict: dict, entry: dict, baseline: Optional[dict], max_entries: int = 50
) -> None:
    existing = list(baseline.get("changelog", [])) if baseline else []
    if entry.get("changes"):
        existing.append(entry)
    if len(existing) > max_entries:
        existing = existing[-max_entries:]
    arch_dict["changelog"] = existing
    arch_dict["changelog_serial"] = entry["serial"]


def apply_changelog(
    arch: dict,
    previous: Optional[dict],
    *,
    commit_sha: str = "",
    now: Optional[datetime] = None,
    max_entries: int = 50,
) -> dict:
    """Diff ``previous`` projection against ``arch`` and attach the changelog.

    Mutates and returns ``arch`` (adds ``changelog`` and ``changelog_serial``),
    matching analyzer/cli.py ``_apply_changelog`` semantics. ``now`` (a
    ``datetime``) and ``commit_sha`` are injectable for deterministic output;
    with defaults the behavior reproduces the old engine's.
    """
    diff = compute_diff_summary(previous, arch)
    scan_type = "initial" if previous is None else "full"
    prev_serial = (previous or {}).get("changelog_serial", 0)
    timestamp = now.isoformat() if now is not None else None
    entry = build_changelog_entry(
        diff, previous, arch, scan_type, prev_serial + 1,
        commit_sha=commit_sha, timestamp=timestamp,
    )
    _append_changelog(arch, entry, previous, max_entries)
    return arch
