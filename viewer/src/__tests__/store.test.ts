import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import type { Architecture, Component, StatusOverlay, Relationship } from "../types";

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
      adminOpen: false,
      liveConfig: null,
      liveVersion: null,
      liveMonitorStatus: "idle",
      statusOverlay: null,
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

  // Home, drill-up and drill-in all mean "nothing is selected any more", and
  // each used to clear a different subset: the drill and the selection went,
  // detailItem and activePanel stayed, so the reader arrived back at the top of
  // the graph with the previous component's panel still on screen while the
  // beacon reported nothing selected (GUI crawl 2026-09-01,
  // journey.context_leak, tour.exit_leak).
  describe("clearing the selection (Home, drill-up, drill-in)", () => {
    function drilledWithASelection() {
      const grandchild = makeComponent({ id: "gc", name: "Grandchild" });
      const child = makeComponent({ id: "child", name: "Child", children: [grandchild] });
      const parent = makeComponent({ id: "parent", name: "Parent", children: [child] });
      useArchStore.getState().setArchitecture(makeArchitecture({ components: [parent] }));
      useArchStore.getState().drillInto(parent);
      useArchStore.getState().drillInto(child);
      useArchStore.getState().selectComponent("gc");
      const state = useArchStore.getState();
      expect(state.detailItem).not.toBeNull();
      expect(state.activePanel).toBe("detail");
    }

    it("navigateToBreadcrumb(-1) closes the detail panel it left open", () => {
      drilledWithASelection();

      useArchStore.getState().navigateToBreadcrumb(-1);

      const state = useArchStore.getState();
      expect(state.drillLevel).toBeNull();
      expect(state.breadcrumbs).toHaveLength(0);
      expect(state.selectedComponentId).toBeNull();
      expect(state.detailItem).toBeNull();
      expect(state.activePanel).toBeNull();
      expect(state.annotatingComponentId).toBeNull();
    });

    it("drillUp closes the detail panel it left open", () => {
      drilledWithASelection();

      useArchStore.getState().drillUp();

      const state = useArchStore.getState();
      expect(state.drillLevel).toBe("parent");
      expect(state.detailItem).toBeNull();
      expect(state.activePanel).toBeNull();
    });

    it("drillInto closes the previous component's detail panel", () => {
      drilledWithASelection();
      const parent = useArchStore.getState().getComponentById("parent")!;

      useArchStore.getState().drillInto(parent);

      const state = useArchStore.getState();
      expect(state.drillLevel).toBe("parent");
      expect(state.detailItem).toBeNull();
      expect(state.activePanel).toBeNull();
    });

    it("leaves the review panel up in review mode, as selectComponent(null) does", () => {
      drilledWithASelection();
      useArchStore.setState({ reviewMode: true, activePanel: "review" });

      useArchStore.getState().navigateToBreadcrumb(-1);

      const state = useArchStore.getState();
      expect(state.selectedComponentId).toBeNull();
      expect(state.detailItem).toBeNull();
      // The review panel is the workspace, not the old context.
      expect(state.activePanel).toBe("review");
      useArchStore.setState({ reviewMode: false, activePanel: null });
    });

    // Home is the reader's "start over". It used to leave every lens-scoped
    // selection standing, so the beacon and the URL still carried
    // entity=/capability=/rule=/finding= and a half-walked flow from wherever
    // the reader had been (GUI crawl 2026-09-01, journey.context_leak:
    // 'entity="entity:unamentis:curriculum" survived the reset').
    it("navigateToBreadcrumb(-1) clears the lens-scoped selections and the flow walk", () => {
      drilledWithASelection();
      useArchStore.setState({
        selectedCapabilityId: "cap:x",
        selectedEntityId: "entity:x",
        selectedRuleId: "rule:x",
        selectedDesignFindingId: "finding:x",
        flowEntryId: "parent",
        flowStep: 2,
      });

      useArchStore.getState().navigateToBreadcrumb(-1);

      const state = useArchStore.getState();
      expect(state.selectedCapabilityId).toBeNull();
      expect(state.selectedEntityId).toBeNull();
      expect(state.selectedRuleId).toBeNull();
      expect(state.selectedDesignFindingId).toBeNull();
      expect(state.flowEntryId).toBeNull();
      expect(state.flowStep).toBe(0);
    });

    // The other half of the same decision. Drilling up or into a component is
    // movement within the structure lens, not a reset, and a lens switch keeps
    // the selection by design (I12); only Home means "start over".
    it("drillUp leaves the lens-scoped selections alone", () => {
      drilledWithASelection();
      useArchStore.setState({ selectedEntityId: "entity:x", selectedRuleId: "rule:x" });

      useArchStore.getState().drillUp();

      const state = useArchStore.getState();
      expect(state.selectedEntityId).toBe("entity:x");
      expect(state.selectedRuleId).toBe("rule:x");
      useArchStore.setState({ selectedEntityId: null, selectedRuleId: null });
    });
  });

  // The mobile detail sheet's "peek" default is right for a direct tap on a
  // graph node and wrong for a selection the app made for the reader. The store
  // is where the two are told apart: selectComponent is the node tap,
  // navigateToComponent is every path that places the reader somewhere they did
  // not touch (GUI crawl 2026-09-01, tour.evidence_dead on mobile).
  describe("revealDetail", () => {
    function twoComponents() {
      const child = makeComponent({ id: "parent/child", name: "Child" });
      const parent = makeComponent({ id: "parent", name: "Parent", children: [child] });
      useArchStore.getState().setArchitecture(makeArchitecture({ components: [parent] }));
    }

    it("navigateToComponent asks for the detail to be revealed", () => {
      twoComponents();
      expect(useArchStore.getState().revealDetail).toBe(false);

      useArchStore.getState().navigateToComponent("parent/child");

      expect(useArchStore.getState().revealDetail).toBe(true);
      useArchStore.getState().clearRevealDetail();
      expect(useArchStore.getState().revealDetail).toBe(false);
    });

    it("selectComponent, the direct node tap, does not", () => {
      twoComponents();
      useArchStore.getState().clearRevealDetail();

      useArchStore.getState().selectComponent("parent");

      expect(useArchStore.getState().revealDetail).toBe(false);
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

    it("never returns empty when drilling into tab-container with tab children", () => {
      // This reproduces the black screen bug: tab-container children are
      // hero-type "tab" components, but if they have few files and no children
      // of their own, the hero filter would remove everything.
      const tab1 = makeComponent({
        id: "tab-home", name: "Home", type: "tab",
        children: [], files: ["Views/HomeView.swift"],
      });
      const tab2 = makeComponent({
        id: "tab-search", name: "Search", type: "tab",
        children: [], files: ["Views/SearchView.swift"],
      });
      const tabBar = makeComponent({
        id: "tab-bar", name: "Tab Bar", type: "tab-container",
        children: [tab1, tab2],
      });
      const iosClient = makeComponent({
        id: "ios-client", name: "UnaMentis", type: "ios-client",
        children: [tabBar],
      });
      const arch = makeArchitecture({ components: [iosClient] });
      useArchStore.getState().setArchitecture(arch);

      // Drill into iOS client, then into tab bar
      useArchStore.getState().drillInto(iosClient);
      useArchStore.getState().drillInto(tabBar);

      const visible = useArchStore.getState().getVisibleComponents();
      // Must NEVER be empty — the tabs should be visible
      expect(visible.length).toBeGreaterThan(0);
      expect(visible.map((c) => c.id)).toContain("tab-home");
      expect(visible.map((c) => c.id)).toContain("tab-search");
    });

    it("falls back to showing all children when hero filter removes everything", () => {
      // Edge case: all children are non-hero with few files, but a hero
      // grandchild gets promoted and then sibling non-heroes get filtered.
      const screen = makeComponent({
        id: "screen-1", name: "Detail Screen", type: "screen",
        children: [], files: ["DetailScreen.swift"],
      });
      const helper = makeComponent({
        id: "helper-1", name: "Helpers", type: "module",
        children: [], files: ["Helpers.swift"],
      });
      const wrapper = makeComponent({
        id: "wrapper", name: "Feature", type: "module",
        children: [screen, helper],
      });
      const parent = makeComponent({
        id: "parent", name: "Parent", type: "ios-client",
        children: [wrapper],
      });
      const arch = makeArchitecture({ components: [parent] });
      useArchStore.getState().setArchitecture(arch);

      useArchStore.getState().drillInto(parent);

      const visible = useArchStore.getState().getVisibleComponents();
      // The screen (hero) should survive, and the helper should fall back
      // to being shown since removing it would leave too few visible items.
      expect(visible.length).toBeGreaterThan(0);
      expect(visible.map((c) => c.id)).toContain("screen-1");
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

  describe("adminOpen", () => {
    it("toggles admin open state", () => {
      expect(useArchStore.getState().adminOpen).toBe(false);

      useArchStore.getState().setAdminOpen(true);
      expect(useArchStore.getState().adminOpen).toBe(true);

      useArchStore.getState().setAdminOpen(false);
      expect(useArchStore.getState().adminOpen).toBe(false);
    });
  });

  describe("liveMonitorStatus", () => {
    it("transitions between statuses", () => {
      expect(useArchStore.getState().liveMonitorStatus).toBe("idle");

      useArchStore.getState().setLiveMonitorStatus("polling");
      expect(useArchStore.getState().liveMonitorStatus).toBe("polling");

      useArchStore.getState().setLiveMonitorStatus("updating");
      expect(useArchStore.getState().liveMonitorStatus).toBe("updating");

      useArchStore.getState().setLiveMonitorStatus("error");
      expect(useArchStore.getState().liveMonitorStatus).toBe("error");

      useArchStore.getState().setLiveMonitorStatus("paused");
      expect(useArchStore.getState().liveMonitorStatus).toBe("paused");

      useArchStore.getState().setLiveMonitorStatus("idle");
      expect(useArchStore.getState().liveMonitorStatus).toBe("idle");
    });
  });

  describe("applyStatusOverlay", () => {
    it("merges component statuses correctly", () => {
      const comp1 = makeComponent({ id: "comp-1", name: "Service A" });
      const comp2 = makeComponent({ id: "comp-2", name: "Service B" });
      const arch = makeArchitecture({ components: [comp1, comp2] });
      useArchStore.getState().setArchitecture(arch);

      const overlay: StatusOverlay = {
        components: {
          "comp-1": {
            "ci:build": { level: "error", title: "Build failed", category: "ci", updated_at: "2025-01-01T00:00:00Z" },
          },
          "comp-2": {
            "ci:build": { level: "ok", title: "Build passed", category: "ci", updated_at: "2025-01-01T00:00:00Z" },
          },
        },
        architecture: {},
        updated_at: "2025-01-01T00:00:00Z",
        commit_sha: "abc123",
      };

      useArchStore.getState().applyStatusOverlay(overlay);

      const state = useArchStore.getState();
      const updatedComp1 = state.architecture!.components.find((c) => c.id === "comp-1");
      const updatedComp2 = state.architecture!.components.find((c) => c.id === "comp-2");

      expect(updatedComp1?.live_status?.statuses["ci:build"].level).toBe("error");
      expect(updatedComp2?.live_status?.statuses["ci:build"].level).toBe("ok");
      expect(state.statusOverlay).toBe(overlay);
    });

    it("sets architecture-level statuses", () => {
      const arch = makeArchitecture({});
      useArchStore.getState().setArchitecture(arch);

      const overlay: StatusOverlay = {
        components: {},
        architecture: {
          "deploy:production": { level: "warning", title: "Deploy pending", category: "deploy", updated_at: "2025-01-01T00:00:00Z" },
        },
        updated_at: "2025-01-01T00:00:00Z",
        commit_sha: "def456",
      };

      useArchStore.getState().applyStatusOverlay(overlay);

      const state = useArchStore.getState();
      expect(state.architecture!.live_status?.statuses?.["deploy:production"]?.level).toBe("warning");
      expect(state.architecture!.live_status?.last_commit_sha).toBe("def456");
      expect(state.architecture!.live_status?.last_updated).toBe("2025-01-01T00:00:00Z");
    });

    it("merges statuses for nested components", () => {
      const child = makeComponent({ id: "child-1", name: "Nested Service" });
      const parent = makeComponent({ id: "parent-1", name: "Parent", children: [child] });
      const arch = makeArchitecture({ components: [parent] });
      useArchStore.getState().setArchitecture(arch);

      const overlay: StatusOverlay = {
        components: {
          "child-1": {
            "security:scan": { level: "warning", title: "Vulnerability found", category: "security", updated_at: "2025-01-01T00:00:00Z" },
          },
        },
        architecture: {},
        updated_at: "2025-01-01T00:00:00Z",
        commit_sha: "ghi789",
      };

      useArchStore.getState().applyStatusOverlay(overlay);

      const state = useArchStore.getState();
      const nestedComp = state.architecture!.components[0].children[0];
      expect(nestedComp.live_status?.statuses["security:scan"].level).toBe("warning");
    });

    it("preserves referential identity for components whose status did not change (F-VW-5)", () => {
      const grandchild = makeComponent({ id: "gc-1", name: "Grandchild" });
      const unchangedChild = makeComponent({ id: "child-untouched", name: "Untouched", children: [grandchild] });
      const changed = makeComponent({ id: "comp-changed", name: "Changes" });
      const unchangedParent = makeComponent({ id: "parent-untouched", name: "Untouched parent", children: [unchangedChild] });
      const arch = makeArchitecture({ components: [changed, unchangedParent] });
      useArchStore.getState().setArchitecture(arch);

      const before = useArchStore.getState().architecture!;
      const beforeChanged = before.components.find((c) => c.id === "comp-changed")!;
      const beforeUntouchedParent = before.components.find((c) => c.id === "parent-untouched")!;

      const overlay: StatusOverlay = {
        components: {
          "comp-changed": {
            "ci:build": { level: "error", title: "Build failed", category: "ci", updated_at: "2025-01-01T00:00:00Z" },
          },
        },
        architecture: {},
        updated_at: "2025-02-02T00:00:00Z",
        commit_sha: "sha-overlay",
      };
      useArchStore.getState().applyStatusOverlay(overlay);

      const after = useArchStore.getState().architecture!;
      const afterChanged = after.components.find((c) => c.id === "comp-changed")!;
      const afterUntouchedParent = after.components.find((c) => c.id === "parent-untouched")!;

      // The changed component becomes a new object carrying the overlaid status.
      expect(afterChanged).not.toBe(beforeChanged);
      expect(afterChanged.live_status?.statuses["ci:build"].level).toBe("error");

      // The untouched subtree keeps referential identity end to end. The pre-fix
      // JSON deep clone replaced every node object, so these identity checks
      // failed. React Flow now re-renders only the changed node.
      expect(afterUntouchedParent).toBe(beforeUntouchedParent);
      expect(afterUntouchedParent.children[0]).toBe(beforeUntouchedParent.children[0]);
      expect(afterUntouchedParent.children[0].children[0]).toBe(grandchild);
    });

    it("keeps an open component detail panel coherent with the overlaid tree (F-VW-5)", () => {
      const comp = makeComponent({ id: "comp-detail", name: "Detailed" });
      const arch = makeArchitecture({ components: [comp] });
      useArchStore.getState().setArchitecture(arch);
      useArchStore.getState().selectComponent("comp-detail");

      useArchStore.getState().applyStatusOverlay({
        components: {
          "comp-detail": {
            "ci:build": { level: "error", title: "Build failed", category: "ci", updated_at: "2025-01-01T00:00:00Z" },
          },
        },
        architecture: {},
        updated_at: "2025-02-02T00:00:00Z",
        commit_sha: "sha",
      });

      const state = useArchStore.getState();
      const detailComp = state.detailItem!.data as Component;
      const treeComp = state.architecture!.components.find((c) => c.id === "comp-detail")!;
      // The detail panel points at the refreshed component, not the stranded
      // pre-overlay object, so it shows the new status.
      expect(detailComp).toBe(treeComp);
      expect(detailComp.live_status?.statuses["ci:build"].level).toBe("error");
    });
  });

  describe("connectionCounts (F-VW-6)", () => {
    function makeRel(source: string, target: string, type = "depends_on"): Relationship {
      return { source, target, type, label: null, protocol: null, port: null, bidirectional: false };
    }

    it("precomputes per-component connection counts on setArchitecture", () => {
      const a = makeComponent({ id: "a" });
      const b = makeComponent({ id: "b" });
      const c = makeComponent({ id: "c" });
      const arch = makeArchitecture({
        components: [a, b, c],
        relationships: [makeRel("a", "b"), makeRel("a", "b", "http"), makeRel("c", "a")],
      });
      useArchStore.getState().setArchitecture(arch);

      const counts = useArchStore.getState().connectionCounts;
      expect(counts["a"]).toEqual({ incoming: 1, outgoing: 2 });
      expect(counts["b"]).toEqual({ incoming: 2, outgoing: 0 });
      expect(counts["c"]).toEqual({ incoming: 0, outgoing: 1 });
    });

    it("reuses the same connectionCounts map across a status overlay (relationships unchanged)", () => {
      const a = makeComponent({ id: "a" });
      const b = makeComponent({ id: "b" });
      const arch = makeArchitecture({ components: [a, b], relationships: [makeRel("a", "b")] });
      useArchStore.getState().setArchitecture(arch);

      const before = useArchStore.getState().connectionCounts;
      useArchStore.getState().applyStatusOverlay({
        components: {
          a: { "ci:build": { level: "ok", title: "ok", category: "ci", updated_at: "t" } },
        },
        architecture: {},
        updated_at: "t",
        commit_sha: "s",
      });
      // No recompute, same object reference, so ComponentNode selectors that read
      // connectionCounts do not fire on a status poll.
      expect(useArchStore.getState().connectionCounts).toBe(before);
    });
  });

  describe("navigateToComponent", () => {
    it("selects and drills to nested component", () => {
      const grandchild = makeComponent({ id: "gc-1", name: "Grandchild" });
      const child = makeComponent({ id: "child-1", name: "Child", children: [grandchild] });
      const parent = makeComponent({ id: "parent-1", name: "Parent", children: [child] });
      const arch = makeArchitecture({ components: [parent] });
      useArchStore.getState().setArchitecture(arch);

      useArchStore.getState().navigateToComponent("gc-1");

      const state = useArchStore.getState();
      expect(state.selectedComponentId).toBe("gc-1");
      expect(state.drillLevel).toBe("child-1");
      expect(state.activePanel).toBe("detail");
      expect(state.detailItem?.type).toBe("component");
      expect((state.detailItem?.data as Component).id).toBe("gc-1");
    });

    it("handles top-level component without drilling", () => {
      const comp = makeComponent({ id: "top-1", name: "Top Level" });
      const arch = makeArchitecture({ components: [comp] });
      useArchStore.getState().setArchitecture(arch);

      useArchStore.getState().navigateToComponent("top-1");

      const state = useArchStore.getState();
      expect(state.selectedComponentId).toBe("top-1");
      expect(state.drillLevel).toBeNull();
      expect(state.breadcrumbs).toHaveLength(0);
      expect(state.activePanel).toBe("detail");
    });

    it("does nothing for nonexistent component", () => {
      const arch = makeArchitecture({ components: [] });
      useArchStore.getState().setArchitecture(arch);

      useArchStore.getState().navigateToComponent("nonexistent");

      const state = useArchStore.getState();
      expect(state.selectedComponentId).toBeNull();
      expect(state.drillLevel).toBeNull();
    });

    it("does nothing when no architecture loaded", () => {
      useArchStore.getState().navigateToComponent("some-id");

      const state = useArchStore.getState();
      expect(state.selectedComponentId).toBeNull();
    });
  });
});
