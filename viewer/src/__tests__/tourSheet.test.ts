import { describe, it, expect } from "vitest";
import { useArchStore } from "../store";
import type { Architecture, Component } from "../types";

// A tour step is a request for the diagram (GUI crawl 2026-09-02,
// tour.step_not_in_view on mobile). Fail-before: the sheet a tour's evidence
// link had opened at half height stayed there through the next tour, so the
// canvas kept 203 of its 469 px on a phone and the 231 px workbench node at
// the last stop could never come into view. The store now asks the sheet to
// drop back to peek on every step and at the start of a tour; App consumes it.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "c", name: "C", type: "module", path: "src/c", language: "typescript", framework: null,
    description: null, port: null, children: [], files: ["src/c/index.ts"], entry_points: [],
    config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { typescript: 100 } },
    docs: {
      readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null,
      purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [],
    },
    ...overrides,
  };
}

function makeArchitecture(): Architecture {
  const a = makeComponent({ id: "app/a", name: "A" });
  const b = makeComponent({ id: "app/b", name: "B" });
  const root = makeComponent({ id: "app", name: "App", type: "ios-client", children: [a, b] });
  return {
    name: "T", description: "", repository: null, generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0", root_path: "/t", components: [root], relationships: [], symbols: [],
    files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    tours: [{
      id: "walk", title: "Walk", description: "", statement_kind: "authored_interpretation",
      steps: [
        { target: "app/a", title: "A", narration: "a" },
        { target: "app/b", title: "B", narration: "b" },
      ],
    }],
  } as unknown as Architecture;
}

describe("a tour step asks the mobile sheet for the diagram", () => {
  it("requests the collapse when a tour starts and on every component step", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    useArchStore.getState().clearDetailCollapse();
    expect(useArchStore.getState().collapseDetail).toBe(false);

    useArchStore.getState().startTour("walk");
    expect(useArchStore.getState().collapseDetail).toBe(true);
    expect(useArchStore.getState().revealDetail).toBe(false);

    useArchStore.getState().clearDetailCollapse();
    useArchStore.getState().tourStepNext();
    expect(useArchStore.getState().selectedComponentId).toBe("app/b");
    expect(useArchStore.getState().collapseDetail).toBe(true);
    expect(useArchStore.getState().revealDetail).toBe(false);
  });

  it("leaves a reader-requested reveal alone", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    useArchStore.getState().clearDetailCollapse();
    useArchStore.getState().navigateToComponent("app/a");
    expect(useArchStore.getState().revealDetail).toBe(true);
    expect(useArchStore.getState().collapseDetail).toBe(false);
  });
});
