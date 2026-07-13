import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useArchStore } from "../store";
import { initializeSearch, search, resetDetailSearchEntries } from "../utils/search";
import type { Architecture, Component, FileInfo, Symbol as ArchSymbol } from "../types";

// Regression tests for F-VW-3 and the stale-componentDetailCache item of F-VW-7
// (P1-5). Live refresh must not wipe lazily indexed search entries, and it must
// invalidate the detail cache so panels refetch instead of serving stale data.
// These drive the real store and the real search module (no mocks of either);
// only the network fetch is mocked.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "comp-a",
    name: "Component A",
    type: "module",
    path: "src/a",
    language: "typescript",
    framework: null,
    description: null,
    port: null,
    children: [],
    files: ["src/a/index.ts"],
    entry_points: [],
    config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 0, languages: { typescript: 100 } },
    docs: {
      readme: null,
      claude_md: null,
      changelog: null,
      api_docs: null,
      architecture_notes: null,
      purpose: null,
      key_decisions: [],
      patterns: [],
      tech_stack: [],
      env_vars: [],
      api_endpoints: [],
    },
    ...overrides,
  };
}

// Split-mode architecture: top-level files/symbols are empty (they live in the
// per-component detail-*.json files fetched on demand).
function makeSplitArchitecture(overrides: Partial<Architecture> = {}): Architecture {
  return {
    name: "Split Project",
    description: "",
    repository: null,
    generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0",
    root_path: "/split",
    components: [makeComponent()],
    relationships: [],
    symbols: [],
    files: [],
    stats: {
      total_files: 0,
      total_lines: 0,
      total_size_bytes: 0,
      languages: {},
      total_symbols: 0,
      total_components: 0,
      total_relationships: 0,
    },
    ...overrides,
  };
}

function detailResponse(symbols: ArchSymbol[], files: FileInfo[]) {
  return {
    ok: true,
    headers: { get: () => "application/json" },
    json: async () => ({ symbols, files }),
  } as unknown as Response;
}

describe("live refresh: search preservation and cache invalidation (F-VW-3, F-VW-7 / P1-5)", () => {
  beforeEach(() => {
    localStorage.clear();
    resetDetailSearchEntries();
    useArchStore.setState({
      architecture: null,
      annotations: [],
      componentDetailCache: {},
      componentDetailLoading: null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("keeps previously loaded detail symbols searchable after a live refresh", async () => {
    const archV1 = makeSplitArchitecture();
    initializeSearch(archV1);
    useArchStore.setState({ architecture: archV1 });

    // Lazy-load a detail file that adds a distinctive symbol to the search index.
    const symbol: ArchSymbol = {
      id: "sym-1",
      name: "uniqueSymbolXYZ",
      kind: "function",
      file: "src/a/index.ts",
    } as ArchSymbol;
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(detailResponse([symbol], [])));

    await useArchStore.getState().loadComponentDetail("comp-a");
    expect(search("uniqueSymbolXYZ").some((r) => r.name === "uniqueSymbolXYZ")).toBe(true);

    // A live manifest refresh re-runs initializeSearch with the new manifest.
    initializeSearch(makeSplitArchitecture({ generated_at: "2026-07-11T12:00:00Z" }));

    // The lazily-indexed symbol must still be searchable. Pre-fix, initializeSearch
    // reset the index and dropped it.
    expect(search("uniqueSymbolXYZ").some((r) => r.name === "uniqueSymbolXYZ")).toBe(true);
  });

  it("invalidates the detail cache on architecture update so the panel refetches", async () => {
    const archV1 = makeSplitArchitecture();
    initializeSearch(archV1);
    useArchStore.setState({ architecture: archV1 });

    const v1Symbol: ArchSymbol = { id: "s", name: "v1sym", kind: "function", file: "src/a/index.ts" } as ArchSymbol;
    const v2Symbol: ArchSymbol = { id: "s", name: "v2sym", kind: "function", file: "src/a/index.ts" } as ArchSymbol;

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(detailResponse([v1Symbol], []))
      .mockResolvedValueOnce(detailResponse([v2Symbol], []));
    vi.stubGlobal("fetch", fetchMock);

    await useArchStore.getState().loadComponentDetail("comp-a");
    expect(useArchStore.getState().componentDetailCache["comp-a"]).toBeTruthy();
    expect(useArchStore.getState().getComponentSymbols("comp-a").map((s) => s.name)).toContain("v1sym");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Simulate a live architecture update (new scan).
    useArchStore.getState().setArchitecture(makeSplitArchitecture({ generated_at: "2026-07-11T12:00:00Z" }));

    // Cache must be invalidated so stale symbols are not served.
    expect(useArchStore.getState().componentDetailCache["comp-a"]).toBeUndefined();

    // Re-opening the component refetches fresh data.
    const refetched = await useArchStore.getState().loadComponentDetail("comp-a");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(refetched?.symbols.map((s) => s.name)).toContain("v2sym");
    expect(useArchStore.getState().getComponentSymbols("comp-a").map((s) => s.name)).toContain("v2sym");
  });

  it("discards an in-flight detail response that resolves after a live refresh (Copilot review on PR #10)", async () => {
    const archV1 = makeSplitArchitecture();
    initializeSearch(archV1);
    useArchStore.setState({ architecture: archV1 });

    const staleSymbol: ArchSymbol = { id: "s", name: "staleSym", kind: "function", file: "src/a/index.ts" } as ArchSymbol;

    // A deferred fetch: the response resolves only when we say so, simulating a
    // request from the old scan still in flight when the refresh lands.
    let resolveFetch: (r: Response) => void;
    const deferred = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(deferred));

    const inFlight = useArchStore.getState().loadComponentDetail("comp-a");
    expect(useArchStore.getState().componentDetailLoading).toBe("comp-a");

    // Live refresh swaps the architecture and invalidates the cache while the
    // request is still pending. It must also clear the loading marker.
    useArchStore.getState().setArchitecture(
      makeSplitArchitecture({ generated_at: "2026-07-12T00:00:00Z" }),
    );
    expect(useArchStore.getState().componentDetailLoading).toBeNull();

    // The stale response arrives after the swap and must be discarded.
    resolveFetch!(detailResponse([staleSymbol], []));
    const result = await inFlight;

    expect(result).toBeNull();
    expect(useArchStore.getState().componentDetailCache["comp-a"]).toBeUndefined();
    expect(useArchStore.getState().componentDetailLoading).toBeNull();
  });
});
