import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { SolutionIndex } from "../components/SolutionIndex";
import { InventoryPanel } from "../components/InventoryPanel";
import { CoverageBadge } from "../components/CoverageBadge";
import { useArchStore } from "../store";
import type { Architecture, RepositoryInfo, SolutionManifest, SolutionMember } from "../types";
import { SOLUTION_MANIFEST_KIND } from "../types";

// O4: the UI must never promise, reference, or imply coverage information a
// dataset does not carry. These tests target surfaces the orchestrator's
// finding named directly: SolutionIndex's "no source gaps" summary (which was
// indistinguishable from "no member ever measured coverage"), and the
// non-source InventoryPanel's "coverage ledger" pointer (which the PRINCIPLE
// allows only because it is unreachable without a real ledger to point at).

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  useArchStore.setState({
    architecture: null,
    coverageRows: null,
    coverageRowsLoading: false,
    coverageRowsError: null,
    coverageInventory: null,
  });
});

function makeMember(overrides: Partial<SolutionMember> = {}): SolutionMember {
  return {
    slug: "svc",
    label: "Service",
    resolved: true,
    path: "members/svc",
    projection: "members/svc",
    stats: { total_components: 3, total_files: 10, total_lines: 100, total_symbols: 5, total_relationships: 2 },
    ...overrides,
  };
}

function makeSolution(overrides: Partial<SolutionManifest> = {}): SolutionManifest {
  return {
    schema: "solution-explorer/1",
    kind: SOLUTION_MANIFEST_KIND,
    name: "Demo Solution",
    generated_at: "2026-08-18T00:00:00Z",
    analyzer_version: "1.2.0",
    members: [makeMember()],
    summary: {
      member_count: 1,
      composed_count: 1,
      unresolved_count: 0,
      error_count: 0,
      total_source_files: 10,
      total_source_analyzed: 10,
      total_nonsource_files: 0,
      total_files: 10,
      total_lines: 100,
      members_with_gaps: [],
    },
    ...overrides,
  };
}

describe("SolutionIndex summary line (O4)", () => {
  it("does not claim 'no source gaps' when no member carries any coverage data at all (fail-before)", () => {
    // members_with_gaps is empty here for the SAME reason it would be empty
    // if every member were clean: no coverage data exists to find a gap in.
    // Before the fix this rendered the reassuring green "No source gaps in
    // any member" line regardless of which case it was.
    const solution = makeSolution({ members: [makeMember({ coverage: undefined })] });
    render(<SolutionIndex solution={solution} solutionBase="./architecture" darkMode={false} />);
    expect(screen.queryByText(/No source gaps in any member/)).toBeNull();
    expect(screen.getByText(/Coverage data is not available for these members/)).toBeTruthy();
  });

  it("still shows the honest 'no gaps' line when members do carry coverage and none has a gap", () => {
    const solution = makeSolution({
      members: [
        makeMember({
          coverage: {
            summary: { parsed: 10 },
            families: { analyzed: 10, gap: 0, nonsource: 0, source_total: 10 },
            source_percent: "100",
            has_gaps: false,
          },
        }),
      ],
    });
    render(<SolutionIndex solution={solution} solutionBase="./architecture" darkMode={false} />);
    expect(screen.getByText(/No source gaps in any member/)).toBeTruthy();
    expect(screen.queryByText(/Coverage data is not available/)).toBeNull();
  });

  it("shows the gap list when members_with_gaps is non-empty, unaffected by the fix", () => {
    const solution = makeSolution({ summary: { ...makeSolution().summary, members_with_gaps: ["svc"] } });
    render(<SolutionIndex solution={solution} solutionBase="./architecture" darkMode={false} />);
    expect(screen.getByText(/Source gaps in: svc/)).toBeTruthy();
    expect(screen.queryByText(/Coverage data is not available/)).toBeNull();
    expect(screen.queryByText(/No source gaps in any member/)).toBeNull();
  });
});

describe("InventoryPanel's coverage-ledger pointer is unreachable without a real ledger (O4)", () => {
  function makeArchitecture(overrides: Partial<Architecture> = {}): Architecture {
    return {
      name: "Demo",
      description: "A demo project",
      repository: null,
      generated_at: "2025-01-01T00:00:00Z",
      analyzer_version: "1.2.0",
      root_path: "/demo",
      components: [],
      relationships: [],
      symbols: [],
      files: [],
      stats: {
        total_files: 0,
        total_lines: 0,
        total_size_bytes: 0,
        languages: {},
        total_symbols: 0,
        total_components: 0,
        total_relationships: 0,
      },
      ...overrides,
    };
  }

  it("CoverageBadge offers no 'Explore inventory' affordance when the dataset carries no coverage key, even with repositories present", () => {
    const repositories: RepositoryInfo[] = [{ name: "repo" }];
    useArchStore.setState({ architecture: makeArchitecture({ repositories }), darkMode: false });
    render(<CoverageBadge />);
    // The only honest surface left is the plain "unavailable" note.
    expect(screen.getByTestId("coverage-unavailable")).toBeDefined();
    expect(screen.queryByTestId("inventory-explore")).toBeNull();
    // With no way to open it, InventoryPanel's own "coverage ledger" text
    // (asserted directly below) is never mounted, so it never renders here.
    expect(screen.queryByText(/coverage ledger/i)).toBeNull();
  });

  it("InventoryPanel itself never mounts with an open dataset that has no coverage inventory", () => {
    // Direct-mount InventoryPanel with open=true (bypassing the badge's own
    // gating) to prove the component has no independent path to the
    // "coverage ledger" text when the store carries no inventory: coverageInventory
    // stays null, groups is [], and the sample list (and its "coverage
    // ledger" caption) has nothing to render for.
    useArchStore.setState({
      architecture: makeArchitecture(),
      coverageInventory: null,
      coverageRowsLoading: false,
    });
    const { container } = render(<InventoryPanel open={true} onClose={() => {}} />);
    expect(container.textContent).not.toMatch(/coverage ledger/i);
  });
});
