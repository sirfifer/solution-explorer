# The first run on the rebuilt enhancement: what it cost and what it proved

Subject: `unamentis-ios` at `a5717bf`. Deterministic pass: 168 components, 751
files, 199,807 lines, 458 relationships, 100% coverage, 0 gaps, 6 seconds.

This records the first live enrichment after the 2026-08-25 fix set. Scope was
3 of 18 partitions, 129 contract targets. Every figure is read from the run's
own ledger and report.

Extended by `2026-08-30-unamentis-ios-full-run.md`, which runs the same engine
on the same commit at full scale (18 partitions, 626 targets) with the
adjudication and improvement machinery this run did not exercise. The figures
below remain true for the partial run and are not superseded.

## What the fixes did, measured on live calls

| defect | 2026-08-25 private large-repository validation corpus run | this run |
|---|---|---|
| effort in force | xhigh, inherited from user settings | `low` on every row, pinned |
| responses truncated at ceiling | 11 of 31 partitions (35%) | 0 |
| multi-turn agentic drift | 12 calls, alarm starved | 0, alarm fed |
| output discarded unparsed | 46.5% of spend | 0 |
| component duplication | 3.52x | 1.00x |
| work banked on kill | 1 row after 31 calls | every call, as it lands |

The transport-level failure class that destroyed the earlier run did not
recur. That is the part of the fix set this run validates.

## What it cost, and where the money went

$7.96 API-equivalent over 12 invocations for 129 targets.

| rung | what it did | outcome |
|---|---|---|
| 2a (sonnet) | 3 calls, 129 targets | grounded 110 |
| 2b (opus) | 4 calls, 19 escalated items | grounded **1** |
| 2c (fable) | 4 calls, 18 remaining | grounded 2, honest gaps 16 |

**Escalation took 71% of the run's spend ($5.64) to work 15% of the targets,
and resolved 16% of them.** Per item that is $0.297 against rung 2a's ~$0.017,
a 17.5x step for a 1-in-6 success rate.

## Why items escalated

The report classifies every trigger, and the classification is the finding.

| trigger | class | items | dominant question |
|---|---|---|---|
| E1 no-answer | reasoning | 8 | mechanism (7), purpose (1) |
| E2 ungrounded | **context** | 6 | mechanism (4), identity.framework (2) |
| E5 declared confusion | reasoning | 5 | purpose (5) |
| E4 substitution failure | **context** | 3 | purpose (3) |

Two conclusions follow directly.

**Nine of nineteen escalations are context failures, and escalation answers
them with capability.** An E2 item could not cite evidence and an E4 item could
not distinguish itself from a sibling. Neither is a shortage of intelligence;
both are a shortage of facts in the prompt. Sending them to a more expensive
model is a category error, and the 16% resolution rate is what a category error
looks like in a ledger. The cheap fix is more evidence, not more model.

**`identity.framework` escalated to the most expensive tier twice.** The parser
detects the framework, the prompt hands the value over, and `strict_identity`
defaults to False so nothing ever checks the model's answer against it. Paying
Opus to re-derive a fact already held deterministically is the clearest
"belongs in the parser tier" case in the run.

**`mechanism` is the most expensive question in the schema**, driving 11 of 19
escalations across E1 and E2.

## The cache is costing more than it returns

Across the run: 126,126 tokens written to cache, 9,867 read back, a 0.08
read-to-write ratio. Per-call arithmetic reconciles against the ledger with
cache writes billed at roughly 2x base input and reads at roughly 0.1x. Each
partition's unique facts are written to cache and never read, because no later
call shares them. The shared prefix that IS reused is only 3,289 tokens per
call. Net effect is a premium of roughly 12% of input cost for a saving of a
few cents.

This is a structural argument for the prompt shape the rearchitecture specs
already propose: a large stable prefix that is written once and read by every
call, and a small per-call message carrying only the facts that differ.

## What this run does NOT establish

Honesty about scope, since a partial validation presented as a full one is how
the earlier disaster stayed invisible:

- The first attempt carried a $6 cost ceiling that was reached mid-ladder, so
  p3 adjudication and p4 synthesis were skipped and p5 determination failed.
  **A ceiling inside a run's own likely bracket truncates rather than protects,
  which is the documented owner decision this violated.** The rerun removes it.
- 3 of 18 partitions is not the subject. Cost per target here is inflated by
  fixed per-call overhead amortized over fewer calls.
- One run of one subject is n=1 for every ratio above.

## Recommendations, in order of measured value

1. **Route by trigger class, not by failure.** Send `context` failures (E2, E4)
   back to the same tier with more evidence; reserve tier escalation for
   `reasoning` failures. On this run that is 9 of 19 climbs redirected away
   from the expensive path.
2. **Never escalate a question the parser already answers.** `identity.*`
   should be answered deterministically or dropped from the contract, not
   climbed.
3. **Bound the escalation budget as a share of run cost.** 71% for 15% of the
   work would have been visible in-flight and is a tripwire, not a postmortem.
4. **Examine `mechanism`.** It drives 58% of escalations. Either the facts
   needed to answer it are absent from the prompt, or it is being asked of
   components where no answer exists.
5. **Shape prompts for cache reuse**, so the 2x write is amortized by reads
   instead of paid once per call.
