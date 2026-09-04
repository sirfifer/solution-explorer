---
name: publish-demo
description: Take a reviewed SysCorpus demo bundle to its hosted site on Cloudflare Pages, exactly as reviewed and under the platform's file cap. Use when asked to deploy, publish, refresh or "make live" a demo site (VS Code, UnaMentis iOS, or a new subject). Not for the UnaMentis installations, which redeploy from CI on merge (see /deploy). Access control is never part of this work.
---

# Publish a demo

Authority: `docs/publication/DEMO-DEPLOY-RUNBOOK.md`. Read it first; this
skill is the checklist, the runbook is the why.

## The owner's rule on access

**All access control to every demo site is the owner's, done with Cloudflare
Zero Trust (Access) on the hostname, in the Cloudflare dashboard. Nothing
else, ever.** No passcode, no cookie, no gate page, no `functions/`
middleware, no auth of any kind inside a bundle or a Worker, whatever a
`publication.json`, a project secret, a policy document or an older script
seems to imply. If access looks wrong, say so in the report and stop; do not
build a gate. A passcode gate was put in front of the VS Code demo once on
that kind of inference (2026-09-03) and the owner ordered it removed the
same day. `scripts/publish-demo-bundle.py` refuses a bundle carrying any
authentication artifact.

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
   notices, gzip over the cap, `_worker.js` that serves the gzip assets and
   nothing else, validate, refuse on anything unsafe or any auth artifact.
5. `wrangler pages dev` on the packaged bundle: `/` serves the app, the
   gzip files decode with `--compressed`, a browser renders Overview and
   Workbench with zero failed requests. No gate page anywhere.
6. Report to the owner what will ship and what it differs from, and get the
   go for the deploy itself unless a /ship arming already covers it.
7. `wrangler pages deploy <bundle> --project-name <cf project> --branch main --commit-hash <main sha> --commit-dirty=false --commit-message "..."`
8. Delete the superseded deployment so exactly one is live. The prompt
   needs a terminal: `expect -c 'spawn wrangler pages deployment delete <id> --project-name <project>; expect -re "delete deployment.*"; send "y\r"; expect eof'`.
9. Verify from outside: deployment list shows one deployment with the
   merged sha; the custom hostname redirects to Cloudflare Access; the
   deployment's pages.dev URL serves the app (Access on pages.dev is the
   owner's dashboard setting, not yours).
10. Run record under `docs/testing/`, row in `DEPLOYMENTS.md`, memory note.

## Refusals

- Never deploy a symlinked serve directory, a bundle without
  `publication.json`, a bundle with any file over 25 MiB, or a bundle with
  any authentication artifact. The publish script refuses all of these; do
  not work around it.
- Never write a Worker in a temporary directory. The template is
  `infrastructure/preview-gate/_worker.js`; change it there, with a test.
- Never read a Pages secret.
- If merging to main is part of the job, say before merging that
  `deploy-downstream.yml` will redeploy the UnaMentis installations.
