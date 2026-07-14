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
from typing import Optional

from .partition import Partition

__all__ = [
    "StoreFacts",
    "build_partition_prompt",
    "build_architecture_prompt",
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
        self.entities_by_comp = _group_by(data_entities, "component_id")
        self.rules_by_comp = _group_by(rules, "component_id")
        self._rel_by_key = {
            f"{r.get('source','')}|{r.get('target','')}|{r.get('type','')}": r
            for r in relationships
        }
        self._inbound: dict[str, int] = {}
        self._outbound: dict[str, int] = {}
        for r in relationships:
            s, t = r.get("source", ""), r.get("target", "")
            if s:
                self._outbound[s] = self._outbound.get(s, 0) + 1
            if t:
                self._inbound[t] = self._inbound.get(t, 0) + 1

    def component_facts(self, comp_id: str) -> dict:
        """A compact, JSON-serializable fact block for one component."""
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
