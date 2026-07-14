import { useArchStore } from "../store";
import { listAvailableLenses } from "../lenses";
import { Tooltip } from "./Tooltip";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";

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

  const available = listAvailableLenses(architecture);
  // No dataset yet: nothing to show.
  if (available.length === 0) return null;

  // The tooltip on the control shows the active lens's own one-line description
  // (what this lens shows). Options carry no native title: option tooltips are
  // inconsistent across browsers, and the sweep's rule is one tooltip system.
  // Switching lenses updates this control tooltip to the new lens's description.
  const activeDescription =
    available.find((l) => l.id === lens)?.description ?? TOOLTIP_COPY.lens.switcher;

  return (
    <Tooltip content={activeDescription} position="bottom">
      <label
        className={`
          hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs
          ${darkMode ? "bg-zinc-800 text-zinc-400" : "bg-zinc-100 text-zinc-500"}
        `}
        aria-label={TOOLTIP_COPY.lens.switcher}
      >
        <span className="text-[10px] uppercase tracking-wider">Lens</span>
        <select
          value={lens}
          onChange={(e) => setLens(e.target.value)}
          className={`bg-transparent outline-none text-xs font-medium ${darkMode ? "text-zinc-200" : "text-zinc-700"}`}
        >
          {available.map((l) => (
            <option key={l.id} value={l.id}>
              {l.label}
            </option>
          ))}
        </select>
      </label>
    </Tooltip>
  );
}
