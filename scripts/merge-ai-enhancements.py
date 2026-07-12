#!/usr/bin/env python3
"""Merge AI enhancements from a baseline architecture.json into a freshly analyzed one.

The static analyzer does not produce ai_enhance data (it lives outside the
Python model). When the analyzer runs in CI, it outputs clean JSON without
any AI enhancements. This script restores ai_enhance data from a previous
baseline so that human-curated AI work is not lost on every push.

Component IDs drift between analyzer runs. The most common cause is a repo
prefix being added or removed (baseline ``curriculum`` versus target
``unamentis/curriculum``), which happens whenever a repo starts or stops being
analyzed under a multi-repo config. Exact-ID matching alone would drop every
enhancement in that scenario. This script therefore falls back, in order, to:

    1. exact ID match
    2. component ``path`` match (the ID changed but the file path did not)
    3. prefix/suffix match (a baseline ID or path is an unambiguous suffix of
       exactly one target ID or path, the repo-prefix-added pattern)
    4. (name, type) match as a last resort

Every fallback requires a UNIQUE target. Ambiguous candidates are never
guessed; they are left unmatched and reported. Relationships are matched by
(source, target, type) resolved through the same component mapping.

Usage:
    python3 scripts/merge-ai-enhancements.py \
        --baseline .arch-baseline/architecture.json \
        --target .arch-output/architecture.json \
        [--strict] [--strict-threshold 0.90]

The target file is modified in-place. With --strict, the script exits nonzero
(leaving the target untouched) when the fraction of still-present baseline
enhancements that survived the merge falls below the threshold.
"""

import argparse
import json
import sys
from pathlib import Path

DEFAULT_STRICT_THRESHOLD = 0.90


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


def _flatten_components(components, out=None):
    """Recursively collect every component dict into a flat list."""
    if out is None:
        out = []
    for comp in components:
        out.append(comp)
        _flatten_components(comp.get("children", []), out)
    return out


def _is_suffix(base_key, full_key):
    """True if base_key is a strict path-segment suffix of full_key.

    Matches the repo-prefix-added pattern: baseline ``curriculum`` is a suffix
    of target ``unamentis/curriculum`` because the latter ends with
    ``/curriculum``. The separator boundary prevents ``curriculum`` from
    matching ``mycurriculum``. Exact equality is intentionally excluded here;
    that case is handled by the exact-ID and path strategies.
    """
    if not base_key or not full_key or base_key == full_key:
        return False
    return full_key.endswith("/" + base_key)


def _match_components(baseline_ai_comps, target_comps):
    """Match baseline AI-enhanced components onto target components.

    Returns (matches, counts, id_map) where:
      - matches: list of (baseline_comp, target_comp, strategy)
      - counts: per-strategy tallies plus removed/ambiguous classification
      - id_map: {baseline_id -> target_id} for every matched pair, used to
        translate relationship endpoints.

    Strategies run as ordered waves so that a stronger match (exact ID) always
    claims a target before a weaker one (suffix, name+type) can. Each target is
    claimed at most once. Ambiguity (more than one eligible target) is never
    resolved by guessing.
    """
    claimed = set()  # id() of target dicts already assigned
    matches = []
    id_map = {}

    # Target indexes for fast candidate lookup.
    by_id = {}
    by_path = {}
    by_name_type = {}
    for t in target_comps:
        tid = t.get("id", "")
        if tid:
            by_id.setdefault(tid, []).append(t)
        tpath = t.get("path", "")
        if tpath:
            by_path.setdefault(tpath, []).append(t)
        tname = t.get("name", "")
        if tname:
            by_name_type.setdefault((tname, t.get("type")), []).append(t)

    def unclaimed(cands):
        return [t for t in cands if id(t) not in claimed]

    def commit(bcomp, tcomp, strategy):
        claimed.add(id(tcomp))
        matches.append((bcomp, tcomp, strategy))
        bid = bcomp.get("id", "")
        tid = tcomp.get("id", "")
        if bid and tid:
            id_map[bid] = tid

    pending = list(baseline_ai_comps)

    # Wave 1: exact ID.
    remaining = []
    for b in pending:
        cands = unclaimed(by_id.get(b.get("id", ""), []))
        if len(cands) == 1:
            commit(b, cands[0], "exact")
        else:
            remaining.append(b)
    pending = remaining

    # Wave 2: path match.
    remaining = []
    for b in pending:
        bpath = b.get("path", "")
        cands = unclaimed(by_path.get(bpath, [])) if bpath else []
        if len(cands) == 1:
            commit(b, cands[0], "path")
        else:
            remaining.append(b)
    pending = remaining

    # Wave 3: prefix/suffix (repo-prefix-added). A baseline ID or path that is
    # an unambiguous suffix of exactly one unclaimed target ID or path.
    remaining = []
    for b in pending:
        bid = b.get("id", "")
        bpath = b.get("path", "")
        cand_ids = {}
        for t in target_comps:
            if id(t) in claimed:
                continue
            tid = t.get("id", "")
            tpath = t.get("path", "")
            if _is_suffix(bid, tid) or (bpath and _is_suffix(bpath, tpath)):
                cand_ids[id(t)] = t
        cands = list(cand_ids.values())
        if len(cands) == 1:
            commit(b, cands[0], "prefix_suffix")
        else:
            remaining.append(b)
    pending = remaining

    # Wave 4: (name, type) last resort.
    remaining = []
    for b in pending:
        bname = b.get("name", "")
        cands = unclaimed(by_name_type.get((bname, b.get("type")), [])) if bname else []
        if len(cands) == 1:
            commit(b, cands[0], "name_type")
        else:
            remaining.append(b)
    pending = remaining

    # Classify the still-unmatched baseline components. A "removed" component
    # has NO candidate in the target under any strategy (it was genuinely
    # deleted); it must not count against the preservation ratio. An
    # "ambiguous" component had candidates but none could be claimed uniquely;
    # that is unresolved drift and DOES count against the ratio.
    def had_any_candidate(b):
        bid = b.get("id", "")
        bpath = b.get("path", "")
        bname = b.get("name", "")
        if bid and by_id.get(bid):
            return True
        if bpath and by_path.get(bpath):
            return True
        if bname and by_name_type.get((bname, b.get("type"))):
            return True
        for t in target_comps:
            tid = t.get("id", "")
            tpath = t.get("path", "")
            if _is_suffix(bid, tid) or (bpath and _is_suffix(bpath, tpath)):
                return True
        return False

    removed = []
    ambiguous = []
    for b in pending:
        if had_any_candidate(b):
            ambiguous.append(b)
        else:
            removed.append(b)

    counts = {
        "total_baseline_ai": len(baseline_ai_comps),
        "exact": sum(1 for _, _, s in matches if s == "exact"),
        "path": sum(1 for _, _, s in matches if s == "path"),
        "prefix_suffix": sum(1 for _, _, s in matches if s == "prefix_suffix"),
        "name_type": sum(1 for _, _, s in matches if s == "name_type"),
        "preserved": len(matches),
        "removed": len(removed),
        "ambiguous_unmatched": len(ambiguous),
        "ambiguous_ids": sorted(b.get("id", "") for b in ambiguous),
    }
    return matches, counts, id_map


def _make_rel_key(rel):
    """Create a matching key for a relationship."""
    return (rel.get("source", ""), rel.get("target", ""), rel.get("type", ""))


def merge(baseline, target):
    """Merge ai_enhance data from baseline into target dict. Modifies target in-place.

    Returns (comp_counts, rel_stats).
    """
    # Component-level merge with drift-tolerant matching.
    baseline_comps = _flatten_components(baseline.get("components", []))
    baseline_ai_comps = [c for c in baseline_comps if "ai_enhance" in c]
    target_comps = _flatten_components(target.get("components", []))

    matches, comp_counts, id_map = _match_components(baseline_ai_comps, target_comps)
    for bcomp, tcomp, _strategy in matches:
        tcomp["ai_enhance"] = bcomp["ai_enhance"]

    # Relationship-level merge. Baseline relationship endpoints are baseline
    # component IDs; translate them through id_map into the target ID space so
    # drifted-but-matched components still line up. Both the translated key and
    # the original key are accepted so an undrifted repo keeps matching.
    baseline_rel_ai = {}
    for rel in baseline.get("relationships", []):
        if "ai_enhance" not in rel:
            continue
        src = rel.get("source", "")
        tgt = rel.get("target", "")
        typ = rel.get("type", "")
        baseline_rel_ai.setdefault((src, tgt, typ), rel["ai_enhance"])
        t_src = id_map.get(src, src)
        t_tgt = id_map.get(tgt, tgt)
        baseline_rel_ai.setdefault((t_src, t_tgt, typ), rel["ai_enhance"])

    rel_stats = {"preserved": 0, "total": 0, "ai_discovered_carried": 0}
    target_rel_keys = set()
    for rel in target.get("relationships", []):
        key = _make_rel_key(rel)
        target_rel_keys.add(key)
        if key in baseline_rel_ai:
            rel["ai_enhance"] = baseline_rel_ai[key]
            rel_stats["preserved"] += 1
        rel_stats["total"] += 1

    # Forward-carry AI-discovered relationships from baseline. These only exist
    # in the baseline (the static analyzer does not produce them), so they would
    # be silently dropped without this step. Translate endpoints so they point
    # at the target component IDs.
    for rel in baseline.get("relationships", []):
        ai = rel.get("ai_enhance", {})
        if not ai.get("ai_discovered"):
            continue
        src = id_map.get(rel.get("source", ""), rel.get("source", ""))
        tgt = id_map.get(rel.get("target", ""), rel.get("target", ""))
        typ = rel.get("type", "")
        key = (src, tgt, typ)
        if key not in target_rel_keys:
            carried = dict(rel)
            carried["source"] = src
            carried["target"] = tgt
            target.setdefault("relationships", []).append(carried)
            target_rel_keys.add(key)
            rel_stats["ai_discovered_carried"] += 1
            rel_stats["total"] += 1

    # Architecture-level merge.
    if "ai_enhance" in baseline:
        target["ai_enhance"] = baseline["ai_enhance"]

    return comp_counts, rel_stats


def _preservation_ratio(comp_counts):
    """Fraction of still-present baseline enhancements that survived the merge.

    Removed components (no target counterpart at all) are excluded from the
    denominator: legitimately deleting a component must not fail the guard.
    Returns 1.0 when nothing enhanced still exists in the target.
    """
    denom = comp_counts["total_baseline_ai"] - comp_counts["removed"]
    if denom <= 0:
        return 1.0
    return comp_counts["preserved"] / denom


def _print_report(comp_counts, rel_stats):
    ratio = _preservation_ratio(comp_counts)
    carried = rel_stats["ai_discovered_carried"]
    carried_msg = (
        f" {carried} AI-discovered relationships carried forward." if carried else ""
    )
    print(
        "AI enhancement merge: "
        f"{comp_counts['preserved']}/{comp_counts['total_baseline_ai']} "
        f"enhanced components preserved ({ratio * 100:.1f}% of still-present), "
        f"{rel_stats['preserved']}/{rel_stats['total']} relationships preserved."
        f"{carried_msg}"
    )
    print(
        "  Match strategy: "
        f"exact={comp_counts['exact']}, "
        f"path={comp_counts['path']}, "
        f"prefix/suffix={comp_counts['prefix_suffix']}, "
        f"name+type={comp_counts['name_type']}, "
        f"removed={comp_counts['removed']}, "
        f"unmatched={comp_counts['ambiguous_unmatched']}."
    )
    if comp_counts["ambiguous_unmatched"]:
        print(
            "  WARNING: "
            f"{comp_counts['ambiguous_unmatched']} enhanced component(s) had "
            "ambiguous target candidates and were NOT merged (never guessed): "
            f"{comp_counts['ambiguous_ids'][:10]}",
            file=sys.stderr,
        )


def _threshold_ratio(value):
    """argparse type for --strict-threshold: a float within [0.0, 1.0]."""
    try:
        ratio = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid float value: {value!r}") from exc
    if not 0.0 <= ratio <= 1.0:
        raise argparse.ArgumentTypeError(
            f"must be a ratio between 0.0 and 1.0, got {value}"
        )
    return ratio


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
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero (leaving the target untouched) when the preservation "
        "ratio falls below --strict-threshold.",
    )
    parser.add_argument(
        "--strict-threshold",
        type=_threshold_ratio,
        default=DEFAULT_STRICT_THRESHOLD,
        help=f"Minimum fraction of still-present enhancements that must survive "
        f"under --strict (default {DEFAULT_STRICT_THRESHOLD}).",
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

    baseline_index = _build_component_index(baseline.get("components", []))
    baseline_ai_ids = sorted(cid for cid, c in baseline_index.items() if "ai_enhance" in c)

    # Check if baseline has any ai_enhance data worth merging.
    has_ai = (
        "ai_enhance" in baseline
        or bool(baseline_ai_ids)
        or any("ai_enhance" in r for r in baseline.get("relationships", []))
    )

    if not has_ai:
        print("No ai_enhance data in baseline, nothing to merge")
        return

    with open(target_path, "r", encoding="utf-8") as f:
        target = json.load(f)

    comp_counts, rel_stats = merge(baseline, target)

    # Total-loss guard (P0-4), checked BEFORE writing the target. If the
    # baseline carries AI-enhanced components but NONE matched (even with
    # drift-tolerant fallbacks), the schema drifted beyond what we can safely
    # remap. Writing now would overwrite curated AI work with AI-stripped
    # output, so fail loudly and leave the target file untouched.
    if comp_counts["preserved"] == 0 and baseline_ai_ids:
        target_index = _build_component_index(target.get("components", []))
        target_ids = sorted(target_index.keys())
        print(
            "ERROR: baseline has AI-enhanced components but NONE matched target IDs.",
            file=sys.stderr,
        )
        print(
            f"  Baseline has {len(baseline_ai_ids)} AI-enhanced component IDs; "
            f"first 5: {baseline_ai_ids[:5]}",
            file=sys.stderr,
        )
        print(
            f"  Target has {len(target_ids)} component IDs; first 5: {target_ids[:5]}",
            file=sys.stderr,
        )
        print(
            "  Fallbacks tried: exact ID, path, prefix/suffix, name+type. "
            "None produced a unique match.",
            file=sys.stderr,
        )
        print(
            "  Likely cause: component ID and path schema both changed "
            "(e.g. repo restructured, files moved).",
            file=sys.stderr,
        )
        print(
            f"  Target file left unchanged: {target_path}. No AI data was lost.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Strict preservation-ratio guard. Also checked BEFORE writing.
    ratio = _preservation_ratio(comp_counts)
    if args.strict and ratio < args.strict_threshold:
        print(
            f"ERROR: AI preservation ratio {ratio * 100:.1f}% is below the "
            f"--strict threshold of {args.strict_threshold * 100:.1f}%.",
            file=sys.stderr,
        )
        print(
            f"  Preserved {comp_counts['preserved']} of "
            f"{comp_counts['total_baseline_ai'] - comp_counts['removed']} "
            "still-present enhanced components "
            f"({comp_counts['removed']} genuinely removed, excluded).",
            file=sys.stderr,
        )
        print(
            f"  Unmatched (ambiguous drift): {comp_counts['ambiguous_unmatched']}; "
            f"first 10: {comp_counts['ambiguous_ids'][:10]}",
            file=sys.stderr,
        )
        print(
            f"  Target file left unchanged: {target_path}. No AI data was lost.",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(target, f, indent=None, ensure_ascii=False)

    _print_report(comp_counts, rel_stats)


if __name__ == "__main__":
    main()
