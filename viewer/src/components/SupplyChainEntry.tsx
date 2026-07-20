import { useArchStore } from "../store";
import { hasSupplyChain } from "../supplyChain/model";
import { Tooltip } from "./Tooltip";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";

// The supply chain surface entry point (P10-1). A slim bar under the coverage
// and findings bars, present whenever the dataset carries a supply_chain section;
// it opens the globally reachable SupplyChainSurface overlay. When the section is
// absent (an old dataset or a repo with no manifests) it renders nothing, so
// those datasets are byte-identical (no entry point).

export function SupplyChainEntry() {
  const architecture = useArchStore((s) => s.architecture);
  const darkMode = useArchStore((s) => s.darkMode);
  const openSupplyChain = useArchStore((s) => s.openSupplyChain);

  if (!hasSupplyChain(architecture)) return null;

  const sc = architecture!.supply_chain!;
  const { dependencies, direct, ecosystems, targets, warnings } = sc.counts;

  return (
    <div
      className={`px-4 py-1.5 text-xs shrink-0 ${
        darkMode
          ? "bg-teal-950/20 border-b border-teal-900/30 text-teal-200"
          : "bg-teal-50 border-b border-teal-200 text-teal-800"
      }`}
    >
      <button
        type="button"
        data-testid="supply-chain-entry"
        onClick={openSupplyChain}
        className="w-full flex items-center gap-2 text-left"
      >
        <span className="shrink-0">{"\u{1F4E6}"}</span>
        <Tooltip content={TOOLTIP_COPY.supplyChain.entry}>
          <span className="font-semibold shrink-0">
            {dependencies} dependenc{dependencies !== 1 ? "ies" : "y"}
          </span>
        </Tooltip>
        <span className={`shrink-0 ${darkMode ? "text-teal-400/80" : "text-teal-600"}`}>
          {"·"} {ecosystems} ecosystem{ecosystems !== 1 ? "s" : ""}
        </span>
        <span className={`hidden sm:inline shrink-0 ${darkMode ? "text-teal-400/80" : "text-teal-600"}`}>
          {"·"} {direct} direct
        </span>
        {targets > 0 && (
          <span className={`hidden sm:inline shrink-0 ${darkMode ? "text-teal-400/80" : "text-teal-600"}`}>
            {"·"} {targets} target{targets !== 1 ? "s" : ""}
          </span>
        )}
        {warnings > 0 && (
          <Tooltip content={TOOLTIP_COPY.supplyChain.warning} focusable>
            <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${darkMode ? "bg-amber-500/15 text-amber-300" : "bg-amber-100 text-amber-700"}`}>
              {warnings} parse warning{warnings !== 1 ? "s" : ""}
            </span>
          </Tooltip>
        )}
        <span className="flex-1" />
        <span className={`shrink-0 text-[10px] ${darkMode ? "text-teal-400/80" : "text-teal-600"}`}>
          Supply chain &rsaquo;
        </span>
      </button>
    </div>
  );
}
