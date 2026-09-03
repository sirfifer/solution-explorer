# The first visit orientation walk, 2026-09-03

Executes `docs/research/ui-gateway/ORIENTATION-WALK-PROPOSAL.md` on branch
`wt/orientation-walk`. The walk is offered on a reader's first visit, can be
dismissed, stays dismissed in that browser, and can be replayed from Help at
any time. The browser record is localStorage key
`arch-viz-orientation-v1`. The legacy help key is read for compatibility but
is never written.

The work stayed in
`/Volumes/Studio/dev/.worktrees/solution-explorer--relicense-polyform-nc` and
was not pushed. Canonical stores and the owner's running demos were not
modified.

## What shipped

- A fixed, data-aware orientation stop table with eight desktop stops and
  seven mobile stops.
- A first-visit invitation with Show me around and Not now actions.
- Done, Skip, Escape, and outside-click exits, with completion or dismissal
  remembered per browser profile.
- A responsive spotlight and card that follow live controls across Overview
  and Workbench without replacing those controls.
- A rewritten Help dialog whose Guide tab describes the current walk and whose
  footer can replay it from either aperture.
- URL overrides `orientation=start` and `orientation=invite` for review and
  demonstrations. URL synchronization removes the override after consuming it.
- New navigation-beacon fields and deterministic Playwright rules W1 to W5.

## Integration defects found and fixed

| Defect | Resolution |
|---|---|
| Some fast step changes paired the next anchor id with the previous anchor rectangle, leaving a 1px spotlight | Anchor identity and geometry now update as one state value and are remeasured after layout |
| A mobile crossing could hide the header or leave no visible Overview return control | The orientation keeps mobile chrome visible and the mobile Overview control publishes its test id |
| The consumed `orientation` query remained in later synchronized URLs | It is now an inbound-only managed parameter and is dropped by normal URL synchronization |
| Card exclusion used an estimated rectangle and could over-trim a valid highlight | The spotlight now excludes the card's measured rendered rectangle |
| The Help replay crawl waited on a graph rendering detail unrelated to Help | It now waits for the published Workbench state and the visible Help control |

The first two Overview stops use the live identity statement and the primary
question-card group in Portrait. This resolves the plan's anchor ambiguity
without changing the reader's chosen Overview posture.

## Verification

| Check | Result |
|---|---|
| `npx tsc --noEmit` | clean |
| `npx eslint src/` | clean |
| Baseline `npx vitest run` | 65 files, 665 tests, 0 failures |
| Final `npx vitest run` | 69 files, 681 tests, 0 failures |
| Failing-file set before | empty |
| Failing-file set after | empty, therefore a subset of before |
| OW-3 surfaces and journeys regression | 18 of 18 passed |
| VS Code final quick crawl | 70 of 70 passed, desktop Chromium and iPhone 13 WebKit |
| UnaMentis final quick crawl | 70 of 70 passed, desktop Chromium and iPhone 13 WebKit |
| Screenshot geometry checks | 60 of 60 stop captures fit their copy and keep card and highlight disjoint |

Final run records are gitignored testboard artifacts:

- `.testboard/runs/2026-09-03T21-05-58-686Z-crawl-Visual-Studio-Code`
- `.testboard/runs/2026-09-03T21-09-22-258Z-crawl-unamentis-ios`

Both subjects were rebuilt from copies of their canonical stores. The
reprojections produced 571 components, 15,219 files, 151,134 symbols and 5,454
relationships for VS Code, and 165 components, 559 files, 7,617 symbols and
449 relationships for UnaMentis. Both report 100% source coverage. The VS Code
viewer was built in `vscode-demo` mode, preserving Atlas as its default theme.

## Screenshots

The 68 PNG captures are local, gitignored review artifacts under
`viewer/.ow-screens/`. Each of these eight directories contains the listed
invite and stop files:

- `vscode/atlas-light/1440x900`
- `vscode/atlas-light/390x844`
- `vscode/signal-dark/1440x900`
- `vscode/signal-dark/390x844`
- `unamentis-ios/atlas-light/1440x900`
- `unamentis-ios/atlas-light/390x844`
- `unamentis-ios/signal-dark/1440x900`
- `unamentis-ios/signal-dark/390x844`

Desktop directories contain `invite.png`, `what-this-is.png`,
`start-with-a-question.png`, `two-views.png`, `how-much-was-read.png`,
`your-tools.png`, `the-map.png`, `lenses.png`, and `if-you-get-lost.png`.
Mobile directories omit `how-much-was-read.png` and end with
`if-you-get-lost-mobile.png`.

Contact sheets in the same directories were inspected by eye. No card covers
its target, no copy is truncated, and the crossing does not flash the old
Workbench state.

## Open items

| Item | Status |
|---|---|
| Publish to the owner's existing VS Code demo | Not performed. The execution plan explicitly forbids touching the owner's running ports and forbids pushing. The tested candidate is assembled at `.testboard/serve/vscode` and is ready for the owner's normal publication path. |
| Persistence mechanism | Deliberately localStorage rather than a cookie. It has the requested per-browser and per-device behavior without sending orientation state to the server. |
| Browser-profile synchronization | Not added. A different device or browser profile sees the invitation again, as requested. Browser vendors may synchronize site data independently. |

## Cumulative token spend

One primary execution session, no subagents. This runtime does not expose a
cumulative token counter, so a defensible numeric token total is unavailable.
No model call was made by the product or analyzer, and the orientation feature
cannot make one.

## Commands

```sh
# Copy canonical stores, then reproject with the repository environment.
cp /Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/index.db \
  .testboard/stores/vscode/index.db
cp /Volumes/Studio/dev/solution-explorer/.testboard/live/unamentis-ios-full-20260830-a5717bf/index.db \
  .testboard/stores/unamentis-ios/index.db

/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway/.venv-wt/bin/python \
  analyze.py /Volumes/Studio/dev/.demo-corpus/vscode \
  --engine v2 --store .testboard/stores/vscode/index.db \
  --output .testboard/projections/vscode/architecture --split
/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway/.venv-wt/bin/python \
  analyze.py /Volumes/Studio/dev/unamentis-ios \
  --engine v2 --store .testboard/stores/unamentis-ios/index.db \
  --output .testboard/projections/unamentis-ios/architecture --split

/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway/.venv-wt/bin/python \
  scripts/reorient.py \
  .testboard/projections/vscode/architecture --check
/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway/.venv-wt/bin/python \
  scripts/reorient.py \
  .testboard/projections/unamentis-ios/architecture --check

# Build in the VS Code demo mode, then reuse that exact viewer bundle.
/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway/.venv-wt/bin/python \
  scripts/assemble-serve.py vscode \
  --projection "$PWD/.testboard/projections/vscode/architecture" \
  --corrections demos/review-corrections/vscode.json
/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway/.venv-wt/bin/python \
  scripts/assemble-serve.py unamentis-ios \
  --projection "$PWD/.testboard/projections/unamentis-ios/architecture" \
  --corrections demos/review-corrections/unamentis-ios.json --no-build

# Run the quick crawl against isolated local servers, once per subject.
cd viewer
CRAWL_BASE_URL=http://127.0.0.1:5301 \
  CRAWL_DATA_DIR="$PWD/../.testboard/serve/vscode/architecture" \
  CRAWL_PROFILE=quick npm run test:crawl
CRAWL_BASE_URL=http://127.0.0.1:5302 \
  CRAWL_DATA_DIR="$PWD/../.testboard/serve/unamentis-ios/architecture" \
  CRAWL_PROFILE=quick npm run test:crawl
```
