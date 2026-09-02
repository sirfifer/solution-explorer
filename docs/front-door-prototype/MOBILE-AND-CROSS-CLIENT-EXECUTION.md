# Mobile and cross-client execution plan

## Decision

Mobile is a first-class reading and investigation surface, but it is not a
miniature desktop graph. The product should keep one information architecture,
one set of stable identities, and one immutable projection snapshot while each
client uses the interaction model its screen and input method can support.

The shared visual contract is [Readability and usability standard](../standards/READABILITY-USABILITY-STANDARD.md).

For the evaluation period, the web front door and the UnaMentis iOS demo should
load the exact same published projection bundle. This gives us a controlled A/B
comparison of interfaces: differences in comprehension or missing capability
cannot be explained by different analyzer runs, grouping, enrichment, or data
freshness.

## Rendered mobile assessment

The production front door was exercised at 360 x 740, 393 x 852, 430 x 932,
and 844 x 390 with real browser rendering and interaction. Portrait, Questions,
Atlas, theme selection, search, preferences, tree navigation, lens sheets,
Support, Security, and component details all rendered without horizontal page
overflow, console errors, failed requests, or application crashes.

What already works:

- Overview content reflows into a legible single-column journey.
- Questions preserves ordinary-language entry rather than requiring component
  or lens vocabulary.
- Atlas becomes a useful list of bounded system areas.
- Preferences, search, theme selection, and mobile bottom sheets use the full
  phone width effectively.
- Support and Security already have mobile panel variants instead of depending
  on desktop-docked panels.
- The tree is a viable high-density navigator on touch screens.

What did not meet a first-class mobile standard:

- The Overview/Workbench control collapsed to unexplained `O` and `W` buttons.
- Several header and secondary actions were below a 44 px touch target.
- The Workbench header contained more controls than a phone can present; some
  were clipped even though the document itself did not report overflow.
- The Help control competed with bottom navigation and detail sheets.
- Fit-to-view makes a complete component graph visible but too small to read or
  select reliably. Enlarging controls does not solve this information-density
  problem.
- A selected question changed an answer below the fold without bringing that
  answer into view.

## Immediate stabilization

The low-risk pass keeps desktop behavior and data semantics intact while:

- giving Overview a two-row mobile header with full `Overview` and `Workbench`
  labels;
- preserving 44 px phone targets for global navigation, posture selection,
  disclosure, Atlas routes, semantic level selection, and graph controls;
- reducing Workbench mobile chrome to tree, lens, theme, and overflow actions;
- moving Search to the persistent bottom navigation and Review to the mobile
  overflow menu;
- adding an explicit Overview destination to Workbench bottom navigation;
- moving Help clear of bottom navigation;
- scrolling a newly selected question's answer into view on narrow screens.

These changes make the current build safe to evaluate. They do not pretend the
full graph is now a good primary phone interface.

## Target mobile interaction model

### Overview

Overview remains the default mobile entry. Portrait is the fastest orientation,
Questions is the intent-based route, and Atlas is the compact system-level map.
The three are different starts over the same projection, not separate data
products.

### Workbench

On a phone, Workbench should open as a coordinated navigator and inspector:

1. A ranked or hierarchical list is the primary navigation surface.
2. Lens choice changes that list without losing selected identity.
3. Selecting an item opens a half-height summary sheet; expanding it provides
   the full evidence, files, symbols, links, findings, and review actions.
4. Graph is an optional spatial context view, entered deliberately and centered
   on the current selection. It is not the default whole-system canvas.
5. Search and Overview remain one tap away in persistent bottom navigation.

The existing Tree, ranked lens panels, bottom sheet, and detail panel are the
implementation base. The new work is composition and state continuity, not a
parallel mobile feature set.

### Tablet and landscape

Tablet can progressively restore split views and the graph as available width
allows. Breakpoints must follow usable region width, not device labels. Phone
landscape should prefer a two-pane list/detail layout before it attempts the
full desktop header and canvas.

## One data stack for web and iOS

The shared stack should be a versioned, immutable projection bundle, which is
already aligned with the product's local-first architecture. A database service
is not required to prove client parity.

```text
analyzer + store
      |
      v
immutable snapshot bundle
  index.json
  architecture/manifest.json
  architecture/orientation.json
  architecture/support.json
  architecture/security.json
  architecture/components/*.json
  publication.json
      |                         |
      v                         v
web front door             UnaMentis iOS demo
```

Add a small snapshot descriptor with:

- `snapshot_id`, subject identity, commit, generation time, and schema version;
- a base URL and the authoritative entry artifact;
- SHA-256 and byte length for every file;
- feature availability derived from the bundle, never inferred independently
  by a client;
- compatibility minimums for the web and iOS readers.

Both demos receive only the descriptor URL. They must show the same snapshot ID
in an evaluation/about surface and reject a bundle whose checksums or supported
schema do not agree. Themes, launch preference, navigation history, annotations,
and other user state remain client-local and are not part of the shared facts.

For multiple projects, publish a catalog of immutable snapshot descriptors.
Project selection changes the descriptor, not the viewer build. A named
evaluation cohort pins both clients to the same descriptor until that cohort is
closed; refreshing the analyzer creates a new cohort instead of silently moving
the data underneath an experiment.

## A/B evaluation design

Initially this is a paired interface comparison, not traffic optimization.
Participants perform the same mission against the same pinned snapshot in both
clients, with order alternated to reduce learning bias.

Use one small cross-client event vocabulary:

- `session_started`: client, variant, snapshot ID, viewport class, task ID;
- `surface_opened`: Overview direction, lens, tree, graph, search, or detail;
- `identity_selected`: stable projected ID and source surface;
- `evidence_opened`: evidence kind and stable identity;
- `task_completed` or `task_abandoned`: duration and optional confidence;
- `data_unavailable`: requested capability and projection-declared reason.

Do not compare raw tap counts between native and web controls. Compare outcomes:

- time to correctly describe what the system is;
- time to find a named capability without knowing its component;
- time to identify a likely operational or security concern;
- time to reach supporting evidence;
- successful return to the prior context;
- unsupported or missing surfaces by client;
- participant confidence and correctness.

Telemetry must be separable from the projection host, optional for local demos,
and free of source contents. Stable IDs, task IDs, snapshot ID, and interaction
metadata are sufficient.

## Delivery sequence

### M0 — current stabilization

- Complete the touch-target and navigation-chrome fixes above.
- Add automated phone portraits for Overview, Questions, Atlas, Workbench,
  Tree, Search, Support, Security, and component detail.
- Gate on no clipping, no unexpected horizontal overflow, no console errors,
  and keyboard/focus behavior at desktop sizes.

### M1 — shared snapshot contract

- Specify and emit the snapshot descriptor and file hashes.
- Serve one pinned UnaMentis snapshot from the demo data host with CORS, range,
  cache, and content-type behavior verified on Safari and Chromium.
- Configure both clients with the same descriptor URL.
- Add a parity test that loads all declared artifacts in both client adapters
  and compares counts, IDs, route availability, and trust rollups.

### M2 — native iOS Overview

- Implement Portrait, Questions, Atlas, trust, search, theme choices, and launch
  preference using the shared `orientation/v1` contract.
- Preserve route targets as stable state rather than translating them into
  screen-specific names in the data layer.
- Prove the same five task missions on web and iOS before adding visual polish.

### M3 — mobile Workbench composition

- Make the ranked/tree navigator primary on phone and Graph secondary.
- Reuse every available lens through a common list-section-detail protocol.
- Preserve lens, selected ID, semantic level, filters, and sheet position across
  list, graph, search, and Overview transitions.
- Complete touch review for detail tabs, evidence rows, annotations, sets, and
  guided tours.

### M4 — paired evaluation

- Pin a multi-project cohort to immutable descriptors.
- Run counterbalanced web/iOS missions and compare the guided Overview with
  direct Workbench entry on the same immutable projection.
- Produce an automated surface-parity report and a qualitative issue ledger.
- Iterate only after separating data gaps, contract gaps, and interface gaps.

## Acceptance gates

- At 360 x 740, every global action is visible or present in a clearly labeled
  menu and every primary touch target is at least 44 x 44 CSS pixels.
- A user can move Overview -> question -> evidence -> Overview without losing
  subject or selected identity.
- Whole-system Graph is never the only path to a component on a phone.
- Web and iOS display the same snapshot ID and agree on stable IDs, counts,
  available routes, trust rollups, Support rows, and Security rows.
- An unavailable feature is reported from projection metadata, not silently
  omitted by one client.
- A project refresh creates a new immutable experiment cohort.
- Evaluation results can distinguish interface failure from missing data.

## Explicit non-goals for the first iOS pass

- Reproducing the desktop canvas renderer in native code.
- Synchronizing personal preferences or annotations between clients.
- Introducing a mutable application backend solely for the demo.
- Random traffic assignment before paired mission testing has established what
  should be measured.
