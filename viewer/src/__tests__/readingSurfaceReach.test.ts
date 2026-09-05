import { afterEach, describe, expect, it, vi } from "vitest";
import { foreignNodeUnderPoint } from "../utils/readingSurfacePlacement";

/**
 * A floating reading surface must not make the graph unreachable.
 *
 * The regression this guards: at depth 5 of the VS Code demo the preview of
 * one sibling came to rest over the whole of the next one, and because the
 * surface is interactive it swallowed the double-click that would have
 * drilled into it. The node could not be reached at all without panning the
 * graph away first.
 */

function stackOf(...entries: Array<{ node?: string } | "surface">) {
  const elements = entries.map((entry) => {
    if (entry === "surface") {
      return { closest: () => null } as unknown as Element;
    }
    const node = {
      getAttribute: (name: string) => (name === "data-component-id" ? entry.node ?? null : null),
    };
    return { closest: (selector: string) => (selector.includes("graph-node") ? node : null) } as unknown as Element;
  });
  vi.stubGlobal("document", { elementsFromPoint: () => elements });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("foreignNodeUnderPoint", () => {
  it("reports a sibling the surface is covering, so the card can get out of the way", () => {
    stackOf("surface", { node: "src/vs/sessions/test/e2e" });
    expect(foreignNodeUnderPoint(10, 10, "src/vs/sessions/test/browser")).toBe(true);
  });

  it("does not report the surface's own node, which is not somewhere else to go", () => {
    stackOf("surface", { node: "src/vs/sessions/test/browser" });
    expect(foreignNodeUnderPoint(10, 10, "src/vs/sessions/test/browser")).toBe(false);
  });

  it("reports nothing over empty canvas, which is what keeps the card readable", () => {
    stackOf("surface");
    expect(foreignNodeUnderPoint(10, 10, "src/vs/sessions/test/browser")).toBe(false);
  });

  it("takes the first node in the stack, not one buried under it", () => {
    stackOf("surface", { node: "src/vs/sessions/test/browser" }, { node: "src/vs/sessions/test" });
    expect(foreignNodeUnderPoint(10, 10, "src/vs/sessions/test/browser")).toBe(false);
  });

  it("stays quiet where the platform has no hit testing rather than closing the card", () => {
    vi.stubGlobal("document", {});
    expect(foreignNodeUnderPoint(10, 10, "anything")).toBe(false);
  });
});
