# Adversarial review: Prompt and Context Engineer on ORCHESTRATION-SPEC

Reviewer: Prompt and Context Engineer persona. Date: 2026-08-25. Phase 2,
step 1. No files of mine were revised for this review; my own corrections are
listed in section 7 and land in step 2.

Method: I reproduced `data/cost-model.py` (output verified identical to the
spec's tables), re-derived every disputed constant from the recorded corpus
with the same tooling as PROMPT-SPEC.md (tiktoken o200k_base scaled 1.5829,
fit basis stated there), and priced two real ledger rows under candidate rate
sheets. Every number here names its artifact. Claim-taxonomy tags per
VALIDATION-PLAN section 10 are attached to each finding.

## 0. Verdict summary

The orchestration design is sound and I adopt its structure: the target-kind
split, the escalation/v1 handoff, the 2c bound, the checkpoint dependency
order, and the rejection of route-only 2a. The cost model, however, carries
one wrong price sheet and one wrong calibration constant, and both push the
band high. Corrected with recorded evidence, their $96 to $155 ladder band
collapses to roughly $60 to $75, converging on my spec's central $59. The
disagreement is not judgment; every driver is checkable offline and section 4
walks the bridge term by term. Separately, QA's dispersion finding defeats
both specs' worst-case output claims at 2a-comp batch 30; section 6 gives the
batch that restores margin.

## 1. Where we agree, verified independently

So the disputes below are legible against a background of agreement:

- Structure: 569 components, 5,453 relationships, 55 groups, 173 partitions,
  2,003 slots, duplication 3.52x. Both re-derived from the store; exact match.
- Call plan: 55 2a-comp calls (one per group), 100 2a-rel calls at batch 80,
  63 2b calls at batch 15 (19 + 44). My independent chunking reproduces all
  three counts.
- Static instruction block size: their 5,400 tokens versus my measured 5,539
  scaled. Within 3%.
- Relationship per-item output at low, current schema: their 320 versus my
  measured 313 (135 real low-effort blocks). Within 2%.
- Sonnet pricing $3/$15 and the 1h cache-write behavior (2x) as billing
  reality: ledger row 2 reprices to within 1.6% only under that combination
  (section 3).
- The fact-block byte-cap defect is real: `cli/src/util` measures 195,525
  scaled tokens for one component's fact block by my calibration
  (`data/prompt-measure-projection.py` machinery over the re-derived store),
  and my rebuilt worst partition prompt is 217k scaled. The defect stands;
  only its token magnitude is disputed (D7).
- The rejection of route-only 2a (their 3.1) is correct and my prompt design
  depends on it.

## 2. Numeric disagreements, enumerated

Each row: their value, the measured value, the artifact, the cause, the
effect. [C-tags] per the QA taxonomy.

**D1. Chars per token: 1.71 versus 2.72 measured.** [their C2; refuting
evidence C1] Direct, fit-free check: session `c95c2999` billed 39,243
prompt-side tokens (2 input + 39,241 cache creation, transcript usage) for a
106,558-char user message: 2.72 chars per billed token. Fit over all 35
first-turn sessions: 2.80 mean, max residual 1.95%. Cause of their 1.71, as
far as the artifacts allow: the ledger's `tokens_in` conflates
continuation-turn cache creation (12 of the 32 partition sessions ran more
than one turn, re-ingesting their own output as cache creation,
`pipeline.py:328`; QA's corpus inventory, section 1),
and treating per-call token totals as chars-divided-by-rate folds the CLI's
fixed overhead (fit intercept 10,021) into a per-char rate. Their own
cross-check does not reproduce: the recorded ledger's median 2a `tokens_in`
is 22,484, not the "~31k prompt tokens" their comment cites against the
54,064-char median prompt; even the conflated ledger figure gives 2.40.
Effect: every char-derived token count in their model is overstated by about
1.6x: COMP_FACTS_TOK, COMP_FACT_MEAN, REL_FACT_TOK, the brief's share of
PREFIX. QA is adjudicating this dispute; the artifacts to check are named
above.

**D2. Opus priced at $15/$75; the sheet and the ledger say $5/$25.** [their
C2 with a stale constant; refuting evidence C1] `cost-model.py:29` sets
`O_IN, O_OUT = 15e-6, 75e-6` for opus and reuses it for fable. Those are
legacy Opus prices from an earlier generation of the sheet. The current sheet
(claude-api reference, cached 2026-06): Opus 5 $5/$25, Fable 5 $10/$50,
Sonnet 5 $3/$15. The recorded ledger proves the CLI bills at the current
sheet: row 1 (p1 orientation, fable, 19,916 in / 0 cached / 6,688 out,
$0.745 recorded) reprices to $0.733 at $10/$50 with the prompt at the 2x
write rate (1.6% low), while $15/$75 gives $0.800 to $1.099 (7% to 47% off);
row 2 (2a sonnet, $1.029 recorded) reprices to $1.012 at $3/$15 with 2x
writes (1.6% low). Their comment claims the 15/75 assumption was "fitted to
the one p1 fable ledger row"; the arithmetic above shows that row rejects
15/75 and accepts 10/50. Effect: 2b output and input rates overstated 3x,
fable rates overstated 1.5x. This is the largest single error: 2b at batch
15 drops from their $50 to $62.5 to about $24 with no other change
(section 4).

**D3. Fact payloads priced at 1x input; the run billed them at 2x cache
creation.** [C1] `rung2a` charges `COMP_FACTS_CAPPED * S_IN` and `in_r *
S_IN`; `rung2b`/`rung2c` likewise price item context at `O_IN`. Every
recorded first turn shows the entire user message billed as
`ephemeral_1h_input_tokens` (2x), for example `c95c2999`: input_tokens 2,
cache_creation 39,241, cache_read 8,849. The two ledger repricings in D2
close only under all-creation-at-2x. Effect: understates input dollars 2x
wherever D1 overstates tokens 1.6x; net about 0.85x on sonnet inputs. On
opus inputs, D2 and D3 combine to a net 1.5x overstatement (15 versus
2 x 5).

**D4. Fixed output per call at low: 4,400 versus a measured 0.5k to 2.8k.**
[their C2, n=3; refuting evidence C1, n=4] Directly measured on the four
low-effort replay transcripts by separating the components: thinking (billed
output minus scaled delivered text) is 0, 88, 381, 1,507; the JSON envelope
plus block keys inside delivered text is 483 to 1,323. Total per-call fixed:
0.5k to 2.8k. The 4,400 comes from a 3-point aggregate fit whose
decomposition is ill-conditioned: fitted on the same replays, the
per-relationship coefficient goes negative. As a predictor of those four
call TOTALS their formula is serviceable (ratios 0.81 to 1.00), because the
too-high intercept is offset by a too-low per-component term (their 1,100
versus 1,298 measured mean over 25 real low-effort component blocks). The
error surfaces exactly when the batch size changes, which is the entire
point of a decomposed model: at 100 relationship calls the phantom fixed
adds about 290k output tokens to 2a-rel (about $4.4), and at 2b/2c it adds
about 2.9k phantom tokens per call times 63 + 38 calls at opus and fable
rates. Their own M-3 plus my M-P3 resolve the Opus half; the Sonnet half is
settled by the replay measurement.

**D5. Relationship fact block: 335 versus 235 measured.** [C1] Mean over 400
real relationship fact blocks built by the current `relationship_facts`
against the re-derived store. Cause: D1 applied to their 573-char mean.
Effect: +43% on 2a-rel and 2b relationship input tokens.

**D6. 2a-rel context: 800 per call versus 3,703 measured.** [their
estimate, flagged M-5; mine C1 with a caveat] Their `in_r` charges 800
tokens per call for component one-liners. Building the actual context for
all 100 calls (one-liners for every distinct endpoint of the call's 80
edges, including endpoints outside the owning group) measures 3,703 scaled
per call. Cause: edges cross groups, so the endpoint set is much larger than
one group's roster. Effect: understates 2a-rel input by about 290k tokens
(about $1.7 at the correct 2x sonnet rate). Caveat on my own number,
carried to step 2: my measurement used `existing_description`, which a fresh
run mostly lacks until 2a-comp fills it; with fresh one-liner descriptions
the context grows by an estimated further ~1k per call.

**D7. Component facts totals: 825,564 uncapped / 506,452 capped, versus
569,761 / 373,182 measured.** [C1 both sides; cause D1] Sum over all 569
components of the serialized fact blocks (indent-2, as the prompt builder
emits), scaled; cap applied per component at 20k scaled to mirror their
outlier treatment. The outlier itself: their "roughly 339k tokens" for the
`cli/src/util` group's fact block measures 195,525 scaled for the component
(the group adds little; the component is the mass). The defect is real
either way; the byte budget's dollar effect is smaller than modeled.

**D8. 2b component facts mean: 1,451 versus 1,727, and both are the wrong
population.** [both C2] Theirs is the all-569 mean through D1 (2,481 chars;
about 912 scaled at the measured rate). Mine is the mean over the 43
components the run actually attempted, which skews to important, fact-rich
components. The population that matters is the ESCALATED set, which neither
of us has measured. Escalation skews important, so my 1,727 is the safer
planning figure, but this belongs on M-2's measurement list explicitly, not
silently inside either constant.

**D9. PREFIX composition: 12,300 versus measured pieces.** [mixed] Their
3,300 CLI-system figure is the minimum observed cache read (ledger row 2:
3,289); the typical read is 8.8k and the fit intercept for total prompt-side
overhead is 10,021. Their 5,400 static block agrees with my 5,539. Their
3,600 brief is the D1 inflation of a measured 2,032. Net effect small in
dollars; matters for the cache-telemetry predicates (H5 below).

**D10. Escalation population: 284 versus 285 components.** `int(569*0.50)`
versus rounding. Trivial; harmonize on one convention (I will adopt 284 in
step 2 since the source rate is "about 50%" and the difference is noise).

**D11. 2c per-item constants: out 450 / in 2,600 versus out 130 (comp) and
95 (rel) / in 2,177 (comp) and 485 (rel).** [both estimates, flagged] Theirs
are single scalars over a mixed population; mine decompose by kind from
measured attempt and facts sizes plus repair shapes. Up to 5x apart on
input. Both specs already flag 2c as the least-measured rung; M-2's failure
rate reading plus M-P3 resolve it.

**D12. Tier C block targets: 600 / 130 / 4,000 versus measured 880 / 124 /
under 1.5k.** [theirs FLAGGED placeholders; mine C1/C2] Their spec
explicitly delegates these to me (their section 12); PROMPT-SPEC delivers
them: component 880 central (1,263 conservative), relationship 124 central
(153 conservative), per-call fixed 0.5k to 2.8k. Their component 600 was
optimistic by about a third; their relationship 130 was right; their fixed
4,000 was high by about 2.5x. Net on tier C 2a output: roughly a wash, which
is why our 2a totals agree within $4 despite three offsetting errors.

**D13. Ladder band: $96 to $155 versus $55 to $75.** Fully explained by
D1 through D12; the bridge is section 4.

## 3. The price-sheet finding, in full

Because it moves the most money, the complete derivation:

```
ledger row 1 (fable, p1): tokens_in 19,916; cached 0; out 6,688; recorded $0.745
  at $10/$50, prompt at 2x write:  19,916*2*10e-6 + 6,688*50e-6 = $0.733   (-1.6%)
  at $15/$75, same:                19,916*2*15e-6 + 6,688*75e-6 = $1.099   (+47%)
  at $15/$75, prompt at 1x:        19,916*15e-6  + 6,688*75e-6 = $0.800   (+7%)

ledger row 2 (sonnet, 2a): tokens_in 27,031; cached 3,289; out 56,605; recorded $1.029
  at $3/$15, prompt at 2x write, reads 0.1x:
      27,031*2*3e-6 + 3,289*0.3e-6 + 56,605*15e-6 = $1.012                 (-1.6%)
```

Two independent rows, two models, both close only under the current sheet
with 1h cache writes. The efficiency postmortem's price model verified to
1.4% against this same ledger; the 1.6% residuals here are consistent with
it. No opus row exists in the corpus (the run died before 2b), so opus is
genuinely unobserved; the defensible planning rate is the current sheet's
$5/$25, not a legacy sheet, and M-P7 re-verifies on the first pilot ledger
that contains an opus row.

## 4. The bridge: their mid $115 to my central $59

Starting from their own `cost-model.py` mid case (tier C, batch 15, fixed
multiplier 1.0, 2c entry 20%): 2a $32.9 + 2b $56.2 + 2c $26.1 = $115.2.

| step | change applied | 2a | 2b | 2c | ladder |
|---|---|---|---|---|---|
| 0 | their mid | 32.9 | 56.2 | 26.1 | 115.2 |
| 1 | D2: current price sheet (opus 5/25, fable 10/50), inputs at 2x write per D3 | 32.9 | 24.2 | 22.3 | 79.4 |
| 2 | D4: per-call fixed output 4,400/4,000 to 1,530 measured | 27.2 | 19.6 | 16.8 | 63.6 |
| 3 | D1/D5: char-derived input tokens to measured (2b items 912+750 comp, 235+400 rel) | 27.2 | 17.4 | 16.8 | 61.4 |
| 4 | D12: component block 600 to 880+20; D3/D6/D7 on 2a inputs (2x rate, measured context, byte-budget) | 36.3 | 17.4 | 16.8 | 70.5 |
| 5 | remaining: their 2c per-item constants versus mine (D11), handoff and repair sizes (D8, M-2) | 36.3 | ~14 | ~8 | ~58 |

Steps 1 to 4 are arithmetic on named measurements; step 5 is the estimate
layer both specs flag to M-2/M-P3. The corrected band is roughly $60 to $75
(their structure, measured constants), against my independently assembled
$59.4 central / $65.0 conservative. The models now disagree by residual
estimates, not by calibration.

## 5. Hidden work, unpriced dependencies, and design conflicts

**H1. The 2a-comp to 2a-rel sequencing dependency is real work their spec
creates and neither spec prices in wall time or failure handling.** 2a-rel
consumes 2a-comp's fresh `description` one-liners (their 3.1), so no
relationship call for a group can launch until that group's component call
has absorbed. This serializes the rungs' overlap, interacts with
importance-ordered dispatch and the group-adjacent cache ordering (their
section 8 item 3), and needs a stated fallback when a 2a-comp call fails:
parser-derived `existing_description` or facts-only context. My spec
measured context with `existing_description` and therefore underestimates
the fresh-run context slightly (D6 caveat); their spec does not say what
2a-rel does when the description is missing. Both need the same line of
design; I will add the fallback rule in step 2 and ask them to confirm
scheduling.

**H2. The R-10 byte budget can silently break evidence-by-reference.** New,
and important: my citation forms index each component's `files` and `edges`
lists and each relationship's `evidence` list. A byte budget that trims or
reorders those menus between prompt build and validation, or that truncates
them differently on a rerun, renumbers the menu and turns valid citations
into E2s (or worse, into wrong-but-existing citations). Constraint to add
to R-10: fact truncation must never alter the citation menus after a prompt
is built; menus are truncated deterministically before build, and the
validator resolves indexes against the same stored menus. This is a
dependency between their roadmap item and my schema that neither spec
stated. QA should own a test for it (menu-stability under the byte budget).

**H3. Response-shape conflict at 2b.** Their worked example (their 4.2) has
the rung return `{"<target_id>": {"flow": {...}, "corrections": []}}`, a
dynamic-key map. My schemas use arrays with explicit `"i"`/`"k"` fields
precisely so `--json-schema` needs no dynamic keys. Proposed merge, already
implemented in my prompts: their escalation/v1 as the INPUT format,
unchanged; my array envelope as the OUTPUT format; their `corrections` list
adopted inside my entries. One format each direction, no information lost.
They should confirm.

**H4. Per-call CLI overhead is absent from their input model.** Every call
reads about 10k tokens of CLI system prompt (fit intercept; reads 0.1x).
155 sonnet + 63 opus + 38 fable calls is about $1.2 per run. Small, but the
model claims reproducibility to the dollar, and it also matters for their
cache predicates (H5).

**H5. Their cache-telemetry predicates do not match measured CLI behavior
and would fail a healthy run.** Their section 8 expects the warm call's
`tokens_cache_creation` "within 15% of the prefix size (12.3k)" and
run-wide `sum(tokens_cached) ~ (calls - 1) * prefix`. Measured reality: the
CLI writes the ENTIRE user message to cache on every call (creation ~ user
message, tens of thousands of tokens, not ~prefix), and every call's read
includes the CLI system prompt on top of the appended prefix. A healthy
redesigned run shows: warm call creation ~ prefix + user message; later
calls read ~ CLI-system + prefix and creation ~ own user message. My spec's
section 10 predicates encode this; theirs would flag every healthy call as
a cache miss. QA should adopt the corrected predicates in the telemetry
gate.

**H6. TTL causation is stated backwards.** Their section 8 TTL note implies
the 1h-rate billing followed from 554s calls outrunning the 5m TTL.
Measured: every first turn bills `ephemeral_1h_input_tokens` including
short calls; the 1h TTL is the CLI's write choice, not a consequence of
call length. Matters only because their V-6 asks whether the CLI exposes
TTL class per call: it does, in `usage.cache_creation.ephemeral_1h/5m`,
already present in the recorded transcripts.

**H7. Their wall-time estimate inherits D4.** 150 to 300s per 2a call
assumes their output sizes; at measured low-effort outputs (about 10 to 11k
per call central) generation is nearer 90 to 150s per call, so 2a wall at 4
workers is nearer 1.1 to 1.6h than 2.2h. Direction favorable; no action
needed beyond re-basing after M-P1.

**H8. `lacked` self-report alignment.** Their protocol expects the sending
rung to propose `lacked`; their spec does not define the field the sending
rung emits it in. My spec supplies it (`"l": "fact" | "judgment"` plus
`"need"` on uncertain answers, coordinator maps to their vocabulary and
owns `validator-scope`/`capability`). They should confirm the mapping so
the coordinator has one rule.

## 6. Task 2: the dispersion question against my headroom claim

Direct answers:

1. **My "worst case 63%" is mean-calibrated, not dispersion-adjusted.** It
   is mean per-block (conservative variant, 1,263 + 20 envelope) times the
   maximum batch (30) plus the measured thinking bound (1,530). The same is
   true of the Architect's "37.4k worst case, 58%" at their 3.3. Neither
   number satisfies QA's G2 as specified.
2. **The margin does not survive a 1.90x dispersion factor at batch 30.**
   2a-comp: 40,020 x 1.90 = 76,038, 119% of the 64,000 ceiling. Refused by
   G2, correctly. The Architect's 37,400 x 1.90 = 71,060, 111%, also
   refused. 2a-rel at batch 80 survives: 15,370 x 1.90 = 29,203, 46%. 2b at
   batch 15 survives trivially (repairs-only worst about 3.1k mean; even a
   pathological full-block re-emission of 15 components is 15 x 1,283 +
   1,530 = 20,775 mean, 62% dispersion-adjusted). 2c at batch 5 survives.
3. **The batch adjustment that restores margin: cap 2a-comp calls at 21
   components.** Mean worst becomes 21 x 1,283 + 1,530 = 28,473; times 1.90
   is 54,099, 85% of ceiling, with the central block estimate sitting at
   61% dispersion-adjusted. Cost: the 55 group calls become 61 (groups over
   21 split in two; re-derived from the real store), adding 6 calls of
   fixed output and overhead, about +$0.20 per run. Cap 25 would land at
   99.8% of ceiling and is not a margin; 21 is the setting. No change
   needed at 2a-rel, 2b, or 2c.

Two evidence notes for the adjudication, offered, not argued past the gate:
the 1.90 dispersion was measured at xhigh over per-session totals including
continuation turns, so it partly measures the overflow-continuation feedback
itself (an overflow re-bills its own output as a second turn), a mechanism
that `num_turns` alarming plus low effort remove; and at low effort the four
replay calls' actual-to-predicted ratios under my decomposed model are 0.93
to 1.08 (n=4). QA's own section 11 item 5 already says 1.90 stands as the
conservative default until Level 1 recalibrates `dispersion_max(low)`;
M-P1/M-P2's 12 calls double as that calibration sample for the new schema.
Until then, cap 21.

## 7. What my own spec got wrong; revisions for step 2

Listed now so step 2 is mechanical:

1. **"3x headroom on the worst call" (my section 7) is wrong.** Mean-based
   headroom at cap 30 is 1.6x, and dispersion-adjusted it is negative.
   Replace with the cap-21 sizing and the 85% dispersion-adjusted figure.
2. **"Zero calls project over the ceiling" (my section 9) must be
   re-qualified** as mean-calibrated, with the dispersion-adjusted table
   added and the 2a-comp plan restated as 61 calls at cap 21. Ladder totals
   move by about +$0.20 central.
3. **My 2a-comp input includes the uncapped `cli/src/util` monster.** With
   the R-10 byte budget at 20k scaled per component, 2a-comp creation drops
   about 175k scaled tokens, about -$1.05. I claimed the direction; step 2
   quantifies it and adds H2's menu-stability constraint next to it.
4. **My 2a-rel context is measured with parser-era descriptions** (D6
   caveat): fresh-run one-liners add roughly +1k per call, about +$0.6 per
   run, and the missing-description fallback rule (H1) must be stated in my
   2a-rel prompt section.
5. **Population harmonization**: 285 to 284 (D10), matching the Architect.
6. **Adopt and state the H3 merge explicitly** (their input protocol, my
   output envelope, `corrections` adopted) so the two specs cite one
   handoff format by name.

None of these move my central figure by more than about a dollar in either
direction; the dispersion re-sizing is the only one that changes the plan
shape (61 component calls, not 55).

## 8. For QA

The two calibration disputes you are adjudicating are D1 (chars per token)
and D4 (fixed output at low); the artifacts and derivations for both are
named in section 2, and my side's raw materials are committed under
`data/prompt-*`. Beyond those, the findings that need your tests: H2 (menu
stability under the byte budget), H5 (cache predicates corrected to
measured CLI behavior before they enter the telemetry gate), D2 (price
table pinned to the ledger-verified sheet, and M-P7 re-verification on the
first ledger containing an opus row), and section 6's cap-21 as the G2
input for 2a-comp until `dispersion_max(low)` is recalibrated from
M-P1/M-P2.
