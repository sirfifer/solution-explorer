# Implementation Delta: Orchestration

Author: Agent Orchestration Architect persona. Date: 2026-08-26.
Status: implementation delta against ORCHESTRATION-SPEC.md revision 2, written
after the repair effort of 2026-08-25 to 26 and the five live runs it bought.
Baseline artifacts: the v2 full build at
`/Volumes/Studio/dev/.demo-corpus/_out/unamentis-ios/runs/full-build/`
(`ledger.jsonl`, `report.json`, `adjudication.json`, `synthesis.json`,
`progress.jsonl`, `REPORT.md`), the effort postmortem
(`docs/quality/ENRICHMENT-EFFORT-POSTMORTEM-2026-08-26.md`), and the F-9 cache
probe (`docs/quality/rearchitecture/data/f9-cache-probe-2026-08-26.md`).

Every number in this document is re-derived from a named artifact or labeled an
estimate with its basis. Code line references are pinned to commit `a98479b`
(HEAD at time of writing), because the working tree carries live uncommitted
edits (a new `compact.py`, modified `ladder.py`, `prompts.py` and others,
implementing the compact schema and a prompt prefix seam). Section 0.4 records
what that in-flight work means for this delta.

Zero model calls were made for this document. The one live measurement it
relies on beyond the run ledgers, the F-9 probe, was run by the coordinator
and is cited as a measurement doc, not reproduced.

---

## 0. What changed since revision 2

### 0.1 Landed since the spec was written, verified in HEAD source

| revision 2 item | status at `a98479b` | where |
|---|---|---|
| R-1 effort pin | LANDED. `--effort` always on argv, `DEFAULT_EFFORT = "low"` | `engine.py:73`, `engine.py:209-215` |
| R-2 success-path `stop_reason`, `num_turns` | LANDED | `engine.py:273-285`, `pipeline.py:448-487` |
| R-4 parse salvage plus ladder corrective retry | LANDED (fence strip, brace span, truncation repair, shape guard, one retry) | `engine.py:510-659`, `ladder.py:498-522` |
| R-5 validator referenced-at fix, store-only | LANDED (`symbol_reference` signals, distinct referenced verdict) | `evidence.py:119`, `evidence.py:153`, `evidence.py:349-356` |
| R-6 ledger fields, partial | PARTIAL. `tokens_cache_write` and `tokens_fresh_in` split landed (`pipeline.py:307-308`); `effort`, `stop_reason`, `num_turns`, `session_id`, `partition_id` landed (`pipeline.py:309-313`). `prefix_hash` and the 1h/5m TTL split did NOT land |
| R-9 absorb-on-completion checkpointing | LANDED. Banked per call in the coordinator | `ladder.py:531-551` |
| Byte-bounded fact blocks and verify batches | LANDED | `passes.py:161`, `passes.py:164-183` |
| Batched verify passes | LANDED (edges, findings, identity) | `passes.py:349`, `passes.py:748`, `passes.py:941-951` |
| Parallel ladder with `warm_first` | LANDED | `ladder.py:446-569`, `pipeline.py:552-554` |
| Identity-payload trim for verify-identity | LANDED at `71849ad`, AFTER the v2 run started, so v2 paid the untrimmed price | `prompts.py:1057-1097` |

NOT landed at HEAD: any caching mechanism (no caching flag on the argv, no
prefix file, no `prefix_hash`), the meta-phase digests (determination still
ships full corpora, `determine.py:227-287`), trigger-class routing (2b receives
every escalated item, `ladder.py:655-677`), and the tier C schema (in flight in
the working tree, see 0.4).

### 0.2 Measured facts that supersede revision 2 assumptions

1. **The Opus price is arbitrated: $5/$25.** Revision 2 carried it dual and
   demanded the first pilot Opus ledger row. The v2 ledger has 93 Opus rows.
   Modeling every row at base input $5/MTok (2x for 1h cache writes, 0.1x for
   reads) and output $25/MTok reproduces the ledger's Opus cost within 3.7%
   ($28.95 modeled vs $30.02 ledgered); at $15/$75 the model overshoots 2.9x
   ($86.85). Sonnet at $3/$15 fits within 4.0%, Fable at $10/$50 within 2.5%.
   The 2.5 to 4% residual is consistent across models (CLI side-billing) and is
   the tolerance the price predicate pins. Every dual-priced figure in
   revision 2 collapses to its $5/$25 column.
2. **F-9 is closed, favorably, with one extra flag.** The probe doc shows the
   naive `--append-system-prompt-file` FAILS (the default system prompt carries
   about 5,860 per-call dynamic tokens, so the prefix diverges before appended
   content and nothing is ever read), and that adding
   `--exclude-dynamic-system-prompt-sections` makes the system block
   byte-stable: the second identical call read 14,560 tokens at 0.1x and wrote
   762, cost falling from $0.0926 to $0.0096. Prefix savings are now priced at
   read rates unconditionally. PROMPT-SPEC section 10's fail-contingency
   booking is closed on the favorable side.
3. **Session resume is verified headlessly.** `claude -p --resume <session_id>`
   re-reads the entire prior context at 0.1x and writes only the new message
   (probe addendum: read 15,544, wrote 21, $0.0056 against a cold-equivalent
   $0.08). One-shot per call, serial within a session.
4. **Meta-phase fixed cost is measured, and it is worse than the estimate.**
   Revision 2 allowed $10 to $20 for P3 to P5. On the 168-component v2 subject:
   P3 $17.61, P4 $2.24, P5 $14.83, work orders $4.68, total $39.36 (ledger
   sums). The earlier $27.86 figure was run 3 (cycle2). Either number
   invalidates ladder-only projections, and M-7 is closed by measurement.
5. **Low-effort output dispersion has first real data.** The 19 2a calls at
   pinned low effort produced 305 to 1,047 output tokens per target (mean 611,
   median 579), a max-to-mean ratio of 1.71 on the contract schema. This does
   not yet relax G2's 1.90 (different schema than tier C, n=19), but it is the
   first measured `dispersion_max(low)` datum and it points the same direction
   the spec predicted.
6. **The v2 escalation record replaces the postmortem's baseline populations.**
   Climb events 267 (2b received 147 targets, 2c received 120, ledger `targets`
   sums); distinct items that climbed or gapped 168 (`report.json`
   escalations). The commissioning brief's "2b received 210 and resolved 48
   (23%)" does not re-derive from the v2 artifacts; the v2 numbers are 147
   received, 27 terminal-grounded at opus (census `by_state`), 18.4%. This
   delta uses the v2 numbers throughout and flags the discrepancy rather than
   silently adopting either figure.
7. **One transcription note.** The postmortem says 4,472,161 cache-write
   tokens; the ledger sums to 4,473,161 (with 320 fresh input tokens, total
   input 4,473,481). The 1,000-token difference changes nothing downstream but
   is recorded so the numbers trace.

### 0.3 The v2 economic baseline this delta optimizes

From `ledger.jsonl`, 161 calls, $85.64, 84 minutes:

| phase / rung | model | calls | input/call | input total | output | cost |
|---|---|---|---|---|---|---|
| p2 2a | sonnet | 19 | 37,551 | 713,480 | 382,018 | $10.39 |
| p5 determination | fable | 3 | 229,033 | 687,101 | 10,848 | $14.83 |
| p2 2c | fable | 24 | 25,843 | 620,241 | 204,887 | $23.04 |
| p2 2b | opus | 30 | 19,851 | 595,558 | 246,881 | $12.41 |
| p3 verify-edges | opus | 19 | 27,015 | 513,290 | 42,383 | $6.52 |
| p3 verify-identity | opus | 11 | 45,454 | 499,994 | 65,088 | $6.98 |
| work orders | sonnet | 19 | 20,716 | 393,610 | 139,298 | $4.68 |
| p3 spot-check | opus | 25 | 9,161 | 229,047 | 9,912 | $2.58 |
| p3 verify-findings | opus | 4 | 24,250 | 97,003 | 9,957 | $1.28 |
| p4 spine + narrative | fable | 2 | 43,139 | 86,277 | 9,234 | $2.24 |
| p3 substitution | opus | 4 | 5,870 | 23,481 | 435 | $0.25 |
| p1 orientation | fable | 1 | 14,399 | 14,399 | 2,816 | $0.44 |

Cache behavior, measured: sonnet calls read a constant 3,289 tokens (the CLI's
own cacheable base block) on 37 of 38 calls; **opus and fable calls read zero
across all 123 calls**. Total fresh input across the whole run: 320 tokens.
Everything else, 4.47M tokens, billed as 2x 1h cache writes that nothing ever
read back. Effective price per context token: 1.95x base for this run against
0.128x for the owner's 95.5h interactive session (5,962,610 writes,
393,018,389 reads, same formula), a **15.2x** ratio re-derived from both
ledgers. The postmortem's "roughly 20x" was the same comparison on a slightly
different basis; the order of magnitude is the finding.

### 0.4 The in-flight working tree

During this document's preparation the working tree accumulated uncommitted
edits by a concurrent implementer: `analyzer/enrich/compact.py` (new),
`prompts.py` (adds `_cached_prompt` / `split_cached_prompt` sentinel markers, a
compact component and relationship schema carrying the `l`/`need` self-report),
and `ladder.py` (target-kind split of 2a jobs, per-call output budgets). Two
consequences for this delta:

- The prompt-side halves of several revision 2 items (tier C schema, the
  `l`/`need` self-report, the prefix seam) are being implemented now. This
  document specifies the orchestration halves against that seam and flags every
  contract the two must agree on (section 3.6 and the final reconciliation).
- One integration defect to catch at commit time: the working-tree `ladder.py`
  passes `output_budget_chars=` to `RunContext.invoker`, which at
  `pipeline.py:697-723` does not accept it. The parameter must land in
  `pipeline.py` in the same commit or the ladder raises `TypeError` at runtime.

---

## 1. The caching verdict

The owner's directive: push hard on caching, several times, before concluding
anything negative, and rest every keep-or-drop on arithmetic from the v2
ledger. Done below. The one-line verdict first:

**Caching was under-priced by roughly 3x in the spec and dismissed on a
measurement that no longer holds. On the v2 ledger, the verified stable-prefix
mechanism recovers about $20 of $85.64 (23%) before any diet, and about $11 to
$13 of the smaller post-diet run. Keep it, land it first, and take the input
diets on top of it, not instead of it.**

Pricing used everywhere in this section: base input sonnet $3, opus $5, fable
$10 per MTok (ledger-fit, section 0.2 item 1); 1h cache write 2x base; cache
read 0.1x base; output sonnet $15, opus $25, fable $50. Savings therefore
accrue at 1.9x base per token moved from write to read.

### 1.1 Mechanism A: stable system prefix per rung. KEEP, land first.

Verified mechanism (probe doc findings 2 to 5): with
`--exclude-dynamic-system-prompt-sections` plus `--append-system-prompt-file`,
the system block (CLI base plus appended prefix) is byte-stable and every
non-warm call reads it at 0.1x, writing only a 762 to 778-token relocated
dynamic tail plus its own user message.

Three components of the saving, computed on v2:

**A1. Stop re-writing the CLI's own system prompt.** Today every opus and
fable call writes its full system prompt at 2x and reads nothing (123 calls,
zero reads); sonnet calls write about 5,860 dynamic tokens each and read only
the 3,289 base. Per non-warm call the saving is
`1.9 x system_size - 2 x 770` tokens at base price. Sonnet (measured
system 9,149, dynamic 5,860): $0.031/call x 37 calls = **$1.1**. Opus and
fable system sizes are not isolatable from the v2 ledger (bounded above by the
substitution rows' 5,868 full write including user message, so between about
3.3k and 5.8k); at that range: opus 92 non-warm calls **$2.2 to $4.1**, fable
29 calls **$1.4 to $2.6**. Probe P-A (section 1.6) pins the exact figures.

**A2. Move rung instructions, schema and brief into the appended file.**
Measured shared content: the 18 rebuilt 2a contract prompts share a
byte-identical 15,695-char prefix (instructions, schema, vocabularies, brief),
about 7.6k billed tokens by the proportional method (27% of mean prompt chars
against the ledger-derived 28.4k user tokens per call). Escalation prompts
share the assignment, contract schema and brief, about 5.5k billed (estimate,
same method). Verify-pass preambles are small (1,101 and 1,232 chars
measured). Savings at 1.9x base per non-warm call: 2a $0.78, work orders
$0.82 (same rung file, section 1.5), 2b $1.51, 2c $2.40, verify preambles
about $0.2. Subtotal **about $5.7** (plus or minus 30% on the two estimated
prefix sizes).

**A3. Put the determination's shared corpus in a per-run appended file.** The
three p5 calls ship a near-identical 220k-token body (census, adjudication,
synthesis, criteria, brief; only the forced-round block, rounds-so-far and
budget note differ). Today: $13.74 of input. With the corpus in a per-run
prefix file and the variable parts moved to the user tail: warm call writes
213k at 2x ($4.26) plus its 7k tail; calls 2 and 3 read 213k at 0.1x ($0.21
each) and write only tails. Total about $5.1, saving **$8.6**. Section 2.1's
digest makes most of this moot; A3 is the interim win that needs no digest and
no prompt redesign beyond moving three blocks to the tail (the forced-round
text currently sits at position 3 of the parts list, `determine.py:245-255`,
which would otherwise break the byte-stable prefix between call 1 and later
calls).

**Mechanism A total on v2: about $18 to $22, central $20,** of which $8.6
is superseded when the p5 digest lands (the digest's own saving is larger).
Post-diet steady state: A1 plus A2 persist at about **$11 to $13 per
run-equivalent**, and both scale with call count, not subject size.

Risk: low. The probe shows the model sees the cached prefix content (it
recited a rule from it) and answer shape survived the dynamic-section
relocation on schema calls; the prompt-shape tests must pin that on the real
rung prompts (probe doc, closing note). Implementation cost: one flag always
on, prefix-file plumbing in the invoker, byte-identical render rule, ledger
fields (section 5). Failure mode is graceful: a cache miss re-bills the prefix
at 2x, which is exactly today's baseline.

**Keep.** This is the single largest transport-level recovery available and
it carries no quality trade at all.

### 1.2 Mechanism B: session resume. KEEP, narrowly: p5 fallback only.

Verified (probe addendum). The arithmetic on v2 decides where it fits:

- **p5 determination**: shared 220k corpus, tiny per-call unique tail, calls
  inherently serial (rounds depend on each other). Resume saves about **$8.6**,
  the same as A3 within $0.2. Either works; A3 is preferred because it keeps
  calls stateless and needs no session bookkeeping. Resume is the designated
  fallback if probe P-B finds a size ceiling on appended files (a 213k-token
  prefix file is far beyond what the probe tested).
- **Verify passes**: per-call content is disjoint (each batch carries its own
  items), so a resumed session re-reads all prior turns at 0.1x for no
  benefit. On verify-edges: 19 turns of about 34k tokens each accumulate about
  615k read-tokens ($0.31 at opus read rates) to save only the 1,232-char
  preamble rewrite ($0.07). Net negative, plus full serialization of a phase
  that currently runs 4-wide. **Drop for verify passes**, with this arithmetic
  as the reason.
- **The ladder**: same disjointness, same verdict, worse: the full-cycle run's
  754-call drift disaster was a multi-turn phase. Resume's per-call one-shot
  bounds drift, but there is still no shared corpus to amortize. **Drop.**

### 1.3 Mechanism C: run-level cached corpus block, model-scoped. SPLIT verdict.

The owner asked specifically whether a run-level cached corpus could turn the
verification-plus-determination input share into 0.1x reads. Computed per
candidate corpus on v2:

- **All component fact blocks as a sonnet corpus prefix** (the 2a payloads,
  about 540k billed tokens): each fact is read by exactly ONE 2a call today,
  so the corpus write costs the same $3.24 the disjoint shipping costs, and
  then every one of 37 sonnet calls pays to read the whole corpus at 0.1x:
  37 x 540k x $0.3/M = $6.0 ADDED. **Drop for the bulk ladder, it is
  net-negative at this subject size** (and pushes every call to 550k context,
  a quality risk in itself). Caching pays only for content read by many calls.
  Revisit only if a future subject shows high cross-partition fact overlap,
  with this same arithmetic re-run on its ledger.
- **Endpoint summaries as an opus corpus for verify-edges**: measured
  repetition: the 19 rebuilt batches ship 916 endpoint-summary instances over
  only 133 distinct endpoints (6.9x repetition, mean 703 chars each). One
  cached block of all 133 (about 28k billed): write $0.28, 19 reads $0.27,
  replaces about 190k tokens of 2x writes ($1.90). Net **save about $1.35**.
  Keep as an option, but the per-call dedupe (section 2.4) captures most of it
  with no transport dependency; do that first.
- **The p5 corpus**: this is exactly A3 above, keep in that form.
- **Cross-phase reuse on one model**: the 2a rung file can serve the
  work-order calls (both sonnet, both build from the same instruction set once
  work orders route through the repair path, section 3.5). Measured phase
  gaps make this free: sonnet's last 2a call 20:55 UTC, first work-order call
  21:43, a 48-minute gap inside the 1h TTL; fable 2c ends 21:17, p4 21:40,
  p5 21:43; every same-model successor phase starts within the window and each
  read refreshes it. No scheduler change needed; the predicate in section 5
  guards it.

### 1.4 TTL scheduling. KEEP the current order, add the predicate.

All v2 writes are `ephemeral_1h` (probe finding 6; the CLI chooses 1h on every
first turn). Measured phase spans: no rung phase exceeds 12 minutes wall; the
longest same-model gap is 48 minutes (above). Low-effort call durations (2a
mean 144s, max 351s; everything else under 90s mean) keep even a 4-wide
pool's warm-to-last-read distance far inside the window. `warm_first`
(`pipeline.py:552-554`, `ladder.py:555`) finally becomes meaningful with
mechanism A: the first call of a rung writes the prefix entry, the following
N-1 read it. Ordering rules adopted from revision 2 section 8 stand unchanged
(importance order, group-adjacent dispatch); nothing further is needed at this
subject size.

### 1.5 Per-phase mechanism assignment, digest versus cache made explicit

The rule that falls out of the arithmetic: **cache what many calls read,
digest what no call needs in full, and when both apply, digest first and cache
the digest.** Per phase on the v2 ledger:

| phase | cache saving alone | diet saving alone | assignment |
|---|---|---|---|
| p5 determination | $8.6 (A3 corpus-in-prefix or resume) | $12.1 (digest, section 2.1) | digest first, digest rides the p5 prefix file; A3 is the interim, resume the size-ceiling fallback |
| p2 2a | $0.8 prefix + share of A1 | output-side compact schema (Prompt persona, in flight) | both; prefix file per rung |
| p2 2b / 2c | $3.9 prefix + share of A1 | routing shrinks the population itself (section 3) | both; routing changes the call count, prefix cheapens what remains |
| verify-identity | preamble only, negligible | $4.0 already landed at HEAD (payload trim, 55.5k to about 10k per call) + evidence fix (section 2.3) | diet; no caching worth building |
| verify-edges | $1.35 (endpoint corpus) | about $1.0 to $1.5 (per-call dedupe) | diet first; corpus block optional second |
| spot-check / substitution / findings | negligible (small, digest-fed already) | none needed | leave alone |
| work orders | shares 2a prefix ($0.8) | reroute through repair path (section 3.5) | both |
| p1 / p4 | single calls, nothing shared | none | leave alone |

### 1.6 Remaining probes (specified for the coordinator; I will not run them)

The F-9 probe closed the load-bearing question on sonnet. Two gaps remain
before the section 5 predicates can be pinned per model:

**P-A: base block and append behavior on opus and fable.** The v2 ledger's
123 zero-read calls prove the DEFAULT system prompt never caches on these
models; it does not prove the exclude+append combination behaves as it does on
sonnet (candidate explanations differ: no breakpoint versus a larger
minimum-cacheable threshold, and the fix behaves differently under each).
Calls, per model in {opus, fable}: (1) two identical plain calls, no extra
flags, user message "Reply with exactly: ok"; (2) three calls with
`--exclude-dynamic-system-prompt-sections --append-system-prompt-file
<the probe's existing f9-prefix.txt>`, same user message. Expected PASS
signature, mirroring the sonnet C-series: call 2 of the flagged set shows
`cache_read >= (call 1 cache_write - 800)` and `cache_write <= 900`; the plain
pair pins the per-model base and dynamic sizes from write deltas. Expected
FAIL signature: flagged call 2 reads 0 or only a small base block. Cost bound:
10 calls, under $1.50 (fable dominates). Everything in section 1.1's A1 range
collapses to a point once this runs; no keep-or-drop verdict changes either
way, only the predicate constants.

**P-B: appended-file size ceiling.** A3 and the digest-in-prefix design put
15k to 213k tokens in the appended file; the probe tested 6.4k. Calls: the
C-series shape on fable with generated rule-text files of about 30k and about
200k tokens (2 calls each). PASS: same read-back signature at both sizes.
FAIL at the large size only: A3 falls back to resume (mechanism B), digests
unaffected. Cost bound: 4 calls, under $10 (the 200k fable write is $4 twice).

### 1.7 The archaeology: where caching was argued away, and whether it holds

Searched: the git history, the rearchitecture reviews register, and the
assessment documents. The record:

1. **The specs never dismissed caching.** ORCHESTRATION-SPEC revision 2
   section 8 and PROMPT-SPEC section 10 designed the mechanism this delta now
   lands, priced it at about $7 per run, and gated it on F-9. QA-FINAL-VERDICT
   named the F-9 gate inside P-1 and priced the failure exposure at about $5.
   None of that was a dismissal; it was a design nobody implemented.
2. **The dismissal happened in the repair effort's triage.**
   `docs/quality/ENHANCEMENT-ASSESSMENT-2026-08-26.md` item 6 records it:
   "Cache write/read imbalance. 126,126 tokens written, 9,867 read, a 0.08
   ratio, roughly a 12% premium on input for a few cents of saving." Cache
   reuse was then ranked 5th of 7 in the postmortem's what-is-left list, and
   the implementation pass shipped everything transport-level EXCEPT the
   prefix plumbing and the named probe.
3. **That reasoning does not hold against the v2 numbers, in three ways.**
   (a) Scale: "a few cents" was computed on a 126k-written small run; the v2
   full build wrote 4.47M tokens, and the same ratio prices the same defect at
   about $20 of $85.64. (b) Framing: the 0.08 read ratio was treated as small
   stakes when it was actually the diagnostic of a broken mechanism; nothing
   COULD be read because no stable prefix existed, which is the F-9 failure
   mode the probe has now demonstrated and fixed. (c) Scope: the "12% premium"
   priced only the 2x-versus-1x write class on the run's own shape. It did not
   price the opus and fable system-prompt rewrite (invisible until the v2
   ledger's zero-read columns were split out), the p5 corpus re-shipping, or
   resume. The owner's suspicion is confirmed by arithmetic: caching was
   dismissed on the strength of a flawed status quo (a small run, on a
   transport where caching could not work), not on a measured verdict about
   the mechanism, and the measured verdict, now in, is favorable.

---

## 2. Meta-phase input diet

Method for every diet below: what the phase's prompt ships today (measured
from the v2 ledger and prompts rebuilt from HEAD code against the real store),
against what the phase's OUTPUT is observed to use (read from `report.json`,
`REPORT.md`, and the work orders it issued). The diet keeps everything the
output demonstrably consumed and cuts what nothing consumed.

### 2.1 Determination (p5): 229,033 to about 27,000 input tokens per call

**What it ships** (rebuilt byte-for-byte from `determine.py:227-287` against
the run artifacts; chars, with billed-token shares scaled to the measured
220k-token user message): census 332,882 chars (58%), adjudication 196,852
(34%), synthesis 23,882 (4%), brief 9,480, criteria 6,446, contract 1,568.
Inside the census: the 524 grounded items with empty `failed` lists account
for 197,192 chars (59% of census), the 102 gap and escalate items for 116,774.
Inside the adjudication dict: per-edge outcome rows 67,614 chars, 158 full
spot-check rows 55,046, identity outcomes 18,068, findings 10,165, plus
plan_preview and accounting fields no judge needs.

**What the output uses** (all three calls' outputs examined):

- The verdict reasoning cites aggregates: "grounded items fell from 524 to
  498 to 491", "347 of 457 edges independently confirmed, only 10 refuted",
  "the adjudicator's 53% spot-check disagreement rate concentrates on the
  band-1 spine", and the parser_first record.
- The criteria verdicts cite tours by name, work-order outcomes, confirmed
  edges, and named components ("Core/Audio", "Services/Protocols"); never a
  grounded item's per-item detail.
- The 7 work orders' `scope` lists name exactly the disputed and failed
  items: components from the unsupported spot-checks, the gap items'
  questions, specific edge groups. Every id in every scope traces to a failed,
  disputed, or refuted record, none to a merely grounded one.

**The digest, derived from that:** per call,

- census digest: `by_state` and trigger tallies; the 102 gap items and any
  escalate items IN FULL (id, questions, triggers, notes); the parser_first
  tally (top classes with counts plus exemplars); grounded items as counts
  per rung only. About 15k chars.
- adjudication digest: per-pass tallies and rates; the refuted and uncertain
  edge id lists; the 84 unsupported spot-check rows trimmed to target,
  question, claim head, reason; substitution rows in full (4); identity
  summary per field. About 12k chars.
- synthesis: SHIPPED IN FULL (23,882 chars). The criteria verdicts quote the
  tours by name and content; cutting them would cut evidence the output
  demonstrably uses.
- criteria, brief, contract, rounds-so-far, budget note: unchanged.

Total about 70k chars, about 27k billed tokens per call. Input side falls
from $13.74 to about $1.62, **saving $12.1 per run**, and the digest itself
rides the p5 prefix file (section 1.5) so rounds 2 and 3 read it at 0.1x.
Where the digests live: `census_digest()` beside `Census` in `contract.py`,
`adjudication_digest()` beside the existing spot-check `build_digest`
(`adjudicate.py:216`). Explicitly NOT in `digest.py`: that module
(`digest.py:1-280`) is the frozen provenance-hash vocabulary (blake2b content
digests, invariant I4/I5), and overloading the name with prompt summaries
would be a second meaning for a frozen term. This is the reconciliation the
commission asked for: the existing digest.py is untouched and the meta-phase
summaries take a different name in different modules.

Quality trade and its measurement: section 6 row 1. The structural risk
(digest drops something a judge needed) is bounded by an ablation: one
determination call on the v2 artifacts with the digest, diffed against the
recorded v2 verdict on the criteria table; disagreement beyond the criteria
the record already shows unstable fails the gate.

### 2.2 Work orders: full contract partitions to scoped repairs

Today (`workorder.py:266-296`): an order re-partitions its scope and re-ships
FULL contract partition prompts, 19 calls at 20,716 in and 7,331 out per call,
$4.68, and the v2 record shows the two rounds made the census WORSE (grounded
524 to 491, 47 items demoted to escalate) while "changed no contract state"
appears verbatim in outcome notes. The determination itself diagnosed the
failure classes: unparseable partitions, module-name citations, fact-name
mismatches, and issued a "one component per partition" order in round 2.

Delta: an order executes through the SAME repair path as context-class
escalations (section 3): compact escalation prompt, the order's lens as the
assignment, only the named questions answered, evidence attached by rung 0,
batch bounded by bytes, one component per call for band-1 targets (adopting
the determination's own lesson as the default for critical items). Expected
shape per call: about 8k in, about 2k out. On the v2 population: $4.68 to
about $1.6. The larger effect is quality: repairs merge as deltas, so a
failed repair can no longer demote a previously grounded answer, which is the
mechanism behind the 524-to-491 regression (full re-emission overwrote good
blocks with worse ones under merge).

### 2.3 Verify-identity: the 98-of-99-uncertain result, diagnosed and fixed

**Diagnosis, from the store's verdict rows** (`identity-verdict` enrichment
rows, tallied): overall 98 uncertain, 1 confirmed, 0 corrected. Per field:
`port` confirmed 99/99, `name` uncertain 34, `type` uncertain 50, `framework`
**uncertain 97 of 99**. The overall verdict is "uncertain if ANY field is
uncertain" (`passes.py:980-989`), so framework alone forces the number. And
the model says exactly why, in its reasons (verbatim, with counts): "No
import or symbol evidence in the supplied facts confirms the UI framework"
(11), "No imports, symbols, or patterns in the facts to confirm the UI
framework" (11), "Only a .swift path is recorded; no framework evidence in the
facts" (7), and so on. Every top reason is the same sentence: the prompt
ships no framework evidence.

**The evidence exists and is store-resident.** The store holds 101 `framework`
signal rows (kind='framework', value `{"name":"SwiftUI"}`, file path attached;
verified by direct query), plus 10,084 `symbol_reference` rows that carry
import evidence. `_identity_facts` (`passes.py:820-838`) ships none of it:
file_sample is paths only, `patterns` comes from docs and is empty here.

**The fix is input, not demotion.** Attach to each identity item: the
component's framework signal rows (name, path, line where present) and an
import census over its files (which framework modules its files reference,
with one file-and-line exemplar each). Cost: about 300 chars per component,
under 1k billed per batch. The pass keeps its current judge and thresholds;
nothing about the model changes, only the evidence it named as missing.
Post-fix expectation, flagged not asserted: framework uncertains collapse to
the components genuinely lacking signals; measured by re-running the pass and
re-tallying (section 6 row 3). Demotion or removal is NOT the case to make:
the pass's design (verify published identity or flag it) is the owner's 
standing ruling, its output is cheap (65k tokens), and its one measured 
failure is an input starvation this fix addresses. What IS demoted: the 
input bill. The HEAD payload trim (section 0.1, landed after v2 started) 
already cuts the pass from 55.5k per successful call to about 10k rebuilt; 
with evidence attached it stays near 11k, and the pass total falls from 
$6.98 (including its two million-token "Prompt is too long" failures, both 
also cured by the landed byte-bounding) to about $1.1.

Aggregation refinement, one line: the overall verdict should treat a
`port: uncertain` on a component that claims no port as confirmed-absent
rather than uncertain, so the roll-up measures real doubt. On v2 data port
never fired (99 confirmed), so this is hygiene, not savings.

### 2.4 Verify-edges: stop re-shipping the same endpoints

Measured (batches rebuilt from HEAD code against the store): 19 batches ship
916 endpoint-summary instances covering 133 distinct endpoints, 6.9x
repetition, mean 703 chars per instance; endpoint summaries are about 57% of
the pass's shipped content. Diet: within each call, ship each distinct
endpoint once in an `endpoints` map and reference it from edges by id
(builder change, Prompt persona owns the wording); expected input reduction
about 35 to 45% of the pass ($6.52 toward about $4.2, estimate by the
within-call repetition share of the rebuilt batches). The cross-call residue
is mechanism C's endpoint corpus ($1.35 further, optional, section 1.3).
Verdict rows already come back per edge id, so nothing downstream changes.

### 2.5 What this section adds up to

| phase | v2 input/call | after delta | run saving (input side) |
|---|---|---|---|
| p5 determination | 229,033 | about 27,000 | $12.1 |
| verify-identity | 45,454 (untrimmed) | about 11,000 | $5.9 (of which about $4 already landed at HEAD) |
| verify-edges | 27,015 | about 16,000 | $2.3 (incl. corpus option) |
| work orders | 20,716 | about 8,000 | $3.1 (plus output side) |

Meta-phase input drops from 26% of run input to under 8%, and the
"system inspecting itself" share of the bill falls with it.

---

## 3. Escalation routing by trigger class

### 3.1 The measured case

The trigger vocabulary is E1 to E5 (`contract.py:76-80`); the class map the
run itself publishes (`runreport.py:176`): E2, E3, E4 are `context` (the tier
had facts and could not ground, cite or reconcile them), E1 and E5 are
`reasoning`. From the v2 artifacts:

- 168 distinct items climbed or gapped; 267 climb events (147 into 2b, 120
  into 2c, ledger `targets`).
- Terminal failed questions by trigger: E2 91, E1 54, E5 41, E4 2 (REPORT.md
  economics table, re-derived from `report.json`). By item at terminal state:
  pure context 60, pure reasoning 42, mixed 23, and 43 items grounded en route
  (their trigger sets clear on resolution, so class-at-entry is not recoverable
  post-hoc; section 3.4 fixes that logging gap).
- Resolution: 2b terminal-grounded 27 of 147 received (18.4%); 2c grounded 18
  of 120; 102 honest gaps. Escalation above 2a consumed $35.45 and 1,667,567
  tokens (REPORT.md economics), and the escalation rungs generated 1,700
  output tokens per climb against 600 per target at 2a.
- Mechanically-caused failures inside E2, counted from the terminal notes:
  30 module-or-keyword-cited-as-symbol, 13 self-declared-uncertain scored as
  E2, 8 `line_count`-versus-`lines` fact-name mismatches, 2 outside-analyzed-
  set. At least 40 of 188 terminal failed questions (21%) are failures no
  model at any price can fix, because the defect is in the citation vocabulary
  or the fact naming.

Escalating a context failure buys a more capable model the same missing
facts. The v2 record prices that category error at up to $35.45 of climbing
for a 23% blended resolution rate.

### 3.2 The deterministic routing rule

At the 2a-to-2b seam (`ladder.py:655-677`, where `pending` is currently every
`escalate` state):

```
class_of(state):
    triggers = {f.trigger for f in state.failed}
    if triggers <= {"E2", "E3", "E4"}:            -> "context"
    elif not triggers & {"E2", "E3", "E4"}:       -> "reasoning"
    else:                                          -> "mixed"

route(state):
    rung 0 first, always: re-validate citations under the current
      vocabulary (referenced-at, fact-name aliases, component-id kind);
      a state whose failures all clear here re-enters grounded with no
      model call.
    "context"  and not state.repair_attempted -> same-tier repair batch
      (invoker key p2a_bulk, rung label "2a-repair"), evidence attached
      per 3.3, batch 5, byte-bounded. Set repair_attempted.
    "context"  and state.repair_attempted     -> climb (the repair had its
      one chance; loop forbidden).
    "reasoning" or "mixed"                     -> climb to 2b unchanged.
```

The rule is total, deterministic, and evaluable from the contract state alone.
`mixed` climbs because its reasoning-class questions need the climb anyway and
splitting one item across two calls would give it two writers per rung, which
absorption commutativity forbids (revision 2 section 7, unchanged). The
one-repair bound plus the existing no-loop terminal design keeps the ladder
finite. The `l`/`need` self-report (in the working-tree compact schema)
refines but never overrides this: a `need` the coordinator can resolve against
the store strengthens the context routing; an unresolvable `need`
reclassifies to judgment and climbs, exactly the revision 2 section 4.2
constraints, now with the field actually being emitted.

### 3.3 What evidence gets attached (mine), and what the repair prompt says (not mine)

Attachment, built by rung 0 per failed question, budget 1,200 billed tokens
per item:

- the failing citation plus the validator's verdict string, verbatim;
- for E2 symbol failures: the referenced-at rows for that symbol (path, line)
  and, when the cited name is a component or module, the component-id citation
  form the vocabulary supports;
- for fact-name failures: the correct fact key with its value (the
  `line_count` class);
- for E4: the sibling components' one-liners the answer collided with;
- the item's full evidence menus, re-rendered under the current vocabulary.

Flagged assumptions about the repair prompt, for the Prompt and Context
Engineer to confirm or correct (their side of the boundary):

1. The repair prompt is the compact escalation prompt restricted to the named
   questions, with the attachment block above; I assume about 2.5k to 3.5k
   billed input per component item and about 800 per relationship item.
2. The repair response is deltas only (answers for the named questions plus
   an optional corrections list), about 300 to 500 output tokens per item;
   merge semantics unchanged (`ladder.py:129-165`).
3. `l`/`need` remains schema-bound to uncertain answers and the repair prompt
   instructs re-declaration, not re-answering, when evidence still does not
   suffice.
4. The attachment renders inside the item, after facts, so the rung prefix
   stays byte-stable.

### 3.4 Populations, expected savings, and the honest uncertainty

Class-at-entry was not recorded in v2 (resolved items clear their triggers),
so the context share of 2b receipts is bounded, not known: between 48%
(60 of 125 unresolved) and 66% (83 of 125 counting mixed). At a 55% central:

- 2b receives about 66 instead of 147; opus ladder cost $12.41 to about $5.6
  (proportional per item, stated as such).
- About 81 items take a sonnet repair call instead: 17 calls at about $0.17
  each (19k in at $6/M write-equivalent, 2.5k out at $15/M), about $2.9.
- 2c receipts fall by whatever the repair resolves. At a 35% repair
  resolution rate (HYPOTHESIS, the single number this design most needs
  measured), 2c receives about 92 instead of 120; fable ladder cost $23.04 to
  about $17.7.
- Net ladder saving about $9 central, range $5 to $13, plus the output side
  (escalation output shrinks with its population) and plus the bucket effect
  the run report already states: sonnet and opus draw from separate weekly
  allowances, so an opus call avoided is worth more than its price.

Measurement M-R1 before adoption: replay the v2 context-class population
(reconstructable from the census: the 60 pure-context items plus the E2-heavy
mixed ones) through the repair path on the real store, 12 to 17 calls, bound
$4. It yields the repair resolution rate, the real repair-call shape, and the
class-at-entry log. The routing lands behind it per the no-regression
protocol. Logging fix that makes the next run self-measuring: record
`entry_triggers` and `entry_class` on the contract state at the moment it
first enters `escalate` (`ladder.py:660`, persisted in the contract row by
`_stamp`, `ladder.py:954`), and surface both in `_escalations`
(`runreport.py:346-372`).

### 3.5 Coordination with the in-flight compact work

The working tree's compact escalation prompt and `l`/`need` fields are the
prompt half of this design. The routing decision, the batch composition, the
attachment content, the one-repair bound, and the ledger accounting are the
orchestration half and live where section 5's file notes put them. The two
halves meet at exactly the four flagged assumptions in 3.3 plus the prefix
seam (`split_cached_prompt`), and nowhere else.

---

## 4. Deterministic validation

Executable predicates over `ledger.jsonl`, `report.json` and the store. A
harness evaluates each and answers pass or fail with no judgment call. V-P1
to V-P3 are assertable on the v2 ledger today; the rest activate with the
deltas they validate. Constants marked P-A resolve when that probe runs.

| id | predicate | pinned numbers, tolerance |
|---|---|---|
| V-P1 effort | every row: `effort == "low"` | zero exceptions (v2: 161/161) |
| V-P2 turns | every ok row: `num_turns == 1` and `stop_reason == "end_turn"` | zero exceptions (v2: pass) |
| V-P3 price fit | per model: ledger cost within modeled cost at {sonnet 3/15, opus 5/25, fable 10/50}, writes 2x, reads 0.1x | ratio in [0.98, 1.06] (v2: 1.025 to 1.040) |
| V-P4 warm call | first call per rung per model: `tokens_cache_write >= prefix_tokens(rung)` and `tokens_cached <= base_block(model) + 200` | base_block: sonnet 3,289 measured; opus, fable from P-A |
| V-P5 non-warm read floor | every later same-rung call: `tokens_cached >= base_block(model) + prefix_tokens(rung) - 2%` | prefix_tokens recorded at render time beside `prefix_hash`; miss rate <= 10% of non-warm calls per rung (v2 sonnet organic miss rate 1/37) |
| V-P6 non-warm write ceiling | every later same-rung call: `tokens_cache_write <= 900 + user_payload_estimate(call)` | 900 = probe's 762-778 relocated-dynamic floor plus margin |
| V-P7 prefix stability | all rows of one rung in one run share one `prefix_hash` | zero drift |
| V-P8 input per call by phase | `tokens_in` ceilings: p5 35,000; verify-identity 15,000; verify-edges 30,000; 2b 25,000; 2c 30,000; repair 22,000; work-order-as-repair 12,000 | hard fail above ceiling; ceilings re-pinned only by a committed measurement doc |
| V-P9 no oversize requests | zero rows with error matching "Prompt is too long" | v2 had 2; byte-bounding landed, predicate keeps it dead |
| V-P10 routing conservation | every 2b row's items carry entry_class in {reasoning, mixed}; every repair row's items carry entry_class context; per item, repair rows <= 1; census conservation: every 2a target ends in exactly one terminal state | zero exceptions |
| V-P11 escalation rates | items entering 2b <= 45% of 2a targets; repair population <= 25% | v2 baselines 23.5% and n/a; re-pin after M-R1 |
| V-P12 TTL adjacency | for each model, gap between consecutive calls that share a prefix < 55 minutes | v2 max observed 48 |
| V-P13 identity evidence | every identity item whose component has >= 1 framework signal row in the store carries it in the prompt payload | deterministic input check; the outcome metric lives in section 6, not here |

Relation to the QA-FINAL-VERDICT section 5 table, row by row: P-1's F-9
cache-read gate is SUPERSEDED (closed by the probe doc, passed with the
exclude flag; the tier C A/B halves of P-1 remain open). P-3's Opus price
arbitration is SUPERSEDED (closed by V-P3 on the v2 ledger; its batch-parity
half remains open). R-2 (cache predicate thresholds) is SUPERSEDED by V-P4 to
V-P7 plus probe P-A. R-3 (price fit) is SUPERSEDED, closed. R-5 (M-7, P3 to
P5 cost) is SUPERSEDED, closed by measurement: $39.36 on the v2 subject.
P-2 is PARTIALLY INFORMED: dispersion at low measured 1.71 max-to-mean on 19
contract-schema calls; the tier C measurement it exists for remains open, and
G2's 1.90 stands until it runs. H-1, H-2, P-4, P-5, P-6, P-7, R-1, R-4 are
unchanged by this delta.

---

## 5. File-by-file implementation notes

Against `a98479b`. Ordered so each step lands and validates alone; every step
names its gate. Steps 1 to 3 are transport and accounting with zero prompt
changes and zero quality exposure; they go first per the owner's directive.

**Step 1. engine.py: flags and prefix plumbing.** Add
`--exclude-dynamic-system-prompt-sections` unconditionally to the argv
(`engine.py:209-215`; same comment discipline as the effort pin: an unstated
prefix stability is a decision nobody made). Teach `ClaudeCliInvoker`
(`engine.py:171-183`) to split its incoming prompt with the working tree's
`split_cached_prompt` seam: when a prefix is present, write it once to
`<run_dir>/prefixes/<sha256>.txt` (byte-identical render, sorted keys, no
timestamps, never edited mid-run) and pass `--append-system-prompt-file`; the
user tail goes to stdin. Record the sha and the prefix token estimate on the
result for the ledger. Optional `resume_session_id` parameter mapping to
`--resume` (used only by the p5 fallback; nothing else may pass it). Gate:
probe P-A signatures reproduced by two unit-level live calls per model inside
the probe budget, plus the existing argv tests extended.

**Step 2. pipeline.py: ledger truth.** `LedgerRow` (`pipeline.py:284-341`)
gains `prefix_hash`, `prefix_tokens_est`, and, if the envelope's usage block
carries the `cache_creation` TTL split, `tokens_cache_write_1h` / `_5m`
(capture verified in the probe; all-1h expected). `_usage_tokens`
(`pipeline.py:344-377`) reads the split. `RunContext.invoker`
(`pipeline.py:697-723`) accepts and forwards the prefix identity, and MUST in
the same commit accept `output_budget_chars`, which the working-tree ladder
already passes (section 0.4's TypeError). Gate: V-P4 to V-P7 evaluated
against a smoke run's ledger by `scripts/enrichment-audit.py`.

**Step 3. determine.py interim: corpus to the tail-stable shape.** Reorder
`build_determination_prompt` (`determine.py:238-287`) so the variable blocks
(forced-round text, rounds-so-far, budget note) render AFTER the stable corpus,
and emit the stable corpus as the call's prefix through the seam. This is
mechanism A3: $8.6 on v2 shape, no content change at all. Gate: byte-diff of
rendered parts against the v2 reconstruction, plus V-P5 on the next run's p5
rows.

**Step 4. contract.py and adjudicate.py: the meta digests.**
`census_digest()` beside `Census`; `adjudication_digest()` beside
`build_digest` (`adjudicate.py:216`); `determine.py:410-419` consumes them;
`digest.py` untouched (section 2.1's naming reconciliation). REPORT.md keeps
rendering from the FULL census as today (`runreport.py:324-345`); only the
prompt goes on the diet. Gate: the section 2.1 ablation, then V-P8's p5
ceiling.

**Step 5. passes.py: identity evidence and edge dedupe.** `_identity_facts`
(`passes.py:820-838`) gains `framework_signals` (store `signals` rows,
kind='framework', joined through `component_files`) and an import census from
`symbol_reference` rows; `verify_edges` (`passes.py:349-358`) ships a
per-call `endpoints` map once and references it from edges (builder wording
with the Prompt persona). Gate: V-P13, V-P8 ceilings, and the section 6
row 3 outcome re-measurement.

**Step 6. ladder.py: the router.** At `ladder.py:655-677`: rung 0
re-validation sweep, `class_of`, the split into repair jobs (invoker key
`p2a_bulk`, rung label `2a-repair`, batch 5, byte-bounded) and climb batches;
`_escalation_item` (`ladder.py:794`) gains the attachment block;
`repair_attempted`, `entry_triggers`, `entry_class` persisted through `_stamp`
(`ladder.py:954`) and surfaced by `runreport.py:346-372`; the economics class
map moves to `contract.py` as the single vocabulary and `runreport.py:176`
imports it. Gate: M-R1 (section 3.4) passes first; then V-P10, V-P11.

**Step 7. workorder.py: orders become repairs.** `execute_work_order`
(`workorder.py:266-315`) stops building full contract partitions
(`workorder.py:293`) for re-grounding orders and routes scope through step
6's repair machinery with the order's lens as assignment; one component per
call for critical-band targets. Gate: replay the v2 round-1 orders on the
real store, assert no previously grounded state demotes (the 524-to-491
regression class), bound $3.

Steps 1 to 3 are a week-one landing with no gauntlet. Steps 4 to 7 each ride
the no-regression protocol: isolate, validate on real work, roll back on
regression.

---

## 6. Quality trades register

Quality is the constraint; every diet or routing change lands with the
measurement that would catch its regression.

| # | change | expected quality effect | regression detector |
|---|---|---|---|
| 1 | p5 digest (2.1) | none intended; judge sees everything its outputs ever used. Risk: a needed grounded-item detail vanishes | ablation against the recorded v2 determination (2.1); criteria-verdict diff; work-order scopes must still resolve to real target ids |
| 2 | prefix caching (1.1) | none; identical content, different billing class. Risk: dynamic-section relocation changes answer shape | prompt-shape tests on real rung prompts (probe doc closing note); V-P2 stays clean |
| 3 | identity evidence fix (2.3) | positive expected: the pass can decide. Risk: none identified; input grows slightly | re-run tally: framework uncertain rate, currently 97/99; success means it falls to the signal-less residue; V-P13 guards the input side |
| 4 | edge endpoint dedupe (2.4) | none; same facts, referenced once | verdict distribution on a replay batch within 2 points of v2's (confirmed 347, refuted 10, uncertain 100) |
| 5 | trigger-class routing (3) | positive expected: context items get facts, which is what their failure said they lacked. Risk: repair rate lower than hypothesized, items reach 2b one round later | M-R1 before landing; census grounded fraction and honest-gap explanation rate (u3) not below the v2 baseline (83.7%, 9 unexplained gaps); V-P11 |
| 6 | work orders as repairs (7) | positive expected: ends the measured regression class (grounded 524 to 491 across two rounds) | step 7's replay gate; per-round measured_delta must never show net state demotion |
| 7 | resume fallback for p5 | none; serial phase already | session_id continuity in ledger; V-P2 per resumed call |

The standing quality issues this delta does NOT claim to move, so nobody
reads motion into them: the 53.2% adjudication disagreement rate (the
adjudicator vocabulary fix landed at `f766208` after the v2 build and is
unmeasured), and the adjudicator's vagueness-rewarding scoring, which is the
Prompt and QA personas' shared open item.

---

## 7. Register of deltas versus revision 2, with the evidence that changed each

1. **Opus price: dual carried, now $5/$25.** Evidence: 93 v2 ledger rows,
   fit ratio 1.037 versus 0.346 (section 0.2). Revision 2's Level 2
   sign-off condition is satisfied on record.
2. **F-9: named assumption, now measured mechanism with a required second
   flag.** Evidence: the probe doc. Revision 2 section 8's predicates are
   replaced by V-P4 to V-P7 with measured constants (sonnet base 3,289,
   dynamic floor 900, not the modeled 12,546 overhead, which conflated base
   and dynamic content this environment renders differently).
3. **Caching value: about $7 per run, now about $20 pre-diet, $11 to $13
   post-diet.** Evidence: sections 1.1 to 1.5 arithmetic on the v2 ledger.
   The spec priced only the rung prefixes; the opus and fable zero-read
   columns and the p5 corpus were not visible until this ledger split them
   out.
4. **Session resume: revision 2 did not price it; now verified, adopted
   narrowly (p5 fallback), and rejected with arithmetic everywhere else.**
   Evidence: probe addendum plus section 1.2's verify-edges negative case.
5. **warm_first: correctly kept in revision 2, but useless as shipped**
   (user-message prefixes never hit). Evidence: v2's 121,693 read tokens all
   attributable to the CLI base block. It becomes real with step 1.
6. **Meta-phase costs: $10 to $20 estimate replaced by $39.36 measured**, and
   the digest designs are now derived from observed output usage rather than
   from prompt-side reasoning (section 2.1). M-7 closed.
7. **Escalation protocol: the handoff format stands; the ROUTING changes.**
   Revision 2 section 4.2 defined `fact-not-in-prompt` routing through rung-0
   augmentation; v2 measured the population (context-class about half of
   climbers, 18.4% 2b resolution, 21% of terminal failures mechanical) and
   this delta promotes that route from a vocabulary entry to the default path
   for the entire context class, with the one-repair bound and M-R1 as gate.
8. **2c bound: unchanged in design, cheaper in expectation.** Routing shrinks
   its intake; the budget-slice and terminal-honesty rules of revision 2
   section 6 are untouched.
9. **Batch sizing: unchanged.** Cap 21 and the G2 rule stand; dispersion at
   low has a first measurement (1.71, n=19, contract schema) that supports
   but does not yet trigger the relaxation condition.
10. **Ledger telemetry: revision 2's field list lands minus two, plus two.**
    `tokens_cache_write` and `tokens_fresh_in` landed during the repair
    effort; `prefix_hash` and the TTL split land in step 2; `entry_class` and
    `repair_attempted` are new, born from the v2 population-logging gap
    (section 3.4).
11. **The identity verify pass: absent from revision 2's scope, now in it**,
    because the 98-of-99 number turned out to be an input-starvation defect
    with a store-resident fix, not a model or design failure (section 2.3).
12. **Work orders: revision 2 treated descent as out of ladder scope; the v2
    record (two rounds, negative measured delta, $4.68) pulls it in**, as a
    consumer of the same repair machinery (section 2.2, step 7).
