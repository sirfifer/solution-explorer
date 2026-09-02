import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore, nodeBudgetForCanvas, DEFAULT_NODE_BUDGET } from "../store";
import type { Architecture, Component } from "../types";

// Owner decision 2026-08-17: visibility is decided by IMPORTANCE, not file
// count, and how many nodes are shown adjusts to the viewport ("If we are on an
// iphone, it should be appropriate to that. If I'm on a computer with a 40" 4k
// monitor it is another extreme"). Before this, a mechanical "fewer than 10
// files" rule buried 31 modules of the UnaMentis iOS client behind one box, ten
// of them tagged critical.

function comp(over: Partial<Component> & { id: string }): Component {
  return {
    name: over.id, type: "module", path: `src/${over.id}`, language: "swift",
    framework: null, description: null, port: null, children: [], files: ["a.swift"],
    entry_points: [], config_files: [],
    metrics: { files: 1, lines: 10, size_bytes: 10, symbols: 1, languages: {} },
    docs: {
      readme: null, claude_md: null, changelog: null, api_docs: null,
      architecture_notes: null, purpose: null, key_decisions: [], patterns: [],
      tech_stack: [], env_vars: [], api_endpoints: [],
    },
    ...over,
  } as Component;
}

function withFiles(id: string, n: number, extra: Partial<Component> = {}): Component {
  return comp({ id, files: Array.from({ length: n }, (_, i) => `${id}/f${i}.swift`), ...extra });
}

const CRITICAL = { criticality: "critical" as const };
const SUPPORTING = { criticality: "supporting" as const };

// A client with one hero child and many small modules, the UnaMentis shape.
function architecture(): Architecture {
  const kids: Component[] = [
    comp({ id: "TabBar", type: "tab-container" }),
    // Small but critical: the old rule hid every one of these.
    withFiles("Voice", 4, { ai_enhance: CRITICAL }),
    withFiles("STT", 9, { ai_enhance: CRITICAL }),
    withFiles("Session", 3, { ai_enhance: CRITICAL }),
    // Large but unimportant: the old rule always showed this.
    withFiles("Settings", 12, { ai_enhance: SUPPORTING }),
    withFiles("Debug", 8, { ai_enhance: SUPPORTING }),
    withFiles("Views", 6, { ai_enhance: SUPPORTING }),
    withFiles("Tools", 5, { ai_enhance: SUPPORTING }),
  ];
  const client = comp({ id: "app", name: "App", type: "ios-client", children: kids, files: [] });
  return {
    name: "T", description: "", repository: null, generated_at: "2026-01-01T00:00:00Z",
    analyzer_version: "1.2.0", root_path: "/t", components: [client],
    relationships: [], symbols: [], files: [],
    stats: {
      total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {},
      total_symbols: 0, total_components: 9, total_relationships: 0,
    },
  } as Architecture;
}

function visibleAt(budget: number): { shown: string[]; aggregated: number } {
  useArchStore.setState({ nodeBudget: budget, drillLevel: "app" });
  const shown = useArchStore.getState().getVisibleComponents().map((c) => c.name);
  const aggs = useArchStore.getState().getAggregateNodes();
  return { shown, aggregated: aggs.reduce((n, a) => n + a.memberCount, 0) };
}

beforeEach(() => {
  useArchStore.setState({
    architecture: architecture(), drillLevel: "app", selectedComponentId: null, detailItem: null, activePanel: null,
    nodeBudget: DEFAULT_NODE_BUDGET, lens: "structure",
  });
});

describe("nodeBudgetForCanvas: the budget follows the viewport", () => {
  it("gives a phone a small budget and a large display a much bigger one", () => {
    const phone = nodeBudgetForCanvas(390, 600);
    const laptop = nodeBudgetForCanvas(1184, 760);
    const bigDisplay = nodeBudgetForCanvas(3400, 1900);
    expect(phone).toBeLessThan(laptop);
    expect(laptop).toBeLessThan(bigDisplay);
  });

  it("never returns an unusable or incomprehensible number", () => {
    expect(nodeBudgetForCanvas(200, 200)).toBeGreaterThanOrEqual(6);
    expect(nodeBudgetForCanvas(10000, 10000)).toBeLessThanOrEqual(40);
    expect(nodeBudgetForCanvas(0, 0)).toBe(DEFAULT_NODE_BUDGET);
  });

  it("shrinks when the detail panel takes canvas width", () => {
    // The measured widths from the real app: 1184 with the panel closed, 864 open.
    expect(nodeBudgetForCanvas(864, 760)).toBeLessThanOrEqual(nodeBudgetForCanvas(1184, 760));
  });
});

describe("ranking: importance decides visibility, not file count", () => {
  it("shows small critical modules and aggregates large unimportant ones", () => {
    // Budget 4 = the hero plus three slots, exactly the three criticals.
    const { shown, aggregated } = visibleAt(4);
    // All three criticals are on the canvas despite holding only 3-9 files;
    // the old size rule hid every one of them.
    expect(shown).toEqual(expect.arrayContaining(["Voice", "STT", "Session"]));
    // The 12-file supporting module lost its place to them. Under the old rule
    // it was always shown and they never were.
    expect(shown).not.toContain("Settings");
    expect(aggregated).toBe(4);
  });

  it("spends leftover room on the best of the rest, largest first", () => {
    // One slot beyond the criticals: the biggest supporting module takes it.
    const { shown } = visibleAt(5);
    expect(shown).toContain("Settings");
    expect(shown).not.toContain("Tools");
  });

  it("always shows hero-typed children regardless of budget", () => {
    const { shown } = visibleAt(1);
    expect(shown).toContain("TabBar");
  });

  it("pins the URL-selected component before spending the remaining budget", () => {
    useArchStore.setState({ selectedComponentId: "Tools" });
    const { shown } = visibleAt(4);
    expect(shown).toContain("Tools");
    expect(useArchStore.getState().getAggregateNodes().flatMap((group) => group.members.map((member) => member.id)))
      .not.toContain("Tools");
  });

  it("shows more when the viewport allows more, and nothing is lost", () => {
    const tight = visibleAt(5);
    const roomy = visibleAt(20);
    expect(roomy.shown.length).toBeGreaterThan(tight.shown.length);
    expect(roomy.aggregated).toBe(0);
    // Nothing vanishes: shown + aggregated always accounts for every child.
    expect(tight.shown.length + tight.aggregated).toBe(8);
    expect(roomy.shown.length + roomy.aggregated).toBe(8);
  });
});

describe("expansion opens a list, never more canvas nodes", () => {
  it("toggleAggregate opens the member list in the detail panel", () => {
    visibleAt(5);
    const agg = useArchStore.getState().getAggregateNodes()[0];
    const before = useArchStore.getState().getVisibleComponents().length;
    useArchStore.getState().toggleAggregate(agg.id);
    const state = useArchStore.getState();
    expect(state.detailItem?.type).toBe("aggregate");
    expect(state.activePanel).toBe("detail");
    // The canvas is untouched: this is what prevents the 45-node speck field.
    expect(state.getVisibleComponents().length).toBe(before);
  });

  it("toggling the same aggregate again closes the panel", () => {
    visibleAt(5);
    const agg = useArchStore.getState().getAggregateNodes()[0];
    useArchStore.getState().toggleAggregate(agg.id);
    useArchStore.getState().toggleAggregate(agg.id);
    expect(useArchStore.getState().detailItem).toBeNull();
  });
});
