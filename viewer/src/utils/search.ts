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

// The documents in index order, and each one's lowercase haystack (name,
// path, kind, text). Admission is decided by literal containment over the
// haystack (matchesLiterally); Fuse ranks only what was admitted.
//
// Load bearing on a large subject (GUI crawl 2026-09-02, search.slow_input).
// One Fuse search over the whole index ran Bitap across every character of
// every field of 167,479 documents (20 MB of indexed text) on each keystroke:
// 1.6 to 4.9 s per query on VS Code, all of it inside React's input flush, so
// the box would not accept the next character. The literal scan the relevance
// gate already performs (S7) costs 12 ms over the same data when the haystack
// is precomputed once at index time, and ranking a bounded candidate set
// costs 1 ms. Measured in Node against the served shards; see
// docs/testing/RUN-2026-09-02-vscode-demo-gate.md.
let indexedDocs: SearchResult[] = [];
let indexedHaystacks: string[] = [];
let indexBuilt = false;
// How many admitted documents are handed to Fuse for ranking. Beyond this a
// query is too broad for ranking to matter, and Fuse over tens of thousands of
// documents is the stall this replaces. Index order puts components first, so
// the cap keeps the identities a reader most likely meant.
const RANK_CANDIDATE_CAP = 2000;
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
// The merged, deduplicated entries currently in the Fuse index, keyed by
// `${type}:${id}` and held in index order. Kept across incremental additions so
// a detail load can append the handful of documents it brings instead of
// rebuilding the whole index (see addToSearchIndex).
let entryByKey = new Map<string, SearchResult>();

// How many shard requests loadSearchShards keeps in flight at once. Bounded
// rather than unbounded: firing all ~85 requests at once risks connection-pool
// exhaustion (HTTP/1.1 browsers cap at ~6 connections per origin) and can end
// up slower than a small pool. 6 fully uses that per-origin limit without
// queuing overhead, and stays comfortably safe under HTTP/2 multiplexing too.
const SHARD_FETCH_CONCURRENCY = 6;

// Whether the background shard load (loadSearchShards) is in progress, done,
// or has failed outright. Exposed so SearchOverlay can tell the user results
// may be incomplete instead of presenting a partially-loaded index as final
// (comprehension-study: "trustworthy map" is the product's central claim).
// Plain module state + pub/sub, matching the rest of this file's style (no
// React import here); the component subscribes and mirrors it into useState.
/**
 * State of the background search-shard load.
 *
 * "partial" means some shards loaded and at least one did not, so the index is
 * usable but genuinely incomplete. It is distinct from "failed", where nothing
 * loaded at all. Both must be surfaced: presenting an incomplete index as
 * complete is the defect this state exists to prevent.
 */
export type ShardLoadState = "idle" | "loading" | "loaded" | "partial" | "failed";
let shardLoadState: ShardLoadState = "idle";
const shardLoadListeners = new Set<(state: ShardLoadState) => void>();

function setShardLoadState(next: ShardLoadState) {
  shardLoadState = next;
  for (const listener of shardLoadListeners) listener(next);
}

/** Current state of the background shard load. See ShardLoadState. */
export function getShardLoadState(): ShardLoadState {
  return shardLoadState;
}

/** Subscribe to shard-load state changes. Returns an unsubscribe function. */
export function subscribeShardLoadState(
  listener: (state: ShardLoadState) => void,
): () => void {
  shardLoadListeners.add(listener);
  return () => {
    shardLoadListeners.delete(listener);
  };
}

// Merge all sources into one deduplicated, Fuse-indexed list. Entries are keyed
// by `${type}:${id}`; when a shard entry and a base entry share a key the base
// metadata (kind/language) is preserved and the shard's free text is folded in,
// so a component gains searchable description/help text without losing its type
// badge (P6-4).
/**
 * How many times the index has been rebuilt.
 *
 * Load bearing, and the fix for a real defect. The search index is module state
 * that GROWS as shards stream in, and SearchOverlay memoised its results on the
 * query alone. So a query typed before the shards landed was answered once,
 * against a partial index, and never recomputed. Components and files were
 * unaffected because they come from the manifest and are indexed at boot; all
 * 153,231 private large-repository validation corpus symbols live only in the shards, so symbol search returned
 * "No results" permanently.
 *
 * It was invisible on a small subject, where the shards land in milliseconds.
 * On a 60 MB index it made 91% of the index unreachable.
 */
let indexVersion = 0;
const indexListeners = new Set<(version: number) => void>();

/** The current index generation. Changes whenever entries are added. */
export function getSearchIndexVersion(): number {
  return indexVersion;
}

/** Subscribe to index changes. Returns an unsubscribe function. */
export function subscribeSearchIndex(listener: (version: number) => void): () => void {
  indexListeners.add(listener);
  return () => {
    indexListeners.delete(listener);
  };
}

function bumpIndexVersion() {
  indexVersion += 1;
  for (const listener of indexListeners) listener(indexVersion);
}

/**
 * How many times the whole Fuse index has been built from scratch.
 *
 * Test-only observability. Every split-mode detail load used to rebuild the
 * index wholesale, so opening forty components tokenised the entire corpus
 * forty times and the page stalled long enough for a search pick to time out.
 * The bound is asserted in searchShards.test.ts; without a counter the
 * difference between "incremental" and "still rebuilding, just faster" is not
 * observable from outside.
 */
let fullRebuildCount = 0;

/** Test hook: number of full index rebuilds since load. See fullRebuildCount. */
export function getSearchIndexRebuildCount(): number {
  return fullRebuildCount;
}

// Merge a lower-priority entry into one already claimed for the same key. The
// first writer wins every field it actually has; a later entry only fills gaps.
// Shard entries additionally concatenate their free text, because that text is
// the whole reason the shards exist (P6-4).
function mergeEntry(
  existing: SearchResult,
  r: SearchResult,
  mergeText: boolean,
): SearchResult {
  return {
    ...existing,
    name: existing.name || r.name,
    path: existing.path || r.path,
    kind: existing.kind || r.kind,
    language: existing.language ?? r.language,
    componentId: existing.componentId ?? r.componentId,
    text: mergeText
      ? [existing.text, r.text].filter(Boolean).join(" ") || undefined
      : (existing.text ?? r.text),
  };
}

// Whether two entries carry the same searchable and displayed content. Used to
// decide when an addition genuinely changes the index and when it is a repeat.
function sameEntry(a: SearchResult, b: SearchResult): boolean {
  return (
    a.type === b.type &&
    a.id === b.id &&
    a.name === b.name &&
    a.path === b.path &&
    a.kind === b.kind &&
    a.language === b.language &&
    a.componentId === b.componentId &&
    a.text === b.text
  );
}

function sameEntries(a: SearchResult[], b: SearchResult[]): boolean {
  return a.length === b.length && a.every((entry, i) => sameEntry(entry, b[i]));
}

// Whether two entries read the same to search: the fields in the haystack and
// the Fuse keys. `language` and `componentId` are neither, so an entry that
// only fills those in (a shard file entry carries no language; the detail
// entry for the same file does) can be patched in place instead of forcing a
// full rebuild, which is what every first landing on VS Code paid for.
function sameSearchable(a: SearchResult, b: SearchResult): boolean {
  return (
    a.type === b.type &&
    a.id === b.id &&
    a.name === b.name &&
    a.path === b.path &&
    a.kind === b.kind &&
    a.text === b.text
  );
}

function haystackOf(item: SearchResult): string {
  return [item.name, item.path, item.kind, item.text]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function rebuildFuse() {
  const byKey = new Map<string, SearchResult>();
  const put = (r: SearchResult, mergeText: boolean) => {
    const key = `${r.type}:${r.id}`;
    const existing = byKey.get(key);
    if (!existing) {
      byKey.set(key, { ...r });
      return;
    }
    byKey.set(key, mergeEntry(existing, r, mergeText));
  };

  for (const r of baseResults) put(r, false);
  for (const entries of detailResultsByComponent.values()) {
    for (const r of entries) put(r, false);
  }
  for (const r of shardResults) put(r, true);

  entryByKey = byKey;
  indexedDocs = [...byKey.values()];
  indexedHaystacks = indexedDocs.map(haystackOf);
  indexBuilt = true;
  fullRebuildCount += 1;
  bumpIndexVersion();
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
  setShardLoadState("idle");

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
 *
 * Incremental. This runs once per detail shard, so a reader who opens forty
 * components pays for it forty times; a full rebuild each time tokenises every
 * document already indexed and, on a large subject, stalls the page long enough
 * that a search pick times out. New documents are appended to the live Fuse
 * index instead. Three cases still fall back to a full rebuild, all rare and
 * all cases where appending would be wrong:
 *
 *   - nothing has been indexed yet (no index to append to),
 *   - a component that was already loaded comes back with different entries,
 *     so its previous documents must be dropped rather than added to,
 *   - an incoming entry would change a document already in the index, and Fuse
 *     has no in-place update.
 *
 * Appending preserves the index version contract (issue #116): the version is
 * bumped whenever documents are actually added, so SearchOverlay's memo
 * recomputes and a query typed before the entries landed sees them. A repeat
 * load that adds nothing bumps nothing, because nothing changed.
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
  const previous = detailResultsByComponent.get(key);
  detailResultsByComponent.set(key, entries);

  if (!indexBuilt) {
    rebuildFuse();
    return;
  }
  if (previous) {
    // The same component again. Identical entries are the common case (a shard
    // loaded twice) and must not duplicate anything, so there is nothing to do.
    // Different entries mean the old ones have to go, which only a rebuild does.
    if (sameEntries(previous, entries)) return;
    rebuildFuse();
    return;
  }

  const added: SearchResult[] = [];
  for (const r of entries) {
    const entryKey = `${r.type}:${r.id}`;
    const existing = entryByKey.get(entryKey);
    if (!existing) {
      const doc = { ...r };
      entryByKey.set(entryKey, doc);
      added.push(doc);
      continue;
    }
    const merged = mergeEntry(existing, r, false);
    if (!sameSearchable(existing, merged)) {
      rebuildFuse();
      return;
    }
    // Only the non-searchable fields changed (or nothing did): fill them in
    // place. The document object is shared with indexedDocs, so the index
    // sees the change without a rebuild, and the version is unaffected
    // because nothing a query can match has changed.
    existing.language = merged.language;
    existing.componentId = merged.componentId;
  }

  if (added.length === 0) return;
  for (const doc of added) {
    indexedDocs.push(doc);
    indexedHaystacks.push(haystackOf(doc));
  }
  bumpIndexVersion();
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
  setShardLoadState("idle");
  rebuildFuse();
}

/**
 * Lazily load the prebuilt search shards and merge them into the index (P6-4).
 * Idempotent (loads once per session). Degrades silently when no shards exist
 * (monolithic or pre-v2 datasets), so this is safe to call unconditionally.
 *
 * Shards are fetched with bounded concurrency (SHARD_FETCH_CONCURRENCY workers
 * pulling from a shared index cursor) rather than sequentially: over a real
 * network the per-request round trip, not bandwidth, dominates load time for a
 * large shard set. Results are written into a slot pre-assigned by each
 * shard's position in the manifest, so the entries handed to addShardEntries
 * are always assembled in shard-manifest order regardless of which fetch
 * finishes first. That determinism matters: Fuse ranking / tie-breaking can
 * depend on stable input order, and a nondeterministic index would make
 * results and tests flaky.
 */
export async function loadSearchShards(baseUrl = "./architecture/search"): Promise<void> {
  if (shardsLoadStarted) return;
  shardsLoadStarted = true;
  setShardLoadState("loading");
  try {
    const manifestRes = await fetch(`${baseUrl}/manifest.json`);
    const isJson = manifestRes.ok && (manifestRes.headers.get("content-type")?.includes("json") ?? false);
    if (!isJson) {
      // No shard set for this dataset (monolith / pre-v2). Nothing to load,
      // so the index is already complete: not a failure state.
      setShardLoadState("loaded");
      return;
    }
    const manifest = await manifestRes.json();
    const shardNames: string[] = Array.isArray(manifest?.shards) ? manifest.shards : [];

    // Slot per shard index, filled out of order, read back in order.
    const bySlot: ShardEntry[][] = new Array(shardNames.length);
    let nextIndex = 0;
    let missed = 0;
    const runWorker = async () => {
      while (nextIndex < shardNames.length) {
        const i = nextIndex++;
        const name = shardNames[i];
        // One bad shard costs one shard. Letting it throw here would reject
        // Promise.all and discard every sibling that loaded fine, so a single
        // 404 or a single malformed file would lose the whole index instead of
        // a fraction of it.
        try {
          const res = await fetch(`${baseUrl}/${name}`);
          if (!res.ok) {
            missed++;
            continue;
          }
          const data = await res.json();
          if (Array.isArray(data)) bySlot[i] = data as ShardEntry[];
          else missed++;
        } catch {
          missed++;
        }
      }
    };
    const workerCount = Math.min(SHARD_FETCH_CONCURRENCY, shardNames.length);
    await Promise.all(Array.from({ length: workerCount }, runWorker));

    const collected: ShardEntry[] = ([] as ShardEntry[]).concat(...bySlot.filter(Boolean));
    if (collected.length > 0) addShardEntries(collected);
    // A shard we could not read is missing content, so the index is genuinely
    // incomplete and must not be reported as complete. Partial and total loss
    // are distinguished because they are different facts, though both tell the
    // user the same thing.
    if (missed === 0) setShardLoadState("loaded");
    else if (collected.length > 0) setShardLoadState("partial");
    else setShardLoadState("failed");
  } catch {
    // Best-effort: a missing shard set is not an error (monolith / old data),
    // but a genuine failure here (network error, malformed manifest/shard
    // JSON) must not be reported as a complete index, so it's flagged
    // distinctly from "loaded" for the UI to surface.
    setShardLoadState("failed");
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
function matchesLiterally(haystack: string, needle: string, tokens: string[]): boolean {
  if (haystack.includes(needle)) return true;
  return tokens.length > 1 && tokens.every((t) => haystack.includes(t));
}

export function search(query: string, limit: number = 50): SearchResult[] {
  const q = query.trim();
  if (!indexBuilt || !q) return [];

  const needle = q.toLowerCase();
  const tokens = needle.split(/[^a-z0-9_./-]+/).filter(Boolean);
  const candidates: SearchResult[] = [];
  for (let i = 0; i < indexedDocs.length; i++) {
    if (!matchesLiterally(indexedHaystacks[i], needle, tokens)) continue;
    candidates.push(indexedDocs[i]);
    if (candidates.length >= RANK_CANDIDATE_CAP) break;
  }
  if (candidates.length === 0) return [];

  return new Fuse(candidates, FUSE_OPTIONS)
    .search(q)
    .slice(0, limit)
    .map((r) => ({
      ...r.item,
      score: r.score ?? 0,
    }));
}
