import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import {
  DEFAULT_LENS_ID,
  listAvailableLenses,
  hasDataEntities,
  accessCountForEntity,
  rankEntitiesByAccess,
  collectEntityAccessors,
  collectEntityOwnerIds,
  buildEntityEgoGraph,
  buildDataLandingGraph,
  READ_EDGE_TYPE,
  WRITE_EDGE_TYPE,
} from "../lenses";
import { parseUrlState, replaceUrlState } from "../utils/urlState";
import type { Architecture, Component, DataEntity, EntityAccess } from "../types";

// P6-3 Data lens: availability gate, ranked-by-access grouping (I11), the ego
// view (owner hub plus accessor spokes with read/write edges, inferred marked),
// cross-lens identity (I12), and URL round-trip. "Who touches this data" is the
// heart, so the accessor collection and the ego edges are exercised directly.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "c", name: "C", type: "module", path: "src/c", language: "python",
    framework: null, description: null, port: null, children: [], files: ["src/c/i.py"],
    entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { python: 100 } },
    docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
    ...overrides,
  };
}

function makeArchitecture(overrides: Partial<Architecture> = {}): Architecture {
  return {
    name: "T", description: "", repository: null, generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0", root_path: "/t", components: [], relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    ...overrides,
  };
}

function entity(overrides: Partial<DataEntity> & Pick<DataEntity, "id" | "name" | "kind" | "component_id">): DataEntity {
  return {
    framework: null, fields: [], evidence: [{ file: "m.py", line: 1, snippet: "class" }],
    ...overrides,
  };
}

function access(accessor_id: string, entity_id: string, mode: EntityAccess["mode"], confidence: EntityAccess["confidence"] = "certain"): EntityAccess {
  return { accessor_id, entity_id, mode, confidence, evidence: [{ file: "u.py", line: 2, snippet: "use" }] };
}

// "models" owns User and Session; "mig" owns an untouched migration table. web
// reads User, admin writes User (inferred), models reads its own User; web reads
// Session. quiet touches nothing.
function makeDataArch(): Architecture {
  const models = makeComponent({ id: "models", name: "Models", type: "module" });
  const web = makeComponent({ id: "web", name: "Web", type: "service" });
  const admin = makeComponent({ id: "admin", name: "Admin", type: "service" });
  const mig = makeComponent({ id: "mig", name: "Migrations", type: "module" });
  const quiet = makeComponent({ id: "quiet", name: "Quiet", type: "module" });
  const data_entities: DataEntity[] = [
    entity({ id: "e:user", name: "User", kind: "model", component_id: "models", fields: [{ name: "id", type: "int" }] }),
    entity({ id: "e:session", name: "Session", kind: "model", component_id: "models" }),
    entity({ id: "e:audit", name: "audit_log", kind: "table", component_id: "mig" }),
  ];
  const entity_access: EntityAccess[] = [
    access("web", "e:user", "read"),
    access("admin", "e:user", "write", "inferred"),
    access("models", "e:user", "read"),
    access("web", "e:session", "read"),
  ];
  return makeArchitecture({
    components: [models, web, admin, mig, quiet],
    relationships: [{ source: "web", target: "models", type: "http", label: null, protocol: "http", port: null, bidirectional: false }],
    data_entities, entity_access,
  });
}

function makeBareArch(): Architecture {
  return makeArchitecture({ components: [makeComponent({ id: "a", name: "A" })] });
}

function resetStore() {
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [],
    drillLevel: null, expandedAggregates: {}, detailItem: null, activePanel: null,
    lens: DEFAULT_LENS_ID, reviewMode: false, flowEntryId: null, flowStep: 0,
    selectedCapabilityId: null, selectedEntityId: null, pendingDetailTab: null,
  });
  replaceUrlState({});
}

describe("Data lens availability (P6-3)", () => {
  beforeEach(resetStore);

  it("is available when the dataset carries data entities", () => {
    expect(hasDataEntities(makeDataArch())).toBe(true);
    expect(listAvailableLenses(makeDataArch()).map((l) => l.id)).toContain("data");
  });

  it("is NOT available on a bare dataset (no data_entities key)", () => {
    const bare = makeBareArch();
    expect(hasDataEntities(bare)).toBe(false);
    expect(listAvailableLenses(bare).map((l) => l.id)).not.toContain("data");
  });

  it("is NOT available when the data_entities key is present but empty", () => {
    expect(hasDataEntities(makeArchitecture({ data_entities: [] }))).toBe(false);
  });
});

describe("Data lens ranked-by-access grouping (I11, P6-3)", () => {
  beforeEach(resetStore);

  it("counts access edges per entity", () => {
    const access = makeDataArch().entity_access!;
    expect(accessCountForEntity("e:user", access)).toBe(3);
    expect(accessCountForEntity("e:session", access)).toBe(1);
    expect(accessCountForEntity("e:audit", access)).toBe(0);
  });

  it("ranks entities by access count within kind groups, most-touched first", () => {
    const arch = makeDataArch();
    const groups = rankEntitiesByAccess(arch.data_entities!, arch.entity_access!);
    expect(groups.map((g) => g.kind)).toEqual(["model", "table"]);
    // User (3 accesses) before Session (1) within the model group.
    expect(groups[0].items.map((e) => e.name)).toEqual(["User", "Session"]);
    expect(groups[1].items.map((e) => e.name)).toEqual(["audit_log"]);
  });

  it("lists entity owners in first-seen order", () => {
    expect(collectEntityOwnerIds(makeDataArch().data_entities!)).toEqual(["models", "mig"]);
  });
});

describe("Data lens who-touches-this (the heart, P6-3)", () => {
  beforeEach(resetStore);

  it("collects accessors reads-first then writes, certain before inferred", () => {
    const access = makeDataArch().entity_access!;
    const accessors = collectEntityAccessors("e:user", access);
    expect(accessors.map((a) => `${a.mode}:${a.accessorId}`)).toEqual([
      "read:models", "read:web", "write:admin",
    ]);
    expect(accessors.find((a) => a.accessorId === "admin")!.confidence).toBe("inferred");
  });
});

describe("Data lens ego view (P6-3)", () => {
  beforeEach(resetStore);

  it("builds the ego graph: owner hub, accessor spokes, read/write edges, inferred marked", () => {
    const arch = makeDataArch();
    const { nodes, edges, ownerId } = buildEntityEgoGraph(arch, "e:user");
    expect(ownerId).toBe("models");
    expect(nodes.map((n) => n.id).sort()).toEqual(["admin", "models", "web"]);

    const readEdge = edges.find((e) => e.source === "web" && e.target === "models")!;
    expect(readEdge.type).toBe(READ_EDGE_TYPE);
    expect(readEdge.label).toBe("User");
    expect(readEdge.ai_enhance?.ai_discovered).toBeUndefined(); // certain, not marked

    const writeEdge = edges.find((e) => e.source === "admin")!;
    expect(writeEdge.type).toBe(WRITE_EDGE_TYPE);
    // Inferred access is marked so the graph can dash it (I3).
    expect(writeEdge.ai_enhance?.ai_discovered).toBe(true);

    // Self-access (owner reads its own entity) is kept as a visible self-edge.
    expect(edges.some((e) => e.source === "models" && e.target === "models")).toBe(true);
  });

  it("getLensGraph returns the ego view when an entity is selected, else the owner graph", () => {
    const arch = makeDataArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("data");

    // Landing (no entity selected): the entity-owning components.
    const landing = useArchStore.getState().getLensGraph();
    expect(landing.nodes.map((n) => n.id).sort()).toEqual(["mig", "models"]);
    expect(buildDataLandingGraph(arch).nodes.map((n) => n.id).sort()).toEqual(["mig", "models"]);

    // Selecting an entity swaps to its ego view.
    useArchStore.getState().selectEntity("e:user");
    const ego = useArchStore.getState().getLensGraph();
    expect(ego.nodes.map((n) => n.id).sort()).toEqual(["admin", "models", "web"]);
    expect(ego.edges.some((e) => e.type === READ_EDGE_TYPE)).toBe(true);
    expect(ego.edges.some((e) => e.type === WRITE_EDGE_TYPE)).toBe(true);
  });
});

describe("Data lens selection and identity (I12, P6-3)", () => {
  beforeEach(resetStore);

  it("selecting an entity focuses its owner and requests the Data tab", () => {
    const arch = makeDataArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("data");
    useArchStore.getState().selectEntity("e:user");
    const s = useArchStore.getState();
    expect(s.selectedEntityId).toBe("e:user");
    expect(s.selectedComponentId).toBe("models");
    expect(s.pendingDetailTab).toBe("data");
  });

  it("preserves the selected component when switching lens (I12)", () => {
    const arch = makeDataArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("data");
    useArchStore.getState().selectEntity("e:user");
    useArchStore.getState().setLens("structure");
    expect(useArchStore.getState().selectedComponentId).toBe("models");
    expect(useArchStore.getState().selectedEntityId).toBe("e:user");
  });

  it("round-trips ?lens=data&entity= through the URL, and gates the param by lens", () => {
    replaceUrlState({ lens: "data", entity: "e:user", component: "models" });
    const parsed = parseUrlState();
    expect(parsed.lens).toBe("data");
    expect(parsed.entity).toBe("e:user");
    expect(parsed.component).toBe("models");
    replaceUrlState({ lens: "structure", entity: "e:user" });
    expect(parseUrlState().entity).toBeUndefined();
  });

  it("resets entity selection on architecture reload", () => {
    useArchStore.getState().setArchitecture(makeDataArch());
    useArchStore.getState().selectEntity("e:user");
    expect(useArchStore.getState().selectedEntityId).toBe("e:user");
    useArchStore.getState().setArchitecture(makeDataArch());
    expect(useArchStore.getState().selectedEntityId).toBeNull();
  });
});
