# Implementation Delta: the output contract, the learning channel, and the deterministic gates

Author: Prompt and Context Engineer persona. Date: 2026-08-26.
Status: implementation delta against PROMPT-SPEC.md revision 2. This is not a
spec revision. Every item here is executable against the current code without
further design decisions, or it names the owner of the decision it depends on.

**Code state this delta reconciles against, pinned.** Commit `a98479b` on
`deterministic-gate-hardening`, PLUS the uncommitted change set present in the
working tree while this was written (2026-08-26, 15:37 to 15:55 PDT, growing as
I worked): `compact.py` (new), and modifications to `engine.py`, `ladder.py`,
`prompts.py`, `pipeline.py`, `determine.py`, `workorder.py`, `runreport.py`,
`scripts/enrichment-audit.py`, plus the probe note
`data/f9-cache-probe-2026-08-26.md`. I did not write any of it; it is another
session's in-flight implementation, and it lands a large part of my revision-2
spec. I captured it at two points (`git diff HEAD`, snapshots in my session
scratchpad; second snapshot sha `972dad58`). Because that set is uncommitted
and moving, in-flight code is referenced by function name first and line number
second, and every requirement below is stated so it is checkable whatever the
final line numbers are. Committed code is referenced by exact line against
`a98479b`.

**Measurement basis.** Every number is re-derived from named artifacts or
labeled an estimate with its basis. The substrate is the v2 full build
(`/Volumes/Studio/dev/.demo-corpus/_out/unamentis-ios/runs/full-build/`:
ledger.jsonl 161 rows, report.json, adjudication.json), the run's 159 CLI
transcripts (all located under
`~/.claude/projects/-Volumes-Studio-dev-solution-explorer/`, joined by the
ledger's `session_id`), and the subject store
(`_out/unamentis-ios/index.db`: 626 contract-state rows, 168 component and 458
relationship product rows). Token counts are tiktoken `o200k_base` unless
marked "billed". The output-side scale is fitted fresh in this delta (section
0.1). Analysis scripts (`measure_v2_fields.py`, `measure_v2_channels.py`,
`measure_v2_facts.py`, `measure_v2_final.py`, `measure_v2_claims.py`) ran in
the session scratchpad; each figure below names what it was computed from so
anyone can re-derive it. Zero model calls were made.

---

## 0. The v2 measurements this delta stands on

### 0.1 The output-side scale, fitted on all 73 ladder calls

Per rung, billed `tokens_out` regressed on o200k of the delivered response
text (transcripts joined by session id):

| rung | n | slope | intercept | max residual |
|---|---|---|---|---|
| 2a (sonnet) | 19 | 1.737 | -800 | one small-call outlier; mean ratio 1.671 |
| 2b (opus) | 30 | 1.729 | -191 | 12.9% |
| 2c (fable) | 24 | 1.764 | -345 | 14.8% |

Reading: at `--effort low` on the current transport, **billed output is 1.73 x
o200k of the delivered text, with a per-call fixed term statistically
indistinguishable from zero**. The 1.73 bundles the Claude-versus-o200k
tokenizer ratio (my prompt-side fit was 1.583) with thinking, so thinking at
low is roughly 9% of output, not a large fixed block. This supersedes the
adjudicated old-schema fixed term of 1,369 (bounds 500 to 2,800) for
projection purposes: that fit was 4 replayed probes on the old transport; this
is 73 real calls on the current one. The G2 dispersion default 1.90 stands
until the Level 1 recalibration; the 19-call 2a sample here is usable input
for it.

### 0.2 What one delivered block actually contains (per-field, o200k)

All 168 component and 458 relationship blocks of the v2 2a responses,
decomposed field by field:

**Component, mean 639.5 per block:**

| field group | mean | share | fate under the compact contract |
|---|---|---|---|
| product fields (help_text, description, data_handled, criticality, roles, assessments, flows) | 182.4 | 28.5% | kept byte-for-byte |
| q claims (purpose, mechanism, place, next_step) | 102.6 | 16.0% | kept |
| q evidence arrays | 153.1 | 23.9% | menu references (7.9 citations/block mean) |
| identity.* answers | 114.2 | 17.9% | cut; exception flag only |
| substitution_check sentence | 30.6 | 4.8% | `"generic": true` flag |
| parser_first | 20.8 | 3.3% | `pf` capped at 2, omit-empty |
| status fields | 16.4 | 2.6% | cut; absence means answered |
| self_state + confusion | 14.9 | 2.3% | cut; confusion exception-only |
| reasons | 4.5 | 0.7% | kept (exception-only already) |

**Relationship, mean 159.0 per block:** product 27.4, flow/why claims 41.5,
evidence 68.2 (43% of the block), status/reason 7.5, self_state/confusion
9.3, parser_first 5.1.

### 0.3 The dead channels, quantified

- **Identity restatement**: 447 identity answers were generated; of the 350
  where the parser holds a concrete value, **350 of 350 restate it and 0
  disagree** (containment test against the prompt's own fact blocks). Since
  commit `a23bc4e`, `_parser_settles` (contract.py:305) means none of them is
  even validated. 114.2 o200k per component, about 8.7% of 2a output, bought
  literally zero information in this run.
- **Escalation re-emission**: opus delivered 115,537 o200k over 147 items, of
  which the failed questions' repairs are **3,740 (3.2%)**. Fable delivered
  96,661 over 120 items; repairs 3,334 plus 2,177 of gap prose (5.7%).
  Combined, **95.6% of escalated-rung output re-emits established work**.
  Billed, that is 451,768 tokens, 40% of the entire run's output.
- **Status constants**: of 1,119 answers, 1,048 are `"answered"`, 58
  uncertain, 13 dropped.
- **Evidence kind mix** (2,127 stored citations): symbol 731, **fact 495
  (23.3%)**, file 483, edge 418, doc and manifest 0. Nearly a quarter of all
  citations are the fact kind; section 2.3 is why that matters.

### 0.4 The compact projection, measured on this subject's real content

Every v2 block mechanically transformed into the compact/v1 wire (the
in-flight `compact.py` rules, plus the fact shorthand of section 2.3;
citations remapped into the prompts' own file menus where they resolve, the
escape object elsewhere, so these figures are conservative):

| | mean | p95 | max |
|---|---|---|---|
| component, o200k tokens | 397.7 | 562 | 752 |
| component, JSON bytes | 1,796 | 2,498 | 3,477 |
| relationship, o200k | 80.2 | 105 | 117 |
| relationship, bytes | 362 | 463 | 578 |

Applying the 0.1 fits: **2a projected at 286 billed output tokens per target**
(179,220 for 626 targets), against the measured 610. With repairs-only
escalation (repairs + gaps + envelope, about 20,400 billed), **the ladder
lands at about 319 billed output tokens per unique target against the
measured 1,332: a 0.24 ratio**. Run-level output falls from 1,123,757 to
about 399,000 (0.355), with the p3 verify passes, at 127,775 billed output,
untouched by this delta and now its largest remaining output block.

### 0.5 Retention and the learning population

- Retained product in the store: component rows mean 248 o200k, relationship
  rows 54; total 66,264 over 626 targets, **106 per target**.
- Contract-state rows additionally retain 320 per target (answers, failed
  lists, history). These are consumed (adjudication digests, escalation
  items, the exit report), so "discarded" in the postmortem's 94% means
  overwritten and re-emitted, not unread.
- 168 items climbed. Escalation/v1 items as the in-flight `_escalation_item`
  builds them, measured with real fact blocks: component mean 702 o200k (p95
  1,144, max 1,241), relationship mean 389 (p95 601). Facts are the largest
  part (component fact blocks mean 213, p95 566; relationship 129).
- Failed questions per climbed item: p50 1, p95 2, max 3.
- Honest gaps: 102 in the census (88 in the store; the divergence is a
  defect, section 6 P6), 145 gap questions, `why` mean 31 o200k, 12 of 145
  boilerplate.
- Trigger classes (report.json `escalation_economics.by_trigger`, mapping at
  runreport.py:176): context (E2+E4) 93 items, reasoning (E1+E5) 95. The
  commission's "roughly half were context failures" reproduces exactly.
- Resolution: of 147 items opus received, census says 27 grounded at opus
  (18.4%). Fable grounded 18 of 120 and declared the rest.

### 0.6 Where the dollars actually went

v2's $85.64 splits into **output-side $28.58** and **write-side $54.39** at
the ledger-fit prices (sonnet $3/$15, opus $5/$25, fable $10/$50, writes at
2x). Output is dominated by the escalation rungs (fable $10.24, opus $6.17,
2a $5.73); the write side by the meta-phases shipping corpora (p3 inputs
1.36M, p5 687k, work orders 394k). This delta's schema and escalation changes
attack the output side and the ladder's write side; the F-9 cache result
(section 2.6) attacks the write side generally.

---

## 1. What changed since revision 2

### 1.1 Landed and committed (the repair effort, `30c4a5c`..`a98479b`)

From my spec: the effort pin as a first-class argv flag (engine.py:209-213,
no code path omits it), envelope capture (`stop_reason`, `num_turns` on the
success path), the cache-write split in the ledger, the fact-block byte
budget (prompts.py:140-142, 12,000 chars; my spec's 20k-scaled budget is
superseded by this stricter char budget, fine), batched verify passes, the
ladder's corrective parse retry (ladder.py:501-517 at `a98479b`), and, beyond
my spec, the `fact` evidence kind with its `CITABLE_FACTS` allow-list
(evidence.py:55-64), the validator wired to the same fact blocks the prompt
shows (ladder.py:349-357), `_parser_settles` (contract.py:305-321), and the
adjudicator prompt taught about fact citations (`f766208`, prompts.py, the
spot-check contract). Section 5 shows that last one is only half landed.

### 1.2 Landing in-flight, uncommitted, while this was written

The working tree implements most of the schema diet and several orchestration
items: the compact/v1 wire format and deterministic expansion (`compact.py`:
`normalize_compact_response`, `coverage_issues`, `response_budget_bytes`,
`compact_json_schema`), compact prompt builders with a byte-stable cached
prefix (`prompts.py`: `_COMPACT_COMPONENT_PREFIX`,
`_COMPACT_RELATIONSHIP_PREFIX`, `_COMPACT_ESCALATION_PREFIX`,
`split_cached_prompt`), the 2a split into per-partition component and
relationship calls with per-call delivered-output budgets (`ladder.py`
`_rung_2a`), escalation/v1 handoff items (`_escalation_item` now emits
`established` / `failed` / `todo` / `lacked` / `need`), `--append-system-prompt-file`
plus `--json-schema` plus `--max-turns 1` on marked calls (`engine.py`),
ledger fields `prefix_hash` / `response_bytes` / `output_budget_ok`
(`pipeline.py`), determination digests (`determine.py`: `_census_digest`,
`_adjudication_digest`, `_synthesis_digest`), work orders moved to the
compact escalation shape (`workorder.py`), and audit gates
(`scripts/enrichment-audit.py`). The F-9 cache probe ran (11 calls, $0.42)
and settled the append-file question favorably, with one required flag
(section 2.6).

This delta therefore does two jobs: it pins the numbers those mechanisms must
hit, with the measured basis the in-flight code does not yet carry, and it
names the gaps in the in-flight set that would forfeit measured quality or
efficiency if they ship as-is (sections 2.3, 4, 5, 6, 7).

### 1.3 Stale in my revision 2, superseded here

- **The per-call fixed output term (adjudicated 1,369)**: superseded by the
  n=73 fit of section 0.1 (fixed about 0, slope 1.73). The G2 dispersion
  1.90 stands.
- **Old-schema block baselines (1,770 / 437 at xhigh)**: superseded by the
  measured low-effort baseline on this subject: 639.5 / 159 o200k delivered
  (about 1,106 / 275 billed at the 0.1 slope).
- **The `corrections` array on 2b entries (spec sections 4, 6.7)**:
  withdrawn. The in-flight design corrects an established answer by emitting
  the corrected field directly; `merge_payloads` (ladder.py:129-145) takes
  the correction and keeps everything else. The array's only claimed consumer
  was adjudication visibility, and nothing reads the `why`. Under the
  commission's rule, anything without a consumer is cut. Trade recorded in
  section 8 row 8.
- **Separate 2b and 2c prompt prefixes (spec sections 4, 5)**: merged into
  one repair prefix with a terminal addendum (section 4.2). One text, one
  vocabulary, three users (2b, 2c, the same-tier augmented retry). Caches are
  model-scoped, so sharing the text costs nothing and removes a
  reconciliation surface.
- **M-P4 (`--json-schema` evaluation)**: partially superseded. The in-flight
  code ships the flag on compact calls. What P-4 was to answer and did not
  is narrowed to one open question, the cache interaction (section 2.5).
- **F-9 / the M-P1 cache gate**: resolved by the probe
  (`data/f9-cache-probe-2026-08-26.md`). Requirement moves from "prove the
  mechanism" to "ship the flag and pin the predicate" (sections 2.6, 6 P9).
- **The 61/100 call plan (cap 21 / batch 80)**: the in-flight code splits
  per partition by target kind instead. On this subject the worst component
  call carries 28 components and passes every ceiling check (section 2.4),
  but 28 exceeds the binding cap-21 rule that both specs adopted for the
  general case. The rule stands; the split must chunk (section 7, ladder
  item 2).

### 1.4 Stands unchanged

Quality-first retention of every product field; evidence by reference with
the full object as escape hatch; implicit defaults; the relationship
edge-default with its F-6 mitigations and the M-P5 fabrication count; the
`l`/`need` self-report bound to uncertainty with coordinator validation of
`need`; escalation/v1 as the input format and the array envelope as the
output format; menu stability as a hard constraint on any truncation; the
blind spot-check protocol for human-read quality; effort pinned `low` on
every rung with no rung justified higher; the checked-and-rejected list
(`data_flow_description` versus `flow`, `help_text` versus the contract
prose: both kept, no token in this delta comes from deleting either).

---

## 2. The output contract per rung, final

### 2.1 Field-by-field disposition

The wire format is compact/v1 as implemented in `compact.py`, with the
additions in 2.3. Fate and measured v2 cost of every old-schema field:

**Components** (per-block means from section 0.2):

| old field | disposition | v2 cost | compact cost |
|---|---|---|---|
| all 13 product fields | KEPT, byte-for-byte, same keys | 182.4 | 182.4 |
| `contract.answers.{purpose,mechanism,place,next_step}.claim` | KEPT as `q.<name>.t` | 102.6 | 102.6 |
| `.evidence` arrays | RESTRUCTURED: menu references (`2`, `[2,"Symbol"]`, `[2,120]`, `"E3"`, `["F","field"]`, object escape) | 153.1 | about 25 at 7.9 citations/block |
| `answers.identity.*` | CUT; `id` exception flag only (v2 would have emitted zero flags: 350/350 restate) | 114.2 | 0 |
| `.status` | CUT; absence means answered; exceptions are `"s":"u"` / `"s":"d"` | 16.4 | about 1 |
| `.reason` | KEPT on exceptions as `r` | 4.5 | 4.5 |
| `substitution_check` | RESTRUCTURED: `"generic": true` only on failure | 30.6 | about 1 |
| `parser_first` | RESTRUCTURED: `pf`, max 2 entries, omit-empty | 20.8 | about 6 |
| `self_state` | CUT; `evaluate()` computes the verdict (contract.py:324-441) | 8-ish | 0 |
| `confusion` | KEPT exception-only (null never emitted) | 3.4 null cost | exception only |
| envelope | id-keyed map to array with `"i"`; exact-set checked by `coverage_issues` | | |

Measured compact total: **397.7 o200k mean** (the additive estimate is about
320; the difference is JSON keys, punctuation, gap entries, and the
conservative escape-object fallback where my transform could not resolve a
menu). Reduction 38% of delivered tokens; combined with no re-emission at
escalation, the billed effect is section 0.4's 0.24 ladder ratio.

**Relationships**: `d` and `imp` kept (27.4); `flow`/`why` kept as bare
strings under the edge-default (41.5); evidence arrays cut to the exception
form (68.2 to about 0); statuses and self-state cut. Measured compact total
**80.2 mean** against 159.0.

### 2.2 The three response shapes

Unchanged from my spec in intent, now matching the in-flight wire exactly:

- **Clean pass**: product fields plus `q` with `t` and `e` per question, or a
  bare-string answer for relationship flow/why. Nothing else.
- **Borderline**: the failing question alone carries
  `{"t": bounded claim, "s": "u", "r": why, "l": "fact"|"judgment",
  "need": only with fact}`.
- **Exception flags**: `id` (identity disagreement, with `v`/`e`/`r`),
  `confusion`, `generic: true`, `pf`, and at the terminal rung `gaps`
  (`{q, why}`).

### 2.3 REQUIRED ADDITION: the fact-citation shorthand

The compact wire has no form for the `fact` evidence kind, and the compact
component prompt never mentions it. That kind is **23.3% of all v2 citations**
(495 of 2,127, section 0.3) and exists precisely because count and absence
claims ("6 inbound edges", "no outbound edges") have no file or symbol that
can carry them. Ship compact/v1 without it and every such claim either goes
uncited (E2, the exact escalation driver the fact kind removed) or pays the
full escape object without being told it may.

Specification, three small changes plus one prompt line:

1. `compact.py::_component_evidence` accepts `["F", "<field>"]` and expands
   it to `{"kind": "fact", "component": <this component's id>, "field":
   "<field>"}`. An unknown field expands to the existing `compact-invalid`
   form and fails closed through E2. (`_relationship_evidence` needs no
   change; relationship claims cite the edge by default.)
2. `compact_json_schema` already admits the form structurally (the
   two-element array branch accepts `[string, string]`); no schema change.
3. `build_digest` must carry the fields through to the adjudicator: section 5.
4. `_COMPACT_COMPONENT_PREFIX` gains one line in the EVIDENCE paragraph:
   `["F","inbound_edges"] = this component's own analyzer fact (fields:
   file_count, line_count, inbound_edges, outbound_edges, language,
   framework, port, type, capabilities, data_entities, external_services,
   action_count, ai_surface, has_testing_data, testing). Use it for any claim
   about a count, an absence, or a detected attribute.` The list is
   `CITABLE_FACTS` verbatim and section 5's conformance test pins that.

### 2.4 Delivered-output budgets, with the measured basis they lacked

The in-flight budgets moved (1,600 chars to 3,600 bytes per component, 560 to
720 per relationship) while I measured. The measured distribution (section
0.4) is the justification the numbers need, and the tolerance they must keep:

- `COMPONENT_RESPONSE_BYTES = 3_600`: measured max on real v2-quality content
  is 3,477 bytes; p95 2,498; mean 1,796. The budget covers the observed
  maximum with 3.5% headroom and 2.0x the mean. **The earlier 1,600 value
  would have rejected 106 of 168 real components**; any future tightening
  below 3,600 must re-run the transform harness first.
- `RELATIONSHIP_RESPONSE_BYTES = 720`: measured max 578, p95 463. Sound.
- Per-call pooling (`response_budget_bytes` x 1.08): worst component call on
  this subject (28 components) predicts 50,288 bytes of delivered JSON
  against a 109,417-byte budget, and about 19.4k billed output tokens against
  the 64k ceiling, 58% of it at the 1.90 dispersion factor. Passes.
- **The cap-21 rule still binds.** The per-partition split does not chunk; a
  subject with a 40-component partition would breach the G2 arithmetic both
  specs adopted. Component calls chunk at 21 until Level 1 recalibrates
  `dispersion_max(low)` (the 19-call 2a sample of this run is admissible
  input). Relationship calls chunk at 80. Section 7, ladder item 2.

Schema length limits inside `compact_json_schema`, checked against v2
content: `help_text` maxLength 1,600 against measured p99 806, max 890:
sound. `description` 240 against p99 133: sound. **Raise `t` from 500 to 600
and `r` from 320 to 560**: measured claim max is 612 chars with 3 of 1,569
over 500, and reason max 526; a structured-output rejection forces a full
regeneration to save 100 characters, which is a bad trade. (`need` to 560 for
symmetry.)

### 2.5 Structural enforcement status

`--json-schema` is now wired on every marked call together with
`--max-turns 1`. What remains unmeasured, kept from M-P4 as a single 3-call
probe before the next full build: whether passing `--json-schema` changes the
billed prompt side (schema-as-input) and whether it disturbs the cached
system-prefix entry the F-9 probe validated (the probe ran without the
flag). If it invalidates the cache, the fix is to fold the flag in before
measuring the warm call, not to drop enforcement. Salvage demotes to a
regression test once the probe passes; the audit's P7 predicate (section 6)
enforces that demotion by counting salvage engagements, expected zero.

### 2.6 Context shape and caching: settled by the F-9 probe

The probe (`data/f9-cache-probe-2026-08-26.md`) answers my spec's
load-bearing unknown: appended-file content joins the cached system entry
**only with `--exclude-dynamic-system-prompt-sections`**; without it the
prefix re-bills at 2x on every call and is never read. Numbers now pinned
for the ledger predicate (section 6 P9): base cached block 3,289; excluded
steady state reads base 8,162 plus the appended prefix; steady-state write
floor 762 to 778 plus the call's own user message; writes are 1h TTL;
caches are model-scoped. Requirement: the engine's marked-call argv carries
the exclude flag (in-flight `engine.py` gained append-file plumbing; verify
the exclude flag is on the argv before the next run, section 7 engine item).
My spec's `prefix_exposure_if_MP1_gate_fails_usd` contingency closes on the
favorable side.

The probe's addendum measured headless session-resume economics (reads the
whole prior context at 0.1x). That is an orchestration option for the
verify and determination phases, not a ladder prompt matter; noted here so
nobody re-measures it.

---

## 3. The learning and exit channel, specified

Principle applied throughout: **every element has a named consumer; anything
without one is cut.** The channel's job is (a) escalation handoffs that carry
exactly what failed, (b) per-run learning about what the cheaper rung lacked,
(c) the exit report's transferable-to-deterministic findings.

### 3.1 What a failed or uncertain answer emits (output side)

| element | form and cap | consumers |
|---|---|---|
| bounded claim `t` | string, schema max 600 chars | 2b item `attempt_claim`; reader never sees it |
| `s` | `"u"` or `"d"`, 1 token | `evaluate()` (E1/E2) |
| `r` | one line, schema max 560 chars | `FailedQuestion.note`; escalation item; determination exceptions digest (capped 240 there); REPORT.md gap tables |
| `l` | `"fact"` / `"judgment"` | coordinator routing (section 4.4); `by_trigger` class in the exit report (section 3.4) |
| `need` | concrete missing fact, max 560 chars | rung-0 augmentation lookup; weekly review when unresolvable |

Budget per uncertain answer: about 170 o200k worst case. v2 population: 58
uncertain answers; the whole channel cost under 10k o200k per run.

### 3.2 What the other exception channels emit

| element | cap | consumers |
|---|---|---|
| `pf` entries | 2 x 200 chars | `LadderOutcome.parser_findings`; REPORT.md parser-findings section and `deterministic_opportunities`; `lessons` |
| `confusion` | one sentence | E5 trigger; escalation item `declared_confusion`; REPORT.md |
| `generic: true` | 1 token | E4 trigger; adjudication substitution comparison |
| `id` flag | `{v, e, r}`, about 80 o200k | contract answers record; **exit report identity-flags section, which must be added** (section 7, runreport item), else this channel has no reader and the crown-jewel catches (the UIKit/SwiftUI flag, the misnamed component) surface only by luck |
| `gaps` | `{q, why}`, why max 320 chars, reader-facing | product row `honest_gaps` (the map); REPORT.md gaps section; determination exceptions |

Honest-gap quality bar, now a predicate (section 6 P11): the `why` is
non-empty, is not the E1 boilerplate, and explains what defeated the
attempts. v2 measured 12 boilerplate of 145; the gate holds that at or under
10%.

### 3.3 The escalation handoff (input side), with its budget

Escalation/v1 exactly as the in-flight `_escalation_item` builds it, plus
three caps that the v2 measurement shows are needed:

- `established`: settled answers as **claims plus compact citation references,
  never expanded evidence objects**. The in-flight code copies expanded
  evidence (`evidence: value.get("evidence")`); expanded objects are the
  transcription this architecture removes, and the receiving rung only needs
  to see that the claim is grounded, not re-read the citation. Measured
  effect: established mean 267 o200k as built, about 150 with references.
- `failed[]` entries: `attempt_claim` capped at 300 chars, `note` at 240
  (matching the determination digest's cap), `citations_tried` at 2 in
  compact form with the validator's verdict string.
- `facts`: the component's byte-capped block, unmodified (mean 213, p95 566).

Per-item budgets, enforced at item build time, derived from the measured
distribution (section 0.5): **component item at or under 1,300 o200k (p95
measured 1,144), relationship at or under 700 (p95 601)**; target means after
the established-reference diet about 550 and 330. An item over budget is
truncated by the stated caps, never by dropping `failed` or `todo`.

### 3.4 What the exit report consumes, and the per-run learning ledger

REPORT.md (runreport.py) consumes: the census with trigger counts;
`escalation_economics` (climbed, cost per climb, `by_trigger` with the
context/reasoning class, `deterministic_opportunities` from pf entries);
`parser_findings`; `lessons`; the gaps list with reasons; the adjudication
digests. Two changes:

1. **The trigger-class map becomes recorded, not guessed.** runreport.py:176
   classifies by trigger (`E2/E3/E4` context, `E1/E5` reasoning). With
   `lacked` now recorded on the wire, the class comes from the item's own
   `lacked` value (`fact`/`validator-scope` are context; `judgment`/
   `capability` reasoning), falling back to the trigger heuristic only where
   `lacked` is absent. The report labels which basis each bucket used.
2. **Identity flags get their section** (3.2 above).

Channel total, measured on the v2 population: handoff items about 92k o200k
per run plus exception output under 15k, about **1.55x the retained product
(66k)**. The commission's bound of roughly double the retained data holds
with margin; the pinned ceiling is **2.0x retained product per run**,
checkable from the ledger and store (section 6 P12).

---

## 4. Escalation as patches

### 4.1 What is already right in-flight

`_escalation_item` emits `established` / `failed` / `todo` / `lacked` /
`need`; the repair prompt demands only TODO answers; `merge_payloads` and
`_merge_contract_blocks` make a repairs-only response safe (additive, never
lossy); the response budget prices a repair batch at repairs, not
re-emission. The measured stake: 95.6% of v2's escalated output was
re-emission (section 0.3), worth about $15.7 of the run's $28.58 output side
(95.6% of the escalated rungs' $16.41).

### 4.2 The repair prompt, final text

One prefix for every repair consumer (2b, the terminal rung with its
addendum, the same-tier augmented retry, and work orders with their
assignment header). It replaces `_COMPACT_ESCALATION_PREFIX`, which currently
lacks the trigger vocabulary, the citation grammar, and the E4/E5/identity
instructions:

```
ESCALATION REPAIR. A cheaper tier already worked every item below. A
mechanical validator rejected specific answers; each item's "failed" list
names which question failed, with a trigger code, the attempted claim, and
the citations that did not check out. You have NO tools: everything you may
use is already in this prompt.

Repair ONLY what "todo" names. Work that passed is finished; re-emitting or
rewording it spends the run's budget on something it already has.

Trigger codes: E1 no usable answer was produced. E2 the evidence did not
check out, or the tier was uncertain. E3 the claim contradicts a
deterministic fact. E4 the answer would fit a sibling equally well. E5 the
tier declared confusion.

Return ONLY one JSON object, no prose, no fences:
{"components":[{"i":"<id>","q":{"<failed question>":{"t":"<repaired claim>",
"e":[<citation>]}}}],
 "relationships":[{"k":"<key>","flow":...,"why":...}]}

Rules:
- Every question in an item's "todo" gets exactly one entry: a repaired claim
  with a citation you can make from THIS item's material, or an honest
  {"t":"best bounded claim","s":"u","r":"why this cannot be grounded at this
  tier"}. On "s":"u" only, add "l":"fact" with "need":"<the concrete missing
  fact: a file, a config, a build step>" when a fact absent from this prompt
  would settle it, otherwise "l":"judgment".
- Citations use the item's menus exactly as the bulk pass does: 2 = file
  index 2; [2,"Symbol"] = that symbol in that file; [2,120] = that line;
  "E3" = edge index 3; ["F","inbound_edges"] = this item's own analyzer
  fact; a full evidence object is the escape hatch. Every citation is
  checked mechanically.
- "established" answers are settled. Do not re-emit them. If one is actually
  WRONG, emit the corrected field or answer directly; the merge takes the
  correction and keeps everything else. Corrections are rare and each one
  needs evidence.
- E3: correct the claim, or flag the detected value via
  "id":{"<field>":{"v":<value or null>,"e":[<citation>],"r":"<one line>"}}.
- E4: make the answer specific to THIS item: name the fact that could not be
  true of a sibling. If you cannot, say so with "s":"u".
- E5: the declared confusion is stated on the item. Resolve it from the
  facts if they allow; otherwise restate it more precisely as
  "confusion":"<one sentence>".
```

Terminal addendum (2c only), replacing the in-flight one-liner:

```
This is the LAST rung; there is no rung after you and no loop. A TODO you
cannot ground becomes an honest gap:
"gaps":[{"q":"<question>","why":"<one sentence for the READER of the map:
what specifically defeated the attempts>"}].
A gap declared honestly is a correct outcome. A gap papered over with a
plausible sentence is a lie the map tells with confidence. Never write "could
not be grounded" as the why; say what was missing or contradictory.
```

Both texts follow the writing-style rule: no em or en dashes anywhere in any
prompt this project ships.

### 4.3 The repair response contract

Array envelope, `q`-only entries for the named questions, the exception
channels (`id`, `confusion`, `gaps`) as above, nothing else. Absorption is
the existing `normalize_compact_response` to canonical shape, then
`_absorb`; `coverage_issues` checks the id set of the response against the
batch. A repair entry for an item not in the batch is dropped by the
normalizer's allow-list (already implemented). The delivered budget for a
repair call prices only repairs:
`RESPONSE_ENVELOPE_BYTES + 600 x failed_questions + 400 x gap-eligible
items` is the right shape; until the Architect sets it, the in-flight
per-item budget (3,600/720 per item) is safe but slack by about 5x for
repairs, and the billed gate P5 (section 6) covers the difference.

### 4.4 The trigger-class routing, and what I own of it

The v2 measurement (section 0.5) confirms the commission's premise: half the
climbs are context failures. Escalating those to a bigger model bought a
18.4% resolution rate at opus. The routing itself is the Orchestration
Architect's; this delta owns the two prompts and the response contract, and
flags every routing assumption:

**The same-tier augmented retry** (context-class items): same model that
failed (sonnet), same repair prefix as 4.2 (model-scoped caches make sharing
free), items carrying two extra fields:

```
"augmented": ["<facts added since the failed attempt, named: e.g. 'files
menu extended with Config/AudioSession.swift (the need you stated)'>"],
"attempt": {"<question>": "<the failed claim>"}
```

The response contract is identical to 4.3. The coordinator resolves `need`
against the store before routing (my spec's F-5 constraint, unchanged):
resolvable need routes here once, one loop maximum; unresolvable reclassifies
to judgment and climbs.

**Routing assumptions flagged for the Orchestration delta to confirm or
correct:**

- A1: context-class items (`l: "fact"` with resolvable need, or
  coordinator-assigned `validator-scope`) take the same-tier augmented retry
  once, then climb honestly if still failing.
- A2: judgment and capability classes go to 2b (opus, batch 5 default,
  batch 15 still gated on M-2 parity).
- A3: the recorded `lacked` supersedes the runreport trigger heuristic
  wherever present (section 3.4).
- A4: work orders keep the repair wire (`workorder.py` already does this
  in-flight; its `todo` semantics differ and its budget is per component).
- A5: the per-partition split stays, with cap-21 chunking added (2.4).
- A6: the determination and verify prompt diets are Orchestration-owned; the
  digests landing in-flight (`determine.py`) are consistent with this delta's
  caps (exceptions carry failed lists with 240-char notes) and nothing in
  this document depends on their final shape.

---

## 5. Three-role vocabulary reconciliation

The $85 lesson: generator, validator, and adjudicator each hold a copy of the
evidence vocabulary, and the copies drifted. The fix is one source of truth
and a build-failing conformance check.

### 5.1 Where the vocabulary lives and who reads what

| artifact | role | reads |
|---|---|---|
| `evidence.py::EVIDENCE_KINDS`, `CITABLE_FACTS` | source of truth | validator checks every kind (`check`, evidence.py:182-198) |
| `compact.py` citation grammar (`_component_evidence`, `_relationship_evidence`) | wire codec | expands wire forms into EVIDENCE_KINDS objects; out-of-range fails closed |
| `prompts.py` compact prefixes | generator | teach the wire forms (and, after 2.3, the fact shorthand with the CITABLE_FACTS list verbatim) |
| `prompts.py::build_grounding_spotcheck_prompt` | adjudicator | describes every kind's meaning, including `fact` since `f766208` |
| `adjudicate.py::build_digest` | adjudicator's eyes | forwards citations into the spot-check |
| `compact.py::compact_json_schema` | decoder constraint | admits every wire form |

### 5.2 The drift that is live right now

`build_digest` (adjudicate.py:216-243) filters evidence keys to `kind`,
`path`, `line`, `symbol`, `source`, `target`, `edge_type`. A fact citation
`{"kind": "fact", "component": ..., "field": ...}` survives as
`{"kind": "fact"}`: no component, no field, no value. Commit `f766208`
taught the judge that a fact citation "names a real field of the analyzer's
own output with the value shown", and the digest shows it neither the field
nor the value. The committed fix is inert for the exact citation kind it
describes, which is the three-role failure repeating within one commit of
the postmortem that named it. This is also why the fix being "landed but
unmeasured" must not be treated as landed: as wired, remeasuring the 53.2%
disagreement rate would test nothing.

Fix (adjudicate.py, one function): extend the key filter with `component`
and `field`, and attach the analyzer's value at digest build time by looking
it up from the same fact blocks the validator holds (the validator's
`_check_fact` already returns it in `detail`; the digest builder can call
`validator.check(item)` and merge `detail["value"]`). The digest entry a
fact citation produces is then
`{"kind": "fact", "component": ..., "field": "inbound_edges", "value": 6}`,
which is what the prompt promises the judge.

### 5.3 The conformance check, deterministic, fails the build

One test module (proposed `tests/enrich/test_evidence_vocabulary_contract.py`)
with five assertions, all offline, running with the ordinary suite:

- **T1 validator closure**: for every kind in `EVIDENCE_KINDS`, a valid
  fixture citation passes `EvidenceValidator.check` against a fixture store,
  and an invalid one fails with a reason. (Mostly exists; the fixture set
  becomes the enumeration over the vocabulary rather than hand-picked
  cases.)
- **T2 wire round-trip**: every compact wire form (int, `[i,"Sym"]`,
  `[i,line]`, `"E<n>"`, `["F","<field>"]`, escape object) expands via
  `compact.py` to a kind in `EVIDENCE_KINDS` and passes T1 on the fixture;
  every malformed form expands to the fail-closed shape and fails T1 with
  its reason preserved.
- **T3 prompt closure**: string assertions that the compact component prefix
  names every wire form and contains every entry of `CITABLE_FACTS`; that
  the repair prefix names every trigger code in `TRIGGERS`; and that the
  spot-check prompt names every kind in `EVIDENCE_KINDS`. Adding a kind or a
  citable fact without updating a prompt fails the build. String assertions
  are crude and exactly right here: the drift they catch is textual.
- **T4 digest closure**: for every kind, build a grounded fixture answer,
  run `build_digest`, and assert the digest entry retains the kind's payload
  keys (a fact citation retains `field` and `value`; an edge retains
  `source` and `target`). This is the test that would have failed the
  `f766208` build.
- **T5 the wiring regression**: an integration fixture where a component's
  claim cites `["F","inbound_edges"]`, absorbed through
  `normalize_compact_response` and validated with facts attached the way
  `_rung_2a` attaches them (`ctx.facts.component_facts`, ladder.py:355-357),
  asserts the citation validates. This pins the validator-attached-the-wrong-
  dictionary bug (`8df5965`) forever.

The schema (`compact_json_schema`) is covered by T2 plus a `jsonschema`
validation of each wire fixture, so a schema tightening that outlaws a legal
form also fails the build.

---

## 6. Deterministic validation

Predicates a harness evaluates from run artifacts with no judgment call.
P1, P2, P6, P7 are hard fails; the billed-token gates carry stated
tolerances because billed output includes hidden reasoning the transport
does not let us cap (the runreport's own note is correct on this).
`scripts/enrichment-audit.py` is the enforcement point; section 7 lists its
changes, including replacing its in-flight `--target-ratio` default of
0.105, which no achievable run passes while the verify passes alone bill
127,775 output tokens (measured, v2).

| id | predicate | pinned number and tolerance | basis |
|---|---|---|---|
| P1 | every ledger row has `effort == "low"` | exact | ledger field, existing |
| P2 | `output_budget_ok` is never false; delivered bytes per call at or under `1.08 x (512 + 3600C + 720R)` | exact | budgets cover measured max block (3,477 / 578 bytes) with 3.5% / 24% headroom |
| P3 | 2a billed output per target: `sum(tokens_out) / sum(targets)` over rung-2a rows | at or under **380** (central 286) | section 0.4 projection; 1.33x tolerance for cross-subject content variance (help_text p99 806 chars here) and thinking variance (fit residuals 13 to 15%) |
| P4 | ladder billed output per unique census target | at or under **500** (central 319); same-corpus ratio vs a baseline ledger at or under **0.30** (measured-central 0.24) | sections 0.4, 0.6 |
| P5 | escalated-rung billed output per escalated item | at or under **260** (central about 120: repairs p95 2 questions x about 56 o200k each, plus gaps) | section 0.3 repair measurements |
| P6 | census conservation: every planned target appears exactly once per rung (`coverage_issues` empty on every call); census total equals planned unique targets; **store contract-state terminal distribution equals the report census `by_state`** | exact | the v2 store shows 47 stale `escalate` rows and 88 honest gaps against the census's 0 and 102: the terminal re-stamp defect of section 7, ladder item 3 |
| P7 | schema and parse health: every response re-validates offline against `compact_json_schema`; salvage engagements 0; `failures/` empty; `num_turns == 1` on every row | exact | structural enforcement shipped; salvage is a regression test now |
| P8 | vocabulary conformance: T1 to T5 green | build-time | section 5.3 |
| P9 | cache pattern: on every non-warm marked call, `tokens_cached >= 8,162 + prefix_tokens`; `tokens_cache_write <= 1.1 x (778 + 1.583 x o200k(user message))`; exactly one `prefix_hash` per rung per run | probe-pinned constants | F-9 probe rows; 1.583 is the prompt-side fit |
| P10 | identity silence: zero `identity.*` answers in new-run contract rows; every `id` flag carries `v`, `r`, and at least one citation | exact | v2 measured 350/350 restatements carrying zero information |
| P11 | honest-gap quality: every gap `why` non-empty, not the E1 boilerplate string, at or under 320 chars; boilerplate fraction at or under 10% | v2 measured 12 of 145 (8.3%) | section 0.5 |
| P12 | learning-channel bound: handoff items within per-item budgets (component 1,300, relationship 700 o200k); channel total at or under 2.0x retained product tokens | measured 1.55x on the v2 population | section 3.3 |
| P13 | replay preflight, zero cost, before any live call: rebuild every prompt from the store; assert one byte-identical prefix per rung (hash equality); every planned call passes `predicted_mean x 1.90 <= 0.85 x 64,000` with predicted mean = `targets x central block x 1.73`; worst prompt within the context bound | exact | G2 rule, both specs; central blocks from section 0.4 |

P13's harness also runs the compact transform over
`data/replay-corpus.json` and the current store so that any prompt or schema
edit re-derives the central block sizes before a dollar is spent; the five
scratchpad scripts named in the header are the working prototype and should
be productized as `scripts/enrichment-replay-check.py` (read-only, venv
tiktoken, no model calls).

---

## 7. File-by-file implementation notes

Ordered so each step lands and tests alone. Line numbers: committed refs are
against `a98479b`; in-flight refs are by function and may drift.

1. **compact.py: the fact shorthand.** `_component_evidence` gains the
   `["F", field]` branch (expand to the fact object with this component's
   id; unknown field to `compact-invalid`). Raise `compact_json_schema`
   maxLengths: `t` 600, `r` 560, `need` 560 (basis in 2.4). Test: T2/T5
   fixtures. Lands alone.
2. **ladder.py: cap-21 chunking.** In `_rung_2a`, a partition whose
   `answered_component_ids` exceed 21 emits ceil(n/21) component calls;
   relationship calls chunk at 80. Menus are per component, so chunking
   cannot disturb them; the menu-stability constraint (truncation only
   before prompt build) already holds and keeps its QA test. Test: a
   40-component fixture partition plans two calls; byte-stable plan.
3. **ladder.py: terminal re-stamp.** Both terminal paths that mutate a state
   in memory must re-stamp the contract row: the honest-gap conversion
   (ladder.py:763-792 at `a98479b`) writes the product row only via
   `_write_honest_gaps` and returns early when the payload has no gap prose,
   and the unexamined path never re-stamps. Fix: `_finalize` re-stamps every
   state whose terminal differs from its stored row. This closes the
   measured 47-row store/census divergence and makes P6 pass. Test: kill a
   fixture run after 2b, assert store equals census.
4. **prompts.py: prompt text.** Add the fact-citation line to
   `_COMPACT_COMPONENT_PREFIX` (2.3); replace `_COMPACT_ESCALATION_PREFIX`
   and the terminal addendum with section 4.2's text; keep the relationship
   prefix's `d`-versus-`flow` distinctness sentence (it enforces the
   checked-and-rejected list). Re-measure prefix sizes into P13's fixtures.
   Test: T3 string closure.
5. **adjudicate.py: the digest fix.** `build_digest` carries `component`,
   `field`, and the analyzer `value` for fact citations (5.2). Then, and
   only then, schedule the disagreement-rate remeasurement: a zero-cost
   recompute cannot test a judge, so this is the one live measurement this
   delta asks for beyond the probes already named: re-run the grounding
   spot-check on the v2 store's grounded items (25 calls, about $2.60 at
   the v2 ledger's rate) and compare to 53.2% with the same sampler.
   Test: T4.
6. **ladder.py: handoff caps.** `_escalation_item` sends `established`
   evidence as compact references, caps `attempt_claim` at 300 chars and
   `note` at 240, `citations_tried` at 2 (3.3). Test: item-budget unit test
   over the v2 fixture population.
7. **engine.py: the exclude flag.** Marked calls carry
   `--exclude-dynamic-system-prompt-sections` next to
   `--append-system-prompt-file` (2.6), or the prefix cache never hits and
   P9 fails every row. Then the 3-call cache-plus-schema probe (2.5).
   Test: argv assertion, which this module already patterns.
8. **runreport.py: the two consumers.** Identity-flags section (3.2);
   `lacked`-based trigger classes with labeled fallback (3.4). Test: report
   fixture with one id flag and one lacked item.
9. **scripts/enrichment-audit.py: the gates.** Replace the 0.105 default
   with the pinned P3/P4/P5 numbers and the 0.30 ladder ratio; add P6
   census-store conservation (open the store, compare terminal
   distributions); add P9 with the probe constants; keep the in-flight
   compact-budget and duplication checks. Test: v2 run must FAIL P3/P4/P5
   (it is the baseline), a synthetic compact ledger must pass.
10. **contract.py: no change required.** `required_questions` still lists
    identity questions, but `_parser_settles` guards evaluation and the
    compact prompt no longer asks them; the id flag arrives as an
    `identity.*` answer via `compact.py::_component_entry` and is preserved
    in the record. Removing the identity entries from `COMPONENT_QUESTIONS`
    is a cosmetic cleanup that touches the census vocabulary and is not
    worth the churn now.

Items 1 to 4 are independent of the Orchestration delta. Items 5 to 9 touch
files that delta is also moving; land them behind it, in its tree, in this
order.

## 8. Quality trades register

Every cut, its expected quality effect, and the measurement that detects
regression. "None" is a claim and each such claim names its test.

| # | change | expected quality effect | detected by |
|---|---|---|---|
| 1 | evidence by menu reference | none: the validator expands references to the same objects and runs the same checks; the adjudicator sees resolved citations | T2/T5 round-trip; menu-stability test; M-P1 pilot compliance count |
| 2 | identity emission cut to exception flags | positive: v2's 350 restatements carried zero information and were never validated; a flag is actionable | P10; the id-flag exit-report section (a channel nobody reads is a channel that dies) |
| 3 | statuses, self_state, null confusion, empty pf omitted | none: `evaluate()` recomputes the verdict from what is present | recompute-harness parity on the v2 corpus (V-5, zero cost) |
| 4 | substitution sentence to `generic` flag | risk: the forced generation of the distinguishing fact may be part of what makes the self-test bite; v2 self-reported E4 only twice while the independent check failed 1 of 4 | M-P6 A/B stands; meanwhile P3's substitution spot-check is the real detector and its rate is a run metric |
| 5 | relationship edge-default (no citation on supported claims) | quality-affecting, unchanged from spec F-6: a fabricated claim over a real edge passes the mechanical check silently | M-P5 fabrication count on the recompute harness ($0); P3 sufficiency now receives the edge evidence; prepared guard: mandatory citation when `imp` is `primary` |
| 6 | repairs-only escalation | none on grounded content: the merge is additive (merge_payloads, ladder.py:129-145) | V-4 merge-property test; M-2 parity as defined in ORCHESTRATION-SPEC 3.3 |
| 7 | delivered-byte budgets | risk: a budget below real content silently converts good calls into E1s; the earlier 1,600 value would have rejected 106 of 168 real components | budgets pinned at measured max plus headroom (2.4); P2 counts violations, expected zero; any tightening re-runs the transform harness first |
| 8 | `corrections` array cut in favor of direct field re-emission | minor negative: the reason a correction happened is no longer recorded anywhere | accepted and stated; if adjudication ever needs it, the repair prompt line "each correction needs evidence" makes the citation the record |
| 9 | one shared repair prefix across 2b/2c/augmented retry | none: same vocabulary, terminal behavior added by addendum only | T3 closure; blind spot-check on the first pilot's repairs |
| 10 | terse audit claims (`one tight claim` framing) | none for readers: product prose untouched byte-for-byte; audit claims may shorten | blind spot-check protocol (VALIDATION-PLAN section 9) on pilot blocks; claim-length telemetry against the v2 distribution (mean 110 chars) |

Not traded anywhere: `help_text`, `description`, `data_handled`,
criticality with its edge counts, the four tours, honest gaps that explain
themselves, and the parser-catching channels (`pf`, `id`, `confusion`),
which this delta gives caps, budgets, and for the first time in two cases,
named readers.
