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
import { getLayoutedElements, getEdgeStyle } from "../utils/layout";

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

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { fitView } = useReactFlow();
  const layoutTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

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
      .filter((r) => nodeIds.has(r.source) && nodeIds.has(r.target))
      .map((r, i) => {
        const style = getEdgeStyle(r.type);
        return {
          id: `e-${r.source}-${r.target}-${i}`,
          source: r.source,
          target: r.target,
          type: "smoothstep",
          animated: style.animated,
          label: r.label || undefined,
          labelStyle: { fill: darkMode ? "#9CA3AF" : "#6B7280", fontSize: 11 },
          labelBgStyle: {
            fill: darkMode ? "#18181B" : "#FFFFFF",
            fillOpacity: 0.9,
          },
          style: {
            stroke: style.color,
            strokeDasharray: style.dash || undefined,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: style.color,
            width: 16,
            height: 16,
          },
        };
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

    getLayoutedElements(rawNodes, rawEdges, "RIGHT").then(({ nodes: ln, edges: le }) => {
      setNodes(ln);
      setEdges(le);
      // Delay fitView to allow rendering
      layoutTimeout.current = setTimeout(() => {
        fitView({ padding: 0.15, duration: 300 });
      }, 50);
    });

    return () => {
      if (layoutTimeout.current) clearTimeout(layoutTimeout.current);
    };
  }, [rawNodes, rawEdges, setNodes, setEdges, fitView]);

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
