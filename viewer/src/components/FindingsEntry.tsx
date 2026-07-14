import { useArchStore } from "../store";
import { hasFindingsSurface } from "../findings/model";
import { Tooltip } from "./Tooltip";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";

// The Findings surface entry point (P6-8). A slim bar directly under the coverage
// badge, present whenever the dataset carries findings or concerns; it opens the
// globally reachable FindingsSurface overlay. When neither key is present it
// renders nothing, so legacy datasets are byte-identical (no entry point).

export function FindingsEntry() {
  const architecture = useArchStore((s) => s.architecture);
  const darkMode = useArchStore((s) => s.darkMode);
  const openFindingsSurface = useArchStore((s) => s.openFindingsSurface);

  if (!hasFindingsSurface(architecture)) return null;

  const findings = architecture?.findings ?? [];
  const concerns = architecture?.concerns ?? [];
  const unverified = findings.filter((f) => f.verification_status !== "verified").length;

  return (
    <div
      className={`px-4 py-1.5 text-xs shrink-0 ${
        darkMode
          ? "bg-amber-950/20 border-b border-amber-900/30 text-amber-200"
          : "bg-amber-50 border-b border-amber-200 text-amber-800"
      }`}
    >
      <button
        type="button"
        data-testid="findings-entry"
        onClick={() => openFindingsSurface({ elementFilter: null })}
        className="w-full flex items-center gap-2 text-left"
      >
        <span className="shrink-0">{"\u{1F50E}"}</span>
        <Tooltip content={TOOLTIP_COPY.findings.entry}>
          <span className="font-semibold shrink-0">
            {findings.length} finding{findings.length !== 1 ? "s" : ""}
          </span>
        </Tooltip>
        <span className={`shrink-0 ${darkMode ? "text-amber-400/80" : "text-amber-600"}`}>
          · {concerns.length} concern{concerns.length !== 1 ? "s" : ""}
        </span>
        {unverified > 0 && (
          <Tooltip content={TOOLTIP_COPY.findings.verification.unverified} focusable>
            <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${darkMode ? "bg-amber-500/15 text-amber-300" : "bg-amber-100 text-amber-700"}`}>
              {unverified} unverified
            </span>
          </Tooltip>
        )}
        <span className="flex-1" />
        <span className={`shrink-0 text-[10px] ${darkMode ? "text-amber-400/80" : "text-amber-600"}`}>
          Review what the system noticed &rsaquo;
        </span>
      </button>
    </div>
  );
}
