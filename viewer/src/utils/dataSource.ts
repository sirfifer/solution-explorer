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
  const value = raw.trim();
  if (!value) return DEFAULT_DATA_BASE;
  // Reject anything that could escape the current origin: an absolute URL
  // (has a scheme), a protocol-relative `//host`, or a root-absolute `/path`.
  // Also reject parent-directory traversal so a member link stays inside the
  // deployed tree.
  if (/^[a-z][a-z0-9+.-]*:/i.test(value)) return DEFAULT_DATA_BASE; // scheme
  if (value.startsWith("//")) return DEFAULT_DATA_BASE; // protocol-relative
  if (value.startsWith("/")) return DEFAULT_DATA_BASE; // root-absolute
  if (value.split("/").some((seg) => seg === "..")) return DEFAULT_DATA_BASE;
  // Strip a trailing slash so join is unambiguous.
  return value.replace(/\/+$/, "") || DEFAULT_DATA_BASE;
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
