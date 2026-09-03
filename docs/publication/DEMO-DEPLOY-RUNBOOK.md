# Demo deploy runbook

How a SysCorpus demo bundle gets from a reviewed local page to its hosted
site, and every trap on that path. Written 2026-09-03 after the VS Code
identity front door deploy, which hit each trap below in turn because the
first deploy of that demo had been made from a temporary directory with a
hand-written Worker that nobody committed.

The rule this runbook enforces: **what was reviewed is what gets deployed,
and every step is a committed script or a recorded command.** No temporary
directories, no hand-written Workers, no archaeology through wrangler's
build cache to learn how the last deploy was done.

## 0. Access control is the owner's, and only Cloudflare's

All access control to every demo site is done by the owner with Cloudflare
Zero Trust (Access) on the hostname, in the Cloudflare dashboard. Nothing
else. A bundle never carries a passcode, a cookie check, a gate page, a
`functions/` directory, a `_middleware.js`, or any authentication logic in
its Worker, whatever `publication.json`, a Pages project secret, a policy
document or an older script appears to require. On 2026-09-03 a passcode
gate was composed into the VS Code demo's Worker on exactly that kind of
inference; the owner found a passcode prompt in front of his own site and
ordered it removed the same day. `scripts/publish-demo-bundle.py` refuses a
bundle that carries any such artifact. If access looks wrong or exposed,
report it; the fix is the owner's, in the dashboard.

## 1. The shape of a deploy

| Layer | What it is | Where it comes from |
|---|---|---|
| Code | the viewer build and the analyzer that produced the data | a commit on `main`, after the PR is green and merged |
| Data | the projection: `manifest.json`, `orientation.json`, the detail shards, sidecars | a reprojection or the canonical store, plus review corrections |
| Publication | `publication.json`, upstream license and notices, activity scrub, machine path removed | `demos/publication/<slug>.json`, the subject checkout, `assemble-serve.py` flags |
| Hosting | Cloudflare Pages project, gzip for oversized files | `scripts/publish-demo-bundle.py` and `infrastructure/preview-gate/_worker.js` |
| Access | who may open the site | the owner, Cloudflare Access, dashboard only |

A viewer-only redeploy is never enough when the change touched the
analyzer. The identity front door added a derive pass whose output lives in
`manifest.json` and `orientation.json`; the live data predated it, so the
live page would have kept the old headline no matter how new the viewer
was. Ask every time: does this change alter what the projection contains?
If yes, the data ships with the code.

## 2. The procedure

Run everything from a fresh worktree detached at the merged `main` commit.
Never from a worktree another session is using, and never from the one that
serves the page the owner has open.

```bash
git worktree add --detach /Volumes/Studio/dev/.worktrees/solution-explorer--deploy-<slug> origin/main
cd /Volumes/Studio/dev/.worktrees/solution-explorer--deploy-<slug>
(cd viewer && npm ci)
PY=<a venv python with tree-sitter installed; never the Homebrew python3>
```

### 2.1 Assemble

```bash
$PY scripts/assemble-serve.py <slug> \
  --projection <projection dir> \
  --corrections demos/review-corrections/<slug>.json \
  --publication demos/publication/<slug>.json \
  --upstream-source <subject checkout> \
  --scrub-activity
```

The build runs in `<slug>-demo` mode when `viewer/.env.<slug>-demo` exists
(that is what keeps the VS Code demo on Atlas). Note that this mode build
skips `tsc -b`; run `npx tsc --noEmit` in `viewer/` yourself before you
trust the bundle.

### 2.2 Test the assembled bundle, as assembled

```bash
python3 -m http.server 5189 --bind 127.0.0.1 --directory .testboard/serve/<slug> &
cd viewer && CRAWL_BASE_URL=http://127.0.0.1:5189 CRAWL_PROFILE=quick \
  CRAWL_DATA_DIR=$PWD/../.testboard/serve/<slug>/architecture \
  npx playwright test -c tests/crawl/playwright.config.ts
```

Both viewports must be green on this bundle, not on an earlier one without
the publication metadata. The publication banner costs 45px on a phone and
that was enough to put a top-level node under the zoom controls once. Run
the other canonical subject on the same viewer build as the regression
check.

### 2.3 Package for Pages

```bash
$PY scripts/publish-demo-bundle.py <slug> --serve-dir .testboard/serve/<slug> --out .testboard/publish/<slug>
```

This resolves symlinks, removes `manifest.root_path`, hoists the license and
notices to the root, gzips every file over 25 MiB, writes a `_worker.js`
that serves those gzip assets and nothing else, validates
`publication.json`, and refuses on any symlink, oversized file, missing
license, machine path, or authentication artifact. It prints the deploy
command and does not run it.

### 2.4 Prove the Worker locally

```bash
wrangler pages dev .testboard/publish/<slug> --port 8795 --ip 127.0.0.1 --compatibility-date=2026-07-01
```

Then, with curl: `GET /` returns the app; `--compressed` fetches of the
gzip-served files decode to the full JSON; a small shard returns plain
JSON. Then, in a browser (a Playwright script is fine): open the Overview,
open the Workbench, drill once, and confirm zero failed requests and zero
page errors. The compatibility date must be one the installed `workerd`
supports; the warning tells you when it is not.

### 2.5 Deploy, deliberately

```bash
wrangler pages deploy .testboard/publish/<slug> --project-name <cf project> \
  --branch main --commit-hash <merged main sha> --commit-dirty=false \
  --commit-message "<what and why>"
```

### 2.6 Delete the superseded deployment

Every deployment keeps answering at its own `<id>.<project>.pages.dev`
address until deleted. The owner's rule is one deployment live. The prompt
needs a terminal, so answer it through `expect`:

```bash
expect -c 'spawn wrangler pages deployment delete <old id> --project-name <cf project>; expect -re "delete deployment.*"; send "y\r"; expect eof'
```

### 2.7 Verify from outside

- `wrangler pages deployment list --project-name <cf project>`: exactly one
  row, Production, branch main, source equal to the merged sha.
- The custom hostname redirects to Cloudflare Access.
- The deployment's pages.dev URL serves the app. Whether that hostname is
  also behind Access is the owner's Pages Access policy setting in the
  dashboard; report its state, never change it and never gate it yourself.
- Record the deployment id, the sha, the numbers and the screenshots in a
  run record under `docs/testing/`, and add or update the row in
  `DEPLOYMENTS.md`.

## 3. The traps, each one paid for

**25 MiB per file.** Cloudflare Pages refuses any single asset over 25 MiB:
wrangler refuses client-side, and the upload API answers 500 if that check
is bypassed. A large subject's `manifest.json` (34.7 MiB for VS Code) and
its largest detail shard (47.6 MiB) both exceed it, and compact JSON is not
enough (the shard is 41.8 MiB compact). The mechanism is gzip assets plus a
Worker that serves them with `Content-Encoding: gzip`; the files compress to
2.7 MiB and 4.3 MiB. The publish script does this for every oversized file.

**An advanced-mode Worker replaces `functions/`.** A `_worker.js` at the
bundle root means Pages ignores `functions/` entirely. That is fine, because
nothing in `functions/` is wanted: access control is not in the bundle.

**Access control is not yours to add.** See section 0. The one time it was
added on inference it was wrong, and it cost the owner a passcode prompt on
his own site.

**Old deployments keep answering.** Until deleted, every deployment serves
its content at its own preview URL. Delete the superseded one after every
deploy (2.6).

**A symlinked bundle is not what you tested.** `assemble-serve.py` symlinks
the projection for speed. Wrangler follows symlinks, but the deployable
bundle is a dereferenced copy so the file set on disk is exactly the file
set uploaded, and so the safety check can see the real sizes.

**`manifest.root_path` is a leak.** It names the analyzing machine's working
copy. Blanked with a note by the publish script, as `demo-site.py` does.

**The reviewed bundle is not the publication bundle.** The crawl bundle has
no `publication.json`, no license, no scrub. Package it with the script and
test that, or you are testing something other than what ships.

**Merging to main deploys the installations.** `deploy-downstream.yml` runs
after the Architecture Visualization workflow succeeds on main and
redeploys every UnaMentis installation in `DEPLOYMENTS.md`. Say so before
merging; it is not the demo deploy, but it is outward-facing.

**The workerd compatibility date.** `wrangler pages dev` defaults to today's
date, which a slightly older `workerd` binary refuses. Pass a date the
binary supports.

**wrangler prompts need a terminal.** `deployment delete` asks for
confirmation and answers "no" for itself when stdin is not a terminal.
`expect` is the reliable way to answer it.

## 4. Open items after 2026-09-03

- `scripts/demo-site.py deploy` still expects `functions/_middleware.js` and
  does not gzip. It should call `publish-demo-bundle.py` or be retired in
  favour of it.
- `infrastructure/preview-gate/_middleware.js` and the passcode wording in
  `DISCLOSURE-POLICY.md` describe a gate the owner does not use. Whether to
  retire them is the owner's call; nothing in the publish path uses them.
- `assemble-serve.py` skips `tsc -b` in demo mode (review finding); until
  fixed, run `npx tsc --noEmit` before trusting a demo-mode build.
