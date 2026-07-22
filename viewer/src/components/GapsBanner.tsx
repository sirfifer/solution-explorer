import { useState } from "react";
import { useArchStore } from "../store";
import { Tooltip } from "./Tooltip";

// Producer-gap banner (card R1 honesty surface). When a derive pass, an
// emitter, or another producer could not hand off a whole result, the analyzer
// records a ProducerGap instead of crashing (analyzer/contracts.py). The
// projection carries them under `gaps`; this banner surfaces them visibly so an
// analyzer that failed honestly does not look identical to one that succeeded
// (GUI run finding V9.2). Absent entirely on a clean run (no `gaps` key), so a
// healthy dataset renders nothing and stays byte-identical to before.

export function GapsBanner() {
  const architecture = useArchStore((s) => s.architecture);
  const darkMode = useArchStore((s) => s.darkMode);
  const [expanded, setExpanded] = useState(false);

  const gaps = architecture?.gaps ?? [];
  if (gaps.length === 0) return null;

  return (
    <div
      className={`text-xs shrink-0 ${
        darkMode
          ? "bg-rose-950/25 border-b border-rose-900/40 text-rose-200"
          : "bg-rose-50 border-b border-rose-200 text-rose-800"
      }`}
    >
      <button
        type="button"
        data-testid="gaps-banner"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-1.5 text-left"
        aria-expanded={expanded}
      >
        <span className="shrink-0">{"⚠️"}</span>
        <Tooltip content="Producers that could not hand off a complete result. The analyzer recorded these honest gaps instead of crashing; the rest of the projection is built around them.">
          <span className="font-semibold shrink-0">
            {gaps.length} producer gap{gaps.length !== 1 ? "s" : ""}
          </span>
        </Tooltip>
        <span className="flex-1" />
        <span className={`shrink-0 text-[10px] ${darkMode ? "text-rose-400/80" : "text-rose-600"}`}>
          {expanded ? "Hide" : "What could not be produced"} {expanded ? "▼" : "›"}
        </span>
      </button>

      {expanded && (
        <ul className="px-4 pb-2 space-y-1.5">
          {gaps.map((gap, i) => (
            <li
              key={`${gap.producer}-${gap.stage}-${i}`}
              data-testid="gaps-entry"
              className={`rounded-md px-2 py-1.5 ${
                darkMode ? "bg-rose-950/30" : "bg-rose-100/60"
              }`}
            >
              <div className="flex items-center gap-2">
                <code className={`text-[11px] font-mono ${darkMode ? "text-rose-200" : "text-rose-800"}`}>
                  {gap.producer}
                </code>
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${darkMode ? "bg-rose-500/20 text-rose-300" : "bg-rose-200 text-rose-700"}`}>
                  {gap.stage}
                </span>
                <span className={`text-[10px] ${darkMode ? "text-rose-400/80" : "text-rose-600"}`}>
                  {gap.status}
                </span>
              </div>
              {gap.reason && (
                <div className={`mt-0.5 text-[11px] ${darkMode ? "text-rose-300/90" : "text-rose-700/90"}`}>
                  {gap.reason}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
