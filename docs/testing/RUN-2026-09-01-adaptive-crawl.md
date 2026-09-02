# Adaptive GUI crawl, first run: 2026-09-01

What was built, what it was pointed at, what it found, and what is still open.
Written so nothing here assumes you watched. Design authority is
`GUI-CRAWL-DESIGN.md`; the operator's manual is `viewer/tests/crawl/README.md`.

## The short version

Final state, 2026-09-02, after three fix iterations and one follow-up: the
quick and full profiles both pass 56 of 56 cases on desktop and phone with no
findings, and the viewer unit suite stands at 627 tests. The text below is the
record as it was written at each stage; read "Fix iterations" for what changed.

The crawl now discovers what a build exposes and pursues every present path
to a stated depth, on desktop and on a phone, in 5.6 minutes for the quick
profile. Pointed at the owner's build (the static server on port 5173, the
165-component UnaMentis iOS review projection, viewer at main), it found six
front-end defects that would hit a first-time visitor, none of them about
data or enrichment. Two of the four defects the pre-Overview code had are
gone on main. The product is not ready to send a link until the ranked list
below is fixed.

    deep run:   39 of 55 cases passed, 16 failed; desktop 27/11, mobile 12/5
    remote run: 55 skipped, status LIMITED (the served build predates the
                selector contract; the gate refused to report green)
    exploratory pass: desktop and mobile, 76 steps each, screenshots kept
                locally, two visual confirmations below

## The target

- Code: `main` at e89cd55 (the 5173 server runs d32877f, two whitespace and
  merge commits behind it, same viewer).
- Data: the projection the 5173 server serves, symlinked read-only into this
  worktree's serve root. Manifest SHA-256 verified equal to what the server
  returns. The three Overview sidecars already existed there and were used
  verbatim.
- The deep run drives a build of the same code with the additive `data-*`
  contract attributes present. The remote run drives the served build as is.

## What a visitor hits, ranked by damage

1. **Back leaves the site.** Clicking a question on the Overview switches to
   the workbench without adding a history entry (`history.length` stays 2),
   so the browser's Back button leaves the demo entirely. Finding
   `overview.back_wrong_mode`; reproduced by hand in `repro-back.mjs`.
   Cause: `useUrlSync` pushes history only on drill changes; the mode change
   is a replace.
2. **Home does not clear the old context.** After Home, the canvas shows the
   root while the detail panel still shows the previous component, and the
   beacon reads `selected=""` with `panel="detail"`. Findings
   `journey.context_leak` (5) and `tour.exit_leak` (4). Cause:
   `navigateToBreadcrumb(-1)` clears drill, breadcrumbs and selection but not
   `detailItem` or `activePanel`. A `tab` URL parameter also survives.
3. **The Rules lens is missing.** The projection carries 698 rules and
   `hasRules` is true, yet the lens switcher offers seven lenses without it.
   Findings `surface.lens_missing` (2), `journey.lens_row_dead`,
   `journey.lens_dropped_selection`. Cause not yet identified.
4. **Search from the Overview never leaves the Overview.** Picking a result
   selects the component in the store but the Overview stays on screen.
   Finding `overview.search_dead` (2). Cause: `SearchOverlay` calls
   `navigateToComponent`, which never sets `experienceMode`.
5. **Tour evidence links land on the wrong tab.** "Show me the code" opens
   the owning component's Overview tab, not Files. Finding
   `tour.evidence_dead` (8). Cause: only the cold-URL path seeds `tab=files`;
   the in-app `openFileDeepLink` does not.
6. **The root node's hover preview covers the header.** On arriving in the
   workbench from a question, the pointer sits on the single centred node and
   its preview popup renders over the lens switcher, the level toggle,
   Review, and part of Search and the New/Classic switcher; those controls
   cannot be clicked while it is up. Found by the exploratory pass (every
   header click timed out on obstruction; screenshot d09 shows the popup over
   the header). Not yet a crawl finding; a graph spec case should assert that
   no popup intersects the header.

Also recorded, lower damage: Escape is advertised in the help dialog as
"Close panels / search" but does not close the detail panel
(`journey.advertised_shortcut_dead`); on a phone, double-click drill fails at
two hops because the content area is 320 px tall (`journey.drill_hop`, 2);
three symbol search results land on the owning component rather than the
symbol (`search.wrong_landing`, needs owner judgement on the intended
contract); one deep link does not reveal its tree row
(`reach.deep_link_hidden`).

## What the Overview work fixed

Compared with the run against the pre-Overview code:

| Defect | On main |
|---|---|
| Tour steps selected a component the canvas never drew (50 instances) | Gone. 4 tours, 25 steps, every target drawn, selected and in view |
| AI summary banner squeezed the graph to 103 px (desktop) and 0 px (phone) | Gone on desktop; phone content area now 320 px, still too small to drill |
| Evidence link on the wrong tab | Still present |
| Home leaves the old panel | Still present |
| Escape does not close the panel | Still present |
| Rules rows misclick above 150 rules | Unverifiable: the lens is not offered |

## What was built

| Thing | What it is |
|---|---|
| `GUI-CRAWL-DESIGN.md` | Design authority with two addenda (Overview mode; parameters, discovery, speed) |
| `nav-state` beacon and `data-*` contract | The app publishes its navigation state and identity attributes; additive, no ARIA roles |
| `surfaces`, `graph`, `journeys`, `tours`, `overview` specs | Presence in both directions, canvas behaviour, reset probes, full tour playback, the front door |
| Mobile project | iPhone 13, runs concurrently with desktop |
| Remote target and contract-presence gate | `--url` mirrors the manifest; a build without the contract is reported LIMITED, never green |
| `CRAWL_PARAMS` and `discovery.json` | Features declared off are expected absent; every run writes what the build exposed |
| `control.py run crawl --url / --profile / --no-mobile`, `crawl-report.py`, `/crawl` skill | One-line invocation, blunt REPORT.md, cadence recorded |

## Harness lessons paid for this time

- Waiting for the tree to be visible timed out every mobile case against a
  healthy page: the tree is a hidden drawer on a phone. Wait for attachment.
- Warm navigation asked the tree whether the app had booted; the tree is now
  collapsed by default, so every "warm" move was silently a cold load.
- A bare `goto("/")` now lands on the Overview, so a recovery reload put the
  search sweep in the wrong aperture for every target after a failure.
- Passing `--reporter` on the command line replaces the testboard reporter,
  so intermediate runs wrote no run record.
- A two-state contract gate reported 14 legacy failures that were one
  sixty-second wait for a tree the build does not publish. Three states now.
- Speed: 17 minutes to 5.6 by running the two viewports concurrently, using
  5 s action timeouts where a timeout is the finding, and warm navigation
  everywhere cold arrival is not the claim.

## Environment note

Node 26 on this machine makes the global `localStorage` throw unless
`--localstorage-file` is set, which fails 86 viewer unit tests at baseline
and makes `theme.test.tsx` flaky across workers. CI pins Node 22. Run unit
tests locally with `NODE_OPTIONS="--localstorage-file=$TMPDIR/x.json"`.

## Open, needing a decision

1. Fix the six ranked defects. All are viewer-side and small except the
   missing Rules lens, whose cause is unknown. Recommended order is the list
   above. Each fix should rerun the quick profile before it is called done.
2. Symbol search landing: the crawl accepts either the symbol view or the
   owning component while the shard resolves; three targets landed on the
   component and stayed there. Decide the contract and the spec follows.
3. Commit. Everything is uncommitted on `wt/adaptive-crawl`, merged onto
   main e89cd55, lint and 582 unit tests green.

## Fix iterations, 2026-09-02

Three iterations against the same target, each verified by the quick crawl and
diffed against the previous run. No finding rule appeared that was not already
known.

| Run | Cases | Distinct findings | Wall time |
|---|---|---|---|
| Baseline (main, before fixes) | 39 of 55 passed | 19 | 5.6 min |
| Iteration 1 | 52 of 56 passed | 6 | 2.8 min |
| Iteration 2 | 54 of 56 passed | 2 | 1.1 min |
| Iteration 3, quick (a) | 55 of 56 passed | 2 | 2.1 min |
| Iteration 3, quick (b) | 56 of 56 passed | 0 | 0.9 min |
| Iteration 3, full | 56 of 56 passed | 0 | 1.3 min |

The two quick rows are the same code twice in a row. The difference is the
phone-only drill flake below, which costs the run 83 seconds of retries when it
fires.

Unit tests: 582 to 597 to 611 to 623, lint and build clean throughout.

**Iteration 1 (the six ranked defects).** Back returns to the Overview (the
mode change now pushes a history entry, suppressed during the cold-URL
restore). Home, drill up and drill in clear the detail panel and active panel
through one shared helper that respects review mode, and a stale `tab`
parameter is dropped with the selection. Escape closes the detail panel when
no overlay, drawer or tour owns the key. Choosing a search result from the
Overview enters the workbench. In-app file deep links (tour evidence) seed
the Files tab the way a cold file link does. The node hover preview is
clamped inside the canvas, flips below the node at the top edge, and closes
on pointer movement away; a new crawl case fails if a preview ever covers the
header again. Harness: the Rules lens expectation now mirrors the product's
gate (at least one rule with certain confidence), so the "missing lens" is
retired as a harness error.

**Iteration 2 (the phone, and residue).** The trust strip is one scrolling
row; the drill hint no longer overlaps the breadcrumb bar and says
"double-tap" on coarse pointers; the empty peek sheet is gone when nothing is
selected; the legacy-interface notice is one row on a phone. Content area at
390x664 went from 326 px (49 percent) to 414 px (62 percent). Selections made
for the reader (search result, tree row, evidence link, lens row) open the
detail sheet to half height; a direct node tap keeps the peek behaviour; a
plain tour step deliberately does not reveal, because doing so left 142 px of
canvas during a tour. The Files tab had a zero-height basis inside the sheet
and now has a minimum height, which was the whole remaining cause of evidence
links that showed no file. The tour panel is a docked strip on phones, capped
at 45 percent of the viewport, with narration and step list behind a toggle
that stays in the DOM. Home also clears lens-scoped selections and flow
follow state. Harness: an occlusion check, `graph.node_occluded`, requires a
tour or graph target to be uncovered at its centre; it caught a 23-instance
regression from a first attempt at the hint placement before that attempt was
reverted.

**Still open after two iterations**

- `search.unusable` (2 instances, symbol targets that change every run).
  Cause found and not fixed: every detail shard load calls the full search
  index rebuild, so after some forty shards the page stalls and a symbol pick
  times out. The fix is incremental indexing in `utils/search.ts`, a real
  piece of work rather than a patch.
- `reach.deep_link_hidden` (1, intermittent, depth-4 component): the tree
  row for a deep link is sometimes not revealed when read. The check reads a
  count without a Node-enforced poll, so it may be a harness race; unresolved.
- One desktop tour stop lands under the React Flow minimap
  (`provider-seam` step 3). The minimap was not moved.

**Iteration 3 (the last three, and one wrong diagnosis).** Both of the two
remaining findings are gone, and both turned out to be the harness rather than
the product.

`search.unusable` was not the index rebuild. The trace says the sweep decided
where a result had landed with six separate locator calls, and a symbol result
changes the page twice by design: `navigateToComponent` mounts the component
panel, then the detail fetch resolves and `showDetail` swaps it for the symbol
view. A count that found the component panel was followed by a `getAttribute` on
an element the swap had already removed, which waited out the ten-second poll
and was reported as "the search UI could not be driven at all". The landing is
now read in one `page.evaluate`. Measured before believing the old diagnosis:
across a thirty-target sweep the longest main-thread block was 962 ms and the
slowest landing was 4 ms, so the page was never stalling. The search spec has
since passed five runs running, and the case went from 22.7 s to 14.0 s.

The index work was done anyway, because a rebuild per detail load is wrong on
any large subject even when it is not this defect. `addToSearchIndex` appends
documents to the live Fuse index instead of rebuilding it, and falls back to a
rebuild only where appending would be wrong: nothing indexed yet, a component
reloading with different entries, or an incoming entry that would change a
document already indexed. Forty detail loads now cost zero full rebuilds, the
index version still bumps whenever documents are actually added so the overlay's
memo recomputes (issue #116), and a shard that loads twice adds nothing, bumps
nothing and rebuilds nothing. Three new tests hold that, including the rebuild
bound, which is asserted through a counter exported for the tests.

`reach.deep_link_hidden` was a race in the read. The check counted tree rows
once, while the reveal is an effect that expands the ancestor chain after the
tree mounts. It polls from Node with a three-second budget now and records the
slowest row, which on this projection appears in 37 ms. Five consecutive runs of
that case, plus every run since, pass. It was the harness, not
`TreeNavigator`, so nothing in the reveal path was touched.

The pan-to-selection test in `ArchitectureGraph` is obstruction-aware: the
selected node's rect is checked against the canvas and against the minimap, the
controls, the tour step panel, the drill hint and the two mobile sheets, and a
node that intersects any of them is centred. The geometry is a pure helper,
`isUnobstructed`, with eight unit tests. Two rules are kept intact. A node that
is inside the canvas and unobstructed still does not move (comprehension-study
S5: the second click of a double-click must not land on a moved node), and a
node the reader picked ON THE CANVAS is never moved either, obstructed or not,
which is what stops the new test from reintroducing S5 for any node sitting over
the controls or the drill hint. The `provider-seam` step 3 overlap could not be
reproduced on the current build at 1024, 1280 or 1920 wide, with the obstruction
test on or off, so the change ships on its unit tests rather than on a
before-and-after of that instance.

The snap-into-view case no longer self-skips. It pans 1.5 canvases, derived from
the pane box and split into drags that stay inside it, and if every node still
fits it zooms in with the app's own control until one does not. The full run
records `snap-into-view checked on root (panned 1.5 canvases away)`, where before
it skipped. Every remaining skip in that case pushes a coverage annotation
naming why.

**Open after three iterations (closed below)**

- `journey.drill_hop` and the reset residue behind it, on the phone only,
  intermittent: roughly one quick run in two, the J1 double-tap drill fails at
  every hop and the drill then survives Home. Proven pre-existing by an A/B, the
  same failure occurs with the obstruction test compiled out, and a clicked
  node moves 22 px after the first tap either way, which is more than the 5 px
  the double-tap detector allows. The cause is the canvas resize when the detail
  sheet opens, not the pan effect. The same intermittency shows up once as
  `tour.exit_leak` with the identical "drill survived the reset" residue.
- Nothing else. The full profile, which sweeps all 165 components with no
  budget, recorded no findings at all in 1.3 minutes, and the quick profile
  records none in the runs where the phone flake does not fire.

**Closed since (the phone drill flake).** `journey.drill_hop` was a side effect
of iteration 2: once the empty peek sheet was removed, the first tap on a node
became the thing that mounted the detail sheet, and mounting it reserved 15vh of
canvas, which relaid the graph and slid the just-tapped node 22 px sideways,
past the 5 px slop the double-tap detector allows. The peek snap now reserves
nothing and overlays the bottom of the canvas instead, so at 390x664 the canvas
measures 414 px both before and after the first tap and the node moves 0 px,
where without the fix it went 414 px to 325 px and the node moved 22 px. Half
and full still reserve, the 62 percent content area with nothing selected is
untouched, and the mobile J1 case passed ten runs out of ten followed by a clean
56 of 56 quick run.

## Engine audit, 2026-09-02

The viewer is React Flow over ELK, and those two own layout, viewport,
positioning and hit testing. This pass went back over the fixes above and moved
everything that had reimplemented one of those onto the engine's own API. Two
crawl runs of 56 of 56 with no findings, the mobile J1 case five for five, lint
clean, 632 unit tests, build clean.

**Pan to selection.** Was: the node's screen rectangle rebuilt by hand from
`viewport.x/y/zoom` and the container rect, a hand-written rectangle
containment and overlap test in `utils/graphVisibility`, and `setCenter` on a
midpoint computed from a guessed 280x140 when the node's measured size was
missing. Now: the canvas and each overlay are converted to flow coordinates
with `screenToFlowPosition`, the node is tested against them with
`isNodeIntersecting` (`partially: false` for "wholly inside the canvas",
`partially: true` for "touches an overlay"), the node's bounds come from the
instance form of `getNodesBounds`, which reports what React Flow measured in
the DOM, and the move is `fitView({ nodes: [selected], padding, minZoom: zoom,
maxZoom: zoom, duration })` with the zoom pinned to the zoom already on screen,
so it pans and never scales. Both behavioural rules are unchanged: a visible,
unobstructed selection is never re-centred (S5), and a node picked on the
canvas is never moved even when obstructed.

Guessing a size is now a bug rather than a fallback. The first version of this
refactor read `measured` off the node object in React state, which a fresh
layout can leave undefined for a render or two, and treated that as "not
visible": every direct tap on a phone then re-framed the level and slid the node
out from under the second tap, and the mobile J1 case failed at every hop, twice
in a row. Reading the bounds from React Flow's node lookup instead fixed it, and
where there is no measurement yet the view is now left exactly where it is,
because the next layout re-runs the effect anyway.

**Node hover preview.** Was: a `position: fixed` portal into `document.body` at
coordinates worked out from the trigger's client rect, clamped by hand to the
`.react-flow` box. Now: React Flow's `NodeToolbar` carries it, so the anchor,
the offset, the "does not scale with zoom" and the portal are the engine's, and
the card follows the node through a pan instead of going stale. `NodeToolbar`
has no notion of the canvas edges (`getNodeToolbarTransform` is the node rect,
the viewport, the position, the offset and the alignment and nothing else), and
`align` moves the card by whole node and card widths, which cannot hold a 360px
card inside a 390px phone canvas. So two residual decisions remain, both fed
from measured screen rects rather than from any viewport arithmetic: which
`Position` to hand `NodeToolbar` (Top, flipping to Bottom when there is no room
above, which is what keeps the popup off the header), and how far to slide the
card off centre to clear either side. `graph.preview_covers_header` still
passes, with the run recording a preview that actually opened.

**Drill hint and breadcrumb bar.** Both were already Panels at `top-left` and
`top-right`, which is the engine placing them; the iteration 2 fix caps the
breadcrumb Panel's width and hides the hint below `sm` at depth rather than
repositioning either. Panel placement alone cannot solve the overlap, because
two Panels are independent absolutely positioned boxes and React Flow arbitrates
nothing between them. The 15rem cap checks out against the 15px margin React
Flow gives every Panel. Left as it is.

**The double-tap drill detector stays, and here is why.** Measured on the
review projection at the crawl's own 1280x720 desktop viewport, after every fix
on this branch: selecting a node still moves it 160px at depth 2 (0px at the
root, 3px at depth 1), because the detail panel opening resizes the canvas,
which re-budgets and re-lays out the level. That is more than the 5px the
detector allows and it is the S5 cause itself, still present and outside the pan
effect's control. The native `onNodeDoubleClick` is wired and does fire, so the
two paths overlap, but removing the custom detector would leave the 160px case
depending on how fast the reader's second click is. Report only, as instructed.

**Everything else that computes geometry.** `readViewport` in `utils/snapZoom`
does viewport arithmetic by hand and is kept: it centres on the priority node
and then slides back inside the content bounds, which `getViewportForBounds`
cannot express. `fitZoomNow` already uses `getNodesBounds` and
`getViewportForBounds` and was left alone. `computeOptimalHandles` in
`utils/layout` picks a handle pair from relative node positions, which React
Flow has no primitive for; kept. `collectCanvasObstructions` reads a
`getBoundingClientRect` per overlay, which is the one thing with no engine
answer, and is now the only hand geometry left in the visibility path.
`ElkRoutedEdge` decides whether a label fits the canvas by transforming the
label box with `viewport.x/y/zoom` by hand; it predates this branch and was left
alone, but it is the one remaining reimplementation of the viewport transform in
the viewer and should move to `flowToScreenPosition`.
