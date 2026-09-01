import { useArchStore } from "../store";
import { TrustLedger } from "./TrustLedger";

export function WorkbenchTrustStrip() {
  const architecture = useArchStore((state) => state.architecture);
  const darkMode = useArchStore((state) => state.darkMode);
  const openFindings = useArchStore((state) => state.openFindingsSurface);
  const openSupply = useArchStore((state) => state.openSupplyChain);
  const openTours = useArchStore((state) => state.openTours);
  if (!architecture) return null;
  return (
    <div className={`flex shrink-0 items-center gap-2 overflow-x-auto border-b px-3 py-1.5 ${darkMode ? "border-zinc-800 bg-zinc-950" : "border-zinc-200 bg-white"}`}>
      <TrustLedger compact />
      {architecture.findings?.length ? <button onClick={() => openFindings({ elementFilter: null })} className={chip(darkMode)}>{architecture.findings.length} findings · {architecture.findings.filter((row) => row.verification_status !== "verified").length} unverified</button> : null}
      {architecture.supply_chain && <button onClick={openSupply} className={chip(darkMode)}>{architecture.supply_chain.counts.direct} direct dependencies</button>}
      {architecture.tours?.length ? <button onClick={openTours} className={chip(darkMode)}>{architecture.tours.length} guided paths</button> : null}
      <span className={`ml-auto hidden whitespace-nowrap text-[9px] uppercase tracking-wider lg:block ${darkMode ? "text-zinc-700" : "text-zinc-400"}`}>Open a measure to inspect evidence</span>
    </div>
  );
}

function chip(dark: boolean): string {
  return `whitespace-nowrap rounded-lg border px-2.5 py-1.5 text-[10px] ${dark ? "border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-200" : "border-zinc-200 bg-zinc-50 text-zinc-600 hover:text-zinc-900"}`;
}
