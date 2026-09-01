# VS Code full-run recovery and continuation record

Recorded 2026-08-31 at 17:29 PDT. This is the authoritative handoff for the
interrupted VS Code enrichment run. It exists so another session can recover
the work without relying on chat history and, critically, without repurchasing
the completed bulk work.

Validated update, 2026-08-31 at 20:30 PDT: the resume implementation and paid-
transcript recovery described below are now implemented and tested. No provider
was invoked during this work. The full deterministic suite passes (2,353 passed,
4 skipped, 1 expected failure), and a disposable copy of the real 974 MB
checkpoint successfully reconstructed and recovered through the real evidence
validator. Use the observed continuation command in this document; the old raw
engine command is retained only as historical context.

## Stop condition

The run is stopped. No Solution Explorer enrichment process is active. Claude
weekly usage was reported at 99%, with the account resetting at 21:00 PDT on
2026-08-31. Do not invoke a provider before capacity returns and the resume
preflight below passes.

The run did **not** stop on its configured operator checkpoint. It stopped when
the systemic-failure circuit opened after repeated provider session-limit
failures. The historical `run/REPORT.md` says “run cost ceiling reached” because
it was generated before commit `23f4bea`; that sentence is false. Preserve the
historical report as evidence rather than editing it. The code now reports the
actual stop reason.

## Immutable identity

| Item | Value |
|---|---|
| Subject | VS Code |
| Source tree | `/Volumes/Studio/dev/.demo-corpus/vscode` |
| Source commit | `474a349ad5b745e512ef86b864d1c74f7264dd7a` |
| Source status at checkpoint | clean |
| Engine repository | `/Volumes/Studio/dev/solution-explorer` |
| Engine branch | `deterministic-gate-hardening` |
| Engine HEAD at checkpoint | `23f4bea` |
| Original run identity | `vscode-full-20260831-5f6a814` |
| Original snapshot time | `2026-08-31T21:55:02.477479+00:00` |

The engine branch is three commits ahead of
`origin/deterministic-gate-hardening` at this checkpoint. Those commits are:

1. `5f6a814` — make prompt caching evidence-driven.
2. `ebd4fcd` — keep repair output guards quality-safe.
3. `23f4bea` — report provider-circuit stops honestly.

Do not resume against a different VS Code commit. If the source SHA differs,
stop and restore the pinned tree rather than treating changed code as unfinished
work from this run.

## Durable artifacts

The mutable continuation store is:

`/Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/index.db`

The original run evidence is:

`/Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/run/`

A copy-on-write recovery checkpoint was created before any resume work:

`/Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/checkpoint-before-resume/`

The checkpoint contains both `index.db` and a complete copy of the original
`run/` directory. It is the rollback source. Never run enrichment against the
checkpoint copy directly.

Checkpoint SHA-256 values:

```text
0171e8db3f16b244c7ba672fbc4a25ad66bcef353f17d9828d4a22665420f8b4  index.db
e3c32537ab3c119e9cc7ef5e79bef9b40b57f3e78f0457a85202ad8519e4e47a  run/report.json
a60eeef5564307dec8a7f883fbdd897d9040521bb7f870d181028aa224acb4f3  run/ledger.jsonl
```

The mutable database file hash later differed because SQLite rewrote physical
pages, but this is not a logical-store difference: both mutable and checkpoint
stores pass `PRAGMA integrity_check`, carry the identical target-kind counts and
contract census, and produce the same SHA-256
`ceffd132c8d65b778cf4377d78ffc2a9191f59ea171a8e7dbc108ae5a0281c7a`
over every enrichment column ordered by `(target_kind, target_id)`.

SQLite `PRAGMA integrity_check` returned `ok`. The store has 12,049 enrichment
rows: 571 component products, 5,453 relationship products, 6,024 contract
states, and one subject brief. Thus every planned target has a durable contract
row; the unfinished work is explicitly represented rather than missing.

## Work completed and work remaining

The original run made 432 invocations and recorded $141.857663 in
API-equivalent subscription usage:

| Phase/model | Calls | API-equivalent |
|---|---:|---:|
| Orientation / Fable | 1 | $0.3719 |
| Bulk / Sonnet | 236 | $99.4786 |
| Escalation / Opus | 166 | $34.8224 |
| Residue / Fable | 29 | $7.1848 |
| Total ledger | 432 | $141.8577 |

There were 37 non-success ledger rows, but calling all 37 model failures is
incorrect. Twenty-five were paid, parseable model responses rejected solely by
our local 4,440-byte rule (21 Opus and 4 Fable). Twelve were genuine provider
capacity rejections saying the session limit had been reached and naming its
reset time; they returned zero tokens and zero cost. The retry classifier treated
those capacity responses as transient HTTP 429s and repeated every logical call
three times, which was useless. The current code recognizes an explicit
reset-bearing capacity response immediately, opens the resumable provider
circuit on the first one, and does not retry it.

Delivered response size is now efficiency telemetry, not an answer-validity
boundary. A response that passes JSON, compact-schema, exact-coverage and
evidence checks is retained even when verbose. Its overrun remains visible in
the ledger, Run Report and audit as a warning. This is the quality-first rule:
verbosity can trigger investigation, but cannot destroy valid paid work.

Exact durable target state:

| State | Components | Relationships | Total |
|---|---:|---:|---:|
| grounded@sonnet | 302 | 4,901 | 5,203 |
| grounded@opus | 242 | 178 | 420 |
| grounded@fable | 16 | 12 | 28 |
| honest-gap | 11 | 16 | 27 |
| escalate@sonnet | 0 | 166 | 166 |
| escalate@opus | 0 | 180 | 180 |
| **Total** | **571** | **5,453** | **6,024** |

Therefore 5,651 targets were grounded (93.8%), 27 were honest gaps, and exactly
346 relationships were unfinished at the interruption. No component was
unfinished.

### Deterministic transcript recovery result

All 25 locally rejected responses were recovered from their explicit Claude
session transcripts. Every response passed the closed prompt-menu, schema,
exact-ID-coverage and real evidence checks before the disposable store was
mutated. Two responses used the component repair envelope for relationship-only
menus; a closed alias translates them only when the menu contains relationships
exclusively, the IDs match exactly, and the entries contain only the relationship
`flow`/`why` questions. Adversarial tests prove that mixed menus, wrong IDs and
extra fields cannot take this path.

The 25 responses contained 109 attempts that were still relevant at the
checkpoint. Recovery grounded 62 relationships, converted 7 terminal attempts
to honest gaps, and preserved 40 evidence-valid escalations. Exact post-recovery
state on the disposable full-store copy:

| State | Total |
|---|---:|
| grounded@sonnet | 5,203 |
| grounded@opus | 482 |
| grounded@fable | 28 |
| honest-gap | 34 |
| escalate@sonnet | 66 |
| escalate@opus | 209 |
| escalate@fable | 2 |
| **Total** | **6,024** |

Thus 5,713 are grounded (94.84%), 34 are honest gaps, and 277 relationships
remain unfinished. Recovery closed 69 unfinished relationships without a model
call. It did not force the other 40 to pass; their evidence verdicts remain the
ordinary ladder's work.

The following work has not run and must still run after residue completion:

1. P3 adjudication and grounding/substitution spot checks.
2. P4 synthesis, tours, and lenses.
3. P5 determination against five VS Code-specific criteria and the universal
   criteria.
4. At least one forced improvement round, with a maximum of two rounds.
5. Any bounded work orders issued by determination, followed by targeted
   re-adjudication.
6. The adversarial audit and final publishability decision.
7. A cumulative exit report joining the original run’s economics and learning
   record with the continuation run.

The current partial output is not publishable. Determination is `UNKNOWN`, no
adjudication disagreement rate exists, and the audit correctly fails.

## Critical resume defect: fixed and validated

Do not use an engine checkout older than this validated change set.

At `23f4bea`, `enhance_cli.py` parsed `--update` but passed it only into the
classic `EnhanceConfig`. `_run_ladder_path()` does not pass it into
`LadderConfig`, `LadderConfig` has no update/resume field, and `LadderPhase.run()`
always starts with an empty `LadderOutcome` and executes rung 2a over every
partition. The comment saying “`--update` resumes, skipping everything already
enriched” is aspirational on the ladder path. Issuing that command now would
repurchase the 5,678 completed terminal outcomes instead of continuing them.

The banked data was sufficient. The current implementation now does all of the
following before a live call:

1. Add an explicit ladder resume/update flag to `LadderConfig` and wire the CLI
   `--update` flag into it.
2. On resume, load all `contract-state` rows with `ContractState.from_dict()`.
   Rebuild each in-memory payload from its component/relationship product row
   plus the `answers` stored on its contract-state row.
3. Require exactly the planned 6,024 target keys. Abort before provider work on
   a missing, duplicate, foreign, or source-commit-mismatched state.
4. Preserve the existing generated subject brief, or deliberately reload it
   into P1’s phase result. Do not buy a replacement orientation merely because
   the controller restarted.
5. Skip rung 2a entirely. After transcript recovery, send only the 66 remaining
   `escalate@sonnet` relationships to Opus. Do not send the 209
   `escalate@opus` or 2 `escalate@fable` relationships back through Opus.
6. After that Opus pass, send every still-escalating relationship to Fable.
   Evidence-valid Opus repairs reduce that scope; nothing is demoted merely to
   make the count smaller.
7. Rebuild and persist the final census, then proceed normally through P3–P5.
8. Write the continuation into a **new** run directory. Never append to or
   overwrite the original run evidence.
9. Preserve accounting lineage. The final exit report must distinguish the
   original 432-call/$141.857663 parent run from continuation calls while also
   presenting cumulative calls, tokens, failures, and API-equivalent usage.

## Zero-cost validation completed

Before provider capacity is used, the resume implementation has proved:

- Loading the checkpoint reconstructs exactly 6,024 states and the state table
  above.
- No grounded or honest-gap target is dispatched at rung 2a, Opus, or Fable.
- The `escalate@opus` and `escalate@fable` targets bypass Opus and remain
  eligible for Fable.
- The `escalate@sonnet` targets enter Opus; only their survivors enter
  Fable.
- A missing or extra contract row, changed source commit, malformed state, or
  missing product row aborts before the fake invoker is called.
- Fake-provider completion reaches 6,024 terminal states with zero unfinished
  targets and then executes P3, P4, and P5.
- The continuation report links its parent and keeps cumulative accounting
  separate from current-run budget enforcement.
- The current targeted and full deterministic suites remain green.

Do not weaken or convert unresolved items to honest gaps to make these tests
pass. Transport failure is not evidence about the code.

## Resume preflight after the account reset

Run these checks before any live invocation:

```bash
cd /Volumes/Studio/dev/solution-explorer

git -C /Volumes/Studio/dev/.demo-corpus/vscode rev-parse HEAD
# Must print: 474a349ad5b745e512ef86b864d1c74f7264dd7a

sqlite3 .testboard/live/vscode-full-20260831-5f6a814/index.db 'PRAGMA integrity_check;'
# Must print: ok

shasum -a 256 \
  .testboard/live/vscode-full-20260831-5f6a814/checkpoint-before-resume/index.db
# Must print the checkpoint hash recorded above.
```

Then verify Claude interactively and confirm that the weekly capacity has reset.
Do not use the enrichment run itself as the capacity probe.

Use the observed demo harness, not a raw `analyze.py enhance` command. This path
creates a Processing run, starts `LedgerWatch`, publishes completed-call and
in-flight state to `http://127.0.0.1:4200/#processing`, and writes continuation
evidence into a new directory:

```bash
.venv/bin/python scripts/demo-site.py enhance vscode \
  --resume-store /Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/index.db \
  --run-dir /Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/run-continuation-20260901 \
  --recover-ledger /Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/run/ledger.jsonl \
  --transcript-root /Users/ramerman/.claude/projects/-Volumes-Studio-dev-solution-explorer
```

The VS Code registry's 200 API-equivalent threshold is passed to the ladder as a
resumable runaway checkpoint, not `--max-cost-usd`. No wall-time stop is passed.
If the checkpoint is reached, in-flight answers bank and the control plane waits
for an operator decision; quality is not truncated. A healthy run that is simply
larger or slower than expected is resumed. A broken or explosively duplicating
run is cancelled only after the dashboard evidence establishes that diagnosis.

## Live stop/iterate policy

Watch the continuation ledger, progress stream, and control file. Stop early
and repair deterministically when a concrete systemic defect appears; continue
when a failure is isolated and later phases can add evidence.

The continuation is complete only when all of these are true:

- zero unfinished contract states;
- no provider-capacity or systemic transport failures;
- no target-conservation failure;
- P3 adjudication completed and disagreement is at or below its 20% gate;
- determination is `DONE`, not `UNKNOWN` or `NOT-DONE`;
- all required criteria are met or an explicit quality issue remains visible;
- the adversarial audit passes;
- the cumulative report includes useful learning, parser-first opportunities,
  efficiency/accounting data, and recommendations—not merely product prose;
- the generated viewer data is inspected before publication.

Output density remains a measured quality/efficiency gate. The partial run’s
escalations emitted 376.4 billed tokens per attempt against a 275-token gate.
The wider delivered-byte guard in `ebd4fcd` prevents valid detailed answers from
being destroyed, but does not waive this audit finding. Evaluate it on the
continuation rather than shortening answers blindly.

## Expected remaining scale

The earlier 45–90 minute / $30–$60 estimate omitted repository-scale P3 work
and is withdrawn. The latest deterministic VS Code projection contains 2,694
inferred edges and 2,322 findings. At the current quality-preserving group sizes,
P3 alone has at least 108 edge-verification groups, 93 finding-verification
groups, 6 identity groups, 25 grounding spot checks and at most 13 substitution
checks before any targeted recheck requested by an improvement round.

The best current estimate is **1.75–3 hours** and **15–24 percentage points of
the normal weekly general allowance** after reset. The percentage range uses the
only observed same-day anchor: the account moved from roughly 74% to 99% while
the interrupted run ledgered 141.86 API-equivalent units. Other Claude sessions
were active, so 25 points is an upper bound on what this run itself consumed,
not a universal dollar conversion. Take `/usage` immediately before and after
the continuation; those readings supersede this forecast. Fable has its own
displayed allowance and must be recorded separately.

This is an expectation, not a resource boundary. If the continuation is healthy
and takes more, it continues. The dashboard exists so the extra work is visible
and explainable rather than surprising.

## Evidence index

- Partial human report:
  `.testboard/live/vscode-full-20260831-5f6a814/run/REPORT.md`
- Machine report and audit:
  `.testboard/live/vscode-full-20260831-5f6a814/run/report.json`
- Complete invocation ledger:
  `.testboard/live/vscode-full-20260831-5f6a814/run/ledger.jsonl`
- Item-level progress:
  `.testboard/live/vscode-full-20260831-5f6a814/run/progress.jsonl`
- Persisted operator state:
  `.testboard/live/vscode-full-20260831-5f6a814/run/control.json`
- Subject brief:
  `.testboard/live/vscode-full-20260831-5f6a814/run/subject-brief.json`
- Immutable local rollback checkpoint:
  `.testboard/live/vscode-full-20260831-5f6a814/checkpoint-before-resume/`

The unrelated pre-existing working-tree changes
`docs/remediation/TASKS.md` and
`docs/quality/rearchitecture/AI-PROVIDER-PORTABILITY-RESEARCH-PLAN.md` are not
part of this recovery work and must not be overwritten or swept into its commit.
