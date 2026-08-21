# Secrets and credentials: how privileged work gets done here

Written 2026-08-20 after a session lost time to a solved problem. The rule this
records: **a credential should be used, never read**, and an agent that cannot
find the established path should look for it rather than ask for a weaker one.

## The three paths, in preference order

### 1. A CLI that is already authenticated

`wrangler`, `gh`, `ssh`. The credential is held by the tool, the agent never
sees it, and there is nothing to leak. This covers most work.

Verified capabilities of the local `wrangler` OAuth session: `pages (write)`,
`workers (write)`, `d1 (write)`, `zone (read)`, `ssl_certs (write)`, and more.
That is enough to create Pages projects, upload secrets, and deploy.

**Its limit, and the one that started this:** `wrangler pages` has **no
custom-domain command** at any version through 4.125.0. Attaching a hostname to
a Pages project requires the REST API, which requires a token.

### 2. The macOS login Keychain, via `scripts/cf-api.sh`

For REST work a CLI does not cover. The token lives in the login Keychain,
encrypted at rest and ACL'd, the same store the OS uses for its own credentials.

```bash
scripts/cf-api.sh --store          # one-time bootstrap, input hidden
scripts/cf-api.sh --check          # confirm the stored token still works
scripts/cf-api.sh GET  /accounts/${CF_ACCOUNT_ID}/pages/projects
scripts/cf-api.sh POST /accounts/${CF_ACCOUNT_ID}/pages/projects/foo/domains '{"name":"a.b.c"}'
```

The script fetches the token inside its own process and hands it straight to
`curl`. It is never echoed, never written to a file, never returned to a caller,
and `set +x` is forced so a caller running under `bash -x` cannot leak it.
**The token never enters an agent's context.**

### 3. GitHub Actions, where repository secrets already live

> **Status 2026-08-20: `solution-explorer`'s `CLOUDFLARE_API_TOKEN` is DEAD.**
> `/user/tokens/verify` returns **HTTP 401** with it, and so does a plain Pages
> project list (run `32447591303`). 401 means invalid, expired or revoked; a
> valid token lacking a scope returns **403**. The secret dates from
> 2026-01-31. `wrangler` OAuth on the Studio still works against the same
> account, which isolates the failure to this token rather than the account or
> the project. **Every CI job needing the Cloudflare API is broken until it is
> replaced.** Fix: `~/Desktop/store-cloudflare-token.command`, which installs a
> fresh token into both the Keychain and the repo secret from one paste.
> `expat-intel`'s token is from 2026-01-20 and is worth checking for the same
> failure.

For anything that must run in CI, must be auditable, or where no local
credential exists. `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` have been
repository secrets since 2026-01-31. `expat-intel`'s `deploy-worker.yml`
established the idiom; `.github/workflows/demo-domain.yml` follows it.

Actions secrets **cannot be read back out**, by design. So this path executes
work, it does not supply credentials to anything else.

**Constraint worth knowing before designing around it:** `workflow_dispatch`
only fires for workflows present on the **default branch**. `gh workflow run`
against a feature branch returns `HTTP 404: workflow not found on the default
branch`. A new operation therefore costs a merge before it can be run once,
which is exactly why path 2 exists.

## What NOT to do, and why

- **Do not ask for `export CLOUDFLARE_API_TOKEN=...`.** It moves a long-lived
  credential into plaintext, into shell history, into every child process, and
  into any process listing. It is a real downgrade in posture bought for
  convenience, and it will be refused.
- **Do not read a credential into context to use it.** The secret then exists in
  a transcript forever. Wrap it in a helper that uses it instead.
- **Do not go hunting through dotfiles, config files or keychains for a token.**
  The harness classifier blocks this and is right to: the access pattern is
  indistinguishable from credential exfiltration. If a credential seems missing,
  read this file and check the three paths above.

## When you are blocked

Blocked once is information. Blocked twice on two different approaches is a
**policy boundary**, not a fluke. Stop, and either use an established path or
build one that keeps the secret in a secure store. Do not escalate to the user
for a weaker mechanism.

## Bootstrapping path 2 on a new machine

Typing is expensive for the owner (`~/.claude/skills/ecosystem` rule 3), so the
bootstrap is a click-to-run written directly to the target Mac's Desktop over
SSH, never AirDropped (AirDrop tags it and Gatekeeper refuses it):

```
~/Desktop/store-cloudflare-token.command
```

Double-click, paste once, done. Input is hidden, nothing is written to disk, and
the script verifies the token against `/user/tokens/verify` before reporting
success rather than assuming the write worked.

## Extending this

Other services should follow the same shape rather than inventing a new one:
a keychain service name, a helper that uses the secret without printing it, and
a one-time click-to-run bootstrap. Keep the keychain service name in the helper,
and record the service here.

| Service | Keychain service | Helper |
|---|---|---|
| Cloudflare | `solution-explorer-cloudflare` / `api-token` | `scripts/cf-api.sh` |
