# Enrichment rearchitecture: Phase 1 and 2 findings, plan, and evaluation

Date: 2026-08-25. Status: complete through Phase 2. No code changed, zero live
model calls made; every number below was derived offline from the killed run's
artifacts. This report supersedes the projections in
`ENRICHMENT-REARCHITECTURE-PLAN.md` and builds on `REARCHITECTURE-KICKOFF.md`.

## What was done

Three expert personas were built and run through two phases. Phase 1: each
produced its deliverable independently. Phase 2: the two designers
adversarially reviewed each other, the QA persona independently adjudicated
every dispute from the recorded corpus, both designers revised, and the QA
persona issued a closing verdict. The package is:

- `rearchitecture/ORCHESTRATION-SPEC.md` with `data/cost-model.py`
- `rearchitecture/PROMPT-SPEC.md` with 12 `data/prompt-*` artifacts
- `rearchitecture/VALIDATION-PLAN.md` with the scorecard schema and the
  reconciled replay-corpus inventory
- `rearchitecture/reviews/`: four review documents including the adjudication
  record and the final verdict

QA verdict: **ready**. All falsified and untestable claims reworked or
withdrawn, both cost models regenerate to the cent, four editorial
inconsistencies identified and fixed in the final revision.

## The cost answer

The killed configuration projected $1,000+ in scaled spend and was on track to
fail outright (113 of 173 partitions projected to overflow). Three
independently built cost models, forced through adversarial review onto
adjudicated constants, converge within $6 at the central:

| scaled API-equivalent, VS Code | Opus at $5/$25 | Opus at $15/$75 |
|---|---|---|
| enhancement ladder band | $60 to $95 | $90 to $145 |
| ladder central | $66 | $105 |
| full run band | $71 to $116 | $101 to $166 |
| full run central | $81 | $120 |
| killed configuration | $1,000+ | $1,000+ |

So the realistic expectation is **roughly $70 to $120 for the full VS Code
run, most likely near $81**, a 9x to 12x reduction, at equal or better
quality. The remaining width has three named drivers, each with its closer:

1. **The Opus price constant** (~$39 of central width). The run died before
   Opus ever ran, so no artifact settles it. The first pilot Opus ledger row
   settles it at zero dedicated cost and is a required Level 2 sign-off item.
2. **How much of the schema diet lands** (~$21). Closed by two merged pilot
   probes with a $12 bound.
3. **Rung 2c entry fraction and 2b failure rate** (~$9 to $17). Priors close
   free from a harness recompute; measured for $8.

## Why the old run cost 10x too much

Four multiplicative failures, all verified, none of them "the work was hard":

1. Inherited xhigh effort: 67.8% of billed output was reasoning; billed
   output ran ~4.5x the delivered product; every overflow traces to it.
2. The validator bug: 93% of valid symbol citations rejected, inflating
   relationship escalation from a true 12% to 47%, sending a third of the
   graph to the most expensive model for nothing (~$450 of the projection).
3. The partitioner: every component generated 3.52 times, last write wins.
4. Overflow handling: silent continuations billed at 2x, 46.5% of actual
   spend discarded despite being fully recoverable.

The expensive configuration was also the lower quality one: overflows,
discards, and components vanishing from the census. No quality is being
traded to get the 10x back.

## New defects found in this analysis (in neither postmortem)

- **Fact blocks are capped by count, not bytes**: one partition
  (`cli/src/util`, ~355KB of capability detail) would build a prompt of
  roughly 200k+ tokens, over any context window. Deterministic fix specified.
- **A mean-calibrated output gate is insufficient**: it catches only 7 of 12
  recorded overflows. Output dispersion at xhigh spans 0.72x to 1.90x, so the
  gate must hold worst-case dispersion under the ceiling. All batch sizing in
  the new design is derived from this rule.
- **Salvage must be seam-aware**: naive fence-stripping recovers only 7 of
  10 discarded partitions; the seam-aware variant recovers 10 of 10. Pinned
  as a regression fixture.
- **The validator fix needs no filesystem reads**: the store's existing
  symbol-reference signals (157,508 rows) cover all 1,162 wrongly rejected
  citations. The fix is store-only and preserves the strictness of the check.
- **Envelope fidelity is unproven**: no raw CLI response envelope was
  preserved, so stop_reason and num_turns semantics rest on parsing code.
  Level 1 captures real envelopes before anything depends on them.

## The redesigned pipeline, in brief

- **Rung 2a splits by target kind**: 61 component-group calls (capped at 21
  components by the dispersion rule) and 100 relationship calls. This kills
  the 3.52x duplication and makes per-partition checkpointing safe by
  construction, since each target is written by exactly one call per rung.
- **Static instruction prefixes cache once per rung**; the per-call message
  carries only facts. The caching mechanism is load-bearing and gets a
  Level 1 gate before its savings are booked as real.
- **The schema goes on a diet**: evidence cited by index into menus the
  prompt already supplies, defaults implicit, empties omitted, the four
  transcribed identity answers collapsed to an exception-only flag. The one
  quality-affecting change (relationship evidence defaulting to parser
  evidence) is explicitly disclosed with three mandatory mitigations and a
  zero-cost measurement of fabrication risk before adoption.
- **Escalation carries a delta, not the work**: what was tried, which
  citation got which verdict, and a structured "what the cheaper rung
  lacked" vocabulary, so rungs 2b and 2c do repairs only and every
  escalation teaches the ladder. Rung 2c is bounded ($47 worst case, was
  structurally unbounded).
- **Effort pinned low everywhere**, with the measured basis and a pilot
  check for the models that lack one.
- **Routing stays deterministic.** The plan document's "yes or escalate"
  bulk pass was rejected with math: it hides a fourth pass that re-pays for
  the 70% of items that pass.

## The validation gauntlet and its budget

Nothing runs at scale until each level is green and its scorecard signed:

| level | what | scaled cost |
|---|---|---|
| 0 | replay suites: salvage 10/10, validator corpus, ledger accounting, prompt-shape regression, envelope wiring, census/partitioner | $0 |
| 1 | consolidated probe program: 13 measurements, 8 free, 5 live groups, 33 to 35 calls; proves telemetry, gates, caching, schema compliance, and closes the calibration unknowns | expected $32 to $48, hard cap $50 |
| 2 | full run on the validation subject; cost within tolerance of projection, zero overflows, zero discards, quality at or above baseline; Opus price on record | $10 to $30, cap 1.5x projection |
| 3 | capped VS Code canary ($30 cap), then the full run at the accepted projection, cap 1.5x, on explicit owner sign-off | canary $9 to $25 |

Maximum spend before any medium-scale run: **$50**. Expected total before
the full VS Code run: **$70 to $90, worst case bounded $125 by caps**.

Quality is a measurement throughout: a schema-pinned census in which
vanishing is structurally impossible, grounding validity under the fixed
validator, and a blind spot-check protocol (n=50, scored blind to which
architecture produced the contract, zero tolerance for wrong-on-critical).

## Proposed implementation order (Phase 3, not yet authorized)

1. Telemetry contract and the six replay suites (the harness comes first, so
   every later fix lands with proof).
2. Deterministic fixes, each already specified: effort pin, envelope fields
   on the success path, store-only validator fix, partitioner split by
   target kind, fact-block byte cap, seam-aware salvage, the ladder's
   missing parse retry, per-partition checkpoint absorption, unconflated
   ledger accounting with true target counts.
3. The new prompts and schemas behind structural output enforcement.
4. Preflight gates and in-flight tripwires (dispersion-based output gate,
   drift alarm fed on the success path, cost-deviation stop).
5. The gauntlet, level by level.

## Process evaluation

The adversarial structure earned its cost. Across the reviews: 6 of the
Architect's 23 claim families were falsified and fixed, the Prompt
Engineer's headroom claim was falsified and fixed, two calibration disputes
were settled by independent measurement, an unsourced price constant was
caught before it could distort a decision, and both experts documented
principled rejections rather than folding. Three cost models built three
ways now agree within $6. That is the postmortem discipline applied before
spending money instead of after.

## Decisions for the owner

1. **Proceed to Phase 3** (implementation behind the harness)?
2. **Validation subject** for Level 2. Recommendation unchanged from the
   kickoff report: a whole small diverse project; first choice UnaMentis
   (server repo first), second solution-explorer itself, third a fresh
   registered subject.
3. **Probe budget**: approve the Level 1 program's $50 hard cap (spent only
   after Phase 3 lands, at gauntlet time).

Nothing proceeds until these are decided.
