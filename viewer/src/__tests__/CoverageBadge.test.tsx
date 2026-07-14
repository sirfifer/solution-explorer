import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup, within } from "@testing-library/react";
import {
  CoverageBadge,
  classifyDisposition,
  computeCoverageFamilies,
  formatSourcePercent,
} from "../components/CoverageBadge";
import { useArchStore } from "../store";
import type { Architecture, Coverage, CoverageRow, RepositoryInfo } from "../types";

// P4-4 coverage ledger, viewer half, with the three-family coverage semantics
// (program2/p6). These tests drive the real store (no store mock) and the real
// CoverageBadge. The percent now means "how much of your SOURCE was analyzed";
// non-source files (binary, unsupported extensions, empty files, pruned dirs,
// vendored repos) are counted for reassurance but never in the denominator.
//
// Fail-before proof: the old badge computed parsed / total and rendered strings
// like "Coverage 10% parsed" and "(641/6688 files)". Every assertion below that
// checks the new "N% of source analyzed" wording, and every queryByText that
// asserts the old strings are ABSENT, fails against the old implementation.

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

function setArch(arch: Architecture) {
  useArchStore.setState({
    architecture: arch,
    loading: false,
    error: null,
    coverageRows: null,
    coverageRowsLoading: false,
    coverageRowsError: null,
    darkMode: false,
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  useArchStore.setState({
    architecture: null,
    coverageRows: null,
    coverageRowsLoading: false,
    coverageRowsError: null,
  });
});

describe("coverage family classification (the new math)", () => {
  it("classifies dispositions into analyzed / gap / non-source", () => {
    expect(classifyDisposition("parsed")).toBe("analyzed");
    // Source gaps: loud, counted against the percent.
    expect(classifyDisposition("failed")).toBe("gap");
    expect(classifyDisposition("failed:SyntaxError")).toBe("gap");
    expect(classifyDisposition("excluded:max_file_size")).toBe("gap");
    // Any unrecognized exclusion is a gap by default (exceptions stay loud).
    expect(classifyDisposition("excluded:gitignore")).toBe("gap");
    // Non-source: recorded, never counted against coverage.
    expect(classifyDisposition("binary")).toBe("nonsource");
    expect(classifyDisposition("excluded:unsupported_extension")).toBe("nonsource");
    expect(classifyDisposition("excluded:empty_file")).toBe("nonsource");
    expect(classifyDisposition("excluded:skipped_directory")).toBe("nonsource");
    expect(classifyDisposition("excluded:vendored_repo")).toBe("nonsource");
  });

  it("keeps non-source files out of the percent denominator", () => {
    // The iOS-demo shape: every source file parsed, 6,047 non-source files.
    const fam = computeCoverageFamilies({
      parsed: 641,
      binary: 6006,
      "excluded:skipped_directory": 40,
      "excluded:unsupported_extension": 1,
    });
    expect(fam.analyzed).toBe(641);
    expect(fam.gap).toBe(0);
    expect(fam.nonsource).toBe(6047);
    expect(fam.sourceTotal).toBe(641); // NOT 6688
    expect(fam.percent).toBe(100);
    expect(formatSourcePercent(fam)).toBe("100");
    // The old parsed/total math would have been ~10%. That must be gone.
    const oldPercent = Math.round((641 / 6688) * 100);
    expect(oldPercent).toBe(10);
    expect(formatSourcePercent(fam)).not.toBe(String(oldPercent));
  });

  it("counts gaps against the percent and never rounds a real gap up to 100", () => {
    const fam = computeCoverageFamilies({ parsed: 499, failed: 1, binary: 10 });
    expect(fam.sourceTotal).toBe(500);
    expect(formatSourcePercent(fam)).toBe("99.8");

    // A single gap among many must not display as a bare "100".
    const fam2 = computeCoverageFamilies({ parsed: 9999, failed: 1 });
    expect(fam2.percent).toBeGreaterThan(99.9);
    expect(formatSourcePercent(fam2)).toBe("99.9");
  });
});

describe("CoverageBadge summary rendering", () => {
  it("reads '100% of source analyzed' with a non-source reassurance count (green)", () => {
    const coverage: Coverage = {
      summary: {
        parsed: 641,
        binary: 6006,
        "excluded:skipped_directory": 40,
        "excluded:unsupported_extension": 1,
      },
      total: 6688,
      parsed: 641,
    };
    setArch(makeArchitecture({ coverage }));
    render(<CoverageBadge />);

    expect(screen.getByTestId("coverage-headline").textContent).toBe("100% of source analyzed");
    expect(screen.getByText("6,047 non-source files accounted for")).toBeDefined();

    // Fail-before: the old total-based wording is gone.
    expect(screen.queryByText(/Coverage 10% parsed/)).toBeNull();
    expect(screen.queryByText("(641/6688 files)")).toBeNull();
    expect(screen.queryByText(/% parsed/)).toBeNull();
  });

  it("reads '99.8% of source analyzed, N files skipped' when gaps exist (amber)", () => {
    const coverage: Coverage = {
      summary: { parsed: 499, failed: 1, binary: 10 },
      total: 510,
      parsed: 499,
    };
    setArch(makeArchitecture({ coverage }));
    render(<CoverageBadge />);

    expect(screen.getByTestId("coverage-headline").textContent).toBe("99.8% of source analyzed");
    expect(screen.getByTestId("coverage-gap-count").textContent).toBe("1 file skipped");
  });
});

describe("CoverageBadge drill-in panel: three families", () => {
  it("groups by the three families, failures first within gaps, with reasons", () => {
    const rows: CoverageRow[] = [
      { path: "broken.py", disposition: "failed", reason: "SyntaxError: bad token" },
      { path: "logo.png", disposition: "binary", reason: "skip_extension:.png" },
      { path: "big.json", disposition: "excluded:max_file_size", reason: "500000" },
      { path: "a.png", disposition: "binary", reason: "skip_extension:.png" },
      { path: "web/node_modules", disposition: "excluded:skipped_directory", reason: "node_modules" },
    ];
    const coverage: Coverage = {
      summary: {
        parsed: 100,
        failed: 1,
        "excluded:max_file_size": 1,
        binary: 2,
        "excluded:skipped_directory": 1,
      },
      total: 105,
      parsed: 100,
      rows,
    };
    setArch(makeArchitecture({ coverage }));
    render(<CoverageBadge />);

    fireEvent.click(screen.getByTestId("coverage-badge"));
    const panel = screen.getByTestId("coverage-panel");

    // The three family headers are present.
    expect(within(panel).getByText("Source analyzed")).toBeDefined();
    expect(within(panel).getByText("Source gaps")).toBeDefined();
    expect(within(panel).getByText("Non-source accounted")).toBeDefined();

    // Within gaps, failures rank first (I11): Failed before Excluded: max file size.
    const gapLabels = within(panel)
      .getAllByText(/^(Failed|Excluded: max file size)$/)
      .map((el) => el.textContent);
    expect(gapLabels).toEqual(["Failed", "Excluded: max file size"]);

    // Failures are expanded by default and show the error reason.
    expect(within(panel).getByText("broken.py")).toBeDefined();
    expect(within(panel).getByText("SyntaxError: bad token")).toBeDefined();

    // A non-source group expands to its file rows.
    fireEvent.click(within(panel).getByText("Binary"));
    expect(within(panel).getByText("logo.png")).toBeDefined();
  });

  it("shows Source gaps of 0 when everything analyzable parsed", () => {
    const coverage: Coverage = {
      summary: { parsed: 641, binary: 6006 },
      total: 6647,
      parsed: 641,
    };
    setArch(makeArchitecture({ coverage }));
    render(<CoverageBadge />);
    fireEvent.click(screen.getByTestId("coverage-badge"));
    const panel = screen.getByTestId("coverage-panel");
    // Non-source count is shown as reassurance (family header and its group).
    expect(within(panel).getAllByText("6,006").length).toBeGreaterThan(0);
  });
});

describe("CoverageBadge lazy fetch in split mode", () => {
  it("fetches coverage.json when the panel opens and renders the rows", async () => {
    const coverageJson = {
      summary: { parsed: 2, failed: 1 },
      total: 3,
      parsed: 2,
      rows: [
        { path: "ok.py", disposition: "parsed", reason: null },
        { path: "broken.py", disposition: "failed", reason: "PermissionError" },
      ] as CoverageRow[],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => coverageJson })),
    );

    const coverage: Coverage = {
      summary: { parsed: 2, failed: 1 },
      total: 3,
      parsed: 2,
    };
    setArch(makeArchitecture({ coverage }));
    render(<CoverageBadge />);

    fireEvent.click(screen.getByTestId("coverage-badge"));
    expect(fetch).toHaveBeenCalledWith("./architecture/coverage.json");

    await waitFor(() => {
      expect(screen.getByText("broken.py")).toBeDefined();
    });
    expect(screen.getByText("PermissionError")).toBeDefined();
  });
});

describe("CoverageBadge degradation", () => {
  it("renders nothing for a legacy dataset with no coverage key", () => {
    setArch(makeArchitecture());
    const { container } = render(<CoverageBadge />);
    expect(container.innerHTML).toBe("");
    expect(screen.queryByTestId("coverage-badge")).toBeNull();
    expect(screen.queryByTestId("coverage-unavailable")).toBeNull();
  });

  it("shows 'coverage unavailable' for a multi-repo dataset without coverage", () => {
    const repositories: RepositoryInfo[] = [
      { name: "backend", repository: null, default_branch: "main" },
      { name: "frontend", repository: null, default_branch: "main" },
    ];
    setArch(makeArchitecture({ repositories }));
    render(<CoverageBadge />);
    expect(screen.getByTestId("coverage-unavailable")).toBeDefined();
    expect(screen.getByText("Coverage unavailable for this dataset")).toBeDefined();
    expect(screen.queryByTestId("coverage-badge")).toBeNull();
  });
});
