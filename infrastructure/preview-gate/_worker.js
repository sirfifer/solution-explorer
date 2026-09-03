/**
 * Pages advanced-mode Worker for a published SysCorpus demo bundle.
 *
 * scripts/publish-demo-bundle.py copies this file to the bundle root and
 * replaces the GZIPPED_JSON placeholder with the paths it compressed. It is
 * committed here, beside the gate it wraps, because the first deployment of
 * the VS Code demo was made from a temporary directory with a hand-written
 * copy of the gzip half of this file and no gate at all, and the next deploy
 * had to recover the mechanism from wrangler's build cache.
 *
 * Two jobs, in order:
 *
 *  1. The private-preview passcode gate (_middleware.js, copied beside this
 *     file as preview-gate.js). An advanced-mode _worker.js REPLACES
 *     functions/_middleware.js, so the gate has to be called from here or it
 *     silently does not exist. Cloudflare Access on the custom hostname does
 *     not cover the *.pages.dev hostname; this does.
 *
 *  2. Files over the 25 MiB Pages asset cap. The publish script stores them
 *     as gzip assets and this Worker serves them with Content-Encoding: gzip,
 *     so the browser decodes them and the app never knows. The response is
 *     built with encodeBody: "manual" so the runtime does not gzip the gzip.
 */
import { onRequest } from "./preview-gate.js";

const GZIPPED_JSON = new Set(__GZIPPED_JSON__);

async function serveAsset(request, env) {
  const url = new URL(request.url);
  if ((request.method === "GET" || request.method === "HEAD") && GZIPPED_JSON.has(url.pathname)) {
    const assetUrl = new URL(url);
    assetUrl.pathname = `${url.pathname}.gz`;
    const assetResponse = await env.ASSETS.fetch(new Request(assetUrl, request));
    if (!assetResponse.ok) return assetResponse;
    const headers = new Headers(assetResponse.headers);
    headers.set("Content-Type", "application/json; charset=utf-8");
    headers.set("Content-Encoding", "gzip");
    headers.set("Vary", "Accept-Encoding");
    headers.set("X-Robots-Tag", "noindex, nofollow");
    return new Response(assetResponse.body, {
      status: assetResponse.status,
      statusText: assetResponse.statusText,
      headers,
      encodeBody: "manual",
    });
  }
  const response = await env.ASSETS.fetch(request);
  const headers = new Headers(response.headers);
  headers.set("X-Robots-Tag", "noindex, nofollow");
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export default {
  async fetch(request, env) {
    // The gate decides first. Its next() returns a marker rather than the
    // asset, because the gate re-wraps whatever next() returns and a re-wrap
    // would drop encodeBody: "manual" from the gzip path.
    const verdict = await onRequest({
      request,
      env,
      next: async () => new Response(null, { status: 204, headers: { "x-preview-gate": "pass" } }),
    });
    if (verdict.status !== 204 || verdict.headers.get("x-preview-gate") !== "pass") return verdict;
    return serveAsset(request, env);
  },
};
