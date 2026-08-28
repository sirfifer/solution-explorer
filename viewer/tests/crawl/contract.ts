/**
 * The expectation model: what the DATA says the UI must be able to show.
 *
 * The crawl is adaptive in the sense that it knows nothing about any particular
 * subject before it runs. It does not know how wide or deep the tree is, which
 * lenses the dataset activates, or which tabs a component will offer. All of
 * that is discovered. But discovery from the DOM alone can only ever prove that
 * what is on screen works; it can never notice what is MISSING, which is the
 * defect class that has actually bitten us. So discovery runs from both ends:
 * the projection supplies the ground truth of what should be reachable, and the
 * DOM supplies what is reachable, and the crawl is the comparison.
 *
 * Nothing here imports from viewer/src. This module reads the shipped artifact
 * exactly as an outside consumer would, so a change to the app that breaks the
 * published contract shows up as a failure rather than being compensated for.
 */

import fs from "node:fs";
import path from "node:path";

export interface ExpectedComponent {
  id: string;
  name: string;
  type: string;
  path: string;
  depth: number;
  parentId: string | null;
  childIds: string[];
  fileCount: number;
  symbolCount: number;
  hasAiEnhance: boolean;
}

export interface Contract {
  dataDir: string;
  name: string;
  components: Map<string, ExpectedComponent>;
  rootIds: string[];
  relationships: { source: string; target: string; type: string }[];
  /** Lens-bearing arrays, by manifest key, with the component ids they name. */
  lensComponentIds: Map<string, Set<string>>;
  enrichedShare: number;
  /** True only when a non-public sidecar visibly and exactly discloses a partial overlay. */
  disclosedPartialEvaluation: boolean;
  publicationBanner: string;
  maxDepth: number;
}

function resolveDataDir(): string {
  const explicit = process.env.CRAWL_DATA_DIR;
  if (explicit) return path.resolve(explicit);
  const serveDir = process.env.CRAWL_SERVE_DIR;
  if (serveDir) return path.resolve(serveDir, "architecture");
  throw new Error(
    "no projection to read: set CRAWL_DATA_DIR (the directory holding manifest.json) " +
      "or CRAWL_SERVE_DIR (an assembled serve root)",
  );
}

export function loadContract(): Contract {
  const dataDir = resolveDataDir();
  const manifestPath = path.join(dataDir, "manifest.json");
  if (!fs.existsSync(manifestPath)) {
    throw new Error(
      `no manifest.json at ${manifestPath}. The crawl only covers split-mode ` +
        `projections; a monolith architecture.json has no per-component shards ` +
        `to hold the UI to.`,
    );
  }
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  const index: Record<string, { fileCount?: number; symbolCount?: number }> =
    manifest.component_detail_index ?? {};

  const components = new Map<string, ExpectedComponent>();
  const rootIds: string[] = [];
  let maxDepth = 0;

  const walk = (nodes: any[], parentId: string | null, depth: number) => {
    for (const node of nodes ?? []) {
      if (!node || typeof node.id !== "string") continue;
      const counts = index[node.id] ?? {};
      const children: any[] = Array.isArray(node.children) ? node.children : [];
      components.set(node.id, {
        id: node.id,
        name: String(node.name ?? node.id),
        type: String(node.type ?? "unknown"),
        path: String(node.path ?? ""),
        depth,
        parentId,
        childIds: children.map((c) => c?.id).filter((x: any) => typeof x === "string"),
        fileCount: counts.fileCount ?? (Array.isArray(node.files) ? node.files.length : 0),
        symbolCount: counts.symbolCount ?? 0,
        hasAiEnhance: Boolean(node.ai_enhance),
      });
      if (parentId === null) rootIds.push(node.id);
      maxDepth = Math.max(maxDepth, depth);
      walk(children, node.id, depth + 1);
    }
  };
  walk(manifest.components ?? [], null, 0);

  const lensComponentIds = new Map<string, Set<string>>();
  const collect = (key: string, field: string) => {
    const arr = manifest[key];
    if (!Array.isArray(arr)) return;
    const ids = new Set<string>();
    for (const row of arr) {
      const value = row?.[field];
      if (typeof value === "string") ids.add(value);
    }
    if (ids.size) lensComponentIds.set(key, ids);
  };
  collect("capabilities", "component_id");
  collect("rules", "component_id");
  collect("data_entities", "component_id");
  collect("entity_access", "accessor_id");

  const enriched = [...components.values()].filter((c) => c.hasAiEnhance).length;
  let publication: any = null;
  const publicationPath = path.join(dataDir, "publication.json");
  if (fs.existsSync(publicationPath)) {
    publication = JSON.parse(fs.readFileSync(publicationPath, "utf8"));
  }
  const publicationBanner = String(publication?.header?.banner ?? "");
  const footer = Array.isArray(publication?.footer?.always)
    ? publication.footer.always.filter((x: unknown): x is string => typeof x === "string")
    : [];
  const disclosure = [publicationBanner, ...footer].join(" ").toLowerCase();
  const disclosedPartialEvaluation =
    enriched > 0
    && enriched < components.size
    && publication?.purpose === "evaluation"
    && ["private-preview", "internal"].includes(publication?.access?.visibility)
    && disclosure.includes("partial")
    && disclosure.includes(`${enriched} of ${components.size}`);

  return {
    dataDir,
    name: String(manifest.name ?? "unknown"),
    components,
    rootIds,
    relationships: (manifest.relationships ?? [])
      .filter((r: any) => r && typeof r.source === "string" && typeof r.target === "string")
      .map((r: any) => ({ source: r.source, target: r.target, type: String(r.type ?? "") })),
    lensComponentIds,
    enrichedShare: components.size ? enriched / components.size : 0,
    disclosedPartialEvaluation,
    publicationBanner,
    maxDepth,
  };
}

/**
 * A budget-respecting, deterministic, depth-stratified sample.
 *
 * A full sweep is the default and the right thing for anything under the
 * budget. Above it, sampling takes a proportional slice from every depth band
 * rather than the first N in tree order, because tree order front-loads the
 * shallow nodes and the deep ones are exactly where reachability breaks. The
 * caller is expected to log what was dropped: a silent cap reads as "we covered
 * everything" when it did not.
 */
export function sampleComponents(
  contract: Contract,
  budget: number,
): { chosen: ExpectedComponent[]; dropped: number } {
  const all = [...contract.components.values()].sort((a, b) => a.id.localeCompare(b.id));
  if (budget <= 0 || all.length <= budget) return { chosen: all, dropped: 0 };

  const byDepth = new Map<number, ExpectedComponent[]>();
  for (const c of all) {
    const bucket = byDepth.get(c.depth) ?? [];
    bucket.push(c);
    byDepth.set(c.depth, bucket);
  }
  const chosen: ExpectedComponent[] = [];
  for (const [, bucket] of [...byDepth.entries()].sort((a, b) => a[0] - b[0])) {
    const share = Math.max(1, Math.round((bucket.length / all.length) * budget));
    const stride = Math.max(1, Math.floor(bucket.length / share));
    for (let i = 0; i < bucket.length && chosen.length < budget; i += stride) {
      chosen.push(bucket[i]);
    }
  }
  return { chosen, dropped: all.length - chosen.length };
}

/**
 * A component substantial enough to exercise a surface, without being the one
 * pathological node in the subject.
 *
 * Picking "the biggest" seems obviously right and is a trap. On VS Code the
 * biggest component is src/vs/workbench: 3,625 files and 47,339 symbols in a
 * 50 MB shard, which locks the browser. Every lens then failed for the same
 * reason, and the lens sweep spent its whole budget rediscovering one defect
 * nine times instead of testing nine lenses.
 *
 * So a general-purpose representative is drawn from the upper middle of the
 * distribution: big enough that empty surfaces would be suspicious, nowhere
 * near the tail. The pathological end is not ignored, it gets its own test
 * (see heaviestComponent), where being the worst case is the point.
 */
export function representativeComponent(contract: Contract): ExpectedComponent | null {
  const ranked = [...contract.components.values()]
    .filter((c) => c.fileCount > 0)
    .sort((a, b) => a.fileCount - b.fileCount);
  if (ranked.length === 0) return null;
  return ranked[Math.floor(ranked.length * 0.75)] ?? ranked[ranked.length - 1];
}

/** The heaviest component in the subject, which is the worst case by design. */
export function heaviestComponent(contract: Contract): ExpectedComponent | null {
  const ranked = [...contract.components.values()].sort(
    (a, b) => b.symbolCount - a.symbolCount || b.fileCount - a.fileCount,
  );
  return ranked[0] ?? null;
}

/** Paths that are allowed to 404, mirroring datasets.yaml's probe inventory. */
export function allowedErrorPaths(): string[] {
  const extra = (process.env.CRAWL_ALLOW_ERRORS ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return [
    "/live-config.json",
    "/architecture/publication.json",
    ...extra,
  ];
}

export function componentBudget(): number {
  const raw = process.env.CRAWL_MAX_COMPONENTS;
  if (raw === undefined) return 0;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}
