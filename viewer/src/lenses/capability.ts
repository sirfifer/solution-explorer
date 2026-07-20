/**
 * Capability lens (P6-3, LENS-DESIGN.md section 4 L2): "What can it do?"
 *
 * Treats capabilities (API operations, CLI commands, events, jobs) as first-class
 * objects: what the system can be asked to do, which kind, who owns it, and, per
 * L2's key finding, whether tests prove it works. The test linkage is the bridge
 * that works: each capability carries `detail.tests` (P5-1 groundwork), so the
 * lens shows "what can it do, is it proven, and where is the contract" in one view.
 *
 * The lens lands on a ranked panel (I11: rank, do not just render) grouping
 * capabilities by kind with counts, each group expandable; the graph is the
 * spatial complement showing the capability-owning components with per-kind count
 * badges. Selecting a capability selects its owning component (I12 stable
 * identity), opens the Capabilities tab, and highlights the entry. The ranking and
 * grouping math lives here so it is testable in isolation; selection lives in the
 * store.
 *
 * Availability gates on capability data (isAvailable): a dataset with no
 * capabilities (a bare architecture, old data) never shows the lens.
 */
import type { Architecture, Capability, Component, Relationship } from "../types";
import { registerLens, type LensDefinition, type LensQuestion } from "./registry";

// The kinds in the order the panel and the graph present them.
export const CAP_KIND_ORDER: Capability["kind"][] = ["api", "cli", "event", "job"];

// True when the dataset carries any capability. Absence hides the lens.
export function hasCapabilities(arch: Architecture): boolean {
  return (arch.capabilities?.length ?? 0) > 0;
}

// A capability is "proven" when the L2 test linkage found at least one test that
// references it (detail.tests non-empty). This is the proof bridge (L2).
export function capabilityIsTested(cap: Capability): boolean {
  return (cap.detail.tests?.length ?? 0) > 0;
}

// The distinct component ids that own at least one capability, in first-seen
// order over the capability list (deterministic, matches projection order).
export function collectCapabilityOwnerIds(caps: Capability[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const c of caps) {
    if (c.component_id && !seen.has(c.component_id)) {
      seen.add(c.component_id);
      out.push(c.component_id);
    }
  }
  return out;
}

// One ranked group of capabilities of a single kind (I11 landing).
export interface CapabilityGroup {
  kind: Capability["kind"];
  items: Capability[];
}

// Group capabilities by kind in CAP_KIND_ORDER; rank within a group by path for
// api (the natural contract key), by name otherwise. Empty groups are dropped so
// the panel shows only kinds that exist. Deterministic: ties fall back to id.
export function groupCapabilitiesByKind(caps: Capability[]): CapabilityGroup[] {
  return CAP_KIND_ORDER.map((kind) => ({
    kind,
    items: caps
      .filter((c) => c.kind === kind)
      .sort((a, b) => {
        // D6: fixture-origin capabilities rank behind product ones (kept, not
        // dropped). Product items always precede test scaffolding within a kind.
        const fa = a.fixture ? 1 : 0;
        const fb = b.fixture ? 1 : 0;
        if (fa !== fb) return fa - fb;
        if (kind === "api") {
          const pa = a.detail.path ?? a.name;
          const pb = b.detail.path ?? b.name;
          if (pa !== pb) return pa.localeCompare(pb);
        } else if (a.name !== b.name) {
          return a.name.localeCompare(b.name);
        }
        return a.id.localeCompare(b.id);
      }),
  })).filter((g) => g.items.length > 0);
}

// Per-component capability counts by kind, for the graph node badges. Only
// components that own a capability appear in the map.
export type CapabilityKindCounts = Record<Capability["kind"], number>;

export function capabilityCountsByComponent(
  caps: Capability[],
): Map<string, CapabilityKindCounts> {
  const map = new Map<string, CapabilityKindCounts>();
  for (const c of caps) {
    if (!c.component_id) continue;
    let counts = map.get(c.component_id);
    if (!counts) {
      counts = { api: 0, cli: 0, event: 0, job: 0 };
      map.set(c.component_id, counts);
    }
    counts[c.kind] += 1;
  }
  return map;
}

// Recursively collect the components whose ids are in `ids`, in pre-order so the
// node order is deterministic and matches the source tree.
function collectComponentsByIds(components: Component[], ids: Set<string>): Component[] {
  const out: Component[] = [];
  const walk = (comps: Component[]) => {
    for (const c of comps) {
      if (ids.has(c.id)) out.push(c);
      walk(c.children);
    }
  };
  walk(components);
  return out;
}

// The graph selection: the capability-owning components (globally, across the
// whole tree) plus the structural relationships among them. Non-owners are not
// drawn; the ranked panel is the entry point, never a hairball (I11).
export function buildCapabilityGraph(arch: Architecture): {
  nodes: Component[];
  edges: Relationship[];
} {
  const ownerIds = new Set(collectCapabilityOwnerIds(arch.capabilities ?? []));
  const nodes = collectComponentsByIds(arch.components, ownerIds);
  const edges = arch.relationships.filter(
    (r) => ownerIds.has(r.source) && ownerIds.has(r.target),
  );
  return { nodes, edges };
}

// The Capability question list (I14). Every id is exercised in
// capabilityQuestions.test.
export const CAPABILITY_QUESTIONS: LensQuestion[] = [
  {
    id: "what-can-it-do",
    question: "What can this system do?",
    gesture:
      "Open the Capability lens: capabilities are grouped by kind (API, CLI, events, jobs) with counts; expand a group to see each operation.",
  },
  {
    id: "which-kind",
    question: "Which kind of capability is this?",
    gesture:
      "Read the group heading: each capability sits under its kind (API operation, CLI command, event, or job).",
  },
  {
    id: "who-owns",
    question: "Which component owns this capability?",
    gesture:
      "Each entry names its owning component; selecting the capability selects that component in the graph and opens its Capabilities tab.",
  },
  {
    id: "is-proven",
    question: "Is this capability proven by tests?",
    gesture:
      "Read the tested/untested badge on the entry: the L2 test linkage marks a capability tested when a test references its route or command.",
  },
  {
    id: "where-contract",
    question: "Where is the contract defined?",
    gesture:
      "Open the Capabilities tab: each capability lists its evidence as file:line with a source link to the defining line.",
  },
];

export const capabilityLens: LensDefinition = {
  id: "capability",
  label: "Capability",
  description:
    "What can it do: API operations, CLI commands, events, and jobs grouped by kind, each owned by a component and proven (or not) by tests.",
  isAvailable: hasCapabilities,
  // The graph shows the capability-owning components with per-kind count badges;
  // the ranked grouping lives in CapabilityPanel. Structure is untouched.
  getGraph: (ctx) => {
    const { nodes, edges } = buildCapabilityGraph(ctx.architecture);
    return { nodes, aggregates: [], edges };
  },
  questions: CAPABILITY_QUESTIONS,
};

registerLens(capabilityLens);
