import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent, cleanup, screen, act } from "@testing-library/react";
import { SearchOverlay } from "../components/SearchOverlay";
import { useArchStore } from "../store";
import { initializeSearch, resetDetailSearchEntries, resetShardSearchEntries } from "../utils/search";
import type { Architecture, Component } from "../types";

// GUI regression findings from the 2026-07-22 Discovered table (PR #86 review
// F8, PR #85 review F9). Both fixes live in SearchOverlay.tsx's effects.

const loadSearchShardsMock = vi.fn(() => Promise.resolve());

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
