import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { computeOffsets, computeVisibleRange } from "../utils/virtual";

interface VirtualListProps<T> {
  items: T[];
  /** Fixed row height in pixels. */
  rowHeight: number;
  renderRow: (item: T, index: number) => ReactNode;
  getKey: (item: T, index: number) => string;
  overscan?: number;
  className?: string;
}

/**
 * A windowed list that renders only the rows in view (P6-4). Long detail-panel
 * lists (symbols can run into the thousands) stay responsive because the DOM
 * only ever holds the visible rows plus a small overscan. The windowing math is
 * pure and tested in utils/virtual.ts; this component supplies the scroll
 * container and viewport measurement. When the viewport height is unknown (for
 * example before layout, or in a non-layout test environment) it renders every
 * row, so nothing is hidden by a missing measurement.
 */
export function VirtualList<T>({
  items,
  rowHeight,
  renderRow,
  getKey,
  overscan = 6,
  className,
}: VirtualListProps<T>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setViewportHeight(el.clientHeight);
    update();
    let ro: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(update);
      ro.observe(el);
    }
    return () => ro?.disconnect();
  }, []);

  const offsets = useMemo(
    () => computeOffsets(items.map(() => rowHeight)),
    [items, rowHeight],
  );
  const range = useMemo(
    () => computeVisibleRange(offsets, scrollTop, viewportHeight, overscan),
    [offsets, scrollTop, viewportHeight, overscan],
  );

  const rows: ReactNode[] = [];
  for (let i = range.start; i < range.end; i++) {
    rows.push(
      <div
        key={getKey(items[i], i)}
        style={{ position: "absolute", top: offsets[i], left: 0, right: 0, height: rowHeight }}
      >
        {renderRow(items[i], i)}
      </div>,
    );
  }

  return (
    <div
      ref={containerRef}
      onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
      className={`relative overflow-y-auto ${className ?? ""}`}
    >
      <div style={{ height: range.totalHeight, position: "relative" }}>{rows}</div>
    </div>
  );
}
