# Validation Plan: the harness that proves the enrichment rearchitecture

Author: QA and Validation Engineer persona, enrichment rearchitecture engagement.
Date: 2026-08-25. Branch: `deterministic-gate-hardening`.

Foundation: `docs/quality/postmortem/2026-08-25-enrichment-overflow.md`,
`docs/quality/postmortem/2026-08-25-efficiency.md`,
`docs/quality/ENRICHMENT-REARCHITECTURE-PLAN.md`.

Rules of evidence for this document: every number is either re-derived here
from named artifacts (marked "verified"), taken from a postmortem as baseline
(marked "postmortem"), or an estimate with its basis stated. Code citations are
file:line against the current branch, re-read today, not against the killed
run's snapshot. Where this branch has landed a defence since the postmortems,
that is stated; where it has not, that is stated too.

New measurements produced for this plan and not previously recorded:

1. The salvage method recovers 10 of 10 discarded partitions, confirmed
   independently, with every requested component block AND every requested
   relationship block present. It requires seam-aware fence stripping: the
   re-injected fence must be removed together with its trailing newline. A
   line-based fence strip leaves a control character inside a JSON string and
   recovers only 7 of 10. (Verified; section 7.1.)
2. The current validator rejects 1,162 of 1,270 symbol citations (91.5%) in
   the parseable corpus with the single defined-elsewhere reason, and for all
   1,162 the cited symbol text is literally present in the cited file. Zero
   are absent. The referenced-at fix would accept the entire wrongly rejected
   set. (Verified; section 7.2.)
3. A mean-calibrated output projection is NOT a sufficient overflow gate at
   xhigh: it flags only 7 of the 12 recorded overflow sessions, and no
   headroom factor separates the classes (catching 12 of 12 false-flags 13 of
   20 safe partitions). Per-call output dispersion at xhigh spans 0.72x to
   1.90x of the prediction. The gate must therefore demand structural margin:
   predicted mean times worst observed dispersion under the ceiling for every
   partition, which xhigh cannot satisfy and low effort can. (Verified;
   section 4.2.)

Reproduction: the analysis scripts that produced these numbers run offline
over the recorded corpus (transcripts, ledger, failures, the VS Code store at
`/Volumes/Studio/dev/.demo-corpus/_out/vscode/index.db`). The verified session
inventory they emit is committed at
`docs/quality/rearchitecture/data/replay-corpus.json`.

---

## 1. Corpus inventory: what the killed run actually left behind

Verified today by content correlation, never by phrase matching. A run
partition call is identified by two independent keys: exactly one real user
message whose text begins with the contract partition prompt head, and summed
per-turn usage matching exactly one ledger row on the (tokens_in,
tokens_cached, tokens_out) triple. Killed-in-flight sessions carry a second
synthetic user record reading "[Request interrupted by user]".

The transcript directory holds 10,476 session files; 2,552 were touched on
2026-08-25. The 08:05 to 10:00 window contains 38 files, which resolve
completely:

| role | count | notes |
|---|---|---|
| run partition calls (rung 2a) | 32 | one per attempted partition |
| killed in flight at the 09:54 stop | 4 | zero answer text, thinking only |
| run orientation call (p1) | 1 | session `804013c8`, fable |
| operator interactive session | 1 | session `8ff72055`, started 08-24 |
| total | 38 | |

Cross-checks, all verified:

- Ledger: 32 rows, $40.43, every row `ok: true`, 31 rung-2a rows plus one
  p1_orientation row. The 31 rung-2a rows and 31 of the 32 partition sessions
  form an exact one-to-one matching on the token triple, with one session
  left over.
- The one partition call with no ledger row is `e65748d4`, the 1200 second
  subprocess timeout: billed, never ledgered, its content truncated mid-answer
  and unrecoverable. Its retry is `c43619cb`, whose first user message is
  byte-identical. This confirms the postmortem's double-billing finding.
- All 10 files in `failures/` are byte-identical to the final-turn text of
  exactly one session each (mapping in `data/replay-corpus.json`).
- Among the 32 partition calls: 12 contain a `max_tokens` stop (14 such stops
  total) and 12 ran more than one API turn. Three of the four
  killed-in-flight sessions had also hit `max_tokens` before the kill.
- The VS Code store exists and matches the postmortems: 15,219 files, 151,134
  symbols, 5,453 edges, exactly one enrichment row
  (`target_kind='subject-brief'`).
- The 4 killed-in-flight sessions contain zero characters of answer text.
  They are excluded from every salvage claim, exactly as the corrected
  postmortem excludes them.

The corpus is therefore complete, internally consistent, and sufficient for a
zero-live-cost replay suite. Nothing below rests on an artifact that was not
located today.

Caution that must survive into the suite: raw CLI stdout envelopes were NOT
preserved. The transcripts record per-turn API messages and usage; the ledger
records what the invoker computed from the envelope. Envelope-level fixtures
(section 7.5) are reconstructions whose field names come from the code that
parsed them, and Level 1 of the gauntlet must capture real envelopes to retire
that assumption.

---

## 2. Current code: what has landed and what has not

The postmortems describe the killed run's snapshot. Re-verified against the
current branch today:

Landed and real:

- Systemic-failure circuit: `analyzer/enrich/pipeline.py:180-266`
  (`BudgetMeter.note_result`, threshold 5 identical consecutive failures), fed
  on every call at `pipeline.py:383`. Unit tests exist at
  `tests/test_enrich_retry.py:278-330`.
- Soft per-run cost ceiling: engine path at `analyzer/enrich/engine.py:362`
  (`DEFAULT_MAX_COST_USD = 10.0`) with incremental submission at
  `engine.py:761-830`; ladder path via `BudgetMeter` cost and wall ceilings
  (`pipeline.py:225-250`), registry values in `demos/registry/vscode.json`
  ($200, 240 minutes).
- Live run telemetry: ledger streaming with `at` and `spent_usd` per row
  (`pipeline.py:617-641`), tailed by `LedgerWatch` in
  `scripts/testboard_emit.py` (commit 24ec757).
- Deliberate run records: `demos/runs/` is gitignored; keeper records are
  added with `git add -f` (commit f7501c3).
- Honest gap versus failed call separation at the terminal rung:
  `analyzer/enrich/ladder.py:581-636`. An unexamined item stays `escalate`
  and is never stamped `honest_gap`.
- Cache reads ledgered separately from fresh input: `pipeline.py:308-329`.

Not landed, verified missing today, with the postmortem's measured cost of
each absence:

| gap | where | measured consequence |
|---|---|---|
| no `--effort` pin; `--setting-sources user` still read | `engine.py:182-187`; `~/.claude/settings.json` still sets `effortLevel: xhigh` (verified today) | 67.8% of billed output was reasoning; 73% output reduction available (postmortem) |
| `stop_reason` discarded on every path | `InvokeResult` has no such field (`engine.py:104-130`); success return at `engine.py:236-243` | 11 of 31 completed partitions hit the ceiling invisibly (postmortem) |
| `num_turns` folded into usage only on the error branch | `engine.py:229`; success branch returns bare API usage | the drift alarm at `pipeline.py:390-400` starved across 12 multi-turn calls (postmortem) |
| no output-ceiling tripwire | no code compares `tokens_out` to the model ceiling anywhere in `analyzer/enrich/` | $18.82, 46.5% of run dollars, discarded (postmortem) |
| no salvage on parse failure | `ladder.py:445-459` writes `failures/` and returns None; `_parse_json_object` (`engine.py:468-488`) strips a leading fence only | 10 of 10 discarded partitions were recoverable (verified) |
| ladder has no parse-failure retry | `_invoke_parallel` makes one attempt (`ladder.py:439-460`); the engine path retries once with feedback (`engine.py:599-657`) | the postmortem names the ladder as the one call site without the retry |
| absorption is not checkpointed | rung 2a absorbs only after the whole pool drains (`ladder.py:504-525`); `store.commit()` only in `_finalize` (`ladder.py:832`) | the killed run banked 1 store row in 100 minutes (postmortem) |
| 2a census vanish still possible | a partition whose payload is None is skipped (`ladder.py:517-519`); requested targets that the model omits are skipped (`ladder.py:681-684`); census is built from states only (`ladder.py:830`) | 10 partitions' targets vanished from the census (postmortem) |
| symbol validator requires the definition site | `evidence.py:236-250`, `_symbols_by_path` membership only | 1,162 of 1,270 citations wrongly rejected (verified); about $450 of needless escalation (postmortem) |
| partitioner repeats components per chunk | `partition.py:249-264` | 3.52x duplicated component work, 2,003 slots for 569 components (postmortem) |
| ledger `targets` counts components only | `ladder.py:496-503` | rung-2a work understated about fourfold (postmortem) |
| retry attempts merge tokens into one row | `retry.py:159-160, 200-222` sums `cost_usd` across attempts, returns the last attempt's usage | the $3.41 timeout attempt is invisible in tokens; only its dollars appear (verified against `e65748d4`) |
| no per-call effort, session id, partition id in the ledger | `LedgerRow` fields at `pipeline.py:269-305` | run sessions must be identified by content correlation, as section 1 had to |
| `--json-schema` unused | no reference in `analyzer/` (verified) | the overflow failure class remains representable |

Everything in this plan hangs off this register. A fix that lands must flip
its row from missing to landed by pointing at the code and at the test.

---

## 3. The telemetry contract

No redesigned run executes a single call until every call records the
following, asserted by tests, not assumed. The ledger row (extending
`LedgerRow`, `pipeline.py:269-305`) is the unit of record; the run report
aggregates it.

Per call, required:

| field | source | why |
|---|---|---|
| `session_id` | CLI envelope | section 1 had to reconstruct identity from token triples; that is forensics, not telemetry |
| `partition_id` / batch id | the caller | joins the row to the plan and the census |
| `rung`, `phase`, `model_bound` | the caller | exists today as `model` |
| `models_answered` | envelope `modelUsage` | ground truth of what billed; the engine path already parses it (`engine.py:263-279`) but the ladder ledger never sees it |
| `effort` | the argv the invoker constructed | the pin, recorded where it was applied; absence of the field fails preflight (section 4.1) |
| `stop_reason` | envelope, top level | the overflow signal; currently discarded |
| `num_turns` | envelope, on success AND error | feeds the drift alarm at `pipeline.py:390-400` |
| `tokens_input`, `tokens_output`, `tokens_cache_creation`, `tokens_cache_read` | envelope usage, four separate fields | `pipeline.py:328` currently folds cache creation into `tokens_in`, which made a continuation's re-billed output indistinguishable from a large prompt |
| `targets_components`, `targets_relationships` | the caller | `targets` today is `len(part.component_ids)` (`ladder.py:500`), a fourfold understatement |
| `attempts`, and per-attempt (cost, four token classes, error) | the retrying invoker | `retry.py` currently sums cost and drops attempt tokens; the timeout double-bill was invisible |
| `cost_usd`, `wall_seconds`, `ok`, `error`, `at`, `spent_usd` | as today | already present |

Tests that the contract demands (all runnable at Level 0, zero live cost):

- T-TEL-1: `ClaudeCliInvoker` success-path parse surfaces `stop_reason` and
  `num_turns` from a reconstructed envelope fixture. This is the two-line fix
  the postmortem names; the test drives envelope JSON through the real parse
  by stubbing the subprocess, the pattern the existing argv tests already use.
- T-TEL-2: `_usage_tokens` (or its replacement) returns four classes, never
  three. Fixture: the recorded usage of session `ad7b77ab` (2 turns), whose
  cache_creation carries the re-ingested first turn.
- T-TEL-3: ledger row token totals reproduce the recorded ledger for all 31
  matched sessions when replayed from transcript usage
  (`data/replay-corpus.json` is the join table).
- T-TEL-4: a retried call writes per-attempt records such that the run report
  can show tokens for the attempt that timed out. Fixture: the `e65748d4` and
  `c43619cb` pair.
- T-TEL-5: every ledger row written by any phase carries `session_id`,
  `effort`, and both target counts, enforced in `record_ledger_row` as a
  refusal to write an incomplete row, and the refusal itself is tested.

---

## 4. Preflight gates

Gates are code that refuses to launch. Each gate names its test. All three run
in `--dry-run` mode too, so a plan preview shows what the launch decision
would be.

### 4.1 G1: effort explicitly pinned for every rung

Refuse launch unless every rung binding carries an explicit effort, threaded
into the invoker argv. Today no effort handling exists anywhere in
`analyzer/enrich/` (verified by search), the argv at `engine.py:182-187` has
no `--effort`, `--setting-sources user` at `engine.py:184` imports the
operator's settings, and the operator's settings still say `xhigh` (verified
today). `ModelSpec` (`models.py:64`) has no effort slot, so the fix lands in
the binding, not in a global.

- T-G1-1: argv construction test, extending the existing exact-argv tests:
  every rung's invoker argv contains `--effort <pinned>`.
- T-G1-2: a `LadderPolicy` whose binding lacks an effort fails preflight with
  a named reason, and the refusal happens before any invoker is built.
- Assumption to retire at Level 1: the CLI envelope does not (as far as any
  recorded artifact shows) echo the effort in force. Until a live probe
  confirms the flag's effect from the envelope or the output profile, the pin
  is asserted at argv level and verified behaviorally by the Level 1 output
  profile (a pinned-low call whose output is 4x the low calibration fails the
  level).

### 4.2 G2: projected output under the ceiling, with structural margin

The postmortem proves a text-only projection flags zero of the real
overflows. This plan's own measurement (new, verified) goes further: the
mean-calibrated projection (3,221 per component + 513 per relationship +
29,244 fixed, at xhigh) flags only 7 of the 12 overflow sessions, and no
scalar headroom separates the classes, because per-call dispersion at xhigh
runs 0.72x to 1.90x of the mean. Five overflows sat at predicted 56k to 59k,
under the 64k ceiling, and overflowed anyway.

The gate is therefore not "predicted mean under ceiling". It is:

    predicted_mean(partition, effort) * dispersion_max(effort) < ceiling
    for EVERY partition, else refuse the run.

with `dispersion_max` the maximum observed actual/predicted ratio for that
effort, taken from recorded calls, refreshed whenever model or schema
changes. At xhigh, dispersion_max is 1.90 (verified, n=32, total billed output per
session including continuation turns, which is the economically relevant
quantity), and the killed
run's configuration fails this gate 113 of 173 times on the mean alone
(postmortem), which is the correct refusal. At low effort the postmortem's
replay measured a maximum of 29,115 output tokens on the corpus's own worst
prompts, and the redesigned schema shrinks that further, so the gate passes
with real margin rather than with luck.

- T-G2-1: the gate, given the killed run's 173-partition plan and xhigh
  calibration, refuses.
- T-G2-2: the gate flags all 12 recorded overflow sessions when evaluated on
  the recorded corpus (fixture: `data/replay-corpus.json` target counts and
  stop reasons).
- T-G2-3: the text-only projection variant of the gate is asserted to flag 0
  of 12, kept as a permanent regression proof of why the multiplier exists.
- Calibration inputs are ledger data, never guesses: the test refuses a
  calibration table whose `basis` does not name a run.

### 4.3 G3: budget caps present and armed

Refuse launch unless per-run cost ceiling, per-run wall ceiling, and per-call
timeout are all finite, and additionally a per-call cost backstop exists
(`--max-budget-usd` per call is postmortem fix 8; currently absent). The
ceilings exist on both paths today (section 2); what is missing is the
refusal when they are absent: `LadderPolicy.max_cost_usd` defaults to None
(`pipeline.py:445`), which today means unlimited and must come to mean
not launchable outside dry runs.

- T-G3-1: a config with any of the three ceilings absent refuses with a named
  reason.
- T-G3-2: the projection from G2, times the calibrated cost model, must fit
  under the cost ceiling, else refuse: a run that projects over its own cap
  is not allowed to discover that live. Tested with the killed run's plan
  against its $45-era ceiling (refuses) and against the current registry $200
  (also refuses at xhigh; passes at the redesign's projection).

---

## 5. In-flight tripwires, and the tests that prove they fire

Tripwires are armed state, not dashboards. Every one appears in the scorecard
with `armed` and `fired` flags, so an unarmed tripwire is visible after the
fact (section 6).

### 5.1 W1: output ceiling, warn at 0.85, abort above 1.0

Acts on per-call `tokens_output` (and `stop_reason == "max_tokens"`) the
moment a call returns. Warn logs a note at 0.85 of the model ceiling; a call
at or above the ceiling marks the partition failed-for-salvage (section 7.1)
and, when two calls in one run hit the ceiling, stops launching new work,
because the second occurrence proves the projection wrong, not the call
unlucky. The recorded run would have warned on call 1 (56,605 tokens, 88%)
at $1.77 spent and stopped on call 5 at $6.44 (postmortem, re-checked against
the ledger today: rows 2 and 6 of `ledger.jsonl`).

- T-W1-1: replaying the recorded ledger rows through the tripwire in row
  order fires the warn on the first 2a row and the abort on the fifth, at the
  recorded cumulative spends.
- T-W1-2: a run of rows all under 0.85 fires nothing.

### 5.2 W2: the agentic-drift alarm actually fires on the success path

The alarm exists (`pipeline.py:390-400`) and was starved by `engine.py:229`
placing `num_turns` in usage only on the error branch. Zero tests today
reference `num_turns` or the drift note (verified by search over `tests/`).
A unit test that hand-feeds `usage={"num_turns": 2}` into `MeteredInvoker`
would pass while the real path stays starved, so the required test is an
integration across the seam:

- T-W2-1: a reconstructed success envelope with `num_turns: 2` goes through
  `ClaudeCliInvoker.__call__`'s real stdout parse (subprocess stubbed), the
  resulting `InvokeResult` through a real `MeteredInvoker`, and the drift note
  must appear in `ctx.notes`. This test fails on today's code, which is the
  point; it is the regression that would have caught the starvation.
- T-W2-2: same wire with `num_turns: 1` produces no note.
- T-W2-3: the 12 multi-turn sessions in `data/replay-corpus.json` replayed as
  envelope fixtures produce exactly 12 drift notes.

### 5.3 W3: cumulative cost tracks projection

The run carries its G2/G3 projection. After each ledger row, if
`spent / projected_spend_at_this_call_count` exceeds a stated factor (default
1.5) the run stops launching new work with a named reason, using the same
drain-and-skip semantics the ceilings already have (`ladder.py:481-488`).
Distinct from the absolute ceiling: this fires while money remains, on the
grounds that the projection is already disproven.

- T-W3-1: replaying the killed run's ledger against its own $80-at-low
  projection stops within the first three rows (the xhigh rows cost about 4x
  the projected per-call figure).
- T-W3-2: a ledger tracking within the factor never fires.

### 5.4 W4: the systemic-failure circuit stays armed

Landed (`pipeline.py:180-266`), fed at `pipeline.py:383`, unit-tested at
`tests/test_enrich_retry.py:278-330`. Two additions this plan requires:

- T-W4-1 (integration): a mocked invoker that fails identically five times
  inside `_invoke_parallel` causes the pool to drain and skip pending jobs,
  and the skipped jobs appear as not-attempted in the census, not as failures
  and not as gaps. The existing tests exercise `BudgetMeter` directly; none
  exercises the ladder wiring end to end.
- T-W4-2 (arming canary): the scorecard writer refuses to emit a scorecard
  whose tripwire list lacks `systemic_failure` with `armed: true`. Disarming
  the circuit then becomes visible at sign-off rather than silent.

### 5.5 W5: timeout accounting

A per-attempt timeout kill must still produce a ledger record for the
attempt (the telemetry contract's per-attempt requirement). The recorded run
lost session `e65748d4` entirely: 128,000 output tokens billed, no row. With
per-attempt records, a timeout is charged, visible, and counted by W3.

- T-W5-1: an invoker whose first attempt times out and whose second succeeds
  yields a row (or attempt sub-records) showing both attempts' tokens, and
  the budget is charged for both.

---

## 6. The postflight scorecard

Machine-readable, one per run, any level. Schema committed at
`docs/quality/rearchitecture/data/enrichment-scorecard.schema.json`, draft-07,
`additionalProperties: false` throughout, following the precedent of
`docs/quality/scorecard.schema.json`. A run without a scorecard did not
happen; the wrapper that launches a run writes the scorecard in the same
process that writes the run report, and the gauntlet's sign-off reads the
scorecard, never the console.

Scored dimensions and their hard constraints:

- Cost versus projection: both recorded, plus the explicit ratio. The
  projection carries its `basis`; a projection with no basis fails schema.
- Overflows: count plus the offending rows. Sign-off criteria reference the
  count directly.
- Discards: count, salvaged, unrecovered, and dollars. Salvaged is not a
  pardon: a Level 2 run with discards fails even if salvage recovered them,
  because salvage is the airbag, not the brake.
- Escalation by cause, with the causes enumerated in the schema
  (`evidence_rejected_referenced_elsewhere`, `evidence_rejected_fabricated`,
  `self_declared`, `omitted_by_model`, `parse_failure`, `other`). The killed
  run could not tell a validator bug from hard work; this field is what makes
  that distinction a number.
- Census: `total_targets` counted from the plan, `by_state` counts,
  `accounted` equal to the total, and `vanished` schema-pinned to a maximum
  of 0. The schema makes a scorecard with vanished targets invalid, which
  makes census conservation a structural property of sign-off. The code-side
  invariant (every planned target reaches a state even when its call fails,
  closing `ladder.py:517-519` and `ladder.py:681-684`) has its own replay
  test, R6.
- Grounding: citations checked, valid, invalid split into fabricated versus
  other, and `validator_version`, because rates across validator versions are
  not comparable and the schema forces the writer to say which one ran.
- Tripwires: every tripwire from section 5 appears with `armed` and `fired`.
- Quality: the baseline reference and the blind spot-check verdicts
  (section 9).
- Verdict: `pass` with an empty `blocking` list, or the blocking reasons.

---

## 7. The replay suite: zero live cost, built from the corpus

Fixture root (to be created at implementation time):
`tests/fixtures/replay-2026-08-25/`, populated from the artifacts named in
`data/replay-corpus.json`. The transcripts live outside the repo; the fixture
build step copies the needed sessions in, and the suite fails loudly if a
fixture is missing rather than skipping. Everything below ran today as
offline analysis; the suite turns each into a permanent test.

### 7.1 R1: salvage recovers 10 of 10, and refuses the unrecoverable

Verified today. Fixtures: the 10 `failures/` files with their sessions' full
turn sequences. The salvage under test: strip a re-injected fence at each
turn seam together with its newline, dedupe the longest suffix/prefix overlap
at the seam, take the brace span, parse.

- Pass: 10 of 10 parse, and for each the parsed object contains every
  component id and every relationship key the partition prompt requested
  (verified today: also true of relationships, which the postmortem did not
  claim).
- Negative fixtures: the 4 killed-in-flight sessions and `e65748d4` must
  return unrecoverable. Salvage must never fabricate a partial object from
  thinking-only content.
- Sharpness: the seam can mangle characters inside a string (a lost separator
  was observed in `4d94e8dd`, "src" joined to "extension"), so salvaged
  payloads MUST still pass the evidence validator; the suite asserts that
  salvaged evidence goes through validation rather than being trusted. A
  salvage that recovers the block but with a now-invalid citation surfaces as
  a validation failure, not as silent acceptance.
- Regression proof of the seam rule: the line-based fence strip variant is
  asserted to recover only 7 of 10 (verified today), pinned so nobody
  simplifies the salvage back into the broken form.

### 7.2 R2: the fixed symbol validator, accepting real citations, rejecting fabricated ones

Verified today over the parseable corpus (31 of 32 partition responses,
salvage included): 1,270 symbol citations; the current
`EvidenceValidator._check_symbol` (`evidence.py:236-250`) accepts 104,
rejects 1,162 as defined-elsewhere, 3 as unknown symbol, 1 as unindexed
path. For all 1,162 defined-elsewhere rejections the symbol text is present
in the cited file in the pinned working tree; for 0 it is absent. (The
postmortem's 1,128 of 1,215 was measured over deduplicated blocks; both
measurements agree that more than 90% fail with the one reason.)

The fix must distinguish "referenced at" from "defined at", not loosen the
check. Suite:

- Pass set: the 1,162 wrongly rejected citations validate under the fixed
  validator, with the result recording `referenced_at`, not `defined_at`.
- Reject set, still rejected: the 3 unknown-symbol and 1 unindexed-path
  citations, plus synthesized fabrications built from the pass set: symbol
  swapped for a real symbol absent from that file, path swapped to a file
  that does not contain the symbol, line pushed past end of file. One
  fabrication per class per real citation, generated deterministically.
- The 104 currently accepted citations still validate as `defined_at`.
- Escalation effect is recomputed through the real `state_from_block`, and
  the relationship escalation rate moves from 47% toward the postmortem's
  recomputed 12%; the suite asserts the recomputation runs, with the exact
  rate recorded in the scorecard of the next run rather than asserted as a
  fixed number here.

### 7.3 R3: ledger accounting against recorded usage

Fixtures: the 31 matched (session, ledger row) pairs. The suite replays each
session's per-turn usage through the accounting under test and requires the
four token classes separately (T-TEL-2/3), the continuation turns'
cache_creation visibly separate from prompt input, and the retry pair
(`e65748d4`/`c43619cb`) yielding per-attempt visibility (T-TEL-4).

### 7.4 R4: prompt-shape regression

Fixtures: the 31 recorded partition prompts (from the transcripts) plus the
store. Any prompt or schema change replays `build_contract_partition_prompt`
(and its successors) against the recorded partitions and reports the
projected token delta per partition using the postmortem's fitted char-token
calibration (validated at 0.1% error against a live probe; postmortem). The
suite fails when a change increases projected output for any recorded
partition beyond a stated tolerance without a spec note saying so. This is
how "this schema change saves X" claims (section 10, C2) get their evidence
at zero cost.

### 7.5 R5: envelope-to-alarm integration

The reconstructed-envelope fixtures behind T-TEL-1 and T-W2-1/2/3. Field
names are taken from the parsing code (`engine.py:218-243`) because raw
stdout was not preserved; each fixture file carries a header noting that
reconstruction, and Level 1 captures real envelopes to replace them. Until
then this suite proves wiring, not CLI behavior, and says so.

### 7.6 R6: census conservation and partitioner shape

- Census: replaying the recorded payloads through the real absorb path with
  one partition's payload forced to None must leave that partition's targets
  in an explicit non-vanished state under the fixed design. On today's code
  this test fails (targets vanish, `ladder.py:517-519`), which is its
  purpose.
- Partitioner: `plan_partitions` over the real store's architecture
  reproduces the killed run's shape (173 partitions, 2,003 component slots
  for 569 components; postmortem, reproducible offline). After the
  partitioner fix, the same fixture must show each component exactly once,
  and the census total must still account for every component and
  relationship, which is the structural proof that de-duplication lost
  nothing.

---

## 8. The graduated gauntlet

No level is skipped; no level is entered while the previous one is red; a red
level, once fixed, reruns from its own start, not from where it broke. All
dollar figures are scaled API-equivalent units, consistent with the
postmortems. Every level ends with a scorecard; sign-off is a reading of the
scorecard against the level's criteria, and Level 2 to 3 sign-off is the
owner's, by name.

### Level 0: replay. Cost $0.

Run: suites R1 through R6, plus T-TEL, T-G, T-W tests.
Sign-off criteria, all mechanical:

- R1 salvage 10 of 10, negatives refused.
- R2 pass set 1,162 of 1,162, reject sets 100%, distinction recorded.
- R3 accounting reproduces all 31 rows in four classes.
- R4 baseline deltas established for the redesigned prompts, on record.
- R5 wiring green (with the reconstruction caveat on record).
- R6 census conservation green under the fixed design; partitioner shape
  green.
- Every tripwire test fires its tripwire; every gate test refuses its bad
  config.

### Level 1: micro. Revised by section 13.6: the consolidated probe program plus this micro-run, cap $50. The micro-run itself: estimated $3 to $6, capped $10 within that envelope.

Run: orientation plus about 5 partitions on the small validation subject,
efforts pinned, all gates armed, deliberately including one partition
predicted near the top of the projection band. Also: kill the run once,
deliberately, mid-partition, then resume with `--update`.

Basis for the estimate: measured low-effort replay outputs of 9.5k to 29k
tokens per call and the postmortem's $80-per-173-partitions rung-2a figure
(about $0.46 per call), plus the orientation call's recorded $0.75.

Sign-off criteria:

- Telemetry: every ledger row carries every contract field of section 3;
  raw CLI envelopes captured and archived, R5 fixtures replaced or confirmed.
- Effort: recorded output tokens per call within the low-effort calibration
  band; a call at 4x the band fails the level (this is the behavioral check
  behind G1's argv assertion).
- Gates: demonstrably armed (the run report shows the preflight evaluation).
- Kill-safety: the killed-and-resumed run loses at most the in-flight
  partitions, the store shows per-partition banked work, the census of the
  resumed run accounts for every target, vanish count zero.
- Scorecard: validates against the schema, tripwires all armed, none fired
  except any deliberately provoked.

### Level 2: full small subject. Estimated $10 to $30, cap 1.5x its own projection.

Run: the complete redesigned pipeline on the validation subject, no caps
loosened, quality baseline comparison per section 9.

Sign-off criteria:

- Cost within 25% of the preflight projection (the projection is on the
  scorecard with its basis).
- Zero overflows. Zero discards (salvage may exist; it must not be needed).
- Census: vanished 0, accounted equals planned, by construction of the
  schema.
- Escalation by cause shows `evidence_rejected_referenced_elsewhere` at or
  near zero (the validator fix holds under live output).
- Quality: blind spot-check pass per section 9; coverage and grounding at or
  above the baseline capture.
- Owner reviews the scorecard and signs Level 3 entry explicitly.

### Level 3: canary, then full VS Code.

Canary: about 17 partitions (10% of the recorded plan), hard cap $30,
estimated $9 to $25 (basis: the efficiency postmortem's per-partition figures
across tiers A through C). Criteria: identical to Level 2, evaluated on the
canary scorecard, plus wall-time per call within 2x of Level 2's per-call
median (VS Code partitions are bigger; the factor is stated so drift is a
number, not an impression).

Full run: only after canary green and explicit owner sign-off on both the
Level 2 and canary scorecards. Projection per the Phase 2 adjudicated bands
(section 13.6: full run $71 to $116 at Opus $5/$25, central $81; $101 to
$166 at $15/$75, central $120; the Opus arbitration on record collapses the
dual band before this point); cap at 1.5x the accepted projection; the
registry ceiling (`demos/registry/vscode.json`, $200) is raised deliberately
in the same commit as the sign-off note if the accepted projection requires
it. W3 armed at 1.5x. The run is boring or it stops itself.

Gauntlet cost envelope, revised in section 13.6 for the consolidated probe
program: total live spend before the full VS Code run is bounded by the
Level 1 cap ($50, probes plus micro-run, $32 expected at Opus $5/$25), plus
Level 2 at 1.5x a projection of at most $30, plus the $30 canary cap: worst
case $125, expected roughly $70 to $90. Spend before any medium-scale live
run (Levels 0 and 1 only): at most $50, expected about $32.

---

## 9. The quality baseline: "no quality sacrifice" as a measurement

Quality claims compare two architectures on the same subject. Nothing is
comparable to a number that was never captured, so the baseline is captured
before the redesign runs anywhere (Level 0 output for the corpus baseline;
Level 2 for the live one).

Baselines:

1. VS Code corpus baseline, free, already paid for: the 31 recovered
   partition responses (salvage included) covering the killed run's attempted
   partitions. Re-validated under the FIXED validator so grounding rates are
   comparable (old-validator rates never mix with new; the scorecard's
   `validator_version` enforces the same rule at run time).
2. Validation-subject baseline: captured once on the small subject at
   Level 2 time by running the CURRENT architecture with only the landed
   defences, under its own caps, so before and after exist for the same
   subject at the same commit of the parser. Estimated cost is inside the
   Level 2 envelope; if the owner declines the extra spend, the VS Code
   corpus baseline is the sole baseline and the plan says so on the
   scorecard.

Metrics, in fixed order of authority:

1. Coverage: census accounted equals planned, vanish zero, per architecture.
2. Grounding validity under the fixed validator: share of items with at
   least one valid citation, and the referenced/defined split.
3. Blind spot-check accuracy: a stratified sample (by importance ranking) of
   25 components and 25 relationships from the overlap of both architectures'
   coverage. Each sampled contract's claims are verified against the pinned
   working tree (`/Volumes/Studio/dev/.demo-corpus/vscode`, commit 474a349a)
   and scored correct / partial / wrong / unscoreable. Scoring is blind:
   items from both architectures are shuffled into one batch, architecture
   identity stripped, and the scorer (the adjudication rung, or the owner for
   a sample of the sample) sees facts and claims only. Verdicts land in both
   scorecards with `blind: true`; non-blind verdicts are recorded but
   excluded from the comparison.
4. Honest-gap rate: tracked, not gated, with the rule that a redesign
   converting answered items into honest gaps is a quality regression unless
   each such gap survives adjudication.
5. Product-field completeness: reader-facing fields non-empty and
   schema-valid, per architecture.

Pass rule for "no quality sacrifice" at Level 2 and 3: coverage and grounding
not below baseline; blind spot-check correct-rate not below baseline by more
than 8 percentage points, which is the honest detectability floor at n=50
(at these sample sizes a smaller true regression can hide; the plan states
this rather than pretending n=50 proves equality). Any `wrong` verdict on a
`critical`-importance item blocks regardless of rates.

---

## 10. Claim taxonomy: making the Phase 2 review mechanical

Every claim in the Architect's and Prompt Engineer's specs gets tagged with
one type. A claim with no tag, or a tag with missing evidence, goes back to
its author. The review is then a table walk, not a debate.

| type | the claim sounds like | required evidence | reviewer action |
|---|---|---|---|
| C1 measured fact | "output is 77.7% of spend" | named artifact plus the derivation (script or command) that reproduces the number | re-run or spot-check the derivation; a number that cannot be re-derived is struck |
| C2 calibrated projection | "tier C costs about $33" | the fit inputs, the fitted form, and its error against at least one held-out real observation; confidence interval stated | check the held-out error exists and the interval is honest; "about" with no interval goes back |
| C3 quality-neutral change | "quality trade: none" | the metric that would move if the claim were false, and the R4/Level test that measures it on named fixtures | confirm the metric and test exist and are scheduled; unmeasurable neutrality goes back (the postmortem's rejected "free deletions" of `data_flow_description` and `help_text` are the cautionary precedent) |
| C4 structural impossibility | "targets cannot vanish" | the code shape that makes the state unrepresentable, plus a test that tries to produce the state and fails, plus the schema constraint where one applies (census `vanished` max 0) | verify the test attacks the invariant rather than restating it |
| C5 existence claim | "the CLI supports `--json-schema`" | a recorded artifact showing it, or an explicit Level 1 probe task with its cost; version-stamped | unverified existence claims become Level 1 probe line items, never assumptions |
| C6 model-behavior claim | "low effort is stable" | at least N independent probes with dispersion reported (the two medium-effort probes that disagreed sharply are the precedent; one probe is an anecdote) | check N and dispersion; N=1 goes back |

Standing reviewer rules: a savings claim (C1 or C2) about tokens must state
which of the four billing classes it moves. A projection whose basis is
another projection inherits the weakest basis in the chain and must say so.
Both postmortems' retraction lists are the required reading before tagging;
the first draft's nine wrong figures were all C1 claims with missing
derivations.

---

## 11. Highest-risk unverified assumptions, stated as work

1. Envelope fidelity: no raw CLI stdout envelope from the killed run was
   preserved, so `stop_reason`, `num_turns`, `session_id`, and `modelUsage`
   field names and semantics rest on the code that parsed them and on CLI
   documentation, not on a recorded artifact. Level 1 captures and archives
   raw envelopes; R5 fixtures are then regenerated from reality.
2. Effort pinning efficacy: `--effort low` behavior is measured on 4 prompts
   (postmortem replay). Whether the flag overrides `--setting-sources user`
   inheritance in all cases is asserted from CLI semantics, not proven. The
   Level 1 output-profile check is the proof, and it is cheap.
3. Rung 2b economics: escalation-rate and Opus-cost figures carry the
   postmortem's stated plus or minus 30%, resting on the unverified
   assumption that Opus's fixed reasoning overhead resembles Sonnet's. The
   canary at Level 3 is sized to measure this before the full run.
4. Rung 2c is unmeasured and structurally unbounded in the current design
   (postmortem finding). The redesign must bound it; the gauntlet cannot,
   because no recorded 2c call exists at all.
5. Dispersion calibration at low effort: `dispersion_max(low)` currently
   rests on 4 replay calls. Level 1 adds calibration points; until then G2
   holds the xhigh-derived worst case (1.90) as the conservative default for
   every effort.

---

## 12. Deliverable index

- This plan: `docs/quality/rearchitecture/VALIDATION-PLAN.md`
- Verified corpus inventory (machine-readable):
  `docs/quality/rearchitecture/data/replay-corpus.json`
- Scorecard schema:
  `docs/quality/rearchitecture/data/enrichment-scorecard.schema.json`
- Phase 2 adjudication measurements (machine-readable):
  `docs/quality/rearchitecture/data/qa-adjudication.json`
- Phase 2 testability pass:
  `docs/quality/rearchitecture/reviews/QA-TESTABILITY-PASS.md`
- Phase 2 closing verdict:
  `docs/quality/rearchitecture/reviews/QA-FINAL-VERDICT.md`
- Source artifacts: ledger and failures under
  `demos/runs/vscode/2026-08-25/enrichment/`; transcripts under
  `~/.claude/projects/-Volumes-Studio-dev-solution-explorer/` (identified per
  section 1's method, never by phrase); store at
  `/Volumes/Studio/dev/.demo-corpus/_out/vscode/index.db`; pinned tree at
  `/Volumes/Studio/dev/.demo-corpus/vscode`.

---

## 13. Addendum, Phase 2: adjudicated constants and new obligations

Recorded after the testability pass over the two designer specs
(`reviews/QA-TESTABILITY-PASS.md`, which carries the derivations). Each item
amends this plan in place.

### 13.1 Adjudicated calibration constants

These replace the corresponding figures wherever this plan's gates and
fixtures calibrate, and `data/qa-adjudication.json` is their machine-readable
record:

- Chars per billed prompt-side token, marginal: **2.85** (fit slope over all
  35 recorded first turns, max residual 6.32%), with a separate per-call
  fixed prompt-side overhead of **10k to 12.5k tokens** (mostly cache read
  after warm). Per-session average ratios that fold the overhead in (1.71)
  are not marginal rates and must not be used for pricing.
- Output at `--effort low`, current schema: **1,050 per component, 382 per
  relationship, 1,369 fixed per call** (LSQ over the four low replay probes,
  max error 5.7%; fixed-term bounds 500 to 2,800). Thinking measured 0 to
  about 455 tokens per call by the chars method. The G2 gate's low-effort
  calibration starts here; the 1.90 dispersion worst case of section 4.2
  still applies until Level 1 widens the sample.
- Prices: Sonnet $3/$15 and Fable $10/$50 verified against ledger rows (1.6%
  and 1.8% residual, with unique input billing as 1h cache creation at 2x).
  **Opus is unverified offline; $5/$25 assumed. The first pilot Opus ledger
  row arbitrates it, and Level 2 sign-off requires that arbitration on
  record.** A 3x error here is the single largest open cost risk.

### 13.2 R2 fixture upgrade: the referenced-at index is in the store

The store's `signals` table, `kind='symbol_reference'` (157,508 rows,
`{name, count}` with `file_id` and `line`), covers **1,162 of 1,162** of the
corpus's wrongly rejected symbol citations. The R2 replay fixture therefore
derives expected verdicts store-only: `referenced-at` from the signal index,
`defined-at` from `_symbols_by_path`, no filesystem reads. The fabricated-
citation reject set is unchanged. The validator fix that R2 tests must load
this index in `EvidenceValidator._load`.

### 13.3 Telemetry contract additions (section 3)

- `tokens_cache_creation_1h` and `tokens_cache_creation_5m`, from
  `usage.cache_creation.ephemeral_*`: verified present in the recorded API
  usage blocks (the killed run's writes were 100% 1h class). Whether the CLI
  stdout envelope forwards the breakdown joins the Level 1 envelope capture.
- `prefix_hash` (sha256 of the rendered system-append prefix), adopted from
  the Prompt Engineer's spec: detects mid-run prefix drift, the silent cache
  invalidator.
- `entries_returned` alongside the two target counts, for census
  conservation per call.
- Probe runs ledger their argv (including `--effort`) like any other run;
  this pass had to recover probe efforts by matching billed output against
  postmortem tables, which is forensics, not telemetry.

### 13.4 New Level 0 tests accepted from the designer specs

- Merge-property test (Architect V-4): a delta-only 2b/2c response merged
  over a banked block never loses an established answer, and extra keys
  outside `todo` are dropped by the absorber. Joins R6.
- Cache telemetry gate (both specs' section 8/10 predicates): thresholds set
  from the first pilot's ledger rows (M-P1/M-6), not invented; the gate then
  runs per ladder run and lands in the scorecard's tripwire list.
- Two zero-cost harness runs scheduled on the R2/R6 recompute harness, both
  currently flagged as estimates in the specs: the failed-questions-per-item
  distribution (the 1.5 / 1.0 estimates), and the 2b population under the
  new schema rules (the 939-item assumption, M-P5).

### 13.5 Rung-0 identity provenance (V-3), half resolved

`framework` and `port` identity answers can cite signal rows (`file_id`,
`line`). `language` and `type` have no per-attribute signal row; before
R-14 lands, the rung-0 design must name the derived-evidence convention for
them (dominant-extension census or manifest row), and the R2-style fixture
for identity answers tests both forms.

### 13.6 Addendum, Phase 2 final: the consolidated probe program and re-anchored projections

Recorded after the closing verdict pass (`reviews/QA-FINAL-VERDICT.md`,
which carries the regeneration evidence and the consolidated table).

- **Level 1 is redefined** as the consolidated probe program (merged
  M/M-P/plan series: 33 to 35 live calls) plus the micro-run of this plan's
  original Level 1. Cap **$50**; expected **$32** at Opus $5/$25, up to $48
  if the Opus price arbitrates high (the M-2 probe's bound is dual, like
  the price). Zero-cost harness work (M-P5 populations and failed-questions
  distribution, the replay fixtures, threshold-setting from pilot rows)
  runs at Level 0 or rides Level 1 rows for $0, and the harness runs come
  BEFORE any live probe spends.
- **Level 3 projections re-anchored** from the postmortem-era $110 to $250
  to the Phase 2 three-model convergence: ladder $60 to $95 central $66 at
  Opus $5/$25 ($90 to $145 central $105 at $15/$75); full run $71 to $116
  central $81 ($101 to $166 central $120). The dual band collapses when the
  first pilot Opus ledger row lands, which remains a Level 2 sign-off
  requirement.
- **Escalation-population figure, ruled**: both specs harmonize on the
  postmortem's 939 (285 components + 654 relationships); 284 is an integer
  floor artifact. The M-P5 harness recompute supersedes both and is the
  number the scorecard's census uses thereafter.
- **G2 calibration bookkeeping**: the new-schema per-call fixed output
  limit for cap 21 is 1,688 (cap drops to 20 if M-P1 measures the 2,800
  bound); `dispersion_max(low)` from the merged M-1/M-P2 probe is the
  cap-relaxation input, n at least 10.
- Four editorial cross-spec exceptions (E-1 to E-4) are recorded in the
  final verdict with one-line fixes; none blocks presentation and none
  changes a gate or cap in this plan.
