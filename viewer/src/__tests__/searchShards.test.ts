import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  initializeSearch,
  addShardEntries,
  search,
  resetDetailSearchEntries,
  resetShardSearchEntries,
  loadSearchShards,
  getShardLoadState,
  subscribeShardLoadState,
  addToSearchIndex,
  getSearchIndexRebuildCount,
  getSearchIndexVersion,
  subscribeSearchIndex,
  type ShardEntry,
} from "../utils/search";
import type { Architecture, Component, FileInfo, Symbol } from "../types";

// P6-4: the viewer consumes the prebuilt search shards so search covers
// descriptions, docstrings, and AI help text, and split-mode symbols are
// findable before their component is opened.
//
// Fail-before / construction proof: with only the in-browser base index (no
// shard merge), a query for a word that lives only in a docstring, an AI help
// text, or a split-mode symbol returns nothing. This test first asserts exactly
// that, then asserts the shard merge makes those queries resolve. Reverting
// addShardEntries to a no-op fails every post-merge assertion.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "auth-svc", name: "Auth Service", type: "service", path: "src/auth",
    language: "typescript", framework: null, description: null, port: null,
    children: [], files: ["src/auth/token.ts"], entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { typescript: 100 } },
    docs: {
      readme: null, claude_md: null, changelog: null, api_docs: null,
      architecture_notes: null, purpose: null, key_decisions: [], patterns: [],
      tech_stack: [], env_vars: [], api_endpoints: [],
    },
    ...overrides,
  };
}

// Split mode: the monolith has NO files/symbols, so the base index only knows
// the component's name and type.
function makeSplitArchitecture(): Architecture {
  return {
    name: "T", description: "", repository: null,
    generated_at: "2025-01-01T00:00:00Z", analyzer_version: "1.2.0", root_path: "/t",
    components: [makeComponent()], relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
  };
}

const shardEntries: ShardEntry[] = [
  { ref_kind: "component", ref_id: "auth-svc", name: "Auth Service", path: "src/auth", component: "auth-svc", text: "Handles user authentication and token issuance" },
  { ref_kind: "enrichment", ref_id: "component:auth-svc", name: "Auth Service", path: "src/auth", component: "auth-svc", text: "Validates credentials against the ldap directory" },
  { ref_kind: "symbol", ref_id: "sym:src/auth/token.ts:issueToken:10", name: "issueToken", path: "src/auth/token.ts", component: "auth-svc", text: "Issues a signed jwt token" },
  { ref_kind: "file", ref_id: "src/auth/token.ts", name: "token.ts", path: "src/auth/token.ts", component: "auth-svc", text: "Token utility helpers" },
];

const ids = (q: string) => search(q).map((r) => r.id);

describe("shard-backed search (P6-4)", () => {
  beforeEach(() => {
    resetShardSearchEntries();
    resetDetailSearchEntries();
    initializeSearch(makeSplitArchitecture());
  });

  it("cannot find description, docstring, help text, or split symbols before shards load", () => {
    // Base index knows the component name only.
    expect(ids("Auth")).toContain("auth-svc");
    // These words live only in shard text / are split-mode-only:
    expect(ids("authentication")).not.toContain("auth-svc");
    expect(ids("ldap")).toHaveLength(0);
    expect(ids("issueToken")).toHaveLength(0);
    expect(ids("jwt")).toHaveLength(0);
  });

  it("finds a component by its description once shards are merged", () => {
    addShardEntries(shardEntries);
    expect(ids("authentication")).toContain("auth-svc");
  });

  it("finds a component by its AI help text (enrichment channel)", () => {
    addShardEntries(shardEntries);
    expect(ids("ldap")).toContain("auth-svc");
  });

  it("finds a split-mode symbol by name and docstring before its component is opened", () => {
    addShardEntries(shardEntries);
    const byName = search("issueToken");
    expect(byName.map((r) => r.id)).toContain("sym:src/auth/token.ts:issueToken:10");
    // Carries the owning component so selection can navigate there.
    const hit = byName.find((r) => r.id === "sym:src/auth/token.ts:issueToken:10");
    expect(hit?.componentId).toBe("auth-svc");
    // Also findable by a docstring word.
    expect(ids("jwt")).toContain("sym:src/auth/token.ts:issueToken:10");
  });

  it("merges shard text onto the base entry without duplicating it or losing the type badge", () => {
    addShardEntries(shardEntries);
    const results = search("Auth");
    const compHits = results.filter((r) => r.id === "auth-svc");
    // One merged entry, not one base + one shard duplicate.
    expect(compHits).toHaveLength(1);
    // The base component type is preserved for the badge, not overwritten by the
    // generic shard "component" kind.
    expect(compHits[0].kind).toBe("service");
  });
});

// loadSearchShards: bounded-concurrency fetch + the loading-state signal
// (viewer fix). Sequential per-shard `await` in a `for` loop made the shard
// set load in a time proportional to round trips × shard count over a real
// network; these tests cover the parallel fetch (assembly order must stay
// deterministic regardless of completion order) and the loading indicator
// that keeps the UI from presenting a still-filling index as complete.
describe("loadSearchShards: bounded-parallel fetch and loading state", () => {
  beforeEach(() => {
    resetShardSearchEntries();
    resetDetailSearchEntries();
    initializeSearch(makeSplitArchitecture());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function manifestResponse(shards: string[]) {
    return {
      ok: true,
      headers: { get: (h: string) => (h.toLowerCase() === "content-type" ? "application/json" : null) },
      json: async () => ({ shards }),
    };
  }

  it("fetches shards in parallel yet assembles entries in shard-manifest order, not completion order", async () => {
    const shardNames = Array.from({ length: 8 }, (_, i) => `shard-${i}.json`);

    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("manifest.json")) return Promise.resolve(manifestResponse(shardNames));
      const i = shardNames.findIndex((n) => url.endsWith(n));
      const entry: ShardEntry = {
        ref_kind: "component",
        ref_id: `s${i}`,
        // Identical searchable fields across every shard: any two entries
        // score identically, so a stable result order proves assembly order,
        // not an artifact of one entry outscoring another.
        name: "ShardMatch",
        path: "p",
        component: "c",
        text: "",
      };
      // Later-indexed shards resolve first (inverted delay), so completion
      // order is the reverse of manifest order.
      const delayMs = (shardNames.length - i) * 3;
      return new Promise((resolve) => {
        setTimeout(() => resolve({ ok: true, json: async () => [entry] }), delayMs);
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    await loadSearchShards();

    // All 8 shard requests were issued (bounded concurrency still reaches
    // every shard), and results are assembled in shard-manifest order.
    const shardFetchCalls = fetchMock.mock.calls.filter(([url]) => !String(url).endsWith("manifest.json"));
    expect(shardFetchCalls).toHaveLength(8);
    const ids = search("ShardMatch").map((r) => r.id);
    expect(ids).toEqual(shardNames.map((_, i) => `s${i}`));
  });

  it("reports loading while the fetch is in flight and loaded once it settles, notifying subscribers", async () => {
    expect(getShardLoadState()).toBe("idle");

    let releaseManifest!: (value: unknown) => void;
    const manifestPromise = new Promise((resolve) => {
      releaseManifest = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => (url.endsWith("manifest.json") ? manifestPromise : Promise.resolve({ ok: true, json: async () => [] }))),
    );

    const seen: string[] = [];
    const unsubscribe = subscribeShardLoadState((s) => seen.push(s));

    const loadPromise = loadSearchShards();
    // The function runs synchronously up to its first `await`, so the state
    // flips to "loading" before this call returns.
    expect(getShardLoadState()).toBe("loading");

    releaseManifest(manifestResponse([]));
    await loadPromise;

    expect(getShardLoadState()).toBe("loaded");
    expect(seen).toEqual(["loading", "loaded"]);
    unsubscribe();
  });

  // A shard that 404s or arrives malformed used to be skipped silently while
  // the state still went to "loaded", so the overlay told the user the index
  // was complete when content was missing. That is precisely the defect this
  // state exists to prevent. Raised in review on PR #100.
  it("reports partial, not loaded, when some shards fail, and keeps the ones that succeeded", async () => {
    const shardNames = ["shard-0.json", "shard-1.json", "shard-2.json"];
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("manifest.json")) return Promise.resolve(manifestResponse(shardNames));
      if (url.endsWith("shard-1.json")) return Promise.resolve({ ok: false, status: 404 });
      const i = shardNames.findIndex((n) => url.endsWith(n));
      const entry: ShardEntry = {
        ref_kind: "component", ref_id: `s${i}`, name: "PartialMatch",
        path: "p", component: "c", text: "",
      };
      return Promise.resolve({ ok: true, json: async () => [entry] });
    });
    vi.stubGlobal("fetch", fetchMock);

    await loadSearchShards();

    expect(getShardLoadState()).toBe("partial");
    // The surviving shards are still usable: a partial index beats none, as
    // long as the user is told it is partial.
    expect(search("PartialMatch").map((r) => r.id)).toEqual(["s0", "s2"]);
  });

  // One malformed shard used to reject Promise.all, discarding every sibling
  // that had loaded fine, so a single bad file lost the entire index.
  it("loses only the malformed shard, not every shard that loaded beside it", async () => {
    const shardNames = ["shard-0.json", "shard-1.json", "shard-2.json"];
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("manifest.json")) return Promise.resolve(manifestResponse(shardNames));
      if (url.endsWith("shard-1.json")) {
        return Promise.resolve({ ok: true, json: async () => { throw new SyntaxError("bad json"); } });
      }
      const i = shardNames.findIndex((n) => url.endsWith(n));
      const entry: ShardEntry = {
        ref_kind: "component", ref_id: `s${i}`, name: "SurvivorMatch",
        path: "p", component: "c", text: "",
      };
      return Promise.resolve({ ok: true, json: async () => [entry] });
    });
    vi.stubGlobal("fetch", fetchMock);

    await loadSearchShards();

    expect(getShardLoadState()).toBe("partial");
    expect(search("SurvivorMatch").map((r) => r.id)).toEqual(["s0", "s2"]);
  });

  it("reports failed, not partial, when every shard fails and nothing was collected", async () => {
    const shardNames = ["shard-0.json", "shard-1.json"];
    const fetchMock = vi.fn((url: string) => {
      if (url.endsWith("manifest.json")) return Promise.resolve(manifestResponse(shardNames));
      return Promise.resolve({ ok: false, status: 500 });
    });
    vi.stubGlobal("fetch", fetchMock);

    await loadSearchShards();

    expect(getShardLoadState()).toBe("failed");
  });

  it("marks the load failed, not loaded, when the fetch throws, so callers can't mistake it for a complete index", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    // Non-fatal to the caller: still resolves rather than throwing (a missing
    // or unreachable shard set must not break the app).
    await expect(loadSearchShards()).resolves.toBeUndefined();
    expect(getShardLoadState()).toBe("failed");
  });
});

// Incremental detail indexing. Every split-mode detail load called the full
// index rebuild, so a reader who opened forty components tokenised the whole
// corpus forty times; on the 165-component subject the page stalled long enough
// that the crawl's symbol pick timed out (finding `search.unusable`). Reverting
// addToSearchIndex to an unconditional rebuildFuse fails the bound below.
describe("incremental detail indexing", () => {
  beforeEach(() => {
    resetShardSearchEntries();
    resetDetailSearchEntries();
    initializeSearch(makeSplitArchitecture());
  });

  function detailSymbol(component: number, index: number): Symbol {
    return {
      id: `sym:src/c${component}/mod.ts:fn${index}:${index}`,
      name: `fn${component}_${index}`,
      kind: "function",
      file: `src/c${component}/mod.ts`,
      line: index,
      end_line: index + 1,
      code_preview: "",
      visibility: "public",
      docstring: null,
      parent: null,
      dependencies: [],
    };
  }

  function detailFile(component: number): FileInfo {
    return {
      path: `src/c${component}/mod.ts`,
      language: "typescript",
      lines: 10,
      size_bytes: 100,
      symbols: [],
      imports: [],
      exports: [],
      module_doc: null,
    };
  }

  it("loads forty detail shards without rebuilding the index forty times", () => {
    const before = getSearchIndexRebuildCount();
    for (let c = 0; c < 40; c++) {
      addToSearchIndex(
        [detailSymbol(c, 0), detailSymbol(c, 1)],
        [detailFile(c)],
        `comp-${c}`,
      );
    }
    // Forty loads, no full rebuild at all: every document was appended.
    expect(getSearchIndexRebuildCount() - before).toBe(0);

    // And the index is complete: every shard's symbols are findable.
    expect(search("fn0_0").map((r) => r.id)).toContain("sym:src/c0/mod.ts:fn0:0");
    expect(search("fn39_1").map((r) => r.id)).toContain("sym:src/c39/mod.ts:fn1:1");
  });

  it("bumps the index version as entries arrive so a memoised query recomputes (#116)", () => {
    const seen: number[] = [];
    const unsubscribe = subscribeSearchIndex((v) => seen.push(v));
    addToSearchIndex([detailSymbol(1, 0)], [detailFile(1)], "comp-1");
    expect(seen).toHaveLength(1);
    unsubscribe();
  });

  it("adds nothing, and rebuilds nothing, when the same detail shard loads twice", () => {
    addToSearchIndex([detailSymbol(2, 0)], [detailFile(2)], "comp-2");
    const rebuildsAfterFirst = getSearchIndexRebuildCount();
    const versionAfterFirst = getSearchIndexVersion();
    const firstHits = search("fn2_0");
    expect(firstHits).toHaveLength(1);

    addToSearchIndex([detailSymbol(2, 0)], [detailFile(2)], "comp-2");

    // No duplicate row, no rebuild, and no pointless memo invalidation.
    expect(search("fn2_0")).toHaveLength(1);
    expect(search("mod.ts").filter((r) => r.type === "file")).toHaveLength(1);
    expect(getSearchIndexRebuildCount()).toBe(rebuildsAfterFirst);
    expect(getSearchIndexVersion()).toBe(versionAfterFirst);
  });

  it("drops the old entries when a reloaded component comes back with fewer symbols", () => {
    addToSearchIndex([detailSymbol(3, 0), detailSymbol(3, 1)], [detailFile(3)], "comp-3");
    expect(search("fn3_1")).toHaveLength(1);

    addToSearchIndex([detailSymbol(3, 0)], [detailFile(3)], "comp-3");

    expect(search("fn3_1")).toHaveLength(0);
    expect(search("fn3_0")).toHaveLength(1);
  });
});
