# Rearchitecture kickoff: personas, validation strategy, and target proposal

Date: 2026-08-25. Author: session following the killed VS Code enrichment run.
Companion to `ENRICHMENT-REARCHITECTURE-PLAN.md` and the two postmortems in
`postmortem/`. This document reports what was built and what is proposed. No
code was changed and nothing was run.

## The understanding this work proceeds from

The goal is a full, high-quality enrichment of a real project at a cost that
reflects the work, reached only after validation so thorough that a full run
is boring. The 2026-08-25 run is the negative example: projected $1,000+ in
scaled spend for work the measurements price near $90 to $110, killed at ~$44
with 46.5% of that discarded. The mandate has three parts:

1. Quality is the constraint, never the trade. No proposal that lowers
   coverage or accuracy is acceptable, and quality claims are measured, not
   asserted.
2. Efficiency is the objective. The unit is tokens by billing class. The run
   bills through the Claude account, so dollars are scaled stand-ins, and they
   scale honestly.
3. Confidence before scale. VS Code is not attempted again until a graduated
   validation ladder is green and the owner has signed the scorecard.

## Fresh analysis of the findings

The postmortems are unusually strong: three independent reviews, nine wrong
figures caught and corrected, every number re-derived from artifacts. Reading
them together, the central conclusion holds up:

**The 10x cost gap is fully explained by identified defects. No part of it is
the price of quality.** The blowup is several independent multipliers stacked:

- Reasoning tax: inherited xhigh effort made billed output ~4.5x the delivered
  product; 67.8% of billed output tokens were thinking, and effort bought
  citation count and prose length, not coverage.
- Duplication: the partitioner produced each component 3.52 times and kept
  whichever answer landed last. Three of the die rolls were pure waste.
- False escalation: the symbol validator rejected 93% of valid citations, so
  the relationship escalation rate was 47% where 12% is correct. That single
  bug routed roughly a third of the graph to the most expensive rung, about
  $450 of the projection, and is the true answer to "why did Opus do most of
  the work". The work was not hard.
- Waste on failure: overflow at the output ceiling triggered silent
  continuations billed at the 2x cache-creation rate, and 46.5% of actual
  spend was then discarded even though all of it was mechanically
  recoverable.

The multiplication is the insight. None of these factors alone makes $1,000
from $90; four of them compounding does. And critically, the expensive
configuration was also the lower quality one: 113 of 173 partitions were
projected to overflow, 10 of 31 completed partitions were thrown away, and
failed components vanished from the census rather than surfacing as
unresolved. Cheap and correct are on the same side.

One instinct from the owner deserves confirmation because the data proves it:
the "conservative overlap" reflex, the idea that more context and more
thinking must yield better results, is measurably false here. The clearest
example is the duplicated evidence channel: 71% overlap between two evidence
arrays where the validator needs exactly one valid citation. Paid redundancy,
mechanically worthless.

### What is verified and what is still assumption

| claim | status |
|---|---|
| xhigh effort caused the overflows; low is stable, 73% cheaper, equal or better coverage | measured, controlled replay on 4 real prompts |
| validator bug drives relationship escalation 47% -> 12% | measured over 1,215 citations, recomputed through the real validator |
| 3.52x component duplication | reproduced against the real store |
| 73.2% of output is scaffolding; evidence arrays 31.3% and pure transcription | measured over 32 transcripts |
| rung 2b economics (~$670 baseline, ~$100 fixed) | estimate, ±30%, run died before 2b |
| rung 2c cost | unmeasured, structurally unbounded in current design |
| batch 15 at rung 2b | hypothesis, needs sample validation |
| medium effort | evidence of instability, two probes disagreed sharply |
| tier C total ~$110 | model fitted on 31 real calls, unvalidated end to end |

Everything in the bottom half is exactly what the validation harness exists to
convert into measurements.

## The three personas

Built, in `docs/quality/personas/rearchitecture/`:

- `_COMMON.md`: binding ground rules. Quality as constraint, rules of
  evidence at the postmortem standard, account framing, artifact map, and the
  adversarial-review protocol among the three.
- `ORCHESTRATION-ARCHITECT.md`: owns rung boundaries, routing, escalation
  protocol, handoff format, batch sizing, checkpointing, and the per-rung cost
  model. Treats escalation as a priced failure. Deliverable:
  `docs/quality/rearchitecture/ORCHESTRATION-SPEC.md`.
- `PROMPT-CONTEXT-ENGINEER.md`: owns every prompt, schema, and the context
  and caching shape. Evidence by reference, implicit defaults, structural
  output enforcement, per-rung effort pins. Deliverable:
  `docs/quality/rearchitecture/PROMPT-SPEC.md`.
- `QA-VALIDATION-ENGINEER.md`: the third persona the owner asked for, a QA
  automation engineer for AI agent systems. Owns the definition of "extremely
  high confidence" as executable checks: the telemetry contract, preflight
  gates, in-flight tripwires, machine-readable run scorecard, a zero-cost
  replay corpus built from the killed run's own transcripts, the graduated
  gauntlet, and the quality baseline. Deliverable:
  `docs/quality/rearchitecture/VALIDATION-PLAN.md`.

The QA persona is deliberately first among equals: the other two produce
designs, and no design claim survives without the measurement that could
falsify it. This mirrors how the postmortems themselves reached reliability.

## How to use them

- **Phase 1, parallel drafts.** Architect and Prompt Engineer draft their
  specs from the postmortems, the code, and the recorded transcripts. QA
  drafts the validation plan and telemetry contract. Near-zero live cost; the
  only live spend is the postmortems' own "do first" probes (validator-fix
  escalation recount, effort probe across five partitions), under $10.
- **Phase 2, adversarial convergence.** The two designers review each other's
  spec hunting for wrong numbers; QA runs the testability pass on both. Output
  is a unified architecture spec plus validation plan, presented to the owner
  for approval before implementation.
- **Phase 3, implementation behind the harness.** The known postmortem fixes
  land first (effort pin, success-path stop_reason and num_turns, ceiling
  assertion, salvage, ladder retry, per-partition checkpoint, validator fix),
  then the redesign. The no-regression protocol applies throughout.
- **Phase 4, the gauntlet.** Level 0 replay (free), Level 1 micro live run,
  Level 2 full run on the validation subject, Level 3 capped VS Code canary
  and then the full run, each level gated on the previous one's scorecard and
  Level 3 gated on owner sign-off.

Mechanically the personas run as subagents seeded with their brief files, and
every deliverable lands in `docs/quality/rearchitecture/`.

## Validation target proposal

The owner picks; this is the recommendation with alternatives.

**Recommended: a whole, small, diverse project (option A), with the capped VS
Code canary kept as the Level 3 entry step.** Sectioning VS Code as the
primary gauge (option B) answers the wrong question: a slice can never show
whole-project behavior, which is where this run actually failed (census
coverage, importance ordering, absorption, end-of-run banking). The capped
canary form of B is still valuable and is retained at Level 3, where partition
capping plus budget ceilings need no new machinery.

Candidates for the Level 2 subject, in preference order:

1. **UnaMentis (start with the server repo).** Ground truth already exists:
   the comprehension study ran against it, the owner knows it deeply, and the
   viewer has already faced it. Diverse stack across the engagement's repos.
   Caveats: the deterministic gate must pass on the chosen repo first, and its
   graph is smaller than ideal for stressing partitioning.
2. **solution-explorer itself.** The strongest possible ground truth, since
   contract accuracy can be scored authoritatively. Caveats: Python-heavy, so
   less tier diversity, and self-analysis can flatter idioms the tool grew up
   with.
3. **A fresh mid-size open source project** picked by /repo-story for tier
   diversity and a 50 to 150 component census (the shape of Gitea, Outline,
   or Focalboard). The best dress rehearsal for an arbitrary customer repo.
   Caveat: no ground truth exists until we build it.

Scale check: at the tier C model, VS Code (569 components, 5,453
relationships) projects to roughly $110, so a 60 to 120 component subject
projects to roughly $10 to $25 for a full Level 2 run, and Level 1 is single
digits. These are estimates and are themselves gauntlet predictions to verify.

## State of the branch

`deterministic-gate-hardening` already carries part of the answer: the
systemic-failure circuit, deliberate run records, honest-gap reporting, live
run telemetry, and a soft per-run cost ceiling. Still open from the postmortem
fix list: the effort pin, stop_reason and num_turns on the success path, the
0.85/1.0 output-ceiling gate, salvage on parse failure, the ladder's missing
parse retry, per-partition checkpoint absorption, the validator fix, and
unconflated cache accounting. The personas are instructed to verify against
current code rather than assume the postmortem's snapshot.

## Explicitly not done

No personas have been run, no code changed, no live calls made, no target
registered. Next step is the owner's call on the report and the target.
