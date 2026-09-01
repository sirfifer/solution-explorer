import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useArchStore } from "../store";
import { buildOrientationFallback, attachHumanViews } from "../utils/orientation";
import { getLens, listAvailableLenses } from "../lenses";
import { ExperienceSwitcher } from "../components/ExperienceSwitcher";
import { conciseOverviewStatement, SystemOverview } from "../components/SystemOverview";
import { HelpSystem } from "../components/HelpSystem";
import { SupportPanel } from "../components/SupportPanel";
import type { Architecture, Component, SecurityProjection, SupportProjection } from "../types";

function component(id: string, type = "module", children: Component[] = []): Component {
  return {
    id, name: id, type, path: `src/${id}`, language: "typescript", framework: null,
    description: null, port: null, children, files: [], entry_points: [], config_files: [],
    metrics: { files: 0, lines: 0, size_bytes: 0, symbols: 0, languages: {} },
    docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
  };
}

function architecture(overrides: Partial<Architecture> = {}): Architecture {
  const web = component("web", "web-client");
  const api = component("api", "api-server");
  const model = component("trip-model");
  return {
    name: "Transit", description: "", repository: null, generated_at: "2026-08-31T00:00:00Z",
    analyzer_version: "2.0.0", root_path: "/transit", components: [web, api, model],
    relationships: [{ source: "web", target: "api", type: "http", label: null, protocol: "https", port: null, bidirectional: false }],
    symbols: [], files: [], stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 3, total_relationships: 1 },
    ...overrides,
  };
}

const support: SupportProjection = {
  schema: "syscorpus.support/v1", method_caveat: "attention, not incident probability",
  configuration: [{ key: "API_URL", component_id: "web", component_name: "web", kind: "environment_variable", evidence: {} }],
  external_dependencies: [{ name: "Stripe", category: "payments", component_id: "api", component_name: "api", evidence: {} }],
  entry_points: [], data_handled: [],
  attention: [{ component_id: "api", component_name: "api", attention_score: 3, reasons: ["external reliance"] }],
  counts: { configuration: 1, external_dependencies: 1, entry_points: 0, data_entities: 0, attention_components: 1 },
};

const security: SecurityProjection = {
  schema: "syscorpus.security/v1", method_caveat: "not a security audit",
  mechanisms: [{ source: "web", target: "api", mechanism: "bearer", confidence: "certain", evidence: {} }],
  credential_configuration: [],
  communication_boundaries: [{ source: "web", source_name: "web", target: "api", target_name: "api", type: "http", protocol: "https", transport_state: "encrypted_observed", evidence: {} }],
  sensitive_data_leads: [], findings: [], not_observable: ["runtime control effectiveness"],
  counts: { mechanisms: 1, communication_boundaries: 1 },
};

beforeEach(() => {
  localStorage.clear();
  useArchStore.setState({ experienceMode: "overview", darkMode: true, architecture: null, lens: "structure" });
});

describe("human-entry compatibility projection", () => {
  it("builds a deterministic bounded portrait for old projections", () => {
    const arch = architecture();
    const first = buildOrientationFallback(arch);
    const second = buildOrientationFallback(arch);
    expect(first).toEqual(second);
    expect(first.portrait.nodes.map((node) => node.label)).toEqual(["Experiences", "Services & interfaces", "Data & persistence"]);
    expect(first.orientation.deterministic_statement).toContain("3 mapped components");
  });

  it("prefers sidecars and always supplies orientation", () => {
    const arch = architecture();
    const merged = attachHumanViews(arch, { support, security });
    expect(merged.orientation?.schema).toBe("syscorpus.orientation/v1");
    expect(merged.support).toBe(support);
    expect(merged.security).toBe(security);
  });
});

describe("Support and Security lenses", () => {
  it("registers only when the projection carries usable evidence", () => {
    const bare = listAvailableLenses(architecture()).map((lens) => lens.id);
    expect(bare).not.toContain("support");
    expect(bare).not.toContain("security");
    const rich = listAvailableLenses(architecture({ support, security })).map((lens) => lens.id);
    expect(rich).toContain("support");
    expect(rich).toContain("security");
  });

  it("hands the graph stable component identities from each view", () => {
    const arch = architecture({ support, security });
    const context = {
      architecture: arch, drillLevel: null,
      getVisibleComponents: () => arch.components,
      getAggregateNodes: () => [],
      getComponentRelationships: () => arch.relationships,
    };
    expect(getLens("support")?.getGraph(context).nodes.map((node) => node.id).sort()).toEqual(["api", "web"]);
    expect(getLens("security")?.getGraph(context).nodes.map((node) => node.id).sort()).toEqual(["api", "web"]);
  });

  it("renders repeated configuration names without React identity collisions", () => {
    const duplicateConfiguration = {
      ...support,
      configuration: [support.configuration[0], support.configuration[0]],
    };
    useArchStore.setState({ architecture: architecture({ support: duplicateConfiguration }) });
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<SupportPanel />);
    expect(screen.getAllByText("API_URL")).toHaveLength(2);
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});

describe("experience aperture", () => {
  it("bounds rich project prose before using it as the opening headline", () => {
    const prose = "A focused first sentence that explains the product. A much longer implementation inventory follows with every language, service, database, and operational detail.";
    expect(conciseOverviewStatement(prose)).toBe("A focused first sentence that explains the product.");
    expect(conciseOverviewStatement("word ".repeat(80))).toMatch(/…$/);
  });

  it("switches without clearing Workbench navigation and persists the last mode", () => {
    useArchStore.setState({ architecture: architecture(), selectedComponentId: "api" });
    render(<ExperienceSwitcher />);
    fireEvent.click(screen.getByRole("button", { name: "workbench" }));
    expect(useArchStore.getState().experienceMode).toBe("workbench");
    expect(useArchStore.getState().selectedComponentId).toBe("api");
    expect(JSON.parse(localStorage.getItem("arch-experience-preferences-v1") ?? "{}").lastMode).toBe("workbench");
    expect(useArchStore.getState().overviewHandoff).toBe(true);
  });

  it("does not stack the legacy welcome modal on an Overview handoff", () => {
    useArchStore.setState({ overviewHandoff: true });
    render(<HelpSystem />);
    expect(screen.queryByText("Welcome to Architecture Visualizer")).toBeNull();
  });

  it("renders the production Overview, changes direction, and hands context to Workbench", () => {
    const arch = attachHumanViews(architecture(), {});
    useArchStore.setState({
      architecture: arch,
      experienceMode: "overview",
      overviewDirection: "portrait",
      publication: null,
      searchOpen: false,
      trustOpen: false,
      preferencesOpen: false,
    });
    render(<SystemOverview displayName="Transit" />);
    expect(screen.getByText("Transit at a glance")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /questions$/ }));
    expect(screen.getByText("What are you trying to understand?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /How is it organized/ }));
    fireEvent.click(screen.getByRole("button", { name: "Continue with this question →" }));
    expect(useArchStore.getState().experienceMode).toBe("workbench");
    expect(useArchStore.getState().lens).toBe("structure");
    expect(useArchStore.getState().semanticLevel).toBe("system");
  });
});
