import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import {
  DEFAULT_LENS_ID,
  listAvailableLenses,
  hasFlowData,
  collectFlowComponents,
  buildFlowEdges,
  buildAdjacency,
  walkFlow,
  rankEntryFlows,
  collectActionEdges,
} from "../lenses";
import type { Architecture, Component, UIAction } from "../types";

// P6-2 Flow lens: availability gate, screen-flow graph selection (nav/modal/tab
// edges kind-labeled plus target_view action edges), I11 ranked entry flows, the
// follow walk, and I12 cross-lens identity.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "c", name: "C", type: "module", path: "src/c", language: "swift",
    framework: null, description: null, port: null, children: [], files: ["src/c/i.swift"],
    entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { swift: 100 } },
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

function rel(source: string, target: string, type: string, label: string | null = null) {
  return { source, target, type, label, protocol: null, port: null, bidirectional: false };
}

function action(label: string, target_view: string | null): UIAction {
  return { label, action_type: "button", handler: null, file: "v.swift", line: 1, target_view };
}

// A representative UI dataset: a tab bar with two tabs; the Home tab reaches a
// dashboard screen that pushes a detail screen and presents a settings sheet; the
// dashboard also has a button whose target_view links to an orphan screen (the
// modeled-but-never-drawn action edge).
function makeUiArch(): Architecture {
  const detail = makeComponent({ id: "app/detail", name: "Detail", type: "screen" });
  const settings = makeComponent({ id: "app/settings", name: "Settings", type: "screen" });
  const orphan = makeComponent({ id: "app/help", name: "Help", type: "screen" });
  const dashboard = makeComponent({
    id: "app/dashboard", name: "Dashboard", type: "screen",
    actions: [action("Open Help", "Help")],
  });
  const profile = makeComponent({ id: "app/profile", name: "Profile", type: "screen" });
  const tabHome = makeComponent({ id: "app/tab-home", name: "Home", type: "tab" });
  const tabYou = makeComponent({ id: "app/tab-you", name: "You", type: "tab" });
  const tabBar = makeComponent({ id: "app/tab-bar", name: "Tab Bar", type: "tab-container" });
  const ui = makeComponent({
    id: "app/ui", name: "UI", type: "module", files: [],
    children: [tabBar, tabHome, tabYou, dashboard, detail, settings, profile, orphan],
  });
  const app = makeComponent({ id: "app", name: "App", type: "ios-client", files: [], children: [ui] });
  return makeArchitecture({
    components: [app],
    relationships: [
      rel("app/tab-bar", "app/tab-home", "tab", "Home"),
      rel("app/tab-bar", "app/tab-you", "tab", "You"),
      rel("app/tab-home", "app/dashboard", "navigation", "Dashboard"),
      rel("app/dashboard", "app/detail", "navigation", "Detail"),
      rel("app/dashboard", "app/settings", "modal", "sheet"),
      rel("app/tab-you", "app/profile", "navigation", "Profile"),
    ],
  });
}

// A non-UI dataset (like this repo): only modules and http/import edges, no
// screens, tabs, flow edges, or target_view actions.
function makeBackendArch(): Architecture {
  const a = makeComponent({ id: "api", name: "API", type: "api-server", language: "python" });
  const b = makeComponent({ id: "svc", name: "Service", type: "service", language: "python" });
  return makeArchitecture({
    components: [a, b],
    relationships: [rel("svc", "api", "http", "REST")],
  });
}

function resetStore() {
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [],
    drillLevel: null, detailItem: null, activePanel: null,
    lens: DEFAULT_LENS_ID, reviewMode: false, flowEntryId: null, flowStep: 0,
  });
}

describe("Flow lens availability (P6-2)", () => {
  beforeEach(resetStore);

  it("is available on a dataset with flow-bearing data", () => {
    expect(hasFlowData(makeUiArch())).toBe(true);
    expect(listAvailableLenses(makeUiArch()).map((l) => l.id)).toContain("flow");
  });

  it("is NOT available on a non-UI dataset, and never fabricated from http edges", () => {
    const backend = makeBackendArch();
    expect(hasFlowData(backend)).toBe(false);
    expect(listAvailableLenses(backend).map((l) => l.id)).not.toContain("flow");
  });

  it("is available when only target_view actions exist (no flow edges yet)", () => {
    const screen = makeComponent({ id: "s", name: "S", type: "screen", actions: [action("Go", "T")] });
    expect(hasFlowData(makeArchitecture({ components: [screen] }))).toBe(true);
  });
});

describe("Flow lens graph selection (P6-2)", () => {
  beforeEach(resetStore);

  it("selects the flow components and labels each edge by kind", () => {
    const arch = makeUiArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("flow");
    const g = useArchStore.getState().getLensGraph();

    // Only screens, tabs, and the tab container are nodes; modules/clients are not.
    const nodeTypes = new Set(g.nodes.map((n) => n.type));
    expect(nodeTypes).toEqual(new Set(["screen", "tab", "tab-container"]));
    expect(g.aggregates).toEqual([]);

    const byPair = (s: string, t: string) => g.edges.find((e) => e.source === s && e.target === t);
    expect(byPair("app/tab-home", "app/dashboard")?.label).toBe("push: Dashboard");
    expect(byPair("app/dashboard", "app/settings")?.label).toBe("modal (sheet)");
    expect(byPair("app/tab-bar", "app/tab-home")?.label).toBe("tab: Home");
  });

  it("renders target_view actions as flow edges (the modeled-but-never-drawn data)", () => {
    const arch = makeUiArch();
    // FAIL-BEFORE contrast: the Structure lens graph never draws the action link.
    useArchStore.getState().setArchitecture(arch);
    const structureEdges = useArchStore.getState().getComponentRelationships();
    expect(structureEdges.some((e) => e.source === "app/dashboard" && e.target === "app/help")).toBe(false);

    // The Flow lens does: the dashboard's "Open Help" target_view becomes an edge.
    const flowComponents = collectFlowComponents(arch.components);
    const actionEdges = collectActionEdges(arch.components, flowComponents);
    const helpEdge = actionEdges.find((e) => e.target === "app/help");
    expect(helpEdge).toBeDefined();
    expect(helpEdge?.source).toBe("app/dashboard");
    expect(helpEdge?.type).toBe("action");
    expect(helpEdge?.label).toBe("action: Open Help");
  });
});

describe("Flow lens ranked entries and walk (P6-2, I11)", () => {
  beforeEach(resetStore);

  it("ranks entry flows by reachable screen count, widest first", () => {
    const arch = makeUiArch();
    const flowComponents = collectFlowComponents(arch.components);
    const edges = buildFlowEdges(arch, flowComponents);
    const entries = rankEntryFlows(flowComponents, edges);

    // The tab bar reaches the most; it lands first (I11).
    expect(entries[0].id).toBe("app/tab-bar");
    // Intermediate screens (detail/settings/profile) have incoming edges, so they
    // are not entries; the entries are the container, the tabs, and any root screen.
    const entryIds = entries.map((e) => e.id);
    expect(entryIds).toContain("app/tab-home");
    expect(entryIds).toContain("app/tab-you");
    expect(entryIds).not.toContain("app/detail");
    // Home reaches dashboard -> detail + settings + help (via action) = more than You.
    const home = entries.find((e) => e.id === "app/tab-home")!;
    const you = entries.find((e) => e.id === "app/tab-you")!;
    expect(home.reachableCount).toBeGreaterThan(you.reachableCount);
  });

  it("walks a flow as a DFS pre-order from the entry", () => {
    const arch = makeUiArch();
    const flowComponents = collectFlowComponents(arch.components);
    const edges = buildFlowEdges(arch, flowComponents);
    const path = walkFlow("app/tab-home", buildAdjacency(edges));
    // tab-home -> dashboard -> (detail, settings, help via action), unique, pre-order.
    expect(path[0]).toBe("app/tab-home");
    expect(path[1]).toBe("app/dashboard");
    expect(new Set(path)).toEqual(new Set(["app/tab-home", "app/dashboard", "app/detail", "app/settings", "app/help"]));
    expect(path.length).toBe(new Set(path).size); // no repeats
  });
});

describe("Flow lens follow affordance and identity (P6-2, I12)", () => {
  beforeEach(resetStore);

  it("steps forward and backward, selecting each hop", () => {
    const arch = makeUiArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("flow");

    const path = useArchStore.getState().getFlowPath("app/tab-home");
    useArchStore.getState().setFlowEntry("app/tab-home");
    expect(useArchStore.getState().flowEntryId).toBe("app/tab-home");
    expect(useArchStore.getState().flowStep).toBe(0);
    // Entering follow selects the entry (I12: selection is the shared identity).
    expect(useArchStore.getState().selectedComponentId).toBe(path[0]);

    useArchStore.getState().flowStepNext();
    expect(useArchStore.getState().flowStep).toBe(1);
    expect(useArchStore.getState().selectedComponentId).toBe(path[1]);

    useArchStore.getState().flowStepPrev();
    expect(useArchStore.getState().flowStep).toBe(0);
    expect(useArchStore.getState().selectedComponentId).toBe(path[0]);
  });

  it("does not step past the ends of the walk", () => {
    const arch = makeUiArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setFlowEntry("app/tab-you");
    // Prev at the entry is a no-op.
    useArchStore.getState().flowStepPrev();
    expect(useArchStore.getState().flowStep).toBe(0);
    // Step to the end, then Next is a no-op.
    const path = useArchStore.getState().getFlowPath("app/tab-you");
    useArchStore.getState().flowGoToStep(path.length - 1);
    useArchStore.getState().flowStepNext();
    expect(useArchStore.getState().flowStep).toBe(path.length - 1);
  });

  it("preserves the selected element across a lens switch (I12)", () => {
    const arch = makeUiArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().selectComponent("app/dashboard");
    useArchStore.getState().setLens("flow");
    expect(useArchStore.getState().selectedComponentId).toBe("app/dashboard");
    useArchStore.getState().setLens("structure");
    expect(useArchStore.getState().selectedComponentId).toBe("app/dashboard");
  });

  it("returns no entries for a non-UI dataset", () => {
    useArchStore.getState().setArchitecture(makeBackendArch());
    expect(useArchStore.getState().getFlowEntries()).toEqual([]);
  });
});
