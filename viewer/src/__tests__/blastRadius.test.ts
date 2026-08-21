import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import { buildBlastAdjacency, computeBlastRadius } from "../lenses";
import type { Architecture, Component, ComponentDesign, Relationship } from "../types";

// D5: blast radius as an interaction. The transitive sets are computed
// client-side from the edges the viewer already holds, so the feature works at
// any drill level and on any dataset, while the stored per-component count is
// the flag-gated extra that appears on the card.
//
// Contracts under test:
//   1. The two directions are computed correctly and kept apart: dependents are
//      what breaks if this changes, dependencies are what it stands on.
//   2. Cycles terminate, and a node is never its own dependent.
//   3. The mode is a mode: toggling, anchoring, and dropping the anchor behave.
//   4. The card count degrades by absence, and null is never rendered as zero.

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

function design(overrides: Partial<ComponentDesign> = {}): ComponentDesign {
  return {
    fan_in: 0, fan_out: 0, instability: null, abstractness: null,
    distance_main_sequence: null, blast_radius: 0, bands: {}, ...overrides,
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

function rel(source: string, target: string): Relationship {
  return { source, target, type: "import", label: null, protocol: null, port: null, bidirectional: false } as Relationship;
}

// A chain: d depends on c depends on b depends on a. So a is the bedrock.
const CHAIN = [
  { source: "b", target: "a" },
  { source: "c", target: "b" },
  { source: "d", target: "c" },
];

describe("the transitive sets", () => {
  it("counts everything that could break, transitively", () => {
    const { dependents } = computeBlastRadius("a", CHAIN);
    expect([...dependents].sort()).toEqual(["b", "c", "d"]);
  });

  it("counts everything the focus stands on, transitively", () => {
    const { dependencies } = computeBlastRadius("d", CHAIN);
    expect([...dependencies].sort()).toEqual(["a", "b", "c"]);
  });

  it("keeps the two directions apart", () => {
    const { dependents, dependencies } = computeBlastRadius("b", CHAIN);
    expect([...dependents].sort()).toEqual(["c", "d"]);
    expect([...dependencies].sort()).toEqual(["a"]);
  });

  it("returns empty sets for a leaf and for no focus", () => {
    expect([...computeBlastRadius("d", CHAIN).dependents]).toEqual([]);
    const none = computeBlastRadius(null, CHAIN);
    expect(none.dependents.size).toBe(0);
    expect(none.dependencies.size).toBe(0);
  });

  it("terminates on a cycle and never counts a node as its own dependent", () => {
    const cyclic = [
      { source: "a", target: "b" },
      { source: "b", target: "c" },
      { source: "c", target: "a" },
    ];
    const { dependents, dependencies } = computeBlastRadius("a", cyclic);
    expect(dependents.has("a")).toBe(false);
    expect(dependencies.has("a")).toBe(false);
    expect([...dependents].sort()).toEqual(["b", "c"]);
    expect([...dependencies].sort()).toEqual(["b", "c"]);
  });

  it("drops self edges rather than counting a module against itself", () => {
    const { forward, reverse } = buildBlastAdjacency([{ source: "a", target: "a" }]);
    expect(forward.size).toBe(0);
    expect(reverse.size).toBe(0);
    expect([...computeBlastRadius("a", [{ source: "a", target: "a" }]).dependents]).toEqual([]);
  });

  it("handles a diamond without double counting", () => {
    const diamond = [
      { source: "left", target: "base" },
      { source: "right", target: "base" },
      { source: "top", target: "left" },
      { source: "top", target: "right" },
    ];
    expect([...computeBlastRadius("base", diamond).dependents].sort()).toEqual([
      "left", "right", "top",
    ]);
  });

  it("needs no design_signals block, so it works on any dataset", () => {
    // The interaction is computed from edges alone. That is what lets it work
    // at a drill level, where the visible edge set is a subset of the whole.
    const drilled = [{ source: "child-b", target: "child-a" }];
    expect([...computeBlastRadius("child-a", drilled).dependents]).toEqual(["child-b"]);
  });
});

describe("the mode", () => {
  beforeEach(() => {
    useArchStore.setState({
      architecture: makeArchitecture({
        components: [
          makeComponent({ id: "a", design: design({ blast_radius: 3, fan_in: 1 }) }),
          makeComponent({ id: "b" }),
        ],
        relationships: [rel("b", "a")],
      }),
      blastRadiusMode: false,
      blastRadiusFocusId: null,
      selectedComponentId: null,
    });
  });

  it("starts off", () => {
    expect(useArchStore.getState().blastRadiusMode).toBe(false);
    expect(useArchStore.getState().blastRadiusFocusId).toBeNull();
  });

  it("toggles on, accepts an anchor, and drops the anchor on the way out", () => {
    useArchStore.getState().toggleBlastRadiusMode();
    expect(useArchStore.getState().blastRadiusMode).toBe(true);
    useArchStore.getState().setBlastRadiusFocus("a");
    expect(useArchStore.getState().blastRadiusFocusId).toBe("a");
    useArchStore.getState().toggleBlastRadiusMode();
    expect(useArchStore.getState().blastRadiusMode).toBe(false);
    expect(useArchStore.getState().blastRadiusFocusId).toBeNull();
  });

  it("setBlastRadiusMode clears any stale anchor", () => {
    useArchStore.getState().setBlastRadiusFocus("a");
    useArchStore.getState().setBlastRadiusMode(true);
    expect(useArchStore.getState().blastRadiusMode).toBe(true);
    expect(useArchStore.getState().blastRadiusFocusId).toBeNull();
  });

  it("resets on architecture reload so no shading survives a new scan", () => {
    useArchStore.getState().toggleBlastRadiusMode();
    useArchStore.getState().setBlastRadiusFocus("a");
    useArchStore.getState().setArchitecture(makeArchitecture());
    expect(useArchStore.getState().blastRadiusMode).toBe(false);
    expect(useArchStore.getState().blastRadiusFocusId).toBeNull();
  });
});

describe("the card count", () => {
  it("reads the stored per-component count when the dataset carries one", () => {
    useArchStore.setState({
      architecture: makeArchitecture({
        components: [makeComponent({ id: "a", design: design({ blast_radius: 47 }) })],
      }),
    });
    expect(useArchStore.getState().getDesignForComponent("a")!.blast_radius).toBe(47);
  });

  it("degrades by absence on a dataset analyzed without the flag", () => {
    useArchStore.setState({
      architecture: makeArchitecture({ components: [makeComponent({ id: "a" })] }),
    });
    expect(useArchStore.getState().getDesignForComponent("a")).toBeNull();
  });
});
