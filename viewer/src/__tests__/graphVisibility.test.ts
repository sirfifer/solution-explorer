import { describe, it, expect } from "vitest";
import { isUnobstructed, type VisibilityRect } from "../utils/graphVisibility";

// A tour stop (provider-seam step 3, unamentis/services/tts) settled under the
// React Flow minimap: inside the canvas rect, so the pan-to-selection effect
// called it visible and left it there, and the reader was pointed at a node
// they could not see. Containment is necessary, not sufficient.
//
// Fail-before proof: an isUnobstructed that ignores its third argument passes
// the containment cases below and fails every obstruction case.

const container: VisibilityRect = { left: 0, top: 0, right: 1000, bottom: 700 };
const minimap: VisibilityRect = { left: 800, top: 540, right: 990, bottom: 690 };
const tourPanel: VisibilityRect = { left: 0, top: 500, right: 420, bottom: 700 };

describe("isUnobstructed", () => {
  it("accepts a node wholly inside the canvas with nothing over it", () => {
    expect(isUnobstructed({ left: 100, top: 100, right: 380, bottom: 240 }, container, [minimap, tourPanel])).toBe(true);
  });

  it("rejects a node that hangs off any edge of the canvas", () => {
    const cases: VisibilityRect[] = [
      { left: -20, top: 100, right: 260, bottom: 240 },
      { left: 100, top: -20, right: 380, bottom: 120 },
      { left: 800, top: 100, right: 1080, bottom: 240 },
      { left: 100, top: 620, right: 380, bottom: 760 },
    ];
    for (const nodeRect of cases) {
      expect(isUnobstructed(nodeRect, container, [])).toBe(false);
    }
  });

  it("rejects a node fully under the minimap", () => {
    expect(isUnobstructed({ left: 830, top: 560, right: 960, bottom: 660 }, container, [minimap])).toBe(false);
  });

  it("rejects a node that only clips the corner of an overlay", () => {
    // One pixel of overlap is still a truncated node to the reader.
    expect(isUnobstructed({ left: 720, top: 460, right: 801, bottom: 541 }, container, [minimap])).toBe(false);
  });

  it("accepts a node that merely abuts an overlay without overlapping it", () => {
    expect(isUnobstructed({ left: 620, top: 460, right: 800, bottom: 540 }, container, [minimap])).toBe(true);
  });

  it("checks every overlay, not just the first", () => {
    const nodeRect: VisibilityRect = { left: 100, top: 560, right: 380, bottom: 660 };
    expect(isUnobstructed(nodeRect, container, [minimap])).toBe(true);
    expect(isUnobstructed(nodeRect, container, [minimap, tourPanel])).toBe(false);
  });

  it("ignores a zero-area overlay, so a collapsed panel does not veto the whole canvas", () => {
    const collapsed: VisibilityRect = { left: 0, top: 700, right: 1000, bottom: 700 };
    expect(isUnobstructed({ left: 100, top: 100, right: 380, bottom: 240 }, container, [collapsed])).toBe(true);
  });

  it("accepts a node touching the canvas edges exactly, which must not be re-centred", () => {
    // The S5 rule: a node that is fully visible and unobstructed does not move,
    // so the second click of a double-click lands where the first one did.
    expect(isUnobstructed({ left: 0, top: 0, right: 1000, bottom: 700 }, container, [])).toBe(true);
  });
});
