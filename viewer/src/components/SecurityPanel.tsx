import type { ReactNode } from "react";
import { useArchStore } from "../store";

export function SecurityPanel({ mobile = false }: { mobile?: boolean } = {}) {
  const darkMode = useArchStore((state) => state.darkMode);
  const security = useArchStore((state) => state.architecture?.security);
  const navigate = useArchStore((state) => state.navigateToComponent);
  const container = mobile
    ? `flex h-full w-full flex-col overflow-hidden ${darkMode ? "bg-zinc-950" : "bg-zinc-50"}`
    : `hidden w-80 shrink-0 flex-col overflow-hidden border-r md:flex ${darkMode ? "border-zinc-800 bg-zinc-950" : "border-zinc-200 bg-zinc-50"}`;

  if (!security) return null;
  return (
    <section data-se="panel" className={container} aria-label="Security lens">
      <header className={`shrink-0 border-b px-4 py-3 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-violet-500">Repository-observable only</p>
        <h2 className={`mt-1 text-base font-bold ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>Security mechanisms and unknowns</h2>
        <p className={`mt-1 text-xs leading-relaxed ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{security.method_caveat}</p>
      </header>
      <div className="flex-1 space-y-4 overflow-y-auto p-3">
        <SecurityGroup title={`Confirmed mechanisms (${security.mechanisms.length})`} darkMode={darkMode}>
          {security.mechanisms.map((row) => (
            <button key={`${row.source}:${row.target}:${row.mechanism}`} onClick={() => navigate(row.source)} className={rowClass(darkMode)}>
              <strong>{row.mechanism}</strong>
              <small>{row.source} → {row.target} · {row.confidence}</small>
            </button>
          ))}
        </SecurityGroup>
        <SecurityGroup title={`Communication boundaries (${security.communication_boundaries.length})`} darkMode={darkMode}>
          {security.communication_boundaries.slice(0, 20).map((row) => (
            <button key={`${row.source}:${row.target}:${row.type}`} onClick={() => navigate(row.source)} className={rowClass(darkMode)}>
              <strong>{row.source_name} → {row.target_name}</strong>
              <small>{row.protocol} · {row.transport_state.replaceAll("_", " ")}</small>
            </button>
          ))}
        </SecurityGroup>
        <SecurityGroup title={`Credential inputs (${security.credential_configuration.length})`} darkMode={darkMode}>
          {security.credential_configuration.map((row) => (
            <button key={`${row.component_id}:${row.key}`} onClick={() => navigate(row.component_id)} className={rowClass(darkMode)}>
              <strong>{row.key}</strong><small>{row.component_name} · values never included</small>
            </button>
          ))}
        </SecurityGroup>
        {security.findings.length > 0 && (
          <SecurityGroup title={`Security-related leads (${security.findings.length})`} darkMode={darkMode}>
            {security.findings.map((row) => (
              <div key={row.id} className={rowClass(darkMode)}>
                <strong>{row.summary}</strong><small>{row.verification_status} · {row.confidence ?? "confidence unavailable"}</small>
              </div>
            ))}
          </SecurityGroup>
        )}
        <section className={`rounded-xl border p-3 ${darkMode ? "border-amber-500/20 bg-amber-500/5" : "border-amber-200 bg-amber-50"}`}>
          <h3 className={`text-xs font-semibold uppercase tracking-wider ${darkMode ? "text-amber-300" : "text-amber-700"}`}>Not observable from this repository</h3>
          <ul className={`mt-2 list-disc space-y-1 pl-4 text-xs ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
            {security.not_observable.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </section>
      </div>
    </section>
  );
}

function SecurityGroup({ title, darkMode, children }: { title: string; darkMode: boolean; children: ReactNode }) {
  return <section><h3 className={`mb-1 text-xs font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{title}</h3><div className="space-y-1">{children}</div></section>;
}

function rowClass(darkMode: boolean): string {
  return `block min-h-11 w-full rounded-lg px-2.5 py-2 text-left ${darkMode ? "bg-zinc-900/70 hover:bg-zinc-900 text-zinc-200" : "bg-white hover:bg-zinc-100 text-zinc-800"} [&>strong]:block [&>strong]:text-sm [&>small]:mt-0.5 [&>small]:block [&>small]:text-xs [&>small]:text-zinc-400`;
}
