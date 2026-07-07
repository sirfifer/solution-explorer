# Remediation Work Plan

Date: 2026-07-02
Source: [AUDIT-2026-07.md](AUDIT-2026-07.md) (finding IDs referenced throughout)
Task detail: [TASKS.md](TASKS.md) (single source of truth for task status, acceptance criteria, and evidence)

This plan turns the July 2026 audit into an executable program of work. It is written to be handed to other model sessions (Claude Opus 4.8 and Claude Sonnet 5) with no additional context beyond these three documents and the repo itself.

---

## 1. Objectives

Four measurable end states, in priority order:

| # | Objective | Measured by |
|---|---|---|
| O1 | The pipeline tells the truth | Every workflow in this repo parses and runs green on push. The committed AI baseline is real. A test run leaves `git status` clean. No secret can reach a published artifact or log |
| O2 | The front-door promise is true | `npm view solution-explorer` and `pip index versions solution-explorer` (or PyPI page) return a real version. `npx solution-explorer <repo>` works on a machine that has never seen this project. Analysis output is uncapped by default or loudly warns |
| O3 | The review loop closes | Annotations survive reload. Back/forward navigation works. Split-mode detail panels render. Inbound `?file=&line=` deep links land on the right component |
| O4 | Claims, tests, and docs are trustworthy | Every README and PROJECT-OVERVIEW claim is true or removed. Every critical path named in the audit has a regression test that demonstrably fails on the pre-fix code |

## 2. Non-negotiable working principles

These apply to every task and every executor session. They exist because the audit found exactly these failure modes.

1. **Verify before editing.** Line numbers in the audit were correct on 2026-07-02 and will drift. Re-read the cited code and confirm the finding still reproduces before changing anything. If a finding no longer reproduces, record that in TASKS.md instead of "fixing" it.
2. **Every bug fix ships with a regression test that fails on the pre-fix code.** Prove it: stash or revert the fix locally, run the new test, confirm it fails, restore the fix, confirm it passes. Record the command and both outcomes in the task's Evidence field. A test that cannot fail is worse than no test.
3. **Tests assert observable behavior on the real code path.** Do not mock the unit under test. Do not reimplement the logic in the test and assert the reimplementation. Do not add snapshot tests without behavioral assertions. If a test would still pass with the bug reintroduced, it is rejected.
4. **No silent anything.** Truncation, fallback, skipped files, failed merges, and dropped data must warn loudly or fail. When a task touches such a path, add the warning even if the task is about something else.
5. **Do not commit the dirty root `architecture.json`.** It is pytest junk (F-CRIT-7) until task P0-1 regenerates it. Any executor who sees it modified should leave it alone unless their task says otherwise.
6. **Writing style.** All docs and comments follow `.claude/rules/writing-style.md`. In particular, never use em dashes or en dashes as sentence interrupters.
7. **One task, one commit (or a small series), referencing the task ID** (for example `P0-2: fix step-level secrets in live-monitor if-expressions`). Update TASKS.md status and Evidence in the same commit or the immediately following one.
8. **CI is the arbiter.** A task is not done until `pytest`, `ruff check analyzer/ tests/ scripts/`, and in the viewer `npm test -- --run`, `npm run lint`, `npx tsc -b`, and `npm run build` all pass, plus the task's own acceptance criteria.

## 3. Phase structure

Phases are gates, not suggestions. Do not start a phase until the previous phase's exit gate is green, with one exception: Phase 0 runs as two independent streams (see section 5) because the pipeline stream and the viewer stream share no files.

### Phase 0: Ground truth repairs

Goal: stop the repo lying to itself. Fix the four remaining deploy blockers, the security leak, and the broken split-mode rendering. Everything here is small and well localized; the risk is in getting the details exactly right, not in scope.

Tasks: P0-1 through P0-6 (see TASKS.md).

Exit gate, all measurable:
- `pytest tests/ -q` from the repo root leaves `git status --porcelain` empty.
- Root `architecture.json` contains a real `root_path` and real `ai_enhance` data (spot check three components).
- `actionlint` (or a push to a scratch branch) shows live-monitor.yml parses; a push to main runs it past the parse stage.
- `python3 scripts/merge-ai-enhancements.py` on an AI-enhanced baseline with fully drifted IDs exits nonzero with a readable diagnostic and does not modify the target file.
- A grep of a multi-repo run's output JSON for `x-access-token` finds nothing, with a test asserting it.
- In a local split-mode build, clicking a component renders its Files and Symbols tabs after the lazy fetch, verified in a browser and by a component test.
- Worker unit check: `cleanupOrphanedDetails` computes `detail-repo__unamentis.json` for id `repo:unamentis`.

### Phase 1: Make the front-door promise true

Goal: a stranger can use the product, and the two most damaging UX defects in the core loop are gone.

Tasks: P1-1 through P1-5.

Exit gate:
- A version decision is recorded (recommendation: reconcile to 1.2.0, since CHANGELOG already claims 1.x releases; 0.x after a claimed 1.1.0 release is a downgrade story). Tag pushed, release.yml green, `npm view solution-explorer version` and the PyPI page return it.
- On a clean machine (or empty npx cache), `npx solution-explorer@latest <some-repo>` produces a working viewer.
- Default npx and build.sh paths either use `--split` or print a truncation warning that names the flag to fix it; `stats.total_symbols` always equals the emitted array length in single-file mode, with the untruncated count exposed separately.
- Annotations survive a hard reload, verified by a test and by hand.
- Back then Forward returns to the same drill state, verified by a test that simulates popstate and by hand.

### Phase 2: Robustness and honesty

Goal: no silent data loss anywhere, no known perf cliffs, docs match reality, repo hygiene clean.

Tasks: P2-1 through P2-8.

Exit gate:
- Incremental run with a new root-level file and a new directory includes both in output (regression test).
- Self-analysis wall time on this repo does not regress, and the scanner reads each file at most once per scan (assert via a read-counter test or instrumentation).
- Status-overlay poll no longer deep-clones the tree; React Flow re-render count per poll is bounded (manual profile acceptable, note method in Evidence).
- Every claims-table row in AUDIT-2026-07.md section 7 marked FALSE, STALE-DOC, INACCURATE, or INCOHERENT is resolved: claim made true, or claim removed.
- `git ls-files` shows no coverage reports and no `packages/cli/dist` artifacts.

### Phase 3: Close the loop for real

Goal: the strategic gaps. Inbound file/line deep links, drift-tolerant AI preservation, and the test program for critical untested paths.

Tasks: P3-1 through P3-4.

Exit gate:
- `?file=<path>&line=<n>` opens the viewer drilled into the owning component with the symbol containing that line selected, covered by tests for found, ambiguous, and missing cases.
- The AI merge preserves enhancements across an ID-drift scenario (component renamed or reprefixed) via path-based fallback matching, with tests for exact match, drift match, and true removal.
- Each critical path named in F-VW-9 and F-AN findings has at least one behavioral test, and TASKS.md records the fails-before/passes-after evidence for each.

## 4. Model strategy

Default executor: **Claude Opus 4.8** for everything. It is sufficient for all tasks in this plan.

Use **Claude Sonnet 5** where the task is mechanical, fully specified by the task card, and protected by strong verification. Candidates are marked in TASKS.md. Summary of the split:

| Work type | Model | Rationale |
|---|---|---|
| State management, concurrency, effect ordering (P0-6, P1-3, P1-4, P1-5, P2-3) | Opus 4.8 | Subtle identity and timing semantics; the original bugs came from exactly this class of mistake |
| Security fix and its tests (P0-5) | Opus 4.8 | Small diff, but the failure mode is silent credential leakage; wants strongest reasoning on the test design |
| Workflow YAML and worker parity fixes (P0-2, P0-3, P0-4) | Opus 4.8, Sonnet 5 acceptable with the exact-change spec in the task card | Fixes are prescribed precisely; verification (actionlint, unit test) catches errors |
| Scanner performance refactor (P2-2) | Opus 4.8 | Behavior-preserving refactor across a 2,666-line class; needs judgment about identical output |
| Test authoring for critical paths (P3-1, and the regression tests inside every fix task) | Opus 4.8 | The anti-box-checking standard is the hard part; weak tests here defeat the whole program |
| Docs reconciliation (P2-5), repo hygiene (P2-6), lint cleanup (P2-7), template fixes | Sonnet 5 | Mechanical, checkable, low blast radius |
| Release execution (P1-1) | Opus 4.8 plus the human | Needs judgment plus repository secrets and an irreversible publish; the human pushes the tag |
| Deep links and drift-tolerant merge design (P3-2, P3-3) | Opus 4.8 | Genuine design work with cross-layer contracts |

Fable 5 is reserved for plan-level review only (see section 7), per the owner's direction.

## 5. Parallelization strategy

Quality outranks speed. The rule: **at most three concurrent sessions, each owning a disjoint file territory, each on its own branch.** Never let two sessions touch the same file in the same phase. When in doubt, run sequentially.

Recommended concurrency by phase:

| Phase | Streams | Contents |
|---|---|---|
| 0 | 2 | Stream A (pipeline plus Python): P0-1, P0-2, P0-3, P0-4, P0-5. Stream B (viewer): P0-6. No shared files |
| 1 | 1, then 2 | P1-1 (release) runs alone first because tagging wants a clean, decided state. Then Stream A: P1-2 (Python plus CLI). Stream B: P1-3, P1-4, P1-5 (viewer). P1-4 and P1-5 both touch App.tsx and the store, so they stay in the same session, sequenced |
| 2 | up to 3 | Stream A: P2-1, P2-2 (analyzer). Stream B: P2-3, P2-4 (viewer). Stream C: P2-5, P2-6, P2-7, P2-8 (docs, hygiene, misc). Docs stream waits for code streams to land so it documents the fixed reality |
| 3 | 2 | Stream A: P3-2 (viewer deep links) then P3-1 viewer tests. Stream B: P3-3 (merge redesign) then P3-1 Python tests. P3-4 (scanner decomposition) is optional and runs alone if attempted |

Mechanics:
- One git branch per stream per phase (for example `remediation/p0-pipeline`, `remediation/p0-viewer`). PR into main at phase end, or earlier per task if the change is independently shippable.
- Claude Code worktrees (or `git worktree`) keep concurrent sessions from stepping on each other's working tree.
- Merge order within a phase: pipeline/analyzer stream first, then viewer, then docs, to keep rebases trivial.
- After each PR, run `/code-review` on the diff before merge. Findings feed back into the same task, not new tasks.

## 6. Session handoff protocol

Every executor session starts from zero context. The handoff must survive that.

### 6.1 Executor prompt template

Paste this (adjusted per task) as the opening message of each executor session:

```
You are executing remediation work for solution-explorer.

Read, in order, before doing anything:
1. docs/remediation/WORK-PLAN.md (sections 2 and 6 are binding)
2. docs/remediation/TASKS.md, your assigned task(s): <TASK IDS>
3. docs/remediation/AUDIT-2026-07.md, the finding(s) your tasks cite
4. .claude/rules/writing-style.md

Then:
- Re-verify each finding against current code before editing (line numbers may have drifted).
- Implement the fix per the task card. Stay inside the task's file territory: <FILES/DIRS>.
- Write the required regression test. Prove it fails on the pre-fix code (stash the fix, run, unstash), and record both runs in the task's Evidence field.
- Run the full verification block in the task card plus the repo-wide checks
  (pytest, ruff; and for viewer work: npm test -- --run, npm run lint, npx tsc -b, npm run build).
- Update TASKS.md: status, Evidence (commands run and results), deviations if any.
- Commit with the task ID in the message. Do not commit architecture.json unless your task says to.
- Do not expand scope. If you find a new problem, add a line to the Discovered
  During Execution section at the bottom of TASKS.md and keep going.
```

### 6.2 Status discipline

TASKS.md is the single source of truth. Statuses: TODO, IN PROGRESS (with session/branch note), BLOCKED (with reason), DONE (only with Evidence filled), DROPPED (only with justification). Anyone resuming work reads TASKS.md first and trusts it over memory or chat history.

### 6.3 Phase-gate review

At each phase boundary, one short review session (any strong model; this is a good, cheap use of a fresh Opus session) does nothing but: run every exit-gate check in section 3, read the Evidence fields for the phase's tasks, spot-check two regression tests by reverting their fixes, and write a dated gate record at the bottom of TASKS.md. If a gate check fails, the phase is not done, regardless of task statuses.

## 7. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Executor "fixes" a finding that drifted and breaks working code | Principle 1 (verify before editing) plus regression-test proof requirement |
| Box-checking tests that pass regardless of the bug | Principle 2 and 3; phase-gate review reverts fixes to spot-check tests |
| Parallel sessions colliding | File-territory ownership per stream; worktrees; merge order rule |
| Release (P1-1) is irreversible and touches credentials | Human executes the tag push and owns npm/PyPI secrets; dry-run first (`npm publish --dry-run`, `twine check`); the model prepares, the human pulls the trigger |
| Downstream (UnaMentis) breaks while upstream changes land | Downstream is currently green and pinned to `@main`; batch upstream merges per phase and manually dispatch a downstream run after Phase 0 and Phase 1 merges, verifying at DEPLOYMENTS.md URLs |
| Scanner perf refactor changes output | P2-2 requires byte-identical output on a fixture repo before/after (modulo timestamps), asserted in a test |
| Plan documents rot like the last docs did | TASKS.md Evidence discipline; phase-gate records; the docs reconciliation task (P2-5) includes these documents |

## 8. What done looks like

All four objectives in section 1 verified by their stated measurements, all phase gates recorded as passed in TASKS.md, a tagged release live on npm and PyPI, both UnaMentis installations redeployed green with AI enhancements preserved, and a final claims re-audit (re-run the section 7 table from AUDIT-2026-07.md) showing every row VERIFIED or intentionally removed. At that point cut the release notes from CHANGELOG's Unreleased section and consider the audit closed.
