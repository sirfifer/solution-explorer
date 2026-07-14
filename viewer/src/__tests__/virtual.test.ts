import { describe, it, expect } from "vitest";
import { computeOffsets, computeVisibleRange } from "../utils/virtual";

// Construction proof for the VirtualList windowing math (P6-4). jsdom reports
// zero-height elements, so the DOM cannot exercise real scrolling; these assert
// the pure geometry the component relies on.

describe("computeOffsets", () => {
  it("builds a prefix-sum offset array one longer than the heights", () => {
    expect(computeOffsets([10, 20, 30])).toEqual([0, 10, 30, 60]);
  });

  it("handles an empty list", () => {
    expect(computeOffsets([])).toEqual([0]);
  });

  it("clamps negative heights to zero", () => {
    expect(computeOffsets([10, -5, 5])).toEqual([0, 10, 10, 15]);
  });
});

describe("computeVisibleRange", () => {
  const offsets = computeOffsets(new Array(1000).fill(40)); // 1000 rows, 40px each

  it("renders only the visible window plus overscan when the viewport is known", () => {
    // Scrolled to 4000px (row 100), 400px viewport (10 rows) -> rows ~100..110.
    const r = computeVisibleRange(offsets, 4000, 400, 6);
    expect(r.totalHeight).toBe(40000);
    // Window is bounded and small, not the whole 1000 rows.
    expect(r.end - r.start).toBeLessThan(40);
    expect(r.start).toBeLessThanOrEqual(100);
    expect(r.end).toBeGreaterThanOrEqual(110);
    // Top spacer aligns to the first rendered row.
    expect(r.offsetTop).toBe(offsets[r.start]);
  });

  it("renders every row when the viewport height is unknown (0)", () => {
    const r = computeVisibleRange(offsets, 0, 0, 6);
    expect(r.start).toBe(0);
    expect(r.end).toBe(1000);
  });

  it("clamps the window to the list bounds", () => {
    const top = computeVisibleRange(offsets, 0, 400, 6);
    expect(top.start).toBe(0);
    const bottom = computeVisibleRange(offsets, 40000, 400, 6);
    expect(bottom.end).toBe(1000);
  });

  it("handles variable row heights", () => {
    const off = computeOffsets([100, 100, 100, 100, 100]);
    // Viewport [150, 350] touches rows 1, 2 and 3 (row 3 spans 300..400);
    // overscan 0 keeps the window tight.
    const r = computeVisibleRange(off, 150, 200, 0);
    expect(r.start).toBe(1);
    expect(r.end).toBe(4);
  });

  it("returns an empty range for an empty list", () => {
    const r = computeVisibleRange([0], 0, 400, 6);
    expect(r.start).toBe(0);
    expect(r.end).toBe(0);
    expect(r.totalHeight).toBe(0);
  });
});
