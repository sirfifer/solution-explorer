/**
 * Maturity-channel gating for the viewer (card R3).
 *
 * The mirror of analyzer/features.py on the client, and the same Kubernetes /
 * Rust maturity model: each gateable surface declares a stability (stable, beta,
 * or experimental) and a resolved channel (default stable) decides what is
 * active. There are two independent, server-free mechanisms, matching the two
 * kinds of unfinished work described in ROBUSTNESS-STRATEGY.md:
 *
 *   1. BUILD-TIME constant (`__EXPERIMENTAL_BUILD__`). Genuinely-unfinished code
 *      wraps itself in `if (__EXPERIMENTAL_BUILD__) { ... }` so the bundler
 *      dead-code-eliminates it from a production build: invisible to users and
 *      bots, zero bundle cost, not reachable at all. A production build defines
 *      it `false`; an experimental build (`VITE_EXPERIMENTAL_BUILD=1`) defines it
 *      `true`. The diagnostic at the bottom of this file is the honest reference
 *      consumer; no unfinished user feature exists today.
 *
 *   2. RUNTIME channel (`resolveChannel`). Alpha features that ARE wired but
 *      should be off by default declare a `maturity` on their registry entry and
 *      are exercised via a `?channel=` URL-param override, rendered with an
 *      explicit label (see `maturitySuffix`). The registry filters by the
 *      resolved channel (see lenses/registry.ts).
 *
 * Determinism / no-theater: the default `stable` channel activates only stable
 * surfaces, so a default page is unchanged. An experimental surface that shows
 * up always says it is experimental; a half-built surface that looks done is
 * theater.
 */

export type Channel = "stable" | "beta" | "experimental";

/** Stability levels, most stable (index 0) to least. A channel's level is its index. */
export const CHANNEL_ORDER: readonly Channel[] = ["stable", "beta", "experimental"] as const;

export const DEFAULT_CHANNEL: Channel = "stable";

/** The URL query parameter that overrides the channel (labeled, opt-in). */
export const CHANNEL_PARAM = "channel";

export function isChannel(value: string | null | undefined): value is Channel {
  return value === "stable" || value === "beta" || value === "experimental";
}

export function channelLevel(channel: Channel): number {
  const i = CHANNEL_ORDER.indexOf(channel);
  return i < 0 ? 0 : i;
}

/**
 * Whether a surface of the given `maturity` (undefined means stable) is active
 * on `channel`. Rust-toolchain semantics: active when the channel is at least as
 * unstable as the surface. A stable surface is always active; an experimental
 * one is active only on the experimental channel.
 */
export function isMaturityActive(maturity: Channel | undefined, channel: Channel): boolean {
  return channelLevel(channel) >= channelLevel(maturity ?? "stable");
}

/**
 * Resolve the runtime channel. Precedence: an explicit `?channel=` URL-param
 * override (the labeled way to exercise a wired alpha surface), else the build's
 * baseline (an experimental build defaults to experimental; a production build
 * to stable). `search` and `experimentalBuild` are injectable so the resolver is
 * pure and unit-testable; the defaults read the live location and build constant.
 */
export function resolveChannel(
  search?: string,
  experimentalBuild: boolean = __EXPERIMENTAL_BUILD__,
): Channel {
  const raw = search ?? (typeof window !== "undefined" ? window.location.search : "");
  const requested = new URLSearchParams(raw).get(CHANNEL_PARAM);
  if (isChannel(requested)) return requested;
  return experimentalBuild ? "experimental" : DEFAULT_CHANNEL;
}

/**
 * The explicit label suffix for a non-stable surface, e.g. " (experimental)".
 * Empty for a stable surface. This is the no-theater label: any experimental or
 * beta surface that is visible says so.
 */
export function maturitySuffix(maturity: Channel | undefined): string {
  const m = maturity ?? "stable";
  return m === "stable" ? "" : ` (${m})`;
}

// Build-time gate reference consumer (card R3). A production build defines
// `__EXPERIMENTAL_BUILD__` as `false`, so the bundler dead-code-eliminates this
// whole block: the EXPERIMENTAL_BUILD_DIAGNOSTIC sentinel never appears in the
// production bundle (verified by grep in tests/verification). An experimental
// build logs the resolved gate state once. This is the honest demonstration that
// build-gated code is invisible in production; no unfinished user feature exists.
if (__EXPERIMENTAL_BUILD__) {
  console.info(
    "[solution-explorer] EXPERIMENTAL_BUILD_DIAGNOSTIC: maturity gating active; channel =",
    resolveChannel(),
  );
}
