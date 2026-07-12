import Fuse from "fuse.js";
import type { Architecture, Component, FileInfo, Symbol } from "../types";

export interface SearchResult {
  type: "component" | "file" | "symbol";
  id: string;
  name: string;
  path: string;
  kind: string;
  language?: string;
  componentId?: string;
  score: number;
}

const FUSE_OPTIONS = {
  keys: [
    { name: "name", weight: 3 },
    { name: "path", weight: 1 },
    { name: "kind", weight: 0.5 },
  ],
  threshold: 0.4,
  includeScore: true,
  minMatchCharLength: 2,
};

let componentFuse: Fuse<SearchResult> | null = null;
// Entries from the manifest (components, plus files/symbols in monolithic mode).
// Rebuilt wholesale on every initializeSearch.
let baseResults: SearchResult[] = [];
// Entries added lazily from split-mode detail loads, keyed by component id so a
// live refresh can preserve them. A re-load of the same component replaces its
// entries rather than duplicating them (F-VW-3).
const detailResultsByComponent = new Map<string, SearchResult[]>();
// Flat view rebuilt from baseResults + all detail entries; kept for search().
let allResults: SearchResult[] = [];

function rebuildFuse() {
  allResults = [...baseResults];
  for (const entries of detailResultsByComponent.values()) {
    allResults.push(...entries);
  }
  componentFuse = new Fuse(allResults, FUSE_OPTIONS);
}

function fileResult(file: FileInfo): SearchResult {
  const name = file.path.split("/").pop() || file.path;
  return {
    type: "file",
    id: file.path,
    name,
    path: file.path,
    kind: file.language,
    language: file.language,
    score: 0,
  };
}

function symbolResult(sym: Symbol): SearchResult {
  return {
    type: "symbol",
    id: sym.id,
    name: sym.name,
    path: sym.file,
    kind: sym.kind,
    score: 0,
  };
}

export function initializeSearch(arch: Architecture) {
  baseResults = [];

  // Index components
  function indexComponents(components: Component[]) {
    for (const comp of components) {
      baseResults.push({
        type: "component",
        id: comp.id,
        name: comp.name,
        path: comp.path,
        kind: comp.type,
        language: comp.language || undefined,
        score: 0,
      });
      indexComponents(comp.children);
    }
  }
  indexComponents(arch.components);

  // Index files
  for (const file of arch.files) {
    baseResults.push(fileResult(file));
  }

  // Index symbols
  for (const sym of arch.symbols) {
    baseResults.push(symbolResult(sym));
  }

  // Rebuild preserving any detail-derived entries so a live manifest refresh
  // does not drop symbols/files added via split-mode detail loads (F-VW-3).
  rebuildFuse();
}

/**
 * Add lazily loaded (split-mode) files and symbols to the search index. When a
 * componentId is provided the entries are keyed by it, so re-loading the same
 * component replaces its prior entries and a live refresh can preserve them.
 */
export function addToSearchIndex(
  symbols: Symbol[],
  files: FileInfo[],
  componentId?: string,
) {
  const entries: SearchResult[] = [
    ...files.map(fileResult),
    ...symbols.map(symbolResult),
  ];
  // Key by component when known; otherwise use a stable synthetic key so
  // repeated anonymous adds accumulate instead of overwriting.
  const key = componentId ?? `__anon_${detailResultsByComponent.size}`;
  detailResultsByComponent.set(key, entries);
  rebuildFuse();
}

/**
 * Drop all detail-derived entries. Not called on live refresh (those entries
 * are preserved), but available for a full reset if a genuinely different
 * dataset is loaded.
 */
export function resetDetailSearchEntries() {
  detailResultsByComponent.clear();
  rebuildFuse();
}

export function search(query: string, limit: number = 50): SearchResult[] {
  if (!componentFuse || !query.trim()) return [];

  return componentFuse
    .search(query)
    .slice(0, limit)
    .map((r) => ({
      ...r.item,
      score: r.score ?? 0,
    }));
}
