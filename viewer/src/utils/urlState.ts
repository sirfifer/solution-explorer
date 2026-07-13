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
  // Inbound deep-link params (P3-2). `file` is a repo-relative source path; the
  // optional `line` selects the symbol whose range contains it. These are
  // consumed once on load to drive navigation and are not re-persisted into the
  // URL by buildUrl (the resolved component/drill/tab replace them).
  file?: string;
  line?: number;
}

/** Read current navigation state from URL query parameters. */
export function parseUrlState(): UrlState {
  const params = new URLSearchParams(window.location.search);
  const lineRaw = params.get("line");
  // Strict positive-integer token only: parseInt would accept "12abc" as 12,
  // silently navigating somewhere the pasted link never named.
  const lineNum = lineRaw !== null && /^\d+$/.test(lineRaw) ? Number.parseInt(lineRaw, 10) : NaN;
  return {
    component: params.get("component") || undefined,
    tab: params.get("tab") || undefined,
    drill: params.get("drill") || undefined,
    file: params.get("file") || undefined,
    line: Number.isFinite(lineNum) && lineNum > 0 ? lineNum : undefined,
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
