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
import { type Channel, DEFAULT_CHANNEL, isMaturityActive } from "../utils/channel";

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
  // The currently selected capability/entity (P6-3). The Data lens reads
  // selectedEntityId to build the ego view; other lenses ignore these. Optional so
  // existing lenses and callers need not supply them.
  selectedCapabilityId?: string | null;
  selectedEntityId?: string | null;
  // The currently selected rule (P6-6). The Rules lens graph is the rule-owning
  // components regardless of selection, so this is carried for parity and future
  // use; other lenses ignore it. Optional.
  selectedRuleId?: string | null;
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
  /**
   * Maturity gate (card R3). Undefined means "stable" (the default), so every
   * existing lens is stable and unchanged. A lens declared "beta" or
   * "experimental" is filtered out on the default channel and only appears when
   * the resolved channel activates it, rendered with an explicit label. This is
   * the registry's declaration; the URL-param channel decides what is active.
   */
  maturity?: Channel;
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

/**
 * The lenses that have something to show for this dataset AND are active on the
 * resolved maturity channel, in registration order. The channel defaults to
 * "stable" so an existing single-argument caller (and every existing lens, which
 * is stable) is unchanged; a non-stable channel additionally surfaces the beta /
 * experimental lenses it activates (the switcher labels them).
 */
export function listAvailableLenses(
  arch: Architecture | null,
  channel: Channel = DEFAULT_CHANNEL,
): LensDefinition[] {
  if (!arch) return [];
  return [...registry.values()].filter(
    (l) => isMaturityActive(l.maturity, channel) && l.isAvailable(arch),
  );
}

/**
 * Resolve a requested lens id to a usable one: the request if it is registered,
 * active on the resolved channel, and available for the dataset, otherwise the
 * default (Structure). This keeps an unknown, now-unavailable, or
 * channel-gated-off `?lens=` from breaking the view. The channel defaults to
 * "stable" so existing callers are unchanged.
 */
export function resolveLensId(
  id: string | null | undefined,
  arch: Architecture | null,
  channel: Channel = DEFAULT_CHANNEL,
): string {
  const def = id ? registry.get(id) : undefined;
  if (
    def &&
    isMaturityActive(def.maturity, channel) &&
    (!arch || def.isAvailable(arch))
  ) {
    return def.id;
  }
  return DEFAULT_LENS_ID;
}
