import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { DetailPanel } from "../components/DetailPanel";
import { useArchStore } from "../store";
import type { Architecture, Component, FileInfo, Symbol as ArchSymbol } from "../types";

// Regression test for F-CRIT-4 (P0-6): in split mode the detail panel fetches
// detail-<id>.json into componentDetailCache after mount. Before the fix, the
// files/symbols memos were keyed only on [component.id, action] which stay
// referentially stable across the cache update, so the Files and Symbols tabs
// never rendered the fetched data. This test drives the real store and the real
// DetailPanel with a mocked global fetch and asserts the
// empty-then-loading-then-populated sequence.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "repo:demo/api",
    name: "API Service",
    type: "module",
    path: "src/api",
    language: "typescript",
    framework: null,
    description: null,
    port: null,
    children: [],
    files: ["src/api/index.ts"],
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

// Split-mode architecture: files and symbols arrays are empty at the top level
// (they live in per-component detail-*.json files fetched on demand).
function makeSplitArchitecture(component: Component): Architecture {
  return {
    name: "Demo",
    description: "A split-mode project",
    repository: null,
    generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0",
    root_path: "/demo",
    components: [component],
    relationships: [],
    symbols: [],
    files: [],
    stats: {
      total_files: 2,
      total_lines: 200,
      total_size_bytes: 2000,
      languages: { typescript: 200 },
      total_symbols: 3,
      total_components: 1,
      total_relationships: 0,
    },
  };
}

function makeFile(path: string, symbols: string[]): FileInfo {
  return {
    path,
    language: "typescript",
    lines: 100,
    size_bytes: 1000,
    symbols,
    imports: [],
    exports: [],
    module_doc: null,
  };
}

function makeSymbol(id: string, name: string, file: string): ArchSymbol {
  return {
    id,
    name,
    kind: "function",
    file,
    line: 1,
    end_line: 5,
    code_preview: "",
    visibility: "public",
    docstring: null,
    parent: null,
    dependencies: [],
  };
}

describe("DetailPanel split-mode lazy detail (F-CRIT-4)", () => {
  const component = makeComponent();

  // A deferred so we can assert the loading state before the fetch resolves.
  let resolveFetch: (value: { ok: boolean; json: () => Promise<unknown> }) => void;
  let detailPayload: { files: FileInfo[]; symbols: ArchSymbol[] };

  beforeEach(() => {
    detailPayload = {
      files: [
        makeFile("src/api/index.ts", ["sym-handler", "sym-router"]),
        makeFile("src/api/db.ts", ["sym-connect"]),
      ],
      symbols: [
        makeSymbol("sym-handler", "handleRequest", "src/api/index.ts"),
        makeSymbol("sym-router", "buildRouter", "src/api/index.ts"),
        makeSymbol("sym-connect", "connectDatabase", "src/api/db.ts"),
      ],
    };

    const fetchPromise = new Promise<{ ok: boolean; json: () => Promise<unknown> }>((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn(() => fetchPromise));

    // Reset the real store to a clean split-mode state (do NOT mock the store).
    useArchStore.setState({
      architecture: makeSplitArchitecture(component),
      loading: false,
      error: null,
      detailItem: { type: "component", data: component },
      activePanel: "detail",
      componentDetailCache: {},
      componentDetailLoading: {},
      componentDetailErrors: {},
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    useArchStore.setState({ componentDetailCache: {}, componentDetailLoading: {}, componentDetailErrors: {}, detailItem: null });
  });

  it("shows a loading state then renders fetched files and symbols with updated counts", async () => {
    render(<DetailPanel />);

    // The mount effect triggers the lazy fetch and marks this component loading.
    await waitFor(() => {
      expect(useArchStore.getState().componentDetailLoading[component.id]).toBe(true);
    });
    expect(fetch).toHaveBeenCalledWith("./architecture/data/detail-repo__demo--api.json");

    // Files tab: empty before the fetch, so it shows the loading indicator.
    fireEvent.click(screen.getByRole("button", { name: /Files/ }));
    expect(screen.getByRole("status")).toBeDefined();
    expect(screen.getByText("Loading files...")).toBeDefined();
    // The file names are not yet in the DOM.
    expect(screen.queryByText("index.ts")).toBeNull();

    // Resolve the fetch with the detail payload.
    resolveFetch({ ok: true, json: async () => detailPayload });

    // Files now render, proving the panel reacted to the cache update.
    await waitFor(() => {
      expect(screen.getByText("index.ts")).toBeDefined();
    });
    expect(screen.getByText("db.ts")).toBeDefined();
    expect(screen.queryByText("Loading files...")).toBeNull();

    // The Files tab count updated from 0 to 2.
    const filesTabButton = screen.getByRole("button", { name: /Files\s*2/ });
    expect(filesTabButton).toBeDefined();

    // Symbols tab renders the fetched symbols and its count updated to 3.
    fireEvent.click(screen.getByRole("button", { name: /Symbols/ }));
    await waitFor(() => {
      expect(screen.getByText("handleRequest")).toBeDefined();
    });
    expect(screen.getByText("connectDatabase")).toBeDefined();
    const symbolsTabButton = screen.getByRole("button", { name: /Symbols\s*3/ });
    expect(symbolsTabButton).toBeDefined();
  });
});
