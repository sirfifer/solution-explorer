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
  // Active lens (P6-1). Omitted from the URL when it is the default (Structure)
  // so old links and the default view carry no lens param.
  lens?: string;
  // Flow lens follow state (P6-2). `flow` is the entry flow being walked and
  // `step` its index; both are emitted only under the Flow lens so other lenses'
  // links stay clean. They compose with the existing params.
  flow?: string;
  step?: number;
  // Capability/Data lens selection (P6-3). `capability` is the selected capability
  // id (Capability lens); `entity` is the selected entity id (Data lens). Each is
  // emitted only under its own lens, composing with the existing params.
  capability?: string;
  entity?: string;
  // Rules lens selection (P6-6). `rule` is the selected rule id, emitted only
  // under the Rules lens, composing with the existing params.
  rule?: string;
  // Design lens selection (D4). `finding` is the selected design finding id,
  // emitted only under the Design lens, composing with the existing params.
  finding?: string;
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
  const stepRaw = params.get("step");
  // Same strict token discipline as line: a non-negative integer step or nothing.
  const stepNum = stepRaw !== null && /^\d+$/.test(stepRaw) ? Number.parseInt(stepRaw, 10) : NaN;
  return {
    component: params.get("component") || undefined,
    tab: params.get("tab") || undefined,
    drill: params.get("drill") || undefined,
    lens: params.get("lens") || undefined,
    flow: params.get("flow") || undefined,
    step: Number.isFinite(stepNum) && stepNum >= 0 ? stepNum : undefined,
    capability: params.get("capability") || undefined,
    entity: params.get("entity") || undefined,
    rule: params.get("rule") || undefined,
    finding: params.get("finding") || undefined,
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
  // The data-source override (a member open inside a solution, M1) is
  // orthogonal to nav state and must survive every URL rewrite; dropping it
  // broke member drill-in on the first click and killed shareable member
  // links (adversarial-review blocker). Carry it verbatim when present.
  const existing = new URLSearchParams(window.location.search);
  const dataBase = existing.get("data");
  if (dataBase) params.set("data", dataBase);
  if (state.component) params.set("component", state.component);
  if (state.tab) params.set("tab", state.tab);
  if (state.drill) params.set("drill", state.drill);
  // Only emit the lens param when it is non-default, so Structure URLs (and old
  // links) stay clean and unchanged (P6-1).
  if (state.lens && state.lens !== "structure") params.set("lens", state.lens);
  // Flow follow state rides only under the Flow lens (P6-2). Guarding on the lens
  // keeps the params from leaking onto other lenses' links.
  if (state.lens === "flow" && state.flow) {
    params.set("flow", state.flow);
    if (state.step && state.step > 0) params.set("step", String(state.step));
  }
  // Capability/Data lens selection rides only under its own lens (P6-3), keeping
  // the param off other lenses' links.
  if (state.lens === "capability" && state.capability) {
    params.set("capability", state.capability);
  }
  if (state.lens === "data" && state.entity) {
    params.set("entity", state.entity);
  }
  // Rules lens selection rides only under the Rules lens (P6-6).
  if (state.lens === "rules" && state.rule) {
    params.set("rule", state.rule);
  }
  if (state.lens === "design" && state.finding) {
    params.set("finding", state.finding);
  }
  const search = params.toString();
  return search ? `${window.location.pathname}?${search}` : window.location.pathname;
}
