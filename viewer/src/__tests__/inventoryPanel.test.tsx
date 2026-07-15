import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup, within } from "@testing-library/react";
import { CoverageBadge } from "../components/CoverageBadge";
import { useArchStore } from "../store";
import type { Architecture, Coverage, Inventory } from "../types";

// Non-source inventory viewer surface (P6-10). These drive the REAL store (no
// store mock, only fetch stubbed exactly as the live viewer fetches
// coverage.json) and the real CoverageBadge + InventoryPanel. The inventory
// object below is lifted verbatim from a real v2 projection of a synthesized
// xcresult-heavy tree (analyzer/project/inventory.py), so the viewer is tested
// against genuine analyzer output, not invented shapes.
//
// Fail-before proof: the "Explore inventory" affordance and the disproportion
// cue do not exist in the pre-P6-10 CoverageBadge, so every assertion that the
// affordance renders, opens the panel, and names the dominant group fails
// against the old implementation.

// Real analyzer output (analyzer/project/inventory.py, INVENTORY_VERSION 1).
const REAL_INVENTORY: Inventory = {
  version: 1,
  non_source_total: 12,
  source_gap_total: 0,
  groups: [
    {
      id: "build_test_output",
      label: "Build and test output",
      explanation:
        "Generated artifacts from building or testing, such as test result bundles, coverage reports, and logs.",
      recommendation:
        "Remove from version control and add to .gitignore. These are regenerated on every build.",
      count: 8,
      bytes: 40,
      directory_rows: 0,
      extensions: [{ ext: ".bin", count: 8 }],
      top_directories: [{ dir: "TestResults.xcresult", count: 8 }],
      samples: [
        "TestResults.xcresult/Data/blob0.bin",
        "TestResults.xcresult/Data/blob1.bin",
        "TestResults.xcresult/Data/blob2.bin",
        "TestResults.xcresult/Data/blob3.bin",
        "TestResults.xcresult/Data/blob4.bin",
        "TestResults.xcresult/Data/blob5.bin",
        "TestResults.xcresult/Data/blob6.bin",
        "TestResults.xcresult/Data/blob7.bin",
      ],
      flags: { security_sensitive: false, likely_unwanted: true, gitignore_candidate: true },
    },
    {
      id: "product_assets",
      label: "Product assets",
      explanation: "Images, fonts, media, and asset catalogs the product ships.",
      recommendation: "Keep. Expected here. Consider Git LFS if large binaries bloat the history.",
      count: 2,
      bytes: 17,
      directory_rows: 0,
      extensions: [
        { ext: ".png", count: 1 },
        { ext: ".svg", count: 1 },
      ],
      top_directories: [{ dir: "(root)", count: 2 }],
      samples: ["icon.svg", "logo.png"],
      flags: { security_sensitive: false, likely_unwanted: false, gitignore_candidate: false },
    },
    {
      id: "secrets",
      label: "Certificates, keys, and secret-shaped files",
      explanation: "Files shaped like certificates, private keys, or credential stores.",
      recommendation:
        "Verify intent. If any of these are real secrets, remove them from history and rotate the credential.",
      count: 1,
      bytes: 11,
      directory_rows: 0,
      extensions: [{ ext: ".pem", count: 1 }],
      top_directories: [{ dir: "certs", count: 1 }],
      samples: ["certs/server.pem"],
      flags: { security_sensitive: true, likely_unwanted: false, gitignore_candidate: false },
    },
    {
      id: "os_cruft",
      label: "Operating system cruft",
      explanation: "Files the operating system drops into folders, such as .DS_Store and Thumbs.db.",
      recommendation: "Remove from version control and add to .gitignore. These never belong in a repository.",
      count: 1,
      bytes: 1,
      directory_rows: 0,
      extensions: [{ ext: "(none)", count: 1 }],
      top_directories: [{ dir: "(root)", count: 1 }],
      samples: [".DS_Store"],
      flags: { security_sensitive: false, likely_unwanted: true, gitignore_candidate: true },
    },
  ],
  dominant: { id: "build_test_output", count: 8, share: 0.6667 },
};

const SUMMARY = { parsed: 1, binary: 11, "excluded:unsupported_extension": 1 };

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
    coverageInventory: null,
    darkMode: false,
  });
}

function stubCoverageFetch(withInventory: boolean) {
  const json = {
    summary: SUMMARY,
    total: 13,
    parsed: 1,
    rows: [
      { path: ".DS_Store", disposition: "binary", reason: "null_byte" },
      { path: "certs/server.pem", disposition: "excluded:unsupported_extension", reason: ".pem" },
    ],
    ...(withInventory ? { inventory: REAL_INVENTORY } : {}),
  };
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => json })));
}

// Open the coverage badge panel, which lazily loads coverage.json (and with it
// the inventory), then return once the inventory has landed.
async function openBadgeAndLoad() {
  fireEvent.click(screen.getByTestId("coverage-badge"));
  await waitFor(() => {
    expect(useArchStore.getState().coverageInventory).not.toBeNull();
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
    coverageInventory: null,
    fileDeepLink: null,
    fileDeepLinkNotice: null,
  });
});

describe("inventory affordance from the coverage drill-in", () => {
  it("offers Explore inventory once the inventory loads, and opens the panel", async () => {
    stubCoverageFetch(true);
    const coverage: Coverage = { summary: SUMMARY, total: 13, parsed: 1 };
    setArch(makeArchitecture({ coverage }));
    render(<CoverageBadge />);

    await openBadgeAndLoad();
    const explore = await screen.findByTestId("inventory-explore");
    fireEvent.click(explore);

    // The modal opens with the header and the total.
    expect(screen.getByRole("dialog", { name: "Non-source inventory" })).toBeDefined();
    expect(screen.getByText("Non-source inventory")).toBeDefined();
  });

  it("does not offer the affordance for an old dataset without an inventory", async () => {
    stubCoverageFetch(false);
    const coverage: Coverage = { summary: SUMMARY, total: 13, parsed: 1 };
    setArch(makeArchitecture({ coverage }));
    render(<CoverageBadge />);

    fireEvent.click(screen.getByTestId("coverage-badge"));
    await waitFor(() => {
      expect(useArchStore.getState().coverageRows).not.toBeNull();
    });
    // Coverage rows loaded, but no inventory: the affordance never appears.
    expect(useArchStore.getState().coverageInventory).toBeNull();
    expect(screen.queryByTestId("inventory-explore")).toBeNull();
  });
});

describe("inventory panel rendering and ranking", () => {
  async function openPanel() {
    stubCoverageFetch(true);
    const coverage: Coverage = { summary: SUMMARY, total: 13, parsed: 1 };
    setArch(makeArchitecture({ coverage }));
    render(<CoverageBadge />);
    await openBadgeAndLoad();
    fireEvent.click(await screen.findByTestId("inventory-explore"));
  }

  it("ranks groups by count, build and test output first (I11)", async () => {
    await openPanel();
    const cards = screen.getAllByTestId("inventory-group");
    expect(cards.map((c) => c.getAttribute("data-group-id"))).toEqual([
      "build_test_output",
      "product_assets",
      "secrets",
      "os_cruft",
    ]);
  });

  it("shows each group's recommendation and the dominant + security badges", async () => {
    await openPanel();
    // Every group's recommendation is visible.
    const recs = screen.getAllByTestId("inventory-recommendation");
    expect(recs.length).toBe(4);
    expect(
      recs.some((r) => (r.textContent ?? "").includes("Remove from version control")),
    ).toBe(true);
    // The dominant group is badged, and the security-sensitive group is flagged.
    expect(screen.getByText("dominant")).toBeDefined();
    expect(screen.getByText("security")).toBeDefined();
  });

  it("names the dominant group when non-source dwarfs source (disproportion cue)", async () => {
    await openPanel();
    const banner = screen.getByTestId("inventory-disproportion");
    // 12 non-source files versus 1 analyzed source is more than 3 to 1.
    expect(banner.textContent).toContain("more than 3 to 1");
    expect(banner.textContent).toContain("build and test output");
  });

  it("suppresses the disproportion cue when zero source was analyzed", async () => {
    // With no analyzed source the ratio is undefined, so the banner must not
    // fire even though a dominant group exists. Review finding on the P6-10 PR:
    // the pre-fix cue treated 0 as a valid denominator and always fired.
    stubCoverageFetch(true);
    const coverage: Coverage = {
      summary: { binary: 11, "excluded:unsupported_extension": 1 },
      total: 12,
      parsed: 0,
    };
    setArch(makeArchitecture({ coverage }));
    render(<CoverageBadge />);
    await openBadgeAndLoad();
    fireEvent.click(await screen.findByTestId("inventory-explore"));
    expect(screen.queryByTestId("inventory-disproportion")).toBeNull();
  });

  it("expands a group to its files and extension breakdown", async () => {
    await openPanel();
    const buildCard = screen
      .getAllByTestId("inventory-group")
      .find((c) => c.getAttribute("data-group-id") === "build_test_output")!;
    // Expand the group header (the first button in the card).
    fireEvent.click(within(buildCard).getAllByRole("button")[0]);
    expect(within(buildCard).getByText("TestResults.xcresult/Data/blob0.bin")).toBeDefined();
    expect(within(buildCard).getByText(/\.bin 8/)).toBeDefined();
  });

  it("drills into a file path through the real store navigation", async () => {
    await openPanel();
    const buildCard = screen
      .getAllByTestId("inventory-group")
      .find((c) => c.getAttribute("data-group-id") === "build_test_output")!;
    fireEvent.click(within(buildCard).getAllByRole("button")[0]);
    fireEvent.click(within(buildCard).getByText("TestResults.xcresult/Data/blob0.bin"));
    // No component owns a non-source file, so the store records an honest
    // missing-owner notice rather than throwing.
    await waitFor(() => {
      expect(useArchStore.getState().fileDeepLinkNotice).toContain("TestResults.xcresult");
    });
  });
});
