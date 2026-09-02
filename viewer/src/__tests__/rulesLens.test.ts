import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import {
  DEFAULT_LENS_ID,
  listAvailableLenses,
  hasRules,
  collectRuleOwnerIds,
  ruleCountsByComponent,
  groupRulesByKind,
  decisionTableFromRule,
  buildRulesGraph,
  ruleEntityId,
  ruleCapabilityId,
} from "../lenses";
import { parseUrlState, replaceUrlState } from "../utils/urlState";
import type { Architecture, Component, DataEntity, Capability, Rule } from "../types";

// P6-6 Rules lens (LENS-DESIGN L6): availability gate, ranked grouping by kind and
// by owning component (I11), per-kind badge counts, decision-table detection,
// the owner graph, cross-lens identity + the two cross-lens jumps (I12), the URL
// round-trip, and reset-on-reload. Exercised against the real store.

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

function rule(overrides: Partial<Rule> & Pick<Rule, "id" | "kind" | "component_id">): Rule {
  return {
    summary: "mechanical summary",
    detail: {},
    evidence: [{ file: "src/x.py", line: 10, snippet: "code" }],
    confidence: "inferred",
    ...overrides,
  };
}

// billing owns 5 rules (2 policy, 1 validation with a capability trigger, 1
// calculation, 1 io with an entity link); web owns 1 policy (a decision-shaped
// switch); orphan owns nothing. The switch is the decision-table case; the
// if/elif chain is a policy rule that is NOT decision-shaped.
function makeRulesArch(): Architecture {
  const billing = makeComponent({ id: "billing", name: "Billing", type: "service" });
  const web = makeComponent({ id: "web", name: "Web", type: "service" });
  const orphan = makeComponent({ id: "orphan", name: "Orphan", type: "module" });

  const rules: Rule[] = [
    rule({
      id: "rule:web:policy:switch-1", kind: "policy", component_id: "web",
      confidence: "certain",
      summary: 'switch zone -> ["a", "b", "c"]',
      detail: { anchor: "switch", inputs: ["zone"], outputs: ['"a"', '"b"', '"c"'] },
      evidence: [{ file: "web/ship.ts", line: 32, snippet: "switch (zone) {" }],
    }),
    rule({
      id: "rule:billing:policy:if-elif-1", kind: "policy", component_id: "billing",
      summary: "multi-branch: if kind == a (+3 branches)",
      detail: { anchor: "if_elif_chain", inputs: ["kind"] },
      evidence: [{ file: "billing/route.py", line: 5, snippet: "if kind == 'a':" }],
    }),
    rule({
      id: "rule:billing:policy:match-1", kind: "policy", component_id: "billing",
      summary: 'match tier -> ["free", "pro"]',
      detail: { anchor: "match", inputs: ["tier"], outputs: ['"free"', '"pro"'] },
      evidence: [{ file: "billing/plan.py", line: 9, snippet: "match tier:" }],
    }),
    rule({
      id: "rule:billing:validation:guard-1", kind: "validation", component_id: "billing",
      summary: "raise ValueError when not email",
      detail: { anchor: "guard_clause", inputs: ["email"], outputs: ["ValueError"], trigger: { capability: "cap:billing:charge" } },
      evidence: [{ file: "billing/api.py", line: 12, snippet: "if not email:" }],
    }),
    rule({
      id: "rule:billing:calculation:formula-1", kind: "calculation", component_id: "billing",
      summary: "total = subtotal + tax",
      detail: { anchor: "formula", inputs: ["subtotal", "tax"], outputs: ["total"] },
      evidence: [{ file: "billing/calc.py", line: 20, snippet: "total = subtotal + tax" }],
    }),
    rule({
      id: "rule:billing:io:sql-column-1", kind: "io", component_id: "billing", confidence: "certain",
      summary: "amount: NOT NULL",
      detail: { anchor: "sql_column", field: "amount", entity: "e:invoice", framework: "sql", outputs: ["NOT NULL"] },
      evidence: [{ file: "billing/schema.sql", line: 3, snippet: "amount INTEGER NOT NULL," }],
    }),
  ];

  const data_entities: DataEntity[] = [
    { id: "e:invoice", name: "Invoice", kind: "table", component_id: "billing", framework: "sql",
      fields: [{ name: "amount", type: "int" }], evidence: [{ file: "billing/schema.sql", line: 1, snippet: "CREATE TABLE invoice" }] },
  ];
  const capabilities: Capability[] = [
    { id: "cap:billing:charge", component_id: "billing", kind: "api", name: "POST /charges",
      detail: { method: "post", path: "/charges", framework: "flask" },
      evidence: [{ file: "billing/api.py", line: 8, snippet: "@app.post('/charges')" }], confidence: "certain" },
  ];

  return makeArchitecture({
    components: [billing, web, orphan],
    relationships: [
      { source: "web", target: "billing", type: "http", label: null, protocol: "http", port: null, bidirectional: false },
      { source: "billing", target: "orphan", type: "import", label: null, protocol: null, port: null, bidirectional: false },
    ],
    rules, data_entities, capabilities,
  });
}

function makeBareArch(): Architecture {
  return makeArchitecture({ components: [makeComponent({ id: "a", name: "A" })] });
}

function resetStore() {
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [],
    drillLevel: null, detailItem: null, activePanel: null,
    lens: DEFAULT_LENS_ID, reviewMode: false, flowEntryId: null, flowStep: 0,
    selectedCapabilityId: null, selectedEntityId: null, selectedRuleId: null, pendingDetailTab: null,
  });
  replaceUrlState({});
}

describe("Rules lens availability (P6-6)", () => {
  beforeEach(resetStore);

  it("is available when the dataset carries rules", () => {
    expect(hasRules(makeRulesArch())).toBe(true);
    expect(listAvailableLenses(makeRulesArch()).map((l) => l.id)).toContain("rules");
  });

  it("is NOT available on a bare dataset (no rules key)", () => {
    const bare = makeBareArch();
    expect(hasRules(bare)).toBe(false);
    expect(listAvailableLenses(bare).map((l) => l.id)).not.toContain("rules");
  });

  it("is NOT available when the rules key is present but empty", () => {
    expect(hasRules(makeArchitecture({ rules: [] }))).toBe(false);
  });

  it("is NOT available when every rule is an unverified inference", () => {
    const inferredOnly = makeRulesArch();
    inferredOnly.rules = inferredOnly.rules?.map((item) => ({ ...item, confidence: "inferred" }));
    expect(hasRules(inferredOnly)).toBe(false);
    expect(listAvailableLenses(inferredOnly).map((lens) => lens.id)).not.toContain("rules");
  });
});

describe("Rules lens ranked grouping (I11, P6-6)", () => {
  beforeEach(resetStore);

  it("groups by kind in RULE_KIND_ORDER, dropping empty kinds", () => {
    const groups = groupRulesByKind(makeRulesArch().rules!);
    expect(groups.map((g) => g.kind)).toEqual(["policy", "validation", "calculation", "io"]);
    expect(groups[0].count).toBe(3); // 2 billing + 1 web policy
  });

  it("within a kind, groups by owning component ranked by rule count", () => {
    const policy = groupRulesByKind(makeRulesArch().rules!)[0];
    // billing enforces 2 policy rules, web 1: billing ranks first (I11).
    expect(policy.components.map((c) => `${c.componentId}:${c.count}`)).toEqual(["billing:2", "web:1"]);
  });

  it("orders rules within a component by evidence file:line then id", () => {
    const policy = groupRulesByKind(makeRulesArch().rules!)[0];
    const billing = policy.components.find((c) => c.componentId === "billing")!;
    // billing/plan.py:9 (match) sorts before billing/route.py:5 (if-elif): "plan" < "route".
    expect(billing.items.map((r) => r.id)).toEqual(["rule:billing:policy:match-1", "rule:billing:policy:if-elif-1"]);
  });

  it("lists rule owners in first-seen order", () => {
    expect(collectRuleOwnerIds(makeRulesArch().rules!)).toEqual(["web", "billing"]);
  });

  it("counts rules per component by kind for the graph badges", () => {
    const counts = ruleCountsByComponent(makeRulesArch().rules!);
    expect(counts.get("billing")).toEqual({ policy: 2, validation: 1, calculation: 1, io: 1 });
    expect(counts.get("web")).toEqual({ policy: 1, validation: 0, calculation: 0, io: 0 });
    expect(counts.has("orphan")).toBe(false);
  });
});

describe("Rules lens decision tables (P6-6, L6)", () => {
  beforeEach(resetStore);

  const rules = () => makeRulesArch().rules!;

  it("renders a switch policy rule as a decision table (subject + branches)", () => {
    const sw = rules().find((r) => r.id === "rule:web:policy:switch-1")!;
    const table = decisionTableFromRule(sw);
    expect(table).not.toBeNull();
    expect(table!.subject).toBe("zone");
    expect(table!.branches).toEqual(['"a"', '"b"', '"c"']);
  });

  it("renders a match policy rule as a decision table too", () => {
    const m = rules().find((r) => r.id === "rule:billing:policy:match-1")!;
    expect(decisionTableFromRule(m)?.branches).toEqual(['"free"', '"pro"']);
  });

  it("does NOT render an if/elif policy rule as a table (no captured branch labels)", () => {
    const ie = rules().find((r) => r.id === "rule:billing:policy:if-elif-1")!;
    expect(decisionTableFromRule(ie)).toBeNull();
  });

  it("does NOT render a non-policy rule as a table", () => {
    const calc = rules().find((r) => r.id === "rule:billing:calculation:formula-1")!;
    expect(decisionTableFromRule(calc)).toBeNull();
  });

  it("requires at least two branches", () => {
    const oneBranch = rule({ id: "r:one", kind: "policy", component_id: "x",
      detail: { anchor: "switch", inputs: ["z"], outputs: ['"only"'] } });
    expect(decisionTableFromRule(oneBranch)).toBeNull();
  });
});

describe("Rules lens graph (P6-6)", () => {
  beforeEach(resetStore);

  it("shows only rule-owning components plus structural edges among them", () => {
    const arch = makeRulesArch();
    const { nodes, edges } = buildRulesGraph(arch);
    // billing and web own rules; orphan does not.
    expect(nodes.map((n) => n.id).sort()).toEqual(["billing", "web"]);
    // web -> billing kept (both owners); billing -> orphan dropped (orphan excluded).
    expect(edges.map((e) => `${e.source}->${e.target}`)).toEqual(["web->billing"]);
  });

  it("getLensGraph returns the owner graph under the rules lens", () => {
    const arch = makeRulesArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("rules");
    const g = useArchStore.getState().getLensGraph();
    expect(g.nodes.map((n) => n.id).sort()).toEqual(["billing", "web"]);
  });
});

describe("Rules lens selection and identity (I12, P6-6)", () => {
  beforeEach(resetStore);

  it("selecting a rule selects its owning component", () => {
    const arch = makeRulesArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("rules");
    useArchStore.getState().selectRule("rule:billing:io:sql-column-1");
    const s = useArchStore.getState();
    expect(s.selectedRuleId).toBe("rule:billing:io:sql-column-1");
    expect(s.selectedComponentId).toBe("billing");
  });

  it("preserves the selected component when switching lens (I12)", () => {
    const arch = makeRulesArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("rules");
    useArchStore.getState().selectRule("rule:billing:calculation:formula-1");
    useArchStore.getState().setLens("structure");
    expect(useArchStore.getState().selectedComponentId).toBe("billing");
    expect(useArchStore.getState().selectedRuleId).toBe("rule:billing:calculation:formula-1");
  });

  it("round-trips ?lens=rules&rule= through the URL, and gates the param by lens", () => {
    replaceUrlState({ lens: "rules", rule: "rule:web:policy:switch-1", component: "web" });
    const parsed = parseUrlState();
    expect(parsed.lens).toBe("rules");
    expect(parsed.rule).toBe("rule:web:policy:switch-1");
    expect(parsed.component).toBe("web");
    // The rule param is dropped under a different lens.
    replaceUrlState({ lens: "structure", rule: "rule:web:policy:switch-1" });
    expect(parseUrlState().rule).toBeUndefined();
  });

  it("resets rule selection on architecture reload", () => {
    useArchStore.getState().setArchitecture(makeRulesArch());
    useArchStore.getState().selectRule("rule:web:policy:switch-1");
    expect(useArchStore.getState().selectedRuleId).toBe("rule:web:policy:switch-1");
    useArchStore.getState().setArchitecture(makeRulesArch());
    expect(useArchStore.getState().selectedRuleId).toBeNull();
  });
});

describe("Rules lens cross-lens jumps (L6, I12, P6-6)", () => {
  beforeEach(resetStore);

  it("jumps a rule with an entity link to the Data lens with that entity focused", () => {
    const arch = makeRulesArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("rules");
    const jumped = useArchStore.getState().viewRuleInDataLens("rule:billing:io:sql-column-1");
    expect(jumped).toBe(true);
    const s = useArchStore.getState();
    expect(s.lens).toBe("data");
    expect(s.selectedEntityId).toBe("e:invoice");
    // Identity preserved: the entity's owning component is selected (I12).
    expect(s.selectedComponentId).toBe("billing");
  });

  it("is a no-op (returns false) for a rule with no entity link", () => {
    const arch = makeRulesArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("rules");
    expect(useArchStore.getState().viewRuleInDataLens("rule:web:policy:switch-1")).toBe(false);
    expect(useArchStore.getState().lens).toBe("rules");
  });

  it("jumps a rule with a capability trigger to the Capability lens with that capability selected", () => {
    const arch = makeRulesArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("rules");
    const jumped = useArchStore.getState().viewRuleInCapabilityLens("rule:billing:validation:guard-1");
    expect(jumped).toBe(true);
    const s = useArchStore.getState();
    expect(s.lens).toBe("capability");
    expect(s.selectedCapabilityId).toBe("cap:billing:charge");
    expect(s.selectedComponentId).toBe("billing");
  });

  it("is a no-op (returns false) for a rule with no capability trigger", () => {
    const arch = makeRulesArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("rules");
    expect(useArchStore.getState().viewRuleInCapabilityLens("rule:billing:calculation:formula-1")).toBe(false);
    expect(useArchStore.getState().lens).toBe("rules");
  });

  it("exposes a rule's entity and capability links via the helpers", () => {
    const rules = makeRulesArch().rules!;
    const io = rules.find((r) => r.id === "rule:billing:io:sql-column-1")!;
    const guard = rules.find((r) => r.id === "rule:billing:validation:guard-1")!;
    const calc = rules.find((r) => r.id === "rule:billing:calculation:formula-1")!;
    expect(ruleEntityId(io)).toBe("e:invoice");
    expect(ruleCapabilityId(guard)).toBe("cap:billing:charge");
    expect(ruleEntityId(calc)).toBeNull();
    expect(ruleCapabilityId(calc)).toBeNull();
  });
});

describe("Rules lens backward compatibility (P6-6)", () => {
  beforeEach(resetStore);

  it("a dataset with no rules key shows no Rules lens and getRules is empty", () => {
    useArchStore.getState().setArchitecture(makeBareArch());
    expect(useArchStore.getState().getRules()).toEqual([]);
    expect(listAvailableLenses(makeBareArch()).map((l) => l.id)).not.toContain("rules");
  });
});
