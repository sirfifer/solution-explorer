# Enrichment Continuity: the subject playbook and the delta path

Status: design draft, written 2026-08-22 by Fable for owner review. Card 4 of
the enrichment operability program. Nothing here is built; the build cards are
at the end. The design sources are `ENRICHMENT-ENGINE.md` (the ladder this
extends), the first real run's evidence
(`/Volumes/Studio/dev/.evidence/solution-explorer/enrichment-runs/20260822-vscode-unbounded/`),
and the owner's framing of 2026-08-22, quoted where it is load-bearing.

## 1. The reframing this design serves

The full enrichment run is a **bootstrap**: a once-per-subject event whose cost
matters far less than what it leaves behind. Maintenance is **deltas** on a
deliberate cadence (weekly by default, faster or slower per subject as evidence
warrants). The owner's observation that motivates everything below:

> a lot of what we get in the full analysis is a unique understanding of a
> single code base, and doing nothing but some kind of delta operation of the
> same kind seems like we're missing an opportunity. There's an opportunity for
> custom guidance to be one of the work products of the full run that then
> helps the on-demand update.

The first real run supplies the evidence that this works. Its orientation brief
encoded genuinely subject-specific understanding of VS Code: the
common/browser/node/electron runtime-suffix convention, the intended
base/platform/editor/workbench layer order read against the mechanical
120-component cycle, the extension API boundary as a first-class edge, the
instantiation-service DI caveat, and `extensions/copilot/src/util/vs` as a
vendored copy of core utilities. Today that understanding is regenerated per
run, consumed inside it, and discarded. Meanwhile 64 percent of items escalated
past the cheap tier, mostly for grounding failures a subject-aware prompt would
avoid. The waste and the opportunity are the same object.

## 2. The subject playbook

**What it is.** A durable, versioned work product of the bootstrap (and of
every run after it): the distilled, evidence-checked understanding of one
subject that future runs load instead of rediscovering. One file per subject,
`demos/runs/<slug>/playbook.json` plus a human-readable rendering, committed
with the run records so its history is its provenance.

**What it contains.**

| Section | Content | Source |
|---|---|---|
| identity | The frozen subject brief: what this is, who reads the map, what matters, subject criteria | P1 orientation |
| idioms | Per-area conventions a mapper must know (runtime suffixes, vendored copies, test-scaffolding markers, generated-code zones) | P1 brief + P3 adjudication + P5 lessons |
| corrections | Deterministic-layer misclassifications the contract caught, with evidence (the "facts say Next.js, it is not" class) | E5 records |
| grounding map | Which question classes ground easily per component class, and which idioms caused E1/E2 escalations, so 2a prompts pre-empt them | Run lessons + escalation records |
| calibration | Measured per-call cost and wall figures, escalation rates, partition sizing that worked | The run ledger |
| coverage anchors | The architecture-level artifacts (tours, narrative, criteria) and the component sets they rest on, for the delta path's re-evaluation rule | P4/P5 outputs |

**The disciplines that keep it an asset instead of a rot vector.** These are
requirements, not notes; without them the playbook is confirmation bias by
construction, and a wrong idiom entry would propagate into every future update
with confidence.

1. **Citation or absence.** Every playbook entry carries evidence the no-AI
   validator can check, exactly like an enrichment claim. An entry that cannot
   cite does not enter. The validator runs on the playbook at write time and at
   load time (the repo moved; the citations may not have).
2. **Continuously re-earned.** Every delta run's adjudication sample includes
   playbook-derived claims alongside fresh ones. The playbook is treated as a
   set of standing claims under the same scrutiny as any other claim, never as
   ground truth.
3. **Decay is visible.** Each entry records which run last reconfirmed it.
   Entries unconfirmed for N runs (default 6) are flagged decaying in the
   playbook itself and excluded from prompt guidance until reconfirmed. A
   decayed load-bearing entry is a signal to schedule a re-bootstrap.
4. **Re-bootstrap is scheduled reality, not theory.** A full fresh run per
   subject on a slow calendar (quarterly, or on a major-version boundary of
   the subject), producing a fresh playbook that is DIFFED against the old
   one. The diff is itself evidence: what the codebase's understanding-shape
   changed is exactly what a maintainer wants to know.
5. **The product never sees the playbook.** It is run-side context, like the
   contract scaffolding. Nothing from it reaches a projection except through a
   normal, validated, adjudicated enrichment claim.

## 3. The delta path

**Trigger and scoping, fully deterministic.** The store is content-hashed and
incremental; a delta run derives its scope mechanically: components whose
files changed since the last enrichment provenance, plus their blast-radius
neighbors from the design-signals graph (both directions, bounded depth),
plus anything whose enrichment provenance predates a decayed playbook entry
it depended on. No model chooses the scope.

**Execution rides the work-order machinery.** A delta run IS a work order
(T9): scope, lens, criteria, expected effect, budget. The `include_ids`
partition path exists and is tested; results re-enter the contract and
adjudication exactly like bootstrap results. What card D adds around it:

1. P1 is replaced by loading the playbook (no orientation spend).
2. 2a prompts carry the playbook's idioms and grounding map, which is where
   the escalation-rate reduction comes from.
3. Adjudication samples: fresh claims, playbook-derived claims (discipline 2),
   and a small sample of UNCHANGED items as drift detection, so rot in
   untouched areas is caught cheaply instead of never.
4. **The architecture-level re-evaluation rule.** Component-scoped updates can
   silently stale whole-system artifacts. Any tour, narrative section, or
   determination criterion whose coverage anchors intersect the delta scope is
   re-evaluated in the same run; a tour step that no longer cites cleanly is
   repaired or the tour is marked stale, never left asserting a walk that no
   longer exists.
5. The census and Run Report are per-delta, and the projection refresh follows
   the normal pipeline.

**Cadence and economics.** Default weekly per published demo. The bootstrap's
measured ledger gives the per-call figures; after the first real delta the
projection in the dry run states the expected per-delta cost for THIS subject,
and the owner sets cadence per subject from measured numbers rather than
guesses. Design intent, to be validated: a quiet week on a large subject
should cost low single-digit dollars API-equivalent, because scope is a
handful of components and orientation is free.

## 4. Supervision, applying the observability contract

Delta runs and bootstraps run under the same rules card 1 established: the
streaming ledger is the observability channel, the wall and cost ceilings are
armed, and a supervising session (Fable-class, near-zero context) watches the
stream. The supervisor's boundary, restated from the quality review: it may
pause, stop, and alert; it may never modify prompts or work products mid-run.
Calibration changes happen between runs, reviewed.

## 5. What this design declines

- No global quality score for a subject, and no playbook entry that is a
  judgment without evidence. The playbook holds facts and tested guidance,
  not vibes.
- No self-modifying prompt loop. The playbook feeds prompts through a fixed,
  reviewed template; a run cannot rewrite its own instructions.
- No delta shortcut into the product. Every projected claim, bootstrap or
  delta, passes the same contract, validation, and adjudication.

## 6. Build cards

| Card | Size | Content |
|---|---|---|
| D-A playbook emit | M | P5 gains a final playbook-assembly step: brief + lessons + corrections + grounding map + calibration, validator-checked, written beside the run records with provenance. Diff rendering against the prior playbook. |
| D-B playbook load | S | Delta and bootstrap runs load and validate the playbook; 2a/2b prompt assembly gains the idioms and grounding-map sections (offered, bounded, like the design digest). |
| D-C delta scoping | M | The deterministic scope derivation: provenance diff, blast-radius neighbors, decay-triggered inclusions. Dry run prints the scope and its projection. |
| D-D delta execution | M | The work-order-based run mode: no P1 spend, adjudication sampling per discipline 2 and 3, the architecture-level re-evaluation rule, per-delta Run Report. |
| D-E cadence wiring | S | Registry `delta` block (cadence, budgets), harness `refresh` uses the delta mode when a playbook exists, the hub shows per-delta receipts. |

Order: D-A and D-B land with or immediately after the bootstrap (the bootstrap
produces the first playbook). D-C through D-E follow before the second weekly
refresh, so demo one's maintenance never runs a second bootstrap by default.
