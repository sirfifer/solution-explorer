import { useState, useEffect } from "react";
import { useArchStore } from "../store";

const HELP_DISMISSED_KEY = "arch-viz-help-dismissed";

interface HelpStep {
  title: string;
  description: string;
  icon: string;
}

const WELCOME_STEPS: HelpStep[] = [
  {
    title: "Navigate the Architecture",
    description: "The graph shows your codebase as interactive components. Each node represents a package, service, module, or application. Connections show how they relate.",
    icon: "\u{1F310}",
  },
  {
    title: "Drill Down",
    description: "Double-click any component to drill into its sub-components. Use breadcrumbs at the top to navigate back up. Keep drilling to see individual files and symbols.",
    icon: "\u{1F50D}",
  },
  {
    title: "Hover for Documentation",
    description: "Hover over any node to see its documentation: purpose, patterns, tech stack, API endpoints, and environment variables. Everything extracted from your actual code.",
    icon: "\u{1F4DD}",
  },
  {
    title: "Detail Panel",
    description: "Click a component to open the detail panel on the right. It has tabs: Overview (metrics, APIs, env vars), Docs (README, CLAUDE.md, architecture notes), Files, Symbols, and Links.",
    icon: "\u{1F4CA}",
  },
  {
    title: "Search Everything",
    description: "Press Cmd+K (or Ctrl+K) to search across all components, files, and symbols. Use the tree view on the left for hierarchical navigation.",
    icon: "\u{2328}",
  },
];

const KEYBOARD_SHORTCUTS = [
  { keys: ["\u2318", "K"], description: "Open search" },
  { keys: ["Esc"], description: "Close panels / search" },
  { keys: ["\u2318", "+"], description: "Zoom in" },
  { keys: ["\u2318", "-"], description: "Zoom out" },
  { keys: ["\u2318", "0"], description: "Fit to view" },
  { keys: ["?"], description: "Toggle help" },
];

export function HelpSystem() {
  const { darkMode } = useArchStore();
  const [showHelp, setShowHelp] = useState(false);
  const [showWelcome, setShowWelcome] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [activeHelpTab, setActiveHelpTab] = useState<"guide" | "shortcuts" | "about">("guide");

  // Show welcome on first visit
  useEffect(() => {
    const dismissed = localStorage.getItem(HELP_DISMISSED_KEY);
    if (!dismissed) {
      setShowWelcome(true);
    }
  }, []);

  // ? key toggles help
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "?" && !e.metaKey && !e.ctrlKey && !(e.target instanceof HTMLInputElement)) {
        setShowHelp((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const dismissWelcome = () => {
    setShowWelcome(false);
    localStorage.setItem(HELP_DISMISSED_KEY, "true");
  };

  return (
    <>
      {/* Help button (fixed) */}
      <button
        onClick={() => setShowHelp(true)}
        className={`
          fixed bottom-4 right-4 z-20 w-8 h-8 rounded-full flex items-center justify-center
          text-sm font-bold shadow-lg transition-all hover:scale-110
          ${darkMode
            ? "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 border border-zinc-700"
            : "bg-white text-zinc-500 hover:bg-zinc-50 hover:text-zinc-800 border border-zinc-200"
          }
        `}
        title="Help (?)"
      >
        ?
      </button>

      {/* Welcome guide overlay */}
      {showWelcome && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={dismissWelcome} />
          <div className={`
            relative w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden
            ${darkMode ? "bg-zinc-900 border border-zinc-800" : "bg-white border border-zinc-200"}
          `}>
            {/* Step content */}
            <div className="p-8 text-center">
              <div className="text-4xl mb-4">{WELCOME_STEPS[currentStep].icon}</div>
              <h2 className={`text-xl font-bold mb-2 ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>
                {currentStep === 0 ? "Welcome to Architecture Visualizer" : WELCOME_STEPS[currentStep].title}
              </h2>
              <p className={`text-sm leading-relaxed ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
                {WELCOME_STEPS[currentStep].description}
              </p>
            </div>

            {/* Progress dots */}
            <div className="flex justify-center gap-1.5 pb-4">
              {WELCOME_STEPS.map((_, i) => (
                <button
                  key={i}
                  onClick={() => setCurrentStep(i)}
                  className={`w-2 h-2 rounded-full transition-all ${
                    i === currentStep
                      ? "bg-blue-500 w-6"
                      : darkMode ? "bg-zinc-700" : "bg-zinc-300"
                  }`}
                />
              ))}
            </div>

            {/* Navigation */}
            <div className={`flex justify-between px-6 py-4 border-t ${darkMode ? "border-zinc-800" : "border-zinc-100"}`}>
              <button
                onClick={dismissWelcome}
                className={`text-sm ${darkMode ? "text-zinc-500 hover:text-zinc-300" : "text-zinc-400 hover:text-zinc-600"}`}
              >
                Skip
              </button>
              <div className="flex gap-2">
                {currentStep > 0 && (
                  <button
                    onClick={() => setCurrentStep(currentStep - 1)}
                    className={`px-4 py-1.5 rounded-lg text-sm ${darkMode ? "bg-zinc-800 text-zinc-300 hover:bg-zinc-700" : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200"}`}
                  >
                    Back
                  </button>
                )}
                {currentStep < WELCOME_STEPS.length - 1 ? (
                  <button
                    onClick={() => setCurrentStep(currentStep + 1)}
                    className="px-4 py-1.5 rounded-lg text-sm bg-blue-600 text-white hover:bg-blue-500"
                  >
                    Next
                  </button>
                ) : (
                  <button
                    onClick={dismissWelcome}
                    className="px-4 py-1.5 rounded-lg text-sm bg-blue-600 text-white hover:bg-blue-500"
                  >
                    Get Started
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Help panel */}
      {showHelp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={() => setShowHelp(false)} />
          <div className={`
            relative w-full max-w-md max-h-[80vh] rounded-2xl shadow-2xl overflow-hidden flex flex-col
            ${darkMode ? "bg-zinc-900 border border-zinc-800" : "bg-white border border-zinc-200"}
          `}>
            {/* Header */}
            <div className={`flex items-center justify-between px-6 py-4 border-b ${darkMode ? "border-zinc-800" : "border-zinc-100"}`}>
              <h2 className={`font-bold text-lg ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>Help</h2>
              <button
                onClick={() => setShowHelp(false)}
                className={`p-1 rounded-lg ${darkMode ? "hover:bg-zinc-800 text-zinc-500" : "hover:bg-zinc-100 text-zinc-400"}`}
              >
                &#x2715;
              </button>
            </div>

            {/* Tabs */}
            <div className={`flex border-b ${darkMode ? "border-zinc-800" : "border-zinc-100"}`}>
              {(["guide", "shortcuts", "about"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveHelpTab(tab)}
                  className={`flex-1 px-3 py-2 text-xs font-medium capitalize ${
                    activeHelpTab === tab
                      ? darkMode
                        ? "border-b-2 border-blue-500 text-blue-400"
                        : "border-b-2 border-blue-500 text-blue-600"
                      : darkMode
                        ? "text-zinc-500 hover:text-zinc-300"
                        : "text-zinc-400 hover:text-zinc-600"
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
              {activeHelpTab === "guide" && (
                <div className="space-y-4">
                  {WELCOME_STEPS.map((step, i) => (
                    <div key={i} className="flex gap-3">
                      <span className="text-xl shrink-0 w-8 text-center">{step.icon}</span>
                      <div>
                        <h3 className={`text-sm font-semibold mb-0.5 ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>
                          {step.title}
                        </h3>
                        <p className={`text-xs leading-relaxed ${darkMode ? "text-zinc-500" : "text-zinc-500"}`}>
                          {step.description}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {activeHelpTab === "shortcuts" && (
                <div className="space-y-2">
                  {KEYBOARD_SHORTCUTS.map((sc, i) => (
                    <div key={i} className="flex items-center justify-between py-1.5">
                      <span className={`text-sm ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
                        {sc.description}
                      </span>
                      <div className="flex gap-1">
                        {sc.keys.map((key, j) => (
                          <kbd key={j} className={`
                            px-1.5 py-0.5 rounded text-xs font-mono min-w-[24px] text-center
                            ${darkMode ? "bg-zinc-800 text-zinc-300 border border-zinc-700" : "bg-zinc-100 text-zinc-700 border border-zinc-200"}
                          `}>
                            {key}
                          </kbd>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {activeHelpTab === "about" && (
                <div className="space-y-3">
                  <p className={`text-sm ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
                    Architecture Visualizer automatically analyzes your codebase and generates an interactive, navigable architecture diagram.
                  </p>
                  <div className={`p-3 rounded-lg text-xs space-y-1.5 ${darkMode ? "bg-zinc-800" : "bg-zinc-50"}`}>
                    <div className={`${darkMode ? "text-zinc-500" : "text-zinc-400"}`}>Features:</div>
                    <ul className={`space-y-1 ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
                      <li>Multi-language support (Swift, Python, Rust, TypeScript, Go)</li>
                      <li>Automatic component detection from marker files</li>
                      <li>Relationship detection (imports, HTTP, WebSocket, gRPC)</li>
                      <li>Documentation extraction (README, docstrings, CLAUDE.md)</li>
                      <li>Architectural pattern detection (MVVM, MVC, etc.)</li>
                      <li>API endpoint and environment variable discovery</li>
                      <li>Hierarchical drill-down navigation</li>
                      <li>Full-text search across components, files, and symbols</li>
                      <li>Dark/light mode with responsive design</li>
                      <li>GitHub Actions workflow for CI integration</li>
                    </ul>
                  </div>
                  <p className={`text-xs ${darkMode ? "text-zinc-600" : "text-zinc-400"}`}>
                    Analyzer uses zero external dependencies (Python stdlib only).
                    Viewer built with React, React Flow, and TailwindCSS.
                  </p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className={`px-6 py-3 border-t text-center ${darkMode ? "border-zinc-800" : "border-zinc-100"}`}>
              <button
                onClick={() => {
                  setShowHelp(false);
                  localStorage.removeItem(HELP_DISMISSED_KEY);
                  setShowWelcome(true);
                  setCurrentStep(0);
                }}
                className={`text-xs ${darkMode ? "text-zinc-600 hover:text-zinc-400" : "text-zinc-400 hover:text-zinc-600"}`}
              >
                Replay welcome guide
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
