# Interface comparison and VS Code rollout

Status: local evaluation plan, 2026-09-01

## UnaMentis comparison contract

The local UnaMentis demo is one viewer loading one projection. It does not run
two data services, copy JSON, or maintain an old-data/new-data translation.
Only the presentation aperture changes:

- new front door: `?mode=overview`;
- classic explorer: `?mode=workbench`;
- no `mode` parameter: use the saved Start interface preference, defaulting to
  the new front door for a fresh session.

The switch preserves `data`, component selection, drill level, lens, flow step,
semantic level, tab, and unknown future query parameters. Preferences provides
both an in-place switch and “open in another tab” links, so side-by-side tabs
resolve the same projection and differ only by `mode`.

This is an evaluation facility on the dedicated front-door branch. Publishing
the classic interface as a public product choice is not part of the plan.

## Local review loop

Use the two explicit URLs from Preferences rather than navigating each tab by
hand. For every concern:

1. Confirm the subject name and data URL are identical.
2. Put both tabs on the same component, lens, drill level, and theme.
3. Record whether the difference is intentional simplification, missing access,
   misleading emphasis, or a defect shared by both interfaces.
4. Verify the fact in the underlying projection before treating either rendering
   as authoritative.
5. Fix shared data/view-model defects once; fix presentation defects in the
   relevant interface.

High-value UnaMentis comparisons are the default landing, the five portrait
areas, the root iOS client, server/database, Flow, Support, Data, and a component
with a large symbol inventory. Run at wide desktop, tall desktop, and phone
portrait before the interface is considered settled.

## Applying the new interface to the VS Code demo

The VS Code step should be a dataset graduation, not a second implementation.
It must use the same viewer code and interface-mode contract as UnaMentis.

### Phase 1 — projection readiness

- Locate the canonical local VS Code demo assembly and freeze its analyzer
  snapshot ID for the comparison.
- Generate or validate `orientation`, `support`, and `security` sidecars using
  stable component IDs. The deterministic orientation fallback is acceptable
  for a first render, but any manually curated JSON must be justified by a fact
  the analyzer cannot presently derive.
- Verify that both interface URLs fetch the same manifest and sidecars. Record
  component, relationship, file, symbol, and code-line totals once and compare
  both tabs to that record.
- Keep the UnaMentis and VS Code demos as data configurations of one viewer; do
  not fork components or copy the application for VS Code.

Exit: one frozen VS Code projection loads without schema or request errors in
both modes.

### Phase 2 — first rendered pass

- Make the new front door the fresh-session default for the VS Code local URL.
- Retain the classic comparison control during evaluation.
- Capture Portrait, Questions, Atlas, classic root, and at least one nested
  subsystem at 1440 x 900, 1000 x 1400, and 393 x 852.
- Exercise the same lenses available in UnaMentis and explicitly record lenses
  absent because the VS Code projection lacks evidence.
- Check orientation copy and portrait groupings for a very large, multi-domain
  repository. The opening experience must not become a list of hundreds of
  VS Code packages merely because those names exist.

Exit: no clipped primary controls, horizontal document overflow, obscured
selection, microscopic guided answer, or browser error in the required views.

### Phase 3 — scale and fidelity pass

- Measure layout settling time, search readiness, detail load time, and memory
  on the larger projection. Preserve bounded node budgets rather than proving
  scale by rendering every component simultaneously.
- Compare at least ten representative tasks side by side: finding a named
  component, answering an intent-first question, following a relationship,
  inspecting files/symbols, checking data, support, security, findings, and
  returning to the system overview.
- Confirm every simplification has a route into the full evidence and every
  classic-only fact is either deliberately secondary or reachable elsewhere.
- Run the readability standard, all five themes in their intended appearance,
  keyboard navigation, phone touch targets, 200% text resize, and reduced
  motion checks.

Exit: the new interface is at least as fact-complete for the comparison tasks
and materially easier to orient in; any exceptions are written as accepted
tradeoffs rather than left implicit.

### Phase 4 — owner review and convergence

- Review the frozen VS Code and UnaMentis comparisons locally.
- Classify feedback into shared UI changes, dataset-specific projection fixes,
  and deliberate differences.
- Apply shared UI changes once and rerun both demo matrices.
- Remove the local classic comparison affordance from the public configuration,
  or keep it behind an explicit evaluation flag, before release.

Exit: owner approval on both datasets and no unresolved blocker in the
readability, honesty, navigation, or geometry gates.

### Phase 5 — main integration

- Rebase the dedicated front-door branch onto current `main` and resolve only
  known overlaps; do not regenerate demo data during conflict resolution.
- Run the full unit suite, lint, production build, deterministic analyzer gates,
  UnaMentis matrix, and VS Code matrix on the rebased commit.
- Merge the viewer, generated-view contracts, standards, and demo configuration
  together so `main` cannot contain a new UI that lacks the data needed to
  explain itself.
- Tag the two frozen evaluation snapshots and retain their comparison findings
  as regression inputs.

Exit: the new interface is the default on `main`, the classic public path is
retired or explicitly evaluation-only, and both reference demos pass the same
release contract.

## Stop conditions

Pause the VS Code rollout and report before redesigning the engine if:

- the projection cannot supply stable targets for the portrait or question
  routes;
- a bounded answer cannot remain readable without hiding required facts;
- the dataset requires hundreds of active DOM graph nodes for an ordinary task;
- differences between the interfaces trace to different JSON, endpoints, or
  snapshot versions;
- renderer performance prevents an interaction-ready view within the agreed
  local demo budget.

These distinguish a data-contract, interaction-design, or rendering-scale
problem from a cosmetic iteration and prevent the VS Code pass from becoming an
unbounded rewrite.
