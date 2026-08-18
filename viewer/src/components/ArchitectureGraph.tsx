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
  getNodesBounds,
  getViewportForBounds,
} from "@xyflow/react";
import { useArchStore, nodeBudgetForCanvas, READABLE_ZOOM } from "../store";
import { buildDegreeIndex } from "../utils/importance";
import {
  nextSnapState,
  pickSnapTarget,
  readViewport,
  readZoomForFit,
  FIT_PADDING,
  GRAPH_MAX_ZOOM,
  GRAPH_MIN_ZOOM,
  SNAP_DURATION_MS,
  type SnapState,
} from "../utils/snapZoom";
import { ComponentNode } from "./ComponentNode";
import { AggregateNode } from "./AggregateNode";
import { getLayoutedElements, getEdgeStyle, getEdgeCategory, computeOptimalHandles, getHeatColor } from "../utils/layout";
import { getLens, capabilityCountsByComponent, ruleCountsByComponent, type CapabilityKindCounts, type RuleKindCounts } from "../lenses";
import type { Component, Relationship } from "../types";

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
    lens,
    flowEntryId,
    flowStep,
    getFlowPath,
    activityData,
    selectedCapabilityId,
    selectedEntityId,
    selectedRuleId,
    getLensGraph,
    selectComponent,
    navigateToBreadcrumb,
    drillInto,
    drillUp,
    setMobileChromeHidden,
    setNodeBudget,
    shrinkNodeBudget,
    nodeBudget,
  } = useArchStore();

  const [nodes, setNodes, onNodesChangeBase] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { fitView, setCenter, setViewport, getNodes, getEdges, getViewport } = useReactFlow();
  // Measures the canvas so a selection can be tested for on-screen visibility.
  const containerRef = useRef<HTMLDivElement>(null);
  const layoutTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const readabilityTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chromeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMobileRef = useRef(false);
  // Double-tap snap zoom state (see utils/snapZoom and the gesture effect
  // below). pendingSnapRef survives a re-layout so a Read snap is not fitted
  // over; applySnapRef lets the layout effect re-apply it without taking the
  // snap callback as a dependency and re-running the layout.
  const pendingSnapRef = useRef<{ state: SnapState; at: number } | null>(null);
  const applySnapRef = useRef<(state: SnapState) => void>(() => {});
  // Monotonic layout generation. Each layout run captures the current value;
  // when its async ELK promise resolves it applies results only if it is still
  // the latest run, so a slow older layout cannot overwrite a newer one after
  // rapid drill navigation (F-VW-7).
  const layoutGenRef = useRef(0);
  // Bumped whenever a layout is actually applied. The selection-centering effect
  // depends on it so it re-runs after ELK resolves instead of centering on
  // pre-layout grid positions during a URL deep-link restore (F-VW-7).
  const [layoutVersion, setLayoutVersion] = useState(0);

  // Bounded retries for the readability loop, reset per level/lens so a level
  // that needed a small budget does not permanently constrain the next one.
  const shrinkTries = useRef(0);
  useEffect(() => {
    shrinkTries.current = 0;
    pendingSnapRef.current = null;
  }, [drillLevel, lens]);

  // The node budget follows the canvas the viewer actually has, remeasured
  // whenever it changes: opening the detail panel, resizing the window, or
  // rotating a phone all change how many nodes can render readably (owner
  // decision 2026-08-17: it must adjust to the view, not to a fixed number).
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => {
      const { width, height } = el.getBoundingClientRect();
      setNodeBudget(nodeBudgetForCanvas(width, height));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [setNodeBudget]);

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
    // Rules lens (P6-6): per-node rule counts by kind, rendered as a badge cluster
    // by ComponentNode (the Capability lens badge pattern). Only rule-owning
    // components carry counts.
    const ruleCounts =
      lens === "rules"
        ? ruleCountsByComponent(architecture.rules ?? [])
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
      // Rules lens: attach per-kind rule counts for the badge cluster.
      const rules: RuleKindCounts | undefined = ruleCounts?.get(comp.id);
      if (rules) {
        node.data = { ...node.data, ruleBadges: rules };
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
  }, [architecture, drillLevel, selectedComponentId, darkMode, nodeBudget, lens, flowEntryId, flowStep, getFlowPath, activityData, selectedCapabilityId, selectedEntityId, selectedRuleId, getLensGraph]);

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
        // A Read snap taken a moment ago has to survive the re-layout it may
        // have caused: the first tap of the pair deselects, which closes the
        // detail panel, which resizes the canvas and re-budgets the level. Fit
        // over the top of it and the double tap would look like it did nothing.
        const pending = pendingSnapRef.current;
        pendingSnapRef.current = null;
        if (pending && pending.state === "read" && Date.now() - pending.at < 1200) {
          applySnapRef.current("read");
        } else {
          fitView({ padding: FIT_PADDING, duration: SNAP_DURATION_MS });
        }
        // After the fit lands, check what the layout actually achieved. If the
        // level still had to render below a readable zoom, show fewer nodes
        // and let it lay out again; the extras stay reachable in the
        // aggregate's list. Bounded, and shrink-only, so it settles.
        readabilityTimeout.current = setTimeout(() => {
          if (getViewport().zoom >= READABLE_ZOOM) return;
          if (shrinkTries.current >= 3) return;
          if (shrinkNodeBudget()) shrinkTries.current += 1;
        }, 420);
      }, 50);
    });

    return () => {
      if (layoutTimeout.current) clearTimeout(layoutTimeout.current);
      if (readabilityTimeout.current) clearTimeout(readabilityTimeout.current);
    };
  }, [rawNodes, rawEdges, lens, setNodes, setEdges, fitView, getViewport, shrinkNodeBudget]);

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

    // Bring the selection into view, but ONLY when it is not already fully
    // visible. Re-centering on every selection moved a node the user had just
    // clicked out from under the cursor, so the second click of a double-click
    // (and the resulting dblclick) landed on the empty pane instead of the
    // node: the real cause of "double-click does not drill" and of the
    // general click-target flakiness (comprehension-study S5, verified by
    // event trace). Off-screen selections, which is what search results, tree
    // clicks, and deep links produce, still animate into view.
    const nodeWidth = selectedNode.measured?.width ?? 280;
    const nodeHeight = selectedNode.measured?.height ?? 140;
    const centerX = selectedNode.position.x + nodeWidth / 2;
    const centerY = selectedNode.position.y + nodeHeight / 2;
    const viewport = getViewport();
    const container = containerRef.current;
    let fullyVisible = false;
    if (container) {
      const { width, height } = container.getBoundingClientRect();
      // Node bounds in screen space under the current viewport transform.
      const left = selectedNode.position.x * viewport.zoom + viewport.x;
      const top = selectedNode.position.y * viewport.zoom + viewport.y;
      const right = left + nodeWidth * viewport.zoom;
      const bottom = top + nodeHeight * viewport.zoom;
      fullyVisible = left >= 0 && top >= 0 && right <= width && bottom <= height;
    }
    if (!fullyVisible) {
      setCenter(centerX, centerY, { duration: 400 });
    }

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

  // Where and when the last node click landed, in screen coordinates. Selecting
  // a node opens the detail panel, which shrinks the canvas (measured: 1184px
  // to 864px) and slides the node ~160px out from under a stationary cursor, so
  // the second press of a double-click lands on the empty pane and no native
  // dblclick ever reaches the node. Double-click is therefore detected from two
  // presses at the same screen point rather than from the browser's event
  // (comprehension-study S5).
  const lastNodeClickRef = useRef<{ id: string; x: number; y: number; t: number } | null>(null);

  const onNodeClick = useCallback(
    (event: React.MouseEvent, node: Node) => {
      // Aggregate nodes handle their own expand/collapse (P6-4); they are not
      // selectable components, so do not route them through selectComponent.
      if (node.type === "aggregate") return;
      lastNodeClickRef.current = {
        id: node.id,
        x: event.clientX,
        y: event.clientY,
        t: Date.now(),
      };
      selectComponent(node.id);
    },
    [selectComponent],
  );

  const onPaneClick = useCallback(() => {
    selectComponent(null);
  }, [selectComponent]);

  // Second press at the same screen point within the double-click window drills
  // the node the first press selected, wherever that press now lands. Capture
  // phase so it runs before the pane's deselect.
  // 500ms is the conventional OS/browser double-click threshold.
  const DOUBLE_CLICK_MS = 500;
  const DOUBLE_CLICK_SLOP_PX = 5;
  useEffect(() => {
    const onMouseDown = (event: MouseEvent) => {
      const last = lastNodeClickRef.current;
      if (!last) return;
      const stale = Date.now() - last.t > DOUBLE_CLICK_MS;
      const moved =
        Math.abs(event.clientX - last.x) > DOUBLE_CLICK_SLOP_PX ||
        Math.abs(event.clientY - last.y) > DOUBLE_CLICK_SLOP_PX;
      lastNodeClickRef.current = null;
      if (stale || moved) return;
      const node = getNodes().find((n) => n.id === last.id);
      const comp = (node?.data as { component?: Component } | undefined)?.component;
      if (!comp || (comp.children.length === 0 && comp.files.length === 0)) return;
      event.preventDefault();
      event.stopPropagation();
      drillInto(comp);
    };
    window.addEventListener("mousedown", onMouseDown, true);
    return () => window.removeEventListener("mousedown", onMouseDown, true);
  }, [drillInto, getNodes]);

  // Double-click drill at the React Flow level (comprehension-study S5). The
  // node div's own onDoubleClick is swallowed by the node wrapper's
  // drag/selection handling often enough that the tour-taught gesture read as
  // broken, and the default double-click ZOOM made it worse ("zooms instead
  // of drilling"). zoomOnDoubleClick is off below for the same reason.
  const onNodeDoubleClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (node.type === "aggregate") return;
      const comp = (node.data as { component?: Component })?.component;
      if (comp && (comp.children.length > 0 || comp.files.length > 0)) {
        drillInto(comp);
      }
    },
    [drillInto],
  );

  // ---------------------------------------------------------------------
  // Double-tap snap zoom (owner idea 2026-08-18)
  //
  // Fit shows the whole level; Read zooms to a size the labels can be read at
  // and centers on the most important component, because at that zoom not
  // everything fits. Heroes are never aggregated (owner decision 2026-08-18),
  // so on a phone Fit can be 0.23 zoom with ~46x29px nodes; this is the
  // "zooming has to be easy" half of that decision.
  // ---------------------------------------------------------------------

  // The viewport the current level fits in, computed rather than guessed, so
  // the toggle never depends on a magic zoom number.
  const fitZoomNow = useCallback(() => {
    const el = containerRef.current;
    if (!el) return null;
    const { width, height } = el.getBoundingClientRect();
    const all = getNodes();
    if (all.length === 0 || !(width > 0) || !(height > 0)) return null;
    const bounds = getNodesBounds(all);
    const vp = getViewportForBounds(
      bounds, width, height, GRAPH_MIN_ZOOM, GRAPH_MAX_ZOOM, FIT_PADDING,
    );
    return { zoom: vp.zoom, bounds, canvas: { width, height } };
  }, [getNodes]);

  const applySnap = useCallback((state: SnapState) => {
    const fit = fitZoomNow();
    if (!fit) return;
    if (state === "fit") {
      pendingSnapRef.current = null;
      fitView({ padding: FIT_PADDING, duration: SNAP_DURATION_MS });
      return;
    }
    const all = getNodes();
    const components = all
      .map((n) => (n.data as { component?: Component } | undefined)?.component)
      .filter((c): c is Component => Boolean(c));
    // Ranked by the same importance ordering that decided which components are
    // on the canvas at all (utils/importance), against the same relationship
    // set the store ranks with, so the two can never disagree.
    const degree = buildDegreeIndex(architecture?.relationships ?? []);
    const target = pickSnapTarget(components, degree);
    const node = target ? all.find((n) => n.id === target.id) : undefined;
    if (!node) {
      fitView({ padding: FIT_PADDING, duration: SNAP_DURATION_MS });
      return;
    }
    const rect = {
      x: node.position.x,
      y: node.position.y,
      width: node.measured?.width ?? 280,
      height: node.measured?.height ?? 140,
    };
    pendingSnapRef.current = { state: "read", at: Date.now() };
    setViewport(
      readViewport(rect, fit.bounds, fit.canvas, readZoomForFit(fit.zoom)),
      { duration: SNAP_DURATION_MS },
    );
  }, [architecture, fitView, fitZoomNow, getNodes, setViewport]);

  useEffect(() => { applySnapRef.current = applySnap; }, [applySnap]);

  const toggleSnap = useCallback(() => {
    const fit = fitZoomNow();
    if (!fit) return;
    applySnap(nextSnapState(getViewport().zoom, fit.zoom, readZoomForFit(fit.zoom)));
  }, [applySnap, fitZoomNow, getViewport]);

  // Detected the same way the node drill is (comprehension-study S5): two
  // presses at the same SCREEN POINT inside the double-click window, not the
  // browser's dblclick. The first tap deselects, which closes the detail panel
  // and slides the canvas ~160px sideways, so the second press can land on a
  // different element entirely and no dblclick ever fires. pointerdown covers
  // mouse and touch with one path; a pinch's second finger is not the primary
  // pointer and lands far away, so it is rejected twice over.
  const lastPaneDownRef = useRef<{ x: number; y: number; t: number } | null>(null);
  const swallowClickUntilRef = useRef(0);
  useEffect(() => {
    const NON_PANE = ".react-flow__node, .react-flow__edge, .react-flow__controls,"
      + " .react-flow__minimap, .react-flow__panel, button, a, input, select, textarea";
    const isPaneTarget = (target: EventTarget | null): boolean => {
      const el = target instanceof Element ? target : null;
      const container = containerRef.current;
      if (!el || !container || !container.contains(el)) return false;
      return Boolean(el.closest(".react-flow__pane")) && !el.closest(NON_PANE);
    };
    const near = (a: { x: number; y: number }, e: PointerEvent | MouseEvent) =>
      Math.abs(e.clientX - a.x) <= DOUBLE_CLICK_SLOP_PX
      && Math.abs(e.clientY - a.y) <= DOUBLE_CLICK_SLOP_PX;

    const onPointerDown = (event: PointerEvent) => {
      if (!event.isPrimary) return;
      const first = lastPaneDownRef.current;
      // The SECOND press only has to be at the same point in time and space.
      // Requiring it to land on the pane again would fail exactly when the
      // canvas moved under it, which is the case this detection exists for.
      if (first && Date.now() - first.t <= DOUBLE_CLICK_MS && near(first, event)) {
        lastPaneDownRef.current = null;
        swallowClickUntilRef.current = Date.now() + 400;
        event.preventDefault();
        event.stopPropagation();
        toggleSnap();
        return;
      }
      lastPaneDownRef.current = isPaneTarget(event.target)
        ? { x: event.clientX, y: event.clientY, t: Date.now() }
        : null;
    };
    // A pan is a press that travels. Drop the candidate so returning to the
    // start point later cannot be mistaken for the second half of a tap pair.
    const onPointerUp = (event: PointerEvent) => {
      const first = lastPaneDownRef.current;
      if (first && !near(first, event)) lastPaneDownRef.current = null;
    };
    // The press we swallowed above still produces a click; without this it
    // would select whatever node had slid under the second tap.
    const onClick = (event: MouseEvent) => {
      if (Date.now() > swallowClickUntilRef.current) return;
      swallowClickUntilRef.current = 0;
      event.preventDefault();
      event.stopPropagation();
    };
    window.addEventListener("pointerdown", onPointerDown, true);
    window.addEventListener("pointerup", onPointerUp, true);
    window.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown, true);
      window.removeEventListener("pointerup", onPointerUp, true);
      window.removeEventListener("click", onClick, true);
    };
  }, [toggleSnap]);

  return (
    <div ref={containerRef} className="w-full h-full relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onNodeDoubleClick={onNodeDoubleClick}
        onPaneClick={onPaneClick}
        onMoveStart={onMoveStart}
        onMoveEnd={onMoveEnd}
        nodeTypes={nodeTypes}
        zoomOnDoubleClick={false}
        // A node's drag behavior consumes the pointer events that would
        // otherwise become a native dblclick, which is why double-click drill
        // failed for a real mouse even with the handler wired
        // (comprehension-study S5; verified: a synthetic dblclick drilled, a
        // real one never fired). A few pixels of travel now separate a click
        // from a drag, so clicking is reliable and deliberate dragging still
        // works.
        nodeDragThreshold={5}
        fitView
        minZoom={GRAPH_MIN_ZOOM}
        maxZoom={GRAPH_MAX_ZOOM}
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
