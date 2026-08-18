/**
 * Tests for the private-preview gate.
 *
 * DISCLOSURE-POLICY.md rules out client-side gating as theater, so the
 * properties tested here are the ones that make this gate real: an ungated
 * request never reaches the assets, a forged or expired session is refused,
 * changing the passcode revokes outstanding sessions, and a misconfigured gate
 * denies rather than opens.
 *
 * Run: node --test infrastructure/preview-gate/
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { onRequest, __test as t } from "./_middleware.js";

const PASS = "correct-horse";

function req(url = "https://demo.example/", init = {}) {
  return new Request(url, init);
}

/** A `next()` that records whether the protected assets were ever reached. */
function assetSpy() {
  const state = { served: 0 };
  return [
    async () => {
      state.served += 1;
      return new Response("SECRET ARCHITECTURE DATA", {
        headers: { "content-type": "application/json" },
      });
    },
    state,
  ];
}

test("an unauthenticated request never reaches the assets", async () => {
  const [next, state] = assetSpy();
  const res = await onRequest({ request: req(), env: { PREVIEW_PASSCODE: PASS }, next });
  assert.equal(res.status, 401);
  assert.equal(state.served, 0, "the gate must run BEFORE any asset is served");
  const body = await res.text();
  assert.ok(!body.includes("SECRET ARCHITECTURE DATA"));
  assert.match(body, /Private preview/);
});

test("a misconfigured gate denies rather than opens", async () => {
  const [next, state] = assetSpy();
  const res = await onRequest({ request: req(), env: {}, next });
  assert.equal(res.status, 503);
  assert.equal(state.served, 0, "no passcode configured must fail closed");
});

test("the correct passcode mints a session and redirects", async () => {
  const [next] = assetSpy();
  const res = await onRequest({
    request: req("https://demo.example/", {
      method: "POST",
      body: new URLSearchParams({ passcode: PASS }),
    }),
    env: { PREVIEW_PASSCODE: PASS },
    next,
  });
  assert.equal(res.status, 303);
  const cookie = res.headers.get("Set-Cookie");
  assert.match(cookie, /HttpOnly/);
  assert.match(cookie, /Secure/);
  assert.match(cookie, /SameSite=Lax/);
});

test("a wrong passcode is refused and serves no assets", async () => {
  const [next, state] = assetSpy();
  const res = await onRequest({
    request: req("https://demo.example/", {
      method: "POST",
      body: new URLSearchParams({ passcode: "nope" }),
    }),
    env: { PREVIEW_PASSCODE: PASS },
    next,
  });
  assert.equal(res.status, 401);
  assert.equal(state.served, 0);
  assert.match(await res.text(), /did not match/);
});

test("a valid session reaches the assets and is marked noindex", async () => {
  const [next, state] = assetSpy();
  const token = await t.mintToken(PASS, Date.now() + 60_000);
  const res = await onRequest({
    request: req("https://demo.example/architecture/manifest.json", {
      headers: { Cookie: `se_preview=${token}` },
    }),
    env: { PREVIEW_PASSCODE: PASS },
    next,
  });
  assert.equal(res.status, 200);
  assert.equal(state.served, 1);
  assert.equal(res.headers.get("X-Robots-Tag"), "noindex, nofollow");
  assert.equal(await res.text(), "SECRET ARCHITECTURE DATA");
});

test("an expired session is refused", async () => {
  const [next, state] = assetSpy();
  const token = await t.mintToken(PASS, Date.now() - 1);
  const res = await onRequest({
    request: req("https://demo.example/", { headers: { Cookie: `se_preview=${token}` } }),
    env: { PREVIEW_PASSCODE: PASS },
    next,
  });
  assert.equal(res.status, 401);
  assert.equal(state.served, 0);
});

test("a forged session is refused", async () => {
  const [next, state] = assetSpy();
  const forged = `${Date.now() + 60_000}.${"a".repeat(64)}`;
  const res = await onRequest({
    request: req("https://demo.example/", { headers: { Cookie: `se_preview=${forged}` } }),
    env: { PREVIEW_PASSCODE: PASS },
    next,
  });
  assert.equal(res.status, 401);
  assert.equal(state.served, 0);
});

test("changing the passcode revokes every outstanding session", async () => {
  // This is what revocation has to mean for a shared secret: hand out a new
  // passcode and the old links stop working, with nothing else to clean up.
  const token = await t.mintToken(PASS, Date.now() + 60_000);
  assert.equal(await t.tokenIsValid(token, PASS, Date.now()), true);
  assert.equal(await t.tokenIsValid(token, "rotated-passcode", Date.now()), false);
});

test("the token is not merely an expiry a client can rewrite", async () => {
  const token = await t.mintToken(PASS, Date.now() + 60_000);
  const [, signature] = token.split(".");
  const extended = `${Date.now() + 999_000_000}.${signature}`;
  assert.equal(await t.tokenIsValid(extended, PASS, Date.now()), false);
});

test("passcode comparison does not leak length by early exit", () => {
  assert.equal(t.timingSafeEqual("abc", "abc"), true);
  assert.equal(t.timingSafeEqual("abc", "abd"), false);
  assert.equal(t.timingSafeEqual("abc", "abcdef"), false);
  assert.equal(t.timingSafeEqual("", ""), true);
});

test("the gate page escapes the subject name", async () => {
  const html = t.gatePage('<script>alert(1)</script>', "");
  assert.ok(!html.includes("<script>alert"));
  assert.match(html, /&lt;script&gt;/);
});

test("the gate page tells a maintainer what they are looking at", async () => {
  // A maintainer following a preview link should understand the framing before
  // entering anything (DISCLOSURE-POLICY.md principle 1, respect first).
  const html = t.gatePage("Example", "");
  assert.match(html, /unofficial/i);
  assert.match(html, /not affiliated/i);
  assert.match(html, /noindex/);
});
