import { useMemo, useState } from "react";
import { useArchStore } from "../store";
import {
  collectCriticalComponents,
  collectExternalDependencies,
  collectListeningPorts,
  hasCriticalityData,
} from "../lenses";
import { Tooltip } from "./Tooltip";

// The Inventory lens surface (owner decision 2026-08-17). Ranked, bounded
// lists first (I11): criticality, external dependencies, listening ports.
// Every row click-throughs to the component on the canvas (I12), so the
// inventory reinforces the map instead of forking from it.

function SectionLabel({ children, darkMode }: { children: React.ReactNode; darkMode: boolean }) {
  return (
    <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
      {children}
    </div>
  );
}

const CATEGORY_COLORS: Record<string, string> = {
  ai: "bg-purple-500/15 text-purple-500",
  cloud: "bg-sky-500/15 text-sky-500",
  database: "bg-pink-500/15 text-pink-500",
  payment: "bg-emerald-500/15 text-emerald-500",
  monitoring: "bg-amber-500/15 text-amber-500",
};

export function InventoryLensPanel() {
  const darkMode = useArchStore((s) => s.darkMode);
  const architecture = useArchStore((s) => s.architecture);
  const navigateToComponent = useArchStore((s) => s.navigateToComponent);
  const [expandedDep, setExpandedDep] = useState<string | null>(null);

  const critical = useMemo(
    () => (architecture ? collectCriticalComponents(architecture) : []),
    [architecture],
  );
  const enriched = useMemo(
    () => (architecture ? hasCriticalityData(architecture) : false),
    [architecture],
  );
  const dependencies = useMemo(
    () => (architecture ? collectExternalDependencies(architecture) : []),
    [architecture],
  );
  const ports = useMemo(
    () => (architecture ? collectListeningPorts(architecture) : []),
    [architecture],
  );

  if (!architecture) return null;

  const rowClass = `w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
    darkMode ? "hover:bg-zinc-800/60" : "hover:bg-zinc-100"
  }`;
  const nameClass = `font-medium truncate ${darkMode ? "text-zinc-200" : "text-zinc-800"}`;
  const subClass = `text-[11px] truncate ${darkMode ? "text-zinc-500" : "text-zinc-500"}`;

  return (
    <div
      className={`hidden md:flex flex-col w-80 shrink-0 border-r overflow-hidden ${
        darkMode ? "bg-zinc-950 border-zinc-800" : "bg-zinc-50 border-zinc-200"
      }`}
    >
      <div className={`px-4 py-3 border-b shrink-0 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <div className="flex items-center gap-1.5">
          <span>{"\u{1F4CB}"}</span>
          <h2 className={`text-sm font-bold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>Inventory</h2>
        </div>
        <p className={`mt-0.5 text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
          {critical.length} critical/important · {dependencies.length} external{" "}
          {dependencies.length === 1 ? "dependency" : "dependencies"} · {ports.length} ports
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-5">
        <div className="space-y-1.5">
          <SectionLabel darkMode={darkMode}>Critical components</SectionLabel>
          {!enriched ? (
            <p className={`px-1 text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              No criticality data: this dataset is not AI-enriched.
            </p>
          ) : critical.length === 0 ? (
            <p className={`px-1 text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              Nothing is tagged critical or important.
            </p>
          ) : (
            critical.map((entry) => (
              <button
                key={entry.id}
                className={rowClass}
                onClick={() => navigateToComponent(entry.id)}
              >
                <div className="flex items-center gap-2">
                  <Tooltip
                    content={
                      entry.criticality === "critical"
                        ? "Critical: the system fails without it."
                        : "Important: the system degrades without it."
                    }
                  >
                    <span
                      className={`inline-block w-2 h-2 rounded-full shrink-0 ${
                        entry.criticality === "critical" ? "bg-red-500" : "bg-amber-500"
                      }`}
                    />
                  </Tooltip>
                  <span className={nameClass}>{entry.name}</span>
                  <span className={`ml-auto text-[10px] shrink-0 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                    {entry.type}
                  </span>
                </div>
                {entry.purpose && <div className={subClass}>{entry.purpose}</div>}
              </button>
            ))
          )}
        </div>

        <div className="space-y-1.5">
          <SectionLabel darkMode={darkMode}>External dependencies</SectionLabel>
          {dependencies.length === 0 ? (
            <p className={`px-1 text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              No external services detected.
            </p>
          ) : (
            dependencies.map((dep) => (
              <div key={dep.name}>
                <button
                  className={rowClass}
                  onClick={() => setExpandedDep(expandedDep === dep.name ? null : dep.name)}
                >
                  <div className="flex items-center gap-2">
                    <span className={nameClass}>{dep.name}</span>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded shrink-0 ${
                        CATEGORY_COLORS[dep.category] ||
                        (darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-200 text-zinc-600")
                      }`}
                    >
                      {dep.category}
                    </span>
                    <span className={`ml-auto text-[10px] shrink-0 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                      {dep.componentIds.length} user{dep.componentIds.length !== 1 ? "s" : ""}
                    </span>
                  </div>
                </button>
                {expandedDep === dep.name && (
                  <div className="pl-4 pb-1 space-y-0.5">
                    {dep.componentIds.map((id, i) => (
                      <button
                        key={id}
                        className={`block w-full text-left px-2 py-1 rounded text-xs truncate ${
                          darkMode ? "text-zinc-400 hover:bg-zinc-800/60" : "text-zinc-600 hover:bg-zinc-100"
                        }`}
                        onClick={() => navigateToComponent(id)}
                      >
                        {dep.componentNames[i]}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        <div className="space-y-1.5">
          <SectionLabel darkMode={darkMode}>Listening ports</SectionLabel>
          {ports.length === 0 ? (
            <p className={`px-1 text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              No listening ports detected.
            </p>
          ) : (
            ports.map((entry) => (
              <button
                key={entry.id}
                className={rowClass}
                onClick={() => navigateToComponent(entry.id)}
              >
                <div className="flex items-center gap-2">
                  <span className={`font-mono text-xs shrink-0 ${darkMode ? "text-emerald-400" : "text-emerald-600"}`}>
                    :{entry.port}
                  </span>
                  <span className={nameClass}>{entry.name}</span>
                  <span className={`ml-auto text-[10px] shrink-0 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                    {entry.type}
                  </span>
                </div>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
