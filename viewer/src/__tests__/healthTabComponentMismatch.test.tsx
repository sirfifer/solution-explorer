import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { HealthTab } from "../components/admin/HealthTab";
import { useArchStore } from "../store";
import type { Architecture, AdminSummary } from "../types";

// Comprehension-study finding: a live install served two documents that
// silently disagreed about the same repository's component count
// (architecture/manifest.json: 254, admin-summary.json: 251), and nothing in
// the product flagged the contradiction -- a reviewer only found it by
// cross-checking two front doors by hand. HealthTab is the one place the
// product already holds both numbers at once (the loaded architecture's own
// stats.total_components, and the live admin summary's repo.component_count),
// so it is where the silent contradiction should become a visible one.

function makeArchitecture(totalComponents: number): Architecture {
  return {
    name: "T",
    description: "",
    repository: null,
    generated_at: "2026-08-19T02:35:45Z",
    analyzer_version: "2.0.0",
    root_path: "/t",
    components: [],
    relationships: [],
    symbols: [],
    files: [],
    stats: {
      total_files: 1,
      total_lines: 1,
      total_size_bytes: 1,
      languages: {},
      total_symbols: 0,
      total_components: totalComponents,
      total_relationships: 0,
    },
  };
}

function makeAdminData(componentCount: number): AdminSummary {
  return {
    repos: [
      {
        name: "unamentis",
        last_update: "2026-08-19T02:38:42Z",
        version: 1,
        component_count: componentCount,
        status: "ok",
      },
    ],
    activity: [],
    daily_counts: {},
    generated_at: "2026-08-19T02:38:43Z",
  };
}

describe("HealthTab component-count reconciliation", () => {
  afterEach(() => {
    cleanup();
    useArchStore.setState({ architecture: null });
  });

  it("flags a mismatch when the loaded architecture and the live admin summary disagree (the reproduced defect: 254 vs 251)", () => {
    useArchStore.setState({ architecture: makeArchitecture(254) });
    render(<HealthTab adminData={makeAdminData(251)} loading={false} />);

    // Both numbers are still shown (never hide data), but the contradiction
    // is now visible rather than silent.
    expect(screen.getByText("251")).toBeTruthy();
    expect(screen.getByText(/Component count mismatch/)).toBeTruthy();
    expect(screen.getByText(/254 components/)).toBeTruthy();
  });

  it("shows no mismatch warning when the two counts agree", () => {
    useArchStore.setState({ architecture: makeArchitecture(254) });
    render(<HealthTab adminData={makeAdminData(254)} loading={false} />);

    expect(screen.getByText("254")).toBeTruthy();
    expect(screen.queryByText(/Component count mismatch/)).toBeNull();
  });

  it("shows no mismatch warning when no architecture is loaded yet", () => {
    useArchStore.setState({ architecture: null });
    render(<HealthTab adminData={makeAdminData(251)} loading={false} />);

    expect(screen.getByText("251")).toBeTruthy();
    expect(screen.queryByText(/Component count mismatch/)).toBeNull();
  });
});
