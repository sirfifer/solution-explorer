/**
 * Flow lens (P6-2, LENS-DESIGN.md section 4 L4): "What happens when...?"
 *
 * Renders navigation as a walkable screen-flow diagram instead of the flat list
 * the Structure lens shows. Screens, tabs, and tab containers become nodes;
 * navigation (push), modal (sheet/fullScreenCover), tab, and embed relationships
 * become directed flow edges with their kind labeled; and UIAction target_view
 * links become flow edges too. That last one is the data the analyzer has
 * modeled but no view has ever drawn (LENS-DESIGN called it out), so the lens
 * surfaces it here.
 *
 * The lens lands on a ranked list of ENTRY FLOWS (I11: rank, do not just render)
 * rather than the full graph: tab containers, tabs, and top-level screens ranked
 * by how many screens they can reach. Selecting one enters "follow" mode, walking
 * the flow step by step (the question grammar's "what happens from here" gesture,
 * with "how did I get here" as the reverse). The follow state lives in the store;
 * the pure graph and ranking math live here so they are testable in isolation.
 *
 * Availability gates on flow-bearing data (isAvailable): a dataset with no
 * screens, tabs, flow edges, or target_view actions (this repo, most backends)
 * never shows the lens. The runtime request-trace variant (OpenTelemetry) and
 * fabricating flows from http edges are deliberately out of scope (L4).
 */
import type { Architecture, Component, Relationship } from "../types";
import { registerLens, type LensDefinition, type LensQuestion } from "./registry";

// The component types that participate in a screen flow.
export const FLOW_COMPONENT_TYPES = new Set(["screen", "tab", "tab-container"]);

// The relationship types the analyzer emits for UI navigation. All are
// structural edges (utils/layout getEdgeCategory), colored per kind.
export const FLOW_EDGE_TYPES = new Set(["navigation", "tab", "modal", "embed"]);

// The synthetic edge type used for UIAction target_view links, so they render as
// flow edges alongside the real navigation relationships.
export const FLOW_ACTION_EDGE_TYPE = "action";

// One reachable flow a reader can start from (I11 landing). `reachableCount`
// counts every distinct flow node reachable from the entry (used for ranking);
// `screenCount` counts only reachable screen-typed nodes (shown to the reader).
export interface FlowEntry {
  id: string;
  name: string;
  type: string;
  reachableCount: number;
  screenCount: number;
}

// Recursively collect every flow-bearing component in the tree, in pre-order so
// the node order is deterministic and matches the source tree.
export function collectFlowComponents(components: Component[]): Component[] {
  const out: Component[] = [];
  const walk = (comps: Component[]) => {
    for (const c of comps) {
      if (FLOW_COMPONENT_TYPES.has(c.type)) out.push(c);
      walk(c.children);
    }
  };
  walk(components);
  return out;
}

// True when the dataset carries anything the Flow lens can draw: a flow edge, a
// flow-typed component, or a UIAction with a target_view. Absence hides the lens.
export function hasFlowData(arch: Architecture): boolean {
  if (arch.relationships.some((r) => FLOW_EDGE_TYPES.has(r.type))) return true;
  let found = false;
  const walk = (comps: Component[]) => {
    for (const c of comps) {
      if (found) return;
      if (FLOW_COMPONENT_TYPES.has(c.type)) {
        found = true;
        return;
      }
      if (c.actions?.some((a) => a.target_view)) {
        found = true;
        return;
      }
      walk(c.children);
    }
  };
  walk(arch.components);
  return found;
}

// The word shown on a flow edge for each kind, answering "what opens this as
// modal vs push" (I14). navigation is a push, modal is a sheet/fullScreenCover.
function edgeKindWord(type: string): string {
  switch (type) {
    case "navigation":
      return "push";
    case "modal":
      return "modal";
    case "tab":
      return "tab";
    case "embed":
      return "embeds";
    case FLOW_ACTION_EDGE_TYPE:
      return "action";
    default:
      return type;
  }
}

// Compose the label a flow edge shows: the kind word, plus the original label
// (a destination name, or a modal's "sheet"/"fullscreen" presentation) when the
// analyzer supplied one. Kept lens-scoped: the returned relationships are clones,
// so the underlying architecture labels are untouched.
function flowEdgeLabel(type: string, original: string | null): string {
  const kind = edgeKindWord(type);
  if (type === "modal" && original) return `${kind} (${original})`;
  if (type === "embed") return kind;
  return original ? `${kind}: ${original}` : kind;
}

// Resolve a UIAction target_view string to a flow component id. The analyzer
// stores target_view as a view identifier or name, so we match, in order: an
// exact id, an exact (case-insensitive) name, then an id whose last path segment
// equals the target. Returns null when nothing resolves (the action is not drawn).
function resolveTargetView(target: string, flowComponents: Component[]): string | null {
  const lower = target.toLowerCase();
  const byId = flowComponents.find((c) => c.id === target);
  if (byId) return byId.id;
  const byName = flowComponents.find((c) => c.name.toLowerCase() === lower);
  if (byName) return byName.id;
  const bySegment = flowComponents.find((c) => {
    const seg = c.id.split("/").pop()?.toLowerCase();
    return seg === lower;
  });
  return bySegment ? bySegment.id : null;
}

// Build the synthetic flow edges for every UIAction target_view that resolves to
// a flow component. This is the modeled-but-never-drawn data (LENS-DESIGN L4).
export function collectActionEdges(
  components: Component[],
  flowComponents: Component[],
): Relationship[] {
  const flowIds = new Set(flowComponents.map((c) => c.id));
  const edges: Relationship[] = [];
  const walk = (comps: Component[]) => {
    for (const c of comps) {
      for (const a of c.actions ?? []) {
        if (!a.target_view) continue;
        const targetId = resolveTargetView(a.target_view, flowComponents);
        // The source must itself be a flow node for the edge to sit in the
        // diagram; otherwise there is no node to draw the tail from.
        if (targetId && flowIds.has(c.id)) {
          edges.push({
            source: c.id,
            target: targetId,
            type: FLOW_ACTION_EDGE_TYPE,
            label: flowEdgeLabel(FLOW_ACTION_EDGE_TYPE, a.label),
            protocol: null,
            port: null,
            bidirectional: false,
          });
        }
      }
      walk(c.children);
    }
  };
  walk(components);
  return edges;
}

// Select the flow edges among flow components: the real navigation/tab/modal/
// embed relationships (cloned with kind-labeled text) plus the synthetic action
// edges. Only edges whose endpoints are both flow nodes are kept.
export function buildFlowEdges(
  arch: Architecture,
  flowComponents: Component[],
): Relationship[] {
  const flowIds = new Set(flowComponents.map((c) => c.id));
  const real = arch.relationships
    .filter((r) => FLOW_EDGE_TYPES.has(r.type) && flowIds.has(r.source) && flowIds.has(r.target))
    .map((r) => ({ ...r, label: flowEdgeLabel(r.type, r.label) }));
  const actions = collectActionEdges(arch.components, flowComponents);
  return [...real, ...actions];
}

// Build a forward adjacency map (source id -> ordered unique target ids) from the
// flow edges, for reachability ranking and the follow walk.
export function buildAdjacency(edges: Relationship[]): Map<string, string[]> {
  const adj = new Map<string, string[]>();
  for (const e of edges) {
    const list = adj.get(e.source) ?? [];
    if (!list.includes(e.target)) list.push(e.target);
    adj.set(e.source, list);
  }
  return adj;
}

// Walk a flow from an entry as a DFS pre-order over outgoing edges, visiting each
// node once. This is the ordered "journey" the follow affordance steps through:
// consecutive steps tend to be one hop deeper (what happens from here), and the
// prefix up to the current step is the breadcrumb (how did I get here).
export function walkFlow(entryId: string, adjacency: Map<string, string[]>): string[] {
  const order: string[] = [];
  const seen = new Set<string>();
  const visit = (id: string) => {
    if (seen.has(id)) return;
    seen.add(id);
    order.push(id);
    for (const next of adjacency.get(id) ?? []) visit(next);
  };
  visit(entryId);
  return order;
}

// Rank the entry flows (I11). Entries are tab containers, tabs, and top-level
// screens (screens with no incoming flow edge), ranked by reachable node count
// descending so the widest journeys (the tab bar, then each tab) land first;
// ties break by name for a stable order.
export function rankEntryFlows(
  flowComponents: Component[],
  edges: Relationship[],
): FlowEntry[] {
  const adjacency = buildAdjacency(edges);
  const typeById = new Map(flowComponents.map((c) => [c.id, c.type]));
  const incoming = new Set(edges.map((e) => e.target));

  const entries: FlowEntry[] = [];
  for (const c of flowComponents) {
    const isRootScreen = c.type === "screen" && !incoming.has(c.id);
    const isContainerOrTab = c.type === "tab-container" || c.type === "tab";
    if (!isRootScreen && !isContainerOrTab) continue;

    const reached = walkFlow(c.id, adjacency);
    let screenCount = 0;
    for (const id of reached) {
      if (id !== c.id && typeById.get(id) === "screen") screenCount++;
    }
    entries.push({
      id: c.id,
      name: c.name,
      type: c.type,
      reachableCount: reached.length - 1,
      screenCount,
    });
  }

  entries.sort((a, b) => b.reachableCount - a.reachableCount || a.name.localeCompare(b.name));
  return entries;
}

// The Flow question list (I14). Every id is exercised in flowQuestions.test.
export const FLOW_QUESTIONS: LensQuestion[] = [
  {
    id: "where-start",
    question: "Where do the journeys start?",
    gesture:
      "Open the Flow lens: entry flows (tab containers, tabs, and top-level screens) are ranked by how many screens they reach; the top of the list is the widest journey.",
  },
  {
    id: "what-next",
    question: "What happens from here?",
    gesture:
      "Follow an entry flow and press Next: the walk steps forward to the next screen the flow reaches, selecting and centering it.",
  },
  {
    id: "how-here",
    question: "How did I get here?",
    gesture:
      "Press Previous while following: the walk steps back along the breadcrumbed path to the screen you came from.",
  },
  {
    id: "modal-or-push",
    question: "What opens this as a modal versus a push?",
    gesture:
      "Read the flow edge label: navigation reads \"push\", a sheet or fullScreenCover reads \"modal\", and a tab selection reads \"tab\".",
  },
  {
    id: "which-tab",
    question: "Which tab owns this screen?",
    gesture:
      "Trace the incoming tab and navigation edges back to their tab: the diagram groups each tab's screens under the tab that reaches them.",
  },
];

export const flowLens: LensDefinition = {
  id: "flow",
  label: "Flow",
  description:
    "What happens when: screens and navigation as a walkable flow diagram, with entry flows ranked and each hop labeled by kind.",
  // Available only when the dataset carries flow-bearing data. Non-UI repos
  // (backends, this repo) have no screens or flow edges, so the lens stays hidden.
  isAvailable: hasFlowData,
  // A left-to-right layered diagram of the flow-bearing components and their
  // navigation/modal/tab/embed and target_view edges, drawn globally (not drill-
  // scoped) so the whole journey stays visible while following it. The Structure
  // lens is untouched: this selection is entirely flow-specific.
  layoutDirection: "RIGHT",
  getGraph: (ctx) => {
    const flowComponents = collectFlowComponents(ctx.architecture.components);
    return {
      nodes: flowComponents,
      aggregates: [],
      edges: buildFlowEdges(ctx.architecture, flowComponents),
    };
  },
  questions: FLOW_QUESTIONS,
};

registerLens(flowLens);
