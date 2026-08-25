# Root cause: the 2026-08-25 VS Code enrichment run

Status: root cause CONFIRMED by three independent reviews. Rewritten 2026-08-25
after adversarial review corrected nine figures and one headline conclusion in the
first draft. Every number here is re-derived from artifacts; where a figure is an
estimate it says so.

## Summary

The run was killed at ~100 minutes having completed 31 of 173 rung-2a partitions.
Ledger spend $40.43; true spend ~$43.8 (about $3.41 was in flight at the kill and
never reached a ledger row). **$18.82 of that, 46.5% of the run's dollars, was
paid for and then discarded.**

The cause is not that the schema is too large. **The cause is that the run
inherited an interactive reasoning budget**, which consumed roughly two thirds of
every response before the answer began.

## Root cause

`~/.claude/settings.json` sets `"effortLevel": "xhigh"`. `ClaudeCliInvoker`
(`analyzer/enrich/engine.py`) passes `--setting-sources user` and never passes
`--effort`. Every enrichment call therefore ran at xhigh.

Measured across the run's 36 subprocess transcripts:

- **67.8% of every billed output token was extended thinking**, not answer text.
  Calibrated from six turns that emitted 64,000 output tokens and zero characters
  (sessions `9e00d6a7`, `6cd83301`, `e65748d4`, `dc582b63`, `a50d2144`,
  `42811c61`).
- **Not one turn in the run would have exceeded 64,000 tokens on answer content
  alone.** Maximum answer-only turn: 37,479 tokens. Mean: 15,957.

`max_tokens` counts thinking and text together. At xhigh the reasoning consumed
the budget, the answer ran out of room, and the response truncated.

### Controlled replay

Four real prompts from this run, same model and flags, only `--effort` changed.
The xhigh column is the run's own recorded result, so it is a free control.

| prompt | xhigh | low |
|---|---|---|
| 18d33ea2 | 2 turns, 102,177 out, UNPARSEABLE | 1 turn, 29,115 out, parses, 11 comp / 39 rel / 142 answered |
| ad7b77ab | 2 turns, 75,587 out, UNPARSEABLE | 1 turn, 18,963 out, parses, 2 / 40 / 74 answered |
| 594044a3 | 2 turns, 88,145 out, UNPARSEABLE | 1 turn, 25,693 out, parses, 10 / 40 / 134 answered |
| c95c2999 | 1 turn, 40,463 out, parses, 36 answered | 1 turn, 9,527 out, parses, 40 answered |

**73% fewer output tokens, zero overflows, every response parses, coverage equal
or better.**

Effort curve on `c95c2999`: xhigh 40,463 out / 36 answered / 63 evidence / 211-char
relationship descriptions; high 23,948 / 38 / 61 / 119; low 9,527 / 40 / 45 / 105.
Effort buys citations and prose length, not coverage. `medium` is not a safe
middle: it was erratic, still failed to parse one prompt, and dropped the
completeness contract entirely on another.

Projected rung 2a over all 173 partitions: **$80 and 1.9h at low**, against $327
and 6.7h at xhigh with its discard rate.

## The failure chain

1. Response exceeds the 64,000-token output ceiling. **11 of the 31 completed
   partitions (35%)** recorded `stop_reason: max_tokens` at exactly 64,000.
2. The CLI **silently auto-continues**, handing the model its own prior output
   verbatim. 12 sessions ran 2+ turns; one ran 3. Each has exactly one user
   message, so this is an assistant-side resume, not a re-prompt.
3. The re-ingested output is billed as cache-creation at the **`ephemeral_1h`
   rate, 2x base input**.
4. `--output-format json` returns only the **final turn's** text. All 10 failure
   files are byte-identical to their session's final-turn text and begin
   mid-string.
5. `LadderPhase._invoke_parallel` writes it to `failures/`, returns `None`, and
   `_rung_2a` skips it. The ledger still records `ok: true` with full cost.
6. Those components never get a `ContractState`, so `_rung_escalated` never sees
   them. **They vanish from the census entirely rather than showing as
   unresolved.**

### The continuation defects

The model is handed its prior output verbatim; 5 of 9 completed boundaries are
byte-perfect. The failures are three narrow mechanical defects, not the model
guessing:

- **fence re-injection** (4 sessions): turn 2 opens a ```` ```json ```` or bare
  ```` ``` ```` mid-object
- **overlap** (`18d33ea2`): `...in the brow` + `wser/common tiers`
- **dropped whitespace / duplicated fragment** (`594044a3`, `4e180793`): a lost
  space or a restated fragment at the seam, consistent with prefill trailing-
  whitespace stripping

## The discarded work was fully recoverable

**Corrected from the first draft, which claimed the opposite.** A ~15-line
salvage (strip fences anywhere, dedupe the suffix/prefix overlap, take the brace
span) recovers **10 of 10 discarded partitions**, every requested component block
present, $18.82 of $18.82. Verified independently.

The first draft's "still broken: 10" counted a contaminated set: 4 sessions killed
in flight plus a retry duplicate, not the 10 partitions actually discarded.

## Why the defences did not fire

- **A purpose-built alarm already exists and was starved.** `MeteredInvoker`
  (`pipeline.py:390-399`) raises "agentic drift: ... used {turns} turns; the
  transport is not pinned to pure inference" whenever `num_turns > 1`. It never
  fired across 12 multi-turn calls because `ClaudeCliInvoker` folds `num_turns`
  into `usage` **only on the `is_error` branch** (`engine.py:229`); the success
  branch returns the bare API usage block. The detector was built, wired, and
  waiting for a field one line away.
- **The overflow was visible in data the ledger already recorded.** Rung-2a call
  #1 logged `tokens_out: 56,605`, 88% of the ceiling, at $1.77 spent. Call #5
  logged 69,398, 108% of ceiling, at $6.44. A "warn at 0.85, abort above 1.0" rule
  would have stopped the run at $6.44. **What was missing was an assertion, not a
  field.**
- **`stop_reason` is a top-level envelope field** and is discarded by the invoker.
- **The ladder is the one call site that dropped a retry the rest of the codebase
  has.** `passes._invoke_json:166`, `engine._enhance_partition:609` and
  `engine._enhance_architecture:927` all retry a parse failure once with
  corrective feedback. The ladder does not, mirroring its own comment about having
  "quietly dropped" bounded-parallel invocation.
- **Cache-creation tokens are conflated, not absent.** `pipeline.py:328` computes
  `tokens_in = input_tokens + cache_creation_input_tokens`. A continuation turn's
  re-ingested output is therefore indistinguishable from a genuinely large prompt,
  and it bills at 2x while raw input bills at 1x.
- **No check anywhere compares projected output against the model's ceiling.**

### A naive output-budget gate would NOT have caught this

Applying a text-only projection to all 36 real prompts gives a maximum of ~31k
tokens and flags **zero** of the overflows, because it predicts answer text and
ignores reasoning. Any output gate needs a per-effort reasoning multiplier,
calibrated from the ledger rather than guessed. Measured at xhigh: output/product
≈ 4.5x.

## A second, separate money-losing failure

The effective invoke timeout is 1200s (`pipeline.py:500` overrides the invoker's
600s default). It fired once, proven to the second: session `e65748d4` has no
ledger row and a first-user-message byte-identical to `c43619cb`'s, whose start is
1200.7s later. That partition was **billed twice and still produced nothing**
(the retry became `2a-job-23.txt`). Session `6cd83301` used 1,190s of the 1,200s
budget, so this was about to become routine.

## Measured cost shape

- output tokens are **77.7%** of spend
- mean output 66,331 tokens/call against a 64,000 ceiling
- measured block sizes: **1,713 tokens/component**, **282 tokens/relationship**
- output composition run-wide: **24.8% product, 75.2% contract scaffolding**, of
  which byte-identical duplicated evidence (`flow.evidence` == `why.evidence`) is
  **3.4%**
- component work duplicated **3.52x**: 2,003 component slots planned for 569 real
  components
- rung 2a absorbs to the store only after all 173 partitions drain; no checkpoint,
  no signal handler. The store held exactly 1 row (`target_kind='subject-brief'`,
  written 08:14:46, before rung 2a began).

## Claims retracted from the first draft

- "concatenating the turns is not the fix" — it is; 10/10 recover
- "$12.70 discarded" — it is $18.82, 46.5% of run dollars
- "output is ~88% of spend" — 77.7%
- "1,143 tok/component, 215 tok/relationship" — 1,713 and 282
- "cache-creation tokens absent from the ledger entirely" — conflated into
  `tokens_in` by explicit design, and billed at 2x not 1.25x
- "`594044a3` drifted to a different component" — same sentence, one lost space
- "10% duplicated evidence" — 3.4% run-wide; the 10% was an n=1 measurement
- "there is no retry" — the cited ledger contains one (row 29, `retries: 1`)
- "the 2026-08-22 run hit the same wall (331 relationships, ~78k tokens)" —
  unsupported; the only surviving 08-22 artifact is a dry run with 0 invocations
- "tripled the partition count from 57 to 173" — 57 is from a different commit; on
  this snapshot it is 55 to 173
- "calls degrade across a run" — partitions run in importance order, so later calls
  are different work; no control for content

## Fix priority

1. **Pin `--effort` explicitly** and stop inheriting it from user settings.
   Measured 73% output reduction, zero overflows.
2. **Read `stop_reason` and `num_turns` from the envelope on the success path.**
   Two lines; the drift alarm is already built and waiting.
3. **Add the assertion**: warn at 0.85 of the ceiling, abort above it. Would have
   stopped this run at $6.44.
4. **Salvage on parse failure**: fence-strip, overlap-dedupe, brace-span.
   Recovers 10/10.
5. **Give the ladder the parse-failure retry** the other three call sites have.
6. **Checkpoint absorption per partition** instead of after the pool drains.
7. **Evaluate `--json-schema`**, which exists in the CLI and is unused, to make
   this failure class structurally impossible.
8. **Per-call `--max-budget-usd`** as a blunt backstop.

## Evidence

- ledger: `demos/runs/vscode/2026-08-25/enrichment/ledger.jsonl` (32 rows)
- discarded responses: `demos/runs/vscode/2026-08-25/enrichment/failures/` (10)
- subprocess transcripts: 36 sessions in
  `~/.claude/projects/-Volumes-Studio-dev-solution-explorer/`, 2026-08-25
  08:10-09:55. Note the phrase-based identifier used in the first draft also
  matches the operator's own interactive session; match on `session_id` instead
  once the ledger records it.
