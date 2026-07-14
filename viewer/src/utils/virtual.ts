/**
 * Windowing math for the detail-panel VirtualList (P6-4).
 *
 * Long lists (symbols especially, which the analyzer can emit in the thousands)
 * render only the rows in view plus a small overscan, so the DOM stays small no
 * matter how large the list is. Row heights may vary (an inline-expanded symbol
 * row is taller than a collapsed one), so the geometry is driven by an explicit
 * per-row height array rather than a single fixed height.
 *
 * These functions are pure and side-effect free so the windowing is testable
 * without a real layout (jsdom reports zero-height elements).
 */

/**
 * Cumulative pixel offsets for a list of row heights. `offsets[i]` is the top of
 * row i; `offsets[heights.length]` is the total content height. Always one
 * element longer than `heights`.
 */
export function computeOffsets(heights: number[]): number[] {
  const offsets = new Array<number>(heights.length + 1);
  offsets[0] = 0;
  for (let i = 0; i < heights.length; i++) {
    offsets[i + 1] = offsets[i] + Math.max(0, heights[i]);
  }
  return offsets;
}

export interface VisibleRange {
  /** First row index to render (inclusive). */
  start: number;
  /** Last row index to render, exclusive (so rows [start, end) render). */
  end: number;
  /** Total content height in pixels (offsets[last]). */
  totalHeight: number;
  /** Pixel offset of the first rendered row (for the top spacer). */
  offsetTop: number;
}

/**
 * Compute the visible row window for a scroll position.
 *
 * When `viewportHeight` is unknown (0, e.g. before layout or in jsdom) the whole
 * list is returned so nothing is ever hidden by a missing measurement. Otherwise
 * the range covers `[scrollTop, scrollTop + viewportHeight]` widened by
 * `overscan` rows on each side.
 */
export function computeVisibleRange(
  offsets: number[],
  scrollTop: number,
  viewportHeight: number,
  overscan = 6,
): VisibleRange {
  const rowCount = Math.max(0, offsets.length - 1);
  const totalHeight = offsets[rowCount] ?? 0;

  if (rowCount === 0) {
    return { start: 0, end: 0, totalHeight, offsetTop: 0 };
  }

  // Unknown viewport: render everything (safe fallback, never hides a row).
  if (!viewportHeight || viewportHeight <= 0) {
    return { start: 0, end: rowCount, totalHeight, offsetTop: 0 };
  }

  const top = Math.max(0, scrollTop);
  const bottom = scrollTop + viewportHeight;

  // offsets is a prefix-sum array, so both bounds are binary searches:
  // O(log n) per scroll event instead of a linear scan (Copilot, PR #25).
  // start: first row whose bottom edge (offsets[i + 1]) is past the top.
  let lo = 0;
  let hi = rowCount;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (offsets[mid + 1] <= top) lo = mid + 1;
    else hi = mid;
  }
  let start = lo;
  // end: first row whose top edge (offsets[i]) is at or past the bottom.
  hi = rowCount;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (offsets[mid] < bottom) lo = mid + 1;
    else hi = mid;
  }
  let end = lo;

  start = Math.max(0, start - overscan);
  end = Math.min(rowCount, end + overscan);

  return { start, end, totalHeight, offsetTop: offsets[start] };
}
