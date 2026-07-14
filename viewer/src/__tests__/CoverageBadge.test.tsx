import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup, within } from "@testing-library/react";
import { CoverageBadge } from "../components/CoverageBadge";
import { useArchStore } from "../store";
import type { Architecture, Coverage, CoverageRow, RepositoryInfo } from "../types";

// P4-4 coverage ledger, viewer half. These tests drive the real store (no store
// mock) and the real CoverageBadge. They assert:
//   - the badge renders percent parsed and counts per disposition from a
//     coverage-bearing manifest;
//   - the drill-in panel groups by rule and ranks failures first then by count
//     (LENS-DESIGN.md I11);
//   - a legacy dataset with no coverage key renders nothing (identical output);
//   - a multi-repo dataset without coverage shows the unavailable message;
//   - split mode lazy-fetches coverage.json for the row detail.

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
  // Set the architecture directly and reset coverage state, mirroring what
  // setArchitecture does, without pulling in annotation persistence side effects.
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

describe("CoverageBadge summary rendering", () => {
  it("renders percent parsed and counts per disposition from the manifest summary", () => {
    const coverage: Coverage = {
      summary: {
        parsed: 491,
        "excluded:skipped_directory": 19,
        "excluded:unsupported_extension": 7,
        binary: 6,
        "excluded:max_file_size": 5,
        "excluded:empty_file": 1,
      },
      total: 529,
      parsed: 491,
      // No rows: split-mode manifest summary.
    };
    setArch(makeArchitecture({ coverage }));
    render(<CoverageBadge />);

    // 491 / 529 = 92.8 -> 93%.
    expect(screen.getByText("Coverage 93% parsed")).toBeDefined();
    expect(screen.getByText("(491/529 files)")).toBeDefined();
    // A chip per non-parsed disposition (counts per disposition).
    const badge = screen.getByTestId("coverage-badge");
    expect(within(badge).getByText(/19 excluded: skipped directory/)).toBeDefined();
    expect(within(badge).getByText(/6 binary/)).toBeDefined();
    // No "parsed" chip (parsed is the headline, not a chip).
    expect(within(badge).queryByText(/491 parsed/)).toBeNull();
  });
});

describe("CoverageBadge drill-in panel grouping and ranking (I11)", () => {
  it("lists failures first, then exclusions ranked by count, with reasons", () => {
    const rows: CoverageRow[] = [
      { path: "broken.py", disposition: "failed", reason: "SyntaxError: bad token" },
      { path: "logo.png", disposition: "binary", reason: "skip_extension:.png" },
      { path: "big.json", disposition: "excluded:max_file_size", reason: "500000" },
      { path: "a.png", disposition: "binary", reason: "skip_extension:.png" },
      { path: "web/node_modules", disposition: "excluded:skipped_directory", reason: "node_modules" },
      { path: "web/dist", disposition: "excluded:skipped_directory", reason: "dist" },
      { path: ".git", disposition: "excluded:skipped_directory", reason: "vcs" },
    ];
    const coverage: Coverage = {
      summary: {
        parsed: 100,
        failed: 1,
        binary: 2,
        "excluded:max_file_size": 1,
        "excluded:skipped_directory": 3,
      },
      total: 107,
      parsed: 100,
      rows, // inline (monolith): no fetch needed.
    };
    setArch(makeArchitecture({ coverage }));
    render(<CoverageBadge />);

    // Open the panel.
    fireEvent.click(screen.getByTestId("coverage-badge"));
    const panel = screen.getByTestId("coverage-panel");

    // Group headers in DOM order. failed is first despite count 1 (I11 failures
    // first), then excluded:skipped_directory (3), then binary (2), then
    // excluded:max_file_size (1); ties broken by name.
    const labels = within(panel)
      .getAllByText(
        /^(Failed|Binary|Excluded: skipped directory|Excluded: max file size)$/,
      )
      .map((el) => el.textContent);
    expect(labels).toEqual([
      "Failed",
      "Excluded: skipped directory",
      "Binary",
      "Excluded: max file size",
    ]);

    // Failures are expanded by default and show the error reason.
    expect(within(panel).getByText("broken.py")).toBeDefined();
    expect(within(panel).getByText("SyntaxError: bad token")).toBeDefined();

    // An excluded-directory group is a single row per directory whose reason
    // names the pruning rule; expanding it shows the directory paths.
    fireEvent.click(within(panel).getByText("Excluded: skipped directory"));
    expect(within(panel).getByText("web/node_modules")).toBeDefined();
    expect(within(panel).getByText(".git")).toBeDefined();
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

    // Manifest summary only (no inline rows): the split-mode shape.
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
    setArch(makeArchitecture()); // no coverage, no repositories
    const { container } = render(<CoverageBadge />);
    // Absent key changes nothing: the component contributes no DOM.
    expect(container.innerHTML).toBe("");
    expect(screen.queryByTestId("coverage-badge")).toBeNull();
    expect(screen.queryByTestId("coverage-unavailable")).toBeNull();
  });

  it("shows 'coverage unavailable' for a multi-repo dataset without coverage", () => {
    const repositories: RepositoryInfo[] = [
      { name: "backend", repository: null, default_branch: "main" },
      { name: "frontend", repository: null, default_branch: "main" },
    ];
    setArch(makeArchitecture({ repositories })); // repositories but no coverage
    render(<CoverageBadge />);
    expect(screen.getByTestId("coverage-unavailable")).toBeDefined();
    expect(screen.getByText("Coverage unavailable for this dataset")).toBeDefined();
    // No fake percentage.
    expect(screen.queryByTestId("coverage-badge")).toBeNull();
  });
});
