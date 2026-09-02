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
 * Nothing here imports from viewer/src for DATA. This module reads the shipped
 * artifact exactly as an outside consumer would, so a change to the app that
 * breaks the published contract shows up as a failure rather than being
 * compensated for.
 *
 * The one agreed exception is the lens maturity table (src/utils/lensMaturity.ts),
 * imported below. Which lenses a reader may see is not derivable from the
 * projection alone: a lens the data warrants can still be gated off by its
 * maturity on the resolved channel, and a crawl that did not know that would
 * report a correctly-hidden beta lens as missing every run. The table is data
 * with no behaviour (no React, no store, no DOM), which is what makes it safe
 * to be the exception; the lens definitions read their maturity from it, so it
 * is the source rather than a copy that can drift.
 */

import fs from "node:fs";
import path from "node:path";

import type { APIRequestContext } from "@playwright/test";

import { LENS_MATURITY } from "../../src/utils/lensMaturity";

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

/** One tour exactly as the manifest authored it (I11: order is not re-sorted). */
export interface ExpectedTour {
  id: string;
  title: string;
  stepCount: number;
  /** Step targets in authored order: a component id, or a file path. */
  targets: string[];
  /** Per-step evidence file, null where the step carries none. */
  evidence: (string | null)[];
  /** Provenance says the anchored code has drifted (I5). */
  stale: boolean;
}

/**
 * One row of the entry-point table: what must be reachable, and why.
 *
 * `testIds` is a list rather than one id because an affordance is allowed to
 * move. The front-door work retired the opening band (`showLegacyOpeningBands`
 * is a hard-coded false in App.tsx) and rehomed findings, supply chain, tours,
 * coverage and producer gaps into the workbench trust strip. The predicate this
 * table encodes is "the data warrants a way in", not "this particular banner
 * exists", so a row is satisfied by any of its ids and the finding names them
 * all. Requiring the old id would report a deliberate relocation as a
 * regression, which is the harness telling the product where to put its own
 * buttons.
 */
export interface ExpectedEntry {
  /** The data-testids that would each satisfy this entry.  */
  testIds: string[];
  /** Whether the projection warrants it. */
  expected: boolean;
  /** The predicate in words, so a finding says why it was expected. */
  because: string;
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

  /** The manifest's tours, verbatim and in authored order. */
  tours: ExpectedTour[];
  /** The entry-point table, evaluated against this projection. */
  entryPoints: ExpectedEntry[];
  /** The lens ids the data warrants AND the channel leaves active, in registration order. */
  lensesExpected: string[];
  /** True when the projection carries the sidecars the two newest lenses gate on. */
  hasSupport: boolean;
  hasSecurity: boolean;
  /** Row ids the data names per lens-scoped lens, in manifest order. */
  lensRowIds: Map<string, string[]>;
  /**
   * Per-component facts the detail-tab rules turn on, read from the manifest
   * node (see loadDetail for why the shard is not the authority here).
   */
  tabFacts: Map<string, TabFacts>;
}

/**
 * What the data settles about a component's detail tabs.
 *
 * Each field mirrors one presence rule in DetailPanel.tsx. Fields the data
 * cannot settle are simply absent, and the spec asserts nothing about them:
 * asserting a rule the projection does not decide is how a harness invents
 * failures.
 */
export interface TabFacts {
  /** ai tab iff the component carries ai_enhance. */
  ai: boolean;
  /**
   * docs tab iff docs carries readme, claude_md, architecture_notes, api_docs,
   * changelog, or key_decisions. Source: hasDocsTabContent in DetailPanel.tsx,
   * which exists precisely so the tab never appears only to say it is empty.
   */
  docs: boolean;
  /** testing tab iff testing has test_files > 0 or a named framework. */
  testing: boolean;
  /** actions tab iff the component carries at least one action. */
  actions: boolean;
  /** capabilities tab iff the component node carries capabilities. */
  capabilities: boolean;
  /** data tab iff the node carries data_entities or is named as an accessor. */
  data: boolean;
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
  // The app merges the human-view sidecars onto the architecture before any
  // lens sees it (attachHumanViews in utils/orientation.ts), so by the time
  // the switcher asks, `support` and `security` are ordinary fields. The
  // contract has to ask the same merged question. Reading manifest.json alone
  // judged both lenses unwarranted on every subject that ships the sidecars
  // (VS Code, 2026-09-02: four false findings) and was silent on subjects that
  // do not, which is how it went unnoticed. Both stay optional: a projection
  // generated before the sidecars existed still crawls clean.
  for (const key of ["support", "security"] as const) {
    const sidecar = path.join(dataDir, `${key}.json`);
    if (manifest[key] == null && fs.existsSync(sidecar)) {
      manifest[key] = JSON.parse(fs.readFileSync(sidecar, "utf8"));
    }
  }
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

  // ── The derivations the new specs need ────────────────────────────────────
  const tours = readTours(manifest);
  const lensRowIds = readLensRowIds(manifest);
  const lensesExpected = readLensesExpected(manifest);
  const entryPoints = readEntryPoints(manifest, tours, lensesExpected);
  const tabFacts = readTabFacts(manifest);

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
    tours,
    entryPoints,
    lensesExpected,
    hasSupport: hasSupportEvidence(manifest),
    hasSecurity: hasSecurityEvidence(manifest),
    lensRowIds,
    tabFacts,
  };
}

/**
 * The manifest's tours, verbatim.
 *
 * Verbatim matters: the tour list is authored order (I11), never re-sorted, and
 * the whole point of comparing it is to catch a UI that quietly reorders or
 * drops one. Nothing here ranks or filters.
 */
function readTours(manifest: any): ExpectedTour[] {
  const raw: any[] = Array.isArray(manifest.tours) ? manifest.tours : [];
  return raw
    .filter((t) => t && typeof t.id === "string")
    .map((t) => {
      const steps: any[] = Array.isArray(t.steps) ? t.steps : [];
      return {
        id: String(t.id),
        title: String(t.title ?? t.id),
        stepCount: steps.length,
        targets: steps.map((st) => String(st?.target ?? "")),
        evidence: steps.map((st) =>
          typeof st?.evidence?.file === "string" ? String(st.evidence.file) : null,
        ),
        stale: t.provenance?.stale === true,
      };
    });
}

/**
 * The row ids each lens-scoped lens offers, in MANIFEST order.
 *
 * Deliberately not "the order the panel will show". Every one of these panels
 * ranks and groups its own rows (CAP_KIND_ORDER, rankEntitiesByAccess,
 * RULE_KIND_ORDER, DESIGN_KIND_ORDER), so predicting the first row on screen
 * would mean reimplementing four ranking functions out here, where their drift
 * would be invisible. What the data does settle, and what is worth holding the
 * UI to, is the SET: a row the panel shows that the data never named is the UI
 * inventing content, and that check needs no ordering at all.
 *
 * Flow is the odd one. Its entries are ranked by reachability (rankEntryFlows),
 * and its candidate set is "tab containers, tabs, and screens with no incoming
 * flow edge". Only the flow-bearing component set is reproduced here, which is
 * a superset of the candidates, so an entry outside it is still caught.
 */
function readLensRowIds(manifest: any): Map<string, string[]> {
  const out = new Map<string, string[]>();
  const ids = (arr: unknown, field: string): string[] =>
    Array.isArray(arr)
      ? arr.map((row: any) => row?.[field]).filter((x: any): x is string => typeof x === "string")
      : [];

  const capabilities = ids(manifest.capabilities, "id");
  if (capabilities.length) out.set("capability", capabilities);
  const entities = ids(manifest.data_entities, "id");
  if (entities.length) out.set("data", entities);
  const rules = ids(manifest.rules, "id");
  if (rules.length) out.set("rules", rules);
  const findings = ids(manifest.design_signals?.findings, "id");
  if (findings.length) out.set("design", findings);

  const flow: string[] = [];
  walkComponents(manifest.components, (node) => {
    if (FLOW_COMPONENT_TYPES.has(String(node.type ?? ""))) flow.push(String(node.id));
  });
  if (flow.length) out.set("flow", flow);
  return out;
}

/**
 * Which lenses this projection warrants, in registration order.
 *
 * Each predicate mirrors one lens's `isAvailable`, reimplemented over the
 * manifest rather than imported, for the same reason the rest of this file is:
 * a lens that stops being available because its availability check broke must
 * show up as a mismatch, not be quietly agreed with. The maturity gate is the
 * exception and is read from the shared table.
 *
 * Registration order is lenses/index.ts's import order, which is the order the
 * switcher renders.
 */
const LENS_ORDER = [
  "structure",
  "inventory",
  "activity",
  "flow",
  "capability",
  "data",
  "rules",
  "design",
  "support",
  "security",
] as const;

function readLensesExpected(manifest: any): string[] {
  const channel = crawlChannel();
  const available: Record<string, boolean> = {
    // structure.ts and inventory.ts: isAvailable is () => true.
    structure: true,
    inventory: true,
    // activity.ts: arch.activity != null.
    activity: manifest.activity != null,
    // flow.ts: hasFlowData, reimplemented below.
    flow: hasFlowData(manifest),
    // capability.ts / data.ts: the array is non-empty.
    capability: (manifest.capabilities?.length ?? 0) > 0,
    data: (manifest.data_entities?.length ?? 0) > 0,
    // rules.ts hasRules: non-empty AND at least one rule whose confidence is
    // "certain". The gate is not "are there rows", and the comment in the lens
    // says why: "A system-wide lens must not be built entirely from
    // shape-matched branches. Until the projection carries a calibrated
    // corpus-quality score, one evidence-anchored rule is the minimum honest
    // gate." Reading only the length reported a deliberately withheld lens as
    // missing on a projection with 698 inferred rules and no certain one.
    rules: (manifest.rules ?? []).some((rule: any) => rule?.confidence === "certain"),
    // design.ts: design_signals.findings is non-empty.
    design: (manifest.design_signals?.findings?.length ?? 0) > 0,
    // support.ts hasSupportEvidence: any non-zero count in support.counts.
    support: hasSupportEvidence(manifest),
    // security.ts hasSecurityEvidence: any of five evidence arrays non-empty.
    security: hasSecurityEvidence(manifest),
  };
  return LENS_ORDER.filter((id) => available[id] && maturityActive(id, channel));
}

/**
 * hasSupportEvidence from lenses/support.ts, over the manifest.
 *
 * The sidecars are merged onto the architecture before any lens sees it
 * (attachHumanViews in utils/orientation.ts), and assemble-serve.py derives
 * them beside the projection, so by the time the app asks, `support` and
 * `security` are ordinary architecture fields. Reading the merged manifest here
 * asks the same question the lens does.
 */
function hasSupportEvidence(manifest: any): boolean {
  const counts = manifest.support?.counts;
  return Boolean(counts && Object.values(counts).some((c) => (c as number) > 0));
}

/** hasSecurityEvidence from lenses/security.ts, over the manifest. */
function hasSecurityEvidence(manifest: any): boolean {
  const security = manifest.security;
  return Boolean(
    security &&
      ((security.mechanisms?.length ?? 0) ||
        (security.credential_configuration?.length ?? 0) ||
        (security.communication_boundaries?.length ?? 0) ||
        (security.sensitive_data_leads?.length ?? 0) ||
        (security.findings?.length ?? 0)),
  );
}

/** The component types that participate in a screen flow (lenses/flow.ts). */
const FLOW_COMPONENT_TYPES = new Set(["screen", "tab", "tab-container"]);
/** The relationship types the analyzer emits for UI navigation (lenses/flow.ts). */
const FLOW_EDGE_TYPES = new Set(["navigation", "tab", "modal", "embed"]);

/** hasFlowData from lenses/flow.ts, over the manifest. */
function hasFlowData(manifest: any): boolean {
  const rels: any[] = Array.isArray(manifest.relationships) ? manifest.relationships : [];
  if (rels.some((r) => FLOW_EDGE_TYPES.has(String(r?.type ?? "")))) return true;
  let found = false;
  walkComponents(manifest.components, (node) => {
    if (found) return;
    if (FLOW_COMPONENT_TYPES.has(String(node.type ?? ""))) found = true;
    else if (
      Array.isArray(node.actions) &&
      node.actions.some((a: any) => a?.target_view)
    ) {
      found = true;
    }
  });
  return found;
}

/**
 * The maturity channel the crawl drives the app on.
 *
 * The app resolves it from `?channel=`, defaulting to stable. The crawl never
 * sets that param, so stable is the honest default here; CRAWL_CHANNEL exists
 * so a run that DOES drive a non-default channel can say so rather than
 * reporting every gated lens as missing.
 */
const CHANNEL_ORDER = ["stable", "beta", "experimental"] as const;
type CrawlChannel = (typeof CHANNEL_ORDER)[number];

export function crawlChannel(): CrawlChannel {
  const raw = process.env.CRAWL_CHANNEL;
  return (CHANNEL_ORDER as readonly string[]).includes(raw ?? "")
    ? (raw as CrawlChannel)
    : "stable";
}

/** isMaturityActive from utils/channel.ts, over the shared maturity table. */
function maturityActive(lensId: string, channel: CrawlChannel): boolean {
  const maturity = LENS_MATURITY[lensId] ?? "stable";
  return CHANNEL_ORDER.indexOf(channel) >= CHANNEL_ORDER.indexOf(maturity);
}

/**
 * The entry-point table: which globally reachable surfaces this projection
 * warrants.
 *
 * Both directions are findings. An entry the data warrants and the DOM lacks is
 * a feature the reader cannot get to; an entry the DOM shows that the data does
 * not warrant is an affordance that leads nowhere, which is worse, because the
 * reader believes there is something behind it.
 */
function readEntryPoints(
  manifest: any,
  tours: ExpectedTour[],
  lensesExpected: string[],
): ExpectedEntry[] {
  return [
    {
      testIds: ["tours-entry"],
      expected: tours.length > 0,
      because: `the projection carries ${tours.length} tour(s)`,
    },
    {
      testIds: ["findings-entry"],
      expected: (manifest.findings?.length ?? 0) > 0,
      because: `the projection carries ${manifest.findings?.length ?? 0} finding(s)`,
    },
    {
      testIds: ["supply-chain-entry"],
      expected: manifest.supply_chain != null,
      because: manifest.supply_chain != null
        ? "the projection carries a supply_chain section"
        : "the projection carries no supply_chain section",
    },
    {
      // Producer gaps used to have their own banner. They are now a phrase
      // inside the trust ledger's own button ("N unresolved claims"), which
      // opens the drawer that details them, so either satisfies the predicate.
      testIds: ["gaps-banner", "trust-ledger-entry"],
      expected: Array.isArray(manifest.gaps) && manifest.gaps.length > 0,
      because: `the projection carries ${(manifest.gaps ?? []).length} producer gap(s)`,
    },
    {
      // Same relocation: the coverage ledger reads "N/M files mapped" on the
      // trust ledger button rather than in its own band.
      testIds: ["coverage-badge", "trust-ledger-entry"],
      expected: manifest.coverage != null,
      because: manifest.coverage != null
        ? "the projection carries a coverage ledger"
        : "the projection carries no coverage ledger",
    },
    {
      testIds: ["lens-select"],
      expected: lensesExpected.length > 1,
      because: `${lensesExpected.length} lens(es) are warranted`,
    },
    { testIds: ["search-button"], expected: true, because: "search is always offered" },
    { testIds: ["help-button"], expected: true, because: "help is always offered" },
  ];
}

/**
 * Per-component tab facts, read from the MANIFEST node rather than the detail
 * shard.
 *
 * The design says the shard settles these. On a split projection it does not:
 * data/detail-<id>.json carries files and symbols and nothing else, while every
 * presence rule in DetailPanel.tsx reads the manifest's own component node
 * (component.ai_enhance, component.testing, component.actions,
 * component.capabilities, component.data_entities, component.docs). The
 * manifest is therefore where the rules are settled, and asserting against a
 * shard that holds none of it would have failed every component for a reason
 * that was the harness's.
 *
 * Two tabs are deliberately NOT settled here, and the spec asserts nothing
 * about them:
 *   status  gates on component.live_status, which a static projection never
 *           carries and a live deployment adds at runtime.
 *   files / symbols / overview  always present by construction.
 */
function readTabFacts(manifest: any): Map<string, TabFacts> {
  const accessors = new Set<string>();
  for (const row of manifest.entity_access ?? []) {
    if (typeof row?.accessor_id === "string") accessors.add(row.accessor_id);
  }
  const out = new Map<string, TabFacts>();
  walkComponents(manifest.components, (node) => {
    const docs = node.docs ?? null;
    const testing = node.testing ?? null;
    out.set(String(node.id), {
      ai: Boolean(node.ai_enhance),
      docs: Boolean(
        docs &&
          (docs.readme ||
            docs.claude_md ||
            docs.architecture_notes ||
            docs.api_docs ||
            docs.changelog ||
            (Array.isArray(docs.key_decisions) && docs.key_decisions.length > 0)),
      ),
      testing: Boolean(
        testing &&
          ((testing.test_files ?? 0) > 0 || (testing.test_frameworks?.length ?? 0) > 0),
      ),
      actions: Array.isArray(node.actions) && node.actions.length > 0,
      capabilities: Array.isArray(node.capabilities) && node.capabilities.length > 0,
      data:
        (Array.isArray(node.data_entities) && node.data_entities.length > 0) ||
        accessors.has(String(node.id)),
    });
  });
  return out;
}

/** Pre-order walk of the manifest component tree. */
function walkComponents(nodes: any, visit: (node: any) => void): void {
  for (const node of Array.isArray(nodes) ? nodes : []) {
    if (!node || typeof node.id !== "string") continue;
    visit(node);
    walkComponents(node.children, visit);
  }
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
 * Picking "the biggest" seems obviously right and is a trap. On private large-repository validation corpus the
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

/**
 * isContentBlob from store.ts, over the expectation model: a content-typed
 * component with no code anywhere beneath it. The canvas excludes exactly
 * these and nothing else, so the accounting below skips exactly these.
 */
export function isContentBlob(contract: Contract, id: string): boolean {
  const c = contract.components.get(id);
  if (!c || c.type !== "content") return false;
  return c.childIds.every((childId) => isContentBlob(contract, childId));
}

/**
 * Whether the canvas accounts for a component at the level on screen: it is
 * a node, it is a member of a rendered aggregate, or a descendant of it is
 * (the graph promotes hero children and unwraps wrappers; a descendant on
 * screen is the visible trace of the ancestor).
 */
export function isAccountedFor(
  contract: Contract,
  id: string,
  renderedIds: Set<string>,
  aggregatedIds: Set<string>,
): boolean {
  if (renderedIds.has(id) || aggregatedIds.has(id)) return true;
  const c = contract.components.get(id);
  return (c?.childIds ?? []).some((childId) =>
    isAccountedFor(contract, childId, renderedIds, aggregatedIds),
  );
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
    // The Overview sidecars, loaded through App.tsx's optionalJson helper. They
    // are additive, so a projection generated before they existed 404s on all
    // three by design.
    "/architecture/orientation.json",
    "/architecture/support.json",
    "/architecture/security.json",
    ...extra,
  ];
}

export function componentBudget(): number {
  const raw = process.env.CRAWL_MAX_COMPONENTS;
  if (raw === undefined) return 0;
  const n = Number(raw);
  return Number.isFinite(n) && n >= 0 ? n : 0;
}

/**
 * The chain of component ids from a root down to a deepest component.
 *
 * The drill journey needs a path that actually reaches the bottom of the
 * subject, because the defects worth finding live at depth: shallow drills
 * worked long after depth 5 did not (see the README's second finding). Ties at
 * the maximum depth break by id so the same subject always walks the same path
 * and two runs are comparable.
 *
 * Returned root first, deepest last, INCLUDING the deepest component itself.
 * The caller drills every element except the last (drilling into a leaf shows
 * an empty level, which is the app's own documented behaviour, not a defect).
 */
export function pathToDeepest(contract: Contract): ExpectedComponent[] {
  const deepest = [...contract.components.values()]
    .sort((a, b) => b.depth - a.depth || a.id.localeCompare(b.id))[0];
  if (!deepest) return [];
  const chain: ExpectedComponent[] = [];
  let cursor: ExpectedComponent | undefined = deepest;
  while (cursor) {
    chain.unshift(cursor);
    cursor = cursor.parentId ? contract.components.get(cursor.parentId) : undefined;
  }
  return chain;
}

/**
 * The detail shard for a component, fetched over HTTP rather than read off disk.
 *
 * Through the request context on purpose: it is the same fetch the app makes,
 * against the same origin, so it works identically for a locally served root
 * and for a remote deployment where there is no disk to read. A shard that 404s
 * for the app 404s here too, which is the point.
 *
 * Returns null on any non-200 or unparseable body; a missing shard is the
 * caller's finding to name, not this helper's to throw over.
 */
export async function loadDetail(
  request: APIRequestContext,
  componentId: string,
): Promise<{ files: unknown[]; symbols: unknown[] } | null> {
  // Mirrors safeComponentId in src/utils/componentId.ts, which itself mirrors
  // safe_component_id() in analyzer/cli.py. Duplicated rather than imported
  // because it is the shipped file-naming convention, and a change to it that
  // this file did not follow should break the crawl loudly.
  const safeId = componentId.replace(/\//g, "--").replace(/:/g, "__");
  const res = await request.get(`/architecture/data/detail-${safeId}.json`).catch(() => null);
  if (!res || !res.ok()) return null;
  const body = await res.json().catch(() => null);
  if (!body || typeof body !== "object") return null;
  return {
    files: Array.isArray((body as any).files) ? (body as any).files : [],
    symbols: Array.isArray((body as any).symbols) ? (body as any).symbols : [],
  };
}

/**
 * The first row id the DATA names for a lens-scoped lens, or null when the data
 * names none.
 *
 * "First" here means first in the manifest, not first on screen: see
 * readLensRowIds for why predicting the panel's own ranking is not this
 * module's job. Callers that need "the row the reader would click" take the
 * first row from the DOM and then check its id against `lensRowIds`.
 */
export function firstRow(contract: Contract, lens: string): string | null {
  return contract.lensRowIds.get(lens)?.[0] ?? null;
}

/**
 * The Overview's orientation sidecar, fetched over HTTP.
 *
 * Through the request context for the same reason as `loadDetail`: it is the
 * same fetch the app makes, so a local serve root and a remote deployment are
 * one code path and a sidecar that 404s for the app 404s here too.
 *
 * Returns null when the sidecar is absent, and that is not a failure. The app
 * builds a fallback orientation from the architecture when the file is missing
 * (`buildOrientationFallback`), so the Overview still renders; what a test
 * cannot then do is check route availability against authored data, because
 * there is no authored data to check against. The caller says so in a coverage
 * annotation rather than asserting on a document nobody wrote.
 */
export interface ExpectedOrientation {
  questionRoutes: { id: string; available: boolean; target: any }[];
  portraitNodes: { id: string; label: string; stableTargets: string[] }[];
  launchTargets: any[];
  trust: any;
}

export async function loadOrientation(
  request: APIRequestContext,
): Promise<ExpectedOrientation | null> {
  const res = await request.get("/architecture/orientation.json").catch(() => null);
  if (!res || !res.ok()) return null;
  const body = await res.json().catch(() => null);
  if (!body || typeof body !== "object") return null;
  const routes: any[] = Array.isArray((body as any).question_routes)
    ? (body as any).question_routes
    : [];
  const nodes: any[] = Array.isArray((body as any).portrait?.nodes)
    ? (body as any).portrait.nodes
    : [];
  return {
    questionRoutes: routes
      .filter((r) => r && typeof r.id === "string")
      .map((r) => ({ id: String(r.id), available: Boolean(r.available), target: r.target ?? {} })),
    portraitNodes: nodes
      .filter((n) => n && typeof n.id === "string")
      .map((n) => ({
        id: String(n.id),
        label: String(n.label ?? n.id),
        stableTargets: Array.isArray(n.stable_targets)
          ? n.stable_targets.filter((x: unknown): x is string => typeof x === "string")
          : [],
      })),
    launchTargets: Array.isArray((body as any).launch_targets) ? (body as any).launch_targets : [],
    trust: (body as any).trust ?? null,
  };
}

// ── Declared-off parameters ─────────────────────────────────────────────────

/**
 * The parameters file: what this build is KNOWN to have switched off.
 *
 * Discovery stays mechanical. The suite still derives every expectation from
 * the manifest and reads every presence from the DOM, and nothing here adds a
 * hand-written expectation. What it adds is the one fact neither of those two
 * sources can carry: that a feature is absent ON PURPOSE for this build.
 *
 * Without it the only way to stop a deliberately disabled lens reporting as a
 * defect every run is to edit a spec, which is how a suite stops being
 * adaptive. With it, the claim inverts and stays checkable: a declared-off
 * feature that is absent is not a finding, and a declared-off feature that is
 * PRESENT is one, because the build is then not the build it says it is.
 *
 * CRAWL_PARAMS names a JSON file:
 *
 *   { "declared_off": ["lens:design", "entry:tours", "surface:review"],
 *     "notes": "free text, carried into the run record" }
 *
 * Token vocabulary:
 *   lens:<id>        a lens id, as the switcher publishes it
 *   entry:<name>     an entry point, its test id without the -entry suffix
 *   surface:<name>   findings, supply-chain, inventory, review, tours, help,
 *                    search, trust, preferences
 */
export interface CrawlParams {
  declaredOff: Set<string>;
  notes: string;
  /** Where they came from, for the run record. Null when none were given. */
  source: string | null;
}

export function loadParams(): CrawlParams {
  const file = process.env.CRAWL_PARAMS;
  const empty: CrawlParams = { declaredOff: new Set(), notes: "", source: null };
  if (!file) return empty;
  const resolved = path.resolve(file);
  if (!fs.existsSync(resolved)) {
    // Loud, not silent. A parameters file the caller named and the run could
    // not find would otherwise turn every declared-off feature back into a
    // finding, and the run would look like a regression in the product.
    throw new Error(`CRAWL_PARAMS points at ${resolved}, which does not exist`);
  }
  const raw = JSON.parse(fs.readFileSync(resolved, "utf8"));
  const tokens: string[] = Array.isArray(raw?.declared_off)
    ? raw.declared_off.filter((t: unknown): t is string => typeof t === "string")
    : [];
  return {
    declaredOff: new Set(tokens),
    notes: typeof raw?.notes === "string" ? raw.notes : "",
    source: resolved,
  };
}

/** Whether a token is declared off for this build. */
export function isDeclaredOff(params: CrawlParams, token: string): boolean {
  return params.declaredOff.has(token);
}

/** The entry-point token for a row, derived from its first test id. */
export function entryToken(testIds: string[]): string {
  return `entry:${testIds[0].replace(/-entry$/, "")}`;
}
