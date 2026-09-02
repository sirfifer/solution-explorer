/**
 * Is a selected graph node actually readable where it sits?
 *
 * The canvas is not the only thing over the canvas. React Flow's minimap and
 * controls, the tour step panel, the mobile detail sheet and the drill hint are
 * all fixed or absolutely positioned on top of it, so a node can be inside the
 * container rect and still be under something. Testing containment alone let a
 * tour stop (provider-seam step 3) settle under the minimap, where the reader
 * was told to look at a node they could not see.
 *
 * Kept pure and separate from ArchitectureGraph so the geometry is testable
 * without a canvas: rects in, boolean out.
 */

/** A rectangle in client (viewport) coordinates. */
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

function intersects(a: VisibilityRect, b: VisibilityRect): boolean {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

/**
 * Whether nodeRect is wholly inside containerRect and clear of every
 * obstruction. Any overlap at all counts as obstructed: a node half under the
 * minimap reads as truncated, which is the defect.
 *
 * Zero-area obstructions are ignored, so a collapsed or unmounted overlay that
 * still reports a rect does not veto every position on the canvas.
 */
export function isUnobstructed(
  nodeRect: VisibilityRect,
  containerRect: VisibilityRect,
  obstructions: VisibilityRect[],
): boolean {
  const inside =
    nodeRect.left >= containerRect.left &&
    nodeRect.top >= containerRect.top &&
    nodeRect.right <= containerRect.right &&
    nodeRect.bottom <= containerRect.bottom;
  if (!inside) return false;
  for (const o of obstructions) {
    if (o.right <= o.left || o.bottom <= o.top) continue;
    if (intersects(nodeRect, o)) return false;
  }
  return true;
}

/**
 * Read the current on-screen rects of the canvas overlays. Not pure, and not
 * unit-tested; the geometry it feeds is (see isUnobstructed).
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
