import type { Tour } from "../types";

/**
 * Hand-authored fixture tours over the committed sample dataset
 * (viewer/public/architecture, the UnaMentis projection). They are NOT committed
 * into the sample dataset itself: tests inject them via the store, and the browser
 * smoke injects them into a local copy of the served manifest. They exercise the
 * player end to end: multi-step walks, component-id and file-path targets,
 * evidence links, and a stale tour (I5) to prove the stale marker.
 *
 * The component ids and files below are lifted from the committed
 * public/architecture/manifest.json; toursFixture.test asserts every target
 * resolves against that real dataset so the fixture cannot silently rot.
 */
export const SAMPLE_FIXTURE_TOURS: Tour[] = [
  {
    id: "tour:onboarding",
    title: "Onboarding: find your way in",
    description: "A four-stop walk from the repo root down into the learning UI.",
    provenance: { derived_from_commit: "fixturecommit0001", stale: false },
    steps: [
      {
        target: "root",
        title: "Start at the repository root",
        narration:
          "This is the whole system at a glance. Everything hangs off this root component; the tour drills into the app from here.",
      },
      {
        target: "unamentis",
        title: "The UnaMentis app",
        narration:
          "The iOS app container. Its children are the UI tabs and the supporting services the tour will visit.",
        evidence: { file: "UnaMentis/AGENTS.md" },
      },
      {
        target: "unamentis/__ui__/tab-bar",
        title: "The tab bar is the app's spine",
        narration:
          "Every screen is reached through this tab bar. UnaMentisApp.swift wires the tabs together.",
        evidence: { file: "UnaMentis/UnaMentisApp.swift", line: 1 },
      },
      {
        target: "unamentis/__ui__/tab-learning",
        title: "The learning tab",
        narration:
          "Where a learner spends most of their time. LearningView.swift is the entry screen for the learning flow.",
        evidence: { file: "UnaMentis/UI/Learning/LearningView.swift", line: 1 },
      },
    ],
  },
  {
    id: "tour:knowledge-bowl",
    title: "Knowledge Bowl training modes",
    description: "A short tour of the Knowledge Bowl feature. Marked stale on purpose.",
    // Marked stale so the player shows the staleness marker (I5).
    provenance: { derived_from_commit: "fixturecommit0000", stale: true },
    steps: [
      {
        target: "unamentis/__ui__/tab-bar",
        title: "Enter through the tab bar",
        narration: "Knowledge Bowl lives behind its own tab; start where the tabs are defined.",
      },
      {
        // A bare file-path target (not a component id): the player resolves it via
        // the file deep link, exercising the non-component navigation branch.
        target: "UnaMentis/UnaMentisApp.swift",
        title: "Where the app is assembled",
        narration:
          "This file wires the whole app together, including the Knowledge Bowl tab. It is the anchor for this walkthrough.",
        evidence: { file: "UnaMentis/UnaMentisApp.swift", line: 1 },
      },
    ],
  },
];
