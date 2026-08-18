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
  // Free text (descriptions, module docs, docstrings, AI help text) merged in
  // from the prebuilt search shards (P6-4). Searchable but not always displayed.
  text?: string;
  score: number;
}

// One prebuilt search-shard entry (analyzer/project/search_shards.py). Emitted
// since P4-5, consumed here in P6-4 so search covers descriptions, docstrings,
// and AI help text without the viewer having to visit every component.
export interface ShardEntry {
  ref_kind: "component" | "file" | "symbol" | "enrichment";
  ref_id: string;
  name: string;
  path: string;
  component: string;
  text: string;
}

const FUSE_OPTIONS = {
  keys: [
    { name: "name", weight: 3 },
    { name: "path", weight: 1 },
    { name: "kind", weight: 0.5 },
    // Descriptions, docstrings, and AI help text from the shards (P6-4). Weighted
    // low so an identifier match still wins, but present so a plain-language
    // query finds a component by what it does, not just its name.
    { name: "text", weight: 0.7 },
  ],
  threshold: 0.4,
  includeScore: true,
  minMatchCharLength: 2,
  // Match a query anywhere in a field rather than near its start. Without this,
  // Fuse's location/distance scoring buries a word that appears deep in a long
  // description, docstring, or help-text field, defeating shard search (P6-4).
  ignoreLocation: true,
};

let componentFuse: Fuse<SearchResult> | null = null;
// Entries from the manifest (components, plus files/symbols in monolithic mode).
// Rebuilt wholesale on every initializeSearch.
let baseResults: SearchResult[] = [];
// Entries added lazily from split-mode detail loads, keyed by component id so a
// live refresh can preserve them. A re-load of the same component replaces its
// entries rather than duplicating them (F-VW-3).
const detailResultsByComponent = new Map<string, SearchResult[]>();
// Entries merged from the prebuilt search shards (P6-4). Loaded once, lazily.
let shardResults: SearchResult[] = [];
let shardsLoadStarted = false;
// Flat view rebuilt from baseResults + detail entries + shard entries.
let allResults: SearchResult[] = [];

// Merge all sources into one deduplicated, Fuse-indexed list. Entries are keyed
// by `${type}:${id}`; when a shard entry and a base entry share a key the base
// metadata (kind/language) is preserved and the shard's free text is folded in,
// so a component gains searchable description/help text without losing its type
// badge (P6-4).
function rebuildFuse() {
  const byKey = new Map<string, SearchResult>();
  const put = (r: SearchResult, mergeText: boolean) => {
    const key = `${r.type}:${r.id}`;
    const existing = byKey.get(key);
    if (!existing) {
      byKey.set(key, { ...r });
      return;
    }
    byKey.set(key, {
      ...existing,
      name: existing.name || r.name,
      path: existing.path || r.path,
      kind: existing.kind || r.kind,
      language: existing.language ?? r.language,
      componentId: existing.componentId ?? r.componentId,
      text: mergeText
        ? [existing.text, r.text].filter(Boolean).join(" ") || undefined
        : (existing.text ?? r.text),
    });
  };

  for (const r of baseResults) put(r, false);
  for (const entries of detailResultsByComponent.values()) {
    for (const r of entries) put(r, false);
  }
  for (const r of shardResults) put(r, true);

  allResults = [...byKey.values()];
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
  // Shard entries belong to the dataset, not the session: a live manifest
  // refresh must drop stale shard text and allow the (possibly updated) shard
  // set to be fetched again. Detail-derived entries are preserved separately.
  shardResults = [];
  shardsLoadStarted = false;

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
        // Seed description text so search covers it even before shards load,
        // plus the component's API endpoints and env vars: those were absent
        // from every index, so "/ws/audio" and a config-variable name found
        // nothing relevant (comprehension-study S7).
        text: [
          comp.description || comp.docs?.purpose || "",
          ...(comp.docs?.api_endpoints || []).map((e) => `${e.method} ${e.path}`),
          ...(comp.docs?.env_vars || []),
        ]
          .filter(Boolean)
          .join(" ") || undefined,
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

  // Rebuild preserving any detail-derived and shard entries so a live manifest
  // refresh does not drop symbols/files added via split-mode detail loads or the
  // shard index (F-VW-3, P6-4).
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

// Map a shard entry to a canonical search result. Enrichment entries carry a
// `ref_id` of the form `<kind>:<id>` (e.g. `component:viewer/src`) that resolves
// to the enriched element, so its help text merges onto that element's entry.
function shardEntryToResult(e: ShardEntry): SearchResult {
  let type: SearchResult["type"] = "component";
  let id = e.ref_id;
  if (e.ref_kind === "file") {
    type = "file";
  } else if (e.ref_kind === "symbol") {
    type = "symbol";
  } else if (e.ref_kind === "enrichment") {
    const idx = e.ref_id.indexOf(":");
    const k = idx >= 0 ? e.ref_id.slice(0, idx) : "component";
    id = idx >= 0 ? e.ref_id.slice(idx + 1) : e.ref_id;
    type = k === "file" ? "file" : k === "symbol" ? "symbol" : "component";
  }
  return {
    type,
    id,
    name: e.name,
    path: e.path,
    kind: type,
    componentId: e.component || undefined,
    text: e.text || undefined,
    score: 0,
  };
}

/**
 * Merge prebuilt search-shard entries into the index (P6-4). Called by
 * loadSearchShards; exported so the merge is unit-testable in isolation.
 */
export function addShardEntries(entries: ShardEntry[]) {
  shardResults = [...shardResults, ...entries.map(shardEntryToResult)];
  rebuildFuse();
}

/** Drop all shard-derived entries (test/reset helper). */
export function resetShardSearchEntries() {
  shardResults = [];
  shardsLoadStarted = false;
  rebuildFuse();
}

/**
 * Lazily load the prebuilt search shards and merge them into the index (P6-4).
 * Idempotent (loads once per session). Degrades silently when no shards exist
 * (monolithic or pre-v2 datasets), so this is safe to call unconditionally.
 */
export async function loadSearchShards(baseUrl = "./architecture/search"): Promise<void> {
  if (shardsLoadStarted) return;
  shardsLoadStarted = true;
  try {
    const manifestRes = await fetch(`${baseUrl}/manifest.json`);
    const isJson = manifestRes.ok && (manifestRes.headers.get("content-type")?.includes("json") ?? false);
    if (!isJson) return;
    const manifest = await manifestRes.json();
    const shardNames: string[] = Array.isArray(manifest?.shards) ? manifest.shards : [];
    const collected: ShardEntry[] = [];
    for (const name of shardNames) {
      const res = await fetch(`${baseUrl}/${name}`);
      if (!res.ok) continue;
      const data = await res.json();
      if (Array.isArray(data)) collected.push(...(data as ShardEntry[]));
    }
    if (collected.length > 0) addShardEntries(collected);
  } catch {
    // Best-effort: a missing shard set is not an error (monolith / old data).
  }
}

// Relevance gate (comprehension-study S7). `ignoreLocation` lets Fuse's Bitap
// find a short query's letters scattered anywhere in a long field, and it
// scores those hits as near-perfect: "billing", absent from the codebase,
// matched "KBLinguisticMatcher" at 0.007. Score cannot separate that from a
// real match, so admission is decided by literal containment instead and Fuse
// is kept for RANKING only. A single word must appear as a substring; a
// multi-word query must have every word present. "No results" is a correct,
// honest answer, and substring matching is what someone typing an identifier
// or a path already expects.
function matchesLiterally(item: SearchResult, query: string): boolean {
  const haystack = [item.name, item.path, item.kind, item.text]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  const needle = query.toLowerCase().trim();
  if (haystack.includes(needle)) return true;
  const tokens = needle.split(/[^a-z0-9_./-]+/).filter(Boolean);
  return tokens.length > 1 && tokens.every((t) => haystack.includes(t));
}

export function search(query: string, limit: number = 50): SearchResult[] {
  const q = query.trim();
  if (!componentFuse || !q) return [];

  return componentFuse
    .search(q)
    .filter((r) => matchesLiterally(r.item, q))
    .slice(0, limit)
    .map((r) => ({
      ...r.item,
      score: r.score ?? 0,
    }));
}
