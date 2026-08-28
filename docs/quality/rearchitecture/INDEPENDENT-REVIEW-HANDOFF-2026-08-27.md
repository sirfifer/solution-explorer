# Independent review handoff: enrichment readiness

Date: 2026-08-27 (US/Pacific)

## Paste-ready introduction for the reviewing session

Please perform a short independent review of the current uncommitted enrichment
work in `/Volumes/Studio/dev/solution-explorer`. Treat commit `2c01ee0` as the
baseline and inspect the actual working-tree changes; do not rely on the report's
conclusions. The owner requires uncompromised reader comprehension and grounded
quality first, with efficiency strictly second. Efficient output must still
retain enough evidence and operational data for Fable's final exit analysis to
identify deterministic-transfer opportunities, process improvements, and
next-run signals.

Please check the implementation against that standard, run the focused tests you
consider most probative, and report any correctness, quality, observability,
cache, output-economics, pause/resume, or learning-channel concern. Do not commit,
push, or run a paid model call. In particular, determine whether the new Fable
run-analysis seam is useful and evidence-bound rather than either starved or
verbose, and whether any limit acts as a quality dial instead of a distant
runaway guard.

## Current decision state

The tree is deterministically green, but paid work is intentionally paused for
this independent review.

- HEAD: `2c01ee0` (`Make enrichment quality and economics gates truthful`).
- The working tree contains the post-HEAD repair and validation work. It is not
  committed or pushed.
- Complete suite: **2,278 passed, 4 skipped, 1 expected failure** in 163.08s.
- Repository-wide Ruff: pass.
- `git diff --check`: pass.
- No UnaMentis repository or store data was sent to a model during this review.
- The next intended sequence, only after review and explicit data-sharing
  approval, is a bounded live validation of the revised Fable exit-analysis
  contract and then one preflighted UnaMentis partition.

## What changed after the unification commit

This is a routing summary, not a substitute for reading the diff.

1. **Paid-output conservation and truthful completion**

   - A schema-drift or partially invalid bulk response no longer forces the
     entire paid batch to be repurchased.
   - A partial work-order repair banks valid sibling changes without replacing
     the retained multi-sentence product with a repair delta.
   - Determination can settle `done` after a real improvement round when every
     predeclared criterion is met, while retaining additional useful work orders
     as exit-learning opportunities.
   - Unknown subject criteria, provider failures, output truncation, store/census
     divergence, and audit failure remain non-publishable.

2. **Grounding quality**

   - Compact answers can cite up to four exact evidence references.
   - P5 receives supported adjudicated claims needed to judge subject criteria,
     not only the failed examples.
   - Citation inference and repair handling were tightened around manifests,
     service declarations, parsing intent, negative/uniqueness claims, and
     partial repairs.
   - A later quality review removed fixture-specific forbidden phrases and the
     instruction that the safest repair was the shortest one. The operative rule
     is now general: every clause needs evidence, unsupported clauses are
     narrowed, and all supported useful meaning is preserved.

3. **Caching and efficiency accounting**

   - Cache reuse is evaluated at the actual stable-prefix transport boundary.
   - The audit tolerates a narrowly measured 1% character-to-token estimation
     difference while still failing real zero-read misses or prefix
     fragmentation.
   - Bulk, ladder, and escalation output densities use unique or attempted
     targets with the corrected denominators.
   - Delivered JSON byte limits are labeled honestly as structural/runaway
     protection; hidden provider reasoning is measured post-run because this CLI
     exposes no smaller per-call billed-token control.

4. **Run control**

   - Expected cost, post-run efficiency judgment, and runaway protection are
     separate concepts.
   - Persisted pause/resume/cancel state and dashboard decision support were
     added. A pause stops new dispatch, banks completed paid work, survives a
     restart, and supports resume without repurchase.

5. **Exit learning and continuous improvement**

   - The raw report already retained ledger rows, accounting, escalation
     economics, work orders and outcomes, adjudication, parser-first capability
     cards, identity flags, gaps, iterations, and scrub-safe lessons.
   - One final review found that Fable itself was not shown the measured run
     logistics. The current tree adds a compact operations digest to P5's
     uncached tail: calls, targets, model/phase buckets, input/cache/output
     tokens, response bytes, cost, wall time, retries, failures, output-budget
     events, escalation-trigger counts, and distinct parser-first cards.
   - P5 now returns `run_analysis`: a concise summary, evidence-based
     deterministic-transfer candidates with required validation, concrete
     process improvements with their basis, and signals to watch next time.
     Empty arrays are explicitly preferable to invented lessons.
   - The complete deterministic ledger and findings remain in `report.json`;
     the P5 digest samples at most 40 distinct parser cards but records the full
     count and never replaces the complete report collection.

## Most important files to inspect

Start here:

- `docs/quality/rearchitecture/POST-UNIFICATION-CANARY-REPORT-2026-08-27.md`
  — the live-canary record. Read its **Current validation addendum** first; the
  original stop verdict below it is retained as historical failure evidence.
- `analyzer/enrich/determine.py` — P5 contract, measured operations digest,
  model-analysis normalization, criterion settlement, and improvement loop.
- `analyzer/enrich/runreport.py` — authoritative report assembly, accounting,
  escalation economics, parser/identity learning channels, and rendered Run
  Analysis section.
- `analyzer/enrich/compact.py` — compact schema, exact validation, evidence
  conversion, product/contract single-sourcing, and partial-response salvage.
- `analyzer/enrich/prompts.py` — stable prefixes, evidence discipline, repair
  wording, and escalation prompts.
- `analyzer/enrich/workorder.py` — delta repair, partial banking, retained
  product conservation, and repair economics.
- `analyzer/enrich/ladder.py` — routing, transition ledger, escalation deltas,
  honest gaps, and terminal store/census conservation.
- `analyzer/enrich/pipeline.py` — metering, output/runaway tripwires, cache
  telemetry, persisted run state, and report/audit completion boundary.
- `scripts/enrichment-audit.py` — adversarial release gates and corrected cache
  and output-economics predicates.
- `scripts/control.py`, `scripts/testboard/dashboard.html`, and
  `scripts/testboard_emit.py` — operator pause/resume/cancel and decision packet.

Most probative tests:

- `tests/test_enrich_determination.py`
- `tests/test_enrich_compact.py`
- `tests/test_enrich_workorder.py`
- `tests/test_enrich_ladder.py`
- `tests/test_enrich_operability.py`
- `tests/test_enrichment_audit.py`
- `tests/test_testboard.py`
- `tests/test_enrich_cost_ceiling.py`

The deterministic reference output is:

- `tests/fixtures/enrichment-run/report.json`
- `tests/fixtures/enrichment-run/REPORT.md`

## Live evidence already collected

Latest successful polyglot run:

- Run directory: `/private/tmp/enrichment-postfix-polyglot16.JuAUR6/run`
- 48/48 provider calls succeeded.
- API-equivalent cost: $3.781031.
- 11/11 targets grounded.
- All eight predeclared criteria met.
- One real improvement round.
- Independent disagreement: 22.6% before repair, 9.7% after.
- Final determination: `done`.
- Fresh input 96 tokens; cache creation 237,999; cache reads 226,241;
  billed output 26,912; ladder output 4,035.
- Bulk output: 349.3 billed tokens per unique target.
- Ladder output: 366.8 per unique target.
- Escalation output: 96.5 per attempt, with only two attempts and therefore
  correctly below the release sample size.
- Zero delivered-byte violations and zero provider-call failures.
- Rerunning the current adversarial audit produces `verdict: pass` with no
  findings.

Important artifact caveat: that run's embedded `report.json` contains the older
audit result with one 29-token prefix-read shortfall. The 1% tokenizer-estimate
tolerance was corrected after the run, so the immutable live ledger is the same
but the current auditor now passes it. This is documented rather than silently
rewriting the paid artifact.

The new `run_analysis` output contract was added after this live run. Its prompt,
normalization, report rendering, reference artifact, and full pipeline are
deterministically tested, but the provider has not yet returned that field live.
That is the principal remaining validation boundary.

## UnaMentis preflight already completed

No provider call was made. A disposable copy of the real store passed planning
and context preflight:

- Source: `/Volumes/Studio/dev/unamentis-ios` (read-only during preflight)
- Source store: `/Volumes/Studio/dev/.demo-corpus/_out/unamentis-ios/index.db`
- Disposable store: `/private/tmp/enrichment-unamentis-partition1.6L0r4T/index.db`
- Preflight run: `/private/tmp/enrichment-unamentis-partition1.6L0r4T/preflight`
- Store census: 86 components, 458 relationships, 1,899 enrichment rows.
- Planner: 18 total partitions, capped to one for the first live run.
- Approximate orientation input: 5,493 tokens.
- Approximate synthesis input: 25,367 tokens.

The proposed first live partition is serial, one partition only, at most 25
adjudication checks, and one improvement round. Its expected cost is informational
only. Proposed runaway controls are a generous operator pause around $15 and an
emergency boundary around $30; they are intentionally far above the expected
few-dollar partition so they cannot tune answer quality.

## Suggested independent checks

At minimum:

```bash
git status --short
git diff --check
.venv/bin/ruff check .
.venv/bin/pytest -q \
  tests/test_enrich_determination.py \
  tests/test_enrich_compact.py \
  tests/test_enrich_workorder.py \
  tests/test_enrich_ladder.py \
  tests/test_enrich_operability.py \
  tests/test_enrichment_audit.py \
  tests/test_testboard.py
.venv/bin/python scripts/enrichment-audit.py \
  /private/tmp/enrichment-postfix-polyglot16.JuAUR6/run --json
```

The full suite is appropriate if the focused review finds no fundamental issue:

```bash
.venv/bin/pytest -q
```

Please inspect, rather than merely re-run tests, these invariants:

1. A failed compact batch cannot cause accepted paid targets to be repurchased.
2. A delta work order cannot erase previously retained reader prose or grounded
   sibling answers.
3. P5 receives enough measured evidence to make useful logistics and process
   recommendations without receiving the full repetitive ledger.
4. `run_analysis` cannot manufacture deterministic-transfer advice without a
   stated measured basis and validation step.
5. Raw evidence remains available even when the model analysis is absent or P5
   fails.
6. Expected-cost estimates cannot stop a healthy run; only a deliberately remote
   persisted runaway boundary can pause new dispatch.
7. Output and field bounds are structural safety margins, not instructions to
   make reader explanations terse.
8. Future stronger models retain freedom to produce better grounded
   interpretations within the same evidence contract.

## Questions for the reviewer

Please answer these directly:

1. Is there any remaining reason not to run one bounded live validation of the
   new Fable exit-analysis contract?
2. If that passes, is there any remaining reason not to run the preflighted
   single UnaMentis partition?
3. Did any repair improve efficiency by narrowing useful reader meaning,
   suppressing honest uncertainty, or starving the continuous-improvement
   channel?
4. Are any current limits close enough to observed healthy output that they
   could alter quality rather than catch a runaway?
5. What, if anything, should be fixed before paid validation rather than learned
   from that deliberately bounded run?

## Scope and safety notes

- Do not commit or push during this review.
- Do not edit or delete the live artifacts under `/private/tmp`.
- Do not run a paid provider call or send UnaMentis-derived data externally.
- Existing working-tree changes are intentional review material; do not discard
  or reset them.
- Separate a release-blocking defect from a useful future improvement. The
  immediate decision is whether the bounded provider validation is safe and
  informative, not whether the enrichment system can never improve again.
