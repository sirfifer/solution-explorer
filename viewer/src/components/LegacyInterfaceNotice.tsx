import { useArchStore } from "../store";

export function LegacyInterfaceNotice() {
  const darkMode = useArchStore((state) => state.darkMode);
  const setExperienceMode = useArchStore((state) => state.setExperienceMode);

  return (
    <aside
      data-se="legacy-interface-notice"
      role="note"
      className={`flex shrink-0 flex-wrap items-center justify-between gap-3 border-b px-4 py-2 text-xs ${
        darkMode
          ? "border-amber-900/50 bg-amber-950/35 text-amber-100"
          : "border-amber-200 bg-amber-50 text-amber-950"
      }`}
    >
      <p className="leading-relaxed">
        <strong>Deprecated interface.</strong>{" "}
        Retained temporarily for historical comparison, deep-link compatibility, and validation. Overview is the primary SysCorpus interface.
      </p>
      <button
        type="button"
        onClick={() => setExperienceMode("overview")}
        className={`min-h-11 rounded-lg border px-3 py-2 font-semibold sm:min-h-0 ${
          darkMode
            ? "border-amber-700 text-amber-100 hover:bg-amber-900/40"
            : "border-amber-300 bg-white text-amber-950 hover:bg-amber-100"
        }`}
      >
        Return to primary Overview
      </button>
    </aside>
  );
}
