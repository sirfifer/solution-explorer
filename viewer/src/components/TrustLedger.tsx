import { useEffect } from "react";
import { useArchStore } from "../store";

export function TrustLedger({ compact = false }: { compact?: boolean }) {
  const architecture = useArchStore((state) => state.architecture);
  const darkMode = useArchStore((state) => state.darkMode);
  const setTrustOpen = useArchStore((state) => state.setTrustOpen);
  const trust = architecture?.orientation?.trust;
  if (!architecture || !trust) return null;

  if (compact) {
    const mapped = trust.source_coverage.analyzed;
    const total = trust.source_coverage.inventory_total;
    const coverageLabel = mapped != null && total
      ? `${mapped}/${total} files mapped`
      : trust.source_coverage.percent == null ? "Coverage unavailable" : `${trust.source_coverage.percent}% source parsed`;
    const statusCounts = trust.producer_gap_status ?? {};
    const unresolved = statusCounts.unresolved ?? 0;
    const failed = statusCounts.failed ?? 0;
    const producerLabel = [
      unresolved ? `${unresolved} unresolved claims` : "",
      failed ? `${failed} failed producers` : "",
    ].filter(Boolean).join(" · ") || "No producer issues";
    return (
      <button onClick={() => setTrustOpen(true)} className={`flex min-h-11 items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs sm:min-h-0 sm:text-[10px] ${darkMode ? "border-zinc-800 bg-zinc-900 text-zinc-300" : "border-zinc-200 bg-white text-zinc-600"}`}>
        <i className={`h-2 w-2 rounded-full ${trust.source_coverage.status === "complete" ? "bg-emerald-400" : "bg-amber-400"}`} />
        <strong>{coverageLabel}</strong>
        <span>· {producerLabel}</span>
      </button>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <TrustMetric label="Source parsing" value={trust.source_coverage.analyzed != null && trust.source_coverage.inventory_total ? `${trust.source_coverage.analyzed}/${trust.source_coverage.inventory_total}` : trust.source_coverage.percent == null ? "Unavailable" : `${trust.source_coverage.percent}%`} note={trust.source_coverage.inventory_total ? `${trust.source_coverage.binary ?? 0} binary · ${trust.source_coverage.excluded ?? 0} excluded · ${trust.source_coverage.gaps ?? 0} parse gaps` : trust.source_coverage.status.replaceAll("_", " ")} darkMode={darkMode} />
      <TrustMetric label="Producer claims" value={String(trust.producer_gaps)} note={Object.entries(trust.producer_gap_status ?? {}).map(([status, count]) => `${count} ${status}`).join(" · ") || "no unresolved or failed claims"} darkMode={darkMode} />
      <TrustMetric label="Findings" value={String(trust.findings.total)} note={`${trust.findings.unverified} remain unverified`} darkMode={darkMode} />
      <TrustMetric label="Direct dependencies" value={String(trust.direct_dependencies)} note="from the observed supply chain" darkMode={darkMode} />
    </div>
  );
}

function TrustMetric({ label, value, note, darkMode }: { label: string; value: string; note: string; darkMode: boolean }) {
  return <div className={`rounded-xl border p-3 ${darkMode ? "border-zinc-800 bg-zinc-900/70" : "border-zinc-200 bg-white"}`}><span className={`text-xs uppercase tracking-wider ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{label}</span><strong className={`mt-1 block text-xl ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>{value}</strong><small className={`block text-xs ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{note}</small></div>;
}

export function TrustDrawer() {
  const open = useArchStore((state) => state.trustOpen);
  const setOpen = useArchStore((state) => state.setTrustOpen);
  const architecture = useArchStore((state) => state.architecture);
  const darkMode = useArchStore((state) => state.darkMode);
  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open, setOpen]);
  if (!open || !architecture?.orientation) return null;
  const interpreted = architecture.orientation.orientation.interpreted_statement;
  const interpretationStale = Boolean(interpreted?.provenance.stale);
  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-black/45" role="dialog" aria-modal="true" aria-label="Evidence and coverage">
      <button className="absolute inset-0" aria-label="Close evidence and coverage" onClick={() => setOpen(false)} />
      <aside className={`relative h-full w-full max-w-xl overflow-y-auto border-l p-6 shadow-2xl ${darkMode ? "border-zinc-800 bg-zinc-950" : "border-zinc-200 bg-zinc-50"}`}>
        <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-500">Trust ledger</p><h2 className={`mt-1 text-xl font-bold ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>What this view knows—and what it does not</h2></div><button className="min-h-11 min-w-11 rounded-lg p-2 text-zinc-500 hover:bg-zinc-800/20" onClick={() => setOpen(false)} aria-label="Close">✕</button></div>
        <div className="mt-6"><TrustLedger /></div>
        <section className={`mt-6 rounded-xl border p-4 ${darkMode ? "border-violet-500/20 bg-violet-500/5" : "border-violet-200 bg-violet-50"}`}>
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className={`text-xs font-semibold ${darkMode ? "text-violet-200" : "text-violet-800"}`}>Interpretation</h3>{interpretationStale && <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${darkMode ? "bg-amber-400/10 text-amber-300" : "bg-amber-100 text-amber-800"}`}>Stale · withheld</span>}</div>
          <p className={`mt-2 text-sm leading-relaxed ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{interpretationStale ? "An older interpreted summary is retained in the projection for auditability, but is not rendered as product copy because its mapped evidence changed. The Overview now uses the current repository description and structured measurements." : interpreted?.text ?? "No interpreted system statement is present. The Overview uses only deterministic grouping and counts."}</p>
          {interpretationStale && interpreted?.provenance.derived_from_commit && <p className={`mt-2 break-all text-xs ${darkMode ? "text-zinc-500" : "text-zinc-600"}`}>Interpretation derived from commit {interpreted.provenance.derived_from_commit}.</p>}
          <p className={`mt-2 text-xs ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>Status: {architecture.orientation.trust.interpretation.status}. Interpreted copy is presentation context, not a replacement for mapped evidence.</p>
        </section>
        {architecture.security && <section className={`mt-4 rounded-xl border p-4 ${darkMode ? "border-amber-500/20 bg-amber-500/5" : "border-amber-200 bg-amber-50"}`}><h3 className={`text-xs font-semibold ${darkMode ? "text-amber-200" : "text-amber-800"}`}>Security boundary</h3><p className={`mt-2 text-sm ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{architecture.security.method_caveat}</p></section>}
      </aside>
    </div>
  );
}
