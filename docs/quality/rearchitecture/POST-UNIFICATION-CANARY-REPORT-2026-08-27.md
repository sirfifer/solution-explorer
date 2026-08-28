# Post-unification live canary report

Date: 2026-08-27 (US/Pacific)

Reviewed baseline: `2c01ee0398acf1be95c38ab6082d6b194a6ab53c`

## Current validation addendum

This addendum supersedes the historical executive verdict and next-gate list
below. The failure narrative is retained because it is the evidence for the
repairs, not because those defects remain open.

- A third live polyglot canary completed 48 of 48 calls successfully at $3.781031
  API-equivalent, with 11 of 11 targets grounded, all eight predeclared criteria
  met, one measured improvement round, final determination `done`, and
  disagreement reduced from 22.6% to 9.7%.
- The current adversarial audit of that artifact passes with no findings. Its
  report file embedded the preceding 29-token cache-estimation false positive
  because the tokenizer tolerance was corrected after the run; rerunning the
  current auditor records zero prefix shortfalls.
- The duplicate-purchase, partial-product conservation, unknown-criterion,
  avoidable-gap, schema-boundary, cache-estimation, and completion-settlement
  defects described below now have deterministic regressions.
- The output contract was reviewed again for quality pressure. Fixture-specific
  repair wording and shortest-answer optimization were removed; repairs now
  preserve every supported useful meaning and constrain claims by evidence, not
  vocabulary or terseness.
- The exit-learning seam is now explicit. Fable receives a compact digest of
  measured calls, models, tokens, cache use, response bytes, cost, wall time,
  retries, failures, escalation triggers, and parser-first cards. It returns a
  bounded evidence-based `run_analysis` containing deterministic-transfer
  candidates, process improvements, and signals to compare on the next run.
  The complete ledger, accounting, findings, and adjudication remain
  deterministic and authoritative; the digest does not replace or truncate
  them.
- Current verification: repository-wide Ruff passes; `git diff --check` passes;
  the complete suite reports **2,278 passed, 4 skipped, 1 expected failure**.

No UnaMentis source or store data has been sent to a model during this review.
The remaining live gate is a bounded provider validation of the revised Fable
exit-analysis contract, followed by the already-preflighted one-partition
UnaMentis run. Sending the partition's repository-derived facts to the external
Claude provider requires the owner's explicit approval.

## Executive verdict

**STOP. Do not run an UnaMentis partition or a full UnaMentis enrichment yet.**

The transport and cache repairs are real: both paid polyglot runs had zero failed
calls, stayed inside the temporary $3 test guard and delivered-byte budgets, used
one turn per call, and showed no cache-boundary failures. The second run ended at
$2.2306. That temporary guard is not a recommended production policy; see
"Budget and pause policy" below.

The product is nevertheless not release-ready. A live schema drift caused the
entire eight-component Sonnet batch to be purchased twice; the audit correctly
failed the post-run whole-ladder output-density target at 804.9 billed tokens per
unique target against 500. A work-order delta then overwrote the retained
three-to-five-sentence product narrative with the two repaired sentences. The
final determination also carried one unknown subject criterion and the final
census contained an avoidable honest gap on a fixture the pipeline should be
able to map completely.

Those are orchestration and product-integrity defects, not tuning noise. The
UnaMentis canary sequence stopped before any UnaMentis model call.

## Deterministic verification

- Scoped Ruff (`analyzer`, `scripts`, `tests`): pass.
- Focused enrichment/audit suite after contained fixes: 71 passed.
- Full suite: **2,241 passed, 4 skipped, 1 expected failure** in 156.64 seconds.
- Repo-wide Ruff is not clean because two pre-existing archived measurement
  scripts under `docs/quality/rearchitecture/data/` contain 11 style findings.
  They were not modified because they are unrelated research artifacts.
- Fresh polyglot extraction: 8 components, 13 files, 255 lines, 33 symbols, one
  relationship, 100% source coverage.
- Fresh zero-cost ladder preflight: pass; one bounded partition, one worker,
  temporary $3 test guard, one forced improvement round.

## Live work and spend

This review made three paid measurements, all explicitly bounded:

| Measurement | API-equivalent cost | Result |
|---|---:|---|
| First full polyglot pilot | $2.3905 | hard fail: completion unknown; undersized escalation sample above the density line |
| Exact one-item Opus repair replay | $0.107634 | delivered payload improved, but hidden reasoning raised billed output to 384 tokens |
| Second full polyglot pilot | $2.2306 | hard fail: duplicate bulk purchase and completion unknown |
| **Total** | **$4.728734** | UnaMentis not invoked |

The exact replay is important: its response shrank from 539 to 411 UTF-8 bytes
and removed the invalid third citation, yet billed output rose from 294 to 384
tokens. That empirically confirms the design document's warning that
provider-hidden reasoning makes a one- or two-item billed-token density gate a
provider-variance test. The 260-token post-run escalation target remains unchanged, but
the contained audit update requires five attempts before that sub-gate can issue
a release failure. Below five it reports the result as explicitly inconclusive;
the exact delivered-byte and 500-token whole-ladder gates still fail hard.

## Budget and pause policy

Owner correction after this canary: **quality and completion outrank a narrow
cost estimate.** A run must not be truncated because it exceeded an estimate by
$0.25, or because a provisional cost model was mistaken. The controls need three
different names and three different semantics:

1. **Expected cost** is a non-binding planning range. Crossing it changes the
   dashboard's forecast color and records a calibration miss; it does not stop
   work.
2. **Efficiency gates** are post-run measurements such as output density, cache
   reuse, duplicate work, and cost per retained target. They can reject a release
   after the evidence exists, but they do not interrupt generation and discard
   the chance to learn why the estimate was wrong.
3. **Runaway protection** is a deliberately generous disaster boundary. It does
   not mark remaining work skipped or manufacture a partial success. It requests
   a durable pause: stop dispatching new calls immediately, allow already-paid
   in-flight calls to finish and bank their usable output, then enter `paused`
   before the next phase, retry, partition, escalation, or work order starts.

For contained calibration tests, expected cost should be displayed but not used
as a stopping boundary. Runaway protection should be disabled or set far above
the expected envelope so it can catch a loop or fan-out explosion without
deciding the test's result. A production pause boundary should not be chosen
until clean partition canaries establish a measured upper distribution. Its
eventual value should sit above that distribution plus the maximum in-flight
reservation, not inside the likely run bracket.

The current `BudgetMeter` is not this design. Reaching `max_cost_usd` makes later
calls refuse to launch and records remaining work as skipped. There is no
persisted operator-resumable state. That behavior is useful as an emergency
legacy guard but is too close to the normal expected cost in the current test
commands and must not be treated as a quality gate.

The same separation applies to output. Per-field lengths and delivered-response
budgets must not be tuned as terse-prose targets. A structural maximum, if one is
required by a decoder or transport, belongs far above the quality-complete
distribution and protects against a runaway response. Crossing it must preserve
the paid payload, salvage usable items, and request a pause; it must not discard
the response or buy the whole batch again. Desired concision and token density
remain post-run measurements.

### Dashboard-controlled pause

The required run-control state machine is:

```text
running -> pause_requested -> paused -> running
                              |       -> cancel_requested -> cancelled
                              +---------------------------> completed
```

The state and operator action must be persisted in the run directory, not held
only in the browser or process memory. Every launch boundary reads it. Resume
continues from the banked store and ledger without regenerating completed work;
cancel preserves all paid results, closes the census honestly, and writes a
terminal report distinguishing completed, in-flight-at-pause, pending, and
unattempted work.

When the disaster boundary requests a pause, the dashboard must present a
decision packet rather than only a red number:

- trigger, configured boundary, actual spend, and when the projection diverged;
- completed, banked, in-flight, pending, retried, failed, and salvaged work;
- spend and output by phase, rung, model, and unique target;
- duplicate-work, cache-read, response-byte, turn-count, and transport-health
  diagnostics;
- current census, adjudication disagreement, honest gaps, unknown criteria, and
  whether any reader-facing product was demoted;
- forecast to finish, including the assumptions and a range rather than a point;
- system assessment: expected variance, likely runaway/loop, provider anomaly,
  or insufficient evidence;
- operator choices: resume unchanged, resume with a higher disaster boundary,
  cancel and publish no result, or cancel and retain the run only as diagnostic
  evidence.

The dashboard at `127.0.0.1:4200` was not running when this addendum was written,
so its live controls could not be inspected. Repository inspection found the
append-only `progress.jsonl` and `ledger.jsonl` observability streams but no
enrichment pause/resume control seam. Those streams are the right inputs for the
decision packet; watching them is not itself a control.

## Second pilot: what passed

- 18 invocations, zero failed calls.
- $2.2306 actual, under the temporary $3 test guard.
- Zero delivered-byte violations.
- Zero non-warm cache misses, prefix read shortfalls, or stable-prefix
  fragmentations.
- Bulk reported 400.9 billed tokens per attempted target against 430.
- Escalation reported 143.0 billed tokens per attempt (three attempts); below
  the 260 line but still smaller than the five-attempt release sample.
- Independent disagreement improved from 33.3% before the forced work order to
  16.7% afterwards, inside the global 20% quality threshold.
- The forced round measurably improved both instruments: `services/api` moved
  from Opus/Fable history back to Sonnet, and disagreement fell from 0.333333 to
  0.166667. The report now records that as a gain rather than claiming nothing
  changed merely because the terminal state remained `grounded`.
- Final store/census conservation passed: eight grounded items and one honest
  gap, no unresolved transport work.

## Hard failures and root causes

### 1. The full component batch was bought twice

The first Sonnet component response contained all eight requested ids and 8,485
bytes of usable JSON. Seven entries were structurally valid. One citation on
`services/api.next` used a redundant provider spelling:

```json
[2, "services/api/api/server.py", "read_user"]
```

The accepted forms are `[file-index, symbol]` or `[exact-path, symbol]`. The
exact path and symbol were both valid, so this is mechanically normalizable.
Instead, `_invoke_parallel` rejected the response and purchased the complete
eight-component batch again before its salvage path became eligible.

Measured duplicate purchase:

- first eight-target call: 3,295 output tokens, $0.136974;
- second eight-target call: 3,367 output tokens, $0.118486;
- relationship call: 153 output tokens;
- combined P2 ladder output after escalations: 7,244 tokens;
- whole-ladder density: **804.9 per unique target**, post-run target 500.

The audit's bulk-only denominator also masks this class of defect: it divides
6,815 bulk tokens by 17 *attempted* targets and reports 400.9. Against the nine
unique product targets, the same bulk output is 757.2. The whole-ladder unique
target gate caught it, but the bulk gate should not call a duplicate purchase
healthy.

Required correction: normalize closed harmless citation aliases; on any other
item-level schema defect, preserve valid siblings after the first response and
retry only the rejected item (or escalate only that item). Never repurchase a
whole valid batch to correct one entry. Ledger and audit denominators must expose
unique targets and re-attempts separately.

### 2. A partial work order degraded the stored product

The work order correctly returned only the two named repairs for
`services/api`: `mechanism` and `purpose`. Contract answers were merged
additively, but compact normalization also constructed a new `help_text` from
only those two delta atoms. `merge_payloads` then treated that sparse product
field as a full replacement and overwrote the previously retained narrative.

The final stored product is only two sentences:

> README states this is an HTTP API service for the polyglot fixture. A FastAPI
> server in server.py defines a GET /users/{user_id} endpoint and binds port
> 8000.

That violates the product's own three-to-five-sentence quality contract and
drops the established place/why meaning from the reader-facing record even
though those answers remain in contract state. Existing no-demotion tests cover
terminal state, not reader-product conservation.

Required correction: merge semantic atoms first and deterministically rebuild
the product once from the merged atom set, or make work-order normalization emit
no aggregate product field for a partial delta. Add a conformance test proving a
two-question repair cannot shorten or erase established reader-facing meaning.

### 3. Completion is still not proven

P5 returned `done`, but subject criterion `s4` remained `unknown`:

> Every factual claim in the map is verifiable in the committed files; nothing
> is inferred from what a system “like this” would normally have.

The unknown is credible, not formatting noise. Final adjudication still rejected
one of six sampled claims: `services/api` was called a relationship-detection
“anchor rather than a load-bearing service.” Edge counts establish the graph
shape but not that interpretation. The global U2 threshold passes at 16.7%, but
this fixture-specific criterion deliberately set a stricter bar. The independent
audit correctly refused publication despite P5's `done` label.

Required correction: keep interpretive judgment out of fact-grounded claims or
label it as judgment and keep it out of an “every factual claim” proof. A `done`
determination with an unknown executable criterion should also settle as
`done-with-reservations`, never plain `done`, even though the external audit must
still fail the release gate.

### 4. The final honest gap is avoidable

`services/web.next_step` ended as an honest gap after Sonnet, Opus, and Fable
because a local fact was repeatedly used to support a global uniqueness claim.
The terminal prompt already instructs the model to remove the global comparison
and state the supported local relationship. On this tiny, fully documented
fixture, an honest gap for that wording problem is evidence that the repair path
did not do its narrow job; it is not missing source evidence.

Required correction: test the E3 narrowing case with the real compact handoff and
ensure the terminal tier can return the local, supported next step without
inventing or declaring a gap.

### 5. Documentation and runtime guarantees disagree

The engagement report says compact schema conformance is enforced during CLI
decoding and recorded as `structured_output_enforced=true`. Current production
code deliberately omits `--json-schema`, validates in process, and all live rows
record `structured_output_enforced=false`. That change was made to avoid the CLI
discarding a paid batch on a harmless schema rejection, but the guarantee and
tests now describe a different boundary than the engagement report.

In-process validation with item salvage can be the correct design, but the docs,
audit predicates, and retry behavior must state and enforce that design
consistently. The present “retry the entire batch, salvage only after the second
failure” behavior achieves neither decode-time enforcement nor efficient
item-level salvage.

## Contained changes made during this review

The worktree currently contains uncommitted, focused changes and tests that:

- remove model-copied inventory counts from executable P1 criteria while
  preserving the coverage bar;
- give P5 the deterministic map inventory and README evidence needed to answer
  subject coverage criteria;
- tell escalation rungs to emit only the named repair delta without imposing a
  new terse-prose character cap;
- record rung moves and independently measured disagreement reductions as real
  iteration gains;
- retain the 260 post-run escalation target while requiring five attempts for a
  statistically meaningful release judgment;
- update the deterministic reference report and add focused conformance tests.

These changes pass the full suite, but they do **not** resolve the five hard
failures above and should be reviewed as a contained partial patch, not committed
as a declaration of release readiness.

## Exact next gate sequence

1. Fix batch-level repurchase and the audit's attempted-target denominator.
2. Fix partial-product conservation for work orders.
3. Make completion settlement truthful for unknown subject criteria and remove
   the remaining unsupported interpretive claim.
4. Add the real E3 narrowing regression test and eliminate the avoidable gap.
5. Reconcile the documented schema boundary with actual runtime behavior.
6. Run the focused and full deterministic suites.
7. Run one fresh polyglot paid pilot with a non-binding expected-cost range and
   only a deliberately generous runaway-pause boundary. It must have one
   component bulk call, one relationship call, no paid full-batch retry, zero
   failed calls, zero avoidable gaps, final disagreement at or below 20%, every
   criterion met, final determination `done`, and audit verdict `pass`.
8. Add persisted pause/resume/cancel control and its dashboard decision packet
   before any large run. Tests must prove a pause banks in-flight success,
   launches nothing new, survives process restart, resumes without duplicate
   generation, and cancels with an honest terminal report.
9. Only then run one scoped UnaMentis partition, followed by two partitions if
   the first is clean. Do not use the expected-cost estimate as a stopping
   boundary. Recompute the full-run forecast and the generously separated
   runaway-pause boundary from the measured acceptance, retry, escalation, and
   work-order distributions.
