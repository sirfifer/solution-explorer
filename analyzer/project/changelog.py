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
any drift from current behavior fails CI.

Serials are preserved: each entry carries ``previous_serial + 1`` and the entry
is only appended when it has changes, matching the old ``_append_changelog``.
The timestamp and commit sha are injectable so projection output is
byte-deterministic (invariant I4); left to their defaults they reproduce the
old behavior (wall-clock timestamp, empty commit sha).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

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


# ---------------------------------------------------------------------------
# diff + entry construction
# ---------------------------------------------------------------------------

def compute_diff_summary(
    old_baseline: Optional[dict], new_arch: dict, changed_file_count: int = 0
) -> dict:
    """Summarize component/relationship changes between two projections."""
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
            "relationships_added": len(all_rels),
            "relationships_removed": 0,
            "relationships_added_tuples": sorted(all_rels),
            "relationships_removed_tuples": [],
            "files_changed": changed_file_count,
        }

    old_ids = set(_collect_component_ids(old_baseline.get("components", [])))
    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)

    old_metrics = _collect_component_metrics(old_baseline.get("components", []))
    new_metrics = _collect_component_metrics(new_arch.get("components", []))
    modified = sorted(
        cid for cid in (old_ids & new_ids)
        if old_metrics.get(cid, {}) != new_metrics.get(cid, {})
    )

    old_rels = {
        (r.get("source"), r.get("target"), r.get("type"))
        for r in old_baseline.get("relationships", [])
    }
    new_rels = {
        (r.get("source"), r.get("target"), r.get("type"))
        for r in new_arch.get("relationships", [])
    }
    return {
        "components_added": added,
        "components_removed": removed,
        "components_modified": modified,
        "relationships_added": len(new_rels - old_rels),
        "relationships_removed": len(old_rels - new_rels),
        "relationships_added_tuples": sorted(new_rels - old_rels),
        "relationships_removed_tuples": sorted(old_rels - new_rels),
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
    rel_added = diff_summary.get("relationships_added", 0)
    rel_removed = diff_summary.get("relationships_removed", 0)
    if added:
        parts.append(f"{added} component{'s' if added != 1 else ''} added")
    if modified:
        parts.append(f"{modified} component{'s' if modified != 1 else ''} modified")
    if removed:
        parts.append(f"{removed} component{'s' if removed != 1 else ''} removed")
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
