import { useEffect, useRef, useState, useMemo } from "react";
import { useArchStore } from "../store";
import {
  search,
  loadSearchShards,
  getShardLoadState,
  subscribeShardLoadState,
  getSearchIndexVersion,
  subscribeSearchIndex,
  type SearchResult,
  type ShardLoadState,
} from "../utils/search";
import { getLanguageColor } from "../utils/layout";

export function SearchOverlay() {
  const {
    searchOpen,
    searchQuery,
    setSearchOpen,
    setSearchQuery,
    navigateToComponent,
    showDetail,
    openFileDeepLink,
    loadComponentDetail,
    getComponentSymbols,
    architecture,
    darkMode,
    createSetFromSearchResults,
    setActivePanel,
  } = useArchStore();
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  // Mirrors search.ts's shard-load state so results drawn only from the
  // already-loaded architecture aren't presented as complete while shards are
  // still filling in descriptions/docstrings/AI text (or failed to load at
  // all). A subscription rather than polling: search.ts owns the state as
  // plain module data (no React dependency there), so the component syncs to
  // it via a small pub/sub instead of pulling the whole module into the store.
  const [shardLoadState, setShardLoadStateLocal] = useState<ShardLoadState>(getShardLoadState());
  useEffect(() => subscribeShardLoadState(setShardLoadStateLocal), []);
  const shardsPending =
    shardLoadState === "loading" || shardLoadState === "partial" || shardLoadState === "failed";

  // The index grows as shards arrive, so results must depend on the index
  // GENERATION as well as the query. Memoising on the query alone answered a
  // query once against whatever was indexed at that instant and never again,
  // which made every symbol on a large subject permanently unfindable.
  const [indexVersion, setIndexVersion] = useState(getSearchIndexVersion());
  useEffect(() => subscribeSearchIndex(setIndexVersion), []);

  const results = useMemo(
    () => (searchQuery ? search(searchQuery) : []),
    [searchQuery, indexVersion],
  );

  // Focus input and reset the selection whenever the overlay opens. Kept in its
  // own effect, keyed only on searchOpen, so a live-monitor architecture
  // refresh while the overlay is already open does not re-run it: that would
  // steal focus and reset selectedIndex mid-navigation, dropping the user's
  // arrow-key selection (PR #85 review F9).
  useEffect(() => {
    if (searchOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
      setSelectedIndex(0);
    }
  }, [searchOpen]);

  // A non-empty component_detail_index is only ever produced by a split-mode
  // projection's manifest; a monolith dataset omits the key entirely, and a
  // degraded split's skeleton writer can set it to {} (truthy in JS but empty).
  // Gate on non-empty so neither case probes a search index it cannot have
  // (the fetch would 404 on every search open; GUI run 20260721 finding, and
  // PR #86 review F8).
  const hasSearchIndex =
    !!architecture?.component_detail_index &&
    Object.keys(architecture.component_detail_index).length > 0;

  // Lazily load the prebuilt search shards so search covers descriptions,
  // docstrings, and AI help text without visiting each component (P6-4). Kept
  // separate from the focus/reset effect above so an architecture refresh
  // while the overlay is open can safely re-run this (loadSearchShards is
  // idempotent per session) without disturbing the current selection.
  useEffect(() => {
    if (searchOpen && hasSearchIndex) void loadSearchShards();
  }, [searchOpen, hasSearchIndex]);

  // Keyboard shortcut to open
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen(!searchOpen);
      }
      if (e.key === "Escape" && searchOpen) {
        setSearchOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [searchOpen, setSearchOpen]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" && results[selectedIndex]) {
      handleSelect(results[selectedIndex]);
    }
  };

  const handleSelect = (result: SearchResult) => {
    if (result.type === "component") {
      navigateToComponent(result.id);
    } else if (result.type === "file") {
      const file = architecture?.files.find((f) => f.path === result.id);
      if (file) {
        showDetail("file", file);
      } else {
        // Split-mode file present only in the shard index. Route through the
        // inbound deep-link resolver rather than a bare component navigation:
        // it drills to the owning component, opens the panel, and marks the
        // file in the Files tab. The old path landed on the parent's Overview
        // with the file nowhere in sight (comprehension-study S7).
        void openFileDeepLink(result.path || result.id, null);
      }
    } else if (result.type === "symbol") {
      const sym = architecture?.symbols.find((s) => s.id === result.id);
      if (sym) {
        showDetail("symbol", sym);
      } else if (result.componentId) {
        // Split-mode symbol found via the shard index before its component was
        // opened: navigate to the owning component, then once its detail fetch
        // resolves, re-resolve the symbol from the loaded detail and open it
        // (O3). navigateToComponent is synchronous; the detail load is not, so
        // the symbol open has to happen in a follow-up once loadComponentDetail
        // settles. Guarded against the user navigating elsewhere in the
        // meantime, so a slow fetch cannot pop open a stale symbol over
        // whatever the user is looking at by the time it resolves.
        const targetComponentId = result.componentId;
        const targetSymbolId = result.id;
        navigateToComponent(targetComponentId);
        void loadComponentDetail(targetComponentId).then(() => {
          if (useArchStore.getState().selectedComponentId !== targetComponentId) {
            return;
          }
          const match = getComponentSymbols(targetComponentId).find(
            (s) => s.id === targetSymbolId,
          );
          if (match) {
            showDetail("symbol", match);
          }
        });
      }
    }
    setSearchOpen(false);
  };

  // Make a selection set from the current results (P6-9). Closes search and opens
  // the review panel so the new set is immediately visible to annotate/export.
  const handleMakeSet = () => {
    if (results.length === 0 || !searchQuery) return;
    createSetFromSearchResults(searchQuery, results);
    setSearchOpen(false);
    setActivePanel("review");
  };

  if (!searchOpen) return null;

  const kindIcons: Record<string, string> = {
    component: "\u25A0",
    file: "\u25CB",
    symbol: "\u25C6",
  };

  return (
    // The identity attributes below are the crawl's contract with search
    // (viewer/tests/crawl/). Search is the one navigation path nothing proved
    // end to end: the linter shows every index entry resolves in the DATA, and
    // nothing showed that picking a result lands you on it in the UI.
    <div
      data-testid="search-overlay"
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
      onClick={() => setSearchOpen(false)}
    >
      {/* Backdrop */}
      <div className={`absolute inset-0 ${darkMode ? "bg-black/60" : "bg-black/30"} backdrop-blur-sm`} />

      {/* Search panel */}
      <div
        className={`
          relative w-full max-w-lg mx-4 rounded-2xl shadow-2xl overflow-hidden
          ${darkMode ? "bg-zinc-900 border border-zinc-800" : "bg-white border border-zinc-200"}
        `}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Input */}
        <div className={`flex items-center gap-3 px-4 py-3 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <span className={darkMode ? "text-zinc-500" : "text-zinc-400"}>&#x1F50D;</span>
          <input
            ref={inputRef}
            data-testid="search-input"
            type="text"
            placeholder="Search components, files, symbols..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
            className={`
              min-h-11 flex-1 bg-transparent text-base outline-none sm:min-h-0
              ${darkMode ? "text-zinc-200 placeholder-zinc-600" : "text-zinc-800 placeholder-zinc-400"}
            `}
          />
          <kbd className={`text-[10px] px-1.5 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-500" : "bg-zinc-100 text-zinc-400"}`}>
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-[50vh] overflow-y-auto">
          {results.length > 0 ? (
            <div className="py-2">
              {results.map((result, i) => (
                <button
                  key={`${result.type}-${result.id}`}
                  data-testid="search-result"
                  data-result-kind={result.type}
                  data-result-id={result.id}
                  data-result-component={result.componentId}
                  data-result-index={i}
                  className={`
                    w-full flex items-center gap-3 px-4 py-2.5 text-left
                    ${i === selectedIndex
                      ? darkMode
                        ? "bg-blue-500/15 text-blue-300"
                        : "bg-blue-50 text-blue-700"
                      : darkMode
                        ? "hover:bg-zinc-800/50"
                        : "hover:bg-zinc-50"
                    }
                  `}
                  onClick={() => handleSelect(result)}
                  onMouseEnter={() => setSelectedIndex(i)}
                >
                  {/* Type icon */}
                  <span className={`text-xs shrink-0 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                    {kindIcons[result.type] || "\u25CB"}
                  </span>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className={`text-sm font-medium truncate ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                      {result.name}
                    </div>
                    <div className={`text-xs truncate ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                      {result.path}
                    </div>
                  </div>

                  {/* Badges */}
                  <div className="flex items-center gap-2 shrink-0">
                    {result.language && (
                      <span
                        className="w-2 h-2 rounded-full"
                        style={{ backgroundColor: getLanguageColor(result.language) }}
                      />
                    )}
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-500" : "bg-zinc-100 text-zinc-500"}`}>
                      {result.kind}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          ) : searchQuery ? (
            <div
              data-testid="search-no-results"
              className={`py-8 text-center text-sm ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}
            >
              No results for "{searchQuery}"
            </div>
          ) : (
            <div className={`py-8 text-center text-sm ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
              Start typing to search...
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={`
          flex items-center justify-between px-4 py-2 text-[10px] border-t
          ${darkMode ? "border-zinc-800 text-zinc-600" : "border-zinc-200 text-zinc-400"}
        `}>
          <div className="flex gap-3">
            <span><kbd className={`px-1 rounded ${darkMode ? "bg-zinc-800" : "bg-zinc-100"}`}>&uarr;&darr;</kbd> Navigate</span>
            <span><kbd className={`px-1 rounded ${darkMode ? "bg-zinc-800" : "bg-zinc-100"}`}>Enter</kbd> Select</span>
          </div>
          <div className="flex items-center gap-3">
            {shardsPending && (
              <span
                className={
                  shardLoadState === "failed"
                    ? darkMode ? "text-amber-500/80" : "text-amber-600"
                    : darkMode ? "text-zinc-500" : "text-zinc-400"
                }
                title={
                  shardLoadState === "failed"
                    ? "Some search shards failed to load; results may be incomplete."
                    : "Still loading the full search index; results may be incomplete."
                }
              >
                {shardLoadState === "loading" ? "Indexing…" : "Index incomplete"}
              </span>
            )}
            {results.length > 0 && (
              <button
                onClick={handleMakeSet}
                className={`text-[10px] px-2 py-0.5 rounded font-medium ${darkMode ? "bg-blue-600/80 text-white hover:bg-blue-500" : "bg-blue-500 text-white hover:bg-blue-600"}`}
                title="Create a selection set from these results"
              >
                Make set from {results.length} result{results.length !== 1 ? "s" : ""}
              </button>
            )}
            <span>{results.length} result{results.length !== 1 ? "s" : ""}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
