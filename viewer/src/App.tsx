import { useEffect, useState, useCallback, useRef } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { useArchStore } from "./store";
import { ArchitectureGraph } from "./components/ArchitectureGraph";
import { TreeNavigator } from "./components/TreeNavigator";
import { DetailPanel } from "./components/DetailPanel";
import { SearchOverlay } from "./components/SearchOverlay";
import { HelpSystem } from "./components/HelpSystem";
import { ReviewModeButton } from "./components/ReviewModeButton";
import { AnnotationInput } from "./components/AnnotationInput";
import { ReviewSummary } from "./components/ReviewSummary";
import { AdminDashboard } from "./components/AdminDashboard";
import { StatusDashboard } from "./components/StatusDashboard";
import { CoverageBadge } from "./components/CoverageBadge";
import { LensSwitcher } from "./components/LensSwitcher";
import { ActivityPanel } from "./components/ActivityPanel";
import { useLiveMonitor } from "./hooks/useLiveMonitor";
import { useUrlSync } from "./hooks/useUrlSync";
import { useBottomSheet } from "./hooks/useBottomSheet";
import type { SnapPoint } from "./hooks/useBottomSheet";
import { initializeSearch } from "./utils/search";
import { formatNumber, formatRelativeTime, getTypeColors } from "./utils/layout";
import type { Architecture, Component } from "./types";

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
  const windowH = typeof window !== "undefined" ? window.innerHeight : 800;
  const baseHeightPx = (sheetHeight / 100) * windowH;
  const currentHeightPx = isDragging
    ? Math.max(0, Math.min(windowH * 0.95, baseHeightPx - dragOffset))
    : baseHeightPx;

  // Get component info for peek view
  const component = detailItem?.type === "component" ? (detailItem.data as Component) : null;
  const colors = component ? getTypeColors(component.type, darkMode) : null;

  return (
    <div
      className={`
        lg:hidden fixed bottom-0 left-0 right-0 z-30
        flex flex-col rounded-t-2xl shadow-2xl
        ${darkMode ? "bg-zinc-900 border-t border-zinc-800" : "bg-white border-t border-zinc-200"}
      `}
      style={{
        height: currentHeightPx,
        transition: isDragging ? "none" : "height 0.3s cubic-bezier(0.25, 1, 0.5, 1)",
        willChange: isDragging ? "height" : "auto",
        paddingBottom: `env(safe-area-inset-bottom)`,
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

export function App() {
  const {
    architecture,
    loading,
    error,
    darkMode,
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
    toggleDarkMode,
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
  } = useArchStore();

  useLiveMonitor();

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [summaryDismissed, setSummaryDismissed] = useState(false);
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const moreMenuRef = useRef<HTMLDivElement>(null);

  // Tree sidebar swipe-to-close state
  const treeTouchStartX = useRef(0);
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

  // Mobile bottom sheet
  const bottomSheet = useBottomSheet({
    onDismiss: () => setActivePanel(null),
    initialSnap: "peek" as SnapPoint,
  });

  // Collapsible + resizable sidebar widths (restored from session storage)
  const [leftCollapsed, setLeftCollapsed] = useState(() => getStoredValue(STORAGE_KEYS.leftCollapsed, false));
  const [rightCollapsed, setRightCollapsed] = useState(() => getStoredValue(STORAGE_KEYS.rightCollapsed, false));
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

        // Try split mode first (manifest.json)
        const manifestRes = await fetch("./architecture/manifest.json");
        if (isJsonResponse(manifestRes)) {
          const manifest = await manifestRes.json();
          // Split mode: manifest has components/relationships but no symbols/files
          const data: Architecture = { ...manifest, symbols: manifest.symbols || [], files: manifest.files || [] };
          applyIfUnset(data);
          return;
        }

        // Fall back to monolithic architecture.json
        const monoRes = await fetch("./architecture.json");
        if (isJsonResponse(monoRes)) {
          const data: Architecture = await monoRes.json();
          applyIfUnset(data);
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

  // Deep linking: two-way URL sync with popstate suppression (F-VW-2).
  useUrlSync();

  // Auto-expand right panel when content appears
  useEffect(() => {
    if (activePanel === "detail" || activePanel === "review") {
      setRightCollapsed(false);
    }
  }, [activePanel]);

  // Apply dark mode class
  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
    document.documentElement.classList.toggle("light", !darkMode);
    document.body.className = darkMode
      ? "bg-zinc-950 text-zinc-100 antialiased"
      : "bg-white text-zinc-900 antialiased";
  }, [darkMode]);

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

  if (!architecture) return null;

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Header */}
      <header
        className={`
          flex items-center justify-between px-4 py-2 border-b shrink-0 z-30
          ${darkMode ? "bg-zinc-950/95 border-zinc-800" : "bg-white/95 border-zinc-200"}
          backdrop-blur-sm transition-transform duration-300
        `}
        style={{
          paddingTop: `max(0.5rem, env(safe-area-inset-top))`,
          transform: mobileChromeHidden ? "translateY(-100%)" : "none",
        }}
      >
        <div className="flex items-center gap-3">
          {/* Mobile sidebar toggle */}
          <button
            className={`lg:hidden p-2 rounded-lg ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-600"}`}
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            &#x2630;
          </button>

          <div className="flex items-center gap-2">
            <h1 className={`font-bold text-sm ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
              {architecture.name}
            </h1>
            <span className={`hidden sm:inline text-xs ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
              Architecture
            </span>
            {architecture.repositories && architecture.repositories.length > 1 && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${darkMode ? "bg-indigo-500/20 text-indigo-300" : "bg-indigo-100 text-indigo-700"}`}>
                {architecture.repositories.length} repos
              </span>
            )}
            {architecture.repository && (
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
                <span>{architecture.name} Repository</span>
              </a>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Home button - visible when drilled into a component */}
          {drillLevel && (
            <button
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

          {/* Search button */}
          <button
            onClick={() => setSearchOpen(true)}
            className={`
              flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm
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

          {/* Lens switcher (P6-1) */}
          <LensSwitcher />

          {/* Desktop: show all buttons inline */}
          <div className="hidden sm:flex items-center gap-2">
            <ReviewModeButton />

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
              onClick={toggleDarkMode}
              className={`p-2 rounded-lg ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-600"}`}
              title={darkMode ? "Light mode" : "Dark mode"}
            >
              {darkMode ? "\u2600" : "\u263E"}
            </button>

            <button
              onClick={toggleEnhancedFrames}
              className={`p-2 rounded-lg ${darkMode ? "hover:bg-zinc-800" : "hover:bg-zinc-100"} ${enhancedFrames ? (darkMode ? "text-orange-400" : "text-orange-500") : (darkMode ? "text-zinc-400" : "text-zinc-600")}`}
              title={enhancedFrames ? "Switch to classic frames" : "Switch to enhanced frames"}
            >
              {"\u{1F4F1}"}
            </button>
          </div>

          {/* Mobile: overflow menu for secondary actions */}
          <div ref={moreMenuRef} className="sm:hidden relative">
            <button
              onClick={() => setMoreMenuOpen(!moreMenuOpen)}
              className={`p-2 rounded-lg ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-600"}`}
              title="More options"
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
                    onClick={() => { toggleDarkMode(); setMoreMenuOpen(false); }}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm ${darkMode ? "hover:bg-zinc-800 text-zinc-300" : "hover:bg-zinc-100 text-zinc-700"}`}
                  >
                    <span>{darkMode ? "\u2600" : "\u263E"}</span>
                    <span>{darkMode ? "Light mode" : "Dark mode"}</span>
                  </button>
                  <button
                    onClick={() => { toggleEnhancedFrames(); setMoreMenuOpen(false); }}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm ${darkMode ? "hover:bg-zinc-800 text-zinc-300" : "hover:bg-zinc-100 text-zinc-700"}`}
                  >
                    <span>{"\u{1F4F1}"}</span>
                    <span>{enhancedFrames ? "Classic frames" : "Enhanced frames"}</span>
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
            <span>{formatNumber(architecture.stats.total_lines)} lines</span>
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

          {/* Solution Explorer link */}
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
            title="Built with Solution Explorer"
          >
            <span>&#x2699;&#xFE0F;</span>
            <span>Solution Explorer</span>
          </a>
        </div>
      </header>

      {/* AI summary banner */}
      {architecture.ai_enhance?.summary && !summaryDismissed && (
        <div className={`
          px-4 py-2 text-xs shrink-0
          ${darkMode ? "bg-indigo-950/30 border-b border-indigo-800/30 text-indigo-300" : "bg-indigo-50 border-b border-indigo-200 text-indigo-700"}
        `}>
          <div className="flex items-start gap-2">
            <span className="shrink-0 mt-0.5">&#x2728;</span>
            <p className="flex-1 leading-relaxed">{architecture.ai_enhance.summary}</p>
            <div className="flex items-center gap-1 shrink-0">
              {(architecture.ai_enhance.tech_diversity || architecture.ai_enhance.test_health_summary || architecture.ai_enhance.recent_changes_summary) && (
                <button
                  onClick={() => setSummaryExpanded(!summaryExpanded)}
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
            </div>
          )}
        </div>
      )}

      {/* Coverage ledger badge and drill-in panel (P4-4, invariant I2) */}
      <CoverageBadge />

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
              <TreeNavigator />
            </aside>
          </div>
        )}

        {/* Graph (with the Activity lens ranked panel docked left when active) */}
        <main className="flex-1 relative flex overflow-hidden">
          {lens === "activity" && <ActivityPanel />}
          <div className="flex-1 relative">
            <ReactFlowProvider>
              <ArchitectureGraph />
            </ReactFlowProvider>
          </div>
        </main>

        {/* Detail / Review panel - desktop */}
        {(activePanel === "detail" || activePanel === "review") && (
          <aside
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
        {(activePanel === "detail" || activePanel === "review") && (
          <MobileBottomSheet
            darkMode={darkMode}
            activePanel={activePanel}
            bottomSheet={bottomSheet}
          />
        )}
      </div>

      {/* Mobile bottom nav */}
      <nav
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
        {drillLevel && (
          <button
            onClick={() => navigateToBreadcrumb(-1)}
            className={`flex flex-col items-center gap-0.5 px-4 py-1 ${darkMode ? "text-blue-400" : "text-blue-500"}`}
          >
            <span className="text-lg">&#x1F3E0;</span>
            <span className="text-[10px]">Home</span>
          </button>
        )}
        <button
          onClick={() => { setSidebarOpen(true); }}
          className={`flex flex-col items-center gap-0.5 px-4 py-1 ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}
        >
          <span className="text-lg">&#x1F4CB;</span>
          <span className="text-[10px]">Tree</span>
        </button>
        <button
          onClick={() => { setSidebarOpen(false); setActivePanel(null); }}
          className={`flex flex-col items-center gap-0.5 px-4 py-1 ${!drillLevel ? (darkMode ? "text-blue-400" : "text-blue-500") : (darkMode ? "text-zinc-400" : "text-zinc-500")}`}
        >
          <span className="text-lg">&#x1F310;</span>
          <span className="text-[10px]">Graph</span>
        </button>
        <button
          onClick={() => setSearchOpen(true)}
          className={`flex flex-col items-center gap-0.5 px-4 py-1 ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}
        >
          <span className="text-lg">&#x1F50D;</span>
          <span className="text-[10px]">Search</span>
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

      {/* Admin dashboard */}
      {adminOpen && <AdminDashboard />}

      {/* Help system */}
      <HelpSystem />

    </div>
  );
}
