import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import { activityLens, getLens, listAvailableLenses } from "../lenses";
import { buildRationale } from "../components/RationaleStrip";
import { parseUrlState, replaceUrlState } from "../utils/urlState";
import type { Architecture, Component, ActivityData } from "../types";

// P6-5 Activity lens: availability gate (degrades like coverage), the ranked
// hotspot landing (I11), the knowledge map, coupling reached from a component
// (never standalone), cross-lens identity (I12), and the rationale strip (I13).

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "c", name: "C", type: "module", path: "src/c", language: "typescript",
    framework: null, description: null, port: null, children: [], files: ["src/c/i.ts"],
    entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { typescript: 100 } },
    docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
    ...overrides,
  };
}

function makeArchitecture(overrides: Partial<Architecture> = {}): Architecture {
  return {
    name: "T", description: "", repository: null, generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0", root_path: "/t", components: [], relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    ...overrides,
  };
}

// A three-component activity fixture (ranked a > b > c by hotspot score),
// mirroring the P5-4 activity.json shape. Attached inline under
// architecture.activity so loadActivity uses the monolith path (no fetch).
function makeActivity(): ActivityData {
  return {
    provenance: { git: true, shallow: false, head: "abc123", commits: 75, first_commit: "2025-01-01T00:00:00Z", last_commit: "2025-06-01T00:00:00Z" },
    components: [
      {
        id: "a", name: "Alpha", files: 2, commit_count: 50, lines_added: 300, lines_removed: 200,
        churn: 500, lines: 1000, hotspot_score: 1000, first_seen: "2025-01-01T00:00:00Z",
        last_modified: "2025-06-01T00:00:00Z", author_count: 2, top_author_share: 0.8,
        knowledge_island: false, bus_factor: 1,
        authors: [
          { author_key: "alice@x.io", author_name: "Alice", commits: 40, share: 0.8 },
          { author_key: "bob@x.io", author_name: "Bob", commits: 10, share: 0.2 },
        ],
      },
      {
        id: "b", name: "Beta", files: 1, commit_count: 20, lines_added: 120, lines_removed: 80,
        churn: 200, lines: 500, hotspot_score: 400, first_seen: "2025-02-01T00:00:00Z",
        last_modified: "2025-05-01T00:00:00Z", author_count: 1, top_author_share: 1.0,
        knowledge_island: true, bus_factor: 1,
        authors: [{ author_key: "carol@x.io", author_name: "Carol", commits: 20, share: 1.0 }],
      },
      {
        id: "c", name: "Gamma", files: 1, commit_count: 5, lines_added: 60, lines_removed: 40,
        churn: 100, lines: 200, hotspot_score: 100, first_seen: "2025-03-01T00:00:00Z",
        last_modified: "2025-04-01T00:00:00Z", author_count: 1, top_author_share: 1.0,
        knowledge_island: true, bus_factor: 1,
        authors: [{ author_key: "alice@x.io", author_name: "Alice", commits: 5, share: 1.0 }],
      },
    ],
    // Cross-component coupling: a<->b only. c is uncoupled by construction.
    component_coupling: [{ a: "a", b: "b", cochange_count: 12 }],
    file_coupling: [{ a: "src/a/x.ts", b: "src/a/y.ts", cochange_count: 8 }],
    files: {
      "src/a/x.ts": { commit_count: 30, lines_added: 180, lines_removed: 120, churn: 300, lines: 400, hotspot_score: 800, first_seen: null, last_modified: null, component_ids: ["a"], authors: [] },
      "src/a/y.ts": { commit_count: 20, lines_added: 120, lines_removed: 80, churn: 200, lines: 100, hotspot_score: 200, first_seen: null, last_modified: null, component_ids: ["a"], authors: [] },
      "src/b/z.ts": { commit_count: 20, lines_added: 120, lines_removed: 80, churn: 200, lines: 500, hotspot_score: 400, first_seen: null, last_modified: null, component_ids: ["b"], authors: [] },
    },
  };
}

function archWithActivity(): Architecture {
  return makeArchitecture({
    components: [
      makeComponent({ id: "a", name: "Alpha" }),
      makeComponent({ id: "b", name: "Beta" }),
      makeComponent({ id: "c", name: "Gamma" }),
    ],
    activity: makeActivity(),
  });
}

function resetStore() {
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [], drillLevel: null,
    expandedAggregates: {}, detailItem: null, activePanel: null, lens: "structure",
    activityData: null, activityLoading: false, activityError: null,
  });
}

describe("Activity lens availability (P6-5)", () => {
  beforeEach(resetStore);

  it("registers the Activity lens", () => {
    expect(getLens("activity")?.label).toBe("Activity");
  });

  it("is available only when the dataset carries activity data (degrades like coverage)", () => {
    expect(activityLens.isAvailable(archWithActivity())).toBe(true);
    expect(activityLens.isAvailable(makeArchitecture())).toBe(false);
    expect(listAvailableLenses(archWithActivity()).map((l) => l.id)).toContain("activity");
    expect(listAvailableLenses(makeArchitecture()).map((l) => l.id)).not.toContain("activity");
  });
});

describe("Activity lens data (P6-5)", () => {
  beforeEach(resetStore);

  it("loads activity inline (monolith) and ranks hotspots by score (I11)", async () => {
    useArchStore.getState().setArchitecture(archWithActivity());
    await useArchStore.getState().loadActivity();

    const hotspots = useArchStore.getState().getHotspots();
    expect(hotspots.map((c) => c.id)).toEqual(["a", "b", "c"]);
    // Non-increasing hotspot score: the top of the list is where to look first.
    for (let i = 1; i < hotspots.length; i++) {
      expect(hotspots[i - 1].hotspot_score).toBeGreaterThanOrEqual(hotspots[i].hotspot_score);
    }
    expect(hotspots[0].hotspot_score).toBe(Math.max(...hotspots.map((c) => c.hotspot_score)));
  });

  it("degrades to no hotspots and an unavailable lens without activity data", async () => {
    useArchStore.getState().setArchitecture(makeArchitecture({ components: [makeComponent({ id: "a" })] }));
    expect(await useArchStore.getState().loadActivity()).toBeNull();
    expect(useArchStore.getState().getHotspots()).toEqual([]);
    expect(listAvailableLenses(useArchStore.getState().architecture).map((l) => l.id)).not.toContain("activity");
  });

  it("surfaces the knowledge map: author shares top-first, island flag, bus factor", async () => {
    useArchStore.getState().setArchitecture(archWithActivity());
    await useArchStore.getState().loadActivity();

    const a = useArchStore.getState().getActivityComponent("a")!;
    expect(a.authors[0].author_name).toBe("Alice"); // top contributor first
    expect(a.authors[0].share).toBeGreaterThanOrEqual(a.authors[1].share);
    expect(a.knowledge_island).toBe(false);
    expect(a.bus_factor).toBe(1);

    const b = useArchStore.getState().getActivityComponent("b")!;
    expect(b.knowledge_island).toBe(true); // single-author island: at-risk
  });

  it("reaches coupling FROM a component (cross-component, empty when uncoupled)", async () => {
    useArchStore.getState().setArchitecture(archWithActivity());
    await useArchStore.getState().loadActivity();

    const forA = useArchStore.getState().getCouplingForComponent("a");
    expect(forA).toEqual([{ partnerId: "b", partnerName: "Beta", count: 12 }]);
    // The pair is symmetric and anchored to whichever component is focused.
    expect(useArchStore.getState().getCouplingForComponent("b")).toEqual([
      { partnerId: "a", partnerName: "Alpha", count: 12 },
    ]);
    // Never a standalone hairball: an uncoupled component reaches nothing.
    expect(useArchStore.getState().getCouplingForComponent("c")).toEqual([]);
  });

  it("drills a hotspot into its ranked per-file detail", async () => {
    useArchStore.getState().setArchitecture(archWithActivity());
    await useArchStore.getState().loadActivity();
    const files = useArchStore.getState().getComponentActivityFiles("a");
    expect(files.map((f) => f.path)).toEqual(["src/a/x.ts", "src/a/y.ts"]); // ranked by score
  });
});

describe("Activity lens cross-lens identity (I12)", () => {
  beforeEach(resetStore);

  it("keeps selection, drill, breadcrumbs, and the URL lens param across Structure -> Activity", () => {
    const child = makeComponent({ id: "child", name: "Child" });
    const parent = makeComponent({ id: "parent", name: "Parent", children: [child], files: [] });
    const arch = makeArchitecture({ components: [parent], activity: makeActivity() });
    useArchStore.getState().setArchitecture(arch);

    useArchStore.getState().drillInto(parent);
    useArchStore.getState().selectComponent("child");
    const crumbsBefore = useArchStore.getState().breadcrumbs;

    useArchStore.getState().setLens("activity");

    const after = useArchStore.getState();
    expect(after.lens).toBe("activity"); // available, so the switch takes
    expect(after.selectedComponentId).toBe("child");
    expect(after.drillLevel).toBe("parent");
    expect(after.breadcrumbs).toEqual(crumbsBefore);

    // The lens rides the URL composed with the preserved component/drill params.
    replaceUrlState({ lens: "activity", component: "child", drill: "parent" });
    const url = parseUrlState();
    expect(url.lens).toBe("activity");
    expect(url.component).toBe("child");
    expect(url.drill).toBe("parent");

    // Switching back to Structure preserves identity too.
    useArchStore.getState().setLens("structure");
    expect(useArchStore.getState().selectedComponentId).toBe("child");
    expect(useArchStore.getState().drillLevel).toBe("parent");
  });
});

describe("Activity lens rationale strip (I13)", () => {
  beforeEach(resetStore);

  it("flows git author, last change, and churn into the rationale for every element", async () => {
    useArchStore.getState().setArchitecture(archWithActivity());
    await useArchStore.getState().loadActivity();

    const compA = useArchStore.getState().getComponentById("a")!;
    const actA = useArchStore.getState().getActivityComponent("a");
    const r = buildRationale(compA, actA);
    expect(r).not.toBeNull();
    expect(r!.author).toBe("Alice"); // lead author from git history
    expect(r!.churn).toBe(500);
    expect(r!.lastChange).toBeTypeOf("string"); // relative time of last modification
  });

  it("renders nothing when neither activity nor AI data is present", () => {
    const bare = makeComponent({ id: "bare" });
    expect(buildRationale(bare, null)).toBeNull();
  });
});
