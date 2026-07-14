import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useArchStore, collectPrefetchTargets } from "../store";
import type { Architecture, Component } from "../types";

// P6-4: aggregation nodes replace the old silent hero-filter hiding, and
// predictive prefetch warms the detail shards likely to open next.
//
// Fail-before (aggregation): before this change, getVisibleComponents DROPPED
// small internal modules when a hero was present (returning only the hero) and
// there was no getAggregateNodes at all, so the dropped module was unreachable
// from the graph. These tests assert the module is now recoverable as an
// expandable aggregate member. Reverting the store change removes
// getAggregateNodes (the member is gone from both visible and aggregates), so
// the "member is aggregated" and "expand reveals it" assertions fail.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "c",
    name: "C",
    type: "module",
    path: "src/c",
    language: "typescript",
    framework: null,
    description: null,
    port: null,
    children: [],
    files: ["src/c/index.ts"],
    entry_points: [],
    config_files: [],
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
    components: [], relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    ...overrides,
  };
}

// A drill parent whose promoted children are a hero screen (kept) and a small
// helper module (previously dropped by the hero filter, now aggregated).
function makeHeroWithHiddenModule() {
  const screen = makeComponent({ id: "screen-1", name: "Detail Screen", type: "screen", files: ["Detail.swift"] });
  const helper = makeComponent({ id: "helper-1", name: "Helpers", type: "module", files: ["Helpers.swift"] });
  const wrapper = makeComponent({ id: "wrapper", name: "Feature", type: "module", children: [screen, helper] });
  const parent = makeComponent({ id: "app", name: "App", type: "ios-client", children: [wrapper], files: [] });
  return { arch: makeArchitecture({ components: [parent] }), parent };
}

describe("aggregation nodes (P6-4)", () => {
  beforeEach(() => {
    useArchStore.setState({
      architecture: null, selectedComponentId: null, breadcrumbs: [],
      drillLevel: null, expandedAggregates: {},
    });
  });

  it("aggregates a small internal module instead of dropping it silently", () => {
    const { arch, parent } = makeHeroWithHiddenModule();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().drillInto(parent);

    const visible = useArchStore.getState().getVisibleComponents();
    const aggregates = useArchStore.getState().getAggregateNodes();

    // The hero screen is shown as a real node.
    expect(visible.map((c) => c.id)).toContain("screen-1");
    // The helper module is NOT a real node; it is a member of a visible aggregate.
    expect(visible.map((c) => c.id)).not.toContain("helper-1");
    expect(aggregates).toHaveLength(1);
    expect(aggregates[0].aggregateType).toBe("module");
    expect(aggregates[0].memberCount).toBe(1);
    expect(aggregates[0].members.map((m) => m.id)).toContain("helper-1");
    // The label is human-readable and counted (visible trace, not silent).
    expect(aggregates[0].label).toBe("1 module");
  });

  it("reveals the member as a real node when its aggregate is expanded, in place", () => {
    const { arch, parent } = makeHeroWithHiddenModule();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().drillInto(parent);

    const aggId = useArchStore.getState().getAggregateNodes()[0].id;
    useArchStore.getState().expandAggregate(aggId);

    const visible = useArchStore.getState().getVisibleComponents();
    expect(visible.map((c) => c.id)).toContain("helper-1");
    // The aggregate marker stays present so the grouping remains visible.
    expect(useArchStore.getState().getAggregateNodes()).toHaveLength(1);

    // Collapse hides the member again.
    useArchStore.getState().toggleAggregate(aggId);
    expect(useArchStore.getState().getVisibleComponents().map((c) => c.id)).not.toContain("helper-1");
  });

  it("keys aggregate ids by drill level so expansion never leaks across levels", () => {
    const { arch, parent } = makeHeroWithHiddenModule();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().drillInto(parent);
    const aggId = useArchStore.getState().getAggregateNodes()[0].id;
    expect(aggId).toContain("app"); // embeds the drill level
  });

  it("resets aggregate expansion when the architecture reloads", () => {
    const { arch, parent } = makeHeroWithHiddenModule();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().drillInto(parent);
    const aggId = useArchStore.getState().getAggregateNodes()[0].id;
    useArchStore.getState().expandAggregate(aggId);
    expect(useArchStore.getState().expandedAggregates[aggId]).toBe(true);

    // A fresh scan must start from collapsed aggregates.
    useArchStore.getState().setArchitecture(makeHeroWithHiddenModule().arch);
    expect(useArchStore.getState().expandedAggregates).toEqual({});
  });

  it("does not aggregate when there is no hero at the level (nothing hidden)", () => {
    const a = makeComponent({ id: "a", name: "A", type: "module", files: ["a.ts"] });
    const b = makeComponent({ id: "b", name: "B", type: "module", files: ["b.ts"] });
    const parent = makeComponent({ id: "p", name: "P", type: "project", children: [a, b], files: [] });
    const arch = makeArchitecture({ components: [parent] });
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().drillInto(parent);

    expect(useArchStore.getState().getAggregateNodes()).toHaveLength(0);
    expect(useArchStore.getState().getVisibleComponents().map((c) => c.id).sort()).toEqual(["a", "b"]);
  });
});

describe("collectPrefetchTargets (P6-4)", () => {
  it("returns the selection's children then breadcrumb ancestors, deduped and bounded", () => {
    const gc = makeComponent({ id: "gc", name: "GC" });
    const child1 = makeComponent({ id: "child-1", name: "Child 1" });
    const child2 = makeComponent({ id: "child-2", name: "Child 2", children: [gc] });
    const sel = makeComponent({ id: "sel", name: "Sel", children: [child1, child2] });
    const root = makeComponent({ id: "root", name: "Root", children: [sel] });
    const arch = makeArchitecture({ components: [root] });

    const breadcrumbs = [
      { id: "root", name: "Root", type: "project" },
      { id: "sel", name: "Sel", type: "module" },
    ];

    const targets = collectPrefetchTargets(arch, "sel", breadcrumbs, 8);
    // Children first (drill-down), then ancestors (navigate-up), self excluded.
    expect(targets).toEqual(["child-1", "child-2", "root"]);
    expect(targets).not.toContain("sel");
  });

  it("bounds the target set to the limit", () => {
    const children = Array.from({ length: 20 }, (_, i) => makeComponent({ id: `k${i}` }));
    const sel = makeComponent({ id: "sel", children });
    const arch = makeArchitecture({ components: [sel] });
    const targets = collectPrefetchTargets(arch, "sel", [], 5);
    expect(targets).toHaveLength(5);
  });

  it("returns nothing when no architecture is loaded", () => {
    expect(collectPrefetchTargets(null, "x", [])).toEqual([]);
  });
});

describe("prefetchDetails wiring (P6-4)", () => {
  let fetchSpy: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    // Run idle callbacks synchronously so the scheduled fetches are observable.
    (globalThis as { requestIdleCallback?: (cb: () => void) => void }).requestIdleCallback = (cb) => cb();
    fetchSpy = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ symbols: [], files: [] }) }));
    vi.stubGlobal("fetch", fetchSpy);
    useArchStore.setState({
      architecture: null, selectedComponentId: null, breadcrumbs: [],
      drillLevel: null, expandedAggregates: {},
      componentDetailCache: {}, componentDetailLoading: {}, componentDetailErrors: {},
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    delete (globalThis as { requestIdleCallback?: unknown }).requestIdleCallback;
  });

  it("prefetches the child detail shards of the selection in split mode", () => {
    const child = makeComponent({ id: "child-1", name: "Child", files: ["x.ts"] });
    const sel = makeComponent({ id: "sel", name: "Sel", children: [child], files: [] });
    // Split mode: no inline files, so detail is fetched per component.
    const arch = makeArchitecture({ components: [sel] });
    useArchStore.getState().setArchitecture(arch);

    useArchStore.getState().prefetchDetails("sel");

    // The child's detail shard was requested (prefetched for the likely drill).
    expect(fetchSpy).toHaveBeenCalledWith("./architecture/data/detail-child-1.json");
  });

  it("is a no-op in monolith mode (detail already inline)", () => {
    const child = makeComponent({ id: "child-1", files: ["x.ts"] });
    const sel = makeComponent({ id: "sel", children: [child], files: [] });
    // Monolith mode is signalled by a non-empty top-level files array.
    const arch = makeArchitecture({
      components: [sel],
      files: [{ path: "x.ts", language: "ts", lines: 1, size_bytes: 1, symbols: [], imports: [], exports: [], module_doc: null }],
    });
    useArchStore.getState().setArchitecture(arch);

    useArchStore.getState().prefetchDetails("sel");
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
