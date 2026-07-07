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
- Status: TODO
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

### P0-5: Stop GITHUB_TOKEN reaching output JSON and CI logs
- Status: TODO
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

### P0-6: Split-mode detail panel renders lazily loaded data, with a visible loading state
- Status: TODO
- Model: Opus 4.8
- Stream: B (viewer). Branch: remediation/p0-viewer
- Findings: F-CRIT-4
- Files: viewer/src/components/DetailPanel.tsx (near 127-135), viewer/src/store.ts if needed, new test file
- Do:
  1. Make the memo (or the data access) depend on the cache content, not just `component.id`. Cleanest: subscribe to `componentDetailCache[component.id]` via a selector so the panel re-renders when the fetch lands.
  2. Render `componentDetailLoading` as a visible loading state on the Files and Symbols tabs.
  3. Component test with a mocked `fetch` and the real store: open a split-mode component, assert loading state appears, resolve the fetch, assert files and symbols render and counts update. This is the regression test for the whole split-mode path; do not mock the store.
- Accept:
  - [ ] Test proves empty-then-loading-then-populated sequence against the real store and real DetailPanel
  - [ ] Manual check in a local `--split` build of this repo: Files and Symbols tabs populate on first click
- Verify: viewer test run; manual: `python3 analyze.py . --split -o viewer/public/architecture && cd viewer && npm run dev`
- Evidence:

---

## Phase 1: Make the front-door promise true

### P1-1: Reconcile versioning and ship the first real release
- Status: TODO
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
  - [ ] Version decision recorded here with rationale
  - [ ] release.yml green; npm, PyPI, and GitHub release all show the version
  - [ ] `npx solution-explorer@latest` works from cold cache
  - [ ] README badge renders the release
- Verify: commands listed above
- Evidence:

### P1-2: Uncapped analysis on the default paths; loud truncation everywhere else
- Status: TODO
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
  - [ ] `npx` local run (`node packages/cli/dist/... generate` or via npm link) produces a split-mode site
  - [ ] Single-file truncation prints a warning and stats are internally consistent (test-asserted)
  - [ ] README CLI docs updated if flags changed
- Verify: unit tests; run build.sh against this repo and inspect output shape
- Evidence:

### P1-3: Persist review annotations across reloads
- Status: TODO
- Model: Opus 4.8
- Stream: B. Branch: remediation/p1-viewer
- Findings: F-VW-4, F-DC rows 3 and 11
- Files: viewer/src/store.ts (annotation state, 145, 300, 423-454), new persistence util, tests
- Do:
  1. Persist annotations to localStorage keyed by a stable architecture identity (name plus repository; do not key on `generated_at` or annotations vanish on every re-analysis). Include a schema version field and a size guard consistent with the existing localStorage patterns.
  2. Restore on load; reconcile annotations whose target component no longer exists (keep them, flag as orphaned in ReviewSummary, so re-analysis does not silently destroy feedback).
  3. Tests against the real store: add annotations, simulate reload (fresh store, same storage), assert restoration; orphan case; storage-quota failure does not crash.
- Accept:
  - [ ] Hard reload preserves annotations (test plus manual check)
  - [ ] Orphaned annotations visible, not silently dropped, after loading a changed architecture
  - [ ] PROJECT-OVERVIEW/README wording about persistence updated to the now-true claim (or noted for P2-5)
- Verify: viewer tests; manual annotate-reload check
- Evidence:

### P1-4: Fix popstate history corruption
- Status: TODO
- Model: Opus 4.8
- Stream: B. Branch: remediation/p1-viewer (same session as P1-3/P1-5, sequenced; shared files)
- Findings: F-VW-2
- Files: viewer/src/App.tsx (321-366), viewer/src/utils/urlState.ts, tests
- Do: add a suppression mechanism (ref flag set during popstate handling) so store-driven URL pushes are skipped while applying a popstate navigation; use `replaceState` where appropriate. Test with jsdom: drill twice, fire popstate for the earlier state, assert history length does not grow and forward state remains reachable; assert URL reflects the restored state.
- Accept:
  - [ ] Back then Forward restores the same drill state (test-asserted and manual)
  - [ ] No new history entry is created while handling popstate (test-asserted)
- Verify: viewer tests; manual browser check
- Evidence:

### P1-5: Live refresh must not wipe search or serve stale details
- Status: TODO
- Model: Opus 4.8
- Stream: B. Branch: remediation/p1-viewer
- Findings: F-VW-3, plus the stale `componentDetailCache` item in F-VW-7
- Files: viewer/src/utils/search.ts, viewer/src/store.ts (574-602), viewer/src/hooks/useLiveMonitor.ts (near 165), tests
- Do:
  1. On live manifest refresh, rebuild the search index from the new manifest and re-add entries for every component already in `componentDetailCache`, or make the index rebuild preserve detail-derived entries keyed by component.
  2. Invalidate (or version-check) `componentDetailCache` when the architecture updates, so panels do not show stale symbols; the next open refetches.
  3. Tests: index a detail-loaded symbol, apply a live refresh, assert the symbol is still searchable; assert cache invalidation triggers a refetch.
- Accept:
  - [ ] Post-refresh search still finds previously loaded symbols (test-asserted)
  - [ ] Detail panel shows post-refresh data after an update (test-asserted)
- Verify: viewer tests
- Evidence:

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
- Status: TODO
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
- Status: TODO
- Model: Opus 4.8
- Stream: A. Branch: remediation/p3-analyzer
- Findings: F-CRIT-6 root cause, F-PL-3 (dispatch path relies on this merge)
- Files: scripts/merge-ai-enhancements.py, tests, optionally scripts/validate-ai-preservation.py wiring
- Do:
  1. Add fallback matching when exact ID fails: match by component `path`, then by (name, type) as a last resort; same idea for relationships via (source-path, target-path, type). Report per-strategy match counts in the output.
  2. Add a `--strict` flag (exit nonzero below a preservation threshold) and use it in CI workflows so silent data loss becomes impossible.
  3. Wire scripts/validate-ai-preservation.py (already exists) into architecture-viz.yml as a post-merge check.
  4. Tests: exact match, renamed-ID-same-path drift (preserved), true component removal (not preserved, not counted as failure), threshold failure exits nonzero.
- Accept:
  - [ ] Drift scenario preserves enhancements (test-asserted, fails on the pre-fix exact-only matcher)
  - [ ] CI merge step is strict; a simulated total-loss merge fails the workflow
- Verify: pytest; workflow file review; one manual downstream dispatch after merge, checking the preservation counts in the run log
- Evidence:

### P3-4 (optional, stretch): Decompose scanner.py
- Status: TODO
- Model: Opus 4.8
- Stream: solo, only after P2-2's identical-output guard exists
- Findings: F-AN-12 (size), enabled by P2-2
- Do: split the 2,666-line ArchitectureScanner along its natural seams (relationship strategies, docs/testing extraction) into modules, preserving the public API and the identical-output test. Skip this task entirely if timeline pressure exists; it is leverage for the future, not a defect.
- Accept:
  - [ ] Identical-output test green; no module over ~800 lines; public imports unchanged (analyze.py and action.yml paths still work)
- Verify: pytest; self-analysis smoke run
- Evidence:

---

## Discovered during execution

Add new findings here with a date and the task you were on; do not expand task scope inline.

| Date | Found while | Description | Disposition |
|---|---|---|---|

## Phase gate records

Filled by the phase-gate review session per WORK-PLAN.md section 6.3.

| Phase | Date | Reviewer session | Result | Notes |
|---|---|---|---|---|
