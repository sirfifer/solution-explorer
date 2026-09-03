# Handoff to Opus: the identity front door (option 1)

You are executing a fully specified, owner-approved body of work on the
SysCorpus (solution-explorer) codebase. Design and planning are complete.
Your job is execution, verification and honest reporting. Do not
re-litigate the design; where the spec is ambiguous, choose, and record the
choice in your report.

## Where you work

- Worktree: `/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway`
- Branch: `wt/ui-gateway-option1` (already created from `main` at 90775a0)
- Python: `.venv-wt/bin/python` in that worktree, already installed with
  tree-sitter. Never use the Homebrew `python3` for analyzer commands; it
  silently produces zero symbols.
- Viewer: `viewer/node_modules` already installed.
- Never `cd` out of the worktree. Never push. Never touch the owner's
  running demos on ports 5175 and 5176, and never open the canonical
  stores in `/Volumes/Studio/dev/solution-explorer/.testboard/live/` in
  place; copy them first (UG-7 says how).

## Read these first, in this order

1. `docs/research/ui-gateway/SHOW-ME-THE-APP.md` sections 2, 4 and 7: the
   findings, the layered proposal, and the owner's decisions. Read for
   intent; only option 1 is in scope.
2. `docs/research/ui-gateway/SPEC-OPTION1-IDENTITY-FRONT-DOOR.md`: the
   contract. It wins over every task file.
3. `docs/research/ui-gateway/PLAN-2026-09-03.md`: the task table,
   dependency order, schedule, budget and risks.
4. `docs/research/ui-gateway/tasks/UG-1.md`, `UG-2.md`, `UG-4.md`,
   `UG-6.md`, `UG-7.md`: one contract per task. `UG-5.md` is optional and
   only after UG-7 is green.
5. `docs/testing/RUN-2026-09-02-vscode-demo-gate.md`: the previous run
   record; UG-7 mirrors its shape and commands.
6. `.claude/rules/writing-style.md`: the house writing rule. No em dashes
   or en dashes anywhere, including code comments and commit messages.

## Order of execution

1. UG-1 (identity derive pass). Commit when its verify command is green.
2. UG-4 (viewer) and UG-6 (reorient script and crawl rules O9, O10) can run
   while UG-2 waits on UG-1. If you use Sonnet subagents for UG-6 or UG-5,
   hand them the task file verbatim plus the spec sections it cites, hold
   them to the scope fences, and verify their output yourself before
   committing it.
3. UG-2 (orientation additions) after UG-1 is committed.
4. UG-7 (integration): reproject both subjects from store copies, serve on
   5185 and 5186, crawl both with this worktree's harness, screenshots,
   golden refresh, run record, commit.
5. UG-5 only if UG-7 is green and time remains this week.

One commit per task, message starting with the task id, on the branch,
never pushed. The tree is clean between tasks.

## What each task must end with

Run the task's `verify_cmd` and paste its tail. Report: files changed, the
acceptance list from the task file with a verdict per line, any spec
ambiguity and the choice you made, and anything you could not verify,
stated as unverified. A "done" without the verify output is not done.

## Hard rules

- Deterministic only. No model calls anywhere in the analyzer or viewer.
  Enrichment is out of scope.
- Every new statement the viewer shows carries a provenance mark, and
  every form-factor record carries evidence naming a real file. Nothing is
  invented; when a detector finds nothing, the statement is null and the
  page falls back to today's behaviour.
- Scope fences in each task's `scope_allow` are the files you may change
  for that task. Files in `test_paths` are read-only for that task.
- Golden baselines (`tests/golden/**`) are refreshed only in UG-7, only
  after reading the diff, and only if every changed line is the intended
  addition.
- If a step is blocked by something outside the task (a missing store, a
  port in use, an install failure), stop that step, record it as blocked
  with the evidence, and continue with what does not depend on it.

## The one-line acceptance for the whole handoff

On the served VS Code bundle, the overview opens on "Visual Studio Code is
a desktop application for macOS, Windows and Linux, that also runs in a web
browser, is driven from a terminal by a command-line tool, and is extended
by plug-ins." with a chip per form factor and its evidence on click; the
portrait's "User interface" holds the workbench subtree; the recommended
path is the layering spine or the process model; and UnaMentis iOS still
passes 56/56 on the crawl. The run record proves it or says what is
missing.

## When you finish

Report in one message: the commit list on the branch (`git log --oneline
main..wt/ui-gateway-option1`), the path of the run record, the crawl
numbers for both subjects, the screenshot paths, cumulative token spend as
best you can state it, and the open items table from the run record. The
frontier session reviews from that message.
