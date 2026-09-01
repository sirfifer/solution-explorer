import { describe, expect, it } from "vitest";
import type { Edge, Node } from "@xyflow/react";
import { getLayoutedElements } from "../utils/layout";

function node(id: string): Node {
  return {
    id,
    position: { x: 0, y: 0 },
    measured: { width: 280, height: 160 },
    data: { component: { type: "module" } },
  };
}

function edge(id: string, source: string, target: string, label: string): Edge {
  return {
    id,
    source,
    target,
    label,
    labelStyle: { fontSize: 13 },
  };
}

describe("ELK route integration", () => {
  it("returns the collision-aware bend path and label box React Flow will draw", async () => {
    const result = await getLayoutedElements(
      [node("client"), node("api"), node("database")],
      [
        edge("client-api", "client", "api", "HTTP WEBSOCKET 🔒jwt"),
        edge("api-db", "api", "database", "SQL :5432"),
      ],
      "DOWN",
      0.75,
    );

    for (const routed of result.edges) {
      expect(routed.type).toBe("elk");
      expect(routed.data?.elkPath).toMatch(/^M /);
      expect(routed.data?.elkLabel).toEqual(expect.objectContaining({
        x: expect.any(Number),
        y: expect.any(Number),
        width: expect.any(Number),
        height: expect.any(Number),
      }));
    }
  });

  it("uses the rendered node dimensions instead of a generic box", async () => {
    const tall = node("phone");
    tall.measured = { width: 220, height: 380 };
    const result = await getLayoutedElements(
      [tall, node("server")],
      [edge("phone-server", "phone", "server", "WebSocket")],
      "DOWN",
      0.6,
    );
    const routedPhone = result.nodes.find((item) => item.id === "phone");
    const routedServer = result.nodes.find((item) => item.id === "server");
    expect(routedPhone).toBeDefined();
    expect(routedServer).toBeDefined();
    expect((routedServer?.position.y ?? 0) - (routedPhone?.position.y ?? 0)).toBeGreaterThanOrEqual(380);
  });
});
