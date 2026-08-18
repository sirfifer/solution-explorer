import type { Component, Relationship } from "../types";

// The one importance ordering for components at a drill level.
//
// It decides two different things that must never disagree: which components
// survive the node budget and become real nodes (store.ts,
// computeDrillLevelView), and which component the double-tap Read snap frames
// (ArchitectureGraph). It used to live inline in the store; a second copy would
// silently drift, and a snap that framed something other than the most
// important node on screen would read as a bug.
//
// Order: criticality, then how many other components it is wired to, then file
// count, then name for stability. Owner decision 2026-08-17: rank by
// IMPORTANCE, never by size alone.

export function criticalityRank(c: Component): number {
  switch (c.ai_enhance?.criticality) {
    case "critical": return 0;
    case "important": return 1;
    case "supporting": return 3;
    default: return 2; // untagged sits between important and supporting
  }
}

// How many distinct partners each component is wired to. Counted once per
// partner so a chatty pair does not dominate, and self-loops are ignored.
export function buildDegreeIndex(relationships: Relationship[]): Map<string, number> {
  const partners = new Map<string, Set<string>>();
  const add = (a: string, b: string) => {
    let set = partners.get(a);
    if (!set) { set = new Set(); partners.set(a, set); }
    set.add(b);
  };
  for (const rel of relationships) {
    if (rel.source === rel.target) continue;
    add(rel.source, rel.target);
    add(rel.target, rel.source);
  }
  const degree = new Map<string, number>();
  for (const [id, set] of partners) degree.set(id, set.size);
  return degree;
}

// Comparator: most important first.
export function compareByImportance(
  a: Component,
  b: Component,
  degree: Map<string, number>,
): number {
  return criticalityRank(a) - criticalityRank(b)
    || (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0)
    || b.files.length - a.files.length
    || a.name.localeCompare(b.name);
}

// The single most important component of a set, or null for an empty set.
export function mostImportant(
  components: Component[],
  degree: Map<string, number>,
): Component | null {
  let best: Component | null = null;
  for (const c of components) {
    if (best === null || compareByImportance(c, best, degree) < 0) best = c;
  }
  return best;
}
