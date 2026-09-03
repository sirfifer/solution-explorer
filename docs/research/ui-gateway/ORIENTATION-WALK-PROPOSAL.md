# The orientation walk: spec, plan and handoff

Status: PLAN, written 2026-09-03 for owner approval and handoff to an
executing session. Nothing implemented. Evidence taken from the viewer on
`wt/ui-gateway-option1` (commit f02ab67, the option 1 front door), the crawl
harness under `viewer/tests/crawl`, and the demo gate run records under
`docs/testing/`.

This one document is the assessment (section 2), the contract (sections 4
and 5), the task plan (section 6) and the handoff (section 7). Where a
task's text and section 4 disagree, section 4 wins; report the
disagreement rather than resolving it silently.

## 1. The question

After the option 1 front door, does a first-time visitor still need a
guided introduction, and which kind: none, a generic one about the product,
a solution-specific one, or a hybrid? The owner's criterion: very short, no
wall of reading, hops around and points at the key things, and makes sure
the base idea lands.

## 2. Assessment

### 2.1 What exists today

**The old welcome guide is still in the code and still fires, but never
where the public looks.** `viewer/src/components/HelpSystem.tsx` carries a
five-slide centered modal titled "Welcome to Architecture Visualizer" (the
pre-rename product name). It describes hovering nodes for documentation and
the detail panel's tabs. It never mentions the Overview, the Workbench,
lenses, the trust ledger, themes or walkthroughs. Since the Overview became
the first-run guide, the modal is suppressed on the Overview handoff and on
any bundle carrying `publication.json`. It shows only to a person who opens
a Workbench deep link in a fresh browser. The demo gate run record lists
this as P6, decision left to the owner.

**The Help dialog reuses the same copy.** Its Guide tab is the five slides.
Its About tab says "Architecture Visualizer", lists a feature set that is
half the product, and says the analyzer core uses only the Python standard
library. This is what the `?` button opens on the demo today.

**A solution-specific guide already exists, twice.** The Overview's "What
are you trying to understand?" routes assemble an answer from the evidence
and hand off into the Workbench, some with a guided path attached. Inside
the Workbench, the dataset's walkthroughs (`architecture.tours`) play
code-anchored steps in the docked `TourPlayer`. Both adapt to the subject
with no per-subject authoring in the viewer.

**Why the old guide rotted.** Its copy lives in a component with nothing
tying it to the surfaces it describes. A slide can say "hover for
documentation" long after hovering stopped being the mechanism, and no test
notices.

**What nothing says today.** The identity card says what the subject is to
a person. Nothing says what this site is to a person: a map drawn from the
source at one commit, where every statement links to the code it came
from, with two views of the same map. The header labels the subject
("System under study"), the footer's "About this map" is a collapsed
disclosure on published bundles only, and the About tab is stale.

### 2.2 The four shapes

| Shape | Verdict | Why |
|---|---|---|
| None | No | The site never explains itself. The stale modal and About tab remain the only attempt, and they name the wrong product. |
| Generic slide carousel (the old one, refreshed) | No | Slides describe controls the reader cannot see while the modal covers them. It is the form people skip, and the form that rotted unnoticed. |
| Solution-specific wizard | No | Redundant with the question routes and the dataset walkthroughs, and it needs per-subject authoring or model spend for every new subject. |
| **Hybrid: fixed stops, spotlight on the live page, copy that names the subject** | **Adopted by this plan** | Pointing beats describing. The stop list is the same for every subject; the words interpolate the display name and facts the page already loaded. No authoring per subject, no model spend, and each stop anchors on a control the crawl contract asserts exists, so it cannot rot silently. |

## 3. Decisions this plan takes

These are defaults the executor does not re-litigate. The owner may
override any of them before dispatch (section 9).

1. **Name.** "Orientation walk" in code and documents. "Show me around" in
   the UI. Never "tour": the product, the crawl contract and the dataset
   schema all use "tour" for code-anchored walkthroughs.
2. **Invitation, never interruption.** A dismissible corner card on first
   visit. Only a click starts the walk. The walk never auto-starts.
3. **Eight stops, two legs, under sixty seconds.** Five on the Overview,
   three in the Workbench. The walk crosses into the Workbench itself and
   ends there with the way back in view.
4. **Shown on published bundles.** Publication is the audience. The
   `publication` suppression of the old modal is not carried over.
5. **The old modal and its storage key are deleted**, and the Help dialog
   is rewritten in the same change.
6. **Sequence.** Branch from `wt/ui-gateway-option1`, land after option 1
   merges. Not a gate for the VS Code demo going public unless the owner
   says so.

## 4. Specification

### 4.1 Vocabulary

- **Walk**: the whole guided sequence.
- **Stop**: one spotlighted control with its card.
- **Leg**: the stops on one surface (Overview or Workbench).
- **Invite**: the first-visit corner card that offers the walk.
- **Anchor**: the DOM element a stop spotlights, addressed by `data-testid`.
- **Highlight rect**: the part of the anchor the spotlight cuts out.

### 4.2 Files

| Path | Role |
|---|---|
| `viewer/src/orientation/stops.ts` | The stop table (section 4.3) and the context type. Pure data plus template functions. No React. |
| `viewer/src/orientation/model.ts` | Pure helpers: applicable stops for a viewport, first-visit decision from storage and URL, highlight rect geometry, card placement. Unit-tested without a DOM where possible. |
| `viewer/src/components/OrientationWalk.tsx` | The spotlight layer and card. |
| `viewer/src/components/OrientationInvite.tsx` | The first-visit card. |
| `viewer/src/store.ts` | State and actions (section 4.7). |
| `viewer/src/App.tsx` | Mounts both components, extends the nav-state beacon, adds two test ids. |
| `viewer/src/components/HelpSystem.tsx` | Modal deleted, Guide and About rewritten, "Show me around" added (section 4.9). |
| `viewer/src/components/SystemOverview.tsx`, `ExperienceSwitcher.tsx`, `ThemeSwitcher.tsx` | Test ids only (section 4.8). |
| `viewer/src/utils/tooltipCopy.ts` | One new group, `orientation` (section 4.11). |
| `viewer/tests/crawl/orientation.spec.ts` | New spec, rules W1 to W5 (section 5.2). |
| `viewer/tests/crawl/fixtures.ts`, `overview.spec.ts` | Storage seed and dialog roots (section 5.3). |
| `docs/testing/GUI-CRAWL-DESIGN.md` | Addendum for the new spec. |

No new dependency. No analyzer change. No projection change. No golden
refresh.

### 4.3 The stop table

Type, in `stops.ts`:

```ts
export type WalkSurface = "overview" | "workbench";
export type WalkViewport = "all" | "desktop" | "mobile"; // mobile is below the sm breakpoint, 640px
export type CardPlacement = "auto" | "top" | "bottom" | "left" | "right";

export interface WalkContext {
  displayName: string;               // the subject as the header shows it
  identitySummary: string | null;    // orientation.identity.summary, else statement, else null
  lensLabels: string[];              // labels of the lenses the dataset activates, in switcher order
  hasGuidedPaths: boolean;           // any question route carries a tour_id
  isMobile: boolean;                 // viewport below sm
  isMac: boolean;                    // for the search shortcut wording
}

export interface WalkStop {
  id: string;                        // stable, kebab-case; appears in the beacon and the crawl
  surface: WalkSurface;
  anchor: string;                    // a data-testid
  fallbackAnchor?: string;           // used when anchor is absent (identity null, control hidden)
  viewport: WalkViewport;
  placement: CardPlacement;
  heading: string;
  body: (ctx: WalkContext) => string;
}

export const WALK_STOPS: readonly WalkStop[];
```

The records, in order. Body copy is final unless the owner edits it; every
body is under twenty-five words, plain language, no dashes. `{name}` is
`ctx.displayName`.

| # | id | surface | anchor (fallback) | viewport | heading | body |
|---|---|---|---|---|---|---|
| 1 | `what-this-is` | overview | `identity-statement` (`overview-title`) | all | What this is | "A map of {name}, drawn from its source code at one recorded commit. Every statement here links to the code it came from." |
| 2 | `start-with-a-question` | overview | `question-routes` | all | Start with a question | "Pick what you want to understand. The site assembles an answer from the evidence." Append when `hasGuidedPaths`: " Some answers come with a guided walk through the code." |
| 3 | `two-views` | overview | `experience-switcher` | all | Two views of one map | "Overview tells the story. Workbench is the full interactive map with the code behind it. Switch any time without losing your place." |
| 4 | `how-much-was-read` | overview | `overview-trust-button` | desktop | How much was read | "The share of the code the analysis actually read, what it skipped, and why. Honesty is always one click away." |
| 5 | `your-tools` | overview | `header-tools` | all | Search, theme, preferences | "Search everything with {Cmd+K or Ctrl+K}. Change the theme, light or dark, and viewer preferences here." |
| 6 | `the-map` | workbench | `graph-frame` | all | The map | Desktop: "Click a box to read about it. Double-click to open it. Home returns to the top. The tree on the left lists the same things." Mobile: "Tap a box to read about it. Double-tap to open it. Home returns to the top." |
| 7 | `lenses` | workbench | `lens-select` | all | Lenses | "Each lens redraws the map for a purpose: {first three lens labels, lower case, joined with commas} and more. Your place is kept when you switch." With fewer than three labels, name what there is and drop "and more". |
| 8a | `if-you-get-lost` | workbench | `help-button` | desktop | If you get lost | "The ? button replays this walk and lists the keyboard shortcuts. Overview is one click away in the header." |
| 8b | `if-you-get-lost-mobile` | workbench | `more-menu` | mobile | If you get lost | "Help, preferences and review mode live under this menu. Help replays this walk. Overview is one tap away." |

Stop 4 is desktop only because the Overview header's trust button is hidden
below the `md` breakpoint (768px); the desktop rule for this stop is
therefore `min-width: 768px`, not 640px. Encode that as `viewport:
"desktop"` plus a per-stop `minWidth` override, or as a fourth viewport
value; the executor chooses and records it.

The step counter counts applicable stops only, so a phone shows "Step 3 of
7", never "3 of 8" with a gap.

### 4.4 Context

`WalkContext` is built in `OrientationWalk.tsx` from the store on every
render:

- `displayName`: the same value `App` passes to `SystemOverview`.
- `identitySummary`: `orientation.identity?.summary ?? orientation.identity?.statement ?? null`. Reserved for the Guide tab's first line; stop 1 does not repeat the statement it is pointing at.
- `lensLabels`: the labels of the lenses the switcher currently offers, from the same source `LensSwitcher` reads, so the copy never names a lens the reader cannot see.
- `hasGuidedPaths`: `orientation.question_routes.some((r) => r.target.tour_id)`.
- `isMobile`: `window.matchMedia("(max-width: 639px)")`, re-evaluated on resize, the way `tourPanelStartsExpanded` does it.
- `isMac`: `navigator.platform` starts with "Mac" (fall back to Ctrl wording).

### 4.5 Behaviour

**First visit.** On mount, the viewer decides whether to show the invite:

1. If the URL carries `orientation=start`, the walk starts immediately, no invite. Used by the crawl and by a presenter who wants the talk track.
2. Else if the URL carries `orientation=invite`, the invite shows regardless of storage.
3. Else if storage holds `arch-viz-orientation-v1` with any value, or the legacy `arch-viz-help-dismissed` key (a returning browser that dismissed the old guide is not nagged), nothing shows.
4. Else the invite shows.

The URL parameter is read once at mount, like `mode`, and is never written
back by `useUrlSync`.

Storage writes: `done` when the walk reaches Done, `dismissed` when the
invite is dismissed or the walk is exited early. Storage failures are
swallowed exactly as `saveExperiencePreferences` does; with no storage the
invite shows once per page load and no more (component state).

**The invite.** A small card, `data-testid="orientation-invite"`, fixed
bottom-right on desktop (above the `?` button: `bottom-14 right-4`), a
full-width docked strip at the bottom on mobile (`inset-x-0 bottom-0`).
Content: heading "New here?", one line "This map takes a minute to learn.
Let it show you around.", two buttons: "Show me around" (primary,
`data-testid="orientation-start"`) and "Not now"
(`data-testid="orientation-dismiss"`). No backdrop, no focus steal, nothing
dimmed. It renders on either surface, but never while any overlay in
`openOverlays` is open, and never while a dataset tour is active.

**Starting.** `startOrientation()`:

1. Closes every open overlay (search, findings, supply chain, inventory, tours list, help, trust, preferences, admin) and exits any active dataset tour, through the store's existing close actions.
2. Hides the invite.
3. If the current surface is the Workbench, switches to the Overview (`setExperienceMode("overview")`). The walk always begins at stop 1. Workbench state (selection, drill, lens) survives in the store, so a reader who arrived by deep link gets it back at the crossing.
4. Sets `orientationStep` to the first applicable stop.

**Stepping.** Next and Back move through applicable stops. Before rendering
a stop the component:

1. Ensures the surface: if `stop.surface !== experienceMode`, calls `setExperienceMode(stop.surface)` and waits one animation frame for the surface to mount.
2. Resolves the anchor: `[data-testid="<anchor>"]`, visible (non-zero rect, not `display:none`); else the fallback; else the stop is skipped with a console warning in dev builds and the beacon records the skip (`data-orientation-skipped`, comma-separated ids) so the crawl can see it.
3. Scrolls the anchor into view: `scrollIntoView({ block: "center", inline: "nearest" })` on the Overview (window scroll); no scroll in the Workbench (fixed layout), except the tree if it is the anchor's scroll container.
4. Measures after the next frame and positions the highlight and the card.
5. Moves focus to the card's primary button.

The crossing from stop 5 to stop 6 is the one place the surface changes.
Nothing in the walk selects a component, changes the lens, or opens a
panel. The walk is read-only over the page.

**Ending.** Done (on the last stop) and Escape both close the walk; Done
writes `done`, Escape and the backdrop click write `dismissed`. The walk
ends on the Workbench with the experience switcher visible in the header,
which is why stop 8's copy names the way back. Nothing else is left open.

**Replay.** "Show me around" in the Help dialog footer (replacing "Replay
welcome guide") closes Help and calls `startOrientation()`. The same button
sits in the Overview header's preferences drawer if there is a natural
row for it; otherwise Help alone is enough.

**Resize and scroll.** The highlight and card re-measure on window resize,
on scroll (capture phase, throttled to a frame), and when the viewport
crosses the mobile breakpoint. Crossing the breakpoint re-computes the
applicable stop list; if the current stop is no longer applicable the walk
moves to the nearest applicable stop.

### 4.6 The spotlight

**Layer.** One fixed element, `data-testid="orientation-walk"`, covering
the viewport at `z-[60]`: above the dataset tour panel (`z-40`) and Help
(`z-50`), below the trust and preferences drawers (`z-[70]`), which the
walk closes on start anyway. The layer intercepts pointer events; a click
on the backdrop exits the walk (consistent with the other overlays).

**Highlight.** A positioned box at the highlight rect, `pointer-events:
none`, rounded to 10px, with `box-shadow: 0 0 0 9999px rgba(0,0,0,0.55)`
producing the dimmed surround, plus a 2px ring in the theme's accent
(`--se-lumen-blue` or the cyan the front door already uses). The highlight
rect is the anchor rect expanded by 6px, intersected with the viewport,
then intersected with the area not covered by the card. For a large anchor
(the graph frame) that leaves the visible part above or beside the card;
the rule is that the highlight rect is never empty and never under the
card.

**Card.** `data-testid="orientation-card"`, `role="dialog"`,
`aria-labelledby` the heading, `aria-modal="true"`, width 20rem on
desktop, `max-w-[calc(100vw-2rem)]`. Contents, top to bottom: a small
eyebrow "Show me around" with the step counter
(`data-testid="orientation-progress"`, "Step 3 of 8"), the heading, the
body, and a row with Back (`orientation-back`, disabled on the first
stop), a spacer, Skip (`orientation-exit`, reads "Done" on the last stop
with test id `orientation-done`), and Next (`orientation-next`, hidden on
the last stop). Buttons meet the 44px mobile tap target the way the rest
of the header does (`min-h-11 sm:min-h-0`).

**Placement.** `auto` tries below the anchor, then above, then right, then
left, choosing the first that fits inside the viewport with a 12px margin;
the card is then clamped to the viewport. On mobile the card ignores
placement and docks to the bottom (`inset-x-0 bottom-0`, `max-h-[45vh]`,
rounded top corners), the same shape as the mobile dataset tour panel, and
the anchor is scrolled so it sits in the top 55% of the viewport where
scrolling is possible.

**Motion.** A 150ms opacity fade on the card and highlight under
`motion-safe:`; nothing else animates. Scrolling uses `behavior: "auto"`.

**Escape handling.** The walk registers its own keydown listener only while
open, like the other overlays, and it is the only Escape consumer while
open because every other overlay is closed at start.

### 4.7 Store and beacon

Additions to `store.ts`:

```ts
orientationOpen: boolean;          // the walk is on screen
orientationStep: number;           // index into the applicable stop list; 0 when closed
orientationInvite: boolean;        // the invite is on screen
startOrientation: () => void;
orientationNext: () => void;
orientationPrev: () => void;
exitOrientation: (reason: "done" | "dismissed") => void;
dismissOrientationInvite: () => void;
```

`welcomeOpen` and `setWelcomeOpen` are removed. `openOverlays` in
`App.tsx` gains `"orientation"` when `orientationOpen`. The nav-state
beacon gains:

- `data-orientation`: the current stop id, or `""`.
- `data-orientation-step`: the one-based counter as shown, or `""`.
- `data-orientation-invite`: `"true"` or `"false"`.
- `data-orientation-skipped`: comma-separated ids skipped this walk, or `""`.

The store keeps the applicable-stop computation out of itself: it stores
an index, and the component and `model.ts` own the mapping from index to
stop for the current viewport.

### 4.8 Test ids to add

| Element | File | id |
|---|---|---|
| Overview header title `<h1>` | `SystemOverview.tsx` | `overview-title` |
| The "What are you trying to understand?" `<section>` | `SystemOverview.tsx` | `question-routes` |
| Overview header trust button | `SystemOverview.tsx` | `overview-trust-button` |
| Right-hand tool group in the Overview header | `SystemOverview.tsx` | `header-tools` |
| Right-hand tool group in the Workbench header (the div holding search, lens, theme, preferences) | `App.tsx` | `header-tools` |
| Experience switcher wrapper | `ExperienceSwitcher.tsx` | `experience-switcher` |
| Theme switcher trigger button | `ThemeSwitcher.tsx` | `theme-switcher` |
| Preferences buttons (both headers) | `SystemOverview.tsx`, `App.tsx` | `preferences-button` |
| The graph frame (`data-se="graph-frame"`) | `App.tsx` | `graph-frame` |

`header-tools` appears once per surface and the two surfaces never mount
together, so the id is unique at any moment; the same is already true of
`search-button` and `open-workbench`. Existing ids are not renamed.

### 4.9 The Help dialog

- **The five-slide modal is deleted**, with `WELCOME_STEPS`,
  `HELP_DISMISSED_KEY`, the `welcomeOpen` wiring, and the
  `overviewHandoff`/`publication` gating that existed only for it. The
  `data-kind="welcome"` overlay no longer exists.
- **Guide tab** renders the stop table as a static list: the identity
  summary as an opening line when present, then each applicable stop's
  heading and body (rendered with the live context), in walk order, with
  the same icons or none. It is the same data, so it cannot drift from the
  walk.
- **Shortcuts tab** unchanged.
- **About tab** copy, replacing everything there:

  > SysCorpus maps a software system from its source code at one recorded
  > commit. Every statement on this site links to the files it came from,
  > and any statement a model helped phrase says so where it appears.
  >
  > The Overview tells the story of the system. The Workbench is the full
  > interactive map: components, files, symbols, relationships, and the
  > lenses that redraw the map for a purpose.
  >
  > Built with SysCorpus.

  The last line links where the existing "Built with SysCorpus" footer
  link points.
- **Footer button** reads "Show me around", `data-testid="orientation-replay"`,
  and starts the walk.

### 4.10 Accessibility

- The card is a dialog with a labelled heading; focus moves into it on
  every stop and is trapped inside it while open; Escape exits.
- The step counter is inside the dialog's label region so screen readers
  announce it with the heading.
- Every anchor is the actual control, so a reader who leaves the walk is
  looking at the thing that was described.
- Colour contrast of the card follows the existing `darkMode ? ... : ...`
  idiom; the accent ring is decorative and the card border carries the
  boundary.
- Reduced motion: only the `motion-safe:` fade.

### 4.11 Copy and styling

- All copy lives in `stops.ts` and one new `orientation` group in
  `TOOLTIP_COPY` (for the invite's buttons and the replay button's
  tooltip), so the tooltip presence sweep covers it.
- Styling follows the file idiom of `TourPlayer.tsx`: Tailwind classes,
  `darkMode` ternaries, zinc surfaces, the teal or cyan accent the front
  door uses. No new styling approach, no CSS file.
- Product name in UI copy is "SysCorpus". Never "Architecture Visualizer".
- No em dashes or en dashes anywhere, including comments and commit
  messages (`.claude/rules/writing-style.md`).

### 4.12 What is deleted

- The welcome modal and its slide data in `HelpSystem.tsx`.
- `welcomeOpen`, `setWelcomeOpen` in `store.ts` and their beacon and
  `openOverlays` entries.
- The `arch-viz-help-dismissed` key is no longer written. It is still read
  as "already dismissed" (section 4.5) so returning browsers are not
  nagged. The crawl fixture stops seeding it (section 5.3).

## 5. Verification

### 5.1 Unit tests (vitest)

- `stops.test.ts`: every `anchor` and `fallbackAnchor` in `WALK_STOPS`
  appears as a literal `data-testid="<id>"` in some file under
  `viewer/src` (read the sources with `fs`; no DOM). This is the
  rot-resistance test: rename or remove a control and the walk fails
  before it ships. Every body under twenty-five words for a fixture
  context; no dash characters in any heading or body.
- `model.test.ts`: applicable stops for desktop (8) and mobile (7); the
  first-visit decision table of section 4.5 (URL start, URL invite, new
  key, legacy key, nothing); highlight-rect geometry (expansion, viewport
  clip, card exclusion, never empty for a fixture where the card overlaps
  the anchor); placement fallback order.
- `orientationWalk.test.tsx`: renders with a fixture store on the
  Overview, starts, steps to the crossing, asserts `setExperienceMode`
  was called with `workbench`, steps to Done, asserts storage `done` and
  the beacon attributes.
- `helpSystem.test.tsx`: the Guide tab lists the stops; the About tab
  contains "SysCorpus" and not "Architecture Visualizer"; the replay
  button starts the walk.
- `TooltipSweep.test.tsx` passes with the new group.

Vitest has a known set of failing files from environment noise (86
localStorage cases at the time of UG-4). Capture the failing-file set
before and after; the after set must be a subset of the before set. Paste
both in the report.

### 5.2 Crawl rules, `orientation.spec.ts`

Tagged `@desktop` and `@mobile`. Runs with `?mode=overview`. Uses a
fresh context without the storage seed for W1, and `orientation=start`
for W2 to W5 so no rule depends on the invite.

- **W1, the invite.** A bare Overview URL in a context with no storage
  shows `orientation-invite` with `orientation-start` and
  `orientation-dismiss`; clicking dismiss removes it and a reload does not
  show it again. With the storage seed present, no invite renders.
- **W2, every stop lands.** With `orientation=start`, the walk opens at
  stop 1. For each Next until Done: the beacon's `data-orientation` equals
  the expected id for the viewport; the anchor element is visible and its
  rect intersects the viewport; the highlight rect is non-empty and at
  least 44px tall; the card's rect does not intersect the highlight rect;
  `data-orientation-skipped` is empty. Report per stop, the way the tours
  spec reports per step.
- **W3, the crossing and the ending.** The beacon reports `mode` overview
  through stop 5 and workbench from stop 6; Done leaves `data-orientation`
  empty, no `orientation-walk` or `orientation-card` in the DOM, the
  experience switcher visible, and the reset probe clean.
- **W4, Escape.** At stop 3, Escape closes the walk, the beacon is clean,
  storage reads `dismissed`, and the Overview is intact (question routes
  present, no dimming).
- **W5, replay.** Open Help on the Workbench, click `orientation-replay`;
  the walk opens at stop 1 on the Overview.

### 5.3 Harness changes

- `fixtures.ts`: the `crawlPage` seed sets `arch-viz-orientation-v1` to
  `"dismissed"` instead of the old key. `DIALOG_ROOTS` gains
  `orientation-walk` and `orientation-invite`.
- `overview.spec.ts`: the `dialogRoots` selector string used before the
  return-to-Overview click gains `orientation-walk`.
- `surfaces.spec.ts` and `journeys.spec.ts`: unchanged; `help-button`
  still opens `help-overlay`.
- `contract.ts`: unchanged. The walk is always offered, so no expectation
  row is needed; presence is asserted by W1 and W5.
- `docs/testing/GUI-CRAWL-DESIGN.md`: an addendum naming the new spec, the
  storage seed change, and rules W1 to W5.

### 5.4 Manual checks and screenshots

On both served bundles, in Atlas light and Signal dark, at 1440×900 and
390×844: one screenshot per stop plus the invite, saved under
`viewer/.ow-screens/<subject>/<theme>/<viewport>/<stop-id>.png` (listed in
the report; deleted by the reviewer if not gitignored). Confirm by eye
that no card covers its target, that copy fits without truncation, and
that the crossing does not flash the old Workbench state.

## 6. Tasks

One executing session. Commit per task on the branch, message starting
with the task id, never pushed, tree clean between tasks.

| id | task | depends on | est. tokens | verify |
|---|---|---|---|---|
| OW-0 | Worktree, branch, commit this document | none | 5k | `git log` shows the docs commit |
| OW-1 | The walk: stop table, model, store, spotlight, invite, test ids, unit tests | OW-0 | 150k | tsc, eslint, vitest |
| OW-2 | Help dialog rewrite and modal deletion | OW-1 | 40k | tsc, eslint, vitest |
| OW-3 | Crawl: fixture seed, dialog roots, `orientation.spec.ts`, design addendum | OW-1 | 60k | playwright, this spec only, both viewports |
| OW-4 | Integration: build, serve both subjects, full quick crawl both, screenshots, run record | OW-2, OW-3 | 70k | crawl green on both subjects |

Total executor estimate: about 330k tokens. Frontier review afterwards:
about 50k.

### OW-0: setup

```
cd /Volumes/Studio/dev/solution-explorer
git worktree add /Volumes/Studio/dev/.worktrees/solution-explorer--orientation-walk -b wt/orientation-walk wt/ui-gateway-option1
cd /Volumes/Studio/dev/.worktrees/solution-explorer--orientation-walk
cp /Volumes/Studio/dev/.worktrees/solution-explorer--relicense-polyform-nc/docs/research/ui-gateway/ORIENTATION-WALK-PROPOSAL.md docs/research/ui-gateway/
git add docs/research/ui-gateway/ORIENTATION-WALK-PROPOSAL.md
git commit -m "OW-0: plan and spec for the orientation walk"
cd viewer && npm ci
```

Print `pwd` and `git branch --show-current` before every commit (a drifted
working directory once pushed straight to main).

### OW-1: the walk

- scope_allow: `viewer/src/orientation/**`, `viewer/src/components/OrientationWalk.tsx`, `viewer/src/components/OrientationInvite.tsx`, `viewer/src/store.ts`, `viewer/src/App.tsx`, `viewer/src/components/SystemOverview.tsx` (test ids only), `viewer/src/components/ExperienceSwitcher.tsx` (test id only), `viewer/src/components/ThemeSwitcher.tsx` (test id only), `viewer/src/utils/tooltipCopy.ts`, `viewer/src/components/__tests__/**`, `viewer/src/orientation/__tests__/**`.
- test_paths (read-only): `viewer/tests/crawl/**`.
- verify_cmd: `cd /Volumes/Studio/dev/.worktrees/solution-explorer--orientation-walk/viewer && npx tsc --noEmit && npx eslint src/ && npx vitest run 2>&1 | tail -30`
- Read first: sections 4.3 to 4.8 here; `TourPlayer.tsx` in full for the card idiom and the mobile docking; `store.ts` around `setExperienceMode` (line 1243) and the overlay flags (line 398); `App.tsx` `openOverlays` (line 334) and the beacon (line 395); `HelpSystem.tsx` for the first-visit logic being replaced (do not edit it in this task beyond removing the `welcomeOpen` reads if the build requires; OW-2 owns the file).
- Acceptance:
  - `WALK_STOPS` has the nine records of section 4.3 with the copy verbatim.
  - The unit tests of section 5.1 exist and pass, except `helpSystem.test.tsx` (OW-2).
  - Running `npx vite --port 5191` against `../.testboard/serve/vscode` (after OW-0 has assembled one, or against the ui-gateway worktree's served bundle read-only at `/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway/.testboard/serve/vscode` if it exists), `?mode=overview&orientation=start` walks all eight stops on a desktop window and seven on a 390px window, crossing into the Workbench at stop 6, and Done leaves nothing on screen.
  - The invite appears on a fresh profile and not after dismiss or after the walk.
  - The beacon carries the four new attributes.
  - Every id in section 4.8 renders.
  - tsc, eslint clean; vitest failing-file set is a subset of the before set.
- Out of scope: `HelpSystem.tsx` copy, crawl files, analyzer, any projection.

### OW-2: the Help dialog

- scope_allow: `viewer/src/components/HelpSystem.tsx`, `viewer/src/store.ts` (removal of `welcomeOpen` only), `viewer/src/App.tsx` (removal of `welcomeOpen` from the beacon and `openOverlays` only), `viewer/src/utils/tooltipCopy.ts`, `viewer/src/components/__tests__/**`.
- verify_cmd: as OW-1.
- Acceptance:
  - No `data-kind="welcome"` anywhere; no `WELCOME_STEPS`; no write of `arch-viz-help-dismissed`.
  - Guide tab renders the applicable stops from `WALK_STOPS` with the live context; About tab carries the section 4.9 copy; footer button `orientation-replay` starts the walk and closes Help.
  - `?` key and Escape behaviour unchanged for Help.
  - `helpSystem.test.tsx` passes.

### OW-3: the crawl

- scope_allow: `viewer/tests/crawl/orientation.spec.ts`, `viewer/tests/crawl/fixtures.ts`, `viewer/tests/crawl/overview.spec.ts` (the `dialogRoots` string only), `viewer/tests/crawl/README.md`, `docs/testing/GUI-CRAWL-DESIGN.md`.
- verify_cmd: `cd /Volumes/Studio/dev/.worktrees/solution-explorer--orientation-walk/viewer && CRAWL_SERVE_DIR=$PWD/../.testboard/serve/vscode npm run test:crawl -- tests/crawl/orientation.spec.ts 2>&1 | tail -40`
- Acceptance: W1 to W5 pass on desktop and mobile against the VS Code bundle; the same command with the UnaMentis serve dir passes; the seed change does not break any existing spec (run `surfaces.spec.ts` and `journeys.spec.ts` once to prove it); the design doc addendum is written in the voice of the existing addenda.
- Out of scope: any file under `viewer/src`.

### OW-4: integration

- Follow the serve and crawl procedure in `docs/testing/RUN-2026-09-03-ui-gateway.md` (UG-7): copy the canonical stores, never open them in place; assemble with `scripts/assemble-serve.py` under the worktree's venv interpreter; serve on ports 5189 (VS Code) and 5190 (UnaMentis). Never touch 5175, 5176, 5185 or 5186.
- Run the full quick crawl on both subjects, desktop and mobile. Both must match or beat the UG-7 numbers (60 of 60 on each) plus the new W rules.
- Take the screenshots of section 5.4.
- Write `docs/testing/RUN-<date>-orientation-walk.md` in the shape of the UG-7 record: commands, numbers per subject and viewport, screenshot paths, the failing-file lists from vitest, open items table, cumulative token spend.
- Commit as `OW-4: integration and run record`.

## 7. Handoff

You are executing a specified body of work on the SysCorpus
(solution-explorer) codebase. Design is complete. Your job is execution,
verification and honest reporting. Where this document is ambiguous,
choose, and record the choice in your report.

**Where you work.** The worktree and branch OW-0 creates. Never `cd` out of
it. Never push. Never touch the owner's running demos or the canonical
stores under `/Volumes/Studio/dev/solution-explorer/.testboard/live/` in
place.

**Read first, in order.** This document, sections 3 to 6. Then
`viewer/src/components/TourPlayer.tsx`, `viewer/src/components/HelpSystem.tsx`,
`viewer/src/store.ts` (lines 76 to 135 and 1243 to 1300),
`viewer/src/App.tsx` (lines 334 to 430 and 1030 to 1170),
`viewer/tests/crawl/fixtures.ts` (lines 128 to 160 and 565 to 600),
`viewer/tests/crawl/tours.spec.ts` (the per-step reporting shape to copy),
`docs/testing/RUN-2026-09-03-ui-gateway.md` (the serve and crawl
procedure), and `.claude/rules/writing-style.md`.

**Order.** OW-0, OW-1, OW-2, OW-3, OW-4. OW-2 and OW-3 may interleave once
OW-1 is committed. One commit per task.

**Hard rules.**
- No new dependency. No model calls. No analyzer or projection change.
- Scope fences per task. Files in a task's `test_paths` are read-only for it.
- Existing test ids are never renamed.
- No em dashes or en dashes anywhere.
- If a step is blocked by something outside the task, record it as
  blocked with the evidence and continue with what does not depend on it.

**What each task ends with.** The verify command's tail pasted, the
acceptance list with a verdict per line, spec ambiguities with the choice
made, and anything unverified stated as unverified. A "done" without the
verify output is not done.

**The one-line acceptance for the whole.** On a fresh browser the served
VS Code Overview shows a small "New here?" card; "Show me around" walks
eight stops (seven on a phone) that each spotlight a real control with a
short card beside it, crosses into the Workbench at "The map", and ends
with the Overview switch in view; the `?` button replays it; the old
welcome modal is gone; the crawl is green on both subjects with W1 to W5
added; and the run record proves it or says what is missing.

**When you finish.** Report in one message: `git log --oneline
wt/ui-gateway-option1..wt/orientation-walk`, the run record path, crawl
numbers for both subjects and viewports, screenshot paths, cumulative
token spend, and the open items table. The frontier reviews from that
message.

## 8. Schedule, budget and risks

**Schedule.** One to two working days for one session: OW-0 and OW-1 on
the first day, OW-2 through OW-4 on the second. Frontier review the same
day OW-4 lands.

**Budget.** About 330k executor tokens plus 50k frontier review, estimated
before dispatch per the token budget rule. Report cumulative spend in the
run record at each task boundary.

**Risks.**
- **Occlusion findings.** The crawl treats fixed overlays as occlusion.
  The seed keeps the invite out of every existing spec; if the seed is
  missed in a new context the invite appears in screenshots and W-less
  specs fail. Mitigation: the seed lives in the shared `crawlPage`
  fixture, as today.
- **The crossing.** `setExperienceMode("workbench")` sets
  `overviewHandoff`, which used to gate the old modal and now gates
  nothing; `useUrlSync` rewrites the URL on the mode change and drops
  `orientation=start`, which is correct (the parameter is read once).
  Verify that browser Back after Done returns to the Overview without
  reopening the walk.
- **Large anchors on phones.** The graph frame fills the screen; the
  highlight rule of section 4.6 keeps a non-empty rect above the docked
  card. W2's 44px minimum is the assertion.
- **Anchors missing on old bundles.** A bundle without `identity` has no
  `identity-statement`; the fallback `overview-title` covers it. A bundle
  with no lenses beyond Structure gets the reduced stop 7 copy.
- **Vitest environment noise.** The known failing-file set must be
  captured before any change and compared after, or a new failure can
  hide inside it.
- **Option 1 not yet merged.** The branch is cut from
  `wt/ui-gateway-option1`. If option 1 changes before merge, rebase the
  walk on it; the walk touches none of option 1's files except three test
  ids in `SystemOverview.tsx`.

## 9. Owner decisions before dispatch

1. Approve the plan as written, or edit section 3's defaults.
2. Copy: approve the stop bodies in section 4.3 and the About text in
   section 4.9, or mark edits. These are the words the demo audience reads.
3. Invite on first visit (recommended) or replay-only from Help.
4. Whether this lands before the VS Code demo goes public or after.
5. Whether the `orientation=start` URL parameter should be documented for
   presenters in `docs/publication/HANDOFF-DEMO-PROGRAM.md` (recommended,
   one line).
