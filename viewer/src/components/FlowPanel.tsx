import { useArchStore } from "../store";
import { TYPE_META } from "../utils/layout";

// The Flow lens surface (P6-2, LENS-DESIGN.md L4). The landing view is the ranked
// list of ENTRY FLOWS (invariant I11: "where do the journeys start"), tab
// containers and tabs and top-level screens ordered by how many screens they
// reach. Selecting one enters "follow" mode: the walk steps through the flow one
// screen at a time (the question grammar's "what happens from here" forward and
// "how did I get here" backward), breadcrumbing each hop. The graph beside it is
// the spatial complement, ringing the entry and the current step.

function typeIcon(type: string): string {
  return TYPE_META[type]?.icon ?? "\u{1F4F1}";
}

function SectionLabel({ children, darkMode }: { children: React.ReactNode; darkMode: boolean }) {
  return (
    <div className={`text-[10px] uppercase tracking-wider font-semibold ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
      {children}
    </div>
  );
}

// `mobile` (O10): renders the same panel full width and unhidden, for use
// inside the mobile lens bottom sheet instead of the desktop-docked column.
// The desktop wrapper (`hidden md:flex w-80 shrink-0 border-r`) is display:none
// below the md breakpoint, which is exactly why a lens picked on a phone used
// to render nothing.
export function FlowPanel({ mobile = false }: { mobile?: boolean } = {}) {
  const darkMode = useArchStore((s) => s.darkMode);
  const flowEntryId = useArchStore((s) => s.flowEntryId);
  const flowStep = useArchStore((s) => s.flowStep);
  const getFlowEntries = useArchStore((s) => s.getFlowEntries);
  const getFlowPath = useArchStore((s) => s.getFlowPath);
  const setFlowEntry = useArchStore((s) => s.setFlowEntry);
  const flowStepNext = useArchStore((s) => s.flowStepNext);
  const flowStepPrev = useArchStore((s) => s.flowStepPrev);
  const flowGoToStep = useArchStore((s) => s.flowGoToStep);
  const clearFlow = useArchStore((s) => s.clearFlow);
  const getComponentById = useArchStore((s) => s.getComponentById);
  const selectedComponentId = useArchStore((s) => s.selectedComponentId);

  const containerClass = mobile
    ? `flex flex-col w-full h-full overflow-hidden ${darkMode ? "bg-zinc-950" : "bg-zinc-50"}`
    : `hidden md:flex flex-col w-80 shrink-0 border-r overflow-hidden ${
        darkMode ? "bg-zinc-950 border-zinc-800" : "bg-zinc-50 border-zinc-200"
      }`;

  const entries = getFlowEntries();
  const totalScreens = entries.reduce((m, e) => Math.max(m, e.screenCount), 0);

  const header = (
    <div className={`px-4 py-3 border-b shrink-0 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
      <div className="flex items-center gap-1.5">
        <span>{"\u{1F5FA}️"}</span>
        <h2 className={`text-sm font-bold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>Flow</h2>
      </div>
      <p className={`mt-0.5 text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
        {entries.length} entry {entries.length === 1 ? "flow" : "flows"} across the app
      </p>
    </div>
  );

  // FOLLOW MODE: an entry is selected; walk it step by step.
  if (flowEntryId) {
    const path = getFlowPath(flowEntryId);
    const entry = entries.find((e) => e.id === flowEntryId);
    const step = Math.min(flowStep, Math.max(0, path.length - 1));
    const chipBtn = darkMode
      ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-40"
      : "bg-zinc-200 text-zinc-700 hover:bg-zinc-300 disabled:opacity-40";

    return (
      <div className={containerClass} data-testid="lens-panel" data-lens="flow">
        {header}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          <button
            data-testid="flow-exit"
            onClick={clearFlow}
            className={`text-[11px] ${darkMode ? "text-blue-400 hover:text-blue-300" : "text-blue-600 hover:text-blue-700"}`}
          >
            {"←"} All entry flows
          </button>

          <div>
            <SectionLabel darkMode={darkMode}>Following</SectionLabel>
            <div className={`mt-1 flex items-center gap-1.5 text-sm font-semibold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
              <span>{entry ? typeIcon(entry.type) : "\u{1F4F1}"}</span>
              <span className="truncate">{entry?.name ?? flowEntryId}</span>
            </div>
            <p className={`mt-0.5 text-[11px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
              Step {step + 1} of {path.length}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              data-testid="flow-prev"
              onClick={flowStepPrev}
              disabled={step <= 0}
              className={`flex-1 px-2 py-1.5 rounded-lg text-xs font-medium ${chipBtn}`}
              title="How did I get here: step back along the path"
            >
              {"←"} Previous
            </button>
            <button
              data-testid="flow-next"
              onClick={flowStepNext}
              disabled={step >= path.length - 1}
              className={`flex-1 px-2 py-1.5 rounded-lg text-xs font-medium ${chipBtn}`}
              title="What happens from here: step forward"
            >
              Next {"→"}
            </button>
          </div>

          <div>
            <SectionLabel darkMode={darkMode}>Path</SectionLabel>
            <ol className="mt-1.5 space-y-0.5">
              {path.map((id, i) => {
                const comp = getComponentById(id);
                const isCurrent = i === step;
                const visited = i <= step;
                return (
                  <li key={id}>
                    <button
                      onClick={() => flowGoToStep(i)}
                      className={`w-full flex items-center gap-2 px-2 py-1 rounded-md text-left text-[12px] ${
                        isCurrent
                          ? darkMode
                            ? "bg-teal-500/15 text-teal-300"
                            : "bg-teal-100 text-teal-800"
                          : visited
                            ? darkMode
                              ? "text-zinc-300 hover:bg-zinc-800"
                              : "text-zinc-700 hover:bg-zinc-100"
                            : darkMode
                              ? "text-zinc-500 hover:bg-zinc-800"
                              : "text-zinc-400 hover:bg-zinc-100"
                      }`}
                    >
                      <span className={`w-5 shrink-0 text-right tabular-nums text-[10px] ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                        {i + 1}
                      </span>
                      <span className="shrink-0">{comp ? typeIcon(comp.type) : "\u{1F4F1}"}</span>
                      <span className="truncate">{comp?.name ?? id}</span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>
        </div>
      </div>
    );
  }

  // LANDING: the ranked entry flows (I11).
  return (
    <div className={containerClass} data-testid="lens-panel" data-lens="flow">
      {header}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        <SectionLabel darkMode={darkMode}>Entry flows, most reach first</SectionLabel>
        {entries.length === 0 ? (
          <p className={`mt-2 text-xs ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
            No entry flows in this dataset.
          </p>
        ) : (
          <ul className="mt-2 space-y-1">
            {entries.map((e) => {
              const isSelected = e.id === selectedComponentId;
              return (
                <li key={e.id}>
                  <button
                    data-testid="flow-entry"
                    data-flow-id={e.id}
                    onClick={() => setFlowEntry(e.id)}
                    className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-left ${
                      isSelected
                        ? darkMode
                          ? "bg-indigo-500/15"
                          : "bg-indigo-100"
                        : darkMode
                          ? "hover:bg-zinc-800"
                          : "hover:bg-zinc-100"
                    }`}
                    title="Follow this flow step by step"
                  >
                    <span className="shrink-0">{typeIcon(e.type)}</span>
                    <span className="flex-1 min-w-0">
                      <span className={`block text-sm font-medium truncate ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                        {e.name}
                      </span>
                      <span className={`block text-[10px] ${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>
                        {e.type} {"·"} reaches {e.screenCount} screen{e.screenCount !== 1 ? "s" : ""}
                      </span>
                    </span>
                    {totalScreens > 0 && (
                      <span className="w-14 shrink-0">
                        <span className="block h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
                          <span
                            className={`block h-full rounded-full ${darkMode ? "bg-indigo-500/70" : "bg-indigo-500/80"}`}
                            style={{ width: `${Math.max(4, Math.round((e.screenCount / totalScreens) * 100))}%` }}
                          />
                        </span>
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
