import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { initialMobileLensSnap, mobileGraphReserve, MobileLensSheet, shouldShowMobileDetailSheet, shouldShowMobileLensSheet } from "../App";
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

// The detail sheet used to mount on activePanel alone, so a panel left open
// with nothing selected put an empty peek-height slab on the phone and took the
// same 15vh off the canvas through mobileGraphBottomReserve (GUI crawl
// 2026-09-01, mobile chrome). Tested here for the same reason its lens sibling
// is: this is the exact decision App.tsx renders on.
describe("shouldShowMobileDetailSheet", () => {
  it("shows a selected component's detail on a phone", () => {
    expect(shouldShowMobileDetailSheet({ isDesktopViewport: false, activePanel: "detail", hasDetail: true })).toBe(true);
  });

  it("shows nothing when the detail panel is open with nothing selected", () => {
    expect(shouldShowMobileDetailSheet({ isDesktopViewport: false, activePanel: "detail", hasDetail: false })).toBe(false);
  });

  it("still shows the review summary, which is content of its own", () => {
    expect(shouldShowMobileDetailSheet({ isDesktopViewport: false, activePanel: "review", hasDetail: false })).toBe(true);
  });

  it("shows nothing with no panel open at all", () => {
    expect(shouldShowMobileDetailSheet({ isDesktopViewport: false, activePanel: null, hasDetail: true })).toBe(false);
  });

  it("stays hidden on a desktop viewport, where the docked aside owns the detail", () => {
    expect(shouldShowMobileDetailSheet({ isDesktopViewport: true, activePanel: "detail", hasDetail: true })).toBe(false);
  });
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

  it("opens the content-heavy Support report at the full phone snap", () => {
    expect(initialMobileLensSnap("support")).toBe("full");
    expect(initialMobileLensSnap("inventory")).toBe("half");
  });
});

// A small harness: MobileLensSheet takes a real useBottomSheet instance, which
// is a hook and so needs a component to call it from.
function Harness({ lens }: { lens: string }) {
  const bottomSheet = useBottomSheet({ onDismiss: () => {}, initialSnap: initialMobileLensSnap(lens) });
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

  it("gives Support a full-height sheet and puts external reliance first", () => {
    useArchStore.setState({
      architecture: makeArchitecture({
        support: {
          schema: "syscorpus.support/v1",
          method_caveat: "Observed evidence only.",
          configuration: [],
          external_dependencies: [{ name: "Provider", category: "ai", component_id: "c", component_name: "C", evidence: {} }],
          entry_points: [],
          data_handled: [],
          attention: [{ component_id: "c", component_name: "C", attention_score: 2, reasons: ["external reliance"] }],
          counts: { configuration: 0, external_dependencies: 1, entry_points: 0, data_entities: 0, attention_components: 1 },
        },
      }),
      darkMode: false,
    });

    render(<Harness lens="support" />);

    const sheet = document.querySelector('[data-se="mobile-lens-sheet"]') as HTMLElement;
    expect(sheet.style.height).toContain("90vh");
    const headings = screen.getAllByRole("heading", { level: 3 });
    expect(headings.map((heading) => heading.textContent)).toEqual([
      "External reliance (1)",
      "Ranked attention",
    ]);
  });
});

// The peek snap of the detail sheet must not change the canvas height (GUI
// crawl 2026-09-01, journey.drill_hop). The first tap on a node selects it,
// which mounts the detail sheet; if that mount reserves canvas space the layout
// slides the just-tapped node out from under the reader's finger and the second
// tap of a double-tap misses the drill detector's 5 px slop. Measured here
// rather than only in the crawl, because the reserve is a pure function of the
// sheet's state.
//
// Resolves the reserve's calc() string at a real phone viewport: App writes
// `calc(<vh>vh - <px>px)`, which jsdom does not compute.
function reservePx(reserve: string, viewportHeightPx: number): number {
  if (reserve === "0px") return 0;
  const parsed = /^calc\(([\d.]+)vh - ([\d.]+)px\)$/.exec(reserve);
  if (!parsed) throw new Error(`unrecognised reserve: ${reserve}`);
  return (Number(parsed[1]) / 100) * viewportHeightPx - Number(parsed[2]);
}

describe("mobileGraphReserve at 390x664", () => {
  const VIEWPORT_H = 664;
  // The content area the crawl measures at this viewport with nothing selected,
  // 414 px of 664 (62 percent), reclaimed by the empty-sheet fix.
  const CONTENT_AREA_PX = 414;

  it("reserves nothing with no sheet mounted, keeping the reclaimed content area", () => {
    expect(reservePx(mobileGraphReserve(null), VIEWPORT_H)).toBe(0);
    expect(CONTENT_AREA_PX / VIEWPORT_H).toBeGreaterThan(0.6);
  });

  it("leaves the canvas height identical before and after the first tap", () => {
    const beforeTap = CONTENT_AREA_PX - reservePx(mobileGraphReserve(null), VIEWPORT_H);
    const afterTap = CONTENT_AREA_PX - reservePx(
      mobileGraphReserve({ kind: "detail", snap: "peek", sheetHeight: 15 }),
      VIEWPORT_H,
    );
    expect(afterTap).toBe(beforeTap);
    expect(afterTap).toBe(414);
  });

  it("still reserves once the reader opens the sheet to half or full", () => {
    expect(reservePx(mobileGraphReserve({ kind: "detail", snap: "half", sheetHeight: 45 }), VIEWPORT_H))
      .toBeGreaterThan(0);
    expect(reservePx(mobileGraphReserve({ kind: "detail", snap: "full", sheetHeight: 90 }), VIEWPORT_H))
      .toBeGreaterThan(0);
  });

  it("still reserves for the lens sheet, which never opens at peek", () => {
    expect(reservePx(mobileGraphReserve({ kind: "lens", snap: "half", sheetHeight: 45 }), VIEWPORT_H))
      .toBeGreaterThan(0);
  });
});
