import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import { FINDINGS_QUESTIONS } from "../findings/model";
import type { Architecture, Component, Finding, Concern } from "../types";

// P6-8 / I14: the Findings surface answers the section-8 question list, and every
// documented question has a gesture exercised against the real store here.

function makeComponent(id: string, name: string, files: string[]): Component {
  return {
    id, name, type: "module", path: `src/${id}`, language: "typescript",
    framework: null, description: null, port: null, children: [], files,
    entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { typescript: 100 } },
    docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
  };
}

const finding: Finding = {
  id: "finding:duplication:aaa", kind: "duplication",
  summary: "renamed clone across 2 fragments in 2 components",
  confidence: "inferred", verification_status: "unverified", rank_score: 300,
  members: [
    { id: "alpha/x.ts:10", kind: "fragment", component_id: "alpha", file: "alpha/x.ts", line_start: 10, line_end: 40, symbol: "f" },
    { id: "beta/y.ts:12", kind: "fragment", component_id: "beta", file: "beta/y.ts", line_start: 12, line_end: 42, symbol: "f" },
  ],
  evidence: [{ file: "alpha/x.ts", line: 10, symbol: "f" }, { file: "beta/y.ts", line: 12, symbol: "f" }],
};
const lowerFinding: Finding = { ...finding, id: "finding:orphan:gamma", kind: "orphan", rank_score: 50, members: [{ id: "gamma", kind: "component", component_id: "gamma" }] };
const concern: Concern = {
  id: "concern:logging", kind: "logging", title: "Logging", basis: "logging library imports",
  members: [
    { component_id: "alpha", evidence: [{ file: "alpha/x.ts", line: 3, signal: "import:structlog" }], files: [], markers: [] },
    { component_id: "beta", evidence: [{ file: "beta/y.ts", line: 4, signal: "import:loguru" }], files: [], markers: [] },
  ],
};

function makeArch(): Architecture {
  return {
    name: "T", description: "", repository: null, generated_at: "2025-01-01T00:00:00Z",
    analyzer_version: "1.2.0", root_path: "/t",
    components: [makeComponent("alpha", "Alpha", ["alpha/x.ts"]), makeComponent("beta", "Beta", ["beta/y.ts"]), makeComponent("gamma", "Gamma", ["gamma/a.ts"])],
    relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    findings: [lowerFinding, finding], concerns: [concern],
  };
}

function resetStore() {
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [], drillLevel: null,
    reviewMode: false, annotatingComponentId: null, annotations: [],
    findingsSurface: { open: false, tab: "findings", kindFilter: null, elementFilter: null },
    stagedFindingSet: null,
  });
}

describe("Findings question list (I14)", () => {
  beforeEach(resetStore);

  // One gesture per documented question, each asserting the answer.
  const gestures: Record<string, () => void> = {
    // "What did the system notice?" -> ranked findings, worst first (I11).
    noticed: () => {
      useArchStore.getState().setArchitecture(makeArch());
      const ranked = useArchStore.getState().getFindings();
      expect(ranked[0].id).toBe("finding:duplication:aaa");
      expect(ranked[0].rank_score).toBe(Math.max(...ranked.map((f) => f.rank_score)));
    },
    // "Is it confirmed?" -> the verification-status marker, unverified.
    confirmed: () => {
      useArchStore.getState().setArchitecture(makeArch());
      expect(useArchStore.getState().getFindings()[0].verification_status).toBe("unverified");
    },
    // "Where exactly?" -> file:line evidence on the members.
    where: () => {
      useArchStore.getState().setArchitecture(makeArch());
      const top = useArchStore.getState().getFindings()[0];
      expect(top.members[0].file).toBe("alpha/x.ts");
      expect(top.members[0].line_start).toBe(10);
      expect(top.evidence[0].file).toBe("alpha/x.ts");
    },
    // "What shares this trait?" -> concern members.
    "shares-trait": () => {
      useArchStore.getState().setArchitecture(makeArch());
      const c = useArchStore.getState().getConcerns()[0];
      expect(c.members.map((m) => m.component_id)).toEqual(["alpha", "beta"]);
    },
    // "What can I do about it?" -> the I15 affordances (annotate stages the set).
    "what-can-i-do": () => {
      useArchStore.getState().setArchitecture(makeArch());
      const rep = useArchStore.getState().annotateFindingSet(finding);
      expect(rep).toBe("alpha");
      expect(useArchStore.getState().stagedFindingSet?.memberComponentIds).toEqual(["alpha", "beta"]);
    },
  };

  for (const q of FINDINGS_QUESTIONS) {
    it(`answers: ${q.question}`, () => {
      expect(gestures[q.id]).toBeTypeOf("function");
      gestures[q.id]();
    });
  }

  it("every documented question has a tested gesture and vice-versa (coverage)", () => {
    const documented = new Set(FINDINGS_QUESTIONS.map((q) => q.id));
    const tested = new Set(Object.keys(gestures));
    expect(tested).toEqual(documented);
  });
});
