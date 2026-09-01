import type {
  Architecture,
  Component,
  OrientationProjection,
  SecurityProjection,
  SupportProjection,
} from "../types";

const GROUPS = [
  { id: "experience", label: "Experiences", role: "Client-facing products and user flows" },
  { id: "core", label: "Core system", role: "Application and domain implementation" },
  { id: "services", label: "Services & interfaces", role: "Runtime services and API boundaries" },
  { id: "data", label: "Data & persistence", role: "Models, schemas, stores and migrations" },
  { id: "operations", label: "Operations & tools", role: "Infrastructure and operational tooling" },
] as const;

function flatten(components: Component[]): Component[] {
  return components.flatMap((component) => [component, ...flatten(component.children ?? [])]);
}

function groupFor(component: Component): (typeof GROUPS)[number]["id"] {
  const type = component.type.toLowerCase();
  const searchable = `${component.name} ${component.path} ${component.description ?? ""}`;
  if (["ios-client", "android-client", "mobile-client", "web-client", "desktop-app", "watch-app", "screen", "tab", "tab-container"].includes(type)) return "experience";
  if (/(data|database|model|schema|store|persist|migration)/i.test(searchable)) return "data";
  if (["api-server", "service", "worker", "server"].includes(type)) return "services";
  if (["cli-tool", "infrastructure"].includes(type)) return "operations";
  return "core";
}

/**
 * Deterministic compatibility Overview for projections created before
 * orientation.json. It deliberately makes only count/grouping claims already
 * present in the loaded architecture.
 */
export function buildOrientationFallback(architecture: Architecture): OrientationProjection {
  const components = flatten(architecture.components);
  const grouped = new Map<string, Component[]>();
  const componentGroup = new Map<string, string>();
  for (const component of components) {
    const group = groupFor(component);
    componentGroup.set(component.id, group);
    grouped.set(group, [...(grouped.get(group) ?? []), component]);
  }
  const nodes = GROUPS.flatMap((group) => {
    const members = grouped.get(group.id) ?? [];
    if (!members.length) return [];
    const targets = members.map((component) => component.id).sort();
    return [{
      id: `orientation:${group.id}`,
      label: group.label,
      role: group.role,
      member_count: members.length,
      stable_targets: targets.slice(0, 12),
      target_truncated: targets.length > 12,
      statement_kind: "deterministic_grouping" as const,
    }];
  });
  const edgeCounts = new Map<string, { source: string; target: string; evidence_pairs: [string, string][]; relationship_count: number }>();
  for (const relationship of architecture.relationships) {
    const sourceGroup = componentGroup.get(relationship.source);
    const targetGroup = componentGroup.get(relationship.target);
    if (!sourceGroup || !targetGroup || sourceGroup === targetGroup) continue;
    const key = `${sourceGroup}\0${targetGroup}`;
    const row = edgeCounts.get(key) ?? {
      source: `orientation:${sourceGroup}`,
      target: `orientation:${targetGroup}`,
      evidence_pairs: [],
      relationship_count: 0,
    };
    row.relationship_count += 1;
    if (row.evidence_pairs.length < 8) row.evidence_pairs.push([relationship.source, relationship.target]);
    edgeCounts.set(key, row);
  }
  const coverage = architecture.coverage;
  const parsed = coverage?.summary.parsed ?? 0;
  const gap = coverage
    ? Object.entries(coverage.summary).reduce(
        (sum, [key, count]) => sum + (key === "parsed" || ["binary", "vendored", "generated", "asset", "non-source"].includes(key) ? 0 : count),
        0,
      )
    : 0;
  const percent = coverage ? (parsed + gap === 0 ? 100 : Math.round((parsed / (parsed + gap)) * 1000) / 10) : null;
  const interpreted = architecture.ai_enhance?.summary || architecture.description;

  return {
    schema: "syscorpus.orientation/v1",
    subject: {
      id: architecture.name,
      name: architecture.name,
      kind: architecture.repositories?.length ? "multi-repository solution" : "software system",
      repository: architecture.repository,
      default_branch: architecture.default_branch,
      generated_at: architecture.generated_at,
      analyzer_version: architecture.analyzer_version,
    },
    orientation: {
      deterministic_statement: `${architecture.name} contains ${architecture.stats.total_components} mapped components across ${nodes.length} system areas, connected by ${architecture.stats.total_relationships} relationships.`,
      interpreted_statement: interpreted ? {
        text: interpreted,
        status: "interpreted",
        provenance: { stale: false },
      } : null,
      default_path: architecture.tours?.[0]
        ? { kind: "tour", id: architecture.tours[0].id }
        : { kind: "question", id: "organization" },
    },
    portrait: {
      semantic_level: "system",
      method: "deterministic component-type and path grouping (viewer compatibility fallback)",
      nodes,
      edges: [...edgeCounts.values()].sort((a, b) => `${a.source}:${a.target}`.localeCompare(`${b.source}:${b.target}`)),
    },
    question_routes: [
      { id: "organization", label: "How is it organized?", target: { lens: "structure", semantic_level: "system" }, available: true },
      { id: "flow", label: "How does the core experience work?", target: { lens: "flow", tour_id: architecture.tours?.[0]?.id }, available: Boolean(architecture.tours?.length || architecture.relationships.length) },
      { id: "capabilities", label: "What can this system do?", target: { lens: "capability" }, available: Boolean(architecture.capabilities?.length) },
      { id: "data", label: "Where does data live?", target: { lens: "data" }, available: Boolean(architecture.data_entities?.length) },
      { id: "attention", label: "Where should I look first?", target: { surface: "findings" }, available: Boolean(architecture.findings?.length || architecture.gaps?.length) },
      { id: "support", label: "What could make this fail in operation?", target: { lens: "support" }, available: Boolean(architecture.support && Object.values(architecture.support.counts).some((count) => count > 0)) },
      { id: "security", label: "What security mechanisms are visible?", target: { lens: "security" }, available: Boolean(architecture.security && Object.values(architecture.security.counts).some((count) => count > 0)) },
    ],
    trust: {
      source_coverage: { status: !coverage ? "unavailable" : gap ? "has_gaps" : "complete", percent, analyzed: parsed, gaps: gap, target: "coverage.json" },
      interpretation: { status: interpreted ? "present" : "absent", component_count: 0, total_components: components.length },
      producer_gaps: architecture.gaps?.length ?? 0,
      findings: {
        total: architecture.findings?.length ?? 0,
        unverified: architecture.findings?.filter((finding) => finding.verification_status !== "verified").length ?? 0,
      },
      direct_dependencies: architecture.supply_chain?.dependencies.filter((dependency) => dependency.scope === "direct").length ?? 0,
    },
    launch_targets: {
      overview: { mode: "overview" },
      workbench: { mode: "workbench", lens: "structure", semantic_level: "system" },
      search: { mode: "workbench", surface: "search" },
    },
  };
}

export function attachHumanViews(
  architecture: Architecture,
  sidecars: {
    orientation?: OrientationProjection | null;
    support?: SupportProjection | null;
    security?: SecurityProjection | null;
  },
): Architecture {
  const merged: Architecture = {
    ...architecture,
    support: sidecars.support ?? architecture.support,
    security: sidecars.security ?? architecture.security,
  };
  merged.orientation = sidecars.orientation ?? architecture.orientation ?? buildOrientationFallback(merged);
  return merged;
}
