import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import { hasTours, isTourStale, listTours } from "../tours/model";
import { SAMPLE_FIXTURE_TOURS } from "../tours/fixtureTour";
import type { Architecture, Component, Tour } from "../types";
import sampleManifest from "../../tests/gui/fixtures/march-unamentis-sample/architecture/manifest.json";

// P6-7 Tours player. Regression tests against the REAL store: the player reads
// tours from the projection (architecture.tours), plays them by selecting each
// step's target on stable identity (I12), tracks progress (I11), surfaces
// staleness (I5), and resets on reload. The hand-authored SAMPLE_FIXTURE_TOURS
// prove the player end to end over the explicitly named March test fixture.

function makeComponent(id: string, children: Component[] = [], files: string[] = []): Component {
  return {
    id, name: id, type: "module", path: id, language: "typescript",
    framework: null, description: null, port: null, children, files,
    entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { typescript: 100 } },
    docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
  };
}

function makeArch(tours?: Tour[]): Architecture {
  return {
    name: "T", description: "", repository: null, generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0", root_path: "/t",
    components: [makeComponent("app", [makeComponent("app/ui", [], ["app/ui/View.tsx"]), makeComponent("app/svc")], ["app/main.ts"])],
    relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 3, total_relationships: 0 },
    tours,
  };
}

// A three-step tour over the synthetic arch, plus a stale one-step tour.
const WALK: Tour = {
  id: "tour:walk",
  title: "Walk the app",
  description: "root to ui to svc",
  provenance: { derived_from_commit: "abc", stale: false },
  steps: [
    { target: "app", title: "Root", narration: "start here" },
    { target: "app/ui", title: "UI", narration: "the ui", evidence: { file: "app/ui/View.tsx", line: 5 } },
    { target: "app/svc", title: "Service", narration: "the service" },
  ],
};
const STALE_TOUR: Tour = {
  id: "tour:stale",
  title: "Old walk",
  description: "drifted",
  provenance: { derived_from_commit: "old", stale: true },
  steps: [{ target: "app", title: "Root", narration: "start" }],
};

function reset() {
  localStorage.clear();
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [], drillLevel: null,
    detailItem: null, activePanel: null,
    toursOpen: false, activeTourId: null, tourStep: 0,
  });
}

describe("Tours availability and listing (P6-7, I11)", () => {
  beforeEach(reset);

  it("is available only when the dataset carries tours (degrades like everything else)", () => {
    expect(hasTours(makeArch([WALK]))).toBe(true);
    expect(hasTours(makeArch())).toBe(false);
    expect(hasTours(makeArch([]))).toBe(false);
    expect(hasTours(null)).toBe(false);
  });

  it("lists tours in authored order, not re-sorted (I11)", () => {
    useArchStore.getState().setArchitecture(makeArch([STALE_TOUR, WALK]));
    expect(useArchStore.getState().getTours().map((t) => t.id)).toEqual(["tour:stale", "tour:walk"]);
    expect(listTours(makeArch([WALK, STALE_TOUR])).map((t) => t.id)).toEqual(["tour:walk", "tour:stale"]);
  });
});

describe("Playing a tour selects targets on stable identity (I12)", () => {
  beforeEach(reset);

  it("start lands on step 0 and selects its target", () => {
    useArchStore.getState().setArchitecture(makeArch([WALK]));
    useArchStore.getState().startTour("tour:walk");
    const st = useArchStore.getState();
    expect(st.activeTourId).toBe("tour:walk");
    expect(st.tourStep).toBe(0);
    expect(st.toursOpen).toBe(false); // starting closes the list
    expect(st.selectedComponentId).toBe("app");
  });

  it("next and previous walk the steps, selecting each target", () => {
    useArchStore.getState().setArchitecture(makeArch([WALK]));
    useArchStore.getState().startTour("tour:walk");

    useArchStore.getState().tourStepNext();
    expect(useArchStore.getState().tourStep).toBe(1);
    expect(useArchStore.getState().selectedComponentId).toBe("app/ui"); // nested: drilled + selected

    useArchStore.getState().tourStepNext();
    expect(useArchStore.getState().tourStep).toBe(2);
    expect(useArchStore.getState().selectedComponentId).toBe("app/svc");

    // No-op past the end.
    useArchStore.getState().tourStepNext();
    expect(useArchStore.getState().tourStep).toBe(2);

    useArchStore.getState().tourStepPrev();
    expect(useArchStore.getState().tourStep).toBe(1);
    expect(useArchStore.getState().selectedComponentId).toBe("app/ui");
  });

  it("goToStep jumps directly and clamps out-of-range indices", () => {
    useArchStore.getState().setArchitecture(makeArch([WALK]));
    useArchStore.getState().startTour("tour:walk");
    useArchStore.getState().tourGoToStep(2);
    expect(useArchStore.getState().tourStep).toBe(2);
    useArchStore.getState().tourGoToStep(99);
    expect(useArchStore.getState().tourStep).toBe(2); // clamped to last
    useArchStore.getState().tourGoToStep(-5);
    expect(useArchStore.getState().tourStep).toBe(0); // clamped to first
  });

  it("exit clears the active walk", () => {
    useArchStore.getState().setArchitecture(makeArch([WALK]));
    useArchStore.getState().startTour("tour:walk");
    useArchStore.getState().exitTour();
    expect(useArchStore.getState().activeTourId).toBeNull();
    expect(useArchStore.getState().tourStep).toBe(0);
  });

  it("start is a no-op for an unknown or empty tour", () => {
    useArchStore.getState().setArchitecture(makeArch([WALK, { id: "tour:empty", title: "e", description: "", steps: [] }]));
    useArchStore.getState().startTour("tour:nope");
    expect(useArchStore.getState().activeTourId).toBeNull();
    useArchStore.getState().startTour("tour:empty");
    expect(useArchStore.getState().activeTourId).toBeNull();
  });
});

describe("Staleness (I5)", () => {
  beforeEach(reset);

  it("marks a tour stale only when its provenance says so", () => {
    expect(isTourStale(STALE_TOUR)).toBe(true);
    expect(isTourStale(WALK)).toBe(false);
    // No provenance means nothing has claimed drift.
    expect(isTourStale({ id: "x", title: "x", description: "", steps: [] })).toBe(false);
  });
});

describe("Reset on architecture reload", () => {
  beforeEach(reset);

  it("drops the active walk and closes the list on reload", () => {
    useArchStore.getState().setArchitecture(makeArch([WALK]));
    useArchStore.getState().openTours();
    useArchStore.getState().startTour("tour:walk");
    useArchStore.getState().tourStepNext();
    useArchStore.getState().setArchitecture(makeArch([WALK]));
    const st = useArchStore.getState();
    expect(st.activeTourId).toBeNull();
    expect(st.tourStep).toBe(0);
    expect(st.toursOpen).toBe(false);
  });
});

describe("Hand-authored fixture over the committed sample dataset (end to end)", () => {
  beforeEach(reset);

  it("every fixture step target resolves against the real sample dataset", () => {
    const arch = { ...(sampleManifest as unknown as Architecture), tours: SAMPLE_FIXTURE_TOURS };
    useArchStore.getState().setArchitecture(arch);
    const getComponentById = useArchStore.getState().getComponentById;
    const getComponentByFile = useArchStore.getState().getComponentByFile;
    for (const tour of SAMPLE_FIXTURE_TOURS) {
      for (const step of tour.steps) {
        // A target resolves either as a component id or (for a file-path target)
        // as an owning component, and any evidence file resolves to a component.
        const resolves =
          getComponentById(step.target) !== null || getComponentByFile(step.target) !== null;
        expect(resolves, `step target ${step.target} must resolve`).toBe(true);
        if (step.evidence?.file) {
          expect(getComponentByFile(step.evidence.file), `evidence ${step.evidence.file} must resolve`).not.toBeNull();
        }
      }
    }
  });

  it("plays the onboarding fixture tour end to end, selecting a component at each step", () => {
    const arch = { ...(sampleManifest as unknown as Architecture), tours: SAMPLE_FIXTURE_TOURS };
    useArchStore.getState().setArchitecture(arch);
    expect(hasTours(useArchStore.getState().architecture)).toBe(true);

    useArchStore.getState().startTour("tour:onboarding");
    expect(useArchStore.getState().selectedComponentId).toBe("root");

    const onboarding = SAMPLE_FIXTURE_TOURS[0];
    for (let i = 1; i < onboarding.steps.length; i++) {
      useArchStore.getState().tourStepNext();
      expect(useArchStore.getState().tourStep).toBe(i);
      // Each component-id step lands its exact component selected (I12).
      expect(useArchStore.getState().selectedComponentId).toBe(onboarding.steps[i].target);
    }
  });

  it("the second fixture tour is marked stale (I5)", () => {
    expect(isTourStale(SAMPLE_FIXTURE_TOURS[1])).toBe(true);
    expect(isTourStale(SAMPLE_FIXTURE_TOURS[0])).toBe(false);
  });
});
