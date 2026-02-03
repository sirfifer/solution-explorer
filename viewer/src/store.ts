import { create } from "zustand";
import type {
  Architecture,
  Annotation,
  AnnotationTarget,
  Component,
  BreadcrumbItem,
  ViewMode,
  Panel,
  Symbol,
  FileInfo,
  Relationship,
} from "./types";
import { isHeroType, isClientType, isServerType } from "./utils/layout";

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

  // Review mode
  reviewMode: boolean;
  annotations: Annotation[];
  annotatingComponentId: string | null;
  annotatingTarget: { type: AnnotationTarget; id: string; name: string } | null;

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

  // Review actions
  toggleReviewMode: () => void;
  setAnnotatingComponent: (id: string | null) => void;
  setAnnotatingTarget: (target: { type: AnnotationTarget; id: string; name: string; componentId: string } | null) => void;
  addAnnotation: (componentId: string, text: string, targetType?: AnnotationTarget, targetId?: string, targetName?: string) => void;
  updateAnnotation: (id: string, text: string) => void;
  deleteAnnotation: (id: string) => void;
  clearAllAnnotations: () => void;
  getAnnotationsForComponent: (componentId: string) => Annotation[];
  getAnnotationsForTarget: (targetType: AnnotationTarget, targetId: string) => Annotation[];

  // Helpers
  getComponentById: (id: string) => Component | null;
  getVisibleComponents: () => Component[];
  getComponentRelationships: () => Relationship[];
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

  reviewMode: false,
  annotations: [],
  annotatingComponentId: null,
  annotatingTarget: null,

  setArchitecture: (arch) => set({ architecture: arch, loading: false }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error, loading: false }),

  selectComponent: (id) => {
    const arch = get().architecture;
    if (!arch || !id) {
      set({ selectedComponentId: null, detailItem: null, activePanel: get().reviewMode ? get().activePanel : null, annotatingComponentId: null });
      return;
    }
    const comp = findComponent(arch.components, id);
    if (comp) {
      if (get().reviewMode) {
        set({
          selectedComponentId: id,
          annotatingComponentId: id,
        });
      } else {
        set({
          selectedComponentId: id,
          detailItem: { type: "component", data: comp },
          activePanel: "detail",
        });
      }
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

  toggleReviewMode: () => set((s) => ({
    reviewMode: !s.reviewMode,
    annotatingComponentId: null,
    annotatingTarget: null,
    activePanel: !s.reviewMode ? s.activePanel : s.activePanel === "review" ? null : s.activePanel,
  })),

  setAnnotatingComponent: (id) => set({ annotatingComponentId: id, annotatingTarget: null }),

  setAnnotatingTarget: (target) => set({
    annotatingComponentId: target?.componentId ?? null,
    annotatingTarget: target ? { type: target.type, id: target.id, name: target.name } : null,
  }),

  addAnnotation: (componentId, text, targetType = "component", targetId, targetName) => set((s) => {
    const finalTargetId = targetId ?? componentId;
    const finalTargetName = targetName ?? "";
    // For component-level annotations, replace existing; for others, always append
    const filtered = targetType === "component"
      ? s.annotations.filter((a) => !(a.componentId === componentId && a.targetType === "component"))
      : s.annotations.filter((a) => !(a.targetType === targetType && a.targetId === finalTargetId));
    return {
      annotations: [
        ...filtered,
        {
          id: crypto.randomUUID(),
          componentId,
          targetType,
          targetId: finalTargetId,
          targetName: finalTargetName,
          text,
          createdAt: new Date().toISOString(),
        },
      ],
      annotatingComponentId: null,
      annotatingTarget: null,
    };
  }),

  updateAnnotation: (id, text) => set((s) => ({
    annotations: s.annotations.map((a) => a.id === id ? { ...a, text } : a),
  })),

  deleteAnnotation: (id) => set((s) => ({
    annotations: s.annotations.filter((a) => a.id !== id),
  })),

  clearAllAnnotations: () => set({ annotations: [], annotatingComponentId: null, annotatingTarget: null }),

  getAnnotationsForComponent: (componentId) => {
    return get().annotations.filter((a) => a.componentId === componentId);
  },

  getAnnotationsForTarget: (targetType, targetId) => {
    return get().annotations.filter((a) => a.targetType === targetType && a.targetId === targetId);
  },

  getComponentById: (id) => {
    const arch = get().architecture;
    if (!arch) return null;
    return findComponent(arch.components, id);
  },

  getVisibleComponents: () => {
    const { architecture, drillLevel } = get();
    if (!architecture) return [];

    if (!drillLevel) {
      // Top level: show clients (Domain 1) and their dependent servers (Domain 2)
      return flattenTopLevel(architecture.components, architecture.relationships)
        .filter((c) => c.type !== "content");
    }

    const parent = findComponent(architecture.components, drillLevel);
    if (!parent) return [];
    // When drilled in, promote hero grandchildren from non-hero wrappers
    const children = parent.children.length > 0 ? parent.children : [parent];
    const promoted = promoteDrillChildren(children);
    const hasHero = promoted.some((c) => isHeroType(c.type));
    return promoted.filter((c) => {
      if (c.type === "content") return false;
      // When hero components exist at this level, hide small internal modules
      if (hasHero && !isHeroType(c.type)
          && c.type !== "library" && c.type !== "infrastructure"
          && c.children.length === 0 && c.files.length < 10) {
        return false;
      }
      return true;
    });
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

// Collect Domain 1 (client) and Domain 2 candidate (server) components,
// unwrapping structural containers up to a limited depth.
// Once we find a client or server, we STOP: those are the entry points.
// maxUnwrap limits how many levels of non-client/non-server wrappers we pierce.
function collectTopLevelCandidates(
  components: Component[],
  maxUnwrap: number = 2,
): Component[] {
  const result: Component[] = [];

  for (const comp of components) {
    if (comp.type === "project" || comp.type === "repository") {
      // Structural wrapper: always recurse (doesn't count against maxUnwrap)
      result.push(...collectTopLevelCandidates(comp.children, maxUnwrap));
    } else if (isClientType(comp.type) || isServerType(comp.type)) {
      // Domain 1 or Domain 2 candidate: surface it and STOP.
      result.push(comp);
    } else if (maxUnwrap > 0) {
      // Non-client, non-server wrapper (module, package, library, etc.)
      // Check if it directly contains clients/servers (one more level)
      const childCandidates = collectTopLevelCandidates(comp.children, maxUnwrap - 1);
      if (childCandidates.length > 0) {
        // It's a wrapper: skip it, promote the candidates
        result.push(...childCandidates);
      }
      // Otherwise: Domain 3, not surfaced at top level
    }
    // If maxUnwrap === 0, we've gone too deep into wrappers; stop here
  }

  return result;
}

// Given all components and relationships, return the set of component IDs
// for servers that have at least one client-type component depending on them.
function findClientFacingServerIds(
  components: Component[],
  relationships: Relationship[],
): Set<string> {
  const clientIds = new Set<string>();
  function collectClientIds(comps: Component[]) {
    for (const c of comps) {
      if (isClientType(c.type)) clientIds.add(c.id);
      collectClientIds(c.children);
    }
  }
  collectClientIds(components);

  const clientFacingServerIds = new Set<string>();
  for (const rel of relationships) {
    if (clientIds.has(rel.source) && !clientIds.has(rel.target)) {
      clientFacingServerIds.add(rel.target);
    }
    if (clientIds.has(rel.target) && !clientIds.has(rel.source)) {
      clientFacingServerIds.add(rel.source);
    }
  }

  return clientFacingServerIds;
}

// Recursively collect hero-type components for drill-down promotion.
// Unlike collectTopLevelCandidates (which is strict about domains), this
// surfaces all hero types within a drilled component's subtree.
function collectDrillHeroes(components: Component[]): Component[] {
  const result: Component[] = [];
  for (const comp of components) {
    if (isHeroType(comp.type)) {
      result.push(comp);
    } else {
      result.push(...collectDrillHeroes(comp.children));
    }
  }
  return result;
}

// When drilled into a component, promote hero grandchildren from non-hero
// wrappers so they appear at the current level instead of being hidden behind
// generic "module" or "package" blocks.
function promoteDrillChildren(children: Component[]): Component[] {
  const result: Component[] = [];

  for (const child of children) {
    if (isHeroType(child.type)) {
      // Already a hero: keep as-is
      result.push(child);
    } else {
      // Non-hero wrapper: check if it contains hero children
      const childHeroes = collectDrillHeroes(child.children);
      if (childHeroes.length > 0) {
        // Promote the hero grandchildren to this level
        result.push(...childHeroes);
        // Also keep non-hero siblings that are substantial
        for (const grandchild of child.children) {
          if (!isHeroType(grandchild.type)
              && grandchild.type !== "content"
              && !childHeroes.includes(grandchild)) {
            result.push(grandchild);
          }
        }
      } else {
        // No hero children: keep the wrapper itself
        result.push(child);
      }
    }
  }

  return result;
}

export function flattenTopLevel(
  components: Component[],
  relationships: Relationship[],
): Component[] {
  const candidates = collectTopLevelCandidates(components);

  if (candidates.length === 0) {
    // Fallback: no clients or servers detected, use folder-based one-level unwrap
    const result: Component[] = [];
    for (const comp of components) {
      if (comp.type === "project" && comp.children.length > 0) {
        result.push(...comp.children);
      } else {
        result.push(comp);
      }
    }
    return result;
  }

  // Separate clients from servers
  const clients = candidates.filter((c) => isClientType(c.type));
  const serverCandidates = candidates.filter((c) => isServerType(c.type));

  // Determine which servers are client-facing using relationship data
  const clientFacingIds = findClientFacingServerIds(components, relationships);

  // Domain 1: all clients, always included
  // Domain 2: servers that a client depends on
  const topLevel = [...clients];

  for (const server of serverCandidates) {
    if (clientFacingIds.has(server.id)) {
      topLevel.push(server);
    }
  }

  // Safety net: if clients exist but zero servers survived the relationship
  // filter, include all server-typed candidates. This handles cases where the
  // analyzer didn't detect the client-to-server relationship (e.g., the client
  // uses an environment variable for the API URL).
  if (clients.length > 0 && topLevel.length === clients.length && serverCandidates.length > 0) {
    topLevel.push(...serverCandidates);
  }

  return topLevel;
}
