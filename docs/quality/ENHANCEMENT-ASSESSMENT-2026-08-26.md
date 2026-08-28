# Where the enhancement stands: what changed, what it is worth, what is left

Date: 2026-08-26. Subject of every measurement: `unamentis-ios` at `a5717bf`
(168 components, 458 relationships, 751 files, 199,807 lines, 100% parser
coverage, 0 gaps, deterministic pass in 6 seconds).

Three live runs were made. Every number below is read from those runs' own
ledgers, reports and store, and where a figure is an extrapolation it says so.

---

## 1. The short version

**The transport-level disaster is fixed and proven fixed on live calls.** The
failure class that destroyed the 2026-08-25 VS Code run did not recur once
across three runs.

**The enhancement produces real value that the deterministic pass cannot.** I
did not believe this on faith; section 4 shows the actual output side by side.

**But the pipeline currently spends 83% of its money on things other than the
enhancement itself**, and its fixed overhead per run is large enough that a
small project pays roughly ten times more per component than a large one. That
is the central unresolved problem, and it is not the one the postmortems were
written about.

**Verdict on worth: yes for the enhancement, not yet for the pipeline around
it.** Detail in section 6.

---

## 2. What was broken, what was changed, and what it bought

Each row is a defect measured on a real run, a change, and the measured result.

| defect | before | after | evidence |
|---|---|---|---|
| effort inherited from user settings | xhigh; 67.8% of output was reasoning | `low` on every ledger row | 3 runs, every row `effort=low` |
| responses truncated at ceiling | 11 of 31 partitions (35%) | 0 across 3 runs | `stop_reason=end_turn` throughout |
| multi-turn agentic drift | 12 calls, alarm starved | 0; alarm now fed | `num_turns=1` on every row |
| output paid for then discarded | 46.5% of spend | 0 | no failures/ dir in any run |
| component duplication | 3.52x | 1.00x | partitioner measured on the real store |
| work lost on kill | 1 row banked after 31 calls | banked per call | checkpointing verified in run 1 |
| symbol citations rejected | 1,162 of 1,270 (93%) | 314/314 real accepted, 0/595 fabrications | measured on the killed run's corpus |
| oversized fact block | 373,027 chars (exceeds any context window) | under 12,000; total input down 61% | measured on the VS Code store |
| identity climbing the ladder | `identity.framework` to Opus twice | cannot escalate when the parser knows | contract test pins the narrowness |
| per-item verification | 754 edge calls, $10.50, 21 output tokens each | 19 calls verified 457 edges | run 3 ledger |
| parser facts unciteable | no evidence kind for them | `fact` citations, 15-field allow-list | new validator check + tests |

Test suite: 2,178 passing, up from 2,142, with the added tests pinning the
behaviours above rather than merely covering the lines.

### What I cannot claim

Escalation counts fell across the three runs (19 → 15 → 12 items climbing).
The identity fix explains part of that and model output varies between runs, so
I am **not** attributing the trend to the fix. The structural changes
(batching, duplication, byte caps, citation validity) are measurable and
attributable; the ladder-population changes are not, at n=3.

---

## 3. The cost anatomy, which is the real finding

Run 3 completed all five phases for the first time. Its money went here:

| phase group | calls | cost | share |
|---|---|---|---|
| p3 verification | 116 | $11.80 | 34.7% |
| p5 determination | 3 | $8.76 | 25.8% |
| **p2 ladder (the enhancement itself)** | **9** | **$5.66** | **16.7%** |
| p5 work orders | 18 | $5.39 | 15.9% |
| p4 synthesis | 2 | $1.91 | 5.6% |
| p1 orientation | 1 | $0.45 | 1.3% |
| total | 149 | $33.97 | |

**The work a reader actually sees is 16.7% of the bill.** The other 83.3% is
the system verifying itself, judging itself, and writing plans about itself.

Three calls in p5 determination cost $8.76. Eighteen work-order calls emitted
181,362 output tokens, more than the entire enhancement ladder produced.

### Fixed cost versus scaling cost

This matters more than the totals, because it decides which subjects are worth
enhancing at all.

- **Scales with the graph:** the ladder (per partition), edge verification (per
  edge), identity verification (per component), finding verification (per
  finding).
- **Roughly fixed per run:** orientation, synthesis, determination, work
  orders. Measured at **~$16.50** on this subject, and there is no reason it
  would be much smaller on a subject half the size.

Run 3 covered 3 of 18 partitions. A full pass over this repo projects to
roughly **$70**, of which about $16.50 is fixed and about $19 is whole-graph
verification that is incremental and mostly already banked.

**This corrects the rearchitecture estimates.** Those models priced the ladder
carefully and allowed $10 to $20 for "P3 to P5". Measured, p3 to p5 is $27.86
on a 168-component subject, and most of it does not shrink with the subject.
The $70 to $115 full-run figure for VS Code is a ladder figure; the real total
will be higher, and the fixed floor means small subjects are proportionally far
more expensive per component.

---

## 4. Where quality stands

This is the part I under-reported previously, so it is evidence-first.

### What the deterministic pass gives, for one real component

`unamentis` (the app target), deterministic only: id, name, path, type
`ios-client`, language `swift`, framework `UIKit`, 26 files, 35,837 lines,
external service OpenAI, 3 concerns, 2 findings, 47 children, Core Data
entities, 13 UI actions, testing counters. **`description: null`.** Structure
and counts, no explanation.

### What the enhancement adds, same component

- **description**: "The iOS app target that wires together and hosts every
  platform module."
- **help_text**: what it is, what it hosts, how it connects, why it matters.
- **criticality**: `critical`, with the edge counts behind it.
- **data_handled**: the actual Core Data entities by name, plus API keys and
  server configuration.
- **tech_context, testing_assessment, actions_summary, key_user_flows,
  external_services_assessment**: each grounded in a specific fact.
- **honest_gaps**: *"The framework tag says UIKit while the subject brief and
  file layout suggest SwiftUI is the dominant UI framework; not resolved from
  these facts alone."*

That last item is the strongest quality signal in the run. The enhancement
**caught the deterministic pass being misleading** and, instead of writing a
confident sentence over it, declared the contradiction. 31 honest gaps were
surfaced this way.

Another, from a UI component: *"The component is named
CurriculumDownloadFlowView but its path is CurriculumView.swift with a
1,482-line count. The extractor named a nested view."* That is the enhancement
**finding a parser bug** and reporting it to the reader rather than hiding it.

A third: *"No evidence of any kind describes this view's internals. This is not
a reasoning failure that a higher rung can fix. The facts needed are absent."*
The system correctly diagnosed that escalation would not help because the
shortage was context, not intelligence, which is precisely the finding I
reached independently from the trigger data.

### Synthesis output, which deterministic cannot approach

Four tours were written:

- **"One utterance, end to end"** follows a spoken utterance through microphone
  capture, VAD, STT, the LLM and TTS back to the speaker, showing where the
  sub-500ms budget is spent.
- **"How 17 providers coexist"** walks the four service protocols, then
  selection, keys and fallback, ending at the user-facing switch.
- **"Keeping a 90-minute session coherent"**, **"Knowledge Bowl: one feature,
  four layers"**.

These are what a new engineer actually needs, and no deterministic pass will
ever produce them.

### The 64.1% disagreement rate, correctly understood

Adjudication reported 50 of 78 sampled claims unsupported by their own
evidence. Reading the disagreements rather than the rate:

The fact block for `unamentis/core/audio` contains `inbound_edges: 17`. A tier
wrote "depended on by 17 components", which is **exactly true and taken from
the prompt's own facts**. The citable evidence kinds were file, symbol, edge,
manifest and doc, so the best citation available was two edges, and the
adjudicator correctly ruled two edges cannot support a claim about seventeen.

**The claim was right and structurally unciteable.** That gap inflated the
disagreement rate, drove ungrounded escalations to a tier that could not fix
them, and made a working pipeline look broken. `fact` citations now close it.

Not every disagreement was an artefact. The same component's facts say
`file_count: 0` while the tier claimed "18 Swift files". That is a real error,
it remains detectable, and the design keeps sufficiency with adjudication
rather than with the validator.

**Honest status: the disagreement rate has not been re-measured since the fix.**
Until it is, quality is "materially better than 64.1% suggested, by an amount I
have not yet measured". That measurement is the first item in section 5.

---

## 5. What is left

Ranked by measured value, with what each is worth.

**1. Re-measure the disagreement rate with `fact` citations available.**
Nothing else is trustworthy until this number is known. One run.

**2. p5 determination and work orders: $14.15, 42% of the run.** Three
determination calls at $2.92 each and 18 work-order calls emitting 181,362
output tokens. Neither has been examined at all. Largest single unexplored
cost.

**3. verify-findings: 84 unbatched calls, $5.66.** The same per-item pattern
already fixed twice. Batching it is a known, mechanical change.

**4. The fixed-cost floor (~$16.50/run).** Decides whether small subjects are
economic. Needs a policy: which phases are optional, and on what basis.

**5. Escalation routing by trigger class.** Nine of nineteen climbs in run 1
were `context` failures answered with capability. Sending them back to the same
tier with more evidence, rather than up a tier, is the design fix. The `fact`
citation may already have absorbed part of this; re-measure first.

**6. Cache write/read imbalance.** 126,126 tokens written, 9,867 read, a 0.08
ratio, roughly a 12% premium on input for a few cents of saving.

**7. `mechanism` drives 58% of escalations.** Unexamined.

---

## 6. Is the enhancement worth it?

You are right that I never answered this. Here is my determination.

**The enhancement itself: yes, clearly.** It costs $5.66 to enhance 51
components and 238 relationships, about **$0.02 per enriched item**. For that
it turns a structural inventory into something a stranger can read, and it does
three things the deterministic pass cannot do even in principle: it explains
*why* a component matters, it catches the deterministic pass being wrong (the
UIKit/SwiftUI contradiction, the misnamed extractor component), and it declares
what it could not establish instead of inventing it. At two cents an item that
is not a close call.

**The pipeline around the enhancement: not yet.** Verification, determination,
synthesis and work orders cost $28.31 against the enhancement's $5.66, a factor
of five. Some of that is legitimate: edge verification refuted 17 inferred
edges and flagged 101 as uncertain, which is the map telling the truth about
its own guesses, and that is worth real money. But $8.76 for three
determination calls and 181,362 output tokens of work orders are not obviously
buying a reader anything, and neither has ever been measured.

**The honest summary:** the expensive part of this system is not the part that
creates the value. That was invisible until a run completed the full cycle,
which is precisely why you were right to insist on it.

**What I recommend, in order:**

1. Re-measure disagreement with `fact` citations (one run, cheap).
2. Audit p5 and work orders the way p3 was audited. On the evidence so far I
   expect a comparable finding.
3. Batch verify-findings.
4. Then run the full subject, with the fixed-cost question answered rather than
   discovered.

**What I recommend against:** running full VS Code next. Not because the
transport is unsafe, it is now demonstrably safe, but because 83% of the spend
would go to phases that have never been examined, and on a graph ten times this
size.

---

## 7. Runs behind this document

| run | scope | outcome | cost |
|---|---|---|---|
| ladder-smoke | 3 partitions, $6 ceiling | ladder OK; p3/p4/p5 killed by my ceiling | $7.96 |
| full-cycle | 3 partitions, $25 ceiling | ladder OK; p3 runaway hit the ceiling | $25.02 |
| cycle2 | 3 partitions, $60 stop | **all five phases OK** | $33.97 |

The first run's ceiling was mine and was a mistake: it sat inside the run's own
likely bracket and truncated it, which is the failure mode the vscode registry
note already documents as an owner decision. The second run's $25 stop did its
job, catching a genuine runaway. Both are recorded here because the cost of the
first was real and the lesson was not free.
