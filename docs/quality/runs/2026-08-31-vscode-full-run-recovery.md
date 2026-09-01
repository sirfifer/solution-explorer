# VS Code full-run recovery and continuation record

Recorded 2026-08-31 at 17:29 PDT. This is the authoritative handoff for the
interrupted VS Code enrichment run. It exists so another session can recover
the work without relying on chat history and, critically, without repurchasing
the completed bulk work.

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

There were 37 failed invocations: 25 response-byte-guard failures (21 Opus and
4 Fable) and 12 Fable provider-capacity failures. The byte guard is repaired by
`ebd4fcd`; provider capacity requires the account reset.

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

Therefore 5,651 targets are grounded (93.8%), 27 are honest gaps, and exactly
346 relationships remain unfinished. No component remains unfinished.

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

## Critical resume defect: fix this before invoking Claude

Do **not** run the generic ladder command with `--update` yet.

As of `23f4bea`, `enhance_cli.py` parses `--update` but passes it only into the
classic `EnhanceConfig`. `_run_ladder_path()` does not pass it into
`LadderConfig`, `LadderConfig` has no update/resume field, and `LadderPhase.run()`
always starts with an empty `LadderOutcome` and executes rung 2a over every
partition. The comment saying “`--update` resumes, skipping everything already
enriched” is aspirational on the ladder path. Issuing that command now would
repurchase the 5,678 completed terminal outcomes instead of continuing them.

The banked data is sufficient for a true continuation; the missing piece is a
small deterministic loader and routing seam. Implement and test all of the
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
5. Skip rung 2a entirely. Send only the 166 `escalate@sonnet` relationships to
   Opus. Do not send the 180 `escalate@opus` relationships back through Opus.
6. After that bounded Opus pass, send every still-escalating relationship to
   Fable. The maximum initial Fable scope is 346 targets, about 70 five-target
   batches; successful Opus repairs reduce it.
7. Rebuild and persist the final census, then proceed normally through P3–P5.
8. Write the continuation into a **new** run directory. Never append to or
   overwrite the original run evidence.
9. Preserve accounting lineage. The final exit report must distinguish the
   original 432-call/$141.857663 parent run from continuation calls while also
   presenting cumulative calls, tokens, failures, and API-equivalent usage.

## Required zero-cost tests for the resume seam

Before provider capacity is used, the resume implementation must prove:

- Loading the checkpoint reconstructs exactly 6,024 states and the state table
  above.
- No grounded or honest-gap target is dispatched at rung 2a, Opus, or Fable.
- The 180 `escalate@opus` targets bypass Opus and remain eligible for Fable.
- The 166 `escalate@sonnet` targets enter Opus; only their survivors enter
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

After the resume seam and its tests land, use a new directory and an explicit
policy. The intended command shape is:

```bash
python3 analyze.py enhance /Volumes/Studio/dev/.demo-corpus/vscode \
  --store /Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/index.db \
  --ladder \
  --update \
  --run-dir /Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/run-continuation-20260831 \
  --max-parallel 4 \
  --pause-at-cost-usd 100 \
  --cache-policy adaptive \
  --min-rounds 1 \
  --max-rounds 2 \
  --spot-check-fraction 0.1 \
  --max-spot-checks 25
```

The `$100` value is a resumable disaster checkpoint, not a hard answer budget.
It is above the current $30–$60 continuation estimate. If reached, in-flight
answers bank and the control plane pauses before launching more work; quality is
not truncated. Raising it must be an informed operator decision based on the
dashboard and continuation ledger.

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

The best current estimate is 45–90 minutes and $30–$60 API-equivalent after
capacity returns. This is a range, not a ceiling. It covers the 346 unresolved
relationships, adjudication, synthesis, determination, and bounded improvement
work. Actual Opus acceptance and repair rates determine the result.

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
