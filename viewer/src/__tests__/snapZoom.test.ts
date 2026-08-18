import { describe, it, expect } from "vitest";
import {
  nextSnapState,
  pickSnapTarget,
  readViewport,
  readZoomForFit,
  SNAP_EDGE_PAD,
  GRAPH_MAX_ZOOM,
  READ_SNAP_ZOOM,
} from "../utils/snapZoom";
import { buildDegreeIndex, compareByImportance } from "../utils/importance";
import { READABLE_ZOOM } from "../store";
import type { Component, Relationship } from "../types";

// Double-tap snap zoom (owner idea 2026-08-18). The gesture plumbing is not
// unit-testable without a browser; the DECISIONS are, and they are what can be
// wrong: which state the next tap goes to, what zoom Read lands at, and which
// component Read frames.

function comp(over: Partial<Component> & { id: string }): Component {
  return {
    name: over.id, type: "module", path: `src/${over.id}`, language: "swift",
    framework: null, description: null, port: null, children: [], files: ["a.swift"],
    entry_points: [], config_files: [],
    metrics: { files: 1, lines: 10, size_bytes: 10, symbols: 1, languages: {} },
    docs: {
      readme: null, claude_md: null, changelog: null, api_docs: null,
      architecture_notes: null, purpose: null, key_decisions: [], patterns: [],
      tech_stack: [], env_vars: [], api_endpoints: [],
    },
    ...over,
  } as Component;
}

const CRITICAL = { criticality: "critical" as const };
const IMPORTANT = { criticality: "important" as const };
const SUPPORTING = { criticality: "supporting" as const };

function rel(source: string, target: string): Relationship {
  return { source, target, type: "uses" } as Relationship;
}

// The three measured device cases from the comprehension study's aggregation
// work: the zoom each one's iOS-client drill level actually fits at.
const FIT_PHONE = 0.23;
const FIT_LAPTOP = 0.72;
const FIT_LARGE = 1.01;

describe("Read zoom", () => {
  it("lands clear of the readability floor on a phone, where the feature exists", () => {
    const z = readZoomForFit(FIT_PHONE);
    expect(z).toBe(READ_SNAP_ZOOM);
    expect(z).toBeGreaterThan(READABLE_ZOOM);
  });

  it("is always a real move in from fit, including where the level already fits readably", () => {
    for (const fit of [FIT_PHONE, FIT_LAPTOP, FIT_LARGE, 1.5]) {
      const z = readZoomForFit(fit);
      // Otherwise a double tap on a large display would zoom OUT, or do
      // nothing at all, and the toggle would read as broken.
      expect(z).toBeGreaterThan(fit);
    }
  });

  it("never asks for more zoom than the canvas allows", () => {
    expect(readZoomForFit(1.9)).toBeLessThanOrEqual(GRAPH_MAX_ZOOM);
    expect(readZoomForFit(GRAPH_MAX_ZOOM)).toBe(GRAPH_MAX_ZOOM);
  });
});

describe("Which state the next tap goes to", () => {
  it("toggles: fit, read, fit", () => {
    const fit = FIT_PHONE;
    const read = readZoomForFit(fit);
    expect(nextSnapState(fit, fit, read)).toBe("read");
    expect(nextSnapState(read, fit, read)).toBe("fit");
    expect(nextSnapState(fit, fit, read)).toBe("read");
  });

  it("decides from where the view IS, so a pinch in between cannot desync it", () => {
    const fit = FIT_PHONE;
    const read = readZoomForFit(fit);
    // Pinched in past the read state: the useful next move is back out.
    expect(nextSnapState(1.8, fit, read)).toBe("fit");
    // Pinched to somewhere still too small to read: take me in.
    expect(nextSnapState(0.3, fit, read)).toBe("read");
  });

  it("splits the two states perceptually, not arithmetically", () => {
    const fit = 0.2;
    const read = 0.8;
    // Geometric mean is 0.4; an arithmetic split would put the boundary at 0.5
    // and call 0.45 "already read", which it plainly is not.
    expect(nextSnapState(0.39, fit, read)).toBe("read");
    expect(nextSnapState(0.41, fit, read)).toBe("fit");
  });

  it("degenerates to fit rather than looping if read is not reachable", () => {
    expect(nextSnapState(1, 1, 1)).toBe("fit");
  });
});

describe("What the Read state frames", () => {
  // The UnaMentis iOS-client shape: hero screens the aggregation rules always
  // show, plus critical modules.
  const nodes: Component[] = [
    comp({ id: "tab-bar", type: "tab-container", ai_enhance: CRITICAL }),
    comp({ id: "launch-screen", type: "screen" }),
    comp({ id: "detail-screen", type: "screen", ai_enhance: SUPPORTING }),
    comp({ id: "practice-screen", type: "screen", ai_enhance: IMPORTANT }),
    comp({ id: "stt", ai_enhance: CRITICAL, files: ["a", "b", "c"] }),
  ];
  const relationships = [
    rel("tab-bar", "practice-screen"),
    rel("tab-bar", "detail-screen"),
    rel("tab-bar", "stt"),
  ];

  it("frames the most important component, not the first or the biggest", () => {
    const degree = buildDegreeIndex(relationships);
    // stt is critical too, and has more files; tab-bar wins on connections.
    expect(pickSnapTarget(nodes, degree)?.id).toBe("tab-bar");
  });

  it("falls back to connections, then files, then name", () => {
    const bare = buildDegreeIndex([]);
    // No connections anywhere: the critical pair separates on file count.
    expect(pickSnapTarget(nodes, bare)?.id).toBe("stt");
    const tied = [comp({ id: "beta", ai_enhance: CRITICAL }), comp({ id: "alpha", ai_enhance: CRITICAL })];
    expect(pickSnapTarget(tied, bare)?.id).toBe("alpha");
  });

  it("prefers an untagged component to an explicitly supporting one", () => {
    const degree = buildDegreeIndex([]);
    const pick = pickSnapTarget(
      [comp({ id: "supporting", ai_enhance: SUPPORTING }), comp({ id: "untagged" })],
      degree,
    );
    expect(pick?.id).toBe("untagged");
  });

  it("has nothing to frame on an empty level", () => {
    expect(pickSnapTarget([], new Map())).toBeNull();
  });

  it("uses the same ordering the canvas uses to decide what is visible at all", () => {
    // The guard against the two drifting apart: if the store's visibility
    // ranking and the snap target ever used different comparators, the snap
    // could center on something the canvas does not even show.
    const degree = buildDegreeIndex(relationships);
    const ranked = [...nodes].sort((a, b) => compareByImportance(a, b, degree));
    expect(pickSnapTarget(nodes, degree)?.id).toBe(ranked[0].id);
  });
});

describe("Where the Read state lands", () => {
  const canvas = { width: 1184, height: 768 };
  // A level much wider and taller than the canvas at read zoom, with the
  // priority node at its top-left corner: the ELK shape that exposed this.
  const content = { x: 0, y: 0, width: 3000, height: 2000 };
  const corner = { x: 0, y: 0, width: 280, height: 140 };
  const zoom = 0.85;

  it("frames the priority node without a screenful of empty canvas beside it", () => {
    const vp = readViewport(corner, content, canvas, zoom);
    // Nothing to the left of or above the level is on screen...
    expect(vp.x).toBeLessThanOrEqual(SNAP_EDGE_PAD);
    expect(vp.y).toBeLessThanOrEqual(SNAP_EDGE_PAD);
    // ...and the priority node is still fully visible.
    expect(corner.x * zoom + vp.x).toBeGreaterThanOrEqual(0);
    expect((corner.x + corner.width) * zoom + vp.x).toBeLessThanOrEqual(canvas.width);
    expect((corner.y + corner.height) * zoom + vp.y).toBeLessThanOrEqual(canvas.height);
  });

  it("centers the priority node when it is nowhere near an edge", () => {
    const middle = { x: 1400, y: 900, width: 280, height: 140 };
    const vp = readViewport(middle, content, canvas, zoom);
    const cx = (middle.x + middle.width / 2) * zoom + vp.x;
    const cy = (middle.y + middle.height / 2) * zoom + vp.y;
    expect(cx).toBeCloseTo(canvas.width / 2, 6);
    expect(cy).toBeCloseTo(canvas.height / 2, 6);
  });

  it("never shows canvas past the far edge of the level either", () => {
    const far = { x: 2720, y: 1860, width: 280, height: 140 };
    const vp = readViewport(far, content, canvas, zoom);
    expect((content.x + content.width) * zoom + vp.x).toBeGreaterThanOrEqual(canvas.width - SNAP_EDGE_PAD);
    expect((content.y + content.height) * zoom + vp.y).toBeGreaterThanOrEqual(canvas.height - SNAP_EDGE_PAD);
  });

  it("centers the whole level on an axis where it already fits", () => {
    // Tall and narrow: the width fits at read zoom, the height does not.
    const narrow = { x: 0, y: 0, width: 400, height: 2000 };
    const node = { x: 0, y: 1000, width: 280, height: 140 };
    const vp = readViewport(node, narrow, canvas, zoom);
    const contentCenterX = (narrow.x + narrow.width / 2) * zoom + vp.x;
    expect(contentCenterX).toBeCloseTo(canvas.width / 2, 6);
    // The axis that does not fit still frames the priority node.
    expect((node.y + node.height / 2) * zoom + vp.y).toBeCloseTo(canvas.height / 2, 6);
  });
});
