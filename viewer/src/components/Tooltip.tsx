import { useState, useRef, useCallback, type ReactElement, type ReactNode } from "react";
import { useArchStore } from "../store";

interface TooltipProps {
  content: ReactNode;
  children: ReactElement;
  delay?: number;
  position?: "top" | "bottom";
}

export function Tooltip({ content, children, delay = 300, position = "top" }: TooltipProps) {
  const { darkMode } = useArchStore();
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState({ x: 0, y: 0 });
  const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const triggerRef = useRef<HTMLSpanElement>(null);

  const show = useCallback(() => {
    timeout.current = setTimeout(() => {
      if (triggerRef.current) {
        const rect = triggerRef.current.getBoundingClientRect();
        setCoords({
          x: rect.left + rect.width / 2,
          y: position === "top" ? rect.top : rect.bottom,
        });
      }
      setVisible(true);
    }, delay);
  }, [delay, position]);

  const hide = useCallback(() => {
    if (timeout.current) clearTimeout(timeout.current);
    setVisible(false);
  }, []);

  return (
    <>
      <span
        ref={triggerRef}
        onMouseEnter={show}
        onMouseLeave={hide}
        className="inline-flex"
      >
        {children}
      </span>
      {visible && content && (
        <div
          className="fixed z-[100] pointer-events-none"
          style={{
            left: coords.x,
            top: position === "top" ? coords.y - 8 : coords.y + 8,
            transform: position === "top"
              ? "translate(-50%, -100%)"
              : "translate(-50%, 0)",
          }}
        >
          <div className={`
            max-w-[280px] px-3 py-2 rounded-lg text-xs leading-relaxed shadow-lg border
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
        </div>
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
      content={
        <div>
          <div className="font-semibold mb-0.5">{name}</div>
          <div className="opacity-80">{description}</div>
          {url && (
            <div className="mt-1 text-blue-400 text-[10px] pointer-events-auto">
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
