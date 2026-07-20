import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { renderHook, act, cleanup } from "@testing-library/react";
import { useArchStore } from "../store";
import { useUrlSync } from "../hooks/useUrlSync";
import { parseUrlState, pushUrlState } from "../utils/urlState";
import { registerLens, type LensDefinition } from "../lenses";
import type { Architecture, Component } from "../types";

// A second lens available for the lens-URL tests below (P6-1).
const flowTestLens: LensDefinition = {
  id: "flow-test", label: "Flow (test)", description: "test",
  isAvailable: () => true,
  getGraph: () => ({ nodes: [], aggregates: [], edges: [] }),
  questions: [],
};
registerLens(flowTestLens);

// Regression test for F-VW-2 (P1-4): the popstate handler mutates the store,
// which fires the URL-sync subscription. Before the fix, that subscription
// pushed a NEW history entry mid-popstate, re-pushing the just-restored state
// and destroying the forward stack. The fix suppresses store-driven URL writes
// while a popstate is being applied. This drives the real store and the real
// useUrlSync hook against jsdom's history and asserts no entry is pushed during
// popstate handling and that the URL reflects the restored state.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "comp",
    name: "Component",
    type: "module",
    path: "src/comp",
    language: "typescript",
    framework: null,
    description: null,
    port: null,
    children: [],
    files: ["src/comp/index.ts"],
    entry_points: [],
    config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { typescript: 100 } },
    docs: {
      readme: null,
      claude_md: null,
      changelog: null,
      api_docs: null,
      architecture_notes: null,
      purpose: null,
      key_decisions: [],
      patterns: [],
      tech_stack: [],
      env_vars: [],
      api_endpoints: [],
    },
    ...overrides,
  };
}

// A -> B nesting so we can drill two levels deep.
function makeArchitecture(): Architecture {
  const childB = makeComponent({ id: "B", name: "B", path: "src/a/b", files: ["src/a/b/index.ts"] });
  const parentA = makeComponent({ id: "A", name: "A", path: "src/a", files: [], children: [childB] });
  return {
    name: "Nav Project",
    description: "",
    repository: null,
    generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0",
    root_path: "/nav",
    components: [parentA],
    relationships: [],
    symbols: [],
    files: [],
    stats: {
      total_files: 0,
      total_lines: 0,
      total_size_bytes: 0,
      languages: {},
      total_symbols: 0,
      total_components: 0,
      total_relationships: 0,
    },
  };
}

describe("useUrlSync popstate suppression (F-VW-2 / P1-4)", () => {
  beforeEach(() => {
    // Reset the URL to a clean base without adding a history entry.
    window.history.replaceState({}, "", "/");
    useArchStore.setState({
      architecture: null,
      selectedComponentId: null,
      drillLevel: null,
      breadcrumbs: [],
      annotations: [],
      componentDetailCache: {},
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("does not grow history and keeps the restored URL when applying a popstate", () => {
    // Architecture is set before mounting so the one-shot URL-restore effect sees
    // an empty URL and does nothing.
    useArchStore.setState({ architecture: makeArchitecture() });
    renderHook(() => useUrlSync());

    const store = useArchStore.getState();
    const compA = store.getComponentById("A")!;
    const compB = store.getComponentById("B")!;

    // Drill A then B: each drill change pushes a history entry.
    act(() => { useArchStore.getState().drillInto(compA); });
    act(() => { useArchStore.getState().drillInto(compB); });

    expect(useArchStore.getState().drillLevel).toBe("B");
    expect(parseUrlState().drill).toBe("B");

    const historyLenBeforeBack = window.history.length;

    // Simulate the browser Back button: the browser sets the URL to the previous
    // entry (drill=A) and then fires popstate. Use replaceState so we change the
    // URL without adding an entry, mirroring a real back navigation's URL state.
    act(() => {
      window.history.replaceState({}, "", "/?drill=A");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    // The store restored the earlier drill state.
    expect(useArchStore.getState().drillLevel).toBe("A");
    // The URL still reflects the restored state; our handler did not rewrite it.
    expect(parseUrlState().drill).toBe("A");
    // Crucially, applying the popstate did NOT push a new history entry. On the
    // pre-fix code the subscription re-pushed drill=A here, growing history by 1
    // and destroying the forward stack.
    expect(window.history.length).toBe(historyLenBeforeBack);
  });

  it("still writes the URL for normal store-driven drill navigation", () => {
    useArchStore.setState({ architecture: makeArchitecture() });
    renderHook(() => useUrlSync());

    const compA = useArchStore.getState().getComponentById("A")!;
    expect(parseUrlState().drill).toBeUndefined();

    act(() => { useArchStore.getState().drillInto(compA); });

    // Outside of popstate handling, the subscription must still sync to the URL.
    expect(parseUrlState().drill).toBe("A");
  });

  it("preserves an existing ?tab= param when a selection change rewrites the URL (F-VW-7)", () => {
    useArchStore.setState({ architecture: makeArchitecture() });
    renderHook(() => useUrlSync());

    // DetailPanel owns the tab param. Simulate it having written one.
    window.history.replaceState({}, "", "/?tab=symbols");
    expect(parseUrlState().tab).toBe("symbols");

    // A selection change fires the URL-sync subscription (replaceState path).
    act(() => { useArchStore.getState().selectComponent("A"); });

    // The rewritten URL keeps the tab param instead of erasing it. Pre-fix the
    // writer rebuilt the URL from component/drill only and dropped ?tab.
    expect(parseUrlState().component).toBe("A");
    expect(parseUrlState().tab).toBe("symbols");
  });

  it("consumes an inbound ?file=&line= deep link on load, composing with ?tab (P3-2)", () => {
    // Child B lives under A and owns a file. A deep link should drill to A and
    // select B, honoring the explicit tab param.
    window.history.replaceState({}, "", "/?file=src/a/b/index.ts&line=3&tab=symbols");

    useArchStore.setState({ architecture: makeArchitecture() });
    renderHook(() => useUrlSync());

    const state = useArchStore.getState();
    // Navigation was driven by the file deep link (not by absent component/drill).
    expect(state.selectedComponentId).toBe("B");
    expect(state.drillLevel).toBe("A");
    expect(state.fileDeepLink).toMatchObject({ componentId: "B", filePath: "src/a/b/index.ts", line: 3 });
    // The explicit tab param is honored and preserved in the URL after navigation.
    expect(parseUrlState().tab).toBe("symbols");
    // The one-shot file/line params are consumed (dropped from the rebuilt URL).
    expect(parseUrlState().file).toBeUndefined();
    expect(parseUrlState().line).toBeUndefined();
  });
});

describe("useUrlSync lens state (P6-1)", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/");
    useArchStore.setState({
      architecture: null, selectedComponentId: null, drillLevel: null,
      breadcrumbs: [], annotations: [], componentDetailCache: {}, lens: "structure",
    });
  });
  afterEach(() => cleanup());

  it("writes ?lens= when the lens changes and omits it for the default", () => {
    useArchStore.setState({ architecture: makeArchitecture() });
    renderHook(() => useUrlSync());

    act(() => { useArchStore.getState().setLens("flow-test"); });
    expect(parseUrlState().lens).toBe("flow-test");

    // Back to the default Structure lens: the param is dropped to keep URLs clean.
    act(() => { useArchStore.getState().setLens("structure"); });
    expect(parseUrlState().lens).toBeUndefined();
  });

  it("restores the lens from the URL on load", () => {
    window.history.replaceState({}, "", "/?lens=flow-test");
    useArchStore.setState({ architecture: makeArchitecture() });
    renderHook(() => useUrlSync());
    expect(useArchStore.getState().lens).toBe("flow-test");
  });

  it("applies the lens on browser back/forward", () => {
    useArchStore.setState({ architecture: makeArchitecture() });
    renderHook(() => useUrlSync());
    act(() => { useArchStore.getState().setLens("flow-test"); });
    expect(useArchStore.getState().lens).toBe("flow-test");

    // Back to a URL without a lens param: popstate restores the default.
    act(() => {
      window.history.replaceState({}, "", "/");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(useArchStore.getState().lens).toBe("structure");
  });
});

describe("data param survival (M1 adversarial-review blocker)", () => {
  it("pushUrlState preserves ?data= so member views survive navigation", () => {
    window.history.replaceState({}, "", "/?data=./architecture/members/web");
    pushUrlState({ component: "app", tab: null, drill: null, lens: "structure" } as never);
    const params = new URLSearchParams(window.location.search);
    expect(params.get("data")).toBe("./architecture/members/web");
    expect(params.get("component")).toBe("app");
    window.history.replaceState({}, "", "/");
  });

  it("pushUrlState emits no data param outside a member view", () => {
    window.history.replaceState({}, "", "/");
    pushUrlState({ component: "app", tab: null, drill: null, lens: "structure" } as never);
    expect(new URLSearchParams(window.location.search).get("data")).toBeNull();
  });
});
