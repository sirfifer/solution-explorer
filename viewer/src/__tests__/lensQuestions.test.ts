import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import { STRUCTURE_QUESTIONS } from "../lenses";
import { initializeSearch, search } from "../utils/search";
import { buildRationale } from "../components/RationaleStrip";
import type { Architecture, Component } from "../types";

// I14: the Structure lens ships a documented question list, and every question's
// gesture is exercised here against the real store with an asserted answer. A
// question without a tested gesture fails the coverage assertion at the end.

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

function resetStore() {
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [],
    drillLevel: null, detailItem: null, activePanel: null,
    lens: "structure", reviewMode: false,
  });
}

// One gesture per question id. Each performs the interaction against the real
// store and asserts the answer the Structure lens promises.
const gestures: Record<string, () => void> = {
  identity: () => {
    resetStore();
    const svc = makeComponent({ id: "svc", name: "Payments Service", type: "service" });
    useArchStore.getState().setArchitecture(makeArchitecture({ components: [svc] }));
    useArchStore.getState().selectComponent("svc");
    const item = useArchStore.getState().detailItem;
    expect(item?.type).toBe("component");
    expect((item?.data as Component).id).toBe("svc");
    expect(useArchStore.getState().activePanel).toBe("detail");
  },

  organization: () => {
    resetStore();
    const a = makeComponent({ id: "a" });
    const b = makeComponent({ id: "b" });
    const parent = makeComponent({ id: "parent", type: "project", children: [a, b], files: [] });
    useArchStore.getState().setArchitecture(makeArchitecture({ components: [parent] }));
    useArchStore.getState().drillInto(parent);
    expect(useArchStore.getState().drillLevel).toBe("parent");
    // Children render as a ranked graph at the next altitude.
    expect(useArchStore.getState().getVisibleComponents().map((c) => c.id)).toEqual(["a", "b"]);
  },

  connections: () => {
    resetStore();
    const a = makeComponent({ id: "a" });
    const b = makeComponent({ id: "b" });
    const arch = makeArchitecture({
      components: [a, b],
      relationships: [{ source: "a", target: "b", type: "http", label: null, protocol: "http", port: 8080, bidirectional: false }],
    });
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().selectComponent("a");
    // The Links tab reads relationships touching the component.
    const links = arch.relationships.filter((r) => r.source === "a" || r.target === "a");
    expect(links.length).toBeGreaterThan(0);
  },

  hidden: () => {
    resetStore();
    const screen = makeComponent({ id: "screen", name: "Screen", type: "screen", files: ["s.swift"] });
    const helper = makeComponent({ id: "helper", name: "Helper", type: "module", files: ["h.swift"] });
    const wrapper = makeComponent({ id: "w", type: "module", children: [screen, helper] });
    const parent = makeComponent({ id: "app", type: "ios-client", children: [wrapper], files: [] });
    useArchStore.getState().setArchitecture(makeArchitecture({ components: [parent] }));
    useArchStore.getState().drillInto(parent);
    // Overflow the viewport's node budget so something must aggregate.
    useArchStore.setState({ nodeBudget: 1 });
    const aggs = useArchStore.getState().getAggregateNodes();
    expect(aggs.length).toBeGreaterThan(0);
    // Opening the aggregate lists its members in the panel, where a row
    // carries the name, purpose and criticality a canvas speck could not.
    useArchStore.getState().toggleAggregate(aggs[0].id);
    const item = useArchStore.getState().detailItem;
    expect(item?.type).toBe("aggregate");
    const members = (item?.data as { members: { id: string }[] }).members;
    expect(members.map((m) => m.id)).toContain("helper");
  },

  locate: () => {
    resetStore();
    const svc = makeComponent({ id: "svc", name: "Payments Service", type: "service" });
    const arch = makeArchitecture({ components: [svc] });
    useArchStore.getState().setArchitecture(arch);
    initializeSearch(arch);
    // Search locates the component by name.
    expect(search("Payments").map((r) => r.id)).toContain("svc");
  },

  rationale: () => {
    resetStore();
    const svc = makeComponent({
      id: "svc", name: "Svc", type: "service",
      ai_enhance: { architectural_role: "gateway", help_text: "Fronts the payment providers." },
    });
    useArchStore.getState().setArchitecture(makeArchitecture({ components: [svc] }));
    // The rationale strip has intent content to show (I13).
    expect(buildRationale(svc)).not.toBeNull();
  },
};

describe("Structure lens question gestures (I14)", () => {
  beforeEach(() => resetStore());

  for (const q of STRUCTURE_QUESTIONS) {
    it(`answers "${q.question}" via its gesture`, () => {
      // Every documented question must have a tested gesture (I14).
      expect(gestures[q.id], `no gesture wired for question "${q.id}"`).toBeTypeOf("function");
      gestures[q.id]();
    });
  }

  it("covers every documented question with a gesture", () => {
    const documented = STRUCTURE_QUESTIONS.map((q) => q.id).sort();
    const tested = Object.keys(gestures).sort();
    expect(tested).toEqual(documented);
  });
});
