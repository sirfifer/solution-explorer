import { describe, expect, it } from "vitest";
import { applicableStops, firstVisitDecision, highlightRect, placeCard, type Rect } from "../model";
import { WALK_STOPS } from "../stops";

const anchor: Rect = { top: 100, right: 180, bottom: 140, left: 100, width: 80, height: 40 };

describe("orientation model", () => {
  it("selects eight desktop stops and seven mobile stops", () => {
    expect(applicableStops(WALK_STOPS, 1440).map((stop) => stop.id)).toHaveLength(8);
    expect(applicableStops(WALK_STOPS, 390).map((stop) => stop.id)).toHaveLength(7);
    expect(applicableStops(WALK_STOPS, 700).some((stop) => stop.id === "how-much-was-analyzed")).toBe(false);
  });

  it.each([
    ["?orientation=start", "done", "true", "start"],
    ["?orientation=invite", "done", "true", "start"],
    ["", "done", null, "none"],
    ["", null, "true", "none"],
    ["", null, null, "start"],
  ])("chooses the first visit entry for %s", (search, stored, legacy, expected) => {
    expect(firstVisitDecision(search, stored, legacy)).toBe(expected);
  });

  it("expands and clips a highlight to the viewport", () => {
    expect(highlightRect(anchor, { width: 160, height: 130 })).toEqual({
      top: 94,
      right: 160,
      bottom: 130,
      left: 94,
      width: 66,
      height: 36,
    });
  });

  it("keeps the highlight nonempty and outside an overlapping card", () => {
    const result = highlightRect(anchor, { width: 400, height: 300 }, {
      top: 118,
      right: 300,
      bottom: 260,
      left: 80,
      width: 220,
      height: 142,
    });
    expect(result.width).toBeGreaterThan(0);
    expect(result.height).toBeGreaterThan(0);
    expect(result.bottom).toBeLessThanOrEqual(118);
  });

  it("places below first, then falls back above", () => {
    expect(placeCard(anchor, { width: 100, height: 60 }, { width: 500, height: 400 }).placement).toBe("bottom");
    const lowAnchor = { ...anchor, top: 330, bottom: 370 };
    expect(placeCard(lowAnchor, { width: 100, height: 80 }, { width: 500, height: 400 }).placement).toBe("top");
  });

  it("honors a requested side by clamping it into view when it remains clear of the anchor", () => {
    const headerAnchor = { ...anchor, top: 60, bottom: 100, left: 900, right: 1200, width: 300 };
    expect(placeCard(headerAnchor, { width: 320, height: 240 }, { width: 1280, height: 720 }, "left")).toEqual({
      placement: "left",
      top: 12,
      left: 566,
    });
  });
});
