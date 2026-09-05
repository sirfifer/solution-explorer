/** Keep a readable surface inside its boundary, using the room beside its anchor. */
export function readingSurfacePlacement(
  anchor: { left: number; right: number; top: number; bottom: number },
  boundary: { left: number; right: number; top: number; bottom: number },
  size: { width: number; height: number },
  preferred: "top" | "bottom" = "top",
) {
  const pad = 8;
  const width = Math.min(size.width, Math.max(0, boundary.right - boundary.left - pad * 2));
  const above = Math.max(0, Math.min(anchor.top, boundary.bottom) - boundary.top - pad * 2);
  const below = Math.max(0, boundary.bottom - Math.max(anchor.bottom, boundary.top) - pad * 2);
  const side = preferred === "top"
    ? (above >= size.height || above >= below ? "top" : "bottom")
    : (below >= size.height || below >= above ? "bottom" : "top");
  const maxHeight = Math.min(size.height, side === "top" ? above : below);
  const left = Math.max(boundary.left + pad, Math.min(
    (anchor.left + anchor.right - width) / 2, boundary.right - width - pad,
  ));
  const top = Math.max(boundary.top + pad, Math.min(
    side === "top" ? anchor.top - pad - maxHeight : anchor.bottom + pad,
    boundary.bottom - maxHeight - pad,
  ));
  return { left, top, width, maxHeight, side };
}

/**
 * Is a graph node other than `ownerId` beneath this point?
 *
 * A reading surface floats over the canvas, so it routinely comes to rest on
 * top of nodes that are not its own. Those nodes stay clickable only because
 * the surface gets out of the way when the reader points at one: an
 * interactive surface that stayed put would swallow the click and leave the
 * node unreachable without panning the graph first. That is exactly what
 * happened to the drill gesture at depth 5 of the VS Code demo, where the
 * preview of one sibling covered the next one whole.
 *
 * The stack is read rather than the topmost element, because the surface
 * itself is always on top. The first graph node found under it decides: its
 * own node means the reader is still on the trigger, any other node means the
 * reader has moved on.
 */
/** Is this point within the element's box? Used while the box ignores the pointer. */
export function pointInside(element: Element, x: number, y: number): boolean {
  const rect = element.getBoundingClientRect();
  return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
}

export function foreignNodeUnderPoint(x: number, y: number, ownerId: string): boolean {
  if (typeof document === "undefined" || typeof document.elementsFromPoint !== "function") {
    return false;
  }
  for (const element of document.elementsFromPoint(x, y)) {
    const node = element.closest?.('[data-testid="graph-node"]');
    if (node) return node.getAttribute("data-component-id") !== ownerId;
  }
  return false;
}
