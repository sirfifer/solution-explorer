/**
 * Data lens (P6-3, LENS-DESIGN.md section 4 L3): "What does it know?"
 *
 * Entities (ORM models, physical tables, migrations, schemas), their fields, and
 * the read/write access edges from the components that touch them. The lens's
 * heart is the question "who touches this data": for any entity, which components
 * read it (green) and which write it (amber), with confidence marked on inferred
 * edges (I3). No incumbent tool serves this below the application level (L3).
 *
 * The lens lands on a ranked panel (I11) of entities ordered by access-edge count
 * (most-touched data first) within kind groups. Selecting an entity focuses its
 * owning component and renders its access graph as an EGO VIEW in the graph: the
 * owner as the hub, its accessor components as spokes, connected by read/write
 * styled edges. The ranking and ego-graph math lives here so it is testable in
 * isolation; selection lives in the store.
 *
 * Availability gates on entity data (isAvailable): a dataset with no data_entities
 * (a bare architecture, old data) never shows the lens.
 */
import type {
  Architecture,
  Component,
  DataEntity,
  EntityAccess,
  Relationship,
} from "../types";
import { registerLens, type LensDefinition, type LensQuestion } from "./registry";

// The kinds in the order the panel presents them, most specific source first.
export const ENTITY_KIND_ORDER: DataEntity["kind"][] = ["model", "table", "migration", "schema"];

// The synthetic edge types used for the ego view, so read/write access renders as
// styled flow edges distinct from structural or communication edges.
export const READ_EDGE_TYPE = "reads";
export const WRITE_EDGE_TYPE = "writes";

// True when the dataset carries any data entity. Absence hides the lens.
export function hasDataEntities(arch: Architecture): boolean {
  return (arch.data_entities?.length ?? 0) > 0;
}

// The distinct component ids that own at least one entity, first-seen order.
export function collectEntityOwnerIds(entities: DataEntity[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const e of entities) {
    if (e.component_id && !seen.has(e.component_id)) {
      seen.add(e.component_id);
      out.push(e.component_id);
    }
  }
  return out;
}

// How many access edges touch an entity (the "most-touched data" rank key, I11).
export function accessCountForEntity(entityId: string, access: EntityAccess[]): number {
  let n = 0;
  for (const a of access) if (a.entity_id === entityId) n++;
  return n;
}

// One ranked group of entities of a single kind (I11 landing). Within the group,
// entities are ordered by access-edge count descending (most-touched first), ties
// by name then id for a stable order.
export interface EntityGroup {
  kind: DataEntity["kind"];
  items: DataEntity[];
}

export function rankEntitiesByAccess(
  entities: DataEntity[],
  access: EntityAccess[],
): EntityGroup[] {
  const countCache = new Map<string, number>();
  const count = (id: string) => {
    let c = countCache.get(id);
    if (c === undefined) {
      c = accessCountForEntity(id, access);
      countCache.set(id, c);
    }
    return c;
  };
  return ENTITY_KIND_ORDER.map((kind) => ({
    kind,
    items: entities
      .filter((e) => e.kind === kind)
      .sort((a, b) => {
        // D6: fixture-origin entities rank behind product ones (kept, not
        // dropped), so real product data is not buried under test scaffolding.
        const fa = a.fixture ? 1 : 0;
        const fb = b.fixture ? 1 : 0;
        if (fa !== fb) return fa - fb;
        const ca = count(a.id);
        const cb = count(b.id);
        if (ca !== cb) return cb - ca;
        if (a.name !== b.name) return a.name.localeCompare(b.name);
        return a.id.localeCompare(b.id);
      }),
  })).filter((g) => g.items.length > 0);
}

// The accessors of an entity: one entry per access edge (a component may read AND
// write, so it can appear twice with different modes). Reads first, then writes;
// within a mode, certain before inferred, then by accessor id (deterministic).
export interface EntityAccessor {
  accessorId: string;
  mode: EntityAccess["mode"];
  confidence: EntityAccess["confidence"];
  evidence: EntityAccess["evidence"];
}

export function collectEntityAccessors(
  entityId: string,
  access: EntityAccess[],
): EntityAccessor[] {
  return access
    .filter((a) => a.entity_id === entityId)
    .map((a) => ({
      accessorId: a.accessor_id,
      mode: a.mode,
      confidence: a.confidence,
      evidence: a.evidence,
    }))
    .sort((a, b) => {
      if (a.mode !== b.mode) return a.mode === "read" ? -1 : 1;
      if (a.confidence !== b.confidence) return a.confidence === "certain" ? -1 : 1;
      return a.accessorId.localeCompare(b.accessorId);
    });
}

// Find a component by id anywhere in the tree.
function findComponentById(components: Component[], id: string): Component | null {
  for (const c of components) {
    if (c.id === id) return c;
    const found = findComponentById(c.children, id);
    if (found) return found;
  }
  return null;
}

// Build the ego view of one entity (I13's "who touches this data"): the owner
// component as the hub plus every accessor component as a spoke, connected by a
// read or write styled edge. Self-access (owner reads/writes its own entity) is
// kept as an edge from the owner to itself so it stays visible. Accessors that do
// not resolve to a component in the tree are skipped (no orphan nodes). The edge
// carries the entity name as its label and its confidence so the graph can mark
// inferred edges (I3).
export function buildEntityEgoGraph(
  arch: Architecture,
  entityId: string,
): { nodes: Component[]; edges: Relationship[]; ownerId: string | null } {
  const entity = (arch.data_entities ?? []).find((e) => e.id === entityId);
  if (!entity) return { nodes: [], edges: [], ownerId: null };
  const access = arch.entity_access ?? [];
  const accessors = collectEntityAccessors(entityId, access);

  const nodeIds = new Set<string>();
  if (entity.component_id) nodeIds.add(entity.component_id);
  for (const a of accessors) nodeIds.add(a.accessorId);

  const nodesById = new Map<string, Component>();
  for (const id of nodeIds) {
    const comp = findComponentById(arch.components, id);
    if (comp) nodesById.set(id, comp);
  }

  const ownerId = entity.component_id && nodesById.has(entity.component_id)
    ? entity.component_id
    : null;

  // Draw an edge from each accessor to the owner (the entity's home). When no
  // owner resolves, fall back to drawing accessors around the first accessor so
  // the ego view still renders (rare; entities always carry an owner in practice).
  const hubId = ownerId ?? accessors.map((a) => a.accessorId).find((id) => nodesById.has(id)) ?? null;

  const edges: Relationship[] = [];
  if (hubId) {
    for (const a of accessors) {
      if (!nodesById.has(a.accessorId)) continue;
      edges.push({
        source: a.accessorId,
        target: hubId,
        type: a.mode === "read" ? READ_EDGE_TYPE : WRITE_EDGE_TYPE,
        label: entity.name,
        protocol: null,
        port: null,
        bidirectional: false,
        // Reuse the AI-discovered dashed style channel to mark inferred edges.
        ai_enhance: a.confidence === "inferred" ? { ai_discovered: true } : undefined,
      });
    }
  }

  return { nodes: [...nodesById.values()], edges, ownerId: hubId };
}

// Recursively collect the components whose ids are in `ids`, pre-order.
function collectComponentsByIds(components: Component[], ids: Set<string>): Component[] {
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

// The landing graph (no entity selected): the entity-owning components globally
// plus the structural relationships among them, parallel to the Capability lens.
export function buildDataLandingGraph(arch: Architecture): {
  nodes: Component[];
  edges: Relationship[];
} {
  const ownerIds = new Set(collectEntityOwnerIds(arch.data_entities ?? []));
  const nodes = collectComponentsByIds(arch.components, ownerIds);
  const edges = arch.relationships.filter(
    (r) => ownerIds.has(r.source) && ownerIds.has(r.target),
  );
  return { nodes, edges };
}

// The Data question list (I14). Every id is exercised in dataQuestions.test.
export const DATA_QUESTIONS: LensQuestion[] = [
  {
    id: "what-knows",
    question: "What data does this system know about?",
    gesture:
      "Open the Data lens: entities are grouped by kind (models, tables, migrations, schemas), ranked by how much they are touched.",
  },
  {
    id: "who-reads",
    question: "Who reads this data?",
    gesture:
      "Focus an entity: the reads list (green) shows every component that reads it, and green edges point to it in the ego view.",
  },
  {
    id: "who-writes",
    question: "Who writes this data?",
    gesture:
      "Focus an entity: the writes list (amber) shows every component that writes it, and amber edges point to it in the ego view.",
  },
  {
    id: "how-sure",
    question: "How sure are we about an access edge?",
    gesture:
      "Read the inferred marker: ORM-class usage is certain; a bare table-name string reference is marked inferred (I3), dashed in the graph.",
  },
  {
    id: "where-defined",
    question: "Where is this entity defined?",
    gesture:
      "Open the Data tab: each entity lists its evidence as file:line with a source link to its declaration.",
  },
];

export const dataLens: LensDefinition = {
  id: "data",
  label: "Data",
  description:
    "What it knows: data entities and who reads and writes them, as an ego view of the components that touch each entity.",
  isAvailable: hasDataEntities,
  // With an entity selected, render its ego view (owner hub plus accessors with
  // read/write edges); otherwise the entity-owning components. The ranked entity
  // list and the who-touches-this detail live in DataPanel. Structure is untouched.
  getGraph: (ctx) => {
    if (ctx.selectedEntityId) {
      const { nodes, edges } = buildEntityEgoGraph(ctx.architecture, ctx.selectedEntityId);
      if (nodes.length > 0) return { nodes, aggregates: [], edges };
    }
    const { nodes, edges } = buildDataLandingGraph(ctx.architecture);
    return { nodes, aggregates: [], edges };
  },
  questions: DATA_QUESTIONS,
};

registerLens(dataLens);
