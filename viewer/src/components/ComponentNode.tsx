import { memo, useState, useRef, useEffect, type ReactNode } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { Component } from "../types";
import { getTypeColors, getLanguageColor, formatNumber, TYPE_META, isHeroType, getHeroGlow } from "../utils/layout";
import { useArchStore } from "../store";
import { Tooltip, TechTooltip } from "./Tooltip";
import { getTechRef, TYPE_DESCRIPTIONS, METRIC_DESCRIPTIONS } from "../utils/techDocs";

interface ComponentNodeData {
  component: Component;
  [key: string]: unknown;
}

// ─── Device Frame Components ───────────────────────────────────────────────────
// Each hero type gets a device-shaped frame. The frame wraps the shared content
// (header, purpose, patterns, metrics, children indicator) as {children}.

interface FrameProps {
  darkMode: boolean;
  colors: ReturnType<typeof getTypeColors>;
  children: ReactNode;
}

function MobileFrame({ darkMode, children }: FrameProps) {
  return (
    <div className={`
      relative rounded-[28px] border-[5px] min-w-[240px] max-w-[300px]
      ${darkMode ? "border-orange-700/60 bg-orange-950/40" : "border-orange-300 bg-orange-50"}
    `}>
      {/* Dynamic Island notch */}
      <div className="absolute top-[6px] left-1/2 -translate-x-1/2 z-10">
        <div className={`w-20 h-[7px] rounded-full ${darkMode ? "bg-orange-900/80" : "bg-orange-200"}`} />
      </div>
      {/* Volume buttons (left) */}
      <div className="absolute -left-[8px] top-[40px] flex flex-col gap-2">
        <div className={`w-[3px] h-5 rounded-full ${darkMode ? "bg-orange-700/50" : "bg-orange-300/80"}`} />
        <div className={`w-[3px] h-5 rounded-full ${darkMode ? "bg-orange-700/50" : "bg-orange-300/80"}`} />
      </div>
      {/* Power button (right) */}
      <div className="absolute -right-[8px] top-[50px]">
        <div className={`w-[3px] h-7 rounded-full ${darkMode ? "bg-orange-700/50" : "bg-orange-300/80"}`} />
      </div>
      {/* Screen area */}
      <div className={`rounded-[22px] overflow-hidden ${darkMode ? "bg-orange-950/60" : "bg-white"}`}>
        <div className="pt-4">
          {children}
        </div>
      </div>
    </div>
  );
}

function ServerFrame({ darkMode, colors, children }: FrameProps) {
  return (
    <div className={`
      relative rounded-md border-[3px] border-l-[5px] min-w-[280px] max-w-[360px]
      ${darkMode ? "border-green-600/50 border-l-green-500/70" : "border-green-300 border-l-green-500/60"}
      ${colors.bg}
    `}>
      {/* Rack top bar with LED status dots */}
      <div className={`flex items-center justify-between px-3 py-1.5 rounded-t-sm border-b
        ${darkMode ? "bg-green-950/50 border-green-800/30" : "bg-green-50 border-green-200"}`}>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-green-500 blink-led" />
          <div className="w-2 h-2 rounded-full bg-amber-500/70" />
          <span className={`font-mono text-[9px] ml-2 ${darkMode ? "text-green-500/70" : "text-green-600/70"}`}>
            $ ~/api
          </span>
        </div>
      </div>
      {/* Content */}
      <div className={darkMode ? "bg-green-950/30" : "bg-white"}>
        {children}
      </div>
    </div>
  );
}

function BrowserFrame({ darkMode, colors, children }: FrameProps) {
  return (
    <div className={`
      relative rounded-xl border-[3px] min-w-[280px] max-w-[360px]
      ${darkMode ? "border-sky-600/40" : "border-sky-300"}
      ${colors.bg}
    `}>
      {/* Title bar with traffic light dots */}
      <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg border-b
        ${darkMode ? "bg-sky-950/50 border-sky-800/30" : "bg-sky-50 border-sky-200"}`}>
        <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
        <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80" />
        <div className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
      </div>
      {/* URL bar */}
      <div className={`px-3 py-1 border-b
        ${darkMode ? "bg-sky-950/30 border-sky-800/20" : "bg-sky-50/50 border-sky-100"}`}>
        <div className={`h-4 rounded-md flex items-center px-2
          ${darkMode ? "bg-sky-900/40" : "bg-sky-100/80"}`}>
          <span className={`text-[9px] font-mono truncate ${darkMode ? "text-sky-500/60" : "text-sky-400"}`}>
            https://...
          </span>
        </div>
      </div>
      {/* Viewport */}
      <div className={darkMode ? "bg-sky-950/30" : "bg-white"}>
        {children}
      </div>
    </div>
  );
}

function WatchFrame({ darkMode, children }: FrameProps) {
  return (
    <div className={`
      relative rounded-[28px] border-[5px] min-w-[220px] max-w-[280px]
      ${darkMode ? "border-pink-700/50 bg-pink-950/30" : "border-pink-300 bg-pink-50"}
    `}>
      {/* Digital crown (right side) */}
      <div className="absolute -right-[9px] top-[35px]">
        <div className={`w-[4px] h-8 rounded-sm ${darkMode ? "bg-pink-700/60" : "bg-pink-300"}`} />
      </div>
      {/* Side button (below crown) */}
      <div className="absolute -right-[8px] top-[70px]">
        <div className={`w-[3px] h-4 rounded-sm ${darkMode ? "bg-pink-700/40" : "bg-pink-300/70"}`} />
      </div>
      {/* Screen area */}
      <div className={`rounded-[22px] overflow-hidden ${darkMode ? "bg-pink-950/40" : "bg-white"}`}>
        {/* Time display */}
        <div className={`text-center pt-2 pb-0.5 text-[9px] font-mono tracking-wider
          ${darkMode ? "text-pink-500/60" : "text-pink-400/80"}`}>
          12:00
        </div>
        {children}
      </div>
    </div>
  );
}

function DesktopFrame({ darkMode, colors, children }: FrameProps) {
  return (
    <div className={`
      relative rounded-lg border-[3px] min-w-[280px] max-w-[360px]
      ${darkMode ? "border-teal-600/40" : "border-teal-300"}
      ${colors.bg}
    `}>
      {/* Window title bar */}
      <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-t-md border-b
        ${darkMode ? "bg-teal-950/50 border-teal-800/30" : "bg-teal-50 border-teal-200"}`}>
        <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
        <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80" />
        <div className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
      </div>
      {/* Menu bar */}
      <div className={`flex items-center gap-3 px-3 py-0.5 text-[9px] border-b
        ${darkMode ? "bg-teal-950/30 border-teal-800/20 text-teal-600/60" : "bg-teal-50/50 border-teal-100 text-teal-500/60"}`}>
        <span>File</span><span>Edit</span><span>View</span><span>Help</span>
      </div>
      {/* Content */}
      <div className={darkMode ? "bg-teal-950/30" : "bg-white"}>
        {children}
      </div>
    </div>
  );
}

function TerminalFrame({ darkMode, colors, children }: FrameProps) {
  return (
    <div className={`
      relative rounded-lg border-[3px] min-w-[280px] max-w-[360px]
      ${darkMode ? "border-lime-700/40" : "border-lime-300"}
      ${colors.bg}
    `}>
      {/* Terminal header */}
      <div className={`flex items-center gap-2 px-3 py-1.5 rounded-t-md
        ${darkMode ? "bg-zinc-900" : "bg-zinc-800"}`}>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80" />
          <div className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
        </div>
        <span className="text-[10px] font-mono text-lime-400/80 ml-1">
          {">_"} terminal
        </span>
      </div>
      {/* Content */}
      <div className={darkMode ? "bg-zinc-900/60" : "bg-zinc-50"}>
        {children}
      </div>
    </div>
  );
}

function ServiceFrame({ darkMode, colors, children }: FrameProps) {
  return (
    <div className={`
      relative rounded-xl border-2 border-dashed min-w-[280px] max-w-[360px]
      ${darkMode ? "border-emerald-500/40" : "border-emerald-300"}
      ${colors.bg}
    `}>
      {/* Floating "live" status badge */}
      <div className={`absolute -top-2 -right-2 z-10 flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[8px] font-medium
        ${darkMode ? "bg-zinc-900 border border-emerald-700/40 text-emerald-400" : "bg-white border border-emerald-300 text-emerald-600"}`}>
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        <span>live</span>
      </div>
      {children}
    </div>
  );
}

function ScreenFrame({ darkMode, colors, children }: FrameProps) {
  return (
    <div className={`
      relative rounded-[20px] border-[3px] min-w-[240px] max-w-[300px]
      ${darkMode ? "border-cyan-600/50 bg-cyan-950/40" : "border-cyan-300 bg-cyan-50"}
    `}>
      {/* Mini status bar */}
      <div className={`flex items-center justify-between px-3 py-1 rounded-t-[16px] border-b
        ${darkMode ? "bg-cyan-950/60 border-cyan-800/30" : "bg-cyan-50 border-cyan-200"}`}>
        <div className={`text-[8px] font-mono ${darkMode ? "text-cyan-500/60" : "text-cyan-400/80"}`}>
          9:41
        </div>
        <div className="flex items-center gap-1">
          <div className={`w-3 h-1.5 rounded-sm ${darkMode ? "bg-cyan-600/40" : "bg-cyan-300/60"}`} />
        </div>
      </div>
      {/* Screen content */}
      <div className={`rounded-b-[16px] overflow-hidden ${darkMode ? "bg-cyan-950/30" : "bg-white"}`}>
        {children}
      </div>
    </div>
  );
}

function TabContainerFrame({ darkMode, colors, children }: FrameProps) {
  return (
    <div className={`
      relative rounded-xl border-2 min-w-[280px] max-w-[360px]
      ${darkMode ? "border-indigo-500/40" : "border-indigo-300"}
      ${colors.bg}
    `}>
      {/* Tab bar indicator */}
      <div className={`flex items-center justify-center gap-3 px-3 py-1.5 rounded-t-lg border-b
        ${darkMode ? "bg-indigo-950/50 border-indigo-800/30" : "bg-indigo-50 border-indigo-200"}`}>
        <div className={`w-4 h-4 rounded-sm ${darkMode ? "bg-indigo-600/40" : "bg-indigo-300/60"}`} />
        <div className={`w-4 h-4 rounded-sm ${darkMode ? "bg-indigo-600/40" : "bg-indigo-300/60"}`} />
        <div className={`w-4 h-4 rounded-sm ${darkMode ? "bg-indigo-600/40" : "bg-indigo-300/60"}`} />
      </div>
      {children}
    </div>
  );
}

function DeviceFrame({ type, darkMode, colors, children }: { type: string; darkMode: boolean; colors: ReturnType<typeof getTypeColors>; children: ReactNode }) {
  const props = { darkMode, colors, children };
  switch (type) {
    case "mobile-client":
    case "ios-client":
    case "android-client":
      return <MobileFrame {...props} />;
    case "api-server": return <ServerFrame {...props} />;
    case "web-client": return <BrowserFrame {...props} />;
    case "watch-app": return <WatchFrame {...props} />;
    case "desktop-app": return <DesktopFrame {...props} />;
    case "cli-tool": return <TerminalFrame {...props} />;
    case "service": return <ServiceFrame {...props} />;
    case "screen": return <ScreenFrame {...props} />;
    case "tab-container": return <TabContainerFrame {...props} />;
    case "tab": return <MobileFrame {...props} />;
    case "application":
      // Application: enhanced hero styling, no device frame
      return (
        <div className={`
          rounded-xl border-[3px] min-w-[280px] max-w-[360px] backdrop-blur-sm
          ${colors.bg} ${colors.border}
          ring-1 ring-offset-0 ${darkMode ? "ring-white/10" : "ring-black/10"}
        `}>
          {children}
        </div>
      );
    default:
      // Non-hero types (module, content, package, library, etc.)
      return (
        <div className={`
          rounded-xl border-2 min-w-[240px] max-w-[320px] backdrop-blur-sm
          ${colors.bg} ${colors.border}
          ${type === "content" ? "opacity-50" : ""}
        `}>
          {children}
        </div>
      );
  }
}

// ─── HoverCard ─────────────────────────────────────────────────────────────────

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
        {(docs.purpose || component.description) && (
          <p className={`text-[11px] leading-relaxed ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
            {docs.purpose || component.description}
          </p>
        )}

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

        {docs.tech_stack && docs.tech_stack.length > 0 && (
          <div>
            <div className={`text-[10px] font-semibold uppercase tracking-wider mb-1 ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              Tech Stack
            </div>
            <div className="flex flex-wrap gap-1">
              {docs.tech_stack.map((t, i) => {
                const ref = getTechRef(t);
                const badge = (
                  <span className={`
                    px-1.5 py-0.5 rounded text-[10px]
                    ${darkMode ? "bg-cyan-900/40 text-cyan-300" : "bg-cyan-100 text-cyan-700"}
                  `}>
                    {t}
                  </span>
                );
                return ref ? (
                  <TechTooltip key={i} name={t} description={ref.description} url={ref.url}>
                    {badge}
                  </TechTooltip>
                ) : (
                  <span key={i}>{badge}</span>
                );
              })}
            </div>
          </div>
        )}

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

// ─── Main Component Node ───────────────────────────────────────────────────────

export const ComponentNode = memo(function ComponentNode({
  data,
  selected,
}: NodeProps) {
  const { component } = data as ComponentNodeData;
  const { selectComponent, drillInto, darkMode, reviewMode, annotations, architecture } = useArchStore();
  const colors = getTypeColors(component.type, darkMode);
  const annotationCount = annotations.filter((a) => a.componentId === component.id).length;
  const connectionCount = architecture?.relationships.filter(
    (r) => r.source === component.id || r.target === component.id,
  ).length ?? 0;
  const hasChildren = component.children.length > 0 || component.files.length > 0;
  const langColor = component.language ? getLanguageColor(component.language) : null;
  const [hovered, setHovered] = useState(false);
  const hoverTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isHero = isHeroType(component.type);

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
        relative
        ${selected ? "node-selected" : ""}
        hover:scale-[1.02] transition-transform duration-150
        cursor-pointer
      `}
      style={isHero ? { boxShadow: getHeroGlow(component.type, darkMode) } : undefined}
      onClick={() => selectComponent(component.id)}
      onDoubleClick={() => hasChildren && drillInto(component)}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Handles on all 4 sides for intelligent edge routing */}
      <Handle id="target-left" type="target" position={Position.Left} className="!bg-zinc-500 !w-2 !h-2 !border-0" />
      <Handle id="target-top" type="target" position={Position.Top} className="!bg-zinc-500 !w-2 !h-2 !border-0" />
      <Handle id="target-right" type="target" position={Position.Right} className="!bg-zinc-500 !w-2 !h-2 !border-0" />
      <Handle id="target-bottom" type="target" position={Position.Bottom} className="!bg-zinc-500 !w-2 !h-2 !border-0" />
      <Handle id="source-left" type="source" position={Position.Left} className="!bg-zinc-500 !w-2 !h-2 !border-0" />
      <Handle id="source-top" type="source" position={Position.Top} className="!bg-zinc-500 !w-2 !h-2 !border-0" />
      <Handle id="source-right" type="source" position={Position.Right} className="!bg-zinc-500 !w-2 !h-2 !border-0" />
      <Handle id="source-bottom" type="source" position={Position.Bottom} className="!bg-zinc-500 !w-2 !h-2 !border-0" />

      {/* Hover documentation card */}
      {hovered && <HoverCard component={component} darkMode={darkMode} />}

      {/* Annotation badge */}
      {annotationCount > 0 && (
        <div className={`
          absolute -top-2 -right-2 z-20 min-w-[20px] h-[20px] flex items-center justify-center
          rounded-full text-[10px] font-bold
          ${darkMode ? "bg-blue-500 text-white" : "bg-blue-500 text-white"}
          ${reviewMode ? "ring-2 ring-blue-400/50 animate-pulse" : ""}
        `}>
          {annotationCount}
        </div>
      )}

      {/* Review mode indicator ring */}
      {reviewMode && annotationCount === 0 && (
        <div className={`
          absolute -top-1 -right-1 z-20 w-3 h-3 rounded-full
          ${darkMode ? "bg-blue-500/30 border border-blue-400/40" : "bg-blue-200 border border-blue-300"}
        `} />
      )}

      {/* Device-shaped frame wrapping all content */}
      <DeviceFrame type={component.type} darkMode={darkMode} colors={colors}>
        {/* Header */}
        <div className={isHero ? "px-4 pt-3 pb-2" : "px-4 pt-3 pb-2"}>
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <h3 className={`font-semibold truncate ${isHero ? "text-base" : "text-sm"} ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
                {TYPE_META[component.type]?.icon && <span className="mr-1.5">{TYPE_META[component.type].icon}</span>}
                {component.name}
              </h3>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                <Tooltip content={TYPE_DESCRIPTIONS[component.type] || component.type} position="bottom">
                  <span className={`${isHero ? "text-[11px] px-2 py-0.5" : "text-[10px] px-1.5 py-0.5"} rounded-full font-medium ${colors.badge}`}>
                    {TYPE_META[component.type]?.label || component.type}
                  </span>
                </Tooltip>
                {component.framework && (() => {
                  const ref = getTechRef(component.framework);
                  return ref ? (
                    <TechTooltip name={component.framework} description={ref.description} url={ref.url}>
                      <span className={`${isHero ? "text-[11px] font-medium" : "text-[10px]"} ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                        {component.framework}
                      </span>
                    </TechTooltip>
                  ) : (
                    <span className={`${isHero ? "text-[11px] font-medium" : "text-[10px]"} ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                      {component.framework}
                    </span>
                  );
                })()}
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

          {/* Purpose line */}
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
        <div className={`px-4 pb-3 flex items-center gap-3 text-[11px] flex-wrap ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
          {langColor && (() => {
            const langRef = component.language ? getTechRef(component.language) : null;
            const langEl = (
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: langColor }} />
                <span>{component.language}</span>
              </span>
            );
            return langRef ? (
              <TechTooltip name={component.language!} description={langRef.description} url={langRef.url}>
                {langEl}
              </TechTooltip>
            ) : langEl;
          })()}
          {component.metrics?.files > 0 && (
            <Tooltip content={METRIC_DESCRIPTIONS.files}>
              <span>{formatNumber(component.metrics.files)} files</span>
            </Tooltip>
          )}
          {component.metrics?.lines > 0 && (
            <Tooltip content={METRIC_DESCRIPTIONS.loc}>
              <span>{formatNumber(component.metrics.lines)} loc</span>
            </Tooltip>
          )}
          {component.port && (
            <Tooltip content="The network port this service listens on.">
              <span className={`font-mono ${darkMode ? "text-blue-400" : "text-blue-600"}`}>:{component.port}</span>
            </Tooltip>
          )}
          {docs?.readme && (
            <Tooltip content="This component has a README file with documentation.">
              <span className={`text-[9px] ${darkMode ? "text-green-600" : "text-green-500"}`}>
                DOC
              </span>
            </Tooltip>
          )}
          {docs?.api_endpoints && docs.api_endpoints.length > 0 && (
            <Tooltip content={`This component exposes ${docs.api_endpoints.length} API endpoint${docs.api_endpoints.length !== 1 ? "s" : ""}.`}>
              <span className={`text-[9px] ${darkMode ? "text-blue-600" : "text-blue-500"}`}>
                API
              </span>
            </Tooltip>
          )}
          {connectionCount > 0 && (
            <Tooltip content={METRIC_DESCRIPTIONS.conn}>
              <span className={darkMode ? "text-zinc-600" : "text-zinc-400"}>
                {connectionCount} conn
              </span>
            </Tooltip>
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
      </DeviceFrame>
    </div>
  );
});
