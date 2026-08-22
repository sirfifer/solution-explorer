/**
 * The component-tree collector the focused-graph lenses share. Previously four
 * private copies (capability, data, rules, design) that had to be edited in
 * lockstep; a tree-shape change missed in one silently dropped nodes from that
 * lens's graph.
 */
import type { Component } from "../types";

export function collectComponentsByIds(
  components: Component[],
  ids: Set<string>,
): Component[] {
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
