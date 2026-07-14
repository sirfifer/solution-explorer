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

    // Restore the lens first so the graph selects the right nodes/edges before
    // drill/selection are applied (P6-1). Unknown/unavailable ids fall back to
    // Structure inside setLens.
    if (urlState.lens) {
      store.setLens(urlState.lens);
    }

    // Flow lens follow state (P6-2). If the link names an entry flow (and the
    // Flow lens is active and available), enter follow mode and jump to the saved
    // step. This drives its own selection, so it takes precedence over the
    // component/drill params below.
    if (urlState.flow && useArchStore.getState().lens === "flow") {
      store.setFlowEntry(urlState.flow);
      if (urlState.step) store.flowGoToStep(urlState.step);
      return;
    }

    // Capability/Data lens selection (P6-3). If the link names a capability (under
    // the Capability lens) or an entity (under the Data lens), select it; that
    // drives its own component selection, so it takes precedence over the
    // component/drill params below.
    if (urlState.capability && useArchStore.getState().lens === "capability") {
      store.selectCapability(urlState.capability);
      return;
    }
    if (urlState.entity && useArchStore.getState().lens === "data") {
      store.selectEntity(urlState.entity);
      return;
    }

    // Inbound file/line deep link takes precedence: it computes its own drill and
    // selection from the owning component, so it overrides any component/drill
    // params (P3-2). The tab param is still honored, defaulting to the Files tab.
    if (urlState.file) {
      // Seed the tab into the URL before navigation so the detail panel mounts on
      // it; the URL writer below preserves it as component/drill are filled in.
      replaceUrlState({ tab: urlState.tab || "files" });
      store.openFileDeepLink(urlState.file, urlState.line ?? null);
      return;
    }

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
      const selChanged = state.selectedComponentId !== prev.selectedComponentId;
      const drillChanged = state.drillLevel !== prev.drillLevel;
      const lensChanged = state.lens !== prev.lens;
      const flowChanged =
        state.flowEntryId !== prev.flowEntryId || state.flowStep !== prev.flowStep;
      const capEntityChanged =
        state.selectedCapabilityId !== prev.selectedCapabilityId ||
        state.selectedEntityId !== prev.selectedEntityId;
      if (selChanged || drillChanged || lensChanged || flowChanged || capEntityChanged) {
        const update = {
          component: state.selectedComponentId || undefined,
          drill: state.drillLevel || undefined,
          // Carry the active lens so a lens switch is shareable and survives
          // back/forward (P6-1, invariant I12).
          lens: state.lens,
          // Carry the Flow follow state so a walked flow is shareable (P6-2).
          flow: state.flowEntryId || undefined,
          step: state.flowStep || undefined,
          // Carry the Capability/Data lens selection so it is shareable (P6-3).
          capability: state.selectedCapabilityId || undefined,
          entity: state.selectedEntityId || undefined,
          // Preserve the active-tab param that DetailPanel manages; rebuilding
          // the URL from component/drill alone would erase it (F-VW-7).
          tab: parseUrlState().tab,
        };
        // pushState for drill navigation (supports browser back), replaceState
        // for selection or a lens-only change (minor changes that should not add
        // a history entry).
        if (drillChanged) {
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
        // Restore the lens from the target URL (absent means the default).
        store.setLens(urlState.lens ?? "structure");

        // Flow follow state (P6-2): restore or clear it to match the target URL,
        // then let it own selection when present.
        if (urlState.flow && useArchStore.getState().lens === "flow") {
          store.setFlowEntry(urlState.flow);
          if (urlState.step) store.flowGoToStep(urlState.step);
          return;
        }
        if (useArchStore.getState().flowEntryId) store.clearFlow();

        // Capability/Data lens selection (P6-3): restore or clear it to match the
        // target URL, then let it own the component selection when present.
        if (urlState.capability && useArchStore.getState().lens === "capability") {
          store.selectCapability(urlState.capability);
          return;
        }
        if (urlState.entity && useArchStore.getState().lens === "data") {
          store.selectEntity(urlState.entity);
          return;
        }
        if (useArchStore.getState().selectedCapabilityId) store.clearCapability();
        if (useArchStore.getState().selectedEntityId) store.clearEntity();

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
