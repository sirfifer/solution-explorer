import { describe, expect, it } from "vitest";
import type { Component } from "../types";
import { componentHelp, componentSummary, usableComponentText } from "../utils/componentText";

function component(overrides: Partial<Component> = {}): Component {
  return {
    id: "c", name: "C", type: "module", path: "src/c", language: null,
    framework: null, description: null, port: null, children: [], files: [],
    entry_points: [], config_files: [], metrics: { files: 0, lines: 0, symbols: 0, size_bytes: 0 },
    docs: { purpose: "", patterns: [], tech_stack: [], api_endpoints: [], env_vars: [] },
    ...overrides,
  } as Component;
}

describe("component text fallbacks", () => {
  it("rejects blank and package-localization placeholders", () => {
    expect(usableComponentText("  ")).toBeNull();
    expect(usableComponentText("%description%")).toBeNull();
  });

  it("prefers repository-derived prose and falls back to enrichment", () => {
    expect(componentSummary(component({
      description: "%description%",
      ai_enhance: { description: "Mapped extension behavior." },
    }))).toBe("Mapped extension behavior.");
    expect(componentSummary(component({
      description: "Mechanical description.",
      ai_enhance: { description: "Interpreted description." },
    }))).toBe("Mechanical description.");
  });

  it("uses help text for help before the concise summary", () => {
    const value = component({
      description: "Mechanical description.",
      ai_enhance: { help_text: "Longer help." },
    });
    expect(componentHelp(value)).toBe("Longer help.");
  });
});
