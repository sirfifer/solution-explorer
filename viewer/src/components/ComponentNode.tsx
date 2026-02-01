import { memo, useState, useRef, useEffect } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { Component } from "../types";
import { getTypeColors, getLanguageColor, formatNumber, TYPE_META } from "../utils/layout";
import { useArchStore } from "../store";

interface ComponentNodeData {
  component: Component;
  [key: string]: unknown;
}

function HoverCard({ component, darkMode }: { component: Component; darkMode: boolean }) {
  const docs = component.docs;
  if (!docs) return null;

  const hasDocs = docs.purpose || docs.readme || docs.patterns?.length || docs.tech_stack?.length
    || docs.api_endpoints?.length || docs.env_vars?.length || docs.architecture_notes;

  if (!hasDocs && !component.description) return null;

  return (
    <div
      className={`
        absolute left-1/2 -translate-x-1/2 bottom-full mb-2 z-50
        w-[360px] max-h-[320px] overflow-y-auto
        rounded-xl border shadow-2xl text-xs
        ${darkMode
          ? "bg-zinc-900/95 border-zinc-700 text-zinc-300"
          : "bg-white/95 border-zinc-200 text-zinc-700"
        }
        backdrop-blur-md
      `}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="p-3 space-y-2">
        {/* Purpose / Description */}
        {(docs.purpose || component.description) && (
          <p className={`text-[11px] leading-relaxed ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
            {docs.purpose || component.description}
          </p>
        )}

        {/* Patterns */}
        {docs.patterns && docs.patterns.length > 0 && (
          <div>
            <div className={`text-[10px] font-semibold uppercase tracking-wider mb-1 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              Patterns
            </div>
            <div className="flex flex-wrap gap-1">
              {docs.patterns.map((p, i) => (
                <span key={i} className={`
                  px-1.5 py-0.5 rounded text-[10px]
                  ${darkMode ? "bg-violet-900/40 text-violet-300" : "bg-violet-100 text-violet-700"}
                `}>
                  {p}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Tech Stack */}
        {docs.tech_stack && docs.tech_stack.length > 0 && (
          <div>
            <div className={`text-[10px] font-semibold uppercase tracking-wider mb-1 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              Tech Stack
            </div>
            <div className="flex flex-wrap gap-1">
              {docs.tech_stack.map((t, i) => (
                <span key={i} className={`
                  px-1.5 py-0.5 rounded text-[10px]
                  ${darkMode ? "bg-cyan-900/40 text-cyan-300" : "bg-cyan-100 text-cyan-700"}
                `}>
                  {t}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* API Endpoints */}
        {docs.api_endpoints && docs.api_endpoints.length > 0 && (
          <div>
            <div className={`text-[10px] font-semibold uppercase tracking-wider mb-1 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              API Endpoints ({docs.api_endpoints.length})
            </div>
            <div className="space-y-0.5">
              {docs.api_endpoints.slice(0, 5).map((ep, i) => (
                <div key={i} className="flex items-center gap-1.5 font-mono text-[10px]">
                  <span className={`px-1 rounded text-[9px] font-bold
                    ${ep.method === "GET" ? "bg-green-900/30 text-green-400" :
                      ep.method === "POST" ? "bg-blue-900/30 text-blue-400" :
                      ep.method === "DELETE" ? "bg-red-900/30 text-red-400" :
                      "bg-yellow-900/30 text-yellow-400"}
                  `}>
                    {ep.method}
                  </span>
                  <span className={darkMode ? "text-zinc-400" : "text-zinc-600"}>{ep.path}</span>
                </div>
              ))}
              {docs.api_endpoints.length > 5 && (
                <span className={`text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                  +{docs.api_endpoints.length - 5} more
                </span>
              )}
            </div>
          </div>
        )}

        {/* Env Vars */}
        {docs.env_vars && docs.env_vars.length > 0 && (
          <div>
            <div className={`text-[10px] font-semibold uppercase tracking-wider mb-1 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              Env Vars ({docs.env_vars.length})
            </div>
            <div className="flex flex-wrap gap-1">
              {docs.env_vars.slice(0, 8).map((v, i) => (
                <span key={i} className={`
                  font-mono px-1 py-0.5 rounded text-[9px]
                  ${darkMode ? "bg-amber-900/30 text-amber-300" : "bg-amber-100 text-amber-700"}
                `}>
                  {v}
                </span>
              ))}
              {docs.env_vars.length > 8 && (
                <span className={`text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                  +{docs.env_vars.length - 8} more
                </span>
              )}
            </div>
          </div>
        )}

        {/* Docs available indicator */}
        <div className={`flex gap-2 pt-1 border-t ${darkMode ? "border-zinc-800" : "border-zinc-100"}`}>
          {docs.readme && (
            <span className={`text-[9px] ${darkMode ? "text-green-500" : "text-green-600"}`}>README</span>
          )}
          {docs.claude_md && (
            <span className={`text-[9px] ${darkMode ? "text-purple-500" : "text-purple-600"}`}>CLAUDE.md</span>
          )}
          {docs.changelog && (
            <span className={`text-[9px] ${darkMode ? "text-blue-500" : "text-blue-600"}`}>CHANGELOG</span>
          )}
          {docs.architecture_notes && (
            <span className={`text-[9px] ${darkMode ? "text-orange-500" : "text-orange-600"}`}>Architecture</span>
          )}
        </div>
      </div>
    </div>
  );
}

export const ComponentNode = memo(function ComponentNode({
  data,
  selected,
}: NodeProps) {
  const { component } = data as ComponentNodeData;
  const { selectComponent, drillInto, darkMode } = useArchStore();
  const colors = getTypeColors(component.type, darkMode);
  const hasChildren = component.children.length > 0 || component.files.length > 0;
  const langColor = component.language ? getLanguageColor(component.language) : null;
  const [hovered, setHovered] = useState(false);
  const hoverTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (hoverTimeout.current) clearTimeout(hoverTimeout.current);
    };
  }, []);

  const handleMouseEnter = () => {
    hoverTimeout.current = setTimeout(() => setHovered(true), 400);
  };
  const handleMouseLeave = () => {
    if (hoverTimeout.current) clearTimeout(hoverTimeout.current);
    setHovered(false);
  };

  const docs = component.docs;
  const hasPatterns = docs?.patterns && docs.patterns.length > 0;

  return (
    <div
      className={`
        relative rounded-xl border-2 backdrop-blur-sm
        min-w-[240px] max-w-[320px]
        ${colors.bg} ${colors.border}
        ${selected ? "node-selected" : ""}
        ${component.type === "content" ? "opacity-50" : ""}
        hover:scale-[1.02] transition-transform duration-150
        cursor-pointer
      `}
      onClick={() => selectComponent(component.id)}
      onDoubleClick={() => hasChildren && drillInto(component)}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <Handle type="target" position={Position.Left} className="!bg-zinc-500 !w-2 !h-2 !border-0" />
      <Handle type="source" position={Position.Right} className="!bg-zinc-500 !w-2 !h-2 !border-0" />

      {/* Hover documentation card */}
      {hovered && <HoverCard component={component} darkMode={darkMode} />}

      {/* Header */}
      <div className="px-4 pt-3 pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <h3 className={`font-semibold text-sm truncate ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
              {TYPE_META[component.type]?.icon && <span className="mr-1.5">{TYPE_META[component.type].icon}</span>}
              {component.name}
            </h3>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${colors.badge}`}>
                {TYPE_META[component.type]?.label || component.type}
              </span>
              {component.framework && (
                <span className={`text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                  {component.framework}
                </span>
              )}
            </div>
          </div>
          {hasChildren && (
            <button
              className={`
                shrink-0 w-6 h-6 rounded-lg flex items-center justify-center
                text-xs font-bold
                ${darkMode ? "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200" : "bg-zinc-200 text-zinc-600 hover:bg-zinc-300"}
              `}
              onClick={(e) => {
                e.stopPropagation();
                drillInto(component);
              }}
              title="Drill into component"
            >
              &darr;
            </button>
          )}
        </div>

        {/* Purpose line (if available) */}
        {docs?.purpose && (
          <p className={`text-[10px] mt-1.5 leading-snug line-clamp-2 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            {docs.purpose}
          </p>
        )}
      </div>

      {/* Patterns badges */}
      {hasPatterns && (
        <div className="px-4 pb-1.5 flex flex-wrap gap-1">
          {docs!.patterns.slice(0, 3).map((p, i) => (
            <span key={i} className={`
              text-[9px] px-1.5 py-0.5 rounded
              ${darkMode ? "bg-violet-900/30 text-violet-400" : "bg-violet-50 text-violet-600"}
            `}>
              {p}
            </span>
          ))}
          {docs!.patterns.length > 3 && (
            <span className={`text-[9px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
              +{docs!.patterns.length - 3}
            </span>
          )}
        </div>
      )}

      {/* Metrics bar */}
      <div className={`px-4 pb-3 flex items-center gap-3 text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
        {langColor && (
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: langColor }} />
            <span>{component.language}</span>
          </div>
        )}
        {component.metrics?.files > 0 && (
          <span>{formatNumber(component.metrics.files)} files</span>
        )}
        {component.metrics?.lines > 0 && (
          <span>{formatNumber(component.metrics.lines)} loc</span>
        )}
        {component.port && (
          <span className={`font-mono ${darkMode ? "text-blue-400" : "text-blue-600"}`}>:{component.port}</span>
        )}
        {/* Doc indicators */}
        {docs?.readme && (
          <span className={`text-[9px] ${darkMode ? "text-green-600" : "text-green-500"}`} title="Has README">
            DOC
          </span>
        )}
        {docs?.api_endpoints && docs.api_endpoints.length > 0 && (
          <span className={`text-[9px] ${darkMode ? "text-blue-600" : "text-blue-500"}`} title="Has API endpoints">
            API
          </span>
        )}
      </div>

      {/* Children indicator */}
      {component.children.length > 0 && (
        <div className={`
          px-4 py-1.5 border-t text-[10px]
          ${darkMode ? "border-zinc-800/50 text-zinc-600" : "border-zinc-200 text-zinc-400"}
        `}>
          {component.children.length} sub-component{component.children.length !== 1 ? "s" : ""}
        </div>
      )}
    </div>
  );
});
