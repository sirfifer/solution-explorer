// Data-source resolution for single-repo AND multi-repo (solution) datasets.
//
// The viewer historically fetched a fixed `./architecture/` tree. A composed
// solution (MULTI-REPO-DESIGN.md, M1) deploys the SAME tree at the root, but
// each member repo lives under `./architecture/members/<slug>/` as a complete
// standalone projection. To open a member with the unchanged viewer experience,
// a `?data=<base>` query param overrides the fetch base. This is the KISS route:
// no build-time config, no router, just a prefix resolved from the URL.
//
//   default (no param):        ./architecture
//   ?data=./architecture/members/web  -> that member's projection
//
// The base is sanitized: only a relative path is accepted (no scheme, no
// protocol-relative `//host`, no leading slash), so the param cannot point the
// viewer at an arbitrary origin. A rejected value falls back to the default.

export const DEFAULT_DATA_BASE = "./architecture";

const DATA_PARAM = "data";

function sanitizeBase(raw: string | null): string {
  if (!raw) return DEFAULT_DATA_BASE;
  let value = raw.trim();
  if (!value) return DEFAULT_DATA_BASE;
  // Decode percent-encoding first so an encoded attack cannot slip past the
  // shape check (%5C backslash, %2e%2e traversal). A malformed encoding is
  // rejected outright.
  try {
    value = decodeURIComponent(value);
  } catch {
    return DEFAULT_DATA_BASE;
  }
  // ALLOWLIST, not blocklist (adversarial-review blocker: a leading backslash
  // is normalized by the WHATWG URL parser into a protocol-relative
  // cross-origin URL, and encoded traversal escaped the deployed tree). The
  // only shapes a solution ever emits are the default base and member bases
  // beneath it, so only those shapes are accepted:
  //   ./architecture
  //   ./architecture/members/<slug>[/members/<slug>...]
  // with slugs restricted to the slugify alphabet [a-z0-9-].
  const m = value.replace(/\/+$/, "");
  if (m === DEFAULT_DATA_BASE) return DEFAULT_DATA_BASE;
  if (/^\.\/architecture(\/members\/[a-z0-9-]+)+$/.test(m)) return m;
  return DEFAULT_DATA_BASE;
}

// The current data base, resolved from `?data=` (default `./architecture`).
export function getDataBase(search: string = window.location.search): string {
  try {
    const params = new URLSearchParams(search);
    return sanitizeBase(params.get(DATA_PARAM));
  } catch {
    return DEFAULT_DATA_BASE;
  }
}

// Resolve a projection-relative path (e.g. "manifest.json",
// "data/detail-x.json") against the current data base.
export function dataUrl(relPath: string, search: string = window.location.search): string {
  const base = getDataBase(search);
  const rel = relPath.replace(/^\/+/, "");
  return `${base}/${rel}`;
}

// True when a non-default data base is selected (a member is open inside a
// solution), so the viewer can show a "back to solution" affordance.
export function isMemberView(search: string = window.location.search): boolean {
  return getDataBase(search) !== DEFAULT_DATA_BASE;
}

// The URL to open a member's dataset in the standalone viewer experience.
// `projection` is the member's path relative to the solution root (e.g.
// "members/web/"), and `solutionBase` is the solution root data base.
export function memberDataUrl(projection: string, solutionBase: string): string {
  const base = solutionBase.replace(/\/+$/, "");
  const proj = projection.replace(/^\/+|\/+$/g, "");
  const target = `${base}/${proj}`;
  const params = new URLSearchParams(window.location.search);
  params.set(DATA_PARAM, target);
  return `?${params.toString()}`;
}
