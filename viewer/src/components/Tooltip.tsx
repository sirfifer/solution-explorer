import { useRef, type ReactElement, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useArchStore } from "../store";
import { useHoverDisclosure } from "../hooks/useHoverDisclosure";
import { useReadingSurfacePosition } from "../hooks/useReadingSurfacePosition";

interface TooltipProps {
  content: ReactNode;
  children: ReactElement;
  delay?: number;
  position?: "top" | "bottom";
  // Retained for existing callers. All help surfaces now allow pointer entry
  // and scrolling; a link is no longer required to make content reachable.
  interactive?: boolean;
  // Make the trigger reachable by keyboard when the wrapped child is not itself
  // focusable (a badge or a plain span). Interactive children (buttons, links)
  // already take focus and surface the tooltip via the wrapper's onFocus.
  focusable?: boolean;
  // Explicit accessible label. Defaults to `content` when it is a plain string,
  // so assistive tech and keyboard users get the tooltip text without a hover.
  label?: string;
  // Wrapper display class. Defaults to inline-flex; pass e.g. "block w-full" when
  // the trigger must keep a block child's width (a full-width bar).
  className?: string;
}

export function Tooltip({
  content,
  children,
  delay = 300,
  position = "top",
  focusable = false,
  label,
  className = "inline-flex",
}: TooltipProps) {
  const { darkMode } = useArchStore();
  const { visible, enter: show, leave: hide, retain: onTooltipEnter } = useHoverDisclosure(delay);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const surfaceRef = useRef<HTMLDivElement>(null);
  const placement = useReadingSurfacePosition(triggerRef, surfaceRef, visible, position, 280);

  // Keyboard focus is a first-class trigger, not just mouse hover. onFocus/onBlur
  // on the wrapper surface the tooltip when the child (or the wrapped child)
  // takes focus. When content is a plain string it also becomes the wrapper's
  // aria-label. Known limitation: on a non-focusable wrapper (a plain span)
  // assistive tech support for that label is inconsistent; the robust pattern
  // is aria-describedby on the actually-focusable element, recorded as a
  // follow-up in TASKS.md (it needs cloneElement and touches every call site).
  const ariaLabel = label ?? (typeof content === "string" ? content : undefined);

  return (
    <>
      <span
        ref={triggerRef}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        tabIndex={focusable ? 0 : undefined}
        aria-label={ariaLabel}
        className={className}
      >
        {children}
      </span>
      {visible && content && createPortal(
        <div
          ref={surfaceRef}
          role="tooltip"
          className="fixed z-[9999] pointer-events-auto nowheel nopan overflow-y-auto se-reading-surface"
          style={{
            left: placement?.left ?? 0,
            top: placement?.top ?? 0,
            width: placement?.width ?? 280,
            maxHeight: placement?.maxHeight ?? 420,
            visibility: placement ? "visible" : "hidden",
          }}
          onMouseEnter={onTooltipEnter}
          onMouseLeave={hide}
          onPointerMove={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          // Keyboard parity for interactive tooltips: tabbing from the trigger
          // into the tooltip's link fires the wrapper's onBlur (which schedules
          // the hide); focus landing inside the tooltip must cancel that hide,
          // exactly as mouse-enter does, or the link is unreachable by keyboard.
          onFocus={onTooltipEnter}
          onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) hide(); }}
        >
          <div className={`
            px-3 py-2 rounded-lg text-sm leading-relaxed shadow-lg border
            ${darkMode
              ? "bg-zinc-800 border-zinc-700 text-zinc-200"
              : "bg-white border-zinc-200 text-zinc-700 shadow-zinc-200/50"
            }
          `}>
            {content}
          </div>
        </div>,
        document.body
      )}
    </>
  );
}

/** Convenience: tooltip with a doc link */
export function TechTooltip({ name, description, url, children }: {
  name: string;
  description: string;
  url?: string;
  children: ReactElement;
}) {
  return (
    <Tooltip
      interactive={!!url}
      content={
        <div>
          <div className="font-semibold mb-0.5">{name}</div>
          <div className="opacity-80">{description}</div>
          {url && (
            <div className="mt-1 text-blue-600 dark:text-blue-400 text-xs">
              <a href={url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                {url.replace(/^https?:\/\//, "").split("/")[0]} &rarr;
              </a>
            </div>
          )}
        </div>
      }
    >
      {children}
    </Tooltip>
  );
}
