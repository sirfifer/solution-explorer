import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import {
  FLOW_QUESTIONS,
  collectFlowComponents,
  buildFlowEdges,
} from "../lenses";
import type { Architecture, Component, UIAction } from "../types";

// I14: the Flow lens ships a documented question list, and every question's
// gesture is exercised here against the real store with an asserted answer. A
// question without a tested gesture fails the coverage assertion at the end.

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

function makeUiArch(): Architecture {
  const detail = makeComponent({ id: "app/detail", name: "Detail", type: "screen" });
  const settings = makeComponent({ id: "app/settings", name: "Settings", type: "screen" });
  const dashboard = makeComponent({
    id: "app/dashboard", name: "Dashboard", type: "screen",
    actions: [action("Open Help", "Detail")],
  });
  const tabHome = makeComponent({ id: "app/tab-home", name: "Home", type: "tab" });
  const tabBar = makeComponent({ id: "app/tab-bar", name: "Tab Bar", type: "tab-container" });
  const ui = makeComponent({
    id: "app/ui", name: "UI", type: "module", files: [],
    children: [tabBar, tabHome, dashboard, detail, settings],
  });
  const app = makeComponent({ id: "app", name: "App", type: "ios-client", files: [], children: [ui] });
  return makeArchitecture({
    components: [app],
    relationships: [
      rel("app/tab-bar", "app/tab-home", "tab", "Home"),
      rel("app/tab-home", "app/dashboard", "navigation", "Dashboard"),
      rel("app/dashboard", "app/detail", "navigation", "Detail"),
      rel("app/dashboard", "app/settings", "modal", "sheet"),
    ],
  });
}

function resetStore() {
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [],
    drillLevel: null, expandedAggregates: {}, detailItem: null, activePanel: null,
    lens: "structure", reviewMode: false, flowEntryId: null, flowStep: 0,
  });
}

const gestures: Record<string, () => void> = {
  "where-start": () => {
    resetStore();
    useArchStore.getState().setArchitecture(makeUiArch());
    useArchStore.getState().setLens("flow");
    const entries = useArchStore.getState().getFlowEntries();
    expect(entries.length).toBeGreaterThan(0);
    // Ranked landing: the widest journey (the tab bar) is first (I11).
    expect(entries[0].id).toBe("app/tab-bar");
  },

  "what-next": () => {
    resetStore();
    useArchStore.getState().setArchitecture(makeUiArch());
    useArchStore.getState().setLens("flow");
    const path = useArchStore.getState().getFlowPath("app/tab-home");
    useArchStore.getState().setFlowEntry("app/tab-home");
    useArchStore.getState().flowStepNext();
    // "What happens from here" advances to the next screen the flow reaches.
    expect(useArchStore.getState().flowStep).toBe(1);
    expect(useArchStore.getState().selectedComponentId).toBe(path[1]);
  },

  "how-here": () => {
    resetStore();
    useArchStore.getState().setArchitecture(makeUiArch());
    useArchStore.getState().setLens("flow");
    const path = useArchStore.getState().getFlowPath("app/tab-home");
    useArchStore.getState().setFlowEntry("app/tab-home");
    useArchStore.getState().flowStepNext();
    useArchStore.getState().flowStepPrev();
    // "How did I get here" steps back along the breadcrumbed path.
    expect(useArchStore.getState().flowStep).toBe(0);
    expect(useArchStore.getState().selectedComponentId).toBe(path[0]);
  },

  "modal-or-push": () => {
    resetStore();
    const arch = makeUiArch();
    const flowComponents = collectFlowComponents(arch.components);
    const edges = buildFlowEdges(arch, flowComponents);
    const nav = edges.find((e) => e.source === "app/tab-home" && e.target === "app/dashboard");
    const modal = edges.find((e) => e.source === "app/dashboard" && e.target === "app/settings");
    // The edge kind reads on the label: a push versus a modal.
    expect(nav?.label?.startsWith("push")).toBe(true);
    expect(modal?.label?.startsWith("modal")).toBe(true);
  },

  "which-tab": () => {
    resetStore();
    const arch = makeUiArch();
    const flowComponents = collectFlowComponents(arch.components);
    const edges = buildFlowEdges(arch, flowComponents);
    // Trace the dashboard's incoming edge back to the tab that owns it.
    const incoming = edges.filter((e) => e.target === "app/dashboard");
    expect(incoming.map((e) => e.source)).toContain("app/tab-home");
    const tab = flowComponents.find((c) => c.id === "app/tab-home");
    expect(tab?.type).toBe("tab");
  },
};

describe("Flow lens question gestures (I14)", () => {
  beforeEach(resetStore);

  for (const q of FLOW_QUESTIONS) {
    it(`answers "${q.question}" via its gesture`, () => {
      expect(gestures[q.id], `no gesture wired for question "${q.id}"`).toBeTypeOf("function");
      gestures[q.id]();
    });
  }

  it("covers every documented question with a gesture", () => {
    const documented = FLOW_QUESTIONS.map((q) => q.id).sort();
    const tested = Object.keys(gestures).sort();
    expect(tested).toEqual(documented);
  });
});
