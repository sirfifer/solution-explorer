# Independent validation report: unified enrichment economics implementation

Date: 2026-08-26 (US/Pacific)

Reviewer: independent follow-up session

Reviewed commit: `e1dbb70df6e7bc1e1202ccb9d0e59f09dde7d1ab`

Live subject: the repository's 8-component, 1-relationship polyglot fixture
Live allowance consumed: $2.1505 API-equivalent across 15 invocations

## Executive verdict

**STOP: do not launch UnaMentis or VS Code yet.**

The unified implementation is substantially better than the system it replaces.
Its deterministic architecture is coherent, its zero-cost call plans pass, its
cache boundary works when a call succeeds, and—most importantly—its adjudicator
correctly caught a serious quality defect in the pilot rather than blessing it.

It is not ready for a full corpus run. The first bounded live pilot exposed a
production-only failure mode that the injected test seam did not model:

1. The Sonnet component call failed structured-output validation because one of
   eight entries contained the harmless but schema-unknown key `name`. The whole
   eight-component response was lost.
2. Both Opus repair batches failed at the same transport/schema boundary.
3. All eight components consequently fell through to Fable.
4. Fable grounded them mechanically, but independent adjudication rejected 3 of
   the 4 claims it sampled as unsupported by their cited evidence.
5. P5 correctly returned `not-done`, while the process still exited zero and
   every phase was reported `OK`.

That combination fails both non-negotiables of this engagement: quality is not
yet demonstrated, and the cheap rung is not carrying the work. Expanding the
sample would spend more allowance to reconfirm a failure already established at
the smallest useful scale.

## What was reviewed

- The final engagement report, both persona implementation deltas, validation
  plan, orchestration and prompt specifications, cache probe record, and prior
  post-run assessment.
- The unified commit and all 31 files changed by it, with particular attention
  to the production transport, compact schemas, prompt splitting, ladder state
  machine, evidence validator, work-order descent, audit predicates, run report,
  and CLI controls.
- The committed tests and the live Claude CLI boundary, not only the injected
  invoker seam.

The reviewed branch and its remote both resolved to `e1dbb70`; the worktree was
clean before this review's contained corrections.

## Deterministic verification

### Static and automated checks

- Targeted enrichment suite before review changes: **139 passed**.
- Review-specific ladder/control/coverage suite after corrections: **57 passed**.
- Repository-wide Ruff command: **pass** after correcting one unrelated
  ambiguous variable in `scripts/build-quality-report.py`.
- Full suite after all contained corrections: **2,210 passed, 4 skipped,
  1 expected failure** in 149.93 seconds. An earlier concurrent run's only
  teardown error was caused by this review's temporary fixture projection
  appearing while that suite was in flight; it was removed immediately and the
  suite was restarted in isolation.

### Zero-cost replay preflight

Both real stores pass the deterministic plan checks: one byte-stable prefix per
target kind, every response projection under the G2 dispersion limit, and every
prompt under the context warning bound.

| Subject | Components | Relationships | Planned rung-2a calls | Projected billed output |
|---|---:|---:|---:|---:|
| UnaMentis iOS | 168 | 458 | 32 (14 component, 18 relationship) | 179,062 tokens |
| VS Code | 569 | 5,453 | 231 (61 component, 170 relationship) | 1,146,472 tokens |

This proves the call planner and arithmetic. It does **not** prove that a live
model will satisfy the schema or that the CLI will preserve a rejected payload;
the pilot demonstrated that distinction.

## Contained defects corrected during review

These are narrow contract fixes, not changes to model policy or quality
thresholds:

1. `--retry-attempts` was parsed but ignored by the ladder path. It now reaches
   the real retry policy and has a CLI-to-provider regression test.
2. `entry_class_basis` was lost whenever an item climbed a rung, leaving the
   report's routing explanation null after successful repair. It now survives
   with the rest of the entry routing record.
3. Duplicate compact targets were rejected at rung 2a but silently accepted by
   higher rungs and work orders through last-write-wins normalization. Both paths
   now reject the ambiguous target and report an exact-set coverage violation.
4. Work orders had no exact response-coverage check. They now use the same
   deterministic coverage contract as the ladder.
5. The cache audit only examined schema-bound compact rows, even though P5 is
   intentionally cacheable without that schema. Cache grouping now covers every
   ledger row carrying a stable prefix hash.
6. The real repository-wide Ruff command failed on an ambiguous one-letter
   variable; that report/test utility issue is corrected.

The committed reference report was regenerated only for the expected routing
basis change.

## Live pilot

Command shape:

```text
analyze.py enhance tests/fixtures/polyglot \
  --ladder --max-parallel 1 --max-cost-usd 3 \
  --min-rounds 0 --max-rounds 0 --retry-attempts 1
```

The zero-round setting deliberately prevented work-order execution: this first
probe was intended to test generation, validation, reporting, and economics
before buying repair rounds. The default one-round pipeline may improve the
quality result, but it cannot repair the lower-rung transport loss without first
paying for the failed calls and the climb.

### Run result

| Measure | Result |
|---|---:|
| Invocations | 15 |
| API-equivalent cost | $2.1505 |
| Total billed output | 14,775 tokens |
| Ladder billed output | 3,610 tokens |
| Planned/final targets | 9 / 9 |
| Failed invocations | 3 |
| Terminal census | 8 grounded at Fable, 1 honest gap |
| Grounding disagreement | 3 of 4 claims unsupported (75%) |
| P5 verdict | `not-done` |
| Process exit | 0 |
| Independent audit | **FAIL** |

The run report is internally useful: it names the unsupported claims, produces
specific work orders, records the honest gap, and refuses a `done` verdict. The
problem is that these findings do not affect phase status or process success.

## Blocking findings

### B1. Structured-output rejection loses valid work and forces escalation

The Sonnet model returned all eight requested component entries. Entry 6 used
`name` alongside the required compact fields. The CLI's internal
`StructuredOutput` tool rejected the entire payload:

```text
Output does not match required schema:
/components/5: must NOT have additional properties
```

The process then exited 1 with empty stderr. The engine recorded only
`claude exited 1: `, zero tokens, no session id, and no response to salvage.
Because `result.ok` was false, the ladder's corrective JSON retry did not run;
because there was no structured status or transient marker, the transport retry
classified it as deterministic. Eight otherwise-produced entries became eight
E1 escalations.

This is an all-or-nothing batch failure caused by the enforcement mechanism, not
by absence of model work. It is exactly the kind of production seam that mocked
`InvokeResult(ok=True, ...)` tests cannot reveal.

Both Opus repair batches then failed:

- one emitted an ordinary JSON text response rather than invoking
  `StructuredOutput`;
- one invoked the tool with a placeholder root key and received required-root
  schema errors.

Fable succeeded on both terminal batches. Observed compact generation success
was therefore Sonnet 1/2 calls (only the relationship call), Opus 0/2, Fable
2/2. On component work it was Sonnet 0/1 and Opus 0/2.

Required remedy before another pilot:

1. Preserve actionable CLI failure detail and a transcript/session reference on
   schema rejection.
2. Treat a structured-output validation rejection as a bounded semantic repair,
   not as a blank deterministic transport failure.
3. Decide how to avoid losing an entire batch to one harmless alias. The live
   example supports accepting `name` as a bounded ignored alias, but a general
   solution should preserve strict byte bounds without making unknown cosmetic
   fields catastrophic.
4. Add subprocess-level tests for these exact CLI envelopes and exits.

### B2. Mechanical grounding is not sufficient grounding

The adjudicator's 75% disagreement is credible and specific, not stylistic. For
`services/api`, Fable made compound claims whose citations covered only parts of
the sentence:

- a `capabilities` fact and `port` fact did not establish that packaging came
  from `pyproject.toml` or that port 8000 was declared by docker-compose;
- `inbound_edges: 1` did not establish that this was the *only* component with
  an inbound edge, nor identify the caller and protocol;
- framework and edge-count facts did not establish component typing or the
  web-to-api HTTP source.

The current evidence validator proves that cited objects exist. It cannot prove
that every clause of a compound claim follows from those objects. P3 is the
correct place for that judgment and worked well here, but the result must feed a
hard completion gate and a validated repair round before the run can succeed.

### B3. Exit status contradicts the quality result

The command exited zero with all five phases marked `OK` even though:

- three invocations failed;
- the cheap and middle component rungs produced no accepted component work;
- the universal grounding criterion was `UNMET`;
- P5's verdict was `not-done`;
- the standalone audit verdict was `fail`.

Operational success and quality success need distinct, deterministic states.
At minimum, a completed run must return nonzero when the final determination is
`not-done` after its allowed rounds, when a required universal criterion is
unmet, or when the audit has a `fail` finding. A phase with failed model calls
may be `partial`, but it cannot be indistinguishable from an error-free `OK`.

### B4. The multi-turn predicate misclassifies schema handoff as agentic drift

All three successful schema-bound calls reported `num_turns: 2` and
`stop_reason: tool_use` despite `--max-turns 1`. Their Claude transcripts show
one model response invoking the CLI's internal `StructuredOutput` tool followed
by its tool-result handoff. No repository tool, browse, shell, or agent loop was
available (`--tools ""`).

The current meter and audit call this “agentic drift.” That diagnosis is false
for schema-bound calls. Preserve the raw turn count, but derive drift from
external tool/agent activity; for the current transport, the one internal
structured-output handoff is expected. Otherwise every successful hard-schema
call fails the audit by construction.

## What the pilot did validate

### Caching is real

The two Fable terminal calls shared an identical prefix. The first was cold; the
second read 12,962 cached tokens against a 2,455-token prefix estimate and wrote
only 5,021 tokens. Its API-equivalent cost fell from $0.4657 to $0.1937 while
answering four rather than five targets. This is direct live confirmation that
the repaired cache boundary works on the actual ladder path.

The audit's one cache-boundary failure came from the two blank Opus failures,
both of which recorded zero usage. It is evidence of the schema/transport
failure, not evidence that a successful repeated prefix missed cache.

### Output size control worked for delivered payloads

All three accepted compact responses stayed inside their deterministic UTF-8
byte budgets. Ladder billed output was 401 tokens per unique target, under the
500-token ladder gate. The rung-2a result of 24.6 tokens per target is unusable
as evidence because the component call failed and only the one relationship was
accepted.

### The learning channel is useful

The run preserved the honest gap, unsupported-claim reasons, escalation causes,
identity/edge/finding verdicts, and concrete work orders. P4 correctly proposed
moving cross-component claims to the relationship/root locations where their
evidence lives. This is the sort of exit data the commission required.

## Deterministic work that should move out of AI

The live disagreement exposes a clean deterministic boundary:

- Framework, language, port, component type, route/capability names, inbound and
  outbound edge counts, edge source/target/protocol, and the manifest/file that
  declares each fact are already analyzer facts. Generate those semantic atoms
  and their citations mechanically.
- Comparative words such as “only,” “all,” and “single” should require a global
  analyzer fact or be rejected. A local `inbound_edges: 1` fact cannot support a
  global uniqueness claim.
- Component help text can be assembled from deterministic factual clauses plus
  one AI-authored interpretation/next-step clause. The contract should reference
  the same atoms rather than asking the model to restate them with a narrower
  citation menu.
- Known cross-component facts belong on the relationship target. The model
  should not reconstruct the caller and protocol inside a component claim when
  the edge row already owns them.

This reduces tokens and improves quality simultaneously; it is not a trade of
quality for cost.

## Cost projection status

No defensible full-run price can be certified from this pilot because the
observed route was pathological: primary component generation failed, Opus
repair failed, and all component work moved to Fable. Linear extrapolation would
price the failure mode, not the intended architecture.

The zero-cost planner still supplies useful workload projections:

- UnaMentis rung 2a: 179,062 billed output tokens across 32 calls.
- VS Code rung 2a: 1,146,472 billed output tokens across 231 calls.

The pre-existing model places the VS Code ladder at roughly $67-$147 depending
on escalation and output dispersion; prior measured work warns that meta phases
sit above that ladder figure. Scaling that ladder band by the two subjects'
planned rung-2a output gives a purely arithmetic UnaMentis ladder band of roughly
$10-$23. Neither band is an authorization estimate until the blocking transport
and quality gates pass a bounded pilot. A final projection should be recomputed
from the successful rerun's actual Sonnet acceptance rate, escalation rate,
repair resolution, cache reads, P3 target counts, and work-order rounds.

## Required next gate

Do not repeat a full five-phase pilot immediately. First add production-boundary
tests and fix B1, B3, and B4. Then run this sequence:

1. One real 2a component call over 5-8 fixture components. It must either pass or
   preserve and repair a schema rejection without escalating the whole batch.
2. One real Opus repair call over 2-3 named failures. It must return an accepted
   delta with a usable transcript and error path.
3. The same tiny full pipeline with one improvement round. Required outcomes:
   zero blank failures, no false agentic-drift finding, final `done`, no unmet
   universal criterion, adjudicator disagreement at the agreed quality ceiling,
   and audit pass.
4. Only then run one UnaMentis partition, followed by two partitions if the first
   is clean. Recompute costs from those measurements before authorizing either
   full corpus.

## Artifacts

The temporary pilot artifacts are under:

```text
docs/quality/rearchitecture/data/pilot-2026-08-26/
```

They include `ledger.jsonl`, `progress.jsonl`, `report.json`, `REPORT.md`, the
subject brief, adjudication record, and synthesis record. The source store was a
fresh temporary extraction; no enrichment or projection in a user corpus was
modified.
