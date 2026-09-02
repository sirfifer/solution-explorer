import { useArchStore } from "../store";

export function LegacyInterfaceNotice() {
  const darkMode = useArchStore((state) => state.darkMode);
  const setExperienceMode = useArchStore((state) => state.setExperienceMode);

  return (
    <aside
      data-se="legacy-interface-notice"
      role="note"
      className={`flex shrink-0 flex-nowrap items-center justify-between gap-3 border-b px-4 py-2 text-xs ${
        darkMode
          ? "border-amber-900/50 bg-amber-950/35 text-amber-100"
          : "border-amber-200 bg-amber-50 text-amber-950"
      }`}
    >
      {/* One row, and two hidden sm:inline spans. On a 390px phone the notice
          wrapped its button onto a second line and the sentence onto a third,
          taking 132px of a 664px screen: a fifth of the viewport spent on a
          banner, above a graph left with 320px (GUI crawl 2026-09-01, mobile
          chrome). It is 61px now. The claim a reader has to have, that this
          interface is deprecated and Overview is the primary one, is kept at
          every width; the provenance clause and the word "primary" in the
          button are what a phone drops. Nothing changes from sm up. */}
      <p className="min-w-0 leading-relaxed">
        <strong>Deprecated interface.</strong>{" "}
        <span className="hidden sm:inline">
          Retained temporarily for historical comparison, deep-link compatibility, and validation.{" "}
        </span>
        Overview is the primary SysCorpus interface.
      </p>
      <button
        type="button"
        onClick={() => setExperienceMode("overview")}
        className={`min-h-11 shrink-0 whitespace-nowrap rounded-lg border px-3 py-2 font-semibold sm:min-h-0 ${
          darkMode
            ? "border-amber-700 text-amber-100 hover:bg-amber-900/40"
            : "border-amber-300 bg-white text-amber-950 hover:bg-amber-100"
        }`}
      >
        {/* Both spaces sit OUTSIDE the span. The accessible-name algorithm
            trims each element's own contribution before joining, so a space
            carried inside the span is dropped and the label reads
            "Return to primaryOverview" to a screen reader. HTML collapses the
            resulting double space when the span is hidden. */}
        Return to <span className="hidden sm:inline">primary</span> Overview
      </button>
    </aside>
  );
}
