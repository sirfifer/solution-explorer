import { useArchStore } from "../store";
import { TrustLedger } from "./TrustLedger";

export function WorkbenchTrustStrip() {
  const architecture = useArchStore((state) => state.architecture);
  const darkMode = useArchStore((state) => state.darkMode);
  const openFindings = useArchStore((state) => state.openFindingsSurface);
  const openSupply = useArchStore((state) => state.openSupplyChain);
  const openTours = useArchStore((state) => state.openTours);
  const activeTourId = useArchStore((state) => state.activeTourId);
  const exitTour = useArchStore((state) => state.exitTour);
  if (!architecture) return null;
  return (
    // One row, always. The chips used to be allowed to shrink, so on a phone
    // the ledger's own label wrapped inside its button and the strip grew to
    // about 120px of a 664px screen (GUI crawl 2026-09-01, mobile chrome).
    // shrink-0 on every chip keeps each at its natural width and hands the
    // overflow to the horizontal scroll this container already had, so no label
    // is shortened and the graph gets the vertical space back.
    <div data-testid="trust-strip" className={`flex shrink-0 flex-nowrap items-center gap-2 overflow-x-auto border-b px-3 py-1.5 ${darkMode ? "border-zinc-800 bg-zinc-950" : "border-zinc-200 bg-white"}`}>
      <TrustLedger compact />
      {architecture.findings?.length ? <button data-testid="findings-entry" onClick={() => openFindings({ elementFilter: null })} className={chip(darkMode)}>{architecture.findings.length} findings · {architecture.findings.filter((row) => row.verification_status !== "verified").length} unverified</button> : null}
      {architecture.supply_chain && <button data-testid="supply-chain-entry" onClick={openSupply} className={chip(darkMode)}>{architecture.supply_chain.counts.direct} direct dependencies</button>}
      {architecture.tours?.length ? <button data-testid="tours-entry" onClick={() => { if (activeTourId) exitTour(); openTours(); }} className={chip(darkMode)}>{activeTourId ? "Choose another guided path" : `${architecture.tours.length} guided paths`}</button> : null}
      <span className={`ml-auto hidden whitespace-nowrap text-[9px] uppercase tracking-wider lg:block ${darkMode ? "text-zinc-700" : "text-zinc-400"}`}>Open a measure to inspect evidence</span>
    </div>
  );
}

function chip(dark: boolean): string {
  return `min-h-11 shrink-0 whitespace-nowrap rounded-lg border px-2.5 py-1.5 text-xs sm:min-h-0 sm:text-[10px] ${dark ? "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200" : "border-zinc-200 bg-zinc-50 text-zinc-600 hover:text-zinc-900"}`;
}
