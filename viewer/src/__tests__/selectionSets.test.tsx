import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { useArchStore } from "../store";
import { ReviewSummary } from "../components/ReviewSummary";
import type { Architecture, Component, Finding, Concern } from "../types";

// Regression tests for P6-9 (selection sets and directives). They exercise the
// real store (no store mock) and the real setStorage localStorage layer provided
// by jsdom. The finding and concern fixtures below are real rows lifted from a v2
// projection of this repo (analyze.py . --store <db>), trimmed for size.

const DUP_FINDING: Finding = {
  confidence: "inferred",
  detail: { clone_class: "similar", component_ids: ["analyzer", "analyzer/derive"], total_tokens: 997 },
  evidence: [
    { end_line: 202, file: "analyzer/derive/docs.py", line: 149, symbol: "detect_patterns" },
    { end_line: 2582, file: "analyzer/scanner.py", line: 2509, symbol: "_detect_patterns" },
  ],
  id: "finding:duplication:4317ed01",
  kind: "duplication",
  members: [
    { component_id: "analyzer/derive", file: "analyzer/derive/docs.py", id: "analyzer/derive/docs.py:149", kind: "fragment", line_end: 202, line_start: 149, symbol: "detect_patterns" },
    { component_id: "analyzer", file: "analyzer/scanner.py", id: "analyzer/scanner.py:2509", kind: "fragment", line_end: 2582, line_start: 2509, symbol: "_detect_patterns" },
  ],
  rank_score: 192.85,
  summary: "similar clone across 2 fragments in 2 components",
  verification_status: "unverified",
};

const LOGGING_CONCERN: Concern = {
  basis: "logging library imports",
  detail: {},
  id: "concern:logging",
  kind: "logging",
  members: [
    { component_id: "analyzer", evidence: [{ file: "analyzer/incremental.py", signal: "import" }], files: ["analyzer/incremental.py"], markers: ["logging"] },
    { component_id: "analyzer/parsers", evidence: [{ file: "analyzer/parsers/tree_sitter_base.py", signal: "import" }], files: ["analyzer/parsers/tree_sitter_base.py"], markers: ["logging"] },
  ],
  title: "Logging",
};

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "analyzer",
    name: "analyzer",
    type: "module",
    path: "analyzer",
    language: "python",
    framework: null,
    description: null,
    port: null,
    children: [],
    files: ["analyzer/incremental.py"],
    entry_points: [],
    config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { python: 100 } },
    docs: {
      readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null,
      purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [],
    },
    ...overrides,
  };
}

function makeArchitecture(overrides: Partial<Architecture> = {}): Architecture {
  return {
    name: "solution-explorer",
    description: "A test project",
    repository: "https://github.com/acme/demo",
    generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0",
    root_path: "/demo",
    components: [
      makeComponent(),
      makeComponent({ id: "analyzer/derive", name: "derive", path: "analyzer/derive", files: ["analyzer/derive/docs.py"] }),
      makeComponent({ id: "analyzer/parsers", name: "parsers", path: "analyzer/parsers", files: ["analyzer/parsers/tree_sitter_base.py"] }),
    ],
    relationships: [],
    symbols: [],
    files: [],
    stats: {
      total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {},
      total_symbols: 0, total_components: 3, total_relationships: 0,
    },
    findings: [DUP_FINDING],
    concerns: [LOGGING_CONCERN],
    ...overrides,
  };
}

// Simulate a fresh page load: wipe in-memory set state while localStorage (the
// persistence layer) survives, exactly as a browser reload does (P1-3 pattern).
function simulateReload() {
  useArchStore.setState({ architecture: null, selectionSets: [], setAnnotations: [], annotations: [] });
}

describe("selection sets (P6-9)", () => {
  beforeEach(() => {
    localStorage.clear();
    useArchStore.setState({ architecture: null, selectionSets: [], setAnnotations: [], annotations: [], reviewMode: false, activePanel: null });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("creates a set from a finding's members with stable-identity refs", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    const id = useArchStore.getState().createSetFromFinding("finding:duplication:4317ed01");
    expect(id).toBeTruthy();
    const set = useArchStore.getState().getSetById(id!)!;
    expect(set.origin).toBe("finding:duplication:4317ed01");
    expect(set.members).toHaveLength(2);
    // Members carry the finding's stable fragment ids and file/line spans.
    const refs = set.members.map((m) => m.ref).sort();
    expect(refs).toEqual(["analyzer/derive/docs.py:149", "analyzer/scanner.py:2509"]);
    const derive = set.members.find((m) => m.ref === "analyzer/derive/docs.py:149")!;
    expect(derive.file).toBe("analyzer/derive/docs.py");
    expect(derive.lineStart).toBe(149);
    expect(derive.lineEnd).toBe(202);
    expect(derive.componentId).toBe("analyzer/derive");
  });

  it("creates a set from a concern's members", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    const id = useArchStore.getState().createSetFromConcern("concern:logging");
    expect(id).toBeTruthy();
    const set = useArchStore.getState().getSetById(id!)!;
    expect(set.name).toBe("Logging");
    expect(set.origin).toBe("concern:logging");
    expect(set.members.map((m) => m.componentId).sort()).toEqual(["analyzer", "analyzer/parsers"]);
    // Concern members carry the signal evidence.
    expect((set.members[0].evidence ?? []).some((e) => e.includes("import"))).toBe(true);
  });

  it("returns null when the finding or concern id is unknown", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    expect(useArchStore.getState().createSetFromFinding("finding:nope")).toBeNull();
    expect(useArchStore.getState().createSetFromConcern("concern:nope")).toBeNull();
  });

  it("survives a hard reload (sets and set-annotations restored from storage)", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    const id = useArchStore.getState().createSetFromConcern("concern:logging")!;
    useArchStore.getState().setSetIntent(id, "All logging goes through the shared structured logger.");
    useArchStore.getState().setSetMemberNote(id, "analyzer", "this one still uses print()");
    expect(useArchStore.getState().selectionSets).toHaveLength(1);

    simulateReload();
    expect(useArchStore.getState().selectionSets).toHaveLength(0);

    // Reloading the same architecture identity restores the set and its annotation.
    useArchStore.getState().setArchitecture(makeArchitecture({ generated_at: "2026-07-14T00:00:00Z" }));
    const sets = useArchStore.getState().selectionSets;
    expect(sets).toHaveLength(1);
    expect(sets[0].members).toHaveLength(2);
    const ann = useArchStore.getState().getSetAnnotation(sets[0].id)!;
    expect(ann.intent).toBe("All logging goes through the shared structured logger.");
    expect(ann.memberNotes.find((n) => n.memberRef === "analyzer")?.note).toBe("this one still uses print()");
  });

  it("keeps orphaned members after a changed architecture (not silently dropped)", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    const id = useArchStore.getState().createSetFromConcern("concern:logging")!;

    simulateReload();
    // Same identity, but analyzer/parsers is gone after re-analysis.
    useArchStore.getState().setArchitecture(
      makeArchitecture({ components: [makeComponent()] }),
    );

    const set = useArchStore.getState().getSetById(id)!;
    expect(set.members).toHaveLength(2);
    // The removed member is retained but no longer resolves to a component.
    expect(useArchStore.getState().getComponentById("analyzer/parsers")).toBeNull();
  });

  it("renders a selection set in ReviewSummary with an orphaned badge", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    useArchStore.getState().createSetFromConcern("concern:logging");

    simulateReload();
    useArchStore.getState().setArchitecture(
      makeArchitecture({ components: [makeComponent()] }),
    );

    render(<ReviewSummary />);
    expect(screen.getByTestId("selection-sets")).toBeTruthy();
    expect(screen.getByTestId("selection-set-card")).toBeTruthy();
    // The orphaned member surfaces a visible count, not a silent drop.
    expect(screen.getByText("1 orphaned")).toBeTruthy();
  });

  it("manual add-to-set creates and appends to a manual set, de-duped", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    const id = useArchStore.getState().addComponentToSet(null, "analyzer")!;
    expect(id).toBeTruthy();
    useArchStore.getState().addComponentToSet(null, "analyzer/derive");
    useArchStore.getState().addComponentToSet(null, "analyzer"); // duplicate, ignored
    const set = useArchStore.getState().getSetById(id)!;
    expect(set.origin).toBe("manual");
    expect(set.members.map((m) => m.ref).sort()).toEqual(["analyzer", "analyzer/derive"]);
  });

  it("does not crash when localStorage write fails (quota)", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    expect(() => useArchStore.getState().createSetFromConcern("concern:logging")).not.toThrow();
    expect(useArchStore.getState().selectionSets).toHaveLength(1);
    spy.mockRestore();
  });

  it("deleting a set persists the removal and drops its annotation", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    const id = useArchStore.getState().createSetFromConcern("concern:logging")!;
    useArchStore.getState().setSetIntent(id, "intent");
    useArchStore.getState().deleteSet(id);

    simulateReload();
    useArchStore.getState().setArchitecture(makeArchitecture());
    expect(useArchStore.getState().selectionSets).toHaveLength(0);
    expect(useArchStore.getState().setAnnotations).toHaveLength(0);
  });
});
