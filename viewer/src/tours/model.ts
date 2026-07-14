/**
 * Tours model (P6-7, LENS-DESIGN.md section 4, L7).
 *
 * Pure helpers for the guided-walkthrough player, kept out of the store so they
 * are unit-testable in isolation. Tours are NOT a lens: like the findings
 * surface they are a globally reachable feature, available whenever the dataset
 * carries tours, that plays an ordered sequence of code-anchored steps. Each step
 * is a highlighted location (selected on stable identity, I12) plus narration;
 * the tour detects its own staleness via content-hash provenance (I5).
 */
import type { Architecture, Tour } from "../types";
import type { LensQuestion } from "../lenses/registry";

// The Tours question list (I14), each pairing an L7 human question with the exact
// gesture the player uses to answer it. Every id is exercised with a coverage
// assertion in toursQuestions.test.
export const TOURS_QUESTIONS: LensQuestion[] = [
  {
    id: "list",
    question: "What walkthroughs exist?",
    gesture:
      "Open the Tours entry point: every tour is listed in authored order (I11) with a step-count badge.",
  },
  {
    id: "walk",
    question: "Walk me through it.",
    gesture:
      "Play a tour: next and previous step through its targets, each selected on stable identity (I12) with its narration in the docked step panel.",
  },
  {
    id: "where",
    question: "Where am I?",
    gesture:
      "The step panel breadcrumbs progress: step X of N, so the reader always knows their place in the walk.",
  },
  {
    id: "code",
    question: "Show me the code.",
    gesture:
      "Each step's evidence link opens the exact file and line the step is anchored to.",
  },
  {
    id: "current",
    question: "Is this current?",
    gesture:
      "A stale marker appears on any tour whose provenance says its anchored code has drifted since it was generated (I5).",
  },
];

/** Whether the dataset carries any tours for the player to show. */
export function hasTours(arch: Architecture | null): boolean {
  if (!arch) return false;
  return (arch.tours?.length ?? 0) > 0;
}

/** The tours as authored (I11: ordered as authored, not re-sorted). */
export function listTours(arch: Architecture | null): Tour[] {
  return arch?.tours ?? [];
}

/**
 * Whether a tour is stale (I5): its provenance marks it stale because the code it
 * is anchored to has drifted since generation. A tour with no provenance is not
 * stale (nothing has claimed drift).
 */
export function isTourStale(tour: Tour): boolean {
  return tour.provenance?.stale === true;
}

/** The number of steps in a tour, for the count badge. */
export function tourStepCount(tour: Tour): number {
  return tour.steps.length;
}
