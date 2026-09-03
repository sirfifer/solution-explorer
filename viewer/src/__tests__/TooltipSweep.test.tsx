import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, fireEvent, cleanup, within, act } from "@testing-library/react";
import { Tooltip } from "../components/Tooltip";
import { previewPlacement } from "../components/ComponentNode";
import { LensSwitcher } from "../components/LensSwitcher";
import { CoverageBadge } from "../components/CoverageBadge";
import { FindingsEntry } from "../components/FindingsEntry";
import { ToursEntry } from "../components/ToursEntry";
import { FindingsSurface } from "../components/FindingsSurface";
import { TOOLTIP_COPY, SWEPT_SURFACES, dispositionTooltip } from "../utils/tooltipCopy";
import { useArchStore } from "../store";
import type { Architecture, Finding, Concern, Tour } from "../types";
import "../lenses";

// The tooltip sweep (program2/p6). Two guarantees:
//   1. every swept surface has non-empty tooltip copy, and none of it uses the
//      em or en dash forbidden by the writing-style rule;
//   2. the named surfaces render their tooltip trigger wired to the shared
//      Tooltip system (asserted through the accessible label the trigger exposes),
//      and the trigger works for keyboard focus, not only mouse hover.

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
    lens: "structure",
  });
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  useArchStore.setState({
    architecture: null,
    findingsSurface: { open: false, tab: "findings", kindFilter: null, elementFilter: null },
  });
});

// Every leaf string in a nested copy object.
function leaves(obj: unknown): string[] {
  if (typeof obj === "string") return [obj];
  if (obj && typeof obj === "object") return Object.values(obj).flatMap(leaves);
  return [];
}

describe("tooltip copy quality", () => {
  it("every tooltip string is non-empty and free of em/en dashes", () => {
    const all = leaves(TOOLTIP_COPY);
    expect(all.length).toBeGreaterThan(30);
    for (const s of all) {
      expect(s.trim().length).toBeGreaterThan(0);
      // Writing-style rule: no em dash (U+2014) or en dash (U+2013).
      expect(s).not.toContain("—");
      expect(s).not.toContain("–");
    }
  });

  // The coverage assertion enumerating the swept surfaces: each named surface
  // resolves to at least one non-empty copy string.
  it("every swept surface resolves to non-empty copy", () => {
    const resolve: Record<(typeof SWEPT_SURFACES)[number], string[]> = {
      "lens.switcher": [TOOLTIP_COPY.lens.switcher],
      "coverage.percent": [TOOLTIP_COPY.coverage.percent],
      "coverage.families": [
        TOOLTIP_COPY.coverage.familyAnalyzed,
        TOOLTIP_COPY.coverage.familyGaps,
        TOOLTIP_COPY.coverage.familyNonSource,
      ],
      "coverage.dispositions": leaves(TOOLTIP_COPY.coverage.disposition),
      "inventory.explore": [TOOLTIP_COPY.inventory.explore],
      "inventory.group": [TOOLTIP_COPY.inventory.group],
      "inventory.recommendation": [TOOLTIP_COPY.inventory.recommendation],
      "inventory.securitySensitive": [TOOLTIP_COPY.inventory.securitySensitive],
      "findings.entry": [TOOLTIP_COPY.findings.entry],
      "findings.kind": leaves(TOOLTIP_COPY.findings.kind),
      "findings.verification": leaves(TOOLTIP_COPY.findings.verification),
      "findings.confidence": [TOOLTIP_COPY.findings.confidence],
      "concern.row": [TOOLTIP_COPY.concern.row],
      "concern.basis": [TOOLTIP_COPY.concern.basis],
      "activity.hotspotScore": [TOOLTIP_COPY.activity.hotspotScore],
      "activity.busFactor": [TOOLTIP_COPY.activity.busFactor],
      "activity.knowledgeIsland": [TOOLTIP_COPY.activity.knowledgeIsland],
      "activity.couplingCount": [TOOLTIP_COPY.activity.couplingCount],
      "rules.kind": [TOOLTIP_COPY.rules.kind],
      "rules.inferred": [TOOLTIP_COPY.rules.inferred],
      "capability.kind": [TOOLTIP_COPY.capability.kind],
      "capability.tested": [TOOLTIP_COPY.capability.tested],
      "supplyChain.entry": [TOOLTIP_COPY.supplyChain.entry],
      "supplyChain.scopeNote": [TOOLTIP_COPY.supplyChain.scopeNote],
      "supplyChain.pinStatus": [
        TOOLTIP_COPY.supplyChain.pinExact,
        TOOLTIP_COPY.supplyChain.pinRange,
        TOOLTIP_COPY.supplyChain.pinUnpinned,
      ],
      "supplyChain.scope": [
        TOOLTIP_COPY.supplyChain.direct,
        TOOLTIP_COPY.supplyChain.transitive,
      ],
      "evidence.link": [TOOLTIP_COPY.evidence.link],
      "inventoryLens.externalDependencies": [TOOLTIP_COPY.inventoryLens.externalDependencies],
      "tours.stale": [TOOLTIP_COPY.tours.stale],
      "orientation.controls": leaves(TOOLTIP_COPY.orientation),
      "directive.export": [TOOLTIP_COPY.directive.export],
      "directive.exemption": [TOOLTIP_COPY.directive.exemption],
      "rationale.fields": leaves(TOOLTIP_COPY.rationale),
    };
    for (const surface of SWEPT_SURFACES) {
      const copies = resolve[surface];
      expect(copies.length, `surface ${surface} has copy`).toBeGreaterThan(0);
      for (const c of copies) expect(c.trim().length).toBeGreaterThan(0);
    }
  });
});

describe("Tooltip keyboard focus accessibility", () => {
  it("shows on keyboard focus, not only mouse hover, and exposes an accessible label", () => {
    vi.useFakeTimers();
    render(
      <Tooltip content="Focus reveals me." focusable>
        <span>trigger</span>
      </Tooltip>,
    );
    // Accessible label is present without any interaction (assistive tech path).
    const trigger = screen.getByLabelText("Focus reveals me.");
    expect(trigger).toBeDefined();
    // Keyboard focus surfaces the tooltip content after the show delay.
    fireEvent.focus(trigger);
    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(screen.getAllByText("Focus reveals me.").length).toBeGreaterThan(0);
  });
});

describe("swept surfaces render their tooltip triggers", () => {
  it("lens switcher option control carries its tooltip", () => {
    setArch(makeArchitecture());
    render(<LensSwitcher />);
    // The active lens's description is the tooltip; the switcher exposes the
    // switcher-level accessible label.
    expect(screen.getByLabelText(TOOLTIP_COPY.lens.switcher)).toBeDefined();
  });

  it("coverage badge headline and family labels carry tooltips", () => {
    setArch(
      makeArchitecture({
        coverage: {
          summary: { parsed: 641, binary: 6006, "excluded:skipped_directory": 41 },
          total: 6688,
          parsed: 641,
        },
      }),
    );
    render(<CoverageBadge />);
    expect(screen.getByLabelText(TOOLTIP_COPY.coverage.percent)).toBeDefined();
    expect(screen.getByLabelText(TOOLTIP_COPY.coverage.nonSourceCount)).toBeDefined();
    // Open the drill-in: the three family sections each label themselves.
    fireEvent.click(screen.getByTestId("coverage-badge"));
    expect(screen.getAllByLabelText(TOOLTIP_COPY.coverage.familyAnalyzed).length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText(TOOLTIP_COPY.coverage.familyGaps).length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText(TOOLTIP_COPY.coverage.familyNonSource).length).toBeGreaterThan(0);
  });

  it("findings entry bar carries its tooltip", () => {
    const finding: Finding = {
      id: "f1",
      kind: "duplication",
      summary: "Two near-identical helpers.",
      members: [{ id: "m1", kind: "fragment", file: "a.ts", line_start: 3 }],
      evidence: [],
      confidence: "inferred",
      verification_status: "unverified",
      rank_score: 42,
    };
    setArch(makeArchitecture({ findings: [finding] }));
    render(<FindingsEntry />);
    expect(screen.getByLabelText(TOOLTIP_COPY.findings.entry)).toBeDefined();
  });

  it("findings surface renders kind, verification, and confidence tooltips", () => {
    const finding: Finding = {
      id: "f1",
      kind: "duplication",
      summary: "Two near-identical helpers.",
      members: [{ id: "m1", kind: "fragment", file: "a.ts", line_start: 3 }],
      evidence: [],
      confidence: "inferred",
      verification_status: "unverified",
      rank_score: 42,
    };
    setArch(makeArchitecture({ findings: [finding] }));
    useArchStore.setState({
      findingsSurface: { open: true, tab: "findings", kindFilter: null, elementFilter: null },
    });
    render(<FindingsSurface />);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText(TOOLTIP_COPY.findings.kind.duplication)).toBeDefined();
    expect(within(dialog).getByLabelText(TOOLTIP_COPY.findings.verification.unverified)).toBeDefined();
    expect(within(dialog).getByLabelText(TOOLTIP_COPY.findings.confidence)).toBeDefined();
  });

  it("findings surface renders concern row and basis tooltips", () => {
    const concern: Concern = {
      id: "logging",
      kind: "concern",
      title: "Logging",
      basis: "imports of the logger in 4 components",
      members: [{ component_id: "c1", evidence: [], files: [], markers: [] }],
    };
    setArch(makeArchitecture({ concerns: [concern] }));
    useArchStore.setState({
      findingsSurface: { open: true, tab: "concerns", kindFilter: null, elementFilter: null },
    });
    render(<FindingsSurface />);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByLabelText(TOOLTIP_COPY.concern.row)).toBeDefined();
    expect(within(dialog).getByLabelText(TOOLTIP_COPY.concern.basis)).toBeDefined();
  });

  it("tours entry stale marker carries its tooltip", () => {
    const staleTour: Tour = {
      id: "t1",
      title: "The request path",
      description: "From route to response.",
      steps: [],
      provenance: { stale: true } as Tour["provenance"],
    };
    setArch(makeArchitecture({ tours: [staleTour] }));
    render(<ToursEntry />);
    expect(screen.getByLabelText(TOOLTIP_COPY.tours.entry)).toBeDefined();
    // The stale marker only appears when a tour is stale.
    expect(screen.getByLabelText(TOOLTIP_COPY.tours.stale)).toBeDefined();
  });
});

describe("dispositionTooltip fallback semantics", () => {
  it("returns the exact copy for known dispositions", () => {
    expect(dispositionTooltip("parsed")).toBe(TOOLTIP_COPY.coverage.disposition.parsed);
    expect(dispositionTooltip("binary")).toBe(TOOLTIP_COPY.coverage.disposition.binary);
  });

  it("maps failed:* onto the failed copy", () => {
    expect(dispositionTooltip("failed:SyntaxError")).toBe(TOOLTIP_COPY.coverage.disposition.failed);
  });

  it("never borrows the parsed copy for an unknown disposition (gap semantics)", () => {
    // classifyDisposition counts every unrecognized disposition as a gap, so
    // the tooltip must say gap, not "Parsed successfully". Fail-before: the
    // pre-fix fallback returned the parsed copy for e.g. "timeout".
    expect(dispositionTooltip("timeout")).toBe(TOOLTIP_COPY.coverage.disposition.unknownExcluded);
    expect(dispositionTooltip("excluded:gitignore")).toBe(
      TOOLTIP_COPY.coverage.disposition.unknownExcluded,
    );
    expect(dispositionTooltip("timeout")).not.toBe(TOOLTIP_COPY.coverage.disposition.parsed);
  });
});

// The graph node's hover preview is the third popup on this surface, and it was
// the only one drawn in a portal at fixed coordinates, so nothing about the
// layout stopped it from covering the header. On a projection with one root the
// node sits centred near the top of the canvas and the popup took the lens
// switcher, the level toggle, Review and part of Search with it (GUI crawl
// 2026-09-01, graph.preview_covers_header).
//
// React Flow's NodeToolbar carries the card now, so the anchor, the offset and
// the "does not scale with zoom" are the engine's. NodeToolbar has no notion of
// the canvas edges, so the flip and the sideways clamp stay here. Both are
// pure, so they are checked here rather than through a browser.
describe("node hover preview placement", () => {
  const canvas = { left: 0, right: 1000, top: 100 };
  const card = { width: 360, height: 200 };

  it("stays above the node when there is room above it", () => {
    const node = { left: 480, right: 620, top: 500, bottom: 560 };
    const { flipBelow, shiftX } = previewPlacement(node, canvas, card);
    expect(flipBelow).toBe(false);
    // Centred on the node is where NodeToolbar puts it, so nothing to correct.
    expect(shiftX).toBe(0);
  });

  it("flips below the node rather than over the header", () => {
    // A node 40px below the canvas top has no room for a 200px card above it.
    const node = { left: 480, right: 620, top: 140, bottom: 200 };
    expect(previewPlacement(node, canvas, card).flipBelow).toBe(true);
  });

  it("shifts inside the canvas rather than off either edge", () => {
    // Centred on a node at the left edge the card would start at -150.
    const nearLeft = { left: 0, right: 60, top: 500, bottom: 560 };
    expect(previewPlacement(nearLeft, canvas, card).shiftX).toBe(8 - -150);

    const nearRight = { left: 960, right: 1000, top: 500, bottom: 560 };
    expect(previewPlacement(nearRight, canvas, card).shiftX).toBe(1000 - 360 - 8 - 800);
  });

  it("pins the card's start on screen when the canvas is narrower than it is", () => {
    const phone = { left: 0, right: 360, top: 100 };
    const node = { left: 100, right: 290, top: 500, bottom: 560 };
    const { shiftX } = previewPlacement(node, phone, card);
    // Centred would start at 15; the only satisfiable edge is the left one.
    expect(shiftX).toBe(8 - 15);
  });

  it("leaves NodeToolbar's own placement alone when there is no canvas to clamp against", () => {
    const node = { left: 480, right: 620, top: 40, bottom: 100 };
    expect(previewPlacement(node, null, card)).toEqual({ flipBelow: false, shiftX: 0 });
  });
});
