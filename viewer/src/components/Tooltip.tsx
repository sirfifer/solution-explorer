import { useState, useRef, useCallback, type ReactElement, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useArchStore } from "../store";

interface TooltipProps {
  content: ReactNode;
  children: ReactElement;
  delay?: number;
  position?: "top" | "bottom";
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
  interactive = false,
  focusable = false,
  label,
  className = "inline-flex",
}: TooltipProps) {
  const { darkMode } = useArchStore();
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState({ x: 0, y: 0 });
  const showTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const triggerRef = useRef<HTMLSpanElement>(null);

  const clearTimers = useCallback(() => {
    if (showTimeout.current) { clearTimeout(showTimeout.current); showTimeout.current = null; }
    if (hideTimeout.current) { clearTimeout(hideTimeout.current); hideTimeout.current = null; }
  }, []);

  const show = useCallback(() => {
    clearTimers();
    showTimeout.current = setTimeout(() => {
      if (triggerRef.current) {
        const rect = triggerRef.current.getBoundingClientRect();
        setCoords({
          x: rect.left + rect.width / 2,
          y: position === "top" ? rect.top : rect.bottom,
        });
      }
      setVisible(true);
    }, delay);
  }, [delay, position, clearTimers]);

  const hide = useCallback(() => {
    clearTimers();
    if (interactive) {
      hideTimeout.current = setTimeout(() => setVisible(false), 300);
    } else {
      setVisible(false);
    }
  }, [interactive, clearTimers]);

  const onTooltipEnter = useCallback(() => {
    if (interactive) clearTimers();
  }, [interactive, clearTimers]);

  const onTooltipLeave = useCallback(() => {
    if (interactive) {
      clearTimers();
      hideTimeout.current = setTimeout(() => setVisible(false), 300);
    }
  }, [interactive, clearTimers]);

  // Keyboard focus is a first-class trigger, not just mouse hover. onFocus/onBlur
  // on the wrapper surface the tooltip when the child (or the wrapper itself,
  // when `focusable`) takes focus. When content is a plain string it also becomes
  // the wrapper's aria-label so assistive tech reads it without any hover.
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
          className={`fixed z-[9999] ${interactive ? "pointer-events-auto" : "pointer-events-none"}`}
          style={{
            left: coords.x,
            top: position === "top" ? coords.y - 8 : coords.y + 8,
            transform: position === "top"
              ? "translate(-50%, -100%)"
              : "translate(-50%, 0)",
          }}
          onMouseEnter={onTooltipEnter}
          onMouseLeave={onTooltipLeave}
        >
          <div className={`
            min-w-[120px] max-w-[280px] px-3 py-2 rounded-lg text-xs leading-relaxed shadow-lg border
            ${darkMode
              ? "bg-zinc-800 border-zinc-700 text-zinc-200"
              : "bg-white border-zinc-200 text-zinc-700 shadow-zinc-200/50"
            }
          `}>
            {content}
            {/* Arrow */}
            <div
              className={`absolute left-1/2 -translate-x-1/2 w-2 h-2 rotate-45 border
                ${darkMode ? "bg-zinc-800 border-zinc-700" : "bg-white border-zinc-200"}
                ${position === "top"
                  ? "bottom-[-5px] border-t-0 border-l-0"
                  : "top-[-5px] border-b-0 border-r-0"
                }
              `}
            />
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
            <div className="mt-1 text-blue-400 text-[10px]">
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
