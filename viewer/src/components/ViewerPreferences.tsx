import { useEffect } from "react";
import { useArchStore } from "../store";
import { interfaceHref } from "../utils/urlState";

const INTERFACES = [
  {
    mode: "overview" as const,
    label: "New front door",
    description: "Comprehension-first orientation, guided questions, and atlas entry.",
  },
  {
    mode: "workbench" as const,
    label: "Classic explorer",
    description: "The original dense graph, lenses, tree, and detail workspace.",
  },
];

export function ViewerPreferences() {
  const state = useArchStore();
  useEffect(() => {
    if (!state.preferencesOpen) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") state.setPreferencesOpen(false);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [state.preferencesOpen, state.setPreferencesOpen]);
  if (!state.preferencesOpen) return null;
  const dark = state.darkMode;
  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-black/45" role="dialog" aria-modal="true" aria-label="Viewer preferences">
      <button className="absolute inset-0" aria-label="Close preferences" onClick={() => state.setPreferencesOpen(false)} />
      <aside className={`relative h-full w-full max-w-md overflow-y-auto border-l p-6 shadow-2xl ${dark ? "border-zinc-800 bg-zinc-950" : "border-zinc-200 bg-zinc-50"}`}>
        <div className="flex items-start justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-500">Viewer preferences</p><h2 className={`mt-1 text-xl font-bold ${dark ? "text-zinc-100" : "text-zinc-900"}`}>Choose how you return</h2></div><button className="min-h-11 min-w-11 rounded-lg p-2 text-zinc-500" onClick={() => state.setPreferencesOpen(false)} aria-label="Close viewer preferences">✕</button></div>
        <section className="mt-6" aria-labelledby="interface-heading">
          <div className="flex items-end justify-between gap-4">
            <div>
              <h3 id="interface-heading" className={`text-sm font-semibold ${dark ? "text-zinc-200" : "text-zinc-800"}`}>Interface</h3>
              <p className={`mt-1 text-xs leading-relaxed ${dark ? "text-zinc-400" : "text-zinc-600"}`}>Switch this tab, or open both interfaces side by side.</p>
            </div>
            <span className={`shrink-0 rounded-full px-2 py-1 text-[10px] font-semibold ${dark ? "bg-cyan-400/10 text-cyan-300" : "bg-cyan-50 text-cyan-700"}`}>Same data</span>
          </div>
          <div className="mt-3 space-y-2">
            {INTERFACES.map((item) => {
              const active = state.experienceMode === item.mode;
              return (
                <div key={item.mode} className={`rounded-xl border p-3 ${active ? dark ? "border-cyan-500/50 bg-cyan-500/10" : "border-cyan-300 bg-cyan-50" : dark ? "border-zinc-800 bg-zinc-900" : "border-zinc-200 bg-white"}`}>
                  <button
                    className="flex min-h-11 w-full items-center justify-between gap-3 text-left"
                    aria-pressed={active}
                    aria-label={`Switch to ${item.label}`}
                    onClick={() => {
                      state.setExperienceMode(item.mode);
                      state.setPreferencesOpen(false);
                    }}
                  >
                    <span>
                      <strong className={`block text-sm ${dark ? "text-zinc-100" : "text-zinc-900"}`}>{item.label}</strong>
                      <small className={`mt-1 block leading-relaxed ${dark ? "text-zinc-400" : "text-zinc-600"}`}>{item.description}</small>
                    </span>
                    <span aria-hidden className={active ? "text-cyan-500" : "text-zinc-500"}>{active ? "●" : "○"}</span>
                  </button>
                  <a
                    href={interfaceHref(item.mode)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`mt-2 inline-flex min-h-11 items-center text-xs font-semibold sm:min-h-0 ${dark ? "text-cyan-300" : "text-cyan-700"}`}
                    aria-label={`Open ${item.label} in a new tab with the same data`}
                  >
                    Open in another tab ↗
                  </a>
                </div>
              );
            })}
          </div>
          <p className={`mt-3 text-xs leading-relaxed ${dark ? "text-zinc-500" : "text-zinc-600"}`}>
            Comparing <strong className={dark ? "text-zinc-300" : "text-zinc-700"}>{state.architecture?.name ?? "the current projection"}</strong>. Only the <code>mode</code> parameter changes; the data URL and navigation parameters stay the same.
          </p>
        </section>
        <PreferenceSelect label="Start interface" value={state.startView} options={[{ value: "overview", label: "New front door" }, { value: "workbench", label: "Classic explorer" }, { value: "last", label: "Last used" }]} onChange={(value) => state.setStartView(value as typeof state.startView)} dark={dark} />
        <PreferenceSelect label="Overview direction" value={state.overviewDirection} options={["portrait", "questions", "atlas"]} onChange={(value) => state.setOverviewDirection(value as typeof state.overviewDirection)} dark={dark} />
        <PreferenceSelect label="Workbench density" value={state.workbenchDensity} options={["focused", "dense"]} onChange={(value) => state.setWorkbenchDensity(value as typeof state.workbenchDensity)} dark={dark} />
        <label className={`mt-5 flex min-h-11 items-center justify-between rounded-xl border p-4 ${dark ? "border-zinc-800 bg-zinc-900" : "border-zinc-200 bg-white"}`}><span><strong className={`block text-sm ${dark ? "text-zinc-200" : "text-zinc-800"}`}>Remember navigation</strong><small className={dark ? "text-zinc-400" : "text-zinc-600"}>Resume the last aperture when Start interface is Last used.</small></span><input className="h-6 w-6" type="checkbox" checked={state.rememberNavigation} onChange={(event) => state.setRememberNavigation(event.target.checked)} /></label>
        <p className={`mt-6 text-xs leading-relaxed ${dark ? "text-zinc-400" : "text-zinc-600"}`}>Themes and light/dark appearance are stored separately. Navigation stays in the URL so a shared link always wins over these preferences.</p>
      </aside>
    </div>
  );
}

type PreferenceOption = string | { value: string; label: string };

function PreferenceSelect({ label, value, options, onChange, dark }: { label: string; value: string; options: PreferenceOption[]; onChange: (value: string) => void; dark: boolean }) {
  return <label className="mt-5 block"><span className={`mb-2 block text-sm font-semibold ${dark ? "text-zinc-300" : "text-zinc-700"}`}>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)} className={`min-h-11 w-full rounded-xl border px-3 py-2.5 text-sm capitalize ${dark ? "border-zinc-800 bg-zinc-900 text-zinc-200" : "border-zinc-200 bg-white text-zinc-800"}`}>{options.map((option) => { const normalized = typeof option === "string" ? { value: option, label: option } : option; return <option key={normalized.value} value={normalized.value}>{normalized.label}</option>; })}</select></label>;
}
