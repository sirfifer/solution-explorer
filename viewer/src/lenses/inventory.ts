/**
 * Inventory lens (comprehension-study Thrust 2; owner decision 2026-08-17).
 *
 * The first questions every stakeholder asked had correct per-component
 * answers and no aggregate surface: "show me everything critical" and "show me
 * everything this depends on". This lens is that surface, complete for the
 * loaded solution and built to grow into the stakeholder-view roadmap
 * (Security and Supply-chain views reuse the ranked-inventory pattern).
 * Invariant I11: it opens with ranked, bounded lists, never a graph.
 */
import type { Architecture, Component } from "../types";
import { registerLens, type LensDefinition, type LensQuestion } from "./registry";
import { LENS_MATURITY } from "../utils/lensMaturity";

export interface CriticalEntry {
  id: string;
  name: string;
  type: string;
  criticality: "critical" | "important";
  purpose: string | null;
  role: string | null;
}

export interface DependencyEntry {
  name: string;
  category: string;
  /** Ids of the components that use this service, in tree order. */
  componentIds: string[];
  componentNames: string[];
}

export interface PortEntry {
  id: string;
  name: string;
  type: string;
  port: number;
}

function walk(components: Component[]): Component[] {
  const out: Component[] = [];
  const visit = (comps: Component[]) => {
    for (const comp of comps) {
      out.push(comp);
      visit(comp.children || []);
    }
  };
  visit(components);
  return out;
}

// Rank weight within a criticality tier (I11: the list must lead with what a
// stakeholder means by "critical piece"). Servers, clients, and data stores
// outrank internal modules; screens and tabs sink to the bottom even when the
// enrichment tagged them critical.
const TYPE_RANK: Record<string, number> = {
  "api-server": 0, "service": 0, "infrastructure": 0,
  "ios-client": 1, "android-client": 1, "mobile-client": 1,
  "web-client": 1, "desktop-app": 1, "watch-app": 1, "cli-tool": 1,
  "application": 2, "package": 3, "library": 3, "module": 3,
  "screen": 8, "tab-container": 8, "tab": 8,
};

function typeRank(type: string): number {
  return TYPE_RANK[type] ?? 5;
}

/** Every component tagged critical or important: critical first, then within a
 * tier by type weight (servers and clients before modules before screens),
 * then tree order. Empty when the dataset carries no criticality data. */
export function collectCriticalComponents(arch: Architecture): CriticalEntry[] {
  const entries: Array<CriticalEntry & { order: number }> = [];
  let order = 0;
  for (const comp of walk(arch.components)) {
    const ai = comp.ai_enhance;
    if (ai?.criticality !== "critical" && ai?.criticality !== "important") continue;
    entries.push({
      id: comp.id,
      name: comp.name,
      type: comp.type,
      criticality: ai.criticality,
      purpose: ai.description || comp.docs?.purpose || null,
      role: ai.architectural_role || null,
      order: order++,
    });
  }
  entries.sort((a, b) =>
    (a.criticality === b.criticality ? 0 : a.criticality === "critical" ? -1 : 1)
    || typeRank(a.type) - typeRank(b.type)
    || a.order - b.order,
  );
  return entries.map(({ order: _order, ...entry }) => entry);
}

/** Whether the dataset can rank criticality at all (AI-enriched). */
export function hasCriticalityData(arch: Architecture): boolean {
  return walk(arch.components).some((c) => c.ai_enhance?.criticality);
}

/** External services aggregated across all components, most-used first. */
export function collectExternalDependencies(arch: Architecture): DependencyEntry[] {
  const byName = new Map<string, DependencyEntry>();
  for (const comp of walk(arch.components)) {
    for (const svc of comp.external_services || []) {
      let entry = byName.get(svc.name);
      if (!entry) {
        entry = {
          name: svc.name,
          category: svc.category,
          componentIds: [],
          componentNames: [],
        };
        byName.set(svc.name, entry);
      }
      if (!entry.componentIds.includes(comp.id)) {
        entry.componentIds.push(comp.id);
        entry.componentNames.push(comp.name);
      }
    }
  }
  return [...byName.values()].sort(
    (a, b) => b.componentIds.length - a.componentIds.length || a.name.localeCompare(b.name),
  );
}

/** Components that listen on a port, ascending by port number. */
export function collectListeningPorts(arch: Architecture): PortEntry[] {
  return walk(arch.components)
    .filter((c): c is Component & { port: number } => typeof c.port === "number")
    .map((c) => ({ id: c.id, name: c.name, type: c.type, port: c.port }))
    .sort((a, b) => a.port - b.port);
}

export const INVENTORY_QUESTIONS: LensQuestion[] = [
  {
    id: "critical",
    question: "Which components are make-or-break critical?",
    gesture:
      "The Critical list ranks every component tagged critical, then important, each with its one-line purpose. Click a row to see it on the map.",
  },
  {
    id: "dependencies",
    question: "What outside services does this depend on?",
    gesture:
      "The External dependencies list aggregates every detected vendor and service with the components that use it, most-used first.",
  },
  {
    id: "ports",
    question: "What runs where?",
    gesture:
      "The Listening ports list names every component that serves on a port, ascending.",
  },
];

export const inventoryLens: LensDefinition = {
  id: "inventory",
  label: "Inventory",
  maturity: LENS_MATURITY.inventory,
  description:
    "What matters and what it depends on: criticality ranking, external services, and listening ports.",
  // Available for every dataset: dependencies and ports are deterministic;
  // the criticality section states its absence honestly when unenriched.
  isAvailable: () => true,
  getGraph: (ctx) => ({
    nodes: ctx.getVisibleComponents(),
    aggregates: ctx.getAggregateNodes(),
    edges: ctx.getComponentRelationships(),
  }),
  questions: INVENTORY_QUESTIONS,
};

registerLens(inventoryLens);
