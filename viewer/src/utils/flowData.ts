import type { Architecture, Component } from "../types";

// Whether a projection carries anything the Flow lens can draw. A leaf module
// on purpose: lenses/flow.ts registers the lens as a side effect of being
// imported, and registration order is the switcher's order, so nothing outside
// lenses/index.ts may import a lens module. The Overview's fallback
// orientation (utils/orientation.ts) needs this one rule without that side
// effect, and the analyzer mirrors it in analyzer/project/human_views.py.

// The component types that participate in a screen flow.
export const FLOW_COMPONENT_TYPES = new Set(["screen", "tab", "tab-container"]);

// The relationship types the analyzer emits for UI navigation. All are
// structural edges (utils/layout getEdgeCategory), colored per kind.
export const FLOW_EDGE_TYPES = new Set(["navigation", "tab", "modal", "embed"]);

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
