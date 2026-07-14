import { useArchStore } from "../store";
import { hasTours, isTourStale } from "../tours/model";

// The Tours entry point (P6-7, LENS-DESIGN L7). A slim bar below the findings
// entry, present ONLY when the dataset carries tours; it opens the tour list.
// When no tours are present it renders nothing, so legacy datasets are unchanged
// (degrades like coverage/activity/findings).

export function ToursEntry() {
  const architecture = useArchStore((s) => s.architecture);
  const darkMode = useArchStore((s) => s.darkMode);
  const openTours = useArchStore((s) => s.openTours);

  if (!hasTours(architecture)) return null;

  const tours = architecture?.tours ?? [];
  const staleCount = tours.filter(isTourStale).length;

  return (
    <div
      className={`px-4 py-1.5 text-xs shrink-0 ${
        darkMode
          ? "bg-teal-950/20 border-b border-teal-900/30 text-teal-200"
          : "bg-teal-50 border-b border-teal-200 text-teal-800"
      }`}
    >
      <button
        type="button"
        data-testid="tours-entry"
        onClick={openTours}
        className="w-full flex items-center gap-2 text-left"
      >
        <span className="shrink-0">{"\u{1F5FA}️"}</span>
        <span className="font-semibold shrink-0">
          {tours.length} walkthrough{tours.length !== 1 ? "s" : ""}
        </span>
        {staleCount > 0 && (
          <span className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-medium ${darkMode ? "bg-amber-500/15 text-amber-300" : "bg-amber-100 text-amber-700"}`}>
            {staleCount} stale
          </span>
        )}
        <span className="flex-1" />
        <span className={`shrink-0 text-[10px] ${darkMode ? "text-teal-400/80" : "text-teal-600"}`}>
          Take a guided tour &rsaquo;
        </span>
      </button>
    </div>
  );
}
