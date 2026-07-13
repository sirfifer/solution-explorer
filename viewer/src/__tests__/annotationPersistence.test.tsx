import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { useArchStore } from "../store";
import { ReviewSummary } from "../components/ReviewSummary";
import type { Architecture, Component } from "../types";

// Regression tests for F-VW-4 (P1-3): review annotations must survive a hard
// reload and re-analysis. They exercise the real store (no store mock) and the
// real annotationStorage localStorage layer provided by jsdom.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "comp-a",
    name: "Component A",
    type: "module",
    path: "src/a",
    language: "typescript",
    framework: null,
    description: null,
    port: null,
    children: [],
    files: ["src/a/index.ts"],
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

function makeArchitecture(overrides: Partial<Architecture> = {}): Architecture {
  return {
    name: "Demo Project",
    description: "A test project",
    repository: "https://github.com/acme/demo",
    generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0",
    root_path: "/demo",
    components: [makeComponent()],
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
    ...overrides,
  };
}

// Simulate a fresh page load: the module-level Zustand store is a singleton, so
// wipe its in-memory annotation/architecture state to mimic a reload while
// localStorage (the persistence layer) survives, exactly as a browser reload does.
function simulateReload() {
  useArchStore.setState({ architecture: null, annotations: [], componentDetailCache: {} });
}

describe("annotation persistence (F-VW-4 / P1-3)", () => {
  beforeEach(() => {
    localStorage.clear();
    useArchStore.setState({ architecture: null, annotations: [], componentDetailCache: {}, reviewMode: false, activePanel: null });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("restores annotations after a hard reload", () => {
    const arch = makeArchitecture();
    useArchStore.getState().setArchitecture(arch);

    useArchStore.getState().addAnnotation("comp-a", "Looks fragile here");
    expect(useArchStore.getState().annotations).toHaveLength(1);

    simulateReload();
    expect(useArchStore.getState().annotations).toHaveLength(0);

    // Reloading the same architecture must restore the annotation from storage.
    useArchStore.getState().setArchitecture(makeArchitecture());
    const restored = useArchStore.getState().annotations;
    expect(restored).toHaveLength(1);
    expect(restored[0].text).toBe("Looks fragile here");
    expect(restored[0].componentId).toBe("comp-a");
  });

  it("keys on identity, not generated_at, so re-analysis preserves annotations", () => {
    useArchStore.getState().setArchitecture(makeArchitecture({ generated_at: "2025-01-01T00:00:00Z" }));
    useArchStore.getState().addAnnotation("comp-a", "keep me across scans");

    simulateReload();

    // Same name + repository, brand-new generated_at (a re-analysis).
    useArchStore.getState().setArchitecture(makeArchitecture({ generated_at: "2026-07-11T12:00:00Z" }));
    expect(useArchStore.getState().annotations).toHaveLength(1);
    expect(useArchStore.getState().annotations[0].text).toBe("keep me across scans");
  });

  it("keeps orphaned annotations after loading a changed architecture (not silently dropped)", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    useArchStore.getState().addAnnotation("comp-a", "feedback on a component that will be removed");

    simulateReload();

    // Same identity (name + repository) but the component is gone after re-analysis.
    const changed = makeArchitecture({ components: [makeComponent({ id: "comp-b", name: "Component B", files: ["src/b/index.ts"] })] });
    useArchStore.getState().setArchitecture(changed);

    const anns = useArchStore.getState().annotations;
    expect(anns).toHaveLength(1);
    expect(anns[0].componentId).toBe("comp-a");
    // The component itself is truly gone.
    expect(useArchStore.getState().getComponentById("comp-a")).toBeNull();
  });

  it("surfaces orphaned annotations in ReviewSummary instead of hiding them", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    useArchStore.getState().addAnnotation("comp-a", "orphan-visible-text");

    simulateReload();
    const changed = makeArchitecture({ components: [makeComponent({ id: "comp-b", name: "Component B", files: ["src/b/index.ts"] })] });
    useArchStore.getState().setArchitecture(changed);

    render(<ReviewSummary />);
    expect(screen.getByTestId("orphaned-annotations")).toBeTruthy();
    expect(screen.getByText("orphan-visible-text")).toBeTruthy();
  });

  it("does not crash when localStorage write fails (quota)", () => {
    const arch = makeArchitecture();
    useArchStore.getState().setArchitecture(arch);

    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });

    expect(() => useArchStore.getState().addAnnotation("comp-a", "still works in memory")).not.toThrow();
    expect(useArchStore.getState().annotations).toHaveLength(1);
    spy.mockRestore();
  });

  it("removing annotations persists the removal", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    useArchStore.getState().addAnnotation("comp-a", "temporary note");
    useArchStore.getState().clearAllAnnotations();

    simulateReload();
    useArchStore.getState().setArchitecture(makeArchitecture());
    expect(useArchStore.getState().annotations).toHaveLength(0);
  });
});
