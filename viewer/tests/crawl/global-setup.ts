/**
 * Remote target support: crawl a deployed origin, not just a local serve root.
 *
 * The crawl's whole method is comparing the DOM against the projection, so it
 * needs the projection on disk before the first worker starts. Against a local
 * serve root that is free: the directory is right there. Against the published
 * demo there is no directory, only an origin, and the projection has to be
 * fetched once, up front, and handed to the workers as CRAWL_DATA_DIR.
 *
 * Fetched here rather than per worker on purpose. A worker that downloads its
 * own copy pays for it once per worker and, worse, can be looking at a
 * different deployment from its neighbour if a release lands mid-run. One
 * download, one version stamp on the run record, one answer to "what was
 * crawled".
 *
 * What is fetched is deliberately the minimum the contract reads eagerly:
 * manifest.json (required), publication.json (optional, a 404 is normal and
 * already on the allowlist), and the search index's manifest plus its first
 * shard, which is all drawTargets reads. Detail shards are NOT mirrored: they
 * are fetched on demand through the request context (contract.loadDetail), so a
 * 573-component subject does not become a 300 MB download before any test runs.
 *
 * Local runs are untouched. With CRAWL_SERVE_DIR set this returns immediately
 * and CRAWL_DATA_DIR keeps its existing meaning.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

/** How long any one download may take before the run fails with a clear reason. */
const FETCH_TIMEOUT_MS = 60_000;

/**
 * A host reduced to one safe path segment. Same allowlist discipline as the
 * reporter's pathSafe: the input is somebody else's origin, and guessing which
 * characters are dangerous means missing the one you did not think of.
 */
function hostSegment(url: string): string {
  let host: string;
  try {
    host = new URL(url).host;
  } catch {
    host = "unknown";
  }
  const cleaned = host
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/^[.-]+/, "")
    .replace(/-+$/, "")
    .slice(0, 64);
  return cleaned || "unknown";
}

async function download(
  baseUrl: string,
  relPath: string,
  destDir: string,
  { required }: { required: boolean },
): Promise<unknown | null> {
  const url = new URL(relPath, baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`).toString();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(url, { signal: controller.signal });
  } catch (err) {
    if (required) {
      throw new Error(`could not fetch ${url}: ${(err as Error).message}`);
    }
    return null;
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) {
    if (required) {
      throw new Error(`${url} answered ${res.status}; the crawl needs it to build expectations`);
    }
    return null;
  }
  const text = await res.text();
  // A single-page-app host answers 200 with index.html for anything it does not
  // recognise, so "it returned something" is not "the file exists". The same
  // guard the app itself applies (isJsonResponse in App.tsx).
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    if (required) {
      throw new Error(
        `${url} answered 200 but not JSON (an SPA fallback, most likely). ` +
          `The crawl only covers split-mode projections served at /architecture/.`,
      );
    }
    return null;
  }
  const dest = path.join(destDir, relPath.replace(/^architecture\//, ""));
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, text, "utf8");
  return parsed;
}

export default async function globalSetup(): Promise<void> {
  const serveDir = process.env.CRAWL_SERVE_DIR;
  const baseUrl = process.env.CRAWL_BASE_URL;
  // A local serve root, or no remote named: nothing to mirror. The existing
  // path is unchanged, which is the point of both guards.
  if (serveDir || !baseUrl) return;
  if (process.env.CRAWL_DATA_DIR) return;

  const dataDir = path.join(
    HERE,
    "results",
    "remote-data",
    hostSegment(baseUrl),
    "architecture",
  );
  fs.rmSync(dataDir, { recursive: true, force: true });
  fs.mkdirSync(dataDir, { recursive: true });

  const manifest = (await download(baseUrl, "architecture/manifest.json", dataDir, {
    required: true,
  })) as any;

  await download(baseUrl, "architecture/publication.json", dataDir, { required: false });

  const searchManifest = (await download(
    baseUrl,
    "architecture/search/manifest.json",
    dataDir,
    { required: false },
  )) as any;
  // One shard is all drawTargets reads, and on a large subject the rest are
  // hundreds of megabytes for no extra signal (see search.spec.ts).
  const firstShard = searchManifest?.shards?.[0];
  if (typeof firstShard === "string") {
    await download(baseUrl, `architecture/search/${firstShard}`, dataDir, { required: false });
  }

  process.env.CRAWL_DATA_DIR = dataDir;
  // Read by the reporter so the run record says which deployment this was, and
  // which build of it, rather than only that it was remote.
  process.env.CRAWL_REMOTE = "1";
  process.env.CRAWL_REMOTE_GENERATED_AT = String(manifest?.generated_at ?? "");

  // eslint-disable-next-line no-console
  console.log(
    `[crawl] remote target ${baseUrl}: mirrored ${manifest?.name ?? "unknown"} ` +
      `(generated ${manifest?.generated_at ?? "unknown"}) into ${dataDir}`,
  );
}
