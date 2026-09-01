import { BaseEdge, getSmoothStepPath, useStore, useViewport, type EdgeProps } from "@xyflow/react";

export interface ElkRouteData extends Record<string, unknown> {
  elkPath?: string;
  elkLabel?: { x: number; y: number; width: number; height: number };
}

// Below this point a 13px relationship label is under 7 effective pixels. It
// communicates no readable information and turns a Fit overview into texture;
// keep the collision-safe lane, then reveal its label as the user approaches
// Read scale.
const EDGE_LABEL_REVEAL_ZOOM = 0.55;

/**
 * Draw the route ELK actually solved instead of asking React Flow to invent a
 * second path after layout. That keeps label placement, bend points, and the
 * space ELK reserved around nodes in one coordinate system.
 */
export function ElkRoutedEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  label,
  labelStyle,
  labelShowBg,
  labelBgStyle,
  labelBgPadding,
  labelBgBorderRadius,
  style,
  markerStart,
  markerEnd,
  interactionWidth,
}: EdgeProps) {
  const route = data as ElkRouteData | undefined;
  const viewport = useViewport();
  const canvasWidth = useStore((state) => state.width);
  const canvasHeight = useStore((state) => state.height);
  const [fallbackPath, fallbackLabelX, fallbackLabelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });
  const labelBox = route?.elkLabel;
  const labelFitsCanvas = viewport.zoom >= EDGE_LABEL_REVEAL_ZOOM && (!labelBox || (
    (labelBox.x - labelBox.width / 2) * viewport.zoom + viewport.x >= 4
    && (labelBox.x + labelBox.width / 2) * viewport.zoom + viewport.x <= canvasWidth - 4
    && (labelBox.y - labelBox.height / 2) * viewport.zoom + viewport.y >= 4
    && (labelBox.y + labelBox.height / 2) * viewport.zoom + viewport.y <= canvasHeight - 4
  ));

  return (
    <BaseEdge
      id={id}
      path={route?.elkPath ?? fallbackPath}
      labelX={route?.elkLabel?.x ?? fallbackLabelX}
      labelY={route?.elkLabel?.y ?? fallbackLabelY}
      label={labelFitsCanvas ? label : undefined}
      labelStyle={labelStyle}
      labelShowBg={labelShowBg ?? Boolean(label)}
      labelBgStyle={labelBgStyle}
      labelBgPadding={labelBgPadding ?? [7, 5]}
      labelBgBorderRadius={labelBgBorderRadius ?? 4}
      style={style}
      markerStart={markerStart}
      markerEnd={markerEnd}
      interactionWidth={interactionWidth}
    />
  );
}
