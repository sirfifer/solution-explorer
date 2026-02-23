import { create } from "zustand";
import type {
  Architecture,
  Annotation,
  AnnotationTarget,
  AnnotationTargetContext,
  Component,
  BreadcrumbItem,
  ViewMode,
  Panel,
  Symbol,
  FileInfo,
  Relationship,
  LiveConfig,
  LiveVersion,
  StatusOverlay,
  ChangelogEntry,
} from "./types";
import { isHeroType, isClientType, isServerType } from "./utils/layout";

// Storage key for dark mode preference (localStorage for persistence across sessions)
const DARK_MODE_KEY = "arch-dark-mode";
const ENHANCED_FRAMES_KEY = "arch-enhanced-frames";
const CHANGELOG_READ_KEY = "arch-changelog-read";

// High-water mark + sparse read set for efficient read tracking.
// w = watermark (everything at or below is read), r = individually-read serials above watermark.
interface ChangelogReadState {
  w: number;
  r: number[];
}

function getStoredChangelogRead(): ChangelogReadState {
  try {
    const stored = localStorage.getItem(CHANGELOG_READ_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      if (typeof parsed.w === "number" && Array.isArray(parsed.r)) {
        return parsed as ChangelogReadState;
      }
    }
  } catch {
    // Ignore parse errors
  }
  return { w: 0, r: [] };
}

function saveStoredChangelogRead(state: ChangelogReadState): void {
  try {
    localStorage.setItem(CHANGELOG_READ_KEY, JSON.stringify(state));
  } catch {
    // Ignore storage errors
  }
}

// Collapse the watermark forward when sparse reads fill contiguous gaps.
function collapseChangelogRead(state: ChangelogReadState): ChangelogReadState {
  const sorted = [...state.r].sort((a, b) => a - b);
  let w = state.w;
  let i = 0;
  while (i < sorted.length && sorted[i] <= w + 1) {
    if (sorted[i] === w + 1) w = sorted[i];
    i++;
  }
  return { w, r: sorted.slice(i) };
}

function isSerialRead(state: ChangelogReadState, serial: number): boolean {
  return serial <= state.w || state.r.includes(serial);
}

function getStoredDarkMode(): boolean {
  try {
    const stored = localStorage.getItem(DARK_MODE_KEY);
    if (stored !== null) {
      return JSON.parse(stored) as boolean;
    }
  } catch {
    // Ignore parse errors
  }
  // Default to dark mode
  return true;
}

function saveStoredDarkMode(value: boolean): void {
  try {
    localStorage.setItem(DARK_MODE_KEY, JSON.stringify(value));
  } catch {
    // Ignore storage errors
  }
}

function getStoredEnhancedFrames(): boolean {
  try {
    const stored = localStorage.getItem(ENHANCED_FRAMES_KEY);
    if (stored !== null) {
      return JSON.parse(stored) as boolean;
    }
  } catch {
    // Ignore parse errors
  }
  // Default to enhanced frames
  return true;
}

function saveStoredEnhancedFrames(value: boolean): void {
  try {
    localStorage.setItem(ENHANCED_FRAMES_KEY, JSON.stringify(value));
  } catch {
    // Ignore storage errors
  }
}

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
  enhancedFrames: boolean;

  // Review mode
  reviewMode: boolean;
  annotations: Annotation[];
  annotatingComponentId: string | null;
  annotatingTarget: { type: AnnotationTarget; id: string; name: string; targetContext?: AnnotationTargetContext } | null;

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
  toggleEnhancedFrames: () => void;

  // Review actions
  toggleReviewMode: () => void;
  setAnnotatingComponent: (id: string | null) => void;
  setAnnotatingTarget: (target: { type: AnnotationTarget; id: string; name: string; componentId: string; targetContext?: AnnotationTargetContext } | null) => void;
  addAnnotation: (componentId: string, text: string, targetType?: AnnotationTarget, targetId?: string, targetName?: string, targetContext?: AnnotationTargetContext) => void;
  updateAnnotation: (id: string, text: string) => void;
  deleteAnnotation: (id: string) => void;
  clearAllAnnotations: () => void;
  getAnnotationsForComponent: (componentId: string) => Annotation[];
  getAnnotationsForTarget: (targetType: AnnotationTarget, targetId: string) => Annotation[];

  // Live monitoring
  adminOpen: boolean;
  liveConfig: LiveConfig | null;
  liveVersion: LiveVersion | null;
  liveMonitorStatus: "idle" | "polling" | "updating" | "error" | "paused";
  statusOverlay: StatusOverlay | null;

  setAdminOpen: (open: boolean) => void;
  setLiveConfig: (config: LiveConfig | null) => void;
  setLiveVersion: (version: LiveVersion | null) => void;
  setLiveMonitorStatus: (status: "idle" | "polling" | "updating" | "error" | "paused") => void;
  applyStatusOverlay: (overlay: StatusOverlay) => void;
  navigateToComponent: (componentId: string) => void;

  // Component detail cache (for split mode)
  componentDetailCache: Record<string, { symbols: Symbol[]; files: FileInfo[] }>;
  componentDetailLoading: string | null;
  loadComponentDetail: (componentId: string) => Promise<{ symbols: Symbol[]; files: FileInfo[] } | null>;

  // Changelog
  changelogReadState: ChangelogReadState;
  isChangelogEntryRead: (serial: number) => boolean;
  markChangelogEntryRead: (serial: number) => void;
  markAllChangelogRead: () => void;
  getUnreadChangelogCount: () => number;
  getChangelog: () => ChangelogEntry[];

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

function buildComponentIndex(components: Component[]): Map<string, Component> {
  const index = new Map<string, Component>();
  function walk(comps: Component[]) {
    for (const comp of comps) {
      index.set(comp.id, comp);
      walk(comp.children);
    }
  }
  walk(components);
  return index;
}

function findParentId(components: Component[], targetId: string): string | null {
  for (const comp of components) {
    for (const child of comp.children) {
      if (child.id === targetId) return comp.id;
    }
    const found = findParentId(comp.children, targetId);
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

  darkMode: getStoredDarkMode(),
  enhancedFrames: getStoredEnhancedFrames(),

  componentDetailCache: {},
  componentDetailLoading: null,

  reviewMode: false,
  annotations: [],
  annotatingComponentId: null,
  annotatingTarget: null,

  adminOpen: false,
  liveConfig: null,
  liveVersion: null,
  liveMonitorStatus: "idle",
  statusOverlay: null,
  changelogReadState: getStoredChangelogRead(),

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

  toggleDarkMode: () => set((s) => {
    const newValue = !s.darkMode;
    saveStoredDarkMode(newValue);
    return { darkMode: newValue };
  }),
  toggleEnhancedFrames: () => set((s) => {
    const newValue = !s.enhancedFrames;
    saveStoredEnhancedFrames(newValue);
    return { enhancedFrames: newValue };
  }),

  toggleReviewMode: () => set((s) => ({
    reviewMode: !s.reviewMode,
    annotatingComponentId: null,
    annotatingTarget: null,
    activePanel: !s.reviewMode ? s.activePanel : s.activePanel === "review" ? null : s.activePanel,
  })),

  setAnnotatingComponent: (id) => set({ annotatingComponentId: id, annotatingTarget: null }),

  setAnnotatingTarget: (target) => set({
    annotatingComponentId: target?.componentId ?? null,
    annotatingTarget: target ? { type: target.type, id: target.id, name: target.name, targetContext: target.targetContext } : null,
  }),

  addAnnotation: (componentId, text, targetType = "component", targetId, targetName, targetContext) => set((s) => {
    const finalTargetId = targetId ?? componentId;
    const finalTargetName = targetName ?? "";
    // For component-level annotations, replace existing; for others, replace by (targetType, targetId)
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
          targetContext,
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

  setAdminOpen: (open) => set({ adminOpen: open }),
  setLiveConfig: (config) => set({ liveConfig: config }),
  setLiveVersion: (version) => set({ liveVersion: version }),
  setLiveMonitorStatus: (status) => set({ liveMonitorStatus: status }),

  applyStatusOverlay: (overlay) => {
    const arch = get().architecture;
    if (!arch) {
      set({ statusOverlay: overlay });
      return;
    }

    // Build flat index for O(1) lookups
    const index = buildComponentIndex(arch.components);

    // Deep clone components to avoid mutating the existing tree
    const updatedComponents = JSON.parse(JSON.stringify(arch.components)) as Component[];
    const updatedIndex = buildComponentIndex(updatedComponents);

    // Merge component statuses
    for (const [componentId, statuses] of Object.entries(overlay.components)) {
      const comp = updatedIndex.get(componentId);
      if (comp) {
        comp.live_status = {
          statuses,
          last_updated: overlay.updated_at,
        };
      }
    }

    // Set architecture-level live_status
    const updatedArch: Architecture = {
      ...arch,
      components: updatedComponents,
      live_status: {
        ...arch.live_status,
        statuses: overlay.architecture,
        last_commit_sha: overlay.commit_sha,
        last_updated: overlay.updated_at,
      },
    };

    set({ architecture: updatedArch, statusOverlay: overlay });
  },

  navigateToComponent: (componentId) => {
    const arch = get().architecture;
    if (!arch) return;

    const comp = findComponent(arch.components, componentId);
    if (!comp) return;

    // Check if the component is top-level (no parent)
    const parentId = findParentId(arch.components, componentId);

    if (parentId) {
      // Nested component: drill to parent, then select
      const parent = findComponent(arch.components, parentId);
      if (parent) {
        const crumbs = buildBreadcrumbs(arch.components, parentId);
        set({
          drillLevel: parentId,
          breadcrumbs: crumbs,
          selectedComponentId: componentId,
          detailItem: { type: "component", data: comp },
          activePanel: "detail",
        });
      }
    } else {
      // Top-level component: just select it
      set({
        drillLevel: null,
        breadcrumbs: [],
        selectedComponentId: componentId,
        detailItem: { type: "component", data: comp },
        activePanel: "detail",
      });
    }
  },

  isChangelogEntryRead: (serial) => {
    return isSerialRead(get().changelogReadState, serial);
  },

  markChangelogEntryRead: (serial) => {
    const current = get().changelogReadState;
    if (isSerialRead(current, serial)) return;
    const updated = collapseChangelogRead({ w: current.w, r: [...current.r, serial] });
    saveStoredChangelogRead(updated);
    set({ changelogReadState: updated });
  },

  markAllChangelogRead: () => {
    const arch = get().architecture;
    const serial = arch?.changelog_serial ?? 0;
    const updated: ChangelogReadState = { w: serial, r: [] };
    saveStoredChangelogRead(updated);
    set({ changelogReadState: updated });
  },

  getUnreadChangelogCount: () => {
    const { architecture, changelogReadState } = get();
    if (!architecture?.changelog) return 0;
    return architecture.changelog.filter((e) => !isSerialRead(changelogReadState, e.serial)).length;
  },

  getChangelog: () => {
    return get().architecture?.changelog ?? [];
  },

  getAnnotationsForComponent: (componentId) => {
    return get().annotations.filter((a) => a.componentId === componentId);
  },

  getAnnotationsForTarget: (targetType, targetId) => {
    return get().annotations.filter((a) => a.targetType === targetType && a.targetId === targetId);
  },

  loadComponentDetail: async (componentId) => {
    // Already cached
    const cached = get().componentDetailCache[componentId];
    if (cached) return cached;

    // In monolithic mode (files/symbols loaded in architecture), no need to fetch
    const arch = get().architecture;
    if (arch && arch.files.length > 0) return null;

    set({ componentDetailLoading: componentId });
    const safeId = componentId.replace(/\//g, "--");
    try {
      const res = await fetch(`./architecture/data/detail-${safeId}.json`);
      if (res.ok) {
        const detail = await res.json();
        set((state) => ({
          componentDetailCache: { ...state.componentDetailCache, [componentId]: detail },
          componentDetailLoading: null,
        }));
        // Add to search index
        const { addToSearchIndex } = await import("./utils/search");
        addToSearchIndex(detail.symbols || [], detail.files || []);
        return detail;
      }
    } catch {
      // Fetch failed, leave as null
    }
    set({ componentDetailLoading: null });
    return null;
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
    // Check detail cache first (split mode)
    const cached = get().componentDetailCache[componentId];
    if (cached) return cached.files;
    // Fall back to monolithic data
    const { architecture } = get();
    if (!architecture) return [];
    const comp = findComponent(architecture.components, componentId);
    if (!comp) return [];
    return architecture.files.filter((f) => comp.files.includes(f.path));
  },

  getComponentSymbols: (componentId) => {
    // Check detail cache first (split mode)
    const cached = get().componentDetailCache[componentId];
    if (cached) return cached.symbols;
    // Fall back to monolithic data
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
