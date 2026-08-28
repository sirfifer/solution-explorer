# Enrichment economics: the unified result of a dual-session engagement

**Date**: 2026-08-26. **Branch**: `wt/enrichment-economics` (worktree-isolated).
**Status**: final, after cross-session review in both directions. This report
supersedes its earlier revision, which carried four claims the review
falsified; they are corrected here and named in section 6.

The commission: fix the output-side token waste for real, with deterministic
validation; preserve the learning, escalation, and exit channels; re-examine
caching hard before accepting any dismissal of it; quality first throughout.
Two sessions were commissioned in parallel and their work converged here.

## 1. The base implementation, built by the concurrent session

The core of what ships is the concurrent session's work, and it leads this
report because most of what runs is theirs:

- The compact/v1 single-source wire: semantic atoms generated once, expanded
  deterministically into product and contract, replacing duplicated prose.
- Component and relationship calls split, with exact target conservation
  through `coverage_issues` (missing, extra, and duplicate targets are
  explicit failures, never silent).
- JSON Schema structural enforcement and UTF-8 response budgets on the wire.
- Escalations and work orders emitting deltas instead of rewriting settled
  work; the additive merge that makes a failed repair unable to demote a
  grounded answer.
- P5 determination digests (counts plus exceptions plus full synthesis)
  replacing shipped corpora.
- The immutable transition history that preserves why items escalated.
- The engine's cache-boundary plumbing, including
  `--exclude-dynamic-system-prompt-sections`, adopted from the live probe
  within minutes of its publication.
- The audit's hard-fail structure and the correction of its own earlier 10.5%
  whole-run gate once the measured arithmetic showed it unachievable, named
  plainly by that session as validation theater.
- The transport seam test and audit boundary tests, which this branch now
  carries, and which pin exactly the seam the injected-invoker suite cannot
  see.
- The honest limitation note that the CLI exposes no `max_tokens`, so no
  pre-billing token ceiling exists on this transport (verified: the flag does
  not exist).

Their review of this branch then found the release-blocking P5 schema defect
plus six real inconsistencies (section 3), all verified against the code and
all fixed in this final pass.

## 2. What this session added on top of that base

- **Measurement grounding**: two persona implementation deltas re-derived
  every number from the v2 run's artifacts (output 1,332 billed tokens per
  target with 94% discarded; 95.6% of escalated output re-emitting settled
  work; 350 of 350 identity restatements carrying zero information; the
  trigger-class populations; the per-field costs behind every diet).
- **All live probes** (28 calls, $1.48 total, protocol and raw envelopes in
  `data/f9-cache-probe-2026-08-26.md`): the naive append never caches; with
  the exclude flag the stable prefix reads at 0.1x on all three tiers (81 to
  90% repeat-call cost cuts); the opus and fable default system prompts never
  cache at all, which was the v2 ledger's 123 zero-read calls; headless
  resume reads the whole prior context at 0.1x; and the schema interaction of
  section 3.
- **Five defect fixes outside the base implementation's file set**: the
  adjudicator digest stripped fact-citation fields, leaving the committed
  judge fix inert; terminal states without new payloads never re-stamped the
  store (a measured 47-row store/census divergence, now reconciled in
  `_finalize`); verify-identity's 98-of-99 uncertain was input starvation,
  and the framework signal rows its own reasons named as missing now ship;
  verify-edges shipped each endpoint 6.9 times and now ships each once per
  call, with the cross-call residue deliberately left to the optional cached
  corpus mechanism; the
  fact-citation shorthand `["F","<field>"]` existed in no wire form despite
  being 23.3% of real citations.
- Chunk caps shared by live execution, dry runs, and the zero-cost preflight
  (`scripts/enrichment-replay-check.py`); the repair and terminal prompts;
  escalation handoffs carrying citation references instead of expanded
  objects; class-at-entry telemetry; the identity-flags exit-report section;
  the evidence-vocabulary conformance suite
  (`tests/test_evidence_vocabulary_contract.py`); and the audit's input
  ceilings and store-census conservation gates.

## 3. The cross-review fixes, landed in this final pass

1. **The P5 release blocker** (their find, this session's defect): a
   cacheable prompt is no longer compact-schema-eligible by default.
   Unrecognized prefixes get the cache boundary and single-turn pinning with
   no schema, and a transport test drives a real determination prompt through
   `ClaudeCliInvoker` to pin it.
2. **The schema is now byte-constant per rung** (new measurement, probe
   addendum 3): `--json-schema` content participates in the cached entry, so
   the original per-call count bounds would have silently destroyed the
   caching win on every ladder call. Bounds now sit at the rung caps and
   `coverage_issues` remains the exact-count authority.
3. **The fact vocabulary matches what the fact block emits**: `line_count`
   became `lines` at the source of truth, both prompt texts follow, and a
   conformance test asserts every citable name is a key the block can
   actually show. The mismatch was the v2 build's measured 8-failure class.
4. **The work-order validator now attaches fact blocks**; correct fact
   citations in work-order repairs no longer fail closed. Present in both
   trees until their review caught it.
5. **The `lacked` self-report is now the primary classification basis**, as
   the design specified and the earlier report falsely claimed: answers and
   failed questions carry it, class-at-entry prefers it with the trigger map
   as fallback, and both the contract state and the report label how much of
   each basis was used.
6. **The claim length bound covers the measured maximum** (640 against the
   observed 612) instead of contradicting its own justification.
7. **The cache predicate has a real floor**: the ledger records the prefix
   size estimate and the audit requires every non-warm call to have read at
   least its own prefix, not merely more than zero.
8. **The test suites are unioned**: the base session's compact and audit
   tests run beside this branch's conformance and ladder suites.

## 4. What is guaranteed, stated honestly

Three different guarantees, not one:

- **Pre-request, deterministic**: allowed JSON structure, per-field length
  bounds, array caps, and per-call UTF-8 response budgets are fixed before
  any call is made; the preflight rebuilds the real call plan at zero cost
  and checks byte-stable prefixes and output projections.
- **Post-response, deterministic**: delivered bytes against budget, exact
  target coverage, and store-census conservation are evaluated mechanically
  from the run's own artifacts. Schema conformance is enforced at decode
  time by the CLI's `--json-schema` and recorded per call in the ledger's
  `structured_output_enforced` flag; successful response bodies are not
  persisted, so there is no separate offline revalidation.
- **Post-run, measured**: billed output densities (2a at or under 380 tokens
  per target, ladder 500, escalated attempts 260), the 0.30 same-corpus
  ratio, input-per-call ceilings, and the cache read floors are ledger gates.

There is **no pre-billing ceiling on billed output tokens** on this
transport: the CLI exposes no `max_tokens`, and hidden reasoning shares the
billed output. The 286-tokens-per-target figure is a projection on measured
block sizes, cross-checked by an independent reconstruction of the call plan
but sharing the same block-size basis; it becomes a measured result only when
the bounded live pilot runs. No post-change enhancement run has happened; the
only live calls in this engagement were the 28 probe calls.

## 5. Verification of this branch

- Full suite green in the worktree (2,194 passed before this final pass;
  final counts in the commit gate, which now runs the suite before
  committing).
- The audit against the v2 baseline run FAILS on exactly the measured
  defects, which is the correct result for the "before" run; the preflight
  PASSES against the real store on the current code.
- The golden reference run is regenerated deliberately at each contract-shape
  change, per its own policy.

## 6. Corrections to the earlier revision of this report

The cross-session review falsified four claims, all mine: that P5 caching
worked (it was structurally broken by the ladder schema); that trigger
classes came from the `lacked` self-report (unimplemented at the time); that
the 286 projection was derived two independent ways (shared block-size
basis); and that output was "all deterministically gated" (conflated the
three guarantee tiers of section 4). It also identified the writer this
report had called unidentified: the concurrent session was the other
commissioned effort. The earlier snapshot-completeness claim was also
overstated: the import missed the base session's two untracked test files,
recovered in this pass.

## 7. Remaining, and deliberately gated

- **Trigger-class routing activation** waits on measurement M-R1 (replaying
  the v2 context-class population through the repair path, bound $4). The
  vocabulary, telemetry, and repair prompts are in; the routing switch is
  not, per the no-regression protocol.
- **Work orders' no-demotion replay** (bound $3) before the next full build.
- **Probe P-B** (appended-file size ceiling at 30k and 200k tokens) before
  the p5 corpus-in-prefix interim is trusted beyond digest scale.
- **The p5 digest ablation** the Orchestration delta gates on (one
  determination call over the v2 artifacts with the digested prompt, diffed
  against the recorded v2 verdict on the criteria table) before the digest
  is trusted on a full run.
- **The adjudicator remeasurement** (about $2.60) now that the judge can see
  fact evidence, against the 53.2% baseline.
- **The bounded live quality pilot**, both sessions' independently reached
  conclusion, as the release gate before any full subject run.

## 8. Process record

Two sessions worked one commission. The concurrent session built the base
implementation in the shared checkout (its final state is preserved verbatim
in `data/concurrent-session-snapshot-2026-08-26.patch` and
`data/concurrent-session-compact-2026-08-26.py`); this session imported that
state into an isolated worktree as its attributed base, corrected and
extended it per the persona deltas, and each session then reviewed the
other's work. The review in both directions found real defects that neither
suite caught alone, which is the strongest argument the process record
offers: the seam neither session's tests could see was found by the other
session reading the code.
