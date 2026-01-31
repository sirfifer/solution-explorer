import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import type { Architecture, Component } from "../types";

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "test-comp",
    name: "Test Component",
    type: "module",
    path: "src/test",
    language: "typescript",
    framework: null,
    description: null,
    port: null,
    children: [],
    files: ["src/test/index.ts"],
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
    name: "Test Project",
    description: "A test project",
    repository: null,
    generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.0.0",
    root_path: "/test",
    components: [],
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

describe("ArchStore", () => {
  beforeEach(() => {
    // Reset store to initial state
    useArchStore.setState({
      architecture: null,
      loading: true,
      error: null,
      selectedComponentId: null,
      breadcrumbs: [],
      drillLevel: null,
      viewMode: "graph",
      activePanel: null,
      detailItem: null,
      searchOpen: false,
      searchQuery: "",
      darkMode: true,
    });
  });

  describe("setArchitecture", () => {
    it("stores architecture and stops loading", () => {
      const arch = makeArchitecture();
      useArchStore.getState().setArchitecture(arch);

      const state = useArchStore.getState();
      expect(state.architecture).toBe(arch);
      expect(state.loading).toBe(false);
    });
  });

  describe("setError", () => {
    it("stores error and stops loading", () => {
      useArchStore.getState().setError("Something failed");

      const state = useArchStore.getState();
      expect(state.error).toBe("Something failed");
      expect(state.loading).toBe(false);
    });
  });

  describe("selectComponent", () => {
    it("selects a component by id", () => {
      const comp = makeComponent({ id: "comp-1", name: "Comp 1" });
      const arch = makeArchitecture({ components: [comp] });
      useArchStore.getState().setArchitecture(arch);

      useArchStore.getState().selectComponent("comp-1");

      const state = useArchStore.getState();
      expect(state.selectedComponentId).toBe("comp-1");
      expect(state.detailItem?.type).toBe("component");
      expect(state.activePanel).toBe("detail");
    });

    it("clears selection when id is null", () => {
      useArchStore.getState().selectComponent(null);

      const state = useArchStore.getState();
      expect(state.selectedComponentId).toBeNull();
      expect(state.detailItem).toBeNull();
    });

    it("does nothing if component not found", () => {
      const arch = makeArchitecture({ components: [] });
      useArchStore.getState().setArchitecture(arch);

      useArchStore.getState().selectComponent("nonexistent");

      const state = useArchStore.getState();
      expect(state.selectedComponentId).toBeNull();
    });
  });

  describe("drillInto", () => {
    it("drills into a component with children", () => {
      const child = makeComponent({ id: "child-1", name: "Child" });
      const parent = makeComponent({
        id: "parent-1",
        name: "Parent",
        children: [child],
      });
      const arch = makeArchitecture({ components: [parent] });
      useArchStore.getState().setArchitecture(arch);

      useArchStore.getState().drillInto(parent);

      const state = useArchStore.getState();
      expect(state.drillLevel).toBe("parent-1");
      expect(state.breadcrumbs.length).toBeGreaterThan(0);
    });

    it("does not drill into leaf component", () => {
      const leaf = makeComponent({ id: "leaf", children: [], files: [] });
      const arch = makeArchitecture({ components: [leaf] });
      useArchStore.getState().setArchitecture(arch);

      useArchStore.getState().drillInto(leaf);

      expect(useArchStore.getState().drillLevel).toBeNull();
    });
  });

  describe("drillUp", () => {
    it("goes up one level in breadcrumbs", () => {
      const grandchild = makeComponent({ id: "gc", name: "Grandchild" });
      const child = makeComponent({ id: "child", name: "Child", children: [grandchild] });
      const parent = makeComponent({ id: "parent", name: "Parent", children: [child] });
      const arch = makeArchitecture({ components: [parent] });
      useArchStore.getState().setArchitecture(arch);

      // Drill to child
      useArchStore.getState().drillInto(parent);
      useArchStore.getState().drillInto(child);
      expect(useArchStore.getState().drillLevel).toBe("child");

      // Drill up
      useArchStore.getState().drillUp();
      expect(useArchStore.getState().drillLevel).toBe("parent");
    });

    it("returns to root when at top level", () => {
      const child = makeComponent({ id: "child", name: "Child" });
      const parent = makeComponent({ id: "parent", name: "Parent", children: [child] });
      const arch = makeArchitecture({ components: [parent] });
      useArchStore.getState().setArchitecture(arch);

      useArchStore.getState().drillInto(parent);
      useArchStore.getState().drillUp();

      expect(useArchStore.getState().drillLevel).toBeNull();
      expect(useArchStore.getState().breadcrumbs).toHaveLength(0);
    });
  });

  describe("getVisibleComponents", () => {
    it("returns top-level components when not drilled", () => {
      const comp = makeComponent({ id: "comp-1" });
      const arch = makeArchitecture({ components: [comp] });
      useArchStore.getState().setArchitecture(arch);

      const visible = useArchStore.getState().getVisibleComponents();
      expect(visible.length).toBe(1);
      expect(visible[0].id).toBe("comp-1");
    });

    it("flattens project-type components", () => {
      const child1 = makeComponent({ id: "child-1", name: "Child 1" });
      const child2 = makeComponent({ id: "child-2", name: "Child 2" });
      const project = makeComponent({
        id: "project",
        name: "Project",
        type: "project",
        children: [child1, child2],
      });
      const arch = makeArchitecture({ components: [project] });
      useArchStore.getState().setArchitecture(arch);

      const visible = useArchStore.getState().getVisibleComponents();
      expect(visible.length).toBe(2);
      expect(visible.map((c) => c.id)).toContain("child-1");
      expect(visible.map((c) => c.id)).toContain("child-2");
    });

    it("keeps repository-type components as drillable groups", () => {
      const child = makeComponent({ id: "child-1", name: "Service" });
      const repo = makeComponent({
        id: "repo:backend",
        name: "backend",
        type: "repository",
        children: [child],
      });
      const arch = makeArchitecture({ components: [repo] });
      useArchStore.getState().setArchitecture(arch);

      const visible = useArchStore.getState().getVisibleComponents();
      expect(visible.length).toBe(1);
      expect(visible[0].id).toBe("repo:backend");
      expect(visible[0].type).toBe("repository");
    });

    it("shows children when drilled into a component", () => {
      const child1 = makeComponent({ id: "child-1", name: "Child 1" });
      const child2 = makeComponent({ id: "child-2", name: "Child 2" });
      const parent = makeComponent({
        id: "parent",
        name: "Parent",
        children: [child1, child2],
      });
      const arch = makeArchitecture({ components: [parent] });
      useArchStore.getState().setArchitecture(arch);

      useArchStore.getState().drillInto(parent);
      const visible = useArchStore.getState().getVisibleComponents();
      expect(visible.length).toBe(2);
    });
  });

  describe("getComponentRelationships", () => {
    it("returns relationships between visible components", () => {
      const comp1 = makeComponent({ id: "a", name: "A" });
      const comp2 = makeComponent({ id: "b", name: "B" });
      const arch = makeArchitecture({
        components: [comp1, comp2],
        relationships: [
          { source: "a", target: "b", type: "import", label: null, protocol: null, port: null, bidirectional: false },
        ],
      });
      useArchStore.getState().setArchitecture(arch);

      const rels = useArchStore.getState().getComponentRelationships();
      expect(rels.length).toBe(1);
      expect(rels[0].source).toBe("a");
      expect(rels[0].target).toBe("b");
    });

    it("filters out relationships with non-visible components", () => {
      const comp1 = makeComponent({ id: "a", name: "A" });
      const arch = makeArchitecture({
        components: [comp1],
        relationships: [
          { source: "a", target: "hidden", type: "import", label: null, protocol: null, port: null, bidirectional: false },
        ],
      });
      useArchStore.getState().setArchitecture(arch);

      const rels = useArchStore.getState().getComponentRelationships();
      expect(rels.length).toBe(0);
    });
  });

  describe("toggleDarkMode", () => {
    it("toggles dark mode", () => {
      expect(useArchStore.getState().darkMode).toBe(true);

      useArchStore.getState().toggleDarkMode();
      expect(useArchStore.getState().darkMode).toBe(false);

      useArchStore.getState().toggleDarkMode();
      expect(useArchStore.getState().darkMode).toBe(true);
    });
  });

  describe("search", () => {
    it("opens and closes search", () => {
      useArchStore.getState().setSearchOpen(true);
      expect(useArchStore.getState().searchOpen).toBe(true);

      useArchStore.getState().setSearchOpen(false);
      expect(useArchStore.getState().searchOpen).toBe(false);
    });

    it("clears query when closing", () => {
      useArchStore.getState().setSearchOpen(true);
      useArchStore.getState().setSearchQuery("test");
      expect(useArchStore.getState().searchQuery).toBe("test");

      useArchStore.getState().setSearchOpen(false);
      expect(useArchStore.getState().searchQuery).toBe("");
    });
  });
});
