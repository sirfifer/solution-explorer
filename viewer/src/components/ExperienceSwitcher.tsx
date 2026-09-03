import { useArchStore } from "../store";

export function ExperienceSwitcher({ className = "" }: { className?: string }) {
  const mode = useArchStore((state) => state.experienceMode);
  const setMode = useArchStore((state) => state.setExperienceMode);
  const darkMode = useArchStore((state) => state.darkMode);
  return (
    <div data-testid="experience-switcher" className={`flex rounded-lg border p-0.5 ${darkMode ? "border-zinc-800 bg-zinc-900" : "border-zinc-200 bg-zinc-100"} ${className}`} aria-label="Experience mode">
      {(["overview", "workbench"] as const).map((item) => (
        <button
          key={item}
          data-testid={item === "overview" ? "open-overview" : "open-workbench"}
          onClick={() => setMode(item)}
          aria-pressed={mode === item}
          aria-label={item === "overview" ? "Open Overview" : "Open Workbench"}
          title={item === "workbench" ? "Open the detailed technical workspace" : "Open the comprehension-first overview"}
          className={`min-h-11 flex-1 rounded-md px-3 py-2 text-sm font-semibold transition sm:min-h-0 sm:flex-none sm:py-1.5 sm:text-[11px] ${mode === item ? darkMode ? "bg-zinc-700 text-white shadow" : "bg-white text-zinc-900 shadow" : darkMode ? "text-zinc-500 hover:text-zinc-300" : "text-zinc-500 hover:text-zinc-800"}`}
        >
          {item === "overview" ? "Overview" : "Workbench"}
        </button>
      ))}
    </div>
  );
}
