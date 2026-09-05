# Run record: shipping the UI captures and structured explanations

Date: 2026-09-04. Owner directive: check PR #129's gate, merge it, and deploy.
What the session found instead was that #129 could not ship as merged, and the
deploy waited on a fix.

## What was already true when the session started

PR #129 was merged as `813e006` with every check green, and the VS Code demo
was still serving the PR #127 build from the night before. The merge had
fired `deploy-downstream.yml`, which redeploys the UnaMentis installations,
but nothing had deployed the VS Code demo: that is a manual runbook path, not
a workflow.

## The data #129 needs, and the silent failure that nearly shipped

#129 is not a viewer-only change. Two inputs carry its data, and both are
optional sidecars the viewer degrades past without an error:

| Input | Feeds | Where it was |
|---|---|---|
| `--ui-surfaces demos/ui-surfaces/vscode` | the workbench capture and its six source-linked hotspots | committed in the repo |
| `--enrichment-store <store>` | the structured component explanations | 6024 audited `contract-state` rows already in the canonical store |

No AI content was regenerated. The store copy's enrichment row counts are
identical to the canonical store's, kind for kind.

The runbook and the `publish-demo` skill both predated #129 and named neither
flag. Following them literally would have deployed #129's viewer over data
that had nothing for it to render: a bundle that assembles, passes every
check, deploys cleanly and shows none of the work. Both documents now carry
the flags and say why. That correction is in PR #130.

Assembly reproduced the bundle the #129 session had reviewed byte for byte:
`manifest.json`, `orientation.json`, `activity.json`, `ui-surfaces.json` and
`publication.json` all matched on SHA-256. The manifest grows from 36.4 MB to
39.8 MB, which is the explanations on all 571 components; the base projection
carried none.

## The defect that held the deploy

The VS Code GUI crawl failed `J1: drilling to the bottom` at depth 5.
Reproducible, and attributed by control:

| Code | Data | J1 desktop |
|---|---|---|
| `813e006` (#129) | with enrichment and captures | FAIL |
| `813e006` (#129) | without either | FAIL |
| `7d67b4c` (#127, live at the time) | same | PASS in 8.4s |

So the viewer code regressed it, not the new data. The trace named the
mechanism exactly: after a drill lands, the pointer has not moved, a
different node renders under it, and that node's hover preview opens 400x253
over the whole of the next node in the chain. #129 had made the preview
interactive so a reader could move in and scroll it, so the preview held the
double-click. Moving toward the target made it worse, because that point is
inside the card and the card took the mouse-enter and retained itself. The
node was unreachable without panning the graph away first.

Measured at the failing hop: target node at x 287 y 418, 339 by 176; the open
preview belonging to `src/vs/sessions/test/browser` at x 257 y 362, 400 by
253, covering it whole.

This is a reader-facing defect, not a harness artifact, and CI cannot see it:
the VS Code crawl needs the private dataset and runs only at deploy time.

## The fix (PR #130)

Three parts, and the first two attempts are worth recording because they
failed for instructive reasons.

Attempt one dismissed the card on `pointermove`. It only works while the
pointer keeps moving, and a stationary reader or a retrying harness never
sends another move. Attempt two made the card itself deaf to the pointer,
which worked, and the trace then named a second blocker underneath it: React
Flow gives the toolbar wrapper pointer-events of its own and the wrapper is
larger than the card.

What shipped: the card is born deaf to the pointer, and the window listener
that already owned the hover lifecycle turns it on only where the reader is
on the card and no other node is underneath. The default being off is what
makes it deterministic, because the first hit test passes without waiting for
an event or a retry, and `pointer-events` is set on the element rather than
through state so it holds for the next hit test rather than after a render.
The toolbar wrapper is transparent too. A coarse pointer keeps the card
interactive as before.

Trade: where the card overlaps another node the node wins, so the card cannot
be scrolled in that region without moving it off first. An unreachable node
is the worse failure.

A regression the crawl would not have caught was found by reading the touch
path: the listener that switches the card on is gated on `!isTouchDevice`, so
the first version left the card permanently non-interactive on touch. No
crawl case covers touch and hold. Fixed before merge.

## Verification

| Check | Result |
|---|---|
| VS Code crawl, desktop and mobile, run serially | 77 of 77, exit 0 |
| `J1` at depth 5 | passes in 8.1s, against 8.4s for the healthy control |
| `hover documentation can be entered and scrolled` | passes at 1440x1000 and 1024x768 |
| Viewer unit tests | 704 passed, including 5 new for the reach helper |
| `tsc --noEmit`, `npm run lint` | clean, clean |
| UnaMentis iOS crawl on the same viewer build | failure set identical, test for test, to unmodified `813e006` |
| PR #130 CI | all 13 checks green |
| Packaging | 681 files, no symlinks, nothing over the 25 MiB cap, no access control inside |
| `wrangler pages dev` | capture PNG decodes at 1440x900; manifest decodes to 39.8 MB with 571 of 571 explanations; big shard decodes to 49.9 MB; 0 failed requests, 0 page errors |
| Shipped asset carries the fix | `elementsFromPoint` present in `index-D8RBOGN7.js` |
| Tested build equals packaged build | `index-D8RBOGN7.js` in both |
| Merged tree equals tested tree | `74ffb1845aa028ae00b6eba1c0518ccd9f0f8c20` |

The UnaMentis failures belong to a check bundle assembled without
`--publication` and `--upstream-source`. They are not what those sites serve,
and they are unaffected by this change. The cross-subject check was run
because merging fires `deploy-downstream.yml`.

## Deploy

| | |
|---|---|
| Project | `syscorpus-vscode` |
| Deployment | `63b162e8-5b86-4626-89f5-a2cae8b5778e`, Production, branch main, source `6ec5ee5` |
| Uploaded | 680 files, 12 new against the previous deployment |
| Deleted | `69f96419` (the superseded #127 deployment) and `c409cd5b` (see below), so exactly one is live; both URLs now 404 |
| Verified from outside | the deployment's pages.dev URL serves the app with no gate strings; `ui-surfaces.json` and the capture PNG both served; production alias 200 |
| Custom hostname | `vscode-demo.syscorpus.com` still 302s to Cloudflare Access, unchanged |

**A provenance error, made and corrected.** The first deploy, `c409cd5b`,
carried a `--commit-hash` typed from memory rather than read:
`6ec5ee54cbb1...` where main is `6ec5ee57971b...`. The bundle content was
correct and verified; only the recorded commit was wrong, which breaks the
audit trail this project exists to keep. Redeployed as `63b162e8` with
`$(git rev-parse origin/main)` read directly, and `c409cd5b` deleted. Never
hand-expand a short SHA.

## Open items

| # | Item | Owner decision needed |
|---|---|---|
| 1 | `[mobile] tours: every tour plays end to end` is unstable under parallelism. It failed on the first run of this session before any change, and stalled twice for 19 to 25 minutes. The crawl config's `timeout: 2 * 60 * 60 * 1000` turns a stall into a silent hang rather than a failure, which cost most of this session's confusion. Serial runs are clean | whether to stabilise the test or lower the per-test timeout |
| 2 | CI cannot catch this defect class at all. A case on the synthetic reading fixture, which CI does run, would have caught the depth-5 regression before merge. Not added here, because it is new test surface | whether to add the guard |
| 3 | The Pages Access policy for `*.syscorpus-vscode.pages.dev` remains a dashboard toggle, carried over from the 2026-09-03 record | enable, or leave the pages.dev hostnames open |
