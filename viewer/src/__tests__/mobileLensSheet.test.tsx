import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { MobileLensSheet, shouldShowMobileLensSheet } from "../App";
import { useBottomSheet } from "../hooks/useBottomSheet";
import { useArchStore } from "../store";
import type { Architecture, Component } from "../types";

// O10: below the md breakpoint (768px, e.g. 390x844) the desktop-docked lens
// panel is display:none, so before this fix selecting a lens on a phone
// produced no panel at all with no explanation. Two things are tested here,
// against the real production code rather than a re-implementation:
//   1. shouldShowMobileLensSheet, the exact decision App.tsx renders on, at
//      the acceptance viewport and its boundary cases.
//   2. MobileLensSheet actually shows the chosen lens's real panel content
//      (not a placeholder), reusing the same panel components the desktop
//      docked column renders.
// This does not mount <App /> itself: <App /> unconditionally renders the
// ReactFlow graph, which has no jsdom setup anywhere in this suite (no
// ResizeObserver polyfill, etc.) and that gap is out of scope for this fix.
// Testing the exported decision function plus the exported sheet component
// covers the same production code path without fighting that gap.

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
    components: [], relationships: [], symbols: [], files: [],
    stats: { total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {}, total_symbols: 0, total_components: 0, total_relationships: 0 },
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  useArchStore.setState({ architecture: null });
});

describe("shouldShowMobileLensSheet (O10)", () => {
  it("shows at a phone width (390x844, isPanelViewport false) with a non-structure lens and nothing else open", () => {
    expect(shouldShowMobileLensSheet({ isPanelViewport: false, lens: "inventory", activePanel: null })).toBe(true);
  });

  it("stays hidden at a panel-viewport width: the desktop docked column already handles it", () => {
    expect(shouldShowMobileLensSheet({ isPanelViewport: true, lens: "inventory", activePanel: null })).toBe(false);
  });

  it("stays hidden on the default structure lens, which has no ranked panel to show", () => {
    expect(shouldShowMobileLensSheet({ isPanelViewport: false, lens: "structure", activePanel: null })).toBe(false);
  });

  it("yields to the detail sheet once a lens row navigates to a component", () => {
    expect(shouldShowMobileLensSheet({ isPanelViewport: false, lens: "inventory", activePanel: "detail" })).toBe(false);
    expect(shouldShowMobileLensSheet({ isPanelViewport: false, lens: "inventory", activePanel: "review" })).toBe(false);
  });
});

// A small harness: MobileLensSheet takes a real useBottomSheet instance, which
// is a hook and so needs a component to call it from.
function Harness({ lens }: { lens: string }) {
  const bottomSheet = useBottomSheet({ onDismiss: () => {}, initialSnap: "half" });
  return <MobileLensSheet lens={lens} darkMode={false} bottomSheet={bottomSheet} />;
}

describe("MobileLensSheet renders real panel content at the acceptance viewport (O10)", () => {
  it("shows the Inventory lens panel's actual content, external dependencies included", () => {
    const architecture = makeArchitecture({
      components: [
        comp({ id: "usm-core", name: "USM Core", external_services: [{ name: "OpenAI", category: "ai" }] }),
      ],
    });
    useArchStore.setState({ architecture, darkMode: false });

    render(<Harness lens="inventory" />);

    // Real InventoryLensPanel content, not a placeholder or an empty sheet.
    expect(screen.getByText("External dependencies")).toBeTruthy();
    expect(screen.getByText("OpenAI")).toBeTruthy();
  });

  it("shows the Rules lens panel's actual content for a different lens", () => {
    useArchStore.setState({ architecture: makeArchitecture({ components: [] }), darkMode: false });
    render(<Harness lens="rules" />);
    // RulesPanel's own empty-state copy, proving the real panel mounted.
    expect(screen.getByText(/no rules/i)).toBeTruthy();
  });
});
