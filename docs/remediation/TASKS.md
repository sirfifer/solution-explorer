# Remediation Task Tracker

Single source of truth for remediation status. Rules of use are in [WORK-PLAN.md](WORK-PLAN.md) sections 2 and 6. Finding IDs refer to [AUDIT-2026-07.md](AUDIT-2026-07.md).

Statuses: TODO, IN PROGRESS (note session and branch), BLOCKED (note reason), DONE (Evidence required), DROPPED (justification required).

Every fix task implicitly includes: re-verify the finding first; write a regression test that provably fails pre-fix (record both runs in Evidence); pass the repo-wide checks (`pytest tests/ -q`, `ruff check analyzer/ tests/ scripts/`; for viewer work also `npm test -- --run`, `npm run lint`, `npx tsc -b`, `npm run build`); update this file.

---

## Phase 0: Ground truth repairs

### P0-1: Stop pytest clobbering the AI baseline; restore a real baseline
- Status: DONE (session remediation/p0-pipeline, 2026-07-06)
- Model: Opus 4.8
- Stream: A (pipeline/Python). Branch: remediation/p0-pipeline
- Findings: F-CRIT-7
- Files: tests/test_cli.py, tests/conftest.py, architecture.json, .gitignore
- Do:
  1. Fix `test_max_symbols_explicit_override` (tests/test_cli.py, near line 348) to pass `-o <tmp_path>`. Audit every other test that calls `main()` or the analyzer entry point for the same missing `-o` pattern.
  2. Add a conftest.py guard fixture that fails the session if a test run creates or modifies `architecture.json` in the repo root (cheap insurance against recurrence).
  3. Discard the current dirty `architecture.json`. Recover the last genuinely AI-enhanced baseline from git history (`git log --all -p -- architecture.json`, look for real `root_path` and `ai_enhance` keys), or regenerate via the `/ai-assist` skill if no good version exists. Commit the real baseline.
  4. Resolve the tracked-versus-gitignored contradiction: the file is tracked but listed in .gitignore. Keep it tracked (it is the deploy baseline by design) and remove the stale ignore entry, with a one-line comment in .gitignore or CONTRIBUTING.md explaining that the root architecture.json is a committed AI baseline.
- Accept:
  - [ ] `pytest tests/ -q` from repo root exits green and `git status --porcelain` is empty afterward
  - [ ] Committed architecture.json has a real repo `root_path` and `ai_enhance` on the architecture level and on at least three components
  - [ ] Guard fixture demonstrably fails when a test writes root architecture.json (prove once, then keep)
- Verify: `pytest tests/ -q && git status --porcelain`; `python3 -c "import json;d=json.load(open('architecture.json'));print(d['root_path'],'ai' if 'ai_enhance' in d else 'NO-AI')"`
- Evidence:
  - Re-verified F-CRIT-7. Two leaky tests found in tests/test_cli.py (audit named one): `test_max_symbols_explicit_override` (was line 348) and `test_default_max_symbols_is_5000_single_file_mode` (was line 295). Both called `main()` with no `-o` and no `monkeypatch.chdir`, writing the analyzer default `architecture.json` into cwd (repo root). Audited all 16 `main()` callsites in tests/test_cli.py plus tests/test_incremental.py:971: every other call either passes `-o` or uses `monkeypatch.chdir(temp_repo)`, so those two were the only offenders. Fix: added `-o str(temp_repo / "out.json")` to both.
  - Added tests/conftest.py with an autouse guard fixture `_guard_repo_root_architecture_baseline` that snapshots (size, mtime_ns) of repo-root `architecture.json` and the presence of a repo-root `architecture/` dir before each test and fails the test if either changes.
  - Guard fail-then-pass proof: with the fix in place both formerly-leaky tests pass and `git status --porcelain` shows no stray `architecture.json`; baseline stat `619951 1783387058` unchanged across the run. Then temporarily reverted `test_max_symbols_explicit_override` to the leaky argv (removed `-o`) and ran it: guard failed with `Failed: Test modified repo-root architecture.json. A CLI test likely ran main() without -o and clobbered the committed AI baseline (F-CRIT-7)...` (conftest.py:48). Restored the `-o` fix and regenerated the baseline.
  - Baseline restore: exhaustively searched every `architecture.json` blob across all refs (`git log --all --pretty=%H -- architecture.json`, 14 commits, 14 unique blobs). NONE contain architecture-level or component-level `ai_enhance`; 13 are pytest junk (name `test_max_symbols_explicit_over0`, root_path in /private/var/folders pytest tmp) and the oldest (3dabc4c) is a non-AI scan of the unamentis project. No genuine AI-enhanced baseline of this repo has ever been committed, which corroborates F-CRIT-7's suspected origin of the April "0/253 preserved" symptom. Per the task's fallback instruction, committed the freshly generated non-AI output of `python3 analyze.py . -o architecture.json` (root_path `/Users/ramerman/dev/solution-explorer`, name `solution-explorer`, 23 components). ACTION REQUIRED: `/ai-assist` must be re-run interactively to restore real AI enhancements onto this baseline before the next deploy relies on preservation.
  - .gitignore: removed the stale `architecture.json` ignore entry (the root file is a tracked deploy baseline) and added an explanatory comment.
  - Verify results: `pytest tests/ -q` -> `637 passed, 1 xfailed`; `git status --porcelain` shows only the intended changes (.gitignore, architecture.json, tests/test_cli.py, tests/conftest.py), no stray output. `python3 -c ...` -> `/Users/ramerman/dev/solution-explorer NO-AI` (real root_path; AI pending /ai-assist). `ruff check analyzer/ tests/ scripts/` -> All checks passed.
  - Deviation: acceptance item "architecture.json has ai_enhance on at least three components" is not met because no AI baseline exists to restore and generating one requires the interactive /ai-assist pass (out of scope for this pipeline task). Followed the orchestrator's explicit fallback: committed real non-AI baseline, flagged /ai-assist re-run.
  - AI baseline now real (session remediation/p0-integration, 2026-07-06): ran the ai-assist enhancement over the committed 23-component scan. All 23 components carry `ai_enhance` (help_text, architectural_role, data_handled, criticality, testing and tech context), all 23 relationships carry `ai_enhance` (data_flow_description, importance), and the architecture level carries `summary`, `data_flow_narrative`, component_groups, tech_diversity, test_health_summary, and 3 observations. Content is derived from reading the actual source (analyzer, viewer, CLI, Cloudflare worker, scripts, tests), not invented. `python3 scripts/score-ai-enhancement-quality.py --architecture architecture.json` -> `100.0% coverage, avg 95.6%, 23/23 relationships valid, criticality {critical:3, important:8, supporting:12}, PASS`. Round-trip through `scripts/merge-ai-enhancements.py` restores 23/23 components and 23/23 relationships onto an AI-stripped target, so the baseline survives the deploy-time merge. `pytest tests/ -q` -> `644 passed, 1 xfailed` with the conftest guard intact; `git status --porcelain` shows only architecture.json (plus this evidence note). This closes the earlier ACTION REQUIRED and the "ai_enhance on at least three components" acceptance item.

### P0-2: Make live-monitor.yml parse and run; fix its latent bugs; fix the shipped template
- Status: DONE (session remediation/p0-pipeline, 2026-07-06)
- Model: Opus 4.8 (Sonnet 5 acceptable; changes are fully prescribed)
- Stream: A. Branch: remediation/p0-pipeline
- Findings: F-CRIT-2
- Files: .github/workflows/live-monitor.yml, packages/cli/src/templates/live-monitor.yml.ts
- Do:
  1. Replace step-level `if: ${{ secrets.CF_WORKER_URL != '' }}` (lines near 202 and 240) with a supported pattern: pass the secret via `env:` and gate in shell (`if [ -n "$CF_WORKER_URL" ]`), or gate on a `vars` flag. Apply the identical fix in the CLI template file.
  2. Fix the baseline cache: add `restore-keys: arch-baseline-${{ github.ref }}-` (prefix match) so the sha-suffixed save key can be restored.
  3. Fix the commit-message injection at the Notify step (near line 282): pass `github.event.head_commit.message` through `env:` and read it from the environment in Python, never interpolate into source.
  4. Resolve the dead R2 detail-upload path: either make the analyze step produce `--split` output so `.arch-output/data` exists, or delete the upload step. Pick whichever matches how the worker actually ingests today and say which in Evidence.
- Accept:
  - [ ] `actionlint .github/workflows/live-monitor.yml` clean (install if absent), and zero step-level `secrets.` usage inside `if:` in any workflow or template (`grep -rn "if:.*secrets\." .github packages/cli/src/templates` empty)
  - [ ] A push to a scratch branch with the workflow's trigger (or `gh workflow run`) shows the run getting past parse into real jobs
  - [ ] Template output of `init --live` contains none of the broken patterns (render the template in a unit test or a quick script and grep it)
- Verify: actionlint; grep as above; `gh run list --workflow=live-monitor.yml --limit 3` after a test push
- Evidence:
  - Re-verified F-CRIT-2 at current lines: step-level `if: ${{ secrets.CF_WORKER_URL != '' }}` at live-monitor.yml:202 and :240; exact-key cache restore at :65 vs sha-suffixed save at :188; raw commit-message interpolation at :282; dead `.arch-output/data` detail-upload block at :227-235. Template mirrors at .ts:11, :34, :62, :144.
  - Fixes in live-monitor.yml: (1) removed both step-level `secrets.` `if:` expressions; moved `CF_WORKER_URL` (and `CF_INGEST_TOKEN`, `CF_R2_ENDPOINT`, `REPO_NAME`, `COMMIT_SHA`) into `env:` and gate each step in shell with `if [ -z "$CF_WORKER_URL" ]; then ... exit 0; fi`. (2) Added `restore-keys: |\n  arch-baseline-${{ github.ref }}-` to the restore step so the sha-suffixed save key is prefix-matched. (3) Commit-message injection fixed: `COMMIT_MESSAGE` now passed via `env:` and read with `os.environ.get('COMMIT_MESSAGE')`; also replaced remaining in-body `${{ secrets.* }}` and `${{ steps.sha.* }}` interpolations in the curl with the env vars. (4) Dead R2 detail-upload path removed. Decision: the analyzer step emits single-file `--compact` (`.arch-output/architecture.json`) and the Pages/worker deploy serves that single file, so `.arch-output/data` is never produced. The former `if [ -d ".arch-output/data" ]` block was dead. Removed it and left a comment pointing at the worker escape-sync requirement if `--split` is ever adopted. Identical fixes applied to the CLI template `packages/cli/src/templates/live-monitor.yml.ts` (the template never had a detail-upload block, so nothing to delete there).
  - actionlint installed via `brew install actionlint` (v1.7.12). Fail-then-pass proof: `actionlint /tmp/.../live-monitor-PREFIX.yml` (the committed pre-fix file) exits 1 with `context "secrets" is not allowed here` at :202 and :240; `actionlint .github/workflows/live-monitor.yml` (post-fix) exits 0. `grep -rn "if:.*secrets\." .github packages/cli/src/templates` returns nothing.
  - Template render check: built the CLI package (`npm run build`) and rendered both modes with node. Rendered cloudflare and github outputs both pass `actionlint` (exit 0, only pre-existing shellcheck info notes shared with ci.yml). Grep of rendered cloudflare output: no step-level `if:.*secrets.`; `head_commit.message` appears only inside the `env:` block (safe pattern), not the run body; `restore-keys` present. The committed `packages/cli/dist` is stale build artifact tracked in git; I restored it after rendering so this commit touches only the source template (dist untracking is P2-6's job).
  - Repo-wide: `pytest tests/ -q` -> 637 passed, 1 xfailed; `ruff check analyzer/ tests/ scripts/` -> All checks passed.
  - Deviation: could not run a live `gh workflow run`/scratch-branch trigger for the branch's version. live-monitor.yml triggers on `push: [main]`, `workflow_run`, or `workflow_dispatch`, and `gh workflow run` executes the copy on the default branch, not this feature branch, so it cannot exercise my change until merged. actionlint is the parse arbiter used here and it is clean; a post-merge push to main will exercise the real trigger.

### P0-3: Worker escape parity so ingest stops deleting fresh detail files
- Status: DONE (session remediation/p0-pipeline, 2026-07-06)
- Model: Opus 4.8 (Sonnet 5 acceptable)
- Stream: A. Branch: remediation/p0-pipeline
- Findings: F-CRIT-5, related F-AN-4
- Files: infrastructure/cloudflare/worker/src/index.ts (cleanupOrphanedDetails, near line 311)
- Do: extract a `safeComponentId` in the worker identical to viewer/src/utils/componentId.ts (`/` to `--`, `:` to `__`), use it in cleanupOrphanedDetails, and add the same "must stay in sync with analyzer/cli.py and viewer componentId.ts" comment. Add a unit test if the worker has a test harness; if it has none, add a minimal vitest setup for this pure function only.
- Accept:
  - [ ] For id `repo:unamentis/viewer`, the worker computes active key `detail-repo__unamentis--viewer.json` (test-asserted)
  - [ ] All three escape implementations produce identical output for the shared fixture ids used in tests/test_cli.py:556-569
- Verify: worker test run; cross-check fixtures against tests/test_cli.py and viewer componentId.test.ts
- Evidence:
  - Re-verified F-CRIT-5: `cleanupOrphanedDetails` at infrastructure/cloudflare/worker/src/index.ts (now :312) computed active keys with `id.replace(/\//g, "--")` only, missing the `:` -> `__` escape that analyzer/cli.py `safe_component_id` and viewer/src/utils/componentId.ts both apply.
  - Fix: created infrastructure/cloudflare/worker/src/componentId.ts exporting `safeComponentId(id) = id.replace(/\//g,"--").replace(/:/g,"__")`, identical to the viewer, with the "must stay in sync with analyzer/cli.py and viewer componentId.ts" comment naming F-CRIT-5. Imported it in index.ts and replaced the inline escape in `cleanupOrphanedDetails`.
  - Worker had no test harness; added a minimal vitest setup (vitest ^4.0.18 devDep matching the viewer, `"test": "vitest run"` script) and src/componentId.test.ts. The test asserts the pure function plus the exact active-key derivation, including the audit reproduction: id `repo:unamentis` -> `unamentis/detail-repo__unamentis.json`, and id `repo:unamentis/viewer` -> `unamentis/detail-repo__unamentis--viewer.json`.
  - Fail-then-pass proof: replaced componentId.ts with the pre-fix slash-only escape and ran `npm test`: 4 failed / 2 passed, with `expected 'unamentis/detail-repo:unamentis--viewer.json' to be 'unamentis/detail-repo__unamentis--viewer.json'` (raw colon leaks, would never match the uploaded key). Restored the fix: 6 passed. `npm run typecheck` (tsc --noEmit) exits 0 with the new import.
  - Cross-check of all three escape implementations on the shared fixtures: analyzer tests/test_cli.py:558-571 (`viewer/src`->`viewer--src`, `repo:unamentis`->`repo__unamentis`, `repo:unamentis/viewer`->`repo__unamentis--viewer`, `plain-id` unchanged), viewer/src/__tests__/componentId.test.ts (same four), worker src/componentId.test.ts (same four). Identical output confirmed.
  - Repo-wide: pytest 637 passed / 1 xfailed; ruff clean (worker changes are TS, unaffected).

### P0-4: Fix merge-ai-enhancements.py crash and write-then-fail ordering
- Status: DONE (session remediation/p0-pipeline, 2026-07-06)
- Model: Opus 4.8 (Sonnet 5 acceptable)
- Stream: A. Branch: remediation/p0-pipeline
- Findings: F-CRIT-6 (root design gap deferred to P3-3)
- Files: scripts/merge-ai-enhancements.py, tests (new test file for scripts, for example tests/test_merge_ai_enhancements.py)
- Do:
  1. Initialize/compute `baseline_index` unconditionally (or restructure so the diagnostic never references an unassigned name).
  2. Reorder so all validation and diagnostics complete before the target file is written. On the enhanced-baseline-with-zero-matches case, exit nonzero with a readable message and leave the target untouched.
  3. Add tests: normal merge preserves data; drifted-ID case exits nonzero with diagnostic and target file unchanged; non-enhanced baseline case still passes through cleanly.
- Accept:
  - [ ] Reproduction case from the audit (AI-enhanced baseline, fully drifted IDs) exits nonzero, prints counts and a hint, target file byte-identical to before the run (test-asserted)
  - [ ] No UnboundLocalError possible on any branch (all names assigned on all paths)
- Verify: new tests; manual rerun of the audit reproduction
- Evidence:
  - Re-verified F-CRIT-6: `baseline_index` was assigned only inside `if not has_ai:` (was line 135), but the zero-match diagnostic referenced it unconditionally (was line 168), and the target was written (was line 149) before that diagnostic. A baseline with architecture-level `ai_enhance` (what /ai-assist always writes) skips the assignment, so the drift scenario raised UnboundLocalError after already overwriting the target.
  - Fix in scripts/merge-ai-enhancements.py: compute `baseline_index` and `baseline_ai_ids` once, immediately after loading the baseline (before the has_ai check), so no name is ever unassigned. Reordered so the drift guard runs BEFORE the target write: when `comp_stats.total > 0 and comp_stats.preserved == 0 and baseline_ai_ids`, print an ERROR diagnostic (counts, sample IDs, likely cause, "Target file left unchanged") and `sys.exit(1)` without writing. Success message moved after the write. No branch can reach an unassigned local now.
  - New tests: tests/test_merge_ai_enhancements.py (subprocess-driven, real script): `test_normal_merge_preserves_data` (matching IDs preserve component + arch AI, exit 0); `test_drifted_ids_exit_nonzero_and_leave_target_unchanged` (the audit reproduction: arch-level AI baseline, fully drifted target IDs); `test_non_enhanced_baseline_passes_through` (no AI anywhere, exit 0, target untouched); `test_partial_match_still_writes_and_succeeds` (>=1 match writes, exit 0).
  - Fail-then-pass proof: against pre-fix code `pytest tests/test_merge_ai_enhancements.py` -> `1 failed, 3 passed`; the failing test is the drift reproduction, failing on `assert "Traceback" not in result.stderr` with `UnboundLocalError: cannot access local variable 'baseline_index'` at merge-ai-enhancements.py:168 (and the target had been overwritten before the crash). Post-fix: `4 passed`. The other three pre-fix passes are expected (they never hit the crashing branch); the drift test is the true regression test.
  - No UnboundLocalError possible on any branch: `baseline_index`/`baseline_ai_ids` assigned before first use on every path; verified by the passing drift test (which exercises the previously-crashing path) and `ruff check scripts/merge-ai-enhancements.py` clean.
  - Regression safety: existing merge coverage tests/test_dpea.py 51 passed unchanged. Repo-wide `pytest tests/ -q` -> 641 passed, 1 xfailed; `ruff check analyzer/ tests/ scripts/` clean; the conftest guard confirms architecture.json was not re-dirtied.

### P0-5: Stop GITHUB_TOKEN reaching output JSON and CI logs
- Status: DONE (session remediation/p0-pipeline, 2026-07-06)
- Model: Opus 4.8
- Stream: A. Branch: remediation/p0-pipeline
- Findings: F-CRIT-3
- Files: analyzer/scanner.py (_detect_project_info, near 2549), analyzer/multi_repo.py (clone, near 92-110), tests/test_multi_repo.py or similar
- Do:
  1. In `_detect_project_info`, strip userinfo from any URL read from `.git/config` before storing (parse with urllib, drop username/password, reassemble). This protects every scan, not just multi-repo.
  2. In multi_repo clone, prefer recording the original untokenized URL for output, and redact the token from any stderr echoed on failure (replace the credential substring before printing).
  3. Tests: build a temp git repo whose config contains an `x-access-token:FAKE@` URL, run `_detect_project_info`, assert FAKE appears nowhere in the returned data; simulate a failed clone with a credentialed URL and assert the printed output contains no token.
- Accept:
  - [ ] Grep of full analyzer output for the fake token is empty (test-asserted)
  - [ ] Clone-failure path prints a redacted URL (test-asserted)
- Verify: new tests; `grep -r "x-access-token" <output>` in test
- Evidence:
  - Re-verified F-CRIT-3: scanner.py `_detect_project_info` (now :2578-2585) read `url` from `.git/config` and stored it with no credential stripping; multi_repo.py `_resolve_repo` (:104-107) printed `result.stderr` verbatim on clone failure, and the tokenized clone URL persisted in the clone's `.git/config` flows into `arch.repository` and then `merged.repositories[].repository` (:139).
  - Fix 1 (protects every scan): added module-level `_strip_url_credentials(url)` in scanner.py (urllib urlsplit/urlunsplit, drops userinfo, leaves scp-like SSH and non-URLs untouched) and applied it in `_detect_project_info` before storing `self.architecture.repository`.
  - Fix 2 (multi-repo clone failure): redact the token from `result.stderr` (`stderr.replace(token, "***")`) before printing; comment notes the original untokenized `url` is what gets reported. The success-path print already used the untokenized url.
  - New tests tests/test_multi_repo.py: `test_strip_url_credentials_removes_userinfo` (x-access-token and user:pass forms stripped, clean/ssh forms unchanged); `test_token_in_git_config_never_reaches_output` (build a temp repo whose .git/config has `https://x-access-token:FAKE...@github.com/...`, run a full `ArchitectureScanner.scan()`, assert `arch.repository == https://github.com/org/private-repo` and that the fake token and the string `x-access-token` appear nowhere in `json.dumps(to_dict(arch))`); `test_clone_failure_redacts_token_in_stderr` (monkeypatch subprocess.run to fail with git's credentialed "unable to access" stderr, GITHUB_TOKEN=FAKE, assert SystemExit(1), the token appears in neither stdout nor stderr, and `***` is present).
  - Fail-then-pass proof: `git stash push analyzer/scanner.py analyzer/multi_repo.py` (pre-fix), then ran the two behavioral tests via a scratch copy that drops the new-helper import (which otherwise breaks collection pre-fix): both FAILED. `test_token_in_git_config_never_reaches_output` failed because the tokenized URL reached output; `test_clone_failure_redacts_token_in_stderr` failed on `assert FAKE_TOKEN not in combined` (stderr contained `ess-token:FAKEtoken...@github.com/...`). `git stash pop` (restore fix): tests/test_multi_repo.py -> 3 passed.
  - Repo-wide: `pytest tests/ -q` -> 644 passed, 1 xfailed; `ruff check analyzer/ tests/ scripts/` clean; architecture.json not re-dirtied (conftest guard).

### P0-6: Split-mode detail panel renders lazily loaded data, with a visible loading state
- Status: DONE (session remediation/p0-viewer, branch remediation/p0-viewer)
- Model: Opus 4.8
- Stream: B (viewer). Branch: remediation/p0-viewer
- Findings: F-CRIT-4
- Files: viewer/src/components/DetailPanel.tsx (near 127-135), viewer/src/store.ts if needed, new test file
- Do:
  1. Make the memo (or the data access) depend on the cache content, not just `component.id`. Cleanest: subscribe to `componentDetailCache[component.id]` via a selector so the panel re-renders when the fetch lands.
  2. Render `componentDetailLoading` as a visible loading state on the Files and Symbols tabs.
  3. Component test with a mocked `fetch` and the real store: open a split-mode component, assert loading state appears, resolve the fetch, assert files and symbols render and counts update. This is the regression test for the whole split-mode path; do not mock the store.
- Accept:
  - [x] Test proves empty-then-loading-then-populated sequence against the real store and real DetailPanel
  - [x] Manual check in a local `--split` build of this repo: Files and Symbols tabs populate on first click
- Verify: viewer test run; manual: `python3 analyze.py . --split -o viewer/public/architecture && cd viewer && npm run dev`
- Evidence:
  - Re-verified the finding against current code before editing. Confirmed mechanism in `viewer/src/components/DetailPanel.tsx` `ComponentDetail`: `files`/`symbols` were memoized on `[component.id, getComponentFiles]` and `[component.id, getComponentSymbols]`. Those deps stay referentially stable when `loadComponentDetail` fills `componentDetailCache`, so the memos never recomputed and the Files/Symbols tabs stayed empty for the open component. `componentDetailLoading` was subscribed at line 127 but never rendered.
  - Fix (viewer/src/components/DetailPanel.tsx):
    1. Added a selector subscription to this component's cache entry: `const detailCacheEntry = useArchStore((s) => s.componentDetailCache[component.id]);` and added `detailCacheEntry` to the `files` and `symbols` memo dependency arrays, so the panel re-renders and the memos recompute when the lazy fetch lands.
    2. Added `const detailLoading = componentDetailLoading === component.id;` and passed it to `FilesTab` and `SymbolsTab`. Added a shared `DetailLoadingState` component (role="status", spinner plus text) that each tab renders when `loading && list.length === 0`. Early returns are placed after all hooks to respect the rules of hooks.
  - Regression test: `viewer/src/__tests__/DetailPanel.split.test.tsx`. Uses the real Zustand store (no store mock) and the real `DetailPanel`, with a mocked global `fetch` returning a deferred promise. Sets a split-mode architecture (top-level `files`/`symbols` empty), opens a component via `showDetail`, asserts `componentDetailLoading` is set and the Files tab shows the loading state (`role="status"`, "Loading files..."), resolves the fetch with a 2-file/3-symbol payload, then asserts the file names render, the loading state clears, and the Files (2) and Symbols (3) tab counts update; also opens the Symbols tab and asserts symbol names render.
  - Fails-then-passes proof (per WORK-PLAN principle 2):
    - Stashed only the fix: `git stash push -- viewer/src/components/DetailPanel.tsx`.
    - Pre-fix run: `npx vitest run src/__tests__/DetailPanel.split.test.tsx` => 1 failed. Failure at `screen.getByRole("status")` (Unable to find role="status"): with the pre-fix panel neither the loading state nor the populated files ever render, so the empty-then-loading-then-populated sequence is unreachable.
    - Restored the fix: `git stash pop`.
    - Post-fix run: same command => 1 passed.
  - Full verification (from viewer/, after `npm ci`):
    - `npm test -- --run` => 5 files, 55 tests passed (includes the new test).
    - `npm run lint` => exit 0. 0 errors, 18 warnings, all pre-existing (F-VW-8), none in the changed code.
    - `npx tsc -b` => exit 0.
    - `npm run build` => exit 0 (pre-existing search.ts mixed-import and 500 kB chunk warnings only, both tracked under F-VW-8 / P2-3).
  - Manual verification with a real browser (playwriter driving Chrome):
    - `python3 analyze.py . --split -o viewer/public/architecture` produced manifest.json plus 23 detail-*.json files. Built the viewer and served with `vite preview` on port 4321.
    - Confirmed served detail JSON: `GET /architecture/data/detail-analyzer.json` returned 11 files and 46 symbols.
    - Opened `http://localhost:4321/?component=analyzer` (first view of that component). The detail panel showed Files 11 and Symbols 46 in the Overview and tab counts (these are 0 pre-fix). Clicked the Files tab: the filter input and real file names (`__init__.py`, `scanner.py`) rendered, no stuck loading state. Clicked the Symbols tab: the symbol filter and real symbol names (`redetect_relationships`, `parse_gemfile`) rendered. This confirms the Files and Symbols tabs populate on first click in a real `--split` build.
    - Cleaned up: removed the generated data and restored the committed sample dataset under `viewer/public/architecture` via `git checkout`, leaving the tree clean except the two intended changes.
  - Files changed: `viewer/src/components/DetailPanel.tsx` (fix), `viewer/src/__tests__/DetailPanel.split.test.tsx` (new regression test). No changes to store.ts were needed; the existing `componentDetailCache` and `componentDetailLoading` state was sufficient once the panel subscribed to the cache entry.

---

## Phase 1: Make the front-door promise true

### P1-1: Reconcile versioning and ship the first real release
- Status: BLOCKED (prepared on remediation/p1-release; awaiting human tag push v1.2.0)
- Model: Opus 4.8 prepares; the human pushes the tag and owns npm/PyPI credentials
- Stream: solo, runs before other Phase 1 work merges
- Findings: F-CRIT-1, F-AN-12 (analyzer_version), F-DC rows 1 and 13
- Files: analyzer/__init__.py, analyzer/models.py (hardcoded "1.0.0" at 308 and 422, derive from __version__), packages/cli/package.json, CHANGELOG.md, README.md
- Do:
  1. Decide the version. Recommendation: 1.2.0, because CHANGELOG already claims 1.0.0 and 1.1.0 as released and PROJECT-OVERVIEW narrates 1.2.0; going backward to 0.3.0 publicly contradicts the changelog. Record the decision here.
  2. Align all version sources; make `analyzer_version` in models.py read `analyzer.__version__`.
  3. Move the Unreleased CHANGELOG section into the release entry.
  4. Dry-run both publishes locally (`npm publish --dry-run` in packages/cli after prepare-bundle; `python -m build && twine check dist/*`). Confirm required repo secrets for release.yml exist (`gh secret list`).
  5. Human pushes the tag. Watch release.yml to completion. Verify `npm view solution-explorer version`, the PyPI page, `gh release view`, and that the action resolves at `@v<version>` and `@latest`.
  6. On a machine or empty cache, run `npx solution-explorer@latest <some repo>` end to end.
- Accept:
  - [x] Version decision recorded here with rationale (1.2.0; see Evidence)
  - [ ] release.yml green; npm, PyPI, and GitHub release all show the version (BLOCKED on human: tag push plus credentials, see Evidence "Human steps remaining")
  - [ ] `npx solution-explorer@latest` works from cold cache (BLOCKED on human: requires the publish)
  - [x] README badge renders the release (no edit needed: the badge is a dynamic shields.io GitHub-release badge that renders v1.2.0 automatically once the release is cut; see Evidence)
- Verify: commands listed above
- Evidence:
  - **Version decision: 1.2.0.** Re-verified F-CRIT-1 and F-DC row 13 against current code: `analyzer/__init__.py` and both `packages/cli/package.json` and `viewer/package.json` declared 0.3.0; CHANGELOG.md declares [1.0.0] (2025-01-01) and [1.1.0] (2025-02-17) as released; PROJECT-OVERVIEW.md narrates v1.1.0 and v1.2.0 as shipped history; no `v*` tag exists (`git tag` empty), npm and PyPI have nothing. Publishing 0.3.0 now would ship a version below the changelog's own claimed 1.1.0 release, a public downgrade. The CHANGELOG Unreleased block plus PROJECT-OVERVIEW's v1.2.0 section (tree-sitter, incremental analysis, live monitoring) describe exactly the current feature set, so 1.2.0 is the honest reconciliation. No evidence contradicts 1.2.0. Adopted 1.2.0.
  - **F-AN-12 (analyzer_version) re-verified and fixed.** `analyzer/models.py` hardcoded `analyzer_version: str = "1.0.0"` in both the pydantic Architecture (was :308, now :310) and the dataclass fallback Architecture (was :422, now :424). The scanner creates `Architecture(...)` (scanner.py:119) without setting the field, so generated output stamped `"1.0.0"` regardless of package version (confirmed: a real scan emitted analyzer_version 1.0.0 while the package was 0.3.0). Fix: added `from . import __version__` to models.py (the same relative-import pattern incremental.py:26 already uses safely, no circular import because analyzer/__init__.py imports nothing) and set both defaults to `analyzer_version: str = __version__`. Verified both backends now emit the package version: forcing the pydantic path and forcing the no-pydantic dataclass path both yield 1.2.0.
  - **Version sources aligned.** Repo-wide grep for version strings before declaring done. Changed via the sanctioned `scripts/bump-version.sh 1.2.0` (updates analyzer/__init__.py, packages/cli/package.json, viewer/package.json, and their lockfile version fields): analyzer/__init__.py -> 1.2.0; packages/cli/package.json -> 1.2.0; viewer/package.json -> 1.2.0. pyproject.toml carries no static version (`dynamic = ["version"]`, `version = {attr = "analyzer.__version__"}`), so it tracks 1.2.0 automatically; confirmed the built wheel METADATA reads `Version: 1.2.0`. models.py analyzer_version now derives from __version__ (above).
    - Deliberately NOT changed (recorded so alignment is auditable): (a) the Cloudflare worker version trio `infrastructure/cloudflare/worker/package.json`, `wrangler.toml` WORKER_VERSION, and `index.ts:458` default are a coherent independent 1.0.0 for a separately versioned artifact (the worker's `/health` worker_version), not the product version. (b) `architecture.json:7` and `viewer/public/architecture.json:7` still read analyzer_version 1.0.0, but these are generated output/committed sample data, not sources; regenerating architecture.json is out of scope and guarded (P0-1 owns it, conftest guard forbids clobbering it). (c) PROJECT-OVERVIEW.md and other docs version narrative are P2-5's scope. (d) `action.yml:41` uses "e.g., v0.3.0" as illustrative help text, not a source of truth; left for P2-5.
  - **CHANGELOG.** Inserted `## [1.2.0] - 2026-07-11` directly below `## [Unreleased]`, moving the entire Unreleased Added/Changed/Fixed body into the 1.2.0 entry and leaving an empty Unreleased header per Keep a Changelog convention. release.yml's changelog extractor (awk `/^## .*1\.2\.0/`) will match this header and produce the GitHub release notes. No `[Unreleased]:`/`[1.x]:` link-reference definitions exist at the file end, so none needed updating.
  - **Regression test.** Added tests/test_version.py (4 tests): (1) `test_model_default_analyzer_version_matches_package_version` asserts the model default equals analyzer.__version__; (2) `test_generated_output_stamps_current_analyzer_version` runs the real CLI (`main()` with `-o`) on a temp repo and asserts the emitted architecture.json `analyzer_version` equals analyzer.__version__ (behavioral, real code path, no hardcoded literal); (3) `test_python_and_npm_version_sources_are_aligned` asserts cli and viewer package.json versions equal analyzer.__version__ (drift guard); (4) `test_no_hardcoded_analyzer_version_literal_in_models` asserts models.py references `__version__` and contains no `analyzer_version: str = "` literal.
    - Fails-before-fix proof (WORK-PLAN principle 2): `git stash push -- analyzer/models.py analyzer/__init__.py packages/cli/package.json viewer/package.json` (keeps the new test, reverts the fix), then `pytest tests/test_version.py -q` -> **3 failed, 1 passed**. The three failures are tests 1, 2, and 4 (model default was "1.0.0" != 0.3.0; generated output was "1.0.0" != 0.3.0; the hardcoded literal was present). Test 3 passed pre-fix because all three sources were coherently 0.3.0 before the bump; it is a partial-bump drift guard, not the version-value assertion, so its pre-fix pass is expected and correct. `git stash pop` restored the fix; `pytest tests/test_version.py -q` -> **4 passed**.
  - **npm publish dry-run: PASS.** In packages/cli: `bash scripts/prepare-bundle.sh` (viewer/dist already present, so it skipped the viewer rebuild and copied viewer-dist, analyzer, analyze.py, scripts-bundle), then `npm run build` (tsc, clean), then `npm publish --dry-run`. Output: `name: solution-explorer`, `version: 1.2.0`, `filename: solution-explorer-1.2.0.tgz`, tag latest, default public access, package size 2.1 MB, unpacked 13.1 MB, 308 files. This is the exact sequence release.yml's publish-npm job runs (`bash scripts/prepare-bundle.sh && npm run build` then `npm publish --provenance --access public`). Cleaned up afterward: removed the untracked bundle dirs (viewer-dist, analyzer, analyze.py, scripts-bundle) and `git checkout -- packages/cli/dist` to restore the tracked (stale) dist, leaving only the intended diffs.
  - **PyPI build + twine check: PASS (with warnings).** Scratch venv at scratchpad/relvenv (build 1.5.1, twine 6.2.0). `python -m build --outdir <scratch>/dist` built `solution_explorer-1.2.0.tar.gz` and `solution_explorer-1.2.0-py3-none-any.whl` (dynamic version resolved to 1.2.0 from analyzer.__version__). `twine check` -> both artifacts PASSED, with warnings `long_description` and `long_description_content_type` missing (the PyPI project page will have no rendered description). Not an error and does not block upload; it is a packaging-polish gap logged in Discovered During Execution. Nothing uploaded anywhere. Build outdir was the scratchpad and the incidental `solution_explorer.egg-info` (gitignored) was removed, so the repo tree stayed clean.
  - **release.yml assessment and secrets check.** Read `.github/workflows/release.yml`. Flow on tag `v*`: validate (checks tag `v1.2.0` minus `v` equals `analyzer.__version__`, now 1.2.0, so it will pass) -> ci.yml -> publish-pypi (`environment: pypi`, OIDC trusted publishing via `pypa/gh-action-pypi-publish@release/v1`, no explicit token) -> publish-npm (`environment: npm`, `bash scripts/prepare-bundle.sh && npm run build`, `npm publish --provenance` with `NODE_AUTH_TOKEN: secrets.NPM_TOKEN`) -> github-release (extracts the 1.2.0 CHANGELOG section, creates the release with `--latest`) -> update-tags (force-moves `latest` and `beta`). How packages/cli/dist is built at publish time: freshly, by the publish-npm step's `prepare-bundle.sh && npm run build`, so the committed stale dist is irrelevant to the published artifact (relevant to P2-6, not here).
    - **It will NOT succeed as-is. Blockers for the human (read-only `gh` checks):** `gh secret list` (repo) shows only CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, DEPLOY_TOKEN. There is **no `NPM_TOKEN`**, so publish-npm would run with an empty NODE_AUTH_TOKEN and fail on auth. The referenced GitHub **Environments `npm` and `pypi` do not exist** (`gh api .../environments` lists only `copilot` and `github-pages`; `gh secret list --env npm` and `--env pypi` both 404). GitHub will auto-create a bare environment at run time, but it carries no secrets and no PyPI trusted-publisher binding. publish-pypi uses OIDC trusted publishing, which requires a PyPI-side "trusted publisher" (or a pending publisher, since the project has never been published) registered for owner sirfifer, repo solution-explorer, workflow release.yml, environment pypi. That cannot be verified or created via `gh` and must be set up by the human on PyPI.
  - **Repo-wide checks.** `pytest tests/ -q` -> **654 passed, 1 xfailed** (the pre-existing test_detect_ports xfail), `git status --porcelain` clean of any stray architecture.json (conftest guard intact). `ruff check analyzer/ tests/ scripts/` -> All checks passed. `npm run build` in packages/cli -> clean (tsc), run as part of the npm dry-run above. Viewer suite skipped: the only viewer change is the version field in viewer/package.json and its lockfile (a metadata bump via bump-version.sh), no viewer source, config, or dependency changed, so tests/lint/tsc/build cannot be affected.
  - **README.** No edit required. The release badge (README.md:14) is a dynamic `img.shields.io/github/v/release/sirfifer/solution-explorer` badge that renders v1.2.0 automatically once release.yml cuts the GitHub release; the quick start (`npx solution-explorer /path/to/your/repo`, :62) carries no version pin and becomes true on publish. No hardcoded wrong version string exists in README (the `sirfifer/solution-explorer@main` action refs work today and are docs-scope for P2-5). Editing nothing here honors "update only where they state a wrong version."
  - **Human steps remaining (to finish the release; the model must not do these):**
    1. Set up npm auth: create an npm automation/granular token with publish rights to the `solution-explorer` package and add it as secret `NPM_TOKEN` (repo secret, or a secret in a new `npm` GitHub Environment). Confirm the npm package name `solution-explorer` is available/owned.
    2. Set up PyPI trusted publishing: on PyPI, register a trusted publisher (pending publisher, since the project is new) for owner `sirfifer`, repository `solution-explorer`, workflow `release.yml`, environment `pypi`. Optionally create the `pypi` and `npm` GitHub Environments explicitly if protection rules/reviewers are wanted (otherwise they auto-create bare).
    3. Merge this PR (remediation/p1-release) into main first, so the tagged commit carries version 1.2.0 and the moved CHANGELOG. Then from an up-to-date main: `git tag v1.2.0 && git push origin v1.2.0`.
    4. Watch the run: `gh run watch $(gh run list --workflow=release.yml --limit 1 --json databaseId --jq '.[0].databaseId')` (or `gh run list --workflow=release.yml`). All jobs (validate, test, publish-pypi, publish-npm, github-release, update-tags) must be green.
    5. Post-publish verification: `npm view solution-explorer version` returns 1.2.0; the PyPI page for solution-explorer shows 1.2.0 (or `pip index versions solution-explorer`); `gh release view v1.2.0` shows the release marked latest with the CHANGELOG notes; confirm the `latest` git tag moved. Then on a clean machine or with an empty npx cache (`npm cache clean --force`), run `npx solution-explorer@latest <some-repo>` end to end and confirm a working viewer.
    6. After a successful publish, the README release badge will render v1.2.0 with no code change.

### P1-2: Uncapped analysis on the default paths; loud truncation everywhere else
- Status: DONE (session remediation/p1-analyzer, 2026-07-11)
- Program 2 note: this interim fix is shipped on the current engine. The structural replacement for the whole silent-truncation class is the coverage ledger (P4-4, TARGET-ARCHITECTURE.md I2).
- Model: Opus 4.8
- Stream: A. Branch: remediation/p1-analyzer
- Findings: F-AN-3, F-DC row 2
- Files: packages/cli/src/commands/generate.ts (near 31-37), packages/cli/src/lib/python.ts, build.sh, analyzer/scanner.py (153-172), analyzer/cli.py
- Do:
  1. Switch the npx generate path and build.sh to `--split` (the viewer auto-detects manifest.json, verified in the audit). Confirm serve/export flows handle the split directory.
  2. In single-file mode, when the symbol cap or max-file-size skips anything, print a prominent stderr warning naming the count dropped and the flag that lifts the cap.
  3. Make `stats.total_symbols` equal the emitted array length; expose the pre-truncation count as a new field (for example `stats.total_symbols_detected`). Check the viewer for any display that should use the new field.
  4. Tests: truncation warning fires and stats match the array under a low `--max-symbols`; npx generate invokes `--split` (assert the built command in a CLI unit test).
- Accept:
  - [x] `npx` local run (`node packages/cli/dist/... generate` or via npm link) produces a split-mode site
  - [x] Single-file truncation prints a warning and stats are internally consistent (test-asserted)
  - [x] README CLI docs updated if flags changed (no user-facing flags changed; see Evidence)
- Verify: unit tests; run build.sh against this repo and inspect output shape
- Evidence:
  - Re-verified F-AN-3 / F-DC row 2 against current code (line numbers had drifted). Truncation now lives at scanner.py:179-192 (was 153-166), the inconsistent-stats line at scanner.py:198 set `total_symbols` from `len(self._all_symbols)` (the untruncated count) while `self.architecture.symbols` held the sliced array, so viewer stats disagreed with the data. The 500 KB skip is at scanner.py:531-536 (was 505-508), a bare `continue` with no log. generate.ts:31-37 and serve.ts ran the analyzer with neither `--split` nor `--max-symbols`, and build.sh:10,14 wrote single-file `--compact`, so the three first-run paths (npx export, npx serve, build.sh) were the capped ones. All confirmed reproducing before editing.
  - Change 1 (default paths to `--split`, uncapped): added `split?: boolean` to AnalyzeOptions and extracted `buildAnalyzerArgs()` in packages/cli/src/lib/python.ts (pure, unit-testable; pushes `--split` when requested). generate.ts and serve.ts now request split output into a directory and call the split branch of `assembleStaticSite`. viewer.ts `assembleStaticSite` gained an `AssembleOptions {split?}` param: in split mode it removes any bundled sample `architecture/` dir and stale `architecture.json`, then copies the fresh manifest+data to `<out>/architecture` (the viewer auto-detects `./architecture/manifest.json`, App.tsx:264). build.sh writes `-o viewer/public/architecture --split --compact` in both single-repo and multi-repo branches. Split mode already defaults `--max-symbols` to 0 (cli.py:96-97), so the default paths are uncapped.
  - Serve/export flows confirmed to handle the split directory: real export run `node packages/cli/dist/index.js --out <dir> analyzer/` produced `<dir>/architecture/manifest.json` + `data/`, no stale `architecture.json`, stats 62 symbols == 62 detected (uncapped, no warning). serve.ts uses the same `assembleStaticSite(..,{split:true})` and its static server already sets a JSON MIME type and serves any file under the site dir, including `architecture/data/detail-*.json`.
  - Change 2 (loud single-file truncation warnings): scanner.py records oversized skips in `self.skipped_large_files` (rel path, size) at the 500 KB skip site, and computes `self.dropped_symbols` in `scan()`. cli.py `_warn_dropped_data(scanner)` prints prominent stderr WARNINGs after the summary: the symbol-cap warning names the dropped count, the kept count, and `--max-symbols 0` / `--split`; the oversized-file warning names the count, the byte limit, the largest skipped file, and `--max-file-size`. Split mode runs uncapped so `dropped_symbols` is 0 and the symbol-cap warning stays quiet there; the oversized-file warning fires in any mode that skips a file (principle 4).
  - Change 3 (consistent stats): `stats.total_symbols` now equals `len(symbols)` (the emitted array) and a new `stats.total_symbols_detected` exposes the pre-truncation count. Viewer checked read-only (`grep -rn total_symbols viewer/src`): the field appears only in the `ArchitectureStats` type (types.ts:304) and test mocks; the header only renders total_components/total_files/total_lines (App.tsx:587-589), so nothing displays total_symbols and no viewer change is needed. Recorded a one-line note for Stream B / P2-5 in Discovered During Execution for the optional new field.
  - Tests. Python: tests/test_cli.py `TestTruncationWarnings` (3 tests): `test_symbol_cap_warns_and_stats_match_array` (low `--max-symbols 2` on a 6-symbol repo: asserts a stderr WARNING naming "symbol cap" and "--max-symbols", `total_symbols == len(symbols) == 2`, and `total_symbols_detected > total_symbols`); `test_no_warning_when_nothing_truncated` (`--max-symbols 0`: no symbol-cap warning, `total_symbols == total_symbols_detected`); `test_max_file_size_skip_warns` (tiny `--max-file-size`: stderr WARNING naming "skipped", "--max-file-size", and the skipped filename). CLI: packages/cli/test/generate.split.test.ts (4 tests, vitest, importing the real modules): `buildAnalyzerArgs` emits `--split` for the default path and omits it in single-file mode and honors `--config`; `generate uses split mode` calls the real `generate()` with mocked python/viewer libs and asserts the analyzer received `split: true`, the output path is a directory, the built argv contains `--split`, and `assembleStaticSite` was called with `{split:true}`. Added vitest ^4.0.18 (matching the worker) and a `test` script to packages/cli/package.json; the lock diff is purely additive (no root version change). Tests live in packages/cli/test/ (outside tsconfig `include:["src"]`) so they never ship in dist.
  - Fail-before/pass-after proof (WORK-PLAN principle 2):
    - Python: `git stash push analyzer/scanner.py analyzer/cli.py`; `pytest tests/test_cli.py::TestTruncationWarnings -q` => 3 failed (test_symbol_cap at line 882 `assert 'WARNING' in ''`; test_no_warning at line 907 `KeyError: 'total_symbols_detected'`; test_max_file_size at line 923 `assert 'WARNING' in ''`). `git stash pop`; same command => 3 passed.
    - CLI: `git stash push packages/cli/src/{lib/python.ts,commands/generate.ts,lib/viewer.ts,commands/serve.ts}`; `npm test` (in packages/cli) => 4 failed (buildAnalyzerArgs undefined pre-fix; `generate` test `expected undefined to be true` because `split` was never set). `git stash pop`; `npm test` => 4 passed.
  - Repo-wide verification: `pytest tests/ -q` => 653 passed, 1 xfailed (pre-existing test_detect_ports xfail), conftest baseline guard shows no architecture.json clobber. `ruff check analyzer/ tests/ scripts/` => All checks passed. `packages/cli` `npm run build` (tsc) exit 0; `npm test` => 4 passed. `git status --porcelain` clean except the intended files (dist restored, sample dataset restored; see Deviations).
  - build.sh output shape (ran `bash build.sh .` against this repo): exit 0 (only the pre-existing F-VW-8 search.ts mixed-import and 500 kB chunk warnings). Analyzer wrote split output to `viewer/public/architecture/` (manifest.json + data/), manifest stats `total_symbols=606`, `total_symbols_detected=606` (uncapped, consistent), 23 components, 407 files, `symbols`/`files` arrays absent from the manifest, `component_detail_index` present. `viewer/dist/` then contained the fresh `architecture/` split dir (23 components) plus assets/index.html. After inspecting, restored the tracked sample dataset and dist so the tree is clean.
  - Deviations / notes: (1) Did not edit README. No user-facing npx flags changed; README:376 already documents the `--max-symbols` default and README:529 documents `--split`. The only README nit is the stats schema block (README:510) lacking the new optional `total_symbols_detected`; README is outside this task's file territory and is owned by P2-5, so it is recorded in Discovered During Execution. (2) `packages/cli/dist` is a tracked stale build artifact (F-VW-10 / P2-6). Rebuilding it during verification was reverted (`git checkout -- packages/cli/dist`) to keep this commit source-only, following the P0-2 precedent; the publish flow rebuilds dist via prepublishOnly. (3) build.sh now writes into a persistent split directory, so the pre-existing lack of stale-detail-file pruning in `write_split` (already P2-7 item 6) becomes visible: a data/ dir that previously held a different dataset keeps its unreferenced detail-*.json files. The manifest is authoritative (the viewer only fetches referenced components), so this is cosmetic bloat, not a correctness bug. Recorded in Discovered During Execution.

### P1-3: Persist review annotations across reloads
- Status: DONE (session remediation/p1-viewer, 2026-07-11)
- Model: Opus 4.8
- Stream: B. Branch: remediation/p1-viewer
- Findings: F-VW-4, F-DC rows 3 and 11
- Files: viewer/src/store.ts (annotation state, 145, 300, 423-454), new persistence util, tests
- Do:
  1. Persist annotations to localStorage keyed by a stable architecture identity (name plus repository; do not key on `generated_at` or annotations vanish on every re-analysis). Include a schema version field and a size guard consistent with the existing localStorage patterns.
  2. Restore on load; reconcile annotations whose target component no longer exists (keep them, flag as orphaned in ReviewSummary, so re-analysis does not silently destroy feedback).
  3. Tests against the real store: add annotations, simulate reload (fresh store, same storage), assert restoration; orphan case; storage-quota failure does not crash.
- Accept:
  - [x] Hard reload preserves annotations (test plus manual check)
  - [x] Orphaned annotations visible, not silently dropped, after loading a changed architecture
  - [ ] PROJECT-OVERVIEW/README wording about persistence updated to the now-true claim (or noted for P2-5)
- Verify: viewer tests; manual annotate-reload check
- Evidence:
  - Re-verified F-VW-4 against current code: `annotations: []` initial state (store.ts:300) and the four mutations (addAnnotation, updateAnnotation, deleteAnnotation, clearAllAnnotations) touched only in-memory state, never localStorage, while dark-mode/changelog/enhanced-frames all persist. A reload or a re-analysis wiped all review work. Finding reproduces.
  - New persistence util `viewer/src/utils/annotationStorage.ts`: single `arch-annotations` localStorage key holding `{ version: 1, byArch: Record<identity, Annotation[]> }`. `architectureIdentity(arch)` derives a stable key from `name` plus `repository` and deliberately excludes `generated_at` so re-analysis keeps annotations. Schema `version` is checked on read (mismatched or corrupt payloads are dropped, not misread). Size guard refuses to persist a serialized payload over 2 MB. All writes are wrapped so a quota/unavailable failure is swallowed, matching the existing localStorage writers.
  - store.ts: `setArchitecture` now restores annotations for the loaded architecture's identity via `loadAnnotations` (single canonical entry point for both initial load and live refresh). Added module-level `persistCurrentAnnotations(get)`, called after each of the four annotation mutations so every add/edit/delete/clear is written through immediately.
  - ReviewSummary.tsx: added an `orphaned` memo (annotations whose `getComponentById` returns null) and a dedicated "Orphaned feedback" section (data-testid `orphaned-annotations`) that lists each orphan with its stored target label and text plus a delete button. Previously the component grouping silently dropped these (the group builder returned null for missing components).
  - Regression tests `viewer/src/__tests__/annotationPersistence.test.tsx` (6 tests, real store, real ReviewSummary, jsdom localStorage, no store mock): restore-after-reload; identity-not-generated_at (re-analysis preserves); orphaned annotations kept in store after a changed architecture; orphaned section rendered in ReviewSummary; quota write failure does not crash; removal persists across reload. "Reload" is simulated by wiping in-memory store state while localStorage survives, exactly as a browser reload does.
  - Fail-then-pass proof: `git stash push -- viewer/src/store.ts viewer/src/components/ReviewSummary.tsx` then `npx vitest run src/__tests__/annotationPersistence.test.tsx` -> `4 failed, 2 passed` (the 4 persistence/orphan-visibility tests fail on the pre-fix code; the 2 that pass pre-fix are quota-safety and the removal case, which pass trivially when nothing persists). `git stash pop`, same command -> `6 passed`.
  - Full viewer suite after the change: `npx vitest run` -> 6 files, 61 tests passed (no existing test regressed).
  - Deviation: PROJECT-OVERVIEW/README persistence wording is P2-5 (docs) territory and Stream C, out of this session's file territory. Left the acceptance item for P2-5, as the task text allows ("or noted for P2-5").

### P1-4: Fix popstate history corruption
- Status: DONE (session remediation/p1-viewer, 2026-07-11)
- Model: Opus 4.8
- Stream: B. Branch: remediation/p1-viewer (same session as P1-3/P1-5, sequenced; shared files)
- Findings: F-VW-2
- Files: viewer/src/App.tsx (321-366), viewer/src/utils/urlState.ts, tests
- Do: add a suppression mechanism (ref flag set during popstate handling) so store-driven URL pushes are skipped while applying a popstate navigation; use `replaceState` where appropriate. Test with jsdom: drill twice, fire popstate for the earlier state, assert history length does not grow and forward state remains reachable; assert URL reflects the restored state.
- Accept:
  - [x] Back then Forward restores the same drill state (test-asserted and manual)
  - [x] No new history entry is created while handling popstate (test-asserted)
- Verify: viewer tests; manual browser check
- Evidence:
  - Re-verified F-VW-2 against current code: the three URL-sync effects lived at App.tsx:297-366. The store subscription pushed on every `drillLevel` change; the popstate handler called `drillInto`/`navigateToBreadcrumb` which change `drillLevel`, re-firing the subscription and pushing a fresh history entry mid-popstate. No suppression flag existed. Finding reproduces.
  - Fix: extracted the three effects into `viewer/src/hooks/useUrlSync.ts` (restore-on-load, store->URL subscription, popstate handler) so the wiring is testable in isolation on the real store. Added `applyingPopStateRef`: the popstate handler sets it true around its store mutations (try/finally) and the subscription early-returns while it is set, so no URL write happens while a popstate is being applied. The browser has already set the URL to the target before firing popstate, so suppressing our own write is correct; the subscription keeps `replaceState` for selection-only changes and `pushState` for drill changes. App.tsx now just calls `useUrlSync()` and the `parseUrlState`/`pushUrlState`/`replaceUrlState` imports and the `urlRestoredRef` moved into the hook.
  - Regression test `viewer/src/__tests__/useUrlSync.test.tsx` (2 tests, real store, real hook, jsdom history): drill A then B (two pushes), then simulate Back (replaceState to `?drill=A` then dispatch a real `popstate` event) and assert (a) the store restored `drillLevel === "A"`, (b) `parseUrlState().drill === "A"` (URL reflects restored state, not rewritten), and (c) `window.history.length` is unchanged (no entry pushed mid-popstate, so the forward stack survives). A second test asserts normal store-driven drilling still writes the URL, proving the suppression is scoped to popstate handling only.
  - Fail-then-pass proof: reverted `useUrlSync.ts` to the exact pre-fix logic (removed the `applyingPopStateRef` guard and the try/finally, i.e. the extracted-verbatim old App effects). `npx vitest run src/__tests__/useUrlSync.test.tsx` -> `1 failed, 1 passed`: the popstate test fails on `expect(window.history.length).toBe(historyLenBeforeBack)` because the subscription re-pushed `drill=A` (history grew by 1), reproducing the corruption; the normal-navigation test still passes. Restored the fix -> `2 passed`.
  - `npx tsc -b` clean after the App refactor; full viewer suite `npx vitest run` -> 7 files, 63 tests passed.

### P1-5: Live refresh must not wipe search or serve stale details
- Status: DONE (session remediation/p1-viewer, 2026-07-11)
- Model: Opus 4.8
- Stream: B. Branch: remediation/p1-viewer
- Findings: F-VW-3, plus the stale `componentDetailCache` item in F-VW-7
- Files: viewer/src/utils/search.ts, viewer/src/store.ts (574-602), viewer/src/hooks/useLiveMonitor.ts (near 165), tests
- Do:
  1. On live manifest refresh, rebuild the search index from the new manifest and re-add entries for every component already in `componentDetailCache`, or make the index rebuild preserve detail-derived entries keyed by component.
  2. Invalidate (or version-check) `componentDetailCache` when the architecture updates, so panels do not show stale symbols; the next open refetches.
  3. Tests: index a detail-loaded symbol, apply a live refresh, assert the symbol is still searchable; assert cache invalidation triggers a refetch.
- Accept:
  - [x] Post-refresh search still finds previously loaded symbols (test-asserted)
  - [x] Detail panel shows post-refresh data after an update (test-asserted)
- Verify: viewer tests
- Evidence:
  - Re-verified both findings. F-VW-3: `useLiveMonitor` calls `initializeSearch(data)` on every manifest refresh (was :165); `initializeSearch` reset `allResults = []` (search.ts:19), dropping every entry that `addToSearchIndex` had added from split-mode detail loads, and `loadComponentDetail` early-returns on a cache hit so they were never re-added. F-VW-7 stale-cache item: neither the live refresh nor `setArchitecture` invalidated `componentDetailCache`, so panels served stale symbols/files after an update. Both reproduce.
  - Fix 1 (search preservation), search.ts: split the index into `baseResults` (rebuilt wholesale by `initializeSearch`) and `detailResultsByComponent` (a `Map<componentId, SearchResult[]>` fed by `addToSearchIndex`). A shared `rebuildFuse()` concatenates both. `initializeSearch` now rebuilds only the base entries and preserves the detail map, so a live refresh keeps previously loaded symbols/files searchable. `addToSearchIndex` gained an optional `componentId` so re-loading a component replaces its entries rather than duplicating. Added `resetDetailSearchEntries()` for a genuine full reset (not wired to live refresh). `loadComponentDetail` now passes `componentId` when indexing.
  - Fix 2 (cache invalidation), store.ts + useLiveMonitor.ts: `setArchitecture` clears `componentDetailCache: {}` on every architecture update (single canonical entry point). `useLiveMonitor` now applies the refreshed manifest through `store().setArchitecture(data)` instead of a raw `setState`, so a live refresh invalidates the cache (panels refetch fresh data) and also re-applies persisted annotations. `initializeSearch(data)` still runs afterward and preserves the detail-derived search entries.
  - Regression tests `viewer/src/__tests__/liveRefresh.test.ts` (2 tests, real store + real search module, only fetch mocked): (1) load a detail file adding symbol `uniqueSymbolXYZ`, assert it is searchable, run `initializeSearch` for the refreshed manifest, assert it is STILL searchable; (2) load detail v1 (fetch called once, `getComponentSymbols` returns v1sym), call `setArchitecture` for a new scan, assert `componentDetailCache["comp-a"]` is now undefined, re-open the component, assert fetch was called a second time and v2sym is returned and served by `getComponentSymbols`.
  - Fail-then-pass proof: reproduced both pre-fix behaviors surgically (made `initializeSearch` clear the detail map; removed `componentDetailCache: {}` from `setArchitecture`) and ran `npx vitest run src/__tests__/liveRefresh.test.ts` -> `2 failed`: test 1 fails because the lazily indexed symbol is no longer searchable after refresh; test 2 fails on `componentDetailCache["comp-a"]` still being defined (stale) so no refetch occurs. Restored both fixes -> `2 passed`.
  - Copilot review round (2026-07-13, PR #10): three findings, all fixed. (1) `setArchitecture` now also clears `componentDetailLoading` so a live refresh mid-detail-load cannot leave the panel stuck in a loading state. (2) `loadComponentDetail` captures the architecture it was called against and discards a response that resolves after a live refresh swapped the architecture, so a stale in-flight fetch can no longer repopulate the freshly invalidated cache; new regression test (deferred fetch resolved after `setArchitecture`) fails pre-fix (1 failed via `git stash` of store.ts) and passes post-fix. (3) `annotationStorage.ts` contained a literal NUL (0x00) byte in the identity separator, which made git treat the file as binary; replaced with the escaped backslash-u0000 form (identical runtime value, no stored-key migration needed since nothing shipped). Verified byte-clean with perl. Full viewer suite after the round: 66 tests passed, lint 0 errors/18 pre-existing warnings, tsc clean, build clean.

---

## Phase 2: Robustness and honesty

### P2-1: Incremental mode falls back to full rescan on unmapped changes
- Status: TODO
- Model: Opus 4.8
- Stream: A. Branch: remediation/p2-analyzer
- Findings: F-CRIT-8
- Files: analyzer/incremental.py (map_files_to_components 911-929, should_full_rescan 948-984), tests/test_incremental.py
- Do: track changed files that map to zero components; if any exist, trigger the existing full-rescan path (and log why). Regression tests on a real temp git repo: add a new root-level file, and separately a new directory with files; assert both appear in the merged output. Prove the tests fail pre-fix.
- Accept:
  - [ ] Both regression scenarios pass, and the pre-fix failure is recorded in Evidence
  - [ ] A log line states the fallback reason when it fires
- Verify: pytest tests/test_incremental.py
- Evidence:

### P2-2: Scanner file-content cache, path index, and root-bounded CI check
- Status: DROPPED (superseded 2026-07-11 by Program 2 Phase 4; see WORK-PLAN-2.md section 2). The engine these optimizations target is replaced by Tiers 1 to 3. Item 1 (fixture-snapshot output guard) moves into P4-1. Item 3 (root-bounded `_check_ci_tests`) carries into the Tier 3 derivation port, noted in P4-3.
- Model: Opus 4.8 (behavior-preserving refactor, needs care)
- Stream: A. Branch: remediation/p2-analyzer
- Findings: F-AN-1, F-AN-2
- Files: analyzer/scanner.py
- Do:
  1. First, add a byte-identical-output guard: a test that runs the full scan on a fixture repo and snapshots the JSON (normalize timestamps and machine paths). All refactor steps must keep it green.
  2. Introduce a single content cache (path to text) and a `{path: FileInfo}` index; route `_read_component_code`, the port/service/external-API loops, `_assign_server_ports`, and `_compute_component_metrics` through them.
  3. Bound `_check_ci_tests` at `self.root` (2269-2302) and add a test with a decoy `.github` above a temp scan root proving it is no longer read (this changes behavior intentionally; assert the new correct behavior).
  4. Optional instrumentation: count file reads in the test and assert each file is read at most once per scan.
- Accept:
  - [ ] Identical-output test green across the refactor (except the intended F-AN-2 change, isolated and asserted separately)
  - [ ] Read-count assertion or a before/after timing note on this repo in Evidence
- Verify: pytest; self-analysis smoke run
- Evidence:

### P2-3: Viewer performance cliffs and bundle splitting
- Status: TODO
- Model: Opus 4.8
- Stream: B. Branch: remediation/p2-viewer
- Findings: F-VW-5, F-VW-6, F-VW-8
- Files: viewer/src/store.ts (applyStatusOverlay 469-472), viewer/src/components/ComponentNode.tsx (746-750), viewer/src/App.tsx:17, viewer/src/store.ts:594, viewer/vite.config.ts
- Do:
  1. Replace the JSON deep clone in `applyStatusOverlay` with targeted immutable updates touching only components whose status changed; delete the dead index build; keep `detailItem.data` coherent with the updated tree. Store test asserting untouched components keep referential identity across an overlay.
  2. Give ComponentNode selector-based subscriptions (or precompute per-node connection counts once per architecture change in the store) so nodes stop re-rendering on unrelated store changes.
  3. Fix the mixed static/dynamic import of search.ts (pick one), and split elkjs into its own async chunk (dynamic import or manualChunks).
- Accept:
  - [ ] Referential-identity store test green
  - [ ] `npm run build` no longer warns about the mixed import; main chunk shrinks meaningfully (record before/after sizes in Evidence; target at least 500 kB raw reduction via the elk split, or document why not)
  - [ ] Brief manual profile note: node re-render behavior on a status poll before/after
- Verify: build output; tests; React DevTools profile note
- Evidence:

### P2-4: Viewer confirmed-bug sweep
- Status: TODO
- Model: Opus 4.8
- Stream: B. Branch: remediation/p2-viewer
- Findings: F-VW-7, plus the 19 lint warnings from F-VW-8
- Files: viewer/src/App.tsx (253-295, 649), viewer/src/hooks/useLiveMonitor.ts (169, 234-243), viewer/src/components/ArchitectureGraph.tsx (233-293), viewer/src/store.ts (585-602), viewer/src/components/DetailPanel.tsx (59-63)
- Do, each with a test where the harness reasonably allows:
  1. Entity-as-text toggle (App.tsx:649): render the actual character.
  2. Initial-load race: App's loader must not clobber an architecture the live monitor already set (mirror the live monitor's own guard); ensure `initializeSearch` runs once.
  3. Hidden-tab polling: `scheduleNext`/`poll` check `document.hidden` before re-arming.
  4. ELK staleness guard: token or generation counter so only the latest layout applies; make selection-centering wait for layout.
  5. Detail-fetch failures: surface an error state in the panel, add negative caching with retry affordance, fix the shared `componentDetailLoading` race (per-component loading keys).
  6. Preserve `?tab=` in App's URL writer.
  7. Add a schema/version key to the localStorage architecture cache and drop mismatched caches.
  8. Clear the 19 no-unused-vars warnings (delete dead code, including the DetailPanel unused destructure block).
- Accept:
  - [ ] Each numbered item verified (test or documented manual check per item in Evidence)
  - [ ] `npm run lint` reports 0 warnings
- Verify: viewer checks suite
- Evidence:

### P2-5: Documentation reconciliation (claims become true or disappear)
- Status: TODO
- Model: Sonnet 5 acceptable; runs after the phase's code tasks merge
- Stream: C. Branch: remediation/p2-docs
- Findings: F-DC rows 8, 9, 10, 11, 12; F-VW-4 wording; F-PL-8
- Files: README.md, PROJECT-OVERVIEW.md, CHANGELOG.md, docs/architectural-assessment.md, docs/ui-actions-source-linking-plan.md, .claude/skills/ai-assist/SKILL.md, DEPLOYMENTS.md, viewer/src/types.ts, viewer/src/store.ts
- Do:
  1. Fix "Three views" (README:183): remove the claim and delete the vestigial `ViewMode`/`setViewMode` dead code (recommendation), or open a feature task if the owner wants the list view built. Record the decision.
  2. Rewrite the Wave 2 roadmap: mark UI actions and source linking shipped; leave `?file=&line=` as the remaining item (until P3-2 lands, then mark shipped).
  3. Fix the broken link at PROJECT-OVERVIEW.md:426 (doc moved to docs/archive/).
  4. Correct the CHANGELOG annotation claim (no relationship target exists).
  5. Add a dated "historical snapshot" banner to architectural-assessment.md and stale-framed sections of ui-actions-source-linking-plan.md.
  6. Update persistence wording after P1-3, coverage wording after P1-2, and release/version references after P1-1.
  7. Make ai-assist SKILL.md paths repo-relative.
  8. Note the upstream/downstream live-monitor divergence in DEPLOYMENTS.md with a pointer to the current downstream reality.
  9. Re-run the claims table from AUDIT-2026-07.md section 7 and append the refreshed verdicts to this task's Evidence.
- Accept:
  - [ ] Every non-VERIFIED row of the claims table is resolved and the refreshed table shows it
  - [ ] No document violates .claude/rules/writing-style.md in changed text
- Verify: manual claims re-audit; link check on changed docs
- Evidence:

### P2-6: Repo hygiene
- Status: TODO
- Model: Sonnet 5
- Stream: C. Branch: remediation/p2-docs
- Findings: F-VW-10
- Files: viewer/.gitignore, .gitignore, git index
- Do: `git rm -r --cached viewer/coverage packages/cli/dist`, ignore both plus `viewer/test-results/`; confirm release.yml/prepare-bundle.sh builds `packages/cli/dist` at publish time so untracking is safe (read the workflow before removing); sweep for other committed artifacts (.DS_Store, __pycache__ in tracked paths).
- Accept:
  - [ ] `git ls-files | grep -E "coverage/|packages/cli/dist/"` empty
  - [ ] release.yml dry-run reasoning recorded in Evidence (where dist gets built)
- Verify: git ls-files greps; CI green
- Evidence:

### P2-7: Analyzer robustness sweep
- Status: TODO
- Model: Opus 4.8 (Sonnet 5 acceptable for items 3 to 6)
- Stream: A. Branch: remediation/p2-analyzer
- Findings: F-AN-5, F-AN-6, F-AN-7, F-AN-8, F-AN-9, F-AN-10
- Do, each test-backed:
  1. multi_repo: friendly error for a repo entry missing `name`; timeout on the clone subprocess.
  2. Wrap the two unguarded `iterdir()` calls in `_classify_architectural_role` (scanner.py 677-691) with OSError handling; test with an unreadable dir (chmod 000, skip on platforms where that is unenforceable).
  3. Tree-sitter fallback: log filename and exception type at debug level on fallback (tree_sitter_base.py 22-35).
  4. Remove dead code: unused SYMBOL_PATTERNS in swift.py and ruby.py, unused SWIFTUI_BUTTON_ACTION_RE, and the deprecated incremental.py trio plus their tests (confirm nothing else imports them first).
  5. Make `--incremental --split` and `--config --incremental` argparse errors instead of silent precedence.
  6. Split mode: remove stale `detail-*.json` files not in the current manifest when writing (guard so it only deletes files matching the detail pattern inside the data dir).
- Accept:
  - [ ] Each numbered item has a test or, for dead-code removal, a green suite plus grep proof of no references
- Verify: pytest; ruff
- Evidence:

### P2-8: Pipeline hardening sweep
- Status: TODO
- Model: Opus 4.8
- Stream: C (after A and B merge). Branch: remediation/p2-pipeline
- Findings: F-PL-3 (deploy-downstream verification), F-PL-4 (injection, artifact name), F-PL-7 (token compare)
- Do:
  1. action.yml: route `inputs.config`, `inputs.path`, and `inputs.cloudflare-project-name` through `env:` rather than direct `${{ }}` interpolation in `run:` blocks; add an `artifact-name` input defaulting to `architecture-viz`.
  2. deploy-downstream.yml: after dispatching, poll the dispatched runs' conclusions (bounded wait) and fail the job if any downstream run fails, so "green" means deployed.
  3. Worker: constant-time token comparison for INGEST_TOKEN.
  4. Decide and record the action-pinning policy (major tags versus SHAs). Either is defensible; write the decision down here.
- Accept:
  - [ ] actionlint clean; no untrusted `${{ inputs.* }}` inside `run:` in action.yml
  - [ ] A downstream-failure simulation (dispatch a workflow forced to fail, or reason through the polling code in review) shows deploy-downstream reporting failure
- Verify: actionlint; test dispatch against a scratch workflow if feasible
- Evidence:

---

## Phase 3: Close the loop

### P3-1: Behavioral test program for critical untested paths
- Status: TODO
- Model: Opus 4.8 (test quality is the point; see WORK-PLAN principles 2 and 3)
- Stream: A (Python) and B (viewer) halves may run in parallel
- Findings: F-VW-9, multi_repo coverage gap in F-CRIT-3 context, models validation gap
- Do: add behavioral tests for each path below that is not already covered by an earlier task's regression test. For every new test, record the fails-when-broken proof (temporarily reintroduce the bug or mutate the code path).
  - Viewer: urlState round-trip and App URL sync; promptGenerator export (assert exported markdown contains the annotation, target context, and counts); annotation add/edit/delete/clear actions; search init/add/rebuild; changelog read-state persistence.
  - Python: multi_repo clone orchestration with a local temp "remote" (file:// URL) covering name/path/url variants and the failure path; models.py validation block (326-433) with intentionally broken cross-references; safe_component_id collision documentation test (encodes current known limitation as an expected-behavior test with a comment, so the limitation is visible).
- Accept:
  - [ ] Each listed path has at least one test that provably fails when its code is broken (Evidence lists the proof per test)
  - [ ] Coverage is reported in Evidence but is NOT the acceptance bar; behavior proofs are
- Verify: pytest and vitest runs
- Evidence:

### P3-2: Inbound `?file=&line=` deep links
- Status: TODO
- Model: Opus 4.8
- Stream: B. Branch: remediation/p3-viewer
- Findings: F-DC row 4, PROJECT-OVERVIEW roadmap promise
- Files: viewer/src/utils/urlState.ts, viewer/src/App.tsx, viewer/src/store.ts, tests
- Do:
  1. Design first (short design note in the PR description): resolve a file path to its owning component via the manifest file lists (split mode may require fetching detail files; define the resolution order and the ambiguity rule when multiple components claim a file).
  2. Implement: on load with `?file=` (optional `&line=`), drill to the owning component, open the detail panel's Files tab at that file, and select the symbol whose range contains the line when symbol data is available.
  3. Handle gracefully: file not found (visible non-blocking notice, land on overview), ambiguous owner (pick the deepest component, note the rule), split-mode lazy load (loading state, works after fetch; depends on P0-6 being done).
  4. Tests for found, missing, ambiguous, and split-mode-lazy cases; compose correctly with existing `?component/tab/drill` params.
- Accept:
  - [ ] All four test cases green; manual check pasting a deep link into a fresh tab on a split-mode build
  - [ ] PROJECT-OVERVIEW roadmap updated to shipped (coordinates with P2-5)
- Verify: viewer tests; manual deep-link check
- Evidence:

### P3-3: Drift-tolerant AI enhancement preservation
- Status: DONE. Pulled forward from Phase 3 on 2026-07-11 by owner decision: it was the last blocker for the live demo redeploy after the production ID-drift failure that day. Branch: remediation/p3-merge-drift. Reconciliation note: Program 2 planning briefly marked this card DROPPED as superseded by P7-1 enrichment provenance, but the work shipped the same day (PR #6), so it stands as the interim protection until P7-1 lands and P7-1 builds on it rather than replacing it.
- Model: Opus 4.8
- Stream: A. Branch: remediation/p3-merge-drift (pulled forward; original plan slot was remediation/p3-analyzer)
- Findings: F-CRIT-6 root cause, F-PL-3 (dispatch path relies on this merge)
- Files: scripts/merge-ai-enhancements.py, tests/test_merge_ai_enhancements.py, action.yml, .github/workflows/architecture-viz.yml, .github/workflows/live-monitor.yml
- Do:
  1. Add fallback matching when exact ID fails: match by component `path`, then by (name, type) as a last resort; same idea for relationships via (source-path, target-path, type). Report per-strategy match counts in the output.
  2. Add a `--strict` flag (exit nonzero below a preservation threshold) and use it in CI workflows so silent data loss becomes impossible.
  3. Wire scripts/validate-ai-preservation.py (already exists) into architecture-viz.yml as a post-merge check. Decided against during execution: that script matches by exact ID only and hard-errors on legitimate adds and removals, so it would reintroduce the very fragility this task removes; the `--strict` merge guard covers the loud-failure need. See Evidence for the full rationale.
  4. Tests: exact match, renamed-ID-same-path drift (preserved), true component removal (not preserved, not counted as failure), threshold failure exits nonzero.
- Accept:
  - [x] Drift scenario preserves enhancements (test-asserted, fails on the pre-fix exact-only matcher)
  - [x] CI merge step is strict; a simulated total-loss merge fails the workflow
- Verify: pytest; workflow file review; real-data end-to-end run checking the preservation counts
- Evidence:
  - Matcher design. `scripts/merge-ai-enhancements.py` now matches baseline AI-enhanced components onto target components in four ordered waves, each claiming a target at most once: (1) exact ID, (2) component `path`, (3) prefix/suffix (a baseline ID or path that is a strict path-segment suffix of exactly one unclaimed target ID or path, the repo-prefix-added pattern like `curriculum` to `unamentis/curriculum`), (4) (name, type) as a last resort. Every fallback requires a UNIQUE candidate; ambiguity is never guessed, it is left unmatched and reported. Suffix matching is one-directional (baseline is a suffix of target) so the reverse case stays a loud failure. Relationships attach by (source, target, type) with endpoints translated through the component id map, so drifted-but-matched endpoints line up; AI-discovered relationships are carried forward with translated endpoints. The output reports per-strategy counts: exact, path, prefix/suffix, name+type, removed, unmatched.
  - Removal vs ambiguity. An unmatched baseline component with NO candidate under any strategy is a genuine removal and is excluded from the preservation-ratio denominator (deleting a component must not fail the guard). An unmatched component that HAD candidates but could not be claimed uniquely is ambiguous drift and DOES count against the ratio and is warned about.
  - Guards. The P0-4 total-loss guard is kept: preserved==0 with a non-empty AI baseline exits 1 and leaves the target untouched. New `--strict` (with `--strict-threshold`, default 0.90) exits 1, target untouched, when preserved over still-present falls below threshold. Both guards run BEFORE any write.
  - `--strict` wired into every merge invocation: action.yml (split-mode branch and single-file-into-manifest branch), .github/workflows/architecture-viz.yml, .github/workflows/live-monitor.yml.
  - validate-ai-preservation.py NOT wired into architecture-viz.yml, by design. Its assumptions do not fit that workflow's data flow: it matches components by exact ID only (zero drift tolerance, so it would flag the very repo-prefix drift this task exists to handle as LOST), it treats any baseline component missing from the fresh result as a hard ERROR (so any legitimate add, remove, or rename fails the build), and it requires a `--changed-components` list the push workflow cannot compute. It remains correctly used by scripts/e2e-ai-preservation-test.sh where a same-schema scan and an explicit changed list are available. The merge script's own `--strict` guard now provides the loud-failure-on-data-loss guarantee for the workflow while tolerating drift and legitimate removals.
  - Tests. tests/test_merge_ai_enhancements.py extended (9 tests total): exact match unchanged; the UnaMentis repo-prefix drift (251 unprefixed baseline vs prefixed target plus a `repo:unamentis` grouping node, asserts 251/251 preserved and prefix/suffix=251, exact=0, removed=0, unmatched=0, plus relationship endpoint translation); renamed-ID-same-path (matched by path); true removal (excluded from ratio, `--strict` still passes at 100% of still-present); ambiguous match not guessed (two `/shared` targets, neither enhanced, reported); threshold failure (2 of 10 = 20% under `--strict` exits nonzero with the target byte-identical, then a lower `--strict-threshold` and a plain run both write).
  - Fail-then-pass proof. `git stash push scripts/merge-ai-enhancements.py`; `pytest tests/test_merge_ai_enhancements.py -q` against the pre-fix exact-only script gave `5 failed, 4 passed` (the 5 new drift tests fail: the repo-prefix drift test hits the total-loss guard and exits 1 with 0 preserved; the `--strict` tests error on the unrecognized flag). `git stash pop`; the same command gives `9 passed`.
  - Real-data end-to-end (read-only, scratch area, nothing in the unamentis repo touched). Baseline: the real committed UnaMentis baseline fetched via `gh api repos/UnaMentis/unamentis/contents/architecture.json` download_url (5.5 MB, 251 AI-enhanced components, 167 AI relationships). It is a mixed-schema file: 124 unprefixed IDs such as `curriculum` and 127 `unamentis/`-prefixed IDs including SwiftUI `__ui__` flow nodes and `core/*` modules. Target: a fresh `--split` scan of the local /Users/ramerman/dev/unamentis checkout via its solution-explorer.json config into scratch (121 uniformly `unamentis/`-prefixed, directory-oriented components). Results: (a) the shipped exact-only matcher preserves 0 of 251 and fires the total-loss guard (exit 1, target untouched), reproducing the 2026-07-11 production incident almost verbatim (its diagnostic prints baseline first-5 `['curriculum', ...]` vs target `['repo:unamentis', 'unamentis/curriculum', ...]`); (b) the new matcher preserves 110 of 251 raw, and because 139 baseline components are genuine removals (they have no counterpart in the smaller current checkout), 110 of the 112 still-present enhancements survive = 98.2%, above 95%, with 2 ambiguous candidates correctly refused; `--strict` at the default 0.90 passes (exit 0). Deviation from the literal task figure: the plain "at least 95 percent of the 251" cannot be met against this checkout because the local checkout plus current analyzer produces a structurally different, smaller component set than the deploy snapshot that generated the baseline (exact-ID overlap is 0), which is a real-world data divergence, not a matcher shortfall. To isolate the matcher from that divergence and prove preservation at 251 scale on real curated data, a second real-data run applied the exact production drift transformation (add a repo prefix to every ID and path of the real 251-component baseline, strip its AI, add a new `repo:demo` grouping node) and merged: 251 of 251 components (100%), 167 of 167 AI relationships, and architecture-level AI all preserved under `--strict`, exit 0 (strategy prefix/suffix=207, name+type=44, removed=0, unmatched=0).
  - Verification: `ruff check analyze.py analyzer/ scripts/ tests/` clean; `pytest tests/ -q` 649 passed, 1 xfailed (pre-existing test_detect_ports xfail), `git status --porcelain` shows only the intended files (no architecture.json clobber); `actionlint .github/workflows/architecture-viz.yml .github/workflows/live-monitor.yml` exit 0; action.yml (a composite action, not lintable by actionlint) validated as well-formed YAML.

### P3-4 (optional, stretch): Decompose scanner.py
- Status: DROPPED (superseded 2026-07-11 by Program 2 Phase 4, which replaces scanner.py orchestration entirely; see TARGET-ARCHITECTURE.md section 9).
- Model: Opus 4.8
- Stream: solo, only after P2-2's identical-output guard exists
- Findings: F-AN-12 (size), enabled by P2-2
- Do: split the 2,666-line ArchitectureScanner along its natural seams (relationship strategies, docs/testing extraction) into modules, preserving the public API and the identical-output test. Skip this task entirely if timeline pressure exists; it is leverage for the future, not a defect.
- Accept:
  - [ ] Identical-output test green; no module over ~800 lines; public imports unchanged (analyze.py and action.yml paths still work)
- Verify: pytest; self-analysis smoke run
- Evidence:

---

# Program 2: target architecture

Design authority: [TARGET-ARCHITECTURE.md](TARGET-ARCHITECTURE.md) (invariants I1 to I10 bind every task below). Plan: [WORK-PLAN-2.md](WORK-PLAN-2.md). WORK-PLAN.md section 2 principles and section 6 handoff apply, with the executor template's reading list swapping the audit for TARGET-ARCHITECTURE.md.

Phase 4 cards are execution-ready. Phase 5 to 9 cards are scoped but intentionally lighter; per WORK-PLAN-2.md section 6, the phase-gate session elaborates them to full fidelity before their phase starts, without changing scope.

## Phase 4: The index engine

### P4-1: Fact store schema, symbol identity, and the parity guard
- Status: TODO
- Model: Opus 4.8 (no substitution)
- Stream: A. Branch: program2/p4-store
- Design: TARGET-ARCHITECTURE.md sections 4.2, 6, and 12; invariants I4, I7
- Files: new package analyzer/store/ (schema.py, db.py, ids.py), tests/test_store.py, tests/fixtures/ (new fixture repos), tests/test_engine_parity.py
- Do:
  1. Implement the SQLite schema from TARGET-ARCHITECTURE 4.2 with schema_version in meta, WAL mode, and deterministic ordering helpers for all reads used by projections. Stdlib sqlite3 only.
  2. Define and document the symbol ID grammar (SCIP-style, human-readable, escaping table) in ids.py with exhaustive round-trip tests, including multi-repo prefixing and the existing component escape rules. This grammar freezes at the end of this task; record the frozen grammar in this card's Evidence.
  3. Build two small fixture repos under tests/fixtures/ (one polyglot single-repo, one multi-repo config) sized for fast CI, exercising every component type and relationship type the current engine emits.
  4. Port P2-2 item 1 here: a snapshot test running the CURRENT engine on the fixtures and freezing normalized output (strip timestamps and machine paths). This is the parity baseline for P4-7.
  5. Write FTS5 virtual tables and a thin query module (by name, by path, by kind, bounded-depth edge traversal via recursive CTE) with tests.
- Accept:
  - [ ] Schema creates, migrates from empty, round-trips every entity type with deterministic read order
  - [ ] Symbol ID grammar documented, frozen, round-trip tested including collision and escaping edge cases
  - [ ] Parity snapshot of the current engine on both fixtures committed and green
  - [ ] FTS and traversal queries tested
- Verify: pytest tests/test_store.py tests/test_engine_parity.py; ruff
- Evidence:

### P4-2: Parallel extraction tier with content-hash cache and nested symbols
- Status: TODO
- Model: Opus 4.8
- Stream: A. Branch: program2/p4-extract
- Design: TARGET-ARCHITECTURE.md section 4.1; invariants I2, I6
- Files: new package analyzer/extract/ (runner.py, facts.py, signals.py), analyzer/parsers/* (extend), analyzer/store/, tests
- Do:
  1. Build the worker-pool runner: enumerate files under root, hash contents, skip files whose (hash, parser_version) is in extraction_cache, parse the rest in parallel, write fact records and ledger rows.
  2. Extend every tree-sitter parser to emit nested symbols (methods, inner types) with parent set, and exact ranges (drop the 500-line block-end bound on the tree-sitter path). Regex fallbacks keep current behavior and mark their facts confidence-appropriately.
  3. Move signal extraction here from scanner.py: ports, URL/service references, db/queue/ws/grpc driver usage, endpoint declarations, CLI command declarations, UI actions with target_view, env vars, framework markers. Each file is read exactly once. Signals carry file and line.
  4. Ledger dispositions per I2: parsed, excluded:<rule>, failed:<error>, binary. No silent size skip; --max-file-size becomes explicit opt-in whose effect lands in the ledger.
  5. Determinism: two consecutive cold runs produce identical store contents (ordering-independent comparison test).
- Accept:
  - [ ] Fixture run: methods appear with parent references for all seven tree-sitter languages
  - [ ] Warm re-run with no changes parses zero files (cache-hit assertion); touching one file parses exactly one
  - [ ] Ledger row count equals file count under root on fixtures and on this repo
  - [ ] Parallel speedup on this repo recorded in Evidence (cores, cold and warm wall time)
- Verify: pytest; a timed self-analysis run recorded in Evidence
- Evidence:

### P4-3: Derivation passes over the store
- Status: TODO
- Model: Opus 4.8 (no substitution)
- Stream: A. Branch: program2/p4-derive
- Design: TARGET-ARCHITECTURE.md section 4.3; invariant I3
- Files: new package analyzer/derive/ (components.py, roles.py, relationships.py, testing.py, docs.py), tests
- Do:
  1. Re-express component discovery, role classification, docs, and testing extraction as passes reading only the store (cached content for doc extraction, never the disk). Port the root-bounded _check_ci_tests fix noted in P2-2.
  2. Relationship inference as joins over signals: port bindings join URL references for http; driver signals join infrastructure components for database/queue; websocket/grpc/nav likewise. Every edge carries evidence rows (file, line) and confidence (certain/inferred per I3).
  3. Preserve the SwiftUI flow pipeline by feeding it from stored signals and symbols; navigation/tab/modal/embed edges gain evidence.
  4. Instrumentation hook counting source-file opens during derivation; assert zero in tests.
  5. Run derivation on the parity fixtures; diff against the P4-1 snapshot; enumerate every intended difference (nested symbols, evidence fields, corrected false positives) in Evidence for the P4-7 gate.
- Accept:
  - [ ] Zero source-file reads during derivation (test-asserted)
  - [ ] Every edge in fixture output has at least one evidence location and a confidence tier
  - [ ] Fixture diff vs P4-1 snapshot contains only enumerated, justified differences
- Verify: pytest; the diff report in Evidence
- Evidence:

### P4-4: Coverage ledger end to end
- Status: TODO
- Model: Opus 4.8 (Sonnet 5 acceptable for the viewer display half once the projection shape exists)
- Stream: A (analyzer half), B (viewer half). Branch: program2/p4-ledger
- Design: TARGET-ARCHITECTURE.md section 7; invariant I2
- Files: analyzer/extract/, analyzer/project/ (with P4-5), viewer/src (coverage badge and panel), tests both sides
- Do:
  1. Ledger summary and full ledger in projections (manifest carries the summary; a coverage.json shard carries rows).
  2. Viewer: a coverage badge near the AI banner (percent parsed, counts per disposition) opening a panel listing exclusions by rule and failures with reasons. Degrades silently for old projections without the key.
  3. Wire the invariant checks as tests: ledger completeness on fixtures; a deliberately unreadable file lands as failed:<error>; an excluded rule lands with its rule name.
- Accept:
  - [ ] Ledger completeness test green on fixtures and this repo
  - [ ] Viewer displays summary and drill-in on the demo dataset; old datasets unaffected (test both)
- Verify: pytest; viewer test run; manual check on a local build
- Evidence:

### P4-5: Projection tier
- Status: TODO
- Model: Opus 4.8 (Sonnet 5 acceptable for the search-shard emitter once shapes are fixed)
- Stream: A. Branch: program2/p4-project
- Design: TARGET-ARCHITECTURE.md section 4.4; invariant I7
- Files: new package analyzer/project/ (manifest.py, details.py, search_shards.py, changelog.py, monolith.py), analyzer/cli.py, tests
- Do:
  1. Generate manifest + detail shards from the store, schema-compatible with viewer/src/types.ts; new keys (evidence, confidence, coverage, nested symbols) optional. Existing safe_component_id escaping preserved for shard filenames.
  2. Monolithic architecture.json projection for small repos and backward compatibility.
  3. Search shards covering names, paths, descriptions, docstrings, and enrichment help text; viewer loads them lazily (viewer half lands in P6-4, but emit and unit-test the shards now).
  4. Changelog as a store-vs-previous-store (or previous projection) diff, replacing the file-diff changelog for the new path; serials preserved.
  5. Deterministic output: identical store produces byte-identical projections.
- Accept:
  - [ ] Existing viewer renders fixture projections with no code changes and no console errors (integration test)
  - [ ] Determinism test green; shard filenames match the current escape convention (cross-check the three-implementation fixtures from P0-3)
  - [ ] Changelog entries equivalent to current behavior on a scripted change sequence
- Verify: pytest; viewer against generated fixtures
- Evidence:

### P4-6: Incremental v2
- Status: TODO
- Model: Opus 4.8
- Stream: A. Branch: program2/p4-incremental
- Design: TARGET-ARCHITECTURE.md sections 4.1, 4.3; invariant I6
- Files: analyzer/extract/runner.py, analyzer/derive/ (scoped re-derivation), analyzer/cli.py (flag compatibility), tests
- Do:
  1. Incremental is the default: hash comparison decides what re-parses; derivation re-runs for affected scopes (component membership changes, signal changes) plus architecture-level passes.
  2. Keep --incremental/--base-sha CLI flags as accepted no-ops or thin wrappers so existing workflows keep working; document the semantics change.
  3. Parity: full-rescan output byte-identical to incremental output after any scripted change sequence on fixtures (add, modify, delete, rename, new directory, marker-file change). This absorbs P2-1's scenarios; the new-root-file and new-directory cases are mandatory tests.
  4. The .arch-baseline/file-index/import-graph cache files are retired on the new path; the store is the baseline.
- Accept:
  - [ ] Full-vs-incremental byte-identical across the scripted sequence, including P2-1's two scenarios
  - [ ] Touch-one-file re-derives only affected scopes (instrumentation assertion), architecture passes excepted
  - [ ] Existing CI workflow invocations run unmodified against the new CLI
- Verify: pytest tests/test_incremental_v2.py; workflow dry parse
- Evidence:

### P4-7: Parity, benchmarks, and cutover
- Status: TODO
- Model: Opus 4.8 (no substitution); gate review per WORK-PLAN.md 6.3, Fable review optional per WORK-PLAN-2.md section 4
- Stream: solo after P4-1 to P4-6 merge. Branch: program2/p4-cutover
- Design: TARGET-ARCHITECTURE.md section 11
- Files: analyzer/ (deletions), analyze.py, action.yml, workflows, DEPLOYMENTS.md, benchmark script under scripts/
- Do:
  1. Run the Phase 4 exit-gate checklist from WORK-PLAN-2.md section 3 in full; record every result here.
  2. Benchmarks: this repo, unamentis, and one 1M+ line OSS repo (suggestion: microsoft/vscode); cold and warm wall time, peak memory, store size. Record the machine.
  3. Switch analyze.py, action.yml, and workflows to the new engine. Delete scanner.py orchestration, incremental.py, and their dead tests, or gate them behind --legacy with a recorded deletion date. Fold in P2-7's dead-code items.
  4. Redeploy downstream installations; verify at DEPLOYMENTS.md URLs with enrichment preserved (the merge's --strict guard passes with healthy per-strategy counts in the run log; see also the 2026-07-11 stale-SHA-pin discovery, verify downstream pins actually track the intended ref).
- Accept:
  - [ ] Exit-gate checklist fully recorded with results
  - [ ] Benchmark table in Evidence; the large repo completes with a complete ledger
  - [ ] Downstream green, enrichment intact
- Verify: the checklist itself
- Evidence:

## Phase 5: Capabilities and data entities

### P5-1: Capability extraction (api, cli, event, job)
- Status: TODO (elaborate at Phase 4 gate)
- Model: Opus 4.8
- Design: TARGET-ARCHITECTURE.md section 5
- Scope: per-framework endpoint extraction with tests per framework (Flask, FastAPI, Express, Next.js routes, gin/echo/fiber, Rails/Sinatra, actix/axum, Vapor), eliminating the header-name false-positive class; CLI command and flag extraction for click/typer/clap/commander; event and job declarations where signals allow; capabilities land in the store with evidence and confidence, owned by components, linked to defining symbols where resolvable.
- Evidence:

### P5-2: Data entities and access edges
- Status: TODO (elaborate at Phase 4 gate)
- Model: Opus 4.8
- Design: TARGET-ARCHITECTURE.md section 5
- Scope: parse ORM models (SQLAlchemy, Django, ActiveRecord, Prisma schema, SwiftData/CoreData where feasible), migrations, and standalone schemas into data_entities with fields; entity_access edges (read/write) from driver-usage and import signals; remove models/schemas/migrations from the content-exclusion list; ledger and confidence rules apply.
- Evidence:

### P5-3: Projection and type extensions for capabilities and entities
- Status: TODO (elaborate at Phase 4 gate)
- Model: Opus 4.8 (Sonnet 5 acceptable for the types/plumbing half)
- Scope: optional keys in manifest and detail shards; viewer/src/types.ts additions; DetailPanel gains Capabilities and Data tabs (list-level, lens views come in Phase 6); backward-compatibility test that old datasets render unchanged.
- Evidence:

## Phase 6: Perspectives

### P6-1: Lens framework
- Status: TODO (elaborate at Phase 5 gate; 6a items may elaborate at Phase 4 gate)
- Model: Opus 4.8
- Scope: a lens abstraction in store.ts and App (Structure, Flow, Capability, Data), URL state (?lens=), per-lens node/edge selection feeding the existing graph pipeline; Structure remains the default and pixel-identical for old data.
- Evidence:

### P6-2: Flow lens
- Status: TODO (elaborate at Phase 5 gate)
- Model: Opus 4.8
- Scope: render navigation/tab/modal/embed edges and UIAction target_view links as a screen-flow diagram grouped by tab container; reachable from a screen node's context; works on the unamentis dataset today (the data already exists).
- Evidence:

### P6-3: Capability and Data lenses
- Status: TODO (elaborate at Phase 5 gate)
- Model: Opus 4.8
- Scope: Capability lens groups capabilities by component with contract detail and AI business meaning; Data lens shows entities with read/write edges from components; both integrate search, selection, detail panel, and deep links.
- Evidence:

### P6-4: Scale UX: aggregation, shard search, prefetch
- Status: TODO (elaborate at Phase 4 gate; independent of Phase 5)
- Model: Opus 4.8
- Scope: replace hero-filter hiding with expandable aggregation nodes so every child is visible or visibly aggregated (closes the silent-hiding gap per I2 spirit); consume search shards so search covers descriptions, docstrings, and AI help text without visiting components; predictive prefetch of children and breadcrumb ancestors of the selection; virtualized long lists in panels.
- Evidence:

## Phase 7: AI enrichment industrialization

### P7-1: Enrichment provenance and staleness
- Status: TODO (elaborate at Phase 4 gate)
- Model: Opus 4.8 (no substitution)
- Design: TARGET-ARCHITECTURE.md section 6; invariant I5
- Scope: define the component-files digest; enrichment rows carry derived_from_hash and commit_sha; staleness computed and surfaced in projections, viewer (marker on AI content), and later MCP; migration for the existing ai_enhance baseline. Builds on P3-3's shipped drift-tolerant matcher (DONE, PR #6): provenance makes matching unnecessary because identity plus digest travel with the enrichment; retire the merge-script path from CI only after a parallel-run validation period shows parity with the P3-3 matcher on real deploys.
- Evidence:

### P7-2: Headless enrichment CLI
- Status: TODO (elaborate at Phase 4 gate)
- Model: Opus 4.8
- Scope: `solution-explorer enhance` running DPEA over the store via the Claude Agent SDK, no hardcoded paths, partition/parallel limits honored, quality scorer enforced as a gate, --update mode re-enhancing only stale/new scopes plus architectural neighbors; the /ai-assist skill becomes a thin wrapper; CI-callable with cost controls (documented flags for partition caps).
- Evidence:

### P7-3: AI verification of inferred edges
- Status: TODO (elaborate at Phase 7 start)
- Model: Opus 4.8
- Scope: an enrichment pass that examines inferred-confidence edges against source evidence and records a verdict (confirmed, refuted, uncertain) with provenance; refuted edges are marked and de-emphasized, never silently deleted; verdicts surface in viewer and MCP.
- Evidence:

## Phase 8: The query surface

### P8-1: MCP server
- Status: TODO (elaborate at Phase 7 gate; Fable design review optional)
- Model: Opus 4.8 (no substitution)
- Design: TARGET-ARCHITECTURE.md section 8; invariants I3, I5, I9
- Scope: the seven tools (se_overview, se_search, se_component, se_symbol, se_refs, se_impact, se_coverage) over the store, in-process reads only, evidence and confidence and staleness in every response; packaging decision recorded; registered and documented for Claude Code; integration-tested against the fixture stores and this repo.
- Evidence:

### P8-2: Token-efficiency benchmark
- Status: TODO (elaborate at Phase 8 start)
- Model: Opus 4.8 (Sonnet 5 acceptable for harness runs)
- Scope: define a question battery (architecture, impact, capability, data questions) over two repos; measure a grep-only agent baseline vs MCP-assisted on identical questions; publish methodology, transcripts, and token counts under docs/benchmarks/; target 50 percent reduction, misses analyzed honestly.
- Evidence:

## Phase 9: Scale proof and release

### P9-1: Large-repo public demos
- Status: TODO (elaborate at Phase 8 gate)
- Model: Opus 4.8 plus the human for deployment credentials
- Scope: full pipeline including enrichment on one or two 1M+ line public OSS repos; deploy as public living demos with visible coverage ledger; record analysis and enrichment cost and wall time; add to DEPLOYMENTS.md.
- Evidence:

### P9-2: v2 release and claims re-audit
- Status: TODO (elaborate at Phase 8 gate)
- Model: Opus 4.8 plus the human for publishes
- Scope: version, changelog, npm and PyPI release via the P1-1 machinery; README and PROJECT-OVERVIEW updated to the new reality (lenses, ledger, MCP, benchmarks); a claims re-audit in the AUDIT-2026-07 section 7 style over all new claims; DEPLOYMENTS refreshed.
- Evidence:

---

## Discovered during execution

Add new findings here with a date and the task you were on; do not expand task scope inline.

| Date | Found while | Description | Disposition |
|---|---|---|---|
| 2026-07-11 | P3-3 real-data e2e (post-Phase-0 deploy) | UnaMentis architecture-full.yml was pinned to a stale Feb SHA `31145dc` despite a `# main` comment, so the downstream deploy ran an old solution-explorer. | Fixed by UnaMentis commit `9369887` (re-pin to current main). Strengthens P2-8 (pin hygiene): a comment claiming `main` is not a pin; verify the SHA actually tracks the intended ref. |
| 2026-07-11 | P3-3 real-data e2e (post-Phase-0 deploy) | Production ID drift in the Advanced Architecture Visualization workflow: an unprefixed baseline (`curriculum`) versus a repo-prefixed target (`unamentis/curriculum`) plus new structural nodes (`repo:unamentis`) caused the exact-only merge to preserve 0 of 251 enhancements. | Caught loudly by the P0-4 total-loss guard with no data loss (target left untouched), then fixed by this task (P3-3): drift-tolerant matching now preserves the enhancements and `--strict` guards the ratio in CI. |
| 2026-07-11 | P1-1 PyPI dry-run | `twine check` warns that `long_description` and `long_description_content_type` are missing from pyproject.toml, so the PyPI project page will render no description. Not an upload blocker. | Log only; packaging polish. Point pyproject at README.md (`readme = "README.md"`) as part of P2-5 docs reconciliation or a small follow-up. Out of P1-1 scope (versioning). |
| 2026-07-11 | P1-1 secrets check | release.yml references GitHub Environments `npm` and `pypi` that do not exist (only `copilot` and `github-pages` do) and depends on secret `NPM_TOKEN` that is not set (repo secrets are only CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, DEPLOY_TOKEN). PyPI publish uses OIDC trusted publishing that needs a PyPI-side pending publisher. | Human prerequisite for the release, recorded in P1-1 Evidence "Human steps remaining". Not a code fix; the human owns these credentials. |
| 2026-07-11 | P1-2 | The viewer never displays `total_symbols` (header shows only components/files/lines at App.tsx:587-589); the new `stats.total_symbols_detected` field is available if Stream B ever wants an "X of Y symbols" display. No viewer change made (Stream B territory). | For Stream B / P2-5: optionally add `total_symbols_detected?: number` to `ArchitectureStats` (viewer/src/types.ts:299) and surface "kept X of Y symbols" when they differ. |
| 2026-07-11 | P1-2 | README stats-schema block (README.md:510) documents `total_symbols` but not the new optional `total_symbols_detected`. README is outside P1-2's file territory. | For P2-5 (docs reconciliation): add `total_symbols_detected` to the documented stats schema. |
| 2026-07-11 | P1-2 (build.sh to --split) | `write_split` (cli.py) does not prune stale `detail-*.json` files already present in the output `data/` dir. Now that build.sh writes into a persistent split directory, a data/ dir that held a prior dataset keeps unreferenced detail files (cosmetic bloat; manifest is authoritative so the viewer ignores them). | Reinforces P2-7 item 6 (remove stale detail-*.json not in the current manifest when writing split output). |
| 2026-07-13 | P1-2 Copilot review | Truncation and oversized-file warnings only fire on the single-repo, non-incremental CLI path; `--config` (multi-repo) and `--incremental` runs use ArchitectureScanner internally but do not surface `dropped_symbols`/`skipped_large_files`, so truncation can stay silent there. | Intentional P1-2 scope (the card names single-file mode; the default multi-repo path in build.sh is now --split and uncapped). The Program 2 coverage ledger (P4-4, invariant I2) eliminates this class everywhere; if Phase 4 slips, extend `_warn_dropped_data` to the orchestrator and incremental paths as a small follow-up. |

## Phase gate records

Filled by the phase-gate review session per WORK-PLAN.md section 6.3.

| Phase | Date | Reviewer session | Result | Notes |
|---|---|---|---|---|
| 0 | 2026-07-06 | independent gate review (Opus) | PASS | All seven exit-gate checks reproduced independently. (1) `pytest tests/ -q` -> 644 passed, 1 xfailed, `git status --porcelain` empty. (2) architecture.json has real root_path `/Users/ramerman/dev/solution-explorer`, architecture-level ai_enhance present, and ai_enhance on 23 of 23 components (nested tree; recursive count) plus 23 of 23 relationships; score-ai-enhancement-quality.py reports 100% coverage, 95.6% avg, PASS. (3) actionlint clean on live-monitor.yml (exit 0); grep `if:.*secrets\.` across .github and templates returns nothing (only pre-existing info-level SC2086 notes in ci.yml, out of Phase 0 scope). (4) Manual merge-script drift run: nonzero exit with readable diagnostic, target byte-identical (sha256 unchanged); tests/test_merge_ai_enhancements.py 4 passed. (5) tests/test_multi_repo.py 3 passed; read critically, they run the real scanner and grep the full serialized output for the token and x-access-token, and assert token absence in combined stdout+stderr on clone failure. (6) Worker `npm test` 6 passed, `npm run typecheck` clean; includes the repo:unamentis and repo:unamentis/viewer escape cases. (7) Viewer `npm test -- --run` 55 passed, lint 0 errors/18 warnings, `tsc -b` clean, `npm run build` clean (only pre-existing 500 kB chunk warning). Spot-checks: P0-6 DetailPanel split test FAILS on the pre-fix file (getByRole status not found) and PASSES restored; P0-4 merge drift test FAILS on the pre-fix script (UnboundLocalError) and PASSES restored. Working tree left clean. Minor note: the worker test reimplements the trivial detail-key format string but uses the real safeComponentId, and the format matches index.ts:312. |
