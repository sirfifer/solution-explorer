import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { DetailPanel } from "../components/DetailPanel";
import { useArchStore } from "../store";
import type { Architecture, Component } from "../types";

// V3.1: the Docs tab appeared for components whose only docs data was a
// detected pattern (or tech_stack / api_endpoints / env_vars), then rendered
// "No documentation files found" because DocsTab renders none of those. The
// fix makes the tab-presence predicate match exactly what DocsTab renders
// (readme / claude_md / architecture_notes / api_docs / changelog sections,
// plus key_decisions). These tests are fail-before: against the old predicate
// the patterns-only component offered a Docs tab.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "analyzer", name: "analyzer", type: "module", path: "analyzer",
    language: "python", framework: null, description: null, port: null, children: [],
    files: ["analyzer/x.py"], entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { python: 100 } },
    docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
    ...overrides,
  };
}

function makeArchitecture(component: Component): Architecture {
  return {
    name: "T", description: "", repository: null, generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0", root_path: "/t", components: [component], relationships: [], symbols: [],
    files: [{ path: "analyzer/x.py", language: "python", lines: 100, size_bytes: 1000, symbols: [], imports: [], exports: [], module_doc: null }],
    stats: { total_files: 1, total_lines: 100, total_size_bytes: 1000, languages: { python: 100 }, total_symbols: 0, total_components: 1, total_relationships: 0 },
  };
}

function mount(component: Component) {
  useArchStore.setState({
    architecture: makeArchitecture(component),
    loading: false, error: null,
    detailItem: { type: "component", data: component },
    activePanel: "detail",
    componentDetailCache: {}, componentDetailLoading: {}, componentDetailErrors: {},
  });
  render(<DetailPanel />);
}

describe("Docs tab presence matches Docs tab content (V3.1)", () => {
  afterEach(() => {
    cleanup();
    useArchStore.setState({ detailItem: null, activePanel: null });
  });

  it("offers no Docs tab when the only docs data is a detected pattern", () => {
    mount(makeComponent({
      docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: ["Repository Pattern"], tech_stack: ["Python"], env_vars: [], api_endpoints: [] },
    }));
    expect(screen.queryByRole("button", { name: /^Docs$/ })).toBeNull();
  });

  it("offers no Docs tab for env_vars or api_endpoints only (not rendered by DocsTab)", () => {
    mount(makeComponent({
      docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: ["API_KEY"], api_endpoints: [{ method: "GET", path: "/health" }] },
    }));
    expect(screen.queryByRole("button", { name: /^Docs$/ })).toBeNull();
  });

  it("offers a Docs tab when a README exists", () => {
    mount(makeComponent({
      docs: { readme: "# Title\n\nreal docs", claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
    }));
    expect(screen.getByRole("button", { name: /^Docs$/ })).toBeTruthy();
  });

  it("offers a Docs tab when only key decisions exist (DocsTab renders them)", () => {
    mount(makeComponent({
      docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: ["chose X over Y"], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
    }));
    expect(screen.getByRole("button", { name: /^Docs$/ })).toBeTruthy();
  });
});
