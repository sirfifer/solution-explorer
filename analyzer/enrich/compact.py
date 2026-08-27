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
from collections.abc import Iterable
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
                    "e": {"type": "array", "maxItems": 2, "items": {
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
                                "maxProperties": 7,
                                "properties": {
                                    "kind": {"type": "string", "maxLength": 32},
                                    "path": {"type": "string", "maxLength": 500},
                                    "symbol": {"type": "string", "maxLength": 240},
                                    "line": {"type": "integer", "minimum": 1},
                                    "source": {"type": "string", "maxLength": 500},
                                    "target": {"type": "string", "maxLength": 500},
                                    "edge_type": {"type": "string", "maxLength": 80},
                                    "field": {"type": "string", "maxLength": 120},
                                    "value": {"type": "string", "maxLength": 500},
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
        "properties": {name: answer for name in ("purpose", "mechanism", "place", "next_step")},
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
                    "e": {"type": "array", "maxItems": 2,
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
        "why_matters": {"type": "string", "maxLength": 500},
        "data": {"type": "string", "maxLength": 600},
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


def _invalid_evidence(reason: str) -> dict:
    # EvidenceValidator fails this closed and preserves a useful reason through
    # the ordinary E2 path.  Never silently drop a malformed compact citation.
    return {"kind": "compact-invalid", "reason": reason}


def _component_evidence(raw: Any, component_id: str, facts: Any) -> dict:
    block = facts.component_facts(component_id)
    files = list(block.get("files") or [])
    edges = list(facts.component_edge_menu(component_id))

    if isinstance(raw, bool):
        return _invalid_evidence("boolean is not a citation index")
    if isinstance(raw, int):
        if 0 <= raw < len(files):
            return {"kind": "file", "path": files[raw]}
        return _invalid_evidence(f"file index {raw} is outside the supplied menu")
    if isinstance(raw, str) and raw.startswith("E") and raw[1:].isdigit():
        index = int(raw[1:])
        if 0 <= index < len(edges):
            edge = edges[index]
            return {
                "kind": "edge", "source": edge.get("source"),
                "target": edge.get("target"), "edge_type": edge.get("type"),
            }
        return _invalid_evidence(f"edge index {raw} is outside the supplied menu")
    if isinstance(raw, list) and len(raw) == 2 and raw[0] == "F":
        # ["F", "<field>"]: this component's own analyzer fact. The kind exists
        # because count and absence claims ("6 inbound edges") have no file or
        # symbol to carry them; it was 23.3% of all v2 citations and the wire
        # had no form for it (IMPLEMENTATION-DELTA-PROMPT.md section 2.3).
        field = raw[1]
        if isinstance(field, str) and field in CITABLE_FACTS:
            return {"kind": "fact", "component": component_id, "field": field}
        return _invalid_evidence(
            f"fact field {field!r} is not citable; use one of: " + ", ".join(CITABLE_FACTS)
        )
    if isinstance(raw, list) and len(raw) == 2 and isinstance(raw[0], int):
        index, detail = raw
        if not (0 <= index < len(files)):
            return _invalid_evidence(f"file index {index} is outside the supplied menu")
        if isinstance(detail, bool):
            return _invalid_evidence("boolean is neither a symbol nor a line")
        if isinstance(detail, int):
            return {"kind": "file", "path": files[index], "line": detail}
        if isinstance(detail, str) and detail.strip():
            return {"kind": "symbol", "path": files[index], "symbol": detail.strip()}
    if isinstance(raw, dict):
        return dict(raw)
    return _invalid_evidence("citation did not match compact/v1")


def _relationship_evidence(raw: Any, relationship_key: str, facts: Any) -> dict:
    block = facts.relationship_facts(relationship_key)
    evidence = list(block.get("evidence") or [])
    if isinstance(raw, bool):
        return _invalid_evidence("boolean is not a citation index")
    if isinstance(raw, int):
        if 0 <= raw < len(evidence) and isinstance(evidence[raw], dict):
            return dict(evidence[raw])
        return _invalid_evidence(f"relationship evidence index {raw} is outside the menu")
    if isinstance(raw, dict):
        return dict(raw)
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
    answer = {
        "claim": str(raw.get("t") or "").strip(),
        "status": status,
        "evidence": [expand_evidence(item) for item in evidence_raw],
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
    compact_answers = entry.get("q") if isinstance(entry.get("q"), dict) else {
        "purpose": entry.get("purpose"),
        "mechanism": entry.get("mechanism"),
        "place": entry.get("place"),
        "next_step": entry.get("next"),
    }
    answers = {
        str(question): _answer(raw, lambda ev: _component_evidence(ev, component_id, facts))
        for question, raw in compact_answers.items()
        if question in ("purpose", "mechanism", "place", "next_step") and raw is not None
    }
    if entry.get("label") and not product.get("description"):
        product["description"] = str(entry["label"]).strip()
    if entry.get("data") and not product.get("data_handled"):
        product["data_handled"] = str(entry["data"]).strip()
    # Generate each semantic atom once.  The reader prose and audit contract
    # share those exact atoms instead of paying the model for two paraphrases.
    if not product.get("help_text"):
        prose = [
            answers.get(name, {}).get("claim", "")
            for name in ("purpose", "mechanism", "place")
        ]
        prose.append(str(entry.get("why_matters") or "").strip())
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
                lambda ev: _relationship_evidence(ev, key, facts),
            )
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
