import type { CardPlacement, WalkStop } from "./stops";

export const ORIENTATION_STORAGE_KEY = "arch-viz-orientation-v1";
export const LEGACY_HELP_STORAGE_KEY = "arch-viz-help-dismissed";

export type OrientationEntry = "start" | "invite" | "none";

export interface Rect {
  top: number;
  right: number;
  bottom: number;
  left: number;
  width: number;
  height: number;
}

export interface Size {
  width: number;
  height: number;
}

export interface CardPosition {
  top: number;
  left: number;
  placement: Exclude<CardPlacement, "auto">;
}

export function firstVisitDecision(
  search: string,
  stored: string | null,
  legacyStored: string | null,
): OrientationEntry {
  const request = new URLSearchParams(search).get("orientation");
  if (request === "start") return "start";
  if (request === "invite") return "invite";
  if (stored !== null || legacyStored !== null) return "none";
  return "invite";
}

export function readFirstVisitDecision(): OrientationEntry {
  const search = typeof window === "undefined" ? "" : window.location.search;
  try {
    return firstVisitDecision(
      search,
      localStorage.getItem(ORIENTATION_STORAGE_KEY),
      localStorage.getItem(LEGACY_HELP_STORAGE_KEY),
    );
  } catch {
    return firstVisitDecision(search, null, null);
  }
}

export function persistOrientation(value: "done" | "dismissed"): void {
  try {
    localStorage.setItem(ORIENTATION_STORAGE_KEY, value);
  } catch {
    // Browser storage is optional. Component state still hides the invite.
  }
}

export function applicableStops(stops: readonly WalkStop[], viewportWidth: number): WalkStop[] {
  const mobile = viewportWidth < 640;
  return stops.filter((stop) => {
    if (stop.viewport === "mobile" && !mobile) return false;
    if (stop.viewport === "desktop" && mobile) return false;
    if (stop.minWidth !== undefined && viewportWidth < stop.minWidth) return false;
    return true;
  });
}

function rect(top: number, left: number, width: number, height: number): Rect {
  return { top, left, width, height, right: left + width, bottom: top + height };
}

function intersect(a: Rect, b: Rect): Rect | null {
  const left = Math.max(a.left, b.left);
  const top = Math.max(a.top, b.top);
  const right = Math.min(a.right, b.right);
  const bottom = Math.min(a.bottom, b.bottom);
  if (right <= left || bottom <= top) return null;
  return rect(top, left, right - left, bottom - top);
}

export function highlightRect(
  anchor: Rect,
  viewport: Size,
  card: Rect | null = null,
  padding = 6,
): Rect {
  const expanded = rect(
    anchor.top - padding,
    anchor.left - padding,
    anchor.width + padding * 2,
    anchor.height + padding * 2,
  );
  const clipped = intersect(expanded, rect(0, 0, viewport.width, viewport.height))
    ?? rect(Math.max(0, anchor.top), Math.max(0, anchor.left), 1, 1);
  if (!card || !intersect(clipped, card)) return clipped;

  const candidates = [
    rect(clipped.top, clipped.left, clipped.width, Math.max(0, card.top - clipped.top)),
    rect(Math.max(clipped.top, card.bottom), clipped.left, clipped.width, Math.max(0, clipped.bottom - Math.max(clipped.top, card.bottom))),
    rect(clipped.top, clipped.left, Math.max(0, card.left - clipped.left), clipped.height),
    rect(clipped.top, Math.max(clipped.left, card.right), Math.max(0, clipped.right - Math.max(clipped.left, card.right)), clipped.height),
  ].filter((candidate) => candidate.width > 0 && candidate.height > 0);

  return candidates.sort((a, b) => b.width * b.height - a.width * a.height)[0] ?? clipped;
}

function fits(top: number, left: number, card: Size, viewport: Size, margin: number): boolean {
  return top >= margin
    && left >= margin
    && top + card.height <= viewport.height - margin
    && left + card.width <= viewport.width - margin;
}

export function placeCard(
  anchor: Rect,
  card: Size,
  viewport: Size,
  requested: CardPlacement = "auto",
  margin = 12,
): CardPosition {
  const gap = 14;
  const choices: Array<{ placement: Exclude<CardPlacement, "auto">; top: number; left: number }> = [
    { placement: "bottom", top: anchor.bottom + gap, left: anchor.left + (anchor.width - card.width) / 2 },
    { placement: "top", top: anchor.top - card.height - gap, left: anchor.left + (anchor.width - card.width) / 2 },
    { placement: "right", top: anchor.top + (anchor.height - card.height) / 2, left: anchor.right + gap },
    { placement: "left", top: anchor.top + (anchor.height - card.height) / 2, left: anchor.left - card.width - gap },
  ];
  const ordered = requested === "auto"
    ? choices
    : [...choices.filter((choice) => choice.placement === requested), ...choices.filter((choice) => choice.placement !== requested)];
  const chosen = ordered.find((choice) => fits(choice.top, choice.left, card, viewport, margin)) ?? ordered[0];
  return {
    placement: chosen.placement,
    top: Math.min(Math.max(chosen.top, margin), Math.max(margin, viewport.height - card.height - margin)),
    left: Math.min(Math.max(chosen.left, margin), Math.max(margin, viewport.width - card.width - margin)),
  };
}

export function domRect(value: DOMRect): Rect {
  return rect(value.top, value.left, value.width, value.height);
}
