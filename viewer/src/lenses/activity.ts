/**
 * Activity lens (P6-5, LENS-DESIGN.md section 4 L5): "What is alive here, and
 * who knows it?" Derived entirely from git history (P5-4), so it is
 * language-agnostic and free, which is exactly the unfamiliar-codebase scenario.
 *
 * Three connected views, one entry point (LENS-DESIGN L5):
 *  - Hotspots: components ranked by change frequency times size. The gateway
 *    "where should I look first" view (invariant I11), rendered as the ranked
 *    ActivityPanel list; the graph is the spatial complement with heat encoding.
 *  - Knowledge map: authorship distribution, knowledge islands, and bus factor
 *    at component (team) granularity. Reached by focusing a hotspot.
 *  - Change coupling: what changes together, reached FROM a hotspot, never a
 *    standalone hairball.
 *
 * The lens registers unconditionally but is available only when the dataset
 * carries activity data (isAvailable gate), so it degrades exactly like coverage:
 * a dataset without git history never shows it. Its node/edge selection is
 * Structure's, so the spatial graph stays coherent under the lens; the Activity-
 * specific surfaces (ranking, knowledge, coupling) live in ActivityPanel.
 */
import { registerLens, type LensDefinition, type LensQuestion } from "./registry";

// The Activity question list (I14), each pairing a human question with the exact
// gesture that answers it. Every id is exercised in activityQuestions.test.
export const ACTIVITY_QUESTIONS: LensQuestion[] = [
  {
    id: "look-first",
    question: "Where should I look first?",
    gesture:
      "Open the Activity lens: components are ranked by hotspot score (change frequency times size); the top of the list is where the action is.",
  },
  {
    id: "who-knows",
    question: "Who knows this area?",
    gesture:
      "Focus a hotspot: the knowledge panel shows each author's commit share, top author first.",
  },
  {
    id: "at-risk",
    question: "What is at risk if someone leaves?",
    gesture:
      "Read the knowledge badges: a knowledge-island badge (one author holds >= 95% of commits) and the bus factor flag the fragile areas.",
  },
  {
    id: "changes-with",
    question: "What changes together with this?",
    gesture:
      "Focus a hotspot: the change-coupling list shows the components that most often change in the same commit, cross-component pairs by construction.",
  },
  {
    id: "how-alive",
    question: "How alive is this area?",
    gesture:
      "Select any element: the rationale strip shows its last change, churn, and lead author from git history (I13).",
  },
];

export const activityLens: LensDefinition = {
  id: "activity",
  label: "Activity",
  description:
    "What is alive here and who knows it: hotspots, knowledge map, and change coupling from git history.",
  // Available only when the P5-4 activity pass read git history. P5-4 emits the
  // manifest `activity` summary (split) or the inline `activity` key (monolith)
  // exactly then, so presence == availability; absence hides the lens.
  isAvailable: (arch) => arch.activity != null,
  // The graph is the spatial complement: it renders the current drill level's
  // nodes and edges exactly as Structure does, so navigation stays coherent. The
  // Activity-specific ranking, knowledge, and coupling surfaces live in
  // ActivityPanel, and the graph nodes carry a heat ring under this lens.
  getGraph: (ctx) => ({
    nodes: ctx.getVisibleComponents(),
    aggregates: ctx.getAggregateNodes(),
    edges: ctx.getComponentRelationships(),
  }),
  questions: ACTIVITY_QUESTIONS,
};

registerLens(activityLens);
