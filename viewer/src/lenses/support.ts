import type { Architecture } from "../types";
import { collectComponentsByIds } from "../utils/collectComponents";
import { registerLens, type LensDefinition, type LensQuestion } from "./registry";

export const SUPPORT_QUESTIONS: LensQuestion[] = [
  { id: "attention", question: "What could make this fail in operation?", gesture: "Open a ranked component and inspect its observed reliance." },
  { id: "configuration", question: "What must be configured?", gesture: "Inspect configuration keys and their owning components." },
  { id: "external", question: "What is controlled outside this repository?", gesture: "Follow an external dependency to the component that uses it." },
  { id: "entry", question: "Where would I start from a ticket?", gesture: "Open an entry point and continue to its evidence." },
];

export function hasSupportEvidence(architecture: Architecture): boolean {
  const counts = architecture.support?.counts;
  return Boolean(counts && Object.values(counts).some((count) => count > 0));
}

export const supportLens: LensDefinition = {
  id: "support",
  label: "Support",
  description: "Observed configuration, external reliance, entry points, and data involved in operating the system.",
  isAvailable: hasSupportEvidence,
  getGraph: ({ architecture }) => {
    const support = architecture.support;
    const ids = new Set<string>();
    for (const row of support?.attention ?? []) ids.add(row.component_id);
    for (const row of support?.configuration ?? []) ids.add(row.component_id);
    for (const row of support?.external_dependencies ?? []) ids.add(row.component_id);
    for (const row of support?.entry_points ?? []) if (row.component_id) ids.add(row.component_id);
    for (const row of support?.data_handled ?? []) if (row.component_id) ids.add(row.component_id);
    return {
      nodes: collectComponentsByIds(architecture.components, ids),
      aggregates: [],
      edges: architecture.relationships.filter((edge) => ids.has(edge.source) && ids.has(edge.target)),
    };
  },
  questions: SUPPORT_QUESTIONS,
};

registerLens(supportLens);
