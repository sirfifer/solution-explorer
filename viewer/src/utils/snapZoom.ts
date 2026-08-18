import type { Component } from "../types";
import { mostImportant } from "./importance";

// Double-tap snap zoom (owner idea 2026-08-18).
//
// A double tap on empty canvas toggles the view between two states:
//
//   Fit  — the whole level on screen, exactly what fitView already does.
//   Read — zoomed to a size the labels can actually be read at. Not everything
//          fits at that zoom, so the view centers on PRIORITY: the most
//          important component at this level decides what gets framed.
//
// It exists for the phone, where a level whose heroes cannot be aggregated
// (owner decision 2026-08-18) fits only by shrinking every node to ~46x29px.
// Heroes stay unaggregated; this is the "zooming and scrolling has to be easy"
// half of that decision.
//
// The decision itself is pure and lives here so it can be tested without a
// browser; the gesture plumbing lives in ArchitectureGraph.

export type SnapState = "fit" | "read";

// React Flow's zoom limits for this canvas. Shared so the snap math and the
// ReactFlow element cannot disagree about what is reachable.
export const GRAPH_MIN_ZOOM = 0.1;
export const GRAPH_MAX_ZOOM = 2;

// The padding fitView uses, so a computed Fit viewport matches the real one.
export const FIT_PADDING = 0.15;

export const SNAP_DURATION_MS = 300;

// Comfortable reading size for a node (280x140 at zoom 1 gives 238x119 here).
// READABLE_ZOOM (0.6) in store.ts is the floor below which a layout is judged
// unreadable; a deliberate snap should land clear of that floor, not on it.
export const READ_SNAP_ZOOM = 0.85;

// Read must always be a real move in from Fit. Where a level already fits at a
// readable zoom (a large display), snapping "to readable" would otherwise zoom
// OUT or do nothing, and the toggle would read as broken. This makes Read at
// least a quarter step in from wherever Fit landed.
export const MIN_READ_STEP = 1.25;

// The zoom the Read state lands at, given the zoom the level fits at.
export function readZoomForFit(
  fitZoom: number,
  maxZoom: number = GRAPH_MAX_ZOOM,
): number {
  return Math.min(maxZoom, Math.max(READ_SNAP_ZOOM, fitZoom * MIN_READ_STEP));
}

// Which state the next double tap goes to.
//
// Decided from where the view actually is rather than from a remembered state,
// so pinching, panning, or a re-layout in between cannot leave the toggle out
// of sync: zoomed out means "take me in to read", zoomed in means "take me back
// out to the whole level". The split is the geometric mean because zoom is
// multiplicative, so it sits perceptually halfway between the two states.
export function nextSnapState(
  currentZoom: number,
  fitZoom: number,
  readZoom: number,
): SnapState {
  if (!(readZoom > fitZoom)) return "fit";
  return currentZoom >= Math.sqrt(fitZoom * readZoom) ? "fit" : "read";
}

// What the Read state frames: the most important component on the canvas, by
// the same ordering that decided which components are on the canvas at all.
export function pickSnapTarget(
  components: Component[],
  degree: Map<string, number>,
): Component | null {
  return mostImportant(components, degree);
}

// Keeping a clamped node off the very edge of the canvas.
export const SNAP_EDGE_PAD = 24;

export interface SnapRect { x: number; y: number; width: number; height: number }

// One axis of the Read viewport.
//
// The naive answer, "put the priority node dead center", is right on a phone
// and wrong on anything bigger: the most important node is often at the edge of
// an ELK layout, so centering it fills a third of a large display with empty
// canvas while real nodes sit just off screen (measured on the UnaMentis iOS
// level at 2560x1440: 659px of nothing on the left, content continuing past the
// right edge). So center on priority, then slide back inside the content the
// way a map viewer does. The priority node stays fully framed either way; what
// changes is that the rest of the screen shows the level instead of nothing.
function axis(
  targetCenter: number,
  contentStart: number,
  contentSize: number,
  canvasSize: number,
  zoom: number,
  pad: number,
): number {
  const centered = canvasSize / 2 - targetCenter * zoom;
  // Content smaller than the canvas: nothing to slide into, so center the
  // whole level rather than leaving it lopsided.
  if (contentSize * zoom + pad * 2 <= canvasSize) {
    return canvasSize / 2 - (contentStart + contentSize / 2) * zoom;
  }
  const min = canvasSize - pad - (contentStart + contentSize) * zoom;
  const max = pad - contentStart * zoom;
  return Math.min(max, Math.max(min, centered));
}

// The viewport the Read state lands on: the priority node framed at a readable
// zoom, without a screenful of empty canvas beside it.
export function readViewport(
  target: SnapRect,
  content: SnapRect,
  canvas: { width: number; height: number },
  zoom: number,
  pad: number = SNAP_EDGE_PAD,
): { x: number; y: number; zoom: number } {
  return {
    x: axis(target.x + target.width / 2, content.x, content.width, canvas.width, zoom, pad),
    y: axis(target.y + target.height / 2, content.y, content.height, canvas.height, zoom, pad),
    zoom,
  };
}
