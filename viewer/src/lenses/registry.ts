/**
 * Lens framework (P6-1, LENS-DESIGN.md sections 3, 4, 8).
 *
 * A lens is one way of engaging the codebase: Structure (how it is organized),
 * and later Flow, Capability, Data, Activity, Rules, Tours, Ask. Each lens
 * selects the nodes and edges the graph renders and ships a documented question
 * list pairing a human question with the gesture that answers it (invariant
 * I14). Lenses self-register into this registry; the switcher and URL state read
 * it. Structure is the only lens registered today; the others register in their
 * own cards (P6-2, P6-3, P6-5 to P6-9).
 */
import type { Architecture, Component, Relationship, AggregateNode } from "../types";

export const DEFAULT_LENS_ID = "structure";

/** The node/edge selection a lens hands to the existing graph pipeline. */
export interface LensGraph {
  nodes: Component[];
  aggregates: AggregateNode[];
  edges: Relationship[];
}

/**
 * The minimal store surface a lens reads. Kept narrow so lenses do not depend on
 * the whole store type and are unit-testable in isolation.
 */
export interface LensContext {
  architecture: Architecture;
  drillLevel: string | null;
  getVisibleComponents: () => Component[];
  getAggregateNodes: () => AggregateNode[];
  getComponentRelationships: () => Relationship[];
}

/** One documented question and the gesture that answers it (I14). */
export interface LensQuestion {
  id: string;
  question: string;
  gesture: string;
}

export interface LensDefinition {
  id: string;
  label: string;
  description: string;
  /** Whether this lens has anything to show for the loaded dataset. */
  isAvailable: (arch: Architecture) => boolean;
  /** Select the nodes and edges the graph renders under this lens. */
  getGraph: (ctx: LensContext) => LensGraph;
  /**
   * The ELK layout direction the graph should use under this lens. Defaults to
   * "DOWN" (the Structure hierarchy); the Flow lens sets "RIGHT" for a
   * left-to-right walkable diagram. Only the graph's layout reads this.
   */
  layoutDirection?: "RIGHT" | "DOWN";
  /** The question-to-gesture list this lens answers (I14). */
  questions: LensQuestion[];
}

const registry = new Map<string, LensDefinition>();

export function registerLens(def: LensDefinition): void {
  registry.set(def.id, def);
}

export function getLens(id: string | null | undefined): LensDefinition | undefined {
  return id ? registry.get(id) : undefined;
}

export function listLenses(): LensDefinition[] {
  return [...registry.values()];
}

/** The lenses that have something to show for this dataset, in registration order. */
export function listAvailableLenses(arch: Architecture | null): LensDefinition[] {
  if (!arch) return [];
  return [...registry.values()].filter((l) => l.isAvailable(arch));
}

/**
 * Resolve a requested lens id to a usable one: the request if it is registered
 * and available for the dataset, otherwise the default (Structure). This keeps
 * an unknown or now-unavailable `?lens=` from breaking the view.
 */
export function resolveLensId(id: string | null | undefined, arch: Architecture | null): string {
  const def = id ? registry.get(id) : undefined;
  if (def && (!arch || def.isAvailable(arch))) return def.id;
  return DEFAULT_LENS_ID;
}
