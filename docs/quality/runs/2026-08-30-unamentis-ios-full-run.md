# The first full run: 626 targets, $58.92, and a cache that costs more than it saves

Date: 2026-08-30 (run 21:40 to 22:39 local, `2026-08-31T04:40:12Z` in the
testboard id). Subject: `unamentis-ios` at `a5717bf`, the same commit every
enrichment measurement in this directory uses. Status: state. Assessment
written by a reader independent of the run, checked against the run's
artifacts rather than its own report.

Extends `2026-08-25-unamentis-ios-ladder.md`, which recorded the first live
enrichment on the rebuilt engine at 3 of 18 partitions. That document remains
true and is not superseded. This is the same engine at full scale, with the
adjudication and improvement machinery the partial run did not exercise.

Artifacts: `/private/tmp/enrichment-unamentis-full-20260830.PcmHZn/`. Run
record: `.testboard/runs/2026-08-31T04-40-12-260615Z-enhance-unamentis-ios/`.

---

## 1. The short version

The run did its job. It answered 626 of 626 targets, grounded 95.9% of them,
drove adjudicator disagreement to zero on the final sample, correctly
diagnosed its own remaining blocker as a parser defect, and refused to buy a
third improvement round it knew would not help. No calls failed. No transport
violations. The failure class that destroyed the 2026-08-25 private large-repository validation corpus run did
not recur at 4.9x the scale.

It reports `failed` for reasons unrelated to any of that, and the efficiency
picture underneath it has moved rather than improved.

## 2. Why the run reports failed

The audit verdict is `fail` on exactly two checks, both of them output
density, neither of them about correctness.

| check | measured | limit | overshoot |
|---|---|---|---|
| `escalation-output-density` | 260.8 tokens/attempt | 260 | 0.3% |
| `work-order-output-density` | 490.5 tokens/attempt | 260 | 88% |

The first failed by 0.8 tokens per attempt. Across 81 escalation attempts that
is 65 tokens, on a run that moved 7,172,273. A gate that fails a $59 run for
65 tokens is not measuring anything a reader can act on.

The second is a genuine miss, but the gate looks mis-specified. Work orders
emit repair instructions naming claims and reasons, so they are structurally a
longer call type than an escalation. Holding both to a single 260-token limit
compares two different things and will keep failing.

Everything else passed: 272 calls, 0 failed, 0 compact budget violations, 0
non-warm cache misses, 0 prefix read shortfalls.

## 3. Where the money went

$58.9190 API-equivalent, 272 invocations, 7,172,273 tokens, 59.3 minutes wall
against 76.2 minutes of model time.

### 3.1 The cache is running at a net loss

This is the finding that matters most, and the run's own report gets it wrong.
`final-summary.json` records `budgeted_as_saving: true` and notes that only
measured reads are counted. It never nets the write premium against them.

| | tokens |
|---|---|
| cache writes | 5,387,974 |
| cache reads | 1,359,061 |
| read/write ratio | 0.2522 |

Cache writes bill at 1.25x base input, reads at 0.1x. Break-even is therefore
a read/write ratio of 0.25 / 0.9 = 0.2778. This run sits below it.

| | base-token equivalents |
|---|---|
| input cost with caching | 6,871,418 |
| input cost if every token were sent fresh | 6,747,579 |
| net effect of caching | 1.8% more expensive |

Caching cost this run slightly more than not caching at all. Because these are
pure price ratios, write 1.25x, read 0.1x, output 5x, and those ratios hold
for both Sonnet and Opus, the conclusion does not depend on the model mix.

`cache_efficiency.prefix_hashes` lists 8 distinct prefixes across 18
partitions and 32 planned bulk calls. Fresh prefixes are being written far
more often than any prefix is read back. That is the lever, and it is the
largest single cost lever the run exposes.

### 3.2 Output is no longer the problem

The 2026-08-26 postmortem found output was roughly 78% of the bill. That is
fixed.

| measure | value |
|---|---|
| billed output tokens | 424,694 |
| `output_share_of_billed` | 7.31% |
| delivered response payload | 922,306 bytes |
| compact budget violations | 0 |

Converted to dollars at the 5x output ratio, output is roughly 24% of spend
and cache writes are roughly 75%. The cost did not shrink so much as move.

### 3.3 One third of the run produced answers, two thirds checked them

Attributable by rung:

| rung | calls | cost | targets | $/target |
|---|---|---|---|---|
| 2a bulk (sonnet) | 32 | $18.27 | 626 | $0.0292 |
| grounding-spot-check | 93 | $11.30 | 93 | $0.1215 |
| opus escalation | 15 | $5.46 | 67 | $0.0815 |
| P5 work orders | 20 | $4.85 | 73 | $0.0664 |
| p5_determination | 4 | $4.45 | 4 | $1.1126 |
| substitution-check | 69 | $2.35 | 69 | $0.0341 |
| fable escalation | 3 | $1.65 | 14 | $0.1178 |
| spine, narrative, orientation | 3 | $2.38 | 2 | n/a |

The bulk first pass answered every target for $18.27. The remaining spend is
verification, adjudication and repair. That is a defensible allocation for a
system whose product is truthfulness, but it is the number that decides
whether the next run is cheaper, and it should be a deliberate choice rather
than a residual.

Against the partial run, the picture is mixed and worth stating precisely.
Cost per target rose from $0.0617 to $0.0941, up 53%. But the bulk rung alone
fell from $0.0617 to $0.0292, down 53%. The first pass got twice as cheap and
the quality machinery around it more than absorbed the gain.

Escalation improved outright. The partial run spent $0.297 per escalated item
for a 16% resolution rate. This run spent $0.089 per climb across 80 climbs,
a 3.3x reduction in unit cost.

## 4. Quality of the result

| measure | value |
|---|---|
| targets answered | 626 / 626 |
| grounded | 600 (95.9%) |
| honest gaps | 26, all carrying an actionable E2 reason |
| adjudicator disagreement | 64% to 31.3% to 16.4%, then 0% on 118 spot-checked claims |
| criteria met | 8 of 8 |
| relationships enhanced and valid | 458 / 458 |

All five subject-specific criteria were met, including the two that the brief
cared most about: the mic-to-reply pipeline reconstructed with latency and
barge-in points named, and Knowledge Bowl presented as one vertical slice with
the second Modules hierarchy flagged honestly rather than papered over.

Two nuances a reader should carry.

**Round 1 reduced the grounded count while improving the result.** Grounded
went from 617 to 603 as disagreement halved from 64% to 31.3%, at a cost of
$6.96. The system was retracting overclaims, which is the correct trade, but
it means the census is not a progress metric. Round 2 then recovered 603 to
609 for $5.68 and took disagreement to 16.4%.

**The self-diagnosis was correct and it saved money.** The run identified that
`compact-invalid` evidence citations are the root cause of the residual gaps,
that this is a serializer defect rather than a reasoning failure, that two
improvement rounds had already failed to clear it, and that a third identical
round would not change the outcome. It stopped and said so. `compact-invalid`
appears 76 times across 46 sites in `report.json`, concentrated on exactly the
high-value components still gapped: `services/stt`, `services/protocols`,
`services/tts`, `ui/session`.

## 5. The quality gate cannot pass

`scripts/score-ai-enhancement-quality.py` requires `average_score >= 85`. The
highest score any component achieved is exactly 85.0. The gate can therefore
only pass if all 168 components are simultaneously perfect, and it reports 86
of 168 (51.2%) below threshold.

The distribution shows the score is not measuring what its name suggests.

| score | components | cause |
|---|---|---|
| 85.0 | 82 | `optional_populated = 1/2` |
| 77.5 | 69 | `optional_populated = 1/4` |
| other | 17 | scattered, 67.5 to 82.0 |

Both dominant clusters populated exactly one optional field. The entire 7.5
point spread across 149 of 168 components is the denominator, meaning how many
optional fields the component was deemed to have. The score ranks components
by optional-field applicability rather than by enrichment quality, and 30% of
it rides on that term. The "51% below threshold" figure should not be read as
a quality statement until this is rebuilt.

## 6. Two process findings

### 6.1 The scorer was edited after the run, then applied to it

```
22:39:28  run ends (REPORT.md written)
22:43:52  scripts/score-ai-enhancement-quality.py edited
22:44:05  enhancement-quality.json produced, 13 seconds later
```

The edit makes honest gaps score-neutral, neither rewarded nor penalised. The
reasoning recorded in the code comment is sound: requiring invented prose
alongside a truthful gap would turn a sanity validator into a hallucination
incentive. That argument holds on its merits and the change is probably right.

It is still a grader loosened after seeing the result it grades, and any
future reading of this run's score has to know that. The mitigating fact is
that the loosened grader still returned `pass: False`.

### 6.2 The runaway guard was blind for 55 of 59 minutes

`run/control.json` was last written at 21:44, four minutes into the run,
recording `spent_usd: 2.22` and `completed_calls: 2`. The run went on to spend
$58.92 across 272 calls. That stale block is embedded verbatim in the
testboard's `run.json`, so the control plane would have displayed $2.22 while
$59 was being spent.

The operator had raised the checkpoint to $400 during the run, so nothing
tripped. But the checkpoint was being evaluated against a counter that had
stopped updating. The guard did not hold here, it simply was not tested.

Minor and related: `run.json` reports `total: 706` against `completed: 707`,
and the `run_start` event reports `total: 626`. Three denominators for one run.

## 7. What to do next, in order

1. **Fix the compact serializer** so evidence never surfaces as kind
   `compact-invalid`, then re-run citation checkout on the 26 gap items with no
   new enrichment. Zero model spend, clears the run's own named blocker. The
   run's `run_analysis.improvements` already says this and is correct.
2. **Fix the cache prefix strategy** before the next full run. At a 0.2522
   read/write ratio the cache is a net cost. This is the largest cost lever
   available and it is worth more than any further rung tuning.
3. **Fix the `control.json` update loop** before any run with a ceiling that
   is expected to bite.
4. **Re-spec the two density gates.** Give work orders their own limit, and
   decide whether 260 is a real threshold or a number to be 0.3% under.
5. **Rebuild the quality gate.** Raise the achievable ceiling above 85 or lower
   the bar, and remove optional-field applicability from the score.
6. **Route repeated work-order failures to a deterministic queue** rather than
   retrying them. Round 1 and Round 2 both logged "did not repair every named
   question" on the same protocols, stt and ui/session questions.

## 8. Disposition

The generated map is sound and can be pointed at the viewer and demo corpus as
a complete UnaMentis iOS demo. The two audit failures are gate defects, not
product defects, and the honest gaps are labelled and reasoned.

It is not a clean efficiency-release baseline. The cache result in section 3.1
means the run cannot serve as the reference point for efficiency claims until
the prefix strategy is fixed and a run is measured against it.
