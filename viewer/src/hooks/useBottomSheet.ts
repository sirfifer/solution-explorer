import { useRef, useState, useCallback, useEffect } from "react";

export type SnapPoint = "peek" | "half" | "full";

// Heights in vh for each snap point
const SNAP_HEIGHTS: Record<SnapPoint, number> = {
  peek: 15, // ~100px on most phones
  half: 45,
  full: 90,
};

// Velocity threshold (px/ms) for fling gestures
const FLING_VELOCITY = 0.5;
// Minimum drag distance to register as intentional
const MIN_DRAG = 10;

interface UseBottomSheetOptions {
  onDismiss: () => void;
  initialSnap?: SnapPoint;
}

interface UseBottomSheetReturn {
  snap: SnapPoint;
  setSnap: (s: SnapPoint) => void;
  sheetHeight: number; // current height in vh
  isDragging: boolean;
  dragOffset: number; // px offset during drag (positive = dragging down)
  handlers: {
    onTouchStart: (e: React.TouchEvent) => void;
    onTouchMove: (e: React.TouchEvent) => void;
    onTouchEnd: (e: React.TouchEvent) => void;
  };
}

export function useBottomSheet({
  onDismiss,
  initialSnap = "peek",
}: UseBottomSheetOptions): UseBottomSheetReturn {
  const [snap, setSnap] = useState<SnapPoint>(initialSnap);
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState(0);

  const touchStartY = useRef(0);
  const touchStartTime = useRef(0);
  const currentSnap = useRef<SnapPoint>(initialSnap);

  // Keep ref in sync
  useEffect(() => {
    currentSnap.current = snap;
  }, [snap]);

  // Reset to initial snap when it changes (e.g., new component selected)
  useEffect(() => {
    setSnap(initialSnap);
  }, [initialSnap]);

  const snapToVh = useCallback((s: SnapPoint) => SNAP_HEIGHTS[s], []);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartY.current = e.touches[0].clientY;
    touchStartTime.current = Date.now();
    setIsDragging(true);
  }, []);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    const deltaY = e.touches[0].clientY - touchStartY.current;
    setDragOffset(deltaY);
  }, []);

  const onTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      setIsDragging(false);
      const deltaY = e.changedTouches[0].clientY - touchStartY.current;
      const elapsed = Date.now() - touchStartTime.current;
      const velocity = Math.abs(deltaY) / Math.max(elapsed, 1);

      setDragOffset(0);

      if (Math.abs(deltaY) < MIN_DRAG) return;

      const draggingDown = deltaY > 0;
      const isFling = velocity > FLING_VELOCITY;
      const snaps: SnapPoint[] = ["peek", "half", "full"];
      const currentIdx = snaps.indexOf(currentSnap.current);

      if (isFling) {
        // Fling gesture: jump one snap in the fling direction
        if (draggingDown) {
          if (currentIdx === 0) {
            // Fling down from peek = dismiss
            onDismiss();
            return;
          }
          setSnap(snaps[currentIdx - 1]);
        } else {
          if (currentIdx < snaps.length - 1) {
            setSnap(snaps[currentIdx + 1]);
          }
        }
      } else {
        // Slow drag: snap to nearest point based on where the sheet ended up
        const windowH = window.innerHeight;
        const currentHeightPx = (snapToVh(currentSnap.current) / 100) * windowH;
        const newHeightPx = currentHeightPx - deltaY;
        const newHeightVh = (newHeightPx / windowH) * 100;

        // If dragged below peek threshold, dismiss
        if (newHeightVh < SNAP_HEIGHTS.peek / 2) {
          onDismiss();
          return;
        }

        // Find closest snap point
        let closestSnap: SnapPoint = "peek";
        let closestDist = Infinity;
        for (const s of snaps) {
          const dist = Math.abs(SNAP_HEIGHTS[s] - newHeightVh);
          if (dist < closestDist) {
            closestDist = dist;
            closestSnap = s;
          }
        }
        setSnap(closestSnap);
      }
    },
    [onDismiss, snapToVh],
  );

  return {
    snap,
    setSnap,
    sheetHeight: SNAP_HEIGHTS[snap],
    isDragging,
    dragOffset,
    handlers: { onTouchStart, onTouchMove, onTouchEnd },
  };
}
