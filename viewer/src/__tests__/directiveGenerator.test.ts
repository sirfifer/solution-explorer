import { describe, it, expect } from "vitest";
import {
  buildDirectiveModel,
  renderDirectiveMarkdown,
  generateDirective,
  suggestAcceptanceCriteria,
  DIRECTIVE_SCHEMA,
  type DirectiveModel,
} from "../utils/directiveGenerator";
import type { Architecture, Component, SelectionSet, SetAnnotation } from "../types";

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
    files: [],
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

const architecture: Architecture = {
  name: "solution-explorer",
  description: "",
  repository: null,
  generated_at: "2025-01-01T00:00:00Z",
  analyzer_version: "1.2.0",
  root_path: "/demo",
  components: [
    makeComponent(),
    makeComponent({ id: "analyzer/derive", name: "derive", path: "analyzer/derive" }),
  ],
  relationships: [],
  symbols: [],
  files: [],
  stats: {
    total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {},
    total_symbols: 0, total_components: 2, total_relationships: 0,
  },
};

const set: SelectionSet = {
  id: "set-1",
  name: "Deduplicate detect_patterns",
  origin: "finding:duplication:4317ed01",
  createdAt: "2025-01-01T00:00:00Z",
  members: [
    { kind: "file", ref: "analyzer/derive/docs.py:149", componentId: "analyzer/derive", label: "docs.py", file: "analyzer/derive/docs.py", lineStart: 149, lineEnd: 202, evidence: ["clone class: similar", "symbol: detect_patterns"] },
    { kind: "file", ref: "analyzer/scanner.py:2509", componentId: "analyzer", label: "scanner.py", file: "analyzer/scanner.py", lineStart: 2509, lineEnd: 2582, evidence: ["clone class: similar", "symbol: _detect_patterns"] },
  ],
};

const annotation: SetAnnotation = {
  setId: "set-1",
  intent: "Extract the shared pattern-detection logic into one helper.",
  memberNotes: [{ memberRef: "analyzer/scanner.py:2509", note: "this is the older copy" }],
};

describe("directive generator (P6-9)", () => {
  it("names the intent and lists every member with file and lines", () => {
    const model = buildDirectiveModel(set, annotation, architecture);
    expect(model.intent).toBe("Extract the shared pattern-detection logic into one helper.");
    expect(model.members).toHaveLength(2);
    for (const m of model.members) {
      expect(m.file).toBeTruthy();
      expect(typeof m.line_start).toBe("number");
      expect(typeof m.line_end).toBe("number");
    }
    // The per-member note flows into the model.
    const older = model.members.find((m) => m.ref === "analyzer/scanner.py:2509")!;
    expect(older.note).toBe("this is the older copy");
  });

  it("auto-suggests acceptance criteria from the origin, merged with free text", () => {
    const model = buildDirectiveModel(set, annotation, architecture, {
      acceptanceCriteria: ["No behavior change in the extracted helper."],
    });
    // duplication finding origin => extraction criterion is auto-added.
    expect(model.acceptance_criteria.some((c) => c.toLowerCase().includes("extracted into one shared implementation"))).toBe(true);
    expect(model.acceptance_criteria).toContain("No behavior change in the extracted helper.");
  });

  it("moves exempted members out of the work list, each carrying its required reason", () => {
    const model = buildDirectiveModel(set, annotation, architecture, {
      exemptions: {
        "analyzer/scanner.py:2509": "scanner is being deleted in the v1 engine removal",
        "analyzer/derive/docs.py:149": "   ", // blank reason => NOT exempt
      },
    });
    expect(model.exemptions).toHaveLength(1);
    expect(model.exemptions[0].ref).toBe("analyzer/scanner.py:2509");
    expect(model.exemptions[0].reason).toBe("scanner is being deleted in the v1 engine removal");
    // The blank-reason member stays in scope, never exempted without a reason.
    expect(model.members.map((m) => m.ref)).toContain("analyzer/derive/docs.py:149");
    expect(model.members).toHaveLength(1);
  });

  it("embeds a parseable JSON block whose members match the non-exempt set", () => {
    const { markdown, model } = generateDirective(set, annotation, architecture, {
      exemptions: { "analyzer/scanner.py:2509": "out of scope" },
    });
    // The markdown carries a fenced json block.
    const match = markdown.match(/```json\n([\s\S]*?)\n```/);
    expect(match).toBeTruthy();
    const parsed = JSON.parse(match![1]) as DirectiveModel;
    expect(parsed.schema).toBe(DIRECTIVE_SCHEMA);
    expect(parsed.intent).toBe(model.intent);
    // JSON member list matches the model's non-exempt members exactly.
    expect(parsed.members.map((m) => m.ref)).toEqual(model.members.map((m) => m.ref));
    expect(parsed.members.map((m) => m.ref)).toEqual(["analyzer/derive/docs.py:149"]);
    expect(parsed.exemptions.map((e) => e.ref)).toEqual(["analyzer/scanner.py:2509"]);
    // Human sections are present too.
    expect(markdown).toContain("## Intent");
    expect(markdown).toContain("## Members");
    expect(markdown).toContain("## Acceptance criteria");
  });

  it("marks a member orphaned when its component is gone, but keeps it in the order", () => {
    const orphanSet: SelectionSet = {
      ...set,
      members: [
        { kind: "component", ref: "gone", componentId: "gone", label: "removed", file: undefined, lineStart: null, lineEnd: null, evidence: [] },
      ],
    };
    const model = buildDirectiveModel(orphanSet, null, architecture);
    expect(model.members).toHaveLength(1);
    expect(model.members[0].orphaned).toBe(true);
    const md = renderDirectiveMarkdown(model, architecture.name);
    expect(md).toContain("(orphaned)");
  });

  it("suggests concern-kind-specific acceptance criteria", () => {
    expect(suggestAcceptanceCriteria("concern:logging")[0]).toMatch(/shared logger/i);
    expect(suggestAcceptanceCriteria("finding:orphan:x")[0]).toMatch(/entry point|removed/i);
    expect(suggestAcceptanceCriteria("manual")).toHaveLength(0);
  });
});
