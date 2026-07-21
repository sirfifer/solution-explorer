# GUI regression strategy: AI-operated, vector-based, blunt

Designed 2026-07-21 from owner direction. Companion to
`docs/remediation/REGRESSION-STRATEGY.md` (which proves the engine did not
regress) and `ROBUSTNESS-STRATEGY.md` (which proves the engine fails honestly).
This document covers the third leg: proving the VIEWER, the rich graphical
interface that is the product's main engagement surface, is rock solid, and
keeping it that way as it grows. Design authority for the harness, the plan
format, the reporting contract, the orchestration cycle, and the maintenance
convention. Implementation is owner-gated; nothing here is built yet.

## Why this exists

The viewer is the product to most eyes, and rich graph UIs are historically
where flakiness lives. Unit tests (vitest) cover logic; nothing today exercises
the real rendered interface: clicking, drilling, navigating, slicing views. The
owner's standard: a person exhaustively walking the UI would be ideal but does
not scale to large codebases. The scalable equivalent is vector-based testing.
Hit every KIND of interaction, drive each to its FULL depth, and sample
instances rather than enumerating them. One hundred instances of a link type do
not need one hundred tests; three well-chosen ones validate the mechanism.

Two non-negotiables inherited from the project ethos:

- No theater. The report says what is broken in plain words. A partially
  working UI is reported as partially working, never rounded up.
- Mobile is first-class. Every vector runs at desktop AND phone viewport
  (390px portrait, plus landscape for width-hungry views). A feature that only
  works with a mouse at 1440px is a failing test, not a caveat.

## What gets tested (the surface inventory)

Grounded in the current viewer source. The completeness check in the
Maintainability section keeps this list honest as the surface grows.

- Lenses (6, from `viewer/src/lenses/registry.ts`): structure, activity,
  capability, data, flow, rules. Each lens carries question-shaped sub-views
  (for example data: what-knows, who-reads, who-writes, how-sure,
  where-defined) that are part of its depth.
- Detail panel tabs (11, conditional, from `DetailPanel.tsx`): overview, docs,
  files, symbols, relationships, ai, status, testing, actions, capabilities,
  data. Conditional presence is itself a behavior to verify (a tab appears
  exactly when its data exists).
- Graph interactions: node select, expand/collapse drill-down, breadcrumbs and
  back navigation, aggregate nodes, edge rendering per relationship type
  (EDGE_STYLES map plus its fallback), pan/zoom, device frames on client nodes,
  the ? help affordance, role badges, criticality dots.
- Full-depth drill: root component, child component, files tab, symbol,
  CodePreview open, code block visible. This chain is the single most
  important vector; the product's promise is that you can descend from the
  whole system to a line of code.
- Overlays and systems: SearchOverlay (query, result, navigate), HelpSystem,
  TourPlayer, TreeNavigator (including ChangelogPanel with its unread badge),
  LensSwitcher, FindingsSurface, SupplyChainSurface, InventoryPanel,
  CoverageBadge, StatusDashboard, SolutionIndex (multi-repo), ErrorBoundary.
- Review and annotation subsystem (first-class, stateful): ReviewModeButton,
  AnnotationInput, ReviewSummary, selection sets, finding-set annotation and
  directive export, all persisted to localStorage keyed by architecture
  identity (roughly 15 store actions). Persistence round-trips are part of its
  depth.
- Live and admin surfaces (AdminDashboard, live monitoring via
  live-config.json) are real but require a live fixture; they are scoped to
  Phase 4, stated here so their absence from the initial plan is a recorded
  decision, not an oversight.
- Degradation surfaces: unenriched dataset (no ai_enhance anywhere), dataset
  carrying honest gaps (R1's `gaps` key), old pre-gap dataset (additive
  projection promise), split-mode dataset (manifest plus shards) versus
  monolith.

## The vector catalog

A vector is one kind of interaction driven to full depth with sampled
instances. Assertions are behavioral (what a user would see), not
implementation (no CSS class checks unless they are the user-visible label).

| ID | Vector | Full depth means | Sampling rule |
|----|--------|------------------|---------------|
| V1 | Boot and render | App loads the dataset, graph renders nodes and edges, zero uncaught console errors | Both datasets: dogfood monolith, split-mode |
| V2 | Drill to code | Root to child to files/symbols tab to CodePreview showing real code | 3 components of different types, each to the bottom |
| V3 | Detail tabs | Every tab renders content matching the component's data; conditional tabs appear exactly when data exists | Per tab: 2 components with the data, 1 without |
| V4 | Edge types | Each relationship type present in the dataset renders with its distinct style; both endpoint nodes of a sampled edge are navigable. Edges themselves are decorative today (no click handler in ArchitectureGraph); if edge-level interactivity ships later, V4 grows with it | 2 edges per type; sort key is source+target+type lexicographic (relationships carry no id) |
| V5 | Lenses | Each registered lens activates, renders populated content, and each of its sub-views answers with data; switching lenses preserves sane state | Every lens, every sub-view, 1 selection each |
| V6 | Search | Query finds a known component, a known symbol, and a known file; selecting a result navigates to it | 3 queries of the 3 kinds |
| V7 | Navigation state | Breadcrumbs reflect drill path; back returns correctly; expand/collapse round-trips; deep-link URL restores state | 2 drill paths, 1 deep link |
| V8 | Mobile | V1, V2, V5, V6, V10, V13 repeated at 390x844 portrait plus one landscape width-hungry view; tap targets work; touch-and-hold paths exercised; no horizontal page scroll | Same samples as the source vectors |
| V9 | Degradation | Unenriched, gap-carrying, and old datasets all render without errors; gaps surface visibly; AI-dependent surfaces absent, not broken | 1 dataset each |
| V10 | Help and tours | ? affordances open correct content; a tour plays through its sequence | 3 help points, 1 full tour |
| V11 | Findings and surfaces | FindingsSurface, SupplyChainSurface, InventoryPanel, CoverageBadge each render their dataset section and drill into an entry | 2 entries each |
| V12 | Resilience | ErrorBoundary catches an induced render fault with a recoverable UI; malformed dataset degrades to a legible message, not a blank page | 2 induced faults |
| V13 | Review and annotate | Review mode toggles; an annotation is created, edited, deleted; a selection set is created and populated; state survives a full reload (localStorage persistence keyed by architecture identity) | 1 full workflow, desktop and mobile |

Sampling is deterministic: instances are chosen by a stated rule (first N by
sorted id within each class; for edges, sorted by the composite
source+target+type key), never by the runner's whim, so two runs of the plan
test the same things and results are comparable across runs.

V8's mobile repeat list includes V10 and V13 in addition to V1, V2, V5, V6,
and mobile cases may use the press-and-hold action (see the plan format):
ComponentNode gates its hover preview behind a 500ms touch-and-hold on coarse
pointers, a device-specific path that tap-only vocabulary cannot reach.

## The plan format (written for an AI operator)

The plan is data, not prose and not code: one YAML file per vector under
`viewer/tests/gui/plan/` (under the viewer because the tooling it drives is
browser-side; the repo-root `tests/` stays purely the Python analyzer suite).
Each case:

```yaml
- id: V2.1
  vector: drill-to-code
  viewport: desktop          # desktop | mobile | mobile-landscape
  dataset: dogfood           # key into viewer/tests/gui/datasets.yaml
  steps:                     # actions ONLY, imperative, one action each
    - "Load the app and wait for the graph to render"
    - "Click the component node titled 'analyzer'"
    - "Open the detail panel tab labeled 'Symbols'"
    - "Click the first symbol in the list"
  pass_when:                 # ALL assertions live here, each binary
    - "a code preview is visible containing at least 3 lines of source text"
    - "no unexpected console or network errors during the flow"
  evidence: screenshot       # screenshot | screenshot+console | trace
```

Rules that make this executable by a mid-tier model without judgment calls:

- Steps are actions only; assertions live only in pass_when. The verdict
  semantics follow from that split: a step that cannot be performed (element
  genuinely absent, app crashed) makes the case BLOCKED at that step number
  with a screenshot; a completed case whose pass_when is unmet is FAIL. A
  cascade of one boot failure therefore reads as one failure plus blocked
  cases, not forty independent bugs.
- Action vocabulary is small and closed: load, click, open, type, scroll to,
  press and hold for N ms (required for the mobile touch-and-hold preview
  path), switch viewport orientation, reload. A case needing a verb outside
  the vocabulary extends the vocabulary in the same PR, never improvises.
- One action per step, named by user-visible label, never by selector. The
  runner finds elements the way a person would (visible text, role, position),
  which is what makes the tests survive markup refactors.
- Every pass_when line is binary. "Looks right" is banned. If an expectation
  cannot be phrased binarily, the case is redesigned until it can.
- "No unexpected console or network errors" is defined per dataset:
  `datasets.yaml` carries an explicit allowlist of KNOWN intentional probes,
  seeded with the two the app makes by design on every boot (the
  live-config.json fetch that 404s in static mode, and the manifest.json probe
  that 404s on monolith-only datasets). Anything not allowlisted fails the
  case. The allowlist is part of the reviewed plan, so it cannot silently
  grow.
- The plan states its own fixtures: `viewer/tests/gui/datasets.yaml` maps
  dataset keys to generation commands (dogfood: the repo's own projection;
  split-mode: `python3 analyze.py . --split`, which already exists;
  gap-carrying and unenriched variants produced by documented transforms; an
  old-format fixture checked in frozen).

## Execution model

- Target: the local viewer against local datasets. Default target is the
  production build served statically (`vite build` then a static server),
  because that is what users get; a `--dev` option exists for debugging runs.
  No network beyond localhost.
- Execution model, chosen explicitly: the runner is an LLM AGENT driving a
  real browser through Playwright tooling, not a compiled @playwright/test
  suite. That is the owner's intent (fully AI driven) and what makes
  label-based, refactor-surviving steps possible. The honest cost profile:
  a full plan is on the order of a hundred cases across two viewports, each a
  short tool loop, so a complete run is an hours-scale, agent-attended
  activity, not a per-PR CI job. Only `gui-plan-check.py` (static
  completeness) runs in CI. If specific hot vectors later prove perfectly
  stable, freezing them into scripted specs for cheap unattended reruns is a
  Phase 4 option, not the default.
- Sharding: one vector per runner shard, and every shard gets a FRESH browser
  context (isolated localStorage and storage state). This is load-bearing:
  dark mode, annotations, selection sets, and changelog read state all persist
  in localStorage, so shared contexts would bleed state across shards. V13
  owns its persistence assertions and never shares a context with another
  running shard.
- The runner executes steps literally, captures evidence, and writes results.
  It does not interpret failures, does not retry beyond one
  reload-and-reattempt per case (flake detection: a pass on attempt 2 is
  recorded PASS_FLAKY, never silently PASS), and does not editorialize.
- Runner model: Sonnet. The plan's rigidity is what makes this reliable at
  Sonnet's tier: no design judgment is delegated to the runner, only literal
  execution and honest observation. A Haiku experiment is worthwhile once the
  plan is proven stable under Sonnet, on the cheapest vectors first (V1, V6);
  heavy tool loops are the risk. The graduation bar is verdict-consistency,
  scoped precisely: identical id, verdict, step-reached, and per-assertion
  outcomes in results.json across three consecutive full runs. Evidence
  files, timings, and screenshots are excluded from the bar (the app renders
  relative timestamps and animations, so byte-identical evidence is
  impossible by construction).
- Console and network logs are captured for every case; any error outside the
  dataset's declared allowlist fails the case even if the visible assertion
  passed.

## The results contract (two audiences, one truth)

Each run produces `viewer/tests/gui/results/<run-id>/`:

1. `results.json`, the AI-facing record. Schema `gui-results/v1`, one entry
   per case: id, vector, viewport, dataset, verdict (PASS | PASS_FLAKY | FAIL |
   BLOCKED), the step reached, per-assertion outcomes, console error excerpts,
   evidence paths, and wall time. Deterministic field order. This is the input
   a fixing agent works from, complete enough that it never needs to re-run a
   test just to understand a failure.
2. `REPORT.md`, the human narrative. Blunt by contract. Opens with one
   paragraph a non-engineer can read: what is solid, what is broken, what is
   flaky, whether the product is demoable today. Then per-vector detail with
   inline evidence links. Banned phrases include "mostly working", "minor
   issues remain", and any construction that rounds a FAIL up. The report
   states counts (X of Y cases pass) and names every failure.

A run's exit status: GREEN (all pass), FLAKY (passes with PASS_FLAKY present),
RED (any FAIL/BLOCKED). Flaky is a first-class outcome, not a pass, because
flakiness is the historical failure mode of this UI.

## The cycle (orchestration)

The fix loop the owner described, as a state machine:

1. TRIGGER. The orchestrator (Fable or Opus, chosen at invocation by cost and
   availability) receives the goal: run the plan, or run until green.
2. RUN. Orchestrator dispatches the Sonnet runner per vector (parallel shards
   are fine; they share nothing but the built app). Runner writes results.
3. ANALYZE. The orchestrator (never the runner) reads results.json, clusters
   failures by probable root cause (one broken store selector can fail twenty
   cases; the analysis says so), and writes the fix plan: ranked, concrete,
   file-level where possible.
4. FIX. Fixes are delegated (Opus for structural work, Sonnet for mechanical
   fixes), on a worktree, with the normal PR protocol when changes are real.
5. RERUN. Failed and blocked vectors rerun first; a full-plan rerun confirms
   before declaring green (a fix can break a previously passing vector).
6. EXIT. Green: report and stop. Not green and out of ideas or budget: report
   exactly where it stands and what is recommended, never "close enough".

The whole cycle is triggered as a skill (working name `/gui-test-cycle`) whose
definition holds the model-selection policy, the shard fan-out, the results
contract, and the iterate-until criteria, so invoking it is one line: "run a
GUI test cycle on the dogfood" or "... and iterate until green".

## Maintainability (the part that makes it live)

A test system nobody updates is theater within a month. Three mechanisms:

1. The convention, stated here and enforced in review: ANY change that adds or
   alters GUI surface ships with its plan delta in the same PR. New lens: new
   V5 rows. New detail tab: new V3 rows. New overlay: a vector or rows in an
   existing one. This is a review-blocking expectation, the same standing as
   tests for engine changes. It gets recorded in project memory so every
   future session applies it unprompted.
2. The completeness check, mechanized honesty in the coverage-ledger spirit: a
   small script (`scripts/gui-plan-check.py`) with two tiers, honest about
   what each can see. Tier one is static enumeration of the surfaces that ARE
   statically extractable (registered lens ids and their sub-view ids,
   DetailPanel tab keys, EDGE_STYLES relationship types); any enumerated
   surface with zero plan references fails the check. Tier two covers what
   cannot be enumerated from source (overlay and subsystem components have no
   registry): a checked-in surface manifest (`viewer/tests/gui/surface.yaml`)
   lists every component that requires plan coverage, the check cross-checks
   manifest against plan in both directions, AND it flags any new file under
   viewer/src/components/ that appears in neither the manifest nor its
   explicit ignore list, so a new surface cannot land invisibly. The manifest
   is hand-maintained but drift-proof: forgetting it is a CI failure, not a
   silent gap. It cannot judge depth, but it makes silent omission
   impossible. Runs in CI on viewer changes.
3. Frozen expectations where cheap: V9's old-format fixture is checked in
   frozen, so the additive-projection promise is permanently regression-tested
   at the UI level, mirroring the golden-corpus idea one layer up.

## Rollout (owner green-lights each phase)

- Phase 1, build: plan files for V1 through V13 seeded from the current
  surface, datasets.yaml plus fixture transforms, the runner skill and prompt,
  results schema, gui-plan-check.py. Implemented by Opus from this design.
- Phase 2, shake out on the dogfood: run the full plan locally, iterate the
  cycle until green or until findings need owner decisions. The first honest
  REPORT.md about the current UI is a deliverable in itself, whatever it says.
- Phase 3, harden: completeness check into CI, the convention into memory and
  CONTRIBUTING notes, flake tracking across runs (three consecutive
  PASS_FLAKY on one case opens a Discovered-table entry).
- Phase 4, extend: demo dataset once the owner restores the deploy token
  (same plan, second dataset key), the Haiku runner experiment, and a weekly
  scheduled cycle if the owner wants a standing pulse.

## Open questions for the owner

1. Evidence retention: screenshots per run accumulate fast. Proposal: keep the
   latest green run and every red run, prune the rest locally, never commit
   binary evidence to the repo. Confirm or adjust.
2. Where results live: proposal is gitignored `viewer/tests/gui/results/` locally,
   with REPORT.md pasted into the conversation when a cycle is owner-triggered.
   An alternative is committing REPORT.md (not evidence) per milestone run.
3. Budget stance for "iterate until green": a default ceiling per cycle (for
   example three fix iterations before checking in) versus truly unbounded.
