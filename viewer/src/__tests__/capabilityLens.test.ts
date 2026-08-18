import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import {
  DEFAULT_LENS_ID,
  listAvailableLenses,
  hasCapabilities,
  capabilityIsTested,
  collectCapabilityOwnerIds,
  groupCapabilitiesByKind,
  capabilityCountsByComponent,
  buildCapabilityGraph,
} from "../lenses";
import { parseUrlState, replaceUrlState } from "../utils/urlState";
import type { Architecture, Component, Capability } from "../types";

// P6-3 Capability lens: availability gate, ranked grouping by kind (api by path,
// others by name), tested/untested from the L2 test linkage, the owner graph with
// per-kind counts, cross-lens identity (I12), and URL round-trip.

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

function cap(overrides: Partial<Capability> & Pick<Capability, "id" | "kind" | "name" | "component_id">): Capability {
  return {
    detail: {},
    evidence: [{ file: "src/x.py", line: 1, snippet: "code" }],
    confidence: "certain",
    ...overrides,
  };
}

// api "svc" owns two api operations (one tested), one event; cli "tool" owns two
// cli commands and a job; "quiet" owns nothing.
function makeCapArch(): Architecture {
  const svc = makeComponent({ id: "svc", name: "Service", type: "api-server" });
  const tool = makeComponent({ id: "tool", name: "CLI Tool", type: "module" });
  const quiet = makeComponent({ id: "quiet", name: "Quiet", type: "module" });
  const capabilities: Capability[] = [
    // Out of rank order on purpose: /users should sort AFTER /items (api by path).
    // Names deliberately INVERT the path order (alpha_users vs zebra_items) so a
    // name-based sort would flip the result, pinning that api ranks by path.
    cap({ id: "cap:svc:api:users", kind: "api", name: "alpha_users", component_id: "svc",
      detail: { method: "GET", path: "/users", framework: "fastapi", tests: [{ file: "tests/t.py", line: 3, confidence: "inferred" }] } }),
    cap({ id: "cap:svc:api:items", kind: "api", name: "zebra_items", component_id: "svc",
      detail: { method: "GET", path: "/items", framework: "fastapi" } }),
    cap({ id: "cap:svc:event:topic", kind: "event", name: "orders", component_id: "svc",
      detail: { topic: "orders", direction: "publish" }, confidence: "inferred" }),
    // cli names out of order: "analyze" should sort before "build".
    cap({ id: "cap:tool:cli:build", kind: "cli", name: "build", component_id: "tool", detail: { command: "build" } }),
    cap({ id: "cap:tool:cli:analyze", kind: "cli", name: "analyze", component_id: "tool", detail: { command: "analyze" } }),
    cap({ id: "cap:tool:job:nightly", kind: "job", name: "nightly", component_id: "tool",
      detail: { name: "nightly", trigger: "cron" }, confidence: "inferred" }),
  ];
  return makeArchitecture({
    components: [svc, tool, quiet],
    relationships: [{ source: "tool", target: "svc", type: "http", label: "REST", protocol: "http", port: null, bidirectional: false }],
    capabilities,
  });
}

// A bare dataset (this repo, old data): no capabilities key at all.
function makeBareArch(): Architecture {
  return makeArchitecture({ components: [makeComponent({ id: "a", name: "A" })] });
}

function resetStore() {
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [],
    drillLevel: null, detailItem: null, activePanel: null,
    lens: DEFAULT_LENS_ID, reviewMode: false, flowEntryId: null, flowStep: 0,
    selectedCapabilityId: null, selectedEntityId: null, pendingDetailTab: null,
  });
  replaceUrlState({});
}

describe("Capability lens availability (P6-3)", () => {
  beforeEach(resetStore);

  it("is available when the dataset carries capabilities", () => {
    expect(hasCapabilities(makeCapArch())).toBe(true);
    expect(listAvailableLenses(makeCapArch()).map((l) => l.id)).toContain("capability");
  });

  it("is NOT available on a bare dataset (no capabilities key)", () => {
    const bare = makeBareArch();
    expect(hasCapabilities(bare)).toBe(false);
    expect(listAvailableLenses(bare).map((l) => l.id)).not.toContain("capability");
  });

  it("is NOT available when the capabilities key is present but empty", () => {
    const empty = makeArchitecture({ components: [makeComponent()], capabilities: [] });
    expect(hasCapabilities(empty)).toBe(false);
  });
});

describe("Capability lens ranked grouping (I11, P6-3)", () => {
  beforeEach(resetStore);

  it("groups by kind in fixed order and ranks api by path, others by name", () => {
    const groups = groupCapabilitiesByKind(makeCapArch().capabilities!);
    expect(groups.map((g) => g.kind)).toEqual(["api", "cli", "event", "job"]);
    // api ranked by path: /items before /users.
    expect(groups[0].items.map((c) => c.detail.path)).toEqual(["/items", "/users"]);
    // cli ranked by name: analyze before build.
    expect(groups[1].items.map((c) => c.name)).toEqual(["analyze", "build"]);
  });

  it("drops empty kind groups", () => {
    const onlyApi = [makeCapArch().capabilities![0]];
    expect(groupCapabilitiesByKind(onlyApi).map((g) => g.kind)).toEqual(["api"]);
  });

  it("marks tested vs untested from the L2 test linkage", () => {
    const caps = makeCapArch().capabilities!;
    const users = caps.find((c) => c.detail.path === "/users")!;
    const items = caps.find((c) => c.detail.path === "/items")!;
    expect(capabilityIsTested(users)).toBe(true);
    expect(capabilityIsTested(items)).toBe(false);
  });
});

describe("Capability lens graph selection (P6-3)", () => {
  beforeEach(resetStore);

  it("shows only capability-owning components plus edges among them", () => {
    const arch = makeCapArch();
    const { nodes, edges } = buildCapabilityGraph(arch);
    expect(nodes.map((n) => n.id).sort()).toEqual(["svc", "tool"]);
    // The http edge between the two owners is kept; the non-owner "quiet" is absent.
    expect(edges).toHaveLength(1);
    expect(edges[0]).toMatchObject({ source: "tool", target: "svc" });
  });

  it("counts capabilities by kind per owner for the node badges", () => {
    const counts = capabilityCountsByComponent(makeCapArch().capabilities!);
    expect(counts.get("svc")).toEqual({ api: 2, cli: 0, event: 1, job: 0 });
    expect(counts.get("tool")).toEqual({ api: 0, cli: 2, event: 0, job: 1 });
    expect(counts.has("quiet")).toBe(false);
  });

  it("lists capability owners in first-seen order", () => {
    expect(collectCapabilityOwnerIds(makeCapArch().capabilities!)).toEqual(["svc", "tool"]);
  });

  it("getLensGraph returns the owner graph under the capability lens", () => {
    const arch = makeCapArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("capability");
    const g = useArchStore.getState().getLensGraph();
    expect(g.nodes.map((n) => n.id).sort()).toEqual(["svc", "tool"]);
    expect(g.aggregates).toEqual([]);
  });
});

describe("Capability lens selection and identity (I12, P6-3)", () => {
  beforeEach(resetStore);

  it("selecting a capability selects its owning component and requests the Capabilities tab", () => {
    const arch = makeCapArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("capability");
    useArchStore.getState().selectCapability("cap:svc:api:users");
    const s = useArchStore.getState();
    expect(s.selectedCapabilityId).toBe("cap:svc:api:users");
    expect(s.selectedComponentId).toBe("svc");
    expect(s.pendingDetailTab).toBe("capabilities");
  });

  it("preserves the selected component when switching lens (I12)", () => {
    const arch = makeCapArch();
    useArchStore.getState().setArchitecture(arch);
    useArchStore.getState().setLens("capability");
    useArchStore.getState().selectCapability("cap:tool:cli:analyze");
    expect(useArchStore.getState().selectedComponentId).toBe("tool");
    useArchStore.getState().setLens("structure");
    expect(useArchStore.getState().selectedComponentId).toBe("tool");
    expect(useArchStore.getState().selectedCapabilityId).toBe("cap:tool:cli:analyze");
  });

  it("round-trips ?lens=capability&capability= through the URL, composing with component", () => {
    replaceUrlState({ lens: "capability", capability: "cap:svc:api:users", component: "svc" });
    const parsed = parseUrlState();
    expect(parsed.lens).toBe("capability");
    expect(parsed.capability).toBe("cap:svc:api:users");
    expect(parsed.component).toBe("svc");
    // The capability param is not emitted under a different lens.
    replaceUrlState({ lens: "structure", capability: "cap:svc:api:users" });
    expect(parseUrlState().capability).toBeUndefined();
  });

  it("resets capability selection on architecture reload", () => {
    useArchStore.getState().setArchitecture(makeCapArch());
    useArchStore.getState().selectCapability("cap:svc:api:users");
    expect(useArchStore.getState().selectedCapabilityId).toBe("cap:svc:api:users");
    useArchStore.getState().setArchitecture(makeCapArch());
    expect(useArchStore.getState().selectedCapabilityId).toBeNull();
  });
});
