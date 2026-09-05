import { memo, useState, useRef, useEffect, useLayoutEffect, useCallback, useMemo, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  Handle,
  NodeToolbar,
  Position,
  useNodeId,
  useReactFlow,
  useViewport,
  type NodeProps,
} from "@xyflow/react";
import type { Component, AnnotationTarget, AnnotationTargetContext } from "../types";
import { getTypeColors, getLanguageColor, formatNumber, TYPE_META, isHeroType, getHeroGlow, ROLE_META, getRoleBadgeColors } from "../utils/layout";
import { getWorstStatusLevel, getStatusSummary } from "../utils/status";
import { useArchStore } from "../store";
import { THEMES } from "../utils/themes";
import { Tooltip, TechTooltip } from "./Tooltip";
import { getTechRef, getPatternRef, TYPE_DESCRIPTIONS, METRIC_DESCRIPTIONS } from "../utils/techDocs";
import { componentHelp, componentSummary } from "../utils/componentText";
import { StructuredExplanation } from "./StructuredExplanation";
import { useHoverDisclosure } from "../hooks/useHoverDisclosure";
import { useReadingSurfacePosition } from "../hooks/useReadingSurfacePosition";
import { readingSurfacePlacement, foreignNodeUnderPoint, pointInside } from "../utils/readingSurfacePlacement";

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
    <div data-se="card" className={`
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
    <div data-se="card" className={`
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
    <div data-se="card" className={`
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

function EnhancedMobileFrame({ darkMode, children }: FrameProps) {
  return (
    <div data-se="card" className={`
      relative w-[220px] min-h-[380px] rounded-[38px] border-[5px] flex flex-col
      ${darkMode ? "border-orange-700/60 bg-orange-950/40" : "border-orange-300 bg-orange-50"}
    `}
      style={{ boxShadow: darkMode ? "0 0 40px rgba(249, 115, 22, 0.12)" : "none" }}
    >
      {/* Dynamic Island notch with camera & sensor */}
      <div className="absolute top-[14px] left-1/2 -translate-x-1/2 z-10">
        <div className={`w-14 h-5 rounded-xl relative ${darkMode ? "bg-orange-950/90" : "bg-orange-200"}`}
          style={{ boxShadow: darkMode ? "inset 0 1px 4px rgba(0,0,0,0.8), 0 0.5px 0 rgba(255,200,150,0.08)" : "none" }}
        >
          {/* Camera */}
          <div className="absolute top-[6px] right-[14px] w-[9px] h-[9px] rounded-full"
            style={{ background: darkMode ? "radial-gradient(circle at 35% 35%, #282838, #101018)" : "radial-gradient(circle at 35% 35%, #e0e0f0, #b0b0c0)",
              boxShadow: darkMode ? "inset 0 0 3px rgba(100,120,255,0.5), 0 0 5px rgba(100,120,255,0.15)" : "inset 0 0 2px rgba(0,0,0,0.2)" }} />
          {/* Sensor */}
          <div className={`absolute top-[8px] left-[14px] w-[5px] h-[5px] rounded-full ${darkMode ? "bg-orange-950" : "bg-orange-300"}`} />
        </div>
      </div>
      {/* Silent switch */}
      <div className={`absolute -left-[5px] top-[48px] w-[4px] h-[16px] rounded-sm ${darkMode ? "bg-orange-700/50" : "bg-orange-300/80"}`}
        style={{ background: darkMode ? "linear-gradient(to left, hsl(20,45%,20%), hsl(20,45%,14%), hsl(20,45%,20%))" : undefined }} />
      {/* Volume buttons */}
      <div className="absolute -left-[5px] top-[70px] flex flex-col gap-3">
        <div className={`w-[4px] h-7 rounded-sm ${darkMode ? "" : "bg-orange-300/80"}`}
          style={{ background: darkMode ? "linear-gradient(to left, hsl(20,45%,20%), hsl(20,45%,14%), hsl(20,45%,20%))" : undefined }} />
        <div className={`w-[4px] h-7 rounded-sm ${darkMode ? "" : "bg-orange-300/80"}`}
          style={{ background: darkMode ? "linear-gradient(to left, hsl(20,45%,20%), hsl(20,45%,14%), hsl(20,45%,20%))" : undefined }} />
      </div>
      {/* Power button */}
      <div className={`absolute -right-[5px] top-[72px] w-[4px] h-[38px] rounded-sm ${darkMode ? "" : "bg-orange-300/80"}`}
        style={{ background: darkMode ? "linear-gradient(to right, hsl(20,45%,20%), hsl(20,45%,14%), hsl(20,45%,20%))" : undefined }} />
      {/* Screen */}
      <div className={`rounded-[28px] overflow-hidden relative flex-1 flex flex-col ${darkMode ? "bg-orange-950/60" : "bg-white"}`}>
        {/* Screen reflection */}
        <div className="absolute inset-0 rounded-[28px] pointer-events-none z-[5]"
          style={{ background: darkMode ? "linear-gradient(160deg, rgba(255,230,200,0.05) 0%, rgba(255,230,200,0.02) 20%, transparent 40%)" : "none" }} />
        {/* Status bar */}
        <div className="flex justify-between items-center px-5 pt-1.5 pb-0.5 relative z-[4]">
          <span className={`text-[10px] font-semibold font-sans ${darkMode ? "text-orange-700/80" : "text-orange-400"}`}>9:41</span>
          <div className="flex items-center gap-1">
            <div className="flex gap-px items-end">
              <div className={`w-[2px] rounded-[0.5px] ${darkMode ? "bg-orange-700/60" : "bg-orange-300"}`} style={{ height: "4px" }} />
              <div className={`w-[2px] rounded-[0.5px] ${darkMode ? "bg-orange-700/60" : "bg-orange-300"}`} style={{ height: "6px" }} />
              <div className={`w-[2px] rounded-[0.5px] ${darkMode ? "bg-orange-700/60" : "bg-orange-300"}`} style={{ height: "8px" }} />
              <div className={`w-[2px] rounded-[0.5px] ${darkMode ? "bg-orange-700/60" : "bg-orange-300"}`} style={{ height: "10px" }} />
            </div>
            <div className={`w-4 h-2 rounded-sm relative flex items-center p-px ${darkMode ? "border border-orange-700/50" : "border border-orange-300"}`}>
              <div className={`w-[70%] h-full rounded-[1px] ${darkMode ? "bg-orange-700/60" : "bg-orange-300"}`} />
              <div className={`absolute -right-[3px] top-1/2 -translate-y-1/2 w-[2px] h-1 rounded-r-sm ${darkMode ? "bg-orange-700/50" : "bg-orange-300"}`} />
            </div>
          </div>
        </div>
        {/* Content */}
        <div className="flex-1 pt-1">
          {children}
        </div>
        {/* Home indicator */}
        <div className={`w-20 h-1 rounded-full mx-auto mb-2 mt-1.5 ${darkMode ? "bg-orange-700/30" : "bg-orange-300/50"}`} />
      </div>
    </div>
  );
}

function EnhancedWatchFrame({ darkMode, children }: FrameProps) {
  return (
    <div data-se="card" className={`
      relative w-[200px] rounded-[48px] border-[5px] mt-[22px] mb-[22px]
      ${darkMode ? "border-pink-700/50 bg-pink-950/30" : "border-pink-300 bg-pink-50"}
    `}
      style={{ boxShadow: darkMode ? "0 0 50px rgba(236, 72, 153, 0.15)" : "none" }}
    >
      {/* Band top */}
      <div className={`absolute left-1/2 -translate-x-1/2 -top-[22px] w-[52%] h-[22px] rounded-[5px] ${darkMode ? "bg-pink-800/30" : "bg-pink-200/60"}`} />
      {/* Crown */}
      <div className={`absolute -right-[9px] top-[30px] w-1 h-8 rounded-sm ${darkMode ? "bg-pink-700/60" : "bg-pink-300"}`} />
      {/* Side button */}
      <div className={`absolute -right-[8px] top-[70px] w-[3px] h-4 rounded-sm ${darkMode ? "bg-pink-700/40" : "bg-pink-300/70"}`} />
      {/* Screen */}
      <div className={`rounded-[42px] overflow-hidden relative ${darkMode ? "bg-pink-950/40" : "bg-white"}`}>
        {/* Screen reflection */}
        <div className="absolute inset-0 rounded-[42px] pointer-events-none z-[5]"
          style={{ background: darkMode ? "linear-gradient(160deg, rgba(255,200,230,0.05) 0%, rgba(255,200,230,0.02) 20%, transparent 40%)" : "none" }} />
        {/* Time */}
        <div className={`text-center pt-2.5 pb-0.5 text-[10px] font-semibold font-sans tracking-wider ${darkMode ? "text-pink-500/70" : "text-pink-400/80"}`}>
          12:00
        </div>
        <div className="pb-[18px]">
          {children}
        </div>
      </div>
      {/* Band bottom */}
      <div className={`absolute left-1/2 -translate-x-1/2 -bottom-[22px] w-[52%] h-[22px] rounded-[5px] ${darkMode ? "bg-pink-800/30" : "bg-pink-200/60"}`} />
    </div>
  );
}

function WatchFrame({ darkMode, children }: FrameProps) {
  return (
    <div data-se="card" className={`
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
    <div data-se="card" className={`
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
    <div data-se="card" className={`
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
    <div data-se="card" className={`
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

function ScreenFrame({ darkMode, children }: FrameProps) {
  return (
    <div data-se="card" className={`
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
    <div data-se="card" className={`
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

function DeviceFrame({ type, darkMode, colors, enhancedFrames, heroGlow, children }: { type: string; darkMode: boolean; colors: ReturnType<typeof getTypeColors>; enhancedFrames: boolean; heroGlow?: string; children: ReactNode }) {
  const props = { darkMode, colors, children };
  // Wrap frame in a div that applies the hero glow with matching border-radius
  const withGlow = (frame: ReactNode, borderRadius: string) => {
    if (!heroGlow || heroGlow === "none") return frame;
    return <div style={{ boxShadow: heroGlow, borderRadius }}>{frame}</div>;
  };
  switch (type) {
    case "mobile-client":
    case "ios-client":
    case "android-client":
      return withGlow(
        enhancedFrames ? <EnhancedMobileFrame {...props} /> : <MobileFrame {...props} />,
        enhancedFrames ? "38px" : "28px"
      );
    case "api-server": return withGlow(<ServerFrame {...props} />, "6px");
    case "web-client": return withGlow(<BrowserFrame {...props} />, "12px");
    case "watch-app": return withGlow(
      enhancedFrames ? <EnhancedWatchFrame {...props} /> : <WatchFrame {...props} />,
      enhancedFrames ? "48px" : "28px"
    );
    case "desktop-app": return withGlow(<DesktopFrame {...props} />, "8px");
    case "cli-tool": return withGlow(<TerminalFrame {...props} />, "8px");
    case "service": return withGlow(<ServiceFrame {...props} />, "12px");
    case "screen": return withGlow(<ScreenFrame {...props} />, "20px");
    case "tab-container": return withGlow(<TabContainerFrame {...props} />, "12px");
    case "tab": return withGlow(
      enhancedFrames ? <EnhancedMobileFrame {...props} /> : <MobileFrame {...props} />,
      enhancedFrames ? "38px" : "28px"
    );
    case "application":
      // Application: enhanced hero styling, no device frame
      return withGlow(
        <div data-se="card" className={`
          rounded-xl border-[3px] min-w-[280px] max-w-[360px] backdrop-blur-sm
          ${colors.bg} ${colors.border}
          ring-1 ring-offset-0 ${darkMode ? "ring-white/10" : "ring-black/10"}
        `}>
          {children}
        </div>,
        "12px"
      );
    default:
      // Non-hero types (module, content, package, library, etc.)
      return (
        <div data-se="card" className={`
          rounded-xl border-2 min-w-[240px] max-w-[320px] backdrop-blur-sm
          ${colors.bg} ${colors.border}
          ${type === "content" ? "opacity-50" : ""}
        `}>
          {children}
        </div>
      );
  }
}

// ─── ReviewTarget ──────────────────────────────────────────────────────────────
// Wraps individual visual elements in review mode to make them annotatable.

function ReviewTarget({
  targetType, targetId, targetName, componentId, targetContext, children, className,
}: {
  targetType: AnnotationTarget;
  targetId: string;
  targetName: string;
  componentId: string;
  targetContext?: AnnotationTargetContext;
  children: ReactNode;
  className?: string;
}) {
  const { reviewMode, setAnnotatingTarget, annotations } = useArchStore();
  if (!reviewMode) return <>{children}</>;

  const hasAnnotation = annotations.some(
    (a) => a.targetType === targetType && a.targetId === targetId
  );

  return (
    <span
      className={`
        relative cursor-pointer group/rt inline-flex items-center
        ${hasAnnotation
          ? "ring-1 ring-blue-500/50 rounded-sm bg-blue-500/10"
          : "hover:ring-1 hover:ring-blue-400/30 rounded-sm"
        }
        ${className ?? ""}
      `}
      onClick={(e) => {
        e.stopPropagation();
        setAnnotatingTarget({
          type: targetType,
          id: targetId,
          name: targetName,
          componentId,
          targetContext,
        });
      }}
      title={`Add feedback for ${targetName}`}
    >
      {children}
      {hasAnnotation && (
        <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-blue-500 z-10" />
      )}
    </span>
  );
}

// ─── HoverCard ─────────────────────────────────────────────────────────────────

/** Gap kept between the preview and both the node and the canvas edge. */
export const PREVIEW_PAD = 8;

function HoverCard({ component, darkMode, triggerRef, surfaceRef, onEnter, onLeave, coarsePointer }: {
  component: Component;
  darkMode: boolean;
  triggerRef: React.RefObject<HTMLDivElement | null>;
  surfaceRef: React.RefObject<HTMLDivElement | null>;
  onEnter: () => void;
  onLeave: () => void;
  coarsePointer: boolean;
}) {
  // The anchor comes from React Flow, not from the DOM: getNodesBounds gives
  // this node's measured bounds and flowToScreenPosition puts them on screen
  // through the one viewport transform the app has. That is the same rect
  // NodeToolbar itself will position against, so the residual clamp below
  // cannot disagree with where the engine actually draws the card. Subscribing
  // to the viewport re-runs it while the reader pans, which the old
  // fixed-position portal never did.
  const nodeId = useNodeId();
  const { getNodesBounds, flowToScreenPosition } = useReactFlow();
  useViewport();
  // Measured rather than assumed: the card's height depends on how much
  // documentation the component carries, and clamping against the maximum
  // would push a short card below a node it would have fitted above. Hooks stay
  // above the early returns below (rules of hooks).
  const cardRef = surfaceRef;
  const [card, setCard] = useState({ width: 360, height: 320 });
  useLayoutEffect(() => {
    const element = cardRef.current;
    if (!element) return;
    // Layout dimensions are independent of our translated screen position.
    // Measuring the transformed rectangle can alternate fractional values at
    // graph zoom levels and feed an endless measurement/render cycle.
    const box = { width: element.offsetWidth, height: element.offsetHeight };
    setCard((prev) =>
      prev.width === box.width && prev.height === box.height
        ? prev
        : { width: box.width, height: box.height },
    );
  });

  const docs = component.docs ?? {};
  const summary = componentSummary(component);

  const hasDocs = docs.purpose || docs.readme || docs.patterns?.length || docs.tech_stack?.length
    || docs.api_endpoints?.length || docs.env_vars?.length || docs.architecture_notes;
  const hasExplanation = Boolean(
    component.ai_enhance?.explanation
    && Object.keys(component.ai_enhance.explanation).length > 0
  ) || Boolean(component.ai_enhance?.honest_gaps?.length);

  if (!hasDocs && !summary && !hasExplanation) return null;

  const bounds = nodeId ? getNodesBounds([nodeId]) : null;
  if (!bounds || bounds.width <= 0 || bounds.height <= 0) return null;
  const topLeft = flowToScreenPosition({ x: bounds.x, y: bounds.y });
  const bottomRight = flowToScreenPosition({
    x: bounds.x + bounds.width,
    y: bounds.y + bounds.height,
  });
  const canvas = triggerRef.current?.closest(".react-flow")?.getBoundingClientRect() ?? null;
  const placement = readingSurfacePlacement(
    { left: topLeft.x, right: bottomRight.x, top: topLeft.y, bottom: bottomRight.y },
    canvas ?? { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight },
    { width: 400, height: Math.min(420, (cardRef.current?.scrollHeight ?? 420) + 2) },
  );
  const flipBelow = placement.side === "bottom";
  const shiftX = placement.left - ((topLeft.x + bottomRight.x) / 2 - card.width / 2);
  const shiftY = placement.top - (flipBelow ? bottomRight.y + PREVIEW_PAD : topLeft.y - PREVIEW_PAD - card.height);

  const preview = (
    <div
      ref={cardRef}
      data-testid="node-preview"
      data-component-id={component.id}
      role="region"
      aria-label={`Preview of ${component.name}`}
      className={`
        nowheel nopan se-reading-surface
        w-[min(400px,calc(100vw-16px))] max-h-[min(420px,calc(100vh-16px))] overflow-y-auto
        rounded-xl border shadow-2xl text-xs
        ${darkMode
          ? "bg-zinc-900/95 border-zinc-700 text-zinc-300"
          : "bg-white/95 border-zinc-200 text-zinc-700"
        }
        backdrop-blur-md
      `}
      // Deaf to the pointer until the reader is demonstrably on it, and never
      // while it rests on another node. A surface that took pointer events the
      // moment it appeared would hold the clicks of whatever it happened to
      // cover, which is how the depth-5 drill became unreachable. The window
      // listener that owns the hover lifecycle turns this on and off; it is
      // set on the element rather than through state so the change is in
      // effect for the very next hit test rather than after a render.
      //
      // A coarse pointer has no hover to disambiguate: the card is summoned
      // deliberately by touch and hold, and that listener does not run. It
      // stays reachable, exactly as it was before.
      style={{ transform: `translate(${shiftX}px, ${shiftY}px)`, width: placement.width, maxHeight: placement.maxHeight, pointerEvents: coarsePointer ? "auto" : "none" }}
      onClick={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
      onPointerMove={(e) => e.stopPropagation()}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      onFocus={onEnter}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) onLeave(); }}
    >
      <div className="p-4 space-y-3">
        <header className={`border-b pb-3 ${darkMode ? "border-zinc-700" : "border-zinc-200"}`}>
          <h3 className="text-base font-semibold se-info-title">{component.name}</h3>
          <p className="mt-1 text-xs se-info-meta">
            {TYPE_META[component.type]?.label || component.type}
            {component.language ? ` · ${component.language}` : ""}
            {component.metrics?.files ? ` · ${formatNumber(component.metrics.files)} files` : ""}
            {component.metrics?.lines ? ` · ${formatNumber(component.metrics.lines)} lines` : ""}
          </p>
        </header>

        <StructuredExplanation
          explanation={component.ai_enhance?.explanation}
          fallback={summary}
          honestGaps={component.ai_enhance?.honest_gaps}
          stale={component.ai_enhance?.stale}
          compact
        />

        {docs.patterns && docs.patterns.length > 0 && (
          <div>
            <div className="se-info-heading">
              Patterns
            </div>
            <div className="flex flex-wrap gap-1">
              {docs.patterns.map((p, i) => {
                const pRef = getPatternRef(p);
                const badge = (
                  <span className={`
                    px-1.5 py-0.5 rounded text-xs
                    ${darkMode ? "bg-violet-900/40 text-violet-300" : "bg-violet-100 text-violet-700"}
                  `}>
                    {p}
                  </span>
                );
                return pRef ? (
                  <TechTooltip key={i} name={p} description={pRef.description} url={pRef.url}>
                    {badge}
                  </TechTooltip>
                ) : (
                  <span key={i}>{badge}</span>
                );
              })}
            </div>
          </div>
        )}

        {docs.tech_stack && docs.tech_stack.length > 0 && (
          <div>
            <div className="se-info-heading">
              Tech Stack
            </div>
            <div className="flex flex-wrap gap-1">
              {docs.tech_stack.map((t, i) => {
                const ref = getTechRef(t);
                const badge = (
                  <span className={`
                    px-1.5 py-0.5 rounded text-xs
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
            <div className="se-info-heading">
              API Endpoints ({docs.api_endpoints.length})
            </div>
            <div className="space-y-0.5">
              {docs.api_endpoints.slice(0, 5).map((ep, i) => (
                <div key={i} className="flex items-center gap-1.5 font-mono text-xs">
                  <span className={`px-1 rounded text-[11px] font-bold
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
                <span className="text-xs se-info-meta">
                  +{docs.api_endpoints.length - 5} more
                </span>
              )}
            </div>
          </div>
        )}

        {docs.env_vars && docs.env_vars.length > 0 && (
          <div>
            <div className="se-info-heading">
              Env Vars ({docs.env_vars.length})
            </div>
            <div className="flex flex-wrap gap-1">
              {docs.env_vars.slice(0, 8).map((v, i) => (
                <span key={i} className={`
                  font-mono px-1 py-0.5 rounded text-[11px]
                  ${darkMode ? "bg-amber-900/30 text-amber-300" : "bg-amber-100 text-amber-700"}
                `}>
                  {v}
                </span>
              ))}
              {docs.env_vars.length > 8 && (
                <span className="text-xs se-info-meta">
                  +{docs.env_vars.length - 8} more
                </span>
              )}
            </div>
          </div>
        )}

        <div className={`flex gap-2 pt-1 border-t ${darkMode ? "border-zinc-800" : "border-zinc-100"}`}>
          {docs.readme && (
            <span className={`text-xs ${darkMode ? "text-green-400" : "text-green-700"}`}>README</span>
          )}
          {docs.claude_md && (
            <span className={`text-xs ${darkMode ? "text-purple-400" : "text-purple-700"}`}>CLAUDE.md</span>
          )}
          {docs.changelog && (
            <span className={`text-xs ${darkMode ? "text-blue-400" : "text-blue-700"}`}>CHANGELOG</span>
          )}
          {docs.architecture_notes && (
            <span className={`text-xs ${darkMode ? "text-orange-400" : "text-orange-700"}`}>Architecture</span>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <NodeToolbar
      isVisible
      position={flipBelow ? Position.Bottom : Position.Top}
      offset={PREVIEW_PAD}
      align="center"
      // React Flow gives the toolbar wrapper pointer-events of its own, and
      // the wrapper is wider and taller than the card it holds. Left alone it
      // catches presses meant for whatever the card is floating over, which
      // the card itself no longer does. Only the card decides, below.
      style={{ pointerEvents: "none" }}
    >
      {preview}
    </NodeToolbar>
  );
}

// ─── Help Popover ─────────────────────────────────────────────────────────────
// Click-triggered popover showing help text for any component. Shows AI-enhanced
// help_text when available, falls back to docs.purpose / description / README excerpt.

function getHelpContent(component: Component): string | null {
  return componentHelp(component);
}

function HelpPopover({ component, darkMode, triggerRef, onClose }: {
  component: Component;
  darkMode: boolean;
  triggerRef: React.RefObject<HTMLDivElement | null>;
  onClose: () => void;
}) {
  const helpText = getHelpContent(component);
  const ai = component.ai_enhance;
  const popoverRef = useRef<HTMLDivElement>(null);
  const placement = useReadingSurfacePosition(triggerRef, popoverRef, true, "bottom", 380);
  const positioned = placement !== null;
  useLayoutEffect(() => {
    if (positioned) popoverRef.current?.focus();
  }, [positioned]);

  useEffect(() => {
    const trigger = triggerRef.current?.querySelector<HTMLButtonElement>("button");
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!popoverRef.current?.contains(target) && !triggerRef.current?.contains(target)) onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("pointerdown", onPointerDown);
      // Do not take focus away from another control the reader clicked.
      if (document.activeElement === document.body || popoverRef.current?.contains(document.activeElement)) trigger?.focus();
    };
  }, [onClose, triggerRef]);

  if (!helpText && !ai?.explanation && !ai?.honest_gaps?.length) return null;
  const roleMeta = ai?.architectural_role ? ROLE_META[ai.architectural_role] : null;

  const rect = triggerRef.current?.getBoundingClientRect();
  if (!rect) return null;

  return createPortal(
    <div
      ref={popoverRef}
      role="dialog"
      tabIndex={-1}
      aria-label={`About ${component.name}`}
      className={`
        fixed z-[9999] pointer-events-auto nowheel nopan se-reading-surface
        w-[min(380px,calc(100vw-16px))] max-h-[min(420px,calc(100vh-16px))] overflow-y-auto rounded-xl border shadow-2xl text-xs
        ${darkMode
          ? "bg-zinc-900/95 border-zinc-700 text-zinc-300"
          : "bg-white/95 border-zinc-200 text-zinc-700"
        }
        backdrop-blur-md
      `}
      style={{
        left: placement?.left ?? rect.left,
        top: placement?.top ?? rect.bottom + 8,
        width: placement?.width,
        maxHeight: placement?.maxHeight,
        visibility: placement ? "visible" : "hidden",
      }}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="p-4 space-y-3">
        <header className={`border-b pb-3 ${darkMode ? "border-zinc-700" : "border-zinc-200"}`}>
          <div className="flex items-start justify-between gap-3">
            <h3 className="text-base font-semibold se-info-title">{component.name}</h3>
            <button type="button" className="se-node-control shrink-0 rounded se-info-meta" aria-label="Close component information" onClick={onClose}>×</button>
          </div>
          <p className="mt-1 text-xs se-info-meta">
            {TYPE_META[component.type]?.label || component.type}
            {component.language ? ` · ${component.language}` : ""}
          </p>
        </header>
        {/* Role and criticality badges */}
        {(roleMeta || ai?.criticality) && (
          <div className="flex items-center gap-2 flex-wrap">
            {roleMeta && ai?.architectural_role && (
              <span className={`text-xs px-2 py-1 rounded-full font-medium ${getRoleBadgeColors(ai.architectural_role, darkMode)}`}>
                {roleMeta.icon} {roleMeta.label}
              </span>
            )}
            {ai?.criticality && (
              <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                ai.criticality === "critical"
                  ? (darkMode ? "bg-red-900/40 text-red-300" : "bg-red-100 text-red-700")
                  : ai.criticality === "important"
                    ? (darkMode ? "bg-amber-900/40 text-amber-300" : "bg-amber-100 text-amber-700")
                    : (darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500")
              }`}>
                {ai.criticality}
              </span>
            )}
          </div>
        )}

        <StructuredExplanation
          explanation={ai?.explanation}
          fallback={helpText}
          honestGaps={ai?.honest_gaps}
          stale={ai?.stale}
          showEvidence
          compact
        />

        {/* Data handled */}
        {ai?.data_handled && !ai.explanation?.data_handled && (
          <div>
            <div className="se-info-heading">
              Data Handled
            </div>
            <p className="se-info-body">
              {ai.data_handled}
            </p>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}

// ─── Main Component Node ───────────────────────────────────────────────────────

export const ComponentNode = memo(function ComponentNode({
  data,
  selected,
}: NodeProps) {
  const { component } = data as ComponentNodeData;
  // Capability lens (P6-3): per-kind capability counts attached to owner nodes,
  // rendered as a badge cluster. Present only under the Capability lens.
  const capBadges = (data as { capBadges?: Record<string, number> }).capBadges;
  // Rules lens (P6-6): per-kind rule counts attached to rule-owning nodes,
  // rendered as a badge cluster (the same pattern). Present only under the Rules
  // lens.
  const ruleBadges = (data as { ruleBadges?: Record<string, number> }).ruleBadges;
  // Selector-based subscriptions so a node re-renders only when the slice it
  // actually reads changes, instead of on every store mutation (F-VW-6). Actions
  // are stable references; the primitives below only fire a re-render when their
  // value changes for THIS component.
  const selectComponent = useArchStore((s) => s.selectComponent);
  const drillInto = useArchStore((s) => s.drillInto);
  const darkMode = useArchStore((s) => s.darkMode);
  const enhancedFrames = useArchStore((s) => s.enhancedFrames);
  const theme = useArchStore((s) => s.theme);
  const reviewMode = useArchStore((s) => s.reviewMode);
  // Subscribe to the annotations array reference and filter in render: a
  // filtering selector would re-run for every node on every store update
  // (Zustand re-runs selectors to compare), while the array reference only
  // changes on rare annotation edits, so unrelated updates like status polls
  // cost nothing here.
  const annotations = useArchStore((s) => s.annotations);
  const annotationCount = useMemo(
    () => annotations.filter((a) => a.componentId === component.id).length,
    [annotations, component.id],
  );
  // Connection counts come from the store's precomputed map, refreshed only on
  // relationship changes, so status-overlay polls do not re-filter per node.
  const incomingCount = useArchStore((s) => s.connectionCounts[component.id]?.incoming ?? 0);
  const outgoingCount = useArchStore((s) => s.connectionCounts[component.id]?.outgoing ?? 0);
  const colors = getTypeColors(component.type, darkMode);
  const connectionCount = incomingCount + outgoingCount;
  const hasChildren = component.children.length > 0 || component.files.length > 0;
  const langColor = component.language ? getLanguageColor(component.language) : null;
  const { visible: hovered, enter: enterPreview, retain: retainPreview, leave: leavePreview, dismiss: dismissPreview } = useHoverDisclosure(400);
  const [showHelp, setShowHelp] = useState(false);
  const longPressTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nodeRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const helpButtonRef = useRef<HTMLDivElement>(null);
  const isHero = isHeroType(component.type);
  const glowsInThisTheme = THEMES[theme].heroGlow;
  const hasHelpContent = Boolean(
    getHelpContent(component)
    || component.ai_enhance?.explanation
    || component.ai_enhance?.honest_gaps?.length
  );
  const isTouchDevice = typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches;

  useEffect(() => {
    return () => {
      if (longPressTimeout.current) clearTimeout(longPressTimeout.current);
    };
  }, []);

  // A preview can open with no gesture behind it: arriving in the workbench from
  // the Overview draws a node under wherever the pointer was left, and the
  // browser treats that as an enter. Nothing then guarantees the matching leave,
  // so the popup can outlive the reason it appeared. Moving outside both the
  // node and its reading surface starts dismissal. Coarse pointers are left alone, so the 500ms
  // touch-and-hold path is unchanged.
  useEffect(() => {
    if (!hovered || isTouchDevice) return;
    const onPointerMove = (e: PointerEvent) => {
      const node = nodeRef.current;
      const surface = previewRef.current;
      const target = e.target as Node;
      // The surface floats over the canvas and routinely comes to rest on
      // other nodes. It may take the pointer only where the reader is on it
      // and nothing of the graph is underneath; anywhere else it stays deaf so
      // the node beneath keeps its own clicks. Reading the stack rather than
      // the topmost element is what makes this work once the surface is live,
      // because by then the surface is what the pointer lands on.
      let onSurface = false;
      if (surface) {
        onSurface = (surface.contains(target) || pointInside(surface, e.clientX, e.clientY))
          && !foreignNodeUnderPoint(e.clientX, e.clientY, component.id);
        surface.style.pointerEvents = onSurface ? "auto" : "none";
      }
      if (node?.contains(target) || onSurface) retainPreview();
      else leavePreview();
    };
    window.addEventListener("pointermove", onPointerMove);
    return () => window.removeEventListener("pointermove", onPointerMove);
  }, [hovered, isTouchDevice, retainPreview, leavePreview, component.id]);

  const handleMouseEnter = () => {
    if (isTouchDevice) return;
    if (showHelp) return;
    if (hovered) retainPreview();
    else enterPreview();
  };
  const handleMouseLeave = () => {
    leavePreview();
  };

  // Long-press on touch devices shows hover card
  const handleTouchStart = useCallback(() => {
    longPressTimeout.current = setTimeout(retainPreview, 500);
  }, [retainPreview]);
  const handleTouchEnd = useCallback(() => {
    if (longPressTimeout.current) clearTimeout(longPressTimeout.current);
  }, []);
  const handleTouchMove = useCallback(() => {
    if (longPressTimeout.current) clearTimeout(longPressTimeout.current);
  }, []);
  const closeHelp = useCallback(() => setShowHelp(false), []);

  const docs = component.docs;
  const summary = componentSummary(component);
  const hasPatterns = docs?.patterns && docs.patterns.length > 0;

  return (
    <div
      ref={nodeRef}
      data-testid="graph-node"
      data-component-id={component.id}
      data-selected={Boolean(selected)}
      data-has-children={hasChildren}
      className={`
        relative
        ${selected ? "node-selected" : ""}
        hover:scale-[1.02] transition-transform duration-150
        cursor-pointer
      `}
      onClick={() => { dismissPreview(); selectComponent(component.id); }}
      onDoubleClick={() => hasChildren && drillInto(component)}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      onTouchMove={handleTouchMove}
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
      {hovered && !showHelp && <HoverCard component={component} darkMode={darkMode} triggerRef={nodeRef} surfaceRef={previewRef} onEnter={retainPreview} onLeave={leavePreview} coarsePointer={isTouchDevice} />}

      {/* Capability badges (P6-3): counts by kind on capability-owning nodes */}
      {capBadges && (
        <div className="absolute -top-2 -left-2 z-20 flex items-center gap-1">
          {(["api", "cli", "event", "job"] as const)
            .filter((k) => (capBadges[k] ?? 0) > 0)
            .map((k) => (
              <span
                key={k}
                className={`px-1.5 h-5 flex items-center rounded-full text-[11px] font-bold uppercase tracking-wide shadow-sm ${
                  darkMode ? "bg-cyan-500 text-white" : "bg-cyan-600 text-white"
                }`}
                title={`${capBadges[k]} ${k} capabilit${capBadges[k] === 1 ? "y" : "ies"}`}
              >
                {k} {capBadges[k]}
              </span>
            ))}
        </div>
      )}

      {/* Rule badges (P6-6): counts by kind on rule-owning nodes */}
      {ruleBadges && (
        <div className="absolute -top-2 -left-2 z-20 flex flex-wrap items-center gap-1 max-w-[220px]">
          {(["policy", "validation", "calculation", "io"] as const)
            .filter((k) => (ruleBadges[k] ?? 0) > 0)
            .map((k) => (
              <span
                key={k}
                className={`px-1.5 h-5 flex items-center rounded-full text-[11px] font-bold uppercase tracking-wide shadow-sm ${
                  darkMode ? "bg-indigo-500 text-white" : "bg-indigo-600 text-white"
                }`}
                title={`${ruleBadges[k]} ${k} rule${ruleBadges[k] === 1 ? "" : "s"}`}
              >
                {k} {ruleBadges[k]}
              </span>
            ))}
        </div>
      )}

      {/* Annotation badge */}
      {annotationCount > 0 && (
        <div className={`
          absolute -top-2 -right-2 z-20 min-w-[20px] h-[20px] flex items-center justify-center
          rounded-full text-[11px] font-bold
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
      <DeviceFrame type={component.type} darkMode={darkMode} colors={colors} enhancedFrames={enhancedFrames} heroGlow={isHero && glowsInThisTheme ? getHeroGlow(component.type, darkMode) : undefined}>
        {/* Header */}
        <div className={isHero ? "px-4 pt-3 pb-2" : "px-4 pt-3 pb-2"}>
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <h3 data-se="name" className={`font-semibold truncate ${isHero ? "text-base" : "text-sm"} ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
                {TYPE_META[component.type]?.icon && <span className="mr-1.5">{TYPE_META[component.type].icon}</span>}
                <ReviewTarget
                  targetType="component-name"
                  targetId={`${component.id}:name`}
                  targetName={component.name}
                  componentId={component.id}
                  targetContext={{
                    componentPath: component.path,
                    nameSource: `directory name at ${component.path}`,
                    configFiles: component.config_files?.map((c) => c.path),
                  }}
                >
                  {component.name}
                </ReviewTarget>
              </h3>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                <ReviewTarget
                  targetType="component-type"
                  targetId={`${component.id}:type`}
                  targetName={TYPE_META[component.type]?.label || component.type}
                  componentId={component.id}
                  targetContext={{ typeValue: component.type, componentPath: component.path }}
                >
                  <Tooltip content={TYPE_DESCRIPTIONS[component.type] || component.type} position="bottom">
                    <span data-se="badge" className={`text-xs px-2 py-1 rounded-full font-medium ${colors.badge}`}>
                      {TYPE_META[component.type]?.label || component.type}
                    </span>
                  </Tooltip>
                </ReviewTarget>
                {component.framework && (() => {
                  const ref = getTechRef(component.framework);
                  const frameworkEl = ref ? (
                    <TechTooltip name={component.framework} description={ref.description} url={ref.url}>
                      <span className={`text-xs font-medium ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
                        {component.framework}
                      </span>
                    </TechTooltip>
                  ) : (
                    <span className={`text-xs font-medium ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
                      {component.framework}
                    </span>
                  );
                  return (
                    <ReviewTarget
                      targetType="component-framework"
                      targetId={`${component.id}:framework`}
                      targetName={component.framework}
                      componentId={component.id}
                      targetContext={{ frameworkValue: component.framework, componentPath: component.path }}
                    >
                      {frameworkEl}
                    </ReviewTarget>
                  );
                })()}
                {component.ai_enhance?.architectural_role && ROLE_META[component.ai_enhance.architectural_role] && (
                  <span className={`text-xs px-2 py-1 rounded-full font-medium ${getRoleBadgeColors(component.ai_enhance.architectural_role, darkMode)}`}>
                    {ROLE_META[component.ai_enhance.architectural_role].icon} {ROLE_META[component.ai_enhance.architectural_role].label}
                  </span>
                )}
              </div>
            </div>
            <div ref={helpButtonRef} className="flex items-center gap-1 shrink-0 relative">
              {hasHelpContent && (
                <button
                  className={`
                    se-node-control rounded-lg flex items-center justify-center
                    text-xs font-bold
                    ${darkMode ? "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200" : "bg-zinc-200 text-zinc-600 hover:bg-zinc-300"}
                  `}
                  onClick={(e) => {
                    e.stopPropagation();
                    dismissPreview();
                    setShowHelp(!showHelp);
                  }}
                  aria-label={`Open information about ${component.name}`}
                  aria-haspopup="dialog"
                  aria-expanded={showHelp}
                  title="Component info"
                >
                  ?
                </button>
              )}
              {hasChildren && (
                <button
                  className={`
                    se-node-control rounded-lg flex items-center justify-center
                    text-xs font-bold
                    ${darkMode ? "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200" : "bg-zinc-200 text-zinc-600 hover:bg-zinc-300"}
                  `}
                  onClick={(e) => {
                    e.stopPropagation();
                    drillInto(component);
                  }}
                  aria-label={`Open ${component.name}`}
                  title="Drill into component"
                >
                  &darr;
                </button>
              )}
              {showHelp && <HelpPopover component={component} darkMode={darkMode} triggerRef={helpButtonRef} onClose={closeHelp} />}
            </div>
          </div>

          {/* Purpose line */}
          {summary && (
            <ReviewTarget
              targetType="component-purpose"
              targetId={`${component.id}:purpose`}
              targetName="Purpose"
              componentId={component.id}
              targetContext={{ purposeValue: summary, componentPath: component.path }}
              className="block mt-1.5"
            >
              <p className={`text-xs leading-relaxed line-clamp-2 ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
                {summary}
              </p>
            </ReviewTarget>
          )}
        </div>

        {/* Patterns badges */}
        {hasPatterns && (
          <div className="px-4 pb-1.5 flex flex-wrap gap-1">
            {docs!.patterns.slice(0, 3).map((p, i) => (
              <ReviewTarget
                key={i}
                targetType="component-pattern"
                targetId={`${component.id}:pattern:${p}`}
                targetName={p}
                componentId={component.id}
                targetContext={{ patternValue: p, componentPath: component.path }}
              >
                <span className={`
                  text-[11px] px-1.5 py-0.5 rounded
                  ${darkMode ? "bg-violet-900/30 text-violet-300" : "bg-violet-50 text-violet-700"}
                `}>
                  {p}
                </span>
              </ReviewTarget>
            ))}
            {docs!.patterns.length > 3 && (
              <span className="text-[11px] se-info-meta">
                +{docs!.patterns.length - 3}
              </span>
            )}
          </div>
        )}

        {/* Metrics bar */}
        <div className="px-4 pb-3 flex items-center gap-3 text-xs flex-wrap se-info-meta">
          {component.ai_enhance?.criticality && component.ai_enhance.criticality !== "supporting" && (
            <Tooltip focusable content={`${component.ai_enhance.criticality === "critical" ? "Critical: system fails without this" : "Important: degraded behavior without this"}`}>
              <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${
                component.ai_enhance.criticality === "critical"
                  ? (darkMode ? "bg-red-950/60 text-red-300" : "bg-red-50 text-red-800")
                  : (darkMode ? "bg-amber-950/60 text-amber-200" : "bg-amber-50 text-amber-800")
              }`}>
                {component.ai_enhance.criticality === "critical" ? "! Critical" : "▲ Important"}
              </span>
            </Tooltip>
          )}
          {component.ai_enhance?.stale && (
            <Tooltip focusable content="This interpretation predates the component's current file digest and may no longer be accurate.">
              <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[11px] font-medium text-amber-500">stale interpretation</span>
            </Tooltip>
          )}
          {component.live_status?.statuses && (() => {
            const worst = getWorstStatusLevel(component.live_status.statuses);
            if (worst === "ok") return null;
            return (
              <Tooltip focusable content={getStatusSummary(component.live_status.statuses)}>
                <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${
                  worst === "error"
                    ? (darkMode ? "bg-red-950/60 text-red-200" : "bg-red-100 text-red-800")
                    : worst === "warning"
                      ? (darkMode ? "bg-amber-950/60 text-amber-200" : "bg-amber-100 text-amber-800")
                      : (darkMode ? "bg-blue-950/60 text-blue-200" : "bg-blue-100 text-blue-800")
                }`}>
                  {worst === "error" ? "× Error" : worst === "warning" ? "▲ Warning" : "i Info"}
                </span>
              </Tooltip>
            );
          })()}
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
          {/* Blast radius (D5): present only on a --design-signals dataset, and
              only when something actually depends on this component. The count
              is the number, the graph shading is the picture, and the tooltip
              carries the plain-language reading rather than the term. */}
          {(component.design?.blast_radius ?? 0) > 0 && (
            <Tooltip
              content={`If this changes, ${component.design!.blast_radius} other part${
                component.design!.blast_radius === 1 ? "" : "s"
              } could break. Counted by following dependencies through the whole graph.`}
            >
              <span className={darkMode ? "text-rose-400" : "text-rose-600"}>
                {formatNumber(component.design!.blast_radius)} could break
              </span>
            </Tooltip>
          )}
          {component.port && (
            <ReviewTarget
              targetType="component-port"
              targetId={`${component.id}:port`}
              targetName={`:${component.port}`}
              componentId={component.id}
              targetContext={{ portValue: component.port, componentPath: component.path }}
            >
              <Tooltip content="The network port this service listens on.">
                <span className={`font-mono ${darkMode ? "text-blue-400" : "text-blue-600"}`}>:{component.port}</span>
              </Tooltip>
            </ReviewTarget>
          )}
          {docs?.readme && (
            <Tooltip content="This component has a README file with documentation.">
              <span className={`text-[11px] ${darkMode ? "text-green-400" : "text-green-700"}`}>
                DOC
              </span>
            </Tooltip>
          )}
          {docs?.api_endpoints && docs.api_endpoints.length > 0 && (
            <Tooltip content={`This component exposes ${docs.api_endpoints.length} API endpoint${docs.api_endpoints.length !== 1 ? "s" : ""}.`}>
              <span className={`text-[11px] ${darkMode ? "text-blue-400" : "text-blue-700"}`}>
                API
              </span>
            </Tooltip>
          )}
          {component.testing && (component.testing.unit_tests + component.testing.integration_tests + component.testing.e2e_tests) > 0 && (
            <Tooltip content={`${component.testing.unit_tests + component.testing.integration_tests + component.testing.e2e_tests} tests${component.testing.coverage_percent !== null ? ` (${component.testing.coverage_percent.toFixed(0)}% coverage)` : ""}`}>
              <span className={`text-[11px] ${
                component.testing.coverage_percent !== null && component.testing.coverage_percent >= 80
                  ? (darkMode ? "text-green-400" : "text-green-700")
                  : (darkMode ? "text-amber-400" : "text-amber-700")
              }`}>
                TST
              </span>
            </Tooltip>
          )}
          {connectionCount > 0 && (
            <Tooltip content={METRIC_DESCRIPTIONS.conn}>
              <span className={darkMode ? "text-zinc-600" : "text-zinc-400"}>
                {incomingCount > 0 && outgoingCount > 0
                  ? `${incomingCount} in, ${outgoingCount} out`
                  : `${connectionCount} conn`}
              </span>
            </Tooltip>
          )}
        </div>

        {/* Children indicator */}
        {component.children.length > 0 && (
          <div className={`
            px-4 py-1.5 border-t text-xs
            ${darkMode ? "border-zinc-800/50 text-zinc-400" : "border-zinc-200 text-zinc-600"}
          `}>
            {component.children.length} sub-component{component.children.length !== 1 ? "s" : ""}
          </div>
        )}
      </DeviceFrame>
    </div>
  );
});
