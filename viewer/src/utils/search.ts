import Fuse from "fuse.js";
import type { Architecture, Component, FileInfo, Symbol } from "../types";

export interface SearchResult {
  type: "component" | "file" | "symbol";
  id: string;
  name: string;
  path: string;
  kind: string;
  language?: string;
  componentId?: string;
  score: number;
}

let componentFuse: Fuse<SearchResult> | null = null;
let allResults: SearchResult[] = [];

export function initializeSearch(arch: Architecture) {
  allResults = [];

  // Index components
  function indexComponents(components: Component[]) {
    for (const comp of components) {
      allResults.push({
        type: "component",
        id: comp.id,
        name: comp.name,
        path: comp.path,
        kind: comp.type,
        language: comp.language || undefined,
        score: 0,
      });
      indexComponents(comp.children);
    }
  }
  indexComponents(arch.components);

  // Index files
  for (const file of arch.files) {
    const name = file.path.split("/").pop() || file.path;
    allResults.push({
      type: "file",
      id: file.path,
      name,
      path: file.path,
      kind: file.language,
      language: file.language,
      score: 0,
    });
  }

  // Index symbols
  for (const sym of arch.symbols) {
    allResults.push({
      type: "symbol",
      id: sym.id,
      name: sym.name,
      path: sym.file,
      kind: sym.kind,
      score: 0,
    });
  }

  componentFuse = new Fuse(allResults, {
    keys: [
      { name: "name", weight: 3 },
      { name: "path", weight: 1 },
      { name: "kind", weight: 0.5 },
    ],
    threshold: 0.4,
    includeScore: true,
    minMatchCharLength: 2,
  });
}

export function search(query: string, limit: number = 50): SearchResult[] {
  if (!componentFuse || !query.trim()) return [];

  return componentFuse
    .search(query)
    .slice(0, limit)
    .map((r) => ({
      ...r.item,
      score: r.score ?? 0,
    }));
}
