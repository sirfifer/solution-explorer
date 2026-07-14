import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import {
  registerLens,
  getLens,
  listAvailableLenses,
  resolveLensId,
  DEFAULT_LENS_ID,
  type LensDefinition,
} from "../lenses";
import type { Architecture, Component } from "../types";

// P6-1 lens framework: registry + default, pixel-identical Structure selection,
// I12 (identity survives a lens switch), I11 (ranked drill ordering preserved).

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "c", name: "C", type: "module", path: "src/c", language: "typescript",
    framework: null, description: null, port: null, children: [], files: ["src/c/i.ts"],
    entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { typescript: 100 } },
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

// A second lens registered only for the tests, to prove cross-lens identity
// preservation (I12). It intentionally returns a different node selection so a
// switch is observable.
const testLens: LensDefinition = {
  id: "test-lens",
  label: "Test",
  description: "test",
  isAvailable: () => true,
  getGraph: () => ({ nodes: [], aggregates: [], edges: [] }),
  questions: [],
};
registerLens(testLens);

describe("lens registry (P6-1)", () => {
  beforeEach(() => {
    useArchStore.setState({
      architecture: null, selectedComponentId: null, breadcrumbs: [],
      drillLevel: null, expandedAggregates: {}, lens: DEFAULT_LENS_ID,
    });
  });

  it("registers Structure as the default lens", () => {
    expect(useArchStore.getState().lens).toBe("structure");
    expect(getLens("structure")?.label).toBe("Structure");
    expect(resolveLensId(undefined, null)).toBe("structure");
  });

  it("lists the lenses available for a dataset", () => {
    const arch = makeArchitecture();
    const ids = listAvailableLenses(arch).map((l) => l.id);
    expect(ids).toContain("structure");
    expect(ids).toContain("test-lens");
  });

  it("falls back to Structure for an unknown lens id", () => {
    const arch = makeArchitecture({ components: [makeComponent({ id: "a" })] });
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("does-not-exist");
    expect(useArchStore.getState().lens).toBe("structure");
  });

  it("Structure lens selection equals the existing store selectors (pixel-identical)", () => {
    const a = makeComponent({ id: "a", name: "A" });
    const b = makeComponent({ id: "b", name: "B" });
    const arch = makeArchitecture({
      components: [a, b],
      relationships: [{ source: "a", target: "b", type: "import", label: null, protocol: null, port: null, bidirectional: false }],
    });
    useArchStore.getState().setArchitecture(arch);

    const g = useArchStore.getState().getLensGraph();
    const nodesById = g.nodes.map((n) => n.id);
    const directNodes = useArchStore.getState().getVisibleComponents().map((n) => n.id);
    const directEdges = useArchStore.getState().getComponentRelationships();
    expect(nodesById).toEqual(directNodes);
    expect(g.edges).toEqual(directEdges);
    expect(g.aggregates).toEqual(useArchStore.getState().getAggregateNodes());
  });

  it("preserves the selected element, drill level, and breadcrumbs across a lens switch (I12)", () => {
    const child = makeComponent({ id: "child", name: "Child" });
    const parent = makeComponent({ id: "parent", name: "Parent", children: [child], files: [] });
    const arch = makeArchitecture({ components: [parent] });
    useArchStore.getState().setArchitecture(arch);

    useArchStore.getState().drillInto(parent);
    useArchStore.getState().selectComponent("child");
    const before = useArchStore.getState();
    expect(before.drillLevel).toBe("parent");
    expect(before.selectedComponentId).toBe("child");
    const crumbsBefore = before.breadcrumbs;

    useArchStore.getState().setLens("test-lens");

    const after = useArchStore.getState();
    expect(after.lens).toBe("test-lens");
    // Same element stays selected; breadcrumbs and drill survive (I12).
    expect(after.selectedComponentId).toBe("child");
    expect(after.drillLevel).toBe("parent");
    expect(after.breadcrumbs).toEqual(crumbsBefore);
  });

  it("keeps the drill landing's ranked child ordering (I11)", () => {
    // Three substantial modules in a fixed order; no hero, so nothing is
    // promoted or aggregated and the order is the tree order.
    const a = makeComponent({ id: "a", name: "A", files: ["a1.ts", "a2.ts"] });
    const b = makeComponent({ id: "b", name: "B", files: ["b1.ts"] });
    const c = makeComponent({ id: "c", name: "C", files: ["c1.ts"] });
    const parent = makeComponent({ id: "p", name: "P", type: "project", children: [a, b, c], files: [] });
    const arch = makeArchitecture({ components: [parent] });
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().drillInto(parent);

    const order1 = useArchStore.getState().getVisibleComponents().map((c) => c.id);
    const order2 = useArchStore.getState().getVisibleComponents().map((c) => c.id);
    expect(order1).toEqual(["a", "b", "c"]);
    // Deterministic across calls (ranked ordering is stable, not reshuffled).
    expect(order2).toEqual(order1);
  });
});
