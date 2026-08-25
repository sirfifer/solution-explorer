# Adversarial review: Orchestration Architect on PROMPT-SPEC

Reviewer: Agent Orchestration Architect persona. Date: 2026-08-25.
Scope: `PROMPT-SPEC.md` (primary), `VALIDATION-PLAN.md` (as it bears on the
disputes), and their `data/` artifacts. Zero live calls; every number below is
recomputed from the named artifacts. Per the phase rules, my own spec is not
edited here; section 5 lists the revisions I will make in step 2.

## 1. Verdict in brief

The PROMPT-SPEC is the strongest measurement work in this engagement: the
tokenizer fit, the block-level decomposition, and the envelope finding (the
CLI writes the whole user message as 1h cache creation) are all real, and two
of its corrections against my spec stand up under my own recomputation. I
concede both challenges in substance, with corrected magnitudes that differ
from the Prompt Engineer's headline numbers (section 4).

The spec's $59 central ladder figure does NOT survive review as stated. Its
single largest mover is not any of its measurements but an unsourced price
sheet for Opus, worth about $28 on its own, and its worst-case call size
fails the QA persona's G2 dispersion gate as designed. Findings below.

## 2. Findings on PROMPT-SPEC

### F-1. The Opus price ($5/$25 per M) is cited to no artifact, and no artifact can support it. Highest-impact number in the spec.

`prompt-aligned-cost-model.py:118` hardcodes `usd_b = in_b * 2 * 5/1e6 +
out_b * 25/1e6`. Section 0 says "API-equivalent standard rates" and leans on
"the postmortem's price model verified against the ledger to 1.4%". That
verification cannot cover Opus: the killed run's ledger
(`demos/runs/vscode/2026-08-25/enrichment/ledger.jsonl`, 32 rows) contains 31
sonnet rows and 1 fable row, zero opus rows, and the run died before rung 2b.
There is no recorded artifact anywhere in this engagement with an Opus cost
on it.

Sensitivity: at $15/$75 (the Opus 4 era rate, which my own model wrongly
assumed in the other direction), the spec's 2b goes from $14.17 to about
$42.5 and 2c moves similarly, lifting the ladder central from $59 to roughly
$87. A 47% swing in the headline from one unsourced constant. Under the
VALIDATION-PLAN's claim taxonomy this is a C5 existence claim and must name
its source (CLI documentation, the API price sheet, version-stamped), and
M-P7 must be scheduled at Level 1 explicitly BEFORE the 2b projection feeds
G3's T-G3-2 refusal arithmetic, because a 3x price error flips what that
gate refuses.

For the record, I verified the spec's Fable rate where an artifact does
exist: the p1 orientation ledger row (19,916 tokens_in, 6,688 out, $0.745)
fits $10/$50 with 1h cache writes to within 2%, and refutes my own spec's
$15/$75 opus-class assumption for Fable (which predicts $1.10, 47% high). I
will correct that in step 2.

### F-2. The worst-case 2a-C call fails QA's G2 gate as designed. The "3x headroom" claim in section 7 is wrong under that gate.

`prompt-aligned-cost-model.json`: `worst_call_2aC` = 40,020 tokens (30
components at the conservative 1,263 block plus entry, thinking, envelope).
VALIDATION-PLAN 4.2 requires `predicted_mean * dispersion_max(effort) <
ceiling` for every call, with `dispersion_max` defaulting to the
xhigh-derived 1.90 until low-effort dispersion is calibrated beyond n=4
(VALIDATION-PLAN 11.5). 40,020 x 1.90 = 76,038 > 64,000. The shipped plan is
refused at preflight. Section 9's "zero calls project over the 64,000
ceiling" and section 7's "3x headroom on the worst call" both evaluate the
mean against the ceiling with no dispersion factor, which is precisely the
projection style QA measured missing 5 of 12 real overflows.

Resolutions, either acceptable: cap 2a-C at 24 components (24 x 1,263 +
1,650 = 31,962; x1.90 = 60,728, passes), which on the real store splits
exactly 5 groups (the five 30-component groups; re-derived from
`/Volumes/Studio/dev/.demo-corpus/_out/vscode/index.db` this session),
adding 5 calls and roughly $0.40; or size M-P2/M-1 to at least 10 calls and
adopt the measured `dispersion_max(low)` if it comes in at or below 1.55.
2a-R is unaffected (15,370 x 1.90 = 29,203) and so are 2b and 2c. My own
spec has the same defect and section 5 records the same correction.

### F-3. The model's envelope constant contradicts the spec's own envelope measurement.

Section 0 and section 14 quote "envelope 483 to 1,323 per call" (measured on
the 4 low replays, old schema), and section 14 uses that figure against my
4,400. But `prompt-aligned-cost-model.py:97-99` books `ENTRY = 20` per item
plus `ENV = 30` per call: for a 10-item call that is 230 tokens of envelope,
2 to 6x below the spec's own measured range. The new array schema is
legitimately leaner than the old id-keyed maps, but 30 tokens per call is an
assumption, not a measurement, and the same document cannot cite 483-1,323
as evidence against my fixed term while booking 30 in its own model. Worth
only $1 to $2 across the ladder, but it is exactly the class of
internal inconsistency this review exists to catch. M-P1 measures the real
new-schema envelope; until then the model should book the measured floor
(483), not 30.

### F-4. The block-measurement sample is smaller than the postmortem's and the exclusion rule is unstated.

Section 0 measures old-schema blocks from "43 unique component + 822 unique
relationship blocks parsed from 26 sessions". The efficiency postmortem's
corpus is 60 unique component and 1,002 unique relationship blocks from 32
parsed responses, and QA's inventory confirms 31 parseable partition
responses plus salvage (VALIDATION-PLAN 7.2: 1,270 symbol citations). Which
sessions were dropped, and why, is nowhere stated. The likely rule
(single-turn sessions only) has a bias: single-turn sessions are the ones
that did not overflow, hence systematically smaller or simpler partitions,
and the diet ratios (0.678 component, 0.395 relationship,
`prompt-aligned-cost-model.py:92`) were fitted on that sample. The spec
already concedes its parse "agrees within 5 to 11%" with the postmortem's
figures; the missing sentence naming the exclusion rule should also state
the direction of the bias. M-P1 supersedes this live either way.

### F-5. The `l`/`need` extension to escalation/v1: sound design, two required constraints.

The extension (section 3: `"l": "fact" | "judgment"` plus `"need"` on
uncertain answers, coordinator maps `fact` to `fact-not-in-prompt`) is a
good concretization of my protocol's `lacked` self-report, and keeping
`validator-scope` and `capability` coordinator-only is exactly right. Two
gaps:

1. **The schema allows `l`/`need` on any answer, including answered ones.**
   `$defs.answer` in section 7 lists `l` and `need` as free optional
   properties with no dependency on `"s": "u"`. Models pad optional fields
   the instructions mention; the killed run's 100% parser_first fill rate
   under a REQUIRED framing (section 6.4's own finding) is the precedent.
   Constrain it in-schema (draft 2020-12 `dependentSchemas`: `l` requires
   `s`), or the absorber must strip `l`/`need` from answered claims so they
   never reach the ledger's escalation-cause statistics.
2. **`need` is free text and the coordinator must validate it before
   routing.** An `l: "fact"` item routes to rung-0 fact augmentation. The
   model writes `need` while seeing a files menu capped at 8 entries
   (`prompts.py:183`, kept in the new design), so it cannot know whether the
   named fact exists in the store or anywhere. Without a deterministic check
   (is the named file/symbol/config in the analyzed set?) the augmentation
   loop spins on unsatisfiable needs, and my spec's one-loop-maximum bound
   (ORCHESTRATION-SPEC section 6) becomes the only thing standing between
   that and wasted calls. The coordinator rule should be: `need` resolvable
   against the store routes to augmentation; unresolvable `need` reclassifies
   to `judgment` and climbs normally, with the unresolvable text kept for
   the weekly review. This belongs in the protocol contract, not in prompt
   guidance.

Minor: my protocol's `unknown` residual class disappears in the model-facing
enum, correctly (the coordinator supplies it), but the spec should say so
rather than leave the vocabulary looking narrowed.

### F-6. The relationship evidence default (6.3) is a semantic change to the contract, priced as a schema diet.

Under the new default, a confident relationship claim with no citation is
recorded grounded with provenance `edge-default`. The supporting measurement
(99.8% of citations restate the prompt) is real, and I accept the direction.
But the change deletes a failure mode the current design detects: a
fabricated-but-confident claim over a real edge previously had to produce a
citation, and the citation could fail; now it produces nothing and passes.
The residual detectors are the model's own honesty (`s: "u"`) and P3's 10%
sufficiency spot-check. The spec flags this for QA in one sentence; it needs
a number. The zero-cost measurement exists: over the recomputed corpus, count
relationship claims whose ONLY failing citations were genuinely fabricated
(QA's R2 found 3 unknown-symbol plus 1 unindexed-path among 1,270 symbol
citations; the file-kind and edge-kind analogues need the same count). If
that count is single digits out of 2,521, the default is safe and the number
should be in the spec; if it is hundreds, the default needs a guard. Add to
M-P5 explicitly.

### F-7. 2b and 2c conservative columns are not conservative.

`prompt-aligned-cost-model.json`: 2b $14.17 and 2c $8.23 are identical in
the central and conservative columns; the conservative block sizes and any
upper-bound attempt/handoff sizes are not propagated into item payloads or
repair outputs (`f_c_item = 1727 + 250 + 150 + 50` fixed in both branches,
`prompt-aligned-cost-model.py:113`). The 250-token attempt figure is light
for a component item whose handoff carries `citations_tried` verdict strings
(the validator's reason strings alone run to 300 chars each,
`evidence.py:242-247`), and the 2c item books the same size as 2b despite
carrying two attempts under the protocol. Each is worth $1 to $3, not
material alone, but a "conservative" column that only varies 2a understates
the honest upper bound and should say so or vary all four rungs.

### F-8. Population arithmetic: use 285/939 consistently.

Section 9 and the model use 285 components + 654 relationships = 939
(matching the postmortem's recompute). My spec's `cost-model.py` computes
`int(569 * 0.50)` = 284 and states 938. Trivial, but the two specs should
not disagree by one item; I will align to 285/939 in step 2 since the
postmortem's published figure is 939.

### F-9. `--append-system-prompt-file` caching behavior is load-bearing and unverified.

The entire section 10 mechanism (prefix in the system block, billed once,
read at 0.1x by every later call) rests on the appended file joining the
CLI's cached system-block breakpoint. The flag's existence is verified by
string inspection (a proper C5); its caching behavior is not, and M-P4
probes `--json-schema` cache interaction but nothing probes this one. If
appended content lands outside the cached breakpoint, the $7 saving inverts
into the prefix billing at 2x per call (about $2.80 across 210 calls at the
measured prefix sizes) and the `prefix_hash` telemetry reads permanent
cache misses. Cheap resolution: the section 10 ledger predicates already
detect it at Level 1; add one line making the M-P1 pilot assert
`tokens_cache_read >= CLI overhead + prefix` on the non-warm calls, so the
assumption is retired by the first six calls rather than discovered at
Level 2.

### F-10. What survives review untouched

Verified against my own re-derivations and found correct: the envelope
finding (user message bills as 1h creation; `input_tokens: 2` constant;
cache_read constant at 8,849 on 33 of 34 sessions, 3,289 on the warm first
call, from `prompt-tokenizer-fit.json`); the 2a-C/2a-R input totals (574k /
1,652k scaled; my chars-based figures contained two offsetting errors and
their measured values supersede them); the call plan (55/100/63/39 matches
my plan; 100 relationship calls at batch 80 per-group reproduces exactly);
the repeal of "repeat it back unchanged" with `corrections` as the
adjudication channel; the identity-as-exception-flags design; the pf cap;
the retained `d`/`flow` and `help_text` distinctions per the
checked-and-rejected list; and the adoption of escalation/v1 as the single
handoff format.

## 3. Notes on VALIDATION-PLAN

- **The G2 dispersion finding is correct and I adopt it** (section 5 below).
  One methodological note for the record: `dispersion_max` measured across
  different partitions at xhigh mixes stochastic variance with
  model-composition error, so applying the max ratio to every partition is
  conservative rather than exact. That is the right direction for a gate.
- **Level 3's projection line ($110 to $250) predates both Phase 1 specs**
  and now spans neither spec's band. It should be re-anchored after the
  step-2 revisions, or the full-run cap inherits a stale basis.
- **The salvage refinement (seam-aware fence strip, 7/10 versus 10/10) is a
  real improvement** on the postmortem's recipe and my R-4 roadmap item
  should reference it as the implementation.
- **T-G3-2 depends on F-1.** The gate that refuses a run projecting over its
  ceiling needs the price model resolved before its refusal arithmetic means
  anything at 2b/2c.
- **R2's 1,162/1,270 versus the postmortem's 1,128/1,215**: the plan
  explains the delta (dedup) in place. No objection; cite it as the reason
  the two figures may never be mixed in one rate.

## 4. Responses to challenges

### Challenge 1: the 1.71 chars-per-token calibration

**Conceded in substance, with a corrected magnitude.** My 1.71 is wrong, and
the mechanism is exactly what the Prompt Engineer implies: I divided
first-user-message chars by TOTAL first-turn prompt-side tokens, which
includes the CLI's fixed overhead. The corpus proves the overhead is real
and constant: `cache_read_input_tokens` is exactly 8,849 on 33 of 34 usable
sessions (3,289 on the warm first call), and `input_tokens` is 2, so the
user message is precisely the `cache_creation` figure
(`prompt-tokenizer-fit.json`, re-derived this session). Folding 8,849 fixed
tokens into a ratio is the same class of error as the efficiency
postmortem's fixed-versus-marginal warnings, and I made it.

The corrected number is not 2.72 to 2.80, though. The fit-free marginal
rate, chars over cache-creation tokens per session, is **mean 2.385, median
2.361, range 1.872 to 2.748 over the 34 usable sessions**. Their 2.72 is
session `c95c2999`, the maximum of the distribution and the corpus's largest
prompt; their 2.80 chars-equivalent regression mean overweights the large
prompts (my own chars-based least squares on the same 34 points gives
marginal 2.885 with a 12,530 intercept, and that intercept exceeding the
observable 8,849 overhead is the sign the linear form is absorbing
size-correlated structure). So: 1.71 understates the marginal rate by about
1.40x on the honest central, not 1.6x. Their o200k-times-1.5829 method
avoids the chars ambiguity entirely and is the better instrument; I adopt it
for step 2 and drop chars-based conversion.

**On the claimed consequence, I hold.** "Your input-side dollars are
overstated" is wrong in dollars, because of the Prompt Engineer's own
envelope finding: every user-message token bills as 1h cache creation at 2x
base, not as 1x input. My model priced input at 1x. Correcting both errors
together multiplies my input dollars by (1.71/2.385) x 2 = **1.43 upward**
where I priced fresh input, and my 2b/2c input lines move down only because
of the separate price correction (F-1 for Opus, the p1-row fit for Fable).
Net effect of challenge 1 alone on my ladder band: under $5, direction up.
The gap between our totals does not come from this calibration.

### Challenge 2: the fixed-output fit (1,100/comp + 320/rel + 4,400 fixed)

**Conceded on the decomposition; held on the gap attribution.**

Conceded, with their numbers verified: the exact 3-point solve on the replay
data is ill-conditioned exactly as claimed. Solving the three points
(11c/39r/29,115; 2c/40r/18,963; 10c/40r/25,693) exactly gives **comp 841,
rel -2,581, fixed 120,510** (recomputed this session by Cramer's rule): the
relationship coefficient goes negative because r barely varies (39, 40, 40).
My published fit was anchored, not solved (fixed = 0.85 x the xhigh 5,177
delivered intercept, rel = 0.85 x 376), which is why it stayed sane, but the
anchor inherited an intercept their direct measurement contradicts: thinking
at low is 0 to 1,507 and the old-schema envelope 483 to 1,323, so the true
per-call fixed term is roughly 0.5k to 2.8k, not 4,400. The decisive test is
the fourth replay point, which I excluded and they can explain:
c95c2999-low (2 components, 16 relationships, 9,527 billed). My model
predicts 11,720, **+23%**; their decomposition (1,298/313 blocks, ~900
envelope, ~750 thinking) predicts 9,482, **-0.5%**. On the three shared
points the models are comparable (mine -0.5/+2.3/+9.8%, theirs
-0.6/-9.2/+8.6%); on the held-out point theirs wins outright. Direct block
measurement beats an inherited intercept, and I adopt their decomposition
for step 2.

Held: **this dispute does not explain most of the $96-155 versus $55-75
gap.** Substituting their decomposition into my structure moves 2a output by
under 10% (component pass: 569x841 + overhead versus my 569x1,100 + 55x4,400
differ by 2%; relationship pass by about 12%) and trims roughly $10 to $15
from my band, mostly at the 2b/2c fixed tax. The dominant driver of the gap
is F-1: their Opus at $5/$25 and Fable at $10/$50 against my $15/$75
assumptions, worth roughly $30 to $40 at 2b plus 2c, followed by my wider 2c
entry band (10 to 30% versus their pinned 20%) and my heavier handoff
estimates. With both concessions applied and THEIR prices, my corrected band
is roughly **$58 to $93, central near $75**, overlapping their $55 to $75;
with Opus at $15/$75 it is roughly $75 to $120. The residual spread between
the specs is a posture difference (my 2c and handoff conservatism), not a
measurement dispute, and the one number that decides which band is real is
the Opus price, which neither of us can source from a recorded artifact.
QA's adjudication should therefore rank F-1 above both challenges.

One consequence I flag against my own step-2 revision: with the fixed tax at
~1,650 rather than 4,400 and Opus at $5/$25, the batch-15-versus-5 saving at
2b shrinks from my claimed $44-56 to roughly $5-8, and my section 0 line
calling batch size "the single cheapest decision to get right" no longer
holds at that magnitude. M-2 remains worth running (the quality-parity
question stands), but its economic priority drops unless F-1 resolves to the
higher price.

## 5. What the G2 dispersion finding does to my spec (step-2 revision list)

QA's finding (mean-calibrated gate catches 7 of 12 recorded overflows;
dispersion 0.72x to 1.90x at xhigh; no scalar headroom separates the
classes) invalidates the headroom style of my batch-sizing formula. My
section 3.3 used `0.85 x ceiling`, a flat 1.18 headroom; the recorded
corpus shows per-call dispersion up to 1.90, so a call can pass my formula
at the mean and overflow in reality, which is precisely the five overflows
the mean-gate missed. Changes I will make in step 2:

1. **Batch formula**: `batch_max = floor((ceiling / dispersion_max(effort) -
   fixed_out) / per_item_out)`, with `dispersion_max` from QA's calibration
   table, defaulting to 1.90 until low-effort dispersion is measured at
   n >= 10. The 0.85 line survives only as W1's in-flight warn threshold,
   which is its correct role; preflight sizing uses dispersion.
2. **2a-C cap drops from 30 to 24 components** under the 1.90 default
   (24 x 1,263 + 1,650 = 31,962; x1.90 = 60,728 < 64,000). Exactly 5 groups
   on the real store exceed 24 (all five at the 30 cap); splitting them adds
   5 calls and about $0.40. If M-1/M-P2 (merged, sized to 10+ calls)
   measures `dispersion_max(low)` at or below 1.55, the 30 cap returns.
3. **2a-R batch 80, 2b batch 15, 2c batch 5 all survive** the 1.90 factor
   (worst cases 29.2k, well under 22k, and trivial respectively). No change.
4. **Cost projections need no dispersion margin**: dollars follow the mean
   over 155-plus calls and per-call dispersion averages out; the scorecard's
   cost-versus-projection ratio plus W3 already police the aggregate. What
   does need the margin is per-call wall-time (my "about 3h" becomes "2.5 to
   4h" quoting p95 per call) and every per-call output ceiling statement in
   my section 5 table.
5. **Roadmap R-3 splits in two**: G2 as the preflight refusal exactly per
   VALIDATION-PLAN 4.2 (adopting their form verbatim, dispersion multiplier
   included), and W1 as the in-flight tripwire. My original R-3 conflated
   them.
6. **M-1 is undersized for its new job.** Five calls cannot calibrate a
   dispersion maximum. Merge M-1 with M-P2 at 10 to 12 calls, bound $6, and
   have it emit the `dispersion_max(low)` entry for QA's calibration table
   as a primary output, not a byproduct.

Also queued for step 2 from this review: Fable price correction to $10/$50
(F-1 artifact fit), adoption of the o200k-scaled measurement method and
their measured input totals, the anchored-fit replacement per challenge 2,
the 285/939 alignment (F-8), and the batch-economics restatement (end of
section 4).
