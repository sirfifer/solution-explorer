import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
  type NodeTypes,
  MarkerType,
  Panel,
} from "@xyflow/react";
import { useArchStore } from "../store";
import { ComponentNode } from "./ComponentNode";
import { AggregateNode } from "./AggregateNode";
import { getLayoutedElements, getEdgeStyle, getEdgeCategory, computeOptimalHandles, getHeatColor } from "../utils/layout";
import { getLens, capabilityCountsByComponent, type CapabilityKindCounts } from "../lenses";
import type { Relationship } from "../types";

const nodeTypes: NodeTypes = {
  component: ComponentNode,
  aggregate: AggregateNode,
};

export function ArchitectureGraph() {
  const {
    architecture,
    loading,
    drillLevel,
    selectedComponentId,
    breadcrumbs,
    darkMode,
    expandedAggregates,
    lens,
    flowEntryId,
    flowStep,
    getFlowPath,
    activityData,
    selectedCapabilityId,
    selectedEntityId,
    getLensGraph,
    selectComponent,
    navigateToBreadcrumb,
    drillUp,
    setMobileChromeHidden,
  } = useArchStore();

  const [nodes, setNodes, onNodesChangeBase] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { fitView, setCenter, getNodes, getEdges } = useReactFlow();
  const layoutTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chromeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMobileRef = useRef(false);
  // Monotonic layout generation. Each layout run captures the current value;
  // when its async ELK promise resolves it applies results only if it is still
  // the latest run, so a slow older layout cannot overwrite a newer one after
  // rapid drill navigation (F-VW-7).
  const layoutGenRef = useRef(0);
  // Bumped whenever a layout is actually applied. The selection-centering effect
  // depends on it so it re-runs after ELK resolves instead of centering on
  // pre-layout grid positions during a URL deep-link restore (F-VW-7).
  const [layoutVersion, setLayoutVersion] = useState(0);

  // Track if we're on a mobile viewport
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)");
    isMobileRef.current = mq.matches;
    const handler = (e: MediaQueryListEvent) => { isMobileRef.current = e.matches; };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  // Auto-hide chrome on mobile when graph is being panned/zoomed
  const onMoveStart = useCallback(() => {
    if (!isMobileRef.current) return;
    if (chromeTimer.current) clearTimeout(chromeTimer.current);
    setMobileChromeHidden(true);
  }, [setMobileChromeHidden]);

  const onMoveEnd = useCallback(() => {
    if (!isMobileRef.current) return;
    chromeTimer.current = setTimeout(() => {
      setMobileChromeHidden(false);
    }, 2000);
  }, [setMobileChromeHidden]);

  useEffect(() => {
    return () => { if (chromeTimer.current) clearTimeout(chromeTimer.current); };
  }, []);

  // Wrap onNodesChange to recompute edge handles when nodes are dragged
  const onNodesChange = useCallback(
    (changes: Parameters<typeof onNodesChangeBase>[0]) => {
      onNodesChangeBase(changes);

      // If any position changes occurred, recompute handles
      const hasDrag = changes.some((c) => c.type === "position" && c.position);
      if (hasDrag) {
        // Use getNodes to get current positions after the change is applied
        requestAnimationFrame(() => {
          const currentNodes = getNodes();
          const nodeMap = new Map(currentNodes.map((n) => [n.id, n]));
          setEdges((eds) =>
            eds.map((edge) => {
              const sourceNode = nodeMap.get(edge.source);
              const targetNode = nodeMap.get(edge.target);
              if (sourceNode && targetNode) {
                const { sourceHandle, targetHandle } = computeOptimalHandles(
                  sourceNode.position,
                  { width: sourceNode.measured?.width ?? 280, height: sourceNode.measured?.height ?? 140 },
                  targetNode.position,
                  { width: targetNode.measured?.width ?? 280, height: targetNode.measured?.height ?? 140 },
                );
                if (edge.sourceHandle !== sourceHandle || edge.targetHandle !== targetHandle) {
                  return { ...edge, sourceHandle, targetHandle };
                }
              }
              return edge;
            }),
          );
        });
      }
    },
    [onNodesChangeBase, getNodes, setEdges],
  );

  // Build nodes and edges from visible components
  const { rawNodes, rawEdges } = useMemo(() => {
    if (!architecture) return { rawNodes: [], rawEdges: [] };

    // The active lens selects the nodes and edges; Structure returns exactly the
    // existing selectors so old data renders identically (P6-1).
    const { nodes: visible, aggregates, edges: relationships } = getLensGraph();

    // Per-lens node encodings, each gated to its own lens so Structure and every
    // other lens render identically.
    // Flow lens (P6-2): ring the entry node and the current follow step so the
    // walk reads spatially.
    const flowEntryNodeId = lens === "flow" ? flowEntryId : null;
    let flowStepNodeId: string | null = null;
    if (lens === "flow" && flowEntryId) {
      const path = getFlowPath(flowEntryId);
      flowStepNodeId = path[Math.min(flowStep, path.length - 1)] ?? null;
    }
    // Activity lens (P6-5): encode each node's hotspot score as a heat ring,
    // normalized against the max score so colors match the ActivityPanel ranking.
    const heatByComponent = new Map<string, number>();
    if (lens === "activity" && activityData) {
      const maxScore = activityData.components.reduce(
        (m, c) => Math.max(m, c.hotspot_score),
        0,
      );
      for (const c of activityData.components) {
        heatByComponent.set(c.id, maxScore > 0 ? c.hotspot_score / maxScore : 0);
      }
    }
    // Capability lens (P6-3): per-node capability counts by kind, rendered as a
    // badge cluster by ComponentNode. Only owner components carry counts.
    const capCounts =
      lens === "capability"
        ? capabilityCountsByComponent(architecture.capabilities ?? [])
        : null;
    // Data lens (P6-3): the focused entity's owner is the hub of the ego view;
    // ring it so the "who touches this data" center reads spatially.
    let dataOwnerNodeId: string | null = null;
    if (lens === "data" && selectedEntityId) {
      const ent = (architecture.data_entities ?? []).find((e) => e.id === selectedEntityId);
      dataOwnerNodeId = ent?.component_id ?? null;
    }

    const componentNodes: Node[] = visible.map((comp, i) => {
      const node: Node = {
        id: comp.id,
        type: "component",
        position: { x: (i % 4) * 320, y: Math.floor(i / 4) * 200 },
        data: { component: comp },
        selected: comp.id === selectedComponentId,
      };
      const heat = heatByComponent.get(comp.id);
      if (heat !== undefined) {
        node.data = { component: comp, heat };
        node.style = { boxShadow: `0 0 0 3px ${getHeatColor(heat)}`, borderRadius: 14 };
      }
      // Capability lens: attach per-kind capability counts for the badge cluster.
      const caps: CapabilityKindCounts | undefined = capCounts?.get(comp.id);
      if (caps) {
        node.data = { ...node.data, capBadges: caps };
      }
      if (comp.id === flowStepNodeId) {
        node.style = { boxShadow: "0 0 0 3px #2DD4BF", borderRadius: 14 };
      } else if (comp.id === flowEntryNodeId) {
        node.style = { boxShadow: "0 0 0 3px #818CF8", borderRadius: 14 };
      } else if (comp.id === dataOwnerNodeId) {
        // Ring the ego-view hub (the entity's owning component) under the Data lens.
        node.style = { boxShadow: "0 0 0 3px #818CF8", borderRadius: 14 };
      }
      return node;
    });

    // Aggregate nodes make the small internal modules the hero filter would hide
    // visible and expandable in place (P6-4). They carry no edges (their members
    // are collapsed); expanding one promotes its members into real component
    // nodes with their normal edges.
    const aggregateNodes: Node[] = aggregates.map((agg, i) => {
      const idx = componentNodes.length + i;
      return {
        id: agg.id,
        type: "aggregate",
        position: { x: (idx % 4) * 320, y: Math.floor(idx / 4) * 200 },
        data: { aggregate: agg },
        selectable: false,
      };
    });

    const newNodes = [...componentNodes, ...aggregateNodes];
    const nodeIds = new Set(newNodes.map((n) => n.id));
    const newEdges: Edge[] = relationships
      .filter((r: Relationship) => nodeIds.has(r.source) && nodeIds.has(r.target))
      .map((r: Relationship, i: number) => {
        const style = getEdgeStyle(r.type);
        const category = getEdgeCategory(r.type);

        // Build a descriptive label for the edge
        let edgeLabel = "";
        if (category === "communication") {
          const parts: string[] = [];
          if (r.protocol) parts.push(r.protocol);
          if (r.api_style && r.api_style !== r.protocol?.toLowerCase()) parts.push(r.api_style.toUpperCase());
          if (r.port) parts.push(`:${r.port}`);
          if (r.data_format && r.data_format !== "json") parts.push(`[${r.data_format}]`);
          if (r.authentication) parts.push(`\u{1F512}${r.authentication}`);
          if (parts.length > 0) {
            edgeLabel = parts.join(" ");
          } else if (r.label) {
            edgeLabel = r.label;
          }
          // For message queues, show topic/queue name
          if (r.queue_name) {
            edgeLabel = edgeLabel ? `${edgeLabel} (${r.queue_name})` : r.queue_name;
          }
        } else {
          // Structural edges get a simpler label
          if (r.label && r.label !== r.type) {
            edgeLabel = r.label;
          }
        }
        // AI-enhanced: use data flow description as fallback label
        if (!edgeLabel && r.ai_enhance?.data_flow_description) {
          edgeLabel = r.ai_enhance.data_flow_description;
        }

        // Structural edges use a lighter, thinner marker style
        const markerSize = category === "communication" ? 16 : 12;

        const edge: Edge = {
          id: `e-${r.source}-${r.target}-${i}`,
          source: r.source,
          target: r.target,
          type: "smoothstep",
          animated: style.animated,
          label: edgeLabel || undefined,
          labelStyle: {
            fill: darkMode ? "#9CA3AF" : "#6B7280",
            fontSize: category === "communication" ? 11 : 10,
            fontFamily: category === "communication" ? "ui-monospace, monospace" : undefined,
          },
          labelBgStyle: {
            fill: darkMode ? "#18181B" : "#FFFFFF",
            fillOpacity: 0.9,
          },
          style: {
            stroke: style.color,
            strokeDasharray: style.dash || undefined,
            strokeWidth: style.strokeWidth,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: style.color,
            width: markerSize,
            height: markerSize,
          },
        };

        // Bidirectional edges get an arrow on both ends
        if (r.bidirectional) {
          edge.markerStart = {
            type: MarkerType.ArrowClosed,
            color: style.color,
            width: markerSize,
            height: markerSize,
          };
        }

        // AI-discovered relationships get a distinct dashed style
        if (r.ai_enhance?.ai_discovered) {
          edge.style = {
            ...edge.style,
            strokeDasharray: "8 4",
            opacity: 0.7,
          };
        }

        return edge;
      });

    return { rawNodes: newNodes, rawEdges: newEdges };
  }, [architecture, drillLevel, selectedComponentId, darkMode, expandedAggregates, lens, flowEntryId, flowStep, getFlowPath, activityData, selectedCapabilityId, selectedEntityId, getLensGraph]);

  // Apply ELK layout
  useEffect(() => {
    if (rawNodes.length === 0) {
      setNodes([]);
      setEdges([]);
      // Don't return early — let the empty-state panel render below
    }

    // Clear any pending layout
    if (layoutTimeout.current) {
      clearTimeout(layoutTimeout.current);
    }

    // Stamp this layout run so a stale resolution can be discarded below.
    const myGen = ++layoutGenRef.current;

    // The active lens chooses the layout direction: Structure lays out top-down,
    // the Flow lens left-to-right for a walkable diagram (P6-2). Default "DOWN".
    const direction = getLens(lens)?.layoutDirection ?? "DOWN";

    getLayoutedElements(rawNodes, rawEdges, direction).then(({ nodes: ln, edges: le }) => {
      // Discard a stale layout: a newer run superseded this one while ELK was
      // computing (rapid drill navigation), so its positions are obsolete.
      if (myGen !== layoutGenRef.current) return;

      // Build a position map for optimal handle computation
      const nodeMap = new Map(ln.map((n) => [n.id, n]));

      // Assign optimal handles to each edge based on relative node positions
      const edgesWithHandles = le.map((edge) => {
        const sourceNode = nodeMap.get(edge.source);
        const targetNode = nodeMap.get(edge.target);
        if (sourceNode && targetNode) {
          const { sourceHandle, targetHandle } = computeOptimalHandles(
            sourceNode.position,
            { width: sourceNode.measured?.width ?? 280, height: sourceNode.measured?.height ?? 140 },
            targetNode.position,
            { width: targetNode.measured?.width ?? 280, height: targetNode.measured?.height ?? 140 },
          );
          return { ...edge, sourceHandle, targetHandle };
        }
        return edge;
      });

      setNodes(ln);
      setEdges(edgesWithHandles);
      // Signal that a fresh layout landed so the selection-centering effect can
      // re-run against real positions.
      setLayoutVersion((v) => v + 1);
      // Delay fitView to allow rendering
      layoutTimeout.current = setTimeout(() => {
        fitView({ padding: 0.15, duration: 300 });
      }, 50);
    });

    return () => {
      if (layoutTimeout.current) clearTimeout(layoutTimeout.current);
    };
  }, [rawNodes, rawEdges, lens, setNodes, setEdges, fitView]);

  // Pan to selected node and highlight its neighbors
  useEffect(() => {
    if (!selectedComponentId) {
      // Reset all opacities
      setNodes((nds) => nds.map((n) => ({
        ...n,
        style: { ...n.style, opacity: 1, transition: "opacity 0.3s ease" },
      })));
      setEdges((eds) => eds.map((e) => ({
        ...e,
        style: { ...e.style, opacity: 1, transition: "opacity 0.3s ease" },
      })));
      return;
    }

    // Find selected node's current rendered position (after ELK layout)
    const currentNodes = getNodes();
    const selectedNode = currentNodes.find((n) => n.id === selectedComponentId);
    if (!selectedNode) return;

    // Pan to center on selected node
    const nodeWidth = selectedNode.measured?.width ?? 280;
    const nodeHeight = selectedNode.measured?.height ?? 140;
    setCenter(
      selectedNode.position.x + nodeWidth / 2,
      selectedNode.position.y + nodeHeight / 2,
      { duration: 400 },
    );

    // Compute neighbor set from current edges (read via getEdges to avoid dependency loop)
    const currentEdges = getEdges();
    const neighborIds = new Set<string>();
    const connectedEdgeIds = new Set<string>();
    currentEdges.forEach((e) => {
      if (e.source === selectedComponentId || e.target === selectedComponentId) {
        neighborIds.add(e.source);
        neighborIds.add(e.target);
        connectedEdgeIds.add(e.id);
      }
    });

    // Dim non-neighbors
    setNodes((nds) => nds.map((n) => ({
      ...n,
      style: {
        ...n.style,
        opacity: n.id === selectedComponentId || neighborIds.has(n.id) ? 1 : 0.15,
        transition: "opacity 0.3s ease",
      },
    })));

    // Dim non-connected edges, thicken connected ones
    setEdges((eds) => eds.map((e) => ({
      ...e,
      style: {
        ...e.style,
        opacity: connectedEdgeIds.has(e.id) ? 1 : 0.08,
        strokeWidth: connectedEdgeIds.has(e.id) ? 2.5 : undefined,
        transition: "opacity 0.3s ease",
      },
      animated: connectedEdgeIds.has(e.id) ? true : false,
    })));
    // layoutVersion: re-run once ELK has applied real positions so a deep-link
    // restore centers on the laid-out node, not its pre-layout grid slot (F-VW-7).
  }, [selectedComponentId, layoutVersion, getNodes, getEdges, setCenter, setNodes, setEdges]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      // Aggregate nodes handle their own expand/collapse (P6-4); they are not
      // selectable components, so do not route them through selectComponent.
      if (node.type === "aggregate") return;
      selectComponent(node.id);
    },
    [selectComponent],
  );

  const onPaneClick = useCallback(() => {
    selectComponent(null);
  }, [selectComponent]);

  return (
    <div className="w-full h-full relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        onMoveStart={onMoveStart}
        onMoveEnd={onMoveEnd}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.1}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        className={darkMode ? "dark" : "light"}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color={darkMode ? "#27272A" : "#E4E4E7"}
        />
        <Controls
          showInteractive={false}
          position="bottom-left"
        />
        <MiniMap
          position="bottom-right"
          pannable
          zoomable
          nodeColor={(node) => {
            const comp = (node.data as { component?: { type?: string } })?.component;
            const type = comp?.type || "module";
            const colorMap: Record<string, string> = {
              application: "#3B82F6",
              service: "#10B981",
              library: "#8B5CF6",
              package: "#F59E0B",
              module: "#06B6D4",
              infrastructure: "#F43F5E",
            };
            return colorMap[type] || "#6B7280";
          }}
          maskColor={darkMode ? "rgba(0,0,0,0.7)" : "rgba(255,255,255,0.7)"}
          style={{ height: 100, width: 150 }}
        />

        {/* Breadcrumb bar */}
        <Panel position="top-left">
          {breadcrumbs.length > 0 && (
            <div className={`
              flex items-center gap-1 px-3 py-2 rounded-xl text-sm
              ${darkMode ? "bg-zinc-900/90 border border-zinc-800" : "bg-white/90 border border-zinc-200"}
              backdrop-blur-sm shadow-lg
            `}>
              <button
                onClick={() => navigateToBreadcrumb(-1)}
                className={`px-2 py-0.5 rounded-md transition-colors ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-600"}`}
              >
                Home
              </button>
              {breadcrumbs.map((crumb, i) => (
                <span key={crumb.id} className="flex items-center gap-1">
                  <span className={darkMode ? "text-zinc-600" : "text-zinc-300"}>/</span>
                  {i < breadcrumbs.length - 1 ? (
                    <button
                      onClick={() => navigateToBreadcrumb(i)}
                      className={`px-2 py-0.5 rounded-md transition-colors ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-600"}`}
                    >
                      {crumb.name}
                    </button>
                  ) : (
                    <span className={`px-2 py-0.5 font-medium ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                      {crumb.name}
                    </span>
                  )}
                </span>
              ))}
              {drillLevel && (
                <button
                  onClick={drillUp}
                  className={`ml-2 px-2 py-0.5 rounded-md text-xs transition-colors ${darkMode ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-400" : "bg-zinc-100 hover:bg-zinc-200 text-zinc-600"}`}
                  title="Go up one level"
                >
                  &uarr; Up
                </button>
              )}
            </div>
          )}
        </Panel>

        {/* Empty state — shown when drill level has no visible components */}
        {nodes.length === 0 && !loading && (
          <Panel position="top-center">
            <div className={`
              mt-16 flex flex-col items-center gap-3 px-6 py-5 rounded-xl text-sm
              ${darkMode ? "bg-zinc-900/90 border border-zinc-800 text-zinc-400" : "bg-white/90 border border-zinc-200 text-zinc-600"}
              backdrop-blur-sm shadow-lg
            `}>
              <span className="text-2xl">📭</span>
              <p className="font-medium">No components to display at this level</p>
              <p className={`text-xs ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                This component may contain only files or data, not sub-components.
              </p>
              {drillLevel && (
                <button
                  onClick={drillUp}
                  className={`
                    mt-1 px-4 py-1.5 rounded-lg text-xs font-medium transition-colors
                    ${darkMode
                      ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
                      : "bg-zinc-100 hover:bg-zinc-200 text-zinc-700"
                    }
                  `}
                >
                  ↑ Go back up
                </button>
              )}
            </div>
          </Panel>
        )}
      </ReactFlow>
    </div>
  );
}
