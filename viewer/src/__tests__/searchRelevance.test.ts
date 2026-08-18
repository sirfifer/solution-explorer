import { describe, it, expect, beforeEach } from "vitest";
import {
  initializeSearch,
  search,
  resetDetailSearchEntries,
  resetShardSearchEntries,
} from "../utils/search";
import type { Architecture, Component } from "../types";

// Comprehension-study S7: search returned confident-looking noise for terms
// absent from the codebase (a query for "billing" surfaced an unrelated
// linguistic matcher and multilingual docs), and API endpoints and env vars
// were in no index at all, so "/ws/audio" found nothing relevant.

function makeComponent(overrides: Partial<Component> = {}): Component {
  return {
    id: "c", name: "C", type: "module", path: "src/c",
    language: "typescript", framework: null, description: null, port: null,
    children: [], files: [], entry_points: [], config_files: [],
    metrics: { files: 0, lines: 0, size_bytes: 0, symbols: 0, languages: {} },
    docs: {
      readme: null, claude_md: null, changelog: null, api_docs: null,
      architecture_notes: null, purpose: null, key_decisions: [], patterns: [],
      tech_stack: [], env_vars: [], api_endpoints: [],
    },
    ...overrides,
  };
}

function makeArchitecture(components: Component[]): Architecture {
  return {
    name: "T", description: "", repository: null,
    generated_at: "2026-01-01T00:00:00Z", analyzer_version: "1.2.0",
    root_path: "/t", components, relationships: [], symbols: [], files: [],
    stats: {
      total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {},
      total_symbols: 0, total_components: components.length,
      total_relationships: 0,
    },
  };
}

const ARCH = makeArchitecture([
  makeComponent({
    id: "mgmt", name: "unamentis-management", type: "api-server",
    path: "server/management", language: "python",
    docs: {
      readme: null, claude_md: null, changelog: null, api_docs: null,
      architecture_notes: null, purpose: "The management API server.",
      key_decisions: [], patterns: [], tech_stack: [],
      env_vars: ["DIAGNOSTIC_LOGGING"],
      api_endpoints: [
        { method: "GET", path: "/ws/audio" },
        { method: "POST", path: "/api/sessions" },
      ],
    },
  }),
  makeComponent({
    id: "kb", name: "KBLinguisticMatcher", type: "module",
    path: "src/kb/KBLinguisticMatcher.ts",
  }),
  makeComponent({
    id: "ml", name: "MULTILINGUAL_NOTES", type: "module",
    path: "docs/MULTILINGUAL_NOTES.md",
  }),
]);

beforeEach(() => {
  resetDetailSearchEntries();
  resetShardSearchEntries();
  initializeSearch(ARCH);
});

describe("relevance floor", () => {
  it("returns nothing for a concept absent from the codebase", () => {
    // "billing" letters can be found scattered through MULTILINGUAL and
    // KBLinguisticMatcher; neither is an answer.
    expect(search("billing")).toEqual([]);
  });

  it("still finds real matches by name", () => {
    expect(search("management").map((r) => r.id)).toContain("mgmt");
    expect(search("KBLinguistic").map((r) => r.id)).toContain("kb");
  });

  it("still finds a component by its plain-language purpose", () => {
    expect(search("management API").map((r) => r.id)).toContain("mgmt");
  });
});

describe("endpoint and env-var indexing", () => {
  it("finds the owning component by an API endpoint path", () => {
    expect(search("/ws/audio").map((r) => r.id)).toContain("mgmt");
  });

  it("finds the owning component by an environment variable name", () => {
    expect(search("DIAGNOSTIC_LOGGING").map((r) => r.id)).toContain("mgmt");
  });
});
