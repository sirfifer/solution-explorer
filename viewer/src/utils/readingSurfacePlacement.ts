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
