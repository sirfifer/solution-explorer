# Orchestration Spec: the rearchitected enrichment ladder

Author: Agent Orchestration Architect persona. Date: 2026-08-25.
Status: revision 2, post-adjudication. Revision 1 was reviewed adversarially
by the Prompt and Context Engineer (`reviews/PROMPT-ENGINEER-ON-ORCHESTRATION-SPEC.md`)
and by the QA and Validation Engineer (`reviews/QA-TESTABILITY-PASS.md`); the
QA adjudication (`data/qa-adjudication.json`) is binding on this revision.
Section 14 is the changelog; section 13 records the review findings not
adopted, with reasons.

Factual foundation: the two 2026-08-25 postmortems as baseline; the
reconciled corpus (`data/replay-corpus.json`: 32 partition calls, 4
killed-in-flight, 1 orientation, 1 operator session); the 16 replay probe
transcripts; the real VS Code store; current code on branch
`deterministic-gate-hardening`; and the adjudicated constants. Zero model
calls were made for this revision. Reproduce every dollar figure with
`data/cost-model.py`.

## 0. The owner's question, answered first

The killed run projected $1,000+ as configured. The same work, at equal or
better quality, on the design below, regenerated from the adjudicated
constants:

**Rungs 2a+2b+2c: $61 to $97 with Opus at $5/$25, central about $69.** With
orientation, adjudication, synthesis and determination on top (P1 measured
$0.75; P3 to P5 estimated $10 to $20, M-7), **a full run lands at roughly
$72 to $118, central about $83.**

This matches the QA convergence (ladder $55 to $95, central about $65; full
run about $70 to $115, central about $80) within $4 at the central, and the
residual is named: this spec prices 2a inputs at the Prompt Engineer's
directly measured volumes (relationship facts 235 not the chars-rescaled
201, per-call relationship context 4,700 not 800, edge menus and the CLI
overhead priced), worth about +$5, and prices 2c with the Prompt Engineer's
per-kind decomposition rather than the rescaled flat constants, worth about
-$4 at 2c. Same constants, slightly different measurement choices, each one
cited at the line it enters the model.

**The Opus price is the explicitly open variable and is carried dual.** No
Opus ledger row exists in any recorded artifact. At the current-sheet claim
of $5/$25 the ladder is $61 to $97; at the legacy $15/$75 it is $101 to
$147. The first pilot Opus ledger row (an M-2 row) arbitrates, and Level 2
sign-off requires that arbitration on record, per the validation plan. No
conclusion in this spec depends on which price is real except the 2b batch
economics (section 3.3), and that contingency is stated where it applies.

What drives the width at $5/$25, largest first (re-ranked per adjudication):

1. **The Opus price itself** (about $25 to $50 if it resolves to $15/$75):
   resolved by the first pilot Opus row, not by any offline argument.
2. **Tier C schema landing** (about $21 swing): tier B 2a is $57.5, tier C
   $36.8. The Prompt Engineer's measured transform targets (880/124) are the
   central; M-P1/M-4 gate them.
3. **The 2c entry fraction** (about $10 swing at the new decomposition): 10%
   costs $4.9, 30% costs $14.4. Section 6 bounds the worst case at $46.7 so
   this is a range, never a runaway.
4. **The adjudicated fixed-output bounds** (about $20 swing): the per-call
   fixed term is 1,369 with bounds 500 to 2,800 (n=4); at the bounds the
   central moves $64 to $84. M-1/M-P2 tighten it.
5. **Batch size at 2b** (demoted from first place in revision 1): the
   batch-15-versus-5 saving is $5 to $6 at $5/$25, and $16 at $15/$75. The
   revision-1 claim of a $56 penalty was falsified; it was mostly the
   falsified 4,400 fixed term times the falsified Opus output price. Batch 5
   stays the default; section 3.3 has the contingent rule.

Quality does not pay for this. The expensive configuration was the broken
one: at effort low the replay shows zero overflows, every response parses,
coverage equal or better; the validator fix stops escalating a third of the
graph for citing real evidence at its use site (now implementable store-only,
section 3.2 item 2a); the partitioner fix stops rolling the same component
3.52 times and keeping the last roll. Section 9 lists each quality claim and
its measurement, with the parity metrics now defined (section 3.3).

## 1. Current code, verified

The postmortems describe the code as of the killed run. Landed since,
verified in current source (QA's independent register agrees line-exact):

- **Systemic-failure circuit**: `analyzer/enrich/pipeline.py:180-250`
  (threshold of 5 identical failures, `pipeline.py:197`), fed on every call
  at `pipeline.py:383`.
- **Soft per-run cost ceiling plus wall ceiling**: `BudgetMeter`
  (`pipeline.py:133-266`), checked before launch (`pipeline.py:362`) and at
  pool top-up (`ladder.py:481-488`).
- **Live telemetry**: ledger streamed row-by-row (`pipeline.py:617-641`).
- **Deliberate run records**: `demos/runs/` gitignored, keepers added with
  `git add -f` (commit f7501c3).
- **Cache reads split out**: `tokens_cached` separate (`pipeline.py:283`,
  `pipeline.py:308-329`).

NOT landed, verified absent:

- **No effort pin.** `ClaudeCliInvoker` argv is
  `claude -p --output-format json --tools "" --setting-sources user [--model X]`
  (`analyzer/enrich/engine.py:182-187`). No `--effort` anywhere in
  `analyzer/`.
- **Success path still discards `stop_reason` and `num_turns`**
  (`engine.py:236-243`; error branch only at `engine.py:227-230`). The drift
  alarm at `pipeline.py:390-400` is still starved on success.
- **Validator still requires the definition site**
  (`analyzer/enrich/evidence.py:236-250`).
- **Partitioner still duplicates components across chunks**
  (`analyzer/enrich/partition.py:249-264`). Store re-derivation: 173
  partitions, 569 components, 2,003 component slots, 5,453 relationship
  slots, 55 groups, duplication 3.52x. QA re-derived independently; exact.
- **No parse salvage, no ladder parse retry** (`engine.py:468-488`,
  `ladder.py:439-460`). The validation plan's seam-aware fence-strip finding
  (line-based stripping recovers only 7 of 10) is the required
  implementation detail.
- **Cache creation still conflated into `tokens_in`** (`pipeline.py:328`).
- **Ledger `targets` still undercounts 2a fourfold** (`ladder.py:496-503`).

One deterministic defect found in revision 1 and confirmed by both
reviewers, with magnitudes corrected per their measurements:

- **Fact blocks are capped by count, not by size.** `component_facts`
  truncates capabilities to 12 entries but passes each entry's `detail`
  uncapped (`analyzer/enrich/prompts.py:200-205`). Measured: 354,743 chars
  of capability detail under `cli/src/util` (QA V-1; revision 1 said
  372,564, a scoping difference on the same defect); that component's fact
  block alone is 195,525 scaled tokens and the worst rebuilt partition
  prompt is 217,026 scaled tokens (Prompt Engineer, independent
  calibration), which exceeds the 200k context window. The defect and the
  conclusion stand at the corrected magnitudes. Fix is deterministic: a
  per-component fact byte budget (20k scaled in the model), with the
  menu-stability constraint of section 3.2 item 6.

## 2. Design principle

Work flows to the cheapest tier that can do it correctly, and every
escalation is a priced failure that records what the cheaper rung lacked.
Concretely:

1. **Rung 0 (deterministic, $0) does everything the store already knows.**
2. **Rung 2a writes everything once**, split by target kind, at pinned low
   effort, in compact schema. It does not merely route; see 3.1.
3. **Escalation carries a structured handoff** so no rung re-establishes
   what a lower rung proved. The receiving rung answers only the named gaps.
4. **Every batch size is derived from the output ceiling with the measured
   dispersion applied**, then validated on a sample:
   `batch_max = floor((0.85 * ceiling / dispersion_max(effort) - fixed_out) / per_item_out)`.
   Revision 1 used a flat 0.85 headroom; QA measured per-call dispersion of
   0.72x to 1.90x at xhigh and showed a mean-calibrated gate misses 5 of 12
   real overflows, so the dispersion factor is structural, held at 1.90
   until Level 1 recalibrates `dispersion_max(low)` from at least 10 calls.
5. **Work is banked the moment a call's payload absorbs**, so a kill loses
   at most the in-flight calls.

## 3. The rung hierarchy

| rung | question | model | effort | batch | calls (VS Code) |
|---|---|---|---|---|---|
| 0 | what does the store already know? | none | n/a | n/a | 0 |
| 2a-comp | describe and ground each component in this group; name what you cannot ground | sonnet | low (pinned) | **cap 21 components** (G2 rule, below) | **61** |
| 2a-rel | say what crosses each edge and why, grounded, given the components' one-liners | sonnet | low (pinned) | 80 rels | 100 |
| 2b | close exactly these named gaps; corrections only | opus | low (pinned) | **5 (default)**; 15 gated by M-2 parity | 188 (63 at batch 15) |
| 2c | ground or declare an honest gap; terminal | fable | low (pinned) | 5 | 19 to 58, bounded (section 6) |

Call counts re-derived from the real store: 61 = 55 groups with the 6 groups
over 21 components (five of 30, one of 24) split in two; 100 relationship
calls at batch 80 per-group; 188/63 = ceil(285/5)+ceil(654/5) and
ceil(285/15)+ceil(654/15) at the post-validator-fix populations. The Prompt
Engineer's independent chunking reproduces all counts.

**The 2a-comp cap is 21, not revision 1's 30 or the review's proposed 24.**
The binding rule is QA's G2 with the agreed sign-off margin: worst-call
predicted mean times the 1.90 dispersion default at or under 0.85 of the
64,000 ceiling. At the conservative block (1,263 + 20 entry) plus the
adjudicated 1,369 fixed: cap 21 gives mean 28,312, times 1.90 is 53,793,
84.1% of ceiling, PASS. Cap 24 gives 61,106, 95.5%, FAIL. Cap 21 is also the
Prompt Engineer's independently computed setting; the two specs now cite one
rule and one number. The cap relaxes only when Level 1 measures
`dispersion_max(low)` below 1.90 on at least 10 calls of the new schema
(M-1/M-P2, merged).

Efforts are pinned per rung in the tier binding (`ModelSpec` gains an
`effort` field, `analyzer/enrich/models.py`), passed as `--effort` on the
argv (`engine.py:182-187`; flag verified present in CLI 2.1.220). Low is the
only measured-stable setting: 73% less output, zero overflows, equal or
better coverage, and medium measured erratic (the two medium probes at 4,518
versus 10,820 billed, byte-matched in the located replay transcripts).

### 3.1 The minimal question per rung, and the pressure test (brief Q1)

The plan document proposes 2a as "grounded, yes or escalate". **Rejected,
with the math.** A route-only 2a still pays the full input cost (the facts
must be read to judge groundability; at the adjudicated constants 2a's
input side is about $13 of cache creation either way), saves only the
output of grounded items, and then requires a second pass to write the
product fields and contract answers for the roughly 70% of items that pass.
That second pass re-pays the input and adds a fourth model pass to the
chain. The store needs, per component: the product fields and the contract
answers with evidence (`prompts.py:49-101`, `prompts.py:734-806`).
Yes/escalate produces none of that. Revision 1's "$8 either way" was
falsified in figure (O-6); the corrected figure at the 2x write rate is
about $13, and the structural conclusion is unchanged and stronger.

The chain, with no hidden work:

- **Rung 0** answers deterministically everything with a deterministic
  answer (section 3.2). Output: contract rows for identity questions, schema
  defaults, and the fact blocks every later rung reads.
- **2a-comp** is the writer for components. The routing verdict is
  **computed, not asked**: `evaluate()` recomputes the state from answers
  and citations (`analyzer/enrich/contract.py:305-408`), as current code
  already does. The model never decides its own escalation; it only makes
  its failure legible (the `l`/`need` self-report, section 4).
- **2a-rel** runs after 2a-comp and consumes its product: each relationship
  call carries one-liners for every distinct endpoint of its 80 edges
  (endpoints cross groups; measured 3,703 scaled per call with parser-era
  descriptions, about 4,700 with fresh ones). **Sequencing rule (H1,
  adopted)**: a group's relationship calls unlock when the component calls
  covering that call's endpoint set have absorbed; the two call kinds
  interleave in one pool under importance order, so the dependency costs
  scheduling, not a serialized rung. **Fallback (H1)**: an endpoint whose
  component call failed or has not run contributes a facts-only one-liner
  (id, name, type, path, language, framework from the parser), never blocks
  the relationship call, and the ledger row records the degraded context.
- **2b** answers only the failed questions in the handoff, as deltas. The
  merge machinery guarantees unanswered questions keep their lower answers
  (`ladder.py:103-137`). Current code's instruction to "repeat it back
  unchanged" (`ladder.py:170-173`) is repealed; adjudication of prior
  answers becomes the `corrections` list, present only when something was
  wrong.
- **2c** is unchanged in concept: ground it or declare an honest gap, with
  the examined-versus-unexamined distinction already landed
  (`ladder.py:580-636`). Its bound is section 6.

Every store field is produced exactly once, by the cheapest rung that can
produce it.

### 3.2 Deterministic replacement (brief Q3)

Enumerated against current code. Items 1 to 4 are known fixes specified in
the postmortems; 5 to 9 are new to this spec; verification status updated
per QA.

1. **Component duplication, 3.52x** (`partition.py:249-264`). Fix: split
   calls by target kind. Removes 1,434 of 2,003 component slots, 42.8% of
   delivered output. Also what makes absorption commutative (section 7).
2. **Identity questions the parser already answered** (`contract.py:96-115`;
   contradiction check never runs, `strict_identity` False at
   `contract.py:319`). Fix: rung 0 writes the identity contract answers with
   detector evidence; the model speaks about identity only to disagree.
   **Provenance status (QA V-2/V-3)**: `framework` and `port` have citable
   signal rows (`file_id` plus `line`); `language` and `type` need a stated
   derived-evidence convention (dominant-extension census, manifest row)
   before R-14 lands. Half resolved, half named.

   2a. **The validator fix is store-only (QA V-2, resolved better than
   asked).** The store already holds a referenced-at index: `signals` rows
   with `kind='symbol_reference'` (157,508 rows carrying name, file and
   line), covering 1,162 of 1,162 of the corpus's wrongly rejected symbol
   citations. R-5 loads `(path, symbol)` reference pairs in
   `EvidenceValidator._load`, returns a distinct `referenced-at` verdict,
   keeps `defined-at` from `_symbols_by_path`. No filesystem reads, no
   loosening.
3. **Constants emitted as data** (status 91 to 93%, confusion null 88%,
   parser_first empty 91%, self_state grounded 89%). Schema defaults: absent
   means the default. The Prompt Engineer's schema (PROMPT-SPEC section 6)
   implements this; adopted.
4. **Evidence transcription** (100.0% relationship, 96.7% component
   citations restate the prompt). Fix: evidence by reference into the
   prompt's menus; the validator resolves references deterministically.
5. **`substitution_check` as prose** read by substring match
   (`contract.py:550-567`). Fix: structured field; the E4 path
   (`contract.py:542-547`) reads it directly. M-P6 A/Bs detection power.
6. **Fact-block byte budget** (section 1), with the **menu-stability
   constraint (H2, adopted)**: truncation must never alter the citation
   menus after a prompt is built. Menus are truncated deterministically
   BEFORE prompt build, the validator resolves indexes against the same
   stored menus, and a rerun reproduces them byte-identically. QA owns the
   menu-stability test next to R-10.
7. **Ledger accounting**: true target counts, partition/batch id, session
   id, `stop_reason`, `num_turns`, `cache_creation` split with TTL class
   (section 8).
8. **Parse salvage** (fence-strip seam-aware per the validation plan's 7/10
   finding, overlap dedupe, brace span) plus the ladder's one corrective
   retry.
9. **Deterministic scheduling for cache reuse** (section 8): importance
   ordering per rung; relationship chunks of one group dispatched
   adjacently; the H1 unlock rule above.

### 3.3 Batch sizing with the amortization math (brief Q4)

The rule (section 2 item 4) applied per rung, at conservative blocks and the
1.90 dispersion default; `data/cost-model.py` prints the check:

- **2a-comp: cap 21** (84.1% of ceiling; see section 3 for the full
  arithmetic and the recalibration condition).
- **2a-rel: batch 80** holds with wide margin (mean 15,209, times 1.90 is
  28,897, 45.2%).
- **2b: batch 5 default, 15 gated.** Output-safe at either (worst mean about
  3.1k repairs-only; even a pathological full re-emission of 15 components
  is about 20.8k mean, 62% dispersion-adjusted). The economics, corrected:
  batch 15 saves $5 to $6 at Opus $5/$25 and about $16 at $15/$75.
  **Decision rule**: batch 5 remains the default; batch 15 is adopted only
  if M-2 passes the parity metric below AND the arbitrated Opus price makes
  the saving worth having (at $5/$25 it is optional; at $15/$75 it is
  worthwhile). Revision 1's "$56 penalty" and "single cheapest decision"
  claims are withdrawn (falsified, O-2).
- **2c: batch 5.** The population is small and terminal honesty per item
  matters more than the sub-dollar saving of a larger batch.

**Parity, defined (O-10, mandatory revision).** For M-2 (batch 15) and M-4
(tier C schema), "parity" means both of:

1. **Recompute-harness parity**: running both arms' outputs through the V-5
   harness (`state_from_block` plus the fixed validator), the grounded rate
   shifts by no more than 2 percentage points, and no E-trigger class
   appears in one arm that is absent from the other.
2. **Blind spot-check parity** per VALIDATION-PLAN section 9: stratified
   blind-scored sample, correct-rate not below the comparison arm by more
   than 8 percentage points at n=50, and zero `wrong` verdicts on
   critical-importance items.

An arm that fails either metric fails parity; there is no judgment call at
sign-off time.

**Group merging (O-9, restated).** Revision 1 claimed group coherence is
worth more than merging small groups into packed calls. That was an
untestable quality claim and is withdrawn as a claim. It is now a design
preference: one call per group is simpler, reproduces the partitioner's
structure, and the corrected economics make packing worth at most about $2
per run, which does not buy the added machinery. Anyone who wants the
dollar can piggyback a merged-group arm on M-4 and put a number on
coherence; until someone does, preference stands, evidence-free and labeled
as such.

### 3.4 Wall time

Re-based per H7 (adopted): at corrected low-effort outputs (central about 10
to 11k per 2a call) generation runs about 90 to 150s per call at the killed
run's measured 120 tokens/s. At `max_parallel` 4 (`pipeline.py:453`): 2a
about 1.1 to 1.6h, 2b 15 to 40 minutes, 2c under 15 minutes, ladder roughly
1.5 to 2.5h. Per-call p95 quotes the dispersion factor (mean times up to
1.9) for scheduling and timeout budgets; the 1,200s invoke timeout
(`pipeline.py:457`) clears the p95 call comfortably. Estimates, re-based
after M-P1.

## 4. The escalation protocol (brief Q2)

### 4.1 One handoff format, two directions (H3 merge, adopted)

The protocol is `escalation/v1` as the INPUT format, unchanged from
revision 1: per item `established` (settled answers with validated
evidence), `failed[]` with `question`, `trigger`, `attempt_claim`,
`citations_tried` (each citation with the validator's verdict string),
`lacked`, `note`, plus `facts` and `todo`. The OUTPUT format is the Prompt
Engineer's array envelope (explicit `"i"`/`"k"` fields, no dynamic keys, so
`--json-schema` stays simple), carrying only `todo` answers plus the
`corrections` list adopted inside each entry. One format each direction;
both specs cite this section and PROMPT-SPEC sections 3 to 5 as the single
definition.

### 4.2 The `lacked` vocabulary and the sending-side self-report (H8, one rule)

The closed vocabulary and its authority split:

- `fact-not-in-prompt`: the needed fact exists but was not provided; routes
  once through rung-0 fact augmentation instead of up the ladder.
- `judgment`: facts present, genuinely hard; climbs.
- `validator-scope`: evidence real but outside the checker's acceptance;
  when this dominates, the validator is the bug (658 of 795 relationship
  E2s in the killed run).
- `capability`: the sending model could not do the task.
- `unknown`: residual, coordinator-assigned only.

The sending rung emits the self-report in the Prompt Engineer's field form:
`"l": "fact" | "judgment"` plus `"need": "<the missing fact>"`, on uncertain
answers only. Two constraints, from my review of that extension, both
accepted into the shared design:

1. **Schema-bound to uncertainty**: `l`/`need` are valid only alongside
   `"s": "u"` (schema `dependentSchemas`, or the absorber strips them from
   answered claims), so the field cannot become padding.
2. **The coordinator validates `need` before routing**: a `need` resolvable
   against the store (the named file, symbol or config is in the analyzed
   set) routes to fact augmentation; an unresolvable `need` reclassifies to
   `judgment` and climbs normally, with the text kept for the weekly
   escalation review. The coordinator alone assigns `validator-scope` and
   `capability` from validator verdicts and parse state, and overrides the
   self-report where the verdicts contradict it.

### 4.3 Worked example, real data

Relationship
`extensions/copilot/src/extension|src/vs/platform/contextkey/common|uses`,
session `c95c2999`: the 2a response cited `ContextKeyExpr` at its use site
(line 125 of a fixture file the prompt's own facts listed). The current
validator rejects it: `symbol 'ContextKeyExpr' exists in the index but not
in <path>` (`evidence.py:242-247`). Under this protocol the item's
`citations_tried` carries that verdict, the coordinator forces
`lacked: "validator-scope"`, and under the store-only fix (section 3.2 item
2a) the citation validates as `referenced-at` and the item never escalates.
The 2b call for an item that still escalates reads `established` (settled),
`failed` (work), `facts` (grounding) and returns one array entry
`{"k": "<key>", "flow": {answer}, "corrections": []}` in the merged
envelope.

### 4.4 Cost of the handoff

Estimated 750 tokens per component item and 400 per relationship item on
the input side; delta repairs estimated 480/145 on the output side. All
four are flagged to M-2, and the failed-questions-per-item distribution
beneath them runs on the V-5 harness at zero cost first (QA has scheduled
it). What the handoff buys is unchanged: 2b output drops from full
re-emission to deltas, and the re-discovery failure mode is structurally
gone.

## 5. The per-rung cost model (brief deliverable 3)

All figures from `data/cost-model.py` revision 2; run it to reproduce.
Sources: **[ADJ]** the binding adjudication, **[PE]** Prompt Engineer
measurements QA confirmed, **[L]** ledger, **[S]** store re-derivation,
**[PM]** postmortems, **[F]** flagged with resolving measurement.

Parameters:

| parameter | value | source |
|---|---|---|
| marginal chars per billed token | 2.886 | [ADJ] fit over 35 first turns; spot 2.72; replaces the falsified 1.71 |
| fixed prompt-side overhead per call | 12,546 tok | [ADJ] fit intercept; warm call creates it, later calls read at 0.1x |
| unique input billing class | 1h cache creation, 2x base | [ADJ]/[PE] every recorded first turn |
| 2a out per component / relationship / call fixed, tier B at low | 1,050 / 382 / 1,369 (fixed bounds 500 to 2,800) | [ADJ] lsq over all 4 replay probes, max err 5.7%; replaces the falsified 1,100/320/4,400 |
| tier C blocks (comp / rel, entry included) | 900 / 144 | [PE] measured transform, central; [F] M-P1/M-4 |
| component facts, byte-capped, all 569 | 373,182 tok | [PE] D7, direct measurement |
| edge menus, all 569 | 51,900 tok | [PE] 2.2 |
| relationship fact block | 235 tok | [PE] D5, n=400 |
| 2a-rel context per call | 4,700 tok | [PE] D6 measured 3,703 + fresh-run caveat; [F] M-5 |
| rung prefixes (2a-C/2a-R/2b/2c) | 4,364 / 2,808 / 3,072 / 2,745 | [PE] re-measured after the l/need additions (QA final verdict E-2) |
| prices: sonnet / fable | $3/$15, $10/$50 | [L] rows repriced to 1.6% / 1.8% [ADJ] |
| price: opus | **dual: $5/$25 and $15/$75** | no artifact exists; first pilot Opus row arbitrates [ADJ] |
| escalation populations | 285 + 654 = 939 (comp 50%, rel 12%) | [PM] baseline restored per QA final verdict E-1; M-P5's harness recompute supersedes both counts when it runs |
| 2b item input (comp / rel) | 2,477 / 635 | [PE] D8 escalated-set facts 1,727 (population [F] M-2) + handoff [F] M-2 |
| 2b delta out (comp / rel) | 480 / 145 | [F] M-2; distribution on V-5 harness at $0 first |
| 2c item input / output (comp, rel) | 2,477, 635 / 300, 120 | [PE] D11 shapes + second attempt; [F] M-2/M-P3 |
| 2c entry fraction | 10 to 30% | [F] M-2 |
| dispersion_max | 1.90 (all efforts) until Level 1 recalibrates | QA G2, binding |

Results (2c central 20%):

| rung | calls | Opus $5/$25 | Opus $15/$75 | dominant term |
|---|---|---|---|---|
| 2a-comp | 61 | $11.9 (tier C) to $13.2 (tier B) | same (sonnet) | output blocks |
| 2a-rel | 100 | $24.9 (C) to $44.4 (B) | same (sonnet) | rel output; input $10.5 |
| 2b | 188 (batch 5) | $25.1 | $75.2 | input $11.2 to $33.7 + fixed |
| 2b | 63 (batch 15) | $19.8 | $59.4 | |
| 2c | 19 to 58 | $4.9 to $14.4 | same (fable) | population |
| **ladder** | ~350 (~225 at batch 15) | **$61 to $97, central ~$69** | **$101 to $147** | |

Sensitivity: the adjudicated fixed-output bounds (500 to 2,800) move the
$72 batch-5 central between $64 and $84.

Reconciliation: the QA-corrected revision-1 model gives $55/$64/$96
(lo/mid/hi at $5/$25); the Prompt Engineer's independent model gives $59.4
central / $65.0 conservative. This model's $61/$66-72/$97 sits within $4 to
$7 of both, and the deltas are the measurement choices named in section 0.
Three differently built models now agree inside the flagged-estimate noise,
which is the convergence the adjudication was for.

Not claimed: any saving from `data_flow_description` versus `flow.claim` or
`help_text` versus the contract prose (measured textually distinct;
rejected by the efficiency postmortem).

## 6. Bounding rung 2c (brief Q5)

1. **Entry criteria.** An item enters 2c only if: (a) its 2b call returned a
   payload (the examined set, `ladder.py:581-598`), (b) its handoff is
   complete under protocol v1, (c) its `lacked` is not `fact-not-in-prompt`
   (those loop once through rung-0 augmentation and re-enter 2b, one loop
   maximum).
2. **A budget slice.** 2c may spend at most 15% of the run ceiling. Worst
   case regenerated at the adjudicated constants: all 939 items entering 2c
   is 188 calls and **$46.7** (`data/cost-model.py`; revision 1's $131 was
   built on the falsified constants). At the modeled 10 to 30% entry it
   costs $4.9 to $14.4 and never approaches the slice.
3. **A terminal state that is not 2c's problem.** An item 2c cannot
   finalize, or the slice never lets launch, stays in the `escalate` census
   state, which the determination refuses to call complete and `--update`
   re-targets (`ladder.py:607-636`).

Worst-case per-call output at 2c: 5 items times 300 plus 1,369 fixed is
2,869 mean, 8.5% of ceiling dispersion-adjusted. No 2c call can overflow.

## 7. Checkpointing and kill-safety (brief Q6)

Unchanged in design from revision 1; loss-bound figure re-based.

1. **Absorb on completion**, commit per call. Safe because the target-kind
   split makes every target the product of exactly one call per rung, so
   absorption is commutative and the store's end state is order-independent.
   Hard dependency: R-8 before R-9.
2. **Loss bound**: at most `max_parallel` in-flight calls' spend, about $1
   at corrected 2a call costs, and zero banked rows.
3. **Resume** from contract-state rows (`CONTRACT_TARGET_KIND`,
   `ladder.py:68`) keyed by digest and commit, reusing the staleness
   machinery `--update` already has. `--fresh` forces a full re-run.
4. **Kill handler**: SIGINT/SIGTERM stops launches via the budget meter's
   existing `under()` gate, drains, absorbs, commits, writes the report with
   `stopped_by: signal`.

## 8. Context reuse and the fixed telemetry (brief Q7, jointly owned with the Prompt Engineer)

Placement per PROMPT-SPEC section 10 (adopted): rung instructions and the
brief travel in the appended system prefix (byte-identical per rung per
run), facts in the user message, per-call values after the facts. The
`--append-system-prompt-file` caching behavior is a named Level 1 assertion
(M-P1 must show the warm/read pattern below), not an assumption.

Ordering rules: warm_first stays (`ladder.py:477-480`, `pipeline.py:460`);
relationship chunks of one group dispatch adjacently; each rung warms its
own model-scoped cache; the H1 unlock rule schedules 2a-rel behind its
endpoints' component calls.

Ledger changes (the fixed telemetry): `LedgerRow` (`pipeline.py:270-305`)
gains `tokens_input_uncached`, `tokens_cache_creation_1h` and `_5m` (the
usage block carries the split, QA V-6 resolved; undoing the conflation at
`pipeline.py:328`), `tokens_cache_read`, `stop_reason`, `num_turns`,
`effort`, `session_id`, `call_id`, `prefix_hash`, and true target counts
(fixing `ladder.py:496-503`). The invoker forwards `stop_reason` and
`num_turns` on the success path (`engine.py:236-243`), feeding the built
drift alarm (`pipeline.py:390-400`).

**What the ledger must show when caching works** (predicates corrected per
H5, which showed revision 1's would flag every healthy call):

- Warm call per rung: `tokens_cache_creation_1h` approximately CLI overhead
  plus prefix plus that call's user message; `tokens_cache_read` small.
- Every later same-rung call: `tokens_cache_read` approximately CLI
  overhead plus prefix (12,546 + the rung's prefix, near-constant);
  `tokens_cache_creation_1h` approximately that call's own user message;
  `tokens_input_uncached` at or under 10; `prefix_hash` identical;
  `num_turns` 1.
- A later call whose read falls below the prefix-plus-overhead level is a
  cache miss; more than 20% of calls missing fails the telemetry gate
  (thresholds set from M-P1's rows, QA owns the gate).

TTL, corrected per H6: the 1h write class is the CLI's choice on every
first turn, not a consequence of call length; the usage block's
`cache_creation.ephemeral_1h/5m` fields are the record, and the remaining
sliver is whether the CLI's stdout envelope forwards the split (Level 1
envelope capture).

## 9. Quality claims and how each is measured

| change | claimed effect | measured by |
|---|---|---|
| effort pinned low | equal or better coverage, zero overflow | M-1/M-P2 (merged), then run census + overflow count |
| validator referenced-at fix | removes false E2s only; verdict recorded distinctly | V-2 store-only fixture + recompute harness (1,162 of 1,162 covered) |
| target-kind split | none (removes duplicate rolls) | census conservation (R6) + M-4 |
| delta-only 2b | none on grounded content (merge keeps it) | merge-property test (V-4) + M-2 parity as defined in 3.3 |
| batch 15 at 2b | none permitted | M-2 parity as defined in 3.3 |
| tier C schema | none permitted on product fields or contract answerability | M-4/M-P1 parity as defined in 3.3 |
| 2c bound | more honest `escalate` states, fewer silent runaways | census + budget slice accounting |
| byte budget + menu stability | none (menus stable before build) | QA menu-stability test (H2) |

## 10. Proposed measurements

Zero live calls were run for this revision. Consolidated with the Prompt
Engineer's M-P series where the coordinator's plan overlaps.

- **M-1/M-P2 (merged), low-effort stability and dispersion.** 10 to 12 real
  calls on the new prompts at `--effort low` (component and relationship
  kinds). Bound $6. Resolves: low-effort stability on the new schema, the
  per-call fixed term inside its 500 to 2,800 bounds, and
  `dispersion_max(low)` for the G2 calibration table, which is the cap-21
  relaxation condition. Primary output, not a byproduct.
- **M-2, 2b batch and handoff validation.** About 30 real escalated items
  from the V-5 harness reconstruction; 2 batches of 5 and 2 of 15 at low,
  delta-only protocol, on Opus. 6 calls, bound $8 at $5/$25 (up to $24 if
  the price arbitrates high; the bound is stated dual like the price).
  Resolves: batch-15 parity (metric in 3.3), handoff and delta sizes, a
  first 2b failure rate for 2c sizing, and **the first Opus ledger rows,
  which arbitrate the dual price**. The failed-questions distribution runs
  on the harness at $0 before this spends anything.
- **M-3/M-P3, Opus and Fable thinking at low.** No dedicated calls:
  regression over M-2's rows plus two Fable rows.
- **M-4/M-P1 (merged), tier C schema parity.** 3 component groups plus 3
  relationship chunks, both schemas at low. About 12 Sonnet calls, bound
  $6. Resolves: tier C block sizes, new-schema envelope (the measured
  floor, not 30), compliance with index citations, and the
  `--append-system-prompt-file` cache assertion (section 8).
- **M-5, one-liner sufficiency for 2a-rel.** 2 chunks with full facts
  versus one-liners. 4 calls, bound $3. Also measures fresh-description
  context size (the 4,700 figure).
- **M-6, cache telemetry validation.** No dedicated calls: assert section
  8's predicates on M-2/M-4 rows once the ledger split lands; set the gate
  thresholds from those rows.
- **M-7, P3 to P5 cost.** Priced from the next smoke run's ledger.
- **M-8 (replaced; the original was untestable as stated).** The original
  "fit any two fable rows" is withdrawn: four unknown rates against two
  equations is underdetermined. Replacement: prices are asserted from the
  named sheet, then verified against pilot ledger rows per rung (the M-P7
  method); the Fable and Sonnet rates are already ledger-verified, and the
  Opus rate is arbitrated by M-2's first rows, required on record for
  Level 2 sign-off.

Total dedicated spend: **under $25 at $5/$25** (M-2 and M-4 dominate), with
M-2's bound doubling if the Opus price arbitrates high.

## 11. Implementation roadmap, dependency order (brief deliverable 4)

**Phase A: known fixes, already specified in the postmortems, no gauntlet
needed.**

- R-1. Pin `--effort` per rung: `ModelSpec.effort`, argv in
  `ClaudeCliInvoker` (`engine.py:182-187`), registry plumbing. Gate:
  M-1/M-P2 passes first.
- R-2. Success-path `stop_reason` and `num_turns` (`engine.py:236-243`).
- R-3a. **G2 preflight gate**, exactly per VALIDATION-PLAN 4.2: predicted
  mean times `dispersion_max(effort)` under the ceiling for every planned
  call, calibration table with named run basis, refusal on failure.
- R-3b. **W1 in-flight tripwire**: warn at 0.85 of ceiling on per-call
  `tokens_output` and `stop_reason == max_tokens`; abort semantics per the
  validation plan. (Revision 1 conflated R-3a and R-3b into one item.)
- R-4. Parse salvage (seam-aware fence strip per the 7/10 finding, overlap
  dedupe, brace span) plus the ladder's corrective retry.
- R-5. Validator referenced-at fix, **store-only** via `symbol_reference`
  signals (V-2): load reference pairs in `_load`, distinct `referenced-at`
  verdict, `defined-at` kept. Fixture: the 1,162-citation pass set.
- R-6. Ledger fields (section 8) including the `targets` fix,
  cache-creation TTL split, `effort`, `session_id`, `prefix_hash`.
- R-7. Per-call `--max-budget-usd` backstop; `--json-schema` evaluation
  rides M-P4.

**Phase B: structural, deterministic, testable without model calls.**

- R-8. Partitioner target-kind split (component-only and relationship-only
  call plans, cap 21 and batch 80, byte-stable, unit-tested).
- R-9. Absorb-on-completion checkpointing with per-call commit and resume
  from contract-state rows. Depends on R-8 for commutativity.
- R-10. Fact-block byte budget (20k scaled per component) WITH the
  menu-stability constraint (section 3.2 item 6) and its QA test.
- R-11. Kill handler.

**Phase C: new design, sample gauntlet first.**

- R-12. Escalation protocol v1 with the merged output envelope (4.1), the
  `l`/`need` self-report with its two constraints (4.2), coordinator
  override rules. Gate: M-2.
- R-13. Batch 15 at 2b, contingent per 3.3 (parity AND price). Gate: M-2.
- R-14. Rung 0 identity answers and `required_questions` reduction. Gate:
  the V-3 convention for `language` and `type`, stated before landing.
- R-15. 2a-rel one-liner context with the H1 unlock and fallback rules.
  Gate: M-5.
- R-16. Tier C schema adoption (Prompt Engineer owns the schema; batch
  bounds recompute mechanically from measured blocks). Gate: M-4/M-P1.
- R-17. 2c bound (entry criteria, budget slice, augmentation loop). Gate:
  M-2's failure-rate reading.

Every Phase C item lands behind the no-regression protocol.

## 12. Handed to the other personas

**QA and Validation Engineer:**

- V-1 (cost model re-run): revision 2 regenerates from the adjudicated
  constants; the two deviations from your corrected table are the
  measurement choices named in section 0, for your confirmation.
- V-2, V-3, V-6, V-7: resolved or adjudicated per your pass; consumed
  above.
- V-4: the telemetry gate now carries the H5-corrected predicates and
  `prefix_hash`; thresholds from M-P1 rows.
- V-5: the recompute harness is the substrate for M-2's items, the
  failed-questions distribution, and the M-P5 population check; all
  scheduled at $0 before any live probe.
- New: the H2 menu-stability test beside R-10, and the Level 3 projection
  line in the gauntlet ($110 to $250) needs re-anchoring to the
  post-adjudication bands before the full-run cap inherits it.

**Prompt and Context Engineer:**

- The H3 merge is adopted as specified in 4.1; the `l`/`need` constraints
  of 4.2 are the coordinator-side contract; H1's unlock and fallback rules
  are stated in 3.1 for your prompt sections to reference. Your D-series
  and H-series findings are folded per the changelog; dispositions in
  section 13.

## 13. Review findings not adopted, or adopted with modification

- **PE D2 as originally framed (adopt Opus $5/$25 as the working
  constant): modified, not adopted.** The cited sheet is a cached reference,
  not a recorded run artifact, and no ledger row can check it. Per the
  adjudication, the price is carried dual ($5/$25 and $15/$75) with the
  first pilot Opus row as arbiter and Level 2 sign-off requiring it. Every
  Opus-priced figure in this spec appears under both prices.
- **PE section 6's evidence notes on the 1.90 dispersion (that it partly
  measures the overflow-continuation feedback, and that low-effort
  actual-to-predicted ran 0.93 to 1.08 on n=4): not adopted as a basis for
  relaxing G2 now.** Both observations are plausible and worth testing, and
  n=4 is exactly the sample size the adjudication ruled insufficient
  elsewhere. They are folded into M-1/M-P2 as hypotheses the
  `dispersion_max(low)` calibration will confirm or refute; until then 1.90
  and cap 21 stand.
- **QA's rescaled input constants (comp facts 304k, rel fact 201, 2b comp
  facts 871) where the Prompt Engineer has direct measurements: not
  adopted; the measurements are.** The rescale applies one marginal rate to
  quantities that were measured individually with the o200k-scaled method
  QA itself confirmed (P-5, P-7, P-9). This is the stated reason revision
  2's central sits $3 to $6 above the QA-corrected table, and D8's
  population question stays flagged on M-2 either way.
- **QA O-6's corrected "$4.5" input figure: recomputed rather than
  adopted.** At the adjudicated 2x write class and the measured input
  volumes, 2a's input side is about $13. The falsification of revision 1's
  "$8" stands; the corrected figure differs from the QA table's because
  that entry appears to rescale tokens without applying the write class.
  The route-only rejection is unchanged at any of these figures.
- **QA's "keep batch 5 permanently unless parity is clean AND someone still
  wants the ~$5": adopted with one addition**, the price contingency (at
  $15/$75 the saving is $16 and worth wanting). Stated in 3.3.

Everything else in both reviews and the adjudication is adopted as written.

## 14. Changelog: revision 1 to revision 2

Driver key: [ADJ] binding adjudication, [PE] Prompt Engineer review,
[QA] QA finding or testability verdict, [COORD] coordinator ruling.

1. Headline restated: $96-155/$115 replaced by $61-97/~$68 at Opus $5/$25
   with the $101-147 dual band; full run ~$72-118/~$82. [ADJ O-1]
2. Swing ranking rebuilt; Opus price now first; batch-15 "$56 penalty"
   withdrawn, corrected to $5-6 / $16 contingent. [ADJ O-2, dispute 3]
3. Input calibration: 1.71 chars/token replaced by marginal 2.886 with the
   12,546-token per-call overhead priced separately; unique input priced at
   the 1h write rate (2x). [ADJ dispute 1; PE D1/D3; COORD]
4. Output model: 1,100/320/4,400 replaced by the adjudicated 1,050/382/1,369
   (bounds 500-2,800); revision 1's decomposition recorded as falsified on
   the held-out replay point. [ADJ dispute 2; PE D4]
5. Prices: Fable corrected to $10/$50 (ledger-fit); Opus dual-priced, first
   pilot row arbitrates, required for Level 2 sign-off. [ADJ dispute 3;
   COORD]
6. 2a-C batch cap: 30 (rev 1) and 24 (my review proposal) both fail the
   binding G2 rule (mean x 1.90 at or under 0.85 x 64,000); cap set to 21,
   61 calls (6 groups split), matching the Prompt Engineer's computation.
   [QA G2; PE section 6; COORD]
7. Batch formula rewritten with the dispersion factor; 0.85 flat headroom
   demoted to W1's in-flight warn role; R-3 split into R-3a (G2 preflight)
   and R-3b (W1 tripwire). [QA G2]
8. M-1 merged with M-P2 at 10-12 calls, emitting dispersion_max(low) as a
   primary output; cap-21 relaxation bound to it. [QA; my review item 6]
9. Byte-cap magnitudes corrected: 354,743 chars detail, 195,525-token
   component block, 217,026-token worst prompt (still over the 200k
   window); defect and fix unchanged. [QA V-1; PE D7; COORD]
10. Input volumes moved to PE direct measurements: comp facts 373,182
    capped, edge menus 51,900, rel fact 235, rel context 4,700 with the
    fresh-run caveat, rung prefixes 4,226/2,677/2,984/2,745. [PE D5-D7,
    D9; QA confirmations]
11. 2b item inputs moved to the escalated-set planning figure (1,727 facts)
    with the population flagged to M-2; 2c items decomposed by kind with
    the second attempt priced. [PE D8, D11]
12. Escalation population harmonized at 284 + 654 = 938. [PE D10; COORD]
13. Handoff format merged: escalation/v1 input + PE array output envelope +
    `corrections` inside entries; `l`/`need` adopted as the sending field
    with the two constraints (uncertainty-bound, coordinator-validated
    `need`). [PE H3, H8; my review F-5; COORD]
14. H1 sequencing designed: endpoint-unlock rule, interleaved pool,
    facts-only fallback recorded in the ledger. [PE H1]
15. H2 menu-stability constraint added to R-10 with a QA test. [PE H2]
16. Cache predicates corrected to measured CLI behavior (creation = own
    user message; read = overhead + prefix); TTL causation corrected; V-6
    resolved via the usage split fields. [PE H5, H6; QA V-6]
17. CLI overhead priced per call in the model (~$1.2/run). [PE H4]
18. Wall time re-based to 1.5-2.5h with p95 quoting dispersion. [PE H7;
    QA G2]
19. O-6's "$8 either way" corrected to ~$13 at the adjudicated billing
    class; route-only rejection unchanged. [ADJ O-6, recomputed; section 13]
20. O-9 group-coherence claim withdrawn as a claim, restated as a labeled
    preference with the piggyback path onto M-4. [QA O-9]
21. Parity for M-2/M-4 defined as the two-part scored metric (harness
    verdict distribution within 2 points and no new trigger class; blind
    spot-check within 8 points at n=50, zero wrong-on-critical). [QA O-10]
22. M-8 withdrawn as underdetermined; replaced by sheet-assertion plus
    pilot-row verification, Opus arbitration on record for Level 2. [QA
    O-15]
23. 2c worst case regenerated: $131 replaced by $46.6 at the adjudicated
    constants and D11 shapes; slice logic unchanged. [ADJ O-18; PE D11]
24. Validator fix upgraded to store-only via `symbol_reference` signals
    (1,162 of 1,162 covered); R-5 rewritten; rung-0 identity provenance
    marked half-resolved with the V-3 convention gap named on R-14. [QA
    V-2, V-3]
25. Salvage implementation bound to the seam-aware fence-strip finding.
    [QA validation plan]
26. Rejected-findings register added (section 13); this changelog added
    (section 14). [COORD]
27. Escalation population restored to 285 + 654 = 939, the postmortem
    baseline, superseding item 12's harmonization at 284 (an int-floor
    artifact; the specs crossed while harmonizing). M-P5's harness
    recompute supersedes both counts when it runs. Moves: 2c 30% entry
    $14.2 to $14.4 (57 to 58 calls), 2c worst case $46.6 to $46.7, 2b
    batch-5 $25.0 to $25.1 ($75.0 to $75.2 at $15/$75), batch-15 $59.3 to
    $59.4 at $15/$75. [QA final verdict E-1]
28. Rung prefixes updated to the Prompt Engineer's re-measurement after the
    l/need prompt additions: 4,364 / 2,808 / 3,072 / 2,745, superseding
    item 10's values. Sub-dollar effect, folded into the same regeneration.
    Combined with item 27: batch-5 central $71 to $72, ladder central about
    $68 to about $69, full-run central about $82 to about $83; the $61 to
    $97 band, the G2 checks, the cap-21 arithmetic, all call counts, and
    the sensitivity endpoints ($64/$84) are unchanged. [QA final verdict
    E-2]
