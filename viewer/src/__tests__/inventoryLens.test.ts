// Inventory lens (owner decision 2026-08-17): the aggregate surface for the
// first stakeholder questions. I14: every documented question's gesture is
// exercised here with an asserted answer.

import { describe, it, expect } from "vitest";
import {
  inventoryLens,
  INVENTORY_QUESTIONS,
  collectCriticalComponents,
  collectExternalDependencies,
  collectListeningPorts,
  hasCriticalityData,
  getLens,
} from "../lenses";
import type { Architecture, Component } from "../types";

function comp(overrides: Partial<Component>): Component {
  return {
    id: "c", name: "C", type: "module", path: "src/c", language: null,
    framework: null, description: null, port: null, children: [], files: [],
    entry_points: [], config_files: [],
    metrics: { files: 0, lines: 0, size_bytes: 0, symbols: 0, languages: {} },
    docs: {
      readme: null, claude_md: null, changelog: null, api_docs: null,
      architecture_notes: null, purpose: null, key_decisions: [], patterns: [],
      tech_stack: [], env_vars: [], api_endpoints: [],
    },
    ...overrides,
  } as Component;
}

function arch(components: Component[]): Architecture {
  return {
    name: "T", description: "", repository: null,
    generated_at: "2026-01-01T00:00:00Z", analyzer_version: "1.2.0",
    root_path: "/t", components, relationships: [], symbols: [], files: [],
    stats: {
      total_files: 0, total_lines: 0, total_size_bytes: 0, languages: {},
      total_symbols: 0, total_components: components.length,
      total_relationships: 0,
    },
  } as Architecture;
}

const SAMPLE = arch([
  comp({
    id: "server", name: "management", type: "api-server", port: 8766,
    ai_enhance: { criticality: "critical", description: "The API hub." },
    external_services: [{ name: "OpenAI", category: "ai" }],
    children: [
      comp({
        id: "server/tts", name: "tts", type: "module",
        ai_enhance: { criticality: "important", description: "Speech synthesis." },
        external_services: [
          { name: "ElevenLabs", category: "ai" },
          { name: "OpenAI", category: "ai" },
        ],
      }),
    ],
  }),
  comp({ id: "logs", name: "log-server", type: "service", port: 8765 }),
  comp({
    id: "app", name: "iOS", type: "ios-client",
    ai_enhance: { criticality: "critical", description: "The client." },
  }),
]);

describe("inventory lens registration", () => {
  it("registers and is available for every dataset", () => {
    expect(getLens("inventory")).toBe(inventoryLens);
    expect(inventoryLens.isAvailable(SAMPLE)).toBe(true);
    expect(inventoryLens.isAvailable(arch([]))).toBe(true);
  });

  it("documents its questions (I14)", () => {
    expect(INVENTORY_QUESTIONS.map((q) => q.id)).toEqual([
      "critical", "dependencies", "ports",
    ]);
  });
});

describe("answers: Which components are make-or-break critical?", () => {
  it("ranks critical before important, tree order within a tier", () => {
    const entries = collectCriticalComponents(SAMPLE);
    expect(entries.map((e) => e.id)).toEqual(["server", "app", "server/tts"]);
    expect(entries[0].criticality).toBe("critical");
    expect(entries[0].purpose).toBe("The API hub.");
    expect(entries[2].criticality).toBe("important");
  });

  it("sinks screens below servers and clients within a tier (I11 ranking)", () => {
    const withScreen = arch([
      comp({ id: "chat", name: "Chat", type: "screen", ai_enhance: { criticality: "critical" } }),
      comp({ id: "server", name: "management", type: "api-server", ai_enhance: { criticality: "critical" } }),
      comp({ id: "app", name: "iOS", type: "ios-client", ai_enhance: { criticality: "critical" } }),
    ]);
    expect(collectCriticalComponents(withScreen).map((e) => e.id)).toEqual([
      "server", "app", "chat",
    ]);
  });

  it("is honestly empty without enrichment", () => {
    const plain = arch([comp({ id: "a" })]);
    expect(hasCriticalityData(plain)).toBe(false);
    expect(collectCriticalComponents(plain)).toEqual([]);
    expect(hasCriticalityData(SAMPLE)).toBe(true);
  });
});

describe("answers: What outside services does this depend on?", () => {
  it("aggregates vendors across the tree, most-used first, users listed", () => {
    const deps = collectExternalDependencies(SAMPLE);
    expect(deps.map((d) => d.name)).toEqual(["OpenAI", "ElevenLabs"]);
    expect(deps[0].componentIds).toEqual(["server", "server/tts"]);
    expect(deps[1].componentNames).toEqual(["tts"]);
  });
});

describe("answers: What runs where?", () => {
  it("lists listening components ascending by port", () => {
    const ports = collectListeningPorts(SAMPLE);
    expect(ports.map((p) => `${p.name}:${p.port}`)).toEqual([
      "log-server:8765", "management:8766",
    ]);
  });
});

describe("question coverage", () => {
  it("every documented question has a tested gesture and vice-versa", () => {
    // The three describe blocks above each exercise one question id.
    const tested = ["critical", "dependencies", "ports"];
    expect(INVENTORY_QUESTIONS.map((q) => q.id).sort()).toEqual([...tested].sort());
  });
});
