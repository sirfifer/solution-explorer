/**
 * Is a selected graph node actually readable where it sits?
 *
 * The canvas is not the only thing over the canvas. React Flow's minimap and
 * controls, the tour step panel, the mobile detail sheet and the drill hint are
 * all Panels or fixed app chrome painted on top of it, so a node can be inside
 * the container rect and still be under something. Testing containment alone
 * let a tour stop (provider-seam step 3) settle under the minimap, where the
 * reader was told to look at a node they could not see.
 *
 * Nothing here reimplements the viewport transform or the overlap test. The
 * transform is React Flow's `screenToFlowPosition`, the overlap test is React
 * Flow's `isNodeIntersecting`, and both are passed in so the decision can be
 * unit tested without a canvas. What is left by hand is the one thing the
 * engine has no primitive for: reading where the overlays currently sit, which
 * is a `getBoundingClientRect` per overlay and nothing else.
 */

import type { Rect } from "@xyflow/react";

/** A rectangle in client (viewport) coordinates, as getBoundingClientRect gives it. */
export interface VisibilityRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/**
 * CSS selectors for the overlays that sit over the graph canvas. Each is
 * matched against the whole document, because only the first two are children
 * of the React Flow container.
 */
export const CANVAS_OBSTRUCTION_SELECTORS = [
  ".react-flow__minimap",
  ".react-flow__controls",
  '[data-testid="tour-step-panel"]',
  '[data-testid="drill-hint"]',
  '[data-se="mobile-detail-sheet"]',
  '[data-se="mobile-lens-sheet"]',
] as const;

/** React Flow's screenToFlowPosition, narrowed to what this module needs. */
export type ScreenToFlowPosition = (
  clientPosition: { x: number; y: number },
  options?: { snapToGrid: boolean },
) => { x: number; y: number };

/** React Flow's isNodeIntersecting, narrowed to the rect-versus-rect form. */
export type IsNodeIntersecting = (
  node: { id: string } | Rect,
  area: Rect,
  partially?: boolean,
) => boolean;

/**
 * A client-space rectangle expressed in flow coordinates, so it can be compared
 * with a node by the engine's own intersection test.
 *
 * The corners go through screenToFlowPosition rather than through arithmetic on
 * `viewport.x/y/zoom`, which is the whole point: there is exactly one viewport
 * transform in this app and React Flow owns it. Snapping is turned off here
 * because these are measurements, not drop targets.
 */
export function toFlowRect(
  rect: VisibilityRect,
  screenToFlowPosition: ScreenToFlowPosition,
): Rect {
  const topLeft = screenToFlowPosition({ x: rect.left, y: rect.top }, { snapToGrid: false });
  const bottomRight = screenToFlowPosition({ x: rect.right, y: rect.bottom }, { snapToGrid: false });
  return {
    x: topLeft.x,
    y: topLeft.y,
    width: Math.max(0, bottomRight.x - topLeft.x),
    height: Math.max(0, bottomRight.y - topLeft.y),
  };
}

/**
 * Read the current on-screen rects of the canvas overlays. Not pure, and not
 * unit-tested; the decision it feeds is (see isSelectionUnobstructed).
 *
 * Zero-area overlays are dropped here, so a collapsed or unmounted panel that
 * still reports a rect cannot veto every position on the canvas.
 */
export function collectCanvasObstructions(): VisibilityRect[] {
  if (typeof document === "undefined") return [];
  const rects: VisibilityRect[] = [];
  for (const selector of CANVAS_OBSTRUCTION_SELECTORS) {
    for (const el of Array.from(document.querySelectorAll(selector))) {
      const r = el.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) continue;
      rects.push({ left: r.left, top: r.top, right: r.right, bottom: r.bottom });
    }
  }
  return rects;
}

/**
 * Whether the node is wholly inside the canvas and clear of every overlay.
 *
 * Both questions are asked of React Flow. Containment is
 * `isNodeIntersecting(node, pane, false)`, which is true only when one rect
 * swallows the other. Obstruction is `isNodeIntersecting(node, overlay, true)`,
 * which is true on any overlap at all: a node half under the minimap reads as
 * truncated, which is the defect.
 */
export function isSelectionUnobstructed({
  node,
  paneRect,
  obstructions,
  screenToFlowPosition,
  isNodeIntersecting,
}: {
  node: { id: string } | Rect;
  paneRect: VisibilityRect;
  obstructions: VisibilityRect[];
  screenToFlowPosition: ScreenToFlowPosition;
  isNodeIntersecting: IsNodeIntersecting;
}): boolean {
  if (!isNodeIntersecting(node, toFlowRect(paneRect, screenToFlowPosition), false)) {
    return false;
  }
  for (const overlay of obstructions) {
    const area = toFlowRect(overlay, screenToFlowPosition);
    if (area.width <= 0 || area.height <= 0) continue;
    if (isNodeIntersecting(node, area, true)) return false;
  }
  return true;
}
