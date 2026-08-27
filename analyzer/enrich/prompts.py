"""Per-partition and architecture-level prompt construction from store facts.

This is the DPEA "Enhance" contract, industrialized. The `/ai-assist` skill had
each subagent read source files; here the fact store grounds the model with more
than raw files ever could: the projected component (rich fields the scorer reads:
language, framework, metrics, testing, actions, ports, docs), plus the store's
capabilities, data entities, rules, and edge evidence for each component. The
prompt embeds the RESOURCES.md payload contract (schema, role vocabulary,
criticality guidance, few-shot calibration) so the model returns schema-valid
`ai_enhance` blocks that pass the quality scorer.

Prompts are pure functions of their inputs, so prompt construction is testable
without invoking a model.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .partition import Partition

__all__ = [
    "StoreFacts",
    "build_partition_prompt",
    "build_architecture_prompt",
    "build_edge_verify_prompt",
    "build_edge_verify_batch_prompt",
    "build_concern_name_prompt",
    "build_intent_conformance_prompt",
    "build_intent_proposal_prompt",
    "build_finding_verify_prompt",
    "build_finding_verify_batch_prompt",
    "build_identify_unknowns_prompt",
    "build_identity_verify_prompt",
    "build_identity_verify_batch_prompt",
    "build_contract_partition_prompt",
    "build_compact_component_prompt",
    "build_compact_relationship_prompt",
    "build_compact_escalation_prompt",
    "split_cached_prompt",
    "build_grounding_spotcheck_prompt",
    "build_substitution_prompt",
]

# The architectural role vocabulary (RESOURCES.md). Kept in sync with the
# scorer's VALID_ROLES; the prompt lists it so the model uses exact values.
ROLE_VOCABULARY = [
    "api-gateway", "auth-service", "data-store", "cache-layer",
    "queue-processor", "event-bus", "orchestrator", "worker",
    "proxy", "monitoring", "logging", "scheduler",
    "notification-service", "file-storage", "search-engine",
    "ml-pipeline", "presentation-layer", "business-logic", "data-access",
]

_SCHEMA_CONTRACT = """\
Return ONLY a single JSON object, no prose, no markdown fences. Shape:

{
  "components": {
    "<component-id>": {
      "help_text": "3-5 complete sentences explaining what this component is, what \
it does, how it connects to its neighbours, and why it matters. Written for a \
reviewer who has never seen the code.",
      "description": "ONE short plain sentence (about 8 to 15 words) naming what \
this component is. This is the one-line tree/summary label, distinct from and \
much shorter than help_text.",
      "data_handled": "specific data types that flow through this component (not \
just 'user data')",
      "criticality": "critical | important | supporting",
      "architectural_role": "one exact value from the ROLE VOCABULARY below, or null",
      "tech_context": "how the language/framework choice fits the architecture \
(include when the component has a language or framework)",
      "testing_assessment": "1-2 sentences (include only when the component has \
testing data)",
      "testing_maturity": "comprehensive | adequate | minimal | untested (only \
when testing data exists)",
      "port_assessment": "what the port is used for (only when a port is set)",
      "complexity_assessment": "size/complexity note (only for >5000 lines or >20 files)",
      "external_services_assessment": "dependency/critical-path note (only when \
external_services exist)",
      "actions_summary": "1-2 sentence summary of UI actions (only when actions exist)",
      "key_user_flows": ["2-5 user flows (only when actions exist)"]
    }
  },
  "relationships": {
    "<source>|<target>|<type>": {
      "data_flow_description": "what flows across this connection",
      "importance": "primary | secondary | internal"
    }
  }
}

RULES:
- Produce an entry in "components" for EVERY component id listed under COMPONENTS \
below. Missing any is a failure.
- help_text MUST be 3 to 5 sentences. data_handled MUST be specific.
- description MUST be a single short sentence (the one-line tree label), NOT a \
copy of help_text.
- criticality MUST be exactly one of: critical, important, supporting. Use the \
CRITICALITY GUIDANCE and the inbound/outbound edge counts to justify it.
- architectural_role MUST be an exact value from the ROLE VOCABULARY, or null if \
none genuinely applies.
- Only include the conditional fields when the component actually has that data \
(the facts note when it does). Do NOT invent fields not listed above.
- Produce an entry in "relationships" for every relationship key listed under \
RELATIONSHIPS below.
"""

_CRITICALITY_GUIDANCE = """\
CRITICALITY GUIDANCE:
- critical: the system cannot function without it (sole API entry point, primary \
data store, auth service). Often many inbound edges or an articulation point.
- important: absence degrades but does not break the system (cache, search, \
notifications).
- supporting: developer tooling, utilities, libraries, leaf UI, infrastructure \
config. Often 0 inbound edges.
"""

_FEWSHOT = """\
QUALITY CALIBRATION (good vs bad):
- Good help_text: "The UserService handles all user lifecycle operations \
including registration, profile updates, and deletion. It is called by the API \
Gateway on every authenticated request to validate sessions. It writes to the \
PostgreSQL database via the UserRepository and publishes user events to the \
event bus. Without it, no authenticated operation can proceed." (4 sentences, \
specific, references neighbours)
- Bad help_text: "This service manages users. It handles CRUD operations." (too \
vague, no context)
- Good data_handled: "User profile objects, authentication tokens, session \
metadata, password hashes"
- Bad data_handled: "User data"
"""


# Byte budgets for one component's fact block. The 569-block VS Code mean is
# 1,417 characters, so these bound the pathological tail without touching a
# normal block. A prompt that cannot fit in a context window is not a quality
# choice, it is a failed call.
MAX_FACT_BLOCK_CHARS = 12_000
MAX_FACT_VALUE_CHARS = 2_000
MAX_FACT_STRING_CHARS = 600


def _cap_value(value: Any, budget: int) -> Any:
    """Trim one fact value to a byte budget, saying so where it trims.

    Lists keep whole leading entries and record how many were dropped, so what
    survives is always something the parser actually found rather than a
    fragment. Strings are cut with an explicit marker. Nothing is silently
    shortened: a reader of the prompt can tell the difference between "this is
    all there was" and "there was more".
    """
    if isinstance(value, str):
        if len(value) <= MAX_FACT_STRING_CHARS:
            return value
        return value[:MAX_FACT_STRING_CHARS] + f"... [+{len(value) - MAX_FACT_STRING_CHARS} chars]"
    if isinstance(value, list):
        kept: list[Any] = []
        used = 0
        for item in value:
            capped = _cap_value(item, budget)
            size = len(json.dumps(capped, default=str))
            if used + size > budget and kept:
                break
            kept.append(capped)
            used += size
        dropped = len(value) - len(kept)
        if dropped > 0:
            kept.append(f"[{dropped} more omitted to fit the prompt budget]")
        return kept
    if isinstance(value, dict):
        out: dict = {}
        used = 0
        for key, item in value.items():
            capped = _cap_value(item, max(200, budget // 2))
            size = len(json.dumps({key: capped}, default=str))
            if used + size > budget and out:
                out["_omitted"] = "further keys omitted to fit the prompt budget"
                break
            out[key] = capped
            used += size
        return out
    return value


def _cap_block(facts: dict) -> dict:
    """Bound a whole fact block, trimming its largest fields first."""
    if len(json.dumps(facts, default=str)) <= MAX_FACT_BLOCK_CHARS:
        return facts
    out = dict(facts)
    # Trim biggest-first so one runaway field cannot evict everything else.
    by_size = sorted(
        out.items(),
        key=lambda kv: len(json.dumps(kv[1], default=str)),
        reverse=True,
    )
    for key, value in by_size:
        if len(json.dumps(out, default=str)) <= MAX_FACT_BLOCK_CHARS:
            break
        if isinstance(value, (str, list, dict)):
            out[key] = _cap_value(value, MAX_FACT_VALUE_CHARS)
    return out


class StoreFacts:
    """Store-derived grounding for prompts, indexed by component id.

    Combines the projected arch component (rich fields the scorer reads) with the
    store's capabilities, data entities, and rules for that component, plus a
    per-component inbound/outbound edge summary. Built once and shared across
    partition prompts.
    """

    def __init__(
        self,
        arch: dict,
        capabilities: list[dict],
        data_entities: list[dict],
        rules: list[dict],
        relationships: list[dict],
    ):
        self.arch = arch
        self.component_index = _index_components(arch.get("components", []))
        self.caps_by_comp = _group_by(capabilities, "component_id")
        # The AI surface rides on the arch itself (projected after the SBOM), so
        # no new constructor parameter: components that talk to, route, or run
        # models get those facts in their block, and the enhancement can say so
        # instead of never learning it. Grounded like everything else here: the
        # rows carry detector evidence, not inference.
        self.ai_by_comp = _group_by(arch.get("ai_surface") or [], "component_id")
        self.entities_by_comp = _group_by(data_entities, "component_id")
        self.rules_by_comp = _group_by(rules, "component_id")
        self._rel_by_key = {
            f"{r.get('source','')}|{r.get('target','')}|{r.get('type','')}": r
            for r in relationships
        }
        self._inbound: dict[str, int] = {}
        self._outbound: dict[str, int] = {}
        self._edges_by_component: dict[str, list[dict]] = {}
        self._enriched_descriptions: dict[str, str] = {}
        for r in relationships:
            s, t = r.get("source", ""), r.get("target", "")
            if s:
                self._outbound[s] = self._outbound.get(s, 0) + 1
                self._edges_by_component.setdefault(s, []).append(r)
            if t:
                self._inbound[t] = self._inbound.get(t, 0) + 1
                self._edges_by_component.setdefault(t, []).append(r)
        for rows in self._edges_by_component.values():
            rows.sort(key=lambda r: (
                str(r.get("source") or ""), str(r.get("target") or ""),
                str(r.get("type") or ""),
            ))

    def component_facts(self, comp_id: str) -> dict:
        """A compact, JSON-serializable fact block for one component.

        Bounded in BYTES before it is returned, not just in item counts. Every
        list here was already capped by length, which is no protection at all
        when one entry is enormous: on the VS Code snapshot a single `cli`
        capability carried a 366,116-character `detail` full of inferred test
        records, making `cli/src/util` a 373,027-character block, 263 times the
        569-block mean and larger on its own than any context window this runs
        against. The partition holding it could never have succeeded.
        """
        return _cap_block(self._component_facts(comp_id))

    def _component_facts(self, comp_id: str) -> dict:
        comp = self.component_index.get(comp_id, {"id": comp_id})
        metrics = comp.get("metrics") or {}
        facts = {
            "id": comp_id,
            "name": comp.get("name"),
            "type": comp.get("type"),
            "path": comp.get("path"),
            "language": comp.get("language"),
            "framework": comp.get("framework"),
            "lines": metrics.get("lines"),
            "file_count": len(comp.get("files", []) or []),
            "files": (comp.get("files") or [])[:8],
            "existing_description": comp.get("description") or None,
            "inbound_edges": self._inbound.get(comp_id, 0),
            "outbound_edges": self._outbound.get(comp_id, 0),
        }
        # Conditional data the schema keys on. Only present when non-empty, so the
        # model sees exactly which optional fields apply.
        if comp.get("port"):
            facts["port"] = comp.get("port")
        if comp.get("testing"):
            facts["has_testing_data"] = True
            facts["testing"] = comp.get("testing")
        if comp.get("actions"):
            facts["has_actions"] = True
            facts["action_count"] = len(comp.get("actions") or [])
        if comp.get("external_services"):
            facts["external_services"] = comp.get("external_services")
        caps = self.caps_by_comp.get(comp_id)
        if caps:
            facts["capabilities"] = [
                {"kind": c.get("kind"), "name": c.get("name"), "detail": c.get("detail")}
                for c in caps[:12]
            ]
        entities = self.entities_by_comp.get(comp_id)
        if entities:
            facts["data_entities"] = [
                {"name": e.get("name"), "kind": e.get("kind")} for e in entities[:12]
            ]
        ai_rows = self.ai_by_comp.get(comp_id)
        if ai_rows:
            facts["ai_surface"] = [
                {
                    "kind": a.get("kind"),
                    "name": a.get("name"),
                    "confidence": a.get("confidence"),
                    "instances": a.get("instance_count"),
                }
                for a in ai_rows[:12]
            ]
        rules = self.rules_by_comp.get(comp_id)
        if rules:
            facts["rules"] = [
                {"kind": r.get("kind"), "summary": r.get("summary")} for r in rules[:12]
            ]
        return facts

    def relationship_facts(self, key: str) -> dict:
        rel = self._rel_by_key.get(key, {})
        return {
            "key": key,
            "source": rel.get("source"),
            "target": rel.get("target"),
            "type": rel.get("type"),
            "label": rel.get("label"),
            "protocol": rel.get("protocol"),
            "port": rel.get("port"),
            "confidence": rel.get("confidence"),
            "evidence": (rel.get("evidence") or [])[:3],
        }

    def component_edge_menu(self, comp_id: str) -> list[dict]:
        """Stable citation menu: at most 8 outbound then 4 inbound edges."""
        rows = self._edges_by_component.get(comp_id, [])
        outbound = [r for r in rows if r.get("source") == comp_id][:8]
        inbound = [r for r in rows if r.get("target") == comp_id][:4]
        return [
            {"source": r.get("source"), "target": r.get("target"), "type": r.get("type")}
            for r in [*outbound, *inbound]
        ]

    def set_enriched_description(self, comp_id: str, description: Any) -> None:
        """Publish a banked 2a-C one-liner for later relationship calls."""
        value = str(description or "").strip()
        if value:
            self._enriched_descriptions[comp_id] = value

    def best_description(self, comp_id: str) -> Optional[str]:
        comp = self.component_index.get(comp_id, {})
        return self._enriched_descriptions.get(comp_id) or comp.get("description") or None


def build_partition_prompt(partition: Partition, facts: StoreFacts) -> str:
    """Build the enhancement prompt for one partition from store facts."""
    components = [facts.component_facts(cid) for cid in partition.component_ids]
    relationships = [facts.relationship_facts(k) for k in partition.relationship_keys]

    parts = [
        "You are enhancing a software architecture graph. Using ONLY the facts "
        "provided (do not invent structure), produce an ai_enhance block for each "
        "component and relationship.",
        "",
        _SCHEMA_CONTRACT,
        "",
        "ROLE VOCABULARY (use exact values): " + ", ".join(ROLE_VOCABULARY),
        "",
        "Where a component's facts include ai_surface entries (model provider "
        "SDKs, gateways, MCP, agent frameworks, local inference, model ids), "
        "its AI role is part of what the component IS: say what it talks to or "
        "routes and through which mechanism, grounded in those entries. Never "
        "invent AI involvement for components without ai_surface facts.",
        "",
        _CRITICALITY_GUIDANCE,
        "",
        _FEWSHOT,
        "",
        "COMPONENTS (produce an ai_enhance for every id):",
        json.dumps(components, indent=2, default=str),
        "",
        "RELATIONSHIPS (produce an ai_enhance for every key):",
        json.dumps(relationships, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ]
    return "\n".join(parts)


def build_architecture_prompt(facts: StoreFacts, *, changelog: Optional[list] = None) -> str:
    """Build the architecture-level (root) enhancement prompt."""
    arch = facts.arch
    summary_components = []
    for comp in arch.get("components", []):
        summary_components.append({
            "id": comp.get("id"),
            "name": comp.get("name"),
            "type": comp.get("type"),
            "language": comp.get("language"),
            "children": [c.get("id") for c in comp.get("children", [])],
        })
    relationships = [
        {"source": r.get("source"), "target": r.get("target"), "type": r.get("type")}
        for r in arch.get("relationships", [])
    ]
    stats = arch.get("stats", {})

    contract = """\
Return ONLY a single JSON object (no prose, no fences) with this shape:

{
  "summary": "3-5 sentence executive summary of the whole system.",
  "data_flow_narrative": "one paragraph describing how a typical request flows \
through the system end to end.",
  "component_groups": [ { "name": "Layer name", "component_ids": ["id", ...] } ],
  "tech_diversity": "1-2 sentences on the technology mix.",
  "test_health_summary": "1-2 sentences on testing across the codebase.",
  "observations": []
}

summary and data_flow_narrative are REQUIRED and must be non-empty. Group the \
top-level components into meaningful layers. Do not add fields beyond those shown.
"""
    parts = [
        "You are writing the architecture-level summary for a software system.",
        "",
        contract,
        "",
        "TOP-LEVEL COMPONENTS:",
        json.dumps(summary_components, indent=2, default=str),
        "",
        "RELATIONSHIPS:",
        json.dumps(relationships, indent=2, default=str),
        "",
        "STATS: " + json.dumps(stats, default=str),
        "",
        "Return the JSON object now.",
    ]
    return "\n".join(parts)


# --- P7-3 / P7-4 verification and naming prompts -----------------------------
#
# Every one of these prompts is adversarial-honest per LENS-DESIGN.md sections 8
# and 9: the model is asked to ground its answer in the supplied evidence and to
# say "uncertain" / "cannot refute" rather than invent. The pass code validates
# the shape and treats anything unparseable as a non-answer (never junk).


def build_edge_verify_prompt(edge: dict, source: dict, target: dict) -> str:
    """Prompt to verify one inferred edge against its own evidence (P7-3).

    ``edge`` carries type, confidence, and evidence (file, line, snippet from the
    store). ``source`` and ``target`` are compact endpoint summaries.
    """
    contract = """\
Return ONLY a single JSON object, no prose, no fences:

{ "status": "confirmed | refuted | uncertain",
  "reason": "one sentence, grounded in the evidence above" }

RULES:
- confirmed: the evidence genuinely shows this connection exists between these
  two components.
- refuted: the evidence does NOT support this connection (for example the
  snippet is a comment, a string that only resembles a URL, an unrelated match,
  or points at a different target).
- uncertain: the evidence is too thin to decide either way.
- reason MUST cite what in the evidence drove the verdict. Do not invent facts
  not present above. When unsure, say uncertain rather than guessing.
"""
    payload = {
        "edge": {
            "source": edge.get("source"),
            "target": edge.get("target"),
            "type": edge.get("type"),
            "confidence": edge.get("confidence"),
            "evidence": (edge.get("evidence") or [])[:5],
        },
        "source_component": source,
        "target_component": target,
    }
    return "\n".join([
        "You are verifying an INFERRED dependency edge in an architecture graph. "
        "The edge was guessed by a static heuristic and may be a false positive. "
        "Using ONLY the evidence and endpoint summaries below, return a verdict.",
        "",
        contract,
        "",
        "EDGE AND EVIDENCE:",
        json.dumps(payload, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ])


def build_edge_verify_batch_prompt(items: list[dict]) -> str:
    """Verify SEVERAL inferred edges in one call (P7-3, batched).

    One call per edge is what a verification pass looks like when nobody has
    measured it. On the 2026-08-25 unamentis-ios run the per-edge loop made 754
    calls costing $10.50 and returned 16,064 output tokens in total: about 21
    tokens of verdict per call, against a prompt paid in full every time. The
    work was almost entirely fixed overhead, charged 754 times.

    The verdict contract per edge is unchanged, so a batched answer is the same
    answer. Each item carries the id the caller will key the verdict by, which
    is what makes a partial or reordered response safe to absorb: a verdict
    nobody asked for is dropped, and an edge with no verdict simply stays
    unverified rather than silently inheriting its neighbour's.
    """
    contract = """\
Return ONLY a single JSON object, no prose, no fences:

{ "verdicts": {
    "<edge id, exactly as given>": {
      "status": "confirmed | refuted | uncertain",
      "reason": "one sentence, grounded in that edge's own evidence" },
    ...
} }

RULES:
- Judge every edge INDEPENDENTLY. Edges in one batch are unrelated to each
  other, and a verdict on one is never evidence about another.
- Return one entry for EVERY id below, using the id exactly as written.
- confirmed: the evidence genuinely shows this connection exists between these
  two components.
- refuted: the evidence does NOT support this connection (for example the
  snippet is a comment, a string that only resembles a URL, an unrelated match,
  or points at a different target).
- uncertain: the evidence is too thin to decide either way.
- reason MUST cite what in that edge's evidence drove the verdict. Do not
  invent facts not present above. When unsure, say uncertain rather than
  guessing.
"""
    # Each distinct endpoint ships ONCE per call and edges reference it by id.
    # The v2 run's 19 batches shipped 916 endpoint-summary instances covering
    # 133 distinct endpoints, a 6.9x repetition that was about 57% of the
    # pass's input (IMPLEMENTATION-DELTA-ORCH.md section 2.4). Verdicts come
    # back per edge id, so nothing downstream changes.
    endpoints: dict[str, dict] = {}
    for item in items:
        for summary in (item.get("source"), item.get("target")):
            if isinstance(summary, dict) and summary.get("id"):
                # The map key IS the id; repeating it inside the entry is the
                # duplication this diet removes.
                endpoints.setdefault(
                    str(summary["id"]),
                    {k: v for k, v in summary.items() if k != "id"},
                )
    payload = [
        {
            "id": item["id"],
            "edge": {
                "source": (item.get("edge") or {}).get("source"),
                "target": (item.get("edge") or {}).get("target"),
                "type": (item.get("edge") or {}).get("type"),
                "confidence": (item.get("edge") or {}).get("confidence"),
                "evidence": ((item.get("edge") or {}).get("evidence") or [])[:5],
            },
        }
        for item in items
    ]
    return "\n".join([
        "You are verifying INFERRED dependency edges in an architecture graph. "
        "Each was guessed by a static heuristic and may be a false positive. "
        "Using ONLY the evidence and endpoint summaries below, return a verdict "
        "for each edge. Each edge's source and target name an entry in the "
        "ENDPOINTS map; that entry is the endpoint's summary.",
        "",
        contract,
        "",
        "ENDPOINTS:",
        json.dumps(endpoints, indent=2, default=str, sort_keys=True),
        "",
        "EDGES AND EVIDENCE:",
        json.dumps(payload, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ])


def build_concern_name_prompt(concern: dict, member_facts: list[dict]) -> str:
    """Prompt to name a mechanical concern in domain language (P7-4 sub-pass 1)."""
    contract = """\
Return ONLY a single JSON object, no prose, no fences:

{ "name": "a short domain-language name (2-5 words) for this cross-cutting concern",
  "description": "one sentence describing what this concern is and why its members
  are grouped, grounded in the members below" }

RULES:
- The name is the human label for this stratum (for example "Structured Logging",
  "Session Authentication", "Relational Persistence"). Use the domain language a
  reviewer would use, not the mechanical slug.
- Do not invent members or behavior not implied by the facts below.
"""
    payload = {
        "concern_slug": concern.get("id"),
        "kind": concern.get("kind"),
        "mechanical_basis": concern.get("basis"),
        "members": member_facts,
    }
    return "\n".join([
        "You are naming a cross-cutting concern (a set of components that share a "
        "detected concern such as logging or authentication) in domain language.",
        "",
        contract,
        "",
        "CONCERN:",
        json.dumps(payload, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ])


def build_intent_conformance_prompt(intent: dict, scope_facts: dict) -> str:
    """Prompt to evaluate one declared intent against the model (P7-4 sub-pass 2).

    The software reflexion-model pattern: intended architecture (the intent
    statement) versus as-built (the store facts in scope). A violation is
    emitted only when the as-built model contradicts the stated intent, with the
    contradicting members cited.
    """
    contract = """\
Return ONLY a single JSON object, no prose, no fences:

{ "satisfied": true | false,
  "confidence": "high | medium | low",
  "reason": "one to two sentences, grounded in the facts below",
  "violating_members": [ { "component_id": "...", "why": "..." } ] }

RULES:
- satisfied=true when the as-built facts are consistent with the intent. Then
  violating_members is [].
- satisfied=false ONLY when the facts concretely contradict the intent (for
  example the intent says "a single audio pipeline" but the facts show two
  independent pipeline implementations). List each contradicting component in
  violating_members with a short why.
- confidence reflects how strongly the facts ground the verdict. Do not invent
  components or behavior absent from the facts. Prefer satisfied=true with low
  confidence over an unsupported violation.
"""
    payload = {
        "intent": {
            "id": intent.get("id"),
            "statement": intent.get("statement"),
            "scope": intent.get("scope"),
        },
        "as_built": scope_facts,
    }
    return "\n".join([
        "You are checking whether a declared architectural INTENT holds against "
        "the as-built system (the software reflexion-model pattern). Using ONLY "
        "the facts below, decide whether the intent is satisfied or violated.",
        "",
        contract,
        "",
        "INTENT AND AS-BUILT FACTS:",
        json.dumps(payload, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ])


def build_intent_proposal_prompt(observed: dict) -> str:
    """Prompt to PROPOSE candidate intents from docs and observed architecture.

    Proposals are advisory only (P7-4): they land in a report, never auto-adopted;
    a human adopts one by editing the declared-intents file.
    """
    contract = """\
Return ONLY a single JSON object, no prose, no fences:

{ "candidates": [
    { "id": "kebab-case-id",
      "statement": "a single declarative architectural intent, testable against
      the model (for example 'all persistence goes through the repository layer')",
      "basis": "what in the observed facts suggested this" } ] }

RULES:
- Propose at most 8 candidates. Each must be a checkable statement about
  structure, not a vague aspiration.
- Ground every candidate in the observed facts (descriptions, capabilities,
  concerns, edges). Do not invent intents the facts do not suggest.
"""
    return "\n".join([
        "You are PROPOSING candidate architectural intents for human review. "
        "These are advisory: a human will adopt or reject each. Using ONLY the "
        "observed facts below, propose testable intent statements.",
        "",
        contract,
        "",
        "OBSERVED ARCHITECTURE:",
        json.dumps(observed, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ])


def build_finding_verify_prompt(finding: dict) -> str:
    """Prompt to adversarially verify one finding against its own evidence (P7-4
    sub-pass 3): the model is asked to REFUTE the finding, and only findings that
    survive the refutation attempt are marked verified (the DeepWiki lesson)."""
    contract = """\
Return ONLY a single JSON object, no prose, no fences:

{ "verdict": "verified | refuted | uncertain",
  "reason": "one sentence, grounded in the evidence above" }

RULES:
- Your job is to TRY TO REFUTE this finding using only its own evidence.
- verified: you tried and could NOT refute it; the evidence genuinely supports
  the finding.
- refuted: the evidence does not support the finding (wrong, a false positive,
  or the members are not actually related as claimed).
- uncertain: the evidence is too thin to confirm or refute.
- Cite what in the evidence drove the verdict. Do not invent facts.
"""
    payload = {
        "finding": {
            "id": finding.get("id"),
            "kind": finding.get("kind"),
            "summary": finding.get("summary"),
            "members": (finding.get("members") or [])[:20],
            "evidence": (finding.get("evidence") or [])[:20],
        }
    }
    return "\n".join([
        "You are adversarially verifying an automatically-detected finding about "
        "a codebase. Findings that cannot survive a refutation attempt must not "
        "be presented as fact. Using ONLY the finding's own evidence below, "
        "attempt to refute it and return a verdict.",
        "",
        contract,
        "",
        "FINDING:",
        json.dumps(payload, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ])


def build_identify_unknowns_prompt(paths: list[str], categories: list[dict]) -> str:
    """Prompt to identify unknown non-source files as project inventory rules (P6-12).

    The model sees the repo paths that the deterministic classifier could not name
    and the full category vocabulary, and returns gitignore-style rules mapping
    patterns to known categories. These become permanent, deterministic,
    project-local rules, so the unknown bucket trends to zero without any core
    product change. The model NEVER invents a category outside the vocabulary.
    """
    contract = """\
Return ONLY a single JSON object, no prose, no fences:

{ "rules": [
    { "pattern": "a gitignore-style glob that matches the file(s), for example
      '*.pdb', 'coverage/**', or 'Fastlane/report.xml'",
      "category": "EXACTLY one of the category ids listed below",
      "explanation": "one sentence: what this kind of file is and why it is here",
      "recommendation": "one sentence: what the project should do about it",
      "evidence": ["one or more of the exact repo paths above that motivated this rule"] }
  ] }

RULES:
- Use the BROADEST honest pattern (an extension glob or a directory glob) so one
  rule retires many unknowns, but never so broad it would swallow unrelated files.
- When an unknown path IS a directory (a pruned directory row like '.venv' or
  '.wrangler', no file extension, accounted as one row), the pattern must match
  that directory path itself: write '.venv', not '.venv/**'. A contents-only
  glob never matches the directory row and the unknown survives.
- 'category' MUST be one of the ids in CATEGORIES. Do not invent a category.
- Only emit a rule when you are confident what the file is. It is correct to
  return fewer rules than paths, or an empty list, rather than guess.
- No em dashes or en dashes in any text. Use commas and periods.
"""
    payload = {
        "unknown_paths": paths[:200],
        "categories": categories,
    }
    return "\n".join([
        "You are teaching a codebase-analysis tool what its unrecognized "
        "non-source files are. For each kind of file below, propose a durable "
        "classification rule mapping a path pattern to a known category.",
        "",
        contract,
        "",
        "CATEGORIES (id: what it means):",
        json.dumps(categories, indent=2, default=str),
        "",
        "UNKNOWN PATHS:",
        json.dumps(payload["unknown_paths"], indent=2, default=str),
        "",
        "Return the JSON object now.",
    ])


def _index_components(components: list, index: Optional[dict] = None) -> dict:
    if index is None:
        index = {}
    for comp in components:
        cid = comp.get("id")
        if cid:
            index[cid] = comp
        _index_components(comp.get("children", []), index)
    return index


def _group_by(rows: list[dict], key: str) -> dict:
    out: dict[str, list[dict]] = {}
    for row in rows:
        k = row.get(key)
        if k:
            out.setdefault(k, []).append(row)
    return out


def build_identity_verify_prompt(comp: dict, facts: dict) -> str:
    """Prompt to verify one component's published identity claims (S2 gate).

    ``comp`` is the projected component dict; ``facts`` is a compact evidence
    summary (file sample, endpoint sample and count, env vars, config files,
    prose excerpt). The owner's ruling (2026-08-17): identity is resolved or
    flagged, never published as a guess, so the model must confirm each claim,
    correct it with cited evidence, or mark it uncertain for the honest-gaps
    record.
    """
    contract = """\
Return ONLY a single JSON object, no prose, no fences:

{ "fields": {
    "name":      { "status": "confirmed | corrected | uncertain", "value": "...", "reason": "...", "evidence": { "file": "...", "line": 1 } },
    "type":      { ... same shape ... },
    "framework": { ... },
    "port":      { ... }
  },
  "prose_issues": [
    { "claim": "the prose statement", "fact": "the contradicting analyzer fact" }
  ]
}

RULES:
- Judge each field of CLAIMS against the EVIDENCE below, nothing else.
- confirmed: the evidence genuinely supports the claimed value; omit "value",
  "reason", and "evidence".
- corrected: the evidence contradicts the claim and shows what the value
  should be. "value" (the corrected value), "reason" (one sentence), and
  "evidence" (a file from the evidence below, line if known) are REQUIRED.
  For "type", correct toward the neutral end when in doubt: a test suite,
  docs tree, or script collection is "module" or "package", never a server.
- uncertain: the evidence cannot decide. "reason" is REQUIRED. Never guess.
- Every field in CLAIMS must appear in "fields". A field absent from CLAIMS
  (value null) is confirmed-as-absent unless evidence shows a real value.
- prose_issues: list every statement in PROSE whose numbers or facts
  contradict the EVIDENCE (for example a stated endpoint count that differs
  from the actual count). Empty list when the prose is consistent or absent.
"""
    return "\n".join([
        "You are auditing the PUBLISHED IDENTITY of one component in an "
        "architecture map. The static analyzer classified it; wrong "
        "classifications ship in the same confident voice as right ones, so "
        "your verdicts gate what gets published.",
        "",
        contract,
        "",
        "CLAIMS:",
        json.dumps({
            "id": comp.get("id"),
            "name": comp.get("name"),
            "type": comp.get("type"),
            "framework": comp.get("framework"),
            "port": comp.get("port"),
            "language": comp.get("language"),
            "path": comp.get("path"),
        }, indent=2, default=str),
        "",
        "EVIDENCE:",
        json.dumps(facts, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ])


# --- The completeness contract payload (ENRICHMENT-ENGINE.md section 4) -------
#
# The ladder's rungs all answer the SAME questions against the SAME grounding
# rule; only the intelligence applied to them changes. So there is one contract
# block appended to the existing ai_enhance schema, and one prompt builder that
# every rung reuses with a different assignment header. The existing schema is
# untouched: a contract-aware response is a superset of what the bulk pass
# already returns, which is what lets the engine keep stamping the product
# payload exactly as before while the contract scaffolding goes to the store and
# the Run Report instead.

_PARSER_FIRST_INSTRUCTION = """\
FIRST, BEFORE ANYTHING ELSE, ANSWER THIS. For every component you are about to
describe, ask: could deterministic processing have gotten this right without a
model, and how would it do so next time? Record every such observation in
"parser_first". Examples of a real parser-first finding: a framework you inferred
from an import the analyzer did not recognise; a relationship obvious from a
config file nothing parsed; a component type the directory layout already
implied. This list is REQUIRED on every component. An empty list is a legitimate
answer and means you found nothing mechanical; do not invent entries to fill it.
"""

_GROUNDING_RULE = """\
THE GROUNDING RULE, which governs every answer you give:

A claim without evidence you can point at is not an answer. Every answer names
its evidence: a file, a symbol, an edge, a manifest entry, or a doc passage. An
answer you cannot cite is marked "uncertain" with a reason, or "dropped". It is
NEVER left standing bare and it is never dressed up in confident prose.

Evidence items take one of these shapes, and every one of them is checked
mechanically after you answer, against the analyzed file set and the graph:

  {"kind": "file",     "path": "src/x.py", "line": 120}
  {"kind": "symbol",   "path": "src/x.py", "symbol": "UserService", "line": 40}
  {"kind": "edge",     "source": "<component-id>", "target": "<component-id>",
                       "edge_type": "imports"}
  {"kind": "manifest", "path": "package.json"}
  {"kind": "doc",      "path": "README.md", "line": 12}
  {"kind": "fact",     "component": "<component-id>", "field": "inbound_edges"}

CITE AT THE GRANULARITY OF YOUR CLAIM. This is the single most common way a
true answer still fails its check:

- A claim about BEHAVIOUR ("switches between two modes", "filters by domain")
  needs the symbol or the line where that behaviour appears. A bare file
  citation says the file exists, which is not evidence for what it does.
- A claim about a COUNT or an ABSENCE ("17 components depend on this", "no
  outbound edges") needs a "fact" citation naming the field you read it from.
  An edge citation supports the existence of that one edge and says nothing
  about how many there are, or that there are no others.
- A claim drawn from a SYMBOL NAME should cite that symbol, not the file that
  contains it.

An answer whose evidence is weaker than its claim is marked "uncertain" with a
reason. That is a better outcome than a confident sentence with a citation that
does not carry it, and it costs the run far less than being escalated.

Use "fact" when your claim comes from the analyzer's own numbers rather than
from reading code: how many files or lines a component has, how many components
depend on it, its detected language or framework. Those numbers are in the
facts you were given, and a file or an edge cannot carry a statement about
seventeen of them. Cite the field you took the number from. Citable fields:
file_count, lines, inbound_edges, outbound_edges, language, framework,
port, type, capabilities, data_entities, external_services, action_count,
ai_surface, has_testing_data, testing.

Paths must come from the files listed in the facts for that component. A citation
to a file that is not in the analyzed set fails the check, and the answer is
recorded as ungrounded no matter how plausible the claim reads. Citing nothing is
better than citing something you invented: an honest "uncertain" costs the run a
cheap escalation, an invented citation costs it trust.
"""

_CONTRACT_SCHEMA = """\
Each component's ai_enhance block gains ONE extra key, "contract":

"contract": {
  "parser_first": ["..."],
  "answers": {
    "purpose":            {"claim": "...", "status": "answered", "evidence": [...]},
    "mechanism":          {"claim": "...", "status": "answered", "evidence": [...]},
    "place":              {"claim": "...", "status": "answered", "evidence": [...]},
    "identity.type":      {"claim": "...", "status": "answered", "evidence": [...]},
    "identity.framework": {"claim": "...", "status": "answered", "evidence": [...]},
    "identity.port":      {"claim": "...", "status": "answered", "evidence": [...]},
    "identity.language":  {"claim": "...", "status": "answered", "evidence": [...]},
    "next_step":          {"claim": "...", "status": "answered", "evidence": [...]}
  },
  "self_state": "grounded" | "escalate",
  "confusion": null,
  "substitution_check": "the one fact in your answers that could NOT be true of \
any sibling component"
}

THE REQUIRED QUESTIONS, and what each one is actually asking:

- purpose:   What is this for, in the subject's own terms? Not what its name
             says. What job does it do for the system.
- mechanism: How does it do it? The one or two structural facts a reader needs:
             the key types, the central flow.
- place:     What depends on it, what does it depend on, and why does that make
             sense? Cite the edges.
- identity.*: Each identity claim SEPARATELY. type, framework, port and language
             are four distinct claims and each carries its own evidence.
- next_step: Where would a reader go from here, and why? Name the component or
             file, and say what they would learn there.

ANSWER STATUS is exactly one of:
  "answered"  you have a claim and evidence for it
  "uncertain" you have a belief you cannot ground; give the reason
  "dropped"   you have nothing worth saying; give the reason

"answers" MUST contain an entry for every question listed under REQUIRED
QUESTIONS for that component, which the facts block names per component. Do not
answer questions that are not listed for it: a component with no port is not
hiding one.

"confusion" is for the case where you cannot reconcile the code with its
comments, docs or naming. State the specific confusion in one sentence, or leave
it null. Declaring confusion is not failure and it is not penalised. It is the
single most useful thing you can tell the next rung, and a subject whose comments
diverge from its code is a known and expected case.

"substitution_check": name the one fact in your answers that could not be true of
a randomly chosen sibling component. If everything you wrote would fit any
sibling equally well, say so plainly, and set self_state to "escalate": a
description that fits everything describes nothing.

"self_state": your own read, "grounded" if you answered every required question
with evidence you would defend, "escalate" otherwise. Your self-assessment is
recorded, and it is then recomputed independently from your answers and your
citations. Overclaiming does not help you and it does not stay hidden.

Relationships take the reduced form:

"contract": {
  "parser_first": [],
  "answers": {
    "flow": {"claim": "what actually crosses this edge", "status": "answered",
             "evidence": [...]},
    "why":  {"claim": "why this connection exists", "status": "answered",
             "evidence": [...]}
  },
  "self_state": "grounded", "confusion": null
}
"""


def _contract_targets(partition: Partition, facts: StoreFacts) -> list[dict]:
    """Per-component fact blocks with the required question list attached.

    Attaching the question set to each component is what keeps the rung and the
    validator asking the same thing. The set is computed from the same
    deterministic facts ``contract.evaluate`` uses, so a rung that answers exactly
    what it was asked cannot be failed for missing a question it was never given.
    """
    from .contract import required_questions

    out = []
    for cid in partition.answered_component_ids:
        block = facts.component_facts(cid)
        block["REQUIRED_QUESTIONS"] = list(required_questions("component", block))
        out.append(block)
    return out


def _context_only_components(partition: Partition, facts: StoreFacts) -> list[dict]:
    """Component facts a relationship-only call reads but does not answer for.

    Carries no REQUIRED_QUESTIONS, because nothing is being asked about these.
    """
    if partition.answers_components:
        return []
    return [facts.component_facts(cid) for cid in partition.component_ids]


# A marked prompt lets the production CLI put the stable instructions in an
# appended system-prompt file while tests and injected invokers still receive a
# plain string.  The provider can cache the identical prefix across calls; facts
# remain the only per-call user message.
_CACHE_PREFIX_START = "<solution-explorer-system-prefix>\n"
_CACHE_PREFIX_END = "\n</solution-explorer-system-prefix>\n"


def _cached_prompt(prefix: str, user_message: str) -> str:
    return _CACHE_PREFIX_START + prefix.strip() + _CACHE_PREFIX_END + user_message.strip()


def split_cached_prompt(prompt: str) -> tuple[Optional[str], str]:
    """Return (stable prefix, user message), or (None, original prompt)."""
    if not isinstance(prompt, str) or not prompt.startswith(_CACHE_PREFIX_START):
        return None, prompt
    end = prompt.find(_CACHE_PREFIX_END, len(_CACHE_PREFIX_START))
    if end < 0:
        return None, prompt
    prefix = prompt[len(_CACHE_PREFIX_START):end]
    user = prompt[end + len(_CACHE_PREFIX_END):]
    return prefix, user


_COMPACT_COMPONENT_PREFIX = """\
ENRICHMENT TASK: components. Use ONLY the deterministic facts supplied. Never
invent structure. Return ONLY one JSON object, no prose or markdown fences:
COMPONENTS (produce one compact entry per requested id).

{"components":[{"i":"<exact id>","label":"one short 8-15 word tree label",
"purpose":{"t":"complete sentence: what job it does","e":[0]},
"mechanism":{"t":"complete sentence: how it works","e":[[1,"Symbol"]]},
"place":{"t":"complete sentence: how it connects","e":["E0"]},
"why_matters":"complete sentence: why a reader should care",
"next":{"t":"complete sentence: where to go next and why","e":[0]},
"data":"specific data types","criticality":"critical|important|supporting"}],
"relationships":[]}

One entry per id. Generate each meaning ONCE. The coordinator constructs the
3-5 sentence help_text from purpose + mechanism + place + why_matters, uses label
as description, data as data_handled, and uses the same grounded atoms for the
audit contract. Every atom must therefore be clear reader prose, not shorthand.
Optional product fields are:
architectural_role, tech_context, testing_assessment, testing_maturity,
port_assessment, complexity_assessment, external_services_assessment,
actions_summary, key_user_flows. Omit nulls, empties, defaults, and all fields not
listed here.

EVIDENCE uses the target's menus: 2 = file index 2; [2,"Symbol"] = symbol in
that file; [2,120] = line; "E3" = edge index 3; ["F","inbound_edges"] = this
component's own analyzer fact (fields: file_count, lines, inbound_edges,
outbound_edges, language, framework, port, type, capabilities, data_entities,
external_services, action_count, ai_surface, has_testing_data, testing). Use
it for any claim about a count, an absence, or a detected attribute. A full
evidence object is the escape hatch. An answer with t+e is answered by default. If it cannot be
grounded, emit {"t":"best bounded claim","s":"u","r":"why"}; add
"l":"fact","need":"specific missing fact" only when more deterministic context
would settle it, otherwise "l":"judgment". Emit {"s":"d","r":"why"} only when
nothing worth saying exists.

Identity values are parser-owned. Emit only a contradiction as
"id":{"framework":{"v":"correct value","e":[0],"r":"why"}}. Emit
"confusion":"..." only for a real code/docs contradiction, "generic":true only
when the answer fits any sibling, and at most two actionable parser findings as
"pf":["what deterministic processing should learn"].

Criticality: critical means the system cannot function without it; important
means absence degrades it; supporting means leaf UI, tooling, utilities, or
internal wiring. Architectural roles use exactly one of: api-gateway,
auth-service, data-store, cache-layer, queue-processor, event-bus, orchestrator,
worker, proxy, monitoring, logging, scheduler, notification-service,
file-storage, search-engine, ml-pipeline, presentation-layer, business-logic,
data-access.
"""


_COMPACT_RELATIONSHIP_PREFIX = """\
ENRICHMENT TASK: relationships. Use ONLY the supplied edge facts and endpoint
context. Return ONLY one JSON object, no prose or markdown fences:
COMPONENTS (produce none); relationships carry the requested edge work.

{"components":[],"relationships":[{"k":"<exact key>",
"imp":"primary|secondary|internal","flow":{"t":"complete reader-facing
sentence describing what crosses the edge","e":[0]},"why":{"t":"complete
sentence explaining why the connection exists","e":[0]}}]}

One entry per key. flow and why MUST use the compact answer form with one or two
citations into that edge's evidence menu: {"t":"...","e":[0]}. When the
evidence is insufficient, use {"t":"...","s":"u","r":"why",
"l":"fact|judgment","need":"only with fact"}. Omit nulls, empties, status for
answered claims, and fields not shown. The coordinator uses flow.t as both the
reader-facing data_flow_description and the audit claim: generate the meaning
once, then reuse it.
"""


def _brief_prefix(brief: Optional[dict]) -> str:
    if not brief:
        return ""
    return "\nSUBJECT BRIEF:\n" + json.dumps(brief, separators=(",", ":"), default=str)


def build_compact_component_prompt(
    partition: Partition, facts: StoreFacts, *, brief: Optional[dict] = None,
) -> str:
    """Compact/v1 component call: stable instructions plus facts-only user data."""
    components = []
    for cid in partition.answered_component_ids:
        block = facts.component_facts(cid)
        block["edges"] = [
            f"{r.get('source')}->{r.get('target')} ({r.get('type')})"
            for r in facts.component_edge_menu(cid)
        ]
        components.append(block)
    user = "COMPONENTS:\n" + json.dumps(components, separators=(",", ":"), default=str)
    user += "\nReturn the JSON object now."
    return _cached_prompt(_COMPACT_COMPONENT_PREFIX + _brief_prefix(brief), user)


def build_compact_relationship_prompt(
    partition: Partition, facts: StoreFacts, *, brief: Optional[dict] = None,
) -> str:
    """Compact/v1 relationship call with endpoint one-liners, never full facts."""
    endpoint_ids = sorted({
        endpoint
        for key in partition.relationship_keys
        for endpoint in (
            facts.relationship_facts(key).get("source"),
            facts.relationship_facts(key).get("target"),
        )
        if endpoint
    })
    context = []
    for cid in endpoint_ids:
        comp = facts.component_index.get(cid, {})
        context.append({
            key: value for key, value in {
                "id": cid, "name": comp.get("name"), "type": comp.get("type"),
                "language": comp.get("language"), "framework": comp.get("framework"),
                "description": facts.best_description(cid),
            }.items() if value not in (None, "")
        })
    relationships = [facts.relationship_facts(key) for key in partition.relationship_keys]
    user = "CONTEXT:\n" + json.dumps(context, separators=(",", ":"), default=str)
    user += "\nRELATIONSHIPS:\n" + json.dumps(relationships, separators=(",", ":"), default=str)
    user += "\nReturn the JSON object now."
    return _cached_prompt(_COMPACT_RELATIONSHIP_PREFIX + _brief_prefix(brief), user)


_COMPACT_ESCALATION_PREFIX = """\
ESCALATION REPAIR. A cheaper tier already worked every item below. A
mechanical validator rejected specific answers; each item's "failed" list
names which question failed, with a trigger code, the attempted claim, and
the citations that did not check out. You have NO tools: everything you may
use is already in this prompt.

Repair ONLY what "todo" names. Work that passed is finished; re-emitting or
rewording it spends the run's budget on something it already has.

Trigger codes: E1 no usable answer was produced. E2 the evidence did not
check out, or the tier was uncertain. E3 the claim contradicts a
deterministic fact. E4 the answer would fit a sibling equally well. E5 the
tier declared confusion.

Return ONLY one JSON object, no prose, no fences:
{"components":[{"i":"<id>","q":{"<failed question>":{"t":"<repaired claim>",
"e":[<citation>]}}}],
 "relationships":[{"k":"<key>","flow":...,"why":...}]}
Always include both top-level arrays, using [] for the other kind.

Rules:
- Every question in an item's "todo" gets exactly one entry: a repaired claim
  with a citation you can make from THIS item's material, or an honest
  {"t":"best bounded claim","s":"u","r":"why this cannot be grounded at this
  tier"}. On "s":"u" only, add "l":"fact" with "need":"<the concrete missing
  fact: a file, a config, a build step>" when a fact absent from this prompt
  would settle it, otherwise "l":"judgment".
- Citations use the item's menus exactly as the bulk pass does: 2 = file
  index 2; [2,"Symbol"] = that symbol in that file; [2,120] = that line;
  "E3" = edge index 3; ["F","inbound_edges"] = this item's own analyzer
  fact; a full evidence object is the escape hatch. Every citation is
  checked mechanically.
- "established" answers are settled. Do not re-emit them. If one is actually
  WRONG, emit the corrected field or answer directly; the merge takes the
  correction and keeps everything else. Corrections are rare and each one
  needs evidence.
- E3: correct the claim, or flag the detected value via
  "id":{"<field>":{"v":<value or null>,"e":[<citation>],"r":"<one line>"}}.
- E4: make the answer specific to THIS item: name the fact that could not be
  true of a sibling. If you cannot, say so with "s":"u".
- E5: the declared confusion is stated on the item. Resolve it from the
  facts if they allow; otherwise restate it more precisely as
  "confusion":"<one sentence>".
"""


def build_compact_escalation_prompt(
    items: list[dict], *, terminal: bool, brief: Optional[dict] = None,
    assignment: Optional[str] = None,
) -> str:
    # Keep these literal ladder-position markers.  Besides making saved prompts
    # intelligible to an operator, the injectable scripted invokers used by the
    # deterministic test harness distinguish the two escalation behaviours by
    # these phrases.
    prefix = (
        "You are the LAST rung of an enrichment ladder.\n"
        if terminal else
        "You are a HIGHER RUNG of an enrichment ladder.\n"
    ) + _COMPACT_ESCALATION_PREFIX
    if assignment:
        prefix += "\nSCOPED ASSIGNMENT:\n" + assignment.strip()
    if terminal:
        prefix += (
            "\nThere is no rung after you and there is no loop. A TODO you "
            "cannot ground becomes an honest gap:\n"
            "\"gaps\":[{\"q\":\"<question>\",\"why\":\"<one sentence for the "
            "READER of the map: what specifically defeated the attempts>\"}].\n"
            "A gap declared honestly is a correct outcome. A gap papered over "
            "with a plausible sentence is a lie the map tells with confidence. "
            "Never write \"could not be grounded\" as the why; say what was "
            "missing or contradictory."
        )
    user = "ITEMS:\n" + json.dumps(items, default=str)
    user += "\nReturn the JSON object now."
    return _cached_prompt(prefix + _brief_prefix(brief), user)


def build_finding_verify_batch_prompt(findings: list[dict]) -> str:
    """Adversarially verify SEVERAL findings in one call.

    Same economics as the other verify passes: the answer is a verdict and one
    sentence, so a per-item call spends nearly everything on the prompt. The
    refutation stance is unchanged, and each finding is still judged only
    against its own evidence.
    """
    contract = """\
Return ONLY a single JSON object, no prose, no fences:

{ "verdicts": {
    "<finding id, exactly as given>": {
      "verdict": "verified | refuted | uncertain",
      "reason": "one sentence, grounded in that finding's own evidence" },
    ...
} }

RULES:
- TRY TO REFUTE each finding. Only those that survive the attempt are verified.
- Judge every finding INDEPENDENTLY, against its own evidence alone. A verdict
  on one finding is never evidence about another.
- Return one entry for EVERY id below, using the id exactly as written.
- uncertain when the evidence is too thin to decide either way.
"""
    return "\n".join([
        "You are adversarially verifying findings in an architecture analysis. "
        "Each was produced by a heuristic and may be a false positive. Try to "
        "refute each one using ONLY its own evidence below.",
        "",
        contract,
        "",
        "FINDINGS AND EVIDENCE:",
        json.dumps(findings, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ])


def build_identity_verify_batch_prompt(items: list[dict]) -> str:
    """Verify SEVERAL components' published identity claims in one call.

    Same reason as the batched edge verify: the answers are independent and
    small relative to the prompt that has to be re-sent for each one. Measured
    on the 2026-08-25 unamentis-ios run, 111 per-component identity calls cost
    $8.54 for a mean of 292 output tokens each.

    Each item keeps its own id so a partial answer is safe: a component with no
    entry stays unverified rather than adopting another component's verdict.
    """
    contract = """\
Return ONLY a single JSON object, no prose, no fences:

{ "components": {
    "<component id, exactly as given>": {
      "fields": {
        "name":      { "status": "confirmed | corrected | uncertain", "value": "...", "reason": "...", "evidence": { "file": "...", "line": 1 } },
        "type":      { ... same shape ... },
        "framework": { ... },
        "port":      { ... }
      },
      "prose_issues": [
        { "claim": "the prose statement", "fact": "the contradicting analyzer fact" }
      ]
    },
    ...
} }

RULES:
- Judge every component INDEPENDENTLY, using only its own facts.
- Return one entry for EVERY id below, using the id exactly as written.
- Every one of the four fields must be present for every component.
- Do not invent evidence. Where a claim cannot be checked from the facts given,
  say uncertain.
"""
    # Only the identity-bearing fields, exactly as the single-item prompt sends
    # them. Passing the whole projected component dict here (files, docs,
    # children and all) made a batch of twelve exceed the context window on the
    # 2026-08-26 rebuild: a payload that is merely heavy per item becomes fatal
    # when a batch multiplies it.
    payload = [
        {
            "id": item["id"],
            "component": {
                k: (item.get("component") or {}).get(k)
                for k in ("id", "name", "type", "framework", "port", "language")
            },
            "facts": item.get("facts"),
        }
        for item in items
    ]
    return "\n".join([
        "You are verifying the PUBLISHED IDENTITY claims of several components "
        "in an architecture map against the analyzer's own facts. For each "
        "component, say whether each identity field is confirmed, corrected, or "
        "uncertain.",
        "",
        contract,
        "",
        "COMPONENTS AND FACTS:",
        json.dumps(payload, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ])


def build_contract_partition_prompt(
    partition: Partition,
    facts: StoreFacts,
    *,
    assignment: Optional[str] = None,
    brief: Optional[dict] = None,
) -> str:
    """Build the contract-aware enrichment prompt for one partition.

    ``assignment`` replaces the opening instruction so a higher rung can state
    that it is closing named gaps rather than starting fresh. ``brief`` is the P1
    subject brief, which warns the rung about a subject whose comments and code
    diverge so that confusion is expected rather than shameful.
    """
    components = _contract_targets(partition, facts)
    relationships = [facts.relationship_facts(k) for k in partition.relationship_keys]

    head = assignment or (
        "You are enhancing a software architecture graph. Using ONLY the facts "
        "provided (do not invent structure), produce an ai_enhance block for each "
        "component and relationship, and complete the completeness contract for "
        "each one."
    )

    parts = [head, "", _PARSER_FIRST_INSTRUCTION, "", _GROUNDING_RULE, ""]
    if brief:
        parts += [
            "SUBJECT BRIEF (what this system is, who reads the map, and what "
            "matters to them). Written by the orientation pass over the docs and "
            "the deterministic summary. Where it names an idiom or a divergence, "
            "expect it:",
            json.dumps(brief, indent=2, default=str),
            "",
        ]
    parts += [
        _SCHEMA_CONTRACT,
        "",
        _CONTRACT_SCHEMA,
        "",
        "ROLE VOCABULARY (use exact values): " + ", ".join(ROLE_VOCABULARY),
        "",
        _CRITICALITY_GUIDANCE,
        "",
        _FEWSHOT,
        "",
    ]
    if components:
        parts += [
            "COMPONENTS (produce an ai_enhance WITH a contract for every id; "
            "REQUIRED_QUESTIONS on each component tells you exactly what its "
            "contract must answer):",
            json.dumps(components, indent=2, default=str),
            "",
        ]
    context_components = _context_only_components(partition, facts)
    if context_components:
        # Facts to write relationships AGAINST, not work to be done. Said
        # plainly, because a model handed component facts under a schema that
        # describes component contracts will otherwise helpfully produce them,
        # which is the duplication this split exists to remove.
        parts += [
            "COMPONENT CONTEXT (read-only. These components are described by "
            "another call. Use their facts to ground the relationships below. "
            "Do NOT emit component blocks for them):",
            json.dumps(context_components, indent=2, default=str),
            "",
        ]
    parts += [
        "RELATIONSHIPS (produce an ai_enhance with a reduced contract for every key):",
        json.dumps(relationships, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ]
    return "\n".join(parts)


# --- P3 adjudication prompts -------------------------------------------------
#
# Both are read-heavy and near-zero output by design: checking a citation is far
# cheaper than producing one, which is the asymmetry that lets the top of the
# ladder be verified without costing what it cost to write.


def build_grounding_spotcheck_prompt(digest: dict) -> str:
    """Ask whether cited evidence actually SUPPORTS its claim.

    The mechanical validator already proved the citation points at something
    real. It cannot judge sufficiency, and this is the only place that judgment
    happens. The prompt therefore says so explicitly: existence is settled, and
    the only question left is whether the evidence carries the weight of the
    claim.

    The digest carries labels and evidence pointers, never the narrative payload.
    Sending the prose would invite grading the writing instead of the grounding.
    """
    contract = """\
Return ONLY a single JSON object, no prose and no fences:

{
  "checks": [
    {"question": "<the question id from the digest>",
     "supported": true | false,
     "confidence": "high" | "medium" | "low",
     "reason": "one sentence; required when supported is false"}
  ]
}

For each claim below, the cited evidence has ALREADY been verified to exist: the
file is in the analyzed set, the line is inside it, the symbol is in that file,
an "edge" citation names a real edge in the dependency graph, a "manifest" or
"doc" citation points at a real file under the root, and a "fact" citation
names a real field of the analyzer's own output for that component with the
value shown.

A "fact" citation is NOT a bare assertion. It points at the deterministic
analyzer's own data, the same numbers the map is built from, and for a claim
ABOUT that data it is the strongest evidence available. A component whose
analyzer record says outbound_edges: 0 has zero outbound edges; demanding a
file or a symbol to prove an edge COUNT, or to prove an absence, asks for
evidence that cannot exist. Judge such a claim on whether it matches the cited
value, not on whether it also cites a file.

Where a claim goes BEYOND the cited fact, hold it to the usual standard: a fact
citation of file_count supports "ten files" and does not support "ten files
each covering a distinct topic", because the count says nothing about topics.
That is settled and is not what you are being asked.

The only question is SUFFICIENCY: does that evidence actually support that claim?

- supported: false when the evidence is real but does not carry the claim. A
  claim that a component "handles authentication for the whole system" cited
  only to the file's existence is not supported. A claim that it "imports the
  session library" cited to that import is.
- supported: false is the useful answer. You are not grading the writing and you
  are not looking for reasons to agree. If the evidence would not convince a
  reader who checked it, say so.
- Use confidence "low" rather than guessing when you cannot tell from what you
  were given. A low-confidence agreement is recorded as exactly that.
"""
    return "\n".join([
        "You are auditing whether claims about a codebase are actually supported "
        "by the evidence attached to them.",
        "",
        contract,
        "",
        "CLAIMS AND THEIR EVIDENCE:",
        json.dumps(digest, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ])


def build_substitution_prompt(description: str, candidates: list[dict]) -> str:
    """The substitution test: does this description describe anything in particular?

    A description that would fit any sibling equally well describes nothing, and
    the design makes that trigger E4. The bulk rung self-applies the test;
    adjudication applies it independently here, because a self-assessment of
    distinctiveness is exactly the assessment a tier has no incentive to fail.
    """
    contract = """\
Return ONLY a single JSON object, no prose and no fences:

{"choice": "<one id from the candidates, or null>",
 "reason": "one sentence",
 "distinctive": true | false}

Answer null, with distinctive false, when the description would fit more than one
of the candidates. That is not a failure to answer: it is the finding. A
description that fits several components is a description of none of them, and
saying so is more useful than picking the most likely one.
"""
    return "\n".join([
        "Below is a description written about ONE component of a software system, "
        "and a list of candidate components it might be describing. Identify which "
        "one it describes.",
        "",
        contract,
        "",
        "DESCRIPTION:",
        description,
        "",
        "CANDIDATES:",
        json.dumps(candidates, indent=2, default=str),
        "",
        "Return the JSON object now.",
    ])
