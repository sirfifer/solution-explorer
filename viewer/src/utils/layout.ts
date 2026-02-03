import ELK from "elkjs/lib/elk.bundled.js";
import type { Node, Edge } from "@xyflow/react";

const elk = new ELK();

// Default sizes based on actual measured node dimensions
// Largest nodes are ~360x230, so use that plus margin
const DEFAULT_NODE_WIDTH = 380;
const DEFAULT_NODE_HEIGHT = 250;

// Priority order for layout: mobile clients first (top-left), then other clients,
// then servers below them
const TYPE_PRIORITY: Record<string, number> = {
  "ios-client": 0,
  "android-client": 1,
  "mobile-client": 2,
  "watch-app": 3,
  "web-client": 4,
  "desktop-app": 5,
  "cli-tool": 6,
  "api-server": 10,
  "service": 11,
  // Everything else gets 20+
};

function getTypePriority(type: string): number {
  return TYPE_PRIORITY[type] ?? 20;
}

export async function getLayoutedElements(
  nodes: Node[],
  edges: Edge[],
  direction: "RIGHT" | "DOWN" = "DOWN",
): Promise<{ nodes: Node[]; edges: Edge[] }> {
  // Sort nodes by type priority for better initial layering
  const sortedNodes = [...nodes].sort((a, b) => {
    const aType = (a.data as { component?: { type?: string } })?.component?.type ?? "";
    const bType = (b.data as { component?: { type?: string } })?.component?.type ?? "";
    return getTypePriority(aType) - getTypePriority(bType);
  });

  const elkGraph = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": direction,
      // Large spacing to prevent overlaps and show relationships clearly
      "elk.spacing.nodeNode": "60",
      "elk.layered.spacing.nodeNodeBetweenLayers": "80",
      "elk.padding": "[top=40,left=40,bottom=40,right=40]",
      // Better edge routing for clearer relationship visualization
      "elk.layered.mergeEdges": "false",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
      "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
      // Consider node priorities for layer assignment - model order takes precedence
      "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
      "elk.layered.layering.strategy": "LONGEST_PATH_SOURCE",
      // Spread nodes more evenly
      "elk.layered.spacing.edgeNodeBetweenLayers": "40",
      "elk.layered.spacing.edgeEdgeBetweenLayers": "20",
      // Prevent overlap
      "elk.layered.compaction.postCompaction.strategy": "NONE",
    },
    children: sortedNodes.map((node, index) => ({
      id: node.id,
      width: node.measured?.width ?? DEFAULT_NODE_WIDTH,
      height: node.measured?.height ?? DEFAULT_NODE_HEIGHT,
      // Use index as layout priority (lower = higher in hierarchy)
      layoutOptions: {
        "elk.priority": String(sortedNodes.length - index),
      },
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
  repository: { bg: "bg-indigo-950/60", border: "border-indigo-500/50", text: "text-indigo-300", badge: "bg-indigo-500/20 text-indigo-300" },
  "mobile-client": { bg: "bg-orange-950/60", border: "border-orange-500/50", text: "text-orange-300", badge: "bg-orange-500/20 text-orange-300" },
  "ios-client": { bg: "bg-orange-950/60", border: "border-orange-500/50", text: "text-orange-300", badge: "bg-orange-500/20 text-orange-300" },
  "android-client": { bg: "bg-emerald-950/60", border: "border-emerald-500/50", text: "text-emerald-300", badge: "bg-emerald-500/20 text-emerald-300" },
  "web-client": { bg: "bg-sky-950/60", border: "border-sky-500/50", text: "text-sky-300", badge: "bg-sky-500/20 text-sky-300" },
  "api-server": { bg: "bg-green-950/60", border: "border-green-500/50", text: "text-green-300", badge: "bg-green-500/20 text-green-300" },
  "watch-app": { bg: "bg-pink-950/60", border: "border-pink-500/50", text: "text-pink-300", badge: "bg-pink-500/20 text-pink-300" },
  "desktop-app": { bg: "bg-teal-950/60", border: "border-teal-500/50", text: "text-teal-300", badge: "bg-teal-500/20 text-teal-300" },
  "cli-tool": { bg: "bg-lime-950/60", border: "border-lime-500/50", text: "text-lime-300", badge: "bg-lime-500/20 text-lime-300" },
  content: { bg: "bg-stone-950/60", border: "border-stone-600/30", text: "text-stone-500", badge: "bg-stone-500/20 text-stone-500" },
};

const TYPE_COLORS_LIGHT: Record<string, { bg: string; border: string; text: string; badge: string }> = {
  application: { bg: "bg-blue-50", border: "border-blue-300", text: "text-blue-700", badge: "bg-blue-100 text-blue-700" },
  service: { bg: "bg-emerald-50", border: "border-emerald-300", text: "text-emerald-700", badge: "bg-emerald-100 text-emerald-700" },
  library: { bg: "bg-violet-50", border: "border-violet-300", text: "text-violet-700", badge: "bg-violet-100 text-violet-700" },
  package: { bg: "bg-amber-50", border: "border-amber-300", text: "text-amber-700", badge: "bg-amber-100 text-amber-700" },
  module: { bg: "bg-cyan-50", border: "border-cyan-300", text: "text-cyan-700", badge: "bg-cyan-100 text-cyan-700" },
  infrastructure: { bg: "bg-rose-50", border: "border-rose-300", text: "text-rose-700", badge: "bg-rose-100 text-rose-700" },
  project: { bg: "bg-zinc-50", border: "border-zinc-300", text: "text-zinc-700", badge: "bg-zinc-100 text-zinc-700" },
  repository: { bg: "bg-indigo-50", border: "border-indigo-300", text: "text-indigo-700", badge: "bg-indigo-100 text-indigo-700" },
  "mobile-client": { bg: "bg-orange-50", border: "border-orange-300", text: "text-orange-700", badge: "bg-orange-100 text-orange-700" },
  "ios-client": { bg: "bg-orange-50", border: "border-orange-300", text: "text-orange-700", badge: "bg-orange-100 text-orange-700" },
  "android-client": { bg: "bg-emerald-50", border: "border-emerald-300", text: "text-emerald-700", badge: "bg-emerald-100 text-emerald-700" },
  "web-client": { bg: "bg-sky-50", border: "border-sky-300", text: "text-sky-700", badge: "bg-sky-100 text-sky-700" },
  "api-server": { bg: "bg-green-50", border: "border-green-300", text: "text-green-700", badge: "bg-green-100 text-green-700" },
  "watch-app": { bg: "bg-pink-50", border: "border-pink-300", text: "text-pink-700", badge: "bg-pink-100 text-pink-700" },
  "desktop-app": { bg: "bg-teal-50", border: "border-teal-300", text: "text-teal-700", badge: "bg-teal-100 text-teal-700" },
  "cli-tool": { bg: "bg-lime-50", border: "border-lime-300", text: "text-lime-700", badge: "bg-lime-100 text-lime-700" },
  content: { bg: "bg-stone-50", border: "border-stone-200", text: "text-stone-400", badge: "bg-stone-100 text-stone-400" },
};

export function getTypeColors(type: string, dark: boolean = true) {
  const map = dark ? TYPE_COLORS : TYPE_COLORS_LIGHT;
  return map[type] || map.module;
}

// Human-readable labels and icons for component types
export const TYPE_META: Record<string, { icon: string; label: string }> = {
  "mobile-client": { icon: "\u{1F4F1}", label: "Mobile Client" },
  "ios-client": { icon: "\u{1F34F}", label: "iOS Client" },
  "android-client": { icon: "\u{1F916}", label: "Android Client" },
  "web-client": { icon: "\u{1F310}", label: "Web Client" },
  "api-server": { icon: "\u2699\uFE0F", label: "API Server" },
  "watch-app": { icon: "\u231A", label: "Watch App" },
  "desktop-app": { icon: "\u{1F5A5}\uFE0F", label: "Desktop App" },
  "cli-tool": { icon: ">_", label: "CLI Tool" },
  content: { icon: "\u{1F4C4}", label: "Content" },
  service: { icon: "\u{1F527}", label: "Service" },
  library: { icon: "\u{1F4DA}", label: "Library" },
  package: { icon: "\u{1F4E6}", label: "Package" },
  module: { icon: "\u{1F9E9}", label: "Module" },
  infrastructure: { icon: "\u2601\uFE0F", label: "Infrastructure" },
  repository: { icon: "\u{1F4C2}", label: "Repository" },
  application: { icon: "\u{1F4E6}", label: "Application" },
  project: { icon: "\u{1F4C1}", label: "Project" },
};

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

// Format a timestamp as relative time (e.g., "2 hours ago", "3 days ago")
export function formatRelativeTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString();
}

// Edge categories: "communication" edges carry runtime data, "structural" edges
// represent code-level or organizational relationships (imports, FFI, companions).
export type EdgeCategory = "communication" | "structural";

export function getEdgeCategory(type: string): EdgeCategory {
  if (["http", "websocket", "grpc", "database", "file"].includes(type)) {
    return "communication";
  }
  return "structural";
}

// Relationship type to edge style
// Communication edges: colored, animated, solid lines with arrows
// Structural edges: gray, not animated, dashed to clearly differentiate
const EDGE_STYLES: Record<string, { color: string; animated: boolean; dash: string; strokeWidth: number }> = {
  import:    { color: "#6B7280", animated: false, dash: "6 4",  strokeWidth: 1.2 },
  http:      { color: "#3B82F6", animated: true,  dash: "",     strokeWidth: 2 },
  websocket: { color: "#8B5CF6", animated: true,  dash: "",     strokeWidth: 2 },
  grpc:      { color: "#10B981", animated: true,  dash: "",     strokeWidth: 2 },
  ffi:       { color: "#F59E0B", animated: false, dash: "4 3",  strokeWidth: 1.2 },
  database:  { color: "#EC4899", animated: true,  dash: "",     strokeWidth: 2 },
  file:      { color: "#6B7280", animated: true,  dash: "8 4",  strokeWidth: 1.5 },
};

export function getEdgeStyle(type: string) {
  return EDGE_STYLES[type] || EDGE_STYLES.import;
}

// Compute the best handle pair for an edge based on relative node positions.
// Returns { sourceHandle, targetHandle } IDs matching the handles on ComponentNode.
export function computeOptimalHandles(
  sourcePos: { x: number; y: number },
  sourceSize: { width: number; height: number },
  targetPos: { x: number; y: number },
  targetSize: { width: number; height: number },
): { sourceHandle: string; targetHandle: string } {
  // Compute center points
  const sx = sourcePos.x + sourceSize.width / 2;
  const sy = sourcePos.y + sourceSize.height / 2;
  const tx = targetPos.x + targetSize.width / 2;
  const ty = targetPos.y + targetSize.height / 2;

  const dx = tx - sx;
  const dy = ty - sy;

  // Determine predominant direction from source to target
  // Use node sizes to add a margin so we prefer horizontal when nodes are side-by-side
  const absDx = Math.abs(dx);
  const absDy = Math.abs(dy);

  let sourceHandle: string;
  let targetHandle: string;

  if (absDx >= absDy) {
    // Horizontal relationship
    if (dx >= 0) {
      sourceHandle = "source-right";
      targetHandle = "target-left";
    } else {
      sourceHandle = "source-left";
      targetHandle = "target-right";
    }
  } else {
    // Vertical relationship
    if (dy >= 0) {
      sourceHandle = "source-bottom";
      targetHandle = "target-top";
    } else {
      sourceHandle = "source-top";
      targetHandle = "target-bottom";
    }
  }

  return { sourceHandle, targetHandle };
}

// "Hero" component types: key architectural building blocks that should stand out visually
export const HERO_TYPES = new Set([
  "api-server",
  "mobile-client",
  "ios-client",
  "android-client",
  "web-client",
  "watch-app",
  "desktop-app",
  "cli-tool",
  "service",
  "application",
]);

export function isHeroType(type: string): boolean {
  return HERO_TYPES.has(type);
}

// Domain 1: Human-facing client types (always top-level)
// Each backed by concrete framework/manifest detection in the analyzer.
export const CLIENT_TYPES = new Set([
  "mobile-client",
  "ios-client",
  "android-client",
  "web-client",
  "watch-app",
  "desktop-app",
  "cli-tool",
]);

// Domain 2 candidates: Server types that may be top-level if a client depends on them
export const SERVER_TYPES = new Set([
  "api-server",
  "service",
]);

export function isClientType(type: string): boolean {
  return CLIENT_TYPES.has(type);
}

export function isServerType(type: string): boolean {
  return SERVER_TYPES.has(type);
}

// Glow colors for hero types (used for box-shadow)
const HERO_GLOW: Record<string, { dark: string; light: string }> = {
  "mobile-client": { dark: "rgba(249,115,22,0.18)", light: "rgba(249,115,22,0.14)" },
  "ios-client": { dark: "rgba(249,115,22,0.18)", light: "rgba(249,115,22,0.14)" },
  "android-client": { dark: "rgba(16,185,129,0.18)", light: "rgba(16,185,129,0.14)" },
  "web-client": { dark: "rgba(14,165,233,0.18)", light: "rgba(14,165,233,0.14)" },
  "api-server": { dark: "rgba(34,197,94,0.18)", light: "rgba(34,197,94,0.14)" },
  "watch-app": { dark: "rgba(236,72,153,0.18)", light: "rgba(236,72,153,0.14)" },
  "desktop-app": { dark: "rgba(20,184,166,0.18)", light: "rgba(20,184,166,0.14)" },
  "cli-tool": { dark: "rgba(132,204,22,0.18)", light: "rgba(132,204,22,0.14)" },
  service: { dark: "rgba(16,185,129,0.18)", light: "rgba(16,185,129,0.14)" },
  application: { dark: "rgba(59,130,246,0.18)", light: "rgba(59,130,246,0.14)" },
};

export function getHeroGlow(type: string, dark: boolean): string {
  const glow = HERO_GLOW[type];
  if (!glow) return "none";
  const color = dark ? glow.dark : glow.light;
  return `0 0 24px 4px ${color}`;
}
