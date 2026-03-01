/**
 * URL state management for deep linking.
 *
 * Encodes navigation state (selected component, active tab, drill level)
 * in URL query parameters so views can be shared and bookmarked.
 */

export interface UrlState {
  component?: string;
  tab?: string;
  drill?: string;
}

/** Read current navigation state from URL query parameters. */
export function parseUrlState(): UrlState {
  const params = new URLSearchParams(window.location.search);
  return {
    component: params.get("component") || undefined,
    tab: params.get("tab") || undefined,
    drill: params.get("drill") || undefined,
  };
}

/** Update URL without adding a browser history entry (for minor state changes). */
export function replaceUrlState(state: UrlState): void {
  const url = buildUrl(state);
  window.history.replaceState({}, "", url);
}

/** Update URL with a new browser history entry (for significant navigation). */
export function pushUrlState(state: UrlState): void {
  const url = buildUrl(state);
  window.history.pushState({}, "", url);
}

function buildUrl(state: UrlState): string {
  const params = new URLSearchParams();
  if (state.component) params.set("component", state.component);
  if (state.tab) params.set("tab", state.tab);
  if (state.drill) params.set("drill", state.drill);
  const search = params.toString();
  return search ? `${window.location.pathname}?${search}` : window.location.pathname;
}
