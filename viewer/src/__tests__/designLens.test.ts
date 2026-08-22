import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import {
  DEFAULT_LENS_ID,
  listAvailableLenses,
  hasDesignSignals,
  designMethodCaveat,
  groupDesignFindings,
  findDesignFinding,
  findingComponentIds,
  findingImplicatesEdge,
  buildScatter,
  zoneFor,
  collectDesignSubjectIds,
  buildDesignFindingGraph,
  buildDesignLandingGraph,
  readZoneThresholds,
  DESIGN_KIND_ORDER,
  METHOD_LABEL,
  ZONE_OF_PAIN_MAX_SUM,
  ZONE_OF_USELESSNESS_MIN_SUM,
} from "../lenses";
import type {
  Architecture,
  Component,
  ComponentDesign,
  DesignFinding,
  DesignSignals,
  Relationship,
} from "../types";

// D4 Design lens: the availability gate, the two-audience rendering contract,
// the ranked grouping, the row-to-graph selection, the scatter's refusal to plot
// what it cannot measure, the edge marks and their worst-case roll-up, and
// reset-on-reload. Exercised against the real store.

const CAVEAT =
  "static import and declared communication edges only; runtime reflection, " +
  "dependency injection wiring, and dynamic dispatch are invisible to this analysis";

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

function makeDesign(overrides: Partial<ComponentDesign> = {}): ComponentDesign {
  return {
    fan_in: 0, fan_out: 0, instability: null, abstractness: null,
    distance_main_sequence: null, blast_radius: 0, bands: {},
    ...overrides,
  };
}

function makeFinding(overrides: Partial<DesignFinding> = {}): DesignFinding {
  return {
    id: "cycle-001", kind: "cycle",
    lead: "These 2 parts are locked together. None of them can be understood, changed, or replaced without the others.",
    term: "Dependency cycle", term_detail: "", method: "static-graph",
    targets: ["a", "b"], edges: [["a", "b"], ["b", "a"]], evidence: [],
    rank_within_kind: 1,
    ...overrides,
  };
}

function makeSignals(overrides: Partial<DesignSignals> = {}): DesignSignals {
  return {
    version: 1, method_caveat: CAVEAT, has_activity: false,
    component_count: 2, finding_counts: { cycle: 1 },
    findings: [makeFinding()], boundaries: [],
    ...overrides,
  };
}

function rel(source: string, target: string, type = "import"): Relationship {
  return {
    source, target, type, label: null, protocol: null, port: null, bidirectional: false,
  } as Relationship;
}

// --- 1. the availability gate --------------------------------------------------

describe("availability", () => {
  it("hides the lens when the dataset carries no design signals", () => {
    expect(hasDesignSignals(makeArchitecture())).toBe(false);
    const ids = listAvailableLenses(makeArchitecture()).map((l) => l.id);
    expect(ids).not.toContain("design");
  });

  it("hides the lens when the block exists but names no findings", () => {
    const arch = makeArchitecture({
      design_signals: makeSignals({ findings: [], finding_counts: {} }),
    });
    expect(hasDesignSignals(arch)).toBe(false);
  });

  it("shows the lens once the dataset can answer its question", () => {
    const arch = makeArchitecture({ design_signals: makeSignals() });
    expect(hasDesignSignals(arch)).toBe(true);
    expect(listAvailableLenses(arch).map((l) => l.id)).toContain("design");
  });

  it("falls back to the default lens when design is requested but unavailable", () => {
    useArchStore.setState({ architecture: makeArchitecture() });
    useArchStore.getState().setLens("design");
    expect(useArchStore.getState().lens).toBe(DEFAULT_LENS_ID);
  });
});

// --- 2. the two-audience rule ----------------------------------------------------

describe("the two-audience rule", () => {
  it("carries a plain-language lead and a separate canonical term", () => {
    const finding = makeFinding();
    expect(finding.lead).not.toBe(finding.term);
    // The lead must not open with the jargon; that is the whole rule.
    expect(finding.lead.startsWith(finding.term)).toBe(false);
  });

  it("names a method label for every epistemic class the analyzer emits", () => {
    expect(METHOD_LABEL["static-graph"]).toBeTruthy();
    expect(METHOD_LABEL["git-history"]).toBeTruthy();
    expect(METHOD_LABEL["static-graph+git-history"]).toBeTruthy();
    // The mixed class must not be described as either half alone.
    expect(METHOD_LABEL["static-graph+git-history"]).not.toBe(METHOD_LABEL["static-graph"]);
    expect(METHOD_LABEL["static-graph+git-history"]).not.toBe(METHOD_LABEL["git-history"]);
  });

  it("reads the method caveat from the payload rather than composing one", () => {
    const arch = makeArchitecture({ design_signals: makeSignals() });
    expect(designMethodCaveat(arch)).toBe(CAVEAT);
    // No signals means no caveat, not an invented one.
    expect(designMethodCaveat(makeArchitecture())).toBe("");
  });
});

// --- 3. the ranked grouping -------------------------------------------------------

describe("grouping", () => {
  it("groups by kind in the documented panel order and drops empty groups", () => {
    const findings = [
      makeFinding({ id: "bs-001", kind: "boundary_strength", targets: [], edges: [] }),
      makeFinding({ id: "cycle-001", kind: "cycle" }),
      makeFinding({ id: "zop-001", kind: "zone_of_pain", targets: ["x"], edges: [] }),
    ];
    const groups = groupDesignFindings(findings);
    expect(groups.map((g) => g.kind)).toEqual(["cycle", "zone_of_pain", "boundary_strength"]);
    expect(groups.every((g) => g.count > 0)).toBe(true);
  });

  it("orders within a kind by rank, never across kinds", () => {
    const findings = [
      makeFinding({ id: "cycle-002", rank_within_kind: 2 }),
      makeFinding({ id: "cycle-001", rank_within_kind: 1 }),
      makeFinding({ id: "zop-001", kind: "zone_of_pain", rank_within_kind: 1, targets: ["x"], edges: [] }),
    ];
    const groups = groupDesignFindings(findings);
    expect(groups[0].items.map((f) => f.id)).toEqual(["cycle-001", "cycle-002"]);
    // Each kind restarts at rank 1, which is what makes cross-kind comparison
    // impossible to express.
    expect(groups[1].items[0].rank_within_kind).toBe(1);
  });

  it("declares every kind the analyzer can emit", () => {
    expect(DESIGN_KIND_ORDER).toHaveLength(6);
    expect(new Set(DESIGN_KIND_ORDER).size).toBe(6);
  });
});

// --- 4. row to graph ---------------------------------------------------------------

describe("row-to-graph navigation", () => {
  const arch = makeArchitecture({
    components: [
      makeComponent({ id: "a", name: "A" }),
      makeComponent({ id: "b", name: "B" }),
      makeComponent({ id: "c", name: "C" }),
    ],
    relationships: [rel("a", "b"), rel("b", "a"), rel("c", "a")],
    design_signals: makeSignals(),
  });

  it("collects both the targets and both ends of every implicated edge", () => {
    const ids = findingComponentIds(makeFinding({ targets: ["a"], edges: [["a", "z"]] }));
    expect([...ids].sort()).toEqual(["a", "z"]);
  });

  it("focuses the graph on exactly the edges the finding names", () => {
    const finding = findDesignFinding(arch, "cycle-001")!;
    const { nodes, edges } = buildDesignFindingGraph(arch, finding);
    expect(nodes.map((n) => n.id).sort()).toEqual(["a", "b"]);
    // c -> a is a real relationship between an implicated node and an
    // unimplicated one; it is not part of the cycle and must not be drawn.
    expect(edges).toHaveLength(2);
    expect(edges.every((e) => finding.edges.some(([s, t]) => s === e.source && t === e.target))).toBe(true);
  });

  it("lands on every implicated component when nothing is selected", () => {
    expect([...collectDesignSubjectIds(arch)].sort()).toEqual(["a", "b"]);
    const { nodes } = buildDesignLandingGraph(arch);
    expect(nodes.map((n) => n.id).sort()).toEqual(["a", "b"]);
  });

  it("recognises an implicated edge in either direction independently", () => {
    const finding = makeFinding({ edges: [["a", "b"]] });
    expect(findingImplicatesEdge(finding, "a", "b")).toBe(true);
    expect(findingImplicatesEdge(finding, "b", "a")).toBe(false);
  });

  it("selecting a finding through the store focuses it and navigates", () => {
    useArchStore.setState({ architecture: arch });
    useArchStore.getState().setLens("design");
    expect(useArchStore.getState().lens).toBe("design");
    useArchStore.getState().selectDesignFinding("cycle-001");
    expect(useArchStore.getState().selectedDesignFindingId).toBe("cycle-001");
    expect(useArchStore.getState().selectedComponentId).toBe("a");
    const graph = useArchStore.getState().getLensGraph();
    expect(graph.nodes.map((n) => n.id).sort()).toEqual(["a", "b"]);
  });

  it("clearing the selection returns to the landing graph", () => {
    useArchStore.setState({ architecture: arch });
    useArchStore.getState().setLens("design");
    useArchStore.getState().selectDesignFinding("cycle-001");
    useArchStore.getState().clearDesignFinding();
    expect(useArchStore.getState().selectedDesignFindingId).toBeNull();
  });

  it("a system-wide finding with no targets navigates nowhere and does not throw", () => {
    const summaryArch = makeArchitecture({
      components: [makeComponent({ id: "a" })],
      design_signals: makeSignals({
        findings: [makeFinding({ id: "bs-001", kind: "boundary_strength", targets: [], edges: [] })],
      }),
    });
    useArchStore.setState({ architecture: summaryArch, selectedComponentId: null });
    useArchStore.getState().setLens("design");
    expect(() => useArchStore.getState().selectDesignFinding("bs-001")).not.toThrow();
    expect(useArchStore.getState().selectedDesignFindingId).toBe("bs-001");
    expect(useArchStore.getState().selectedComponentId).toBeNull();
  });
});

// --- 5. the scatter refuses to plot what it cannot measure -------------------------

describe("the abstractness / instability scatter", () => {
  it("plots only components with both ratios, and counts the rest", () => {
    const arch = makeArchitecture({
      components: [
        makeComponent({ id: "plotted", design: makeDesign({ abstractness: 0.5, instability: 0.5, distance_main_sequence: 0 }) }),
        // A Python component: abstractness unmeasurable, so it has no position.
        makeComponent({ id: "unmeasured", design: makeDesign({ instability: 0.2 }) }),
        makeComponent({ id: "no-block" }),
      ],
    });
    const { points, omitted } = buildScatter(arch);
    expect(points.map((p) => p.componentId)).toEqual(["plotted"]);
    expect(omitted).toBe(1);
  });

  it("never places an unmeasured component at the origin", () => {
    // Fail-before: coercing null to 0 would place this at (0,0), the very
    // centre of the zone of pain, and accuse it of being rigid.
    const arch = makeArchitecture({
      components: [makeComponent({ id: "python-core", design: makeDesign({ fan_in: 20, instability: 0 }) })],
    });
    const { points, omitted } = buildScatter(arch);
    expect(points).toHaveLength(0);
    expect(omitted).toBe(1);
  });

  it("classifies the two corners and the balanced middle", () => {
    expect(zoneFor(0, 0)).toBe("pain");
    expect(zoneFor(0, ZONE_OF_PAIN_MAX_SUM)).toBe("pain");
    expect(zoneFor(1, 1)).toBe("uselessness");
    expect(zoneFor(1, ZONE_OF_USELESSNESS_MIN_SUM - 1)).toBe("uselessness");
    // On the main sequence, A + I == 1.
    expect(zoneFor(0.5, 0.5)).toBe("balanced");
    expect(zoneFor(1, 0)).toBe("balanced");
  });

  it("ranks the plotted points worst distance first", () => {
    const arch = makeArchitecture({
      components: [
        makeComponent({ id: "near", design: makeDesign({ abstractness: 0.5, instability: 0.5, distance_main_sequence: 0 }) }),
        makeComponent({ id: "far", design: makeDesign({ abstractness: 0, instability: 0, distance_main_sequence: 1 }) }),
      ],
    });
    expect(buildScatter(arch).points.map((p) => p.componentId)).toEqual(["far", "near"]);
  });
});

// --- 6. zone thresholds travel as data --------------------------------------------

describe("zone thresholds", () => {
  it("reads the payload's thresholds so the chart shades what the findings used", () => {
    const arch = makeArchitecture({
      design_signals: makeSignals({
        zone_thresholds: {
          zone_of_pain_max_sum: 0.4,
          zone_of_uselessness_min_sum: 1.6,
        },
      }),
    });
    const t = readZoneThresholds(arch);
    expect(t.painMaxSum).toBe(0.4);
    expect(t.uselessnessMinSum).toBe(1.6);
    // The zone classification follows the dataset, not the mirrored constants.
    expect(zoneFor(0.2, 0.2, t)).toBe("pain");
    expect(zoneFor(0.25, 0.25, t)).toBe("balanced");
  });

  it("falls back to the mirrored constants for datasets projected before the key existed", () => {
    const arch = makeArchitecture({ design_signals: makeSignals({}) });
    const t = readZoneThresholds(arch);
    expect(t.painMaxSum).toBe(ZONE_OF_PAIN_MAX_SUM);
    expect(t.uselessnessMinSum).toBe(ZONE_OF_USELESSNESS_MIN_SUM);
  });
});

// --- 7. store integration and reset -------------------------------------------------

describe("store integration", () => {
  beforeEach(() => {
    useArchStore.setState({
      architecture: null, selectedDesignFindingId: null,
      blastRadiusMode: false,
    });
  });

  it("reads per-component design metrics, and null when there are none", () => {
    useArchStore.setState({
      architecture: makeArchitecture({
        components: [
          makeComponent({ id: "with", design: makeDesign({ fan_in: 3, blast_radius: 7 }) }),
          makeComponent({ id: "without" }),
        ],
      }),
    });
    expect(useArchStore.getState().getComponentById("with")?.design?.blast_radius).toBe(7);
    expect(useArchStore.getState().getComponentById("without")?.design).toBeUndefined();
    expect(useArchStore.getState().getComponentById("missing")).toBeNull();
  });

  it("returns an empty finding list rather than throwing on a bare dataset", () => {
    useArchStore.setState({ architecture: makeArchitecture() });
    expect(useArchStore.getState().getDesignFindings()).toEqual([]);
  });

  it("toggles blast radius mode; the anchor is the shared selection (I12)", () => {
    const store = useArchStore.getState();
    store.toggleBlastRadiusMode();
    expect(useArchStore.getState().blastRadiusMode).toBe(true);
    useArchStore.getState().toggleBlastRadiusMode();
    expect(useArchStore.getState().blastRadiusMode).toBe(false);
  });
});
