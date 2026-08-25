# QA Testability Pass and Adjudication

Author: QA and Validation Engineer persona. Date: 2026-08-25. Phase 2, step 1.
Specs under review: `ORCHESTRATION-SPEC.md` and `PROMPT-SPEC.md`, with their
`data/` artifacts. Method: the claim taxonomy of `VALIDATION-PLAN.md`
section 10. Zero live model calls; every measurement here is offline from the
reconciled corpus (`data/replay-corpus.json`), the 16 replay probe transcripts
located this pass, the ledger, the real VS Code store, and the installed CLI
binary. New measurements are committed machine-readable at
`data/qa-adjudication.json`.

Verdict vocabulary, refining the taxonomy's three outcomes:

- **verified (confirmed)**: re-derived offline, agrees.
- **verified (falsified)**: re-derived offline, disagrees; mandatory revision.
- **testable (probe named)**: cannot be settled offline; the spec names the
  probe and its cost, which is acceptable.
- **testable (offline, not yet run)**: settleable at zero cost with the
  existing harness; should be run rather than probed live.
- **untestable as stated**: no measurement could prove it wrong as written;
  mandatory revision in step 2.

## 0. A correction to the review's own inputs

Both specs cite "35 recorded run transcripts". The reconciled corpus resolves
this exactly: 32 partition calls plus 4 killed-in-flight sessions, of which
one (`5d5bb368`) has no assistant turn, gives 35 sessions with recorded
first-turn usage. The figure is right; the derivation belongs on the record.

This pass also located the replay probes both specs lean on: 16 transcripts,
9 under the scratchpad-cwd project directory and 7 under `-private-tmp`,
identified by first-user-message hash against the killed-run prompts. They
cover 5 killed-run prompts plus one unidentified small prompt. Efforts are
not recorded anywhere in them; labels are recovered only by matching billed
output to the postmortem's published numbers (the 4 low probes, the 2 medium
probes at 4,518 and 10,820, the c95c2999 high probe at 23,948 all match
exactly). Five probes carry no recoverable effort label at all. The
telemetry contract's `effort` field exists precisely so this recovery is
never needed again, and probe runs must ledger their argv like any other run.

---

## 1. Adjudication 1: output chars per billed token

**Verdict: the Prompt Engineer is sustained, with one refinement. The
adjudicated constant is 2.85 chars per billed token for marginal prompt
content, plus a separate per-call fixed prompt-side overhead of 10k to
12.5k tokens.**

Measured over all 35 first turns (`data/qa-adjudication.json`,
`dispute1_rows`):

- Least-squares fit of first-turn billed prompt-side tokens (input +
  cache_creation + cache_read) on exact first-user-message chars:
  **slope 0.34652 tokens per char (2.886 chars per token), intercept 12,546
  tokens, maximum residual 6.32%** across all 35 points, retry outlier
  included.
- Spot check, fit-free: `c95c2999` billed 39,243 marginal tokens (input 2 +
  cache_creation 39,241) for 106,558 chars: **2.72**, exactly the Prompt
  Engineer's number.
- **The Architect's 1.71 is reproduced exactly** as the per-session mean of
  chars divided by ALL prompt-side tokens including cache reads: mean 1.711,
  median 1.670. That is the source of the discrepancy, named: 1.71 is an
  average total ratio that folds the CLI's fixed prompt-side overhead (its
  own system prompt, read from cache every call) and the cache reads into
  the per-char rate. It is not a marginal rate, and pricing marginal volumes
  (fact blocks, handoffs) with it overstates their tokens by 2.85/1.71 =
  **1.67x**.
- The refinement the Prompt Engineer's spot check glosses: the ~10-12.5k
  fixed prompt-side tokens per call are real and must be priced per call
  (mostly at the 0.1x cache-read rate after warm). Their own fit's intercept
  (10,021) already does this; the Architect's model has no such term because
  1.71 smeared it into every char.

Consequence for `cost-model.py`: `CT`, `COMP_FACTS_TOK` (506k becomes about
304k), `REL_FACT_TOK` (335 becomes 201), `COMP_FACT_MEAN` (1,451 becomes
871), and `PREFIX` (12.3k becomes about 8.7k) all move. Partially offsetting:
the model prices fact input at the 1x input rate, while the transcripts prove
per-call unique content bills as 1h cache creation at 2x (see section 3).

## 2. Adjudication 2: fixed output per call at low effort

**Verdict: the Prompt Engineer is sustained on the decomposition. The
ill-conditioning claim is confirmed exactly. The adjudicated constants are
1,050 per component, 382 per relationship, 1,369 fixed per call (bounds 500
to 2,800), tier B at low effort.**

Re-derived from the four low-effort replay probes, whose identities and
usage this pass verified against the transcripts (points are (components,
relationships, billed output)): (11, 39, 29,115), (2, 40, 18,963),
(10, 40, 25,693), (2, 16, 9,527).

- **The 3-point fit is ill-conditioned, exactly as claimed.** The three
  larger probes have relationship counts 39, 40, 40. Solving those three
  equations exactly gives per-component 841, per-relationship **−2,581**,
  fixed **120,510**. The negative relationship coefficient the Prompt
  Engineer predicted is the exact solution, not a fitting accident: with the
  relationship count essentially constant, the relationship coefficient and
  the intercept are one free parameter wearing two names.
- The fourth point (c95c2999-low, 16 relationships) conditions the system.
  Least squares over all four: **1,050 per component, 382 per relationship,
  1,369 fixed, maximum error 5.7%**.
- The Architect's published 1,100/320/4,400 fits the three points it was
  built on within 10% and **misses the held-out fourth point by +23%**. That
  is precisely the C2 failure mode the taxonomy exists to catch: a
  calibrated projection with no held-out validation.
- Direct thinking measurement, char method: pure-JSON probes cluster at 2.63
  to 2.75 chars per billed output token; against that reference, the four
  low probes' thinking is approximately 335 / 455 / 32 / 0 tokens. This
  sits inside, and at the low end of, the Prompt Engineer's 0 to 1,507
  band, and nowhere near 4,400.

**Honest remaining uncertainty that only live probes resolve:** n=4, one
subject, one model, one schema. The per-relationship coefficient is 382 here
against the Prompt Engineer's block-mean 313 (22% apart; their block means
underpredict two of the four probes by 10 to 15%). Nothing at all is
measured for Opus or Fable thinking at low effort, and the new-schema block
sizes are transforms, not observations. M-1, M-2/M-P3, and M-P1 are the
resolving probes and remain necessary.

## 3. A third falsified constant, found by this pass: the Opus and Fable prices

Neither designer flagged this as a dispute, and it is worth more dollars
than either dispute they did flag. The Architect's model prices Opus AND
Fable at $15/$75 per million ("assumed opus-class from the single p1 fable
ledger row fit"); the Prompt Engineer's uses Opus $5/$25, Fable $10/$50.

**The Architect's own cited basis falsifies their constant.** The one Fable
ledger row (p1 orientation: 19,916 tokens in, 6,688 out, $0.745226) fits
$10/$50 with the observed 1h cache-write billing to within **1.8%**, and
rejects $15/$75 by **47%**. The Sonnet rate is confirmed the same way (row
2 reproduces to 1.6%). No Opus row exists in any ledger, so the Opus rate
is genuinely unresolvable offline: **the first pilot Opus ledger row (an
M-2 row) arbitrates it, and Level 2 sign-off requires that arbitration on
record.** Until then Opus $5/$25 is the working assumption with the 3x
alternative carried as the dominant cost risk.

## 4. The corrected cost model, and the realistic range

`cost-model.py` rerun with the adjudicated constants (chars/token 2.85,
output 1,050/382/1,369, Fable $10/$50, Opus $5/$25 flagged, unique input
priced as 1h cache write per the transcripts; script logic otherwise the
Architect's own):

| | Architect published | corrected |
|---|---|---|
| 2a tier B | $53.7 | $52.8 |
| 2a tier C | $32.9 | $30.2 |
| 2b batch 15 (x0.7 to x1.3) | $50.0 to $62.5 | $16.2 to $17.5 |
| 2b batch 5 (x0.7 to x1.3) | $81.2 to $118.4 | $19.7 to $23.6 |
| 2c (10% to 30% entry) | $13.0 to $39.3 | $8.6 to $25.5 |
| **ladder lo / mid / hi** | **$96 / $115 / $155** | **$55 / $64 / $96** |
| mid, fixed-out at its 500/2,800 bounds | | $59 / $72 |

Two structural consequences:

1. **The corrected Architect model converges with the Prompt Engineer's
   independent model** ($59.4 central, $65.0 conservative). Two different
   model structures now agree within 10%, which is the kind of agreement
   that survives review.
2. **The batch-15 decision shrinks from "a $56 penalty if ignored" to a $4
   to $6 saving.** The claimed penalty was mostly the 4,400 fixed-output tax
   times 125 extra calls times the 3x-too-high Opus output price. M-2's
   economics no longer justify quality risk at batch 15; its remaining value
   is the 2b failure-rate reading (which 2c sizing genuinely needs) and the
   handoff-size measurement. Recommendation: keep batch 5 as default
   permanently unless M-2's parity result is clean AND someone still wants
   the ~$5.

**Realistic ladder range in light of all adjudications: $55 to $95, central
about $65.** The spread is now dominated, in order, by: the unarbitrated
Opus price (about $25 swing at 3x on 2b, plus 2c if Fable-class pricing were
also wrong, which the ledger row makes unlikely), tier C schema landing
(about $22 swing, M-P1/M-4), the 2c entry fraction (about $17 swing, M-2),
and Opus/Fable thinking at low (about $10, M-P3). With P1 measured at $0.75
and P3 to P5 estimated $10 to $20 (M-7), **a full run lands at roughly $70
to $115, central about $80**, against the plan document's $90 target and the
killed configuration's $1,000+.

## 5. Verification requests V-1 to V-7, dispositions

- **V-1 (re-run the cost model, check [S] figures): done.** The script runs
  and reproduces its published table. The structural [S] figures were
  re-derived independently this pass and are exact: 569 components, 5,453
  relationships, 173 partitions, 2,003 component slots, 55 groups, 3.52x
  duplication. The cited ledger figures check exactly (max tokens_in
  119,352 with 72,982 cached; mean 2a tokens_cached 22,960). Three
  constants are falsified: sections 1 to 3 above. The `cli/src/util`
  capability-detail defect is confirmed in substance: 354,743 chars of
  `detail_json` measured under `cli/src/util%` against the claimed 372,564
  (scoping difference, same defect).
- **V-2 (deterministic referenced-at index): RESOLVED, better than asked.**
  The store already contains one: `signals` rows with
  `kind='symbol_reference'` (157,508 rows, `{name, count}` with `file_id`
  and `line`). Tested against the 1,162 wrongly rejected symbol citations
  from the corpus: **1,162 of 1,162 covered (100.0%)**. R-5 therefore needs
  no filesystem reads and no loosening: load `(path, symbol)` reference
  pairs in `EvidenceValidator._load`, return a distinct `referenced-at`
  verdict, keep `defined-at` from `_symbols_by_path`. The replay fixture
  (VALIDATION-PLAN 7.2) gains store-only expected verdicts.
- **V-3 (rung-0 identity evidence provenance): PARTIAL.** `framework` and
  `port` have citable signal rows (`file_id` plus `line`). `language` and
  `type` have no per-attribute signal row; rung 0 needs a stated
  derived-evidence convention for them (dominant-extension census, manifest
  row) before R-14 lands. The spec's open dependency is real and now has a
  named answer for half its fields.
- **V-4 (telemetry gate, merge-property test): accepted into the plan**
  (addendum, VALIDATION-PLAN section 13), including the Prompt Engineer's
  `prefix_hash` and cache predicates, with thresholds to be set from M-P1's
  rows rather than invented.
- **V-5 (recompute harness as permanent fixture): accepted;** it is
  VALIDATION-PLAN R2/R6 extended with the referenced-at verdicts from V-2.
  Two flagged estimates are computable on it offline now, no probes needed:
  the failed-questions-per-item distribution (the 1.5/1.0 estimate) and the
  2b population under the new rules (M-P5). Scheduled as harness runs, not
  live probes.
- **V-6 (cache TTL class per call): RESOLVED at the API layer.** The
  transcripts' usage blocks carry
  `cache_creation.ephemeral_1h_input_tokens` and
  `ephemeral_5m_input_tokens`; the killed run's writes were 100% 1h class.
  Whether the CLI's stdout envelope forwards the breakdown is the one
  remaining sliver, folded into the Level 1 envelope capture.
- **V-7 (adversarial check of both calibrations): done;** sections 1 and 2.

Also verified while inside V-1's scope: every CLI-capability string the
Prompt Engineer's section 7 rests on is present in the installed 2.1.220
binary (`json-schema`, `append-system-prompt-file`, `effort`,
`structured_output_retry_exhausted`, `structuredOutputAttempts`), by string
inspection, consistent with their method.

## 6. Testability pass: ORCHESTRATION-SPEC

Classification of every quantitative and quality-neutrality claim, grouped
where one verdict covers a family. Types per VALIDATION-PLAN section 10.

| # | claim (section) | type | verdict |
|---|---|---|---|
| O-1 | headline $96-155 / $115; full run $110-175 (0) | C2 | verified (falsified): corrected $55-96 / $64; section 4 |
| O-2 | swing ranking, incl. "batch $56 penalty" (0) | C2 | verified (falsified): batch swing is $4-6; ranking reorders (Opus price now first) |
| O-3 | landed / not-landed code register (1) | C1 | verified (confirmed); matches my independent register, line-exact |
| O-4 | fact-block defect: 372,564 chars, 339k-token group, 632,861-char prompt, ledger 119,352/72,982 (1) | C1 | verified (confirmed): 354,743 chars measured (scoping delta); ledger figures exact; prompt size corroborated by the Prompt Engineer's independent max 217,026 scaled tokens x 2.9 chars/token |
| O-5 | rung table: call counts 55/100/63, worst outputs 37.4k/30.0k/11.6k (3) | C2 | call counts verified (confirmed) via independent re-derivation; output numbers move under adjudicated constants (worst 2a-C becomes ~32.9k) but every no-overflow conclusion survives with more margin |
| O-6 | route-only 2a rejected, "input about $8 either way" (3.1) | C2 | structure verified (confirmed): the hidden second pass is real; dollar figure falsified (about $4.5 corrected); conclusion unchanged |
| O-7 | deterministic replacements 1-9 with measured sizes (3.2) | C1/C4 | verified (confirmed); item 2's open dependency now resolved by V-2/V-3 |
| O-8 | batch_max formula and derived bounds (3.3) | C2 | testable (probe named, M-2); bounds recompute mechanically under adjudicated constants |
| O-9 | "no merging of small groups: group coherence is worth more than the saving" (3.3) | C3 | **untestable as stated**: no metric, no probe; either name the coherence measurement (census/spot-check delta on merged versus unmerged groups inside M-4) or restate as a design preference, which requires no evidence |
| O-10 | "attention dilution... a quality property only the sample shows", M-2 "parity" (3.3, 9) | C3 | **untestable as stated** until "parity" is defined; mandatory: bind to a metric (identical verdict distribution on the recompute harness plus blind spot-check equality per VALIDATION-PLAN section 9) |
| O-11 | wall time 150-300s/call, about 3h (3.4) | C2 | testable (M-1 and Level 1 measure it; basis stated) |
| O-12 | handoff 750/400, delta 480/145 (4.3, 5) | C2 | testable (probe named, M-2); the failed-questions distribution beneath it is testable offline now on the V-5 harness and should be |
| O-13 | parameter table: CT 1.71; comp facts 506k; rel fact 335; prefix 12.3k (5) | C1 | verified (falsified): 2.85 marginal; 304k; 201; 8.7k; section 1 |
| O-14 | parameter table: out fit 1,100/320/4,400 (5) | C2 | verified (falsified): 1,050/382/1,369; section 2 |
| O-15 | parameter table: fable pricing "opus-class" $15/$75, M-8 (5) | C5 | verified (falsified) by its own cited ledger row (section 3); and M-8 as stated ("fit any two fable rows") is **untestable as stated**: four unknown rates against two equations is underdetermined; replace with price-sheet assertion verified against pilot rows (the Prompt Engineer's M-P7 method) |
| O-16 | escalation populations 284/654 (comp 50%, rel 12%) (5) | C1 | verified (confirmed) as the postmortem recompute; re-verifiable offline on the V-5 harness under the new rules (scheduled, M-P5) |
| O-17 | Opus fixed-reasoning ±30% (5) | C6 | testable (probe named, M-3) |
| O-18 | 2c entry 10-30%, worst case "$131" (5, 6) | C2 | testable (M-2); worst-case dollar falsified in magnitude (about $84 corrected); the slice logic survives |
| O-19 | cross-checks against efficiency-pm tiers (5) | C1 | verified (confirmed) for 2a tier C (still agrees after correction); the 2b reconciliation dissolves under corrected prices and should be redone |
| O-20 | checkpoint loss bound about $1.60; commutativity claims (7) | C2/C4 | testable: loss bound at Level 1 kill test; commutativity is the R6 census-conservation and V-4 merge-property tests |
| O-21 | cache expectations: thresholds 15%/25%/20%, "mean cached 22,960", TTL narrative (8) | C1/C2 | the 22,960 verified (confirmed) exactly; thresholds testable (M-6 on M-P1 rows); TTL class verified (confirmed) via usage fields (V-6) |
| O-22 | quality table rows (9) | C3 | all name a measure; two inherit the O-10 parity-definition gap |
| O-23 | experiment cost bounds M-1 to M-8 under $20 (10) | C2 | testable; bounds are estimates with stated scales |

ORCHESTRATION-SPEC totals: 23 claim families reviewed. **Verified
confirmed: 9. Verified falsified: 6 (O-1, O-2, O-6 dollar figure, O-13,
O-14, O-15 price, O-18 dollar figure counted once each). Testable with
named probe: 6. Untestable as stated: 3 (O-9, O-10, O-15's M-8).**

## 7. Testability pass: PROMPT-SPEC

| # | claim (section) | type | verdict |
|---|---|---|---|
| P-1 | fit 1.5829 / 10,021 / max resid 1.95% (0) | C1 | verified (confirmed) by independent char-side fit (2.85-2.89 slope, intercept 12.5k, spot 2.72 exact); note: their script needs tiktoken, absent in this environment; the vendored per-session points in `prompt-tokenizer-fit.json` keep it re-derivable, keep vendoring |
| P-2 | block measurements: 1,861/387 xhigh over 43+822 blocks from 26 sessions (0) | C1 | verified (confirmed) within the stated 5-11% of the postmortem baseline; revision note: state the session-selection rule that yields 26 (the reconciled corpus has 31 parseable), so the count is derivable rather than an artifact of one parser's strictness |
| P-3 | low-effort blocks 1,298/313; envelope 483-1,323; thinking 0-1,507 (0) | C1 | verified (confirmed); my adjudication puts total fixed at 1,369 and thinking at 0-455 on the same probes |
| P-4 | new-schema 1,263/153 measured transform; central 880/124 (0, 6, 9) | C2 | testable (probe named, M-P1); transform verified against committed artifacts |
| P-5 | citation mapping 164/66/8 of 238; 1,530 of 1,533 (0, 6) | C1 | verified (confirmed) against `prompt-projection-results.json`; consistent with the postmortem's larger-sample 100.0%/96.7% |
| P-6 | marker rates 100% / 32.6% / 46.5% (0) | C1 | verified (confirmed) against committed artifact |
| P-7 | baseline 2a input 4.056M / 23,446 / 217,026; prefix 5,539 (0) | C1 | verified (confirmed) against committed artifact; max corroborates O-4 independently |
| P-8 | prices: Sonnet 3/15, Opus 5/25, Fable 10/50 (0) | C5 | Sonnet and Fable verified (confirmed) against ledger rows (1.6% and 1.8%); **Opus is unverifiable offline and is now the top cost risk**; testable (first pilot Opus row, and M-P7); mandatory: mark Opus 5/25 as flagged in the spec, symmetrical with every other flagged constant |
| P-9 | prefix sizes 4,226 / 2,677 / 2,984 / 2,745 (2, 4, 5) | C1 | verified (confirmed) via committed script outputs |
| P-10 | CLI capabilities: `--json-schema`, structured-output path, `--effort`, `--append-system-prompt-file` (7, 10, 11) | C5 | verified (confirmed) by independent binary string inspection; the client-side-versus-API question and retry cost remain testable (M-P4) |
| P-11 | worked example: 6,050 in; 11,107 out; 1,592 versus 1,105; 343 versus 155 (8) | C1 | verified (confirmed) against committed fixtures (token figures inherit the tiktoken caveat of P-1) |
| P-12 | per-run table $59.39 / $65.03; zero projected overflow; G2 multiplier 1.00-1.06 plus <= 1.5k (9) | C2 | model verified (confirmed) as computed from its inputs (committed JSON); flagged inputs each carry a named probe; the low-effort multiplier is verified (confirmed) offline by this pass's chars-per-output-token measurement |
| P-13 | cache behavior: run paid 2x on 4.06M; no cross-call prefix reads; large reads are retry duplicates (10) | C1 | verified (confirmed): 1h-class fields in usage; cache_creation equals each call's own message; the retry pair's read pattern matches |
| P-14 | append-file prefix becomes the cached cross-call system entry (10) | C5 | testable, but the probe must be named explicitly: fold an assertion into M-P1 (first pilot ledger must show the section 10 warm/read predicates) rather than leaving the mechanism as prose; revision note |
| P-15 | cacheable minimums 1,024/512 (10) | C5 | testable at pilot; low risk |
| P-16 | effort table: low multiplier; medium banned on 4,518 versus 10,820 (11) | C1/C6 | verified (confirmed); this pass matched both medium probes byte-for-byte in the located transcripts |
| P-17 | quality trades table (12) | C3 | all rows name a measure; one weak metric: "M-P1 human read of pilot blocks" is **untestable as stated** until bound to the blind spot-check protocol of VALIDATION-PLAN section 9 (scored verdicts, not a read) |
| P-18 | failed-questions 1.5/1.0; 2b population holds under new rules (4, 9, M-P5) | C2 | testable (offline, not yet run): both computable on the V-5 harness at zero cost; schedule as harness runs |
| P-19 | probe cost bounds, total under $10 (13) | C2 | testable; estimates with stated scales |

PROMPT-SPEC totals: 19 claim families reviewed. **Verified confirmed: 12.
Verified falsified: 0. Testable with named probe: 5. Testable offline not
yet run: 1. Untestable as stated: 1 (P-17's human-read metric).**

## 8. Mandatory revisions for step 2

For the Orchestration Architect:

1. Replace CT 1.71 with the marginal rate 2.85 plus an explicit per-call
   fixed prompt-side term, and reprice unique input at the 1h write rate
   the transcripts prove (section 1).
2. Replace the output model 1,100/320/4,400 with 1,050/382/1,369 (bounds
   500 to 2,800 on the fixed term) and re-derive every downstream number:
   headline range, batch_max values, worst-call outputs, 2c worst case,
   batch-15 savings (section 2).
3. Replace Opus/Fable $15/$75: Fable $10/$50 (ledger-fit), Opus $5/$25
   flagged pending the first pilot Opus row (section 3). Withdraw M-8 as
   stated; adopt the price-sheet-plus-pilot-verification method.
4. Re-rank the section 0 swing drivers; the batch-15 claim ("single
   cheapest decision", "$56") does not survive correction.
5. O-9: give the no-merge quality claim a metric inside M-4, or restate it
   as a preference.
6. O-10: define "parity" for M-2 and M-4 as a scored metric (recompute
   harness verdict distribution plus blind spot-checks), not a word.

For the Prompt and Context Engineer:

7. Flag Opus $5/$25 as an assumption with its resolving observation (the
   first pilot Opus ledger row), symmetrical with every other flagged
   constant (P-8).
8. P-14: name the probe that proves `--append-system-prompt-file` content
   joins the cached system entry (an explicit M-P1 ledger assertion).
9. P-17: bind "human read of pilot blocks" to the blind spot-check protocol
   (VALIDATION-PLAN section 9) so the verdicts are scored and comparable.
10. State the session-selection rule behind "26 sessions" (P-2), and note
    the tiktoken dependency in the reproduction instructions (P-1).

Neither spec has an unnamed-probe problem anywhere else: the flagged-
assumption discipline both authors used is exactly what the taxonomy asks
for, and it made this review mechanical.

## 8a. Convergence with the cross-reviews

The two designers' adversarial reviews of each other
(`PROMPT-ENGINEER-ON-ORCHESTRATION-SPEC.md`,
`ARCHITECT-ON-PROMPT-SPEC.md`) were published while this pass was in
progress and were not inputs to its measurements. Read afterwards, they
converge with the adjudication independently: the Prompt Engineer's D1 to D4
match sections 1 to 3 here (their corrected-Architect ladder lands at $63.6
after their steps 1 and 2, against this pass's $64 mid), and the Architect's
F-1 makes the same Opus-price objection this pass sustains: $5/$25 is cited
to no artifact and no offline artifact can support it. Three documents now
agree on the resolution: Sonnet and Fable rates are ledger-proven, unique
input bills at the 1h write rate, and the Opus rate is the arbitration the
first pilot Opus ledger row must settle before Level 2 sign-off.

## 9. Consequences folded into the validation plan

Recorded as VALIDATION-PLAN section 13 (addendum): the adjudicated
constants for the G2 gate calibration; V-2's store-only referenced-at
fixture (expected verdicts from `symbol_reference` signals); V-3's
half-resolved provenance with the convention gap named; V-4's merge-property
test and the `prefix_hash` field adopted into the telemetry contract; V-6's
TTL split fields (`tokens_cache_creation_1h` / `_5m`) added to the
contract; the two zero-cost harness runs scheduled (failed-questions
distribution, 2b population under new rules); and the Opus-price
arbitration promoted to a Level 2 sign-off requirement.
