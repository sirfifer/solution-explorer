import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup, within } from "@testing-library/react";
import { SupplyChainEntry } from "../components/SupplyChainEntry";
import { SupplyChainSurface } from "../components/SupplyChainSurface";
import {
  hasSupplyChain,
  dependenciesForEcosystem,
  filterByScope,
  evidenceLabel,
} from "../supplyChain/model";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";
import { useArchStore } from "../store";
import type { Architecture, SupplyChain } from "../types";

// The supply chain surface (P10-1). Driven against REAL analyzer output: the
// supply_chain sections in ./fixtures/*.json are emitted by
// analyzer.sbom.collect_supply_chain over the committed manifest fixtures, so the
// viewer is verified against the exact shape the projection produces, not a mock.
import npmSection from "./fixtures/supply_chain.npm.json";
import multiSection from "./fixtures/supply_chain.multi.json";
import mixedSection from "./fixtures/supply_chain.mixed.json";

const NPM = npmSection as unknown as SupplyChain;
const MULTI = multiSection as unknown as SupplyChain;
const MIXED = mixedSection as unknown as SupplyChain;

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
  useArchStore.setState({ architecture: arch, loading: false, error: null, darkMode: false });
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  useArchStore.setState({ architecture: null, supplyChainOpen: false });
});

// ---------------------------------------------------------------------------
// The real fixtures carry the shapes the analyzer emits.
// ---------------------------------------------------------------------------

describe("real analyzer output", () => {
  it("the npm fixture section is well formed", () => {
    expect(NPM.version).toBe(1);
    expect(NPM.sbom_endpoint).toBe("sbom.json");
    expect(NPM.sbom_format).toBe("CycloneDX 1.5");
    expect(NPM.counts.direct).toBe(3);
    expect(NPM.counts.transitive).toBe(1);
    // The vendored reference rode in from the coverage inventory.
    expect(NPM.vendored?.[0].path).toBe("node_modules");
  });

  it("the multi fixture spans every ecosystem and carries a parse warning", () => {
    const ids = MULTI.ecosystems.map((e) => e.id);
    expect(ids).toEqual(["npm", "pypi", "swift", "golang", "gem", "cargo", "cocoapods", "nuget"]);
    expect(MULTI.counts.warnings).toBeGreaterThan(0);
    // A language target/SDK version is surfaced separately.
    expect(MULTI.targets.some((t) => t.kind === "python")).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Model helpers.
// ---------------------------------------------------------------------------

describe("supply chain model", () => {
  it("hasSupplyChain gates on real content", () => {
    expect(hasSupplyChain(null)).toBe(false);
    expect(hasSupplyChain(makeArchitecture())).toBe(false);
    expect(hasSupplyChain(makeArchitecture({ supply_chain: NPM }))).toBe(true);
  });

  it("dependenciesForEcosystem and filterByScope select correctly", () => {
    const npm = dependenciesForEcosystem(NPM, "npm");
    expect(npm.length).toBe(4);
    expect(filterByScope(npm, "direct").length).toBe(3);
    expect(filterByScope(npm, "transitive").length).toBe(1);
    expect(filterByScope(npm, "all").length).toBe(4);
    // Ranked direct-before-transitive (the projection's order is preserved).
    const scopes = npm.map((d) => d.scope);
    expect(scopes.slice(0, 3).every((s) => s === "direct")).toBe(true);
    expect(scopes[3]).toBe("transitive");
  });

  it("evidenceLabel renders file and optional line", () => {
    expect(evidenceLabel({ file: "package.json", line: 12 })).toBe("package.json:12");
    expect(evidenceLabel({ file: "package.json" })).toBe("package.json");
  });
});

// ---------------------------------------------------------------------------
// Entry bar.
// ---------------------------------------------------------------------------

describe("SupplyChainEntry", () => {
  it("renders nothing without a supply_chain section", () => {
    setArch(makeArchitecture());
    const { container } = render(<SupplyChainEntry />);
    expect(container.firstChild).toBeNull();
  });

  it("renders counts and opens the surface", () => {
    setArch(makeArchitecture({ supply_chain: NPM }));
    render(<SupplyChainEntry />);
    expect(screen.getByLabelText(TOOLTIP_COPY.supplyChain.entry)).toBeDefined();
    expect(screen.getByText(/4 dependencies/)).toBeDefined();
    fireEvent.click(screen.getByTestId("supply-chain-entry"));
    expect(useArchStore.getState().supplyChainOpen).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Surface overlay.
// ---------------------------------------------------------------------------

describe("SupplyChainSurface", () => {
  it("is closed until opened", () => {
    setArch(makeArchitecture({ supply_chain: MULTI }));
    const { container } = render(<SupplyChainSurface />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the scope note, targets, ecosystems, and sbom link", () => {
    setArch(makeArchitecture({ supply_chain: MULTI }));
    useArchStore.setState({ supplyChainOpen: true });
    render(<SupplyChainSurface />);
    const dialog = screen.getByRole("dialog");

    // No-theater scope note is shown verbatim.
    expect(within(dialog).getByText(MULTI.scope_note)).toBeDefined();
    // Language targets called out at the top.
    expect(within(dialog).getByTestId("supply-chain-targets")).toBeDefined();
    // Every ecosystem section renders.
    for (const eco of MULTI.ecosystems) {
      expect(within(dialog).getByTestId(`supply-chain-ecosystem-${eco.id}`)).toBeDefined();
    }
    // The SBOM link points at the CycloneDX endpoint.
    const link = within(dialog).getByText("CycloneDX 1.5").closest("a");
    expect(link?.getAttribute("href")).toContain("sbom.json");
    // Parse warnings surface loudly.
    expect(within(dialog).getByTestId("supply-chain-warnings")).toBeDefined();
  });

  it("defaults to direct scope and switches to all", () => {
    setArch(makeArchitecture({ supply_chain: NPM }));
    useArchStore.setState({ supplyChainOpen: true });
    render(<SupplyChainSurface />);
    const dialog = screen.getByRole("dialog");

    // Direct default: the three direct npm deps show, the transitive one does not.
    expect(within(dialog).getByText("left-pad")).toBeDefined();
    expect(within(dialog).queryByText("undici")).toBeNull();

    // Switch to all: the transitive dep appears.
    fireEvent.click(within(dialog).getByText(/^all \(/));
    expect(within(dialog).getByText("undici")).toBeDefined();
  });

  it("renders pin-status and scope badges with dependency evidence", () => {
    setArch(makeArchitecture({ supply_chain: NPM }));
    useArchStore.setState({ supplyChainOpen: true });
    render(<SupplyChainSurface />);
    const dialog = screen.getByRole("dialog");
    // left-pad is an exact pin (bare 1.3.0 in npm); its badge and evidence render.
    expect(within(dialog).getAllByText("pinned").length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText("direct").length).toBeGreaterThan(0);
    expect(within(dialog).getByLabelText("Open package.json:6")).toBeDefined();
  });

  it("shows the vendored section when present", () => {
    setArch(makeArchitecture({ supply_chain: NPM }));
    useArchStore.setState({ supplyChainOpen: true });
    render(<SupplyChainSurface />);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByTestId("supply-chain-vendored")).toBeDefined();
    expect(within(dialog).getByText("node_modules")).toBeDefined();
  });

  it("closes on Escape", () => {
    setArch(makeArchitecture({ supply_chain: NPM }));
    useArchStore.setState({ supplyChainOpen: true });
    render(<SupplyChainSurface />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(useArchStore.getState().supplyChainOpen).toBe(false);
  });

  it("keeps fixture dependencies out of the shipping tables but accounts for them", () => {
    // The mixed fixture has one shipping dep (left-pad) and one fixture-origin
    // dep (fixture-only-dep) from a manifest under tests/fixtures (finding 1).
    expect(MIXED.counts.dependencies).toBe(1);
    expect(MIXED.counts.fixture.dependencies).toBe(1);
    setArch(makeArchitecture({ supply_chain: MIXED }));
    useArchStore.setState({ supplyChainOpen: true });
    render(<SupplyChainSurface />);
    const dialog = screen.getByRole("dialog");
    // The shipping dependency shows; the fixture dependency is hidden until the
    // fixture section is expanded (ranked behind, not deleted).
    expect(within(dialog).getByText("left-pad")).toBeDefined();
    expect(within(dialog).queryByText("fixture-only-dep")).toBeNull();
    const section = within(dialog).getByTestId("supply-chain-fixtures");
    fireEvent.click(within(section).getByRole("button"));
    expect(within(dialog).getByText("fixture-only-dep")).toBeDefined();
  });
});
