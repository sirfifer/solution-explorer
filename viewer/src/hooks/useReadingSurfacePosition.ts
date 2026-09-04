import { useLayoutEffect, useState, type RefObject } from "react";
import { readingSurfacePlacement } from "../utils/readingSurfacePlacement";

export function useReadingSurfacePosition(
  trigger: RefObject<HTMLElement | null>,
  surface: RefObject<HTMLElement | null>,
  visible: boolean,
  preferred: "top" | "bottom",
  width: number,
  height = 420,
) {
  const [placement, setPlacement] = useState<ReturnType<typeof readingSurfacePlacement> | null>(null);
  useLayoutEffect(() => {
    if (!visible) return;
    const update = () => {
      if (!trigger.current || !surface.current) return;
      const next = readingSurfacePlacement(trigger.current.getBoundingClientRect(), {
        left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight,
      }, { width, height: Math.min(height, surface.current.scrollHeight + 2) }, preferred);
      setPlacement((previous) => previous && Object.keys(next).every(
        (key) => previous[key as keyof typeof next] === next[key as keyof typeof next],
      ) ? previous : next);
    };
    update();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(update) : null;
    if (trigger.current) observer?.observe(trigger.current);
    if (surface.current) observer?.observe(surface.current);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [trigger, surface, visible, preferred, width, height]);
  return placement;
}
