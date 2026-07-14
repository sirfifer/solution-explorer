import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import { DIRECTIVE_SCHEMA } from "../utils/directiveGenerator";
import type { Architecture, Component, Finding, Concern } from "../types";

// The P6-8 / P6-9 integration (Program 2, Stream B, Task A): the findings surface
// now drives the P6-9 selection-set + directive engine directly. "Annotate the
// set" builds a real selection set and opens the set annotation flow; "Export
// directive" builds the set and renders a parseable, structured work order. These
// regression tests run against the REAL store (no store mock) and the real
// setStorage localStorage layer, with the finding/concern fixtures lifted from a
// v2 projection of this repo (analyze.py . --store <db>), trimmed for size.

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
    { component_id: "analyzer", evidence: [{ file: "analyzer/incremental.py", line: 12, signal: "import" }], files: ["analyzer/incremental.py"], markers: ["logging"] },
    { component_id: "analyzer/parsers", evidence: [{ file: "analyzer/parsers/tree_sitter_base.py", line: 8, signal: "import" }], files: ["analyzer/parsers/tree_sitter_base.py"], markers: ["logging"] },
  ],
  title: "Logging",
};

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "analyzer", name: "analyzer", type: "module", path: "analyzer", language: "python",
    framework: null, description: null, port: null, children: [], files: ["analyzer/incremental.py"],
    entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { python: 100 } },
    docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
    ...overrides,
  };
}

function makeArchitecture(): Architecture {
  return {
    name: "solution-explorer", description: "", repository: null, generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0", root_path: "/demo",
    components: [
      makeComponent(),
      makeComponent({ id: "analyzer/derive", name: "derive", path: "analyzer/derive", files: ["analyzer/derive/docs.py", "analyzer/scanner.py"] }),
      makeComponent({ id: "analyzer/parsers", name: "parsers", path: "analyzer/parsers", files: ["analyzer/parsers/tree_sitter_base.py"] }),
    ],
    relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 3, total_relationships: 0 },
    findings: [DUP_FINDING],
    concerns: [LOGGING_CONCERN],
  };
}

// Pull the fenced ```json machine-readable work order out of a rendered directive.
function parseDirectiveJson(markdown: string): Record<string, unknown> {
  const match = markdown.match(/```json\n([\s\S]*?)\n```/);
  expect(match).toBeTruthy();
  return JSON.parse(match![1]);
}

function reset() {
  localStorage.clear();
  useArchStore.setState({
    architecture: null, selectionSets: [], setAnnotations: [], annotations: [],
    reviewMode: false, activePanel: null, annotatingComponentId: null,
    findingsSurface: { open: false, tab: "findings", kindFilter: null, elementFilter: null },
    stagedFindingSet: null,
  });
}

describe("Findings-to-sets integration: annotate flow (Task A)", () => {
  beforeEach(reset);

  it("annotate builds a real set from a projection finding and opens the annotation flow", () => {
    const store = useArchStore.getState();
    store.setArchitecture(makeArchitecture());
    // Fail-before proof: no set exists for this finding before the affordance runs.
    expect(useArchStore.getState().selectionSets.filter((s) => s.origin === DUP_FINDING.id)).toHaveLength(0);

    const setId = useArchStore.getState().annotateFindingSet(DUP_FINDING);
    expect(setId).toBeTruthy();

    const st = useArchStore.getState();
    const set = st.getSetById(setId!)!;
    // The set's members match the finding's members (stable fragment ids).
    expect(set.origin).toBe(DUP_FINDING.id);
    expect(set.members.map((m) => m.ref).sort()).toEqual(
      DUP_FINDING.members.map((m) => m.id).sort(),
    );
    // The set annotation flow is open (review mode + review panel); overlay closed.
    expect(st.reviewMode).toBe(true);
    expect(st.activePanel).toBe("review");
    expect(st.findingsSurface.open).toBe(false);
  });
});

describe("Findings-to-sets integration: full finding-to-directive flow (Task A)", () => {
  beforeEach(reset);

  it("produces a set, a set annotation, and a parseable directive whose members match the finding", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());

    // 1. Annotate: build the set and open the annotation flow.
    const setId = useArchStore.getState().annotateFindingSet(DUP_FINDING)!;
    expect(setId).toBeTruthy();

    // 2. State the shared intent (the reviewer's annotation) -> a SetAnnotation.
    useArchStore.getState().setSetIntent(setId, "Extract the shared pattern-detection helper.");
    const annotation = useArchStore.getState().getSetAnnotation(setId)!;
    expect(annotation).toBeTruthy();
    expect(annotation.intent).toBe("Extract the shared pattern-detection helper.");

    // 3. Export the directive; the fenced JSON block is a parseable work order.
    const result = useArchStore.getState().exportDirectiveForFinding(DUP_FINDING.id)!;
    expect(result).toBeTruthy();
    const json = parseDirectiveJson(result.markdown);

    expect(json.schema).toBe(DIRECTIVE_SCHEMA);
    expect(json.intent).toBe("Extract the shared pattern-detection helper.");
    // Load-bearing assertion: the directive's members match the finding's members.
    const directiveRefs = (json.members as Array<{ ref: string }>).map((m) => m.ref).sort();
    expect(directiveRefs).toEqual(DUP_FINDING.members.map((m) => m.id).sort());
    // Each finding member carries its file/line span into the directive.
    const derive = (json.members as Array<{ ref: string; file: string; line_start: number }>).find(
      (m) => m.ref === "analyzer/derive/docs.py:149",
    )!;
    expect(derive.file).toBe("analyzer/derive/docs.py");
    expect(derive.line_start).toBe(149);
  });

  it("export reuses the finding's set rather than spawning duplicates", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    useArchStore.getState().exportDirectiveForFinding(DUP_FINDING.id);
    useArchStore.getState().exportDirectiveForFinding(DUP_FINDING.id);
    useArchStore.getState().annotateFindingSet(DUP_FINDING);
    expect(useArchStore.getState().selectionSets.filter((s) => s.origin === DUP_FINDING.id)).toHaveLength(1);
  });

  it("returns null for an unknown finding id (no set, no directive)", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    expect(useArchStore.getState().exportDirectiveForFinding("finding:nope")).toBeNull();
    expect(useArchStore.getState().annotateFindingSet({ ...DUP_FINDING, id: "finding:nope" })).toBeNull();
    expect(useArchStore.getState().selectionSets).toHaveLength(0);
  });
});

describe("Concern rows gain the same two affordances (Task A)", () => {
  beforeEach(reset);

  it("annotate a concern builds its set and opens the annotation flow", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    const setId = useArchStore.getState().annotateConcernSet(LOGGING_CONCERN)!;
    const st = useArchStore.getState();
    const set = st.getSetById(setId)!;
    expect(set.origin).toBe("concern:logging");
    expect(set.members.map((m) => m.componentId).sort()).toEqual(["analyzer", "analyzer/parsers"]);
    expect(st.reviewMode).toBe(true);
    expect(st.activePanel).toBe("review");
    expect(st.findingsSurface.open).toBe(false);
  });

  it("export a concern directive is parseable and its members match the concern", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    const result = useArchStore.getState().exportDirectiveForConcern("concern:logging")!;
    const json = parseDirectiveJson(result.markdown);
    expect(json.schema).toBe(DIRECTIVE_SCHEMA);
    const componentIds = (json.members as Array<{ component_id: string }>).map((m) => m.component_id).sort();
    expect(componentIds).toEqual(["analyzer", "analyzer/parsers"]);
  });

  it("returns null for an unknown concern id", () => {
    useArchStore.getState().setArchitecture(makeArchitecture());
    expect(useArchStore.getState().exportDirectiveForConcern("concern:nope")).toBeNull();
    expect(useArchStore.getState().annotateConcernSet({ ...LOGGING_CONCERN, id: "concern:nope" })).toBeNull();
  });
});
