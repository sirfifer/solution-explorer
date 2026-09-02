import { describe, it, expect, vi } from "vitest";
import type { Rect } from "@xyflow/react";
import {
  isSelectionUnobstructed,
  toFlowRect,
  type VisibilityRect,
} from "../utils/graphVisibility";

// A tour stop (provider-seam step 3, unamentis/services/tts) settled under the
// React Flow minimap: inside the canvas rect, so the pan-to-selection effect
// called it visible and left it there, and the reader was pointed at a node
// they could not see. Containment is necessary, not sufficient.
//
// The module no longer owns any geometry. It converts client rects to flow
// coordinates with React Flow's screenToFlowPosition and asks React Flow's
// isNodeIntersecting the two questions. So there are two things to hold: that
// the conversion is a real inverse of the viewport transform, and that the
// right question is asked of each rectangle (containment for the canvas, any
// overlap at all for an overlay).

/** The canvas, its two worst overlays, and the node, all in client space. */
const pane: VisibilityRect = { left: 0, top: 0, right: 1000, bottom: 700 };
const minimap: VisibilityRect = { left: 800, top: 540, right: 990, bottom: 690 };
const tourPanel: VisibilityRect = { left: 0, top: 500, right: 420, bottom: 700 };

/**
 * A screenToFlowPosition with the same contract as React Flow's: undo the
 * viewport transform, relative to a container whose top-left is the client
 * origin (which `pane` above is).
 */
function screenToFlow(zoom: number, tx: number, ty: number) {
  return (p: { x: number; y: number }) => ({ x: (p.x - tx) / zoom, y: (p.y - ty) / zoom });
}

/**
 * React Flow's isNodeIntersecting, as shipped in
 * @xyflow/react 12.10 (`overlappingArea > 0` when partially, otherwise one
 * rectangle has to swallow the other). Stated here so the cases below assert
 * behaviour rather than call shape; the call shape is asserted separately.
 */
function intersectingWith(nodeRect: Rect) {
  return (_node: unknown, area: Rect, partially = true): boolean => {
    const xOverlap = Math.max(
      0,
      Math.min(nodeRect.x + nodeRect.width, area.x + area.width) - Math.max(nodeRect.x, area.x),
    );
    const yOverlap = Math.max(
      0,
      Math.min(nodeRect.y + nodeRect.height, area.y + area.height) - Math.max(nodeRect.y, area.y),
    );
    const overlap = Math.ceil(xOverlap * yOverlap);
    return (
      (partially && overlap > 0) ||
      overlap >= area.width * area.height ||
      overlap >= nodeRect.width * nodeRect.height
    );
  };
}

const node = { id: "selected" };

function visible(
  nodeRect: Rect,
  obstructions: VisibilityRect[],
  transform = screenToFlow(1, 0, 0),
): boolean {
  return isSelectionUnobstructed({
    node,
    paneRect: pane,
    obstructions,
    screenToFlowPosition: transform,
    isNodeIntersecting: intersectingWith(nodeRect),
  });
}

describe("toFlowRect", () => {
  it("is the inverse of the viewport transform, not a copy of it", () => {
    // Zoom 2, panned by (-100, -50): a client rect from (100,50) to (300,250)
    // is flow (100,50) to (200,150).
    const flow = toFlowRect(
      { left: 100, top: 50, right: 300, bottom: 250 },
      screenToFlow(2, -100, -50),
    );
    expect(flow).toEqual({ x: 100, y: 50, width: 100, height: 100 });
  });

  it("never reports a negative size for an inverted rect", () => {
    const flow = toFlowRect({ left: 300, top: 250, right: 100, bottom: 50 }, screenToFlow(1, 0, 0));
    expect(flow.width).toBe(0);
    expect(flow.height).toBe(0);
  });
});

describe("isSelectionUnobstructed", () => {
  it("asks React Flow for containment against the canvas and overlap against overlays", () => {
    const spy = vi.fn().mockReturnValue(false);
    isSelectionUnobstructed({
      node,
      paneRect: pane,
      obstructions: [minimap],
      screenToFlowPosition: screenToFlow(1, 0, 0),
      isNodeIntersecting: spy,
    });
    // The canvas question is "is it wholly inside", which is partially: false.
    expect(spy).toHaveBeenCalledWith(node, { x: 0, y: 0, width: 1000, height: 700 }, false);

    const overlapSpy = vi.fn().mockImplementation((_n, _a, partially) => partially === false);
    isSelectionUnobstructed({
      node,
      paneRect: pane,
      obstructions: [minimap],
      screenToFlowPosition: screenToFlow(1, 0, 0),
      isNodeIntersecting: overlapSpy,
    });
    // The overlay question is "does it touch at all", which is partially: true.
    expect(overlapSpy).toHaveBeenCalledWith(node, { x: 800, y: 540, width: 190, height: 150 }, true);
  });

  it("accepts a node wholly inside the canvas with nothing over it", () => {
    expect(visible({ x: 100, y: 100, width: 280, height: 140 }, [minimap, tourPanel])).toBe(true);
  });

  it("rejects a node that hangs off any edge of the canvas", () => {
    const cases: Rect[] = [
      { x: -20, y: 100, width: 280, height: 140 },
      { x: 100, y: -20, width: 280, height: 140 },
      { x: 800, y: 100, width: 280, height: 140 },
      { x: 100, y: 620, width: 280, height: 140 },
    ];
    for (const nodeRect of cases) {
      expect(visible(nodeRect, [])).toBe(false);
    }
  });

  it("rejects a node fully under the minimap", () => {
    expect(visible({ x: 830, y: 560, width: 130, height: 100 }, [minimap])).toBe(false);
  });

  it("rejects a node that only clips the corner of an overlay", () => {
    // One pixel of overlap is still a truncated node to the reader.
    expect(visible({ x: 720, y: 460, width: 81, height: 81 }, [minimap])).toBe(false);
  });

  it("accepts a node that merely abuts an overlay without overlapping it", () => {
    expect(visible({ x: 620, y: 460, width: 180, height: 80 }, [minimap])).toBe(true);
  });

  it("checks every overlay, not just the first", () => {
    const nodeRect: Rect = { x: 100, y: 560, width: 280, height: 100 };
    expect(visible(nodeRect, [minimap])).toBe(true);
    expect(visible(nodeRect, [minimap, tourPanel])).toBe(false);
  });

  it("ignores a zero-area overlay, so a collapsed panel does not veto the whole canvas", () => {
    const collapsed: VisibilityRect = { left: 0, top: 700, right: 1000, bottom: 700 };
    expect(visible({ x: 100, y: 100, width: 280, height: 140 }, [collapsed])).toBe(true);
  });

  it("accepts a node touching the canvas edges exactly, which must not be re-centred", () => {
    // The S5 rule: a node that is fully visible and unobstructed does not move,
    // so the second click of a double-click lands where the first one did.
    expect(visible({ x: 0, y: 0, width: 1000, height: 700 }, [])).toBe(true);
  });

  it("judges visibility under the live viewport, not under an assumed one", () => {
    // The same node in flow space, seen at zoom 2 panned by (-100, -50): the
    // canvas covers flow (50,25) to (550,375), so a node at flow (600,100) is
    // off screen even though it would be inside at zoom 1 and no pan.
    const offAtThisZoom = { x: 600, y: 100, width: 280, height: 140 };
    expect(visible(offAtThisZoom, [], screenToFlow(2, -100, -50))).toBe(false);
    expect(visible(offAtThisZoom, [], screenToFlow(1, 0, 0))).toBe(true);
  });
});
