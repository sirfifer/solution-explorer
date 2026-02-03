import { useCallback, useEffect, useMemo, useRef } from "react";
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
import { getLayoutedElements, getEdgeStyle, getEdgeCategory, computeOptimalHandles } from "../utils/layout";
import type { Relationship } from "../types";

const nodeTypes: NodeTypes = {
  component: ComponentNode,
};

export function ArchitectureGraph() {
  const {
    architecture,
    drillLevel,
    selectedComponentId,
    breadcrumbs,
    darkMode,
    getVisibleComponents,
    getComponentRelationships,
    selectComponent,
    navigateToBreadcrumb,
    drillUp,
  } = useArchStore();

  const [nodes, setNodes, onNodesChangeBase] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { fitView, setCenter, getNodes, getEdges } = useReactFlow();
  const layoutTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

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

    const visible = getVisibleComponents();
    const relationships = getComponentRelationships();

    const newNodes: Node[] = visible.map((comp, i) => ({
      id: comp.id,
      type: "component",
      position: { x: (i % 4) * 320, y: Math.floor(i / 4) * 200 },
      data: { component: comp },
      selected: comp.id === selectedComponentId,
    }));

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
          if (r.port) parts.push(`:${r.port}`);
          if (parts.length > 0) {
            edgeLabel = parts.join(" ");
          } else if (r.label) {
            edgeLabel = r.label;
          }
        } else {
          // Structural edges get a simpler label
          if (r.label && r.label !== r.type) {
            edgeLabel = r.label;
          }
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

        return edge;
      });

    return { rawNodes: newNodes, rawEdges: newEdges };
  }, [architecture, drillLevel, selectedComponentId, darkMode, getVisibleComponents, getComponentRelationships]);

  // Apply ELK layout
  useEffect(() => {
    if (rawNodes.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    // Clear any pending layout
    if (layoutTimeout.current) {
      clearTimeout(layoutTimeout.current);
    }

    getLayoutedElements(rawNodes, rawEdges, "DOWN").then(({ nodes: ln, edges: le }) => {
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
      // Delay fitView to allow rendering
      layoutTimeout.current = setTimeout(() => {
        fitView({ padding: 0.15, duration: 300 });
      }, 50);
    });

    return () => {
      if (layoutTimeout.current) clearTimeout(layoutTimeout.current);
    };
  }, [rawNodes, rawEdges, setNodes, setEdges, fitView]);

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
  }, [selectedComponentId, getNodes, getEdges, setCenter, setNodes, setEdges]);

  const onNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
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
      </ReactFlow>
    </div>
  );
}
