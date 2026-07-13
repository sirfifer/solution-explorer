import { useEffect, useRef } from "react";
import { useArchStore } from "../store";
import { parseUrlState, replaceUrlState, pushUrlState } from "../utils/urlState";

/**
 * Two-way sync between the store's navigation state and the browser URL.
 *
 * Extracted from App so the back/forward wiring is testable in isolation
 * against the real store (F-VW-2). Three concerns:
 *  1. Restore navigation state from the URL once, on first architecture load.
 *  2. Push/replace the URL when the store's drill/selection changes.
 *  3. Apply the URL to the store on browser back/forward (popstate).
 *
 * The popstate handler mutates the store, which fires the store subscription in
 * (2). Without suppression that subscription pushes a NEW history entry while a
 * popstate is being applied, which re-pushes the state just navigated to and
 * destroys the forward stack (F-VW-2). `applyingPopStateRef` gates the
 * subscription so no URL write happens while a popstate is being applied. The
 * browser has already set the URL to the target before firing popstate, so
 * suppressing our own write is correct.
 */
export function useUrlSync(): void {
  const architecture = useArchStore((s) => s.architecture);
  const urlRestoredRef = useRef(false);
  const applyingPopStateRef = useRef(false);

  // Restore navigation state from URL on initial architecture load.
  useEffect(() => {
    if (!architecture || urlRestoredRef.current) return;
    urlRestoredRef.current = true;

    const urlState = parseUrlState();
    const store = useArchStore.getState();

    // Restore drill level first (so the component is visible in the graph).
    if (urlState.drill) {
      const drillComp = store.getComponentById(urlState.drill);
      if (drillComp) {
        store.drillInto(drillComp);
      }
    }

    // Then restore selected component.
    if (urlState.component) {
      store.selectComponent(urlState.component);
    }
  }, [architecture]);

  // Sync store state changes to the URL.
  useEffect(() => {
    const unsubscribe = useArchStore.subscribe((state, prev) => {
      // Suppress URL writes while a popstate navigation is being applied; the
      // browser already owns the URL during back/forward (F-VW-2).
      if (applyingPopStateRef.current) return;
      if (
        state.selectedComponentId !== prev.selectedComponentId ||
        state.drillLevel !== prev.drillLevel
      ) {
        const isDrillChange = state.drillLevel !== prev.drillLevel;
        const update = {
          component: state.selectedComponentId || undefined,
          drill: state.drillLevel || undefined,
          // Preserve the active-tab param that DetailPanel manages; rebuilding
          // the URL from component/drill alone would erase it (F-VW-7).
          tab: parseUrlState().tab,
        };
        // pushState for drill navigation (supports browser back), replaceState
        // for selection (a minor change that should not add a history entry).
        if (isDrillChange) {
          pushUrlState(update);
        } else {
          replaceUrlState(update);
        }
      }
    });
    return unsubscribe;
  }, []);

  // Handle browser back/forward.
  useEffect(() => {
    const handlePopState = () => {
      const urlState = parseUrlState();
      const store = useArchStore.getState();

      // Guard the store mutations below so the subscription above does not push
      // a fresh history entry mid-popstate and corrupt the forward stack.
      applyingPopStateRef.current = true;
      try {
        if (urlState.drill) {
          const drillComp = store.getComponentById(urlState.drill);
          if (drillComp) {
            store.drillInto(drillComp);
          }
        } else {
          store.navigateToBreadcrumb(-1);
        }

        if (urlState.component) {
          store.selectComponent(urlState.component);
        } else {
          store.selectComponent(null);
        }
      } finally {
        applyingPopStateRef.current = false;
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);
}
