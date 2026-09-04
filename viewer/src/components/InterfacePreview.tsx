import { useMemo, useState } from "react";
import type { UISurfaceHotspot, UISurfacesProjection } from "../types";
import { dataUrl } from "../utils/dataSource";

const UI_KINDS = new Set(["desktop-app", "web-app", "web-client", "ios-app", "android-app", "mobile-client", "watch-app"]);

export function hasUserInterface(formFactors: Array<{ kind: string }> | undefined): boolean {
  return Boolean(formFactors?.some((factor) => UI_KINDS.has(factor.kind)));
}

export function InterfacePreview({
  surfaces,
  expectsInterface,
  darkMode,
  onOpenSource,
}: {
  surfaces?: UISurfacesProjection;
  expectsInterface: boolean;
  darkMode: boolean;
  onOpenSource: (hotspot: UISurfaceHotspot) => void | Promise<void>;
}) {
  const primaryClient = surfaces?.clients.find((client) => client.primary) ?? surfaces?.clients[0];
  const [clientId, setClientId] = useState<string | null>(null);
  const selectedClient = surfaces?.clients.find((client) => client.id === clientId) ?? primaryClient;
  const availableScreens = useMemo(
    () => surfaces?.screens.filter((screen) => screen.client_id === selectedClient?.id) ?? [],
    [selectedClient?.id, surfaces],
  );
  const [screenId, setScreenId] = useState<string | null>(null);
  const screen = availableScreens.find((item) => item.id === screenId)
    ?? availableScreens.find((item) => item.role === "primary")
    ?? availableScreens[0];
  const [activeHotspot, setActiveHotspot] = useState<string | null>(null);

  if (!surfaces || !screen || !selectedClient) {
    if (!expectsInterface) return null;
    return (
      <section data-testid="interface-preview-missing" className={`rounded-[2rem] border p-6 ${darkMode ? "border-amber-500/20 bg-amber-500/5" : "border-amber-200 bg-amber-50"}`}>
        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-500">Interface capture</p>
        <h3 className={`mt-2 text-lg font-bold ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>No verified screenshot is attached</h3>
        <p className="mt-2 text-sm leading-6 text-zinc-500">This subject has a user interface, but this snapshot does not yet include a provenance-checked capture.</p>
      </section>
    );
  }

  const matchLabel = screen.capture.source_match === "exact" ? "Exact source match" : "Representative runtime";

  return (
    <section data-testid="interface-preview" data-source-match={screen.capture.source_match} className={`overflow-hidden rounded-[2rem] border ${darkMode ? "border-zinc-800 bg-zinc-950/75" : "border-zinc-200 bg-white"}`}>
      <div className="flex flex-wrap items-start justify-between gap-3 p-5 pb-4 sm:px-6">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-500">Interface · {selectedClient.label}</p>
          <h3 className={`mt-1 text-xl font-bold ${darkMode ? "text-zinc-100" : "text-zinc-900"}`}>{screen.label}</h3>
          <p className="mt-1 text-xs text-zinc-500">Hover a region to identify it. Open it to follow the screenshot into source.</p>
        </div>
        <span data-testid="capture-provenance" className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ${screen.capture.source_match === "exact" ? "border-emerald-500/30 text-emerald-500" : "border-amber-500/30 text-amber-500"}`}>{matchLabel}</span>
      </div>

      <div data-testid="interface-client-coverage" className="flex flex-wrap gap-2 px-5 pb-4 sm:px-6">
        {surfaces.clients.map((client) => {
          const hasScreen = surfaces.screens.some((item) => item.client_id === client.id);
          const selected = client.id === selectedClient.id;
          return <button
            key={client.id}
            type="button"
            disabled={!hasScreen}
            onClick={() => setClientId(client.id)}
            title={client.note}
            className={`min-h-11 rounded-full border px-3 py-2 text-[10px] font-bold uppercase tracking-wide sm:min-h-0 ${selected ? "border-cyan-400 bg-cyan-500/10 text-cyan-500" : client.coverage === "missing" || client.coverage === "unavailable" ? "border-amber-500/30 text-amber-500" : darkMode ? "border-zinc-700 text-zinc-400" : "border-zinc-300 text-zinc-600"} disabled:cursor-not-allowed disabled:opacity-80`}
          >{client.label} · {client.coverage}</button>;
        })}
      </div>

      {availableScreens.length > 1 && <div className="flex gap-2 px-5 pb-4 sm:px-6">{availableScreens.map((item) => <button key={item.id} onClick={() => setScreenId(item.id)} className={`min-h-11 rounded-lg px-3 text-xs font-semibold sm:min-h-0 sm:py-2 ${item.id === screen.id ? "bg-cyan-500 text-white" : darkMode ? "bg-zinc-900 text-zinc-300" : "bg-zinc-100 text-zinc-700"}`}>{item.label}</button>)}</div>}

      <div className="relative bg-black" data-testid="interface-image-stage">
        <img src={dataUrl(screen.image.path)} width={screen.image.width} height={screen.image.height} alt={`${screen.capture.runtime_name} ${screen.label} interface capture`} className="block h-auto w-full" />
        {screen.hotspots.map((hotspot) => {
          const active = activeHotspot === hotspot.id;
          return <button
            key={hotspot.id}
            type="button"
            aria-label={`${hotspot.label}: open source`}
            title={`${hotspot.label} · ${hotspot.evidence.file}:${hotspot.evidence.line}`}
            onMouseEnter={() => setActiveHotspot(hotspot.id)}
            onMouseLeave={() => setActiveHotspot(null)}
            onFocus={() => setActiveHotspot(hotspot.id)}
            onBlur={() => setActiveHotspot(null)}
            onClick={() => onOpenSource(hotspot)}
            className={`absolute border-2 transition ${active ? "border-cyan-300 bg-cyan-400/20 shadow-[0_0_0_2px_rgba(0,0,0,0.45)]" : "border-transparent hover:border-cyan-300 hover:bg-cyan-400/20 focus:border-cyan-300 focus:bg-cyan-400/20"}`}
            style={{ left: `${hotspot.rect.x * 100}%`, top: `${hotspot.rect.y * 100}%`, width: `${hotspot.rect.width * 100}%`, height: `${hotspot.rect.height * 100}%` }}
          ><span className="sr-only">{hotspot.label}</span></button>;
        })}
      </div>

      <div className="grid gap-2 p-4 sm:grid-cols-2 sm:p-5">
        {screen.hotspots.map((hotspot) => <button key={hotspot.id} onMouseEnter={() => setActiveHotspot(hotspot.id)} onMouseLeave={() => setActiveHotspot(null)} onFocus={() => setActiveHotspot(hotspot.id)} onBlur={() => setActiveHotspot(null)} onClick={() => onOpenSource(hotspot)} className={`min-h-11 rounded-xl border px-3 py-2 text-left ${activeHotspot === hotspot.id ? "border-cyan-400 bg-cyan-500/10" : darkMode ? "border-zinc-800 bg-zinc-900/60" : "border-zinc-200 bg-zinc-50"}`}>
          <strong className={`block text-xs ${darkMode ? "text-zinc-200" : "text-zinc-800"}`}>{hotspot.label}</strong>
          <span className="mt-1 block truncate text-[10px] text-zinc-500">{hotspot.evidence.file}:{hotspot.evidence.line}</span>
        </button>)}
      </div>
      <div className={`border-t px-5 py-3 text-[10px] leading-4 text-zinc-500 ${darkMode ? "border-zinc-800" : "border-zinc-200"}`}>
        Captured {screen.capture.captured_at.slice(0, 10)} with {screen.capture.runtime_name} {screen.capture.runtime_version}. {screen.capture.notes}
      </div>
    </section>
  );
}
