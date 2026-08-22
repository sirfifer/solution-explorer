import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import {
  DESIGN_QUESTIONS,
  buildScatter,
  designMethodCaveat,
  groupDesignFindings,
  METHOD_LABEL,
} from "../lenses";
import type {
  Architecture,
  Component,
  ComponentDesign,
  DesignFinding,
  Relationship,
} from "../types";

// D4: every documented Design-lens question is answerable by an executable
// gesture (invariant I14). Each gesture below is the real sequence a reader
// performs, run against the real store.

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

function design(overrides: Partial<ComponentDesign> = {}): ComponentDesign {
  return {
    fan_in: 0, fan_out: 0, instability: null, abstractness: null,
    distance_main_sequence: null, blast_radius: 0, bands: {}, ...overrides,
  };
}

function rel(source: string, target: string): Relationship {
  return { source, target, type: "import", label: null, protocol: null, port: null, bidirectional: false } as Relationship;
}

const FINDINGS: DesignFinding[] = [
  {
    id: "cycle-001", kind: "cycle",
    lead: "These 2 parts are locked together. None of them can be understood, changed, or replaced without the others.",
    term: "Dependency cycle", term_detail: "", method: "static-graph",
    targets: ["core", "helpers"], edges: [["core", "helpers"], ["helpers", "core"]],
    evidence: [], rank_within_kind: 1,
  },
  {
    id: "zone-of-pain-001", kind: "zone_of_pain",
    lead: "This is load-bearing: 3 parts lean on it. It has no flexibility built in, and it keeps being changed anyway.",
    term: "Zone of pain", term_detail: "high fan-in, concrete, high churn",
    method: "static-graph+git-history", targets: ["core"], edges: [],
    evidence: [], rank_within_kind: 1,
  },
  {
    id: "change-coupling-001", kind: "change_coupling",
    lead: "These two are separated on the diagram, but in practice they change together. The boundary may be drawn in the wrong place.",
    term: "Cross-boundary change coupling", term_detail: "CCP", method: "git-history",
    targets: ["core", "ui"], edges: [], evidence: [], rank_within_kind: 1,
  },
  {
    id: "boundary-strength-001", kind: "boundary_strength",
    lead: "3 of the 4 seams between parts are separated by convention only; 1 is separated by a real contract.",
    term: "Boundary strength", term_detail: "source vs service boundary",
    method: "static-graph", targets: [], edges: [], evidence: [], rank_within_kind: 1,
  },
];

function architecture(): Architecture {
  return {
    name: "T", description: "", repository: null, generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0", root_path: "/t",
    components: [
      makeComponent({
        id: "core", name: "Core",
        design: design({ fan_in: 3, fan_out: 0, instability: 0, abstractness: 0, distance_main_sequence: 1, blast_radius: 12, bands: { fan_in: "q5", churn: "q5" } }),
      }),
      makeComponent({
        id: "helpers", name: "Helpers",
        design: design({ fan_in: 1, fan_out: 1, instability: 0.5, abstractness: 0.5, distance_main_sequence: 0, blast_radius: 2, bands: { fan_in: "q3" } }),
      }),
      // A Python component: no abstractness reading, so it is never plotted.
      makeComponent({ id: "ui", name: "UI", language: "python", design: design({ fan_in: 0, fan_out: 2, instability: 1 }) }),
    ],
    relationships: [rel("core", "helpers"), rel("helpers", "core"), rel("ui", "core")],
    symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 3, total_relationships: 3 },
    design_signals: {
      version: 1, method_caveat: CAVEAT, has_activity: true, component_count: 3,
      finding_counts: { cycle: 1, zone_of_pain: 1, change_coupling: 1, boundary_strength: 1 },
      findings: FINDINGS,
      boundaries: [
        { source: "core", target: "helpers", strength: "source" },
        { source: "ui", target: "core", strength: "service" },
      ],
    },
  };
}

function seed() {
  useArchStore.setState({
    architecture: architecture(),
    selectedDesignFindingId: null,
    selectedComponentId: null,
    blastRadiusMode: false,
    drillLevel: null,
  });
  useArchStore.getState().setLens("design");
}

const gestures: Record<string, () => void> = {
  "where-is-it-weak": () => {
    // Open the lens: findings grouped by kind, each with a lead and a term chip.
    expect(useArchStore.getState().lens).toBe("design");
    const groups = groupDesignFindings(useArchStore.getState().getDesignFindings());
    expect(groups.length).toBeGreaterThan(0);
    for (const group of groups) {
      for (const finding of group.items) {
        expect(finding.lead.length).toBeGreaterThan(0);
        expect(finding.term.length).toBeGreaterThan(0);
        expect(finding.lead).not.toBe(finding.term);
      }
    }
  },
  "locked-together": () => {
    // Read the cycle group, select the row, and the graph draws exactly that loop.
    const groups = groupDesignFindings(useArchStore.getState().getDesignFindings());
    const cycles = groups.find((g) => g.kind === "cycle")!;
    expect(cycles.count).toBe(1);
    useArchStore.getState().selectDesignFinding("cycle-001");
    const graph = useArchStore.getState().getLensGraph();
    expect(graph.nodes.map((n) => n.id).sort()).toEqual(["core", "helpers"]);
    expect(graph.edges).toHaveLength(2);
  },
  "load-bearing": () => {
    // The zone-of-pain group names it, and the scatter puts it in the shaded corner.
    const groups = groupDesignFindings(useArchStore.getState().getDesignFindings());
    const pain = groups.find((g) => g.kind === "zone_of_pain")!;
    expect(pain.items[0].targets).toEqual(["core"]);
    const scatter = buildScatter(useArchStore.getState().architecture!);
    const core = scatter.points.find((p) => p.componentId === "core")!;
    expect(core.zone).toBe("pain");
    // And the component whose abstractness is unknown is declared, not plotted.
    expect(scatter.omitted).toBe(1);
  },
  "how-do-we-know": () => {
    // Every row carries a method chip, and the caveat is available verbatim.
    const findings = useArchStore.getState().getDesignFindings();
    for (const finding of findings) {
      expect(METHOD_LABEL[finding.method]).toBeTruthy();
    }
    // A mixed claim says so rather than choosing the flattering half.
    const pain = findings.find((f) => f.id === "zone-of-pain-001")!;
    expect(pain.method).toBe("static-graph+git-history");
    expect(designMethodCaveat(useArchStore.getState().architecture!)).toBe(CAVEAT);
  },
  "blast-radius": () => {
    // The count is on the component's card, and the mode shades the graph
    // around the shared selection (I12): selecting IS anchoring.
    expect(useArchStore.getState().getComponentById("core")!.design!.blast_radius).toBe(12);
    useArchStore.getState().toggleBlastRadiusMode();
    expect(useArchStore.getState().blastRadiusMode).toBe(true);
    useArchStore.getState().selectComponent("core");
    expect(useArchStore.getState().selectedComponentId).toBe("core");
  },
  "seams": () => {
    // The boundary-strength summary counts the seams by how they are held.
    const summary = useArchStore
      .getState()
      .getDesignFindings()
      .find((f) => f.kind === "boundary_strength")!;
    expect(summary.lead).toContain("convention only");
    expect(summary.lead).toContain("real contract");
    expect(useArchStore.getState().architecture!.design_signals!.boundaries).toHaveLength(2);
  },
};

describe("Design lens question gestures (I14)", () => {
  beforeEach(seed);

  for (const q of DESIGN_QUESTIONS) {
    it(`answers "${q.question}" via its gesture`, () => {
      expect(gestures[q.id], `no gesture wired for question "${q.id}"`).toBeTypeOf("function");
      gestures[q.id]();
    });
  }

  it("covers every documented question with a gesture", () => {
    expect(Object.keys(gestures).sort()).toEqual(DESIGN_QUESTIONS.map((q) => q.id).sort());
  });
});
