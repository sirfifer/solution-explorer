import { useArchStore } from "../store";

export function ExperienceSwitcher() {
  const mode = useArchStore((state) => state.experienceMode);
  const setMode = useArchStore((state) => state.setExperienceMode);
  const darkMode = useArchStore((state) => state.darkMode);
  return (
    <div className={`flex rounded-lg border p-0.5 ${darkMode ? "border-zinc-800 bg-zinc-900" : "border-zinc-200 bg-zinc-100"}`} aria-label="Experience mode">
      {(["overview", "workbench"] as const).map((item) => (
        <button
          key={item}
          onClick={() => setMode(item)}
          aria-pressed={mode === item}
          aria-label={item}
          className={`rounded-md px-2.5 py-1.5 text-[11px] font-semibold capitalize transition ${mode === item ? darkMode ? "bg-zinc-700 text-white shadow" : "bg-white text-zinc-900 shadow" : darkMode ? "text-zinc-500 hover:text-zinc-300" : "text-zinc-500 hover:text-zinc-800"}`}
        >
          <span className="hidden md:inline">{item}</span>
          <span className="md:hidden" aria-hidden>{item === "overview" ? "O" : "W"}</span>
        </button>
      ))}
    </div>
  );
}
