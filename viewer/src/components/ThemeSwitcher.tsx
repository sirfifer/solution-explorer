import { useEffect, useRef, useState } from "react";
import { useArchStore } from "../store";
import { THEME_LIST, THEMES } from "../utils/themes";

/**
 * The dress control in the header.
 *
 * This replaces the old sun/moon button rather than sitting beside it,
 * because the two settings it carries are one question asked twice: which
 * theme, and which of that theme's two variants. Every theme ships both a
 * light and a dark variant, so appearance stays an axis of its own and the
 * pair belongs in one popover.
 *
 * The swatches are literal hex values from the theme registry, not theme
 * variables. A chip has to show the dress you would be switching into, so it
 * cannot be painted by the dress currently in force.
 */

function Swatch({ colors, size = 15 }: { colors: readonly [string, string, string]; size?: number }) {
  // A paint chip rather than a dot. Three inks read as three inks at this size
  // only if the shape has square corners; inside a circle they collapse into a
  // single smudge and every theme looks the same in the list.
  return (
    <span
      className="inline-flex shrink-0 overflow-hidden rounded-[3px] ring-1 ring-black/20"
      style={{ width: size * 1.5, height: size }}
      aria-hidden="true"
    >
      {colors.map((c) => (
        <span key={c} style={{ background: c, width: (size * 1.5) / 3, height: size }} />
      ))}
    </span>
  );
}

export function ThemeSwitcher() {
  const darkMode = useArchStore((s) => s.darkMode);
  const toggleDarkMode = useArchStore((s) => s.toggleDarkMode);
  const theme = useArchStore((s) => s.theme);
  const setTheme = useArchStore((s) => s.setTheme);

  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("click", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("click", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  const current = THEMES[theme];

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Theme: ${current.label}, ${darkMode ? "dark" : "light"}`}
        title={`Theme: ${current.label} (${darkMode ? "dark" : "light"})`}
        className={`
          flex items-center gap-2 px-2 py-2 rounded-lg min-h-[44px] sm:min-h-0
          ${darkMode ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-zinc-100 text-zinc-600"}
        `}
      >
        <Swatch colors={current.swatch} />
        <span className="hidden lg:inline text-xs">{current.label}</span>
        <span className="text-[9px] opacity-60" aria-hidden="true">{"▾"}</span>
      </button>

      {open && (
        <div
          role="menu"
          className={`
            absolute right-0 top-full mt-1 w-60 rounded-xl shadow-xl border z-50 overflow-hidden
            ${darkMode ? "bg-zinc-900 border-zinc-700" : "bg-white border-zinc-200"}
          `}
        >
          <div className={`px-3 pt-2.5 pb-1 text-[10px] uppercase tracking-wider ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            Theme
          </div>
          {THEME_LIST.map((t) => {
            const active = t.name === theme;
            return (
              <button
                key={t.name}
                role="menuitemradio"
                aria-checked={active}
                onClick={() => { setTheme(t.name); setOpen(false); }}
                className={`
                  min-h-11 w-full flex items-center gap-2.5 px-3 py-2 text-left
                  ${darkMode ? "hover:bg-zinc-800" : "hover:bg-zinc-100"}
                  ${active ? (darkMode ? "bg-zinc-800/60" : "bg-zinc-100/70") : ""}
                `}
              >
                <Swatch colors={t.swatch} size={17} />
                <span className="min-w-0 flex-1">
                  <span className={`block text-sm leading-tight ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                    {t.label}
                  </span>
                  <span className={`block text-[11px] leading-tight ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>
                    {t.tagline}
                  </span>
                </span>
                {active && (
                  <span className={darkMode ? "text-emerald-400" : "text-emerald-600"} aria-hidden="true">
                    {"✓"}
                  </span>
                )}
              </button>
            );
          })}

          <div className={`mt-1 border-t ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
            <div className={`px-3 pt-2.5 pb-1 text-[10px] uppercase tracking-wider ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              Appearance
            </div>
            {/*
              Light and dark stay a separate control because they are a
              separate axis: each theme carries both variants, so choosing a
              dress never chooses a time of day.
            */}
            <div className="flex gap-1 px-2 pb-2.5">
              {([false, true] as const).map((wantDark) => {
                const active = darkMode === wantDark;
                return (
                  <button
                    key={String(wantDark)}
                    role="menuitemradio"
                    aria-checked={active}
                    onClick={() => { if (darkMode !== wantDark) toggleDarkMode(); }}
                    className={`
                      min-h-11 flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs
                      ${active
                        ? (darkMode ? "bg-zinc-800 text-zinc-200" : "bg-zinc-200 text-zinc-800")
                        : (darkMode ? "text-zinc-500 hover:bg-zinc-800/60" : "text-zinc-500 hover:bg-zinc-100")
                      }
                    `}
                  >
                    <span aria-hidden="true">{wantDark ? "☾" : "☀"}</span>
                    <span>{wantDark ? "Dark" : "Light"}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
