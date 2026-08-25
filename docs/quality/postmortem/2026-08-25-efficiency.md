# Enrichment efficiency: where the money actually goes

Companion to `2026-08-25-enrichment-overflow.md`. Figures measured over 37 CLI
transcripts from the killed run (32 parsed: 60 unique component blocks, 1,002
unique relationship blocks). Token counts are tiktoken o200k_base scaled by a
factor fitted against true Claude input tokens, validated end-to-end at 0.1%
error against a live probe. Price model verified against the ledger to 1.4%.

## The three cost drivers, in order of size

### 1. A validator bug is sending a third of the graph to Opus

`EvidenceValidator._check_symbol` (`analyzer/enrich/evidence.py:236`) accepts a
symbol citation only if the symbol is **defined** in the cited path
(`_symbols_by_path`). The enrichment task describes relationships ("X uses Y"), so
the natural and prompt-invited citation is Y at its **use site** in X. That is
rejected.

**1,128 of 1,215 symbol citations (93%) fail this check**, all with the same
reason. Recomputing every contract state through the real `state_from_block` and
`EvidenceValidator`:

| | current | accepting a symbol at a known referencing file |
|---|---|---|
| component escalation rate | 53% | 50% |
| **relationship escalation rate** | **47%** | **12%** |

658 of 795 relationship E2 failures are this one mismatch. Estimated effect on run
cost: **−$450**, by shrinking the rung-2b population from 2,865 items to 939.

This is the answer to "why did Opus do most of the work". The work was not hard.
The grounding check was rejecting valid citations en masse and the ladder did
exactly what it was designed to do with a failed check: escalate.

Fix must preserve the distinction: record "referenced at" versus "defined at"
rather than simply loosening the check.

### 2. Effort inherited as xhigh (see the overflow postmortem)

Regression over 20 single-turn complete responses:

```
DELIVERED JSON = 1,150/component + 376/relationship +  5,177 fixed
BILLED OUTPUT  = 3,221/component + 513/relationship + 29,244 fixed
                              JSON share of billed output: 36.4%
```

**~29,000 output tokens of reasoning per call before a single block is written**,
plus ~2,000 more per component.

### 3. Component work duplicated 3.52x by the partitioner

Reproduced against the real store: 173 partitions, 569 components, **2,003
component slots**, 5,453 relationship slots, 55 distinct component groups. One
group is chunked 14 ways. Relationships are not duplicated at all; the entire
3.52x is component repetition (`partition.py:263`).

It produces 3.52 independent answers for the same component and keeps whichever
landed last. That is not redundancy for quality, it is 3.52 rolls of one die with
only the last counted.

Fix: split by target kind. One component-only call per group, and
relationship-only calls carrying component facts as input context but returning no
component blocks. Removes 1,434 component slots = **42.8% of delivered output**,
**−$125**, quality trade none.

## Output composition, corrected

Weighted by the real 2,003 component / 5,453 relationship slot mix:

| | first estimate (n=1) | measured |
|---|---|---|
| product (what the map's reader sees) | 18% | **23.2%** |
| contract / audit scaffolding | 69% | **73.2%** |
| block keys | — | 3.6% |
| byte-identical `flow.evidence` == `why.evidence` | 10% | **2.9%** |

Per block: component 1,770 tokens (product 528 / contract 1,224); relationship 437
tokens (product 58 / contract 346). **A relationship block is 79% scaffolding and
only 58 tokens of it is content anyone reads.**

`_clean_component_payload` strips `contract` before the product row is written, so
**73.2% of emitted output never reaches a reader**. That is a legitimate design
choice, but it prices the scaffolding as audit, and audit does not need prose.

## Evidence arrays are transcription, not evidence

Evidence arrays are **31.3% of all delivered output**.

- **100.0%** of 2,521 relationship citations already appear in the prompt's own
  `relationship_facts.evidence` or restate the edge the prompt names. Seven items
  out of 2,521 are anything else.
- **96.7%** of 370 component citations are a path from the prompt's own
  `files[:8]` list. Only 12 point at a file the prompt did not list.

`_GROUNDING_RULE` constrains evidence to a closed set the prompt already contains,
then pays ~52 output tokens per item to re-spell a member of it. A selection from
a known list needs an index, not a JSON object with a full path.

`EvidenceValidator.any_valid()` needs exactly one valid citation, so the 71%
overlap between `why.evidence` and `flow.evidence` is mechanically worthless.

## Constants emitted as data

- 91% of component answers and 93% of relationship answers carry
  `"status": "answered"`
- 88% of relationship `confusion` is null
- 91% of relationship `parser_first` is `[]`
- 89% of relationship `self_state` is `"grounded"`, and `contract.py`'s own
  docstring says the self-declaration "is an input, never the verdict" because
  `evaluate()` recomputes it
- `identity.language` / `framework` / `port` are asked only because the parser
  already detected them, the prompt hands the values over, and `strict_identity`
  defaults to `False` so `_contradiction_notes` never runs. Generated, stored,
  never checked. 144 tokens per component.
- `substitution_check` costs 69.4 tokens of English to answer what
  `_is_substitution_failure()` (`contract.py:562`) reads as a boolean via substring
  match

Not free deletions, checked and rejected: `data_flow_description` vs `flow.claim`
(mean word coverage 0.38) and `help_text` vs `purpose`+`mechanism`+`place`
(coverage 0.43) are conceptually duplicated but textually distinct. Anyone
claiming a free win there is wrong.

## Escalation economics

The ledger's `targets` field records `len(part.component_ids)`
(`ladder.py:496`), so a call that produced **43.1 contract targets** on average is
logged as 2 or 10. **The ledger understates rung 2a's work about fourfold.**

| | rung 2a | rung 2b batch 5 | rung 2b batch 15 |
|---|---|---|---|
| targets per call | 43.1 | 5 | 15 |
| fixed overhead per item | **$0.0125** | **$0.172** | **$0.057** |
| all-in per component | $0.0873 | ~$0.32 | ~$0.20 |

**13.8x step in per-item fixed overhead at the boundary.** Batch 5 pays the
per-call reasoning tax three times more often per item than batch 15 would. Rung
2a routinely handles 43 targets per call, so 15 at a more capable rung is not
obviously beyond it. Needs sample validation before adoption.

At the measured escalation rates, **rung 2b is 573 calls at roughly $670, larger
than rung 2a.** The run died before reaching it, which is why no earlier estimate
saw it.

## Achievable cost

The killed run's $40.43 bought 138 of 2,003 component slots: **the cheapest 7% of
the work, not 18%.** Under the fitted model, **113 of 173 partitions were
projected to exceed the 64,000-token ceiling.** The run was not merely expensive,
it was on track to fail.

| tier | changes | rung 2a | rung 2b | over ceiling | total |
|---|---|---|---|---|---|
| baseline as configured | — | $326 | ~$670 | 113/173 | **$1,000+** |
| **A** configuration only | effort, validator bug, batch size, output gate | $126 | ~$100 | 13/173 | **~$250** |
| **B** A + partitioner | + split by target kind | ~$75 | ~$100 | 0 | **~$190** |
| **C** B + schema | + evidence by reference, implicit defaults, omit empties | **~$33** | **~$45** | 0 | **~$110** |

Tier C emits 1,441,307 JSON tokens against the baseline's 5,928,734, a **76%
reduction**, in **49 calls instead of 173**, with every product field and every
contract question intact.

Confidence: rung 2a is fitted on 31 real calls, high. Rung 2b rests on measured
escalation rates plus an unverified assumption that Opus's fixed reasoning matches
Sonnet's, so treat as ±30%. Rung 2c is genuinely unmeasured and structurally
unbounded in the current design, which is its own finding.

## Do first

1. Fix the validator bug (#1). It decides roughly 70% of the money.
2. Replicate the effort probe across five partitions. **Two independent probes of
   the same prompt at `--effort medium` disagreed sharply** (4,518 vs 10,820
   billed output; contract dropped vs contract present), which is evidence that
   medium is unstable rather than dominant. `low` was stable across four prompts.

Together these cost under $10.
