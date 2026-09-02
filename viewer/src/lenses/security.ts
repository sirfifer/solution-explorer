import type { Architecture } from "../types";
import { collectComponentsByIds } from "../utils/collectComponents";
import { registerLens, type LensDefinition, type LensQuestion } from "./registry";

export const SECURITY_QUESTIONS: LensQuestion[] = [
  { id: "mechanisms", question: "What authentication mechanisms are visible?", gesture: "Inspect a confirmed mechanism and its exact boundary." },
  { id: "boundaries", question: "Which communication boundaries are observable?", gesture: "Compare evidenced transport labels without treating unknown as safe." },
  { id: "credentials", question: "Where are credential inputs referenced?", gesture: "Open the owning component; secret values are never displayed." },
  { id: "unknown", question: "What cannot this repository prove?", gesture: "Read the explicit not-observable ledger before drawing a conclusion." },
];

export function hasSecurityEvidence(architecture: Architecture): boolean {
  const security = architecture.security;
  return Boolean(security && (
    security.mechanisms.length || security.credential_configuration.length ||
    security.communication_boundaries.length || security.sensitive_data_leads.length ||
    security.findings.length
  ));
}

export const securityLens: LensDefinition = {
  id: "security",
  label: "Security",
  description: "Repository-observable security mechanisms, boundaries, leads, and explicit unknowns—not a verdict.",
  isAvailable: hasSecurityEvidence,
  getGraph: ({ architecture }) => {
    const security = architecture.security;
    const ids = new Set<string>();
    for (const row of security?.mechanisms ?? []) { ids.add(row.source); ids.add(row.target); }
    for (const row of security?.communication_boundaries ?? []) { ids.add(row.source); ids.add(row.target); }
    for (const row of security?.credential_configuration ?? []) ids.add(row.component_id);
    for (const row of security?.sensitive_data_leads ?? []) if (row.component_id) ids.add(row.component_id);
    return {
      nodes: collectComponentsByIds(architecture.components, ids),
      aggregates: [],
      edges: architecture.relationships.filter((edge) => ids.has(edge.source) && ids.has(edge.target)),
    };
  },
  questions: SECURITY_QUESTIONS,
};

registerLens(securityLens);
