# The deterministic GUI crawl

A scripted, subject-agnostic Playwright suite that proves the viewer can reach
and render everything the projection holds. It is the mechanical half of GUI
testing; `viewer/tests/gui/` (the AI-operated vector plan) is the judgement
half. Neither replaces the other.

## What each one is for

| | `viewer/tests/gui/` | `viewer/tests/crawl/` (here) |
|---|---|---|
| Operated by | an LLM agent driving a browser | `@playwright/test`, unattended |
| Cases | ~100 hand-authored, hand-walked | none; the shape is discovered per dataset |
| Answers | does this surface read correctly to a person | is everything in the data reachable and non-broken |
| Cost | hours, agent-attended | minutes, free to rerun |
| Catches | wrong copy, bad affordance, misleading layout | unreachable components, blank tabs, dead deep links, console errors at scale |

The crawl exists because the defects that actually hurt us were coverage
defects, not aesthetic ones: the data was whole and the UI still could not get
you to it. That question is exhaustively checkable by machine, and checking it
by hand across a subject the size of private large-repository validation corpus is not realistic.

## Running it

The bounded graph cases include the hover-reading regression: move the actual
pointer into a scrollable popup, remain beyond the dismissal delay, scroll its
content without moving the graph, return to the trigger, and then leave. They
also check all four containment edges and the clicked help panel's focus,
Escape/close behavior, and exclusion of duplicate previews. These cases run in
both quick and full profiles at normal and smaller desktop window sizes.
CI also runs these cases against `fixtures/reading/manifest.json`, a synthetic
long explanation that guarantees overflow. `CRAWL_REQUIRE_SCROLLABLE=1` makes
missing scrolling coverage a failure in that gate rather than a skip.

The suite needs two things: a served build, and the projection that build is
serving, so it can compare the UI against the data.

```bash
# 1. Build the viewer and assemble a serve root from the projection you want
#    to crawl. assemble-serve.py builds unless told not to, and symlinks the
#    projection rather than copying it.
python3 scripts/assemble-serve.py <slug> --projection <your-projection-dir>

# 2. Crawl it. Playwright starts the static server itself.
cd viewer
CRAWL_SERVE_DIR=<repo>/.testboard/serve/<slug> npm run test:crawl
```

Or against the published site, with no serve root at all. A `globalSetup`
downloads the manifest, the publication sidecar when it answers 200, and the
search index's first shard into `results/remote-data/<host>/architecture/`,
then points the workers at it. Detail shards are fetched on demand rather than
mirrored, so a large subject does not become a several-hundred-megabyte
download before the first test runs.

```bash
cd viewer
CRAWL_BASE_URL=https://<host> npm run test:crawl
```

Environment:

| Variable | Meaning |
|---|---|
| `CRAWL_SERVE_DIR` | directory to serve; Playwright starts `http.server` on it |
| `CRAWL_BASE_URL` | crawl an already-running or remote origin instead (default `http://127.0.0.1:4180`) |
| `CRAWL_DATA_DIR` | the projection to read as ground truth (default `<serve dir>/architecture`; set for you when crawling a remote origin) |
| `CRAWL_PROFILE` | `quick` (default) or `full`. See profiles below |
| `CRAWL_MAX_COMPONENTS` | budget for the per-component sweeps; unset or `0` means every component. An explicit value always beats the profile's |
| `CRAWL_MOBILE` | `0` disables the mobile project; it runs by default |
| `CRAWL_CHANNEL` | the maturity channel the expectations assume (default `stable`, which is what the app resolves without `?channel=`) |
| `CRAWL_MODE` | not a variable: the aperture is a URL parameter. Workbench specs add `mode=workbench` themselves; `overview.spec.ts` navigates without it on purpose |
| `CRAWL_PARAMS` | path to a JSON parameters file naming what this build has switched off (below) |
| `CRAWL_ALLOW_ERRORS` | extra comma-separated URL fragments allowed to 404 |

### Profiles

The two profiles bound the two different kinds of work in here. The
**exhaustive sweeps** (every component by URL, every tab of every component)
cost one navigation per component and are hour-scale on a large subject, so
they are what a budget is for. The **bounded specs** (surfaces, graph,
journeys, tours) do a fixed amount of work whatever the subject's size and
always run in full: budgeting them would mean sometimes not playing a tour,
which is the thing they exist to check.

- `quick` (default): sets `CRAWL_MAX_COMPONENTS=40` when nothing else has.
  Under ten minutes on a 168-component subject, both projects.
- `full`: no budget. Hour-scale, as the sweeps already are.

### Projects

Two Playwright projects, both reported under their own name in the run record:

- `desktop` (Desktop Chrome) runs every test.
- `mobile` (`devices["iPhone 13"]`, 390x844, touch, WebKit) runs the tests
  tagged `@mobile`: the boot check, all of surfaces and tours, journeys J1, J5
  and J6, every orientation rule, and the graph's click and drill cases. The detail panel lives in a
  bottom sheet at this size and the lens panels in a second one, but the
  selector contract is identical on both, so no spec branches on viewport. A
  mobile failure is a real failure. `npx playwright install webkit` once, or
  `CRAWL_MOBILE=0` to skip the project.

Results land in `viewer/tests/crawl/results/` (gitignored): `crawl-results.json`
plus failure screenshots and traces. The run record goes to
`.testboard/runs/<stamp>-crawl-<subject>/`, with `-remote` appended when the
target was a deployed origin.

## How it stays subject-agnostic

Every expectation comes from the artifact, never from a constant in a spec:

- the component set, the parent/child lists and the per-component file and
  symbol counts come from `manifest.json` and `component_detail_index`
- the entry points, the lens set, the tour list, the lens-scoped row ids and the
  per-component tab facts are all derived from the manifest by `contract.ts`,
  and compared against the DOM in BOTH directions
- the Overview's question routes and portrait areas come from
  `architecture/orientation.json`, fetched through the request context like a
  detail shard. When the sidecar is absent the app builds a fallback and the
  Overview still works, so the spec says so in a coverage annotation instead of
  asserting against a document nobody authored
- the lens list is also read off the lens switcher, so a lens registered next
  month is exercised the day it ships, and the two lists must agree
- the sample, when a budget is set, is depth-stratified so deep nodes are not
  the ones dropped, and what was dropped is reported in the run annotations

The two things it does hardcode are the honest-empty rule (a surface with no
data must say so; blank is a failure) and the requirement that nothing logs a
console error or an undeclared 404. The 404 allowlist mirrors the probe
inventory in `viewer/tests/gui/datasets.yaml`.

`contract.ts` reads the shipped artifact and imports nothing from `viewer/src`,
so a change to the app that breaks the published contract shows up as a failure
rather than being compensated for. There is exactly one agreed exception:
`src/utils/lensMaturity.ts`, a dependency-free table of lens ids to stability
levels. Which lenses a reader may see is not derivable from the projection
alone, because a lens the data warrants can still be gated off by its maturity
on the resolved channel, and a crawl that did not know that would report a
correctly-hidden beta lens as missing on every run. The table is data with no
behaviour, which is what makes it safe to be the exception, and the lens
definitions read their maturity from it, so it is the source rather than a copy
that can drift.

## The selector contract

The suite drives the app through attributes the components publish on purpose.

An ARIA role is a contract, not a label, so one is added only where the
component keeps the promise the role makes.

The tab bar deliberately did **not** gain `role="tablist"`/`role="tab"`. That
pattern obliges arrow-key navigation between tabs and `aria-controls` pairing,
neither of which these buttons implement, and claiming the role without the
behavior leaves a screen-reader user worse off than a plain button does. Adding
it also changed the accessible role that seven existing unit tests query by,
which is how the overreach got caught. The tabs carry identity attributes only.

The tree did not gain `role="tree"`/`role="treeitem"` either, for the same
reason and after making the same mistake. An earlier revision added them, along
with `aria-level` and `aria-selected`. The tree pattern obliges a roving
tabindex, Up/Down between visible items, Right to expand, Left to collapse and
move to the parent, and Home/End; this tree implements none of it. Announcing
"tree" and then ignoring every key that announcement teaches a reader to press
is the tab-bar error wearing a different role name. `aria-expanded` stays on
the expanders, because a disclosure button really does expand.

So the crawl drives the tree through `data-*` attributes alone.

| Attribute | On | Carries |
|---|---|---|
| `data-testid="tree-navigator"` | the tree container | the tree root |
| `data-testid="tree-node"` | each component row | `data-component-id`, `data-depth`, `data-has-children`, `data-expanded`, `data-selected` |
| `data-testid="tree-node-toggle"` | the expander | click target that does not select |
| `data-testid="tree-children"` | a revealed child group | `data-parent-id` |
| `data-testid="tree-folder"` | an "Internal Components" group | `data-folder-name`, `data-expanded` |
| `data-testid="detail-panel"` | the detail pane | `data-component-id` actually rendered |
| `data-testid="detail-title"` | its heading | the component name |
| `data-testid="detail-tab"` | each tab | `data-tab`, `data-active` |
| `data-testid="detail-tabpanel"` | the tab body | `data-tab` currently shown |
| `data-testid="lens-select"` | the lens switcher | `data-lens` |
| `data-testid="identity-statement"` | the Overview headline | the composed statement, when the sidecar has one |
| `data-testid="form-factor"` | each form-factor chip | `data-kind` |
| `data-testid="form-factor-evidence"` | the opened chip's evidence panel | one `file:line marker` row per evidence entry |
| `data-testid="authors-claim"` | the maintainers' quoted paragraph | the README claim, captioned with its source |
| `data-testid="scale-summary"` | the demoted count line | the three headline counts, opening the trust drawer |

The suite also drives the shell, the canvas, the overlays and the tour player.
Same rule: every one is a contract, and removing one must break the crawl
loudly rather than quietly reducing what it covers.

### The navigation state beacon

One always-mounted, visually hidden `<div>` in `App.tsx` that publishes the
store's navigation state as attributes. It renders nothing, reads nothing but
the store, and is `aria-hidden` because it is not content.

It exists because half of what this suite checks is state, and state is not
reliably visible. "Nothing from the last journey is still in force" cannot be
read off a screenshot, and inferring it from which panels happen to be mounted
means writing a second, worse copy of the store in the test.

| Attribute | Carries |
|---|---|
| `data-testid="nav-state"` | the beacon itself |
| `data-mode` | which aperture published this state: overview or workbench |
| `data-level` | the semantic altitude: system, domain or component |
| `data-direction` | the Overview's opening posture: portrait, questions or atlas |
| `data-handoff` | "true" when this workbench was arrived at from Overview |
| `data-drill` | `drillLevel` or "" |
| `data-selected` | `selectedComponentId` or "" |
| `data-lens` | the active lens id |
| `data-flow`, `data-flow-step` | the followed entry flow and its step; both "" when no flow is being walked |
| `data-capability`, `data-entity`, `data-rule`, `data-finding` | the lens-scoped selection each lens owns, or "" |
| `data-tour`, `data-tour-step` | the active tour and its step; both "" when no tour is playing |
| `data-panel` | `activePanel` or "" |
| `data-detail` | `component`, `file`, `symbol`, `aggregate`, or "" |
| `data-overlays` | comma-joined open overlays from: search, findings, supply-chain, inventory, tours, help, admin, review, trust, preferences |
| `data-blast` | "true" when blast-radius mode is on, else "" |

The beacon is mounted in BOTH apertures. `App` returns `SystemOverview` before
it renders the workbench, so a beacon mounted only in the workbench could never
publish `data-mode="overview"`, which is the one state it most needs to answer.

**The beacon is never asserted alone.** Every state check reads the beacon AND
the visible expression of the same state: a panel present or absent, a node
carrying the selected class, a URL parameter. A beacon that says "reset" while
a tour panel is still on screen is a failure, and it is one this suite has
already found in the other direction (see what it has found, below).

### The shell, the canvas, the overlays

| Attribute | On | Carries |
|---|---|---|
| `data-testid="entry-bar"` | wrapper around the entry strip (coverage, gaps, findings, supply chain, tours) | `display: contents`, so it draws no box |
| `data-testid="drill-home"` | the header Home button | present only when drilled |
| `data-testid="search-button"` | the header search button | |
| `data-testid="help-button"` | the labeled Help button in the upper-right header | |
| `data-testid="help-overlay"` | the welcome or help dialog root | `data-kind`: welcome or help |
| `data-testid="findings-surface"` | FindingsSurface dialog root | |
| `data-testid="supply-chain-surface"` | SupplyChainSurface dialog root | |
| `data-testid="inventory-panel"` | InventoryPanel dialog root | |
| `data-testid="review-summary"` | ReviewSummary panel root | |
| `data-testid="breadcrumb-item"` | each breadcrumb in the graph header | `data-component-id`, `data-current` |
| `data-testid="graph-node"` | the ComponentNode card | `data-component-id`, `data-selected`, `data-has-children` |
| `data-testid="aggregate-node"` | the AggregateNode card | `data-aggregate-id`, `data-expanded` |
| `data-testid="node-preview"` | the node's hover documentation popup | `data-component-id` |
| `.react-flow__node[data-id]` | graph nodes (React Flow native) | the component or aggregate id; class `selected` when selected |
| `.react-flow` | the canvas container (React Flow native) | the bounding box for in-view checks |
| `data-testid="lens-panel"` | the mounted lens panel root | `data-lens` |
| `data-testid="lens-row"` | a selectable row in the Capability, Data, Rules and Design panels | `data-lens`, `data-row-id`, `data-selected` |
| `data-testid="flow-entry"` | an entry flow row in FlowPanel | `data-flow-id` |
| `data-testid="flow-next"`, `"flow-prev"`, `"flow-exit"` | FlowPanel follow controls | |
| `data-testid="tours-list-overlay"` | the tour list dialog root | |
| `data-testid="tour-list-item"` | a tour in the list | `data-tour-id`, `data-step-count`, `data-stale` |
| `data-testid="tour-step-panel"` | the docked step panel | `data-tour-id`, `data-step`, `data-step-count` |
| `data-testid="tour-step-item"` | a row in the step panel's jump list | `data-step`, `data-current` |
| `data-testid="tour-exit"` | the exit button in the step panel | |
| `data-testid="trust-strip"` | WorkbenchTrustStrip root | |
| `data-testid="trust-ledger-entry"` | the compact trust ledger button | coverage and producer gaps live here now |
| `data-testid="trust-drawer"` | TrustDrawer root | |
| `data-testid="preferences-drawer"` | ViewerPreferences root | |

### The Overview front door

| Attribute | On | Carries |
|---|---|---|
| `data-testid="system-overview"` | the Overview root | `data-direction` |
| `data-testid="overview-direction"` | each direction button | `data-direction`, `data-selected` |
| `data-testid="question-route"` | each question route button | `data-route-id`, `data-available` |
| `data-testid="question-route-continue"` | the button that acts on the chosen question | `data-route-id` |
| `data-testid="portrait-card"` | each portrait node card, in portrait and atlas | `data-node-id`, `data-target` |
| `data-testid="open-workbench"` | "Open detailed workspace", "Full map", and the switcher's workbench button | |
| `data-testid="open-overview"` | the switcher's return-to-Overview button | |

`.react-flow__node` and `.react-flow` are the only class selectors the suite
uses. They are framework-published identity rather than styling: a node's id
and the canvas's bounding box are not reachable any other way.

Changing or removing any of these breaks the crawl loudly, which is the point:
the attributes are the contract, and a refactor that drops them should have to
say so.

Three overlay flags were lifted out of component-local state so the beacon can
see them: HelpSystem's help and welcome dialogs, and the inventory panel that
CoverageBadge opens. Nothing about when they open or close changed; the
components still own every gesture that moves them.

## What each spec proves

| Spec | Question |
|---|---|
| `reachability` | can a reader GET to everything the data holds, by URL and by clicking |
| `depth` | when they arrive, is the view populated the way the data says |
| `search` | does picking a result land you on what it named |
| `surfaces` | is exactly what the data warrants on screen, and does it work |
| `graph` | does the diagram do what it looks like it does |
| `journeys` | does a path leave anything behind when the reader returns to the start |
| `tours` | does the guided walkthrough actually walk |
| `overview` | does the front door open onto the right thing, and is the trip back lossless |

**`surfaces.spec.ts`** checks the perimeter in both directions: every globally
reachable entry point (coverage, gaps, findings, supply chain, tours, search,
help, the lens switcher) must be present exactly when the projection carries
the data behind it, and the lens switcher must offer exactly the lenses the
data warrants. Then each present entry is opened, checked for text, checked
against the beacon's overlay list, closed, and checked for having moved
nothing. Last, a depth-stratified sample of components is held to the detail
tab presence rules read out of `DetailPanel.tsx`. Coverage and gaps are treated
as inline disclosures rather than overlays, because they are, and the lens
switcher is treated as a control, because it is.

**`graph.spec.ts`** asserts nothing about node positions, which are layout
output and change for reasons that have nothing to do with the product. It
asserts what a reader can name: only nodes the projection warrants render at a
level, clicking one selects it and clicking the empty pane clears it, selecting
something off-screen brings it into view within two seconds, and
double-clicking a node with children drills into it while Home comes back to a
bare URL. The in-view check starts from a node that is genuinely off-screen,
panning the canvas away if it has to, because the app deliberately does not
re-centre a selection that is already visible.

**`journeys.spec.ts`** walks six paths and then runs the shared reset probe
after each one. J1 drills to the deepest component and back; J2 walks browser
back one level at a time and forward once; J3 round-trips every lens holding a
selection (invariant I12); J4 picks the first row in every lens that has rows
and checks the state and URL param it owns, and that leaving the lens leaves
none of them behind; J5 opens and closes every overlay from inside a drill; J6
loads a deep link cold and reloads it. The reset probe returns the way a reader
would, then asserts the beacon, the DOM and the URL are all back to nothing.

**`overview.spec.ts`** covers the aperture a fresh reader actually lands in.
O1 checks that a bare URL opens the front door and not the workbench, and that
the two apertures are not both on screen. O2 renders each of the three opening
directions. O3 compares the question routes against `orientation.json` in both
directions, including each route's availability flag. O4 follows every available
route and asserts per target kind (a lens sets the lens and the URL, a surface
opens and is named in the overlays list, a tour starts under its own id), while
an unavailable route must do nothing even when the click is forced. O5 opens
every portrait card and holds it to the graph spec's in-view rule. O6 is the
lossless round trip: drill, select, lens and level must be identical after
leaving to Overview and coming back, and browser history must restore the
aperture it left. O7 opens and closes the trust and preferences drawers and
checks that changing the start view actually changes what a bare URL does. O8
searches from the front door and follows the first component result into the
workbench. O9 checks that the front door says what the system is: the headline
matches `identity.statement` in the sidecar character for character, there is
one form-factor chip per record, and opening the first chip reveals the file its
evidence names; when the sidecar carries no identity the rule records that and
checks nothing it cannot check. O10 measures that no `data-se="stat"` count tile
is inside the first viewport of the Portrait posture, at both sizes, and that
the demoted counts are still one click away.

**`tours.spec.ts`** plays every tour end to end with no sampling, because tours
are few by nature and a tour is what somebody is shown when they are being
convinced the tool works. A step's target is realised only when all of the
beacon's selection, the node's selected class, the node being fully inside the
canvas, and the drill level agree. It also checks the entry's count, the list
against the manifest in authored order with step counts and stale markers, the
evidence link, Previous back to the start, a jump to the middle step, and both
exit routes.

## Two apertures, one suite

The viewer has a front door (Overview) and a workbench, over one projection.
Every workbench spec navigates with `mode=workbench` explicitly, added by
`gotoState`/`navigateState` unless the caller passes `mode`, so the six specs
written about the workbench test the aperture they were written for instead of
spending their first assertion discovering they are somewhere else. The reset
probe's "start" is the workbench root, and it checks the aperture first: a
journey that silently dropped the reader back to the front door would leave
every other field trivially clean.

`overview.spec.ts` owns the transition, and is the only spec that navigates
without a mode, because "what does a reader get when they name nothing" is its
first question.

Two affordances moved rather than disappeared. The opening band that used to
carry the AI summary, the coverage badge, the gaps banner and the findings,
supply chain and tours entries now sits behind `showLegacyOpeningBands`, a
hard-coded `false` in `App.tsx`, and those entry points live in the workbench
trust strip instead. The entry-point table therefore accepts any of a row's
ids: the predicate it encodes is "the data warrants a way in", not "this
particular banner exists". Requiring the old id would report a deliberate
relocation as a regression, which is the harness telling the product where to
put its own buttons.

## Parameters in, discovery out

Discovery stays mechanical: every expectation still comes from the manifest and
every presence from the DOM. The parameters file adds the one fact neither can
carry, and the run writes back the one fact neither consumer should have to
re-derive.

### `CRAWL_PARAMS`: what this build has switched off

```json
{
  "declared_off": ["lens:design", "entry:tours", "surface:review"],
  "notes": "design signals are off for this deployment pending the D5 rework"
}
```

Naming a feature here INVERTS its claim rather than silencing it. Absence stops
being a finding; PRESENCE becomes one, reported as
`surface.declared_off_present`, because a build that still offers a feature its
own parameters say is off is not the build the parameters describe. Coverage
annotations end with `declared off by params: ...`, so a reading of the run
always says which expectations were suspended and why.

Without this, the only way to stop a deliberately disabled lens reporting as a
defect on every run is to edit a spec, which is how a suite stops being
adaptive. A missing file named by `CRAWL_PARAMS` is a hard error rather than an
empty set: silently proceeding would turn every declared-off feature back into
a finding and the run would read as a regression in the product.

Token vocabulary:

| Token | Means |
|---|---|
| `lens:<id>` | a lens id, as the switcher publishes it |
| `entry:<name>` | an entry point, its test id without the `-entry` suffix |
| `surface:<name>` | one of findings, supply-chain, inventory, review, tours, help, search, trust, preferences |

### `discovery.json`: what this build exposes

Written into the run directory beside `run.json`. It is the machine-readable
inventory an orchestrator reads instead of running the suite again and parsing
prose: which entry points were found present and absent against which
predicate, the lenses offered against the lenses expected, the tour ids with
their step counts and stale flags, the question route ids with their
availability, the portrait cards, and the sample sizes each budgeted sweep
actually used.

Discoveries are separate from findings on purpose. A finding says something is
wrong; a discovery says what is there, whether or not anything is wrong with
it. Both ride on annotations, so a case that fails still contributes what it had
already learned before the assertion threw.

## Speed

Playwright is fast, and a slow suite means the suite is being used badly rather
than that the work is large. Four things keep it honest:

- **Two workers, one per project.** The projects are independent browsers over
  one static file server, which is what a file server is for. Not
  `fullyParallel`: cases within a project share a page and a recorder, and
  several deliberately reason about what the previous navigation left behind.
  This is unrelated to the control plane's serial guard, which is about not
  running two heavy jobs at once.
- **A five-second action timeout.** In the bounded specs a timeout IS the
  finding, and waiting fifteen seconds to learn something knowable in five is
  minutes of nothing happening across a run with a dozen such findings. Not a
  correctness trade: every wait is still Node-enforced, and a control that
  genuinely needs longer than five seconds to become clickable is a finding
  worth reporting rather than one worth waiting out.
- **Warm navigation everywhere the claim allows.** A cold load re-parses the
  whole projection. Only three places need one, because arriving from outside is
  the claim: reachability by URL, J6's reload, and O1's bare-URL boot.
  Everywhere else a warm move proves the same thing for the cost of a render.
- **Polls at 100ms.** `expect.poll` backs off by default (100, 250, 500, 1000),
  so a condition true at 120ms is not observed until 350ms. Fixed 100ms
  intervals with unchanged ceilings speed up the pass case without changing what
  counts as a finding.

`run.json` carries `slowest`: the eight longest cases with their durations, so
"which cases cost the time" is answerable from the record rather than a
stopwatch.

## The contract-presence gate

A build that predates this contract publishes no `nav-state`, and every test
that reads it would then fail for one reason, dozens of times, drowning
whatever the run was meant to find. The contract is probed once per worker on
the first boot, and there are THREE states, not two:

| What the build publishes | What runs |
|---|---|
| `nav-state` | everything |
| `tree-navigator` but no beacon | the legacy reachability, depth and search specs; everything that reads the beacon skips |
| neither | nothing |

The third state is the one that matters and was found the hard way. Run against
a build that carries only `lens-select` and React Flow's own ids, the two-state
gate skipped the 41 beacon-dependent cases correctly and then reported
**fourteen failures** from the legacy specs, all of them the same sixty-second
wait for a tree that build does not publish. Fourteen findings about one
absence, reading as fourteen defects in a product that has none of them.

Each state has its own annotation, carried into the reporter's `coverage`:

```
contract.absent: this build does not publish nav-state; only the legacy
reachability, depth and search specs ran

contract.absent: this build publishes neither nav-state nor tree-navigator,
so no spec in this suite could run against it
```

The run's status is then **limited**: not failed, because nothing that ran was
wrong, and never green, because a board that says "passed" over a fraction of
the suite is asserting something it has no evidence for. A run where every case
skipped is `limited` outright, with no passes and no failures to misread.

## What this has actually found

Kept as a record of what the suite is for, and of which defects only appeared at
real scale. Every one of these was invisible to the 1,600 unit tests and to the
data linter, because all of them are about whether a reader can reach and use
what the data holds.

**Found and fixed:**

1. **A deep link never revealed its component in the tree.** You arrived at a
   detail panel with no row in the navigator: no sense of place, no siblings, no
   way further down without restarting from the top. `expandedIds` was local to
   `TreeNavigator` and nothing reacted to `selectedComponentId`, so URL, search
   and graph-click selection all left the tree untouched.
2. **The same fix was incomplete, and only private large-repository validation corpus showed it.** Revealing the
   ancestor chain was not enough for components under an "Internal Components"
   folder, because `collectOtherComponents` puts a component in a group and
   never recurses into its children. At depth 5 the thing in the group is an
   ANCESTOR, so matching only the selected id left eleven `extensions/`
   components with no row at all. It passed on this repo because our tree is
   shallow enough that the selected component usually is the grouped one.
3. **The Files tab rendered blank** for a component with zero files instead of
   saying so. A blank panel and a broken panel look identical, and that
   ambiguity teaches people to distrust every empty surface in the product.
4. **The Rules lens hung the browser indefinitely on private large-repository validation corpus.** Isolating panel
   load from graph load found it: 3,745 rules under one owner render in 636 ms,
   while 335 rules under 194 owners never finish. `getLensGraph` never applied
   the node budget the viewer already had, so the lens handed elk 194 nodes and
   2,892 edges. Bounding nodes alone was not enough, since the kept nodes carry
   the edges with them; edges are the real driver. Now bounded centrally, so no
   lens can do this again. Full private large-repository validation corpus Rules lens: 1.5 s.

**Open, from the first run of the new specs against the enriched UnaMentis iOS
projection (168 components, 4 tours):**

5. **Every tour narrates components the diagram never shows.** Fifty step
   realisations across four tours failed the same way: the step selects its
   target and the narration describes it, while the level the reader is looking
   at has grouped that component into `__agg__unamentis__module` and renders no
   node for it. `navigateToTourTarget` drills to the parent and selects the
   child; nothing reconciles that with the hero filter's decision about what the
   level shows. This is the defect the extension was commissioned to find.
6. **A tour's evidence link does not open the code.** "Show me the code" is one
   of the five documented Tours questions, and clicking `</> KBQuestion.swift:1`
   leaves the reader on the owning component's OVERVIEW tab. `openFileDeepLink`
   marks the file inside the Files tab, but only the cold-URL route seeds
   `tab=files` (useUrlSync does it; the in-app call does not), so the file is
   marked on a tab nobody is looking at.
7. **Home leaves the old context's panel on screen.** `navigateToBreadcrumb(-1)`
   clears `drillLevel`, the breadcrumbs and `selectedComponentId`, but not
   `detailItem` or `activePanel`. So the beacon reports nothing selected while
   the detail panel from the journey is still up. Verbatim the owner's named
   defect class: go back to the start and something from the old context is
   still in force.
8. **The Rules lens's windowed list is laid out to the wrong row height.**
   `RULE_ROW_HEIGHT` is 56 while rules render 68 to 174px tall, and VirtualList
   positions rows absolutely at 56px intervals. Rows overlap by up to 118px, and
   a hit test at the first row's centre point returns the row BELOW it, so the
   first rule of every window cannot be clicked. Fires on any subject with more
   than 150 rules in one kind group.
9. **The entry strip can leave the content area no room.** On this projection
   the AI summary banner alone is 410px of a 1280x720 viewport, and with the
   coverage, findings, supply chain and tours bars the graph and every lens
   panel are left 103px. On an iPhone 13 the content area is 390x0 and the
   canvas never becomes visible at all. `App.tsx` already names the risk
   ("Starting that summary expanded can reduce the actual graph to zero height
   on an ordinary laptop viewport") but only collapses the summary for a
   non-public evaluation sidecar, which this projection does not carry.
10. **Escape does not close the detail panel**, while the help dialog's own
    shortcut list advertises Esc as "Close panels / search". Every Escape
    listener in the app is registered only while its own overlay is open.
11. **A deep link's `tab` param outlives everything else.** After Home, Escape
    and a pane click clear the drill, the selection and the lens, `?tab=` is
    still in the URL, because the URL writer preserves it verbatim and nothing
    clears it when the panel closes.

**Found by the front-door pass, on the review projection (165 components):**

12. **The Rules lens is not offered although the projection carries 698 rules.**
    NOT a product defect, and the record is kept because the harness was wrong
    in the direction that costs the most: it reported a deliberately withheld
    lens as missing, three times over, on every run. `hasRules` is not
    `rules.length > 0`; it is "at least one rule whose confidence is `certain`",
    and the comment in `lenses/rules.ts` says why: "A system-wide lens must not
    be built entirely from shape-matched branches." All 698 rules in this
    projection are `inferred`, so the product is right to hide the lens.
    `contract.ts` now mirrors the real gate, and `discovery.json` records both
    lists side by side either way.
13. **Search from the front door does not go anywhere.** The Overview mounts its
    own `SearchOverlay`, and choosing a component result calls
    `navigateToComponent`, which never touches `experienceMode`. The reader is
    left on the Overview with a selection they cannot see.
14. **Crossing into the workbench writes no history entry.** `useUrlSync` pushes
    only when the DRILL changes and replaces otherwise, so a mode change
    replaces. Measured as `history.length` unchanged across the handoff, which
    is the mechanism rather than a guess about where "back" landed.
15. **A tour's evidence link still lands on the Overview tab**, unchanged from
    the first pass and now reported with the tab it landed on.

**Three harness lessons from this pass, all paid for:**

- **A wait written on one viewport describes that viewport.** `gotoState`
  waited for the tree navigator to be VISIBLE. Below the `lg` breakpoint the
  tree is a drawer, so every mobile case timed out for sixty seconds against a
  healthy page. Twelve red cases, one cause, none of them the product's.
- **A boot signal must not be a layout default.** The wait then anchored on the
  tree being ATTACHED, and the workbench moved to a "focused" density that
  starts the sidebar collapsed, so `TreeNavigator` stopped being rendered at
  all. The wait was really a wait on a layout decision, and when the decision
  moved the harness reported the product as dead. It anchors on the beacon now,
  which is always mounted in both apertures and whose whole job is to say the
  app is up.
- **A test that finds nothing must not pass.** The mobile tab sweep reported
  "0/165 components checked" and went green, because on a phone the detail panel
  lives in a bottom sheet that renders no content at its default "peek" snap.
  `discovery.json` is partly a response to this: a sample size in the record is
  a number somebody can look at, where a coverage sentence nobody reads is not.

**Two lessons about the harness itself, both paid for:**

- **Every wait must be one Playwright enforces from Node.** The lens sweep first
  used `page.evaluate` to ask whether the page had settled. That takes an
  argument rather than options, so it carries no timeout, and on a main thread
  spinning at 100% CPU it never returns. The budget existed and never fired, and
  the suite hung exactly as the product had. A harness that hangs instead of
  reporting is the same failure as a product that hangs instead of rendering.
- **Do not pick the biggest thing as your representative.** The lens sweep chose
  the component with the most files, which on private large-repository validation corpus is `src/vs/workbench`, so
  every lens failed for the same unrelated reason and the sweep proved nothing
  about lenses. It now uses an upper-middle component, and the pathological end
  gets its own test where being the worst case is the point.

**A third harness lesson, from the first run of the mobile project:**

- **A wait written on one viewport describes that viewport.** `gotoState`
  waited for the tree navigator to be VISIBLE. Below the `lg` breakpoint the
  tree is a drawer behind the header's hamburger, so it is in the DOM and
  correctly invisible, and every single mobile case timed out after sixty
  seconds against a perfectly healthy page. Twelve red cases, one cause, none
  of them the product's. The wait now asks for ATTACHED, which is also the
  honest expression of what it was ever waiting on: the data has arrived and
  rendered, not this particular element is on screen.

**Three harness lessons from the third fix pass, all paid for:**

- **A read of a page in motion has to be one read.** `search.spec.ts` decided
  where a result had landed with six locator calls: count the symbol view, count
  the file view, count the component panel, then read the attribute off whichever
  answered. A symbol result changes the page twice by design, because
  `navigateToComponent` mounts the component panel and the detail fetch then
  swaps it for the symbol view, so a count that found the component panel was
  followed by a `getAttribute` on an element the swap had already removed. That
  read waited out the whole ten-second poll and was recorded as
  `search.unusable`, "the search UI could not be driven at all", for three runs.
  The landing is read in one `page.evaluate` now: one round trip, one DOM state.
  The lesson generalises to any helper that asks two questions of a live page.
- **A count is not a wait.** The deep-link reveal check read
  `tree-node` count once and called a row missing if it was zero, while the
  reveal is an effect that expands the ancestor chain after the tree mounts.
  It polls from Node with a three-second budget now and records how long the
  slowest row took, because a row that takes two seconds and a row that never
  comes are different facts. On the review projection the slowest row appears in
  37 ms, and `reach.deep_link_hidden` has not recurred.
- **A precondition a case manufactures has to be derived from the subject.**
  The snap-into-view case panned by a fixed 900 by 700 pixels to get a node
  off-screen, and on a subject whose whole graph fits it silently self-skipped.
  It pans 1.5 canvases now, derived from the pane box and split into drags that
  stay inside it, and if every node still fits it zooms in with the app's own
  control until one does not. Nodes larger than the canvas are excluded, since
  nothing can bring those fully into view. Every remaining skip pushes a
  coverage annotation naming why, so a skip is a fact in the record rather than
  a silent hole.

**A fourth harness lesson, from the tours and graph occlusion checks:**

- **An occlusion read taken during the pan animation reports a covering that a
  reader never sees.** `describeOcclusion` read `document.elementFromPoint`
  once, right after the in-view wait passed. Selecting a tour stop or a
  component triggers ArchitectureGraph's 400ms `fitView` pan, and a read taken
  150ms in finds the node still travelling under the minimap or a panel that
  will not be there once it settles. `waitForUnoccluded` now polls the same
  point every 100ms for up to two seconds, same shape as `waitForInView`, and
  only reports the finding if the node is still covered when the ceiling
  passes. Every read of where a node is must poll until the engine's animation
  has settled.

## What it does not cover yet

Named so the gaps are decisions rather than oversights:

- **Node positions.** The graph spec asserts behaviour (which nodes belong at a
  level, selection, drill, snap-into-view) and never geometry beyond "is this
  node inside the canvas". Where elk puts things is layout output and would be
  brittle to assert.
- **Panel ranking.** Each lens panel ranks and groups its own rows
  (`CAP_KIND_ORDER`, `rankEntitiesByAccess`, `RULE_KIND_ORDER`,
  `DESIGN_KIND_ORDER`, `rankEntryFlows`). The crawl checks that every row the
  panel shows is one the data names, in both directions, but not the order it
  shows them in: predicting that would mean reimplementing five ranking
  functions out here, where their drift would be invisible. Ranking is a
  judgement question and belongs to the AI plan.
- **The status tab.** Its rule turns on `component.live_status`, which a static
  projection never carries and a live deployment adds at runtime, so the data
  cannot settle it and `surfaces.spec.ts` asserts nothing about it either way.
- **Review mode and annotations.** `review-summary` publishes its root and the
  beacon lists the review overlay, but no journey enters review mode yet.
- **Visual regression.** Deliberately out of scope. Screenshots are captured on
  failure only, as evidence, never as an assertion.
