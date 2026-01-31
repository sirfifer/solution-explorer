import { useEffect, useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { useArchStore } from "./store";
import { ArchitectureGraph } from "./components/ArchitectureGraph";
import { TreeNavigator } from "./components/TreeNavigator";
import { DetailPanel } from "./components/DetailPanel";
import { SearchOverlay } from "./components/SearchOverlay";
import { HelpSystem } from "./components/HelpSystem";
import { initializeSearch } from "./utils/search";
import { formatNumber, formatBytes } from "./utils/layout";
import type { Architecture } from "./types";

export function App() {
  const {
    architecture,
    loading,
    error,
    darkMode,
    activePanel,
    setArchitecture,
    setLoading,
    setError,
    setSearchOpen,
    setActivePanel,
    toggleDarkMode,
  } = useArchStore();

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [mobilePanel, setMobilePanel] = useState<"graph" | "tree" | "detail">("graph");

  // Load architecture data
  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        const res = await fetch("./architecture.json");
        if (!res.ok) throw new Error(`Failed to load architecture data: ${res.status}`);
        const data: Architecture = await res.json();
        setArchitecture(data);
        initializeSearch(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load data");
      }
    }
    load();
  }, [setArchitecture, setLoading, setError]);

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
      <header className={`
        flex items-center justify-between px-4 py-2 border-b shrink-0 z-30
        ${darkMode ? "bg-zinc-950/95 border-zinc-800" : "bg-white/95 border-zinc-200"}
        backdrop-blur-sm
      `}>
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
            <span className={`text-xs ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
              Architecture
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
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

          {/* Theme toggle */}
          <button
            onClick={toggleDarkMode}
            className={`p-2 rounded-lg ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-600"}`}
            title={darkMode ? "Light mode" : "Dark mode"}
          >
            {darkMode ? "\u2600" : "\u263E"}
          </button>

          {/* Stats */}
          <div className={`hidden md:flex items-center gap-3 text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            <span>{formatNumber(architecture.stats.total_components)} components</span>
            <span>{formatNumber(architecture.stats.total_files)} files</span>
            <span>{formatNumber(architecture.stats.total_lines)} lines</span>
          </div>

          {/* Repo link */}
          {architecture.repository && (
            <a
              href={architecture.repository}
              target="_blank"
              rel="noopener noreferrer"
              className={`p-2 rounded-lg ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-600"}`}
              title="View repository"
            >
              &#x1F517;
            </a>
          )}
        </div>
      </header>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Tree sidebar - desktop */}
        <aside className={`
          hidden lg:flex flex-col w-64 shrink-0 border-r
          ${darkMode ? "bg-zinc-950 border-zinc-800" : "bg-zinc-50 border-zinc-200"}
        `}>
          <TreeNavigator />
        </aside>

        {/* Tree sidebar - mobile overlay */}
        {sidebarOpen && (
          <div className="lg:hidden fixed inset-0 z-40 flex">
            <div className="absolute inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
            <aside className={`
              relative w-72 flex flex-col
              ${darkMode ? "bg-zinc-950" : "bg-white"}
            `}>
              <TreeNavigator />
            </aside>
          </div>
        )}

        {/* Graph */}
        <main className="flex-1 relative">
          <ReactFlowProvider>
            <ArchitectureGraph />
          </ReactFlowProvider>
        </main>

        {/* Detail panel - desktop */}
        {activePanel === "detail" && (
          <aside className={`
            hidden lg:flex flex-col w-80 shrink-0 border-l
            ${darkMode ? "bg-zinc-950 border-zinc-800" : "bg-zinc-50 border-zinc-200"}
          `}>
            <DetailPanel />
          </aside>
        )}

        {/* Detail panel - mobile bottom sheet */}
        {activePanel === "detail" && (
          <div className={`
            lg:hidden fixed bottom-0 left-0 right-0 z-30
            max-h-[60vh] flex flex-col rounded-t-2xl shadow-2xl
            ${darkMode ? "bg-zinc-900 border-t border-zinc-800" : "bg-white border-t border-zinc-200"}
          `}>
            {/* Drag handle */}
            <div className="flex justify-center py-2">
              <div className={`w-10 h-1 rounded-full ${darkMode ? "bg-zinc-700" : "bg-zinc-300"}`} />
            </div>
            <div className="flex-1 overflow-y-auto">
              <DetailPanel />
            </div>
          </div>
        )}
      </div>

      {/* Mobile bottom nav */}
      <nav className={`
        lg:hidden flex items-center justify-around border-t py-2 shrink-0
        ${darkMode ? "bg-zinc-950/95 border-zinc-800" : "bg-white/95 border-zinc-200"}
        backdrop-blur-sm
      `}>
        <button
          onClick={() => { setSidebarOpen(true); }}
          className={`flex flex-col items-center gap-0.5 px-4 py-1 ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}
        >
          <span className="text-lg">&#x1F4CB;</span>
          <span className="text-[10px]">Tree</span>
        </button>
        <button
          onClick={() => { setSidebarOpen(false); setActivePanel(null); }}
          className={`flex flex-col items-center gap-0.5 px-4 py-1 ${darkMode ? "text-blue-400" : "text-blue-500"}`}
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

      {/* Search overlay */}
      <SearchOverlay />

      {/* Help system */}
      <HelpSystem />

      {/* Footer timestamp */}
      {architecture.generated_at && (
        <div className={`
          fixed bottom-2 left-2 text-[9px] z-10 hidden lg:block
          ${darkMode ? "text-zinc-700" : "text-zinc-400"}
        `}>
          Generated: {new Date(architecture.generated_at).toLocaleString()}
        </div>
      )}
    </div>
  );
}
