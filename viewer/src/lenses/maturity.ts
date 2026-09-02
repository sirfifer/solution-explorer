/**
 * The lens maturity table, as a dependency-free constant.
 *
 * Every lens declares a maturity (card R3, utils/channel.ts): a stable lens is
 * active on every channel, a beta or experimental one only when the resolved
 * `?channel=` activates it. The registry filters on exactly this, so which
 * lenses a reader can see depends on it.
 *
 * It lives in its own module, importing nothing, for one reason: the crawl's
 * expectation model has to know which lenses a projection warrants, and that
 * answer is not derivable from the projection alone because the channel gate
 * can switch a lens off regardless of what the data holds. `viewer/tests/crawl`
 * otherwise imports nothing from `viewer/src`, deliberately, so that a change
 * to the app which breaks the published contract shows up as a failure rather
 * than being compensated for. This table is the single agreed exception, and it
 * is safe to be one precisely because it is data with no behaviour: no React,
 * no store, no DOM, nothing to execute.
 *
 * The lens definitions below read their `maturity` from here, so this is the
 * source rather than a copy of it. Moving a lens to "beta" here moves it in the
 * app and in the crawl's expectations at the same time, which is the property
 * that makes a duplicated table not worth having.
 */

/** Stability of a surface. Mirrors `Channel` in utils/channel.ts by value. */
export type LensMaturity = "stable" | "beta" | "experimental";

/**
 * Maturity by lens id, for every registered lens. A lens absent from this table
 * is treated as stable by the registry (the `maturity?:` default), so an entry
 * here is only load bearing when it is NOT stable; the stable rows are listed
 * anyway so the table is a complete inventory rather than a list of exceptions.
 */
export const LENS_MATURITY: Record<string, LensMaturity> = {
  structure: "stable",
  inventory: "stable",
  activity: "stable",
  flow: "stable",
  capability: "stable",
  data: "stable",
  rules: "stable",
  design: "stable",
  support: "stable",
  security: "stable",
};
