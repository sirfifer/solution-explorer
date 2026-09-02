import { useEffect, useState } from "react";
import { useArchStore } from "../store";
import { isTourStale, tourStepCount } from "../tours/model";
import { evidenceLabel } from "../findings/model";
import { Tooltip } from "./Tooltip";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";

// The guided-walkthrough player (P6-7, LENS-DESIGN L7). Two surfaces, one
// component:
//   - the TOUR LIST overlay (toursOpen, no active tour): tours in authored order
//     (I11) with step-count badges and a stale marker (I5);
//   - the docked STEP PANEL (a tour is active): the current step's narration with
//     next/previous/exit, a progress breadcrumb (I11 "where am I"), an evidence
//     link per step ("show me the code"), and a stale marker on the tour.
// Each step selects its target on stable identity (I12), handled by the store.
// Tours are a projection artifact (architecture.tours); no store table.

/**
 * Whether the step panel's narration and step list start open.
 *
 * The panel is 22rem wide and up to 70vh tall. On a desktop that sits in a
 * corner of a large canvas; on a phone it covered the whole diagram, so a tour
 * narrated a picture the reader could not see (GUI crawl 2026-09-01). Below the
 * sm breakpoint the panel is therefore a compact docked strip, capped so at
 * least 55% of the viewport stays with the canvas, and the prose is one tap
 * away on the header. Exported so the default is testable without a viewport.
 */
export function tourPanelStartsExpanded(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
  return window.matchMedia("(min-width: 640px)").matches;
}

function StaleMarker({ darkMode }: { darkMode: boolean }) {
  return (
    <Tooltip content={TOOLTIP_COPY.tours.stale}>
      <span
        data-testid="tour-stale-marker"
        className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${darkMode ? "bg-amber-500/15 text-amber-300" : "bg-amber-100 text-amber-700"}`}
      >
        {"⚠"} may be stale
      </span>
    </Tooltip>
  );
}

function InterpretationMarker({ darkMode }: { darkMode: boolean }) {
  return (
    <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${darkMode ? "bg-violet-500/15 text-violet-300" : "bg-violet-100 text-violet-700"}`}>
      guided interpretation
    </span>
  );
}

export function TourPlayer() {
  const darkMode = useArchStore((s) => s.darkMode);
  const toursOpen = useArchStore((s) => s.toursOpen);
  const activeTourId = useArchStore((s) => s.activeTourId);
  const tourStep = useArchStore((s) => s.tourStep);
  const getTours = useArchStore((s) => s.getTours);
  const getTourById = useArchStore((s) => s.getTourById);
  const startTour = useArchStore((s) => s.startTour);
  const tourStepNext = useArchStore((s) => s.tourStepNext);
  const tourStepPrev = useArchStore((s) => s.tourStepPrev);
  const tourGoToStep = useArchStore((s) => s.tourGoToStep);
  const exitTour = useArchStore((s) => s.exitTour);
  const closeTours = useArchStore((s) => s.closeTours);
  const openFileDeepLink = useArchStore((s) => s.openFileDeepLink);
  const [expanded, setExpanded] = useState(tourPanelStartsExpanded);

  const activeTour = activeTourId ? getTourById(activeTourId) : null;

  // Escape closes the list overlay, or exits an active tour.
  useEffect(() => {
    if (!toursOpen && !activeTour) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (activeTour) exitTour();
      else closeTours();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toursOpen, activeTour, exitTour, closeTours]);

  // ── The docked step panel (an active tour wins over the list) ──────────────
  if (activeTour) {
    const steps = activeTour.steps;
    const step = Math.min(tourStep, Math.max(0, steps.length - 1));
    const current = steps[step];
    const chipBtn = darkMode
      ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-40"
      : "bg-zinc-200 text-zinc-700 hover:bg-zinc-300 disabled:opacity-40";

    return (
      <div
        data-testid="tour-step-panel"
        data-tour-id={activeTour.id}
        data-step={step}
        data-step-count={steps.length}
        data-expanded={expanded}
        // Below sm this is a docked strip across the bottom, capped at 45vh so
        // at least 55% of the viewport stays with the diagram the narration is
        // about. From sm up it is the floating corner card it has always been.
        className={`fixed z-40 flex flex-col border shadow-2xl inset-x-0 bottom-0 max-h-[45vh] rounded-t-2xl sm:inset-x-auto sm:bottom-4 sm:left-4 sm:w-[22rem] sm:max-w-[calc(100vw-2rem)] sm:max-h-[70vh] sm:rounded-2xl ${
          darkMode ? "bg-zinc-950 border-zinc-800 text-zinc-200" : "bg-white border-zinc-200 text-zinc-800"
        }`}
      >
        {/* Header: tour title, stale marker, progress, exit. Tapping it opens
            and closes the narration and step list below, which is the whole
            mechanism on a phone; on a desktop it starts open and the tap is
            simply available. */}
        <div className={`shrink-0 px-4 pt-3 pb-2 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <div className="flex items-center gap-1.5">
            <div
              data-testid="tour-panel-toggle"
              role="button"
              tabIndex={0}
              aria-expanded={expanded}
              onClick={() => setExpanded((open) => !open)}
              onKeyDown={(e) => {
                if (e.key !== "Enter" && e.key !== " ") return;
                e.preventDefault();
                setExpanded((open) => !open);
              }}
              title={expanded ? "Hide the narration" : "Show the narration"}
              className="flex min-w-0 flex-1 cursor-pointer items-center gap-1.5 text-left"
            >
              <span>{"\u{1F5FA}️"}</span>
              <h2 className="text-sm font-bold truncate">{activeTour.title}</h2>
              {isTourStale(activeTour) && <StaleMarker darkMode={darkMode} />}
              {activeTour.statement_kind === "authored_interpretation" && <InterpretationMarker darkMode={darkMode} />}
              <span aria-hidden className={`ml-auto shrink-0 text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                {expanded ? "▾" : "▸"}
              </span>
            </div>
            <button
              type="button"
              data-testid="tour-exit"
              onClick={exitTour}
              className={`shrink-0 p-1 rounded ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-500"}`}
              title="Exit tour (Esc)"
            >
              {"✕"}
            </button>
          </div>
          {/* Progress breadcrumb (I11 "where am I") */}
          <p data-testid="tour-progress" className={`mt-0.5 text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            Step {step + 1} of {steps.length}
          </p>
        </div>

        {/* Body: current step narration + evidence. Always mounted, hidden while
            collapsed, so the step list and the evidence link stay in the DOM in
            both states and nothing that addresses them by name disappears. */}
        <div className={expanded ? "flex-1 overflow-y-auto px-4 py-3 space-y-3" : "hidden"}>
          <div>
            <div className={`text-sm font-semibold ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
              {current.title}
            </div>
            <p className={`mt-1 text-xs leading-relaxed ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
              {current.narration}
            </p>
            {current.verification_status === "unverified" && (
              <p className={`mt-2 text-[11px] leading-5 ${darkMode ? "text-violet-300" : "text-violet-700"}`}>
                Teaching narration anchored to source, not a verified runtime assertion.
              </p>
            )}
            {current.evidence?.file && (
              <button
                type="button"
                data-testid="tour-evidence-link"
                onClick={() => void openFileDeepLink(current.evidence!.file, current.evidence!.line ?? null)}
                className={`mt-2 font-mono text-[11px] ${darkMode ? "text-blue-400 hover:text-blue-300 hover:underline" : "text-blue-600 hover:text-blue-700 hover:underline"}`}
                title={`Open ${current.evidence.file}`}
              >
                {"</>"} {evidenceLabel({ file: current.evidence.file, line: current.evidence.line })}
              </button>
            )}
          </div>

          {/* Progress breadcrumb list: jump to any step */}
          <ol className="space-y-0.5">
            {steps.map((s, i) => {
              const isCurrent = i === step;
              const visited = i <= step;
              return (
                <li key={`${s.target}:${i}`}>
                  <button
                    type="button"
                    data-testid="tour-step-item"
                    data-step={i}
                    data-current={isCurrent}
                    onClick={() => tourGoToStep(i)}
                    className={`w-full flex items-center gap-2 px-2 py-1 rounded-md text-left text-[12px] ${
                      isCurrent
                        ? darkMode
                          ? "bg-teal-500/15 text-teal-300"
                          : "bg-teal-100 text-teal-800"
                        : visited
                          ? darkMode
                            ? "text-zinc-300 hover:bg-zinc-800"
                            : "text-zinc-700 hover:bg-zinc-100"
                          : darkMode
                            ? "text-zinc-500 hover:bg-zinc-800"
                            : "text-zinc-400 hover:bg-zinc-100"
                    }`}
                  >
                    <span className={`w-5 shrink-0 text-right tabular-nums text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                      {i + 1}
                    </span>
                    <span className="truncate">{s.title}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        </div>

        {/* Footer: prev / next */}
        <div className={`shrink-0 flex items-center gap-2 px-4 py-2.5 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <button
            type="button"
            data-testid="tour-prev"
            onClick={tourStepPrev}
            disabled={step <= 0}
            className={`flex-1 px-2 py-1.5 rounded-lg text-xs font-medium ${chipBtn}`}
            title="Previous step"
          >
            {"←"} Previous
          </button>
          <button
            type="button"
            data-testid="tour-next"
            onClick={tourStepNext}
            disabled={step >= steps.length - 1}
            className={`flex-1 px-2 py-1.5 rounded-lg text-xs font-medium ${chipBtn}`}
            title="Next step"
          >
            Next {"→"}
          </button>
        </div>
      </div>
    );
  }

  // ── The tour list overlay ──────────────────────────────────────────────────
  if (!toursOpen) return null;
  const tours = getTours();
  const panelCls = darkMode
    ? "bg-zinc-950 border-zinc-800 text-zinc-200"
    : "bg-white border-zinc-200 text-zinc-800";

  return (
    <div
      data-testid="tours-list-overlay"
      className="fixed inset-0 z-50 flex items-start justify-center pt-[6vh] px-4"
      role="dialog"
      aria-modal="true"
      aria-label="Guided walkthroughs"
    >
      <div className="absolute inset-0 bg-black/50" onClick={closeTours} />
      <div className={`relative w-full max-w-lg max-h-[85vh] flex flex-col rounded-2xl border shadow-2xl ${panelCls}`}>
        <div className={`shrink-0 px-4 pt-3 pb-2 border-b ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <div className="flex items-center gap-2">
            <span>{"\u{1F5FA}️"}</span>
            <h2 className="text-sm font-bold">Guided walkthroughs</h2>
            <button
              type="button"
              onClick={closeTours}
              className={`ml-auto p-1 rounded ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-500"}`}
              title="Close (Esc)"
            >
              {"✕"}
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2" data-testid="tour-list">
          {tours.length === 0 ? (
            <p className={`px-2 py-6 text-center text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              No walkthroughs for this dataset.
            </p>
          ) : (
            tours.map((tour) => (
              <button
                key={tour.id}
                type="button"
                data-testid="tour-list-item"
                data-tour-id={tour.id}
                data-step-count={tourStepCount(tour)}
                data-stale={isTourStale(tour)}
                onClick={() => startTour(tour.id)}
                className={`w-full text-left rounded-lg border px-3 py-2.5 ${darkMode ? "border-zinc-800 hover:bg-zinc-900/60" : "border-zinc-200 hover:bg-zinc-50"}`}
                title="Play this walkthrough"
              >
                <div className="flex items-center gap-2">
                  <span className={`text-sm font-semibold ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
                    {tour.title}
                  </span>
                  {isTourStale(tour) && <StaleMarker darkMode={darkMode} />}
                  {tour.statement_kind === "authored_interpretation" && <InterpretationMarker darkMode={darkMode} />}
                  <span className={`ml-auto shrink-0 text-[10px] px-1.5 py-0.5 rounded tabular-nums ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-600"}`}>
                    {tourStepCount(tour)} step{tourStepCount(tour) !== 1 ? "s" : ""}
                  </span>
                </div>
                {tour.description && (
                  <p className={`mt-1 text-[11px] leading-relaxed ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                    {tour.description}
                  </p>
                )}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
