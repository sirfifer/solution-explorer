# Handoff: double-tap snap zoom

Written 2026-08-18 for a fresh session. Everything needed to start is here; the
background is in `COMPREHENSION-STUDY-2026-08-17.md` in this same directory.

## Where the work lives

- Branch `wt/comprehension-fixes`, worktree
  `~/dev/.worktrees/solution-explorer--comprehension-fixes`. 12 commits.
- `main` is untouched at `e0c704e` and matches `origin/main`. Nothing is pushed
  or merged. Do not merge without the owner's say-so.
- A Python venv for the analyzer tests is at `.venv-wt/` inside the worktree
  (untracked). `.venv-wt/bin/python -m pytest tests/ -q` runs the suite.

## What is already done

All nine findings (S1 to S9) from the cold-start comprehension study are fixed
and browser-verified against the real UnaMentis demo dataset, plus the
aggregation rework the owner decided on. See the status table and the
"Remediation status" section of the study report.

Test posture to expect, verified as the correct baseline:

- Python: 1451 passed, 3 failed, all three pre-existing and unrelated. Two are
  MCP failures that reproduce identically on clean `main`. The third
  (`test_pruned_directory_row_stands_in_for_its_contents`) fails ONLY inside a
  git worktree, where `.git` is a file rather than a directory, so the ledger
  emits `excluded:unsupported_extension` instead of a directory disposition.
  Proven by running the same analyzer code against both checkouts. It passes in
  CI and in the main checkout.
- Viewer: 365 passed, 86 failed, every failure pre-existing on `main`. Verify
  this the honest way rather than trusting the count: collect the failing test
  FILE names on `main` and on the branch and diff the two lists. They must be
  identical. Do not absorb a new failure into the baseline.
- `npx tsc --noEmit` and `npx eslint src/` are both clean. Keep them that way.

## The task

Build double-tap snap zoom, then evaluate whether it is actually any good.

The owner's words (2026-08-18), which are the spec:

> I think that there should be a double tap snap zoom ... it snaps between two
> states. One snap would be to fitting the screen again under all the
> constraints for a given device, given environment. The other direction is
> snapping to readability ... snap based on priority, like if you've got a bunch
> of heroes and there's the one that's the main one and some priority to it,
> then that should dictate what part of the view that won't fit on the screen is
> the center of the snap to read.

And on scope:

> The only way we'll know whether this actually works or is plausible is to give
> it a go ... This will probably have to be good for now or we'll just have to
> do some physical experimentation.

So: build it, try it, report honestly whether it feels right. Real-device
testing by the owner is expected afterward. It is explicitly allowed to come
back and say the idea does not work in practice.

### Behaviour

A double tap **on empty canvas** (not on a node) toggles between two states:

1. **Fit** — the whole level on screen, which is what `fitView` already does.
2. **Read** — zoomed to a comfortably readable scale. Because not everything
   fits at that scale, the view CENTERS ON PRIORITY: the most important
   component at this level decides what gets framed.

Which state a tap goes to depends on where the view currently is, so repeated
taps toggle. Pinch zoom on touch keeps working untouched.

### Implementation notes, learned the hard way

- `zoomOnDoubleClick` is already `false` on the `ReactFlow` element. It was
  disabled to fix the node double-click drill (finding S5), so the pane
  double-tap is free to use.
- **Do not rely on the browser's `dblclick` event.** The node drill fix exists
  because a first click can open or close the detail panel, which resizes the
  canvas (measured: 1184px to 864px) and slides content ~160px out from under a
  stationary cursor, so the second press lands somewhere else and no `dblclick`
  ever fires on the intended target. Detect the gesture the same way
  `ArchitectureGraph.tsx` already does for nodes: two presses at the same screen
  point (5px slop) within a 500ms window. Reuse that pattern rather than
  inventing a second one.
- Use `pointerdown` so the same code path covers mouse and touch. A pinch's
  second finger lands far away, so the position check rejects it naturally.
- To decide which state the view is currently in, compute the fit viewport
  rather than guessing from a magic zoom number: `getNodesBounds` and
  `getViewportForBounds` are exported by `@xyflow/react`. If the current zoom is
  within a small epsilon of the fit zoom, the next snap is Read; otherwise it is
  Fit.
- For the Read target, rank with the SAME importance ordering the canvas already
  uses so the two never drift: criticality, then connection count, then file
  count. That comparator currently lives inline in `computeDrillLevelView` in
  `viewer/src/store.ts`. Extract it into one exported helper and use it in both
  places rather than copying it.
- `READABLE_ZOOM` (0.6) is already exported from `store.ts` and is the threshold
  the readability loop uses. The Read snap should land at or above it; something
  around 0.85 is comfortable, and it is worth trying a couple of values.

### Where to touch

- `viewer/src/components/ArchitectureGraph.tsx` — the gesture, the snap, the
  container ref (already present as `containerRef`).
- `viewer/src/store.ts` — export the shared importance comparator.
- New test file alongside `viewer/src/__tests__/nodeBudget.test.ts`. Keep the
  snap DECISION pure and testable: a function of (current zoom, fit zoom) to the
  next state, plus target selection as a function of the node set. Test those
  directly; do not try to unit-test the gesture plumbing.

### How to verify it for real

A local instance of the fixed viewer against the real dataset is the only
honest test. Rebuild and serve:

```
cd <worktree>/viewer && npm run build
# copy dist to a serve dir, drop in the mirrored dataset, serve it, then drive
# a real browser against it
```

The mirrored UnaMentis dataset (254 components, split mode, AI-enriched) was
kept in the previous session's scratchpad. If it is gone, re-mirror it from
`https://solution-explorer.unamentis.org/architecture/` (manifest plus the
per-component `data/detail-*.json` shards, using a browser User-Agent because
Cloudflare blocks the default Python one).

Check at three viewport sizes, since adapting to the view is the whole point:

| Viewport | Current fit state on the iOS client drill level |
|---|---|
| Phone, 390x844 | 8 hero nodes at 0.23 zoom, ~46x29px each |
| Laptop, 1440x900 | 7 nodes at 0.72 zoom, ~179x79px |
| Large, 2560x1440 | 10 nodes at 1.01 zoom, ~251x97px |

The phone row is the case snap zoom exists for. Confirm a double tap there
lands somewhere readable and centered on something worth reading, and that a
second double tap returns to fit.

## Decided, do not revisit without the owner

- **Heroes never aggregate**, rejected explicitly on 2026-08-18. Where hero
  types clash with a readable default view, partial readability plus easy zoom
  and scroll is the accepted answer. The phone case stands by decision.
- **Low confidence is never a published UI state.** It is a pipeline problem to
  resolve, or an honest gap record. No confidence labels on nodes.
- **Aggregation ranks by importance, not size**, and the node count is derived
  from the actual canvas, never a fixed number.

## Working agreement with the owner

Read `docs/remediation/COMPREHENSION-STUDY-2026-08-17.md` first. Two rules that
have been raised repeatedly and matter more than they look:

1. **Never surface a decision without the full packet.** Naming a topic and
   saying "this needs your call" is not acceptable. A decision comes with the
   concrete situation backed by fresh evidence, why it matters, how widespread
   it is, three or four real options each with a picture and an effort estimate
   and explicit for/against, a recommendation with reasoning, and exactly what is
   being asked. Deliver it as a document, and pair it with clickable options,
   because typing is painful for him.
2. **An analysis request ends at the analysis.** Do not slide from
   investigating into implementing without an explicit go-ahead.
