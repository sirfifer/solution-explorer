# Run record: shipping the identity front door to the VS Code demo

Date: 2026-09-03. Owner directive: the reviewed Overview changes must be
committed, pushed and live on the VS Code demo, and what was tested locally
must be what is deployed. Executed under the ship workflow from the frontier
session; the option 1 implementation itself was Opus's work on
`wt/ui-gateway-option1` (see `RUN-2026-09-03-ui-gateway.md`).

## What was reviewed

The owner confirmed `http://127.0.0.1:5185/?mode=overview` as the reviewed
page: the viewer built from `wt/ui-gateway-option1` at `f02ab67`, over a
reprojection of the VS Code snapshot (commit `474a349a`) from a copy of the
canonical store with the branch's analyzer, plus the six review corrections
in `demos/review-corrections/vscode.json`. Compared with the canonical
finalization projection that the live demo served until today: identical
component set, one more relationship (5454 against 5453), 15 more files
counted (15,219 against 15,204), and the new `identity` block. The data
shipped is that reprojection.

## Commits

| sha | what |
|---|---|
| `befd7df` | Register `IdentityCard.tsx` in the GUI plan surface inventory (first CI run failed the plan completeness check) |
| `89780e3` | Keep phone fits clear of the zoom controls (see below) |
| `ade4f4c` | Squash merge of PR #122 to main |

Tree of `ade4f4c` verified identical to the tree of `89780e3`
(`4db602d635c705575d157827664716d901940e80`), so the bundle built at
`89780e3` is the merged content.

## The phone fit finding

The publication bundle's mobile crawl failed two graph cases: the leftmost
top-level node (`cli`, x=25 to 88) sat under the React Flow zoom controls
(x=15 to 59). Measured across four bundles on the iPhone 13 viewport:

| bundle | cli node x | passes |
|---|---|---|
| branch viewer, reprojection, no publication (5185) | 25 to 88, y clears controls by 1px | yes |
| main viewer, reprojection, publication | 25 to 97, centre clears by 2px | yes |
| branch viewer, canonical data, publication | 80 to 148 | yes |
| branch viewer, reprojection, publication | 25 to 88, centre under controls | no |

A standing hazard, not a layout change in the branch: the publication
banner's 45px was the pixel that tipped it. Fix: every fit on a canvas
narrower than 640px reserves the controls' width on the left, as it already
reserved the drill hint at the top.

## Verification

| Check | Result |
|---|---|
| `ruff`, `pytest` on the branch | clean; 2458 passed, 5 skipped, 1 xfailed |
| `tsc --noEmit`, `eslint`, `vitest` at `89780e3` | clean, clean, 665 passed |
| `/code-review high` on the branch | no defect in the shipped VS Code output; follow-ups filed as a GitHub issue |
| PR #122 CI at `89780e3` | all jobs green |
| Post-merge on main | `ci.yml` success, Architecture Visualization success, `deploy-downstream.yml` success |
| Quick crawl, publication bundle at `89780e3`, VS Code | 60 of 60, desktop and iPhone 13 |
| Quick crawl, UnaMentis on the same viewer build | 60 of 60 |
| `publish-demo-bundle.py` safety checks | none; `publication.json` OK; 679 files; no symlinks; nothing over 25 MiB |
| `wrangler pages dev` proof | 401 ungated; 401 wrong passcode; 303 right passcode; manifest 2.8 MB on the wire decodes to 36.4 MB with `identity`; big shard 4.5 MB decodes to 49.9 MB; browser through the gate renders Overview (5 chips, 5 portrait cards), Workbench (6 nodes), drill into `src`, 0 failed requests, 0 page errors |

## Deploy

Wrangler refused the first attempt: `manifest.json` is 34.7 MiB and Pages
caps files at 25 MiB. The live deployment from the night before served a
32.6 MiB manifest and a 47.6 MiB shard, which turned out to come from a
`_worker.js` written in a temporary directory that served gzip copies of
those two files. That Worker had no gate, so the data was readable at the
deployment's `*.pages.dev` URL. The mechanism is now committed:
`infrastructure/preview-gate/_worker.js` (gate first, gzip second) and
`scripts/publish-demo-bundle.py`, with `tests/test_publish_demo_bundle.py`
and `docs/publication/DEMO-DEPLOY-RUNBOOK.md`.

| | |
|---|---|
| Project | `syscorpus-vscode` |
| Deployment | `291cf0ea-b70c-4172-bdf6-01bcf3e0c55b`, Production, branch main, source `ade4f4c` |
| Uploaded | 101 new files, 577 already in the project |
| Preview URL | `https://291cf0ea.syscorpus-vscode.pages.dev/`: 401 gate page on `/`, `/architecture/manifest.json`, `/architecture/orientation.json`, `/architecture/data/detail-cli.json` |
| Production alias | `https://syscorpus-vscode.pages.dev/`: 401 gate page |
| Custom hostname | `https://vscode-demo.syscorpus.com/`: 302 to Cloudflare Access, as before |

Not verified from outside: the rendered page behind the gate, because the
passcode is a secret that is used, never read. The identical bundle was
proven under the Workers runtime locally (table above).

## Open items

| # | Item | Owner decision needed |
|---|---|---|
| 1 | CLOSED 2026-09-03: the two earlier deployments `ac1bb93f` and `0fd2ab9c` were deleted from the project at the owner's instruction (`wrangler pages deployment delete`); their preview URLs now return 404 and `291cf0ea` is the only deployment. Still open: the Pages Access policy for `*.syscorpus-vscode.pages.dev`, a dashboard toggle only the owner can set | enable the Access policy on the Pages project |
| 2 | The custom hostname now has Access and the passcode in series | keep, or teach the Worker to honour a verified Access JWT |
| 3 | `demo-site.py deploy` still expects `functions/_middleware.js` and does not gzip | route it through `publish-demo-bundle.py` |
| 4 | Review follow-ups on `analyzer/derive/identity.py` and the assembly scripts | GitHub issue filed from this run |
| 5 | Throwaway Pages projects `zz-size-probe` and `zz-size-probe2` were created to test the cap and deleted; the `zz-size-probe` deploy never uploaded, `zz-size-probe2` returned a 500 from the upload API | none |

## Token spend

About 240,000 session tokens for the ship pass at the frontier, plus the
six review finder agents at roughly 900,000 subagent tokens in total.
