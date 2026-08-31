"""Compact model wire format for the enrichment ladder.

The rich completeness contract is the right *internal* record and the wrong
thing to make a model transcribe.  This module is the compatibility boundary:
models emit terse, index-based JSON and the coordinator expands it into the
canonical product + contract shape consumed by the validator, store, census,
adjudicator, and run report.

Keeping the expansion deterministic is load-bearing.  A compact response never
weakens validation: indexes resolve only against menus the prompt supplied, an
out-of-range index expands to deliberately invalid evidence, and missing targets
remain missing so the ordinary ladder rules escalate them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import PurePosixPath
from typing import Any, Optional

from .contract import CONTRACT_KEY
from .evidence import CITABLE_FACTS

COMPACT_WIRE_VERSION = "compact/v1"

# Hard delivered-response budgets.  They are deliberately expressed in UTF-8
# bytes rather than estimated tokens: bytes are deterministic across machines
# and tokenizers.
# The 8% envelope allowance is narrow enough to be a real gate while tolerating
# JSON punctuation and escaped characters around per-target budgets.
COMPONENT_RESPONSE_BYTES = 3_600
RELATIONSHIP_RESPONSE_BYTES = 720
RESPONSE_ENVELOPE_BYTES = 512
RESPONSE_BUDGET_TOLERANCE = 1.08

# Per-call target caps, shared with the ladder's chunk planner. They live
# here rather than in ladder.py because the JSON schema is bounded by them
# and compact must not import ladder. 21 is the largest component count that
# clears the G2 output arithmetic at the 1.90 dispersion default;
# relationships chunk at 80; escalation batches are far smaller than 40 and
# the cap only bounds the schema.
COMPONENT_CALL_CAP = 21
RELATIONSHIP_CALL_CAP = 80
ESCALATION_SCHEMA_CAP = 40

# Evidence is a correctness channel, not a prose-size dial. Five citations were
# observed on a healthy repair and the former four-item cap silently discarded
# the fifth before adjudication. Twelve is the largest evidence menu one compact
# component answer can reasonably need (the component edge menu itself is
# bounded at twelve); the much broader response-byte guard remains the runaway
# boundary for the complete payload.
MAX_EVIDENCE_ITEMS = 12

_PRODUCT_FIELDS = (
    "help_text", "description", "data_handled", "criticality",
    "architectural_role", "tech_context", "testing_assessment",
    "testing_maturity", "port_assessment", "complexity_assessment",
    "external_services_assessment", "actions_summary", "key_user_flows",
)


def response_budget_bytes(*, components: int = 0, relationships: int = 0) -> int:
    """Exact maximum response size for a compact call, including tolerance."""
    nominal = (
        RESPONSE_ENVELOPE_BYTES
        + max(0, int(components)) * COMPONENT_RESPONSE_BYTES
        + max(0, int(relationships)) * RELATIONSHIP_RESPONSE_BYTES
    )
    return int(nominal * RESPONSE_BUDGET_TOLERANCE)


def coverage_issues(
    obj: Any, *, component_ids: Iterable[str] = (), relationship_keys: Iterable[str] = (),
) -> dict:
    """Exact-set validation for one response envelope.

    Returned counts are deterministic and suitable for both a hard gate and the
    exit report.  Duplicate array entries are failures even when their payloads
    happen to match: last-write-wins is the waste this architecture removes.
    """
    obj = obj if isinstance(obj, dict) else {}

    def observed(raw: Any, id_key: str) -> tuple[list[str], list[str]]:
        if isinstance(raw, dict):
            values = [str(key) for key in raw]
        elif isinstance(raw, list):
            values = [
                str(item.get(id_key) or "") for item in raw if isinstance(item, dict)
            ]
        else:
            values = []
        seen = set()
        duplicates = []
        for value in values:
            if value in seen and value not in duplicates:
                duplicates.append(value)
            seen.add(value)
        return values, duplicates

    expected_c = set(component_ids)
    expected_r = set(relationship_keys)
    got_c, dup_c = observed(obj.get("components"), "i")
    got_r, dup_r = observed(obj.get("relationships"), "k")
    got_c_set, got_r_set = set(got_c), set(got_r)
    return {
        "missing_components": sorted(expected_c - got_c_set),
        "extra_components": sorted(got_c_set - expected_c),
        "duplicate_components": sorted(dup_c),
        "missing_relationships": sorted(expected_r - got_r_set),
        "extra_relationships": sorted(got_r_set - expected_r),
        "duplicate_relationships": sorted(dup_r),
    }


def _extract_payload(user: str, label: str) -> Any:
    marker = label + ":\n"
    start = user.find(marker)
    if start < 0:
        return None
    start += len(marker)
    try:
        return json.JSONDecoder().raw_decode(user[start:])[0]
    except (json.JSONDecodeError, ValueError):
        return None


def compact_json_schema(prefix: Optional[str], user: str) -> Optional[dict]:
    """A structural, length-bounded schema for a marked compact prompt.

    This constrains the delivered JSON during decoding; the coordinator still
    performs exact id-set validation because a schema cannot cheaply express a
    different enum of ids for every cacheable call.

    The schema is BYTE-CONSTANT PER RUNG, never per call. The live probe
    measured that --json-schema content participates in the cached entry: an
    identical schema preserves the 0.1x prefix read, and a schema that varies
    by even one byte forces the entire stable block back to the 2x cold-write
    rate (J-series rows in data/f9-cache-probe-2026-08-26.md). Per-call
    minItems/maxItems counts would therefore have destroyed the caching win
    on every call. Array bounds sit at the rung caps instead, and exact
    per-call counts stay with coverage_issues, which was always the
    authority: a missing or extra target is absorbed as an explicit failure,
    never trusted to the decoder.
    """
    if not prefix:
        return None
    # Claim and reason lengths cover the WHOLE measured v2 distribution
    # including its maxima (claim max 612 chars, reason max 526), because a
    # structured-output rejection forces a full regeneration to save a
    # hundred characters, which is a bad trade. The delta's 600 still cut
    # the measured maximum; the cross-session review caught the
    # inconsistency, so the bound sits above it with margin
    # (IMPLEMENTATION-DELTA-PROMPT.md section 2.4).
    answer = {
        "oneOf": [
            {"type": "string", "maxLength": 640},
            {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "t": {"type": "string", "maxLength": 640},
                    # A compact compound claim can legitimately need separate
                    # documentation, identity, file, count and edge facts. A
                    # live repair emitted five valid citations and the former
                    # four-item cap silently stripped the last one.
                    "e": {"type": "array", "maxItems": MAX_EVIDENCE_ITEMS, "items": {
                        "oneOf": [
                            {"type": "integer", "minimum": 0},
                            {"type": "string", "maxLength": 120},
                            {"type": "array", "minItems": 2, "maxItems": 2,
                             "items": {"oneOf": [
                                 {"type": "integer"},
                                 {"type": "string", "maxLength": 160},
                             ]}},
                            {
                                "type": "object", "additionalProperties": False,
                                "maxProperties": 8,
                                "properties": {
                                    "kind": {"type": "string", "maxLength": 32},
                                    "path": {"type": "string", "maxLength": 500},
                                    "symbol": {"type": "string", "maxLength": 240},
                                    "line": {"type": "integer", "minimum": 1},
                                    "source": {"type": "string", "maxLength": 500},
                                    "target": {"type": "string", "maxLength": 500},
                                    "edge_type": {"type": "string", "maxLength": 80},
                                    "component": {"type": "string", "maxLength": 500},
                                    "field": {"type": "string", "maxLength": 120},
                                    "value": {"type": "string", "maxLength": 500},
                                    "scope": {"enum": ["local", "global"]},
                                },
                            },
                        ],
                    }},
                    "s": {"enum": ["u", "d"]},
                    "r": {"type": "string", "maxLength": 560},
                    "l": {"enum": ["fact", "judgment"]},
                    "need": {"type": "string", "maxLength": 560},
                },
            },
        ]
    }
    q = {
        "type": "object", "additionalProperties": False,
        "properties": {
            name: answer for name in (
                "purpose", "mechanism", "place", "next_step",
                "why_matters", "data_handled",
            )
        },
    }
    product = {
        "help_text": {"type": "string", "maxLength": 1_600},
        "description": {"type": "string", "maxLength": 240},
        "data_handled": {"type": "string", "maxLength": 600},
        "criticality": {"enum": ["critical", "important", "supporting"]},
        "architectural_role": {"type": "string", "maxLength": 40},
        "tech_context": {"type": "string", "maxLength": 700},
        "testing_assessment": {"type": "string", "maxLength": 600},
        "testing_maturity": {"enum": ["comprehensive", "adequate", "minimal", "untested"]},
        "port_assessment": {"type": "string", "maxLength": 400},
        "complexity_assessment": {"type": "string", "maxLength": 500},
        "external_services_assessment": {"type": "string", "maxLength": 500},
        "actions_summary": {"type": "string", "maxLength": 500},
        "key_user_flows": {"type": "array", "maxItems": 5,
                           "items": {"type": "string", "maxLength": 320}},
    }
    gaps = {
        "type": "array", "maxItems": 4, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["q", "why"], "properties": {
                "q": {"type": "string", "maxLength": 40},
                "why": {"type": "string", "maxLength": 400},
            },
        },
    }
    identity_exception = {
        "type": "object", "additionalProperties": False, "maxProperties": 4,
        "properties": {
            field: {
                "type": "object", "additionalProperties": False,
                "required": ["v", "r"], "properties": {
                    "v": {"oneOf": [
                        {"type": "string", "maxLength": 160},
                        {"type": "integer"},
                    ]},
                    "r": {"type": "string", "maxLength": 240},
                    "e": {"type": "array", "maxItems": MAX_EVIDENCE_ITEMS,
                          "items": answer["oneOf"][1]["properties"]["e"]["items"]},
                },
            }
            for field in ("type", "framework", "port", "language")
        },
    }
    comp_properties = {
        "i": {"type": "string", "maxLength": 500}, **product, "q": q,
        "label": {"type": "string", "maxLength": 240},
        "purpose": answer, "mechanism": answer, "place": answer, "next": answer,
        "why_matters": answer,
        "data": answer,
        "id": identity_exception,
        "confusion": {"type": "string", "maxLength": 400},
        "generic": {"const": True},
        "pf": {"type": "array", "maxItems": 2,
               "items": {"type": "string", "maxLength": 400}},
        "gaps": gaps,
    }
    rel_properties = {
        "k": {"type": "string", "maxLength": 1_200},
        "d": {"type": "string", "maxLength": 500},
        "imp": {"enum": ["primary", "secondary", "internal"]},
        "flow": answer, "why": answer, "gaps": gaps,
    }

    if prefix.startswith("ENRICHMENT TASK: components"):
        comp_max, rel_max = COMPONENT_CALL_CAP, 0
        comp_required = [
            "i", "label", "purpose", "mechanism", "place", "next",
            "why_matters", "data", "criticality",
        ]
        rel_required = ["k"]
        # Initial component generation uses semantic atoms, never the older q
        # duplicate.  Escalations use q for delta answers.  Keeping both in one
        # schema allowed a response to satisfy the required atoms while the
        # normalizer silently preferred q, discarding the new material.
        comp_properties = {
            key: value for key, value in comp_properties.items() if key != "q"
        }
    elif prefix.startswith("ENRICHMENT TASK: relationships"):
        comp_max, rel_max = 0, RELATIONSHIP_CALL_CAP
        comp_required = ["i"]
        rel_required = ["k", "imp", "flow", "why"]
    elif prefix.startswith(("You are the LAST rung", "You are a HIGHER RUNG")):
        comp_max, rel_max = ESCALATION_SCHEMA_CAP, ESCALATION_SCHEMA_CAP
        comp_required = ["i"]
        rel_required = ["k"]
    else:
        # Cacheable is NOT the same thing as compact-schema-eligible. Any
        # phase may mark a stable prefix for the cache boundary (p5
        # determination does), and forcing the ladder schema onto such a call
        # would structurally forbid its real answer shape: a determination
        # verdict pinned to {"components":[],"relationships":[]} is a run
        # that silently cannot conclude. Found by the cross-session review;
        # the injected-invoker test suite cannot see this seam, so the
        # transport test in tests/test_enrich_compact.py pins it.
        return None

    def array_schema(properties: dict, required: list[str], cap: int) -> dict:
        return {
            "type": "array", "minItems": 0, "maxItems": cap,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": required, "properties": properties,
            },
        }

    return {
        "type": "object", "additionalProperties": False,
        "required": ["components", "relationships"],
        "properties": {
            "components": array_schema(comp_properties, comp_required, comp_max),
            "relationships": array_schema(rel_properties, rel_required, rel_max),
        },
    }


def _is_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _schema_issues(value: Any, schema: dict, path: str = "$") -> list[str]:
    """Validate the compact schema subset without a runtime dependency.

    The project deliberately has no jsonschema dependency. This covers every
    keyword emitted by :func:`compact_json_schema`; adding a new keyword there
    therefore requires adding it here and a test, rather than silently weakening
    the production boundary.
    """
    if "oneOf" in schema:
        alternatives = [_schema_issues(value, item, path) for item in schema["oneOf"]]
        if any(not errors for errors in alternatives):
            return []
        shortest = min(alternatives, key=len, default=[f"{path}: matched no alternative"])
        return [f"{path}: matched no allowed shape", *shortest[:2]]
    expected = schema.get("type")
    if expected and not _is_type(value, expected):
        return [f"{path}: expected {expected}, got {type(value).__name__}"]
    issues: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        issues.append(f"{path}: value is not one of {schema['enum']!r}")
    if "const" in schema and value != schema["const"]:
        issues.append(f"{path}: value must equal {schema['const']!r}")
    if isinstance(value, str) and len(value) > int(schema.get("maxLength", len(value))):
        issues.append(f"{path}: string length {len(value)} exceeds {schema['maxLength']}")
    if isinstance(value, int) and not isinstance(value, bool) and "minimum" in schema:
        if value < schema["minimum"]:
            issues.append(f"{path}: {value} is below minimum {schema['minimum']}")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", len(value))):
            issues.append(f"{path}: has {len(value)} items, minimum is {schema['minItems']}")
        if len(value) > int(schema.get("maxItems", len(value))):
            issues.append(f"{path}: has {len(value)} items, maximum is {schema['maxItems']}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                issues.extend(_schema_issues(item, item_schema, f"{path}[{index}]"))
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        for required in schema.get("required") or []:
            if required not in value:
                issues.append(f"{path}: missing required property {required!r}")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    issues.append(f"{path}: unknown property {key!r}")
        if len(value) > int(schema.get("maxProperties", len(value))):
            issues.append(
                f"{path}: has {len(value)} properties, maximum is {schema['maxProperties']}"
            )
        for key, child in value.items():
            if key in properties:
                issues.extend(_schema_issues(child, properties[key], f"{path}.{key}"))
    return issues


def _strip_unknown(value: Any, schema: dict, path: str = "$") -> tuple[Any, list[str]]:
    """Remove bounded cosmetic aliases while retaining an explicit audit note."""
    if "oneOf" in schema:
        # Providers sometimes redundantly return both the file-menu index and
        # the exact path in a symbol citation: ``[2, "src/api.py", "read"]``.
        # The compact contract accepts either ``[index, locator]`` or
        # ``[path, locator]``; the three-part spelling carries no additional
        # meaning.  Normalize it before choosing a oneOf branch so one harmless
        # redundant value cannot invalidate (and repurchase) an entire batch.
        if (
            isinstance(value, list)
            and len(value) == 3
            and isinstance(value[0], int)
            and not isinstance(value[0], bool)
            and isinstance(value[1], str)
            and isinstance(value[2], (str, int))
        ):
            normalized, removed = _strip_unknown(
                [value[1], value[2]], schema, path
            )
            return normalized, [f"{path}[0] redundant file index", *removed]
        alternatives = schema["oneOf"]
        matching = [
            item for item in alternatives
            if not item.get("type") or _is_type(value, item["type"])
        ]
        chosen = min(
            matching or alternatives,
            key=lambda item: len(_schema_issues(value, item)),
        )
        return _strip_unknown(value, chosen, path)
    removed: list[str] = []
    if isinstance(value, dict) and schema.get("type") == "object":
        properties = schema.get("properties") or {}
        # Some providers spell a second citation as sibling ``e2`` rather than
        # the second item of ``e``. Inside an unmistakable answer object this is
        # a closed cosmetic alias: fold it into the bounded evidence array so a
        # valid supporting citation is not silently discarded during repair.
        if "e" in properties and "e2" in value:
            value = dict(value)
            evidence = value.get("e")
            evidence = list(evidence) if isinstance(evidence, list) else []
            second = value.pop("e2")
            max_evidence = int(
                properties["e"].get("maxItems", MAX_EVIDENCE_ITEMS)
            )
            for item in (second if isinstance(second, list) else [second]):
                if item not in evidence and len(evidence) < max_evidence:
                    evidence.append(item)
            value["e"] = evidence
        # Resolve the provider's familiar {file, snippet} spelling only inside
        # an unmistakable compact evidence object. Without this closed alias a
        # valid file locator is stripped to {}, causing a pure spelling
        # difference to climb every rung.
        if (
            "kind" in properties and "path" in properties
            and "file" in value and "path" not in value
        ):
            value = dict(value)
            value["path"] = value.get("file")
            value.setdefault("kind", "file")
        cleaned = {}
        for key, child in value.items():
            if schema.get("additionalProperties") is False and key not in properties:
                removed.append(f"{path}.{key}")
                continue
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                cleaned[key], child_removed = _strip_unknown(
                    child, child_schema, f"{path}.{key}"
                )
                removed.extend(child_removed)
            else:
                cleaned[key] = child
        return cleaned, removed
    if isinstance(value, list) and schema.get("type") == "array":
        item_schema = schema.get("items")
        max_items = schema.get("maxItems")
        if path.endswith(".e") and isinstance(max_items, int) and len(value) > max_items:
            removed.append(f"{path}[{max_items}:]")
            value = value[:max_items]
        cleaned = []
        for index, child in enumerate(value):
            if isinstance(item_schema, dict):
                child, child_removed = _strip_unknown(
                    child, item_schema, f"{path}[{index}]"
                )
                removed.extend(child_removed)
            cleaned.append(child)
        return cleaned, removed
    return value, removed


def validate_compact_response(
    obj: Any, *, prefix: Optional[str], user: str
) -> tuple[Any, list[str], list[str]]:
    """Return ``(sanitized, errors, stripped_paths)`` for a compact response."""
    schema = compact_json_schema(prefix, user)
    if schema is None:
        return obj, [], []
    sanitized, stripped = _strip_unknown(obj, schema)
    return sanitized, _schema_issues(sanitized, schema), stripped


def salvage_compact_response(
    obj: Any, *, prefix: Optional[str], user: str
) -> tuple[Optional[dict], list[str]]:
    """Keep individually valid entries after a failed corrective response.

    This is the final bulkhead: one malformed item becomes one missing target
    for the ordinary ladder to escalate; its valid siblings are never bought a
    third time.
    """
    schema = compact_json_schema(prefix, user)
    if schema is None or not isinstance(obj, dict):
        return None, []
    out = {"components": [], "relationships": []}
    rejected: list[str] = []
    for branch in ("components", "relationships"):
        values = obj.get(branch)
        if not isinstance(values, list):
            rejected.append(branch)
            continue
        item_schema = schema["properties"][branch]["items"]
        for index, value in enumerate(values):
            cleaned, _ = _strip_unknown(value, item_schema, f"$.{branch}[{index}]")
            if _schema_issues(cleaned, item_schema, f"$.{branch}[{index}]"):
                rejected.append(f"{branch}[{index}]")
            else:
                out[branch].append(cleaned)
    if not out["components"] and not out["relationships"]:
        return None, rejected
    return out, rejected


def _invalid_evidence(reason: str) -> dict:
    # EvidenceValidator fails this closed and preserves a useful reason through
    # the ordinary E2 path.  Never silently drop a malformed compact citation.
    return {"kind": "compact-invalid", "reason": reason}


def _raw_citation_snapshot(raw: Any) -> Any:
    """Keep bounded, JSON-safe malformed input for deterministic replay.

    The old compact-invalid row retained only our diagnosis, throwing away the
    provider bytes needed to improve the parser without buying the answer
    again. Compact citations are tiny by contract, but the bound makes that
    invariant explicit even for a malformed object.
    """
    try:
        encoded = json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        encoded = repr(raw)
    if len(encoded.encode("utf-8")) <= 2_000:
        try:
            return json.loads(encoded)
        except json.JSONDecodeError:
            return encoded
    return encoded[:2_000] + "…"


def _component_evidence(
    raw: Any, component_id: str, facts: Any, *, claim: str = ""
) -> Any:
    block = facts.component_facts(component_id)
    files = list(block.get("files") or [])
    edges = list(facts.component_edge_menu(component_id))

    def supplied_symbol(symbol: str, *, parent: str = "") -> Optional[dict]:
        """Resolve only an unambiguous parser declaration supplied to this item."""
        name = symbol.strip()
        parent_name = parent.strip()
        matches = [
            item for item in (block.get("source_declarations") or [])
            if isinstance(item, dict)
            and str(item.get("name") or "") == name
            and str(item.get("file") or "") in files
        ]
        if parent_name and len(matches) > 1:
            matches = [
                item for item in matches
                if parent_name in str(item.get("parent") or "").split()
            ]
        if len(matches) != 1:
            resolver = getattr(facts, "component_symbol_evidence", None)
            if callable(resolver):
                return resolver(component_id, name, parent=parent_name)
            return None
        match = matches[0]
        out = {
            "kind": "symbol", "path": match["file"], "symbol": name,
        }
        if match.get("line") is not None:
            out["line"] = match["line"]
        return out

    def manifest_path(path: str) -> bool:
        name = PurePosixPath(path).name.lower()
        return name in {
            "package.json", "pyproject.toml", "cargo.toml", "package.swift",
            "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
            "docker-compose.yml", "docker-compose.yaml", "compose.yml",
            "compose.yaml",
        }

    if isinstance(raw, bool):
        return _invalid_evidence("boolean is not a citation index")
    if isinstance(raw, int):
        if 0 <= raw < len(files):
            return {"kind": "file", "path": files[raw]}
        return _invalid_evidence(f"file index {raw} is outside the supplied menu")
    if isinstance(raw, str) and raw.startswith("F."):
        field = raw[2:]
        if field in CITABLE_FACTS:
            item = {"kind": "fact", "component": component_id, "field": field}
            if field.startswith(("same_", "system_")) or field in (
                "subject_documentation", "peer_components",
            ):
                item["scope"] = "global"
            return item
        return _invalid_evidence(f"fact field {field!r} is not citable")
    if isinstance(raw, str) and raw.startswith("fact:"):
        field = raw[5:]
        if field in CITABLE_FACTS:
            item = {"kind": "fact", "component": component_id, "field": field}
            if field.startswith(("same_", "system_")) or field in (
                "subject_documentation", "peer_components",
            ):
                item["scope"] = "global"
            return item
        return _invalid_evidence(f"fact field {field!r} is not citable")
    if isinstance(raw, str) and raw.startswith("symbol:"):
        symbol = raw[7:].strip()
        resolved = supplied_symbol(symbol)
        if resolved is not None:
            resolved.pop("line", None)
            return resolved
        return _invalid_evidence(
            f"symbol shorthand {symbol!r} did not identify one supplied declaration"
        )
    if isinstance(raw, str) and raw in CITABLE_FACTS:
        item = {"kind": "fact", "component": component_id, "field": raw}
        if raw.startswith(("same_", "system_")) or raw == "peer_components":
            item["scope"] = "global"
        return item
    if isinstance(raw, str) and raw in files:
        return {"kind": "file", "path": raw}
    if isinstance(raw, str) and "->" in raw:
        _, _, suffix = raw.partition("->")
        matches = [path for path in files if path == suffix or path.endswith("/" + suffix)]
        if len(matches) == 1:
            return {"kind": "file", "path": matches[0]}
    if isinstance(raw, str) and raw == block.get("path"):
        return {"kind": "fact", "component": component_id, "field": "path"}
    if isinstance(raw, str) and raw.startswith("E") and raw[1:].isdigit():
        index = int(raw[1:])
        if 0 <= index < len(edges):
            edge = edges[index]
            return {
                "kind": "edge", "source": edge.get("source"),
                "target": edge.get("target"), "edge_type": edge.get("type"),
            }
        # Repair a stale example/menu index only in the one case that remains
        # deterministic: this component has one edge and the claim names one of
        # that edge's endpoint slugs. This exact shape occurred in the live
        # CurriculumView repair (E3 against a one-edge E0 menu). Never guess
        # among multiple edges.
        if len(edges) == 1:
            edge = edges[0]
            claim_key = re.sub(r"[^a-z0-9]", "", claim.lower())
            endpoint_keys = {
                re.sub(
                    r"[^a-z0-9]", "",
                    str(edge.get(side) or "").rsplit("/", 1)[-1].lower(),
                )
                for side in ("source", "target")
            }
            if any(key and key in claim_key for key in endpoint_keys):
                return {
                    "kind": "edge", "source": edge.get("source"),
                    "target": edge.get("target"), "edge_type": edge.get("type"),
                }
        return _invalid_evidence(f"edge index {raw} is outside the supplied menu")
    if raw == "F":
        # A recurring model shorthand for "the local fact(s) named in this
        # sentence". Resolve it only when the claim itself names an exact
        # allow-listed field; count contradiction checks then verify the value.
        named = [
            field for field in CITABLE_FACTS
            if field.replace("_", " ") in claim.lower()
            or (
                field == "inbound_edges" and "inbound" in claim.lower()
            )
            or (
                field == "outbound_edges" and "outbound" in claim.lower()
            )
        ]
        if named:
            return [
                {"kind": "fact", "component": component_id, "field": field}
                for field in named
            ]
        return _invalid_evidence("bare F did not name a citable field in its claim")
    if isinstance(raw, list) and len(raw) == 2 and raw[0] == "F":
        # ["F", "<field>"]: this component's own analyzer fact. The kind exists
        # because count and absence claims ("6 inbound edges") have no file or
        # symbol to carry them; it was 23.3% of all v2 citations and the wire
        # had no form for it (IMPLEMENTATION-DELTA-PROMPT.md section 2.3).
        field = raw[1]
        if isinstance(field, str) and field in CITABLE_FACTS:
            item = {"kind": "fact", "component": component_id, "field": field}
            if field.startswith(("same_", "system_")) or field in (
                "subject_documentation", "peer_components",
            ):
                item["scope"] = "global"
            return item
        # Live repair calls occasionally read ``F`` as "the supplied source
        # fact" and place the exact declaration name in the second slot.  It is
        # safe to repair only because the name must resolve to one parser-owned
        # declaration in this target's closed menu.  This is not a fuzzy alias.
        if isinstance(field, str):
            resolved = supplied_symbol(field)
            if resolved is not None:
                return resolved
        return _invalid_evidence(
            f"fact field {field!r} is not citable; use one of: " + ", ".join(CITABLE_FACTS)
        )
    if (
        isinstance(raw, list)
        and len(raw) == 2
        and raw[0] == "S"
        and isinstance(raw[1], str)
    ):
        resolved = supplied_symbol(raw[1])
        if resolved is not None:
            return resolved
        return _invalid_evidence(
            f"symbol reference {raw[1]!r} did not identify one supplied declaration"
        )
    if (
        isinstance(raw, list)
        and len(raw) == 2
        and raw[0] == component_id
        and isinstance(raw[1], str)
        and raw[1] in CITABLE_FACTS
    ):
        # A provider occasionally spells the local fact reference as
        # [component_id, field] instead of ["F", field]. It is equally closed
        # and unambiguous because the component must be the item currently
        # being normalized; accepting it prevents a correct repair from being
        # rejected over a redundant self identifier.
        field = raw[1]
        item = {"kind": "fact", "component": component_id, "field": field}
        if field.startswith(("same_", "system_")) or field in (
            "subject_documentation", "peer_components",
        ):
            item["scope"] = "global"
        return item
    if isinstance(raw, list) and len(raw) == 2 and isinstance(raw[0], int):
        index, detail = raw
        if isinstance(detail, str) and detail in CITABLE_FACTS:
            item = {"kind": "fact", "component": component_id, "field": detail}
            if detail.startswith(("same_", "system_")) or detail in (
                "subject_documentation", "peer_components",
            ):
                item["scope"] = "global"
            return item
        if not (0 <= index < len(files)):
            # A provider can treat the prompt's source-declaration atom as a
            # citation menu entry and return [atom-index, "Symbol"] rather than
            # the declaration's file index. Resolve this only when the symbol
            # name identifies exactly one parser-owned declaration supplied to
            # this target. The live UnaMentis canary returned [2, "ViewName"]
            # for nineteen one-file screen targets; rejecting those exact
            # declarations as compact-invalid caused needless Opus climbs.
            if isinstance(detail, str) and detail.strip():
                resolved = supplied_symbol(detail)
                if resolved is not None:
                    return resolved
            return _invalid_evidence(f"file index {index} is outside the supplied menu")
        if isinstance(detail, bool):
            return _invalid_evidence("boolean is neither a symbol nor a line")
        if isinstance(detail, int):
            return {"kind": "file", "path": files[index], "line": detail}
        if isinstance(detail, str) and detail.strip():
            if detail.strip() in (files[index], PurePosixPath(files[index]).name):
                return {"kind": "file", "path": files[index]}
            if manifest_path(files[index]):
                return {"kind": "manifest", "path": files[index]}
            return {"kind": "symbol", "path": files[index], "symbol": detail.strip()}
    if isinstance(raw, list) and len(raw) == 2 and isinstance(raw[0], str):
        path, detail = raw
        if path in {"source_declaration", "source_declarations"} and isinstance(detail, str):
            resolved = supplied_symbol(detail)
            if resolved is not None:
                resolved.pop("line", None)
                return resolved
            return _invalid_evidence(
                f"source_declarations reference {detail!r} was not unique"
            )
        if path.startswith("symbol:") and isinstance(detail, str):
            resolved = supplied_symbol(detail, parent=path[7:])
            if resolved is not None:
                return resolved
            return _invalid_evidence(
                f"symbol pair {path!r}, {detail!r} did not identify one supplied declaration"
            )
        if path not in files:
            return _invalid_evidence(f"path {path!r} is outside the supplied file menu")
        if isinstance(detail, str) and detail.strip():
            if detail.strip() in (path, PurePosixPath(path).name):
                return {"kind": "file", "path": path}
            if manifest_path(path):
                return {"kind": "manifest", "path": path}
            return {"kind": "symbol", "path": path, "symbol": detail.strip()}
    if isinstance(raw, dict):
        item = dict(raw)
        # A bare file citation from a component call normally means "this
        # target's declaration in that file", but a file's existence alone is
        # too weak for source-content claims. Upgrade it only when the target's
        # normalized id/name identifies exactly one supplied parser declaration
        # in that exact file. Otherwise retain the original citation and let the
        # evidence validator/judge treat it at its stated strength.
        if (
            str(item.get("kind") or "") == "file"
            and item.get("path") in files
            and item.get("line") is None
            and not item.get("symbol")
        ):
            target_names = {
                re.sub(r"[^a-z0-9]", "", component_id.rsplit("/", 1)[-1].lower()),
                re.sub(r"[^a-z0-9]", "", str(block.get("name") or "").lower()),
            }
            matches = [
                declaration
                for declaration in (block.get("source_declarations") or [])
                if isinstance(declaration, dict)
                and declaration.get("file") == item.get("path")
                and re.sub(
                    r"[^a-z0-9]", "",
                    str(declaration.get("name") or "").lower(),
                ) in target_names
            ]
            if len(matches) == 1:
                return {
                    key: value for key, value in {
                        "kind": "symbol", "path": item["path"],
                        "symbol": matches[0].get("name"),
                        "line": matches[0].get("line"),
                    }.items() if value is not None
                }
        return item
    return _invalid_evidence("citation did not match compact/v1")


def _relationship_evidence(raw: Any, relationship_key: str, facts: Any) -> dict:
    block = facts.relationship_facts(relationship_key)
    evidence = list(block.get("evidence") or [])

    def canonical(item: Any) -> dict:
        if not isinstance(item, dict):
            return _invalid_evidence("relationship citation is not an object")
        path = item.get("path") or item.get("file")
        kind = str(item.get("kind") or "").strip().lower()
        if path and kind not in ("file", "symbol", "manifest", "doc"):
            kind = "file"
        if path:
            out = {"kind": kind or "file", "path": path}
            if item.get("line") is not None:
                out["line"] = item.get("line")
            if kind == "symbol" and item.get("symbol"):
                out["symbol"] = item.get("symbol")
            return out
        if item.get("source") and item.get("target"):
            return {
                "kind": "edge", "source": item.get("source"),
                "target": item.get("target"),
                "edge_type": item.get("edge_type") or item.get("type"),
            }
        return dict(item)
    if isinstance(raw, bool):
        return _invalid_evidence("boolean is not a citation index")
    if isinstance(raw, int):
        if 0 <= raw < len(evidence) and isinstance(evidence[raw], dict):
            return canonical(evidence[raw])
        return _invalid_evidence(f"relationship evidence index {raw} is outside the menu")
    if isinstance(raw, str) and raw.startswith("F."):
        raw = ["F", raw[2:]]
    if isinstance(raw, str) and raw.startswith("fact:"):
        raw = ["F", raw[5:]]
    if isinstance(raw, str) and raw in CITABLE_FACTS:
        raw = ["F", raw]
    if (
        isinstance(raw, list)
        and len(raw) == 2
        and raw[0] == "F"
        and isinstance(raw[1], str)
        and raw[1] in CITABLE_FACTS
        and raw[1] in block
    ):
        field = raw[1]
        item = {"kind": "fact", "component": relationship_key, "field": field}
        if field.startswith(("same_", "system_")) or field in (
            "subject_documentation", "peer_components",
        ):
            item["scope"] = "global"
        return item
    if (
        isinstance(raw, list)
        and len(raw) == 2
        and isinstance(raw[0], int)
        and isinstance(raw[1], str)
        and raw[1] in CITABLE_FACTS
        and raw[1] in block
    ):
        field = raw[1]
        item = {"kind": "fact", "component": relationship_key, "field": field}
        if field.startswith(("same_", "system_")) or field in (
            "subject_documentation", "peer_components",
        ):
            item["scope"] = "global"
        return item
    if isinstance(raw, str) and raw.startswith("file:"):
        path = raw[5:]
        matches = [
            item for item in evidence
            if isinstance(item, dict)
            and (item.get("path") or item.get("file")) == path
        ]
        if len(matches) == 1:
            return canonical(matches[0])
        return _invalid_evidence(f"relationship file {path!r} is outside the menu")
    if isinstance(raw, dict):
        return canonical(raw)
    return _invalid_evidence("citation did not match compact/v1")


def _answer(raw: Any, expand_evidence, *, default_evidence: Iterable[dict] = ()) -> dict:
    """Expand one terse answer into the canonical Answer mapping."""
    if isinstance(raw, str):
        return {
            "claim": raw.strip(), "status": "answered",
            "evidence": [dict(item) for item in default_evidence],
        }
    if not isinstance(raw, dict):
        return {"claim": "", "status": "dropped", "reason": "answer was absent"}
    status = {"u": "uncertain", "d": "dropped"}.get(raw.get("s"), "answered")
    evidence_raw = raw.get("e") if isinstance(raw.get("e"), list) else []
    # A recurring compact spelling flattens a single two-part citation into
    # the evidence array itself: ``e:["S","View"]`` rather than the canonical
    # ``e:[["S","View"]]``. Treat only closed, unambiguous pair markers as one
    # citation. Numeric arrays remain multiple file citations, so this cannot
    # guess between legitimate meanings.
    if (
        len(evidence_raw) == 2
        and isinstance(evidence_raw[0], str)
        and evidence_raw[0] in {
            "S", "F", "source_declaration", "source_declarations",
        }
        and isinstance(evidence_raw[1], str)
    ):
        evidence_raw = [evidence_raw]
    expanded = []
    for item in evidence_raw:
        value = expand_evidence(item, str(raw.get("t") or ""))
        if isinstance(value, list):
            expanded.extend(value)
        else:
            if (
                isinstance(value, dict)
                and value.get("kind") == "compact-invalid"
                and "raw_citation" not in value
            ):
                value["raw_citation"] = _raw_citation_snapshot(item)
            expanded.append(value)
    answer = {
        "claim": str(raw.get("t") or "").strip(),
        "status": status,
        "evidence": expanded,
    }
    if status == "answered" and not answer["evidence"] and default_evidence:
        answer["evidence"] = [dict(item) for item in default_evidence]
    if raw.get("r"):
        answer["reason"] = str(raw["r"]).strip()
    # These fields are retained for escalation/v1 learning.  Answer.from_any
    # intentionally ignores them when deciding groundedness.
    if status == "uncertain" and raw.get("l") in ("fact", "judgment"):
        answer["lacked"] = raw["l"]
        if raw.get("l") == "fact" and raw.get("need"):
            answer["need"] = str(raw["need"]).strip()
    return answer


def _component_entry(entry: dict, component_id: str, facts: Any) -> dict:
    product = {name: entry[name] for name in _PRODUCT_FIELDS if entry.get(name) not in (None, "", [])}
    # Analyzer-owned attributes are prose formatting work, not inference. Render
    # them from the exact fact block so framework, port, size, service, and test
    # statements cannot drift while being paraphrased by a model.
    fact_block = facts.component_facts(component_id)
    identity = [
        str(fact_block.get(name)) for name in ("type", "language", "framework")
        if fact_block.get(name) not in (None, "")
    ]
    if identity:
        deterministic = "Analyzer classification: " + "; ".join(identity) + "."
        interpretation = str(product.get("tech_context") or "").strip()
        product["tech_context"] = (deterministic + " " + interpretation).strip()[:700]
    if fact_block.get("port") not in (None, ""):
        deterministic = (
            f"The analyzer records port {fact_block['port']} for this component."
        )
        interpretation = str(product.get("port_assessment") or "").strip()
        product["port_assessment"] = (
            deterministic + " " + interpretation
        ).strip()[:400]
    lines = fact_block.get("lines")
    files = fact_block.get("file_count")
    if (isinstance(lines, int) and lines > 5_000) or (
        isinstance(files, int) and files > 20
    ):
        deterministic = (
            f"The analyzer records {lines or 0:,} lines across {files or 0:,} files."
        )
        interpretation = str(product.get("complexity_assessment") or "").strip()
        product["complexity_assessment"] = (
            deterministic + " " + interpretation
        ).strip()[:500]
    if fact_block.get("external_services"):
        names = [
            str(item.get("name") or item.get("service") or item)
            if isinstance(item, dict) else str(item)
            for item in fact_block["external_services"][:8]
        ]
        deterministic = "Analyzer-detected external services: " + ", ".join(names) + "."
        interpretation = str(product.get("external_services_assessment") or "").strip()
        product["external_services_assessment"] = (
            deterministic + " " + interpretation
        ).strip()[:500]
    if fact_block.get("has_testing_data"):
        deterministic = "Analyzer-detected testing data is present."
        interpretation = str(product.get("testing_assessment") or "").strip()
        product["testing_assessment"] = (
            deterministic + " " + interpretation
        ).strip()[:600]
    delta_answers = isinstance(entry.get("q"), dict)
    compact_answers = entry.get("q") if delta_answers else {
        "purpose": entry.get("purpose"),
        "mechanism": entry.get("mechanism"),
        "place": entry.get("place"),
        "next_step": entry.get("next"),
    }
    answers = {
        str(question): _answer(
            raw,
            lambda ev, claim: _component_evidence(
                ev, component_id, facts, claim=claim
            ),
        )
        for question, raw in compact_answers.items()
        if question in (
            "purpose", "mechanism", "place", "next_step",
            "why_matters", "data_handled",
        ) and raw is not None
    }
    if entry.get("label") and not product.get("description"):
        product["description"] = str(entry["label"]).strip()
    for wire_name, question, product_name in (
        ("why_matters", "why_matters", None),
        ("data", "data_handled", "data_handled"),
    ):
        if entry.get(wire_name) not in (None, "", []):
            answer_value = _answer(
                entry[wire_name],
                lambda ev, claim: _component_evidence(
                    ev, component_id, facts, claim=claim
                ),
            )
            if (
                question == "data_handled"
                and fact_block.get("data_entity_count") == 0
                and "no data entit" in answer_value.get("claim", "").lower()
            ):
                answer_value["evidence"].append({
                    "kind": "fact", "component": component_id,
                    "field": "data_entity_count",
                })
            answers[question] = answer_value
            if product_name and answer_value.get("claim"):
                product[product_name] = answer_value["claim"]
    local_singletons = {
        "file_count": r"\b(?:only|sole|single|one)\s+(?:source\s+)?files?\b",
        "inbound_edges": r"\b(?:only|sole|single|one)\s+inbound\s+(?:edge|relationship)\b",
        "outbound_edges": r"\b(?:only|sole|single|one)\s+outbound\s+(?:edge|relationship)\b",
        "capability_count": r"\b(?:only|sole|single|one)\s+(?:route|capability|endpoint)\b",
        "data_entity_count": r"\b(?:only|sole|single|one)\s+data\s+entit(?:y|ies)\b",
    }
    global_singletons = {
        "same_language_component_count": (
            rf"\b(?:only|sole|single|one)\b[^.]{{0,100}}(?:"
            rf"\b{re.escape(str(fact_block.get('language') or ''))}\b[^.]{{0,60}}"
            r"\b(?:component|representative|sample|target)\b|"
            r"\b(?:component|representative|sample|target)\b[^.]{0,60}"
            rf"\b{re.escape(str(fact_block.get('language') or ''))}\b)"
        ),
        "same_type_component_count": (
            rf"\b(?:only|sole|single|one)\b[^.]{{0,100}}(?:"
            rf"\b{re.escape(str(fact_block.get('type') or ''))}\b[^.]{{0,60}}"
            r"\b(?:component|representative|sample|target|type)\b|"
            r"\b(?:component|representative|sample|target|type)\b[^.]{0,60}"
            rf"\b{re.escape(str(fact_block.get('type') or ''))}\b)"
        ),
        "system_relationship_count": (
            r"\b(?:only|sole|single|one)\b[^.]{0,80}"
            r"\b(?:edge|relationship|call)\b"
        ),
        "system_capability_count": (
            r"\b(?:only|sole|single|one)\s+(?:api\s+)?capabilit(?:y|ies)\b"
        ),
        "system_capability_component_count": (
            r"\b(?:only|sole|single|one)\b[^.]{0,80}"
            r"\bcomponent\b[^.]{0,80}\bcapabilit(?:y|ies)\b"
        ),
    }
    for answer_value in answers.values():
        claim = str(answer_value.get("claim") or "")
        for field, pattern in local_singletons.items():
            if fact_block.get(field) == 1 and re.search(pattern, claim, re.I):
                evidence = answer_value.setdefault("evidence", [])
                citation = {
                    "kind": "fact", "component": component_id, "field": field,
                }
                if citation not in evidence:
                    evidence.append(citation)
        for field, pattern in global_singletons.items():
            if fact_block.get(field) == 1 and re.search(pattern, claim, re.I):
                evidence = answer_value.setdefault("evidence", [])
                citation = {
                    "kind": "fact", "component": component_id,
                    "field": field, "scope": "global",
                }
                if citation not in evidence:
                    evidence.append(citation)
        capabilities = fact_block.get("capabilities") or []
        capability_terms = []
        for capability in capabilities:
            if not isinstance(capability, dict):
                continue
            capability_terms.append(str(capability.get("name") or ""))
            detail = capability.get("detail") or {}
            if isinstance(detail, dict):
                capability_terms.extend([
                    str(detail.get("path") or ""),
                    str(detail.get("framework") or ""),
                    str(detail.get("symbol") or "").rsplit(" ", 1)[-1],
                ])
        if any(
            len(term) >= 4 and term.lower() in claim.lower()
            for term in capability_terms
        ):
            evidence = answer_value.setdefault("evidence", [])
            citation = {
                "kind": "fact", "component": component_id,
                "field": "capabilities",
            }
            if citation not in evidence and len(evidence) < MAX_EVIDENCE_ITEMS:
                evidence.append(citation)
        deterministic_matches = []
        if re.search(r"\b\d[\d,]*\s+lines?\b", claim, re.I):
            deterministic_matches.append("lines")
        if re.search(
            r"\b\d[\d,]*[- ]files?\b|\b(?:single|one)\s+files?\b",
            claim,
            re.I,
        ):
            deterministic_matches.append("file_count")
        if re.search(
            r"\bno\s+(?:detected\s+|internal\s+)?capabilit(?:y|ies)\b",
            claim,
            re.I,
        ):
            deterministic_matches.append("capability_count")
        if re.search(
            r"\b(?:no|without)\b[^.]{0,80}\b(?:data\s+)?entit(?:y|ies)\b",
            claim,
            re.I,
        ):
            deterministic_matches.append("data_entity_count")
        if fact_block.get("file_count") == 0 and re.search(
            r"\b(?:file_count\s*(?:is|of|:)?\s*0|zero\s+files?|"
            r"no\s+(?:source\s+)?files?|not\s+code)\b",
            claim,
            re.I,
        ):
            deterministic_matches.append("file_count")
        if fact_block.get("lines") == 0 and re.search(
            r"\b(?:zero\s+lines?|no\s+lines?(?:\s+of\s+code)?)\b",
            claim,
            re.I,
        ):
            deterministic_matches.append("lines")
        if fact_block.get("inbound_edges") == 0 and re.search(
            r"\b(?:no|zero)\b[^.]{0,35}\binbound\b|"
            r"\binbound_edges\s*(?:is|are|:)?\s*0\b",
            claim,
            re.I,
        ):
            deterministic_matches.append("inbound_edges")
        if fact_block.get("outbound_edges") == 0 and re.search(
            r"\b(?:no|zero)\b[^.]{0,35}\boutbound\b|"
            r"\boutbound_edges\s*(?:is|are|:)?\s*0\b",
            claim,
            re.I,
        ):
            deterministic_matches.append("outbound_edges")
        if (
            fact_block.get("inbound_edges") == 0
            and fact_block.get("outbound_edges") == 0
            and re.search(
                r"\bno\b[^.]{0,35}\b(?:connections?|edges?)\b", claim, re.I
            )
        ):
            deterministic_matches.extend(("inbound_edges", "outbound_edges"))
        if "highest inbound" in claim.lower():
            deterministic_matches.append("system_max_inbound_edges")
        if "highest outbound" in claim.lower():
            deterministic_matches.append("system_max_outbound_edges")
        for field in ("framework", "language", "port", "type"):
            value = fact_block.get(field)
            if value not in (None, "") and str(value).lower() in claim.lower():
                deterministic_matches.append(field)
        child_components = fact_block.get("child_components") or []
        if any(str(child).lower() in claim.lower() for child in child_components):
            deterministic_matches.append("child_components")
        peer_components = fact_block.get("peer_components") or []
        if any(
            any(
                len(str(value)) >= 2
                and re.search(
                    rf"(?<![a-z0-9]){re.escape(str(value).lower())}(?![a-z0-9])",
                    claim.lower(),
                )
                for value in (peer.get("id"), peer.get("name"))
                if value not in (None, "")
            )
            for peer in peer_components if isinstance(peer, dict)
        ):
            deterministic_matches.append("peer_components")
        descendant_edges = fact_block.get("descendant_edges") or []
        if any(
            str(edge.get("source") or "").lower() in claim.lower()
            or str(edge.get("target") or "").lower() in claim.lower()
            for edge in descendant_edges if isinstance(edge, dict)
        ):
            deterministic_matches.append("descendant_edges")
        files = fact_block.get("files") or []
        names_a_file = any(
            str(path).lower() in claim.lower()
            or PurePosixPath(str(path)).name.lower() in claim.lower()
            for path in files
        )
        already_cites_file = any(
            isinstance(item, dict)
            and item.get("kind") in ("file", "symbol", "manifest", "doc")
            for item in answer_value.get("evidence") or []
        )
        if names_a_file and not already_cites_file:
            deterministic_matches.append("files")
        edges = fact_block.get("edges") or []
        if any(
            (
                str(edge.get("source") or "").lower() in claim.lower()
                and str(edge.get("target") or "").lower() in claim.lower()
            )
            or (
                str(edge.get("type") or "").lower() in claim.lower()
                and (
                    str(edge.get("source") or "").lower() in claim.lower()
                    or str(edge.get("target") or "").lower() in claim.lower()
                )
            )
            for edge in edges if isinstance(edge, dict)
        ):
            deterministic_matches.append("edges")
        config_files = fact_block.get("config_files") or []
        if any(
            str(item.get("path") or "").lower() in claim.lower()
            or PurePosixPath(str(item.get("path") or "")).name.lower()
            in claim.lower()
            or any(
                len(str(service)) >= 2
                and re.search(
                    rf"\b{re.escape(str(service).lower())}\b",
                    claim.lower(),
                )
                for service in (item.get("services") or [])
            )
            for item in config_files if isinstance(item, dict)
        ):
            deterministic_matches.append("config_files")
        if (
            config_files
            and re.search(r"\b(?:compose|service\s+declaration)\b", claim, re.I)
            and any(
                "compose" in str(item.get("path") or "").lower()
                or "compose" in str(
                    item.get("type") or item.get("kind") or ""
                ).lower()
                for item in config_files if isinstance(item, dict)
            )
        ):
            deterministic_matches.append("config_files")
        if "readme" in claim.lower():
            local_docs = fact_block.get("documentation") or {}
            if isinstance(local_docs, dict) and local_docs.get("readme_excerpt"):
                deterministic_matches.append("documentation")
            elif fact_block.get("subject_documentation"):
                deterministic_matches.append("subject_documentation")
        # Intent and corpus-comparison prose is not carried by parser facts.
        # When the deterministic subject documentation supplied to this exact
        # target declares that context, attach it automatically.  This does not
        # manufacture evidence: it makes the already-supplied README fact the
        # citation for claims whose vocabulary explicitly signals documented
        # intent or whole-subject comparison.
        if fact_block.get("subject_documentation") and re.search(
            r"\b(?:fixture|test(?:ing|\s+suite)?|pars(?:e|er|ing)|parity|verify|validat(?:e|ing)|"
            r"prove|planted|built\s+to|exists\s+to|other\s+language|distinct\s+from)\b",
            claim,
            re.I,
        ):
            deterministic_matches.append("subject_documentation")
        for field in dict.fromkeys(deterministic_matches):
            if field not in fact_block:
                continue
            evidence = answer_value.setdefault("evidence", [])
            citation = {
                "kind": "fact", "component": component_id, "field": field,
            }
            if field.startswith(("same_", "system_")) or field in (
                "subject_documentation", "peer_components",
            ):
                citation["scope"] = "global"
            if citation not in evidence:
                evidence.append(citation)
    # Generate each semantic atom once.  The reader prose and audit contract
    # share those exact atoms instead of paying the model for two paraphrases.
    if not product.get("help_text") and not delta_answers:
        prose = [
            answers.get(name, {}).get("claim", "")
            for name in ("purpose", "mechanism", "place")
        ]
        prose.append(answers.get("why_matters", {}).get("claim", ""))
        product["help_text"] = " ".join(text for text in prose if text)
    # Identity is parser-owned by default.  Only exceptions cross the wire, and
    # they remain in the audit record for adjudication and future parser work.
    for field, flag in (entry.get("id") or {}).items():
        if field not in ("type", "framework", "port", "language") or not isinstance(flag, dict):
            continue
        value = flag.get("v")
        answers[f"identity.{field}"] = {
            "claim": f"corrected {field}: {value}",
            "status": "answered" if flag.get("e") else "uncertain",
            "reason": str(flag.get("r") or "parser identity may be wrong"),
            "evidence": [
                _component_evidence(ev, component_id, facts)
                for ev in (flag.get("e") or [])
            ],
        }
    contract = {
        "parser_first": [str(x) for x in (entry.get("pf") or [])[:2]],
        "answers": answers,
        "confusion": str(entry.get("confusion") or "").strip() or None,
    }
    if entry.get("generic") is True:
        contract["substitution_check"] = "would fit any sibling component"
    product[CONTRACT_KEY] = contract
    gaps = entry.get("gaps")
    if isinstance(gaps, list):
        product["honest_gaps"] = [
            {"question": str(g.get("q") or ""), "why": str(g.get("why") or "")}
            for g in gaps if isinstance(g, dict) and g.get("q")
        ]
    return product


def _relationship_entry(entry: dict, key: str, facts: Any) -> dict:
    product = {}
    if entry.get("imp"):
        product["importance"] = entry["imp"]
    answers = {}
    for question in ("flow", "why"):
        if question in entry:
            answers[question] = _answer(
                entry[question],
                lambda ev, claim: _relationship_evidence(ev, key, facts),
            )
    relationship_facts = facts.relationship_facts(key)
    for answer in answers.values():
        claim = str(answer.get("claim") or "")
        evidence = answer.setdefault("evidence", [])
        if (
            relationship_facts.get("system_relationship_count") == 1
            and re.search(
                r"\b(?:only|sole|single|one)\b[^.]{0,80}"
                r"\b(?:edge|relationship|call|connection)\b",
                claim,
                re.I,
            )
        ):
            citation = {
                "kind": "fact", "component": key,
                "field": "system_relationship_count", "scope": "global",
            }
            if citation not in evidence:
                evidence.append(citation)
        if relationship_facts.get("subject_documentation") and re.search(
            r"\b(?:fixture|test(?:ing|\s+suite)?|pars(?:e|er|ing)|parity|verify|validat(?:e|ing)|"
            r"prove|planted|built\s+to|exists\s+to)\b",
            claim,
            re.I,
        ):
            citation = {
                "kind": "fact", "component": key,
                "field": "subject_documentation", "scope": "global",
            }
            if citation not in evidence:
                evidence.append(citation)
    if entry.get("d"):
        product["data_flow_description"] = entry["d"]
    elif answers.get("flow", {}).get("claim"):
        # Same semantic atom serves the reader and the contract.
        product["data_flow_description"] = answers["flow"]["claim"]
    product[CONTRACT_KEY] = {"parser_first": [], "answers": answers}
    gaps = entry.get("gaps")
    if isinstance(gaps, list):
        product["honest_gaps"] = [
            {"question": str(g.get("q") or ""), "why": str(g.get("why") or "")}
            for g in gaps if isinstance(g, dict) and g.get("q")
        ]
    return product


def normalize_compact_response(
    obj: Any,
    *,
    facts: Any,
    component_ids: Iterable[str] = (),
    relationship_keys: Iterable[str] = (),
) -> dict:
    """Expand compact/v1 or pass the canonical legacy shape through unchanged."""
    if not isinstance(obj, dict):
        return {"components": {}, "relationships": {}}
    raw_components = obj.get("components")
    raw_relationships = obj.get("relationships")
    allowed_components = set(component_ids)
    allowed_relationships = set(relationship_keys)
    # Legacy/canned branches remain valid independently.  Mixed envelopes are
    # normalized branch by branch; one legacy branch can never bypass checks on
    # a compact sibling.
    components = dict(raw_components) if isinstance(raw_components, dict) else {}
    if isinstance(raw_components, list):
        for entry in raw_components:
            if not isinstance(entry, dict):
                continue
            cid = str(entry.get("i") or "")
            if cid and cid in allowed_components:
                components[cid] = _component_entry(entry, cid, facts)
    relationships = dict(raw_relationships) if isinstance(raw_relationships, dict) else {}
    if isinstance(raw_relationships, list):
        for entry in raw_relationships:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("k") or "")
            if key and key in allowed_relationships:
                relationships[key] = _relationship_entry(entry, key, facts)
    return {"components": components, "relationships": relationships}
