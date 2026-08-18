// Relationship roll-up (comprehension-study S1): edges between descendants of
// visible nodes must draw at the visible level instead of silently dropping,
// and a component's Links tab must show edges crossing its subtree boundary.

import { describe, it, expect } from "vitest";
import {
  buildNearestVisibleMap,
  collectSubtreeIds,
  rollUpRelationships,
  boundaryRelationships,
} from "../utils/relationshipRollup";
import type { Component, Relationship } from "../types";

function comp(id: string, children: Component[] = []): Component {
  return {
    id,
    name: id.split("/").pop() || id,
    type: "module",
    path: id,
    language: null,
    framework: null,
    port: null,
    children,
    files: [],
    entry_points: [],
    config_files: [],
    metrics: { files: 0, lines: 0, size_bytes: 0, symbols: 0, languages: {} },
    docs: {
      readme: null,
      claude_md: null,
      changelog: null,
      api_docs: null,
      architecture_notes: null,
      purpose: null,
      key_decisions: [],
      patterns: [],
      tech_stack: [],
      env_vars: [],
      api_endpoints: [],
    },
  } as unknown as Component;
}

function rel(
  source: string,
  target: string,
  type = "uses",
  extra: Partial<Relationship> = {},
): Relationship {
  return {
    source,
    target,
    type,
    label: null,
    protocol: null,
    port: null,
    bidirectional: false,
    ...extra,
  };
}

// The UnaMentis shape in miniature: an iOS client whose deep service modules
// call the management server, invisible at top level before the roll-up.
const TREE: Component[] = [
  comp("app", [comp("app/services", [comp("app/services/stt"), comp("app/services/tts")])]),
  comp("server", [comp("server/management", [comp("server/management/auth")])]),
];

describe("buildNearestVisibleMap", () => {
  it("maps every node to its nearest visible ancestor-or-self", () => {
    const map = buildNearestVisibleMap(TREE, new Set(["app", "server"]));
    expect(map.get("app")).toBe("app");
    expect(map.get("app/services/stt")).toBe("app");
    expect(map.get("server/management/auth")).toBe("server");
  });

  it("leaves nodes with no visible ancestor unmapped", () => {
    const map = buildNearestVisibleMap(TREE, new Set(["server"]));
    expect(map.has("app/services/stt")).toBe(false);
    expect(map.get("server/management")).toBe("server");
  });
});

describe("collectSubtreeIds", () => {
  it("collects the component and all descendants", () => {
    const ids = collectSubtreeIds(TREE, "app");
    expect(ids).toEqual(
      new Set(["app", "app/services", "app/services/stt", "app/services/tts"]),
    );
  });

  it("is empty for an unknown id", () => {
    expect(collectSubtreeIds(TREE, "nope").size).toBe(0);
  });
});

describe("rollUpRelationships", () => {
  const visible = new Set(["app", "server"]);

  it("draws deep cross-component edges between the visible ancestors", () => {
    const rolled = rollUpRelationships(
      [rel("app/services/stt", "server/management", "websocket", { protocol: "WebSocket" })],
      TREE,
      visible,
    );
    expect(rolled).toHaveLength(1);
    expect(rolled[0].source).toBe("app");
    expect(rolled[0].target).toBe("server");
    expect(rolled[0].type).toBe("websocket");
    expect(rolled[0].protocol).toBe("WebSocket");
    expect(rolled[0].rolled_up?.count).toBe(1);
    expect(rolled[0].rolled_up?.pairs).toEqual([
      { source: "app/services/stt", target: "server/management" },
    ]);
  });

  it("merges edges landing on the same visible pair and type, keeping first facts", () => {
    const rolled = rollUpRelationships(
      [
        rel("app/services/stt", "server/management", "websocket"),
        rel("app/services/tts", "server/management", "websocket", { port: 8766 }),
        rel("app/services/tts", "server/management/auth", "http", { protocol: "HTTP" }),
      ],
      TREE,
      visible,
    );
    expect(rolled).toHaveLength(2);
    const ws = rolled.find((r) => r.type === "websocket")!;
    expect(ws.port).toBe(8766);
    expect(ws.label).toBe("2 websocket links");
    expect(ws.rolled_up?.count).toBe(2);
    const http = rolled.find((r) => r.type === "http")!;
    expect(http.protocol).toBe("HTTP");
  });

  it("passes exact visible-to-visible edges through as the same object", () => {
    const exact = rel("app", "server", "http");
    const rolled = rollUpRelationships([exact], TREE, visible);
    expect(rolled).toHaveLength(1);
    expect(rolled[0]).toBe(exact);
    expect(rolled[0].rolled_up).toBeUndefined();
  });

  it("folds deep edges into an existing exact edge of the same pair and type", () => {
    const exact = rel("app", "server", "websocket", { protocol: "WebSocket" });
    const rolled = rollUpRelationships(
      [exact, rel("app/services/stt", "server/management", "websocket")],
      TREE,
      visible,
    );
    expect(rolled).toHaveLength(1);
    expect(rolled[0].protocol).toBe("WebSocket");
    expect(rolled[0].rolled_up?.count).toBe(1);
  });

  it("drops edges internal to one visible node and edges with unmapped endpoints", () => {
    const rolled = rollUpRelationships(
      [
        rel("app/services", "app/services/stt"),
        rel("app/services/stt", "elsewhere"),
      ],
      TREE,
      visible,
    );
    expect(rolled).toHaveLength(0);
  });
});

describe("boundaryRelationships", () => {
  it("includes edges crossing the subtree boundary in both directions", () => {
    const { relationships, subtree } = boundaryRelationships(
      [
        rel("app/services/stt", "server/management", "websocket"),
        rel("server/management", "app/services/tts", "http"),
        rel("server/management", "server/management/auth", "uses"),
      ],
      TREE,
      "app",
    );
    expect(relationships).toHaveLength(2);
    expect(subtree.has("app/services/stt")).toBe(true);
    expect(subtree.has("server")).toBe(false);
  });

  it("keeps direct edges and deduplicates repeats", () => {
    const dupe = rel("app", "app/services", "uses", { label: "uses Services" });
    const { relationships } = boundaryRelationships(
      [dupe, { ...dupe }],
      TREE,
      "app",
    );
    expect(relationships).toHaveLength(1);
  });

  it("excludes internal wiring that does not name the component", () => {
    const { relationships } = boundaryRelationships(
      [rel("app/services", "app/services/stt", "uses")],
      TREE,
      "app",
    );
    expect(relationships).toHaveLength(0);
  });
});
