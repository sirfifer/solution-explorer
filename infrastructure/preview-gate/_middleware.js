/**
 * Private-preview gate for a Solution Explorer demo (DISCLOSURE-POLICY.md step 3).
 *
 * The policy is explicit that a preview must be gated SERVER SIDE, and that
 * "client-side-only gating is theater and is not acceptable". This is a
 * Cloudflare Pages Function middleware, so it runs before any asset is served:
 * an ungated request never receives the architecture data, not even as a
 * background fetch the page chooses not to render.
 *
 * Deploy: copy this file to `functions/_middleware.js` in the bundle root and
 * set PREVIEW_PASSCODE as a Pages secret on the project.
 *
 * Cloudflare Access (email allowlist or one-time PIN) is the other acceptable
 * gate and is stronger, because it authenticates a person rather than a shared
 * secret. Prefer it where the audience is known. This exists for the case the
 * policy actually describes, handing a maintainer a preview link and a passcode.
 *
 * Design decisions worth knowing:
 *
 *  - FAIL CLOSED. With no PREVIEW_PASSCODE configured, everything is denied.
 *    A gate that silently opens when misconfigured is worse than no gate,
 *    because it is believed.
 *  - The session cookie is an HMAC over an expiry, keyed by the passcode, so it
 *    cannot be forged and it dies on its own. Changing the passcode invalidates
 *    every outstanding session, which is what revocation should mean.
 *  - Passcode comparison is constant time.
 *  - The gate page states plainly what this is and that it is unofficial, so a
 *    maintainer who follows a link understands it before entering anything.
 */

const COOKIE_NAME = "se_preview";
const SESSION_HOURS = 12;
const encoder = new TextEncoder();

function timingSafeEqual(a, b) {
  const ab = encoder.encode(a);
  const bb = encoder.encode(b);
  // Compare lengths without branching out early; a length mismatch still walks
  // the longer buffer so the timing does not leak the passcode length.
  let diff = ab.length ^ bb.length;
  const len = Math.max(ab.length, bb.length);
  for (let i = 0; i < len; i++) {
    diff |= (ab[i] ?? 0) ^ (bb[i] ?? 0);
  }
  return diff === 0;
}

async function hmac(key, message) {
  const cryptoKey = await crypto.subtle.importKey(
    "raw", encoder.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", cryptoKey, encoder.encode(message));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function mintToken(passcode, expiresAt) {
  return `${expiresAt}.${await hmac(passcode, String(expiresAt))}`;
}

async function tokenIsValid(token, passcode, now) {
  if (typeof token !== "string" || !token.includes(".")) return false;
  const [expiresAt, signature] = token.split(".", 2);
  const expiry = Number(expiresAt);
  if (!Number.isFinite(expiry) || expiry <= now) return false;
  return timingSafeEqual(signature, await hmac(passcode, expiresAt));
}

function readCookie(request, name) {
  const header = request.headers.get("Cookie") || "";
  for (const part of header.split(";")) {
    const [k, ...rest] = part.trim().split("=");
    if (k === name) return rest.join("=");
  }
  return null;
}

function gatePage(subject, message) {
  const safe = (s) => String(s || "").replace(/[<>&"]/g, (c) => (
    { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;" }[c]
  ));
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Private preview</title>
<style>
  :root { color-scheme: light dark; }
  body { margin:0; min-height:100vh; display:grid; place-items:center;
         font: 16px/1.6 ui-sans-serif, system-ui, sans-serif;
         background:#0f1413; color:#e6edea; padding:24px; }
  main { max-width: 34rem; }
  h1 { font-size:1.4rem; margin:0 0 .75rem; }
  p { color:#93a29e; margin:0 0 1rem; }
  form { display:flex; gap:.5rem; flex-wrap:wrap; margin-top:1.5rem; }
  input { flex:1 1 14rem; padding:.7rem .8rem; border-radius:6px;
          border:1px solid #3a4643; background:#161d1b; color:inherit; font:inherit; }
  button { padding:.7rem 1.2rem; border-radius:6px; border:0; cursor:pointer;
           background:#5fcfb8; color:#08211c; font:inherit; font-weight:600; }
  .err { color:#f0906c; }
</style></head><body><main>
<h1>Private preview</h1>
<p>This is an unofficial architecture map of <strong>${safe(subject)}</strong>, generated
from public source. It is a private preview shared for review and is not published.
It is not affiliated with or endorsed by the project.</p>
${message ? `<p class="err">${safe(message)}</p>` : ""}
<form method="POST">
  <input type="password" name="passcode" placeholder="Passcode" autofocus
         autocomplete="current-password" aria-label="Passcode">
  <button type="submit">View preview</button>
</form>
</main></body></html>`;
}

export async function onRequest(context) {
  const { request, env, next } = context;
  const passcode = env.PREVIEW_PASSCODE;
  const subject = env.PREVIEW_SUBJECT || "this project";

  // Fail closed: an unconfigured gate denies rather than opens.
  if (!passcode) {
    return new Response(
      "This preview is not configured. Set the PREVIEW_PASSCODE secret on the Pages project.",
      { status: 503, headers: { "content-type": "text/plain; charset=utf-8" } },
    );
  }

  const now = Date.now();
  if (await tokenIsValid(readCookie(request, COOKIE_NAME), passcode, now)) {
    const response = await next();
    // A preview must never be indexed, whatever the asset.
    const headers = new Headers(response.headers);
    headers.set("X-Robots-Tag", "noindex, nofollow");
    return new Response(response.body, { status: response.status, headers });
  }

  if (request.method === "POST") {
    const form = await request.formData().catch(() => null);
    const submitted = form ? String(form.get("passcode") || "") : "";
    if (timingSafeEqual(submitted, passcode)) {
      const expiresAt = now + SESSION_HOURS * 3600 * 1000;
      const token = await mintToken(passcode, expiresAt);
      return new Response(null, {
        status: 303,
        headers: {
          Location: new URL(request.url).pathname,
          "Set-Cookie": `${COOKIE_NAME}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${SESSION_HOURS * 3600}`,
          "X-Robots-Tag": "noindex, nofollow",
        },
      });
    }
    return new Response(gatePage(subject, "That passcode did not match."), {
      status: 401,
      headers: { "content-type": "text/html; charset=utf-8", "X-Robots-Tag": "noindex, nofollow" },
    });
  }

  return new Response(gatePage(subject, ""), {
    status: 401,
    headers: { "content-type": "text/html; charset=utf-8", "X-Robots-Tag": "noindex, nofollow" },
  });
}

// Exported for the test suite; the middleware entry point is onRequest.
export const __test = { timingSafeEqual, hmac, mintToken, tokenIsValid, readCookie, gatePage };
