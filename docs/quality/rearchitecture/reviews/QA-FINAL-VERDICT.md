# QA Final Verdict: Phase 2 closing pass

Author: QA and Validation Engineer persona. Date: 2026-08-25. Phase 2, final
step. Under review: ORCHESTRATION-SPEC revision 2 (changelog section 14,
rejections section 13), PROMPT-SPEC revision 2 (changelog section 16), their
regenerated data artifacts, and both specs against each other. Zero live
model calls; both cost models were regenerated in this pass (section 3).

## 1. Claim closure

Every claim the testability pass marked falsified or untestable is
accounted for in the revisions. The full walk:

ORCHESTRATION-SPEC, falsified claims (6): all reworked.

- O-1 headline range: regenerated from the adjudicated constants
  (changelog 1); the falsified $96-155/$115 is withdrawn and the new bands
  print from `cost-model.py`.
- O-2 swing ranking and the "$56 batch penalty": withdrawn and corrected to
  $5-6 / $16 price-contingent (changelog 2); the ranking now leads with the
  Opus price, which matches the adjudication.
- O-6 "$8 either way": corrected with the falsification kept on record
  (changelog 19); see section 4a for the residual on whose corrected figure
  is right.
- O-13 input calibration (1.71 family): replaced by marginal 2.886 plus the
  12,546-token per-call overhead, unique input at the 1h write rate
  (changelog 3).
- O-14 output model (1,100/320/4,400): replaced by the adjudicated
  1,050/382/1,369 with bounds, falsification recorded (changelog 4).
- O-15/O-18 prices and the 2c worst case: Fable corrected to the ledger-fit
  $10/$50, Opus dual-priced, $131 regenerated to $46.6 (changelogs 5, 23).

ORCHESTRATION-SPEC, untestable claims (3): all closed.

- O-9 group coherence: withdrawn as a claim, restated as a labeled
  evidence-free preference with a named piggyback path onto M-4
  (section 3.3). That is the exact remedy the pass offered.
- O-10 "parity": defined as a two-part scored metric (recompute-harness
  verdict distribution within 2 points and no new trigger class; blind
  spot-check within 8 points at n=50, zero wrong-on-critical), binding for
  M-2 and M-4 (section 3.3).
- M-8: withdrawn as underdetermined; replaced by sheet assertion plus
  pilot-row verification with the Opus arbitration a Level 2 requirement
  (changelog 22).

PROMPT-SPEC, untestable claim (1) and mandatory flags (3): all closed.

- P-17 "human read": bound to the blind spot-check protocol, in both the
  quality table (section 12) and M-P1 itself.
- Opus price flagged and dual-priced everywhere (F-1; section 0 and every
  dollar table).
- F-9 append-file caching: named as a Level 1 gate inside M-P1, with the
  cache-read predicate spelled out.
- The 26-session sample rule and the tiktoken dependency: stated
  (section 0), with the exclusion bias direction discussed and the
  per-session points vendored.

**Open items: none.** The one revision-2 statement that does not fully hold
is editorial, not substantive: PROMPT-SPEC changelog 9 says no projection
books the prefix saving as realized until F-9 passes, but the section 9
central prices the rung prefixes at the cache-read rate, which is the
caching-works assumption. The exposure if F-9 fails is about $5 across the
run (prefix tokens repriced from 0.1x reads to 2x writes). Fix is one
sentence: either label the ~$5 exposure or price prefixes at the write rate
until the gate passes. Recorded in section 2 as exception E-4.

## 2. Cross-spec consistency

Checked against the coordinator's list plus everything found on the way:

| item | status |
|---|---|
| 2a-C cap 21, same binding rule | **agree.** Both cite the identical rule and arithmetic (28,312 mean, 53,793 dispersed, 84.1% of ceiling, PASS; cap 24 FAIL at 95.5%), the same relaxation condition (Level 1 `dispersion_max(low)` at n >= 10), and the lower-cap-wins tiebreak. Both scripts print the check and agree to the token. |
| merged handoff format | **agree.** escalation/v1 as input, array envelope with `corrections` as output, defined once (ORCH 4.1, PROMPT 3 to 5), `l`/`need` with the two constraints in both. |
| dual Opus pricing, pilot-row arbiter, Level 2 requirement | **agree.** Both specs carry both prices in every Opus figure and name the same arbiter and the same sign-off condition. |
| dispersion rule stated identically | **agree.** Same formula, same 1.90 default, same n >= 10 recalibration; PROMPT-SPEC adds the specific 1.55 threshold at which cap 30 returns, which is a refinement, not a conflict. |
| byte-cap figures | **agree.** 354,743 chars of detail, the 195,525-token block, the 217,026-token worst prompt, and the 196,579-token removal are consistent quantities used consistently. |
| merged M-1/M-P2 probe | **agree.** Both describe one merged probe, 10 to 12 calls, `dispersion_max(low)` as the primary output, cap relaxation bound to it. |
| escalation population 284/285 | **EXCEPTION E-1: the two specs crossed while harmonizing.** ORCH changelog 12 moved to 284 + 654 = 938 "harmonized with PE"; PROMPT changelog 8 held 285 + 654 = 939 "matching the Architect's step-2 alignment". Each landed where the other left. Ruling: use the efficiency postmortem's 939 (285 + 654), because the postmortem is the trusted baseline and 284 is an `int()` floor artifact of 569 x 0.50; the M-P5 harness recompute supersedes both numbers shortly anyway. Worth about $0.02; must still be one number. |
| rung prefix sizes | **EXCEPTION E-2: ORCH section 5 cites the pre-revision prefixes** (4,226 / 2,677 / 2,984 / 2,745) while PROMPT-SPEC re-measured after the F-5 additions (4,364 / 2,808 / 3,072 / 2,745, changelog 15). Sub-dollar impact; ORCH's parameter table should take the re-measured values. |
| which batch the "central" books | **EXCEPTION E-3: PROMPT-SPEC's central books 2b at batch 15 (63 calls)** while both specs agree batch 5 is the default pending M-2 parity. On the default, their central is $60.42 + $4.28 = $64.70 at $5/$25 (their own script prints the delta). Not a model error; a labeling gap: the central table should either book the default or carry the batch label. |
| F-9 booking statement | **EXCEPTION E-4**, described in section 1: one sentence reconciles the changelog with the table. |

None of the four exceptions moves any decision figure by more than about
$5, none changes a gate, a cap, or a probe, and each has a one-line fix.

## 3. Regeneration

- `data/cost-model.py` (revision 2): runs clean on system python.
  Reproduces the spec's tables exactly: 2a tier B $57.5 / tier C $36.8; 2b
  $25.0/$19.8 at $5/$25 and $75.0/$59.3 at $15/$75; 2c $4.9 to $14.2 with
  the $46.6 worst case; the G2 check (84.1% PASS, 95.5% FAIL, 45.2% PASS);
  bands lo/mid/hi $67/$71/$97 (batch 5) and $61/$66/$91 (batch 15) at
  $5/$25, $117/$121/$147 and $101/$106/$131 at $15/$75; fixed-out
  sensitivity $64/$84. The spec's "$61 to $97, central about $68" is the
  span across batch variants and matches.
- `data/prompt-aligned-cost-model.py` (revision 2): runs clean in the
  project venv (tiktoken present there, as the spec now documents).
  Regenerated JSON matches the section 9 table to the cent on all four
  variants: central $60.42 / $89.42, conservative $92.98 / $141.02, with
  per-rung figures identical, and prints the dispersion-rule arithmetic and
  the $4.28 batch delta.

## 4. Residual adjudications

**(a) Rescaled inputs versus direct measurements: I accept the Architect's
rejection.** My corrected table rescaled aggregate char counts by one
marginal rate; the Prompt Engineer measured each input quantity
individually with the o200k method my own pass confirmed (P-1, P-5, P-7,
P-9). Direct measurement outranks rescaling in my own rules of evidence.
The same goes for their O-6 recomputation: my quick $4.5 did not apply the
2x write class; about $13 at measured volumes is the better figure, the
falsification of revision 1's "$8" stands as a falsification of precision,
and the route-only rejection never depended on the number. The $3 to $6
model residual is properly named in ORCH section 0 and stays.

**(b) The PE-central-versus-corrected-mid gap: stays an open band, with one
action now.** On a common batch-5 basis the gap is about $6 ($64.70 versus
$71), entirely inside the flagged 2b/2c per-item estimates (handoff 750/400,
delta 480/145, failed-questions 1.5/1.0, 2c shapes). The action that is due
now is not a probe: the scheduled zero-cost M-P5 harness run measures the
failed-questions distribution and the true post-fix populations, and will
close most of this band before M-2 spends a dollar. It should run first;
both specs already agree to that ordering. Beyond that, the band waits for
M-2 exactly as flagged.

**(c) The price-contingent batch rule: sanity-checked, endorsed.** The
arithmetic holds in both models: batch 15 saves $4.28 to $5.2 at Opus
$5/$25 and $15.70 at $15/$75 (2b $75.0 versus $59.3). The rule spends
quality risk only when the reward is real, parity (now a scored metric) is
required in either case, and the decision cannot be made before M-2's rows
arbitrate the price anyway, since those are the same rows. One note for the
run sheet: M-2's own bound doubles under the high price ($8 to $24), which
the Architect states; the consolidated budget below carries the dual bound.

## 5. Consolidated proposed measurements

Merged and deduplicated across ORCH M-1..M-8, PROMPT M-P1..M-P8, and the
validation plan's gauntlet. Zero-cost harness work runs before any live
call.

| id | what runs | live calls | scaled bound | decides | level |
|---|---|---|---|---|---|
| H-1 (M-P5) | recompute harness over all banked blocks: old versus new rules with the fixed validator; fabrication count; failed-questions distribution; true 2b/2c populations | 0 | $0 | 6.3 guard, populations, handoff sizing priors, most of the (b) band | 0 |
| H-2 (V-5 fixtures) | R1 salvage, R2 referenced-at (store-only expected verdicts), R3 accounting, R4 prompt-shape, R6 census + merge-property + menu-stability | 0 | $0 | Level 0 sign-off | 0 |
| P-1 (M-4 + M-P1) | tier C A/B: 3 component groups + 3 relationship chunks, both schemas, low; blind-scored; append-file cache-read gate (F-9) | 12 | $6 | tier C adoption, real block sizes and envelope, F-9 | 1 |
| P-2 (M-1 + M-P2) | the new-schema prompts repeated for dispersion | 6 | $6 | dispersion_max(low), fixed-term bounds, cap-21 relaxation | 1 |
| P-3 (M-2) | about 30 harness-reconstructed escalated items, 2 batches of 5 + 2 of 15, Opus, delta-only | 6 | $8 at $5/$25; $24 if the price arbitrates high | batch parity, handoff and delta sizes, 2b failure rate, **the Opus price** | 1 |
| P-4 (M-P4) | 3 M-P1 prompts rerun with `--json-schema` | 3 | $2 | structural enforcement, schema cost, cache interaction | 1 |
| P-5 (M-5) | 2 relationship chunks, full facts versus one-liners | 4 | $3 | 2a-rel context and H1 rule | 1 |
| P-6 (M-P6) | substitution boolean versus sentence A/B | 2-4 | $2 | 6.6 fallback | 1 |
| P-7 (plan L1) | micro-run with deliberate kill and resume; raw envelope capture | ~6 | $5 (cap $10) | telemetry end-to-end, kill-safety, R5 fixture replacement | 1 |
| R-1 (M-3 + M-P3) | regression over P-3's rows plus two Fable rows | 0 | $0 | Opus/Fable thinking budget | 1 |
| R-2 (M-6) | cache predicates and gate thresholds from P-1/P-3 rows | 0 | $0 | telemetry gate thresholds | 1 |
| R-3 (M-P7, absorbs M-8 replacement) | price fit against the pilot ledger; **Opus arbitration on record** | 0 | $0 | price model; Level 2 entry condition | 1 to 2 |
| R-4 (M-P8) | pf fill rate from P-1 responses | 0 | $0 | pf framing | 1 |
| R-5 (M-7) | P3 to P5 cost from the Level 2 ledger | 0 | $0 | full-run band | 2 |

Live totals: **33 to 35 calls, $32 expected at Opus $5/$25 ($48 if the
price arbitrates high), every item individually capped.** This exceeds the
validation plan's original Level 1 envelope ($10), which predates the probe
program; the plan's addendum (section 13.6) now sets the consolidated
Level 1 cap at **$50**, covering the probe program plus the micro-run with
margin for the dual-price corner. **Maximum spend before any medium-scale
run (Level 2 entry): $50 hard cap, $32 expected.** Levels 0 and the
harness work remain $0.

## 6. The definitive cost statement for the owner

All figures scaled API-equivalent dollars, VS Code subject, quality gates as
specified. The two Opus columns exist because no recorded artifact carries
an Opus price; the first pilot Opus ledger row (probe P-3) collapses the
table to one column and is required on record before Level 2 sign-off.

| | Opus $5/$25 | Opus $15/$75 |
|---|---|---|
| ladder (2a+2b+2c), band | $60 to $95 | $90 to $145 |
| ladder, central | **$66** | **$105** |
| full run (adds P1 $0.75 measured; P3 to P5 $10 to $20 estimated) | $71 to $116 | $101 to $166 |
| full run, central | **$81** | **$120** |
| killed-run configuration, for scale | $1,000+ | $1,000+ |

Bands synthesize the three independently built models (QA-corrected
revision 1: $55/$64/$96; Architect revision 2: $61 to $97 central $68; PE
revision 2: $60.42 central, $92.98 conservative), which agree within $6 at
the central on a common batch basis. The PE's $141 corner is excluded from
the band because it stacks every conservative parameter AND the legacy
price simultaneously; it is the correct number for that stack and the stack
is not the expected case.

Top three width drivers and what closes each:

1. **The Opus price** (about $39 of central width): closed by probe P-3's
   first Opus ledger rows; a Level 2 sign-off requirement, zero dedicated
   cost.
2. **Tier C schema landing and the new-schema fixed term** (about $21 plus
   the $64-to-$84 fixed-out sensitivity): closed by P-1/P-2 ($12 bound),
   which also decide the cap-21 relaxation.
3. **The 2c entry fraction and 2b failure rate** (about $9 to $17): priors
   closed free by H-1 on the harness, measured live by P-3 ($8 bound).

## 7. Verdict

**Ready.** The package (three specs at revision 2, four review documents,
the regenerated data artifacts, the reconciled corpus, and the adjudication
record) is fit to present to the owner as the Phase 1 and 2 outcome:

- Every falsified and untestable claim from the testability pass is
  reworked, withdrawn, or properly bounded, with changelogs and a
  documented-rejections register on both specs (section 1).
- Both cost models regenerate cleanly and match their published tables
  (section 3).
- Three independently built models converge within $6 at the central; the
  remaining width is owned by named, priced measurements, not by argument
  (section 6).
- The four cross-spec exceptions (E-1 population digit, E-2 stale prefix
  row, E-3 central batch label, E-4 F-9 booking sentence) are editorial,
  worth at most about $5 combined, and each has a one-line fix. They should
  be folded in at the next touch of either spec; none blocks presentation,
  and this verdict document is their record in the meantime.
- The consolidated probe program is $32 expected, $50 capped, before any
  medium-scale run, against a decision worth several hundred dollars per
  full run and a validated path from $1,000+ to about $81 central.

Nothing blocks readiness.
