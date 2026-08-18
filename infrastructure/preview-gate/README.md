# Private-preview gate

Server-side gating for an unpublished Solution Explorer demo, as
`docs/publication/DISCLOSURE-POLICY.md` step 3 requires:

> Deploy gated, never public. Acceptable gates: Cloudflare Access (email
> allowlist or one-time PIN) or a shared passcode enforced server-side (Pages
> Function middleware). Client-side-only gating is theater and is not acceptable.

`_middleware.js` is that Pages Function. It runs before any asset is served, so
an ungated request never receives the architecture data, not even as a fetch the
page chooses not to render.

## Which gate to use

**Cloudflare Access** is stronger and is the right default when the audience is
known, because it authenticates a person rather than a shared secret, and access
is revoked per person without disturbing anyone else. It is account
configuration, not code, and lives in the Cloudflare dashboard on the Pages
project.

**This middleware** covers the case the policy actually describes: handing a
maintainer a preview link and a passcode in an outreach email, where requiring
them to have a Cloudflare identity would be a rude ask.

## Deploying it

1. Copy `_middleware.js` to `functions/_middleware.js` in the deployed bundle
   root (beside `index.html`).
2. Set the Pages project secrets:
   - `PREVIEW_PASSCODE`, required. Without it the gate denies everything.
   - `PREVIEW_SUBJECT`, optional, the project name shown on the gate page.
3. Set `access.visibility` to `private-preview` in `publication.json`, and
   describe the gate in `access.gate`. Never put the passcode in that file.

Rotating the passcode revokes every outstanding session, because sessions are
signed with it. That is the whole revocation story for a shared secret, and it
is deliberate.

## What it guarantees, and what it does not

Guaranteed, and covered by `preview-gate.test.mjs`:

- An unauthenticated request never reaches the assets. The test asserts the
  asset handler is not called, not merely that the response looks like a login.
- A misconfigured gate denies rather than opens. A gate that silently opens when
  misconfigured is worse than no gate, because it is believed.
- Sessions are HMAC-signed over their expiry, keyed by the passcode, so a client
  cannot forge one or extend its own expiry.
- Passcode comparison is constant time and does not leak length by early exit.
- Every response carries `X-Robots-Tag: noindex, nofollow`.
- The gate page states the unofficial, not-affiliated framing before anyone
  enters anything, so a maintainer following a link understands what they are
  looking at (`DISCLOSURE-POLICY.md` principle 1, respect first).

Not guaranteed:

- A shared passcode is shareable. Anyone given it can pass it on. Use Cloudflare
  Access where that matters.
- This protects the deployment, not the Cloudflare deploy-preview URLs the
  platform generates. Confirm those are not publicly reachable for a private
  preview project, or use Access, which covers them.

## Running the tests

```
node --test infrastructure/preview-gate/*.test.mjs
```

No dependencies; it uses Node's own test runner against the real `onRequest`
handler. CI runs it as the `Preview Gate Tests` job, and the CI gate depends on
it.
