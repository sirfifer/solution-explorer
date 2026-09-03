import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { useArchStore } from "./store";
import { ArchitectureGraph } from "./components/ArchitectureGraph";
import { TreeNavigator } from "./components/TreeNavigator";
import { DetailPanel } from "./components/DetailPanel";
import { SearchOverlay } from "./components/SearchOverlay";
import { HelpSystem } from "./components/HelpSystem";
import { ReviewModeButton } from "./components/ReviewModeButton";
import { ThemeSwitcher } from "./components/ThemeSwitcher";
import { applyThemeToDocument } from "./utils/themes";
import { AnnotationInput } from "./components/AnnotationInput";
import { ReviewSummary } from "./components/ReviewSummary";
import { AdminDashboard } from "./components/AdminDashboard";
import { StatusDashboard } from "./components/StatusDashboard";
import { CoverageBadge } from "./components/CoverageBadge";
import { GapsBanner } from "./components/GapsBanner";
import { PublicationBanner } from "./components/PublicationBanner";
import { PublicationFooter } from "./components/PublicationFooter";
import { FindingsEntry } from "./components/FindingsEntry";
import { FindingsSurface } from "./components/FindingsSurface";
import { SupplyChainEntry } from "./components/SupplyChainEntry";
import { SupplyChainSurface } from "./components/SupplyChainSurface";
import { ToursEntry } from "./components/ToursEntry";
import { TourPlayer } from "./components/TourPlayer";
import { LensSwitcher } from "./components/LensSwitcher";
import { FlowPanel } from "./components/FlowPanel";
import { InventoryLensPanel } from "./components/InventoryLensPanel";
import { ActivityPanel } from "./components/ActivityPanel";
import { CapabilityPanel } from "./components/CapabilityPanel";
import { DataPanel } from "./components/DataPanel";
import { RulesPanel } from "./components/RulesPanel";
import { DesignPanel } from "./components/DesignPanel";
import { SupportPanel } from "./components/SupportPanel";
import { SecurityPanel } from "./components/SecurityPanel";
import { SystemOverview } from "./components/SystemOverview";
import { ExperienceSwitcher } from "./components/ExperienceSwitcher";
import { WorkbenchTrustStrip } from "./components/WorkbenchTrustStrip";
import { TrustDrawer } from "./components/TrustLedger";
import { ViewerPreferences } from "./components/ViewerPreferences";
import { useLiveMonitor } from "./hooks/useLiveMonitor";
import { useUrlSync } from "./hooks/useUrlSync";
import { useBottomSheet } from "./hooks/useBottomSheet";
import type { SnapPoint } from "./hooks/useBottomSheet";
import { initializeSearch } from "./utils/search";
import { collectCriticalComponents, collectExternalDependencies } from "./lenses";
import { formatNumber, formatRelativeTime, getTypeColors } from "./utils/layout";
import { dataUrl, getDataBase } from "./utils/dataSource";
import { parsePublication, publicationDisplayName } from "./utils/publication";
import { attachHumanViews } from "./utils/orientation";
import { SolutionIndex } from "./components/SolutionIndex";
import { Tooltip } from "./components/Tooltip";
import { TOOLTIP_COPY } from "./utils/tooltipCopy";
import { OrientationInvite } from "./components/OrientationInvite";
import { OrientationWalk } from "./components/OrientationWalk";
import { applicableStops } from "./orientation/model";
import { WALK_STOPS } from "./orientation/stops";
import type {
  Architecture,
  Component,
  OrientationProjection,
  SecurityProjection,
  SolutionManifest,
  SupportProjection,
} from "./types";
import { SOLUTION_MANIFEST_KIND } from "./types";

const MOBILE_NAV_HEIGHT_PX = 72;

function mobileSheetSize(sheetHeight: number): string {
  return `calc(${sheetHeight}vh - ${(MOBILE_NAV_HEIGHT_PX * sheetHeight) / 100}px)`;
}

// How much of the canvas the mounted mobile sheet reserves below itself.
//
// The detail sheet's peek snap reserves nothing, so the peek strip overlays the
// bottom of the canvas instead of shrinking it. A tap on a node selects it,
// which mounts this sheet, and reserving 15vh at that moment relaid the canvas
// and slid the just-tapped node about 22 px, past the 5 px slop the double-tap
// drill detector allows, so drilling by double-tap failed roughly one phone run
// in two (GUI crawl 2026-09-01, journey.drill_hop). That is the same rule as
// the pan effect's: a node the reader just touched must not move under their
// finger (comprehension-study S5). The canvas height is therefore identical
// before and after the first tap, and the reclaimed space from the empty-sheet
// fix is untouched, because nothing selected still mounts no sheet at all.
//
// Half and full still reserve: by then the reader has asked for the sheet, the
// strip would cover most of the canvas, and a guided selection landing under it
// is brought clear by the pan effect, which already counts both mobile sheets
// as obstructions.
export function mobileGraphReserve(
  sheet: { kind: "detail" | "lens"; snap: SnapPoint; sheetHeight: number } | null,
): string {
  if (!sheet) return "0px";
  if (sheet.kind === "detail" && sheet.snap === "peek") return "0px";
  return mobileSheetSize(sheet.sheetHeight);
}

// Session storage keys for UI state persistence
const STORAGE_KEYS = {
  leftCollapsed: "arch-left-collapsed",
  rightCollapsed: "arch-right-collapsed",
  leftWidth: "arch-left-width",
  rightWidth: "arch-right-width",
  darkMode: "arch-dark-mode",
} as const;

// Helper to get value from storage with fallback
function getStoredValue<T>(key: string, fallback: T, storage: Storage = sessionStorage): T {
  try {
    const stored = storage.getItem(key);
    if (stored !== null) {
      return JSON.parse(stored) as T;
    }
  } catch {
    // Ignore parse errors
  }
  return fallback;
}

// Helper to save value to storage
function setStoredValue<T>(key: string, value: T, storage: Storage = sessionStorage): void {
  try {
    storage.setItem(key, JSON.stringify(value));
  } catch {
    // Ignore storage errors
  }
}

function MobileBottomSheet({ darkMode, activePanel, bottomSheet }: {
  darkMode: boolean;
  activePanel: string;
  bottomSheet: ReturnType<typeof useBottomSheet>;
}) {
  const { detailItem } = useArchStore();
  const { snap, setSnap, sheetHeight, isDragging, dragOffset, handlers } = bottomSheet;

  // Compute actual height during drag
  const windowH = typeof window !== "undefined"
    ? Math.max(320, window.innerHeight - MOBILE_NAV_HEIGHT_PX)
    : 728;
  const baseHeightPx = (sheetHeight / 100) * windowH;
  const currentHeightPx = isDragging
    ? Math.max(0, Math.min(windowH * 0.95, baseHeightPx - dragOffset))
    : baseHeightPx;

  // Get component info for peek view
  const component = detailItem?.type === "component" ? (detailItem.data as Component) : null;
  const colors = component ? getTypeColors(component.type, darkMode) : null;

  return (
    <div
      data-se="mobile-detail-sheet"
      className={`
        lg:hidden fixed left-0 right-0 z-30
        flex flex-col rounded-t-2xl shadow-2xl
        ${darkMode ? "bg-zinc-900 border-t border-zinc-800" : "bg-white border-t border-zinc-200"}
      `}
      style={{
        bottom: `calc(${MOBILE_NAV_HEIGHT_PX}px + env(safe-area-inset-bottom))`,
        height: isDragging ? currentHeightPx : mobileSheetSize(sheetHeight),
        transition: isDragging ? "none" : "height 0.3s cubic-bezier(0.25, 1, 0.5, 1)",
        willChange: isDragging ? "height" : "auto",
      }}
    >
      {/* Drag handle area (full width touch target) */}
      <div
        className="flex flex-col items-center pt-2 pb-1 cursor-grab active:cursor-grabbing touch-none shrink-0"
        {...handlers}
      >
        <div className={`w-10 h-1 rounded-full ${darkMode ? "bg-zinc-700" : "bg-zinc-300"}`} />
      </div>

      {/* Peek header: always visible, shows component name */}
      {component && snap === "peek" && !isDragging && (
        <div
          data-testid="detail-sheet-peek"
          className="flex items-center gap-2 px-4 py-2 shrink-0 cursor-pointer"
          onClick={() => setSnap("half")}
        >
          {colors && (
            <span
              className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
              style={{ backgroundColor: colors.bg }}
            />
          )}
          <span className={`text-sm font-medium truncate ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
            {component.name}
          </span>
          <span className={`text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            {component.type}
          </span>
          <span className={`ml-auto text-xs ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            Swipe up for details
          </span>
        </div>
      )}

      {/* Full detail content: visible in half/full mode, or always during drag */}
      {(snap !== "peek" || isDragging) && (
        <div className="flex-1 overflow-y-auto min-h-0">
          {activePanel === "review" ? <ReviewSummary /> : <DetailPanel />}
        </div>
      )}
    </div>
  );
}

// Whether the mobile detail/review sheet should mount, exported for the same
// testability reason as shouldShowMobileLensSheet below.
//
// The sheet used to mount on activePanel alone. In review mode, and on any path
// that leaves the panel open with nothing selected, that put a peek-height
// sheet on screen with no content in it: the peek header only renders for a
// selected component, so the reader got an empty 15vh slab and the canvas lost
// the same 15vh to mobileGraphBottomReserve (GUI crawl 2026-09-01, mobile
// chrome). Nothing selected now means no sheet at all and the canvas keeps the
// space. A selected component, and the review summary, are unchanged.
export function shouldShowMobileDetailSheet({ isDesktopViewport, activePanel, hasDetail }: {
  isDesktopViewport: boolean;
  activePanel: string | null;
  hasDetail: boolean;
}): boolean {
  if (isDesktopViewport) return false;
  if (activePanel === "review") return true;
  return activePanel === "detail" && hasDetail;
}

// Whether the mobile lens sheet should mount (O10), exported so its exact
// production logic is directly unit-testable without mounting all of <App />
// (which unconditionally renders the ReactFlow graph, untested in jsdom here).
// Mutually exclusive with the detail/review sheet: navigating from a lens row
// always opens the detail sheet (store.navigateToComponent sets activePanel
// to "detail"), and the two sheets sharing the bottom of a phone screen has
// nowhere to go.
export function shouldShowMobileLensSheet({ isPanelViewport, lens, activePanel }: {
  isPanelViewport: boolean;
  lens: string;
  activePanel: string | null;
}): boolean {
  return !isPanelViewport && lens !== "structure" && activePanel !== "detail" && activePanel !== "review";
}

// Support is a ranked operational report, not a terse control strip. Opening
// it into the generic half-height snap left only ~199 px for the real content
// on a phone and put external reliance more than a screen below the fold.
// Give that lens the full mobile canvas immediately; the drag handle still
// allows the user to collapse or dismiss it.
export function initialMobileLensSnap(lens: string): SnapPoint {
  return lens === "support" ? "full" : "half";
}

// The mobile counterpart to the desktop-docked lens panel (O10). Below the md
// breakpoint the docked panel is display:none (its own `hidden md:flex`
// wrapper), so without this a lens picked on a phone rendered nothing with no
// explanation. Reuses the same bottom-sheet chrome as MobileBottomSheet above
// (drag handle, rounded top, snap-driven height) rather than inventing a
// second mobile pattern, per the fix's own preference for reuse. Exported for
// the same testability reason as shouldShowMobileLensSheet above.
export function MobileLensSheet({ lens, darkMode, bottomSheet }: {
  lens: string;
  darkMode: boolean;
  bottomSheet: ReturnType<typeof useBottomSheet>;
}) {
  const { isDragging, dragOffset, sheetHeight, handlers } = bottomSheet;

  const windowH = typeof window !== "undefined"
    ? Math.max(320, window.innerHeight - MOBILE_NAV_HEIGHT_PX)
    : 728;
  const baseHeightPx = (sheetHeight / 100) * windowH;
  const currentHeightPx = isDragging
    ? Math.max(0, Math.min(windowH * 0.95, baseHeightPx - dragOffset))
    : baseHeightPx;

  return (
    <div
      data-se="mobile-lens-sheet"
      className={`
        md:hidden fixed left-0 right-0 z-30
        flex flex-col rounded-t-2xl shadow-2xl
        ${darkMode ? "bg-zinc-900 border-t border-zinc-800" : "bg-white border-t border-zinc-200"}
      `}
      style={{
        bottom: `calc(${MOBILE_NAV_HEIGHT_PX}px + env(safe-area-inset-bottom))`,
        height: isDragging ? currentHeightPx : mobileSheetSize(sheetHeight),
        transition: isDragging ? "none" : "height 0.3s cubic-bezier(0.25, 1, 0.5, 1)",
        willChange: isDragging ? "height" : "auto",
      }}
    >
      {/* Drag handle area (full width touch target) */}
      <div
        className="flex flex-col items-center pt-2 pb-1 cursor-grab active:cursor-grabbing touch-none shrink-0"
        {...handlers}
      >
        <div className={`w-10 h-1 rounded-full ${darkMode ? "bg-zinc-700" : "bg-zinc-300"}`} />
      </div>

      <div className="flex-1 overflow-hidden min-h-0">
        {lens === "flow" && <FlowPanel mobile />}
        {lens === "inventory" && <InventoryLensPanel mobile />}
        {lens === "activity" && <ActivityPanel mobile />}
        {lens === "capability" && <CapabilityPanel mobile />}
        {lens === "data" && <DataPanel mobile />}
        {lens === "rules" && <RulesPanel mobile />}
        {lens === "design" && <DesignPanel mobile />}
        {lens === "support" && <SupportPanel mobile />}
        {lens === "security" && <SecurityPanel mobile />}
      </div>
    </div>
  );
}

/** The open-overlay flags the beacon publishes, gathered in one place. */
interface OverlayFlags {
  searchOpen: boolean;
  findingsOpen: boolean;
  supplyChainOpen: boolean;
  inventoryOpen: boolean;
  toursOpen: boolean;
  helpOpen: boolean;
  welcomeOpen: boolean;
  orientationOpen: boolean;
  adminOpen: boolean;
  activePanel: string | null;
  trustOpen: boolean;
  preferencesOpen: boolean;
}

/**
 * Which overlays and dialogs are open right now, by the names the beacon
 * publishes.
 *
 * One derivation, two readers: the beacon prints it, and the global Escape
 * handler asks it whether anything else owns the key. Each overlay registers
 * its own Escape listener while it is open, so a second handler that did not
 * check this list would close the detail panel underneath an open dialog on
 * the same keypress.
 */
function openOverlays(f: OverlayFlags): string[] {
  return [
    f.searchOpen && "search",
    f.findingsOpen && "findings",
    f.supplyChainOpen && "supply-chain",
    f.inventoryOpen && "inventory",
    f.toursOpen && "tours",
    (f.helpOpen || f.welcomeOpen) && "help",
    f.orientationOpen && "orientation",
    f.adminOpen && "admin",
    f.activePanel === "review" && "review",
    f.trustOpen && "trust",
    f.preferencesOpen && "preferences",
  ].filter((x): x is string => typeof x === "string");
}

// The navigation-state beacon.
//
// One always-mounted, visually hidden element that publishes the store's
// navigation state as data-* attributes. It renders nothing and reads nothing
// but the store, so it cannot change behaviour; it exists so a test (and anyone
// with devtools open) can read the app's own account of where it is, rather
// than inferring it from which panels happen to be on screen.
//
// Asserting on it alone would be worthless: a beacon that says "reset" while a
// tour panel is still up is exactly the bug worth catching. So the crawl checks
// the beacon AND the visible expression of the same state, and a disagreement
// between them is the finding.
//
// aria-hidden because it is not content: a screen reader has the real UI.
export function NavStateBeacon() {
  const drillLevel = useArchStore((s) => s.drillLevel);
  const selectedComponentId = useArchStore((s) => s.selectedComponentId);
  const lens = useArchStore((s) => s.lens);
  const flowEntryId = useArchStore((s) => s.flowEntryId);
  const flowStep = useArchStore((s) => s.flowStep);
  const selectedCapabilityId = useArchStore((s) => s.selectedCapabilityId);
  const selectedEntityId = useArchStore((s) => s.selectedEntityId);
  const selectedRuleId = useArchStore((s) => s.selectedRuleId);
  const selectedDesignFindingId = useArchStore((s) => s.selectedDesignFindingId);
  const activeTourId = useArchStore((s) => s.activeTourId);
  const tourStep = useArchStore((s) => s.tourStep);
  const activePanel = useArchStore((s) => s.activePanel);
  const detailItem = useArchStore((s) => s.detailItem);
  const blastRadiusMode = useArchStore((s) => s.blastRadiusMode);
  const searchOpen = useArchStore((s) => s.searchOpen);
  const findingsOpen = useArchStore((s) => s.findingsSurface.open);
  const supplyChainOpen = useArchStore((s) => s.supplyChainOpen);
  const inventoryOpen = useArchStore((s) => s.inventoryOpen);
  const toursOpen = useArchStore((s) => s.toursOpen);
  const helpOpen = useArchStore((s) => s.helpOpen);
  const welcomeOpen = useArchStore((s) => s.welcomeOpen);
  const orientationOpen = useArchStore((s) => s.orientationOpen);
  const orientationStep = useArchStore((s) => s.orientationStep);
  const orientationInvite = useArchStore((s) => s.orientationInvite);
  const orientationSkipped = useArchStore((s) => s.orientationSkipped);
  const adminOpen = useArchStore((s) => s.adminOpen);
  // The front door (main, 2026-09-01). The mode is the single most important
  // thing a test can ask, because every other field means something different
  // depending on which aperture published it: a bare drill in Overview is not
  // the same claim as a bare drill in the workbench.
  const experienceMode = useArchStore((s) => s.experienceMode);
  const semanticLevel = useArchStore((s) => s.semanticLevel);
  const overviewDirection = useArchStore((s) => s.overviewDirection);
  // Whether this workbench was ARRIVED AT from Overview rather than entered
  // directly. The app already branches on it (HelpSystem suppresses the
  // first-run modal after a handoff, because "replacing it immediately with the
  // first-run five-step modal makes a deliberate handoff feel like a restart"), so
  // a test that could not see it would be blind to the difference between the
  // two ways of standing in the same place.
  const overviewHandoff = useArchStore((s) => s.overviewHandoff);
  const trustOpen = useArchStore((s) => s.trustOpen);
  const preferencesOpen = useArchStore((s) => s.preferencesOpen);

  const overlays = openOverlays({
    searchOpen, findingsOpen, supplyChainOpen, inventoryOpen, toursOpen,
    helpOpen, welcomeOpen, orientationOpen, adminOpen, activePanel, trustOpen, preferencesOpen,
  });
  const orientationStops = applicableStops(
    WALK_STOPS,
    typeof window === "undefined" ? 1024 : window.innerWidth,
  );
  const orientationStop = orientationOpen ? orientationStops[orientationStep] : undefined;

  return (
    <div
      data-testid="nav-state"
      aria-hidden="true"
      className="hidden"
      data-drill={drillLevel ?? ""}
      data-selected={selectedComponentId ?? ""}
      data-lens={lens}
      data-flow={flowEntryId ?? ""}
      // Flow and tour steps are indexes, meaningless without a walk in
      // progress, so they read "" rather than 0 when nothing is being walked.
      data-flow-step={flowEntryId ? String(flowStep) : ""}
      data-capability={selectedCapabilityId ?? ""}
      data-entity={selectedEntityId ?? ""}
      data-rule={selectedRuleId ?? ""}
      data-finding={selectedDesignFindingId ?? ""}
      data-tour={activeTourId ?? ""}
      data-tour-step={activeTourId ? String(tourStep) : ""}
      data-orientation={orientationStop?.id ?? ""}
      data-orientation-step={orientationStop ? String(orientationStep + 1) : ""}
      data-orientation-invite={orientationInvite ? "true" : "false"}
      data-orientation-skipped={orientationSkipped.join(",")}
      data-panel={activePanel ?? ""}
      // "aggregate" is a fourth detail kind the store carries; it is published
      // as itself rather than folded into "" so the beacon never claims nothing
      // is open while an aggregate's member list is.
      data-detail={detailItem?.type ?? ""}
      data-overlays={overlays.join(",")}
      data-blast={blastRadiusMode ? "true" : ""}
      data-mode={experienceMode}
      data-level={semanticLevel}
      data-direction={overviewDirection}
      data-handoff={overviewHandoff ? "true" : ""}
    />
  );
}

export function App() {
  const {
    architecture,
    publication,
    setPublication,
    loading,
    error,
    darkMode,
    theme,
    activePanel,
    reviewMode,
    annotatingComponentId,
    drillLevel,
    lens,
    setArchitecture,
    setLoading,
    setError,
    setSearchOpen,
    setActivePanel,
    enhancedFrames,
    toggleEnhancedFrames,
    navigateToBreadcrumb,
    adminOpen,
    setAdminOpen,
    liveConfig,
    liveMonitorStatus,
    mobileChromeHidden,
    fileDeepLinkNotice,
    clearFileDeepLinkNotice,
    experienceMode,
    setExperienceMode,
    workbenchDensity,
    setPreferencesOpen,
    toggleReviewMode,
    detailItem,
    revealDetail,
    clearRevealDetail,
    collapseDetail,
    clearDetailCollapse,
  } = useArchStore();

  useLiveMonitor();

  const [sidebarOpen, setSidebarOpen] = useState(false);
  // Multi-repo (M1): a composed solution root manifest renders the member index
  // instead of the component graph. null for a normal single-repo dataset.
  const [solution, setSolution] = useState<SolutionManifest | null>(null);
  const [summaryDismissed, setSummaryDismissed] = useState(false);
  // Owner decision 2026-08-17: the summary starts EXPANDED for a first-time
  // visitor (the rollup answers the first questions right up front) and
  // remembers the collapse afterward.
  const [summaryExpanded, setSummaryExpanded] = useState(() =>
    getStoredValue("arch-summary-expanded", true, localStorage),
  );
  const evaluationSummaryAdjusted = useRef(false);
  const setSummaryExpandedPersisted = useCallback((expanded: boolean) => {
    setSummaryExpanded(expanded);
    setStoredValue("arch-summary-expanded", expanded, localStorage);
  }, []);
  // A private evaluation can legitimately carry a large architecture summary,
  // several honesty/status bands, and publication framing at once. Starting
  // that summary expanded can reduce the actual graph to zero height on an
  // ordinary laptop viewport. Collapse it once when the evaluation sidecar
  // arrives; the reader can still expand it immediately, and public/non-eval
  // publications retain the owner-decided expanded default.
  useEffect(() => {
    if (
      publication?.purpose === "evaluation"
      && publication.access.visibility !== "public"
      && !evaluationSummaryAdjusted.current
    ) {
      evaluationSummaryAdjusted.current = true;
      setSummaryExpanded(false);
    }
  }, [publication]);
  // One detail/review panel instance per form factor (S4): matches the lg:
  // breakpoint the panel classes already use.
  const [isDesktopViewport, setIsDesktopViewport] = useState(
    () => typeof window === "undefined" || window.matchMedia("(min-width: 1024px)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const onChange = (e: MediaQueryListEvent) => setIsDesktopViewport(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  // One lens-panel instance per form factor (O10), matching the md: breakpoint
  // the lens panel classes already use (narrower than the lg: detail-panel
  // split above, so it tracks the panels' own hidden md:flex threshold rather
  // than reusing isDesktopViewport, which would change behavior in 768-1023px).
  const [isPanelViewport, setIsPanelViewport] = useState(
    () => typeof window === "undefined" || window.matchMedia("(min-width: 768px)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 768px)");
    const onChange = (e: MediaQueryListEvent) => setIsPanelViewport(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const bannerCritical = useMemo(
    () => (architecture ? collectCriticalComponents(architecture) : []),
    [architecture],
  );
  const bannerDependencies = useMemo(
    () => (architecture ? collectExternalDependencies(architecture) : []),
    [architecture],
  );
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const moreMenuRef = useRef<HTMLDivElement>(null);

  // Tree sidebar swipe-to-close state
  const treeTouchStartX = useRef(0);
  const treeCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [treeDragOffset, setTreeDragOffset] = useState(0);
  const [treeDragging, setTreeDragging] = useState(false);

  const onTreeTouchStart = useCallback((e: React.TouchEvent) => {
    treeTouchStartX.current = e.touches[0].clientX;
    setTreeDragging(true);
  }, []);
  const onTreeTouchMove = useCallback((e: React.TouchEvent) => {
    const delta = e.touches[0].clientX - treeTouchStartX.current;
    // Only allow dragging left (negative delta)
    setTreeDragOffset(Math.min(0, delta));
  }, []);
  const onTreeTouchEnd = useCallback(() => {
    setTreeDragging(false);
    if (treeDragOffset < -80) {
      setSidebarOpen(false);
    }
    setTreeDragOffset(0);
  }, [treeDragOffset]);

  // A mobile tree selection otherwise leaves the drawer and its backdrop over
  // the graph/detail it just opened. Delay closing through the native
  // double-click window so a reader can still drill from the tree with a
  // double-tap; a single tap then reveals its destination without another
  // manual close gesture.
  const closeTreeAfterSelection = useCallback(() => {
    if (treeCloseTimer.current) clearTimeout(treeCloseTimer.current);
    treeCloseTimer.current = setTimeout(() => {
      setSidebarOpen(false);
      treeCloseTimer.current = null;
    }, 250);
  }, []);

  useEffect(() => () => {
    if (treeCloseTimer.current) clearTimeout(treeCloseTimer.current);
  }, []);

  // Mobile bottom sheet
  const bottomSheet = useBottomSheet({
    onDismiss: () => setActivePanel(null),
    initialSnap: "peek" as SnapPoint,
  });

  // Mobile lens-panel bottom sheet (O10). A separate instance from the detail
  // sheet above: the two are mutually exclusive (this one is mounted only when
  // no detail/review panel is open, see the render below) but track their own
  // drag/snap state independently. Starts at "half", not "peek": unlike the
  // detail sheet, there is no compact peek-only header to show while collapsed
  // (same reasoning as the review-mode snap effect further down), so peek would
  // render a mostly blank sheet for a lens the user just deliberately picked.
  const lensBottomSheet = useBottomSheet({
    onDismiss: () => useArchStore.getState().setLens("structure"),
    initialSnap: initialMobileLensSnap(lens),
  });
  const showMobileDetailSheet = shouldShowMobileDetailSheet({
    isDesktopViewport,
    activePanel,
    hasDetail: detailItem !== null,
  });
  const mobileGraphBottomReserve = mobileGraphReserve(
    showMobileDetailSheet
      ? { kind: "detail", snap: bottomSheet.snap, sheetHeight: bottomSheet.sheetHeight }
      : shouldShowMobileLensSheet({ isPanelViewport, lens, activePanel })
        ? { kind: "lens", snap: lensBottomSheet.snap, sheetHeight: lensBottomSheet.sheetHeight }
        : null,
  );

  // Collapsible + resizable sidebar widths (restored from session storage)
  const [leftCollapsed, setLeftCollapsed] = useState(() => getStoredValue(STORAGE_KEYS.leftCollapsed, workbenchDensity === "focused"));
  const [rightCollapsed, setRightCollapsed] = useState(() => getStoredValue(STORAGE_KEYS.rightCollapsed, workbenchDensity === "focused"));
  const [leftWidth, setLeftWidth] = useState(() => getStoredValue(STORAGE_KEYS.leftWidth, 256));
  const [rightWidth, setRightWidth] = useState(() => getStoredValue(STORAGE_KEYS.rightWidth, 320));
  const resizing = useRef<"left" | "right" | null>(null);
  const startX = useRef(0);
  const startWidth = useRef(0);

  // Close more menu on outside click
  useEffect(() => {
    if (!moreMenuOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (moreMenuRef.current && !moreMenuRef.current.contains(e.target as Node)) {
        setMoreMenuOpen(false);
      }
    };
    document.addEventListener("click", handleClick);
    return () => document.removeEventListener("click", handleClick);
  }, [moreMenuOpen]);

  // Persist panel state to session storage
  useEffect(() => { setStoredValue(STORAGE_KEYS.leftCollapsed, leftCollapsed); }, [leftCollapsed]);
  useEffect(() => { setStoredValue(STORAGE_KEYS.rightCollapsed, rightCollapsed); }, [rightCollapsed]);
  useEffect(() => { setStoredValue(STORAGE_KEYS.leftWidth, leftWidth); }, [leftWidth]);
  useEffect(() => { setStoredValue(STORAGE_KEYS.rightWidth, rightWidth); }, [rightWidth]);

  const onMouseDown = useCallback((side: "left" | "right", e: React.MouseEvent) => {
    e.preventDefault();
    resizing.current = side;
    startX.current = e.clientX;
    startWidth.current = side === "left" ? leftWidth : rightWidth;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [leftWidth, rightWidth]);

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!resizing.current) return;
      const delta = e.clientX - startX.current;
      if (resizing.current === "left") {
        setLeftWidth(Math.max(180, Math.min(480, startWidth.current + delta)));
      } else {
        setRightWidth(Math.max(240, Math.min(600, startWidth.current - delta)));
      }
    };
    const onMouseUp = () => {
      if (resizing.current) {
        resizing.current = null;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    };
    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  // Load architecture data (try split manifest.json first, fall back to monolithic)
  useEffect(() => {
    // Guard against Vite SPA fallback: non-existent paths return 200 with text/html
    function isJsonResponse(res: Response): boolean {
      return res.ok && (res.headers.get("content-type")?.includes("json") ?? false);
    }

    async function optionalJson<T>(path: string): Promise<T | null> {
      try {
        const response = await fetch(dataUrl(path));
        return isJsonResponse(response) ? await response.json() as T : null;
      } catch {
        return null;
      }
    }

    // Apply loaded static data only if the live monitor has not already loaded
    // an architecture (from its cache or an authoritative poll). The static file
    // is the deployed baseline; if live data arrived first it is at least as
    // fresh, so this loader must not clobber it. Mirrors the live monitor's own
    // `if (!store().architecture)` guard and ensures initializeSearch runs once
    // per source instead of racing a double init (F-VW-7).
    function applyIfUnset(data: Architecture) {
      if (useArchStore.getState().architecture) return;
      setArchitecture(data);
      initializeSearch(data);
    }

    async function load() {
      try {
        setLoading(true);

        // Try split mode first (manifest.json). dataUrl resolves the ?data=
        // base so a member of a composed solution loads with the same code path.
        const manifestRes = await fetch(dataUrl("manifest.json"));
        if (isJsonResponse(manifestRes)) {
          const manifest = await manifestRes.json();
          // A composed multi-repo SOLUTION root: render the member index, not a
          // component graph (MULTI-REPO-DESIGN.md, M1).
          if (manifest && manifest.kind === SOLUTION_MANIFEST_KIND) {
            if (!useArchStore.getState().architecture) {
              setSolution(manifest as SolutionManifest);
              setLoading(false);
            }
            return;
          }
          // Split mode: manifest has components/relationships but no symbols/files
          const base: Architecture = { ...manifest, symbols: manifest.symbols || [], files: manifest.files || [] };
          const [orientation, support, security] = await Promise.all([
            optionalJson<OrientationProjection>("orientation.json"),
            optionalJson<SupportProjection>("support.json"),
            optionalJson<SecurityProjection>("security.json"),
          ]);
          const data = attachHumanViews(base, { orientation, support, security });
          applyIfUnset(data);
          return;
        }

        // Fall back to monolithic architecture.json
        const monoRes = await fetch("./architecture.json");
        if (isJsonResponse(monoRes)) {
          const data: Architecture = await monoRes.json();
          applyIfUnset(attachHumanViews(data, {}));
          return;
        }

        // Both paths failed to return JSON
        const status = monoRes.ok
          ? "Server returned HTML instead of JSON (no architecture data file found)"
          : `HTTP ${monoRes.status}`;
        throw new Error(
          `Could not load architecture data. ${status}. Run the analyzer to generate the data file.`
        );
      } catch (err) {
        // If the live monitor already loaded an architecture, a static-file miss
        // is not a failure; do not clobber a working view with an error screen.
        if (useArchStore.getState().architecture) return;
        setError(err instanceof Error ? err.message : "Failed to load architecture data");
      }
    }
    load();
  }, [setArchitecture, setLoading, setError]);

  // Load the OPTIONAL publication.json sidecar (design authority:
  // docs/publication/PUBLICATION-METADATA.md). It sits alongside the projection
  // and is resolved through the same data base as the architecture fetch, so a
  // member of a composed solution loads its own sidecar via ?data=. It is
  // publishing metadata, never analysis data, and only feeds the presentation
  // layer (display name, header banner, footer attribution). When the file is
  // absent, non-JSON (Vite SPA fallback), unparseable, or fails validation, the
  // viewer renders exactly as today (design rule 2): publication stays null and
  // every consumer falls back to architecture.name. A background 404 here is
  // expected and harmless, mirroring the manifest and live-config probes.
  useEffect(() => {
    let cancelled = false;

    async function loadPublication() {
      try {
        const res = await fetch(dataUrl("publication.json"));
        if (!res.ok) return;
        if (!(res.headers.get("content-type")?.includes("json") ?? false)) return;
        const raw = await res.json();
        const parsed = parsePublication(raw);
        if (!cancelled && parsed) setPublication(parsed);
      } catch {
        // Absent or unreadable sidecar: render exactly as today (no-op).
      }
    }

    loadPublication();
    return () => {
      cancelled = true;
    };
  }, [setPublication]);

  // Deep linking: two-way URL sync with popstate suppression (F-VW-2).
  useUrlSync();

  // Escape closes the detail panel, which the help dialog's own shortcut list
  // has always advertised ("Esc: Close panels / search") and nothing
  // implemented: every Escape listener in the app belongs to an overlay and is
  // registered only while that overlay is open (GUI crawl 2026-09-01,
  // journey.advertised_shortcut_dead).
  //
  // Last in the chain rather than competing with them: if any overlay, dialog
  // or drawer is open it owns the key, and a tour owns it too (Escape exits the
  // tour). The state is read at event time so this registers once and cannot go
  // stale. A field with focus keeps its own Escape (AnnotationInput cancels an
  // annotation with it), so a keypress from inside one is left alone.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const target = e.target as HTMLElement | null;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable
      ) return;
      const s = useArchStore.getState();
      if (s.activeTourId) return;
      const open = openOverlays({
        searchOpen: s.searchOpen,
        findingsOpen: s.findingsSurface.open,
        supplyChainOpen: s.supplyChainOpen,
        inventoryOpen: s.inventoryOpen,
        toursOpen: s.toursOpen,
        helpOpen: s.helpOpen,
        welcomeOpen: s.welcomeOpen,
        orientationOpen: s.orientationOpen,
        adminOpen: s.adminOpen,
        activePanel: s.activePanel,
        trustOpen: s.trustOpen,
        preferencesOpen: s.preferencesOpen,
      });
      if (open.length > 0) return;
      if (!s.selectedComponentId) return;
      // selectComponent(null) is the app's definition of a cleared selection,
      // review mode's panel rule included.
      s.selectComponent(null);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Auto-expand right panel when content appears
  useEffect(() => {
    if (activePanel === "detail" || activePanel === "review") {
      setRightCollapsed(false);
    }
  }, [activePanel]);

  // Mobile: opening the review summary must expand the bottom sheet past its
  // peek snap. The peek header only renders for a selected component, and in
  // review mode there is none, so a peek-height sheet would show blank content
  // (adversarial review of the mobile-parity PR). Snap to half so the summary
  // is visible without a manual swipe.
  useEffect(() => {
    if (activePanel === "review") {
      bottomSheet.setSnap("half");
    }
  }, [activePanel, bottomSheet.setSnap]);

  // Mobile: a selection the app made FOR the reader has to be visible, for the
  // same reason review mode does above. The sheet's "peek" default is right for
  // a direct tap on a graph node, where the reader can see what they touched and
  // the peek header names it; it is wrong for a tour step, a tour's evidence
  // link, a search result or a tree row, which land on something the reader
  // never touched and left them reading a name they already had. The store sets
  // revealDetail on exactly those paths (see its comment); this consumes it.
  useEffect(() => {
    if (!revealDetail) return;
    bottomSheet.setSnap("half");
    clearRevealDetail();
  }, [revealDetail, bottomSheet.setSnap, clearRevealDetail]);

  // The other direction. A tour step and the start of a tour ask for the
  // diagram, so the sheet drops back to its peek strip and the canvas gets
  // its height back; see collapseDetail in the store for the measured case.
  useEffect(() => {
    if (!collapseDetail) return;
    bottomSheet.setSnap("peek");
    clearDetailCollapse();
  }, [collapseDetail, bottomSheet.setSnap, clearDetailCollapse]);

  // Apply the dress (data-theme) and the time of day (dark/light) to the root
  // element. Both are pure CSS switches: every themed value in the viewer is a
  // Tailwind utility that resolves through a custom property, and themes.css
  // redefines those properties under these selectors. Nothing about data,
  // layout, or interaction changes with either.
  useEffect(() => {
    // The store applies this synchronously when either setting changes; this
    // covers first mount and any path that sets state without going through
    // those actions. Idempotent either way.
    applyThemeToDocument(theme, darkMode);
    // The page ground comes from the theme rather than a hardcoded utility, so
    // the paper and parchment themes are not sitting on a white or near-black
    // slab that belongs to Signal.
    document.body.className = darkMode
      ? "bg-[var(--se-page)] text-zinc-100 antialiased"
      : "bg-[var(--se-page)] text-zinc-900 antialiased";
  }, [darkMode, theme]);

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className="text-center">
          <div className={`animate-spin w-8 h-8 border-2 rounded-full mb-4 mx-auto ${darkMode ? "border-zinc-700 border-t-blue-500" : "border-zinc-300 border-t-blue-500"}`} />
          <p className={`text-sm ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>Loading architecture...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-screen flex items-center justify-center">
        <div className={`text-center max-w-md mx-4 p-8 rounded-2xl ${darkMode ? "bg-zinc-900" : "bg-zinc-50"}`}>
          <div className="text-4xl mb-4">&#x26A0;&#xFE0F;</div>
          <h2 className={`text-lg font-bold mb-2 ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
            Architecture Data Not Found
          </h2>
          <p className={`text-sm mb-4 ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{error}</p>
          <div className={`text-xs text-left p-4 rounded-lg font-mono ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-600"}`}>
            <p>Run the analyzer first:</p>
            <p className="mt-2 text-blue-400">python3 analyze.py /path/to/repo -o viewer/public/architecture.json</p>
          </div>
        </div>
      </div>
    );
  }

  // A composed multi-repo solution renders the member index (M1). Tapping a
  // member navigates (via ?data=) into that member's standalone dataset, which
  // loads through the normal architecture path below.
  if (solution) {
    return (
      <SolutionIndex
        solution={solution}
        solutionBase={getDataBase()}
        darkMode={darkMode}
      />
    );
  }

  if (!architecture) return null;

  // The DISPLAY name: publication.subject.name (editable sidecar) when present,
  // else the folder-derived architecture.name (the contextual default). This is
  // display only; the annotation identity key stays on architecture.name.
  const displayName = publicationDisplayName(publication, architecture.name);
  const showLegacyOpeningBands = false;

  if (experienceMode === "overview") {
    // The beacon rides along here too. It is the only element that can answer
    // "which aperture am I in", so mounting it only in the workbench would
    // make the one state it exists to publish unreadable in exactly the mode a
    // fresh reader lands in.
    return (
      <>
        <NavStateBeacon />
        <SystemOverview displayName={displayName} />
      </>
    );
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <NavStateBeacon />

      {/* Publication header banner (always region), rendered at the very top per
          the placement contract. Absent-file behavior: renders nothing. */}
      <PublicationBanner />
      {/* Header */}
      <header
        className={`
          flex items-center justify-between gap-1 px-2 py-2 border-b shrink-0 z-30 sm:gap-3 sm:px-4
          ${darkMode ? "bg-zinc-950/95 border-zinc-800" : "bg-white/95 border-zinc-200"}
          backdrop-blur-sm transition-transform duration-300
        `}
        style={{
          paddingTop: `max(0.5rem, env(safe-area-inset-top))`,
          transform: mobileChromeHidden ? "translateY(-100%)" : "none",
        }}
      >
        <div className="flex items-center gap-3">
          {/* Mobile sidebar toggle. min-h/min-w-[44px] under sm meets the ~44px
              mobile tap-target guideline (header-wide pass); sm:* reverts to the
              original compact size. */}
          <button
            data-testid="tree-expand"
            className={`lg:hidden flex items-center justify-center p-2 rounded-lg min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-600"}`}
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label="Open architecture tree"
          >
            &#x2630;
          </button>

          <div className="hidden min-w-0 items-center gap-2 sm:flex">
            <h1 className={`max-w-40 truncate font-bold text-sm ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
              {displayName}
            </h1>
            <span className={`hidden sm:inline text-xs ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
              Architecture
            </span>
            {architecture.repositories && architecture.repositories.length > 1 && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${darkMode ? "bg-indigo-500/20 text-indigo-300" : "bg-indigo-100 text-indigo-700"}`}>
                {architecture.repositories.length} repos
              </span>
            )}
            {architecture.repository && /^https?:/i.test(architecture.repository) && (
              <a
                href={architecture.repository}
                target="_blank"
                rel="noopener noreferrer"
                className={`
                  hidden sm:flex items-center gap-1 text-xs px-2 py-0.5 rounded-md
                  ${darkMode
                    ? "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                    : "text-zinc-500 hover:text-zinc-700 hover:bg-zinc-100"
                  }
                `}
              >
                <span>&#x1F517;</span>
                <span>{displayName} Repository</span>
              </a>
            )}
          </div>
        </div>

        <div data-testid="header-tools" className="flex min-w-0 items-center gap-1 sm:gap-2">
          <ExperienceSwitcher className="hidden sm:flex" />
          {/* Home button - visible when drilled into a component */}
          {drillLevel && (
            <button
              data-testid="drill-home"
              onClick={() => navigateToBreadcrumb(-1)}
              className={`
                flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium
                ${darkMode
                  ? "bg-blue-500/15 text-blue-300 hover:bg-blue-500/25"
                  : "bg-blue-100 text-blue-700 hover:bg-blue-200"
                }
              `}
              title="Return to top-level architecture view"
            >
              <span>&#x1F3E0;</span>
              <span className="hidden sm:inline">Home</span>
            </button>
          )}

          {/* Search button. min-h-[44px] under sm meets the ~44px mobile tap-target
              guideline; sm:min-h-0 keeps the compact desktop height (PR #85
              review F3 header-wide follow-up). */}
          <button
            data-testid="search-button"
            onClick={() => setSearchOpen(true)}
            className={`
              hidden items-center gap-2 px-3 py-1.5 rounded-lg text-sm sm:flex
              min-h-[44px] sm:min-h-0
              ${darkMode
                ? "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-300"
                : "bg-zinc-100 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-700"
              }
            `}
          >
            <span>&#x1F50D;</span>
            <span className="hidden sm:inline">Search</span>
            <kbd className={`hidden sm:inline text-[10px] px-1 rounded ${darkMode ? "bg-zinc-700" : "bg-zinc-200"}`}>
              &#x2318;K
            </kbd>
          </button>

          {/* Lens switcher (P6-1). Visible on every viewport so lenses are
              reachable on a phone (GUI run finding V8.4). */}
          <LensSwitcher />

          {/* Review mode: reachable on every viewport so the annotation
              workflow works on a phone (GUI run finding V8.8). The button is
              already responsive (icon-only under sm). */}
          <div className="hidden sm:block"><ReviewModeButton /></div>

          {/* Theme + appearance. Reachable on every viewport, the way the lens
              switcher is: on a phone the dark-mode toggle used to be buried in
              the overflow menu, and the dress is the first thing a demo
              audience asks to see changed. */}
          <ThemeSwitcher />

          <button data-testid="preferences-button" onClick={() => setPreferencesOpen(true)} className={`hidden rounded-lg p-2 sm:block ${darkMode ? "text-zinc-400 hover:bg-zinc-800" : "text-zinc-600 hover:bg-zinc-100"}`} aria-label="Viewer preferences">◒</button>

          {/* Desktop: remaining secondary buttons inline */}
          <div className="hidden sm:flex items-center gap-2">
            {liveConfig && (
              <button
                onClick={() => setAdminOpen(!adminOpen)}
                className={`p-2 rounded-lg relative ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-600"}`}
                title="Admin Dashboard (Cmd+Shift+A)"
              >
                {"\u2699"}
                {architecture?.live_status?.statuses &&
                  Object.values(architecture.live_status.statuses).some((s) => s.level === "error") && (
                  <div className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                )}
              </button>
            )}

            <button
              onClick={toggleEnhancedFrames}
              className={`p-2 rounded-lg ${darkMode ? "hover:bg-zinc-800" : "hover:bg-zinc-100"} ${enhancedFrames ? (darkMode ? "text-orange-400" : "text-orange-500") : (darkMode ? "text-zinc-400" : "text-zinc-600")}`}
              title={enhancedFrames ? "Switch to classic frames" : "Switch to enhanced frames"}
            >
              {"\u{1F4F1}"}
            </button>
          </div>

          {/* Mobile: overflow menu for secondary actions. This control is only
              rendered under sm (the wrapper is sm:hidden), so a fixed 44px tap
              target applies; there is no desktop size to preserve here. */}
          <div ref={moreMenuRef} className="sm:hidden relative">
            <button
              data-testid="more-menu"
              onClick={() => setMoreMenuOpen(!moreMenuOpen)}
              className={`flex items-center justify-center p-2 rounded-lg min-h-[44px] min-w-[44px] ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-600"}`}
              title="More options"
              aria-label="More options"
            >
              {"\u22EF"}
            </button>
            {moreMenuOpen && (
              <div className={`
                absolute right-0 top-full mt-1 w-48 rounded-xl shadow-xl border z-50
                ${darkMode ? "bg-zinc-900 border-zinc-700" : "bg-white border-zinc-200"}
              `}>
                <div className="py-1">
                  <button
                    onClick={() => { toggleEnhancedFrames(); setMoreMenuOpen(false); }}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm ${darkMode ? "hover:bg-zinc-800 text-zinc-300" : "hover:bg-zinc-100 text-zinc-700"}`}
                  >
                    <span>{"\u{1F4F1}"}</span>
                    <span>{enhancedFrames ? "Classic frames" : "Enhanced frames"}</span>
                  </button>
                  <button
                    onClick={() => { setPreferencesOpen(true); setMoreMenuOpen(false); }}
                    className={`min-h-11 w-full flex items-center gap-2 px-3 py-2 text-sm ${darkMode ? "hover:bg-zinc-800 text-zinc-300" : "hover:bg-zinc-100 text-zinc-700"}`}
                  >
                    <span>◒</span>
                    <span>Viewer preferences</span>
                  </button>
                  <button
                    onClick={() => { toggleReviewMode(); setMoreMenuOpen(false); }}
                    className={`min-h-11 w-full flex items-center gap-2 px-3 py-2 text-sm ${darkMode ? "hover:bg-zinc-800 text-zinc-300" : "hover:bg-zinc-100 text-zinc-700"}`}
                  >
                    <span>✍️</span>
                    <span>{reviewMode ? "Exit review mode" : "Review mode"}</span>
                  </button>
                  <button
                    data-testid="help-button"
                    onClick={() => { window.dispatchEvent(new Event("arch-viz-open-help")); setMoreMenuOpen(false); }}
                    className={`min-h-11 w-full flex items-center gap-2 px-3 py-2 text-sm ${darkMode ? "hover:bg-zinc-800 text-zinc-300" : "hover:bg-zinc-100 text-zinc-700"}`}
                  >
                    <span>?</span>
                    <span>Help</span>
                  </button>
                  {liveConfig && (
                    <button
                      onClick={() => { setAdminOpen(!adminOpen); setMoreMenuOpen(false); }}
                      className={`w-full flex items-center gap-2 px-3 py-2 text-sm ${darkMode ? "hover:bg-zinc-800 text-zinc-300" : "hover:bg-zinc-100 text-zinc-700"}`}
                    >
                      <span>{"\u2699"}</span>
                      <span>Admin Dashboard</span>
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Stats */}
          <div className={`hidden md:flex items-center gap-3 text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            <span>{formatNumber(architecture.stats.total_components)} components</span>
            <span>{formatNumber(architecture.stats.total_files)} files</span>
            {architecture.stats.lines_by_class ? (
              // Honest headline numbers (S8): lead with code lines; the rest
              // of the taxonomy is visible inline and detailed on hover.
              <span
                title={`Code ${formatNumber(architecture.stats.lines_by_class.code)} · Data ${formatNumber(architecture.stats.lines_by_class.data)} · Docs ${formatNumber(architecture.stats.lines_by_class.docs)} · Config ${formatNumber(architecture.stats.lines_by_class.config)} · Total ${formatNumber(architecture.stats.total_lines)} lines`}
              >
                {formatNumber(architecture.stats.lines_by_class.code)} code lines
                <span className={darkMode ? "text-zinc-600" : "text-zinc-300"}>
                  {" "}+ {formatNumber(architecture.stats.total_lines - architecture.stats.lines_by_class.code)} data/docs
                </span>
              </span>
            ) : (
              <span>{formatNumber(architecture.stats.total_lines)} lines</span>
            )}
            {architecture.generated_at && (
              <>
                <span className={darkMode ? "text-zinc-700" : "text-zinc-300"}>|</span>
                <span className={`font-medium ${darkMode ? "text-zinc-400" : "text-zinc-500"}`} title={new Date(architecture.generated_at).toLocaleString()}>
                  Generated {formatRelativeTime(architecture.generated_at)}
                </span>
              </>
            )}
          </div>

          {/* Live connection indicator */}
          {liveConfig && (
            <div className={`flex items-center gap-1.5 text-xs ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
              <span className={`inline-block w-2 h-2 rounded-full ${
                liveMonitorStatus === "error" ? "bg-red-500" :
                liveMonitorStatus === "paused" ? (darkMode ? "bg-zinc-600" : "bg-zinc-400") :
                liveMonitorStatus === "updating" ? "bg-green-500 animate-pulse" :
                "bg-green-500"
              }`} />
              <span>Live</span>
            </div>
          )}

          {/* SysCorpus project link */}
          <a
            href="https://github.com/sirfifer/solution-explorer"
            target="_blank"
            rel="noopener noreferrer"
            className={`
              hidden sm:flex items-center gap-1 text-[10px] px-2 py-1 rounded-md
              ${darkMode
                ? "text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800"
                : "text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100"
              }
            `}
            title="Built with SysCorpus"
          >
            <span>&#x2699;&#xFE0F;</span>
            <span>SysCorpus</span>
          </a>
        </div>
      </header>

      <WorkbenchTrustStrip />

      {showLegacyOpeningBands && <>

      {/* AI summary banner */}
      {architecture.ai_enhance?.summary && !summaryDismissed && (
        <div data-se="summary" className={`
          px-4 py-2 text-xs shrink-0
          ${darkMode ? "bg-indigo-950/30 border-b border-indigo-800/30 text-indigo-300" : "bg-indigo-50 border-b border-indigo-200 text-indigo-700"}
        `}>
          <div className="flex items-start gap-2">
            <span className="shrink-0 mt-0.5">&#x2728;</span>
            <p className="flex-1 leading-relaxed">{architecture.ai_enhance.summary}</p>
            <div className="flex items-center gap-1 shrink-0">
              {(architecture.ai_enhance.tech_diversity || architecture.ai_enhance.test_health_summary ||
                architecture.ai_enhance.recent_changes_summary || architecture.ai_enhance.data_flow_narrative ||
                architecture.ai_enhance.component_groups?.length ||
                bannerCritical.length > 0 || bannerDependencies.length > 0) && (
                <button
                  onClick={() => setSummaryExpandedPersisted(!summaryExpanded)}
                  className={`p-0.5 rounded ${darkMode ? "hover:bg-indigo-900/40 text-indigo-500" : "hover:bg-indigo-100 text-indigo-400"}`}
                  title={summaryExpanded ? "Show less" : "Show more"}
                >
                  {summaryExpanded ? "▲" : "▼"}
                </button>
              )}
              <button
                onClick={() => setSummaryDismissed(true)}
                className={`p-0.5 rounded ${darkMode ? "hover:bg-indigo-900/40 text-indigo-500" : "hover:bg-indigo-100 text-indigo-400"}`}
                title="Dismiss"
              >
                &#x2715;
              </button>
            </div>
          </div>
          {summaryExpanded && (
            <div className={`mt-2 pt-2 space-y-2 border-t ${darkMode ? "border-indigo-800/30" : "border-indigo-200"}`}>
              {/* Rollup rows (owner decision 2026-08-17): the first stakeholder
                  questions answered up front, with the Inventory lens as the
                  full surface one click away. */}
              {bannerCritical.length > 0 && (
                <div className="flex items-start gap-2">
                  <span className={`shrink-0 font-semibold uppercase tracking-wider ${darkMode ? "text-indigo-500" : "text-indigo-400"}`}>Critical</span>
                  <p className="leading-relaxed">
                    {bannerCritical.slice(0, 6).map((entry, i) => (
                      <span key={entry.id}>
                        {i > 0 && ", "}
                        <button
                          className="underline decoration-dotted underline-offset-2 hover:opacity-75"
                          onClick={() => useArchStore.getState().navigateToComponent(entry.id)}
                        >
                          {entry.name}
                        </button>
                      </span>
                    ))}
                    {bannerCritical.length > 6 && ` and ${bannerCritical.length - 6} more`}
                  </p>
                </div>
              )}
              {bannerDependencies.length > 0 && (
                <div className="flex items-start gap-2">
                  <Tooltip content={TOOLTIP_COPY.inventoryLens.externalDependencies} focusable>
                    <span className={`shrink-0 font-semibold uppercase tracking-wider underline decoration-dotted underline-offset-2 ${darkMode ? "text-indigo-500" : "text-indigo-400"}`}>
                      Depends on (detected)
                    </span>
                  </Tooltip>
                  <p className="leading-relaxed">
                    {bannerDependencies.slice(0, 8).map((d) => d.name).join(", ")}
                    {bannerDependencies.length > 8 && ` and ${bannerDependencies.length - 8} more`}
                  </p>
                </div>
              )}
              {(bannerCritical.length > 0 || bannerDependencies.length > 0) && (
                <button
                  className={`text-[11px] font-semibold underline underline-offset-2 ${darkMode ? "text-indigo-400 hover:text-indigo-300" : "text-indigo-600 hover:text-indigo-500"}`}
                  onClick={() => useArchStore.getState().setLens("inventory")}
                >
                  View critical components and dependencies in the Inventory lens
                </button>
              )}
              {architecture.ai_enhance.data_flow_narrative && (
                <div className="flex items-start gap-2">
                  <span className={`shrink-0 font-semibold uppercase tracking-wider ${darkMode ? "text-indigo-500" : "text-indigo-400"}`}>Flow</span>
                  <p className="leading-relaxed">{architecture.ai_enhance.data_flow_narrative}</p>
                </div>
              )}
              {architecture.ai_enhance.tech_diversity && (
                <div className="flex items-start gap-2">
                  <span className={`shrink-0 font-semibold uppercase tracking-wider ${darkMode ? "text-indigo-500" : "text-indigo-400"}`}>Tech</span>
                  <p className="leading-relaxed">{architecture.ai_enhance.tech_diversity}</p>
                </div>
              )}
              {architecture.ai_enhance.test_health_summary && (
                <div className="flex items-start gap-2">
                  <span className={`shrink-0 font-semibold uppercase tracking-wider ${darkMode ? "text-indigo-500" : "text-indigo-400"}`}>Tests</span>
                  <p className="leading-relaxed">{architecture.ai_enhance.test_health_summary}</p>
                </div>
              )}
              {architecture.ai_enhance.recent_changes_summary && (
                <div className="flex items-start gap-2">
                  <span className={`shrink-0 font-semibold uppercase tracking-wider ${darkMode ? "text-indigo-500" : "text-indigo-400"}`}>Recent</span>
                  <p className="leading-relaxed">{architecture.ai_enhance.recent_changes_summary}</p>
                </div>
              )}
              {architecture.ai_enhance.observations && architecture.ai_enhance.observations.length > 0 && (
                <div className="flex items-start gap-2">
                  <span className={`shrink-0 font-semibold uppercase tracking-wider ${darkMode ? "text-indigo-500" : "text-indigo-400"}`}>Notes</span>
                  <div className="space-y-1">
                    {architecture.ai_enhance.observations.map((obs, i) => (
                      <div key={i} className="flex items-start gap-1.5">
                        <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${
                          obs.confidence === "high"
                            ? (darkMode ? "bg-indigo-900/40 text-indigo-300" : "bg-indigo-100 text-indigo-600")
                            : (darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500")
                        }`}>
                          {obs.category.replace(/_/g, " ")}
                        </span>
                        <span className="leading-relaxed">{obs.description}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {architecture.ai_enhance.component_groups && architecture.ai_enhance.component_groups.length > 0 && (
                <div className="flex items-start gap-2">
                  <span className={`shrink-0 font-semibold uppercase tracking-wider ${darkMode ? "text-indigo-500" : "text-indigo-400"}`}>Groups</span>
                  <div className="flex flex-wrap gap-1">
                    {architecture.ai_enhance.component_groups.map((group, i) => (
                      <span
                        key={i}
                        className={`px-1.5 py-0.5 rounded ${darkMode ? "bg-indigo-900/40 text-indigo-300" : "bg-indigo-100 text-indigo-600"}`}
                        title={group.component_ids.join(", ")}
                      >
                        {group.name} ({group.component_ids.length})
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Restore affordance (S9): a dismissed summary was one misclick from
          gone with no way back short of a reload. */}
      {architecture.ai_enhance?.summary && summaryDismissed && (
        <div className={`px-4 py-1 shrink-0 ${darkMode ? "bg-zinc-950" : "bg-white"}`}>
          <button
            onClick={() => setSummaryDismissed(false)}
            className={`text-[11px] ${darkMode ? "text-indigo-400 hover:text-indigo-300" : "text-indigo-600 hover:text-indigo-500"}`}
            title="Show the AI summary banner again"
          >
            &#x2728; Show summary
          </button>
        </div>
      )}

      {/* The entry strip: every globally reachable surface this dataset
          warrants, each present only when its own data is present. Wrapped so
          the crawl can ask "what does this projection offer" in one query.
          `contents` means the wrapper renders no box, so the strip lays out
          exactly as it did before it was wrapped.

          Note that the whole strip currently sits inside
          showLegacyOpeningBands, which is a hard-coded false, so none of it
          renders in the workbench today. The wrapper is here anyway: it is the
          contract for these entries wherever they are mounted, and the crawl
          reports their absence rather than being written around it. */}
      <div data-testid="entry-bar" className="contents">
        {/* Coverage ledger badge and drill-in panel (P4-4, invariant I2) */}
        <CoverageBadge />

        {/* Producer-gap banner (R1 honesty surface), directly under coverage
            because both are honesty-about-scope; present only when the dataset
            carries producer gaps. */}
        <GapsBanner />

        {/* Findings surface entry point (P6-8), near the coverage badge; present
            whenever the dataset carries findings or concerns. */}
        <FindingsEntry />

        {/* Supply chain / SBOM entry point (P10-1), present whenever the dataset
            carries a supply_chain section; opens the SupplyChainSurface overlay. */}
        <SupplyChainEntry />

        {/* Tours entry point (P6-7); present only when the dataset carries tours. */}
        <ToursEntry />
      </div>
      </>}

      {/* Review mode banner */}
      {reviewMode && (
        <div className={`
          flex items-center justify-center gap-2 px-4 py-1.5 text-xs shrink-0
          ${darkMode ? "bg-blue-500/10 text-blue-300 border-b border-blue-500/20" : "bg-blue-50 text-blue-700 border-b border-blue-200"}
        `}>
          <span>&#x270D;&#xFE0F;</span>
          <span>Review Mode: click any component to add feedback</span>
        </div>
      )}

      {/* Status dashboard banner */}
      <StatusDashboard />

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Tree sidebar - desktop */}
        <aside
          className={`
            hidden lg:flex flex-col shrink-0 border-r relative
            ${darkMode ? "bg-zinc-950 border-zinc-800" : "bg-zinc-50 border-zinc-200"}
            transition-[width] duration-200 ease-in-out
          `}
          style={{ width: leftCollapsed ? 36 : leftWidth }}
        >
          {leftCollapsed ? (
            <button
              data-testid="tree-expand"
              onClick={() => setLeftCollapsed(false)}
              className={`w-full h-full flex items-center justify-center ${darkMode ? "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900" : "text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100"}`}
              title="Expand sidebar"
            >
              <span className="text-sm">{"\u00BB"}</span>
            </button>
          ) : (
            <>
              <TreeNavigator />
              {/* Collapse button */}
              <button
                onClick={() => setLeftCollapsed(true)}
                className={`absolute top-2 right-2 z-30 w-6 h-6 flex items-center justify-center rounded ${darkMode ? "text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800" : "text-zinc-400 hover:text-zinc-600 hover:bg-zinc-200"} transition-colors`}
                title="Collapse sidebar"
              >
                <span className="text-xs">{"\u00AB"}</span>
              </button>
              {/* Resize handle - wider grab area with visual indicator */}
              <div
                className={`absolute top-0 right-0 w-2 h-full cursor-col-resize z-20 group flex items-center justify-center`}
                onMouseDown={(e) => onMouseDown("left", e)}
              >
                {/* Visual indicator line */}
                <div className={`w-0.5 h-16 rounded-full transition-colors duration-75 ${darkMode ? "bg-zinc-700 group-hover:bg-blue-400" : "bg-zinc-300 group-hover:bg-blue-500"} group-active:bg-blue-600`} />
              </div>
            </>
          )}
        </aside>

        {/* Tree sidebar - mobile overlay */}
        {sidebarOpen && (
          <div className="lg:hidden fixed inset-0 z-40 flex">
            <div className="absolute inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
            <aside
              className={`
                relative w-72 flex flex-col
                ${darkMode ? "bg-zinc-950" : "bg-white"}
              `}
              style={{
                transform: treeDragging ? `translateX(${treeDragOffset}px)` : "none",
                transition: treeDragging ? "none" : "transform 0.3s ease",
              }}
              onTouchStart={onTreeTouchStart}
              onTouchMove={onTreeTouchMove}
              onTouchEnd={onTreeTouchEnd}
            >
              <TreeNavigator onSelect={closeTreeAfterSelection} />
            </aside>
          </div>
        )}

        {/* Graph (with the active lens's ranked panel docked left when present).
            The docked panel is mounted only at panel-viewport widths (O10):
            mounting both this and the mobile lens sheet duplicated every
            control in the DOM, the same reason the detail panel above is
            split by isDesktopViewport rather than left to CSS alone. */}
        <main className="flex-1 relative flex overflow-hidden">
          {isPanelViewport && lens === "flow" && <FlowPanel />}
          {isPanelViewport && lens === "inventory" && <InventoryLensPanel />}
          {isPanelViewport && lens === "activity" && <ActivityPanel />}
          {isPanelViewport && lens === "capability" && <CapabilityPanel />}
          {isPanelViewport && lens === "data" && <DataPanel />}
          {isPanelViewport && lens === "rules" && <RulesPanel />}
          {isPanelViewport && lens === "design" && <DesignPanel />}
          {isPanelViewport && lens === "support" && <SupportPanel />}
          {isPanelViewport && lens === "security" && <SecurityPanel />}
          <div data-se="graph-frame" data-testid="graph-frame" className="flex-1 relative" style={{ paddingBottom: mobileGraphBottomReserve }}>
            <ReactFlowProvider>
              <ArchitectureGraph />
            </ReactFlowProvider>
          </div>
        </main>

        {/* Detail / Review panel - desktop. Mounted only at desktop widths:
            mounting both this and the bottom sheet duplicated every control in
            the DOM (two Copy All buttons, two independent Clear All confirm
            states; comprehension-study S4). */}
        {isDesktopViewport && (activePanel === "detail" || activePanel === "review") && (
          <aside
            data-se="panel"
            className={`
              hidden lg:flex flex-col shrink-0 border-l relative
              ${darkMode ? "bg-zinc-950 border-zinc-800" : "bg-zinc-50 border-zinc-200"}
              transition-[width] duration-200 ease-in-out
            `}
            style={{ width: rightCollapsed ? 36 : rightWidth }}
          >
            {rightCollapsed ? (
              <button
                onClick={() => setRightCollapsed(false)}
                className={`w-full h-full flex items-center justify-center ${darkMode ? "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900" : "text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100"}`}
                title="Expand panel"
              >
                <span className="text-sm">{"\u00AB"}</span>
              </button>
            ) : (
              <>
                {/* Collapse button */}
                <button
                  onClick={() => setRightCollapsed(true)}
                  className={`absolute top-2 left-4 z-30 w-6 h-6 flex items-center justify-center rounded ${darkMode ? "text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800" : "text-zinc-400 hover:text-zinc-600 hover:bg-zinc-200"} transition-colors`}
                  title="Collapse panel"
                >
                  <span className="text-xs">{"\u00BB"}</span>
                </button>
                {/* Resize handle - wider grab area with visual indicator */}
                <div
                  className={`absolute top-0 left-0 w-2 h-full cursor-col-resize z-20 group flex items-center justify-center`}
                  onMouseDown={(e) => onMouseDown("right", e)}
                >
                  {/* Visual indicator line */}
                  <div className={`w-0.5 h-16 rounded-full transition-colors duration-75 ${darkMode ? "bg-zinc-700 group-hover:bg-blue-400" : "bg-zinc-300 group-hover:bg-blue-500"} group-active:bg-blue-600`} />
                </div>
                {activePanel === "review" ? <ReviewSummary /> : <DetailPanel />}
              </>
            )}
          </aside>
        )}

        {/* Detail / Review panel - mobile bottom sheet */}
        {showMobileDetailSheet && activePanel && (
          <MobileBottomSheet
            darkMode={darkMode}
            activePanel={activePanel}
            bottomSheet={bottomSheet}
          />
        )}

        {/* Lens panel - mobile bottom sheet (O10). Only when no detail/review
            sheet is already claiming the bottom of the screen: picking a row
            inside the lens panel navigates to a component, which opens the
            detail sheet (navigateToComponent always sets activePanel to
            "detail"), and the two sheets sharing the screen has nowhere to go
            on a phone. Dismissing the detail sheet (activePanel back to null)
            brings the lens sheet back, same as the docked panel staying put
            beside the detail aside on desktop. */}
        {shouldShowMobileLensSheet({ isPanelViewport, lens, activePanel }) && (
          <MobileLensSheet
            lens={lens}
            darkMode={darkMode}
            bottomSheet={lensBottomSheet}
          />
        )}
      </div>

      {/* Publication footer attribution (always region), rendered at the bottom
          per the placement contract, above the mobile bottom nav. Absent-file
          behavior: renders nothing. */}
      <PublicationFooter />

      {/* Mobile bottom nav */}
      <nav
        data-se="mobile-nav"
        className={`
          lg:hidden flex items-center justify-around border-t py-2 shrink-0
          ${darkMode ? "bg-zinc-950/95 border-zinc-800" : "bg-white/95 border-zinc-200"}
          backdrop-blur-sm transition-transform duration-300
        `}
        style={{
          paddingBottom: `max(0.5rem, env(safe-area-inset-bottom))`,
          transform: mobileChromeHidden ? "translateY(100%)" : "none",
        }}
      >
        <button
          onClick={() => setExperienceMode("overview")}
          className={`flex min-h-11 min-w-14 flex-col items-center gap-0.5 px-2 py-1 ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}
        >
          <span className="text-lg">&#x25CE;</span>
          <span className="text-xs">Overview</span>
        </button>
        <button
          onClick={() => { setSidebarOpen(true); }}
          className={`flex min-h-11 min-w-14 flex-col items-center gap-0.5 px-2 py-1 ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}
        >
          <span className="text-lg">&#x1F4CB;</span>
          <span className="text-xs">Tree</span>
        </button>
        <button
          onClick={() => { setSidebarOpen(false); setActivePanel(null); }}
          className={`flex min-h-11 min-w-14 flex-col items-center gap-0.5 px-2 py-1 ${!drillLevel ? (darkMode ? "text-blue-400" : "text-blue-500") : (darkMode ? "text-zinc-400" : "text-zinc-500")}`}
        >
          <span className="text-lg">&#x1F310;</span>
          <span className="text-xs">Graph</span>
        </button>
        <button
          data-testid="search-button"
          onClick={() => setSearchOpen(true)}
          className={`flex min-h-11 min-w-14 flex-col items-center gap-0.5 px-2 py-1 ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}
        >
          <span className="text-lg">&#x1F50D;</span>
          <span className="text-xs">Search</span>
        </button>
      </nav>

      {/* File deep-link "not found" notice (non-blocking, dismissible) */}
      {fileDeepLinkNotice && (
        <div
          role="status"
          className={`
            fixed bottom-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3
            px-4 py-2.5 rounded-xl shadow-xl text-sm max-w-[90vw]
            ${darkMode ? "bg-zinc-800 text-zinc-200 border border-zinc-700" : "bg-white text-zinc-800 border border-zinc-200"}
          `}
        >
          <span>&#x26A0;&#xFE0F;</span>
          <span className="truncate">{fileDeepLinkNotice}</span>
          <button
            onClick={clearFileDeepLinkNotice}
            className={`shrink-0 p-1 rounded ${darkMode ? "hover:bg-zinc-700 text-zinc-400" : "hover:bg-zinc-100 text-zinc-500"}`}
            title="Dismiss"
          >
            &#x2715;
          </button>
        </div>
      )}

      {/* Annotation input modal */}
      {annotatingComponentId && <AnnotationInput />}

      {/* Search overlay */}
      <SearchOverlay />

      <TrustDrawer />
      <ViewerPreferences />

      {/* Findings and concerns surface overlay (P6-8) */}
      <FindingsSurface />

      {/* Supply chain / SBOM surface overlay (P10-1) */}
      <SupplyChainSurface />

      {/* Guided-walkthrough player: tour list overlay + docked step panel (P6-7) */}
      <TourPlayer />

      {/* Admin dashboard */}
      {adminOpen && <AdminDashboard />}

      {/* Help system */}
      <HelpSystem />

      <OrientationInvite />
      <OrientationWalk />

    </div>
  );
}
