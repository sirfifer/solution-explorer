import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { DetailPanel } from "../components/DetailPanel";
import { useArchStore } from "../store";
import type { Architecture, Component, ComponentTesting } from "../types";

// Regression (surfaced by the Flow lens P6-2): the SwiftUI flow detector emits a
// `testing: {}` object for screen/tab/tab-container components. That object is
// truthy but has no `test_frameworks`, so the DetailPanel tab computation used to
// throw `Cannot read properties of undefined (reading 'length')` the moment such
// a component was selected. The Structure lens rarely selects these UI nodes; the
// Flow lens follows them by design, so this crash blocked the whole feature. The
// fix guards the partial testing object with optional chaining.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "app/tab-bar", name: "Tab Bar", type: "tab-container", path: "app/ui",
    language: "swift", framework: null, description: null, port: null, children: [],
    files: ["app/ui/TabBar.swift"], entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { swift: 100 } },
    docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
    ...overrides,
  };
}

function makeArchitecture(component: Component): Architecture {
  return {
    name: "T", description: "", repository: null, generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0", root_path: "/t", components: [component], relationships: [], symbols: [],
    files: [{ path: "app/ui/TabBar.swift", language: "swift", lines: 100, size_bytes: 1000, symbols: [], imports: [], exports: [], module_doc: null }],
    stats: { total_files: 1, total_lines: 100, total_size_bytes: 1000, languages: { swift: 100 }, total_symbols: 0, total_components: 1, total_relationships: 0 },
  };
}

describe("DetailPanel tolerates a partial testing object (P6-2 Flow lens)", () => {
  afterEach(() => {
    cleanup();
    useArchStore.setState({ detailItem: null, activePanel: null });
  });

  it("renders a component whose testing is an empty object without throwing", () => {
    // The real data shape: `testing: {}`, a ComponentTesting with none of its
    // fields present. Cast because the type declares them required.
    const component = makeComponent({ testing: {} as ComponentTesting });
    useArchStore.setState({
      architecture: makeArchitecture(component),
      loading: false, error: null,
      detailItem: { type: "component", data: component },
      activePanel: "detail",
      componentDetailCache: {}, componentDetailLoading: {}, componentDetailErrors: {},
    });

    // Before the guard this render threw during the tab computation.
    expect(() => render(<DetailPanel />)).not.toThrow();
    // The component name renders (it appears in the header and title), and no
    // Testing tab is offered for an empty testing object.
    expect(screen.getAllByText("Tab Bar").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /Testing/ })).toBeNull();
  });
});
