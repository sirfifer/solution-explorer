import { useMemo } from "react";
import { useArchStore } from "../store";

export function SupportPanel({ mobile = false }: { mobile?: boolean } = {}) {
  const darkMode = useArchStore((state) => state.darkMode);
  const architecture = useArchStore((state) => state.architecture);
  const navigate = useArchStore((state) => state.navigateToComponent);
  const support = architecture?.support;
  const rows = useMemo(() => support?.attention ?? [], [support]);
  const container = mobile
    ? `flex h-full w-full flex-col overflow-hidden ${darkMode ? "bg-zinc-950" : "bg-zinc-50"}`
    : `hidden w-80 shrink-0 flex-col overflow-hidden border-r md:flex ${darkMode ? "border-zinc-800 bg-zinc-950" : "border-zinc-200 bg-zinc-50"}`;

  if (!support) return null;
  return (
    <section data-se="panel" className={container} aria-label="Support and Operations lens">
      <header className={`shrink-0 border-b px-4 py-3 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-cyan-500">Observed operational surface</p>
        <h2 className={`mt-1 text-sm font-bold ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>What could break at 3am?</h2>
        <p className={`mt-1 text-[10px] leading-relaxed ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>{support.method_caveat}</p>
      </header>
      <div className="flex-1 space-y-4 overflow-y-auto p-3">
        <section>
          <h3 className={`mb-1 text-[10px] font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>Ranked attention</h3>
          <ol className="space-y-1.5">
            {rows.map((row, index) => (
              <li key={row.component_id}>
                <button
                  className={`w-full rounded-xl border px-3 py-2 text-left transition ${darkMode ? "border-zinc-800 bg-zinc-900/70 hover:border-cyan-500/50" : "border-zinc-200 bg-white hover:border-cyan-400"}`}
                  onClick={() => navigate(row.component_id)}
                >
                  <span className="text-[10px] text-cyan-500">{String(index + 1).padStart(2, "0")} · attention {row.attention_score}</span>
                  <strong className={`mt-0.5 block text-xs ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>{row.component_name}</strong>
                  <span className={`block text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>{row.reasons.join(" · ")}</span>
                </button>
              </li>
            ))}
          </ol>
        </section>
        <CompactGroup
          title={`Configuration (${support.configuration.length})`}
          rows={support.configuration.map((row) => ({ key: `${row.kind}:${row.key}`, label: row.key, meta: row.component_name, componentId: row.component_id }))}
          darkMode={darkMode}
          onOpen={navigate}
        />
        <CompactGroup
          title={`External reliance (${support.external_dependencies.length})`}
          rows={support.external_dependencies.map((row) => ({ key: `${row.component_id}:${row.name}`, label: row.name, meta: `${row.category} · ${row.component_name}`, componentId: row.component_id }))}
          darkMode={darkMode}
          onOpen={navigate}
        />
        <CompactGroup
          title={`Entry points (${support.entry_points.length})`}
          rows={support.entry_points.map((row) => ({ key: row.id, label: row.name, meta: `${row.kind} · ${row.confidence}`, componentId: row.component_id }))}
          darkMode={darkMode}
          onOpen={navigate}
        />
      </div>
    </section>
  );
}

function CompactGroup({ title, rows, darkMode, onOpen }: {
  title: string;
  rows: Array<{ key: string; label: string; meta: string; componentId: string | null }>;
  darkMode: boolean;
  onOpen: (id: string) => void;
}) {
  if (!rows.length) return null;
  return (
    <section>
      <h3 className={`mb-1 text-[10px] font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>{title}</h3>
      <ul className="space-y-1">
        {rows.slice(0, 12).map((row) => (
          <li key={row.key}>
            <button
              disabled={!row.componentId}
              onClick={() => row.componentId && onOpen(row.componentId)}
              className={`w-full rounded-lg px-2 py-1.5 text-left ${darkMode ? "hover:bg-zinc-900" : "hover:bg-white"}`}
            >
              <span className={`block truncate text-xs ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{row.label}</span>
              <span className={`block truncate text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>{row.meta}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
