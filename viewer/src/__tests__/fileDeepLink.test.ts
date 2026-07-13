import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useArchStore } from "../store";
import { resetDetailSearchEntries } from "../utils/search";
import type { Architecture, Component, FileInfo, Symbol as ArchSymbol } from "../types";

// Tests for inbound ?file=&line= deep links (P3-2). These drive the real store
// (no mocks of it); only the network fetch is stubbed for the split-mode case.
// Cases: found (monolithic), missing, ambiguous (deepest owner wins), and
// split-mode-lazy (symbol resolves after the detail fetch).

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "comp",
    name: "Component",
    type: "module",
    path: "src/comp",
    language: "typescript",
    framework: null,
    description: null,
    port: null,
    children: [],
    files: [],
    entry_points: [],
    config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 1, languages: { typescript: 100 } },
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

function makeArchitecture(overrides: Partial<Architecture> = {}): Architecture {
  return {
    name: "Deep Link Project",
    description: "",
    repository: null,
    generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0",
    root_path: "/dl",
    components: [],
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

function makeSymbol(overrides: Partial<ArchSymbol> = {}): ArchSymbol {
  return {
    id: "sym-1",
    name: "targetFn",
    kind: "function",
    file: "src/a/index.ts",
    line: 10,
    end_line: 20,
    code_preview: "",
    visibility: "public",
    docstring: null,
    parent: null,
    dependencies: [],
    ...overrides,
  };
}

function makeFileInfo(path: string, symbols: string[] = []): FileInfo {
  return { path, language: "typescript", lines: 30, size_bytes: 500, symbols, imports: [], exports: [], module_doc: null };
}

function resetStore() {
  useArchStore.setState({
    architecture: null,
    selectedComponentId: null,
    drillLevel: null,
    breadcrumbs: [],
    detailItem: null,
    activePanel: null,
    componentDetailCache: {},
    componentDetailLoading: {},
    componentDetailErrors: {},
    fileDeepLink: null,
    fileDeepLinkNotice: null,
    annotations: [],
  });
}

describe("file deep links (P3-2)", () => {
  beforeEach(() => {
    resetDetailSearchEntries();
    resetStore();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("found (monolithic): navigates to the owner and resolves the symbol at the line", async () => {
    const comp = makeComponent({ id: "comp-a", name: "A", path: "src/a", files: ["src/a/index.ts"] });
    const arch = makeArchitecture({
      components: [comp],
      files: [makeFileInfo("src/a/index.ts", ["sym-1"])],
      symbols: [makeSymbol({ id: "sym-1", file: "src/a/index.ts", line: 10, end_line: 20 })],
    });
    useArchStore.setState({ architecture: arch });

    const result = await useArchStore.getState().openFileDeepLink("src/a/index.ts", 15);

    expect(result).toBe("found");
    const state = useArchStore.getState();
    // Top-level owner: selected and detail panel opened.
    expect(state.selectedComponentId).toBe("comp-a");
    expect(state.activePanel).toBe("detail");
    // The symbol whose range [10,20] contains line 15 is recorded.
    expect(state.fileDeepLink).toMatchObject({ componentId: "comp-a", filePath: "src/a/index.ts", line: 15, symbolId: "sym-1" });
    expect(state.fileDeepLinkNotice).toBeNull();
  });

  it("found without a line does not resolve a symbol but still navigates", async () => {
    const comp = makeComponent({ id: "comp-a", files: ["src/a/index.ts"] });
    const arch = makeArchitecture({
      components: [comp],
      files: [makeFileInfo("src/a/index.ts", ["sym-1"])],
      symbols: [makeSymbol()],
    });
    useArchStore.setState({ architecture: arch });

    const result = await useArchStore.getState().openFileDeepLink("src/a/index.ts", null);
    expect(result).toBe("found");
    expect(useArchStore.getState().fileDeepLink?.symbolId).toBeNull();
  });

  it("missing: shows a non-blocking notice and does not navigate", async () => {
    const comp = makeComponent({ id: "comp-a", files: ["src/a/index.ts"] });
    useArchStore.setState({ architecture: makeArchitecture({ components: [comp] }) });

    const result = await useArchStore.getState().openFileDeepLink("src/does/not/exist.ts", 5);

    expect(result).toBe("missing");
    const state = useArchStore.getState();
    expect(state.fileDeepLinkNotice).toContain("src/does/not/exist.ts");
    // No navigation happened: still on the overview.
    expect(state.selectedComponentId).toBeNull();
    expect(state.drillLevel).toBeNull();
    expect(state.activePanel).toBeNull();
    expect(state.fileDeepLink).toBeNull();
  });

  it("ambiguous: the deepest component that lists the file wins", async () => {
    // Both the parent and its child list the same path; the deeper child owns it.
    const child = makeComponent({ id: "child", name: "Child", path: "src/a/b", files: ["src/a/b/util.ts"] });
    const parent = makeComponent({ id: "parent", name: "Parent", path: "src/a", files: ["src/a/b/util.ts"], children: [child] });
    const arch = makeArchitecture({
      components: [parent],
      files: [makeFileInfo("src/a/b/util.ts", ["sym-2"])],
      symbols: [makeSymbol({ id: "sym-2", file: "src/a/b/util.ts", line: 1, end_line: 50 })],
    });
    useArchStore.setState({ architecture: arch });

    const result = await useArchStore.getState().openFileDeepLink("src/a/b/util.ts", 5);

    expect(result).toBe("found");
    const state = useArchStore.getState();
    // The child (depth 1) wins over the parent (depth 0). navigateToComponent
    // drills to the parent and selects the child.
    expect(state.selectedComponentId).toBe("child");
    expect(state.drillLevel).toBe("parent");
    expect(state.fileDeepLink?.componentId).toBe("child");
  });

  it("split-mode-lazy: resolves the symbol after the detail fetch lands", async () => {
    // Split mode: no top-level files/symbols; details come from a fetched file.
    const comp = makeComponent({ id: "comp-a", name: "A", path: "src/a", files: ["src/a/index.ts"] });
    useArchStore.setState({ architecture: makeArchitecture({ components: [comp] }) });

    const detailSymbol = makeSymbol({ id: "sym-split", file: "src/a/index.ts", line: 100, end_line: 140 });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: { get: () => "application/json" },
      json: async () => ({ symbols: [detailSymbol], files: [makeFileInfo("src/a/index.ts", ["sym-split"])] }),
    } as unknown as Response);
    vi.stubGlobal("fetch", fetchMock);

    const result = await useArchStore.getState().openFileDeepLink("src/a/index.ts", 120);

    expect(result).toBe("found");
    // The detail file was fetched to obtain symbol ranges.
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const state = useArchStore.getState();
    expect(state.selectedComponentId).toBe("comp-a");
    // Symbol resolved from the lazily fetched detail data.
    expect(state.fileDeepLink?.symbolId).toBe("sym-split");
    expect(state.componentDetailCache["comp-a"]).toBeTruthy();
  });
});

describe("parseUrlState line strictness (Copilot review on PR #15)", () => {
  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  it("accepts only a pure positive-integer line token", async () => {
    const { parseUrlState } = await import("../utils/urlState");

    window.history.replaceState(null, "", "/?file=src/a.ts&line=12");
    expect(parseUrlState().line).toBe(12);

    // parseInt would read these as 12 / 0; a pasted deep link must not
    // silently navigate to a line the URL never named.
    window.history.replaceState(null, "", "/?file=src/a.ts&line=12abc");
    expect(parseUrlState().line).toBeUndefined();

    window.history.replaceState(null, "", "/?file=src/a.ts&line=abc");
    expect(parseUrlState().line).toBeUndefined();

    window.history.replaceState(null, "", "/?file=src/a.ts&line=0");
    expect(parseUrlState().line).toBeUndefined();

    window.history.replaceState(null, "", "/?file=src/a.ts&line=-5");
    expect(parseUrlState().line).toBeUndefined();
  });
});
