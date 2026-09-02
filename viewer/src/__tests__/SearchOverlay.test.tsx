import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent, cleanup, screen, act, waitFor } from "@testing-library/react";
import { SearchOverlay } from "../components/SearchOverlay";
import { useArchStore } from "../store";
import { initializeSearch, resetDetailSearchEntries, resetShardSearchEntries, addShardEntries } from "../utils/search";
import type { Architecture, Component, Symbol } from "../types";

// GUI regression findings from the 2026-07-22 Discovered table (PR #86 review
// F8, PR #85 review F9). Both fixes live in SearchOverlay.tsx's effects.

const loadSearchShardsMock = vi.fn(() => Promise.resolve());

// Captured at module load, before any test can stub it out via setState (as
// the "effect split" suite below does for navigateToComponent without
// restoring it), so the O3 suite can put the real implementation back.
const realNavigateToComponent = useArchStore.getState().navigateToComponent;

vi.mock("../utils/search", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../utils/search")>();
  return { ...actual, loadSearchShards: (...args: unknown[]) => loadSearchShardsMock(...(args as [])) };
});

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "alpha-svc", name: "Alpha Service", type: "service", path: "src/alpha",
    language: "typescript", framework: null, description: null, port: null,
    children: [], files: [], entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { typescript: 100 } },
    docs: {
      readme: null, claude_md: null, changelog: null, api_docs: null,
      architecture_notes: null, purpose: null, key_decisions: [], patterns: [],
      tech_stack: [], env_vars: [], api_endpoints: [],
    },
    ...overrides,
  };
}

function makeArchitecture(overrides: Partial<Architecture> = {}): Architecture {
  return {
    name: "T", description: "", repository: null,
    generated_at: "2025-01-01T00:00:00Z", analyzer_version: "1.2.0", root_path: "/t",
    components: [
      makeComponent({ id: "alpha-svc", name: "Alpha Service", path: "src/alpha-svc" }),
      makeComponent({ id: "alpha-gw", name: "Alpha Gateway", path: "src/alpha-gw" }),
    ],
    relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  useArchStore.setState({ architecture: null, searchOpen: false, searchQuery: "" });
});

describe("SearchOverlay: component_detail_index empty-object gate (PR #86 review F8)", () => {
  beforeEach(() => {
    loadSearchShardsMock.mockClear();
    resetShardSearchEntries();
    resetDetailSearchEntries();
    initializeSearch(makeArchitecture());
  });

  it("does not probe shards when component_detail_index is absent (monolith)", () => {
    useArchStore.setState({
      architecture: makeArchitecture(), // no component_detail_index key
      searchOpen: true,
    });
    render(<SearchOverlay />);
    expect(loadSearchShardsMock).not.toHaveBeenCalled();
  });

  it("does not probe shards when component_detail_index is an empty object (degraded split skeleton, fail-before)", () => {
    // A degraded split-mode skeleton writer can set component_detail_index to
    // {}, which is truthy in JS. The old gate (`architecture.component_detail_index`)
    // would still fire the probe here and 404 on every search open.
    useArchStore.setState({
      architecture: makeArchitecture({ component_detail_index: {} }),
      searchOpen: true,
    });
    render(<SearchOverlay />);
    expect(loadSearchShardsMock).not.toHaveBeenCalled();
  });

  it("does probe shards when component_detail_index is non-empty (healthy split)", () => {
    useArchStore.setState({
      architecture: makeArchitecture({
        component_detail_index: { "alpha-svc": { symbolCount: 3, fileCount: 2 } },
      }),
      searchOpen: true,
    });
    render(<SearchOverlay />);
    expect(loadSearchShardsMock).toHaveBeenCalledTimes(1);
  });
});

describe("SearchOverlay: effect split preserves selection across a live refresh (PR #85 review F9)", () => {
  beforeEach(() => {
    loadSearchShardsMock.mockClear();
    resetShardSearchEntries();
    resetDetailSearchEntries();
  });

  it("keeps the arrow-key selection when the architecture object changes while the overlay stays open", () => {
    const archV1 = makeArchitecture();
    initializeSearch(archV1);
    const navigateToComponent = vi.fn();

    useArchStore.setState({
      architecture: archV1,
      searchOpen: true,
      searchQuery: "Alpha",
      navigateToComponent,
    });

    render(<SearchOverlay />);

    // Both "Alpha Service" and "Alpha Gateway" match; confirm two results render.
    const resultButtons = screen.getAllByRole("button").filter((b) => b.textContent?.includes("Alpha"));
    expect(resultButtons.length).toBeGreaterThanOrEqual(2);

    const input = screen.getByPlaceholderText("Search components, files, symbols...");

    // Move the selection down to the second result.
    fireEvent.keyDown(input, { key: "ArrowDown" });

    // Simulate a live-monitor refresh: a NEW architecture object (different
    // reference, same content) arrives while the overlay is still open. Before
    // the fix this re-ran the combined effect and reset selectedIndex to 0.
    const archV2 = makeArchitecture({ generated_at: "2026-01-01T00:00:00Z" });
    initializeSearch(archV2);
    act(() => {
      useArchStore.setState({ architecture: archV2 });
    });

    // Selecting now (Enter) must still resolve to the SECOND result, proving
    // the refresh did not reset the user's in-progress selection.
    fireEvent.keyDown(input, { key: "Enter" });

    expect(navigateToComponent).toHaveBeenCalledTimes(1);
    expect(navigateToComponent).toHaveBeenCalledWith("alpha-gw");
  });

  it("still resets selection and focuses the input on a fresh open (first-open behavior preserved)", () => {
    vi.useFakeTimers();
    try {
      const arch = makeArchitecture();
      initializeSearch(arch);
      useArchStore.setState({ architecture: arch, searchOpen: false, searchQuery: "" });
      const { rerender } = render(<SearchOverlay />);
      expect(useArchStore.getState().searchOpen).toBe(false);

      act(() => {
        useArchStore.setState({ searchOpen: true });
      });
      rerender(<SearchOverlay />);
      act(() => {
        vi.advanceTimersByTime(60);
      });

      const input = screen.getByPlaceholderText("Search components, files, symbols...") as HTMLInputElement;
      expect(document.activeElement).toBe(input);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("SearchOverlay: symbol search re-resolves once the owning component loads (O3)", () => {
  const targetSymbol: Symbol = {
    id: "sym-thing", name: "doThing", kind: "function",
    file: "src/beta-svc/thing.ts", line: 10, end_line: 20,
    code_preview: "", visibility: "public", docstring: null, parent: null, dependencies: [],
  };

  function splitModeArchitecture(): Architecture {
    // Split mode: symbols/files arrive only via per-component detail fetches, so
    // arch.symbols/arch.files stay empty until a component's detail is loaded.
    return makeArchitecture({
      components: [makeComponent({ id: "beta-svc", name: "Beta Service", path: "src/beta-svc" })],
      symbols: [],
      files: [],
    });
  }

  beforeEach(() => {
    resetShardSearchEntries();
    resetDetailSearchEntries();
    useArchStore.setState({
      componentDetailCache: {},
      componentDetailLoading: {},
      componentDetailErrors: {},
      selectedComponentId: null,
      detailItem: null,
      navigateToComponent: realNavigateToComponent,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("navigates to the owning component then opens the symbol once its detail resolves", async () => {
    const arch = splitModeArchitecture();
    initializeSearch(arch);
    // Shard entry for a symbol whose component detail has not been fetched yet
    // (P6-4 index), the exact split-mode scenario O3 describes.
    addShardEntries([
      { ref_kind: "symbol", ref_id: "sym-thing", name: "doThing", path: "src/beta-svc/thing.ts", component: "beta-svc", text: "" },
    ]);

    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      expect(String(url)).toContain("detail-beta-svc.json");
      return { ok: true, json: async () => ({ symbols: [targetSymbol], files: [] }) } as Response;
    }));

    useArchStore.setState({ architecture: arch, searchOpen: true, searchQuery: "doThing" });
    render(<SearchOverlay />);

    const resultButton = await screen.findByText("doThing");
    fireEvent.click(resultButton);

    // Landed on the owning component immediately (synchronous half of the fix).
    expect(useArchStore.getState().selectedComponentId).toBe("beta-svc");

    // Once the detail fetch resolves, the symbol itself is opened (async half).
    await waitFor(() => {
      const item = useArchStore.getState().detailItem;
      expect(item?.type).toBe("symbol");
      expect((item?.data as Symbol).id).toBe("sym-thing");
    });
  });

  it("does not open a stale symbol if the user navigates elsewhere before the detail resolves", async () => {
    const arch = splitModeArchitecture();
    initializeSearch(arch);
    addShardEntries([
      { ref_kind: "symbol", ref_id: "sym-thing", name: "doThing", path: "src/beta-svc/thing.ts", component: "beta-svc", text: "" },
    ]);

    let resolveFetch: (v: Response) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => { resolveFetch = resolve; })));

    useArchStore.setState({ architecture: arch, searchOpen: true, searchQuery: "doThing" });
    render(<SearchOverlay />);

    const resultButton = await screen.findByText("doThing");
    fireEvent.click(resultButton);
    expect(useArchStore.getState().selectedComponentId).toBe("beta-svc");

    // User navigates away before the fetch settles.
    act(() => {
      useArchStore.setState({ selectedComponentId: "other-component", detailItem: null });
    });

    // Now let the fetch resolve.
    await act(async () => {
      resolveFetch({ ok: true, json: async () => ({ symbols: [targetSymbol], files: [] }) } as Response);
      await Promise.resolve();
      await Promise.resolve();
    });

    // The stale symbol must not have been opened over wherever the user went.
    expect(useArchStore.getState().detailItem).toBeNull();
  });
});

// The Overview mounts its own SearchOverlay, and every result it offers is a
// workbench object. Picking one used to select it in the store and leave the
// reader on the front door with nothing to show for it (GUI crawl 2026-09-01,
// overview.search_dead). All three result kinds cross over, because all three
// land somewhere only the workbench draws.
describe("SearchOverlay: a result chosen from the Overview crosses into the workbench", () => {
  function searchableArchitecture(): Architecture {
    return makeArchitecture({
      files: [{
        path: "src/alpha/alphaThing.ts", language: "typescript", lines: 10,
        size_bytes: 100, symbols: ["sym-alpha"], imports: [], exports: [], module_doc: null,
      }],
      symbols: [{
        id: "sym-alpha", name: "alphaThing", kind: "function",
        file: "src/alpha/alphaThing.ts", line: 1, end_line: 5, code_preview: "",
        visibility: "public", docstring: null, parent: null, dependencies: [],
      }],
    });
  }

  function pickFirstResultOfKind(kind: string) {
    const result = document.querySelector(`[data-result-kind="${kind}"]`);
    expect(result, `a ${kind} result is offered`).not.toBeNull();
    fireEvent.click(result as Element);
  }

  beforeEach(() => {
    resetShardSearchEntries();
    resetDetailSearchEntries();
    useArchStore.setState({
      navigateToComponent: realNavigateToComponent,
      experienceMode: "overview",
      selectedComponentId: null,
      detailItem: null,
      fileDeepLink: null,
      fileDeepLinkNotice: null,
    });
  });

  for (const kind of ["component", "file", "symbol"]) {
    it(`sets the workbench aperture for a ${kind} result`, () => {
      const arch = searchableArchitecture();
      initializeSearch(arch);
      useArchStore.setState({
        architecture: arch, searchOpen: true, searchQuery: "alpha",
        experienceMode: "overview",
      });
      render(<SearchOverlay />);

      pickFirstResultOfKind(kind);

      expect(useArchStore.getState().experienceMode).toBe("workbench");
    });
  }

  // On a phone the detail panel is a bottom sheet that opens at "peek", which
  // is right for a direct tap on a graph node and wrong for a search result:
  // the reader never touched the thing they landed on, so peek shows them a
  // name they just typed. Every kind of result asks for the detail to be
  // revealed, monolithic-mode branches included.
  for (const kind of ["component", "file", "symbol"]) {
    it(`asks for the mobile detail sheet to open for a ${kind} result`, () => {
      const arch = searchableArchitecture();
      initializeSearch(arch);
      useArchStore.setState({
        architecture: arch, searchOpen: true, searchQuery: "alpha",
        experienceMode: "overview", revealDetail: false,
      });
      render(<SearchOverlay />);

      pickFirstResultOfKind(kind);

      expect(useArchStore.getState().revealDetail).toBe(true);
      useArchStore.getState().clearRevealDetail();
    });
  }
});
