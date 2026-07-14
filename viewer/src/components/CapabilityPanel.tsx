import { useMemo, useState } from "react";
import { useArchStore } from "../store";
import { groupCapabilitiesByKind, capabilityIsTested, CAP_KIND_ORDER } from "../lenses";
import type { Capability, Component } from "../types";
import { Tooltip } from "./Tooltip";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";

// The Capability lens surface (P6-3, LENS-DESIGN.md L2). The landing view is a
// ranked panel (invariant I11) grouping capabilities by kind (api, cli, event,
// job) with counts, each group expandable to its capabilities; api ranks by path,
// others by name. Each entry names its owning component and shows a tested/
// untested badge from the L2 test linkage (the proof bridge). Selecting an entry
// selects its owning component (I12), opens the Capabilities tab, and highlights
// the entry.

const KIND_LABEL: Record<Capability["kind"], string> = {
  api: "API",
  cli: "CLI",
  event: "Events",
  job: "Jobs",
};

// Flatten the component tree into an id -> name map for labeling owners.
function buildNameMap(components: Component[]): Record<string, string> {
  const map: Record<string, string> = {};
  const walk = (list: Component[]) => {
    for (const c of list) {
      map[c.id] = c.name;
      if (c.children.length > 0) walk(c.children);
    }
  };
  walk(components);
  return map;
}

function TestedBadge({ tested, darkMode }: { tested: boolean; darkMode: boolean }) {
  if (tested) {
    return (
      <Tooltip content={TOOLTIP_COPY.capability.tested}>
        <span
          className={`px-1.5 py-0.5 rounded text-[10px] ${darkMode ? "bg-emerald-500/15 text-emerald-300" : "bg-emerald-100 text-emerald-700"}`}
        >
          tested
        </span>
      </Tooltip>
    );
  }
  return (
    <Tooltip content={TOOLTIP_COPY.capability.untested}>
      <span
        className={`px-1.5 py-0.5 rounded text-[10px] ${darkMode ? "bg-zinc-800 text-zinc-500" : "bg-zinc-100 text-zinc-500"}`}
      >
        untested
      </span>
    </Tooltip>
  );
}

export function CapabilityPanel() {
  const darkMode = useArchStore((s) => s.darkMode);
  const architecture = useArchStore((s) => s.architecture);
  const selectedCapabilityId = useArchStore((s) => s.selectedCapabilityId);
  const getCapabilities = useArchStore((s) => s.getCapabilities);
  const selectCapability = useArchStore((s) => s.selectCapability);

  const capabilities = getCapabilities();
  const groups = useMemo(() => groupCapabilitiesByKind(capabilities), [capabilities]);
  const nameMap = useMemo(() => buildNameMap(architecture?.components ?? []), [architecture]);

  // Which kind groups are expanded. Default: all expanded so the reader sees the
  // whole surface at once; toggling collapses a kind.
  const [collapsed, setCollapsed] = useState<Set<Capability["kind"]>>(new Set());
  const toggle = (kind: Capability["kind"]) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });

  const testedCount = capabilities.filter(capabilityIsTested).length;

  const containerClass = `hidden md:flex flex-col w-80 shrink-0 border-r overflow-hidden ${
    darkMode ? "bg-zinc-950 border-zinc-800" : "bg-zinc-50 border-zinc-200"
  }`;

  return (
    <div className={containerClass}>
      <div className={`px-4 py-3 border-b shrink-0 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        <div className="flex items-center gap-1.5">
          <span>{"\u{1F6E0}"}</span>
          <h2 className={`text-sm font-bold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>Capabilities</h2>
        </div>
        <p className={`mt-0.5 text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
          {capabilities.length} capabilit{capabilities.length === 1 ? "y" : "ies"} · {testedCount} proven by tests
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-3">
        {groups.length === 0 && (
          <div className={`text-xs text-center py-6 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            No capabilities in this dataset.
          </div>
        )}
        {groups.map((group) => {
          const isCollapsed = collapsed.has(group.kind);
          return (
            <div key={group.kind}>
              <button
                onClick={() => toggle(group.kind)}
                className={`w-full flex items-center justify-between px-2 py-1 rounded ${darkMode ? "hover:bg-zinc-900" : "hover:bg-white"}`}
              >
                <Tooltip content={TOOLTIP_COPY.capability.kind}>
                  <span className={`text-[11px] font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
                    {KIND_LABEL[group.kind]} ({group.items.length})
                  </span>
                </Tooltip>
                <span className={`text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                  {isCollapsed ? "▸" : "▾"}
                </span>
              </button>
              {!isCollapsed && (
                <ul className="mt-1 space-y-1">
                  {group.items.map((cap) => {
                    const selected = cap.id === selectedCapabilityId;
                    const label =
                      cap.kind === "api" ? (cap.detail.path || cap.name) : cap.name;
                    const owner = cap.component_id ? (nameMap[cap.component_id] ?? cap.component_id) : "unowned";
                    return (
                      <li key={cap.id}>
                        <button
                          onClick={() => selectCapability(cap.id)}
                          className={`w-full text-left rounded-lg px-2.5 py-1.5 transition-colors ${
                            selected
                              ? darkMode ? "bg-blue-500/15 ring-1 ring-blue-500/40" : "bg-blue-50 ring-1 ring-blue-300"
                              : darkMode ? "hover:bg-zinc-900" : "hover:bg-white"
                          }`}
                        >
                          <div className="flex items-center gap-1.5">
                            {cap.kind === "api" && cap.detail.method && (
                              <span className={`text-[9px] font-bold px-1 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-300" : "bg-zinc-200 text-zinc-600"}`}>
                                {cap.detail.method.toUpperCase()}
                              </span>
                            )}
                            <span className={`flex-1 text-xs font-mono truncate ${darkMode ? "text-zinc-200" : "text-zinc-800"}`} title={cap.id}>
                              {label}
                            </span>
                          </div>
                          <div className="mt-1 flex items-center justify-between gap-2">
                            <span className={`text-[10px] truncate ${darkMode ? "text-zinc-500" : "text-zinc-400"}`} title={owner}>
                              {owner}
                            </span>
                            <TestedBadge tested={capabilityIsTested(cap)} darkMode={darkMode} />
                          </div>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          );
        })}
      </div>

      <div className={`px-4 py-2 border-t shrink-0 text-[10px] ${darkMode ? "border-zinc-800 text-zinc-600" : "border-zinc-200 text-zinc-400"}`}>
        Ranked {CAP_KIND_ORDER.map((k) => KIND_LABEL[k]).join(" · ")}; api by path, others by name.
      </div>
    </div>
  );
}
