// The viewer intentionally carries no Node type package. Vitest still runs in
// Node, so these two built-ins are available to this source-contract test.
// @ts-expect-error Node types are intentionally absent from the viewer build.
import { readdirSync, readFileSync } from "node:fs";
// @ts-expect-error Node types are intentionally absent from the viewer build.
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { WALK_STOPS, type WalkContext } from "../stops";

declare const process: { cwd: () => string };

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry: { name: string; isDirectory: () => boolean }) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(entry.name) ? [path] : [];
  });
}

const fixtureContext: WalkContext = {
  displayName: "VS Code",
  identitySummary: "A desktop code editor.",
  lensLabels: ["Structure", "Inventory", "Activity", "Flow"],
  hasGuidedPaths: true,
  isMobile: false,
  isMac: true,
};

describe("orientation stop table", () => {
  it("keeps every anchor tied to a literal test id in the viewer", () => {
    const source = sourceFiles(join(process.cwd(), "src"))
      .map((path) => readFileSync(path, "utf8"))
      .join("\n");
    for (const stop of WALK_STOPS) {
      expect(source, stop.anchor).toContain(`data-testid="${stop.anchor}"`);
      if (stop.fallbackAnchor) {
        expect(source, stop.fallbackAnchor).toContain(`data-testid="${stop.fallbackAnchor}"`);
      }
    }
  });

  it("keeps the approved copy short and free of sentence dashes", () => {
    for (const stop of WALK_STOPS) {
      const body = stop.body(fixtureContext);
      expect(body.trim().split(/\s+/).length, stop.id).toBeLessThanOrEqual(25);
      expect(`${stop.heading}${body}`, stop.id).not.toMatch(/[–—]/);
    }
  });

  it("uses stable unique ids", () => {
    expect(new Set(WALK_STOPS.map((stop) => stop.id)).size).toBe(WALK_STOPS.length);
    for (const stop of WALK_STOPS) expect(stop.id).toMatch(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);
  });
});
