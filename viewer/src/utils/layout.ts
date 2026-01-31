import ELK from "elkjs/lib/elk.bundled.js";
import type { Node, Edge } from "@xyflow/react";

const elk = new ELK();

const DEFAULT_NODE_WIDTH = 280;
const DEFAULT_NODE_HEIGHT = 140;

export async function getLayoutedElements(
  nodes: Node[],
  edges: Edge[],
  direction: "RIGHT" | "DOWN" = "RIGHT",
): Promise<{ nodes: Node[]; edges: Edge[] }> {
  const elkGraph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": direction,
      "elk.spacing.nodeNode": "60",
      "elk.layered.spacing.nodeNodeBetweenLayers": "80",
      "elk.padding": "[top=40,left=40,bottom=40,right=40]",
      "elk.layered.mergeEdges": "true",
      "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
      "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
    },
    children: nodes.map((node) => ({
      id: node.id,
      width: node.measured?.width ?? DEFAULT_NODE_WIDTH,
      height: node.measured?.height ?? DEFAULT_NODE_HEIGHT,
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      sources: [edge.source],
      targets: [edge.target],
    })),
  };

  const layout = await elk.layout(elkGraph);

  const layoutedNodes = nodes.map((node) => {
    const elkNode = layout.children?.find((n) => n.id === node.id);
    if (elkNode) {
      return {
        ...node,
        position: {
          x: elkNode.x ?? 0,
          y: elkNode.y ?? 0,
        },
      };
    }
    return node;
  });

  return { nodes: layoutedNodes, edges };
}

// Color mapping for component types
const TYPE_COLORS: Record<string, { bg: string; border: string; text: string; badge: string }> = {
  application: { bg: "bg-blue-950/60", border: "border-blue-500/50", text: "text-blue-300", badge: "bg-blue-500/20 text-blue-300" },
  service: { bg: "bg-emerald-950/60", border: "border-emerald-500/50", text: "text-emerald-300", badge: "bg-emerald-500/20 text-emerald-300" },
  library: { bg: "bg-violet-950/60", border: "border-violet-500/50", text: "text-violet-300", badge: "bg-violet-500/20 text-violet-300" },
  package: { bg: "bg-amber-950/60", border: "border-amber-500/50", text: "text-amber-300", badge: "bg-amber-500/20 text-amber-300" },
  module: { bg: "bg-cyan-950/60", border: "border-cyan-500/50", text: "text-cyan-300", badge: "bg-cyan-500/20 text-cyan-300" },
  infrastructure: { bg: "bg-rose-950/60", border: "border-rose-500/50", text: "text-rose-300", badge: "bg-rose-500/20 text-rose-300" },
  project: { bg: "bg-zinc-800/60", border: "border-zinc-500/50", text: "text-zinc-300", badge: "bg-zinc-500/20 text-zinc-300" },
};

const TYPE_COLORS_LIGHT: Record<string, { bg: string; border: string; text: string; badge: string }> = {
  application: { bg: "bg-blue-50", border: "border-blue-300", text: "text-blue-700", badge: "bg-blue-100 text-blue-700" },
  service: { bg: "bg-emerald-50", border: "border-emerald-300", text: "text-emerald-700", badge: "bg-emerald-100 text-emerald-700" },
  library: { bg: "bg-violet-50", border: "border-violet-300", text: "text-violet-700", badge: "bg-violet-100 text-violet-700" },
  package: { bg: "bg-amber-50", border: "border-amber-300", text: "text-amber-700", badge: "bg-amber-100 text-amber-700" },
  module: { bg: "bg-cyan-50", border: "border-cyan-300", text: "text-cyan-700", badge: "bg-cyan-100 text-cyan-700" },
  infrastructure: { bg: "bg-rose-50", border: "border-rose-300", text: "text-rose-700", badge: "bg-rose-100 text-rose-700" },
  project: { bg: "bg-zinc-50", border: "border-zinc-300", text: "text-zinc-700", badge: "bg-zinc-100 text-zinc-700" },
};

export function getTypeColors(type: string, dark: boolean = true) {
  const map = dark ? TYPE_COLORS : TYPE_COLORS_LIGHT;
  return map[type] || map.module;
}

// Language icons/colors
const LANG_COLORS: Record<string, string> = {
  swift: "#F05138",
  python: "#3776AB",
  rust: "#DEA584",
  typescript: "#3178C6",
  javascript: "#F7DF1E",
  go: "#00ADD8",
  java: "#ED8B00",
  kotlin: "#7F52FF",
  ruby: "#CC342D",
  cpp: "#00599C",
  c: "#A8B9CC",
  csharp: "#512BD4",
  dart: "#0175C2",
  html: "#E34F26",
  css: "#1572B6",
  shell: "#89E051",
};

export function getLanguageColor(lang: string): string {
  return LANG_COLORS[lang] || "#6B7280";
}

// Format bytes to human readable
export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

// Format number with commas
export function formatNumber(n: number): string {
  return n.toLocaleString();
}

// Relationship type to edge style
const EDGE_STYLES: Record<string, { color: string; animated: boolean; dash: string }> = {
  import: { color: "#6B7280", animated: false, dash: "" },
  http: { color: "#3B82F6", animated: true, dash: "" },
  websocket: { color: "#8B5CF6", animated: true, dash: "5 5" },
  grpc: { color: "#10B981", animated: true, dash: "" },
  ffi: { color: "#F59E0B", animated: false, dash: "3 3" },
  database: { color: "#EC4899", animated: false, dash: "" },
  file: { color: "#6B7280", animated: false, dash: "8 4" },
};

export function getEdgeStyle(type: string) {
  return EDGE_STYLES[type] || EDGE_STYLES.import;
}
