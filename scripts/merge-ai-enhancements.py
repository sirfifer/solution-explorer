#!/usr/bin/env python3
"""Merge AI enhancements from a baseline architecture.json into a freshly analyzed one.

The static analyzer does not produce ai_enhance data (it lives outside the
Python model). When the analyzer runs in CI, it outputs clean JSON without
any AI enhancements. This script restores ai_enhance data from a previous
baseline so that human-curated AI work is not lost on every push.

Usage:
    python3 scripts/merge-ai-enhancements.py \
        --baseline .arch-baseline/architecture.json \
        --target .arch-output/architecture.json

The target file is modified in-place.
"""

import argparse
import json
import sys
from pathlib import Path


def _build_component_index(components, index=None):
    """Recursively build a dict mapping component ID to component dict."""
    if index is None:
        index = {}
    for comp in components:
        comp_id = comp.get("id", "")
        if comp_id:
            index[comp_id] = comp
        _build_component_index(comp.get("children", []), index)
    return index


def _merge_component_ai(target_components, baseline_index, stats):
    """Recursively copy ai_enhance from baseline onto matching target components."""
    for comp in target_components:
        comp_id = comp.get("id", "")
        baseline_comp = baseline_index.get(comp_id)
        if baseline_comp and "ai_enhance" in baseline_comp:
            comp["ai_enhance"] = baseline_comp["ai_enhance"]
            stats["preserved"] += 1
        else:
            stats["missing"] += 1
        stats["total"] += 1
        _merge_component_ai(comp.get("children", []), baseline_index, stats)


def _make_rel_key(rel):
    """Create a matching key for a relationship."""
    return (rel.get("source", ""), rel.get("target", ""), rel.get("type", ""))


def merge(baseline, target):
    """Merge ai_enhance data from baseline into target dict. Modifies target in-place."""
    # Component-level merge
    baseline_index = _build_component_index(baseline.get("components", []))
    comp_stats = {"preserved": 0, "missing": 0, "total": 0}
    _merge_component_ai(target.get("components", []), baseline_index, comp_stats)

    # Relationship-level merge
    baseline_rels = {}
    for rel in baseline.get("relationships", []):
        if "ai_enhance" in rel:
            baseline_rels[_make_rel_key(rel)] = rel["ai_enhance"]

    rel_stats = {"preserved": 0, "total": 0, "ai_discovered_carried": 0}
    target_rel_keys = set()
    for rel in target.get("relationships", []):
        key = _make_rel_key(rel)
        target_rel_keys.add(key)
        if key in baseline_rels:
            rel["ai_enhance"] = baseline_rels[key]
            rel_stats["preserved"] += 1
        rel_stats["total"] += 1

    # Forward-carry AI-discovered relationships from baseline.
    # These only exist in the baseline (the static analyzer does not produce them),
    # so they would be silently dropped without this step.
    for rel in baseline.get("relationships", []):
        ai = rel.get("ai_enhance", {})
        if not ai.get("ai_discovered"):
            continue
        key = _make_rel_key(rel)
        if key not in target_rel_keys:
            target.setdefault("relationships", []).append(rel)
            target_rel_keys.add(key)
            rel_stats["ai_discovered_carried"] += 1
            rel_stats["total"] += 1

    # Architecture-level merge
    if "ai_enhance" in baseline:
        target["ai_enhance"] = baseline["ai_enhance"]

    return comp_stats, rel_stats


def main():
    parser = argparse.ArgumentParser(
        description="Merge AI enhancements from baseline into freshly analyzed architecture JSON."
    )
    parser.add_argument(
        "--baseline",
        required=True,
        help="Path to previous architecture.json containing ai_enhance data",
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Path to freshly analyzed architecture.json (modified in-place)",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    target_path = Path(args.target)

    if not baseline_path.is_file():
        print(f"Baseline not found: {baseline_path}, skipping merge")
        return

    if not target_path.is_file():
        print(f"Target not found: {target_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(baseline_path, "r", encoding="utf-8") as f:
            baseline = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Could not read baseline: {exc}", file=sys.stderr)
        sys.exit(1)

    # Check if baseline has any ai_enhance data worth merging
    has_ai = "ai_enhance" in baseline
    if not has_ai:
        baseline_index = _build_component_index(baseline.get("components", []))
        has_ai = any("ai_enhance" in c for c in baseline_index.values())
    if not has_ai:
        has_ai = any("ai_enhance" in r for r in baseline.get("relationships", []))

    if not has_ai:
        print("No ai_enhance data in baseline, nothing to merge")
        return

    with open(target_path, "r", encoding="utf-8") as f:
        target = json.load(f)

    comp_stats, rel_stats = merge(baseline, target)

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(target, f, indent=None, ensure_ascii=False)

    carried = rel_stats['ai_discovered_carried']
    carried_msg = f" {carried} AI-discovered relationships carried forward." if carried else ""
    print(
        f"AI enhancement merge: "
        f"{comp_stats['preserved']}/{comp_stats['total']} components, "
        f"{rel_stats['preserved']}/{rel_stats['total']} relationships preserved."
        f"{carried_msg} "
        f"{comp_stats['missing']} components without ai_enhance."
    )


if __name__ == "__main__":
    main()
