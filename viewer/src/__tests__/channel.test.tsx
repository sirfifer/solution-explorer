import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import {
  resolveChannel,
  isMaturityActive,
  maturitySuffix,
  channelLevel,
  isChannel,
  DEFAULT_CHANNEL,
} from "../utils/channel";
import {
  registerLens,
  listAvailableLenses,
  resolveLensId,
  DEFAULT_LENS_ID,
  type LensDefinition,
} from "../lenses";
import { LensSwitcher } from "../components/LensSwitcher";
import { useArchStore } from "../store";
import type { Architecture, Component } from "../types";

// Maturity-channel gating on the client (card R3): channel resolution, the
// registry's maturity filter, and the explicit "experimental" label in the UI.

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
    analyzer_version: "1.2.0", root_path: "/t",
    components: [makeComponent({ id: "a" })],
    relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    ...overrides,
  };
}

// Two test-only lenses declaring non-stable maturities, registered to exercise
// the filter. Unique ids so they cannot collide with the real lenses.
const expLens: LensDefinition = {
  id: "test-exp-lens",
  label: "Experimental Test",
  description: "an experimental test lens",
  maturity: "experimental",
  isAvailable: () => true,
  getGraph: () => ({ nodes: [], aggregates: [], edges: [] }),
  questions: [],
};
const betaLens: LensDefinition = {
  id: "test-beta-lens",
  label: "Beta Test",
  description: "a beta test lens",
  maturity: "beta",
  isAvailable: () => true,
  getGraph: () => ({ nodes: [], aggregates: [], edges: [] }),
  questions: [],
};
registerLens(expLens);
registerLens(betaLens);

describe("channel resolution", () => {
  it("defaults to stable with no override and a production build", () => {
    expect(resolveChannel("", false)).toBe("stable");
    expect(DEFAULT_CHANNEL).toBe("stable");
  });

  it("honors a ?channel= URL-param override", () => {
    expect(resolveChannel("?channel=experimental", false)).toBe("experimental");
    expect(resolveChannel("?channel=beta", false)).toBe("beta");
    expect(resolveChannel("?channel=stable", true)).toBe("stable");
  });

  it("ignores an invalid ?channel= value and falls back to the build baseline", () => {
    expect(resolveChannel("?channel=nightly", false)).toBe("stable");
    expect(resolveChannel("?channel=nightly", true)).toBe("experimental");
  });

  it("an experimental build defaults to experimental without a param", () => {
    expect(resolveChannel("", true)).toBe("experimental");
  });

  it("isChannel guards the three valid values", () => {
    expect(isChannel("stable")).toBe(true);
    expect(isChannel("beta")).toBe(true);
    expect(isChannel("experimental")).toBe(true);
    expect(isChannel("nightly")).toBe(false);
    expect(isChannel(null)).toBe(false);
  });
});

describe("maturity activation semantics", () => {
  it("channelLevel orders the channels", () => {
    expect(channelLevel("stable")).toBe(0);
    expect(channelLevel("beta")).toBe(1);
    expect(channelLevel("experimental")).toBe(2);
  });

  it("isMaturityActive is Rust-toolchain: channel >= feature level", () => {
    // undefined maturity means stable, always active
    expect(isMaturityActive(undefined, "stable")).toBe(true);
    expect(isMaturityActive("stable", "stable")).toBe(true);
    // beta feature
    expect(isMaturityActive("beta", "stable")).toBe(false);
    expect(isMaturityActive("beta", "beta")).toBe(true);
    expect(isMaturityActive("beta", "experimental")).toBe(true);
    // experimental feature
    expect(isMaturityActive("experimental", "stable")).toBe(false);
    expect(isMaturityActive("experimental", "beta")).toBe(false);
    expect(isMaturityActive("experimental", "experimental")).toBe(true);
  });

  it("maturitySuffix labels only non-stable surfaces", () => {
    expect(maturitySuffix(undefined)).toBe("");
    expect(maturitySuffix("stable")).toBe("");
    expect(maturitySuffix("beta")).toBe(" (beta)");
    expect(maturitySuffix("experimental")).toBe(" (experimental)");
  });
});

describe("registry maturity filter", () => {
  const arch = makeArchitecture();

  it("stable channel hides beta and experimental lenses", () => {
    const ids = listAvailableLenses(arch, "stable").map((l) => l.id);
    expect(ids).toContain("structure"); // a real stable lens still shows
    expect(ids).not.toContain("test-beta-lens");
    expect(ids).not.toContain("test-exp-lens");
  });

  it("the default (no channel arg) matches the stable channel", () => {
    const ids = listAvailableLenses(arch).map((l) => l.id);
    expect(ids).not.toContain("test-exp-lens");
    expect(ids).not.toContain("test-beta-lens");
  });

  it("beta channel surfaces beta but not experimental", () => {
    const ids = listAvailableLenses(arch, "beta").map((l) => l.id);
    expect(ids).toContain("test-beta-lens");
    expect(ids).not.toContain("test-exp-lens");
  });

  it("experimental channel surfaces both", () => {
    const ids = listAvailableLenses(arch, "experimental").map((l) => l.id);
    expect(ids).toContain("test-beta-lens");
    expect(ids).toContain("test-exp-lens");
  });

  it("resolveLensId gates a non-active lens id back to the default", () => {
    expect(resolveLensId("test-exp-lens", arch, "stable")).toBe(DEFAULT_LENS_ID);
    expect(resolveLensId("test-exp-lens", arch, "experimental")).toBe("test-exp-lens");
  });
});

describe("LensSwitcher labeling and URL-param override", () => {
  beforeEach(() => {
    useArchStore.setState({
      architecture: makeArchitecture(),
      selectedComponentId: null, breadcrumbs: [],
      drillLevel: null, lens: DEFAULT_LENS_ID,
    });
    window.history.pushState({}, "", "/");
  });
  afterEach(() => {
    cleanup();
    window.history.pushState({}, "", "/");
  });

  it("default channel: no experimental lens and no experimental label", () => {
    render(<LensSwitcher />);
    expect(screen.queryByText(/Experimental Test/)).toBeNull();
    expect(screen.queryByText(/\(experimental\)/)).toBeNull();
  });

  it("?channel=experimental: the experimental lens is shown WITH its label", () => {
    window.history.pushState({}, "", "/?channel=experimental");
    render(<LensSwitcher />);
    // The option text includes the explicit "(experimental)" label suffix.
    const option = screen.getByText(/Experimental Test \(experimental\)/);
    expect(option).not.toBeNull();
    expect((option as HTMLOptionElement).value).toBe("test-exp-lens");
  });
});
