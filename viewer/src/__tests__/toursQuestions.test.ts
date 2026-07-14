import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import { TOURS_QUESTIONS, isTourStale } from "../tours/model";
import type { Architecture, Component, Tour } from "../types";

// P6-7 / I14: the Tours player answers the L7 question list, and every documented
// question has a gesture exercised against the real store here.

function makeComponent(id: string, children: Component[] = [], files: string[] = []): Component {
  return {
    id, name: id, type: "module", path: id, language: "typescript",
    framework: null, description: null, port: null, children, files,
    entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { typescript: 100 } },
    docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
  };
}

const WALK: Tour = {
  id: "tour:walk", title: "Walk the app", description: "root to ui",
  provenance: { stale: false },
  steps: [
    { target: "app", title: "Root", narration: "start here" },
    { target: "app/ui", title: "UI", narration: "the ui", evidence: { file: "app/ui/View.tsx", line: 5 } },
  ],
};
const STALE_TOUR: Tour = {
  id: "tour:stale", title: "Old walk", description: "drifted",
  provenance: { stale: true },
  steps: [{ target: "app", title: "Root", narration: "start" }],
};

function makeArch(): Architecture {
  return {
    name: "T", description: "", repository: null, generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0", root_path: "/t",
    components: [makeComponent("app", [makeComponent("app/ui", [], ["app/ui/View.tsx"])], ["app/main.ts"])],
    relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 2, total_relationships: 0 },
    tours: [WALK, STALE_TOUR],
  };
}

function resetStore() {
  localStorage.clear();
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [], drillLevel: null,
    detailItem: null, activePanel: null, toursOpen: false, activeTourId: null, tourStep: 0,
  });
}

describe("Tours question list (I14)", () => {
  beforeEach(resetStore);

  const gestures: Record<string, () => void> = {
    // "What walkthroughs exist?" -> the list in authored order with step counts.
    list: () => {
      useArchStore.getState().setArchitecture(makeArch());
      const tours = useArchStore.getState().getTours();
      expect(tours.map((t) => t.id)).toEqual(["tour:walk", "tour:stale"]);
      expect(tours[0].steps.length).toBe(2); // step-count badge source
    },
    // "Walk me through it." -> play the tour, next steps through targets (I12).
    walk: () => {
      useArchStore.getState().setArchitecture(makeArch());
      useArchStore.getState().startTour("tour:walk");
      expect(useArchStore.getState().selectedComponentId).toBe("app");
      useArchStore.getState().tourStepNext();
      expect(useArchStore.getState().selectedComponentId).toBe("app/ui");
    },
    // "Where am I?" -> the progress index tracks the walk.
    where: () => {
      useArchStore.getState().setArchitecture(makeArch());
      useArchStore.getState().startTour("tour:walk");
      useArchStore.getState().tourStepNext();
      expect(useArchStore.getState().tourStep).toBe(1); // "step 2 of N"
    },
    // "Show me the code." -> the step's evidence link file:line.
    code: () => {
      useArchStore.getState().setArchitecture(makeArch());
      const step = useArchStore.getState().getTourById("tour:walk")!.steps[1];
      expect(step.evidence?.file).toBe("app/ui/View.tsx");
      expect(step.evidence?.line).toBe(5);
    },
    // "Is this current?" -> the stale marker on a drifted tour (I5).
    current: () => {
      useArchStore.getState().setArchitecture(makeArch());
      const [walk, stale] = useArchStore.getState().getTours();
      expect(isTourStale(walk)).toBe(false);
      expect(isTourStale(stale)).toBe(true);
    },
  };

  for (const q of TOURS_QUESTIONS) {
    it(`answers: ${q.question}`, () => {
      expect(gestures[q.id]).toBeTypeOf("function");
      gestures[q.id]();
    });
  }

  it("every documented question has a tested gesture and vice-versa (coverage)", () => {
    const documented = new Set(TOURS_QUESTIONS.map((q) => q.id));
    const tested = new Set(Object.keys(gestures));
    expect(tested).toEqual(documented);
  });
});
