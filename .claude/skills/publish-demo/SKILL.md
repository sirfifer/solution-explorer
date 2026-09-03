---
name: publish-demo
description: Take a reviewed SysCorpus demo bundle to its hosted private preview on Cloudflare Pages, exactly as reviewed, gated, and under the platform's file cap. Use when asked to deploy, publish, refresh or "make live" a demo site (VS Code, UnaMentis iOS, or a new subject). Not for the UnaMentis installations, which redeploy from CI on merge (see /deploy).
---

# Publish a demo

Authority: `docs/publication/DEMO-DEPLOY-RUNBOOK.md`. Read it first; this
skill is the checklist, the runbook is the why.

## Before anything outward

1. **Name what changes.** Code only, or code and data? A change to the
   analyzer or the orientation builder changes the projection, and the live
   data must be regenerated or the page will not show the change. Say which
   in one sentence before starting.
2. **Confirm the reviewed page.** Open the exact locally served bundle the
   owner reviewed and confirm the port and URL with them. Everything below
   must produce the same page plus publication metadata, nothing else.
3. **Fresh deploy worktree** detached at the merged `main` commit, its own
   `npm ci`, a venv python for the scripts. Never the worktree serving the
   reviewed page, never one another session is using.

## The steps, in order, none skipped

1. `scripts/assemble-serve.py <slug> --projection ... --corrections ... --publication ... --upstream-source ... --scrub-activity`
2. `npx tsc --noEmit` in `viewer/` (demo-mode builds skip it).
3. Quick crawl of the assembled bundle, desktop and mobile, on this subject
   and on the other canonical subject with the same viewer build.
4. `scripts/publish-demo-bundle.py <slug>`: dereference, scrub, hoist
   notices, gzip over the cap, `_worker.js` with the gate, validate, refuse
   on anything unsafe.
5. `wrangler pages dev` on the packaged bundle with probe bindings: 401
   ungated, 303 on the passcode, gzip files decode with the cookie, a
   browser passes the gate and renders Overview and Workbench with zero
   failed requests.
6. Report to the owner what will ship and what it differs from, and get the
   go for the deploy itself unless a /ship arming already covers it.
7. `wrangler pages deploy <bundle> --project-name <cf project> --branch main --commit-hash <main sha> --commit-dirty=false --commit-message "..."`
8. Verify from outside: deployment list, 401 gate on the new preview URL
   and the production alias, custom hostname still behind Access.
9. Run record under `docs/testing/`, row in `DEPLOYMENTS.md`, memory note.

## Refusals

- Never deploy a symlinked serve directory, a bundle without
  `publication.json`, a bundle whose `_worker.js` does not import the gate,
  or a bundle with any file over 25 MiB. The publish script refuses all of
  these; do not work around it.
- Never write a Worker in a temporary directory. The template is
  `infrastructure/preview-gate/_worker.js`; change it there, with a test.
- Never read a Pages secret. `wrangler pages secret list` shows names only;
  that is all you need to know the gate will open.
- If merging to main is part of the job, say before merging that
  `deploy-downstream.yml` will redeploy the UnaMentis installations.
