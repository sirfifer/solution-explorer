# The first visit orientation walk, 2026-09-03

Executes `docs/research/ui-gateway/ORIENTATION-WALK-PROPOSAL.md` on branch
`wt/orientation-walk`. The walk starts automatically on a reader's first visit,
can be skipped immediately, stays dismissed in that browser, and can be
replayed from the visible upper-right Help control at any time. The browser record is localStorage key
`arch-viz-orientation-v1`. The legacy help key is read for compatibility but
is never written.

The work stayed in
`/Volumes/Studio/dev/.worktrees/solution-explorer--relicense-polyform-nc` and
was not pushed. Canonical stores and the owner's running demos were not
modified.

## Owner smoke-review amendment

The first local smoke review changed the opening emphasis before deployment.
SysCorpus is now part of the first lesson and the persistent product frame: the
centered opening, Overview header, Overview context band, Help link, Workbench
product link, and footer all name the product. The project name remains beside
it in the header and in the opening sentence. The product links resolve to
`https://syscorpus.com/`, verified HTTP 200 on 2026-09-03.

A second smoke-review amendment gives the first page more explanatory weight
without turning it into a prose wall. It now calls the result an explorable,
evidence-linked model of the subject and uses three compact statements to name
system understanding, source-level traceability, and multiple investigative
angles. An in-product interface-guide action provides the longer explanation.

A third smoke-review amendment removes the optional corner invitation. A new
browser now begins with a centered orientation step that gives equal visual
weight to the generated project and SysCorpus, with Skip immediately available.
Every stop now uses the generated project name where it improves the lesson and
describes SysCorpus as the way the reader explores that project.

A fourth smoke-review amendment changes the opening to "Meet {project} through
the lens of SysCorpus", asks "How much of {project} was analyzed?" at the trust
step, expands the theme and lens choices while each is taught, and makes the
Workbench crossing wait for real graph nodes. Finishing or skipping returns to
Overview. The browser regression now verifies visible nodes both during the map
step and after reopening Workbench from the completed tour.

A fifth smoke-review amendment makes replay genuinely discoverable. A labeled
`Replay tour` button is always present in the Overview and Workbench headers,
including the compact mobile layouts. The Help action remains available as a
secondary path.

A sixth smoke-review amendment moves Help out of the obscure corner affordance
and into both upper-right headers as a plainly labeled control. Inside Help, a
full-width primary button says `Replay guided tour`, preceded by a sentence that
explains what it does.

A seventh smoke-review amendment makes the opening Project and Presented by
blocks external links that open in new tabs. The Visual Studio Code demo points
to its official product homepage at `https://code.visualstudio.com/`; SysCorpus
points to `https://syscorpus.com/`. An optional `subject.homepage_url`
publication field carries this generically, with the repository as a fallback.
The project heading is also linked in the Overview and desktop Workbench frame.

An eighth smoke-review amendment removes the standalone `Replay tour` header
button. Help is the single persistent route back to the tour. It remains
upper-right and contains the prominent full-width `Replay guided tour` action.
The theme and lens stops now spotlight each expanded menu tightly, while a
separate labeled outline identifies the exact toolbar control that opened it.

The footer notice is deliberately scoped to the product software and viewer:
"© 2025-2026 Richard Amerman. SysCorpus software and viewer." It does not claim
the viewed project's name, source, or documentation; their ownership, license,
commit, and non-affiliation language remain in publication metadata.

## What shipped

- A fixed, data-aware orientation stop table with eight desktop stops and
  seven mobile stops.
- An automatic, centered first-visit orientation with balanced Project and
  Presented by identity blocks plus immediate Skip and Next actions.
- Done, Skip, Escape, and outside-click exits, with completion or dismissal
  remembered per browser profile.
- A responsive spotlight and card that follow live controls across Overview
  and Workbench without replacing those controls.
- Tour-driven theme and lens menus that open only for their relevant stops and
  close cleanly when the reader advances or exits.
- A map-readiness gate and visible preparation state, so the Workbench lesson
  cannot land on an empty canvas shell.
- A rewritten Help dialog whose Guide tab describes the current walk and whose
  footer can replay it from either aperture.
- A labeled upper-right Help control and an unmistakable full-width
  `Replay guided tour` action inside Help.
- Tight menu spotlights plus separately labeled Theme and Lens trigger outlines,
  avoiding empty bounding rectangles around disjoint elements.
- Public-facing project and SysCorpus links on the opening identity blocks,
  opening in new tabs with repository links kept distinct.
- URL overrides `orientation=start` and `orientation=invite` for review and
  demonstrations. URL synchronization removes the override after consuming it.
- New navigation-beacon fields and deterministic Playwright rules W1 to W6.

## Integration defects found and fixed

| Defect | Resolution |
|---|---|
| Some fast step changes paired the next anchor id with the previous anchor rectangle, leaving a 1px spotlight | Anchor identity and geometry now update as one state value and are remeasured after layout |
| A mobile crossing could hide the header or leave no visible Overview return control | The orientation keeps mobile chrome visible and the mobile Overview control publishes its test id |
| The consumed `orientation` query remained in later synchronized URLs | It is now an inbound-only managed parameter and is dropped by normal URL synchronization |
| Card exclusion used an estimated rectangle and could over-trim a valid highlight | The spotlight now excludes the card's measured rendered rectangle |
| The Help replay crawl waited on a graph rendering detail unrelated to Help | It now waits for the published Workbench state and the visible Help control |
| The map lesson could appear before asynchronous layout produced any nodes | The lesson waits for a completed nonempty layout, while the canvas shows a preparation status |
| Theme and lens controls were named but visually collapsed | Their choice lists expand for the relevant stop, participate in card placement, and close on advance |
| Done left the reader in Workbench | Every tour exit now restores Overview; reopening Workbench is regression-tested for visible nodes |

The first two Overview stops use the live identity statement and the primary
question-card group in Portrait. This resolves the plan's anchor ambiguity
without changing the reader's chosen Overview posture.

## Verification

| Check | Result |
|---|---|
| `npx tsc --noEmit` | clean |
| `npx eslint src/` | clean |
| Baseline `npx vitest run` | 65 files, 665 tests, 0 failures |
| Final `npx vitest run` | 69 files, 689 tests, 0 failures after the replay, linking, and responsive-header amendments |
| Failing-file set before | empty |
| Failing-file set after | empty, therefore a subset of before |
| OW-3 surfaces and journeys regression | 18 of 18 passed |
| Orientation W1 to W6 | 12 of 12 passed, desktop Chromium and iPhone 13 WebKit |
| VS Code final quick crawl | 74 of 74 passed after the Help-only replay and split menu-highlight amendments, desktop Chromium and iPhone 13 WebKit |
| Centered opening visual | Playwright mobile capture inspected; project and SysCorpus receive equal identity blocks, copy fits, Skip and Next remain clear |
| UnaMentis final quick crawl | 70 of 70 passed, desktop Chromium and iPhone 13 WebKit |
| Publication validation and publish-helper tests | publication metadata valid; 43 of 43 tests passed |
| Expanded-control geometry | Theme and lens lists receive tight menu spotlights and labeled trigger outlines, do not cover the tour card, and close afterward on both viewports |

After the owner-requested product-framing, expanded first-page, and automatic
balanced-opening amendments,
the full viewer suite is 69 files and 689 tests with 0 failures. The VS Code
quick crawl is 74 of 74 on desktop Chromium and iPhone 13, including rule O11
across Portrait, Questions and Atlas, the new capability summary, and map nodes
during and after the orientation. TypeScript, ESLint, publication validation,
the `vscode-demo` production build, and all 43 publication and bundle-helper
tests are clean. The in-app browser was unavailable
to the execution session, so the owner's local smoke review remains the visual
approval step.

Final run records are gitignored testboard artifacts:

- `.testboard/runs/2026-09-03T21-05-58-686Z-crawl-Visual-Studio-Code`
- `.testboard/runs/2026-09-03T21-09-22-258Z-crawl-unamentis-ios`

Both subjects were rebuilt from copies of their canonical stores. The
reprojections produced 571 components, 15,219 files, 151,134 symbols and 5,454
relationships for VS Code, and 165 components, 559 files, 7,617 symbols and
449 relationships for UnaMentis. Both report 100% source coverage. The VS Code
viewer was built in `vscode-demo` mode, preserving Atlas as its default theme.

## Screenshots

The 68 PNG captures from the earlier invitation iteration are local, gitignored
review artifacts under `viewer/.ow-screens/`. They are retained as historical
geometry evidence but the `invite.png` captures are superseded by the centered
`what-this-is` opening. Each of these eight directories contains the earlier
files:

- `vscode/atlas-light/1440x900`
- `vscode/atlas-light/390x844`
- `vscode/signal-dark/1440x900`
- `vscode/signal-dark/390x844`
- `unamentis-ios/atlas-light/1440x900`
- `unamentis-ios/atlas-light/390x844`
- `unamentis-ios/signal-dark/1440x900`
- `unamentis-ios/signal-dark/390x844`

Desktop directories contain `invite.png`, `what-this-is.png`,
`start-with-a-question.png`, `two-views.png`, `how-much-was-analyzed.png`,
`your-tools.png`, `the-map.png`, `lenses.png`, and `if-you-get-lost.png`.
Mobile directories omit `how-much-was-analyzed.png` and end with
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
