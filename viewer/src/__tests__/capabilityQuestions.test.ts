import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import { CAPABILITY_QUESTIONS, groupCapabilitiesByKind, capabilityIsTested } from "../lenses";
import type { Architecture, Component, Capability } from "../types";

// I14: the Capability lens ships a documented question list, and every question's
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
    architecture: null, selectedComponentId: null, breadcrumbs: [], drillLevel: null,
    expandedAggregates: {}, detailItem: null, activePanel: null, lens: "structure",
    selectedCapabilityId: null, selectedEntityId: null, pendingDetailTab: null,
  });
  const svc = makeComponent({ id: "svc", name: "Service", type: "api-server" });
  const capabilities: Capability[] = [
    { id: "cap:svc:api:users", component_id: "svc", kind: "api", name: "read_users",
      detail: { method: "GET", path: "/users", framework: "fastapi", tests: [{ file: "tests/t.py", line: 3, confidence: "inferred" }] },
      evidence: [{ file: "svc/server.py", line: 10, snippet: "@app.get" }], confidence: "certain" },
    { id: "cap:svc:cli:run", component_id: "svc", kind: "cli", name: "run",
      detail: { command: "run" }, evidence: [{ file: "svc/cli.py", line: 4, snippet: "@click" }], confidence: "certain" },
  ];
  useArchStore.getState().setArchitecture(makeArchitecture({ components: [svc], capabilities }));
  useArchStore.getState().setLens("capability");
}

const gestures: Record<string, () => void> = {
  "what-can-it-do": () => {
    seed();
    const groups = groupCapabilitiesByKind(useArchStore.getState().getCapabilities());
    expect(groups.map((g) => g.kind)).toEqual(["api", "cli"]);
  },
  "which-kind": () => {
    seed();
    const cap = useArchStore.getState().getCapabilities().find((c) => c.id === "cap:svc:api:users")!;
    expect(cap.kind).toBe("api");
  },
  "who-owns": () => {
    seed();
    useArchStore.getState().selectCapability("cap:svc:api:users");
    expect(useArchStore.getState().selectedComponentId).toBe("svc");
    expect(useArchStore.getState().pendingDetailTab).toBe("capabilities");
  },
  "is-proven": () => {
    seed();
    const caps = useArchStore.getState().getCapabilities();
    expect(capabilityIsTested(caps.find((c) => c.id === "cap:svc:api:users")!)).toBe(true);
    expect(capabilityIsTested(caps.find((c) => c.id === "cap:svc:cli:run")!)).toBe(false);
  },
  "where-contract": () => {
    seed();
    const cap = useArchStore.getState().getCapabilities().find((c) => c.id === "cap:svc:api:users")!;
    expect(cap.evidence[0].file).toBe("svc/server.py");
    expect(cap.evidence[0].line).toBe(10);
  },
};

describe("Capability lens question gestures (I14)", () => {
  beforeEach(seed);

  for (const q of CAPABILITY_QUESTIONS) {
    it(`answers "${q.question}" via its gesture`, () => {
      expect(gestures[q.id], `no gesture wired for question "${q.id}"`).toBeTypeOf("function");
      gestures[q.id]();
    });
  }

  it("covers every documented question with a gesture", () => {
    expect(Object.keys(gestures).sort()).toEqual(CAPABILITY_QUESTIONS.map((q) => q.id).sort());
  });
});
