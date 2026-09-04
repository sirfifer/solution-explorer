import { useEffect, useState } from "react";
import { useArchStore } from "../store";
import { listAvailableLenses } from "../lenses";
import { maturitySuffix, resolveChannel } from "../utils/channel";
import { Tooltip } from "./Tooltip";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";
import { ORIENTATION_SHOWCASE_EVENT, type OrientationShowcaseDetail } from "../orientation/showcase";

// The lens switcher (P6-1). Lets the reader change perspective without losing
// their place (invariant I12: selection, breadcrumbs, and URL survive). It lists
// the lenses available for the loaded dataset; today that is Structure, and the
// later lenses (Flow, Capability, Data, Activity, Rules, Tours, Ask) appear here
// as they register.
export function LensSwitcher() {
  const darkMode = useArchStore((s) => s.darkMode);
  const architecture = useArchStore((s) => s.architecture);
  const lens = useArchStore((s) => s.lens);
  const setLens = useArchStore((s) => s.setLens);
  const [showcaseOpen, setShowcaseOpen] = useState(false);

  useEffect(() => {
    const handleShowcase = (event: Event) => {
      setShowcaseOpen((event as CustomEvent<OrientationShowcaseDetail>).detail.stopId === "lenses");
    };
    window.addEventListener(ORIENTATION_SHOWCASE_EVENT, handleShowcase);
    return () => window.removeEventListener(ORIENTATION_SHOWCASE_EVENT, handleShowcase);
  }, []);

  // Resolve the maturity channel (card R3). Default "stable" shows only stable
  // lenses (the current behavior, unchanged); a `?channel=` override surfaces the
  // beta/experimental lenses it activates, each labeled below.
  const channel = resolveChannel();
  const available = listAvailableLenses(architecture, channel);
  // No dataset yet: nothing to show.
  if (available.length === 0) return null;

  // The tooltip on the control shows the active lens's own one-line description
  // (what this lens shows). Options carry no native title: option tooltips are
  // inconsistent across browsers, and the sweep's rule is one tooltip system.
  // Switching lenses updates this control tooltip to the new lens's description.
  const activeDescription =
    available.find((l) => l.id === lens)?.description ?? TOOLTIP_COPY.lens.switcher;

  return (
    <div data-testid="lens-switcher" className="relative">
      <Tooltip content={activeDescription} position="bottom">
      <label
        className={`
          flex items-center gap-1.5 px-2 py-2 sm:py-1 rounded-lg text-xs
          min-h-[44px] sm:min-h-0
          ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500"}
        `}
        aria-label={TOOLTIP_COPY.lens.switcher}
      >
        {/* The label word is dropped on the smallest screens to save header
            width; the select itself is the mobile-first lens control (every
            lens reachable on a phone, GUI run finding V8.4). */}
        <span className="hidden sm:inline text-[10px] uppercase tracking-wider">Lens</span>
        <select
          data-testid="lens-select"
          data-lens={lens}
          value={lens}
          onChange={(e) => setLens(e.target.value)}
          className={`bg-transparent outline-none text-xs font-medium ${darkMode ? "text-zinc-200" : "text-zinc-700"}`}
        >
          {available.map((l) => (
            <option key={l.id} value={l.id}>
              {l.label}
              {maturitySuffix(l.maturity)}
            </option>
          ))}
        </select>
      </label>
      </Tooltip>
      {showcaseOpen && (
        <div
          data-testid="lens-menu"
          role="menu"
          aria-label="Available lenses"
          className={`absolute right-0 top-full z-50 mt-1 max-h-[40vh] w-60 overflow-y-auto rounded-xl border shadow-xl ${darkMode ? "border-zinc-700 bg-zinc-900" : "border-zinc-200 bg-white"}`}
        >
          <div className={`px-3 pb-1 pt-2.5 text-[10px] uppercase tracking-wider ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            Explore through a lens
          </div>
          {available.map((item) => {
            const active = item.id === lens;
            return (
              <button
                type="button"
                key={item.id}
                role="menuitemradio"
                aria-checked={active}
                onClick={() => setLens(item.id)}
                className={`min-h-11 w-full px-3 py-2 text-left ${darkMode ? "hover:bg-zinc-800" : "hover:bg-zinc-100"} ${active ? darkMode ? "bg-zinc-800/60" : "bg-zinc-100/70" : ""}`}
              >
                <span className={`block text-sm font-medium ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                  {item.label}{maturitySuffix(item.maturity)}
                </span>
                <span className={`block text-[11px] leading-4 ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>
                  {item.description}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
