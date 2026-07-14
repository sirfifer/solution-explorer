import { describe, it, expect } from "vitest";
import { buildRationale } from "../components/RationaleStrip";
import type { Component } from "../types";

// I13: the rationale strip surfaces whatever ownership / last-change / churn /
// commit / PR / AI-intent data is present, and renders nothing when none is.
// buildRationale is the pure core the strip renders; a null return means the
// strip renders nothing (degrades cleanly).

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "c", name: "C", type: "module", path: "src/c", language: "typescript",
    framework: null, description: null, port: null, children: [], files: [],
    entry_points: [], config_files: [],
    metrics: { files: 0, lines: 0, size_bytes: 0, symbols: 0, languages: {} },
    docs: { readme: null, claude_md: null, changelog: null, api_docs: null, architecture_notes: null, purpose: null, key_decisions: [], patterns: [], tech_stack: [], env_vars: [], api_endpoints: [] },
    ...overrides,
  };
}

describe("buildRationale (I13)", () => {
  it("returns nothing when the dataset carries no rationale data", () => {
    expect(buildRationale(makeComponent())).toBeNull();
  });

  it("surfaces AI intent (architectural role and help-text presence) when present", () => {
    const r = buildRationale(makeComponent({
      ai_enhance: { architectural_role: "gateway", help_text: "Fronts the providers.", ai_enhanced_at: "2026-07-13T00:00:00Z" },
    }));
    expect(r).not.toBeNull();
    expect(r?.role).toBe("gateway");
    expect(r?.hasAiIntent).toBe(true);
    expect(r?.aiEnhancedAt).toBe("2026-07-13T00:00:00Z");
  });

  it("surfaces git-activity fields (author, last change, churn, commit, PR) when present", () => {
    const r = buildRationale(makeComponent({
      rationale: { author: "arivera", last_change: "3 days ago", churn: 12, commit: "abcdef1234", pr: "142" },
    }));
    expect(r).not.toBeNull();
    expect(r?.author).toBe("arivera");
    expect(r?.lastChange).toBe("3 days ago");
    expect(r?.churn).toBe(12);
    expect(r?.commit).toBe("abcdef1234");
    expect(r?.pr).toBe("142");
  });

  it("uses the first author when only an authors array is present", () => {
    const r = buildRationale(makeComponent({ rationale: { authors: ["lead", "second"] } }));
    expect(r?.author).toBe("lead");
  });

  it("treats churn of zero as present (not absent)", () => {
    const r = buildRationale(makeComponent({ rationale: { churn: 0 } }));
    expect(r).not.toBeNull();
    expect(r?.churn).toBe(0);
  });
});
