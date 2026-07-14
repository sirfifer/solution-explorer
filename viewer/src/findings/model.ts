/**
 * Findings and concerns model (P6-8, LENS-DESIGN.md sections 8, 9, 10).
 *
 * Pure helpers for the ranked findings surface and the concern browser, kept
 * out of the store so they are unit-testable in isolation. The surface itself is
 * NOT a lens: it is a globally reachable ranked surface available whenever the
 * dataset carries findings or concerns (invariant I11 ranked, I15 actionable).
 */
import type { Architecture, Finding, Concern } from "../types";
import type { LensQuestion } from "../lenses/registry";

// The Findings question list (I14), each pairing a section-8 human question with
// the exact gesture the surface uses to answer it. Every id is exercised in
// findingsQuestions.test with a coverage assertion.
export const FINDINGS_QUESTIONS: LensQuestion[] = [
  {
    id: "noticed",
    question: "What did the system notice?",
    gesture:
      "Open the Findings surface: findings are ranked by rank_score, worst first (I11), so 'look here' is the top of the list.",
  },
  {
    id: "confirmed",
    question: "Is it confirmed?",
    gesture:
      "Read the verification-status badge on each finding: an unverified finding is marked unverified and is not presented as established fact (I15, the DeepWiki lesson).",
  },
  {
    id: "where",
    question: "Where exactly?",
    gesture:
      "Expand the finding: each member carries a file:line evidence link that navigates to the exact location.",
  },
  {
    id: "shares-trait",
    question: "What shares this trait?",
    gesture:
      "Open the Concerns tab: a concern lists every member touching the shared cross-cutting concern, expandable to its members with evidence.",
  },
  {
    id: "what-can-i-do",
    question: "What can I do about it?",
    gesture:
      "Use a finding's action affordances: open members (navigate to each), annotate the set (build a selection set and open the set annotation flow), or export a directive (build the set and copy a structured work order for an AI executor).",
  },
];

/** Whether the dataset carries anything for the Findings surface to show. */
export function hasFindingsSurface(arch: Architecture | null): boolean {
  if (!arch) return false;
  return (arch.findings?.length ?? 0) > 0 || (arch.concerns?.length ?? 0) > 0;
}

/**
 * Findings ranked by rank_score descending, ties broken by id (I11). The getter
 * re-sorts rather than trusting projection order, so "look here first" holds even
 * if the projection emitted them unordered.
 */
export function sortFindings(findings: Finding[]): Finding[] {
  return [...findings].sort(
    (a, b) => b.rank_score - a.rank_score || a.id.localeCompare(b.id),
  );
}

/** The distinct finding kinds present, in stable (sorted) order, for the filter. */
export function findingKinds(findings: Finding[]): string[] {
  return [...new Set(findings.map((f) => f.kind))].sort();
}

/** Findings of one kind, or all when kind is null/"all". Preserves input order. */
export function filterFindingsByKind(findings: Finding[], kind: string | null): Finding[] {
  if (!kind || kind === "all") return findings;
  return findings.filter((f) => f.kind === kind);
}

/**
 * The findings touching a component, derived from the finding members'
 * component_id (robust: independent of whether the projection set the
 * per-component `findings` ref). Ranked like the surface.
 */
export function findingsForComponent(findings: Finding[], componentId: string): Finding[] {
  return sortFindings(
    findings.filter((f) => f.members.some((m) => m.component_id === componentId)),
  );
}

/** The concern ids a component belongs to, derived from concern membership. */
export function concernsForComponent(concerns: Concern[], componentId: string): Concern[] {
  return concerns.filter((c) => c.members.some((m) => m.component_id === componentId));
}

/**
 * The representative component id for a finding: the first member carrying a
 * component id. This is where "annotate the set" attaches its single-element
 * annotation today, until true set annotation lands (P6-9).
 */
export function representativeComponentId(finding: Finding): string | null {
  for (const m of finding.members) {
    if (m.component_id) return m.component_id;
  }
  return null;
}

/** A short "file:line" label for a piece of fragment evidence, or the path. */
export function evidenceLabel(ev: {
  file?: string | null;
  line?: number | null;
  path?: string;
}): string {
  if (ev.file) return ev.line ? `${ev.file}:${ev.line}` : ev.file;
  if (ev.path) return ev.path;
  return "";
}
