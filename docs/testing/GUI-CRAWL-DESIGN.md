# The adaptive GUI crawl: design authority

Designed 2026-09-01 from owner direction. This document is the design authority
for `viewer/tests/crawl/`, superseding the design notes in that directory's
README where the two disagree. The README stays the operator's manual (how to
run it, the selector table, what it has found); this is the statement of what
the suite must prove and why.

## Where everything lives

| Question | Where |
|---|---|
| What must the suite prove, and why | this document, including the two addenda at the end |
| How to run it, the selector table, what it has found | `viewer/tests/crawl/README.md` |
| How it fits beside the linter and the AI-operated plan, and when it runs | `docs/testing/DETERMINISTIC-CHECKS.md`, section 2 |
| The first run and the fix iterations that followed | `docs/testing/RUN-2026-09-01-adaptive-crawl.md` |
| One-line invocation for a session | `.claude/skills/crawl/SKILL.md` (`/crawl`) |
| The control-plane job and its flags | `scripts/control.py` (`run crawl --slug`, `--url`, `--profile`, `--no-mobile`, `--dry-run`) |
| The report renderer | `scripts/crawl-report.py` |
| The specs, fixtures, expectation model, reporter | `viewer/tests/crawl/` |
| The app-side contract | `data-testid="nav-state"` in `viewer/src/App.tsx` and the attributes listed below |
| Run records and discovery output | `.testboard/runs/<stamp>-crawl-<subject>/` (`run.json`, `discovery.json`, `REPORT.md`; local, never committed) |

## What the owner asked for

A test that runs every time a significant amount of work lands, and every time
a new subject is taken through a full pass, and that finds what is broken. It
cannot be a fixed script over a fixed interface: the viewer shows different
lenses, entry points, tabs and tours depending on the projection it loads, and
features will be switchable off. So the test has to recognise what is present,
trust that the set of present features is the version of the interface under
test, and then pursue every present path to a reasonable depth, checking that
each behaves. Two named examples of the class of defect it exists to find: you
drill into a context, go back to the start, and something from the old context
is still in force; and a guided tour whose diagram does not snap to and
highlight each stop.

## What already existed, and the decision

Two GUI harnesses were already in the repo.

- `viewer/tests/gui/` is the AI-operated vector plan: about a hundred
  hand-walked cases against the dogfood dataset, run by a Sonnet agent, hours
  per run. It judges whether a surface reads correctly to a person. It is
  dataset-specific by construction (it names components) and cannot adapt.
- `viewer/tests/crawl/` is the deterministic Playwright crawl: every
  expectation derived from the manifest at run time, so it already adapts to
  any subject. It proves reachability (URL and tree), per-tab honesty, lens
  entry, search routing, and the heaviest component. It has found real defects
  at scale and records its own mistakes.

The crawl is the right foundation and is extended rather than replaced. What
it lacked is exactly the owner's list: it never asserted anything about
navigation state after a path, never touched the graph canvas, never played a
tour, never compared which entry points are present against what the data
says should be present, and ran one desktop viewport. This design adds those
as new spec files under the same fixtures, reporter and run record, so one
command still runs everything and the testboard shows one run.

## Principles (additions to the crawl's existing rules)

1. **Discovery from both ends, presence in both directions.** The data says
   what must be present; the DOM says what is present. An entry point the data
   warrants but the DOM lacks is a finding. An entry point the DOM shows but
   the data does not warrant is also a finding. Presence is never assumed from
   a list in the test.
2. **Trust presence, verify behaviour.** Once a feature is present it is
   pursued to a stated depth: opened, used, stepped through, closed. The test
   never decides a present feature "does not matter".
3. **Every path ends with a reset probe.** After each journey the suite
   returns to the start the way a reader would (Home, Escape) and asserts that
   nothing of the journey survives: no drill, no selection, no lens-scoped
   selection, no tour, no overlay, a bare URL. Residue is reported by name as a
   context leak, naming the journey that left it.
4. **State is asserted twice.** The app publishes its navigation state on a
   beacon element (below). Every state assertion checks the beacon AND the
   visible expression of that state (a panel present or absent, a node
   carrying the selected class, a URL parameter). A beacon that says "reset"
   while a tour panel is still on screen is a failure, so the beacon cannot
   drift from the truth unnoticed.
5. **The existing rules stand.** Findings are recorded before assertions.
   Per-item loops record and continue. Every wait is Node-enforced. No silent
   caps. Honest-empty over blank. Nothing may scream. Do not pick the biggest
   thing as the representative.

## The selector contract additions

All additive `data-*` attributes; no ARIA roles are added (the README records
why). Each is a contract: removing one must break the crawl loudly.

### The navigation state beacon

One always-mounted, visually hidden element in `App.tsx`:

```
data-testid="nav-state"
  data-drill        drillLevel or ""
  data-selected     selectedComponentId or ""
  data-lens         lens id
  data-flow         flowEntryId or ""
  data-flow-step    flowStep as a number, "" when no flow
  data-capability   selectedCapabilityId or ""
  data-entity       selectedEntityId or ""
  data-rule         selectedRuleId or ""
  data-finding      selectedDesignFindingId or ""
  data-tour         activeTourId or ""
  data-tour-step    tourStep as a number, "" when no tour
  data-panel        activePanel or ""
  data-detail       "component" | "file" | "symbol" | ""
  data-overlays     comma-joined list of open overlays from: search, findings,
                    supply-chain, inventory, tours, help, admin, review
  data-blast        "true" when blastRadiusMode is on, else ""
```

The beacon reads store state only. It exists for tests and for anyone
debugging the app in devtools; it renders nothing visible.

### Other additions

| Attribute | On | Carries |
|---|---|---|
| `data-testid="drill-home"` | the header Home button | present only when drilled |
| `data-testid="breadcrumb-item"` | each breadcrumb in the graph header | `data-component-id`, `data-current` |
| `.react-flow__node[data-id]` | graph nodes (React Flow native) | the component or aggregate id; class `selected` when selected |
| `.react-flow` | the canvas container (React Flow native) | bounding box for in-view checks |
| `data-testid="graph-node"` | the ComponentNode card | `data-component-id`, `data-selected`, `data-has-children` |
| `data-testid="aggregate-node"` | the AggregateNode card | `data-aggregate-id`, `data-expanded` |
| `data-testid="tour-list-item"` (exists) | | gains `data-tour-id`, `data-step-count`, `data-stale` |
| `data-testid="tour-step-panel"` (exists) | | gains `data-tour-id`, `data-step`, `data-step-count` |
| `data-testid="tour-step-item"` | each row in the step panel's jump list | `data-step`, `data-current` |
| `data-testid="tour-exit"` | the exit button in the step panel | |
| `data-testid="tours-list-overlay"` | the tour list dialog root | |
| `data-testid="help-button"` | the fixed ? button | |
| `data-testid="help-overlay"` | the welcome or help dialog root | `data-kind`: welcome or help |
| `data-testid="search-button"` | the header search button | |
| `data-testid="findings-surface"` | FindingsSurface dialog root | |
| `data-testid="supply-chain-surface"` | SupplyChainSurface dialog root | |
| `data-testid="inventory-panel"` | InventoryPanel dialog root | |
| `data-testid="review-summary"` | ReviewSummary panel root | |
| `data-testid="lens-row"` | a selectable row in Capability, Data, Rules and Design panels | `data-lens`, `data-row-id`, `data-selected` |
| `data-testid="flow-entry"` | an entry flow row in FlowPanel | `data-flow-id` |
| `data-testid="flow-next"`, `"flow-prev"`, `"flow-exit"` | FlowPanel follow controls | |
| `data-testid="lens-panel"` | the mounted lens panel root | `data-lens` |
| `data-testid="entry-bar"` | wrapper around the entry strip (coverage, gaps, findings, supply chain, tours) | |

The two React Flow class selectors join `.react-flow__node` as the only
permitted class selectors; they are framework-published identity, not styling.

## The expectation model additions (`contract.ts`)

Derived from the projection, never typed into a spec:

- `tours`: the manifest's tour list verbatim (id, title, steps, provenance).
- `entryPoints`: the predicate table below, evaluated against the manifest.
- `lensesExpected`: which lens ids the data warrants, mirroring each lens's
  `isAvailable` (structure and inventory always; activity iff `activity`;
  capability iff `capabilities` non-empty; data iff `data_entities` non-empty;
  rules iff `rules` non-empty; flow iff `hasFlowData`, reimplemented from
  `lenses/flow.ts` over the manifest; design iff `design_signals`). Maturity
  gating by channel is honoured: the contract reads the registry's maturity
  table only through a small exported list that the build can import without
  importing the app, `viewer/src/utils/lensMaturity.ts`, a TS constant with no
  React, store or DOM dependency. It sits under `utils/` rather than `lenses/`
  because `lenses/` holds one lens definition file per lens and nothing else.
  If the channel gates a lens off, it is expected absent.
- `pathToDeepest`: the component chain from a root to a deepest component,
  for the drill journey.
- `loadDetail(id)`: the detail shard for a component, fetched through the
  Playwright request context against the base URL, so it works for a local
  serve root and for a remote origin alike.
- `firstRow(lens)`: the first selectable row id the data offers for each
  lens-scoped selection (first capability id, first entity id, first rule id,
  first design finding id, first entry flow).

Entry point predicate table:

| Entry | Present iff |
|---|---|
| `tours-entry` | `tours.length > 0`; its text names that count |
| `findings-entry` | `findings` non-empty |
| `supply-chain-entry` | `supply_chain` present |
| `gaps-banner` | `gaps` present and non-empty |
| `coverage-badge` | `coverage` present |
| `lens-select` | more than one lens expected |
| `search-button` | always |
| `help-button` | always |

## Remote targets

`CRAWL_BASE_URL` may name a remote origin (the published demo) with no
`CRAWL_SERVE_DIR`. A Playwright `globalSetup` then downloads what the contract
needs (`architecture/manifest.json`, `architecture/publication.json` when it
answers 200, `architecture/search/manifest.json` and its first shard) into
`viewer/tests/crawl/results/remote-data/<host>/architecture/` and sets
`CRAWL_DATA_DIR` for the workers. Detail shards are fetched on demand through
the request context. The default 404 allowlist is unchanged. The reporter
records the remote base URL and the downloaded manifest's version stamp, so a
run against the deployed site is distinguishable from a local one on the board.

## The new specs

Each is a file beside the existing four. Every test tags itself `@desktop`,
`@mobile`, or both.

### `surfaces.spec.ts` (presence in both directions, then one level of use)

1. For every row of the entry point table: present iff the predicate says so.
   Mismatches are findings `surface.missing` and `surface.unwarranted`.
2. Lens switcher options equal `lensesExpected` as a set. Findings
   `surface.lens_missing`, `surface.lens_unwarranted`.
3. For every present entry: open it, assert its surface root is visible with
   at least `MIN_PANEL_TEXT` characters of text, assert the beacon's overlays
   list names it, press Escape, assert the surface is gone and the overlays
   list is empty, and assert the beacon's navigation fields are unchanged from
   before the open. Findings `surface.dead_entry`, `surface.blank_surface`,
   `surface.wont_close`, `surface.open_changed_nav`.
4. Detail tab presence on a sample of up to 12 components (depth-stratified
   through `sampleComponents`): read each component's detail shard; the tab
   set on screen must be exactly what the data warrants for the tabs whose
   rule the shard settles (ai iff `ai_enhance`; capabilities iff the component
   appears in `capabilities`; data iff it appears in `data_entities` or
   `entity_access`; testing iff the shard carries testing data; actions iff it
   carries actions; docs per the app's own rule, which the builder reads from
   `DetailPanel.tsx` and records in the spec's header comment). Tabs whose
   rule the data cannot settle are not asserted, and the spec says which.
   Findings `surface.tab_missing`, `surface.tab_unwarranted`.

### `graph.spec.ts` (the canvas behaves)

1. Root level: every rendered `.react-flow__node` id is a root component id, a
   child of the single root when the projection has one root, or an aggregate
   id; at least one node renders. Finding `graph.invented_node`.
2. Click a node: beacon selected equals its id, the node carries the selected
   class, the detail panel shows that id. Click the empty pane: selected is
   "" and no detail panel. Findings `graph.click_dead`, `graph.pane_no_clear`.
3. Snap into view: choose a component at the current level whose node is NOT
   fully inside the `.react-flow` box (pan the canvas away if every node is
   visible), select it from the tree row, and assert that within 2 seconds its
   node is fully inside the box. Finding `graph.no_snap`. The app's rule is
   that an already visible selection is not re-centred; the spec respects it
   by starting from an off-screen node.
4. Drill by double-click on a node with children: beacon drill equals its id,
   the URL carries `drill=<id>`, the breadcrumb items end with it, the Home
   button is present, and every rendered node id is one of its children or an
   aggregate. Home: drill "", no breadcrumbs, no Home button, URL bare.
   Findings `graph.drill_dead`, `graph.drill_wrong_children`, `graph.home_dead`.

### `journeys.spec.ts` (paths, then a reset probe)

A journey is a function that performs a path and returns a label. After every
journey the shared `resetProbe(page, label)` runs: click Home if present,
press Escape twice, wait for the beacon to settle, then assert the reset state
(beacon drill, selected, flow, capability, entity, rule, finding, tour all "";
lens structure; overlays ""; no detail panel; no tour step panel; no dialog
roots; URL search empty or carrying only `data`). Residue is finding
`journey.context_leak` with the journey label and the residual fields.

- J1 Drill to the bottom: follow `pathToDeepest` by double-clicking each node
  in turn (falling back to the tree row when the node is aggregated or off
  budget), assert the beacon's drill and the URL after each hop, then Home.
- J2 Back and forward: after J1's descent, press browser back once per hop and
  assert the beacon drill and URL step back exactly one level each time; then
  forward once and assert it re-applies. Findings `journey.back_wrong`,
  `journey.forward_wrong`.
- J3 Lens round trip preserves selection: select a component, switch to every
  expected lens and back to structure; the beacon's selected must never
  change (invariant I12). Finding `journey.lens_dropped_selection`.
- J4 Lens-scoped selection, once per available lens with rows (capability,
  data, rules, design, flow): enter the lens, click the first `lens-row` or
  `flow-entry`; assert the beacon field is set, the owning component is
  selected, and the URL carries the lens's parameter. For flow, additionally
  step next and prev and assert `flow-step` and the URL `step`. Switch back to
  structure: the URL must carry none of `capability`, `entity`, `rule`,
  `finding`, `flow`, `step`. Findings `journey.lens_row_dead`,
  `journey.lens_param_leak`.
- J5 Overlay hygiene: with a component selected and a drill in place, open
  each present overlay and close it with Escape; the beacon's navigation
  fields must be unchanged after each. Finding `journey.overlay_changed_nav`.
- J6 Cold reload restores: compose a deep link (drill, component, tab, and a
  non-default lens when available), load it cold, read the beacon; reload;
  the beacon must be identical. Finding `journey.reload_drift`.

### `tours.spec.ts` (the guided tour snaps and highlights)

Skipped with a coverage annotation when the projection carries no tours.

1. The entry names the count; the list overlay shows exactly the manifest's
   tours in authored order with matching step counts and stale markers.
   Findings `tour.entry_count`, `tour.list_mismatch`.
2. Play every tour end to end (tours are few by nature; no sampling):
   - start: step panel present with the tour id, progress reads "Step 1 of N",
     step 0's target is realised (below).
   - for each Next: the progress text advances, the target is realised, the
     recorder is clean.
   - a target is realised when: for a component-id target, the beacon's
     selected equals it, the graph node carries the selected class, the node
     is fully inside the canvas box within 2 seconds, and the beacon's drill is
     the target's parent (or "" for a top-level target); for a file or symbol
     target, a `file-detail` or `symbol-detail` is shown whose path or id
     matches. Findings `tour.step_target_missed`, `tour.step_not_in_view`,
     `tour.step_drill_wrong`, `tour.progress_wrong`.
   - evidence: on one step per tour with evidence, click the evidence link;
     a `file-detail` must show that file, and the step panel must still be
     present with the same step. Finding `tour.evidence_dead`.
   - Previous from the last step returns to the first, one step at a time.
   - jump: click the step item for the middle step; the panel and target
     follow. Finding `tour.jump_dead`.
   - exit via the exit button: the step panel is gone, the beacon's tour is
     "", and the last selection is left in place (the store's documented
     behaviour). Then the reset probe. Finding `tour.exit_leak`.
   - one tour additionally exits via Escape.

### Mobile

A second Playwright project, `mobile`, using `devices["iPhone 13"]` (390x844,
touch). It runs the tests tagged `@mobile`: reachability's boot test, all of
surfaces, tours, and journeys J1, J5, J6, and graph's click and drill tests.
The detail panel lives in a bottom sheet on this viewport; the selector
contract is identical, so no spec branches on viewport. `CRAWL_MOBILE=0`
disables the project. Mobile failures are real failures, reported under their
project name in the run record.

## Profiles and how it is run

Two profiles, set by `CRAWL_PROFILE`:

- `quick` (default): `CRAWL_MAX_COMPONENTS=40`, both projects. The bounded
  specs (surfaces, graph, journeys, tours) always run in full; only the
  exhaustive sweeps (reachability by URL, depth per tab) are budgeted. Target:
  under 15 minutes on a 170-component subject.
- `full`: no budget. Hour-scale on VS Code, as the sweeps already are.

Entry points, all through the control plane so runs are serial and land on
the testboard:

```bash
# after significant work, against a locally assembled subject
python3 scripts/control.py run assemble --slug unamentis-ios --projection <dir>
python3 scripts/control.py run crawl --slug unamentis-ios            # quick
python3 scripts/control.py run crawl --slug unamentis-ios --profile full

# against the published site
python3 scripts/control.py run crawl --url https://<host>            # quick
```

`scripts/crawl-report.py <run-dir>` renders `run.json` into `REPORT.md` in the
run directory: one plain paragraph first (what is solid, what is broken,
whether it is demoable), then findings grouped by rule with instance counts
and examples, then coverage lines, then per-case status. The banned phrases
from the GUI strategy apply.

## When it runs (the cadence)

Recorded here, in `DETERMINISTIC-CHECKS.md`, in the demo program document, and
in project memory so future sessions apply it unprompted:

1. After any significant change to the viewer, the store, the lenses, or the
   projection schema: `quick` against the current canonical subject before the
   work is called done. A PR that changes viewer behaviour reports the run id.
2. After every new subject's full pass (analyze, assemble, and again after
   enrichment, since enrichment adds tours and AI surfaces): `quick` at least,
   `full` before publication.
3. Not in CI. It needs a served projection and a browser; `gui-plan-check`
   remains the only CI-side GUI check.

## Division of labour for building and running

- Design: this document (Fable).
- Construction: Opus, from this document, on the `wt/adaptive-crawl`
  worktree, with the crawl README updated to the new selector table and the
  new specs, and `DETERMINISTIC-CHECKS.md` updated for the cadence.
- Running and digesting: Sonnet, through the control plane, producing the run
  digest via `crawl-report.py`. The runner does not interpret.
- Analysis of what the run found: Fable.

## What the first run is for

The first run against the enriched UnaMentis iOS projection (168 components,
4 tours) is a shake-out of both the product and the harness. Harness defects
are fixed before anything is reported as a product defect. Product findings
are reported exactly as found, clustered by probable cause, never rounded up.

## Addendum 2026-09-01: the Overview front door and the mode transition

Written the same day, after `main` moved past this branch's base with the
front-door work (`docs/front-door-prototype/DESIGN-PROPOSAL.md`,
`docs/remediation/FRONT-DOOR-EXECUTION-PLAN.md`). The viewer now has two
apertures over one projection: **Overview**, the default landing surface, and
the **workbench**, which is everything the sections above describe. The
transition between them is specified as lossless: subject, question, lens,
semantic level, selected object and tour step are route state and survive the
switch in both directions. That claim is exactly the class this suite exists
to check, so the addendum folds it in.

### Facts the specs rely on (from `store.ts`, `useUrlSync.ts`, `SystemOverview.tsx`)

- A fresh origin boots into Overview (`startView` default). Any workbench
  parameter on the URL (`lens`, `component`, `drill`, `file`, `flow`,
  `capability`, `entity`, `rule`, `finding`) or `mode=workbench` boots into
  the workbench. `mode=overview` forces Overview. Back/forward restore the
  mode from the URL.
- The mode a reader last used is remembered in localStorage under
  `arch-experience-preferences-v1` when `rememberNavigation` is on. The crawl
  clears storage per run (it already dismisses the welcome overlay the same
  way), so every run starts from the product default.
- Overview reads `architecture/orientation.json`: `question_routes` (each with
  `available` and a `target` naming a lens, a surface or a tour), `portrait`
  nodes (each with `stable_targets`, component ids), `launch_targets`, and
  `trust`. Assembly generates the sidecar when the projection lacks it.
- Overview has three directions (portrait, questions, atlas), a search button,
  a trust button, a preferences button, portrait cards that hand off to the
  workbench with a component selected, question routes that hand off with a
  lens or surface or tour, and "Open detailed workspace". The workbench has a
  return control to Overview and a semantic level toggle (system, domain,
  component) that is URL state (`level`).
- Two new lenses exist: `support` (iff `support.json`) and `security` (iff
  `security.json`). They join `lensesExpected`.

### Selector contract additions

| Attribute | On | Carries |
|---|---|---|
| beacon `nav-state` gains | | `data-mode` (overview or workbench), `data-level`, `data-direction`, `data-handoff` (overviewHandoff), and `trust`, `preferences` join the `data-overlays` vocabulary |
| `data-testid="system-overview"` | the Overview root | `data-direction` |
| `data-testid="overview-direction"` | each direction button | `data-direction`, `data-selected` |
| `data-testid="question-route"` | each question route button | `data-route-id`, `data-available` |
| `data-testid="portrait-card"` | each portrait node card | `data-node-id`, `data-target` (first stable target) |
| `data-testid="open-workbench"` | "Open detailed workspace" and "Full map" | |
| `data-testid="open-overview"` | the workbench's return-to-Overview control(s) | |
| `data-testid="trust-drawer"` | TrustDrawer root | |
| `data-testid="preferences-drawer"` | ViewerPreferences root | |
| `data-testid="trust-strip"` | WorkbenchTrustStrip root | |

### Expectation model additions

`orientation`: the sidecar parsed verbatim when present (fetched through the
request context, like detail shards), else null with a coverage annotation
saying the Overview is the generated fallback and route availability cannot
be checked against data. `lensesExpected` gains support and security.

### How the existing specs change

Every workbench spec loads with `mode=workbench` explicitly (a parameter added
by `gotoState`/`navigateState` unless the caller passes `mode`), so the
reachability, depth, search, graph, journeys and tours specs test the aperture
they were written for, and the Overview is tested by its own spec. The reset
probe's "start" remains the workbench root: the probe asserts `data-mode` is
workbench and the workbench fields are clear. A separate probe (`O5` below)
covers returning to the front door.

### `overview.spec.ts` (the front door), desktop and mobile

- O1 Boot: a bare URL on a cleared origin lands on Overview (`data-mode`
  overview, `system-overview` present, no tree, no graph). Finding
  `overview.boot_wrong_mode`.
- O2 Directions: each of the three direction buttons renders its section with
  at least `MIN_PANEL_TEXT` characters and no recorder problems. Finding
  `overview.direction_blank`.
- O3 Routes match data: the set of `question-route` ids equals
  `orientation.question_routes` ids, and each `data-available` equals the
  sidecar's flag. Findings `overview.route_missing`,
  `overview.route_availability`.
- O4 Every available route hands off correctly: click it, assert
  `data-mode` workbench, and then per target kind: lens target sets
  `data-lens` (and `data-level` when the target names one) and the URL carries
  `lens`; surface target opens that surface (findings surface visible, in the
  overlays list); tour target starts that tour (`tour-step-panel` with the
  tour id). Then return to Overview through `open-overview`. Findings
  `overview.route_dead`, `overview.route_wrong_target`. Unavailable routes
  are disabled and clicking one changes nothing.
- O5 Portrait cards hand off to the named component: for every card, click,
  assert workbench with `data-selected` equal to the card's target, the
  component's node selected and in view (the graph spec's in-view rule),
  return to Overview. Finding `overview.card_dead`.
- O6 Lossless round trip: in the workbench, drill, select a component, pick a
  non-default lens where available, and set level domain; go to Overview via
  `open-overview`; assert Overview shows; go back via `open-workbench`; the
  beacon's drill, selected, lens and level must equal what they were.
  Browser back from the workbench after a handoff returns to Overview
  (`data-mode` overview) and forward returns to the same workbench state.
  Findings `overview.roundtrip_lost_state`, `overview.back_wrong_mode`.
- O7 Trust and preferences: each opens (drawer visible, overlays list names
  it) and closes on Escape with nav unchanged. Preferences: toggle the start
  view to workbench, reload a bare URL, assert workbench; toggle it back,
  reload, assert Overview. Finding `overview.preference_not_honoured`.
- O8 Search from Overview: the search button opens the overlay; choosing the
  first component result lands in the workbench with that component selected.
  Finding `overview.search_dead`.

### Contract-presence gate

A build that predates this contract (no `nav-state` element after boot) must
not fail forty cases for one reason. `fixtures.ts` checks for the beacon once
per worker after the first boot; if it is absent, every test that needs it is
skipped with one annotation, `contract.absent: this build does not publish
nav-state; only the legacy reachability, depth and search specs ran`, and the
reporter carries the same line in `coverage`. The run is then reported as
limited, never as green.

### The canonical dataset for the first run

`docs/front-door-prototype/CANONICAL-UNAMENTIS-IOS-DEMO.md` names the
canonical UnaMentis iOS projection (168 components, 4 tours, 458
relationships) and the assemble command that derives the Overview sidecars
beside it. The first run uses exactly that. The build on port 5173 that the
owner pointed at serves a 165-component review variant of the same subject
from another worktree; it is crawled second, through `--url`, and any
difference between the two runs is reported as a difference in data, not in
the product, unless evidence says otherwise.

## Addendum 2026-09-01 (later): parameters in, discovery out, and speed

Owner direction the same evening, recorded so the split of labour is explicit.

**Discovery is mechanical; the model is not in the loop at run time.** The
projection and the rendered DOM are the parameter source for every spec. What
a model does is decide to run, read the result, and judge. Where a human or an
orchestrator knows something the data cannot say, it is passed in as
parameters rather than decided by the runner:

- `CRAWL_PARAMS=<json>` names features deliberately switched off for this
  version (`declared_off`: `lens:<id>`, `entry:<name>`, `surface:<name>`).
  A declared-off feature is expected absent; its presence is the finding
  `surface.declared_off_present`. Coverage annotations say what was declared.
- Every run writes `discovery.json` beside `run.json`: what the version
  exposed (entry points present and absent per predicate, lenses offered,
  tours and step counts, question routes and availability, sample sizes).
  An orchestrator reads this instead of re-deriving it, and a later run can
  diff two versions' exposure.

**Speed is a requirement, not a nicety.** Playwright is fast; a long run means
the harness is doing something a reader never does. Standing rules: cold
loads only where cold arrival is the claim (URL sweep, cold reload, first
boot); warm in-app navigation everywhere else; projects run concurrently;
bounded specs use a short action timeout because there a timeout is the
finding; every wait polls with a tight ceiling and stays Node-enforced. Each
run reports its slowest cases and the reason, and the quick profile's target
on a 170-component subject is single-digit minutes.
