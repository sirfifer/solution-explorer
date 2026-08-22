import { useMemo } from "react";
import { useArchStore } from "../store";
import {
  buildScatter,
  designMethodCaveat,
  groupDesignFindings,
  METHOD_LABEL,
  readZoneThresholds,
  type ScatterPoint,
} from "../lenses";
import type { DesignFinding } from "../types";

// The Design lens surface (D4). The landing view is a ranked panel (invariant
// I11): findings grouped by kind, each group in the order Part 3 of the research
// document lists them, and each row rendered under the two-audience rule.
//
// THE TWO-AUDIENCE RULE IS THE LAYOUT. Every row puts the plain-language
// consequence first, in the largest type on the row, because that sentence is
// the whole point: a reader with no architecture vocabulary must learn what this
// costs them. The canonical term follows on a small chip for the practitioner
// who wants to know which body of theory stands behind the claim, and the method
// chip says which epistemic class the claim is in. The strings themselves come
// from the analyzer, which took them from the translation table; nothing here
// composes finding prose, so the viewer and the machine front door cannot drift
// into two different phrasings of the same fact.
//
// THE CAVEAT IS ALWAYS ON SCREEN. The foot of the panel renders
// design_signals.method_caveat verbatim. A static graph is not runtime truth,
// and the panel says so every time rather than hoping the reader remembers.

// Chip colours per kind, dark and light. Colour distinguishes kinds; it never
// encodes severity, because there is no severity to encode.
const KIND_CHIP: Record<DesignFinding["kind"], { light: string; dark: string }> = {
  cycle: { light: "bg-rose-100 text-rose-700", dark: "bg-rose-900/40 text-rose-300" },
  zone_of_pain: { light: "bg-amber-100 text-amber-700", dark: "bg-amber-900/40 text-amber-300" },
  stability_inversion: { light: "bg-orange-100 text-orange-700", dark: "bg-orange-900/40 text-orange-300" },
  change_coupling: { light: "bg-violet-100 text-violet-700", dark: "bg-violet-900/40 text-violet-300" },
  zone_of_uselessness: { light: "bg-sky-100 text-sky-700", dark: "bg-sky-900/40 text-sky-300" },
  boundary_strength: { light: "bg-emerald-100 text-emerald-700", dark: "bg-emerald-900/40 text-emerald-300" },
};

// The canonical term, rendered as the secondary element. Never the lead.
function TermChip({ finding, darkMode }: { finding: DesignFinding; darkMode: boolean }) {
  const colors = KIND_CHIP[finding.kind];
  const title = finding.term_detail ? `${finding.term} (${finding.term_detail})` : finding.term;
  return (
    <span
      title={title}
      className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${darkMode ? colors.dark : colors.light}`}
    >
      {finding.term}
    </span>
  );
}

// The epistemic class. "from the code graph" is not the same claim as "from git
// history", and a reader deciding whether to trust a finding needs to know which.
function MethodChip({ finding, darkMode }: { finding: DesignFinding; darkMode: boolean }) {
  return (
    <span
      className={`text-[9px] px-1 py-0.5 rounded uppercase tracking-wide ${
        darkMode ? "bg-zinc-800 text-zinc-500" : "bg-zinc-100 text-zinc-500"
      }`}
    >
      {METHOD_LABEL[finding.method] ?? finding.method}
    </span>
  );
}

function FindingRow({ finding, selected }: { finding: DesignFinding; selected: boolean }) {
  const darkMode = useArchStore((s) => s.darkMode);
  const selectDesignFinding = useArchStore((s) => s.selectDesignFinding);
  return (
    <li>
      <button
        onClick={() => selectDesignFinding(finding.id)}
        className={`w-full text-left rounded-lg px-2.5 py-2 transition-colors ${
          selected
            ? darkMode
              ? "bg-indigo-500/15 ring-1 ring-indigo-500/40"
              : "bg-indigo-50 ring-1 ring-indigo-300"
            : darkMode
              ? "hover:bg-zinc-900"
              : "hover:bg-white"
        }`}
      >
        {/* The lead. Plain language, first, and the largest thing on the row. */}
        <span
          className={`block text-[11.5px] leading-snug ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}
        >
          {finding.lead}
        </span>
        {/* The term second, then the method. Never the other way round. */}
        <span className="mt-1.5 flex items-center gap-1.5 flex-wrap">
          <TermChip finding={finding} darkMode={darkMode} />
          <MethodChip finding={finding} darkMode={darkMode} />
          {finding.targets.length > 0 && (
            <span
              className={`text-[9px] tabular-nums ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}
            >
              {finding.targets.length} part{finding.targets.length === 1 ? "" : "s"}
            </span>
          )}
        </span>
      </button>
    </li>
  );
}

// The abstractness / instability scatter, the signature chart of this school of
// analysis since the 1990s. Hand-rolled SVG: the viewer ships no charting
// library and this needs no dependency.
//
// The main sequence is the diagonal from (0 abstractness, 1 instability) to
// (1, 0), the line where abstractness and stability are in balance. The two
// shaded corners are the zones. A component is plotted only when BOTH ratios are
// known; the count of omitted components is printed beneath the chart, because a
// chart that silently drops half a system is the JPEG-artifact failure the
// project's own lossy-compression rule forbids.
const CHART = { w: 240, h: 240, pad: 24 };

function Scatter() {
  const darkMode = useArchStore((s) => s.darkMode);
  const architecture = useArchStore((s) => s.architecture);
  const selectComponent = useArchStore((s) => s.selectComponent);
  const data = useMemo(
    () => (architecture ? buildScatter(architecture) : { points: [], omitted: 0 }),
    [architecture],
  );
  // The zone corners come from the payload (falling back to the mirrored
  // constants for older datasets), so the shading marks exactly the regions
  // the findings beside the chart were computed against.
  const zones = architecture
    ? readZoneThresholds(architecture)
    : { painMaxSum: 0.5, uselessnessMinSum: 1.5 };

  if (data.points.length === 0) {
    return (
      <div className={`px-4 py-3 text-[10.5px] leading-relaxed ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
        No component in this dataset has both an abstractness and an instability
        reading, so there is nothing to plot. Abstractness can only be measured in
        languages whose declarations distinguish an interface from a class.
      </div>
    );
  }

  const { w, h, pad } = CHART;
  const px = (i: number) => pad + i * (w - 2 * pad);
  const py = (a: number) => h - pad - a * (h - 2 * pad);
  const grid = darkMode ? "#3f3f46" : "#d4d4d8";
  const axis = darkMode ? "#52525b" : "#a1a1aa";
  const text = darkMode ? "#a1a1aa" : "#71717a";

  return (
    <div className="px-3 pb-2">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full h-auto"
        role="img"
        aria-label="Abstractness against instability, with the main sequence and the two zones"
      >
        {/* Zone of pain: concrete and load-bearing, the bottom-left corner. */}
        <polygon
          points={`${px(0)},${py(0)} ${px(zones.painMaxSum)},${py(0)} ${px(0)},${py(zones.painMaxSum)}`}
          fill={darkMode ? "rgba(245,158,11,0.16)" : "rgba(245,158,11,0.14)"}
        />
        {/* Zone of uselessness: abstract and unused, the top-right corner. */}
        <polygon
          points={`${px(1)},${py(1)} ${px(zones.uselessnessMinSum - 1)},${py(1)} ${px(1)},${py(zones.uselessnessMinSum - 1)}`}
          fill={darkMode ? "rgba(56,189,248,0.16)" : "rgba(56,189,248,0.14)"}
        />
        {/* The main sequence. */}
        <line x1={px(0)} y1={py(1)} x2={px(1)} y2={py(0)} stroke={grid} strokeWidth="1" strokeDasharray="4 3" />
        {/* Axes. */}
        <line x1={px(0)} y1={py(0)} x2={px(1)} y2={py(0)} stroke={axis} strokeWidth="1" />
        <line x1={px(0)} y1={py(0)} x2={px(0)} y2={py(1)} stroke={axis} strokeWidth="1" />
        <text x={px(0.5)} y={h - 6} textAnchor="middle" fontSize="8" fill={text}>
          instability, easy to change
        </text>
        <text
          x={10}
          y={py(0.5)}
          textAnchor="middle"
          fontSize="8"
          fill={text}
          transform={`rotate(-90 10 ${py(0.5)})`}
        >
          abstractness
        </text>
        {data.points.map((p: ScatterPoint) => (
          <circle
            key={p.componentId}
            cx={px(p.i)}
            cy={py(p.a)}
            r={3.5}
            className="cursor-pointer"
            fill={
              p.zone === "pain"
                ? "#f59e0b"
                : p.zone === "uselessness"
                  ? "#38bdf8"
                  : darkMode
                    ? "#818cf8"
                    : "#6366f1"
            }
            opacity={0.85}
            onClick={() => selectComponent(p.componentId)}
          >
            <title>{`${p.name}: abstractness ${p.a.toFixed(2)}, instability ${p.i.toFixed(2)}`}</title>
          </circle>
        ))}
      </svg>
      {data.omitted > 0 && (
        <p className={`mt-1 text-[9.5px] leading-snug ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
          {data.omitted} component{data.omitted === 1 ? " is" : "s are"} not plotted: their
          abstractness could not be measured, so they have no position on this chart.
        </p>
      )}
    </div>
  );
}

// `mobile` (O10): see FlowPanel's comment on the same prop.
export function DesignPanel({ mobile = false }: { mobile?: boolean } = {}) {
  const darkMode = useArchStore((s) => s.darkMode);
  const architecture = useArchStore((s) => s.architecture);
  const selectedDesignFindingId = useArchStore((s) => s.selectedDesignFindingId);
  const clearDesignFinding = useArchStore((s) => s.clearDesignFinding);
  const blastRadiusMode = useArchStore((s) => s.blastRadiusMode);
  const toggleBlastRadiusMode = useArchStore((s) => s.toggleBlastRadiusMode);
  const getDesignFindings = useArchStore((s) => s.getDesignFindings);

  const findings = getDesignFindings();
  const groups = useMemo(() => groupDesignFindings(findings), [findings]);
  const caveat = architecture ? designMethodCaveat(architecture) : "";

  const containerClass = mobile
    ? `flex flex-col w-full h-full overflow-hidden ${darkMode ? "bg-zinc-950" : "bg-zinc-50"}`
    : `hidden md:flex flex-col w-80 shrink-0 border-r overflow-hidden ${
        darkMode ? "bg-zinc-950 border-zinc-800" : "bg-zinc-50 border-zinc-200"
      }`;

  return (
    <div className={containerClass}>
      <div className={`px-4 py-3 border-b shrink-0 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <div className="flex items-center gap-1.5">
          <span>{"\u{1F4D0}"}</span>
          <h2 className={`text-sm font-bold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>Design</h2>
        </div>
        <p className={`mt-0.5 text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
          {findings.length} finding{findings.length === 1 ? "" : "s"} about how this system is held together
        </p>
      </div>

      <div className="flex-1 overflow-y-auto pb-4">
        <div className={`px-4 py-2.5 text-[11px] leading-relaxed ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
          Each finding says what it costs you first. The term beside it is what
          the literature calls it.
        </div>

        {/* Blast radius is an interaction, not a report (D5). The toggle lives
            here because this is the lens that explains why it matters. */}
        <div className="px-4 pb-2">
          <button
            onClick={toggleBlastRadiusMode}
            aria-pressed={blastRadiusMode}
            className={`w-full text-left rounded-lg px-2.5 py-1.5 text-[10.5px] transition-colors ${
              blastRadiusMode
                ? darkMode
                  ? "bg-rose-500/15 ring-1 ring-rose-500/40 text-rose-200"
                  : "bg-rose-50 ring-1 ring-rose-300 text-rose-700"
                : darkMode
                  ? "bg-zinc-900 text-zinc-400 hover:bg-zinc-800"
                  : "bg-white text-zinc-500 hover:bg-zinc-100"
            }`}
          >
            {blastRadiusMode ? "Blast radius on" : "Show blast radius"}
            <span className={`block text-[9.5px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              Select a part to shade everything that could break if it changes.
            </span>
          </button>
        </div>

        {selectedDesignFindingId && (
          <div className="px-4 pb-2">
            <button
              onClick={clearDesignFinding}
              className={`text-[10px] underline ${darkMode ? "text-zinc-500 hover:text-zinc-300" : "text-zinc-400 hover:text-zinc-600"}`}
            >
              Clear selection, show every implicated part
            </button>
          </div>
        )}

        <div className="px-2 space-y-3">
          {groups.length === 0 && (
            <div className={`text-xs text-center py-6 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
              No design findings in this dataset.
            </div>
          )}
          {groups.map((group) => (
            <div key={group.kind}>
              <div
                className={`px-2 py-1 text-[11px] font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}
              >
                {group.label} ({group.count})
              </div>
              <ul className="space-y-1">
                {group.items.map((finding) => (
                  <FindingRow
                    key={finding.id}
                    finding={finding}
                    selected={finding.id === selectedDesignFindingId}
                  />
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className={`mt-4 px-2 pt-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
          <div
            className={`px-2 text-[11px] font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}
          >
            Abstract against changeable
          </div>
          <Scatter />
        </div>
      </div>

      {/* The caveat, verbatim from the payload, always on screen. */}
      {caveat && (
        <div
          className={`px-4 py-2 border-t shrink-0 text-[9.5px] leading-snug ${
            darkMode ? "border-zinc-800 text-zinc-600" : "border-zinc-200 text-zinc-400"
          }`}
        >
          How this was measured: {caveat}.
        </div>
      )}
    </div>
  );
}
