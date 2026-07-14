import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import { ACTIVITY_QUESTIONS } from "../lenses";
import { buildRationale } from "../components/RationaleStrip";
import type { Architecture, Component, ActivityData } from "../types";

// I14: the Activity lens ships a documented question list, and every question's
// gesture is exercised here against the real store with an asserted answer. A
// question without a tested gesture fails the coverage assertion at the end.

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

function makeActivity(): ActivityData {
  return {
    provenance: { git: true, shallow: false, head: "abc", commits: 75, first_commit: null, last_commit: null },
    components: [
      { id: "a", name: "Alpha", files: 2, commit_count: 50, lines_added: 300, lines_removed: 200, churn: 500, lines: 1000, hotspot_score: 1000, first_seen: null, last_modified: "2025-06-01T00:00:00Z", author_count: 2, top_author_share: 0.8, knowledge_island: false, bus_factor: 1, authors: [
        { author_key: "alice@x.io", author_name: "Alice", commits: 40, share: 0.8 },
        { author_key: "bob@x.io", author_name: "Bob", commits: 10, share: 0.2 },
      ] },
      { id: "b", name: "Beta", files: 1, commit_count: 20, lines_added: 120, lines_removed: 80, churn: 200, lines: 500, hotspot_score: 400, first_seen: null, last_modified: null, author_count: 1, top_author_share: 1.0, knowledge_island: true, bus_factor: 1, authors: [
        { author_key: "carol@x.io", author_name: "Carol", commits: 20, share: 1.0 },
      ] },
    ],
    component_coupling: [{ a: "a", b: "b", cochange_count: 12 }],
    file_coupling: [],
    files: {
      "src/a/x.ts": { commit_count: 30, lines_added: 180, lines_removed: 120, churn: 300, lines: 400, hotspot_score: 800, first_seen: null, last_modified: null, component_ids: ["a"], authors: [] },
    },
  };
}

function seed(): void {
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [], drillLevel: null,
    expandedAggregates: {}, detailItem: null, activePanel: null, lens: "structure",
    activityData: null, activityLoading: false, activityError: null,
  });
  const arch = makeArchitecture({
    components: [makeComponent({ id: "a", name: "Alpha" }), makeComponent({ id: "b", name: "Beta" })],
    activity: makeActivity(),
  });
  useArchStore.getState().setArchitecture(arch);
}

// One gesture per question id. Each performs the interaction against the real
// store (loading activity through the real code path) and asserts the answer.
const gestures: Record<string, () => Promise<void>> = {
  "look-first": async () => {
    seed();
    useArchStore.getState().setLens("activity");
    await useArchStore.getState().loadActivity();
    // The ranked list opens with the highest-scoring component first.
    expect(useArchStore.getState().getHotspots()[0].id).toBe("a");
  },

  "who-knows": async () => {
    seed();
    await useArchStore.getState().loadActivity();
    const a = useArchStore.getState().getActivityComponent("a")!;
    // Author shares, top contributor first.
    expect(a.authors[0].author_name).toBe("Alice");
    expect(a.authors[0].share).toBeGreaterThanOrEqual(a.authors[1].share);
  },

  "at-risk": async () => {
    seed();
    await useArchStore.getState().loadActivity();
    const b = useArchStore.getState().getActivityComponent("b")!;
    // Knowledge island plus bus factor flag the fragile area.
    expect(b.knowledge_island).toBe(true);
    expect(b.bus_factor).toBeGreaterThanOrEqual(1);
  },

  "changes-with": async () => {
    seed();
    await useArchStore.getState().loadActivity();
    // Focus a hotspot, read its cross-component coupling partners.
    useArchStore.getState().selectComponent("a");
    const coupling = useArchStore.getState().getCouplingForComponent("a");
    expect(coupling.length).toBeGreaterThan(0);
    expect(coupling[0].partnerId).not.toBe("a"); // cross-component
    expect(coupling[0].count).toBe(12);
  },

  "how-alive": async () => {
    seed();
    await useArchStore.getState().loadActivity();
    const compA = useArchStore.getState().getComponentById("a")!;
    const actA = useArchStore.getState().getActivityComponent("a");
    const r = buildRationale(compA, actA);
    // Last change, churn, and lead author flow into the rationale strip (I13).
    expect(r?.lastChange).toBeTypeOf("string");
    expect(r?.churn).toBe(500);
    expect(r?.author).toBe("Alice");
  },
};

describe("Activity lens question gestures (I14)", () => {
  beforeEach(seed);

  for (const q of ACTIVITY_QUESTIONS) {
    it(`answers "${q.question}" via its gesture`, async () => {
      expect(gestures[q.id], `no gesture wired for question "${q.id}"`).toBeTypeOf("function");
      await gestures[q.id]();
    });
  }

  it("covers every documented question with a gesture", () => {
    const documented = ACTIVITY_QUESTIONS.map((q) => q.id).sort();
    const tested = Object.keys(gestures).sort();
    expect(tested).toEqual(documented);
  });
});
