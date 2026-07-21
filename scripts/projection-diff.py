#!/usr/bin/env python3
"""Deterministic diff over two full solution-explorer projections (card G1).

This is the projection-diff tool from REGRESSION-STRATEGY.md. It answers one
question the owner wants to ask continuously, especially for the demo: did this
build improve or regress the representation of the project, and exactly what
changed since the last build.

It reads two full projections (the monolith ``architecture.json`` written by
``analyze.py -o``, old/blue first then new/green) and reports the deltas across
every projection section:

  - components: count and identity (added, removed, changed type/path/language)
  - relationships: per-kind counts and added/removed edges
  - findings: new, resolved, and changed (rank_score or verification_status)
  - coverage: total, parsed, and per-disposition summary deltas
  - inventory: non-source total, source-gap total, dominant, per-group counts
  - data_entities: count, added, removed
  - entity_access: count, added, removed
  - capabilities: count, added, removed
  - enrichment: AI-enrichment coverage at component, relationship, and
    architecture level

Determinism is a hard contract: the diff never reads a timestamp, sorts every
enumerated list, and produces byte-identical output for byte-identical inputs.
Two runs over the same pair of files always agree.

Sections absent from an older or simpler dataset are treated as empty, never an
error, so the tool follows the additive-projection rule (old datasets diff
cleanly against new ones; the appearance of a whole new section shows up as
additions).

Usage:
    python3 scripts/projection-diff.py OLD.json NEW.json
    python3 scripts/projection-diff.py OLD.json NEW.json --format json
    python3 scripts/projection-diff.py OLD.json NEW.json --output diff.json --format json
    python3 scripts/projection-diff.py OLD.json NEW.json --exit-code   # exit 1 if anything changed

The text report is for humans and PR comments; ``--format json`` is the complete
machine-readable delta for CI. ``--exit-code`` turns a non-empty diff into a
non-zero exit so a golden-corpus job can gate on "no unexplained change."
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

# The projection sections this tool understands, in a fixed presentation order.
# Kept in sync with analyzer/project/frontdoor.py::_MANIFEST_SECTIONS for the
# sections that carry diffable identity.

# How many entries a single text-report list shows before it summarizes the
# remainder. The JSON output is never truncated; this only keeps the human
# report readable. When it truncates it says so (no silent caps).
_TEXT_LIST_CAP = 50


def load_projection(path: str | Path) -> dict:
    """Load a projection JSON file, returning its top-level object.

    Raises a clear error for a missing file or malformed JSON rather than a
    bare stack trace, because this runs in CI and in redeploy scripts where the
    failure needs to be legible.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"projection not found: {p}")
    try:
        with p.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(f"projection is not valid JSON ({p}): {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"projection root is not a JSON object ({p})")
    return data


def flatten_components(arch: dict) -> dict[str, dict]:
    """Flatten the nested component tree into an id -> node map.

    Components nest via ``children``; identity lives on ``id``. A node without
    an id is skipped rather than crashing the diff, and if two nodes share an id
    the first wins (deterministic by tree order), which keeps the map stable.
    """
    out: dict[str, dict] = {}

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        cid = node.get("id")
        if isinstance(cid, str) and cid and cid not in out:
            out[cid] = node
        for child in node.get("children", []) or []:
            walk(child)

    for root in arch.get("components", []) or []:
        walk(root)
    return out


def _index_by(items: Any, keyfn: Callable[[dict], Optional[str]]) -> dict[str, dict]:
    """Index a list of dicts by a stable string key, skipping unkeyable items."""
    out: dict[str, dict] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        key = keyfn(item)
        if isinstance(key, str) and key and key not in out:
            out[key] = item
    return out


def _counts_by(items: Any, keyfn: Callable[[dict], Optional[str]]) -> dict[str, int]:
    """Count a list of dicts grouped by a string key (deterministic)."""
    out: dict[str, int] = {}
    for item in items or []:
        if not isinstance(item, dict):
            continue
        key = keyfn(item) or "(unknown)"
        out[key] = out.get(key, 0) + 1
    return out


def _merge_count_delta(
    old_counts: dict[str, int], new_counts: dict[str, int]
) -> dict[str, dict[str, int]]:
    """Per-key {old, new} counts for every key present on either side, changes only."""
    keys = sorted(set(old_counts) | set(new_counts))
    delta: dict[str, dict[str, int]] = {}
    for key in keys:
        o = old_counts.get(key, 0)
        n = new_counts.get(key, 0)
        if o != n:
            delta[key] = {"old": o, "new": n}
    return delta


def _rel_key(rel: dict) -> str:
    return f"{rel.get('source', '')}\t{rel.get('target', '')}\t{rel.get('type', '')}"


def _rel_label(rel: dict) -> str:
    return f"{rel.get('source', '?')} -> {rel.get('target', '?')} ({rel.get('type', '?')})"


def _access_key(acc: dict) -> str:
    return f"{acc.get('accessor_id', '')}\t{acc.get('entity_id', '')}\t{acc.get('mode', '')}"


def _access_label(acc: dict) -> str:
    mode = acc.get("mode", "?")
    return f"{acc.get('accessor_id', '?')} {mode} {acc.get('entity_id', '?')}"


# Identity fields on a component whose change is a real structural signal (not
# prose or metrics that move on every run). A change here is worth flagging.
_COMPONENT_IDENTITY_FIELDS = ("type", "path", "language", "name")


def _diff_components(old: dict, new: dict) -> dict:
    old_map = flatten_components(old)
    new_map = flatten_components(new)
    old_ids = set(old_map)
    new_ids = set(new_map)
    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    changed: list[dict] = []
    for cid in sorted(old_ids & new_ids):
        o = old_map[cid]
        n = new_map[cid]
        field_changes = {}
        for field in _COMPONENT_IDENTITY_FIELDS:
            ov = o.get(field)
            nv = n.get(field)
            if ov != nv:
                field_changes[field] = {"old": ov, "new": nv}
        if field_changes:
            changed.append({"id": cid, "fields": field_changes})
    return {
        "old_count": len(old_map),
        "new_count": len(new_map),
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def _diff_relationships(old: dict, new: dict) -> dict:
    old_rels = old.get("relationships", []) or []
    new_rels = new.get("relationships", []) or []
    old_map = _index_by(old_rels, _rel_key)
    new_map = _index_by(new_rels, _rel_key)
    added = sorted(_rel_label(new_map[k]) for k in (set(new_map) - set(old_map)))
    removed = sorted(_rel_label(old_map[k]) for k in (set(old_map) - set(new_map)))
    by_kind = _merge_count_delta(
        _counts_by(old_rels, lambda r: r.get("type")),
        _counts_by(new_rels, lambda r: r.get("type")),
    )
    return {
        "old_count": len(old_rels),
        "new_count": len(new_rels),
        "by_kind": by_kind,
        "added": added,
        "removed": removed,
    }


def _diff_findings(old: dict, new: dict) -> dict:
    old_list = old.get("findings", []) or []
    new_list = new.get("findings", []) or []
    old_map = _index_by(old_list, lambda f: f.get("id"))
    new_map = _index_by(new_list, lambda f: f.get("id"))
    new_ids = sorted(set(new_map) - set(old_map))
    resolved_ids = sorted(set(old_map) - set(new_map))
    changed: list[dict] = []
    for fid in sorted(set(old_map) & set(new_map)):
        o = old_map[fid]
        n = new_map[fid]
        entry: dict[str, Any] = {"id": fid, "kind": n.get("kind")}
        moved = False
        if o.get("rank_score") != n.get("rank_score"):
            entry["rank_score"] = {"old": o.get("rank_score"), "new": n.get("rank_score")}
            moved = True
        if o.get("verification_status") != n.get("verification_status"):
            entry["verification_status"] = {
                "old": o.get("verification_status"),
                "new": n.get("verification_status"),
            }
            moved = True
        if moved:
            changed.append(entry)
    by_kind = _merge_count_delta(
        _counts_by(old_list, lambda f: f.get("kind")),
        _counts_by(new_list, lambda f: f.get("kind")),
    )
    return {
        "old_count": len(old_list),
        "new_count": len(new_list),
        "by_kind": by_kind,
        "new": [{"id": fid, "kind": new_map[fid].get("kind")} for fid in new_ids],
        "resolved": [
            {"id": fid, "kind": old_map[fid].get("kind")} for fid in resolved_ids
        ],
        "changed": changed,
    }


def _diff_coverage(old: dict, new: dict) -> dict:
    old_cov = old.get("coverage") or {}
    new_cov = new.get("coverage") or {}
    old_sum = old_cov.get("summary") or {}
    new_sum = new_cov.get("summary") or {}
    summary_delta: dict[str, dict[str, int]] = {}
    for disp in sorted(set(old_sum) | set(new_sum)):
        o = old_sum.get(disp, 0)
        n = new_sum.get(disp, 0)
        if o != n:
            summary_delta[disp] = {"old": o, "new": n}
    return {
        "total": {"old": old_cov.get("total"), "new": new_cov.get("total")},
        "parsed": {"old": old_cov.get("parsed"), "new": new_cov.get("parsed")},
        "summary": summary_delta,
    }


def _diff_inventory(old: dict, new: dict) -> dict:
    old_inv = (old.get("coverage") or {}).get("inventory") or {}
    new_inv = (new.get("coverage") or {}).get("inventory") or {}
    scalar: dict[str, dict] = {}
    for field in ("non_source_total", "source_gap_total", "dominant"):
        ov = old_inv.get(field)
        nv = new_inv.get(field)
        if ov != nv:
            scalar[field] = {"old": ov, "new": nv}
    old_groups = _index_by(old_inv.get("groups"), lambda g: g.get("id"))
    new_groups = _index_by(new_inv.get("groups"), lambda g: g.get("id"))
    group_delta: dict[str, dict] = {}
    for gid in sorted(set(old_groups) | set(new_groups)):
        o = old_groups.get(gid)
        n = new_groups.get(gid)
        oc = o.get("count") if o else None
        nc = n.get("count") if n else None
        if oc != nc:
            label = (n or o).get("label")
            group_delta[gid] = {"label": label, "old": oc, "new": nc}
    return {"scalars": scalar, "groups": group_delta}


def _diff_id_list(old: dict, new: dict, section: str) -> dict:
    old_list = old.get(section, []) or []
    new_list = new.get(section, []) or []
    old_map = _index_by(old_list, lambda x: x.get("id"))
    new_map = _index_by(new_list, lambda x: x.get("id"))
    return {
        "old_count": len(old_list),
        "new_count": len(new_list),
        "added": sorted(set(new_map) - set(old_map)),
        "removed": sorted(set(old_map) - set(new_map)),
    }


def _diff_entity_access(old: dict, new: dict) -> dict:
    old_list = old.get("entity_access", []) or []
    new_list = new.get("entity_access", []) or []
    old_map = _index_by(old_list, _access_key)
    new_map = _index_by(new_list, _access_key)
    return {
        "old_count": len(old_list),
        "new_count": len(new_list),
        "added": sorted(_access_label(new_map[k]) for k in (set(new_map) - set(old_map))),
        "removed": sorted(_access_label(old_map[k]) for k in (set(old_map) - set(new_map))),
    }


def _enrichment_stats(arch: dict) -> dict:
    comps = flatten_components(arch)
    comp_total = len(comps)
    comp_enriched = sum(1 for c in comps.values() if c.get("ai_enhance"))
    rels = arch.get("relationships", []) or []
    rel_total = len(rels)
    rel_enriched = sum(
        1 for r in rels if isinstance(r, dict) and r.get("ai_enhance")
    )
    return {
        "component_total": comp_total,
        "component_enriched": comp_enriched,
        "relationship_total": rel_total,
        "relationship_enriched": rel_enriched,
        "architecture_enriched": bool(arch.get("ai_enhance")),
    }


def _diff_enrichment(old: dict, new: dict) -> dict:
    return {"old": _enrichment_stats(old), "new": _enrichment_stats(new)}


def _identity(arch: dict) -> dict:
    return {
        "name": arch.get("name"),
        "analyzer_version": arch.get("analyzer_version"),
        "repository": arch.get("repository"),
        "default_branch": arch.get("default_branch"),
    }


def _section_has_changes(section: str, payload: dict) -> bool:
    """Whether a computed section payload represents a real change."""
    if section == "components":
        return bool(payload["added"] or payload["removed"] or payload["changed"])
    if section == "relationships":
        return bool(payload["added"] or payload["removed"] or payload["by_kind"])
    if section == "findings":
        return bool(payload["new"] or payload["resolved"] or payload["changed"])
    if section == "coverage":
        return bool(
            payload["summary"]
            or payload["total"]["old"] != payload["total"]["new"]
            or payload["parsed"]["old"] != payload["parsed"]["new"]
        )
    if section == "inventory":
        return bool(payload["scalars"] or payload["groups"])
    if section in ("data_entities", "capabilities", "entity_access"):
        return bool(payload["added"] or payload["removed"])
    if section == "enrichment":
        return payload["old"] != payload["new"]
    return False


def diff_projections(old: dict, new: dict) -> dict:
    """Compute the full, deterministic delta object between two projections."""
    sections = {
        "components": _diff_components(old, new),
        "relationships": _diff_relationships(old, new),
        "findings": _diff_findings(old, new),
        "coverage": _diff_coverage(old, new),
        "inventory": _diff_inventory(old, new),
        "data_entities": _diff_id_list(old, new, "data_entities"),
        "entity_access": _diff_entity_access(old, new),
        "capabilities": _diff_id_list(old, new, "capabilities"),
        "enrichment": _diff_enrichment(old, new),
    }
    changed_sections = {
        name: _section_has_changes(name, payload) for name, payload in sections.items()
    }
    return {
        "schema": "solution-explorer/projection-diff/v1",
        "identity": {"old": _identity(old), "new": _identity(new)},
        "sections": sections,
        "changed_sections": changed_sections,
        "has_changes": any(changed_sections.values()),
    }


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------


def _fmt_list(items: list[str], indent: str = "    ") -> list[str]:
    """Render a list with the text cap applied, announcing any truncation."""
    lines = [f"{indent}{item}" for item in items[:_TEXT_LIST_CAP]]
    extra = len(items) - _TEXT_LIST_CAP
    if extra > 0:
        lines.append(
            f"{indent}... and {extra} more (use --format json for the full list)"
        )
    return lines


def _signed(old: Any, new: Any) -> str:
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        delta = new - old
        sign = "+" if delta >= 0 else ""
        return f"{old} -> {new} ({sign}{delta})"
    return f"{old} -> {new}"


def render_text(diff: dict) -> str:
    old_id = diff["identity"]["old"]
    new_id = diff["identity"]["new"]
    lines: list[str] = []
    lines.append("Projection diff")
    lines.append(
        f"  old: {old_id.get('name')} (analyzer {old_id.get('analyzer_version')})"
    )
    lines.append(
        f"  new: {new_id.get('name')} (analyzer {new_id.get('analyzer_version')})"
    )
    lines.append("")

    if not diff["has_changes"]:
        lines.append(
            "No changes: the two projections are identical across all diffed sections."
        )
        return "\n".join(lines) + "\n"

    s = diff["sections"]

    # Components
    c = s["components"]
    if diff["changed_sections"]["components"]:
        lines.append(f"Components: {_signed(c['old_count'], c['new_count'])}")
        if c["added"]:
            lines.append(f"  added ({len(c['added'])}):")
            lines.extend(_fmt_list(c["added"]))
        if c["removed"]:
            lines.append(f"  removed ({len(c['removed'])}):")
            lines.extend(_fmt_list(c["removed"]))
        if c["changed"]:
            lines.append(f"  changed identity ({len(c['changed'])}):")
            for ch in c["changed"][:_TEXT_LIST_CAP]:
                fields = ", ".join(
                    f"{f}: {v['old']!r} -> {v['new']!r}" for f, v in ch["fields"].items()
                )
                lines.append(f"    {ch['id']}: {fields}")
            extra = len(c["changed"]) - _TEXT_LIST_CAP
            if extra > 0:
                lines.append(f"    ... and {extra} more (use --format json)")
        lines.append("")

    # Relationships
    r = s["relationships"]
    if diff["changed_sections"]["relationships"]:
        lines.append(f"Relationships: {_signed(r['old_count'], r['new_count'])}")
        if r["by_kind"]:
            lines.append("  by kind:")
            for kind, cnt in r["by_kind"].items():
                lines.append(f"    {kind}: {_signed(cnt['old'], cnt['new'])}")
        if r["added"]:
            lines.append(f"  added edges ({len(r['added'])}):")
            lines.extend(_fmt_list(r["added"]))
        if r["removed"]:
            lines.append(f"  removed edges ({len(r['removed'])}):")
            lines.extend(_fmt_list(r["removed"]))
        lines.append("")

    # Findings
    f = s["findings"]
    if diff["changed_sections"]["findings"]:
        lines.append(f"Findings: {_signed(f['old_count'], f['new_count'])}")
        if f["by_kind"]:
            lines.append("  by kind:")
            for kind, cnt in f["by_kind"].items():
                lines.append(f"    {kind}: {_signed(cnt['old'], cnt['new'])}")
        if f["new"]:
            lines.append(f"  new ({len(f['new'])}):")
            lines.extend(_fmt_list([f"[{x['kind']}] {x['id']}" for x in f["new"]]))
        if f["resolved"]:
            lines.append(f"  resolved ({len(f['resolved'])}):")
            lines.extend(_fmt_list([f"[{x['kind']}] {x['id']}" for x in f["resolved"]]))
        if f["changed"]:
            lines.append(f"  changed ({len(f['changed'])}):")
            for ch in f["changed"][:_TEXT_LIST_CAP]:
                parts = []
                if "rank_score" in ch:
                    parts.append(
                        f"rank {ch['rank_score']['old']} -> {ch['rank_score']['new']}"
                    )
                if "verification_status" in ch:
                    parts.append(
                        f"status {ch['verification_status']['old']}"
                        f" -> {ch['verification_status']['new']}"
                    )
                lines.append(f"    [{ch.get('kind')}] {ch['id']}: {'; '.join(parts)}")
            extra = len(f["changed"]) - _TEXT_LIST_CAP
            if extra > 0:
                lines.append(f"    ... and {extra} more (use --format json)")
        lines.append("")

    # Coverage
    cov = s["coverage"]
    if diff["changed_sections"]["coverage"]:
        lines.append("Coverage:")
        lines.append(f"  total: {_signed(cov['total']['old'], cov['total']['new'])}")
        lines.append(f"  parsed: {_signed(cov['parsed']['old'], cov['parsed']['new'])}")
        if cov["summary"]:
            lines.append("  by disposition:")
            for disp, cnt in cov["summary"].items():
                lines.append(f"    {disp}: {_signed(cnt['old'], cnt['new'])}")
        lines.append("")

    # Inventory
    inv = s["inventory"]
    if diff["changed_sections"]["inventory"]:
        lines.append("Inventory (non-source):")
        for field, cnt in inv["scalars"].items():
            lines.append(f"  {field}: {_signed(cnt['old'], cnt['new'])}")
        if inv["groups"]:
            lines.append("  groups:")
            for gid, cnt in inv["groups"].items():
                label = cnt.get("label") or gid
                lines.append(f"    {label} ({gid}): {_signed(cnt['old'], cnt['new'])}")
        lines.append("")

    # Data entities
    de = s["data_entities"]
    if diff["changed_sections"]["data_entities"]:
        lines.append(f"Data entities: {_signed(de['old_count'], de['new_count'])}")
        if de["added"]:
            lines.append(f"  added ({len(de['added'])}):")
            lines.extend(_fmt_list(de["added"]))
        if de["removed"]:
            lines.append(f"  removed ({len(de['removed'])}):")
            lines.extend(_fmt_list(de["removed"]))
        lines.append("")

    # Entity access
    ea = s["entity_access"]
    if diff["changed_sections"]["entity_access"]:
        lines.append(f"Entity access: {_signed(ea['old_count'], ea['new_count'])}")
        if ea["added"]:
            lines.append(f"  added ({len(ea['added'])}):")
            lines.extend(_fmt_list(ea["added"]))
        if ea["removed"]:
            lines.append(f"  removed ({len(ea['removed'])}):")
            lines.extend(_fmt_list(ea["removed"]))
        lines.append("")

    # Capabilities
    cap = s["capabilities"]
    if diff["changed_sections"]["capabilities"]:
        lines.append(f"Capabilities: {_signed(cap['old_count'], cap['new_count'])}")
        if cap["added"]:
            lines.append(f"  added ({len(cap['added'])}):")
            lines.extend(_fmt_list(cap["added"]))
        if cap["removed"]:
            lines.append(f"  removed ({len(cap['removed'])}):")
            lines.extend(_fmt_list(cap["removed"]))
        lines.append("")

    # Enrichment
    if diff["changed_sections"]["enrichment"]:
        eo = s["enrichment"]["old"]
        en = s["enrichment"]["new"]
        lines.append("Enrichment coverage:")
        lines.append(
            "  components enriched: "
            f"{_signed(eo['component_enriched'], en['component_enriched'])}"
            f" of {eo['component_total']} -> {en['component_total']}"
        )
        lines.append(
            "  relationships enriched: "
            f"{_signed(eo['relationship_enriched'], en['relationship_enriched'])}"
            f" of {eo['relationship_total']} -> {en['relationship_total']}"
        )
        if eo["architecture_enriched"] != en["architecture_enriched"]:
            lines.append(
                "  architecture-level: "
                f"{eo['architecture_enriched']} -> {en['architecture_enriched']}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic diff over two full solution-explorer projections (G1).",
    )
    parser.add_argument("old", help="Path to the old/blue projection JSON")
    parser.add_argument("new", help="Path to the new/green projection JSON")
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text; json is the complete machine-readable delta)",
    )
    parser.add_argument(
        "--output",
        help="Write the report to this path instead of stdout",
    )
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit 1 when the projections differ (for CI gating); default always exits 0",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        old = load_projection(args.old)
        new = load_projection(args.new)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    diff = diff_projections(old, new)

    if args.format == "json":
        rendered = json.dumps(diff, indent=2, sort_keys=True) + "\n"
    else:
        rendered = render_text(diff)

    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)

    if args.exit_code and diff["has_changes"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
