import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import { RULE_QUESTIONS, groupRulesByKind, decisionTableFromRule } from "../lenses";
import type { Architecture, Component, DataEntity, Capability, Rule } from "../types";

// I14: the Rules lens ships a documented question list, and every question's
// gesture is exercised here against the real store with an asserted answer. The
// five questions map to LENS-DESIGN L6: where decisions live (ranked kinds), what
// this component enforces (component grouping), what governs this data (entity
// cross-link jump), what guards this contract (capability cross-link jump), and
// how sure we are (confidence marking).

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "c", name: "C", type: "module", path: "src/c", language: "python",
    framework: null, description: null, port: null, children: [], files: ["src/c/i.py"],
    entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { python: 100 } },
    docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
    ...overrides,
  };
}

function makeArchitecture(overrides: Partial<Architecture> = {}): Architecture {
  return {
    name: "T", description: "", repository: null, generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0", root_path: "/t", components: [], relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    ...overrides,
  };
}

function seed(): void {
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [], drillLevel: null, detailItem: null, activePanel: null, lens: "structure",
    selectedCapabilityId: null, selectedEntityId: null, selectedRuleId: null, pendingDetailTab: null,
  });
  const billing = makeComponent({ id: "billing", name: "Billing", type: "service" });
  const web = makeComponent({ id: "web", name: "Web", type: "service" });
  const rules: Rule[] = [
    { id: "rule:billing:policy:switch-1", kind: "policy", component_id: "billing",
      summary: 'switch tier -> ["free", "pro"]',
      detail: { anchor: "switch", inputs: ["tier"], outputs: ['"free"', '"pro"'] },
      evidence: [{ file: "billing/plan.py", line: 3, snippet: "match tier:" }], confidence: "inferred" },
    { id: "rule:billing:validation:guard-1", kind: "validation", component_id: "billing",
      summary: "raise ValueError when not email",
      detail: { anchor: "guard_clause", inputs: ["email"], outputs: ["ValueError"], trigger: { capability: "cap:billing:charge" } },
      evidence: [{ file: "billing/api.py", line: 12, snippet: "if not email:" }], confidence: "inferred" },
    { id: "rule:billing:io:sql-1", kind: "io", component_id: "billing",
      summary: "amount: NOT NULL",
      detail: { anchor: "sql_column", field: "amount", entity: "e:invoice", outputs: ["NOT NULL"] },
      evidence: [{ file: "billing/schema.sql", line: 3, snippet: "amount INTEGER NOT NULL," }], confidence: "certain" },
    { id: "rule:web:policy:if-1", kind: "policy", component_id: "web",
      summary: "multi-branch: if x (+2 branches)",
      detail: { anchor: "if_elif_chain", inputs: ["x"] },
      evidence: [{ file: "web/r.ts", line: 1, snippet: "if (x)" }], confidence: "inferred" },
  ];
  const data_entities: DataEntity[] = [
    { id: "e:invoice", name: "Invoice", kind: "table", component_id: "billing", framework: "sql",
      fields: [{ name: "amount", type: "int" }], evidence: [{ file: "billing/schema.sql", line: 1, snippet: "CREATE TABLE" }] },
  ];
  const capabilities: Capability[] = [
    { id: "cap:billing:charge", component_id: "billing", kind: "api", name: "POST /charges",
      detail: { method: "post", path: "/charges" },
      evidence: [{ file: "billing/api.py", line: 8, snippet: "@app.post" }], confidence: "certain" },
  ];
  useArchStore.getState().setArchitecture(makeArchitecture({ components: [billing, web], rules, data_entities, capabilities }));
  useArchStore.getState().setLens("rules");
}

const gestures: Record<string, () => void> = {
  "where-decisions-live": () => {
    seed();
    // Ranked kinds: policy leads, and each group carries a count.
    const groups = groupRulesByKind(useArchStore.getState().getRules());
    expect(groups.map((g) => g.kind)).toEqual(["policy", "validation", "io"]);
    expect(groups[0].kind).toBe("policy");
    expect(groups[0].count).toBe(2);
  },
  "what-enforces": () => {
    seed();
    // The policy group subgroups by owning component; billing enforces 1 policy,
    // web 1: tie, sorted by id -> billing first, and the component grouping is present.
    const policy = groupRulesByKind(useArchStore.getState().getRules())[0];
    expect(policy.components.map((c) => c.componentId)).toEqual(["billing", "web"]);
    // The io group is enforced by billing.
    const io = groupRulesByKind(useArchStore.getState().getRules()).find((g) => g.kind === "io")!;
    expect(io.components[0].componentId).toBe("billing");
  },
  "governs-data": () => {
    seed();
    // The io rule governs a data entity; the jump lands on the Data lens focused
    // on that entity (the L3 cross-link).
    const jumped = useArchStore.getState().viewRuleInDataLens("rule:billing:io:sql-1");
    expect(jumped).toBe(true);
    expect(useArchStore.getState().lens).toBe("data");
    expect(useArchStore.getState().selectedEntityId).toBe("e:invoice");
  },
  "guards-contract": () => {
    seed();
    // The validation rule guards a capability; the jump lands on the Capability
    // lens with that capability selected (the L2 cross-link).
    const jumped = useArchStore.getState().viewRuleInCapabilityLens("rule:billing:validation:guard-1");
    expect(jumped).toBe(true);
    expect(useArchStore.getState().lens).toBe("capability");
    expect(useArchStore.getState().selectedCapabilityId).toBe("cap:billing:charge");
  },
  "how-sure": () => {
    seed();
    const rules = useArchStore.getState().getRules();
    // The schema-declared io rule is certain; the shape-matched guard is inferred.
    expect(rules.find((r) => r.id === "rule:billing:io:sql-1")!.confidence).toBe("certain");
    expect(rules.find((r) => r.id === "rule:billing:validation:guard-1")!.confidence).toBe("inferred");
    // And the decision-shaped switch renders as a table, the mechanical branching view.
    expect(decisionTableFromRule(rules.find((r) => r.id === "rule:billing:policy:switch-1")!)).not.toBeNull();
  },
};

describe("Rules lens question gestures (I14)", () => {
  beforeEach(seed);

  for (const q of RULE_QUESTIONS) {
    it(`answers "${q.question}" via its gesture`, () => {
      expect(gestures[q.id], `no gesture wired for question "${q.id}"`).toBeTypeOf("function");
      gestures[q.id]();
    });
  }

  it("covers every documented question with a gesture", () => {
    expect(Object.keys(gestures).sort()).toEqual(RULE_QUESTIONS.map((q) => q.id).sort());
  });
});
