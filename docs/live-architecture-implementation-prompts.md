# Live Architecture Implementation: Execution Prompts

Prompts for parallel execution of the live architecture implementation plan across multiple Claude Code sessions. Each session gets one stream.

---

## Execution Plan

### Phase 1: Foundation (Tier 0, run first, both in parallel)

These two streams have zero dependencies. Start them simultaneously. All Tier 1 work is blocked until these complete.

| Session | Stream | Est. Scope | Branch |
|---------|--------|-----------|--------|
| 1 | **A**: Remove Vanilla Python Constraint | Small (docs + pyproject.toml) | `live/stream-a` |
| 2 | **B**: Types + Store Foundation | Medium (types.ts, store.ts, tests) | `live/stream-b` |

### Phase 2: Features (Tier 1, run after Phase 1 merges)

Merge Streams A and B into `main` first. Then launch all six of these in parallel. They have no cross-dependencies.

| Session | Stream | Requires | Branch |
|---------|--------|----------|--------|
| 3 | **C**: Admin Dashboard UI | B merged | `live/stream-c` |
| 4 | **D**: Status Dashboard + Component Status UI | B merged | `live/stream-d` |
| 5 | **E**: Live Monitor Hooks | B merged | `live/stream-e` |
| 6 | **F**: GitHub Actions Workflow + CI Collection | A merged | `live/stream-f` |
| 7 | **G**: Incremental Analyzer | A merged | `live/stream-g` |
| 8 | **I**: Pydantic Models + Validation | A merged | `live/stream-i` |

**App.tsx note**: Streams C, D, and E each touch App.tsx in non-overlapping sections. Merge conflicts will be trivial (import lines at top). Merge them one at a time into main, resolving conflicts as they arise.

### Phase 3: Advanced (Tier 2, run after specific Tier 1 merges)

| Session | Stream | Requires | Branch |
|---------|--------|----------|--------|
| 9 | **H**: Cloudflare-Enhanced Mode | F, G, E merged | `live/stream-h` |
| 10 | **J**: Tree-Sitter Parsing | I merged | `live/stream-j` |
| 11 | **K**: True Incremental Re-Analysis | G, J merged | `live/stream-k` |

### Phase 4: Integration (Tier 3, after all streams merged)

Run integration testing from the implementation doc's "Integration Testing" section. This can be done in a single session against main after all merges.

---

## Session Prompts

Copy the prompt for a given stream into a fresh Claude Code session. Each prompt is self-contained.

---

### Stream A: Remove Vanilla Python Constraint

```
You are implementing Stream A of the live architecture monitoring feature for solution-explorer.

Read the full implementation plan at docs/live-architecture-implementation.md, then execute all tasks under "Stream A: Remove Vanilla Python Constraint" (Tasks A.1 and A.2).

Work on branch: live/stream-a (create from main)

Summary of what to do:
- Audit and update all documentation that says "zero dependencies / stdlib only"
- Replace with pragmatic dependency policy: core analyzer requires only stdlib, optional deps for advanced features
- Files to update: README.md, CONTRIBUTING.md, analyze.py docstring, analyzer/__init__.py docstring, PROJECT-OVERVIEW.md
- Create pyproject.toml at project root with the dependency groups specified in the plan

Run Verification A when done:
- python3 -c "from analyzer.scanner import ArchitectureScanner" works without optional deps
- pip install -e ".[incremental]" installs gitpython
- pytest tests/ -v passes

Commit when verification passes.
```

---

### Stream B: Types + Store Foundation

```
You are implementing Stream B of the live architecture monitoring feature for solution-explorer.

Read the full implementation plan at docs/live-architecture-implementation.md, then execute all tasks under "Stream B: Types + Store Foundation" (Tasks B.1, B.2, and B.3).

Work on branch: live/stream-b (create from main)

Summary of what to do:
- Add all new live monitoring types to viewer/src/types.ts (ComponentStatus, ArchitectureStatus, StatusOverlay, ComponentLiveStatus, LiveVersion, LiveConfig, AdminSummaryRepo, AdminSummaryActivity, AdminSummary)
- Add optional live_status fields to Component and Architecture interfaces
- Extend the Zustand store in viewer/src/store.ts with new state fields and actions
- Implement applyStatusOverlay and navigateToComponent
- Write unit tests in viewer/src/__tests__/store.test.ts

IMPORTANT FEEDBACK (apply these changes to the plan):
1. In applyStatusOverlay, build a flat Map<string, Component> index for O(1) lookups instead of doing recursive tree traversal on every call. For large architectures, recursive traversal on every poll cycle (15-120s) is wasteful.
2. Confirm that no new npm dependencies are needed. All viewer streams should use only existing dependencies (React, Zustand, React Flow).

Run Verification B when done:
- cd viewer && npm test passes with new tests
- cd viewer && npx tsc -b compiles without errors
- No existing tests broken

Commit when verification passes.
```

---

### Stream C: Admin Dashboard UI

```
You are implementing Stream C of the live architecture monitoring feature for solution-explorer.

Read the full implementation plan at docs/live-architecture-implementation.md, then execute all tasks under "Stream C: Admin Dashboard UI" (Tasks C.1 through C.4).

Work on branch: live/stream-c (create from main, which should have Stream B merged)

Summary of what to do:
- Create AdminDashboard.tsx modal (follow SearchOverlay.tsx pattern)
- Create useAdminData hook
- Create 5 tab components: HealthTab, ActivityTab, HistoryTab, SettingsTab, ResourcesTab
- Integrate admin button into App.tsx header
- ESC to close, Cmd+Shift+A to toggle

IMPORTANT FEEDBACK (apply these changes to the plan):
1. SettingsTab MUST be read-only in GitHub mode. In GitHub mode there is no backend to persist changes. Show a message like "Edit solution-explorer.json in your repo to change settings." Only make settings mutable when backend_mode is "cloudflare". Without this, users will toggle settings and wonder why nothing persists.
2. No new npm dependencies should be added.

Run Verification C when done:
- Admin button appears only when liveConfig is set
- Cmd+Shift+A opens/closes the dashboard
- ESC closes the dashboard
- All 5 tabs render
- Resources tab hidden in GitHub mode
- cd viewer && npm test && npx tsc -b

Commit when verification passes.
```

---

### Stream D: Status Dashboard + Component Status UI

```
You are implementing Stream D of the live architecture monitoring feature for solution-explorer.

Read the full implementation plan at docs/live-architecture-implementation.md, then execute all tasks under "Stream D: Status Dashboard + Component Status UI" (Tasks D.1 through D.4).

Work on branch: live/stream-d (create from main, which should have Stream B merged)

Summary of what to do:
- Create StatusDashboard.tsx component (renders between header banners and main content)
- Add status badge rendering to ComponentNode.tsx (colored dots alongside criticality dots)
- Add Status tab to DetailPanel.tsx (conditional, only when live_status exists)
- Integrate StatusDashboard into App.tsx
- Clicking affected components navigates via navigateToComponent from store

No new npm dependencies should be added.

Run Verification D when done:
- StatusDashboard only appears when live_status has non-ok statuses
- StatusDashboard hidden when no live data present (backward compat)
- Clicking affected component navigates correctly
- Status dots appear on ComponentNode alongside criticality dots
- Status tab appears in DetailPanel only when live_status exists
- cd viewer && npm test && npx tsc -b

Commit when verification passes.
```

---

### Stream E: Live Monitor Hooks

```
You are implementing Stream E of the live architecture monitoring feature for solution-explorer.

Read the full implementation plan at docs/live-architecture-implementation.md, then execute all tasks under "Stream E: Live Monitor Hooks" (Tasks E.1 through E.3).

Work on branch: live/stream-e (create from main, which should have Stream B merged)

Summary of what to do:
- Create useLiveMonitor.ts hook with init, adaptive polling, circuit breaker, visibility control, localStorage cache
- Integrate into App.tsx (hook call + connection status indicator in header)
- Write tests for interval calculation, circuit breaker, visibility pause/resume

IMPORTANT FEEDBACK (apply these changes to the plan):
1. Circuit breaker: Do NOT use a terminal "stay paused" state. After the initial 60s pause and failed retry, enter a slow-retry backoff (retry every 5 minutes while in error state). Reset to normal adaptive polling on first success. A terminal pause means a viewer left open overnight stops updating after a transient GitHub Pages outage.
2. Add a full refresh safety net: every 30 minutes, do a full data fetch regardless of ETag state. This catches edge cases where CDN cache inconsistency causes ETag-based polling to miss a change.
3. No new npm dependencies should be added.

Run Verification E when done:
- Without live-config.json: viewer loads identically to current static mode
- With live-config.json: polling starts, connection indicator shows
- Circuit breaker activates after 5 failures, self-heals via slow backoff
- Tab visibility pause/resume works
- localStorage caching works
- cd viewer && npm test && npx tsc -b

Commit when verification passes.
```

---

### Stream F: GitHub Actions Workflow + CI Collection

```
You are implementing Stream F of the live architecture monitoring feature for solution-explorer.

Read the full implementation plan at docs/live-architecture-implementation.md, then execute all tasks under "Stream F: GitHub Actions Workflow + CI Collection" (Tasks F.1 through F.4).

Work on branch: live/stream-f (create from main, which should have Stream A merged)

Summary of what to do:
- Create .github/workflows/live-monitor.yml
- Create scripts/collect-ci-status.py (stdlib only: urllib.request, json, argparse)
- Create scripts/generate-admin-summary.py
- Optionally add live-monitor input to action.yml

IMPORTANT FEEDBACK (apply these changes to the plan):
1. Use GitHub's official actions/deploy-pages + actions/upload-pages-artifact instead of peaceiris/actions-gh-pages@v4. This reduces supply-chain risk and does not require granting a PAT to a third-party action.
2. Address the race condition between update-architecture and update-ci-status deployments. Both jobs deploy to gh-pages and can race. Preferred solution: use a shared concurrency group that covers both jobs, or fold update-ci-status into update-architecture as a single deployment step.

Run Verification F when done:
- Workflow YAML is valid
- python scripts/collect-ci-status.py --repo owner/repo --sha HEAD -o /tmp/status.json runs (requires GITHUB_TOKEN)
- Generated JSON files match their TypeScript type definitions in shape
- pytest tests/ -v still passes

Commit when verification passes.
```

---

### Stream G: Incremental Analyzer

```
You are implementing Stream G of the live architecture monitoring feature for solution-explorer.

Read the full implementation plan at docs/live-architecture-implementation.md, then execute all tasks under "Stream G: Incremental Analyzer" (Tasks G.1 through G.3).

Work on branch: live/stream-g (create from main, which should have Stream A merged)

Summary of what to do:
- Create analyzer/incremental.py with IncrementalAnalyzer class
- Add --incremental, --base-sha, --head-sha, --baseline CLI flags to analyzer/cli.py
- Write tests in tests/test_incremental.py

IMPORTANT FEEDBACK (apply this change to the plan):
1. Add an analyzer version stamp to the baseline. Include a version string (e.g., from pyproject.toml or a constant in the code) in the saved baseline. When the current analyzer version differs from the baseline's version, should_full_rescan() returns True. This ensures parser improvements are applied to all files, not just changed ones.

Run Verification G when done:
- python analyze.py --incremental --base-sha HEAD~1 --head-sha HEAD -o /tmp/arch-test/ . runs successfully
- Falls back to full rescan when no baseline exists
- pytest tests/test_incremental.py -v passes
- pytest tests/ -v passes (existing tests unaffected)

Commit when verification passes.
```

---

### Stream I: Pydantic Models + Validation

```
You are implementing Stream I of the live architecture monitoring feature for solution-explorer.

Read the full implementation plan at docs/live-architecture-implementation.md, then execute all tasks under "Stream I: Pydantic Models + Validation" (Tasks I.1 through I.6).

Work on branch: live/stream-i (create from main, which should have Stream A merged)

Summary of what to do:
- Update pyproject.toml with pydantic dependency (if not already done by Stream A)
- Rewrite analyzer/models.py with Pydantic BaseModel (with dataclass fallback)
- Integrate into scanner.py
- Update multi_repo.py for Pydantic-aware model handling
- Add --validate CLI flag
- Write tests in tests/test_models.py

IMPORTANT FEEDBACK (apply this change to the plan):
1. The Architecture root_validator that checks all relationship sources/targets exist in component IDs should only run when the --validate CLI flag is used, NOT on every Architecture construction. For large architectures this is O(relationships) even with a set (building the ID set is O(components)), and it runs on every construction. Make the cross-reference check opt-in via a class method like Architecture.validate_cross_references() that the CLI calls when --validate is set.

Run Verification I when done:
- pip install -e ".[models]" installs pydantic
- python analyze.py . -o /tmp/test.json works with pydantic
- python analyze.py . -o /tmp/test.json --validate reports validation summary
- Core analyzer still works without pydantic
- pytest tests/test_models.py -v passes
- pytest tests/ -v all existing tests pass
- JSON output structure unchanged

Commit when verification passes.
```

---

### Stream H: Cloudflare-Enhanced Mode

```
You are implementing Stream H of the live architecture monitoring feature for solution-explorer.

Read the full implementation plan at docs/live-architecture-implementation.md, then execute all tasks under "Stream H: Cloudflare-Enhanced Mode" (Tasks H.1 through H.9).

Work on branch: live/stream-h (create from main, which should have Streams F, G, and E merged)

Summary of what to do:
- Create the full infrastructure/cloudflare/ directory structure
- Implement Worker with /ingest, /webhook, /health, /settings endpoints
- Create D1 schema, wrangler.toml, setup script, README
- Implement webhook signature validation
- Resource tracking and self-throttling middleware
- Update live-monitor.yml for conditional R2 upload
- Update useLiveMonitor.ts for CF mode support

IMPORTANT FEEDBACK (apply these changes to the plan):
1. Use timing-safe comparison for webhook signature verification. Replace the string === comparison with crypto.subtle.timingSafeEqual or a byte-by-byte constant-time comparison. The practical risk is low but it is a best practice.
2. Add R2 lifecycle cleanup: after processing a new architecture version in /ingest, compare the manifest's component IDs against existing detail files in R2 and delete orphaned detail-{component-id}.json files.

Run Verification H when done:
- cd infrastructure/cloudflare/worker && npx tsc -b compiles
- cd infrastructure/cloudflare/worker && wrangler dev starts local worker
- curl -X POST localhost:8787/ingest with valid auth returns 204
- curl -X POST localhost:8787/webhook with valid signature processes event
- curl localhost:8787/health returns status JSON
- Resource tracking increments correctly in D1
- Self-throttling returns 429 when limits approached
- Setup script is executable and well-documented

Commit when verification passes.
```

---

### Stream J: Tree-Sitter Parsing

```
You are implementing Stream J of the live architecture monitoring feature for solution-explorer.

Read the full implementation plan at docs/live-architecture-implementation.md, then execute all tasks under "Stream J: Tree-Sitter Parsing" (Tasks J.1 through J.8).

Work on branch: live/stream-j (create from main, which should have Stream I merged)

Summary of what to do:
- Update pyproject.toml with tree-sitter dependencies (if not already present)
- Create TreeSitterParser base class in analyzer/parsers/tree_sitter_base.py
- Create language-specific parsers: swift_ts.py, typescript_ts.py, rust_ts.py (high priority), then python_ts.py, go_ts.py, ruby_ts.py (medium/low)
- Update parser registry in analyzer/parsers/__init__.py
- Write comparison tests in tests/test_tree_sitter.py

Key design: Hybrid approach. Tree-sitter for symbol extraction and imports. Regex stays for framework/port/API endpoint detection. Each tree-sitter parser wraps the regex parser as fallback.

Run Verification J when done:
- pip install -e ".[treesitter]" installs tree-sitter
- python analyze.py . works with tree-sitter (uses AST parsers)
- python analyze.py . works without tree-sitter (falls back to regex)
- Tree-sitter produces superset of regex parser symbols
- pytest tests/test_tree_sitter.py -v passes
- pytest tests/ -v all existing tests pass

Commit when verification passes.
```

---

### Stream K: True Incremental Re-Analysis

```
You are implementing Stream K of the live architecture monitoring feature for solution-explorer.

Read the full implementation plan at docs/live-architecture-implementation.md, then execute all tasks under "Stream K: True Incremental Re-Analysis" (Tasks K.1 through K.7).

Work on branch: live/stream-k (create from main, which should have Streams G and J merged)

Summary of what to do:
- Add component dependency graph builder to analyzer/incremental.py
- Implement selective file re-scanning (rescan_component, merge_component_into_baseline)
- Implement incremental relationship detection
- Rewrite IncrementalAnalyzer.run() for the true incremental pipeline
- Implement baseline caching strategy (.arch-baseline/ directory)
- Add scoped scanning mode to analyzer/scanner.py
- Extend tests in tests/test_incremental.py

IMPORTANT FEEDBACK (apply this change to the plan):
1. Dependency graph expansion should be one level deep by default (direct importers of changed components). Document this as a known limitation. Transitive re-exports can cause missed updates, but one level covers the vast majority of cases. If needed later, add a --deep-incremental flag for transitive expansion.

Run Verification K when done:
- python analyze.py --incremental --base-sha HEAD~1 --head-sha HEAD -o /tmp/test/ . uses true incremental path
- Only affected components are rescanned (visible in verbose output)
- Result matches full scan for the same HEAD
- Incremental scan is significantly faster than full scan for small changes
- pytest tests/test_incremental.py -v passes
- pytest tests/ -v all tests pass

Commit when verification passes.
```

---

## Merge Order

After each phase, merge into main in this order:

**Phase 1**: Stream A, then Stream B (or reverse, no conflict)

**Phase 2** (suggested merge order to minimize conflicts):
1. Stream F (GitHub Actions, no viewer changes)
2. Stream G (analyzer only, no viewer changes)
3. Stream I (analyzer only, no viewer changes)
4. Stream C (viewer, touches App.tsx imports + admin button area)
5. Stream D (viewer, touches App.tsx + ComponentNode + DetailPanel)
6. Stream E (viewer, touches App.tsx + new hook)

**Phase 3**: Stream H, then Stream J, then Stream K

After each merge, verify `npm test`, `npx tsc -b`, and `pytest tests/ -v` still pass before merging the next.
