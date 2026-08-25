# Prompt Spec: what every call says, the shape it answers in, and what it caches

Author: Prompt and Context Engineer persona. Date: 2026-08-25.
Status: revision 2 (Phase 2 step 2), incorporating the QA adjudication
(`data/qa-adjudication.json`, binding), the Architect's review findings F-1
to F-10 (`reviews/ARCHITECT-ON-PROMPT-SPEC.md`), and my own step-1 queued
corrections. Section 16 is the changelog.

Factual foundation: the two 2026-08-25 postmortems, whose measured figures are
taken as baseline; the killed run's 35 recorded transcripts plus the 16
post-run replay probe transcripts; the real VS Code store, re-derived this
session; and current code on branch `deterministic-gate-hardening`, cited by
file and line. Zero live model calls were made. Every number below is measured
from those artifacts or labeled an estimate with its basis. Companion spec:
`ORCHESTRATION-SPEC.md` in this directory; the call plan, batch sizes, and the
escalation protocol are shared with it, and section 14 lists where my
measurements disagree with its parameters.

## 0. Method and measurement basis

Token counts are tiktoken `o200k_base` counts scaled to billed Claude tokens
by a factor fitted against the run's own billed usage. Fitting basis: for all
35 rung-2a sessions of 2026-08-25 whose first-turn usage was recorded, billed
prompt-side tokens (`input_tokens + cache_creation_input_tokens +
cache_read_input_tokens`) were regressed on the o200k count of the exact first
user message. Result: slope **1.5829** (o200k to billed), intercept **10,021**
(the CLI's fixed prompt-side overhead: its system prompt plus per-session
context), maximum residual **1.95%** across the 35 points. A fit-free spot
check agrees: session `c95c2999` billed 39,243 tokens for its 106,558-char
user message, 2.72 chars per billed token. The efficiency postmortem used the
same tokenizer with a live-probe-validated scale; this fit is the offline
re-derivation of that method, and QA item V-7 cross-checks both.

Reproduce with `data/prompt-measure-fit-and-blocks.py` (fit and block
measurements) and `data/prompt-measure-projection.py` (store re-derivation,
prompt builds, schema transformation). Outputs:
`data/prompt-tokenizer-fit.json`, `data/prompt-projection-results.json`,
`data/prompt-cost-model.json`, `data/prompt-aligned-cost-model.json`. The
scripts require `tiktoken` (present in the project venv, absent from the
system python); the per-session points are vendored in
`prompt-tokenizer-fit.json` so every figure stays re-derivable without it.

The QA adjudication cross-checked this fit from the character side and
sustained it: marginal rate 2.886 chars per billed token (equivalently my
o200k slope), per-call fixed prompt-side overhead 12,546 tokens by their fit
against my 10,021 (the two intercepts bracket the observable 8,849-token
constant cache read; the band is 10.0k to 12.5k and the difference is worth
under $0.20 per run at the 0.1x read rate). This spec's models now book the
adjudicated 12,546.

Block-sample rule, stated per F-4 and QA item 10: the 43 + 822 blocks come
from the 26 of 36 in-window sessions whose concatenated text parsed under
fence-strip plus brace-span salvage WITHOUT the seam-aware overlap dedupe
(QA's stronger salvage parses 31). The excluded five are multi-turn overflow
sessions, so the sample under-represents the largest partitions. No
consistent size bias follows (my component mean is 5% above the postmortem's
full-corpus figure, my relationship mean 11% below), and the projection's
conservative column plus M-P1 supersede the sample either way.

Measured foundations this spec stands on:

| fact | value | artifact |
|---|---|---|
| o200k to billed scale / CLI overhead | 1.5829 / 10,021 per call | 35 first-turn transcripts, fit above |
| old-schema block, xhigh (measured here) | component 1,861; relationship 387 | 43 unique component + 822 unique relationship blocks parsed from 26 sessions |
| old-schema block, postmortem baseline | component 1,770; relationship 437 | efficiency postmortem (trusted baseline; my independent parse agrees within 5 to 11%) |
| old-schema block at `--effort low` | component 1,298; relationship 313; envelope 483 to 1,323 per call | the 4 low-effort replay transcripts (25 comp, 135 rel blocks) |
| thinking overhead at `--effort low` | 0 to 1,507 billed tokens per call | same 4 replays: billed output minus scaled delivered text |
| new-schema block (this design), measured by transforming the 43 + 822 real blocks | component 1,263 (-32.2%); relationship 153 (-60.5%) | `data/prompt-projection-results.json`, transform rules in section 6 |
| new-schema block, central at low | component 880; relationship 124 | composition: low-effort old block x measured diet ratio |
| component citations that index the prompt's own lists | 164 of 238 files-menu, 66 of 238 edges, 8 of 238 escape objects | citation mapping over the 43 real blocks against real store facts |
| relationship flow/why citations that restate the prompt | 1,530 of 1,533 (99.8%) | same transform; postmortem measured 100.0% on its larger sample |
| markers at xhigh: parser_first non-empty / confusion non-null / self_state escalate | 100% / 32.6% / 46.5% | the 43 real component blocks |
| baseline 2a input, current prompt, all 173 partitions | 4.056M scaled tokens (mean 23,446; max 217,026) | rebuilt with current `build_contract_partition_prompt` against the re-derived store |
| current prompt's repeated shared prefix | 5,539 scaled tokens per call | same build, split at the COMPONENTS marker |
| adjudicated: per-call fixed prompt-side overhead | 12,546 tokens (band 10.0k to 12.5k) | `data/qa-adjudication.json` dispute 1 |
| adjudicated: tier-B output at low, per comp / per rel / fixed per call | 1,050 / 382 / 1,369 (fixed bounds 500 to 2,800) | `data/qa-adjudication.json` dispute 2, 4-point least squares, max error 5.7% |
| adjudicated: thinking at low, char method | 0 to 455 tokens across the 4 probes | same; sits at the low end of my 0 to 1,507 band |

Open delta carried explicitly: the adjudicated per-relationship coefficient
(382) sits 22% above my block-mean (313); the least-squares coefficient
absorbs per-block key overhead my block counts book separately, and QA notes
my block means underpredict two of the four probes by 10 to 15%. The
conservative column's relationship figure (153, versus 151 from the
adjudicated coefficient times the diet ratio) already covers it; the central
figure (124) may be optimistic by up to that margin. M-P1 closes it.

Prices used for dollar figures: cache write at the 1h rate (2x input, the
rate the run measurably billed), cache read at 0.1x. Sonnet $3/$15 and Fable
$10/$50 are LEDGER-FIT (rows 2 and 1 reprice to 1.6% and 1.8%). **Opus is
dual-priced everywhere in this spec (F-1, mandatory): $5/$25 (current API
sheet) and $15/$75 (legacy sheet). No recorded artifact carries an Opus cost;
the killed run died before rung 2b. The first pilot Opus ledger row (an M-2
row) arbitrates, and per the QA plan that arbitration is a Level 2 sign-off
requirement. No conclusion in this spec rests on a single Opus price.**

## 1. What the prompts must stop paying for

The three classic wastes, located and measured in this pipeline:

1. **Transcription.** Evidence arrays are 31.3% of delivered output and are
   selections from closed sets the prompt supplies: 96.7% of component
   citations are a path from the prompt's own `files[:8]`, 100.0% of
   relationship citations restate `relationship_facts.evidence` or the edge
   itself (efficiency postmortem; re-measured here at 69% + 28% + 3.4% and
   99.8%). A selection from a known list needs an index.
2. **Constants emitted as data.** `"status": "answered"` on 91 to 93% of
   answers, `confusion: null` on 88%, `parser_first: []` on 91%,
   `self_state: "grounded"` on 89% (postmortem), plus identity answers that
   repeat parser-detected values back (266 scaled tokens per component
   measured on the real blocks) and a `substitution_check` sentence (68
   measured; postmortem 69.4) that `_is_substitution_failure` reads as a
   boolean by substring match (`analyzer/enrich/contract.py:550-567`).
3. **The maximal question asked of every call.** Every rung answers the same
   contract mega-schema (`analyzer/enrich/prompts.py:734-806`) and the
   escalation prompt asks the higher rung to re-emit everything including what
   passed (`analyzer/enrich/ladder.py:170-178`, "repeat it back unchanged").

Quality is the constraint: every product field the reader sees is retained
byte-for-byte in this design, and both members of the checked-and-rejected
list stay (section 6.8).

## 2. Rung 2a: the bulk pass, split by target kind

2a runs as two call kinds, matching the Orchestration Architect's split
(ORCHESTRATION-SPEC 3.2 item 1): **2a-C**, component calls of at most 21
components, chunked from the 55 groups (61 calls on VS Code; the cap is set
by the binding dispersion rule, section 9), and **2a-R**, relationship calls
of up to 80 edges carrying component one-liners as context (100 calls).
Model: sonnet, `--effort low`, pinned on the argv (section 11).

Each call kind has a static prefix (identical bytes across all calls of that
kind in a run, delivered via `--append-system-prompt-file`, section 10) and a
per-call user message that carries only the facts.

### 2.1 The 2a-C prompt: static prefix

Measured size including the subject brief: **4,364 scaled tokens**, cached
once, read by 60 subsequent calls (the plan is 61 component calls at the
dispersion-compliant cap of 21, section 9).

```
ENRICHMENT TASK: components.

You are enriching components of a software architecture map. Each component under COMPONENTS carries facts extracted deterministically from the code. Use ONLY those facts. Never invent structure.

Return ONLY one JSON object, no prose, no markdown fences:

{"components": [
  {"i": "<component id>",
   "help_text": "3 to 5 complete sentences: what this component is, what it does, how it connects to its neighbours, why it matters. Written for a reviewer who has never seen the code.",
   "description": "one short sentence, 8 to 15 words: the tree label. Distinct from help_text, never a copy of it.",
   "data_handled": "the specific data types that flow through it, never just 'user data'",
   "criticality": "critical | important | supporting",
   "architectural_role": "an exact value from ROLES, omitted when none genuinely applies",
   "tech_context": "how the language or framework choice fits the architecture (only when the facts show one)",
   "testing_assessment": "1-2 sentences (only when testing facts exist)",
   "testing_maturity": "comprehensive | adequate | minimal | untested (only with testing facts)",
   "port_assessment": "what the port is used for (only when a port is set)",
   "complexity_assessment": "size/complexity note (only >5000 lines or >20 files)",
   "external_services_assessment": "dependency note (only when external_services exist)",
   "actions_summary": "1-2 sentence summary of UI actions (only when actions exist)",
   "key_user_flows": ["2-5 user flows (only when actions exist)"],
   "q": {
     "purpose":   {"t": "<what this is FOR, in the subject's own terms: the job it does for the system>", "e": [<evidence>]},
     "mechanism": {"t": "<HOW it does it: the key types, the central flow>", "e": [<evidence>]},
     "place":     {"t": "<what depends on it, what it depends on, and why that makes sense>", "e": [<evidence>]},
     "next_step": {"t": "<where a reader goes next, and what they learn there>", "e": [<evidence>]}
   }
  }
]}

One entry per id listed under COMPONENTS. Missing any is a failure. Omit every field whose value would be null or empty and every conditional field whose condition does not hold. Do not add fields not shown.

EVIDENCE. "e" holds 1 or 2 citations grounding the claim. Forms:
  2                    the file at index 2 of THIS component's "files" list
  [2, "UserService"]   that file, at the named symbol (used or defined there)
  [2, 120]             that file, at line 120
  "E3"                 the edge at index 3 of THIS component's "edges" list
  {"kind": "file"|"doc"|"manifest", "path": "...", "line": N}   a file not in the list; must be in the analyzed set
Every citation is checked mechanically against the analyzed file set and the graph. A claim you cannot cite is not an answer: write {"t": "...", "s": "u", "r": "<one line: why>"} for uncertain, or {"s": "d", "r": "<why>"} when there is nothing worth saying. An honest "s": "u" costs the run a cheap escalation. An invented citation costs it trust.
On an "s": "u" answer only: when the reason is a fact this prompt does not contain, add "l": "fact" and "need": "<the missing fact, named concretely: a file, a config, a build step>". When the facts are here but the judgment is genuinely hard, add "l": "judgment". Never put "l" or "need" on an answered claim.

DEFAULTS. Emit only exceptions; silence means the default:
- An answer with "t" and "e" is answered. Never write a status field on it.
- IDENTITY. The facts' type, language, framework, and port were detected by the parser. When the code contradicts a detected value, flag it: "id": {"<field>": {"v": <corrected value or null>, "e": [<evidence>], "r": "<one sentence>"}}. When you agree with a detected value, emit nothing for it.
- "confusion": "<one sentence>" only when you cannot reconcile the code with its comments, docs, or naming. Declaring confusion is expected on some subjects and never penalised. It is the most useful thing you can tell the next rung.
- "generic": true only when everything you wrote would fit a sibling component equally well. Saying so plainly is the finding: a description that fits everything describes nothing.
- "pf": ["<one line>"] only for a real parser-first finding: something deterministic processing could have gotten right without a model, and how (a framework inferable from an import the analyzer did not recognise, a relationship visible in a config file nothing parsed, a component type the directory layout implies). At most 2 entries, one line each. Most components yield none; omit the key.

CRITICALITY: critical means the system cannot function without it (sole API entry point, primary data store, auth service; often many inbound edges or an articulation point). important means absence degrades but does not break the system (cache, search, notifications). supporting means developer tooling, utilities, libraries, leaf UI, infrastructure config; often 0 inbound edges.

ROLES: api-gateway, auth-service, data-store, cache-layer, queue-processor, event-bus, orchestrator, worker, proxy, monitoring, logging, scheduler, notification-service, file-storage, search-engine, ml-pipeline, presentation-layer, business-logic, data-access

QUALITY BAR.
Good help_text: "The UserService handles all user lifecycle operations including registration, profile updates, and deletion. It is called by the API Gateway on every authenticated request to validate sessions. It writes to the PostgreSQL database via the UserRepository and publishes user events to the event bus. Without it, no authenticated operation can proceed."
Bad help_text: "This service manages users. It handles CRUD operations."
Good data_handled: "User profile objects, authentication tokens, session metadata, password hashes". Bad: "User data".
The claims in "q" are audit records, not reader prose: one tight sentence each.

Where a component's facts include ai_surface entries (model provider SDKs, gateways, MCP, agent frameworks, local inference, model ids), its AI role is part of what the component IS: say what it talks to or routes and through which mechanism, grounded in those entries. Never invent AI involvement for components without ai_surface facts.

SUBJECT BRIEF (what this system is, who reads the map, and what matters to them; where it names an idiom or a divergence, expect it):
<the P1 brief JSON: identity, audience, what_matters, idiom_warnings, weighting_adjustments>
```

What is gone relative to the current prompt
(`prompts.py:698-806` + `prompts.py:49-126`): the contract mega-block with
its per-question shapes, the parser-first REQUIRED framing (measured to
produce 100% fill), the per-component `REQUIRED_QUESTIONS` arrays
(`prompts.py:809-824`; the four questions are now fixed and identity is a
flag channel, so the arrays carry no information), the evidence-object
grammar as the primary citation form, and `substitution_check` as prose.
What is kept verbatim: every product field, the criticality guidance, the
role vocabulary, the quality calibration, the ai_surface rule, and the brief.

### 2.2 The 2a-C per-call user message

```
COMPONENTS (one response entry per id; each "files" list and "edges" list is that component's citation menu):
<JSON array of component fact blocks>
Return the JSON object now.
```

Fact-block changes, both deterministic:

1. **`edges` menu, new.** The split removes the RELATIONSHIPS section from
   component calls, and 66 of 238 measured component citations were edge
   citations (mostly grounding `place` and `next_step`). Without a visible
   edge list those claims cannot be grounded at all. Each component's facts
   gain `"edges": ["-> <target-id> (<type>)", "<- <source-id> (<type>)", ...]`,
   capped at 8 outbound + 4 inbound, citable as `"E<i>"`. Measured input
   cost: mean 91 scaled tokens per component, 51.9k for all 569 (+$0.31 of
   cache creation per run). Output effect: an edge citation drops from a
   ~25-token object to a 2-token ref.
2. **`REQUIRED_QUESTIONS` removed** from each block (see 2.1).

Dependency: the fact-block byte budget (ORCHESTRATION-SPEC section 1, defect
6; roadmap R-10), now quantified: at 20k scaled per component the budget
removes 196,579 scaled tokens of 2a-C creation (the `cli/src/util` block
alone is 195,525), worth about $1.18 per run at the 2x sonnet write rate;
section 9's input totals book the capped figure.

**Menu-stability constraint on R-10, load-bearing for this whole schema:**
the byte budget must never trim, reorder, or renumber the citation menus
(`files`, `edges`, a relationship's `evidence`) after a prompt is built.
Menus are truncated deterministically BEFORE prompt build, and the validator
resolves indexes against the same stored menus. A budget that touches menus
after build silently converts valid citations into E2s, or worse into wrong
but real ones. QA owns a menu-stability test for this (flagged in my step-1
review, H2).

### 2.3 The 2a-R prompt: static prefix

Measured size including the brief: **2,808 scaled tokens**.

```
ENRICHMENT TASK: relationships.

You are describing edges of a software architecture map. CONTEXT lists the components involved, with their detected identity and one-line descriptions. RELATIONSHIPS lists the edges to describe; each carries the parser's own evidence for the edge. Use ONLY these facts. Never invent structure.

Return ONLY one JSON object, no prose, no markdown fences:

{"relationships": [
  {"k": "<the exact key from RELATIONSHIPS>",
   "d": "<what flows across this connection, specifically>",
   "imp": "primary | secondary | internal",
   "flow": "<one sentence: what actually crosses this edge>",
   "why": "<one sentence: why this connection exists>"
  }
]}

One entry per key listed under RELATIONSHIPS. Missing any is a failure. "d" is the reader-facing description; "flow" and "why" are audit claims, one tight sentence each.

EVIDENCE DEFAULT. A "flow" or "why" claim that the edge's own listed evidence supports needs NO citation; it is grounded in that evidence by default. Cite only when you rely on something else:
  "flow": {"t": "...", "e": [1]}     index 1 of THIS relationship's "evidence" list
  "flow": {"t": "...", "e": [{"kind": "file", "path": "...", "line": N}]}   a file in the analyzed set
A claim even the edge evidence cannot support: {"t": "...", "s": "u", "r": "<one line: why>"}. On an "s": "u" answer only, when the reason is a missing fact, add "l": "fact" and "need": "<the missing fact>"; when the facts are here but the call is hard, "l": "judgment". An honest "s": "u" costs the run a cheap escalation. A confident guess costs it trust.

Some CONTEXT entries may carry no description; ground the claims in the RELATIONSHIPS evidence and the identity fields, never in an invented description.

"imp": primary means a main artery of the system's data flow. secondary means supporting traffic. internal means wiring within one subsystem.

Omit everything that is default: no status on supported answers, no empty lists, no nulls, no fields not shown.

SUBJECT BRIEF (...):
<the P1 brief JSON>
```

Per-call user message:

```
CONTEXT (the components these edges connect):
<JSON array of one-liners: id, name, type, path, language, framework, description>

RELATIONSHIPS (one response entry per key):
<JSON array of relationship fact blocks: key, source, target, type, label, protocol, port, confidence, evidence[:3]>
Return the JSON object now.
```

The one-liners are the enhancement's own `description` fields written by
2a-C, which runs first (ORCHESTRATION-SPEC 3.1); measured mean 70 scaled
tokens per component against 1,727 for a full fact block. Sufficiency of
one-liners is the Architect's experiment M-5.

Fallback rule (my step-1 review, H1): when a component's fresh description
is missing at 2a-R build time (its 2a-C call failed or has not absorbed),
the coordinator falls back to the parser-derived `existing_description`, or
to the identity fields alone when there is none; the prefix line above tells
the model to expect that. A group's relationship calls never block on its
component call beyond the ordering the Architect already specifies.
Input-cost consequence, quantified: my measured context (3,703 scaled per
call mean) used parser-era descriptions; fresh one-liners add an estimated
1k per call, about 100k scaled per run (+$0.60 at the 2x write rate), booked
in section 9's central input.

`d` and `flow` are both kept: the efficiency postmortem measured them as
textually distinct (word coverage 0.38) and rejected the merge as a free win.
The redesign prices `flow`/`why` as one-sentence audit claims instead of
paragraph prose, which is a length instruction, not a deletion.

### 2.4 What the three outcomes look like (brief question 1)

**Clean pass** (about 9 answers in 10, per the measured status rates): the
entry carries product fields plus four
answered claims with index citations and nothing else. No statuses, no
nulls, no empty lists, no self-verdict. The routing verdict is computed, not
asked: `evaluate()` recomputes state from answers and citations
(`contract.py:305-408`), exactly as current code does.

```json
{"i": "extensions/html", "help_text": "...", "description": "...",
 "data_handled": "...", "criticality": "supporting",
 "q": {"purpose": {"t": "...", "e": [0]},
       "mechanism": {"t": "...", "e": [[1, "activate"]]},
       "place": {"t": "...", "e": ["E0"]},
       "next_step": {"t": "...", "e": ["E2"]}}}
```

**Borderline**: one question carries an exception; everything else stays
minimal. The `l`/`need` fields are the escalation-learning self-report
(section 3):

```json
"q": {"mechanism": {"t": "The dispatch table appears generated; no source file in the menu contains it",
                    "s": "u", "r": "no citable source for the generation step",
                    "l": "fact", "need": "the build script that emits the dispatch table"}}
```

The validator turns this into E2 with the reason attached; only `mechanism`
escalates.

**Escalation markers**: `"generic": true` (E4), `"confusion": "..."` (E5), a
`"d"` status (E1), or citations that fail the mechanical check (E2). Each
fires per question or per item exactly as `evaluate()` and
`state_from_block` already compute (`contract.py:501-547`), with one
redefinition: the component's required set is `purpose, mechanism, place,
next_step`; identity questions leave the model's set entirely (section 6.5)
and `required_questions` (`contract.py:96-115`) shrinks accordingly.

## 3. Findings as structure (brief question 2)

The handoff is the Orchestration Architect's `escalation/v1` protocol
(ORCHESTRATION-SPEC section 4), adopted here verbatim as the single format:
`established` (settled answers), `failed[]` with `question`, `trigger`,
`attempt_claim`, `citations_tried` (each with the validator's verdict
string), `lacked`, `note`, plus `facts` and `todo`. One format, produced by
the coordinator from `ContractState` plus the banked attempt, consumed by 2b
and 2c as their ITEMS payload.

Direction of travel, named once so both specs cite one thing: escalation/v1
is the INPUT format (coordinator to rung), and this spec's array envelope
with `corrections` (sections 4, 5, 7) is the OUTPUT format (rung to
coordinator). One format each direction; the Architect's dynamic-key
response sketch is superseded by agreement (their F-10 adopts the array
form's schema rationale).

This spec's contribution on the sending side: the bulk rung's uncertain
answers carry a structured self-report, `"l": "fact" | "judgment"` plus
`"need": "<the missing fact>"` when `l` is `"fact"`. Constraints, binding
per F-5:

1. **`l` and `need` are legal only on an `"s": "u"` answer.** The schema
   enforces it (`dependentSchemas`, section 7), the prompt says it
   (sections 2.1, 2.3, 4), and the absorber strips the fields from any
   answered claim as defense in depth, so padded self-reports can never
   reach the escalation-cause statistics. The killed run's 100%
   parser_first fill rate under a REQUIRED framing is the precedent this
   guards against.
2. **The coordinator validates `need` against the store before routing.**
   `l: "fact"` routes to rung-0 fact augmentation only when the named need
   resolves deterministically (the file, symbol, or config exists in the
   analyzed set); an unresolvable `need` is reclassified to `judgment` and
   climbs normally, with the unresolvable text kept for the weekly review.
   The model writes `need` while seeing a capped menu and cannot know what
   the store holds; without this check the augmentation loop would spin on
   unsatisfiable needs.

The coordinator maps `"fact"` to the protocol's `fact-not-in-prompt`,
`"judgment"` stays `judgment`, and the coordinator alone assigns
`validator-scope` and `capability` from the validator verdicts and parse
state, because the model cannot know at answer time how the checker will
rule. The protocol's `unknown` residual class also remains
coordinator-only: the model-facing enum is deliberately narrower than the
protocol vocabulary, not a narrowing of it. This is what makes "every
escalation asks what the cheaper rung lacked" a recorded field instead of a
hope.

## 4. Rung 2b: repairs only

Model: opus, `--effort low` pending probe M-3/M-P3. Batch: **5, the agreed
default, and the basis every headline figure in this spec books (QA final
verdict E-3)**; batch 15 is the labeled contingency pending the Architect's
M-2 parity, worth $5.26 per run at Opus $5/$25 (fixed output plus the 125
extra calls' cache reads), so QA's recommendation to keep batch 5
permanently is economically reasonable and M-2's remaining value is the
failure-rate and handoff-size reading. Static prefix, measured **3,072
scaled tokens** with the brief:

```
ESCALATION REPAIR.

You are a higher rung of an enrichment ladder. A cheaper tier already worked the items below. A mechanical validator rejected specific answers; each item's "failed" list names exactly which question failed, with a trigger code and a note. You have NO tools: you cannot read files, run commands, or browse the repository. Everything you may use is already in this prompt.

Repair ONLY what is named. Work that passed is finished work; re-emitting or rewording it spends the run's budget on something it already has.

Trigger codes: E1 no answer was produced. E2 the answer's evidence did not check out, or the tier was uncertain. E3 the claim contradicts a deterministic fact. E4 the answer would fit a sibling equally well. E5 the tier declared confusion.

Return ONLY one JSON object, no prose, no markdown fences:

{"components": [
  {"i": "<id>",
   "q": {"<failed question>": {"t": "<repaired claim>", "e": [<evidence>]}},
   "id": {"<identity field>": {"v": <corrected value or null>, "e": [<evidence>], "r": "<one sentence>"}},
   "corrections": [{"field": "<an established answer or product field that is WRONG>", "now": <corrected value>, "why": "<one sentence>"}]}
],
 "relationships": [
  {"k": "<key>",
   "flow": {"t": "<repaired claim>", "e": [<evidence>]},
   "why": {"t": "...", "e": [...]},
   "corrections": [...]}
]}

Rules:
- Every question in an item's "todo" gets exactly one of: a repaired claim with evidence you can cite, or {"s": "u", "r": "<why this cannot be grounded at this tier>"}, which escalates it honestly. On an "s": "u" answer only, add "l": "fact" with "need": "<the missing fact>" when a needed fact is absent from this prompt, or "l": "judgment" when the facts are here but the call is hard.
- Citations use the bulk pass's forms: an integer indexes THIS item's "files" list (components) or "evidence" list (relationships); [i, "Symbol"] names a symbol in that file; [i, line] a line; "E<i>" indexes the item's "edges" list; a full {"kind": ...} object cites a file elsewhere in the analyzed set. Every citation is checked mechanically.
- "established" answers are settled. Do not re-emit them. If one is actually WRONG, say so in "corrections"; that list exists so adjudication is visible, and it is empty or absent almost always.
- E3: resolve the contradiction: correct the claim, or flag the detected value via "id" with evidence.
- E4: make the answer specific to THIS item: name the fact that could not be true of a sibling. If you cannot, say so with "s": "u".
- E5: the declared confusion is stated on the item. Resolve it from the facts if they allow; otherwise restate it more precisely in "confusion": "<one sentence>".
- Never restate unfailed answers, product prose, or the facts.

SUBJECT BRIEF (...):
<the P1 brief JSON>
```

Per-call user message:

```
ITEMS THAT REACHED THIS RUNG (escalation/v1; "todo" is the exhaustive list of what you answer):
<JSON array of protocol items>
Return the JSON object now.
```

Safety of repairs-only responses: the merge machinery is already additive
and never lossy (`merge_payloads` and `_merge_contract_blocks`,
`ladder.py:103-137`), so a response that carries only the failed questions
merges over the banked block without touching what passed. The current
escalation instruction to "repeat it back unchanged" (`ladder.py:170-173`)
is repealed, exactly as ORCHESTRATION-SPEC 3.1 specifies; `corrections`
replaces it as the visible adjudication channel.

Measured output effect: a full re-emitted component block is 1,770 tokens
(postmortem baseline); a repair is one to two claim-plus-citation objects,
about 60 scaled tokens each plus a 15-token wrapper. Estimated failed
questions per escalated item: 1.5 for components, 1.0 for relationships
(estimate; QA can measure the true distribution by recomputing every
recorded block through `state_from_block` with the fixed validator, the
same harness the efficiency postmortem used, zero calls).

## 5. Rung 2c: terminal, ground or declare

Model: fable, `--effort low` pending probe. Batch 5 (Architect 3.3). Static
prefix, measured **2,745 scaled tokens** with the brief:

```
TERMINAL RUNG.

You are the LAST rung of an enrichment ladder. Two tiers before you attempted the items below and could not ground them; each item carries their attempt and the exact failed questions. You have NO tools: you cannot read files, run commands, or browse the repository. Everything you may use is already in this prompt. There is no rung after you and there is no loop.

For each question in an item's "todo", do one of exactly two things:
1. GROUND IT: a repaired claim with evidence you can cite from the material below: {"t": "<claim>", "e": [<evidence>]}.
2. DECLARE AN HONEST GAP: add {"q": "<question>", "why": "<one sentence>"} to that item's "gaps" list. The why is shown to readers of the map, so write it for them: what specifically defeated three attempts.

A gap you declare honestly becomes a visible part of an honest map, which is a correct outcome. A gap you paper over with a plausible sentence becomes a lie the map tells with confidence. Declare the gap.

Return ONLY one JSON object, no prose, no markdown fences:

{"components": [
  {"i": "<id>",
   "q": {"<failed question>": {"t": "<claim>", "e": [<evidence>]}},
   "gaps": [{"q": "<question>", "why": "<one sentence for the reader>"}]}
],
 "relationships": [
  {"k": "<key>",
   "flow": {"t": "...", "e": [...]},
   "why": {"t": "...", "e": [...]},
   "gaps": [{"q": "<flow|why>", "why": "<one sentence>"}]}
]}

Citations use the same forms as every rung: an integer indexes THIS item's "files" list (components) or "evidence" list (relationships); [i, "Symbol"]; [i, line]; "E<i>" for the item's "edges" list; or a full {"kind": ...} object within the analyzed set. Every citation is checked mechanically. Never restate unfailed answers, product prose, or the facts.

SUBJECT BRIEF (...):
<the P1 brief JSON>
```

Same user-message shape as 2b. The declared-gap absorption path already
exists and is kept: gaps close their questions with the reason preserved on
the contract state (`ladder.py:722-753`), and the examined-versus-unexamined
distinction stays exactly as landed (`ladder.py:580-636`).

## 6. The schema diet, item by item (brief question 3)

Transformation rules were applied mechanically to all 43 component and 822
relationship blocks the killed run actually produced, against the real
store's fact menus; sizes in section 0. Item by item:

### 6.1 Evidence by reference

A citation is an index into a per-target menu the prompt already carries:
`files` (present in the facts today, `prompts.py:183`), the new `edges` list,
or the relationship's own `evidence` list (`prompts.py:240`). Forms: `2`,
`[2, "Symbol"]`, `[2, 120]`, `"E3"`. The full evidence object survives only
as the escape hatch for the measured 3.4% of component citations that point
outside the menus. The validator resolves references deterministically to
the same `{kind, path, line, symbol}` objects it checks today
(`evidence.py:138-250`), so every existing check still runs; an
out-of-range index is a failed citation (E2). At most 2 citations per claim:
`any_valid` needs one (`evidence.py:260-267`), the second is the backup.
Measured cost: a restated citation averages ~52 output tokens (postmortem);
an index is 1 to 5.

The symbol form deliberately keeps the symbol name: the validator fix
(roadmap R-5) records `referenced-at` versus `defined-at`, and the
sufficiency spot-check (P3) receives resolved full citations in its digest,
so nothing downstream loses information.

### 6.2 One evidence channel for relationships

The old shape gave `flow` and `why` separate evidence arrays; 71% of the
pairs were byte-identical (postmortem), worthless to a validator that needs
one valid citation. The new shape has no relationship evidence at all in the
default case (6.3), and per-claim `e` only as the exception, so the
duplicated channel structurally cannot occur.

### 6.3 The relationship evidence default. THIS IS A CONTRACT SEMANTIC CHANGE, not a diet item (F-6).

Measured: 1,530 of 1,533 answered flow/why citations restate the
relationship's own evidence list, the edge itself, or the source component's
file list. The default therefore inverts: a supported claim carries no
citation and is recorded as grounded in the edge's parser evidence, with
provenance `edge-default` on the contract state. The explicit `e` form
covers the 0.2% remainder.

Stated plainly, because it must not be buried: this changes what the
contract detects, not just what it costs. Today a confident fabricated
claim over a real edge must produce a citation, and that citation can fail
E2; under the default it produces nothing and passes silently. The
quality-affecting row for this sits in section 12 with the others.
Mitigations, all three required: (a) the `s: "u"` channel with the F-5
self-report stays the honest path and the prompt prices it as cheap; (b)
P3's sufficiency spot-check receives the resolved `edge-default` evidence
and judges whether it carries the claim, exactly as for any citation; (c)
M-P5 now carries the zero-cost quantification the Architect asked for:
count, over the recomputed corpus, the relationship claims whose ONLY
failing citations were genuinely fabricated (the analogue of QA R2's 3
unknown-symbol plus 1 unindexed-path out of 1,270). Single digits out of
2,521 confirms the default is safe; hundreds means it needs a guard
(mandatory citation for `primary`-importance edges is the prepared
fallback). Until M-P5 reports, this change is flagged, not settled.

What the change removes is real but bounded: E2 existence-check theater on
transcribed citations (the 47% relationship escalation rate, of which 658
of 795 were the validator bug) disappears; E2 still fires on `s: "u"` and
on explicit citations that fail.

### 6.4 Implicit defaults

`status`, `self_state`, `confusion: null`, `parser_first: []` are never
emitted at their default values (measured constant 88 to 93% of the time).
Absence is the default; `evaluate()` computes the verdict either way. The
`pf` key is capped at 2 one-line entries and omitted when empty: the
current REQUIRED framing (`prompts.py:698-707`) produced a 100% fill rate at
188 scaled tokens per component, which is padding by instruction. The
parser-first program keeps its channel; it loses its filler. M-P8 measures
the fill rate under the new framing.

### 6.5 Identity as exception flags

Today the model answers `identity.*` for every detected attribute: the
prompt hands it the value, the model restates it with evidence (266 scaled
tokens per component measured), and nothing checks it
(`strict_identity=False` by default, so `_contradiction_notes` never runs,
`contract.py:319-330`). The redesign: rung 0 writes identity contract rows
deterministically (ORCHESTRATION-SPEC 3.2 item 2), the model's required set
drops to the four judgment questions, and the model speaks about identity
only to disagree, via `"id": {field: {v, e, r}}`. Emission is a signal, not
a transcript. Expected quality effect: positive (today's identity answers
are generated, stored, never checked; a flagged disagreement is actionable).
Verification: QA V-3 (evidence provenance per detected attribute) plus M-P5.

### 6.6 The substitution check as a boolean

`"generic": true` replaces the 68-token sentence whose only mechanical
reader is a substring match (`contract.py:550-567`). The E4 path reads the
boolean directly. Trade, stated honestly: the current form forces the model
to produce the distinguishing fact, and that generation act may be part of
what makes the self-test bite. M-P6 A/Bs the two forms on E4 detection
before adoption; if the boolean loses detection power, the fallback is
`"distinct": "<the one fact>"`, still structured, ~20 tokens.

### 6.7 Response envelope

Arrays with an explicit `"i"`/`"k"` field replace id-keyed maps, so the
response schema needs no dynamic keys (section 7). The absorber converts to
maps and enforces the census: every requested id present exactly once;
a missing entry is a call-level defect that triggers the one corrective
retry the ladder currently lacks (`ladder.py:439-460`; parity with
`passes._invoke_json` and the two engine call sites), then per-target E1.

### 6.8 Not claimed, per the checked-and-rejected list

`data_flow_description` versus `flow.claim` (word coverage 0.38) and
`help_text` versus `purpose`+`mechanism`+`place` (coverage 0.43) are both
retained. No token in this projection comes from deleting either. The
savings on those fields come only from the length instruction ("one tight
sentence") applied to audit claims, which the low-effort replays already
exhibit (211-char claims at xhigh versus 105 at low on the same prompt,
overflow postmortem effort curve).

## 7. Structural output enforcement (brief question 4)

**Verified offline against the installed CLI (2.1.220 binary,
`~/.local/share/claude/versions/2.1.220`), by string inspection, not
execution:** the CLI exposes `--json-schema <schema>` ("JSON Schema for
structured output validation", with draft 2020-12 support and its own
validation errors), wired to a structured-output path (`output_config`,
`structured_outputs`, `structuredOutputAttempts`,
`structured_output_retry_exhausted`), and `--effort <level>` exists as a
first-class flag. Neither is used by `ClaudeCliInvoker` today
(`engine.py:182-187`).

What `--json-schema` buys: the malformed-response class the run died on
(fence re-injection, mid-string truncation seams, prose preambles) becomes
structurally impossible for schema-conformant output, and the
`structured_output_retry_exhausted` string implies the CLI itself retries
non-conforming output within the call. Salvage (roadmap R-4) then demotes
from runtime crutch to regression test, exactly as the brief frames it.
`max_tokens` overflow remains possible in principle and stays covered by the
output-budget gate (QA G2/W1); the plan is sized so the worst call passes
that gate's binding dispersion rule with margin (84% of the ceiling at the
1.90 factor, section 9), not merely at the mean.

The schemas, one per call kind. All use `additionalProperties: false`,
optional fields for every default-omitted key, and no dynamic keys. The
2a-C schema in full; the others differ only in their entry definitions:

```json
{"$schema": "https://json-schema.org/draft/2020-12/schema",
 "type": "object", "additionalProperties": false, "required": ["components"],
 "properties": {"components": {"type": "array", "items": {"$ref": "#/$defs/comp"}}},
 "$defs": {
  "ev": {"oneOf": [
    {"type": "integer", "minimum": 0},
    {"type": "array", "prefixItems": [{"type": "integer", "minimum": 0},
                                      {"type": ["string", "integer"]}],
     "minItems": 2, "maxItems": 2, "items": false},
    {"type": "string", "pattern": "^E[0-9]{1,2}$"},
    {"type": "object", "additionalProperties": false, "required": ["kind", "path"],
     "properties": {"kind": {"enum": ["file", "doc", "manifest"]},
                    "path": {"type": "string"}, "line": {"type": "integer"},
                    "symbol": {"type": "string"}}},
    {"type": "object", "additionalProperties": false,
     "required": ["kind", "source", "target"],
     "properties": {"kind": {"const": "edge"}, "source": {"type": "string"},
                    "target": {"type": "string"}}}]},
  "answer": {"type": "object", "additionalProperties": false,
   "properties": {"t": {"type": "string"},
                  "e": {"type": "array", "items": {"$ref": "#/$defs/ev"}, "maxItems": 2},
                  "s": {"enum": ["u", "d"]}, "r": {"type": "string"},
                  "l": {"enum": ["fact", "judgment"]}, "need": {"type": "string"}},
   "dependentSchemas": {
    "l": {"required": ["s"], "properties": {"s": {"const": "u"}}},
    "need": {"required": ["s", "l"], "properties": {"l": {"const": "fact"}}}}},
  "idflag": {"type": "object", "additionalProperties": false, "required": ["v", "r"],
   "properties": {"v": {"type": ["string", "integer", "null"]},
                  "e": {"type": "array", "items": {"$ref": "#/$defs/ev"}, "maxItems": 2},
                  "r": {"type": "string"}}},
  "comp": {"type": "object", "additionalProperties": false,
   "required": ["i", "help_text", "description", "data_handled", "criticality", "q"],
   "properties": {
    "i": {"type": "string"},
    "help_text": {"type": "string"}, "description": {"type": "string"},
    "data_handled": {"type": "string"},
    "criticality": {"enum": ["critical", "important", "supporting"]},
    "architectural_role": {"enum": ["api-gateway", "auth-service", "data-store",
      "cache-layer", "queue-processor", "event-bus", "orchestrator", "worker",
      "proxy", "monitoring", "logging", "scheduler", "notification-service",
      "file-storage", "search-engine", "ml-pipeline", "presentation-layer",
      "business-logic", "data-access"]},
    "tech_context": {"type": "string"}, "testing_assessment": {"type": "string"},
    "testing_maturity": {"enum": ["comprehensive", "adequate", "minimal", "untested"]},
    "port_assessment": {"type": "string"}, "complexity_assessment": {"type": "string"},
    "external_services_assessment": {"type": "string"},
    "actions_summary": {"type": "string"},
    "key_user_flows": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
    "q": {"type": "object", "additionalProperties": false,
          "required": ["purpose", "mechanism", "place", "next_step"],
          "properties": {"purpose": {"$ref": "#/$defs/answer"},
                         "mechanism": {"$ref": "#/$defs/answer"},
                         "place": {"$ref": "#/$defs/answer"},
                         "next_step": {"$ref": "#/$defs/answer"}}},
    "id": {"type": "object", "additionalProperties": false,
           "properties": {"type": {"$ref": "#/$defs/idflag"},
                          "framework": {"$ref": "#/$defs/idflag"},
                          "port": {"$ref": "#/$defs/idflag"},
                          "language": {"$ref": "#/$defs/idflag"}}},
    "confusion": {"type": "string"}, "generic": {"const": true},
    "pf": {"type": "array", "items": {"type": "string"}, "maxItems": 2}}}}}
```

The `"E<i>"` string is the primary edge citation; the edge object survives
as an escape hatch for an edge beyond the menu's 12-entry cap, and the
file-kind object covers the measured 3.4% of out-of-menu paths. 2a-R's
entry: required `k, d, imp, flow, why`;
`flow`/`why` are `oneOf` [string, answer]. 2b's entry: required `i` (or
`k`), optional `q` (all four questions optional), `id`, `corrections`,
`confusion`, `flow`, `why`, `d`. 2c adds `gaps` (array of `{q, why}`,
`required`). Full schema files accompany implementation, not this spec.

Costs and unknowns, honestly: whether the CLI passes the schema through the
API's structured-output mechanism (grammar-constrained decoding) or
validates-and-retries client-side; whether the schema itself bills as input;
how it interacts with the cache prefix and with thinking at low effort; and
what a retry costs when the model misses. None of these can be settled
offline. Measurement M-P4 resolves all four with six probe calls before
adoption. Until it passes, the prompts above are designed to survive without
the flag (the "Return ONLY one JSON object" contract plus salvage plus the
corrective retry), so structural enforcement is an upgrade, not a
dependency.

## 8. Worked example: one real group, exact input, realistic minimal output

The group whose first component is `extensions/copilot/src/util/node`: 11
components, chosen because the killed run actually produced blocks for all
11, so the output below is real model content restructured, not invented.
The full call is one 2a-C invocation.

**Exact input.** System append: the 2a-C prefix of section 2.1 with the
VS Code brief, 4,364 scaled tokens (cached; read on this call). User
message: `data/prompt-worked-example-input.txt`, byte-exact, 3,822 o200k
tokens = **6,050 scaled tokens** (cache creation on this call). Its shape,
first component of eleven:

```
COMPONENTS (one response entry per id; each "files" list and "edges" list is that component's citation menu):
[
  {
    "id": "extensions/copilot/src/util/node",
    "name": "node",
    "type": "module",
    "path": "extensions/copilot/src/util/node",
    "language": "typescript",
    "framework": null,
    "lines": 1021,
    "file_count": 11,
    "files": [
      "extensions/copilot/src/util/node/crypto.ts",
      "extensions/copilot/src/util/node/jsonFile.ts",
      "extensions/copilot/src/util/node/ports.ts",
      ...5 more...
    ],
    "existing_description": null,
    "inbound_edges": 6,
    "outbound_edges": 4,
    "has_testing_data": true,
    "testing": {"test_files": 7, "test_lines": 733, "unit_tests": 58, ...},
    "edges": [
      "-> extensions/copilot/src/util/common (import)",
      "-> extensions/copilot/src/util/vs (import)",
      ...
      "<- extensions/copilot/src/extension (import)",
      ...
    ]
  },
  ...10 more components...
]
Return the JSON object now.
```

**Realistic minimal output.** `data/prompt-worked-example-output.json`: all
11 entries, built by mechanically transforming the killed run's real blocks
for these components into the new schema (13 edge citations remapped to
`"E<i>"` menu refs). Total **11,107 scaled tokens**, 1,010 per component.
First entry, abridged mid-help_text only:

```json
{"components": [
 {"i": "extensions/copilot/src/util/node",
  "help_text": "This module supplies Node.js-specific helper functions for the Copilot extension: crypto.ts wraps cryptographic operations, jsonFile.ts implements JSON file persistence built on the shared TaskQueue from util/common, and ports.ts probes for available network ports [...] with 58 unit tests running in CI.",
  "description": "Node.js-only helper utilities (crypto, JSON files, port scanning) for the Copilot extension.",
  "data_handled": "Cryptographic hash/key material, JSON file contents persisted to disk, OS-level TCP port availability state",
  "criticality": "important",
  "tech_context": "TypeScript compiled for Node.js execution, giving the Copilot extension host access to Node-only APIs (crypto, filesystem-backed JSON I/O, network port probing) that the common/ and vs/ tiers deliberately avoid.",
  "testing_assessment": "58 unit tests across 7 spec files exercise debounce, lock, glob, markdown and anomaly-detection helpers, all wired into CI, giving this small module solid direct coverage.",
  "testing_maturity": "adequate",
  "q": {
   "purpose": {"t": "Supplies Node.js-only utility functions (crypto, JSON file persistence, port scanning) that other Copilot components call when they need capabilities unavailable in the browser/common tiers.", "e": [0, 1]},
   "mechanism": {"t": "jsonFile.ts layers JSON read/write on top of util/common's TaskQueue to serialize file access; ports.ts uses a CancellationToken (from util/vs) to make port scans abortable.", "e": [[1, "TaskQueue"], [2, "CancellationToken"]]},
   "place": {"t": "6 inbound edges show other Copilot components calling into this module for Node-only work; its 4 outbound edges go to util/common (async primitives) and util/vs (base types), matching its position as a leaf utility tier built on the two lower utility layers.", "e": ["E0", "E1"]},
   "next_step": {"t": "Read extensions/copilot/src/util/common next: it's the cross-platform layer this Node tier builds on (TaskQueue, Debouncer, Lock) and clarifies what stays common versus what needs the Node tier.", "e": ["E0"]}
  },
  "pf": ["The path 'extensions/copilot/src/util/node' follows the same runtime-tier folder convention documented for src/vs (common/browser/node/electron-*): the 'node' suffix already tells a reader this code is Node-API-only without needing model inference from the import graph."]}
 , ...10 more entries...
]}
```

The same content in the old schema, from the same real blocks, measures
1,592 scaled tokens for this component against 1,105 new
(`data/prompt-example-component-pair.json` holds the full before/after
pair; the identity answers, statuses, the null confusion, and the evidence
objects account for the difference). A real relationship pair is in
`data/prompt-example-relationship-pair.json`: 343 scaled tokens old, 155
new, with the old block's flow and why citations byte-identical to each
other, both restating a file from the prompt.

**The call, in billing classes** (this exact group, central projection at
low effort):

| class | tokens | basis |
|---|---|---|
| cache read | 16,910 (CLI overhead 12,546 + prefix 4,364) | adjudicated overhead; measured prefix |
| cache creation (1h) | 6,050 | measured user message |
| input, uncached | ~2 | observed constant across the run's calls |
| output | ~11,300 to ~13,900 | central: 11 x 900 + 1,369 adjudicated fixed; upper: the measured 11,107 xhigh-verbosity content plus the 2,800 fixed bound |

## 9. Token projection versus baseline

Every factor's source is named inline. Baseline figures marked [PM] are the
postmortems' and are trusted per the ground rules; everything else is from
this session's artifacts.

**Per block (delivered JSON, scaled tokens):**

| | baseline [PM] | new, conservative (measured transform of xhigh blocks) | new, central (low-effort blocks x measured diet ratio) |
|---|---|---|---|
| component | 1,770 (product 528 / scaffolding 1,224) | 1,263 | **880** |
| relationship | 437 (product 58 / scaffolding 346+) | 153 | **124** |

Product fields are untouched in all columns; the entire reduction is
scaffolding: evidence objects to indexes, constants to silence, identity
answers to exception flags, the substitution sentence to a boolean, pf
padding to a capped channel.

**Per call: dispersion-adjusted sizing (F-2, binding).** The sizing rule,
shared verbatim with the Architect's revised formula and QA's G2:

    worst-call predicted mean x 1.90 <= 0.85 x 64,000

with 1.90 the xhigh-derived `dispersion_max` held as the conservative
default until Level 1 recalibrates `dispersion_max(low)` at n >= 10
(M-P1/M-P2 double as that sample; the four low replays measure 0.93 to 1.08
under this spec's decomposed predictor, which is why the recalibration is
expected to relax the cap). Predicted means use the CONSERVATIVE block
sizes and the adjudicated fixed output of 1,369. Where the two specs'
formulas land on different caps, the lower cap wins; the Architect's F-2
suggested 24, which fails the 0.85 bound (60,728, 94.9%), so 21 stands.

| call kind | count | worst-call mean | x 1.90 | share of ceiling | verdict |
|---|---|---|---|---|---|
| 2a-C, cap 21 components | 61 | 28,312 | 53,793 | 84.1% | passes |
| 2a-C at the old cap 30, for the record | 55 | 39,859 | 75,732 | 118% | refused; this is why the cap moved |
| 2a-R, batch 80 | 100 | 15,209 | 28,897 | 45.2% | passes |
| 2b, batch 5 (default), pathological full re-emission | 188 | 7,784 | 14,790 | 23.1% | passes |
| 2b, batch 15 (contingency), same failure mode | 63 | 20,614 | 39,167 | 61.2% | passes even in the failure mode |
| 2c, batch 5 | 39 | trivial | | under 20% | passes |

Cap-21 compliance holds while the measured new-schema per-call fixed stays
at or under 1,688; if M-P1 measures it at the 2,800 bound, the cap drops to
20 (54,074 dispersed, 84.5%). The killed run had 113 of 173 partitions
projected over the ceiling at the mean alone [PM]. The G2 mean-multiplier
for low effort is measured: billed output = delivered x 1.00 to 1.06 plus a
fixed 1,369 (adjudicated; bounds 500 to 2,800), against 4.5x at xhigh [PM].

**Per run (VS Code, 569 components, 5,453 relationships; call plan shared
with ORCHESTRATION-SPEC: 61 + 100 + 188 + 39 = 388 calls on the batch-5
default basis, E-3).** Token classes, central variant (from
`data/prompt-aligned-cost-model.json`, regenerated by
`prompt-aligned-cost-model.py`):

| rung | calls | cache creation | cache read | output |
|---|---|---|---|---|
| 2a-C sonnet | 61 | 430k (byte-budget capped, edge menus included) | 1,032k | 596k |
| 2a-R sonnet | 100 | 1,752k (fresh-description context included) | 1,535k | 922k |
| 2b opus, batch 5 default | 188 | 988k | 2,936k | 336k |
| 2c fable | 39 | 252k | 596k | 73k |

Dollars, per F-1 dual-priced on Opus, per F-7 with the conservative variant
moving all four rungs (conservative = conservative blocks, fixed output at
its 2,800 bound, heavier handoff items, failed-per-item 2.0/1.5, 2c entry
30%), and per E-3 booked at the batch-5 default with batch 15 as the
labeled contingency:

| rung | central, Opus $5/$25 | central, Opus $15/$75 | conservative, $5/$25 | conservative, $15/$75 |
|---|---|---|---|---|
| 2a-C | $11.82 | $11.82 | $16.40 | $16.40 |
| 2a-R | $24.80 | $24.80 | $29.92 | $29.92 |
| 2b (batch 5 default) | $19.76 | $59.27 | $33.75 | $101.24 |
| 2c (fable, ledger-fit) | $9.30 | $9.30 | $22.64 | $22.64 |
| **ladder, batch-5 basis** | **$65.68** | **$105.19** | **$102.71** | **$170.20** |
| ladder, batch-15 contingency (pending M-2 parity) | $60.42 | $89.42 | $92.98 | $141.02 |

The stacked corners combine every conservative parameter AND the legacy
Opus price simultaneously; QA's convergence band deliberately does not
stack those, which is the whole difference between this table's corners and
their band top (alignment below). Cache-read dollars in every column are
contingent on the M-P1 append-file gate (E-4; the exposure if it fails is
quantified in section 10).

Sources per factor: 2a inputs are exact prompt builds over the re-derived
store, byte-budget and edge menus applied per section 2.2, fresh-description
estimate per section 2.3; 2a outputs are the block measurements of section 0
plus the adjudicated 1,369 fixed (F-3 resolved: the fixed term now IS the
adjudicated envelope-plus-thinking figure, replacing the earlier 30-token
assumption; the 20-token per-entry `"i"` overhead remains an estimate M-P1
confirms); the 939-item 2b population is the postmortem's post-validator-fix
recompute (285 components at 50%, 654 relationships at 12%) [PM], kept at
285 per the Architect's F-8 alignment; 2b/2c item inputs use measured facts
and attempt sizes plus protocol overhead (estimates, with the conservative
column carrying verdict-string-heavy handoffs and two attempts at 2c);
failed-questions-per-item and the 2c entry fraction are estimates flagged to
M-2 and to the scheduled zero-cost harness runs; Opus and Fable thinking at
low is budgeted at the adjudicated Sonnet figure (unmeasured on those
models, probe M-P3). Prices per section 0.

**Against baseline, and alignment with the QA convergence:**

| | as configured (killed run) [PM] | this design (batch-5 basis) |
|---|---|---|
| rung 2a | $326, 173 calls, 35% overflow observed | $36.6 central, 161 calls, every call passing the dispersion gate |
| rung 2b | ~$670 (±30%) | $19.8 at Opus $5/$25; $59.3 at $15/$75 |
| rung 2c | unmeasured, structurally unbounded | $9.3, bounded (ORCHESTRATION-SPEC 6) |
| ladder total | $1,000+ | **$66 central at $5/$25; $105 at $15/$75; $103 conservative; $170 stacked-worst corner** (batch-15 contingency: $60 / $89 / $93 / $141) |
| billed output, 2a | 14.3M nominal (fitted xhigh model) [PM] | 1.52M central |
| per unique component, 2a all-in | $0.573 ($326 / 569) | $0.0208 |
| per relationship, 2a all-in | entangled with component slots | $0.00455 |

Alignment with the adjudication's converged band and the QA final verdict:
this spec's batch-5 central is **$65.68** at Opus $5/$25. The verdict's E-3
arithmetic quotes $64.70, derived from this spec's own earlier delta line,
which counted only the extra fixed output of the 125 additional calls; the
regenerated model also books those calls' cache reads (+$0.98), and $65.68
is the exact figure. It sits inside QA's ladder band ($55 to $95, central
about $65). The $105 legacy-price branch and the $103 conservative case
bracket the band's top; the only figures outside it are the deliberately
stacked corners, which combine two worst-cases QA scores separately. With
P1 measured at $0.75 and P3 to P5 estimated at $10 to $20 (Architect M-7),
the full run lands at roughly $76 to $106 at $5/$25, central about $81,
matching the verdict's converged "$81 central" exactly, and about $121 at
$15/$75. The single number that decides which branch is real is the Opus
price, and the first pilot Opus ledger row settles it before Level 2
sign-off (F-1).

The postmortem's own tier C projected ~$110 for the full run at coarser
resolution [PM]. Section 14 records the adjudication outcomes on the two
calibration disputes that once separated this spec from the Architect's.

## 10. Context shape and caching (brief question 5)

**What the transcripts prove about today's behavior.** Every 2a call's
first turn shows the same pattern (session `c95c2999`: `input_tokens: 2`,
`cache_creation.ephemeral_1h_input_tokens: 39,241`,
`cache_read_input_tokens: 8,849`): the CLI writes the entire user message
to cache at the 1h rate (2x) and reads its own system prompt from cache.
The run therefore paid 2x on all 4.06M scaled tokens of prompt bodies,
including the 5,539-token instruction prefix repeated in all 173, and no
call ever read another call's prefix, because prefix caching is exact-match
at breakpoint positions and the CLI's breakpoint sits at the end of each
(unique) user message. The occasional large reads in the ledger (up to
30,605) are retry duplicates re-reading a byte-identical predecessor
prompt, not partial sharing.

**The mechanism.** Move everything stable into the system prompt via
`--append-system-prompt-file <rung-prefix-file>` (flag verified present in
CLI 2.1.220). The system block is where the CLI already maintains a
breakpoint, so the appended prefix becomes part of the cached,
byte-identical, cross-call system entry.

**LOAD-BEARING AND UNVERIFIED (F-9):** the flag's existence is verified;
that appended content joins the CACHED system entry is not, and everything
in this section rests on it. If appended content lands outside the cached
breakpoint, the prefix bills at 2x on every call instead of once (about
$2.80 per run at the measured prefix sizes) and `prefix_hash` telemetry
reads permanent cache misses. The probe is named and gated: M-P1's first
pilot ledger MUST show, on every non-warm call, `tokens_cache_read >=`
CLI overhead plus the rung prefix, and this assertion is a Level 1
sign-off criterion, not a nice-to-have. Booking statement, reconciled per
the QA final verdict's E-4: section 9's tables DO price prefixes at
cache-read rates, explicitly labeled contingent on this gate; if the gate
fails, the fallback (the appended prefix billing at the 2x write rate on
every call) adds **$10.64 at Opus $5/$25 or $21.61 at $15/$75 on the
batch-5 basis** ($6.99 / $10.67 at the batch-15 contingency), quantified
in `prompt-aligned-cost-model.json` under
`prefix_exposure_if_MP1_gate_fails_usd`. The CLI-overhead share of the
read rows (12,546 per call) is NOT contingent: the killed run shows the
CLI's own system prompt caching without any append.

Stability classification:

| content | stability | placement |
|---|---|---|
| CLI system prompt | constant | system (already cached) |
| rung instructions + schema description + vocabularies + quality bar | constant per rung | system append, first |
| subject brief | constant per run | system append, last |
| fact payloads (components / context+relationships / items) | per call | user message |
| anything per-call (ids, counts) | per call | user message, after facts |

Rules, per the prefix-match invariant: byte-identical render (no
timestamps, no partition ids, sorted JSON keys in the brief), one prefix
file per rung per run, never edited mid-run. `warm_first` stays
(`ladder.py:477-480`, `pipeline.py:460`): the first call writes the prefix
entry before fan-out, so N-1 calls read instead of racing to write.
Group-adjacent dispatch for 2a-R chunks per ORCHESTRATION-SPEC section 8.
Caches are model-scoped: each rung warms its own. All four prefixes
(4,364 / 2,808 / 3,072 / 2,745 with brief) clear Sonnet 5's 1,024-token
and Opus/Fable's 512-token cacheable minimums. TTL: the CLI writes at 1h;
at low-effort call durations (150 to 300s) with 4 workers, same-rung reads
land well inside even the 5m window.

**What it is worth**: the shared prefix stops billing at 2x per call and
bills once plus 0.1x reads: about $7 across the four rungs, plus the
removal of the current 5,539-token in-prompt prefix from every 2a call
(that saving is already inside section 9's input totals). The larger value
is diagnostic: a byte-stable prefix makes the ledger's cache columns a
health signal instead of noise.

**The telemetry required to verify it** (extends `LedgerRow`,
`pipeline.py:270-305`; the current row conflates cache creation into
`tokens_in` at `pipeline.py:328` and discards `stop_reason` and `num_turns`
on the success path, `engine.py:236-243`):

| field | source | why |
|---|---|---|
| `tokens_input_uncached` | `usage.input_tokens` | true per-call marginal input |
| `tokens_cache_creation_1h` / `_5m` | `usage.cache_creation.ephemeral_*` (fields verified present in CLI usage blocks) | the 2x-billed volume, by TTL class; answers QA V-6 |
| `tokens_cache_read` | `usage.cache_read_input_tokens` (today's `tokens_cached`) | the shared-prefix read volume |
| `stop_reason`, `num_turns` | envelope, success path | feeds the built-and-starved drift alarm (`pipeline.py:390-400`) |
| `effort` | the pinned argv value | proves no inheritance, gate G1 |
| `session_id`, `call_id` | envelope / coordinator | joins ledger rows to transcripts (the postmortem's evidence note asks for exactly this) |
| `prefix_hash` | sha256 of the rendered system append | detects mid-run prefix drift, the classic silent invalidator |
| `targets_components`, `targets_relationships`, `entries_returned` | coordinator | fixes the fourfold undercount at `ladder.py:496-503`; census conservation |
| `tokens_delivered_est`, `tokens_thinking_est` | o200k x 1.5829 on the parsed JSON; output minus that | per-call reasoning share, the G2 multiplier's ongoing calibration |

**What the ledger must show when caching works**, checkable by code per
run (QA owns the gate; thresholds theirs to set):

- Warm call per rung: `tokens_cache_creation_1h` within 10% of prefix +
  user message; `tokens_cache_read` approximately the CLI overhead only.
- Every later same-rung call: `tokens_cache_read` >= prefix size and
  near-constant (= CLI overhead + prefix, +-2%); `tokens_cache_creation_1h`
  within 5% of 1.5829 x o200k(user message); `tokens_input_uncached` <= 10;
  `prefix_hash` identical; `num_turns` = 1.
- Any later call whose `tokens_cache_read` falls below the prefix size is a
  cache miss; investigate before scaling, because at 2x it is the single
  most expensive silent regression this design can have.

## 11. The reasoning budget (brief question 6)

Effort is pinned per rung on the argv (`--effort`, flag verified in CLI
2.1.220), never inherited from `~/.claude/settings.json`. Per rung:

| rung | model | effort | expected billed-output multiplier over delivered JSON | basis | confirming probe |
|---|---|---|---|---|---|
| 2a-C, 2a-R | sonnet | **low** | 1.00 to 1.06, plus the adjudicated 1,369 fixed per call (bounds 500 to 2,800; QA's char-method thinking reading on the same probes: 0 to 455) | measured on the 4 low replays; 4/4 parsed, coverage equal or better, 211-char claims shrink to 105 [PM] | Architect M-1 merged with M-P2, sized 10 to 12 calls so it also calibrates dispersion_max(low) |
| 2b | opus | **low** | unknown; budgeted at the Sonnet-adjudicated fixed | none on Opus; the task is narrower than 2a's (named repairs) | M-P3 within the Architect's M-2 rows |
| 2c | fable | **low** | unknown; thinking is always on for fable, effort still bounds it | none | same rows |

No rung gets more than low, and the justification is measured, not asserted:
the effort curve on a real prompt bought citations and prose length, never
coverage (40,463 output / 36 answered at xhigh against 9,527 / 40 at low
[PM]), and the two medium probes of one prompt disagreed by 2.4x with one
dropping the contract entirely (4,518 vs 10,820 billed, re-verified in the
replay transcripts this session). Medium is banned as measured-unstable,
not merely unnecessary. If a probe ever shows a rung failing at low for
reasons effort would fix, the escalation ladder, not the effort knob, is
the designed response: that is what 2b is for.

## 12. Quality trades, each with its measurement

| change | expected quality effect | measured by |
|---|---|---|
| evidence by index | none: same information, same existence checks, sufficiency digest unchanged (resolved citations) | M-P1 pilot + recompute harness parity |
| relationship evidence default | **quality-affecting (F-6): a confident fabricated claim over a real edge previously had to cite and could fail E2; now it passes silently.** Mitigations: `s: "u"` channel, P3 sufficiency on resolved `edge-default` evidence, and the M-P5 fabrication count; `primary`-edge mandatory citation is the prepared guard if the count comes back high | M-P5 fabrication count (zero cost) + escalation-rate comparison |
| identity as exception flags | positive: disagreement becomes a signal; today's answers are never checked | QA V-3 + M-P5 |
| implicit defaults | none: `evaluate()` recomputes either way | schema round-trip tests, $0 |
| substitution boolean | risk: losing the generation effect | M-P6 A/B |
| pf cap at 2, omit-empty | positive: ends measured 100% padding; channel preserved | M-P8 fill-rate |
| terse audit claims | none for readers (product prose untouched) | blind spot-check per VALIDATION-PLAN section 9 on M-P1's pilot blocks: stratified sample, architecture identity stripped, scored correct / partial / wrong / unscoreable; never an unscored read |
| repairs-only 2b | none: additive merge keeps passed work (`ladder.py:103-137`) | QA merge-property test (V-4) |
| split calls + this schema | ends 3.52x last-roll-wins duplication | census conservation (QA R6) |

## 13. Proposed measurements

Numbered M-P to avoid colliding with the Architect's M-1 to M-8; several
share calls with theirs. Zero were run for this spec. Each: what runs, how
many calls, scaled cost bound, and the decision it resolves.

- **M-P1, schema pilot.** 3 component groups (2a-C) + 3 relationship
  slices (2a-R) with the section 2 prompts at low. 6 Sonnet calls, bound
  $3. Resolves: model compliance with index citations and omitted defaults;
  measured new-schema block sizes replacing the 880/124 central estimates
  (and closing the 382-versus-313 relationship delta); the real new-schema
  per-call fixed (envelope plus thinking, replacing the adjudicated
  old-schema 1,369). Merges naturally with the Architect's M-4 A/B. Two
  assertions are Level 1 GATES, not observations: every non-warm call's
  `tokens_cache_read` at or above CLI overhead plus the rung prefix (F-9,
  the append-file caching proof), and the pilot blocks scored by the blind
  spot-check protocol of VALIDATION-PLAN section 9.
- **M-P2, low-effort stability and dispersion on the new prompts.** Merged
  with the Architect's M-1 per their step-2 list: the M-P1 prompts run
  twice each, 10 to 12 calls total, bound $6. Resolves: variance of
  thinking and block sizes at low on the new prompt shape, and the primary
  output QA needs: a first `dispersion_max(low)` entry for the G2
  calibration table (n >= 10). If it lands at or below 1.55, the 2a-C cap
  returns from 21 toward 30 and the batch bounds recompute.
- **M-P3, Opus and Fable thinking at low.** No dedicated calls: regression
  over the Architect's M-2 ledger rows plus two Fable rows. Resolves: the
  1.5k/call budget for 2b/2c, currently borrowed from Sonnet measurements.
- **M-P4, `--json-schema` behavior.** 3 calls from M-P1 re-run with the
  section 7 schema, versus their unconstrained twins. 3 calls, bound $2.
  Resolves: billed input delta (does the schema cost tokens), cache
  interaction (does adding the flag invalidate the system-prefix entry),
  thinking interaction at low, and malformed-rate; decides whether
  structural enforcement ships in the first run or after.
- **M-P5, grounding-decision parity and the fabrication count.** $0 live:
  recompute contract states for all banked killed-run blocks under (a) the
  current schema and validator, (b) the new schema rules with the fixed
  validator, using the QA replay harness (VALIDATION-PLAN 7.2/R6).
  Resolves: the escalation-rate shift from sections 6.3/6.5; whether the
  939-item 2b population assumption holds under the new rules; the
  failed-questions-per-item distribution (replacing the 1.5/1.0 estimates;
  QA scheduled both as harness runs); and, per F-6, the count of
  relationship claims whose only failing citations were genuinely
  fabricated, which decides whether the 6.3 default ships unguarded.
- **M-P6, substitution A/B.** 10 components run with `generic: true`
  boolean versus 10 with the `distinct` sentence form, siblings shuffled,
  scored by the existing substitution adjudication prompt
  (`prompts.py:945-979`) offline where possible. 2 to 4 calls, bound $2.
  Resolves: 6.6's fallback decision.
- **M-P7, price-model verification.** $0: fit section 0's rates against
  any pilot ledger; the postmortem's model verified to 1.4% and mine must
  match it. The first ledger row containing an Opus call is the F-1
  arbiter between $5/$25 and $15/$75, and per the QA plan that arbitration
  must be on record before Level 2 sign-off.
- **M-P8, pf fill rate.** Read from M-P1's responses, $0 extra. Resolves:
  whether the capped framing ends the padding without killing the channel.

Total dedicated spend: **under $15**, with the merged M-P2/M-1 dispersion
calibration dominating; every other measurement rides on existing rows or
costs nothing.

## 14. The two calibration disputes, adjudicated, and QA handoffs

Both disputes this spec raised in step 1 were adjudicated by the QA persona
from the recorded corpus (`data/qa-adjudication.json`, binding):

1. **chars-per-token: sustained.** The Architect's 1.71 reproduces exactly
   as the per-session mean of chars over ALL prompt-side tokens including
   the fixed CLI overhead and cache reads; the marginal rate is 2.85 to
   2.89 chars per billed token (spot check `c95c2999`: 2.72, fit-free).
   Adjudicated constants: marginal 2.886 chars per token, fixed overhead
   12,546 per call, both now booked in this spec's model. The Architect
   conceded and adopted the o200k method for their step 2.
2. **Fixed output at low: sustained on the decomposition.** The 3-point
   solve is ill-conditioned exactly as claimed (per-relationship
   coefficient lands at -2,581). The adjudicated 4-point least squares
   gives 1,050 per component, 382 per relationship, 1,369 fixed (bounds
   500 to 2,800, max error 5.7%), and the Architect's published model
   missed the held-out fourth point by +23%. This spec now books 1,369 as
   its per-call fixed, which also resolves F-3: the earlier 30-token
   envelope assumption is withdrawn. One refinement accepted against my
   side: the adjudicated 382 per relationship sits 22% above my block-mean
   313 (the open delta of section 0), and the Architect's per-item
   coefficients were roughly confirmed.

A third falsified constant found in the pass cuts the other way and I
accept its symmetry: my Opus $5/$25 was as unsourced as their $15/$75, and
this spec is now dual-priced throughout (F-1, section 0).

Also adopted from their spec, unchanged: the escalation/v1 protocol
(section 3 here), the batch bounds recomputed under the shared dispersion
rule (the plan is 61/100/63/39 after the cap-21 sizing; where the two
specs' formulas disagree the lower cap wins), the 2c bound, and the
fact-block byte budget as a dependency, now carrying the menu-stability
constraint of section 2.2.

For the QA and Validation Engineer, beyond the M-P list: the telemetry
fields of section 10 are the contract your section-3 gates need; the
`prefix_hash` and cache predicates are new since your draft; the response
schemas of section 7 are ready for your R4 prompt-shape regression; and the
worked-example files below are fixtures for a zero-cost round-trip test
(transform old blocks to new schema, absorb, recompute states, assert
census conservation).

## 15. Data files

All under `docs/quality/rearchitecture/data/`, prefixed `prompt-`:

- `prompt-measure-fit-and-blocks.py`: the tokenizer fit and block
  measurements over the run transcripts.
- `prompt-measure-projection.py`: store re-derivation, baseline prompt
  builds, the schema transformation, the initial call plan.
- `prompt-tokenizer-fit.json`: fit parameters, per-session points, block
  composition means.
- `prompt-projection-results.json`: baseline input totals, transform
  results, citation-mapping stats, marker rates.
- `prompt-cost-model.json`: prefix and facts sizes, first-pass cost model.
- `prompt-aligned-cost-model.py` and `prompt-aligned-cost-model.json`: the
  section 9 model, revision 2: 61/100/63/39 call plan, adjudicated
  constants, dual Opus pricing, dispersion-rule arithmetic, conservative
  column varying all four rungs.
- `prompt-worked-example-input.txt`: the exact 2a-C user message of
  section 8.
- `prompt-worked-example-output.json`: the full 11-entry realistic output.
- `prompt-example-component-pair.json`, `prompt-example-relationship-pair.json`:
  one real block each, old schema beside new.

## 16. Changelog: revision 2 (Phase 2 step 2)

Every change and its driver. Drivers: A = QA adjudication (binding), F-n =
Architect review finding, QA-n = QA testability-pass mandatory item, S1 =
my own step-1 review self-corrections.

1. Opus dual-priced at $5/$25 and $15/$75 in section 0, the section 9
   tables, and the cost-model script; first pilot Opus ledger row named as
   arbiter and Level 2 sign-off requirement. [F-1, mandatory]
2. Mean-calibrated headroom claims replaced with the binding dispersion
   rule (worst-call mean x 1.90 at or under 0.85 x 64,000, 1.90 held until
   Level 1 recalibration); 2a-C cap 21, plan 61 component calls; the
   Architect's cap-24 alternative shown failing the 0.85 bound, lower cap
   wins; the section 7 "3x headroom" sentence corrected. [F-2, S1]
3. Per-call fixed output re-based to the adjudicated 1,369 (bounds 500 to
   2,800), withdrawing the 30-token envelope assumption and resolving the
   internal inconsistency with the measured 483 to 1,323 envelope. [F-3, A]
4. Block-sample exclusion rule stated (26 of 36 sessions under the weaker
   salvage; excluded five are multi-turn overflow sessions) with the bias
   direction discussed; tiktoken dependency noted. [F-4, QA-10]
5. `l`/`need` bound to `"s": "u"` in-schema via `dependentSchemas`, in all
   three rung prompts, and stripped by the absorber from answered claims;
   coordinator validates `need` against the store, unresolvable reclassifies
   to `judgment`; the protocol's coordinator-only `unknown` class noted.
   [F-5]
6. Relationship evidence default promoted to an explicit contract semantic
   change with three mitigations and the zero-cost fabrication count added
   to M-P5; prepared guard named. [F-6]
7. Conservative column now varies all four rungs (blocks, fixed bound,
   handoff weights, failed-per-item, 2c entry 30%); 2b $14.50 to $24.02 and
   2c $9.30 to $22.64 across variants at $5/$25. [F-7]
8. Populations held at 285/939, now matching the Architect's step-2
   alignment. [F-8, S1]
9. `--append-system-prompt-file` caching marked load-bearing and
   unverified; the M-P1 cache-read assertion promoted to a Level 1 gate;
   section 9 prices prefix reads explicitly labeled contingent on that
   gate, with the fallback exposure quantified in section 10. [F-9;
   wording amended by entry 19]
10. Human-read quality metric bound to the blind spot-check protocol of
    VALIDATION-PLAN section 9 (section 12 and M-P1). [QA-9]
11. Adjudicated constants adopted throughout: marginal 2.886 chars per
    token equivalent, per-call overhead 12,546, output 1,050/382/1,369 with
    the 382-versus-313 open delta carried explicitly in section 0. [A]
12. Byte-budget effect quantified (196,579 scaled tokens, about $1.18) and
    booked; menu-stability constraint on R-10 added. [S1]
13. 2a-R fresh-description context (+1k per call, about $0.60) booked;
    missing-description fallback rule added to the prompt and the
    coordinator contract. [S1]
14. Handoff format direction named once: escalation/v1 in, array envelope
    with `corrections` out. [S1]
15. Prompt prefixes re-measured after the F-5 additions: 4,364 / 2,808 /
    3,072 / 2,745 with brief. [F-5 consequence]
16. M-P2 merged with the Architect's M-1 at 10 to 12 calls, its primary
    output now `dispersion_max(low)` for the G2 table; probe budget
    restated under $15. [F-2, Architect step-2 list]
17. Totals regenerated: ladder central $60.42 at Opus $5/$25, $89.42 at
    $15/$75; conservative $92.98 and $141.02; full run about $71 to $110,
    central about $76 at $5/$25. Alignment with the QA convergence band
    stated in section 9, with the one out-of-band corner explained. [A,
    F-1, F-7; superseded on the batch basis by entry 18]
18. Headline central restated on the batch-5 default basis (QA final
    verdict E-3): 2b books 188 calls, ladder central **$65.68** at Opus
    $5/$25 ($105.19 at $15/$75; conservative $102.71 / $170.20), with
    batch 15 kept as the labeled contingency row ($60.42 / $89.42 /
    $92.98 / $141.02). The verdict's quoted $64.70 came from the earlier
    fixed-output-only delta line; the regenerated model also books the 125
    extra calls' cache reads (+$0.98) and the exact delta is $5.26. Full
    run about $76 to $106 at $5/$25, central about $81, matching the
    verdict's convergence. Dispersion table gains the batch-5 default row
    (23.1% of ceiling in the pathological mode). [E-3]
19. F-9 booking statement reconciled (QA final verdict E-4): section 9's
    cache-read pricing is labeled contingent on the M-P1 append-file gate,
    section 10 quantifies the fallback exposure ($10.64 / $21.61 batch-5;
    $6.99 / $10.67 batch-15; CLI-overhead share not contingent), and
    changelog entry 9 was amended to match. The model script emits the
    exposure block. [E-4]
20. Populations confirmed standing at 285 components / 939 items as ruled;
    the Architect reverts the 284/938 side. No figure moved. [E ruling on
    F-8]
