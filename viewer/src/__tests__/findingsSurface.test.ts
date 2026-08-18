import { describe, it, expect, beforeEach } from "vitest";
import { useArchStore } from "../store";
import {
  hasFindingsSurface,
  sortFindings,
  findingKinds,
  filterFindingsByKind,
  findingsForComponent,
} from "../findings/model";
import type { Architecture, Component, Finding, Concern } from "../types";

// P6-8 Findings and Concerns surface: availability degrade (no keys -> no entry),
// ranking by rank_score (I11), kind filter, per-element findings and the
// contextual badge, concerns membership (I12), the I15 affordances (open members,
// annotate the set with the P6-9 seam, export directive stub).

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "c", name: "C", type: "module", path: "src/c", language: "typescript",
    framework: null, description: null, port: null, children: [], files: ["src/c/i.ts"],
    entry_points: [], config_files: [],
    metrics: { files: 1, lines: 100, size_bytes: 1000, symbols: 5, languages: { typescript: 100 } },
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

// A duplication finding across two components, a lower-ranked orphan, plus a
// concern the two duplication members share. Mirrors the P5-6 projection shape.
function dupFinding(): Finding {
  return {
    id: "finding:duplication:aaa",
    kind: "duplication",
    summary: "renamed clone across 2 fragments in 2 components",
    confidence: "inferred",
    verification_status: "unverified",
    rank_score: 300,
    members: [
      { id: "alpha/x.ts:10", kind: "fragment", component_id: "alpha", file: "alpha/x.ts", line_start: 10, line_end: 40, symbol: "f" },
      { id: "beta/y.ts:12", kind: "fragment", component_id: "beta", file: "beta/y.ts", line_start: 12, line_end: 42, symbol: "f" },
    ],
    evidence: [
      { file: "alpha/x.ts", line: 10, end_line: 40, symbol: "f" },
      { file: "beta/y.ts", line: 12, end_line: 42, symbol: "f" },
    ],
    detail: { clone_class: "renamed" },
  };
}

function orphanFinding(): Finding {
  return {
    id: "finding:orphan:gamma",
    kind: "orphan",
    summary: "component 'gamma' has no incoming references",
    confidence: "inferred",
    verification_status: "unverified",
    rank_score: 50,
    members: [
      { id: "gamma", kind: "component", component_id: "gamma", file: null, line_start: null, line_end: null },
    ],
    evidence: [{ component_id: "gamma", path: "gamma", type: "module", files: ["gamma/a.ts"] }],
    detail: { type: "module" },
  };
}

// A CRA readiness gap: a zero-member finding of the P10-4 kind, carrying the
// clause reference and scope caveat in its detail (matches the projection shape).
function craFinding(): Finding {
  return {
    id: "finding:cra:security_md",
    kind: "cra_readiness",
    summary: "CRA readiness: Security policy (SECURITY.md) not found in the repository.",
    confidence: "inferred",
    verification_status: "unverified",
    rank_score: 72,
    members: [],
    evidence: [],
    detail: {
      item_id: "security_md",
      status: "absent",
      cra_clause: "Annex I Part II(5) coordinated vulnerability disclosure policy",
      scope: "Repo-observable CRA readiness only. It is NOT a conformity assessment.",
    },
  };
}

function loggingConcern(): Concern {
  return {
    id: "concern:logging",
    kind: "logging",
    title: "Logging",
    basis: "logging library imports",
    members: [
      { component_id: "alpha", evidence: [{ file: "alpha/x.ts", line: 3, signal: "import:structlog" }], files: [], markers: ["logger-import"] },
      { component_id: "beta", evidence: [{ file: "beta/y.ts", line: 4, signal: "import:loguru" }], files: [], markers: ["logger-import"] },
    ],
    detail: {},
  };
}

function archWithFindings(): Architecture {
  return makeArchitecture({
    components: [
      makeComponent({ id: "alpha", name: "Alpha", files: ["alpha/x.ts"] }),
      makeComponent({ id: "beta", name: "Beta", files: ["beta/y.ts"] }),
      makeComponent({ id: "gamma", name: "Gamma", files: ["gamma/a.ts"] }),
    ],
    findings: [orphanFinding(), dupFinding()], // deliberately out of rank order
    concerns: [loggingConcern()],
  });
}

function resetStore() {
  localStorage.clear();
  useArchStore.setState({
    architecture: null, selectedComponentId: null, breadcrumbs: [], drillLevel: null, detailItem: null, activePanel: null, lens: "structure",
    reviewMode: false, annotatingComponentId: null, annotatingTarget: null, annotations: [],
    selectionSets: [], setAnnotations: [],
    findingsSurface: { open: false, tab: "findings", kindFilter: null, elementFilter: null },
    stagedFindingSet: null,
  });
}

describe("Findings surface availability (P6-8, degrades like coverage)", () => {
  beforeEach(resetStore);

  it("is available only when the dataset carries findings or concerns", () => {
    expect(hasFindingsSurface(archWithFindings())).toBe(true);
    expect(hasFindingsSurface(makeArchitecture())).toBe(false);
    expect(hasFindingsSurface(makeArchitecture({ findings: [] , concerns: [] }))).toBe(false);
    // Concerns alone are enough to open the surface.
    expect(hasFindingsSurface(makeArchitecture({ concerns: [loggingConcern()] }))).toBe(true);
    expect(hasFindingsSurface(null)).toBe(false);
  });
});

describe("Findings ranking and filter (I11)", () => {
  beforeEach(resetStore);

  it("ranks findings by rank_score desc, ties by id (I11)", () => {
    useArchStore.getState().setArchitecture(archWithFindings());
    const ranked = useArchStore.getState().getFindings();
    expect(ranked.map((f) => f.id)).toEqual(["finding:duplication:aaa", "finding:orphan:gamma"]);
    for (let i = 1; i < ranked.length; i++) {
      expect(ranked[i - 1].rank_score).toBeGreaterThanOrEqual(ranked[i].rank_score);
    }
    expect(ranked[0].rank_score).toBe(Math.max(...ranked.map((f) => f.rank_score)));
  });

  it("sortFindings is a pure re-sort independent of input order", () => {
    const a = dupFinding();
    const b = orphanFinding();
    expect(sortFindings([b, a]).map((f) => f.id)).toEqual([a.id, b.id]);
  });

  it("lists exactly the kinds present and filters to one kind and back", () => {
    const findings = [dupFinding(), orphanFinding()];
    expect(findingKinds(findings)).toEqual(["duplication", "orphan"]);
    expect(filterFindingsByKind(findings, "orphan").map((f) => f.kind)).toEqual(["orphan"]);
    expect(filterFindingsByKind(findings, null)).toHaveLength(2);
    expect(filterFindingsByKind(findings, "all")).toHaveLength(2);
  });

  // P10-4: a repo-observable CRA readiness gap is a zero-member finding of a new
  // kind. The generic surface must list, rank, and filter it like any other.
  it("handles the zero-member cra_readiness kind (P10-4)", () => {
    const findings = [dupFinding(), craFinding()];
    expect(findingKinds(findings)).toEqual(["cra_readiness", "duplication"]);
    const ranked = sortFindings(findings);
    // dupFinding ranks 300, the cra gap 72, so the cra gap sorts below it.
    expect(ranked.map((f) => f.kind)).toEqual(["duplication", "cra_readiness"]);
    const cra = filterFindingsByKind(findings, "cra_readiness");
    expect(cra).toHaveLength(1);
    const gap = cra[0]!;
    expect(gap.members).toHaveLength(0);
    expect((gap.detail as { scope: string }).scope).toContain("NOT a conformity assessment");
  });
});

describe("Per-element findings and the contextual badge", () => {
  beforeEach(resetStore);

  it("derives a component's findings from finding members (robust)", () => {
    useArchStore.getState().setArchitecture(archWithFindings());
    // alpha is a member of the duplication finding only.
    expect(useArchStore.getState().getFindingsForComponent("alpha").map((f) => f.id)).toEqual([
      "finding:duplication:aaa",
    ]);
    // gamma is the orphan.
    expect(useArchStore.getState().getFindingsForComponent("gamma").map((f) => f.id)).toEqual([
      "finding:orphan:gamma",
    ]);
    // a component in no finding has none.
    expect(useArchStore.getState().getFindingsForComponent("delta")).toEqual([]);
    // The pure helper agrees with the store getter.
    expect(findingsForComponent(archWithFindings().findings!, "beta").map((f) => f.id)).toEqual([
      "finding:duplication:aaa",
    ]);
  });

  it("opens the surface filtered to an element and clears the filter", () => {
    useArchStore.getState().setArchitecture(archWithFindings());
    useArchStore.getState().openFindingsSurface({ elementFilter: "alpha" });
    let s = useArchStore.getState().findingsSurface;
    expect(s.open).toBe(true);
    expect(s.tab).toBe("findings"); // an element filter implies the findings tab
    expect(s.elementFilter).toBe("alpha");

    useArchStore.getState().openFindingsSurface({ elementFilter: null });
    s = useArchStore.getState().findingsSurface;
    expect(s.elementFilter).toBeNull();
  });

  it("reopening clears a stale kind filter so the contextual badge never shows an empty list", () => {
    useArchStore.getState().setArchitecture(archWithFindings());
    // Simulate a prior session that narrowed to orphan.
    useArchStore.getState().setFindingsKindFilter("orphan");
    // The contextual badge on alpha (whose only finding is a duplication) reopens
    // the surface filtered to alpha. Without the reset the stale orphan filter
    // would hide alpha's finding entirely.
    useArchStore.getState().openFindingsSurface({ elementFilter: "alpha" });
    const s = useArchStore.getState().findingsSurface;
    expect(s.kindFilter).toBeNull();
    expect(s.elementFilter).toBe("alpha");
    expect(useArchStore.getState().getFindingsForComponent("alpha")).toHaveLength(1);
  });
});

describe("Concerns browser (I12)", () => {
  beforeEach(resetStore);

  it("lists concerns with members and basis; a member resolves and navigates", () => {
    useArchStore.getState().setArchitecture(archWithFindings());
    const concerns = useArchStore.getState().getConcerns();
    expect(concerns.map((c) => c.id)).toEqual(["concern:logging"]);
    expect(concerns[0].basis).toBe("logging library imports");
    expect(concerns[0].members.map((m) => m.component_id)).toEqual(["alpha", "beta"]);

    // Selecting a member navigates to it (I12: same stable identity).
    useArchStore.getState().navigateToComponent("beta");
    expect(useArchStore.getState().selectedComponentId).toBe("beta");
    expect(useArchStore.getState().getConcernById("concern:logging")?.title).toBe("Logging");
  });
});

describe("I15 action affordances and the P6-9 seam", () => {
  beforeEach(resetStore);

  it("stages a finding's member set (the selection-set seam for P6-9)", () => {
    useArchStore.getState().setArchitecture(archWithFindings());
    useArchStore.getState().stageFindingSet(dupFinding());
    const staged = useArchStore.getState().stagedFindingSet!;
    expect(staged.findingId).toBe("finding:duplication:aaa");
    expect(staged.memberComponentIds).toEqual(["alpha", "beta"]); // deduped, in order
    expect(staged.memberCount).toBe(2);
  });

  it("annotate the set: builds a real selection set and opens the set annotation flow", () => {
    useArchStore.getState().setArchitecture(archWithFindings());
    const setId = useArchStore.getState().annotateFindingSet(dupFinding());
    expect(setId).toBeTruthy();
    const st = useArchStore.getState();
    // A real selection set was built from the finding's members (P6-9 engine),
    // replacing the old single-element annotation fallback.
    const created = st.getSetById(setId!)!;
    expect(created.origin).toBe("finding:duplication:aaa");
    expect(created.members.map((m) => m.componentId)).toEqual(["alpha", "beta"]);
    // The set annotation flow is open: review mode with the review panel visible.
    expect(st.reviewMode).toBe(true);
    expect(st.activePanel).toBe("review");
    expect(st.findingsSurface.open).toBe(false); // overlay closed to reveal the review panel
    expect(st.stagedFindingSet?.findingId).toBe("finding:duplication:aaa"); // membership still recorded
  });

  it("annotate reuses an existing set for the same finding instead of duplicating", () => {
    useArchStore.getState().setArchitecture(archWithFindings());
    const first = useArchStore.getState().annotateFindingSet(dupFinding());
    const second = useArchStore.getState().annotateFindingSet(dupFinding());
    expect(second).toBe(first);
    expect(useArchStore.getState().selectionSets.filter((s) => s.origin === "finding:duplication:aaa")).toHaveLength(1);
  });

  it("annotate returns null for a finding not present in the architecture", () => {
    const unknown: Finding = { ...dupFinding(), id: "finding:duplication:not-in-arch" };
    useArchStore.getState().setArchitecture(archWithFindings());
    expect(useArchStore.getState().annotateFindingSet(unknown)).toBeNull();
  });
});

describe("Verification status is preserved and never asserted as fact (I15)", () => {
  beforeEach(resetStore);

  it("every finding surfaces unverified until Phase 7 flips it", () => {
    useArchStore.getState().setArchitecture(archWithFindings());
    for (const f of useArchStore.getState().getFindings()) {
      expect(f.verification_status).toBe("unverified");
      expect(f.confidence).toBe("inferred");
      expect(f.evidence.length).toBeGreaterThan(0); // every finding carries evidence
    }
  });
});

describe("Reset on architecture reload", () => {
  beforeEach(resetStore);

  it("closes the surface and drops the staged set on reload", () => {
    useArchStore.getState().setArchitecture(archWithFindings());
    useArchStore.getState().openFindingsSurface({ elementFilter: "alpha" });
    useArchStore.getState().stageFindingSet(dupFinding());
    useArchStore.getState().setArchitecture(archWithFindings());
    expect(useArchStore.getState().findingsSurface).toEqual({ open: false, tab: "findings", kindFilter: null, elementFilter: null });
    expect(useArchStore.getState().stagedFindingSet).toBeNull();
  });
});
