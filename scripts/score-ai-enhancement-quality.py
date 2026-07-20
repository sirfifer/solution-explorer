#!/usr/bin/env python3
"""Score AI enhancement quality for the DPEA pipeline.

Implements Phase 4a (schema validation) and Phase 4b (quantitative quality
scoring) from the DPEA pattern. Can validate individual partition result files
or a fully assembled architecture JSON.

Usage:
    # Validate a single partition result
    python3 scripts/score-ai-enhancement-quality.py --partition enhancement/result-0.json

    # Validate all partition results in a directory
    python3 scripts/score-ai-enhancement-quality.py --partitions-dir enhancement/

    # Score a fully assembled architecture JSON
    python3 scripts/score-ai-enhancement-quality.py --architecture architecture.json

    # Write machine-readable scores to a file
    python3 scripts/score-ai-enhancement-quality.py --partitions-dir enhancement/ \
        --output enhancement/quality-scores.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

# --- Valid enum values ---

VALID_ROLES = frozenset({
    "api-gateway", "auth-service", "data-store", "cache-layer",
    "queue-processor", "event-bus", "orchestrator", "worker",
    "proxy", "monitoring", "logging", "scheduler",
    "notification-service", "file-storage", "search-engine",
    "ml-pipeline", "presentation-layer", "business-logic", "data-access",
})

VALID_CRITICALITY = frozenset({"critical", "important", "supporting"})

VALID_TESTING_MATURITY = frozenset({
    "comprehensive", "adequate", "minimal", "untested",
})

VALID_IMPORTANCE = frozenset({"primary", "secondary", "internal"})

VALID_OBSERVATION_CATEGORIES = frozenset({
    "missing_relationship", "misclassified_component", "naming_issue",
    "structural_suggestion", "detection_gap", "data_quality",
})

VALID_CONFIDENCE = frozenset({"high", "medium", "low"})

# Component ai_enhance fields that are always expected
REQUIRED_COMPONENT_FIELDS = frozenset({
    "help_text", "data_handled", "criticality",
    "ai_enhanced_at", "ai_enhance_version",
})

# Component ai_enhance fields that are optional but scored
OPTIONAL_COMPONENT_FIELDS = frozenset({
    "architectural_role", "description", "testing_assessment",
    "actions_summary", "key_user_flows",
    "testing_gaps", "testing_maturity",
    "external_services_assessment", "port_assessment",
    "complexity_assessment", "tech_context",
})

# Relationship ai_enhance fields that are always expected
REQUIRED_RELATIONSHIP_FIELDS = frozenset({
    "data_flow_description", "importance", "ai_enhanced_at",
})

# Relationship ai_enhance fields that are optional
OPTIONAL_RELATIONSHIP_FIELDS = frozenset({
    "ai_discovered", "authentication_detail", "payload_examples",
    "error_handling", "sla_notes", "security_notes", "port_context",
})

# Rough ISO 8601 timestamp pattern (YYYY-MM-DDThh:mm:ssZ or with offset)
_ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
)


# --- Phase 4a: Schema validation ---

def validate_component_ai_enhance(comp_id, ai, component_data=None):
    """Validate a single component's ai_enhance block. Returns list of errors."""
    errors = []

    if not isinstance(ai, dict):
        return [f"Component '{comp_id}': ai_enhance is not a dict"]

    # Check required fields
    for field in REQUIRED_COMPONENT_FIELDS:
        if field not in ai or ai[field] is None:
            errors.append(f"Component '{comp_id}': missing required field '{field}'")

    # Validate enum values
    role = ai.get("architectural_role")
    if role is not None and role not in VALID_ROLES:
        errors.append(
            f"Component '{comp_id}': invalid architectural_role '{role}'"
        )

    crit = ai.get("criticality")
    if crit is not None and crit not in VALID_CRITICALITY:
        errors.append(
            f"Component '{comp_id}': invalid criticality '{crit}'"
        )

    maturity = ai.get("testing_maturity")
    if maturity is not None and maturity not in VALID_TESTING_MATURITY:
        errors.append(
            f"Component '{comp_id}': invalid testing_maturity '{maturity}'"
        )

    # Validate timestamp
    ts = ai.get("ai_enhanced_at")
    if ts is not None and not _ISO_TIMESTAMP_RE.match(str(ts)):
        errors.append(
            f"Component '{comp_id}': ai_enhanced_at is not a valid ISO timestamp"
        )

    # Validate version
    version = ai.get("ai_enhance_version")
    if version is not None and version != 2:
        errors.append(
            f"Component '{comp_id}': unexpected ai_enhance_version {version}"
        )

    # Check for unexpected keys
    all_valid_keys = (
        REQUIRED_COMPONENT_FIELDS | OPTIONAL_COMPONENT_FIELDS
    )
    for key in ai:
        if key not in all_valid_keys:
            errors.append(
                f"Component '{comp_id}': unexpected field '{key}'"
            )

    return errors


def validate_relationship_ai_enhance(rel_key, ai):
    """Validate a single relationship's ai_enhance block. Returns list of errors."""
    errors = []
    label = f"Relationship {rel_key[0]}->{rel_key[1]} ({rel_key[2]})"

    if not isinstance(ai, dict):
        return [f"{label}: ai_enhance is not a dict"]

    # Check required fields (ai_discovered relationships have looser requirements)
    is_discovered = ai.get("ai_discovered", False)
    required = REQUIRED_RELATIONSHIP_FIELDS
    if is_discovered:
        required = frozenset({"data_flow_description", "importance"})

    for field in required:
        if field not in ai or ai[field] is None:
            errors.append(f"{label}: missing required field '{field}'")

    # Validate enum values
    importance = ai.get("importance")
    if importance is not None and importance not in VALID_IMPORTANCE:
        errors.append(f"{label}: invalid importance '{importance}'")

    # Validate timestamp
    ts = ai.get("ai_enhanced_at")
    if ts is not None and not _ISO_TIMESTAMP_RE.match(str(ts)):
        errors.append(f"{label}: ai_enhanced_at is not a valid ISO timestamp")

    # Check for unexpected keys
    all_valid_keys = (
        REQUIRED_RELATIONSHIP_FIELDS | OPTIONAL_RELATIONSHIP_FIELDS
    )
    for key in ai:
        if key not in all_valid_keys:
            errors.append(f"{label}: unexpected field '{key}'")

    return errors


def validate_observation(obs, idx):
    """Validate a single observation entry. Returns list of errors."""
    errors = []
    label = f"Observation[{idx}]"

    if not isinstance(obs, dict):
        return [f"{label}: not a dict"]

    cat = obs.get("category")
    if cat not in VALID_OBSERVATION_CATEGORIES:
        errors.append(f"{label}: invalid category '{cat}'")

    if not obs.get("description"):
        errors.append(f"{label}: missing description")

    conf = obs.get("confidence")
    if conf not in VALID_CONFIDENCE:
        errors.append(f"{label}: invalid confidence '{conf}'")

    return errors


# --- Phase 4b: Quantitative quality scoring ---

def _count_sentences(text):
    """Rough sentence count by splitting on period-space or period-end."""
    if not text:
        return 0
    # Split on ". " and count, plus 1 if text ends with "."
    parts = [p.strip() for p in text.replace(". ", ".\n").split("\n") if p.strip()]
    return len(parts)


def score_component(comp_id, ai, component_data=None):
    """Score a single component's ai_enhance quality. Returns (score, details) dict."""
    if not isinstance(ai, dict):
        return 0.0, {"error": "ai_enhance is not a dict"}

    details = {}
    points = 0
    max_points = 0

    # Required field completeness (50% of score)
    for field in REQUIRED_COMPONENT_FIELDS:
        max_points += 10
        val = ai.get(field)
        if val is not None and val != "":
            points += 10
        else:
            details[f"missing_{field}"] = True

    # help_text length conformance (10% of score)
    max_points += 10
    help_text = ai.get("help_text", "")
    sentences = _count_sentences(help_text)
    if 3 <= sentences <= 5:
        points += 10
    elif 2 <= sentences <= 7:
        points += 5
        details["help_text_length"] = f"{sentences} sentences (target: 3-5)"
    else:
        details["help_text_length"] = f"{sentences} sentences (target: 3-5)"

    # Optional field population (context-aware, 30% of score)
    comp = component_data or {}
    applicable_optional = 0
    populated_optional = 0

    # actions_summary / key_user_flows only scored when component has actions
    if comp.get("actions"):
        applicable_optional += 2
        if ai.get("actions_summary"):
            populated_optional += 1
        if ai.get("key_user_flows"):
            populated_optional += 1

    # testing fields only scored when component has testing data
    if comp.get("testing"):
        applicable_optional += 2
        if ai.get("testing_gaps") is not None:
            populated_optional += 1
        if ai.get("testing_maturity") is not None:
            populated_optional += 1

    # external_services_assessment only scored when external_services exists
    if comp.get("external_services"):
        applicable_optional += 1
        if ai.get("external_services_assessment"):
            populated_optional += 1

    # port_assessment only scored when port exists
    if comp.get("port"):
        applicable_optional += 1
        if ai.get("port_assessment"):
            populated_optional += 1

    # complexity_assessment only scored for large components
    metrics = comp.get("metrics", {})
    if metrics.get("lines", 0) > 5000 or metrics.get("files", 0) > 20:
        applicable_optional += 1
        if ai.get("complexity_assessment"):
            populated_optional += 1

    # tech_context scored when language/framework are set
    if comp.get("language") or comp.get("framework"):
        applicable_optional += 1
        if ai.get("tech_context"):
            populated_optional += 1

    # architectural_role always counts
    applicable_optional += 1
    if ai.get("architectural_role"):
        populated_optional += 1

    if applicable_optional > 0:
        max_points += 30
        opt_ratio = populated_optional / applicable_optional
        points += 30 * opt_ratio
        details["optional_populated"] = f"{populated_optional}/{applicable_optional}"

    # Criticality field exists (10% of score, already in required fields)
    # This is a bonus for having a non-null value
    max_points += 10
    if ai.get("criticality") in VALID_CRITICALITY:
        points += 10

    score = (points / max_points * 100) if max_points > 0 else 0.0
    return round(score, 1), details


def score_partition(result_data, component_data_index=None):
    """Score an entire partition result. Returns aggregate metrics."""
    component_data_index = component_data_index or {}

    component_scores = []
    for comp_id, ai in result_data.get("components", {}).items():
        comp_data = component_data_index.get(comp_id, {})
        sc, det = score_component(comp_id, ai, comp_data)
        component_scores.append({
            "component_id": comp_id,
            "score": sc,
            "details": det,
        })

    rel_count = 0
    rel_valid = 0
    for rel_key_str, ai in result_data.get("relationships", {}).items():
        rel_count += 1
        parts = rel_key_str.split("|")
        if len(parts) == 3:
            errs = validate_relationship_ai_enhance(tuple(parts), ai)
            if not errs:
                rel_valid += 1

    avg_score = (
        sum(cs["score"] for cs in component_scores) / len(component_scores)
        if component_scores else 0.0
    )

    # Criticality distribution check
    crits = [
        result_data.get("components", {}).get(cs["component_id"], {}).get("criticality")
        for cs in component_scores
    ]
    crit_dist = {}
    for c in crits:
        if c:
            crit_dist[c] = crit_dist.get(c, 0) + 1

    return {
        "component_count": len(component_scores),
        "component_scores": component_scores,
        "average_score": round(avg_score, 1),
        "relationship_count": rel_count,
        "relationship_valid": rel_valid,
        "criticality_distribution": crit_dist,
        "below_threshold": [
            cs for cs in component_scores if cs["score"] < 85
        ],
    }


# --- Full architecture scoring ---

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


def score_architecture(arch):
    """Score a fully assembled architecture JSON. Returns full report."""
    comp_index = _build_component_index(arch.get("components", []))

    errors = []
    component_scores = []
    missing_ai = []

    for comp_id, comp in comp_index.items():
        ai = comp.get("ai_enhance")
        if not ai:
            missing_ai.append(comp_id)
            continue
        errs = validate_component_ai_enhance(comp_id, ai, comp)
        errors.extend(errs)
        sc, det = score_component(comp_id, ai, comp)
        component_scores.append({
            "component_id": comp_id,
            "score": sc,
            "details": det,
        })

    # Relationship validation
    rel_errors = []
    rel_scores = 0
    total_rels = 0
    for rel in arch.get("relationships", []):
        ai = rel.get("ai_enhance")
        if not ai:
            continue
        total_rels += 1
        key = (rel.get("source", ""), rel.get("target", ""), rel.get("type", ""))
        errs = validate_relationship_ai_enhance(key, ai)
        rel_errors.extend(errs)
        if not errs:
            rel_scores += 1
    errors.extend(rel_errors)

    # Root-level validation
    root_ai = arch.get("ai_enhance", {})
    if not root_ai:
        errors.append("Missing root-level ai_enhance")
    else:
        for field in ("summary", "data_flow_narrative", "ai_enhanced_at", "ai_enhance_version"):
            if not root_ai.get(field):
                errors.append(f"Root ai_enhance: missing '{field}'")
        for obs_idx, obs in enumerate(root_ai.get("observations", [])):
            errors.extend(validate_observation(obs, obs_idx))

    # Criticality distribution
    crit_dist = {}
    for cs in component_scores:
        comp = comp_index.get(cs["component_id"], {})
        c = comp.get("ai_enhance", {}).get("criticality")
        if c:
            crit_dist[c] = crit_dist.get(c, 0) + 1

    # Role distribution
    role_dist = {}
    for comp in comp_index.values():
        role = comp.get("ai_enhance", {}).get("architectural_role")
        if role:
            role_dist[role] = role_dist.get(role, 0) + 1

    avg_score = (
        sum(cs["score"] for cs in component_scores) / len(component_scores)
        if component_scores else 0.0
    )

    total_components = len(comp_index)
    enhanced_components = total_components - len(missing_ai)
    coverage = (enhanced_components / total_components * 100) if total_components else 0.0

    return {
        "total_components": total_components,
        "enhanced_components": enhanced_components,
        "coverage_pct": round(coverage, 1),
        "missing_ai_enhance": missing_ai,
        "average_score": round(avg_score, 1),
        "component_scores": component_scores,
        "below_threshold": [
            cs for cs in component_scores if cs["score"] < 85
        ],
        "total_relationships": len(arch.get("relationships", [])),
        "enhanced_relationships": total_rels,
        "valid_relationships": rel_scores,
        "criticality_distribution": crit_dist,
        "role_distribution": role_dist,
        "validation_errors": errors,
        "pass": len(errors) == 0 and coverage >= 100 and avg_score >= 85,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Score AI enhancement quality for the DPEA pipeline."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--partition",
        help="Path to a single partition result JSON file",
    )
    group.add_argument(
        "--partitions-dir",
        help="Path to directory containing result-*.json files",
    )
    group.add_argument(
        "--architecture",
        help="Path to a fully assembled architecture.json",
    )
    parser.add_argument(
        "--output",
        help="Write machine-readable scores to this JSON file",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=85.0,
        help="Minimum average quality score to pass (default: 85.0)",
    )
    args = parser.parse_args()

    report = None

    if args.architecture:
        path = Path(args.architecture)
        if not path.is_file():
            print(f"File not found: {path}", file=sys.stderr)
            sys.exit(2)
        with open(path, "r", encoding="utf-8") as f:
            arch = json.load(f)
        report = score_architecture(arch)

        print("=" * 60)
        print("AI Enhancement Quality Report")
        print("=" * 60)
        print(f"Components:    {report['enhanced_components']}/{report['total_components']} enhanced ({report['coverage_pct']}%)")
        print(f"Avg score:     {report['average_score']}%")
        print(f"Relationships: {report['valid_relationships']}/{report['enhanced_relationships']} valid")
        print(f"Criticality:   {report['criticality_distribution']}")
        print(f"Roles:         {report['role_distribution']}")

        if report["missing_ai_enhance"]:
            print(f"\nMissing ai_enhance ({len(report['missing_ai_enhance'])}):")
            for cid in sorted(report["missing_ai_enhance"]):
                print(f"  - {cid}")

        if report["below_threshold"]:
            print(f"\nBelow {args.threshold}% threshold ({len(report['below_threshold'])}):")
            for cs in sorted(report["below_threshold"], key=lambda x: x["score"]):
                print(f"  {cs['component_id']}: {cs['score']}% {cs['details']}")

        if report["validation_errors"]:
            print(f"\nValidation errors ({len(report['validation_errors'])}):")
            for err in report["validation_errors"]:
                print(f"  {err}")

        passed = report["pass"] and report["average_score"] >= args.threshold
        print(f"\n{'PASS' if passed else 'FAIL'}")

    elif args.partition:
        path = Path(args.partition)
        if not path.is_file():
            print(f"File not found: {path}", file=sys.stderr)
            sys.exit(2)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        errors = []
        for comp_id, ai in data.get("components", {}).items():
            errors.extend(validate_component_ai_enhance(comp_id, ai))
        for rel_key_str, ai in data.get("relationships", {}).items():
            parts = rel_key_str.split("|")
            if len(parts) == 3:
                errors.extend(validate_relationship_ai_enhance(tuple(parts), ai))

        result = score_partition(data)
        passed = not errors and result["average_score"] >= args.threshold
        report = {"partition": str(path), "errors": errors, "pass": passed, **result}

        print(f"Partition: {path.name}")
        print(f"  Components: {result['component_count']}, avg score: {result['average_score']}%")
        print(f"  Relationships: {result['relationship_valid']}/{result['relationship_count']} valid")
        if errors:
            print(f"  Errors ({len(errors)}):")
            for err in errors:
                print(f"    {err}")
        print(f"  {'PASS' if passed else 'FAIL'}")

    elif args.partitions_dir:
        pdir = Path(args.partitions_dir)
        if not pdir.is_dir():
            print(f"Directory not found: {pdir}", file=sys.stderr)
            sys.exit(2)

        results = []
        all_passed = True
        for rfile in sorted(pdir.glob("result-*.json")):
            with open(rfile, "r", encoding="utf-8") as f:
                data = json.load(f)
            errors = []
            for comp_id, ai in data.get("components", {}).items():
                errors.extend(validate_component_ai_enhance(comp_id, ai))
            for rel_key_str, ai in data.get("relationships", {}).items():
                parts = rel_key_str.split("|")
                if len(parts) == 3:
                    errors.extend(validate_relationship_ai_enhance(tuple(parts), ai))

            result = score_partition(data)
            passed = not errors and result["average_score"] >= args.threshold
            if not passed:
                all_passed = False
            results.append({
                "partition": rfile.name,
                "errors": errors,
                "passed": passed,
                **result,
            })

            status = "PASS" if passed else "FAIL"
            print(
                f"{rfile.name}: {result['component_count']} comps, "
                f"avg {result['average_score']}%, "
                f"{len(errors)} errors -> {status}"
            )

        report = {"partitions": results, "all_passed": all_passed}
        print(f"\nOverall: {'ALL PASSED' if all_passed else 'FAILURES DETECTED'}")

    if args.output and report:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nScores written to {out_path}")

    if report:
        passed = report.get("pass", report.get("all_passed", True))
        sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
