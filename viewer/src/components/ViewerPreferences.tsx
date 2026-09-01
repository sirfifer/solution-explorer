import { useArchStore } from "../store";

export function ViewerPreferences() {
  const state = useArchStore();
  if (!state.preferencesOpen) return null;
  const dark = state.darkMode;
  return (
    <div className="fixed inset-0 z-[70] flex justify-end bg-black/45" role="dialog" aria-modal="true" aria-label="Viewer preferences">
      <button className="absolute inset-0" aria-label="Close preferences" onClick={() => state.setPreferencesOpen(false)} />
      <aside className={`relative h-full w-full max-w-md overflow-y-auto border-l p-6 shadow-2xl ${dark ? "border-zinc-800 bg-zinc-950" : "border-zinc-200 bg-zinc-50"}`}>
        <div className="flex items-start justify-between"><div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-500">Viewer preferences</p><h2 className={`mt-1 text-xl font-bold ${dark ? "text-zinc-100" : "text-zinc-900"}`}>Choose how you return</h2></div><button className="min-h-11 min-w-11 rounded-lg p-2 text-zinc-500" onClick={() => state.setPreferencesOpen(false)} aria-label="Close viewer preferences">✕</button></div>
        <PreferenceSelect label="Start view" value={state.startView} options={["overview", "workbench", "last"]} onChange={(value) => state.setStartView(value as typeof state.startView)} dark={dark} />
        <PreferenceSelect label="Overview direction" value={state.overviewDirection} options={["portrait", "questions", "atlas"]} onChange={(value) => state.setOverviewDirection(value as typeof state.overviewDirection)} dark={dark} />
        <PreferenceSelect label="Workbench density" value={state.workbenchDensity} options={["focused", "dense"]} onChange={(value) => state.setWorkbenchDensity(value as typeof state.workbenchDensity)} dark={dark} />
        <label className={`mt-5 flex min-h-11 items-center justify-between rounded-xl border p-4 ${dark ? "border-zinc-800 bg-zinc-900" : "border-zinc-200 bg-white"}`}><span><strong className={`block text-sm ${dark ? "text-zinc-200" : "text-zinc-800"}`}>Remember navigation</strong><small className={dark ? "text-zinc-400" : "text-zinc-600"}>Resume the last aperture when Start view is Last.</small></span><input className="h-6 w-6" type="checkbox" checked={state.rememberNavigation} onChange={(event) => state.setRememberNavigation(event.target.checked)} /></label>
        <p className={`mt-6 text-xs leading-relaxed ${dark ? "text-zinc-400" : "text-zinc-600"}`}>Themes and light/dark appearance are stored separately. Navigation stays in the URL so a shared link always wins over these preferences.</p>
      </aside>
    </div>
  );
}

function PreferenceSelect({ label, value, options, onChange, dark }: { label: string; value: string; options: string[]; onChange: (value: string) => void; dark: boolean }) {
  return <label className="mt-5 block"><span className={`mb-2 block text-sm font-semibold ${dark ? "text-zinc-300" : "text-zinc-700"}`}>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)} className={`min-h-11 w-full rounded-xl border px-3 py-2.5 text-sm capitalize ${dark ? "border-zinc-800 bg-zinc-900 text-zinc-200" : "border-zinc-200 bg-white text-zinc-800"}`}>{options.map((option) => <option key={option}>{option}</option>)}</select></label>;
}
