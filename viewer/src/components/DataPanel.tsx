import { useMemo } from "react";
import { useArchStore } from "../store";
import {
  rankEntitiesByAccess,
  accessCountForEntity,
  collectEntityAccessors,
  ENTITY_KIND_ORDER,
} from "../lenses";
import type { DataEntity, Component, EntityAccess } from "../types";
import { Tooltip } from "./Tooltip";

// The Data lens surface (P6-3, LENS-DESIGN.md L3). The landing view is a ranked
// panel (invariant I11): entities grouped by kind, ordered within a kind by how
// many components touch them (most-touched data first). Selecting an entity opens
// the focused "who touches this data" view: which components read it (green) and
// which write it (amber), with confidence marked on inferred edges. This is the
// lens's heart. Selecting also focuses the entity's owning component (I12) and
// renders the ego view in the graph.

const KIND_LABEL: Record<DataEntity["kind"], string> = {
  model: "Models",
  table: "Tables",
  migration: "Migrations",
  schema: "Schemas",
};

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

function KindBadge({ kind, darkMode }: { kind: DataEntity["kind"]; darkMode: boolean }) {
  const colors: Record<DataEntity["kind"], string> = {
    model: darkMode ? "bg-violet-900/40 text-violet-300" : "bg-violet-100 text-violet-700",
    table: darkMode ? "bg-emerald-900/40 text-emerald-300" : "bg-emerald-100 text-emerald-700",
    migration: darkMode ? "bg-amber-900/40 text-amber-300" : "bg-amber-100 text-amber-700",
    schema: darkMode ? "bg-zinc-700 text-zinc-300" : "bg-zinc-200 text-zinc-600",
  };
  return (
    <span className={`text-[9px] px-1.5 py-0.5 rounded uppercase tracking-wide ${colors[kind]}`}>{kind}</span>
  );
}

// One accessor row in the focused view. Read edges read green, write edges amber
// (the card's colors), with an inferred marker where confidence is not certain.
function AccessorRow({
  name,
  mode,
  confidence,
  darkMode,
}: {
  name: string;
  mode: EntityAccess["mode"];
  confidence: EntityAccess["confidence"];
  darkMode: boolean;
}) {
  const color =
    mode === "read"
      ? darkMode ? "bg-emerald-500/15 text-emerald-300" : "bg-emerald-100 text-emerald-700"
      : darkMode ? "bg-amber-500/15 text-amber-300" : "bg-amber-100 text-amber-700";
  return (
    <li className="flex items-center gap-2 text-[11px]">
      <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${color}`}>{mode}</span>
      <span className={`flex-1 truncate ${darkMode ? "text-zinc-300" : "text-zinc-700"}`} title={name}>
        {name}
      </span>
      {confidence === "inferred" && (
        <Tooltip content="Inferred by heuristic, not a parse-level certainty." focusable>
          <span
            className={`text-[9px] px-1 py-0.5 rounded uppercase tracking-wide ${darkMode ? "bg-zinc-800 text-zinc-500" : "bg-zinc-100 text-zinc-500"}`}
          >
            inferred
          </span>
        </Tooltip>
      )}
    </li>
  );
}

// `mobile` (O10): see FlowPanel's comment on the same prop.
export function DataPanel({ mobile = false }: { mobile?: boolean } = {}) {
  const darkMode = useArchStore((s) => s.darkMode);
  const architecture = useArchStore((s) => s.architecture);
  const selectedEntityId = useArchStore((s) => s.selectedEntityId);
  const getDataEntities = useArchStore((s) => s.getDataEntities);
  const getEntityAccess = useArchStore((s) => s.getEntityAccess);
  const selectEntity = useArchStore((s) => s.selectEntity);
  const clearEntity = useArchStore((s) => s.clearEntity);
  const selectComponent = useArchStore((s) => s.selectComponent);

  const entities = getDataEntities();
  const access = getEntityAccess();
  const groups = useMemo(() => rankEntitiesByAccess(entities, access), [entities, access]);
  const nameMap = useMemo(() => buildNameMap(architecture?.components ?? []), [architecture]);

  const focused = selectedEntityId ? entities.find((e) => e.id === selectedEntityId) : null;

  const containerClass = mobile
    ? `flex flex-col w-full h-full overflow-hidden ${darkMode ? "bg-zinc-950" : "bg-zinc-50"}`
    : `hidden md:flex flex-col w-80 shrink-0 border-r overflow-hidden ${
        darkMode ? "bg-zinc-950 border-zinc-800" : "bg-zinc-50 border-zinc-200"
      }`;

  const header = (
    <div className={`px-4 py-3 border-b shrink-0 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
      <div className="flex items-center gap-1.5">
        <span>{"\u{1F5C4}"}</span>
        <h2 className={`text-sm font-bold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>Data</h2>
      </div>
      <p className={`mt-0.5 text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
        {entities.length} entit{entities.length === 1 ? "y" : "ies"} · {access.length} access edges
      </p>
    </div>
  );

  if (focused) {
    const accessors = collectEntityAccessors(focused.id, access);
    const reads = accessors.filter((a) => a.mode === "read");
    const writes = accessors.filter((a) => a.mode === "write");
    const owner = focused.component_id ? (nameMap[focused.component_id] ?? focused.component_id) : null;
    return (
      <div className={containerClass} data-testid="lens-panel" data-lens="data">
        {header}
        <div className="flex-1 overflow-y-auto">
          <div className="px-3 pt-2.5">
            <button
              onClick={() => {
                clearEntity();
                selectComponent(null);
              }}
              className={`text-[11px] flex items-center gap-1 rounded px-1.5 py-0.5 ${darkMode ? "text-zinc-400 hover:bg-zinc-900" : "text-zinc-500 hover:bg-white"}`}
            >
              {"‹"} Entities
            </button>
          </div>

          <div className="px-4 pt-2 pb-3">
            <div className="flex items-center gap-2 flex-wrap">
              <KindBadge kind={focused.kind} darkMode={darkMode} />
              <h3 className={`text-sm font-bold truncate ${darkMode ? "text-zinc-100" : "text-zinc-900"}`} title={focused.id}>
                {focused.name}
              </h3>
            </div>
            {owner && (
              <p className={`mt-0.5 text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                defined in {owner}
              </p>
            )}
          </div>

          {/* Who touches this data: the lens's heart */}
          <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"} space-y-2`}>
            <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-emerald-500" : "text-emerald-600"}`}>
              Read by ({reads.length})
            </div>
            {reads.length === 0 ? (
              <p className={`text-[11px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>No readers detected.</p>
            ) : (
              <ul className="space-y-1">
                {reads.map((a, i) => (
                  <AccessorRow
                    key={`r-${a.accessorId}-${i}`}
                    name={nameMap[a.accessorId] ?? a.accessorId}
                    mode="read"
                    confidence={a.confidence}
                    darkMode={darkMode}
                  />
                ))}
              </ul>
            )}
          </div>

          <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"} space-y-2`}>
            <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-amber-500" : "text-amber-600"}`}>
              Written by ({writes.length})
            </div>
            {writes.length === 0 ? (
              <p className={`text-[11px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>No writers detected.</p>
            ) : (
              <ul className="space-y-1">
                {writes.map((a, i) => (
                  <AccessorRow
                    key={`w-${a.accessorId}-${i}`}
                    name={nameMap[a.accessorId] ?? a.accessorId}
                    mode="write"
                    confidence={a.confidence}
                    darkMode={darkMode}
                  />
                ))}
              </ul>
            )}
          </div>

          {focused.fields.length > 0 && (
            <div className={`px-4 py-3 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"} space-y-2`}>
              <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                Fields ({focused.fields.length})
              </div>
              <div className="flex flex-wrap gap-1">
                {focused.fields.map((f, i) => (
                  <span key={`${f.name}-${i}`} className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-300" : "bg-zinc-200 text-zinc-600"}`}>
                    {f.name}{f.type ? `: ${f.type}` : ""}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className={containerClass} data-testid="lens-panel" data-lens="data">
      {header}
      <div className={`px-4 py-2.5 text-[11px] leading-relaxed ${darkMode ? "text-zinc-400" : "text-zinc-500"}`}>
        Ranked by how many components touch each entity. Most-touched data first.
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-3">
        {groups.length === 0 && (
          <div className={`text-xs text-center py-6 ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
            No data entities in this dataset.
          </div>
        )}
        {groups.map((group) => (
          <div key={group.kind}>
            <div className={`px-2 py-1 text-[11px] font-semibold uppercase tracking-wider ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              {KIND_LABEL[group.kind]} ({group.items.length})
            </div>
            <ul className="space-y-1">
              {group.items.map((ent) => {
                const count = accessCountForEntity(ent.id, access);
                const owner = ent.component_id ? (nameMap[ent.component_id] ?? ent.component_id) : "unowned";
                return (
                  <li key={ent.id}>
                    <button
                      data-testid="lens-row"
                      data-lens="data"
                      data-row-id={ent.id}
                      data-selected={ent.id === selectedEntityId}
                      onClick={() => selectEntity(ent.id)}
                      className={`w-full text-left rounded-lg px-2.5 py-1.5 transition-colors ${darkMode ? "hover:bg-zinc-900" : "hover:bg-white"}`}
                    >
                      <div className="flex items-center gap-2">
                        <span className={`flex-1 text-xs font-medium truncate ${darkMode ? "text-zinc-200" : "text-zinc-800"}`} title={ent.id}>
                          {ent.name}
                        </span>
                        <Tooltip content="Components that read or write this entity.">
                          <span
                            className={`shrink-0 text-[10px] tabular-nums px-1.5 py-0.5 rounded ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-600"}`}
                          >
                            {count}
                          </span>
                        </Tooltip>
                      </div>
                      <div className={`mt-0.5 text-[10px] truncate ${darkMode ? "text-zinc-500" : "text-zinc-400"}`} title={owner}>
                        {owner}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
      <div className={`px-4 py-2 border-t shrink-0 text-[10px] ${darkMode ? "border-zinc-800 text-zinc-600" : "border-zinc-200 text-zinc-400"}`}>
        Grouped {ENTITY_KIND_ORDER.join(" · ")}; select an entity to see who touches it.
      </div>
    </div>
  );
}
