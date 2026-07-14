/**
 * Structure lens (P6-1, LENS-DESIGN.md section 4 L1): "How is it organized?"
 *
 * This is today's drill-down graph, now expressed as a lens. Its node/edge
 * selection is exactly the existing store selectors, so with Structure selected
 * the graph renders identically to before the lens framework existed (the
 * pixel-identical requirement for old data). The question list encodes invariant
 * I14: every question the Structure lens answers is paired with the gesture that
 * answers it, and the gestures are exercised in a test.
 */
import { registerLens, type LensDefinition, type LensQuestion } from "./registry";

// The Structure question list (I14), spanning Sillito's scopes with the gestures
// the viewer supports today. Each id is exercised in lensQuestions.test.
export const STRUCTURE_QUESTIONS: LensQuestion[] = [
  {
    id: "identity",
    question: "What is this component and what does it do?",
    gesture:
      "Select it: the detail panel leads with its identity (name, type, purpose) and the rationale strip.",
  },
  {
    id: "organization",
    question: "How is this part organized, and what is inside it?",
    gesture: "Drill in: its children render as a ranked graph at the next altitude.",
  },
  {
    id: "connections",
    question: "What does this connect to (what it depends on, what uses it)?",
    gesture: "Select it and open Links: incoming and outgoing relationships are listed.",
  },
  {
    id: "hidden",
    question: "What small internal modules are grouped here?",
    gesture: "Expand the aggregate node: its grouped members appear in place.",
  },
  {
    id: "locate",
    question: "Where is the thing that does X?",
    gesture: "Search (Cmd-K): name, description, docstring, and help-text matches, shard-backed.",
  },
  {
    id: "rationale",
    question: "Why is it this way, and who touched it?",
    gesture:
      "Select it: the rationale strip shows intent, ownership, and last change where present (I13).",
  },
];

export const structureLens: LensDefinition = {
  id: "structure",
  label: "Structure",
  description: "How the codebase is organized: containers, components, and their dependencies.",
  // Structure applies to every dataset.
  isAvailable: () => true,
  getGraph: (ctx) => ({
    nodes: ctx.getVisibleComponents(),
    aggregates: ctx.getAggregateNodes(),
    edges: ctx.getComponentRelationships(),
  }),
  questions: STRUCTURE_QUESTIONS,
};

registerLens(structureLens);
