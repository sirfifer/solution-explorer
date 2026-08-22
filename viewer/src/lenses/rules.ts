/**
 * Rules lens (P6-6, LENS-DESIGN.md section 4 L6): "Where do the decisions live?"
 *
 * A rule is a discrete unit of decision or constraint logic, operationally typed:
 * policy (a permission gate or decision-table-shaped branch), validation (an
 * input or precondition check), calculation (a domain formula), or io (a declared
 * field bound or format constraint). This is the lens that lets a business-side-
 * technical reader audit what the system actually enforces, drilling every rule
 * to the exact lines and cross-linking a rule to the data it governs (L3) and the
 * capability it guards (L2).
 *
 * The lens lands on a ranked panel (I11: rank, do not just render) grouping rules
 * by kind with counts, each group expandable; within a kind, rules group by owning
 * component ranked by rule count, so "what does this component enforce" reads
 * directly. The graph is the spatial complement: the rule-owning components with
 * per-kind rule-count badges. Selecting a rule selects its owning component (I12
 * stable identity). A rule with an entity link jumps to the Data lens; a rule with
 * a capability trigger jumps to the Capability lens (both preserve identity and
 * URL state). The ranking, grouping, and decision-table math lives here so it is
 * testable in isolation; selection and the cross-lens jumps live in the store.
 *
 * The deterministic engine emits the MECHANICAL summary (invariant I1); the plain-
 * language statement is Phase 7 enrichment (rule.ai_enhance.statement), rendered
 * in a clearly-shaped slot that lights up when enrichment lands, with a staleness
 * marker per invariant I5.
 *
 * Availability gates on rule data (isAvailable): a dataset with no rules (a bare
 * architecture, old data) never shows the lens.
 */
import type { Architecture, Component, Relationship, Rule } from "../types";
import { collectComponentsByIds } from "../utils/collectComponents";
import { registerLens, type LensDefinition, type LensQuestion } from "./registry";

// The kinds in the order the panel and the graph present them: decisions and
// constraints most likely to carry business meaning first (policy, validation),
// then calculation and io. This is the ranking of "where do decisions live".
export const RULE_KIND_ORDER: Rule["kind"][] = ["policy", "validation", "calculation", "io"];

// The policy anchors whose detail carries decision-shaped branches (a subject and
// its case labels), which render as a decision table rather than a summary string.
export const DECISION_ANCHORS = new Set(["switch", "match", "case_when"]);

// True when the dataset carries any rule. Absence hides the lens.
export function hasRules(arch: Architecture): boolean {
  return (arch.rules?.length ?? 0) > 0;
}

// The Data-lens (L3) cross-link target of a rule: the entity whose field an io
// rule constrains, or null when the rule governs no declared entity.
export function ruleEntityId(rule: Rule): string | null {
  return rule.detail.entity ?? null;
}

// The Capability-lens (L2) cross-link target of a rule: the capability this rule
// fires under (its trigger context is a capability's defining symbol), or null.
export function ruleCapabilityId(rule: Rule): string | null {
  return rule.detail.trigger?.capability ?? null;
}

// The distinct component ids that own at least one rule, in first-seen order over
// the rule list (deterministic, matches projection order).
export function collectRuleOwnerIds(rules: Rule[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const r of rules) {
    if (r.component_id && !seen.has(r.component_id)) {
      seen.add(r.component_id);
      out.push(r.component_id);
    }
  }
  return out;
}

// Per-component rule counts by kind, for the graph node badges. Only components
// that own a rule appear in the map.
export type RuleKindCounts = Record<Rule["kind"], number>;

export function ruleCountsByComponent(rules: Rule[]): Map<string, RuleKindCounts> {
  const map = new Map<string, RuleKindCounts>();
  for (const r of rules) {
    if (!r.component_id) continue;
    let counts = map.get(r.component_id);
    if (!counts) {
      counts = { policy: 0, validation: 0, calculation: 0, io: 0 };
      map.set(r.component_id, counts);
    }
    counts[r.kind] += 1;
  }
  return map;
}

// One owning component's rules within a kind group. `count` is the group size,
// the rank key (a component enforcing more rules of a kind sorts first).
export interface RuleComponentGroup {
  componentId: string;
  count: number;
  items: Rule[];
}

// One ranked group of rules of a single kind (I11 landing), subgrouped by owning
// component ranked by rule count (most-enforcing component first). This answers
// both "where do decisions live" (the kind ranking) and "what does this component
// enforce" (the component subgrouping). Deterministic: component groups tie-break
// by id; rules within a component sort by evidence file:line then id.
export interface RuleKindGroup {
  kind: Rule["kind"];
  count: number;
  components: RuleComponentGroup[];
}

function ruleSortKey(rule: Rule): [string, number, string] {
  const ev = rule.evidence[0];
  return [ev?.file ?? "", ev?.line ?? 0, rule.id];
}

function compareRules(a: Rule, b: Rule): number {
  const [fa, la, ia] = ruleSortKey(a);
  const [fb, lb, ib] = ruleSortKey(b);
  if (fa !== fb) return fa.localeCompare(fb);
  if (la !== lb) return la - lb;
  return ia.localeCompare(ib);
}

export function groupRulesByKind(rules: Rule[]): RuleKindGroup[] {
  return RULE_KIND_ORDER.map((kind) => {
    const ofKind = rules.filter((r) => r.kind === kind);
    // Bucket by owning component (unowned rules bucket under "").
    const byComponent = new Map<string, Rule[]>();
    for (const r of ofKind) {
      const owner = r.component_id ?? "";
      const list = byComponent.get(owner);
      if (list) list.push(r);
      else byComponent.set(owner, [r]);
    }
    const components: RuleComponentGroup[] = [...byComponent.entries()]
      .map(([componentId, items]) => ({
        componentId,
        count: items.length,
        items: [...items].sort(compareRules),
      }))
      .sort((a, b) => {
        if (a.count !== b.count) return b.count - a.count;
        return a.componentId.localeCompare(b.componentId);
      });
    return { kind, count: ofKind.length, components };
  }).filter((g) => g.count > 0);
}

// A decision table derived from a policy rule's decision-shaped detail: the
// switched subject plus one row per case label. The extractor (P5-5) records the
// subject in `inputs` and the branch labels in `outputs` for switch/match/
// case_when anchors; it does not capture each branch's body, so the table's
// outcome is the branch case value until Phase 7 enrichment supplies the action.
// Returns null for rules that are not decision-shaped (guard clauses, if/elif
// chains with no captured labels, permission gates, and every non-policy kind),
// which render their mechanical summary instead.
export interface RuleDecisionTable {
  subject: string;
  branches: string[];
}

export function decisionTableFromRule(rule: Rule): RuleDecisionTable | null {
  if (rule.kind !== "policy") return null;
  const anchor = rule.detail.anchor;
  if (!anchor || !DECISION_ANCHORS.has(anchor)) return null;
  const inputs = rule.detail.inputs ?? [];
  const branches = rule.detail.outputs ?? [];
  if (inputs.length === 0 || branches.length < 2) return null;
  return { subject: inputs.join(", "), branches };
}

// The graph selection: the rule-owning components (globally, across the whole
// tree) plus the structural relationships among them, with per-kind rule-count
// badges attached by ArchitectureGraph. Non-owners are not drawn; the ranked
// panel is the entry point, never a hairball (I11). Parallel to the Capability
// lens graph.
export function buildRulesGraph(arch: Architecture): {
  nodes: Component[];
  edges: Relationship[];
} {
  const ownerIds = new Set(collectRuleOwnerIds(arch.rules ?? []));
  const nodes = collectComponentsByIds(arch.components, ownerIds);
  const edges = arch.relationships.filter(
    (r) => ownerIds.has(r.source) && ownerIds.has(r.target),
  );
  return { nodes, edges };
}

// The Rules question list (I14). Every id is exercised in rulesQuestions.test.
export const RULE_QUESTIONS: LensQuestion[] = [
  {
    id: "where-decisions-live",
    question: "Where do the decisions live?",
    gesture:
      "Open the Rules lens: rules are grouped by kind (policy, validation, calculation, io) with counts, ranked so the decision-bearing kinds lead.",
  },
  {
    id: "what-enforces",
    question: "What does this component enforce?",
    gesture:
      "Expand a kind: rules group by owning component ranked by rule count, so the components enforcing the most rules of a kind read first.",
  },
  {
    id: "governs-data",
    question: "What governs this data?",
    gesture:
      "Select an io rule with an entity link and use 'view in Data lens': it jumps to the Data lens with that entity focused (the L3 cross-link).",
  },
  {
    id: "guards-contract",
    question: "What guards this contract?",
    gesture:
      "Select a rule that fires under a capability and use 'view in Capability lens': it jumps to the Capability lens with that capability selected (the L2 cross-link).",
  },
  {
    id: "how-sure",
    question: "How sure are we about this rule?",
    gesture:
      "Read the inferred marker: a declared validator or schema constraint is certain; a shape-matched guard, formula, or branch is marked inferred (I3).",
  },
];

export const rulesLens: LensDefinition = {
  id: "rules",
  label: "Rules",
  description:
    "Where the decisions live: the policies, validations, calculations, and io constraints the system enforces, each drilled to its lines.",
  isAvailable: hasRules,
  // The graph shows the rule-owning components with per-kind rule-count badges;
  // the ranked grouping and rule detail live in RulesPanel. Structure is untouched.
  getGraph: (ctx) => {
    const { nodes, edges } = buildRulesGraph(ctx.architecture);
    return { nodes, aggregates: [], edges };
  },
  questions: RULE_QUESTIONS,
};

registerLens(rulesLens);
