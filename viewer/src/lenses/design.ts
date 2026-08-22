/**
 * Design lens (D4, docs/research/architecture-quality-signals.md Part 3):
 * "Is this architecture any good, and where is it weak?"
 *
 * The eighth lens, joining Structure, Inventory, Flow, Activity, Capability,
 * Data and Rules, and it follows their contract exactly: a ranked panel is the
 * landing surface (invariant I11), each row navigates into the graph with the
 * implicated nodes and edges highlighted, and the lens appears only when the
 * dataset can answer its question.
 *
 * THE TWO-AUDIENCE RULE, which is a build requirement here and not a style
 * note. Every finding renders the plain-language consequence FIRST, the
 * canonical term second as a chip, and a method chip naming its epistemic
 * class. A practitioner recognizes "Dependency cycle" instantly; everyone else
 * reads "these 4 parts are locked together" and needs no prior vocabulary. The
 * machine front door inverts the order for agents. The copy itself comes from
 * the translation table in the research document and is produced by the
 * analyzer, not composed here: the viewer renders `lead` and `term` as given,
 * so the two surfaces cannot drift into different phrasings of the same fact.
 *
 * WHAT THIS LENS DECLINES TO SAY. There is no overall architecture score, no
 * letter grade, and no ranking of one kind of finding against another. Findings
 * are ordered by kind in the panel, which is a presentation order, and by
 * `rank_within_kind` inside a kind, which is the only ranking the data carries.
 * Every panel renders `design_signals.method_caveat` verbatim, because a static
 * graph is not runtime truth.
 *
 * Availability gates on the projected block: a dataset analyzed without
 * --design-signals carries no `design_signals` key and the lens never appears.
 */
import type {
  Architecture,
  Component,
  ComponentDesign,
  DesignFinding,
  Relationship,
} from "../types";
import { collectComponentsByIds } from "../utils/collectComponents";
import { registerLens, type LensDefinition, type LensQuestion } from "./registry";

// The panel order, taken from the ranked-finding list in Part 3 of the research
// document. This is the order a reader meets the findings in, chosen because
// cycles are the least arguable and the most structural. It is deliberately NOT
// a severity ranking: a cycle in a deliberately co-released cluster may be
// fine, and the data carries no cross-kind comparison to justify one.
export const DESIGN_KIND_ORDER: DesignFinding["kind"][] = [
  "cycle",
  "zone_of_pain",
  "stability_inversion",
  "change_coupling",
  "zone_of_uselessness",
  "boundary_strength",
];

// Section headings for each kind. These name the QUESTION the group answers in
// the reader's language; the canonical term rides on each row's chip.
export const DESIGN_KIND_LABEL: Record<DesignFinding["kind"], string> = {
  cycle: "Locked together",
  zone_of_pain: "Load-bearing and rigid",
  stability_inversion: "Standing on shifting ground",
  change_coupling: "Changing together across a boundary",
  zone_of_uselessness: "Flexibility nobody uses",
  boundary_strength: "How the seams are held",
};

// What each method chip says, in the reader's language, plus the tooltip that
// explains the epistemic class. Part 3 requires the chip to name the class.
export const METHOD_LABEL: Record<DesignFinding["method"], string> = {
  "static-graph": "from the code graph",
  "git-history": "from git history",
  "static-graph+git-history": "from the code graph and git history",
};

// True when the dataset carries design signals. Absence hides the lens, which
// is the standing gating principle: a lens only appears when the dataset can
// answer its question.
export function hasDesignSignals(arch: Architecture): boolean {
  return (arch.design_signals?.findings?.length ?? 0) > 0;
}

// The method caveat, read from the payload. Never composed here: the analyzer
// owns the sentence so every surface says the same thing. Empty string when the
// dataset has no signals, and the panel then renders no caveat rather than a
// made-up one.
export function designMethodCaveat(arch: Architecture): string {
  return arch.design_signals?.method_caveat ?? "";
}

// Findings grouped for the panel, in DESIGN_KIND_ORDER, empty groups dropped.
// Within a kind the projection already ordered by rank_within_kind; this sorts
// defensively so a hand-edited or reordered dataset still reads correctly.
export interface DesignFindingGroup {
  kind: DesignFinding["kind"];
  label: string;
  count: number;
  items: DesignFinding[];
}

export function groupDesignFindings(findings: DesignFinding[]): DesignFindingGroup[] {
  return DESIGN_KIND_ORDER.map((kind) => {
    const items = findings
      .filter((f) => f.kind === kind)
      .sort((a, b) => a.rank_within_kind - b.rank_within_kind || a.id.localeCompare(b.id));
    return { kind, label: DESIGN_KIND_LABEL[kind], count: items.length, items };
  }).filter((g) => g.count > 0);
}

export function findDesignFinding(
  arch: Architecture,
  id: string | null | undefined,
): DesignFinding | null {
  if (!id) return null;
  return arch.design_signals?.findings.find((f) => f.id === id) ?? null;
}

// Every component id a finding implicates, including both ends of its edges.
// The graph highlights exactly this set.
export function findingComponentIds(finding: DesignFinding): Set<string> {
  const ids = new Set<string>(finding.targets);
  for (const [source, target] of finding.edges) {
    if (source) ids.add(source);
    if (target) ids.add(target);
  }
  return ids;
}

// Whether a relationship is one of the edges a finding implicates. Used for the
// edge badges and for the focused graph's edge selection.
export function findingImplicatesEdge(
  finding: DesignFinding,
  source: string,
  target: string,
): boolean {
  return finding.edges.some(([s, t]) => s === source && t === target);
}

// --- the abstractness / instability scatter -----------------------------------

// One plotted component. Only components with BOTH ratios known are plotted:
// a component whose abstractness is unmeasurable has no position on this chart,
// and inventing one at the origin would draw it in the zone of pain. The count
// of omitted components is reported beside the chart so the omission is
// declared rather than hidden, which is the lossy-compression rule applied to a
// picture.
export interface ScatterPoint {
  componentId: string;
  name: string;
  // Abstractness, the vertical axis, 0 at the bottom.
  a: number;
  // Instability, the horizontal axis, 0 at the left.
  i: number;
  distance: number;
  zone: "pain" | "uselessness" | "balanced";
}

export interface ScatterData {
  points: ScatterPoint[];
  // How many components could not be plotted because a ratio was unknown.
  omitted: number;
}

// Fallback thresholds mirroring analyzer/derive/design_signals.py, used only
// for datasets projected before the payload carried `zone_thresholds`. Current
// datasets ship the thresholds as data, so the chart shades exactly the
// corners the findings were computed against even if the analyzer retunes
// them; readZoneThresholds resolves payload-first.
export const ZONE_OF_PAIN_MAX_SUM = 0.5;
export const ZONE_OF_USELESSNESS_MIN_SUM = 1.5;

export interface ZoneThresholds {
  painMaxSum: number;
  uselessnessMinSum: number;
}

export function readZoneThresholds(arch: Architecture): ZoneThresholds {
  const t = arch.design_signals?.zone_thresholds;
  return {
    painMaxSum: t?.zone_of_pain_max_sum ?? ZONE_OF_PAIN_MAX_SUM,
    uselessnessMinSum: t?.zone_of_uselessness_min_sum ?? ZONE_OF_USELESSNESS_MIN_SUM,
  };
}

export function zoneFor(
  a: number,
  i: number,
  thresholds?: ZoneThresholds,
): ScatterPoint["zone"] {
  const painMax = thresholds?.painMaxSum ?? ZONE_OF_PAIN_MAX_SUM;
  const uselessnessMin = thresholds?.uselessnessMinSum ?? ZONE_OF_USELESSNESS_MIN_SUM;
  const sum = a + i;
  if (sum <= painMax) return "pain";
  if (sum >= uselessnessMin) return "uselessness";
  return "balanced";
}

export function buildScatter(arch: Architecture): ScatterData {
  const thresholds = readZoneThresholds(arch);
  const points: ScatterPoint[] = [];
  let omitted = 0;
  const walk = (components: Component[]) => {
    for (const comp of components) {
      const design: ComponentDesign | undefined = comp.design;
      if (design) {
        const { abstractness: a, instability: i } = design;
        if (a == null || i == null) {
          omitted += 1;
        } else {
          points.push({
            componentId: comp.id,
            name: comp.name,
            a,
            i,
            distance: design.distance_main_sequence ?? Math.abs(a + i - 1),
            zone: zoneFor(a, i, thresholds),
          });
        }
      }
      walk(comp.children);
    }
  };
  walk(arch.components);
  points.sort((x, y) => y.distance - x.distance || x.componentId.localeCompare(y.componentId));
  return { points, omitted };
}

// --- the graph ----------------------------------------------------------------

// Every component named by any finding. The landing graph, so the reader sees
// the implicated parts of the system rather than a hairball (I11).
export function collectDesignSubjectIds(arch: Architecture): Set<string> {
  const ids = new Set<string>();
  for (const finding of arch.design_signals?.findings ?? []) {
    for (const id of findingComponentIds(finding)) ids.add(id);
  }
  return ids;
}

// The focused graph for one selected finding: the implicated components and the
// relationships among them, so selecting "these 4 are locked together" draws
// exactly that loop. This is the row-to-graph contract every other lens honours.
export function buildDesignFindingGraph(
  arch: Architecture,
  finding: DesignFinding,
): { nodes: Component[]; edges: Relationship[] } {
  const ids = findingComponentIds(finding);
  const nodes = collectComponentsByIds(arch.components, ids);
  // When the finding names specific edges, draw only those; otherwise draw the
  // relationships among the implicated components.
  const edges = finding.edges.length
    ? arch.relationships.filter((r) => findingImplicatesEdge(finding, r.source, r.target))
    : arch.relationships.filter((r) => ids.has(r.source) && ids.has(r.target));
  return { nodes, edges };
}

export function buildDesignLandingGraph(arch: Architecture): {
  nodes: Component[];
  edges: Relationship[];
} {
  const ids = collectDesignSubjectIds(arch);
  const nodes = collectComponentsByIds(arch.components, ids);
  const edges = arch.relationships.filter((r) => ids.has(r.source) && ids.has(r.target));
  return { nodes, edges };
}

// --- blast radius, as an interaction (D5) ---------------------------------------

// The two directions of a blast radius, plus everything else. Computed
// client-side from the edges the viewer already holds, so it works at any drill
// level and on any lens's graph without another projection round trip.
//
// The picture is the point (research document Part 3): dependents shade one way,
// dependencies the other, everything else dims. "If this changes, everything
// shaded could break" is a faster read than any number.
export interface BlastRadius {
  // Transitive dependents: what could break if the focus changes.
  dependents: Set<string>;
  // Transitive dependencies: what the focus itself is standing on.
  dependencies: Set<string>;
}

// Walk one direction of the graph transitively from a starting node. Cycles are
// normal in exactly the graphs this feature is for, so the walk is a visited-set
// traversal and the origin is never included in its own result.
function reachable(
  start: string,
  adjacency: Map<string, string[]>,
): Set<string> {
  const seen = new Set<string>();
  const frontier = [start];
  while (frontier.length > 0) {
    const current = frontier.pop()!;
    for (const next of adjacency.get(current) ?? []) {
      if (next !== start && !seen.has(next)) {
        seen.add(next);
        frontier.push(next);
      }
    }
  }
  return seen;
}

// Build both adjacency maps from a flat edge list. Self-edges are dropped: a
// module that imports itself is a parser artifact, not a blast radius.
export function buildBlastAdjacency(
  edges: { source: string; target: string }[],
): { forward: Map<string, string[]>; reverse: Map<string, string[]> } {
  const forward = new Map<string, string[]>();
  const reverse = new Map<string, string[]>();
  for (const { source, target } of edges) {
    if (!source || !target || source === target) continue;
    // source depends on target, so target changing can break source.
    (forward.get(source) ?? forward.set(source, []).get(source)!).push(target);
    (reverse.get(target) ?? reverse.set(target, []).get(target)!).push(source);
  }
  return { forward, reverse };
}

export function computeBlastRadius(
  focusId: string | null,
  edges: { source: string; target: string }[],
): BlastRadius {
  if (!focusId) return { dependents: new Set(), dependencies: new Set() };
  return blastRadiusFrom(focusId, buildBlastAdjacency(edges));
}

// The same walk over a prebuilt adjacency. The graph memoizes the adjacency on
// its edge set (it does not change between anchor clicks), so each re-anchor
// pays only the two reachable-set walks instead of rebuilding both maps.
export function blastRadiusFrom(
  focusId: string,
  adjacency: { forward: Map<string, string[]>; reverse: Map<string, string[]> },
): BlastRadius {
  return {
    dependents: reachable(focusId, adjacency.reverse),
    dependencies: reachable(focusId, adjacency.forward),
  };
}

// The Design question list (I14). Every id is exercised in designQuestions.test.
export const DESIGN_QUESTIONS: LensQuestion[] = [
  {
    id: "where-is-it-weak",
    question: "Is this architecture any good, and where is it weak?",
    gesture:
      "Open the Design lens: findings are grouped by kind, each stating in plain language what it costs you, with the canonical term on a chip beside it.",
  },
  {
    id: "locked-together",
    question: "Which parts can only change as a unit?",
    gesture:
      "Read the 'Locked together' group: each row is a dependency cycle, and selecting it draws exactly that loop on the graph.",
  },
  {
    id: "load-bearing",
    question: "What is everything leaning on?",
    gesture:
      "Read the 'Load-bearing and rigid' group, or sort the scatter: components low on both abstractness and instability sit in the shaded zone of pain.",
  },
  {
    id: "how-do-we-know",
    question: "How do we know this, and what can the method not see?",
    gesture:
      "Read the method chip on each row (code graph, git history, or both) and the caveat at the foot of the panel, which states what static analysis cannot observe.",
  },
  {
    id: "blast-radius",
    question: "If this changes, what could break?",
    gesture:
      "Select a component and read blast radius on its card, or turn on blast-radius mode to shade every transitive dependent on the graph.",
  },
  {
    id: "seams",
    question: "Are these two parts really separated?",
    gesture:
      "Read the 'How the seams are held' summary: it counts how many seams are convention only versus held by a real network contract.",
  },
];

export const designLens: LensDefinition = {
  id: "design",
  label: "Design",
  description:
    "Where the architecture is weak: parts locked together, load-bearing pieces with no flexibility, and boundaries that history says are drawn in the wrong place.",
  isAvailable: hasDesignSignals,
  getGraph: (ctx) => {
    const finding = findDesignFinding(ctx.architecture, ctx.selectedDesignFindingId);
    if (finding) {
      const { nodes, edges } = buildDesignFindingGraph(ctx.architecture, finding);
      if (nodes.length > 0) return { nodes, aggregates: [], edges };
    }
    const { nodes, edges } = buildDesignLandingGraph(ctx.architecture);
    if (nodes.length > 0) return { nodes, aggregates: [], edges };
    // No finding names a component (say, the only finding is the boundary
    // summary): show the standard visible graph rather than an empty canvas,
    // so the lens still presents the system with its design metrics.
    return {
      nodes: ctx.getVisibleComponents(),
      aggregates: ctx.getAggregateNodes(),
      edges: ctx.getComponentRelationships(),
    };
  },
  questions: DESIGN_QUESTIONS,
};

registerLens(designLens);
