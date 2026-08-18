import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import { DATA_QUESTIONS, rankEntitiesByAccess, collectEntityAccessors } from "../lenses";
import type { Architecture, Component, DataEntity, EntityAccess } from "../types";

// I14: the Data lens ships a documented question list, and every question's
// gesture is exercised here against the real store with an asserted answer.

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

function seed(): void {
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [], drillLevel: null, detailItem: null, activePanel: null, lens: "structure",
    selectedCapabilityId: null, selectedEntityId: null, pendingDetailTab: null,
  });
  const models = makeComponent({ id: "models", name: "Models", type: "module" });
  const web = makeComponent({ id: "web", name: "Web", type: "service" });
  const admin = makeComponent({ id: "admin", name: "Admin", type: "service" });
  const data_entities: DataEntity[] = [
    { id: "e:user", name: "User", kind: "model", component_id: "models", framework: null,
      fields: [{ name: "id", type: "int" }], evidence: [{ file: "models/user.py", line: 7, snippet: "class User" }] },
  ];
  const entity_access: EntityAccess[] = [
    { accessor_id: "web", entity_id: "e:user", mode: "read", confidence: "certain", evidence: [{ file: "web/x.py", line: 2, snippet: "User.get" }] },
    { accessor_id: "admin", entity_id: "e:user", mode: "write", confidence: "inferred", evidence: [{ file: "admin/y.py", line: 3, snippet: "\"users\"" }] },
  ];
  useArchStore.getState().setArchitecture(makeArchitecture({ components: [models, web, admin], data_entities, entity_access }));
  useArchStore.getState().setLens("data");
}

const gestures: Record<string, () => void> = {
  "what-knows": () => {
    seed();
    const s = useArchStore.getState();
    const groups = rankEntitiesByAccess(s.getDataEntities(), s.getEntityAccess());
    expect(groups.map((g) => g.kind)).toEqual(["model"]);
    expect(groups[0].items[0].name).toBe("User");
  },
  "who-reads": () => {
    seed();
    const reads = collectEntityAccessors("e:user", useArchStore.getState().getEntityAccess()).filter((a) => a.mode === "read");
    expect(reads.map((a) => a.accessorId)).toEqual(["web"]);
  },
  "who-writes": () => {
    seed();
    const writes = collectEntityAccessors("e:user", useArchStore.getState().getEntityAccess()).filter((a) => a.mode === "write");
    expect(writes.map((a) => a.accessorId)).toEqual(["admin"]);
  },
  "how-sure": () => {
    seed();
    const accessors = collectEntityAccessors("e:user", useArchStore.getState().getEntityAccess());
    expect(accessors.find((a) => a.accessorId === "admin")!.confidence).toBe("inferred");
    expect(accessors.find((a) => a.accessorId === "web")!.confidence).toBe("certain");
  },
  "where-defined": () => {
    seed();
    const ent = useArchStore.getState().getDataEntities().find((e) => e.id === "e:user")!;
    expect(ent.evidence[0].file).toBe("models/user.py");
    expect(ent.evidence[0].line).toBe(7);
  },
};

describe("Data lens question gestures (I14)", () => {
  beforeEach(seed);

  for (const q of DATA_QUESTIONS) {
    it(`answers "${q.question}" via its gesture`, () => {
      expect(gestures[q.id], `no gesture wired for question "${q.id}"`).toBeTypeOf("function");
      gestures[q.id]();
    });
  }

  it("covers every documented question with a gesture", () => {
    expect(Object.keys(gestures).sort()).toEqual(DATA_QUESTIONS.map((q) => q.id).sort());
  });
});
