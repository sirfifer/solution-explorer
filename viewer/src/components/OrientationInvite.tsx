import { useArchStore } from "../store";
import { TOOLTIP_COPY } from "../utils/tooltipCopy";

export function OrientationInvite() {
  const darkMode = useArchStore((state) => state.darkMode);
  const orientationInvite = useArchStore((state) => state.orientationInvite);
  const orientationOpen = useArchStore((state) => state.orientationOpen);
  const startOrientation = useArchStore((state) => state.startOrientation);
  const dismissOrientationInvite = useArchStore((state) => state.dismissOrientationInvite);
  const searchOpen = useArchStore((state) => state.searchOpen);
  const findingsOpen = useArchStore((state) => state.findingsSurface.open);
  const supplyChainOpen = useArchStore((state) => state.supplyChainOpen);
  const inventoryOpen = useArchStore((state) => state.inventoryOpen);
  const toursOpen = useArchStore((state) => state.toursOpen);
  const activeTourId = useArchStore((state) => state.activeTourId);
  const helpOpen = useArchStore((state) => state.helpOpen);
  const adminOpen = useArchStore((state) => state.adminOpen);
  const activePanel = useArchStore((state) => state.activePanel);
  const trustOpen = useArchStore((state) => state.trustOpen);
  const preferencesOpen = useArchStore((state) => state.preferencesOpen);

  const anotherOverlayOpen = searchOpen
    || findingsOpen
    || supplyChainOpen
    || inventoryOpen
    || toursOpen
    || Boolean(activeTourId)
    || helpOpen
    || adminOpen
    || activePanel === "review"
    || trustOpen
    || preferencesOpen;

  if (!orientationInvite || orientationOpen || anotherOverlayOpen) return null;

  return (
    <aside
      data-testid="orientation-invite"
      aria-label="New visitor orientation"
      className={`fixed inset-x-0 bottom-0 z-50 border px-4 py-3 shadow-2xl sm:inset-x-auto sm:bottom-14 sm:right-4 sm:w-80 sm:rounded-2xl ${darkMode ? "border-zinc-700 bg-zinc-950 text-zinc-100" : "border-zinc-200 bg-white text-zinc-900"}`}
    >
      <h2 className="text-sm font-bold">New here?</h2>
      <p className={`mt-1 text-xs leading-5 ${darkMode ? "text-zinc-400" : "text-zinc-600"}`}>
        This map takes a minute to learn. Let it show you around.
      </p>
      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          data-testid="orientation-dismiss"
          onClick={dismissOrientationInvite}
          title={TOOLTIP_COPY.orientation.dismiss}
          className={`min-h-11 rounded-lg px-3 py-2 text-xs font-medium sm:min-h-0 ${darkMode ? "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200" : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800"}`}
        >
          Not now
        </button>
        <button
          type="button"
          data-testid="orientation-start"
          onClick={startOrientation}
          title={TOOLTIP_COPY.orientation.start}
          className="min-h-11 rounded-lg bg-cyan-500 px-3 py-2 text-xs font-bold text-zinc-950 hover:bg-cyan-400 sm:min-h-0"
        >
          Show me around
        </button>
      </div>
    </aside>
  );
}
