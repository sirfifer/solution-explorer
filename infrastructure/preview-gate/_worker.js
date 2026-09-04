/**
 * Pages advanced-mode Worker for a published SysCorpus demo bundle.
 *
 * ONE job: serve the files that exceed the 25 MiB Pages asset cap. The
 * publish script (scripts/publish-demo-bundle.py) stores each of them as a
 * gzip asset under `<name>.gz` and replaces the GZIPPED_JSON placeholder
 * below with their paths. This Worker answers the original path with the
 * gzip body and Content-Encoding: gzip, so the browser decodes it and the
 * viewer never knows. encodeBody: "manual" keeps the runtime from gzipping
 * the gzip.
 *
 * This Worker does NOT do access control, and must never grow any. Access
 * to every demo site is the owner's, through Cloudflare Zero Trust (Access)
 * on the hostname, configured in the Cloudflare dashboard. Nothing in a
 * bundle authenticates anyone: no passcode, no cookie, no gate page. A
 * passcode gate was composed in here once (2026-09-03) on an inference from
 * the project's secrets, and the owner removed it the same day. The publish
 * script refuses a bundle that carries any such code.
 */
const GZIPPED_JSON = new Set(__GZIPPED_JSON__);

export default {
  async fetch(request, env) {
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
      return new Response(assetResponse.body, {
        status: assetResponse.status,
        statusText: assetResponse.statusText,
        headers,
        encodeBody: "manual",
      });
    }
    return env.ASSETS.fetch(request);
  },
};
