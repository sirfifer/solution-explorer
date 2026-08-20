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
  type ShardEntry,
} from "../utils/search";
import type { Architecture, Component } from "../types";

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

  it("marks the load failed, not loaded, when the fetch throws, so callers can't mistake it for a complete index", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

    // Non-fatal to the caller: still resolves rather than throwing (a missing
    // or unreachable shard set must not break the app).
    await expect(loadSearchShards()).resolves.toBeUndefined();
    expect(getShardLoadState()).toBe("failed");
  });
});
