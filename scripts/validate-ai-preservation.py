#!/usr/bin/env python3
"""Validate that AI enhancement data is preserved through the merge pipeline.

Compares a result architecture.json against a known-good baseline to ensure
that ai_enhance data on unchanged components and relationships is identical.

Usage:
    python3 scripts/validate-ai-preservation.py \
        --baseline tests/e2e/baseline-architecture.json \
        --result /tmp/se-e2e/merged.json \
        --changed-components "comp/a,comp/b"
"""

import argparse
import json
import sys
from pathlib import Path

# Fields within ai_enhance that are timestamps (expected to differ between runs)
_TIMESTAMP_FIELDS = {"ai_enhanced_at"}


def _build_component_index(components, index=None):
    """Recursively build {id: component} mapping."""
    if index is None:
        index = {}
    for comp in components:
        comp_id = comp.get("id", "")
        if comp_id:
            index[comp_id] = comp
        _build_component_index(comp.get("children", []), index)
    return index


def _make_rel_key(rel):
    """Create a matching key for a relationship."""
    return (rel.get("source", ""), rel.get("target", ""), rel.get("type", ""))


def _compare_ai_enhance(baseline_ai, result_ai, context):
    """Compare two ai_enhance dicts field by field. Returns list of difference strings."""
    diffs = []
    all_keys = sorted(set(list(baseline_ai.keys()) + list(result_ai.keys())))
    for key in all_keys:
        if key in _TIMESTAMP_FIELDS:
            continue
        b_val = baseline_ai.get(key)
        r_val = result_ai.get(key)
        if b_val != r_val:
            # Truncate long values for readability
            b_repr = repr(b_val)[:120]
            r_repr = repr(r_val)[:120]
            diffs.append(f"  {context}.ai_enhance.{key}: baseline={b_repr}, result={r_repr}")
    return diffs


def validate(baseline_path, result_path, changed_ids):
    """Run all validation checks. Returns (errors, warnings) lists."""
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)
    with open(result_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    errors = []
    warnings = []

    # --- Component validation ---

    b_index = _build_component_index(baseline.get("components", []))
    r_index = _build_component_index(result.get("components", []))

    b_ids = set(b_index.keys())
    r_ids = set(r_index.keys())

    lost = b_ids - r_ids
    added = r_ids - b_ids

    if lost:
        errors.append(f"LOST {len(lost)} components: {sorted(lost)}")
    if added:
        warnings.append(f"ADDED {len(added)} new components: {sorted(added)}")

    # Check ai_enhance on unchanged components
    unchanged_ids = sorted((b_ids & r_ids) - set(changed_ids))
    comp_ai_ok = 0
    comp_ai_mismatches = 0

    for comp_id in unchanged_ids:
        b_ai = b_index[comp_id].get("ai_enhance", {})
        r_ai = r_index[comp_id].get("ai_enhance", {})

        if b_ai and not r_ai:
            errors.append(f"Component '{comp_id}': ai_enhance LOST entirely")
            comp_ai_mismatches += 1
        elif b_ai:
            diffs = _compare_ai_enhance(b_ai, r_ai, f"component[{comp_id}]")
            if diffs:
                errors.append(f"Component '{comp_id}': ai_enhance DIFFERS:")
                errors.extend(diffs)
                comp_ai_mismatches += 1
            else:
                comp_ai_ok += 1
        else:
            # Neither has ai_enhance, that's fine
            comp_ai_ok += 1

    # Check changed components exist
    for comp_id in changed_ids:
        if comp_id not in r_index:
            errors.append(f"Changed component '{comp_id}' not found in result")
        elif comp_id in b_index:
            b_metrics = b_index[comp_id].get("metrics", {})
            r_metrics = r_index[comp_id].get("metrics", {})
            if b_metrics == r_metrics:
                warnings.append(
                    f"Changed component '{comp_id}': metrics unchanged "
                    f"(change may not have been detected)"
                )

    # --- Relationship validation ---

    b_rels = {}
    for rel in baseline.get("relationships", []):
        b_rels[_make_rel_key(rel)] = rel

    r_rels = {}
    for rel in result.get("relationships", []):
        r_rels[_make_rel_key(rel)] = rel

    lost_rels = set(b_rels.keys()) - set(r_rels.keys())
    added_rels = set(r_rels.keys()) - set(b_rels.keys())

    for key in sorted(lost_rels):
        b_rel = b_rels[key]
        if b_rel.get("ai_enhance", {}).get("ai_discovered"):
            warnings.append(
                f"AI-discovered relationship lost (expected on fresh scan): "
                f"{key[0]} -> {key[1]} ({key[2]})"
            )
        else:
            errors.append(f"Relationship LOST: {key[0]} -> {key[1]} ({key[2]})")

    if added_rels:
        warnings.append(f"ADDED {len(added_rels)} new relationships")

    common_rels = sorted(set(b_rels.keys()) & set(r_rels.keys()))
    rel_ai_ok = 0
    rel_ai_mismatches = 0

    for key in common_rels:
        b_ai = b_rels[key].get("ai_enhance", {})
        r_ai = r_rels[key].get("ai_enhance", {})

        if b_ai and not r_ai:
            errors.append(f"Relationship {key[0]}->{key[1]}: ai_enhance LOST")
            rel_ai_mismatches += 1
        elif b_ai:
            diffs = _compare_ai_enhance(b_ai, r_ai, f"rel[{key[0]}->{key[1]}]")
            if diffs:
                errors.append(f"Relationship {key[0]}->{key[1]}: ai_enhance DIFFERS:")
                errors.extend(diffs)
                rel_ai_mismatches += 1
            else:
                rel_ai_ok += 1
        else:
            rel_ai_ok += 1

    # --- Root-level ai_enhance ---

    b_root_ai = baseline.get("ai_enhance", {})
    r_root_ai = result.get("ai_enhance", {})

    if b_root_ai and not r_root_ai:
        errors.append("Root-level ai_enhance LOST entirely")
    elif b_root_ai:
        diffs = _compare_ai_enhance(b_root_ai, r_root_ai, "root")
        if diffs:
            errors.append("Root-level ai_enhance DIFFERS:")
            errors.extend(diffs)

    return errors, warnings, {
        "baseline_components": len(b_ids),
        "result_components": len(r_ids),
        "unchanged_checked": len(unchanged_ids),
        "comp_ai_ok": comp_ai_ok,
        "comp_ai_mismatches": comp_ai_mismatches,
        "baseline_relationships": len(b_rels),
        "result_relationships": len(r_rels),
        "common_relationships": len(common_rels),
        "rel_ai_ok": rel_ai_ok,
        "rel_ai_mismatches": rel_ai_mismatches,
        "changed_ids": changed_ids,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Validate AI enhancement preservation through the merge pipeline."
    )
    parser.add_argument(
        "--baseline",
        required=True,
        help="Path to the known-good fully enhanced architecture.json",
    )
    parser.add_argument(
        "--result",
        required=True,
        help="Path to the merged result architecture.json",
    )
    parser.add_argument(
        "--changed-components",
        default="",
        help="Comma-separated list of component IDs expected to change",
    )
    args = parser.parse_args()

    baseline_path = Path(args.baseline)
    result_path = Path(args.result)

    if not baseline_path.is_file():
        print(f"Baseline not found: {baseline_path}", file=sys.stderr)
        sys.exit(2)
    if not result_path.is_file():
        print(f"Result not found: {result_path}", file=sys.stderr)
        sys.exit(2)

    changed = [c.strip() for c in args.changed_components.split(",") if c.strip()]
    errors, warnings, stats = validate(baseline_path, result_path, changed)

    print("=" * 60)
    print("AI Enhancement Preservation Validation")
    print("=" * 60)
    print(f"Baseline components:  {stats['baseline_components']}")
    print(f"Result components:    {stats['result_components']}")
    print(f"Unchanged checked:    {stats['unchanged_checked']}")
    print(f"Expected changes:     {stats['changed_ids'] or 'none'}")
    print(f"Baseline rels:        {stats['baseline_relationships']}")
    print(f"Result rels:          {stats['result_relationships']}")
    print()

    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠ {w}")
        print()

    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  ✗ {e}")
        print()
        print("VALIDATION FAILED")
        print(
            f"  Components: {stats['comp_ai_ok']} ok, "
            f"{stats['comp_ai_mismatches']} mismatches"
        )
        print(
            f"  Relationships: {stats['rel_ai_ok']} ok, "
            f"{stats['rel_ai_mismatches']} mismatches"
        )
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        print(
            f"  {stats['comp_ai_ok']} unchanged components: "
            f"ai_enhance preserved"
        )
        print(
            f"  {stats['rel_ai_ok']} common relationships: "
            f"ai_enhance preserved"
        )
        print("  Root-level ai_enhance: preserved")
        sys.exit(0)


if __name__ == "__main__":
    main()
