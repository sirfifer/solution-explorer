import { create } from "zustand";
import type {
  Architecture,
  Component,
  BreadcrumbItem,
  ViewMode,
  Panel,
  Symbol,
  FileInfo,
} from "./types";

interface ArchStore {
  // Data
  architecture: Architecture | null;
  loading: boolean;
  error: string | null;

  // Navigation
  selectedComponentId: string | null;
  breadcrumbs: BreadcrumbItem[];
  drillLevel: string | null; // component id we've drilled into (shows children as nodes)
  viewMode: ViewMode;

  // Panels
  activePanel: Panel;
  detailItem: { type: "component" | "file" | "symbol"; data: Component | FileInfo | Symbol } | null;

  // Search
  searchOpen: boolean;
  searchQuery: string;

  // Theme
  darkMode: boolean;

  // Actions
  setArchitecture: (arch: Architecture) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  selectComponent: (id: string | null) => void;
  drillInto: (component: Component) => void;
  drillUp: () => void;
  navigateToBreadcrumb: (index: number) => void;

  setViewMode: (mode: ViewMode) => void;
  setActivePanel: (panel: Panel) => void;
  showDetail: (type: "component" | "file" | "symbol", data: Component | FileInfo | Symbol) => void;
  closeDetail: () => void;

  setSearchOpen: (open: boolean) => void;
  setSearchQuery: (query: string) => void;

  toggleDarkMode: () => void;

  // Helpers
  getComponentById: (id: string) => Component | null;
  getVisibleComponents: () => Component[];
  getComponentRelationships: () => { source: string; target: string; type: string; label: string | null; port: number | null }[];
  getComponentFiles: (componentId: string) => FileInfo[];
  getComponentSymbols: (componentId: string) => Symbol[];
}

function findComponent(components: Component[], id: string): Component | null {
  for (const comp of components) {
    if (comp.id === id) return comp;
    const found = findComponent(comp.children, id);
    if (found) return found;
  }
  return null;
}

function buildBreadcrumbs(components: Component[], targetId: string): BreadcrumbItem[] {
  const trail: BreadcrumbItem[] = [];

  function search(comps: Component[], path: BreadcrumbItem[]): boolean {
    for (const comp of comps) {
      const current = [...path, { id: comp.id, name: comp.name, type: comp.type }];
      if (comp.id === targetId) {
        trail.push(...current);
        return true;
      }
      if (search(comp.children, current)) return true;
    }
    return false;
  }

  search(components, []);
  return trail;
}

export const useArchStore = create<ArchStore>((set, get) => ({
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

  setArchitecture: (arch) => set({ architecture: arch, loading: false }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error, loading: false }),

  selectComponent: (id) => {
    const arch = get().architecture;
    if (!arch || !id) {
      set({ selectedComponentId: null, detailItem: null });
      return;
    }
    const comp = findComponent(arch.components, id);
    if (comp) {
      set({
        selectedComponentId: id,
        detailItem: { type: "component", data: comp },
        activePanel: "detail",
      });
    }
  },

  drillInto: (component) => {
    const arch = get().architecture;
    if (!arch) return;
    if (component.children.length === 0 && component.files.length === 0) return;

    const crumbs = buildBreadcrumbs(arch.components, component.id);
    set({
      drillLevel: component.id,
      breadcrumbs: crumbs,
      selectedComponentId: null,
      detailItem: null,
    });
  },

  drillUp: () => {
    const { breadcrumbs, architecture } = get();
    if (breadcrumbs.length <= 1) {
      set({ drillLevel: null, breadcrumbs: [], selectedComponentId: null });
      return;
    }
    const parent = breadcrumbs[breadcrumbs.length - 2];
    const newCrumbs = breadcrumbs.slice(0, -1);
    set({
      drillLevel: parent.id,
      breadcrumbs: newCrumbs,
      selectedComponentId: null,
    });
  },

  navigateToBreadcrumb: (index) => {
    const { breadcrumbs } = get();
    if (index < 0) {
      set({ drillLevel: null, breadcrumbs: [], selectedComponentId: null });
      return;
    }
    const crumb = breadcrumbs[index];
    set({
      drillLevel: crumb.id,
      breadcrumbs: breadcrumbs.slice(0, index + 1),
      selectedComponentId: null,
    });
  },

  setViewMode: (mode) => set({ viewMode: mode }),
  setActivePanel: (panel) => set({ activePanel: panel }),

  showDetail: (type, data) =>
    set({ detailItem: { type, data }, activePanel: "detail" }),

  closeDetail: () => set({ detailItem: null, activePanel: null }),

  setSearchOpen: (open) => set({ searchOpen: open, searchQuery: open ? get().searchQuery : "" }),
  setSearchQuery: (query) => set({ searchQuery: query }),

  toggleDarkMode: () => set((s) => ({ darkMode: !s.darkMode })),

  getComponentById: (id) => {
    const arch = get().architecture;
    if (!arch) return null;
    return findComponent(arch.components, id);
  },

  getVisibleComponents: () => {
    const { architecture, drillLevel } = get();
    if (!architecture) return [];

    if (!drillLevel) {
      // Top level: show root components and their direct children
      return flattenTopLevel(architecture.components);
    }

    const parent = findComponent(architecture.components, drillLevel);
    if (!parent) return [];
    return parent.children.length > 0 ? parent.children : [parent];
  },

  getComponentRelationships: () => {
    const { architecture, drillLevel } = get();
    if (!architecture) return [];

    const visible = get().getVisibleComponents();
    const visibleIds = new Set(visible.map((c) => c.id));

    return architecture.relationships.filter(
      (r) => visibleIds.has(r.source) && visibleIds.has(r.target)
    );
  },

  getComponentFiles: (componentId) => {
    const { architecture } = get();
    if (!architecture) return [];
    const comp = findComponent(architecture.components, componentId);
    if (!comp) return [];
    return architecture.files.filter((f) => comp.files.includes(f.path));
  },

  getComponentSymbols: (componentId) => {
    const { architecture } = get();
    if (!architecture) return [];
    const files = get().getComponentFiles(componentId);
    const symbolIds = new Set(files.flatMap((f) => f.symbols));
    return architecture.symbols.filter((s) => symbolIds.has(s.id));
  },
}));

function flattenTopLevel(components: Component[]): Component[] {
  const result: Component[] = [];
  for (const comp of components) {
    if (comp.type === "project" && comp.children.length > 0) {
      result.push(...comp.children);
    } else if (comp.type === "repository") {
      // In multi-repo mode, show repository nodes as top-level drillable groups
      result.push(comp);
    } else {
      result.push(comp);
    }
  }
  return result;
}
