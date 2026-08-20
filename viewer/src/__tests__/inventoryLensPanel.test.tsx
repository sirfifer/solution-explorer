import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { InventoryLensPanel } from "../components/InventoryLensPanel";
import { useArchStore } from "../store";
import type { Architecture, Component } from "../types";

// Fix 3 (a reviewer's "the OpenAI entry never opens" complaint, checked and
// found real against the plain non-source InventoryPanel.tsx, which has no
// external-dependency content at all; the actual external-dependency surface
// is this component, InventoryLensPanel, reached via the Inventory lens).
// These tests drive the REAL component and REAL store action so a regression
// that removes the drill-down (rather than just the lens plumbing) is caught.

function comp(overrides: Partial<Component>): Component {
  return {
    id: "c", name: "C", type: "module", path: "src/c", language: null,
    framework: null, description: null, port: null, children: [], files: [],
    entry_points: [], config_files: [],
    metrics: { files: 0, lines: 0, size_bytes: 0, symbols: 0, languages: {} },
    docs: {
      readme: null, claude_md: null, changelog: null, api_docs: null,
      architecture_notes: null, purpose: null, key_decisions: [], patterns: [],
      tech_stack: [], env_vars: [], api_endpoints: [],
    },
    ...overrides,
  } as Component;
}

function makeArchitecture(overrides: Partial<Architecture> = {}): Architecture {
  return {
    name: "Demo", description: "", repository: null,
    generated_at: "2025-01-01T00:00:00Z", analyzer_version: "1.2.0", root_path: "/demo",
    components: [],
    relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  useArchStore.setState({ architecture: null });
});

describe("InventoryLensPanel: external dependency entries are interactive (Fix 3)", () => {
  it("reveals the referencing components when a dependency entry is clicked, and each one navigates to its component", () => {
    const architecture = makeArchitecture({
      components: [
        comp({ id: "usm-core", name: "USM Core", external_services: [{ name: "OpenAI", category: "ai" }] }),
        comp({ id: "usm-web", name: "USM Web", external_services: [{ name: "OpenAI", category: "ai" }] }),
      ],
    });
    const navigateToComponent = vi.fn();
    useArchStore.setState({ architecture, navigateToComponent, darkMode: false });

    render(<InventoryLensPanel />);

    // Before the click: the referencing components are not listed (collapsed).
    expect(screen.queryByText("USM Core")).toBeNull();
    expect(screen.queryByText("USM Web")).toBeNull();

    // The dependency entry itself is a real button, not a dead-looking row.
    const depButton = screen.getByRole("button", { name: /OpenAI/ });
    fireEvent.click(depButton);

    // After the click: both referencing components are listed and are
    // themselves clickable buttons.
    const usmCoreLink = screen.getByRole("button", { name: "USM Core" });
    const usmWebLink = screen.getByRole("button", { name: "USM Web" });
    expect(usmCoreLink).toBeDefined();
    expect(usmWebLink).toBeDefined();

    fireEvent.click(usmCoreLink);
    expect(navigateToComponent).toHaveBeenCalledWith("usm-core");

    // Clicking the dependency entry again collapses it.
    fireEvent.click(depButton);
    expect(screen.queryByText("USM Core")).toBeNull();
  });

  it("says plainly when there are no external dependencies, rather than showing a dead list", () => {
    useArchStore.setState({ architecture: makeArchitecture({ components: [] }), darkMode: false });
    render(<InventoryLensPanel />);
    expect(screen.getByText("No external services detected.")).toBeTruthy();
  });
});
