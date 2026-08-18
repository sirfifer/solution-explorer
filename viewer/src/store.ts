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
  AggregateNode,
  CoverageRow,
  Inventory,
  ActivityData,
  ActivityComponent,
  ActivityFile,
  Capability,
  DataEntity,
  EntityAccess,
  Finding,
  Concern,
  Tour,
  TourStep,
  Rule,
  SelectionSet,
  SetMember,
  SetAnnotation,
  LiveConfig,
  LiveVersion,
  StatusOverlay,
  ChangelogEntry,
  Publication,
} from "./types";
import type { SearchResult } from "./utils/search";
import { addToSearchIndex } from "./utils/search";
import { resolveChannel } from "./utils/channel";
import {
  getLens,
  resolveLensId,
  DEFAULT_LENS_ID,
  type LensGraph,
  type FlowEntry,
  collectFlowComponents,
  buildFlowEdges,
  buildAdjacency,
  walkFlow,
  rankEntryFlows,
} from "./lenses";
import {
  sortFindings,
  findingsForComponent,
} from "./findings/model";
import { isHeroType, isClientType, isServerType } from "./utils/layout";
import { safeComponentId } from "./utils/componentId";
import { dataUrl } from "./utils/dataSource";
import { rollUpRelationships } from "./utils/relationshipRollup";
import { buildDegreeIndex, compareByImportance } from "./utils/importance";
import {
  architectureIdentity,
  loadAnnotations,
  saveAnnotations,
} from "./utils/annotationStorage";
import { loadSelectionSets, saveSelectionSets } from "./utils/setStorage";
import { generateDirective, type DirectiveModel } from "./utils/directiveGenerator";

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

  // Publication metadata sidecar (publication.json). Optional and independent of
  // the projection: it feeds only the presentation layer (display name, header
  // banner, footer attribution) and never analysis. null when the sidecar is
  // absent or invalid, in which case the viewer renders exactly as today.
  publication: Publication | null;
  setPublication: (publication: Publication | null) => void;

  // Navigation
  selectedComponentId: string | null;
  breadcrumbs: BreadcrumbItem[];
  drillLevel: string | null; // component id we've drilled into (shows children as nodes)
  viewMode: ViewMode;

  // Lens (P6-1). The active perspective. Structure is the default and renders
  // pixel-identically for old data. Switching lens preserves selection,
  // breadcrumbs, drill level, and URL state (invariant I12).
  lens: string;
  setLens: (id: string) => void;
  getLensGraph: () => LensGraph;

  // Flow lens follow state (P6-2, LENS-DESIGN L4). `flowEntryId` is the entry
  // flow currently being walked (null on the ranked landing); `flowStep` is the
  // index into that entry's walk. The walk itself is derived (getFlowPath), not
  // stored, so it always reflects the loaded architecture.
  flowEntryId: string | null;
  flowStep: number;
  getFlowEntries: () => FlowEntry[];
  getFlowPath: (entryId: string) => string[];
  setFlowEntry: (entryId: string | null) => void;
  flowStepNext: () => void;
  flowStepPrev: () => void;
  flowGoToStep: (step: number) => void;
  clearFlow: () => void;

  // Capability and Data lens selection (P6-3, LENS-DESIGN L2/L3). The selected
  // capability/entity drives the panel highlight and the URL param; selecting one
  // also selects its owning component (I12 stable identity) and opens the matching
  // detail tab. Reset on architecture reload.
  selectedCapabilityId: string | null;
  selectedEntityId: string | null;
  selectCapability: (capabilityId: string) => void;
  selectEntity: (entityId: string) => void;
  clearCapability: () => void;
  clearEntity: () => void;
  getCapabilities: () => Capability[];
  getDataEntities: () => DataEntity[];
  getEntityAccess: () => EntityAccess[];
  // The access edges touching one entity (who reads/writes it), for the Data lens
  // focused view; empty when the entity has no access edges.
  getEntityAccessors: (entityId: string) => EntityAccess[];

  // Rules lens selection (P6-6, LENS-DESIGN L6). The selected rule drives the
  // panel highlight and the URL param; selecting one also selects its owning
  // component (I12 stable identity). The two cross-lens jumps switch lens AND
  // select the linked element, preserving identity and URL state. Reset on reload.
  selectedRuleId: string | null;
  selectRule: (ruleId: string) => void;
  clearRule: () => void;
  getRules: () => Rule[];
  // Jump from a rule to the Data lens with the rule's linked entity focused (the
  // L3 cross-link). No-op when the rule carries no entity link. Returns whether it
  // jumped, so the UI can gate the affordance.
  viewRuleInDataLens: (ruleId: string) => boolean;
  // Jump from a rule to the Capability lens with the rule's trigger capability
  // selected (the L2 cross-link). No-op when the rule has no capability trigger.
  viewRuleInCapabilityLens: (ruleId: string) => boolean;

  // A one-shot request to open a specific detail-panel tab (P6-3). Set when
  // selecting a capability/entity so the panel jumps to its Capabilities/Data tab;
  // the panel consumes and clears it. Null when nothing is pending.
  pendingDetailTab: string | null;
  setPendingDetailTab: (tab: string) => void;
  clearPendingDetailTab: () => void;

  // Panels
  activePanel: Panel;
  detailItem: { type: "component" | "file" | "symbol" | "aggregate"; data: Component | FileInfo | Symbol | AggregateNode } | null;

  // Search
  searchOpen: boolean;
  searchQuery: string;

  // Theme
  darkMode: boolean;
  enhancedFrames: boolean;

  // Mobile UI
  mobileChromeHidden: boolean;
  setMobileChromeHidden: (hidden: boolean) => void;

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
  // Node budget derived from the rendered canvas; see nodeBudgetForCanvas.
  nodeBudget: number;
  setNodeBudget: (n: number) => void;
  // Reduce the budget one step when a laid-out level came out unreadable.
  // Returns false once it has bottomed out. See shrinkNodeBudget.
  shrinkNodeBudget: () => boolean;
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

  // Selection sets and set-level annotations (P6-9, LENS-DESIGN section 10).
  // Sets are addressable, nameable collections of members keyed on stable
  // identity, created from a finding, a concern, search results, or manual
  // multi-select. They and their annotations persist alongside single-element
  // annotations by the same architecture identity. Restored on setArchitecture.
  selectionSets: SelectionSet[];
  setAnnotations: SetAnnotation[];
  // Create a set from an explicit member list. Returns the new set's id.
  createSet: (name: string, origin: string, members: SetMember[]) => string;
  // Create a set from a finding's members (clone cluster, orphan, ...). No-op
  // (returns null) when the finding id is unknown. Origin `finding:<id>`.
  createSetFromFinding: (findingId: string) => string | null;
  // Create a set from a concern's members. No-op (returns null) when the concern
  // id is unknown. Origin `concern:<id>`.
  createSetFromConcern: (concernId: string) => string | null;
  // Create a set from the current search results. Origin `search:<query>`.
  createSetFromSearchResults: (query: string, results: SearchResult[]) => string;
  // Manual multi-select: add a component to a set. A null setId appends to (or
  // creates) the manual set. Returns the target set's id. De-dupes by ref.
  addComponentToSet: (setId: string | null, componentId: string) => string | null;
  renameSet: (setId: string, name: string) => void;
  deleteSet: (setId: string) => void;
  setSetIntent: (setId: string, intent: string) => void;
  setSetMemberNote: (setId: string, memberRef: string, note: string) => void;
  getSelectionSets: () => SelectionSet[];
  getSetById: (setId: string) => SelectionSet | null;
  getSetAnnotation: (setId: string) => SetAnnotation | null;
  // Navigate to a set member on its stable identity (I12): always via its owning
  // component so component/file/symbol members all land coherently.
  navigateToSetMember: (member: SetMember) => void;

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

  // Inbound file/line deep links (P3-2). fileDeepLink records the resolved
  // target so the Files tab can highlight the file and (when the line resolves a
  // symbol) mark it. fileDeepLinkNotice carries a non-blocking "file not found"
  // message for the missing case.
  fileDeepLink: { componentId: string; filePath: string; line: number | null; symbolId: string | null } | null;
  fileDeepLinkNotice: string | null;
  openFileDeepLink: (filePath: string, line: number | null) => Promise<"found" | "missing">;
  clearFileDeepLinkNotice: () => void;

  // Component detail cache (for split mode)
  componentDetailCache: Record<string, { symbols: Symbol[]; files: FileInfo[] }>;
  // Per-component loading keys (componentId -> true while in flight) so two
  // simultaneous loads for different components do not clobber each other's
  // loading state (F-VW-7).
  componentDetailLoading: Record<string, boolean>;
  // Per-component detail fetch errors, surfaced in the panel and used as a
  // negative cache so a failed fetch does not refire on every re-open (F-VW-7).
  componentDetailErrors: Record<string, string>;
  loadComponentDetail: (componentId: string) => Promise<{ symbols: Symbol[]; files: FileInfo[] } | null>;
  retryComponentDetail: (componentId: string) => Promise<{ symbols: Symbol[]; files: FileInfo[] } | null>;
  // Predictive prefetch of the detail shards likely to be opened next (P6-4).
  prefetchDetails: (componentId: string) => void;

  // Coverage ledger drill-in rows (P4-4). The badge reads the summary directly
  // from `architecture.coverage`; the panel needs the full rows, which live in
  // the monolith inline but are fetched lazily from coverage.json in split mode.
  coverageRows: CoverageRow[] | null;
  coverageRowsLoading: boolean;
  coverageRowsError: string | null;
  loadCoverageRows: () => Promise<CoverageRow[] | null>;

  // Non-source inventory (P6-10). Rides in coverage.json (split) or inline under
  // architecture.coverage.inventory (monolith), so it arrives with the same
  // lazy fetch as the coverage rows. Null until loaded or when the dataset
  // carries no inventory (old datasets), which the panel degrades on.
  coverageInventory: Inventory | null;

  // Git-activity data (P5-4 / P6-5 Activity lens). The full ranked hotspot list,
  // per-component knowledge, coupling, and per-file detail live in activity.json
  // (split) or inline under architecture.activity (monolith). Loaded lazily on
  // first Activity-lens use or first rationale-strip render, so author/last-
  // change/churn flow into the rationale strip everywhere (I13). Reset on reload.
  activityData: ActivityData | null;
  activityLoading: boolean;
  activityError: string | null;
  loadActivity: () => Promise<ActivityData | null>;
  // Ranked hotspot list (the I11 landing view), already ordered by hotspot score
  // by the projection. Empty until activity data is loaded.
  getHotspots: () => ActivityComponent[];
  getActivityComponent: (componentId: string) => ActivityComponent | null;
  // Change coupling reached FROM a component ("what changes with this"): the
  // cross-component partners, ranked by co-change count. Never a standalone
  // hairball; always anchored to a component id (LENS-DESIGN L5).
  getCouplingForComponent: (componentId: string) => Array<{ partnerId: string; partnerName: string; count: number }>;
  // A component's per-file hotspot detail, ranked (drill-in from a hotspot).
  getComponentActivityFiles: (componentId: string) => Array<ActivityFile & { path: string }>;

  // Findings surface (P6-8, LENS-DESIGN sections 8-10). A globally reachable
  // ranked overlay, available whenever the dataset carries findings or concerns.
  // Transient UI state like SearchOverlay/AdminDashboard (not URL-synced); reset
  // on architecture reload. `elementFilter` scopes the findings list to one
  // component when the contextual detail-panel badge opens the surface.
  findingsSurface: {
    open: boolean;
    tab: "findings" | "concerns";
    kindFilter: string | null;
    elementFilter: string | null;
  };
  openFindingsSurface: (opts?: {
    tab?: "findings" | "concerns";
    kindFilter?: string | null;
    elementFilter?: string | null;
  }) => void;
  closeFindingsSurface: () => void;
  setFindingsSurfaceTab: (tab: "findings" | "concerns") => void;
  setFindingsKindFilter: (kind: string | null) => void;

  // Supply chain surface (P10-1). A globally reachable overlay listing the SBOM
  // (ecosystems, dependencies, targets), available whenever the dataset carries a
  // supply_chain section. Transient UI state like the findings surface (not
  // URL-synced); reset on architecture reload.
  supplyChainOpen: boolean;
  openSupplyChain: () => void;
  closeSupplyChain: () => void;
  // Ranked findings (rank_score desc; I11) and concerns from the projection.
  getFindings: () => Finding[];
  getConcerns: () => Concern[];
  // The findings touching a component (contextual badge; derived from members).
  getFindingsForComponent: (componentId: string) => Finding[];
  getConcernById: (id: string) => Concern | null;

  // Selection-set seam for set-level actions (P6-9 engine, LENS-DESIGN section
  // 10), now wired live from the findings surface (the P6-8/P6-9 integration).
  // `stagedFindingSet` remains as a lightweight record of the last-staged finding
  // membership; the annotate and export affordances below build real selection
  // sets and directives through the P6-9 engine.
  stagedFindingSet: {
    findingId: string;
    label: string;
    memberComponentIds: string[];
    memberCount: number;
  } | null;
  stageFindingSet: (finding: Finding) => void;
  clearStagedSet: () => void;
  // The "annotate the set" affordance (I15), live. Builds (or reuses) a real
  // selection set from the finding's members via the P6-9 engine
  // (createSetFromFinding), closes the findings overlay, and opens the set
  // annotation flow in the review panel so the reviewer states the shared intent
  // and per-member notes. Returns the set id (null when the finding is unknown).
  annotateFindingSet: (finding: Finding) => string | null;
  // The same affordance for a concern row: builds (or reuses) a selection set
  // from the concern's members (createSetFromConcern) and opens the annotation
  // flow. Returns the set id (null when the concern is unknown).
  annotateConcernSet: (concern: Concern) => string | null;
  // The "export directive" affordance (I15), live. Builds (or reuses) a selection
  // set from the finding's members, then renders the structured work-order
  // directive (markdown + embedded, versioned JSON) through the P6-9 generator,
  // using any set annotation already attached. Returns null when the finding is
  // unknown or no architecture is loaded.
  exportDirectiveForFinding: (findingId: string) => { markdown: string; model: DirectiveModel } | null;
  // The same for a concern row: build (or reuse) the concern's set and render its
  // directive. Returns null when the concern is unknown.
  exportDirectiveForConcern: (concernId: string) => { markdown: string; model: DirectiveModel } | null;

  // Tours: guided-walkthrough player (P6-7, LENS-DESIGN L7). Tours ride the
  // projection under architecture.tours (the data-first contract); the player is
  // transient UI state, NOT a store table of tour artifacts (that plus the
  // enrichment-side generation are the analyzer follow-up). `toursOpen` toggles
  // the tour list; `activeTourId`/`tourStep` are the walk in progress. All reset
  // on architecture reload, exactly like the Flow walk (P6-2).
  toursOpen: boolean;
  activeTourId: string | null;
  tourStep: number;
  openTours: () => void;
  closeTours: () => void;
  getTours: () => Tour[];
  getTourById: (id: string) => Tour | null;
  // Start playing a tour: land on step 0 and select its target on stable identity
  // (I12). No-op for an unknown or empty tour.
  startTour: (tourId: string) => void;
  // Step forward/back along the active tour, selecting the step's target. No-op at
  // the ends of the walk.
  tourStepNext: () => void;
  tourStepPrev: () => void;
  // Jump directly to a step (the progress breadcrumb).
  tourGoToStep: (step: number) => void;
  // Exit the active tour (clears the walk; leaves the last selection in place).
  exitTour: () => void;
  // Navigate to a step's target on stable identity (I12): a component id drills to
  // and selects the component; otherwise the step's evidence file (or a file-path
  // target) opens via the file deep link, resolving the symbol at the line.
  navigateToTourTarget: (step: TourStep) => void;

  // Precomputed per-component connection counts, derived from relationships and
  // refreshed only when the architecture's relationships change. Held stable
  // across status-overlay polls so ComponentNode selectors do not fire on every
  // poll (F-VW-6).
  connectionCounts: Record<string, { incoming: number; outgoing: number }>;

  // Changelog
  changelogReadState: ChangelogReadState;
  isChangelogEntryRead: (serial: number) => boolean;
  markChangelogEntryRead: (serial: number) => void;
  markAllChangelogRead: () => void;
  getUnreadChangelogCount: () => number;
  getChangelog: () => ChangelogEntry[];

  // Aggregation nodes (P6-4). Small internal modules that the hero filter would
  // otherwise hide silently are grouped by type into expandable aggregate nodes
  // so every child at a drill level is visible or visibly aggregated.
  // Expansion state is keyed by aggregate id and reset on architecture reload.
  toggleAggregate: (id: string) => void;
  getAggregateNodes: () => AggregateNode[];

  // Helpers
  getComponentById: (id: string) => Component | null;
  getComponentByFile: (filePath: string) => Component | null;
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

function findComponentByFile(components: Component[], filePath: string): Component | null {
  for (const comp of components) {
    if (comp.files.includes(filePath)) return comp;
    const found = findComponentByFile(comp.children, filePath);
    if (found) return found;
  }
  return null;
}

// Resolve the component that owns a file for a `?file=` deep link (P3-2).
// Ownership is read from the manifest `files` arrays alone, so no detail-file
// fetch is needed to locate the owner. When more than one component lists the
// same path (a parent that aggregates a descendant's files), the DEEPEST
// component wins: it is the most specific owner. Depth is distance from the
// root; ties at equal depth are broken by depth-first pre-order (first
// encountered), which is deterministic for a given manifest.
function findDeepestComponentByFile(
  components: Component[],
  filePath: string,
): Component | null {
  let best: Component | null = null;
  let bestDepth = -1;
  function walk(comps: Component[], depth: number) {
    for (const comp of comps) {
      if (comp.files.includes(filePath) && depth > bestDepth) {
        best = comp;
        bestDepth = depth;
      }
      walk(comp.children, depth + 1);
    }
  }
  walk(components, 0);
  return best;
}

// Count incoming and outgoing relationships per component id in a single pass.
// Used to precompute connection counts once per architecture change so
// ComponentNode does not re-filter the relationship list on every store update
// (F-VW-6).
function computeConnectionCounts(
  relationships: Relationship[],
): Record<string, { incoming: number; outgoing: number }> {
  const counts: Record<string, { incoming: number; outgoing: number }> = {};
  for (const rel of relationships) {
    (counts[rel.source] ??= { incoming: 0, outgoing: 0 }).outgoing++;
    (counts[rel.target] ??= { incoming: 0, outgoing: 0 }).incoming++;
  }
  return counts;
}

// Apply a status overlay to a component tree with structural sharing: only the
// components whose status changed (and the ancestors on their path) get new
// object identities. Every untouched subtree keeps referential identity, so
// React Flow re-renders only the nodes that actually changed instead of the
// whole graph on every poll (F-VW-5).
function applyStatusToComponents(
  components: Component[],
  statusMap: StatusOverlay["components"],
  updatedAt: string,
): { components: Component[]; changed: boolean } {
  let changed = false;
  const next = components.map((comp) => {
    const childResult = applyStatusToComponents(comp.children, statusMap, updatedAt);
    const statuses = statusMap[comp.id];
    if (statuses) {
      changed = true;
      return {
        ...comp,
        children: childResult.components,
        live_status: { statuses, last_updated: updatedAt },
      };
    }
    if (childResult.changed) {
      changed = true;
      return { ...comp, children: childResult.components };
    }
    return comp;
  });
  return changed ? { components: next, changed: true } : { components, changed: false };
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
  // Collapse an immediately repeated name (comprehension-study S8): a repo
  // whose root directory shares its name renders "Home / unamentis /
  // unamentis / server", which reads as a bug. The deeper crumb is kept so
  // clicking it still navigates to the real component.
  return trail.filter(
    (crumb, i) => i === 0 || crumb.name !== trail[i - 1].name,
  );
}

// Persist the current in-memory annotations for the loaded architecture's
// stable identity. Called after every annotation mutation so a hard reload or
// re-analysis restores review work (F-VW-4).
function persistCurrentAnnotations(get: () => ArchStore): void {
  const arch = get().architecture;
  if (!arch) return;
  saveAnnotations(architectureIdentity(arch), get().annotations);
}

// Persist the current selection sets and set-annotations for the loaded
// architecture's stable identity. Called after every set mutation so a hard
// reload or re-analysis restores them, exactly like annotations (P6-9).
function persistCurrentSets(get: () => ArchStore): void {
  const arch = get().architecture;
  if (!arch) return;
  saveSelectionSets(
    architectureIdentity(arch),
    get().selectionSets,
    get().setAnnotations,
  );
}

// Build a set member from one finding member (clone fragment, orphan component).
// Members carry stable identity (I4): a component member's ref is its component
// id; a fragment's ref is its unique file:line id. componentId always resolves
// so navigation and evidence work (I12).
function setMemberFromFinding(m: Finding["members"][number], finding: Finding): SetMember {
  const componentId = m.component_id ?? m.id;
  const kind: SetMember["kind"] =
    m.kind === "component" ? "component" : m.symbol ? "symbol" : "file";
  const label =
    m.symbol && m.file
      ? `${m.symbol} (${m.file.split("/").pop()})`
      : m.file
        ? m.file.split("/").pop() || m.file
        : componentId;
  const evidence: string[] = [];
  const cloneClass = (finding.detail as { clone_class?: string } | undefined)?.clone_class;
  if (cloneClass) evidence.push(`clone class: ${cloneClass}`);
  evidence.push(`finding: ${finding.summary}`);
  if (m.symbol) evidence.push(`symbol: ${m.symbol}`);
  return {
    kind,
    ref: m.id,
    componentId,
    label,
    file: m.file ?? undefined,
    lineStart: m.line_start,
    lineEnd: m.line_end,
    evidence,
  };
}

// Split the promoted children at a drill level into the components shown as real
// nodes and the small internal modules grouped into aggregate nodes (P6-4).
//
// This is the single source of truth for the hero filter. The old code DROPPED
// the small-internal set (only warning if it removed everything); here they are
// diverted into typed aggregates so nothing is ever silently hidden. Content-type
// children stay a deliberate exclusion (assets/data blobs, not code).
function computeDrillLevelView(
  promoted: Component[],
  drillLevel: string | null,
  nodeBudget: number,
  relationships: Relationship[],
): { shown: Component[]; aggregates: AggregateNode[] } {
  const shown: Component[] = [];
  const hiddenByType: Record<string, Component[]> = {};

  // Rank, do not hide by size (LENS-DESIGN I11; owner decision 2026-08-17).
  // The old rule folded away any non-hero child with no children and fewer
  // than ten files, using SIZE as a proxy for IMPORTANCE. On the UnaMentis
  // demo that buried 31 modules behind one box, ten of them tagged critical
  // (STT, LLM, Voice, Session, Context, ...), because Swift modules are small
  // by construction. Visibility is now decided by importance, and the number
  // of visible nodes by what the viewport can actually render readably.
  const candidates = promoted.filter((c) => c.type !== "content");

  // Degree from the relationship set: how many other components this one is
  // wired to, counted once per partner so a chatty pair does not dominate.
  const degree = buildDegreeIndex(relationships);

  // Hero-typed children are the structural anchors of a level (the clients,
  // servers, screens); they are always shown, never aggregated, whatever the
  // budget, because hiding one would break the map's shape.
  const heroes = candidates.filter((c) => isHeroType(c.type));
  const others = candidates.filter((c) => !isHeroType(c.type));
  // The same ordering the double-tap Read snap uses to pick what to frame
  // (utils/importance), so what is shown and what is framed cannot drift.
  others.sort((a, b) => compareByImportance(a, b, degree));

  shown.push(...heroes);
  const room = Math.max(0, nodeBudget - heroes.length);
  for (const [i, c] of others.entries()) {
    if (i < room) shown.push(c);
    else (hiddenByType[c.type] ??= []).push(c);
  }

  const levelKey = drillLevel ?? "root";
  const aggregates: AggregateNode[] = Object.entries(hiddenByType)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([type, members]) => ({
      id: `__agg__${levelKey}__${type}`,
      kind: "aggregate" as const,
      aggregateType: type,
      label: `${members.length} ${type}${members.length !== 1 ? "s" : ""}`,
      members,
      memberCount: members.length,
      parentDrillLevel: drillLevel,
    }));

  return { shown, aggregates };
}

// Compute the current drill level's shown components and aggregates in one pass,
// so getVisibleComponents and getAggregateNodes agree and never double-walk.
function drillView(
  architecture: Architecture,
  drillLevel: string | null,
  nodeBudget: number,
): { shown: Component[]; aggregates: AggregateNode[] } {
  if (!drillLevel) {
    const shown = flattenTopLevel(architecture.components, architecture.relationships)
      .filter((c) => c.type !== "content");
    return { shown, aggregates: [] };
  }
  const parent = findComponent(architecture.components, drillLevel);
  if (!parent) return { shown: [], aggregates: [] };
  const children = parent.children.length > 0 ? parent.children : [parent];
  const promoted = promoteDrillChildren(children);
  return computeDrillLevelView(
    promoted, drillLevel, nodeBudget, architecture.relationships,
  );
}

// How many nodes a drill level should show, derived from the canvas the viewer
// actually has (owner decision 2026-08-17: "It needs to adjust to the view" —
// a phone and a 40-inch 4K display must not get the same budget). A node is
// ~280x140 at zoom 1; requiring it to stay at or above READABLE_ZOOM fixes how
// much canvas each one needs, and the canvas size then decides how many fit.
const NODE_W = 280;
const NODE_H = 140;
const NODE_GAP = 40;
// Below roughly this zoom the labels stop being readable; the failure this
// replaces bottomed out at 0.1, where nodes rendered 7px tall.
export const READABLE_ZOOM = 0.6;
// Comprehension floor and ceiling. The ceiling is not a pixel limit: past a few
// dozen nodes a diagram stops being comprehensible however large the display
// (the "hairy ball" the lens research warns about), so more pixels stop buying
// more understanding.
const MIN_NODE_BUDGET = 6;
const MAX_NODE_BUDGET = 40;

// A laid-out graph consumes far more canvas than its nodes' own area: ELK adds
// rank separation, edge-routing channels, and layer depth, and device-framed
// nodes are taller than the base box. Measured on the real dataset, a naive
// grid model over-budgeted by roughly 3x (it allowed 21 nodes on a laptop,
// which fitView then had to render at 0.14 zoom). This factor is the empirical
// correction, calibrated so a typical drill level lands at or above
// READABLE_ZOOM.
const LAYOUT_SPREAD = 1.75;

export function nodeBudgetForCanvas(width: number, height: number): number {
  if (!(width > 0) || !(height > 0)) return DEFAULT_NODE_BUDGET;
  const cellW = NODE_W * READABLE_ZOOM * LAYOUT_SPREAD + NODE_GAP;
  const cellH = NODE_H * READABLE_ZOOM * LAYOUT_SPREAD + NODE_GAP;
  const capacity = Math.max(Math.floor(width / cellW), 1)
    * Math.max(Math.floor(height / cellH), 1);
  return Math.min(MAX_NODE_BUDGET, Math.max(MIN_NODE_BUDGET, capacity));
}

// Used before the canvas has been measured (first render, tests, SSR).
export const DEFAULT_NODE_BUDGET = 15;

// Predictive prefetch targets (P6-4): the children of the selected component plus
// the breadcrumb ancestors, deduplicated and bounded. These are the components a
// user is most likely to open next (drill down into a child, or navigate back up
// an ancestor), so prefetching their detail shards at idle time makes the next
// open instant. Pure so the target set is testable without scheduling.
export function collectPrefetchTargets(
  architecture: Architecture | null,
  componentId: string,
  breadcrumbs: BreadcrumbItem[],
  limit = 8,
): string[] {
  if (!architecture) return [];
  const comp = findComponent(architecture.components, componentId);
  const ordered: string[] = [];
  // Children first (drill-down is the most common next move).
  if (comp) {
    for (const child of comp.children) ordered.push(child.id);
  }
  // Then breadcrumb ancestors (navigate-up), excluding the selection itself.
  for (const crumb of breadcrumbs) {
    if (crumb.id !== componentId) ordered.push(crumb.id);
  }
  const seen = new Set<string>();
  const result: string[] = [];
  for (const id of ordered) {
    if (id === componentId || seen.has(id)) continue;
    seen.add(id);
    result.push(id);
    if (result.length >= limit) break;
  }
  return result;
}

// Schedule a callback at browser idle time, falling back to a short timeout where
// requestIdleCallback is unavailable (Safari, jsdom). Prefetch is best-effort and
// must never block interaction, so failures are swallowed.
function scheduleIdle(fn: () => void): void {
  const ric = (globalThis as { requestIdleCallback?: (cb: () => void) => void })
    .requestIdleCallback;
  if (typeof ric === "function") {
    ric(() => { try { fn(); } catch { /* best-effort */ } });
  } else {
    setTimeout(() => { try { fn(); } catch { /* best-effort */ } }, 1);
  }
}

// Find-or-create the selection set for a finding/concern so the annotate and
// export affordances on the same row reuse one set instead of spawning a
// duplicate on every click. A finding's/concern's id IS its set origin (the
// createSetFrom* actions use it directly), so the origin is the stable key.
function findOrCreateFindingSet(get: () => ArchStore, findingId: string): string | null {
  const existing = get().selectionSets.find((s) => s.origin === findingId);
  if (existing) return existing.id;
  return get().createSetFromFinding(findingId);
}

function findOrCreateConcernSet(get: () => ArchStore, concernId: string): string | null {
  const existing = get().selectionSets.find((s) => s.origin === concernId);
  if (existing) return existing.id;
  return get().createSetFromConcern(concernId);
}

export const useArchStore = create<ArchStore>((set, get) => ({
  architecture: null,
  loading: true,
  error: null,
  publication: null,
  setPublication: (publication) => set({ publication }),

  selectedComponentId: null,
  breadcrumbs: [],
  drillLevel: null,
  viewMode: "graph",
  lens: DEFAULT_LENS_ID,
  flowEntryId: null,
  flowStep: 0,
  selectedCapabilityId: null,
  selectedEntityId: null,
  selectedRuleId: null,
  pendingDetailTab: null,

  activePanel: null,
  detailItem: null,

  searchOpen: false,
  searchQuery: "",

  darkMode: getStoredDarkMode(),
  enhancedFrames: getStoredEnhancedFrames(),

  componentDetailCache: {},
  componentDetailLoading: {},
  componentDetailErrors: {},
  nodeBudget: DEFAULT_NODE_BUDGET,
  coverageRows: null,
  coverageRowsLoading: false,
  coverageRowsError: null,
  coverageInventory: null,
  activityData: null,
  activityLoading: false,
  activityError: null,
  connectionCounts: {},
  findingsSurface: { open: false, tab: "findings", kindFilter: null, elementFilter: null },
  stagedFindingSet: null,
  supplyChainOpen: false,
  toursOpen: false,
  activeTourId: null,
  tourStep: 0,

  reviewMode: false,
  annotations: [],
  annotatingComponentId: null,
  annotatingTarget: null,
  selectionSets: [],
  setAnnotations: [],

  mobileChromeHidden: false,
  setMobileChromeHidden: (hidden) => set({ mobileChromeHidden: hidden }),

  adminOpen: false,
  liveConfig: null,
  liveVersion: null,
  liveMonitorStatus: "idle",
  statusOverlay: null,
  changelogReadState: getStoredChangelogRead(),

  fileDeepLink: null,
  fileDeepLinkNotice: null,

  setArchitecture: (arch) => {
    // Restore persisted annotations for this architecture's stable identity so
    // a hard reload or re-analysis does not destroy review work (F-VW-4).
    const restored = loadAnnotations(architectureIdentity(arch));
    // Restore persisted selection sets and set-annotations for this architecture
    // identity too, so a hard reload or re-analysis keeps them (P6-9).
    const restoredSets = loadSelectionSets(architectureIdentity(arch));
    // Invalidate the split-mode detail cache on every architecture update so
    // panels refetch fresh files/symbols instead of showing stale data from a
    // previous scan (F-VW-3 / F-VW-7). The next open refetches. This is the
    // single entry point both the initial load and the live monitor use.
    set({
      architecture: arch,
      loading: false,
      annotations: restored,
      selectionSets: restoredSets.sets,
      setAnnotations: restoredSets.annotations,
      componentDetailCache: {},
      // Clear any in-flight loading markers and prior fetch errors too: a live
      // refresh mid-detail-load must not leave the panel stuck in a loading or
      // error state keyed to the old scan.
      componentDetailLoading: {},
      componentDetailErrors: {},
      // Aggregate expansion belongs to a specific tree; drop it on reload so a
      // new scan starts from collapsed aggregates (P6-4).
      // Drop any coverage rows fetched for a previous scan; the panel refetches
      // (or reads the new inline rows) on next open.
      coverageRows: null,
      coverageRowsLoading: false,
      coverageRowsError: null,
      coverageInventory: null,
      // Drop activity data fetched for a previous scan; the Activity lens or the
      // rationale strip refetches (or reads the new inline data) on next use.
      activityData: null,
      activityLoading: false,
      activityError: null,
      // Refresh precomputed connection counts for the new relationship set
      // (F-VW-6). Status overlays reuse this map since they never touch
      // relationships.
      connectionCounts: computeConnectionCounts(arch.relationships),
      // A Flow lens walk belongs to a specific dataset; reset it on reload so a
      // new scan starts from the ranked landing (P6-2).
      flowEntryId: null,
      flowStep: 0,
      // Capability/Data lens selection belongs to a specific dataset; reset on
      // reload so a new scan starts from the ranked landing (P6-3).
      selectedCapabilityId: null,
      selectedEntityId: null,
      // Rules lens selection belongs to a specific dataset; reset on reload (P6-6).
      selectedRuleId: null,
      pendingDetailTab: null,
      // The findings overlay and any staged selection set belong to a specific
      // dataset; reset on reload so a new scan starts closed (P6-8).
      findingsSurface: { open: false, tab: "findings", kindFilter: null, elementFilter: null },
      stagedFindingSet: null,
      // The supply chain overlay belongs to a specific dataset; reset on reload
      // so a new scan starts with it closed (P10-1).
      supplyChainOpen: false,
      // A tour walk belongs to a specific dataset; reset it on reload so a new
      // scan starts with the player closed and no active tour (P6-7).
      toursOpen: false,
      activeTourId: null,
      tourStep: 0,
    });
  },
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
      // Selection always shows the component's details, review mode included
      // (comprehension-study S4: review mode used to withhold the panel, so
      // tree and node clicks appeared dead and the Review Summary owned the
      // right rail). In review mode the selection additionally becomes the
      // annotation target; the Review button reopens the summary.
      set({
        selectedComponentId: id,
        detailItem: { type: "component", data: comp },
        activePanel: "detail",
        ...(get().reviewMode ? { annotatingComponentId: id } : {}),
      });
      // Predictive prefetch: warm the detail shards the user is most likely to
      // open next (children + breadcrumb ancestors) at idle time (P6-4).
      get().prefetchDetails(id);
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
    // Prefetch the newly visible children's detail shards at idle time (P6-4).
    get().prefetchDetails(component.id);
  },

  drillUp: () => {
    const { breadcrumbs } = get();
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

  // Switch lens WITHOUT disturbing the current selection, breadcrumbs, or drill
  // level (invariant I12: the same element stays selected across lens switches).
  // An unknown or unavailable id resolves to the default lens.
  setNodeBudget: (n) => {
    if (get().nodeBudget !== n) set({ nodeBudget: n });
  },

  // Close the loop on readability. The budget a viewport can hold depends on
  // the laid-out graph's shape, not just its node count: two levels with the
  // same number of children can differ several-fold in the canvas they need,
  // because ELK's layer depth follows the edges. So the formula sets the
  // starting point and this shrinks it when a real layout still came out below
  // READABLE_ZOOM. Shrink-only and bounded by the caller, so it converges.
  shrinkNodeBudget: () => {
    const next = Math.max(MIN_NODE_BUDGET, Math.floor(get().nodeBudget * 0.7));
    if (next < get().nodeBudget) {
      set({ nodeBudget: next });
      return true;
    }
    return false;
  },

  setLens: (id) => set((s) => ({ lens: resolveLensId(id, s.architecture, resolveChannel()) })),

  // The active lens's node/edge selection, fed to the graph pipeline. For
  // Structure this is exactly the existing selectors, so old data renders
  // identically. Falls back to the default lens if the active id is unknown.
  getLensGraph: () => {
    const { architecture, drillLevel, lens, selectedCapabilityId, selectedEntityId, selectedRuleId } = get();
    if (!architecture) return { nodes: [], aggregates: [], edges: [] };
    const def = getLens(lens) ?? getLens(DEFAULT_LENS_ID)!;
    return def.getGraph({
      architecture,
      drillLevel,
      getVisibleComponents: get().getVisibleComponents,
      getAggregateNodes: get().getAggregateNodes,
      getComponentRelationships: get().getComponentRelationships,
      selectedCapabilityId,
      selectedEntityId,
      selectedRuleId,
    });
  },

  // The ranked entry flows for the Flow lens landing (I11). Empty when the
  // dataset carries no flow-bearing data, so the panel degrades cleanly.
  getFlowEntries: () => {
    const { architecture } = get();
    if (!architecture) return [];
    const flowComponents = collectFlowComponents(architecture.components);
    const edges = buildFlowEdges(architecture, flowComponents);
    return rankEntryFlows(flowComponents, edges);
  },

  // The ordered walk (DFS pre-order) for one entry flow. Consecutive entries are
  // the "what happens from here" steps; the prefix is the "how did I get here"
  // breadcrumb.
  getFlowPath: (entryId) => {
    const { architecture } = get();
    if (!architecture) return [];
    const flowComponents = collectFlowComponents(architecture.components);
    const edges = buildFlowEdges(architecture, flowComponents);
    return walkFlow(entryId, buildAdjacency(edges));
  },

  // Enter (or leave) follow mode for an entry flow, landing on its first step and
  // selecting that node so the graph centers and highlights it (I12: selection is
  // the shared identity across lenses).
  setFlowEntry: (entryId) => {
    if (!entryId) {
      set({ flowEntryId: null, flowStep: 0 });
      get().selectComponent(null);
      return;
    }
    const path = get().getFlowPath(entryId);
    set({ flowEntryId: entryId, flowStep: 0 });
    if (path.length > 0) get().selectComponent(path[0]);
  },

  // Step forward along the current flow, selecting the next screen. No-op at the
  // end of the walk.
  flowStepNext: () => {
    const { flowEntryId, flowStep } = get();
    if (!flowEntryId) return;
    const path = get().getFlowPath(flowEntryId);
    const next = Math.min(flowStep + 1, path.length - 1);
    if (next === flowStep) return;
    set({ flowStep: next });
    get().selectComponent(path[next]);
  },

  // Step back along the breadcrumbed path. No-op at the entry.
  flowStepPrev: () => {
    const { flowEntryId, flowStep } = get();
    if (!flowEntryId) return;
    const path = get().getFlowPath(flowEntryId);
    const prev = Math.max(flowStep - 1, 0);
    if (prev === flowStep) return;
    set({ flowStep: prev });
    get().selectComponent(path[prev]);
  },

  // Jump directly to a breadcrumb hop.
  flowGoToStep: (step) => {
    const { flowEntryId } = get();
    if (!flowEntryId) return;
    const path = get().getFlowPath(flowEntryId);
    const clamped = Math.max(0, Math.min(step, path.length - 1));
    set({ flowStep: clamped });
    if (path.length > 0) get().selectComponent(path[clamped]);
  },

  clearFlow: () => {
    set({ flowEntryId: null, flowStep: 0 });
    get().selectComponent(null);
  },

  // Capability lens (P6-3). Select a capability: highlight it, select its owning
  // component in the graph (I12 stable identity via navigateToComponent), and
  // request the Capabilities tab so the contract and test linkage are in view.
  selectCapability: (capabilityId) => {
    const cap = get().getCapabilities().find((c) => c.id === capabilityId);
    set({ selectedCapabilityId: capabilityId });
    if (cap?.component_id) {
      get().navigateToComponent(cap.component_id);
      set({ pendingDetailTab: "capabilities" });
    }
  },

  // Data lens (P6-3). Select an entity: record it (driving the ego view in the
  // graph), focus its owning component (I12), and request the Data tab so the
  // fields, evidence, and who-touches-this detail are in view.
  selectEntity: (entityId) => {
    const ent = get().getDataEntities().find((e) => e.id === entityId);
    set({ selectedEntityId: entityId });
    if (ent?.component_id) {
      get().navigateToComponent(ent.component_id);
      set({ pendingDetailTab: "data" });
    }
  },

  clearCapability: () => set({ selectedCapabilityId: null }),
  clearEntity: () => set({ selectedEntityId: null }),

  getCapabilities: () => get().architecture?.capabilities ?? [],
  getDataEntities: () => get().architecture?.data_entities ?? [],
  getEntityAccess: () => get().architecture?.entity_access ?? [],
  getEntityAccessors: (entityId) =>
    (get().architecture?.entity_access ?? []).filter((a) => a.entity_id === entityId),

  // Rules lens (P6-6). Select a rule: highlight it and select its owning component
  // in the graph (I12 stable identity via navigateToComponent) so the rationale
  // strip and component detail follow. There is no Rules detail tab, so no tab is
  // requested; the rule's own detail lives in the RulesPanel focused view.
  selectRule: (ruleId) => {
    const rule = get().getRules().find((r) => r.id === ruleId);
    set({ selectedRuleId: ruleId });
    if (rule?.component_id) {
      get().navigateToComponent(rule.component_id);
    }
  },

  clearRule: () => set({ selectedRuleId: null }),

  getRules: () => get().architecture?.rules ?? [],

  // Cross-lens jump L6 -> L3: switch to the Data lens with the rule's linked
  // entity focused. setLens resolves to Data (available when data_entities exist)
  // and selectEntity focuses the entity's owner (I12) and writes the entity URL
  // param, so identity and URL state are preserved. No-op (returns false) when the
  // rule carries no entity link.
  viewRuleInDataLens: (ruleId) => {
    const rule = get().getRules().find((r) => r.id === ruleId);
    const entityId = rule?.detail.entity;
    if (!entityId) return false;
    get().setLens("data");
    if (get().lens !== "data") return false;
    get().selectEntity(entityId);
    return true;
  },

  // Cross-lens jump L6 -> L2: switch to the Capability lens with the rule's
  // trigger capability selected. Preserves identity (the capability's owner is
  // selected) and URL state (the capability URL param). No-op (returns false) when
  // the rule has no capability trigger.
  viewRuleInCapabilityLens: (ruleId) => {
    const rule = get().getRules().find((r) => r.id === ruleId);
    const capabilityId = rule?.detail.trigger?.capability;
    if (!capabilityId) return false;
    get().setLens("capability");
    if (get().lens !== "capability") return false;
    get().selectCapability(capabilityId);
    return true;
  },

  setPendingDetailTab: (tab) => set({ pendingDetailTab: tab }),
  clearPendingDetailTab: () => set({ pendingDetailTab: null }),

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

  addAnnotation: (componentId, text, targetType = "component", targetId, targetName, targetContext) => {
    set((s) => {
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
    });
    persistCurrentAnnotations(get);
  },

  updateAnnotation: (id, text) => {
    set((s) => ({
      annotations: s.annotations.map((a) => a.id === id ? { ...a, text } : a),
    }));
    persistCurrentAnnotations(get);
  },

  deleteAnnotation: (id) => {
    set((s) => ({
      annotations: s.annotations.filter((a) => a.id !== id),
    }));
    persistCurrentAnnotations(get);
  },

  clearAllAnnotations: () => {
    set({ annotations: [], annotatingComponentId: null, annotatingTarget: null });
    persistCurrentAnnotations(get);
  },

  setAdminOpen: (open) => set({ adminOpen: open }),
  setLiveConfig: (config) => set({ liveConfig: config }),
  setLiveVersion: (version) => set({ liveVersion: version }),
  setLiveMonitorStatus: (status) => set({ liveMonitorStatus: status }),

  applyStatusOverlay: (overlay) => {
    const state = get();
    const arch = state.architecture;
    if (!arch) {
      set({ statusOverlay: overlay });
      return;
    }

    // Targeted immutable update: only components whose status changed get new
    // identities; the rest of the tree is shared by reference (F-VW-5). No
    // full-tree JSON clone, no dead index build. Relationships are untouched, so
    // the precomputed connectionCounts map stays valid and is not recomputed.
    const { components: updatedComponents } = applyStatusToComponents(
      arch.components,
      overlay.components,
      overlay.updated_at,
    );

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

    // Keep an open component detail panel coherent with the refreshed tree so it
    // shows post-overlay status instead of a stranded pre-overlay object (F-VW-5).
    let detailItem = state.detailItem;
    if (detailItem && detailItem.type === "component") {
      const refreshed = findComponent(updatedComponents, (detailItem.data as Component).id);
      if (refreshed) {
        detailItem = { type: "component", data: refreshed };
      }
    }

    set({ architecture: updatedArch, statusOverlay: overlay, detailItem });
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

  openFileDeepLink: async (filePath, line) => {
    const arch = get().architecture;
    if (!arch) return "missing";

    // Resolve the owning component from the manifest file lists (deepest wins).
    const owner = findDeepestComponentByFile(arch.components, filePath);
    if (!owner) {
      // Missing: non-blocking notice, stay on the overview (no navigation).
      set({
        fileDeepLink: null,
        fileDeepLinkNotice: `No component in this architecture owns "${filePath}".`,
      });
      return "missing";
    }

    // Navigate: drill to the owner and open its detail panel. navigateToComponent
    // handles both nested (drill to parent + select) and top-level cases.
    get().navigateToComponent(owner.id);
    set({
      fileDeepLink: { componentId: owner.id, filePath, line, symbolId: null },
      fileDeepLinkNotice: null,
    });

    if (line == null) return "found";

    // Symbol resolution needs the per-component symbols. In split mode these
    // arrive via the detail fetch (loading state handled by the panel); in
    // monolithic mode they are already present. Resolve the symbol whose range
    // contains the line and record it so the Files tab can mark it.
    await get().loadComponentDetail(owner.id);
    const symbols = get().getComponentSymbols(owner.id);
    const match = symbols.find(
      (s) => s.file === filePath && line >= s.line && line <= s.end_line,
    );
    if (match) {
      set((state) =>
        state.fileDeepLink && state.fileDeepLink.filePath === filePath
          ? { fileDeepLink: { ...state.fileDeepLink, symbolId: match.id } }
          : {},
      );
    }
    return "found";
  },

  clearFileDeepLinkNotice: () => set({ fileDeepLinkNotice: null }),

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
    const entries = arch?.changelog ?? [];
    // Derive the watermark from the highest entry serial actually present, since
    // the top-level changelog_serial can be missing or stale relative to the
    // entries. Only fall back to it when there are no entries to read from.
    const serial =
      entries.length > 0
        ? entries.reduce((max, e) => Math.max(max, e.serial), -Infinity)
        : (arch?.changelog_serial ?? 0);
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

  // ─── Selection sets (P6-9) ─────────────────────────────────────────────────

  createSet: (name, origin, members) => {
    // De-dupe members by ref so the same site is never listed twice.
    const seen = new Set<string>();
    const deduped = members.filter((m) => {
      if (seen.has(m.ref)) return false;
      seen.add(m.ref);
      return true;
    });
    const id = crypto.randomUUID();
    const setObj: SelectionSet = {
      id,
      name: name.trim() || "Untitled set",
      origin,
      members: deduped,
      createdAt: new Date().toISOString(),
    };
    set((s) => ({ selectionSets: [...s.selectionSets, setObj] }));
    persistCurrentSets(get);
    return id;
  },

  createSetFromFinding: (findingId) => {
    const arch = get().architecture;
    const finding = arch?.findings?.find((f) => f.id === findingId);
    if (!finding) return null;
    const members = finding.members.map((m) => setMemberFromFinding(m, finding));
    const label =
      finding.kind === "duplication"
        ? `Duplication: ${finding.summary}`
        : finding.kind === "orphan"
          ? `Orphan: ${finding.summary}`
          : finding.kind === "unreferenced"
            ? `Unreferenced: ${finding.summary}`
            : finding.summary;
    // finding.id already carries the "finding:<kind>:..." namespace, so it IS the
    // origin (no extra prefix), giving a clean `finding:duplication:...` origin.
    return get().createSet(label, finding.id, members);
  },

  createSetFromConcern: (concernId) => {
    const arch = get().architecture;
    const concern = arch?.concerns?.find((c) => c.id === concernId);
    if (!concern) return null;
    const members: SetMember[] = concern.members.map((m) => {
      const comp = findComponent(arch!.components, m.component_id);
      const firstEv = m.evidence[0];
      const evidence: string[] = [];
      if (concern.basis) evidence.push(`basis: ${concern.basis}`);
      for (const marker of m.markers) evidence.push(`marker: ${marker}`);
      for (const ev of m.evidence.slice(0, 5)) {
        evidence.push(
          ev.line != null
            ? `${ev.signal} at ${ev.file}:${ev.line}`
            : `${ev.signal} at ${ev.file}`,
        );
      }
      return {
        kind: "component" as const,
        ref: m.component_id,
        componentId: m.component_id,
        label: comp?.name ?? m.component_id,
        file: firstEv?.file,
        lineStart: firstEv?.line ?? null,
        lineEnd: null,
        evidence,
      };
    });
    // concern.id already carries the "concern:<kind>" namespace, so it IS the origin.
    return get().createSet(concern.title || concern.id, concern.id, members);
  },

  createSetFromSearchResults: (query, results) => {
    const members: SetMember[] = results.map((r) => {
      const kind: SetMember["kind"] =
        r.type === "component" ? "component" : r.type === "symbol" ? "symbol" : "file";
      const componentId =
        r.type === "component" ? r.id : r.componentId ?? r.id;
      const evidence: string[] = [`matched search "${query}"`];
      return {
        kind,
        ref: r.id,
        componentId,
        label: r.name,
        file: r.type === "component" ? undefined : r.path,
        lineStart: null,
        lineEnd: null,
        evidence,
      };
    });
    return get().createSet(`Search: ${query}`, `search:${query}`, members);
  },

  addComponentToSet: (setId, componentId) => {
    const arch = get().architecture;
    if (!arch) return null;
    const comp = findComponent(arch.components, componentId);
    if (!comp) return null;
    const member: SetMember = {
      kind: "component",
      ref: comp.id,
      componentId: comp.id,
      label: comp.name,
      file: comp.path,
      lineStart: null,
      lineEnd: null,
      evidence: [`added manually from ${comp.path}`],
    };

    // Target an explicit set, or the most recent manual set, or create one.
    let targetId = setId;
    if (!targetId) {
      const manualSets = get().selectionSets.filter((s) => s.origin === "manual");
      targetId = manualSets.length > 0 ? manualSets[manualSets.length - 1].id : null;
    }
    if (!targetId) {
      return get().createSet("Manual selection", "manual", [member]);
    }

    set((s) => ({
      selectionSets: s.selectionSets.map((ss) => {
        if (ss.id !== targetId) return ss;
        if (ss.members.some((m) => m.ref === member.ref)) return ss; // already present
        return { ...ss, members: [...ss.members, member] };
      }),
    }));
    persistCurrentSets(get);
    return targetId;
  },

  renameSet: (setId, name) => {
    set((s) => ({
      selectionSets: s.selectionSets.map((ss) =>
        ss.id === setId ? { ...ss, name: name.trim() || ss.name } : ss,
      ),
    }));
    persistCurrentSets(get);
  },

  deleteSet: (setId) => {
    set((s) => ({
      selectionSets: s.selectionSets.filter((ss) => ss.id !== setId),
      setAnnotations: s.setAnnotations.filter((a) => a.setId !== setId),
    }));
    persistCurrentSets(get);
  },

  setSetIntent: (setId, intent) => {
    set((s) => {
      const existing = s.setAnnotations.find((a) => a.setId === setId);
      if (existing) {
        return {
          setAnnotations: s.setAnnotations.map((a) =>
            a.setId === setId ? { ...a, intent } : a,
          ),
        };
      }
      return {
        setAnnotations: [...s.setAnnotations, { setId, intent, memberNotes: [] }],
      };
    });
    persistCurrentSets(get);
  },

  setSetMemberNote: (setId, memberRef, note) => {
    set((s) => {
      const existing = s.setAnnotations.find((a) => a.setId === setId);
      const upsertNote = (a: SetAnnotation): SetAnnotation => {
        const others = a.memberNotes.filter((n) => n.memberRef !== memberRef);
        const next = note.trim().length > 0 ? [...others, { memberRef, note }] : others;
        return { ...a, memberNotes: next };
      };
      if (existing) {
        return {
          setAnnotations: s.setAnnotations.map((a) =>
            a.setId === setId ? upsertNote(a) : a,
          ),
        };
      }
      return {
        setAnnotations: [
          ...s.setAnnotations,
          upsertNote({ setId, intent: "", memberNotes: [] }),
        ],
      };
    });
    persistCurrentSets(get);
  },

  getSelectionSets: () => get().selectionSets,
  getSetById: (setId) => get().selectionSets.find((s) => s.id === setId) ?? null,
  getSetAnnotation: (setId) =>
    get().setAnnotations.find((a) => a.setId === setId) ?? null,

  navigateToSetMember: (member) => {
    // Navigate on stable identity (I12): always via the owning component, which
    // for a component member is the member itself.
    get().navigateToComponent(member.componentId);
  },

  loadComponentDetail: async (componentId) => {
    // Already cached
    const cached = get().componentDetailCache[componentId];
    if (cached) return cached;

    // In monolithic mode (files/symbols loaded in architecture), no need to fetch
    const arch = get().architecture;
    if (arch && arch.files.length > 0) return null;

    // Negative cache: a prior fetch for this component already failed. Do not
    // refire on every panel re-open; the panel shows a retry affordance that
    // clears this error and calls again (F-VW-7).
    if (get().componentDetailErrors[componentId]) return null;

    // Already loading (per-component key): let the in-flight request settle
    // instead of starting a duplicate that races its sibling (F-VW-7).
    if (get().componentDetailLoading[componentId]) return null;

    // Per-component loading key so a sibling component's load does not clobber
    // this one's loading state (F-VW-7).
    set((state) => ({
      componentDetailLoading: { ...state.componentDetailLoading, [componentId]: true },
    }));
    const safeId = safeComponentId(componentId);
    // Capture the architecture this request belongs to. If a live refresh
    // swaps the architecture (and invalidates the cache) while the fetch is in
    // flight, the stale response must not repopulate the fresh cache.
    const requestArch = arch;

    // Clear only this component's loading key, leaving other in-flight loads
    // untouched. No-op if the architecture was swapped mid-flight (setArchitecture
    // already reset the loading map).
    const clearLoading = () => {
      if (get().architecture !== requestArch) return;
      set((state) => {
        const next = { ...state.componentDetailLoading };
        delete next[componentId];
        return { componentDetailLoading: next };
      });
    };

    // Record a surfaced, negatively-cached error for this component (F-VW-7),
    // unless the architecture was swapped mid-flight (then it is not our error).
    const recordError = (message: string) => {
      if (get().architecture !== requestArch) return;
      set((state) => ({
        componentDetailErrors: { ...state.componentDetailErrors, [componentId]: message },
      }));
    };

    try {
      const res = await fetch(dataUrl(`data/detail-${safeId}.json`));
      if (get().architecture !== requestArch) {
        // Architecture changed mid-flight: discard, the next open refetches.
        return null;
      }
      if (res.ok) {
        const detail = await res.json();
        if (get().architecture !== requestArch) {
          return null;
        }
        set((state) => ({
          componentDetailCache: { ...state.componentDetailCache, [componentId]: detail },
        }));
        // Add to search index, keyed by component so a live refresh preserves
        // these entries and a re-load replaces them (F-VW-3).
        addToSearchIndex(detail.symbols || [], detail.files || [], componentId);
        return detail;
      }
      recordError(`HTTP ${res.status}`);
      return null;
    } catch (err) {
      recordError(err instanceof Error ? err.message : "Fetch failed");
      return null;
    } finally {
      clearLoading();
    }
  },

  retryComponentDetail: (componentId) => {
    // Clear the negative cache and loading marker so the next load refetches.
    set((state) => {
      const errors = { ...state.componentDetailErrors };
      delete errors[componentId];
      const loading = { ...state.componentDetailLoading };
      delete loading[componentId];
      return { componentDetailErrors: errors, componentDetailLoading: loading };
    });
    return get().loadComponentDetail(componentId);
  },

  prefetchDetails: (componentId) => {
    const { architecture, breadcrumbs } = get();
    // Monolith mode: detail is already inline, nothing to fetch.
    if (!architecture || architecture.files.length > 0) return;
    const targets = collectPrefetchTargets(architecture, componentId, breadcrumbs);
    for (const id of targets) {
      // loadComponentDetail is guarded (cache + in-flight + negative cache), so
      // scheduling one idle call per target is safe and self-deduplicating.
      scheduleIdle(() => { void get().loadComponentDetail(id); });
    }
  },

  // Expanding an aggregate opens its ranked member LIST in the detail panel
  // rather than promoting 31 more nodes onto the canvas (owner decision
  // 2026-08-17, option B). The canvas exploding to 45 nodes at minimum zoom,
  // where each rendered 7px tall, is impossible by construction now, and a
  // list can carry purpose and criticality that a speck cannot.
  toggleAggregate: (id) => {
    const agg = get().getAggregateNodes().find((a) => a.id === id);
    if (!agg) return;
    const open = get().detailItem;
    if (open?.type === "aggregate" && (open.data as AggregateNode).id === id) {
      set({ detailItem: null, activePanel: null });
      return;
    }
    set({ detailItem: { type: "aggregate", data: agg }, activePanel: "detail" });
  },

  getAggregateNodes: () => {
    const { architecture, drillLevel } = get();
    if (!architecture) return [];
    return drillView(architecture, drillLevel, get().nodeBudget).aggregates;
  },

  loadCoverageRows: async () => {
    // Already loaded for this architecture.
    const existing = get().coverageRows;
    if (existing) return existing;

    const arch = get().architecture;
    if (!arch) return null;

    // Monolith mode: the full rows ride inline in architecture.coverage.rows, so
    // no fetch is needed. The inventory (P6-10) rides inline the same way.
    const inline = arch.coverage?.rows;
    if (inline && inline.length > 0) {
      set({ coverageRows: inline, coverageInventory: arch.coverage?.inventory ?? null });
      return inline;
    }

    // Nothing to load if the dataset carries no coverage summary at all.
    if (!arch.coverage) return null;

    // Do not refire while a fetch is already in flight or after one failed; the
    // panel surfaces the error and the next architecture load resets it.
    if (get().coverageRowsLoading) return null;
    if (get().coverageRowsError) return null;

    set({ coverageRowsLoading: true });
    // Capture the architecture this request belongs to so a live refresh that
    // swaps the architecture mid-flight does not repopulate the fresh state.
    const requestArch = arch;
    try {
      const res = await fetch(dataUrl("coverage.json"));
      if (get().architecture !== requestArch) return null;
      if (res.ok) {
        const data = await res.json();
        if (get().architecture !== requestArch) return null;
        const rows: CoverageRow[] = Array.isArray(data?.rows) ? data.rows : [];
        // The inventory (P6-10) rides in the same coverage.json. Absent on old
        // datasets, in which case the panel degrades to no inventory affordance.
        const inventory: Inventory | null = data?.inventory ?? null;
        set({ coverageRows: rows, coverageInventory: inventory, coverageRowsLoading: false });
        return rows;
      }
      set({ coverageRowsError: `HTTP ${res.status}`, coverageRowsLoading: false });
      return null;
    } catch (err) {
      if (get().architecture !== requestArch) return null;
      set({
        coverageRowsError: err instanceof Error ? err.message : "Fetch failed",
        coverageRowsLoading: false,
      });
      return null;
    }
  },

  loadActivity: async () => {
    // Already loaded for this architecture.
    const existing = get().activityData;
    if (existing) return existing;

    const arch = get().architecture;
    if (!arch || arch.activity == null) return null;

    // Monolith mode: the full ActivityData rides inline under architecture.activity
    // (distinguished from the manifest summary by its `components` array). No fetch.
    const inline = arch.activity;
    if ("components" in inline && Array.isArray(inline.components)) {
      const data = inline as ActivityData;
      set({ activityData: data });
      return data;
    }

    // Do not refire while a fetch is in flight or after one failed; the next
    // architecture load resets these.
    if (get().activityLoading) return null;
    if (get().activityError) return null;

    set({ activityLoading: true });
    // Capture the architecture this request belongs to so a live refresh that
    // swaps the architecture mid-flight does not repopulate the fresh state.
    const requestArch = arch;
    try {
      const res = await fetch(dataUrl("activity.json"));
      if (get().architecture !== requestArch) return null;
      // Guard against a Vite SPA HTML fallback returning 200 with text/html.
      const isJson = res.ok && (res.headers.get("content-type")?.includes("json") ?? false);
      if (isJson) {
        const data = (await res.json()) as ActivityData;
        if (get().architecture !== requestArch) return null;
        set({ activityData: data, activityLoading: false });
        return data;
      }
      set({ activityError: `HTTP ${res.status}`, activityLoading: false });
      return null;
    } catch (err) {
      if (get().architecture !== requestArch) return null;
      set({
        activityError: err instanceof Error ? err.message : "Fetch failed",
        activityLoading: false,
      });
      return null;
    }
  },

  // The ranked hotspot list is the Activity lens landing view (I11). The
  // projection already sorts components by descending hotspot score, so this is
  // "look here first" with no client-side reshuffle.
  getHotspots: () => get().activityData?.components ?? [],

  getActivityComponent: (componentId) =>
    get().activityData?.components.find((c) => c.id === componentId) ?? null,

  getCouplingForComponent: (componentId) => {
    const data = get().activityData;
    if (!data) return [];
    const arch = get().architecture;
    const nameOf = (cid: string) =>
      (arch ? findComponent(arch.components, cid)?.name : null) ?? cid;
    // component_coupling is cross-component and pre-sorted by co-change count;
    // filtering to the anchor id preserves that order, so this is always the
    // "what changes with this" list, never a standalone graph.
    return data.component_coupling
      .filter((p) => p.a === componentId || p.b === componentId)
      .map((p) => {
        const partnerId = p.a === componentId ? p.b : p.a;
        return { partnerId, partnerName: nameOf(partnerId), count: p.cochange_count };
      });
  },

  getComponentActivityFiles: (componentId) => {
    const data = get().activityData;
    if (!data) return [];
    return Object.entries(data.files)
      .filter(([, f]) => f.component_ids.includes(componentId))
      .map(([path, f]) => ({ ...f, path }))
      .sort((a, b) => b.hotspot_score - a.hotspot_score || a.path.localeCompare(b.path));
  },

  // Findings surface (P6-8). Opening starts from a clean kind filter unless one is
  // explicitly passed, so a stale filter from a prior session never hides the
  // findings the caller meant to show (e.g. the contextual badge opening filtered
  // to an element whose findings are all of a kind the stale filter excludes). The
  // element filter (from the contextual detail badge) implies the findings tab.
  openFindingsSurface: (opts) =>
    set((s) => ({
      findingsSurface: {
        open: true,
        tab: opts?.tab ?? (opts?.elementFilter ? "findings" : s.findingsSurface.tab),
        kindFilter: opts?.kindFilter ?? null,
        elementFilter: opts?.elementFilter ?? null,
      },
    })),
  closeFindingsSurface: () =>
    set((s) => ({ findingsSurface: { ...s.findingsSurface, open: false } })),
  setFindingsSurfaceTab: (tab) =>
    set((s) => ({ findingsSurface: { ...s.findingsSurface, tab } })),
  setFindingsKindFilter: (kind) =>
    set((s) => ({ findingsSurface: { ...s.findingsSurface, kindFilter: kind } })),

  // Supply chain overlay (P10-1). Simple open/close; the surface reads the
  // supply_chain section straight off the architecture.
  openSupplyChain: () => set({ supplyChainOpen: true }),
  closeSupplyChain: () => set({ supplyChainOpen: false }),

  // Ranked by rank_score desc, ties by id (I11): "look here first" holds even if
  // the projection emitted them unordered.
  getFindings: () => sortFindings(get().architecture?.findings ?? []),
  getConcerns: () => get().architecture?.concerns ?? [],
  getFindingsForComponent: (componentId) =>
    findingsForComponent(get().architecture?.findings ?? [], componentId),
  getConcernById: (id) =>
    (get().architecture?.concerns ?? []).find((c) => c.id === id) ?? null,

  // The P6-9 seam (section 10). Record the finding's members as an addressable
  // selection set. True set-level annotation and directive export are P6-9; today
  // this stage plus a single-element annotation on the representative component is
  // as far as the review model reaches.
  stageFindingSet: (finding) => {
    const memberComponentIds = [
      ...new Set(
        finding.members
          .map((m) => m.component_id)
          .filter((cid): cid is string => typeof cid === "string" && cid.length > 0),
      ),
    ];
    set({
      stagedFindingSet: {
        findingId: finding.id,
        label: finding.summary,
        memberComponentIds,
        memberCount: finding.members.length,
      },
    });
  },
  clearStagedSet: () => set({ stagedFindingSet: null }),

  annotateFindingSet: (finding) => {
    // Record the staged membership (the historical seam) and build a real
    // selection set from the finding's members via the P6-9 engine.
    get().stageFindingSet(finding);
    const setId = findOrCreateFindingSet(get, finding.id);
    if (!setId) return null;
    // Close the overlay and open the set annotation flow: review mode with the
    // review panel showing the SelectionSetsSection, where the reviewer states
    // the shared intent and per-member notes for the whole set.
    set((s) => ({ findingsSurface: { ...s.findingsSurface, open: false } }));
    if (!get().reviewMode) get().toggleReviewMode();
    get().setActivePanel("review");
    return setId;
  },

  annotateConcernSet: (concern) => {
    const setId = findOrCreateConcernSet(get, concern.id);
    if (!setId) return null;
    set((s) => ({ findingsSurface: { ...s.findingsSurface, open: false } }));
    if (!get().reviewMode) get().toggleReviewMode();
    get().setActivePanel("review");
    return setId;
  },

  exportDirectiveForFinding: (findingId) => {
    const arch = get().architecture;
    if (!arch) return null;
    const setId = findOrCreateFindingSet(get, findingId);
    if (!setId) return null;
    const setObj = get().getSetById(setId);
    if (!setObj) return null;
    return generateDirective(setObj, get().getSetAnnotation(setId), arch);
  },

  exportDirectiveForConcern: (concernId) => {
    const arch = get().architecture;
    if (!arch) return null;
    const setId = findOrCreateConcernSet(get, concernId);
    if (!setId) return null;
    const setObj = get().getSetById(setId);
    if (!setObj) return null;
    return generateDirective(setObj, get().getSetAnnotation(setId), arch);
  },

  // ─── Tours player (P6-7) ───────────────────────────────────────────────────

  openTours: () => set({ toursOpen: true }),
  closeTours: () => set({ toursOpen: false }),

  getTours: () => get().architecture?.tours ?? [],
  getTourById: (id) => (get().architecture?.tours ?? []).find((t) => t.id === id) ?? null,

  startTour: (tourId) => {
    const tour = get().getTourById(tourId);
    if (!tour || tour.steps.length === 0) return;
    // Close the list and land on the first step, selecting its target (I12).
    set({ activeTourId: tourId, tourStep: 0, toursOpen: false });
    get().navigateToTourTarget(tour.steps[0]);
  },

  tourStepNext: () => {
    const { activeTourId, tourStep } = get();
    if (!activeTourId) return;
    const tour = get().getTourById(activeTourId);
    if (!tour) return;
    const next = Math.min(tourStep + 1, tour.steps.length - 1);
    if (next === tourStep) return;
    set({ tourStep: next });
    get().navigateToTourTarget(tour.steps[next]);
  },

  tourStepPrev: () => {
    const { activeTourId, tourStep } = get();
    if (!activeTourId) return;
    const tour = get().getTourById(activeTourId);
    if (!tour) return;
    const prev = Math.max(tourStep - 1, 0);
    if (prev === tourStep) return;
    set({ tourStep: prev });
    get().navigateToTourTarget(tour.steps[prev]);
  },

  tourGoToStep: (step) => {
    const { activeTourId } = get();
    if (!activeTourId) return;
    const tour = get().getTourById(activeTourId);
    if (!tour || tour.steps.length === 0) return;
    const clamped = Math.max(0, Math.min(step, tour.steps.length - 1));
    set({ tourStep: clamped });
    get().navigateToTourTarget(tour.steps[clamped]);
  },

  exitTour: () => set({ activeTourId: null, tourStep: 0 }),

  navigateToTourTarget: (step) => {
    // Stable identity (I12): a component id drills to and selects the component;
    // otherwise the step's evidence file (or a file-path target) opens via the
    // file deep link, which resolves the symbol at the line where present.
    const comp = get().getComponentById(step.target);
    if (comp) {
      get().navigateToComponent(step.target);
      return;
    }
    if (step.evidence?.file) {
      void get().openFileDeepLink(step.evidence.file, step.evidence.line ?? null);
      return;
    }
    // A bare file-path target (no component match, no evidence): treat the target
    // as a file path so the walk still lands somewhere concrete.
    void get().openFileDeepLink(step.target, null);
  },

  getComponentById: (id) => {
    const arch = get().architecture;
    if (!arch) return null;
    return findComponent(arch.components, id);
  },

  getComponentByFile: (filePath) => {
    const arch = get().architecture;
    if (!arch) return null;
    return findComponentByFile(arch.components, filePath);
  },

  getVisibleComponents: () => {
    const { architecture, drillLevel } = get();
    if (!architecture) return [];

    // Top level and drill levels share one computation (drillView), which
    // returns the ranked shown set plus the aggregates standing in for what did
    // not fit the viewport's node budget. Aggregate members are NOT promoted
    // onto the canvas; they are browsed as a ranked list in the panel, so the
    // canvas can never degrade into unreadable specks. Nothing is ever hidden
    // without a visible, counted trace.
    const { shown } = drillView(architecture, drillLevel, get().nodeBudget);
    return shown;
  },

  getComponentRelationships: () => {
    const { architecture } = get();
    if (!architecture) return [];

    const visible = get().getVisibleComponents();
    const visibleIds = new Set(visible.map((c) => c.id));

    // Roll edges up to their nearest visible ancestors (S1): an edge between
    // descendants of two visible nodes draws between those nodes instead of
    // silently dropping, so the client-to-server wiring is present at the
    // level every visitor starts on. Exact-id edges pass through unchanged.
    return rollUpRelationships(
      architecture.relationships,
      architecture.components,
      visibleIds
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
