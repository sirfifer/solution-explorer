import { useEffect, useMemo, useState } from "react";
import { applicableStops } from "../orientation/model";
import { WALK_STOPS } from "../orientation/stops";
import { useArchStore } from "../store";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";
import { SYSCORPUS } from "../utils/product";
import { buildWalkContext } from "./OrientationWalk";

const KEYBOARD_SHORTCUTS = [
  { keys: ["\u2318", "K"], description: "Open search" },
  { keys: ["Esc"], description: "Close panels / search" },
  { keys: ["\u2318", "+"], description: "Zoom in" },
  { keys: ["\u2318", "-"], description: "Zoom out" },
  { keys: ["\u2318", "0"], description: "Fit to view" },
  { keys: ["?"], description: "Toggle help" },
];

export function HelpSystem() {
  const architecture = useArchStore((state) => state.architecture);
  const publication = useArchStore((state) => state.publication);
  const darkMode = useArchStore((state) => state.darkMode);
  const showHelp = useArchStore((state) => state.helpOpen);
  const setShowHelp = useArchStore((state) => state.setHelpOpen);
  const startOrientation = useArchStore((state) => state.startOrientation);
  const [activeHelpTab, setActiveHelpTab] = useState<"guide" | "shortcuts" | "about">("guide");
  const [viewportWidth, setViewportWidth] = useState(() => typeof window === "undefined" ? 1024 : window.innerWidth);

  useEffect(() => {
    const updateWidth = () => setViewportWidth(window.innerWidth);
    window.addEventListener("resize", updateWidth);
    return () => window.removeEventListener("resize", updateWidth);
  }, []);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "?" && !event.metaKey && !event.ctrlKey && !(event.target instanceof HTMLInputElement)) {
        if (!useArchStore.getState().orientationOpen) {
          setShowHelp(!useArchStore.getState().helpOpen);
        }
        return;
      }
      if (event.key === "Escape" && showHelp) setShowHelp(false);
    };
    const openFromMobileMenu = () => setShowHelp(true);
    const openInterfaceGuide = () => {
      setActiveHelpTab("guide");
      setShowHelp(true);
    };
    window.addEventListener("keydown", handler);
    window.addEventListener("arch-viz-open-help", openFromMobileMenu);
    window.addEventListener("arch-viz-open-interface-guide", openInterfaceGuide);
    return () => {
      window.removeEventListener("keydown", handler);
      window.removeEventListener("arch-viz-open-help", openFromMobileMenu);
      window.removeEventListener("arch-viz-open-interface-guide", openInterfaceGuide);
    };
  }, [setShowHelp, showHelp]);

  const context = useMemo(
    () => architecture ? buildWalkContext(architecture, publication, viewportWidth) : null,
    [architecture, publication, viewportWidth],
  );
  const guideStops = useMemo(() => applicableStops(WALK_STOPS, viewportWidth), [viewportWidth]);

  return (
    <>
      {showHelp && (
        <div
          data-testid="help-overlay"
          data-kind="help"
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="help-title"
        >
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setShowHelp(false)} />
          <div className={`relative flex max-h-[80vh] w-full max-w-md flex-col overflow-hidden rounded-2xl border shadow-2xl ${darkMode ? "border-zinc-800 bg-zinc-900" : "border-zinc-200 bg-white"}`}>
            <div className={`flex items-center justify-between border-b px-6 py-4 ${darkMode ? "border-zinc-800" : "border-zinc-100"}`}>
              <h2 id="help-title" className={`text-lg font-bold ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>Help</h2>
              <button
                onClick={() => setShowHelp(false)}
                className={`min-h-11 min-w-11 rounded-lg p-1 ${darkMode ? "text-zinc-400 hover:bg-zinc-800" : "text-zinc-500 hover:bg-zinc-100"}`}
                aria-label="Close help"
              >
                &#x2715;
              </button>
            </div>

            <div className={`flex border-b ${darkMode ? "border-zinc-800" : "border-zinc-100"}`}>
              {(["guide", "shortcuts", "about"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveHelpTab(tab)}
                  className={`min-h-11 flex-1 px-3 py-2 text-sm font-medium capitalize ${activeHelpTab === tab ? darkMode ? "border-b-2 border-blue-500 text-blue-400" : "border-b-2 border-blue-500 text-blue-600" : darkMode ? "text-zinc-500 hover:text-zinc-300" : "text-zinc-400 hover:text-zinc-600"}`}
                >
                  {tab}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto p-6">
              {activeHelpTab === "guide" && context && (
                <div className="space-y-4">
                  {context.identitySummary && (
                    <p className={`text-sm leading-relaxed ${darkMode ? "text-zinc-300" : "text-zinc-700"}`}>
                      {context.identitySummary}
                    </p>
                  )}
                  <ol className="space-y-4">
                    {guideStops.map((stop, index) => (
                      <li key={stop.id} className="flex gap-3">
                        <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${darkMode ? "bg-zinc-800 text-cyan-400" : "bg-zinc-100 text-cyan-700"}`}>
                          {index + 1}
                        </span>
                        <div>
                          <h3 className={`text-sm font-semibold ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{stop.heading(context)}</h3>
                          <p className={`mt-0.5 text-sm leading-relaxed ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{stop.body(context)}</p>
                        </div>
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              {activeHelpTab === "shortcuts" && (
                <div className="space-y-2">
                  {KEYBOARD_SHORTCUTS.map((shortcut) => (
                    <div key={shortcut.description} className="flex items-center justify-between py-1.5">
                      <span className={`text-sm ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>{shortcut.description}</span>
                      <div className="flex gap-1">
                        {shortcut.keys.map((key) => (
                          <kbd key={key} className={`min-w-[24px] rounded border px-1.5 py-0.5 text-center font-mono text-xs ${darkMode ? "border-zinc-700 bg-zinc-800 text-zinc-300" : "border-zinc-200 bg-zinc-100 text-zinc-700"}`}>
                            {key}
                          </kbd>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {activeHelpTab === "about" && (
                <div className={`space-y-4 text-sm leading-relaxed ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
                  <p>
                    SysCorpus builds an explorable model of a software system from its source at one recorded commit. It connects architectural understanding to the files, symbols, and source evidence behind it, and labels model-assisted phrasing where it appears.
                  </p>
                  <p>
                    Overview presents the system story and question-led entry points. Workbench provides the full technical model: components, files, symbols, relationships, findings, guided paths, and lenses that reorganize the same evidence for a purpose.
                  </p>
                  <p>
                    Built with <a className="text-cyan-500 hover:underline" href={SYSCORPUS.url} target="_blank" rel="noopener noreferrer">SysCorpus</a>. Learn more at syscorpus.com.
                  </p>
                </div>
              )}
            </div>

            <div className={`border-t px-6 py-4 ${darkMode ? "border-zinc-800" : "border-zinc-100"}`}>
              <p className={`mb-2 text-center text-xs ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
                Want to revisit the guided walkthrough?
              </p>
              <button
                data-testid="orientation-replay"
                onClick={() => {
                  setShowHelp(false);
                  startOrientation();
                }}
                title={TOOLTIP_COPY.orientation.replay}
                className="min-h-11 w-full rounded-lg bg-cyan-500 px-4 py-2.5 text-sm font-bold text-zinc-950 shadow-sm hover:bg-cyan-400"
              >
                Replay guided tour
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
