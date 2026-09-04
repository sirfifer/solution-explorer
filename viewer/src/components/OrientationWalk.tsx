import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { listAvailableLenses } from "../lenses";
import { applicableStops, domRect, highlightRect, placeCard, type Rect, type Size } from "../orientation/model";
import { WALK_STOPS, type WalkContext, type WalkStop } from "../orientation/stops";
import { announceOrientationShowcase } from "../orientation/showcase";
import { useArchStore } from "../store";
import type { Architecture, Publication } from "../types";
import { resolveChannel } from "../utils/channel";
import { buildOrientationFallback } from "../utils/orientation";
import { publicationDisplayName, publicationSubjectUrl } from "../utils/publication";
import { SYSCORPUS } from "../utils/product";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";

const DEFAULT_CARD_SIZE: Size = { width: 320, height: 220 };

interface AnchorMeasurement {
  stopId: string;
  anchorId: string;
  rect: Rect;
  originRect: Rect | null;
  originLabel: string | null;
}

function viewportSize(): Size {
  if (typeof window === "undefined") return { width: 1024, height: 768 };
  return { width: window.innerWidth, height: window.innerHeight };
}

export function buildWalkContext(
  architecture: Architecture,
  publication: Publication | null,
  width: number,
): WalkContext {
  const orientation = architecture.orientation ?? buildOrientationFallback(architecture);
  return {
    displayName: publicationDisplayName(publication, architecture.name),
    subjectUrl: publicationSubjectUrl(publication, architecture.repository),
    identitySummary: orientation.identity?.summary ?? orientation.identity?.statement ?? null,
    lensLabels: listAvailableLenses(architecture, resolveChannel()).map((lens) => lens.label),
    hasGuidedPaths: orientation.question_routes.some((route) => Boolean(route.target.tour_id)),
    isMobile: width < 640,
    isMac: typeof navigator !== "undefined" && navigator.platform.startsWith("Mac"),
  };
}

function visibleAnchor(testId: string): HTMLElement | null {
  const element = document.querySelector<HTMLElement>(`[data-testid="${testId}"]`);
  if (!element) return null;
  const bounds = element.getBoundingClientRect();
  const style = window.getComputedStyle(element);
  return bounds.width > 0
    && bounds.height > 0
    && style.display !== "none"
    && style.visibility !== "hidden"
    ? element
    : null;
}

function measuredAnchorRects(stop: WalkStop, element: HTMLElement): Pick<AnchorMeasurement, "rect" | "originRect" | "originLabel"> {
  const base = domRect(element.getBoundingClientRect());
  const showcaseId = stop.id === "your-tools"
    ? "theme-menu"
    : stop.id === "lenses"
      ? "lens-menu"
      : null;
  const showcase = showcaseId ? visibleAnchor(showcaseId) : null;
  if (!showcase) return { rect: base, originRect: null, originLabel: null };
  return {
    rect: domRect(showcase.getBoundingClientRect()),
    originRect: base,
    originLabel: stop.id === "your-tools" ? "Theme control" : "Lens control",
  };
}

function rectFromPosition(top: number, left: number, size: Size): Rect {
  return {
    top,
    left,
    width: size.width,
    height: size.height,
    right: left + size.width,
    bottom: top + size.height,
  };
}

function nearestStepIndex(previous: WalkStop | undefined, nextStops: WalkStop[]): number {
  if (!previous) return 0;
  const exact = nextStops.findIndex((stop) => stop.id === previous.id);
  if (exact >= 0) return exact;
  if (previous.id === "if-you-get-lost" || previous.id === "if-you-get-lost-mobile") {
    return Math.max(0, nextStops.length - 1);
  }
  const position = WALK_STOPS.findIndex((stop) => stop.id === previous.id);
  const nearest = nextStops
    .map((stop, index) => ({ index, distance: Math.abs(WALK_STOPS.indexOf(stop) - position) }))
    .sort((a, b) => a.distance - b.distance)[0];
  return nearest?.index ?? 0;
}

export function OrientationWalk() {
  const architecture = useArchStore((state) => state.architecture);
  const publication = useArchStore((state) => state.publication);
  const darkMode = useArchStore((state) => state.darkMode);
  const experienceMode = useArchStore((state) => state.experienceMode);
  const orientationOpen = useArchStore((state) => state.orientationOpen);
  const orientationStep = useArchStore((state) => state.orientationStep);
  const orientationNext = useArchStore((state) => state.orientationNext);
  const orientationPrev = useArchStore((state) => state.orientationPrev);
  const setOrientationStep = useArchStore((state) => state.setOrientationStep);
  const exitOrientation = useArchStore((state) => state.exitOrientation);
  const markOrientationSkipped = useArchStore((state) => state.markOrientationSkipped);
  const setExperienceMode = useArchStore((state) => state.setExperienceMode);
  const [viewport, setViewport] = useState(viewportSize);
  const [anchor, setAnchor] = useState<AnchorMeasurement | null>(null);
  const [cardSize, setCardSize] = useState(DEFAULT_CARD_SIZE);
  const [measuredCardRect, setMeasuredCardRect] = useState<Rect | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const resizeFrame = useRef<number | null>(null);
  const measurementFrame = useRef<number | null>(null);
  const mapReadyTimer = useRef<number | null>(null);
  const previousStops = useRef(applicableStops(WALK_STOPS, viewport.width));
  const previousFocus = useRef<HTMLElement | null>(null);

  const stops = useMemo(() => applicableStops(WALK_STOPS, viewport.width), [viewport.width]);
  const stop = stops[Math.min(orientationStep, Math.max(0, stops.length - 1))];
  const context = useMemo(
    () => architecture ? buildWalkContext(architecture, publication, viewport.width) : null,
    [architecture, publication, viewport.width],
  );

  useEffect(() => {
    const updateViewport = () => {
      if (resizeFrame.current !== null) cancelAnimationFrame(resizeFrame.current);
      resizeFrame.current = requestAnimationFrame(() => {
        const nextViewport = viewportSize();
        const nextStops = applicableStops(WALK_STOPS, nextViewport.width);
        const oldStop = previousStops.current[useArchStore.getState().orientationStep];
        const nextIndex = nearestStepIndex(oldStop, nextStops);
        if (useArchStore.getState().orientationOpen) setOrientationStep(nextIndex);
        previousStops.current = nextStops;
        setViewport(nextViewport);
      });
    };
    window.addEventListener("resize", updateViewport);
    return () => {
      window.removeEventListener("resize", updateViewport);
      if (resizeFrame.current !== null) cancelAnimationFrame(resizeFrame.current);
    };
  }, [setOrientationStep]);

  const measureAnchor: () => void = useCallback(() => {
    if (!orientationOpen || !stop || stop.surface !== experienceMode) return;
    if (stop.id === "the-map") {
      const graph = document.querySelector<HTMLElement>('[data-layout-pending="false"]');
      const renderedNode = graph?.querySelector<HTMLElement>(".react-flow__node");
      if (!renderedNode) {
        if (mapReadyTimer.current !== null) window.clearTimeout(mapReadyTimer.current);
        mapReadyTimer.current = window.setTimeout(measureAnchor, 100);
        return;
      }
    }
    const primary = visibleAnchor(stop.anchor);
    const fallback = stop.fallbackAnchor ? visibleAnchor(stop.fallbackAnchor) : null;
    const element = primary ?? fallback;
    if (!element) {
      if (import.meta.env.DEV) console.warn(`Orientation stop skipped because its anchor is unavailable: ${stop.id}`);
      markOrientationSkipped(stop.id);
      if (orientationStep >= stops.length - 1) exitOrientation("dismissed");
      else orientationNext();
      return;
    }
    if (stop.surface === "overview") {
      element.scrollIntoView({ behavior: "auto", block: context?.isMobile ? "start" : "center", inline: "nearest" });
    }
    if (measurementFrame.current !== null) cancelAnimationFrame(measurementFrame.current);
    measurementFrame.current = requestAnimationFrame(() => {
      measurementFrame.current = null;
      const settledPrimary = visibleAnchor(stop.anchor);
      const settledFallback = stop.fallbackAnchor ? visibleAnchor(stop.fallbackAnchor) : null;
      const settledElement = settledPrimary ?? settledFallback ?? element;
      setAnchor({
        stopId: stop.id,
        anchorId: settledPrimary ? stop.anchor : stop.fallbackAnchor ?? stop.anchor,
        ...measuredAnchorRects(stop, settledElement),
      });
      setViewport(viewportSize());
    });
  }, [context?.isMobile, experienceMode, exitOrientation, markOrientationSkipped, orientationNext, orientationOpen, orientationStep, stop, stops.length]);

  useEffect(() => {
    announceOrientationShowcase(orientationOpen ? stop?.id ?? null : null);
    return () => announceOrientationShowcase(null);
  }, [experienceMode, orientationOpen, stop?.id]);

  useEffect(() => {
    if (!orientationOpen || !stop) {
      setAnchor(null);
      setMeasuredCardRect(null);
      return;
    }
    if (stop.surface !== experienceMode) {
      setAnchor(null);
      setMeasuredCardRect(null);
      setExperienceMode(stop.surface);
      return;
    }
    setAnchor(null);
    setMeasuredCardRect(null);
    const frame = requestAnimationFrame(measureAnchor);
    return () => {
      cancelAnimationFrame(frame);
      if (measurementFrame.current !== null) cancelAnimationFrame(measurementFrame.current);
      if (mapReadyTimer.current !== null) {
        window.clearTimeout(mapReadyTimer.current);
        mapReadyTimer.current = null;
      }
    };
  }, [experienceMode, measureAnchor, orientationOpen, setExperienceMode, stop]);

  useEffect(() => {
    if (!orientationOpen) return;
    let frame: number | null = null;
    const handleScroll = () => {
      if (frame !== null) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        const element = anchor?.anchorId ? visibleAnchor(anchor.anchorId) : null;
        if (element) {
          setAnchor((current) => current && current.stopId === stop?.id
            ? { ...current, ...(stop ? measuredAnchorRects(stop, element) : {}) }
            : current);
        }
      });
    };
    window.addEventListener("scroll", handleScroll, true);
    return () => {
      window.removeEventListener("scroll", handleScroll, true);
      if (frame !== null) cancelAnimationFrame(frame);
    };
  }, [anchor?.anchorId, orientationOpen, stop?.id]);

  useLayoutEffect(() => {
    if (!orientationOpen || !anchor || anchor.stopId !== stop?.id) return;
    const element = visibleAnchor(anchor.anchorId);
    if (!element) return;
    const update = () => {
      setAnchor((current) => current && current.stopId === stop.id
        ? { ...current, ...measuredAnchorRects(stop, element) }
        : current);
    };
    const frame = requestAnimationFrame(update);
    if (typeof ResizeObserver === "undefined") return () => cancelAnimationFrame(frame);
    const observer = new ResizeObserver(update);
    observer.observe(element);
    const showcase = stop.id === "your-tools"
      ? visibleAnchor("theme-menu")
      : stop.id === "lenses"
        ? visibleAnchor("lens-menu")
        : null;
    if (showcase) observer.observe(showcase);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [anchor?.anchorId, anchor?.stopId, orientationOpen, stop?.id]);

  useLayoutEffect(() => {
    if (!cardRef.current || !orientationOpen) return;
    const update = () => {
      const bounds = cardRef.current?.getBoundingClientRect();
      if (!bounds?.width || !bounds.height) return;
      const nextRect = domRect(bounds);
      setCardSize((current) => Math.abs(current.width - bounds.width) < 1 && Math.abs(current.height - bounds.height) < 1
        ? current
        : { width: bounds.width, height: bounds.height });
      setMeasuredCardRect((current) => current
        && Math.abs(current.top - nextRect.top) < 1
        && Math.abs(current.left - nextRect.left) < 1
        && Math.abs(current.width - nextRect.width) < 1
        && Math.abs(current.height - nextRect.height) < 1
        ? current
        : nextRect);
    };
    update();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(update);
    observer.observe(cardRef.current);
    return () => observer.disconnect();
  }, [anchor?.rect, orientationOpen, orientationStep]);

  useEffect(() => {
    if (!orientationOpen || !anchor) return;
    const frame = requestAnimationFrame(() => {
      const primary = cardRef.current?.querySelector<HTMLElement>("[data-orientation-primary]");
      primary?.focus();
    });
    return () => cancelAnimationFrame(frame);
  }, [anchor, orientationOpen, orientationStep]);

  useEffect(() => {
    if (!orientationOpen) return;
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        exitOrientation("dismissed");
        return;
      }
      if (event.key !== "Tab" || !cardRef.current) return;
      const controls = [...cardRef.current.querySelectorAll<HTMLElement>("button:not(:disabled), [href], [tabindex]:not([tabindex='-1'])")];
      if (controls.length === 0) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("keydown", handleKey);
      previousFocus.current?.focus();
    };
  }, [exitOrientation, orientationOpen]);

  if (!orientationOpen || !architecture || !context || !stop || !anchor || anchor.stopId !== stop.id) return null;

  const isLast = orientationStep >= stops.length - 1;
  const isWelcome = stop.presentation === "welcome";
  const position = isWelcome
    ? {
        top: Math.max(12, (viewport.height - cardSize.height) / 2),
        left: Math.max(12, (viewport.width - cardSize.width) / 2),
      }
    : placeCard(anchor.rect, cardSize, viewport, stop.placement);
  const computedCardRect = isWelcome
    ? rectFromPosition(position.top, position.left, cardSize)
    : context.isMobile
      ? rectFromPosition(viewport.height - cardSize.height, 0, { width: viewport.width, height: cardSize.height })
      : rectFromPosition(position.top, position.left, cardSize);
  const highlight = isWelcome ? null : highlightRect(anchor.rect, viewport, measuredCardRect ?? computedCardRect);
  const originHighlight = isWelcome || !anchor.originRect
    ? null
    : highlightRect(anchor.originRect, viewport, measuredCardRect ?? computedCardRect, 3);

  return (
    <div
      data-testid="orientation-walk"
      data-stop={stop.id}
      data-anchor={anchor.anchorId}
      className="fixed inset-0 z-[60] overflow-hidden"
      onClick={() => exitOrientation("dismissed")}
    >
      {isWelcome ? (
        <div data-testid="orientation-welcome-backdrop" aria-hidden="true" className="pointer-events-none fixed inset-0 bg-black/60 backdrop-blur-[2px]" />
      ) : highlight && (
        <div
          data-testid="orientation-highlight"
          aria-hidden="true"
          className="pointer-events-none fixed rounded-[10px] border-2 border-cyan-400 transition-opacity duration-150 motion-reduce:transition-none"
          style={{
            top: highlight.top,
            left: highlight.left,
            width: highlight.width,
            height: highlight.height,
            boxShadow: "0 0 0 9999px rgba(0, 0, 0, 0.55)",
          }}
        />
      )}
      {originHighlight && anchor.originLabel && (
        <div
          data-testid="orientation-origin-highlight"
          aria-hidden="true"
          className="pointer-events-none fixed rounded-lg border-2 border-cyan-300 bg-cyan-400/15 shadow-[0_0_0_2px_rgba(34,211,238,0.3)]"
          style={{
            top: originHighlight.top,
            left: originHighlight.left,
            width: originHighlight.width,
            height: originHighlight.height,
          }}
        >
          <span data-testid="orientation-origin-label" className="absolute -top-6 right-0 whitespace-nowrap rounded bg-cyan-400 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-zinc-950 shadow">
            {anchor.originLabel}
          </span>
        </div>
      )}
      <div
        ref={cardRef}
        data-testid="orientation-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="orientation-card-label"
        onClick={(event) => event.stopPropagation()}
        className={`fixed flex flex-col overflow-y-auto border shadow-2xl transition-opacity duration-150 motion-reduce:transition-none ${isWelcome ? "max-h-[calc(100vh-2rem)] w-[calc(100vw-2rem)] max-w-lg rounded-2xl p-5 sm:p-6" : "max-h-[45vh] w-full rounded-t-2xl p-4 sm:max-h-[calc(100vh-1.5rem)] sm:w-80 sm:max-w-[calc(100vw-2rem)] sm:rounded-2xl"} ${darkMode ? "border-zinc-700 bg-zinc-950 text-zinc-100" : "border-zinc-200 bg-white text-zinc-900"}`}
        style={isWelcome ? { top: "50%", left: "50%", transform: "translate(-50%, -50%)" } : context.isMobile ? { bottom: 0, left: 0 } : { top: position.top, left: position.left }}
      >
        <div id="orientation-card-label">
          <div className="flex items-center justify-between gap-3">
            <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-500">{isWelcome ? "Project orientation" : "Show me around"}</span>
            <span data-testid="orientation-progress" className={`text-[11px] tabular-nums ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              Step {orientationStep + 1} of {stops.length}
            </span>
          </div>
          <h2 className={`mt-2 font-bold ${isWelcome ? "text-xl leading-tight sm:text-2xl" : "text-base"}`}>{stop.heading(context)}</h2>
        </div>
        {isWelcome && (
          <div data-testid="orientation-welcome-pair" className="mt-4 grid grid-cols-2 gap-2">
            {context.subjectUrl ? (
              <a
                data-testid="orientation-subject-link"
                href={context.subjectUrl}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Visit the official ${context.displayName} website (opens in a new tab)`}
                className={`group rounded-xl border p-3 transition hover:border-cyan-400 hover:text-cyan-500 ${darkMode ? "border-zinc-800 bg-zinc-900/70" : "border-zinc-200 bg-zinc-50"}`}
              >
                <span className="block text-[9px] font-semibold uppercase tracking-wider text-zinc-500">Project</span>
                <strong className="mt-1 flex items-center justify-between gap-2 text-sm"><span>{context.displayName}</span><span aria-hidden="true" className="text-cyan-500">↗</span></strong>
              </a>
            ) : (
              <div data-testid="orientation-subject" className={`rounded-xl border p-3 ${darkMode ? "border-zinc-800 bg-zinc-900/70" : "border-zinc-200 bg-zinc-50"}`}>
                <span className="block text-[9px] font-semibold uppercase tracking-wider text-zinc-500">Project</span>
                <strong className="mt-1 block text-sm">{context.displayName}</strong>
              </div>
            )}
            <a
              data-testid="orientation-syscorpus-link"
              href={SYSCORPUS.url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Visit the SysCorpus website (opens in a new tab)"
              className={`group rounded-xl border p-3 transition hover:border-cyan-400 ${darkMode ? "border-cyan-500/20 bg-cyan-500/5" : "border-cyan-200 bg-cyan-50"}`}
            >
              <span className="block text-[9px] font-semibold uppercase tracking-wider text-zinc-500">Presented by</span>
              <strong className="mt-1 flex items-center justify-between gap-2 text-sm text-cyan-500"><span>SysCorpus</span><span aria-hidden="true">↗</span></strong>
            </a>
          </div>
        )}
        <p className={`mt-3 ${isWelcome ? "text-[15px] leading-7" : "text-sm leading-6"} ${darkMode ? "text-zinc-300" : "text-zinc-600"}`}>{stop.body(context)}</p>
        <div className="mt-4 flex items-center gap-2">
          {orientationStep > 0 && (
            <button
              type="button"
              data-testid="orientation-back"
              onClick={orientationPrev}
              className={`min-h-11 rounded-lg px-3 py-2 text-xs font-medium sm:min-h-0 ${darkMode ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"}`}
            >
              Back
            </button>
          )}
          <span className="flex-1" />
          {isLast ? (
            <button
              type="button"
              data-testid="orientation-done"
              data-orientation-primary
              onClick={() => exitOrientation("done")}
              className="min-h-11 rounded-lg bg-cyan-500 px-3 py-2 text-xs font-bold text-zinc-950 hover:bg-cyan-400 sm:min-h-0"
            >
              Done
            </button>
          ) : (
            <>
              <button
                type="button"
                data-testid="orientation-exit"
                onClick={() => exitOrientation("dismissed")}
                title={TOOLTIP_COPY.orientation.dismiss}
                className={`min-h-11 rounded-lg px-3 py-2 text-xs font-medium sm:min-h-0 ${darkMode ? "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800"}`}
              >
                Skip
              </button>
              <button
                type="button"
                data-testid="orientation-next"
                data-orientation-primary
                onClick={orientationNext}
                className="min-h-11 rounded-lg bg-cyan-500 px-3 py-2 text-xs font-bold text-zinc-950 hover:bg-cyan-400 sm:min-h-0"
              >
                Next
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
