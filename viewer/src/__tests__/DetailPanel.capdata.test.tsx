import { describe, it, expect, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { DetailPanel } from "../components/DetailPanel";
import { useArchStore } from "../store";
import type {
  Architecture,
  Component,
  Capability,
  DataEntity,
  EntityAccess,
} from "../types";

// P5-3 regression suite: the Capabilities and Data tabs land at list level with
// ranked, grouped presentation, evidence source links, and L2 test linkage, and
// old datasets (no capability/entity keys) render identically with no new tab.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "repo:demo/api",
    name: "API Service",
    type: "module",
    path: "src/api",
    language: "typescript",
    framework: null,
    description: null,
    port: null,
    children: [],
    files: ["src/api/index.ts"],
    entry_points: [],
    config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 0, languages: { typescript: 100 } },
    docs: {
      readme: null,
      claude_md: null,
      changelog: null,
      api_docs: null,
      architecture_notes: null,
      purpose: null,
      key_decisions: [],
      patterns: [],
      tech_stack: [],
      env_vars: [],
      api_endpoints: [],
    },
    ...overrides,
  };
}

function makeArchitecture(
  components: Component[],
  overrides: Partial<Architecture> = {},
): Architecture {
  return {
    name: "Demo",
    description: "A project",
    repository: "https://github.com/acme/demo",
    default_branch: "main",
    generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0",
    root_path: "/demo",
    components,
    relationships: [],
    symbols: [],
    files: [],
    stats: {
      total_files: 1,
      total_lines: 100,
      total_size_bytes: 1000,
      languages: { typescript: 100 },
      total_symbols: 0,
      total_components: components.length,
      total_relationships: 0,
    },
    ...overrides,
  };
}

function mount(component: Component, arch: Architecture) {
  useArchStore.setState({
    architecture: arch,
    loading: false,
    error: null,
    detailItem: { type: "component", data: component },
    activePanel: "detail",
    componentDetailCache: {},
    componentDetailLoading: {},
    componentDetailErrors: {},
  });
  return render(<DetailPanel />);
}

afterEach(() => {
  cleanup();
  useArchStore.setState({
    detailItem: null,
    componentDetailCache: {},
    componentDetailLoading: {},
    componentDetailErrors: {},
  });
});

describe("P5-3 backward compatibility", () => {
  it("shows structured user flows even when no narrative summary was supplied", () => {
    const component = makeComponent({ ai_enhance: { key_user_flows: ["Choose a workspace", "Inspect its components"] } });
    mount(component, makeArchitecture([component]));
    fireEvent.click(screen.getByRole("button", { name: "AI Insights" }));
    expect(screen.getByText("Choose a workspace")).toBeDefined();
    expect(screen.getByText("Inspect its components")).toBeDefined();
  });
  it("shows no Capabilities or Data tab when the dataset carries neither key", () => {
    const component = makeComponent();
    const arch = makeArchitecture([component]);
    mount(component, arch);

    expect(screen.queryByRole("button", { name: /Capabilities/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Data/ })).toBeNull();
    // The pre-existing tabs are still present and unchanged.
    expect(screen.getByRole("button", { name: /Overview/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /Files/ })).toBeDefined();
  });

  it("shows no Data tab when only an unrelated component owns entities", () => {
    // entity_access present but none reference this component: still no tab.
    const component = makeComponent();
    const arch = makeArchitecture([component], {
      data_entities: [],
      entity_access: [
        {
          accessor_id: "repo:demo/other",
          entity_id: "entity:repo:demo/other:widget",
          mode: "read",
          confidence: "certain",
          evidence: [{ file: "src/other/x.py", line: 3, snippet: "Widget.query" }],
        },
      ],
    });
    mount(component, arch);
    expect(screen.queryByRole("button", { name: /Data/ })).toBeNull();
  });
});

describe("P5-3 Capabilities tab", () => {
  const capabilities: Capability[] = [
    // Deliberately out of rank order to prove the tab re-orders.
    {
      id: "cap:repo:demo/api:job:cleanup",
      component_id: "repo:demo/api",
      kind: "job",
      name: "cleanup",
      detail: { name: "cleanup", framework: "celery", trigger: "cron" },
      evidence: [{ file: "src/api/jobs.py", line: 5, snippet: "@shared_task" }],
      confidence: "inferred",
    },
    {
      id: "cap:repo:demo/api:api:get-users-id",
      component_id: "repo:demo/api",
      kind: "api",
      name: "GET /users/{id}",
      detail: {
        method: "GET",
        path: "/users/{id}",
        framework: "fastapi",
        tests: [{ file: "tests/test_users.py", line: 12, confidence: "inferred" }],
      },
      evidence: [{ file: "src/api/routes.py", line: 20, snippet: "@app.get('/users/{id}')" }],
      confidence: "certain",
    },
    {
      id: "cap:repo:demo/api:api:post-users",
      component_id: "repo:demo/api",
      kind: "api",
      name: "POST /users",
      detail: { method: "POST", path: "/users", framework: "fastapi" },
      evidence: [{ file: "src/api/routes.py", line: 25, snippet: "@app.post('/users')" }],
      confidence: "certain",
    },
    {
      id: "cap:repo:demo/api:cli:deploy",
      component_id: "repo:demo/api",
      kind: "cli",
      name: "deploy",
      detail: { command: "deploy", framework: "click", flags: ["--env", "--force"] },
      evidence: [{ file: "src/api/cli.py", line: 8, snippet: "@click.command()" }],
      confidence: "certain",
    },
  ];

  it("groups capabilities by kind in api, cli, event, job order and lists them", () => {
    const component = makeComponent({ capabilities });
    const arch = makeArchitecture([component]);
    mount(component, arch);

    const tab = screen.getByRole("button", { name: /Capabilities\s*4/ });
    fireEvent.click(tab);

    // Group headers present.
    expect(screen.getByText(/API \(2\)/)).toBeDefined();
    expect(screen.getByText(/CLI \(1\)/)).toBeDefined();
    expect(screen.getByText(/Jobs \(1\)/)).toBeDefined();

    // Rank: the API group header appears before the CLI group header, which
    // appears before the Jobs group header (source order was job, api, api, cli).
    const html = document.body.innerHTML;
    expect(html.indexOf("API (2)")).toBeLessThan(html.indexOf("CLI (1)"));
    expect(html.indexOf("CLI (1)")).toBeLessThan(html.indexOf("Jobs (1)"));

    // Within the API group, GET /users/{id} sorts before POST /users by name.
    expect(html.indexOf("/users/{id}")).toBeLessThan(html.indexOf("/users<"));
  });

  it("renders method/path for api, flags for cli, and marks inferred confidence", () => {
    const component = makeComponent({ capabilities });
    const arch = makeArchitecture([component]);
    mount(component, arch);
    fireEvent.click(screen.getByRole("button", { name: /Capabilities/ }));

    expect(screen.getByText("GET")).toBeDefined();
    expect(screen.getByText("/users/{id}")).toBeDefined();
    // CLI flags.
    expect(screen.getByText("--env")).toBeDefined();
    expect(screen.getByText("--force")).toBeDefined();
    // The job is inferred, so an inferred badge appears; certain api/cli do not.
    expect(screen.getAllByText("inferred").length).toBeGreaterThan(0);
  });

  it("renders evidence as a well-formed GitHub source link and shows test linkage", () => {
    const component = makeComponent({ capabilities });
    const arch = makeArchitecture([component]);
    mount(component, arch);
    fireEvent.click(screen.getByRole("button", { name: /Capabilities/ }));

    // Evidence file:line text is present.
    expect(screen.getByText("src/api/routes.py:20")).toBeDefined();

    // Evidence source links are real GitHub blob URLs with a line anchor.
    const evidenceLink = screen
      .getAllByRole("link")
      .map((a) => (a as HTMLAnchorElement).href)
      .find((h) => h.includes("src/api/routes.py"));
    expect(evidenceLink).toBe("https://github.com/acme/demo/blob/main/src/api/routes.py#L20");

    // L2 test linkage: the "Tested by" section links the exercising test file.
    expect(screen.getByText(/Tested by \(1\)/)).toBeDefined();
    expect(screen.getByText("tests/test_users.py:12")).toBeDefined();
    const testLink = screen
      .getAllByRole("link")
      .map((a) => (a as HTMLAnchorElement).href)
      .find((h) => h.includes("tests/test_users.py"));
    expect(testLink).toBe("https://github.com/acme/demo/blob/main/tests/test_users.py#L12");
  });
});

describe("P5-3 Data tab", () => {
  const entities: DataEntity[] = [
    {
      id: "entity:repo:demo/api:user",
      component_id: "repo:demo/api",
      name: "User",
      kind: "model",
      framework: "sqlalchemy",
      fields: [
        { name: "email", type: "String" },
        { name: "id", type: "Integer" },
      ],
      evidence: [{ file: "src/api/models.py", line: 4, snippet: "class User(Base)" }],
      table: "users",
    },
    {
      id: "entity:repo:demo/api:invoices",
      component_id: "repo:demo/api",
      name: "invoices",
      kind: "table",
      framework: "sql",
      fields: [{ name: "amount", type: null }],
      evidence: [{ file: "src/api/schema.sql", line: 1, snippet: "CREATE TABLE invoices" }],
    },
  ];

  const worker = makeComponent({ id: "repo:demo/worker", name: "Worker", path: "src/worker" });

  const entity_access: EntityAccess[] = [
    // Another component reads the User entity owned by API.
    {
      accessor_id: "repo:demo/worker",
      entity_id: "entity:repo:demo/api:user",
      mode: "read",
      confidence: "certain",
      evidence: [{ file: "src/worker/task.py", line: 9, snippet: "session.query(User)" }],
    },
    // API itself writes the invoices entity it owns.
    {
      accessor_id: "repo:demo/api",
      entity_id: "entity:repo:demo/api:invoices",
      mode: "write",
      confidence: "inferred",
      evidence: [{ file: "src/api/billing.py", line: 30, snippet: "INSERT INTO invoices" }],
    },
  ];

  it("lists owned entities ranked by kind with kind badges, fields, and evidence links", () => {
    const api = makeComponent({ capabilities: undefined, data_entities: entities });
    const arch = makeArchitecture([api, worker], {
      data_entities: entities,
      entity_access,
    });
    mount(api, arch);

    fireEvent.click(screen.getByRole("button", { name: /Data\s*2/ }));

    // Kind badges.
    expect(screen.getByText("model")).toBeDefined();
    expect(screen.getByText("table")).toBeDefined();

    // model ranks before table (ENTITY_KIND_ORDER), so User appears before invoices.
    const html = document.body.innerHTML;
    expect(html.indexOf(">User<")).toBeLessThan(html.indexOf(">invoices<"));

    // Parsed fields render with types.
    expect(screen.getByText("email: String")).toBeDefined();
    expect(screen.getByText("id: Integer")).toBeDefined();
    // A field with no type renders bare.
    expect(screen.getByText("amount")).toBeDefined();

    // Evidence source link is well formed.
    const link = screen
      .getAllByRole("link")
      .map((a) => (a as HTMLAnchorElement).href)
      .find((h) => h.includes("src/api/models.py"));
    expect(link).toBe("https://github.com/acme/demo/blob/main/src/api/models.py#L4");
  });

  it("shows who else touches an owned entity, both directions, with mode and confidence", () => {
    const api = makeComponent({ data_entities: entities });
    const arch = makeArchitecture([api, worker], {
      data_entities: entities,
      entity_access,
    });
    mount(api, arch);
    fireEvent.click(screen.getByRole("button", { name: /Data/ }));

    // "Accessed by" surfaces the Worker's read of the User entity by name.
    // Mode text is lowercase in the DOM (uppercased via CSS).
    expect(screen.getByText(/Accessed by \(1\)/)).toBeDefined();
    expect(screen.getByText("Worker")).toBeDefined();
    expect(screen.getByText("read")).toBeDefined();

    // "Reads / Writes" surfaces this component's own write of invoices, inferred.
    expect(screen.getByText(/Reads \/ Writes \(1\)/)).toBeDefined();
    expect(screen.getByText("write")).toBeDefined();
    expect(screen.getAllByText("inferred").length).toBeGreaterThan(0);
  });

  it("appears for a component that only accesses entities it does not own", () => {
    // Worker owns nothing but reads User: the Data tab still appears with the
    // outgoing edge, and no owned-entities section.
    const api = makeComponent({ data_entities: entities });
    const arch = makeArchitecture([api, worker], {
      data_entities: entities,
      entity_access,
    });
    mount(worker, arch);

    const tab = screen.getByRole("button", { name: /Data/ });
    expect(tab).toBeDefined();
    fireEvent.click(tab);
    expect(screen.getByText(/Reads \/ Writes \(1\)/)).toBeDefined();
    // The owned-entities header is absent (Worker owns none).
    expect(screen.queryByText(/^Entities \(/)).toBeNull();
  });
});
