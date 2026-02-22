# Live Architecture Monitoring: Implementation Plan

A living document for implementing live architecture monitoring in solution-explorer. Designed for parallel execution by independent agent work streams. Default configuration: OSS project on GitHub with Cloudflare Pages as viewer frontend.

---

## Table of Contents

1. [Dependency Graph](#dependency-graph)
2. [Stream A: Remove Vanilla Python Constraint](#stream-a-remove-vanilla-python-constraint)
3. [Stream B: Types + Store Foundation](#stream-b-types--store-foundation)
4. [Stream C: Admin Dashboard UI](#stream-c-admin-dashboard-ui)
5. [Stream D: Status Dashboard + Component Status UI](#stream-d-status-dashboard--component-status-ui)
6. [Stream E: Live Monitor Hooks](#stream-e-live-monitor-hooks)
7. [Stream F: GitHub Actions Workflow + CI Collection](#stream-f-github-actions-workflow--ci-collection)
8. [Stream G: Incremental Analyzer](#stream-g-incremental-analyzer)
9. [Default Configuration Summary](#default-configuration-summary-github--cf-pages)
10. [Stream H: Cloudflare-Enhanced Mode](#stream-h-cloudflare-enhanced-mode)
11. [Stream I: Pydantic Models + Validation](#stream-i-pydantic-models--validation)
12. [Stream J: Tree-Sitter Parsing](#stream-j-tree-sitter-parsing)
13. [Stream K: True Incremental Re-Analysis](#stream-k-true-incremental-re-analysis)
14. [Integration Testing](#integration-testing)
15. [File Manifest](#file-manifest)

---

## Dependency Graph

```
Tier 0 (start immediately, no deps):
  Stream A: Remove Vanilla Python Constraint
  Stream B: Types + Store Foundation

Tier 1 (requires A and/or B complete):
  Stream C: Admin Dashboard UI              (requires B)
  Stream D: Status Dashboard + Component UI (requires B)
  Stream E: Live Monitor Hooks              (requires B)
  Stream F: GitHub Actions Workflow + CI    (requires A)
  Stream G: Incremental Analyzer            (requires A)
  Stream I: Pydantic Models + Validation    (requires A)

Tier 2 (requires Tier 1 streams):
  Stream H: Cloudflare-Enhanced Mode        (requires F, G, E complete)
  Stream J: Tree-Sitter Parsing             (requires I complete)
  Stream K: True Incremental Re-Analysis    (requires G, J complete)

Tier 3 (all streams complete):
  Integration Testing (full system)
```

Maximum parallelism: 6 agents at Tier 1 (C, D, E, F, G, I running simultaneously).

Streams within the same tier have zero dependencies on each other. Streams C, D, and E all touch [App.tsx](viewer/src/App.tsx) but in different, non-overlapping sections:
- **Stream C**: admin button in header (~line 301-310) + modal render
- **Stream D**: `<StatusDashboard />` between banners (~line 371) and main content (~line 374)
- **Stream E**: `useLiveMonitor()` hook call at function top + small "Live" indicator in header

The only shared edit point is the import/destructuring block at the top of App.tsx. Since Stream B already adds all store fields, the UI streams just consume them. Each agent adds its own import line and destructured variable. Merge conflicts are trivial and can be resolved naturally as they arise.

---

## Stream A: Remove Vanilla Python Constraint

**Purpose**: Unblock the incremental analyzer's use of external libraries (gitpython, etc.)
**Scope**: Documentation updates + pyproject.toml creation
**Dependencies**: None

### Task A.1: Update Documentation

- [ ] Audit all 10 locations listed in the research doc (Section 4) for "zero dependencies / stdlib only" language
- [ ] Replace with pragmatic dependency policy: "Core analyzer requires only Python stdlib. Optional dependencies for advanced features (incremental analysis, live monitoring) are listed in pyproject.toml."
- [ ] Files to check:
  - [README.md](README.md)
  - [CONTRIBUTING.md](CONTRIBUTING.md)
  - [analyze.py](analyze.py) (docstring, lines 2-12)
  - [analyzer/__init__.py](analyzer/__init__.py) (docstring, lines 1-4)
  - [PROJECT-OVERVIEW.md](PROJECT-OVERVIEW.md)

### Task A.2: Create pyproject.toml

- [ ] Create [pyproject.toml](pyproject.toml) at project root

```toml
[project]
name = "solution-explorer"
version = "1.0.0"
description = "Architecture visualization tool for any codebase"
requires-python = ">=3.10"

[project.optional-dependencies]
models = [
    "pydantic>=2.5",
]
incremental = [
    "gitpython>=3.1",
]
treesitter = [
    "tree-sitter>=0.23",
    "tree-sitter-python>=0.23",
    "tree-sitter-javascript>=0.23",
    "tree-sitter-typescript>=0.23",
    "tree-sitter-swift>=0.6",
    "tree-sitter-rust>=0.23",
    "tree-sitter-go>=0.23",
    "tree-sitter-ruby>=0.23",
]
live = [
    "gitpython>=3.1",
    "httpx>=0.27",
    "pydantic>=2.5",
]
all = [
    "solution-explorer[live,treesitter]",
]
dev = [
    "pytest",
    "ruff",
]
```

Dependency groups are additive. `pip install -e ".[all]"` gets everything. Core analyzer always works with zero deps.

### Verification A

- [ ] `python3 -c "from analyzer.scanner import ArchitectureScanner"` works without optional deps
- [ ] `pip install -e ".[incremental]"` installs gitpython
- [ ] `pytest tests/ -v` passes (existing tests unaffected)

---

## Stream B: Types + Store Foundation

**Purpose**: Define all new TypeScript types and Zustand store extensions. Every UI stream depends on this.
**Scope**: [types.ts](viewer/src/types.ts), [store.ts](viewer/src/store.ts), [store.test.ts](viewer/src/__tests__/store.test.ts)
**Dependencies**: None

### Task B.1: New Types

- [ ] Add live monitoring types to [viewer/src/types.ts](viewer/src/types.ts) after the `ArchitectureAIEnhance` interface (line 84)

Types to add:
- `ComponentStatus` - per-component CI/security status entry
- `ArchitectureStatus` - architecture-level status entry
- `StatusOverlay` - the full status-overlay.json shape
- `ComponentLiveStatus` - optional status bag on Component
- `LiveVersion` - version.json shape
- `LiveConfig` - live-config.json shape (controls polling, features, backend mode)
- `AdminSummaryRepo`, `AdminSummaryActivity`, `AdminSummary` - admin-summary.json shape

- [ ] Add optional `live_status?: ComponentLiveStatus` to `Component` interface (after line 102, alongside `ai_enhance`)
- [ ] Add optional live status fields to `Architecture` interface (after line 144, alongside `ai_enhance`):
  ```typescript
  live_status?: {
    statuses?: Record<string, ArchitectureStatus>;
    monitored_branch?: string;
    last_commit_sha?: string;
    last_updated?: string;
  };
  ```

**Backward compatibility**: All new fields are optional. Existing JSON works unchanged.

### Task B.2: Store Extensions

- [ ] Add imports for new types in [viewer/src/store.ts](viewer/src/store.ts) (line 2-14)
- [ ] Add new state fields to `ArchStore` interface (after line 112):
  - `adminOpen: boolean`
  - `liveConfig: LiveConfig | null`
  - `liveVersion: LiveVersion | null`
  - `liveMonitorStatus: "idle" | "polling" | "updating" | "error" | "paused"`
  - `statusOverlay: StatusOverlay | null`
- [ ] Add new actions to `ArchStore` interface:
  - `setAdminOpen: (open: boolean) => void`
  - `setLiveConfig: (config: LiveConfig | null) => void`
  - `setLiveVersion: (version: LiveVersion | null) => void`
  - `setLiveMonitorStatus: (status: ...) => void`
  - `applyStatusOverlay: (overlay: StatusOverlay) => void`
  - `navigateToComponent: (componentId: string) => void`
- [ ] Add initial state values in `create<ArchStore>` (after line 166): all `null`/`false`/`"idle"`
- [ ] Implement `applyStatusOverlay`: merges component statuses from overlay into architecture components' `live_status` field, sets architecture-level `live_status.statuses`. Uses recursive component tree traversal to match by ID.
- [ ] Implement `navigateToComponent`: uses existing `findComponent` and `buildBreadcrumbs` helpers (lines 114-140) to drill to the target component's parent and select it. Handles both top-level and nested components.

### Task B.3: Store Unit Tests

- [ ] Add test suite to [viewer/src/__tests__/store.test.ts](viewer/src/__tests__/store.test.ts)
- [ ] Use existing `makeComponent`/`makeArchitecture` test helpers
- [ ] Tests:
  - `applyStatusOverlay` merges component statuses correctly
  - `applyStatusOverlay` sets architecture-level statuses
  - `navigateToComponent` selects and drills to nested component
  - `navigateToComponent` handles top-level component (no drill needed)
  - `adminOpen` state toggles correctly
  - `liveMonitorStatus` transitions

### Verification B

- [ ] `cd viewer && npm test` passes with new tests
- [ ] `cd viewer && npx tsc -b` compiles without errors
- [ ] No existing tests broken

---

## Stream C: Admin Dashboard UI

**Purpose**: Full-screen admin modal with 5 tabs (Health, Activity, History, Settings, Resources)
**Scope**: New components + App.tsx header integration
**Dependencies**: Stream B (types and store)

### Task C.1: AdminDashboard Shell

- [ ] Create [viewer/src/components/AdminDashboard.tsx](viewer/src/components/AdminDashboard.tsx)

Follow [SearchOverlay.tsx](viewer/src/components/SearchOverlay.tsx) pattern:
- Fixed `inset-0 z-50` with backdrop blur
- Wider content panel than search (`max-w-4xl` vs `max-w-lg`)
- ESC to close, Cmd+Shift+A to toggle (register via useEffect keyboard listener)
- Store-controlled via `adminOpen` / `setAdminOpen`
- Tab state: `"health" | "activity" | "history" | "settings" | "resources"`
- Tab bar uses same style as [DetailPanel.tsx](viewer/src/components/DetailPanel.tsx) tabs (line 229-255)
- Resources tab conditional: only shows when `backend_mode !== "github"` (same spread pattern as DetailPanel line 116-123)

### Task C.2: useAdminData Hook

- [ ] Create [viewer/src/hooks/useAdminData.ts](viewer/src/hooks/useAdminData.ts)
- Fetches `{liveConfig.data_url}/admin-summary.json` when admin dashboard opens
- Returns `{ data: AdminSummary | null, loading: boolean, error: string | null }`
- Only fetches when `liveConfig?.enabled` is true

### Task C.3: Tab Components

- [ ] Create [viewer/src/components/admin/HealthTab.tsx](viewer/src/components/admin/HealthTab.tsx)
  - Repo status table: name, last update (use `formatRelativeTime` from [layout.ts](viewer/src/utils/layout.ts) line 262-276), version, component count, status badge
  - Connection info: polling interval, data source URL, backend mode badge, error count
  - For GitHub mode: shows GitHub Pages URL, polling interval, Pages cache note

- [ ] Create [viewer/src/components/admin/ActivityTab.tsx](viewer/src/components/admin/ActivityTab.tsx)
  - Reverse-chronological list from `adminData.activity`
  - Each row: relative time, commit SHA (first 7 chars, linked to GitHub), commit message, diff summary badges (green added, amber modified, red removed)

- [ ] Create [viewer/src/components/admin/HistoryTab.tsx](viewer/src/components/admin/HistoryTab.tsx)
  - CSS bar chart using proportional width pattern (like language bars in DetailPanel)
  - Shows `daily_counts` for last 30 days
  - Stats: total updates, oldest snapshot date, retention count

- [ ] Create [viewer/src/components/admin/SettingsTab.tsx](viewer/src/components/admin/SettingsTab.tsx)
  - Displays current `liveConfig` as read-only fields
  - Mutable settings: polling intervals, feature flags (as toggle-style inputs)
  - Feature flags show backend mode requirements: `(requires: cloudflare)` in gray text

- [ ] Create [viewer/src/components/admin/ResourcesTab.tsx](viewer/src/components/admin/ResourcesTab.tsx)
  - Only rendered in cloudflare/hybrid mode (handled by conditional tab in AdminDashboard)
  - Usage bars with limit percentages
  - In GitHub mode: tab hidden entirely (not a GitHub-mode concern per design)

### Task C.4: App.tsx Integration

- [ ] Add import for `AdminDashboard` in [App.tsx](viewer/src/App.tsx)
- [ ] Add `adminOpen`, `setAdminOpen`, `liveConfig` to destructured store values
- [ ] Add admin button in header, between dark mode toggle (line 301-307) and stats div (line 310)
  - Only renders when `liveConfig` is present
  - Shows red pulsing status dot when any architecture-level status is "error"
  - Title: "Admin Dashboard (Cmd+Shift+A)"
- [ ] Add `{adminOpen && <AdminDashboard />}` alongside SearchOverlay render

### Verification C

- [ ] Admin button appears only when `liveConfig` is set
- [ ] Cmd+Shift+A opens/closes the dashboard
- [ ] ESC closes the dashboard
- [ ] All 5 tabs render (testable with mock data via browser console `useArchStore.setState()`)
- [ ] Resources tab hidden in GitHub mode
- [ ] `cd viewer && npm test && npx tsc -b`

---

## Stream D: Status Dashboard + Component Status UI

**Purpose**: Show CI/security/deploy status on the architecture graph and in component details
**Scope**: New StatusDashboard component, modifications to ComponentNode.tsx and DetailPanel.tsx
**Dependencies**: Stream B (types and store)

### Task D.1: StatusDashboard Component

- [ ] Create [viewer/src/components/StatusDashboard.tsx](viewer/src/components/StatusDashboard.tsx)

Design:
- Renders between header banners and main content in App.tsx
- Only appears when `architecture?.live_status?.statuses` has active non-ok entries
- Groups statuses by category prefix (e.g., `ci:`, `security:`, `deploy:`)
- Each group shows: category icon, count of issues, affected component names as clickable buttons
- Clicking a component calls `navigateToComponent(id)` from store
- Color scheme: error = red, warning = amber, info = blue (matches existing criticality dot colors in ComponentNode)
- Follows existing banner styling pattern (like AI summary banner, App.tsx lines 345-360)

### Task D.2: ComponentNode.tsx Status Badges

- [ ] Add status badge rendering in [ComponentNode.tsx](viewer/src/components/ComponentNode.tsx)
- Location: metrics bar area (around line 864-932), alongside existing criticality dots
- Logic:
  - Read `component.live_status?.statuses`
  - Compute worst level: error > warning > info > ok
  - If worst level is "ok" or absent, render nothing
  - Otherwise render a colored dot: `error` = red pulsing, `warning` = amber, `info` = blue
  - Wrap in Tooltip showing status summary
- [ ] Add helper functions `getWorstStatusLevel()` and `getStatusSummary()` (top of file or in a small util)

### Task D.3: DetailPanel.tsx Status Tab

- [ ] Modify [DetailPanel.tsx](viewer/src/components/DetailPanel.tsx)
- [ ] Add `"status"` to the `Tab` type union (line 18)
- [ ] Add conditional tab entry using the existing spread pattern (line 116-123):
  ```typescript
  ...(component.live_status?.statuses
    ? [{ key: "status" as Tab, label: "Status",
         count: Object.keys(component.live_status.statuses).length }]
    : []),
  ```
- [ ] Add `StatusTab` inline component that renders each status entry as a card:
  - Color-coded background: red/amber/blue based on level
  - Shows: status dot, title, detail text, optional URL link
  - Follows same styling patterns as existing tab content

### Task D.4: App.tsx StatusDashboard Integration

- [ ] Add import for `StatusDashboard` in [App.tsx](viewer/src/App.tsx)
- [ ] Insert `<StatusDashboard />` between the review mode banner (ends line 371) and the main content div (line 374)

### Verification D

- [ ] StatusDashboard only appears when `live_status` has non-ok statuses
- [ ] StatusDashboard hidden when no live data present (backward compat)
- [ ] Clicking affected component navigates correctly (drills if nested)
- [ ] Status dots appear on ComponentNode alongside criticality dots
- [ ] Status tab appears in DetailPanel only when `live_status` exists
- [ ] `cd viewer && npm test && npx tsc -b`

---

## Stream E: Live Monitor Hooks

**Purpose**: Polling, caching, circuit breaker, and visibility-based update management
**Scope**: New useLiveMonitor hook, App.tsx integration
**Dependencies**: Stream B (types and store)

### Task E.1: useLiveMonitor Hook

- [ ] Create [viewer/src/hooks/useLiveMonitor.ts](viewer/src/hooks/useLiveMonitor.ts)

**Initialization:**
- On mount, fetch `./live-config.json`
- Validate response is JSON (same content-type guard as App.tsx line 122-124)
- If found and `enabled: true`, set `liveConfig` in store
- If not found, do nothing (static mode, backward compat)

**Adaptive polling:**
- Poll `{data_url}/version.json` with `If-None-Match` ETag header
- 304 = no change, reset failure counter
- 200 = new version, fetch `manifest.json` + `status-overlay.json` in parallel
- Merge manifest into architecture via `setArchitecture()` + reinitialize search
- Merge status overlay via `applyStatusOverlay()`
- Error = increment failure counter

**Interval calculation:**
- Updated within 2 min: `min_interval_seconds` (default 15s)
- Updated within 10 min: `default_interval_seconds` (default 30s)
- Idle: `idle_interval_seconds` (default 120s)

**Circuit breaker:**
- 5 consecutive failures = pause for 60s
- After pause: retry once
- Success = resume normal adaptive polling
- Failure = enter slow-retry backoff (retry every 5 minutes while in error state, set `liveMonitorStatus: "error"`)
- Reset to normal adaptive polling on first success

**Visibility control:**
- `document.visibilitychange` listener
- Tab hidden: pause polling, set status "paused"
- Tab visible after 5+ min hidden: immediate poll, then resume adaptive
- Tab visible after <5 min: just resume timer

**localStorage cache:**
- Key: `arch-live-cache-{project_id}`
- On successful manifest fetch: cache in localStorage (try/catch for quota)
- On initial load: if live config detected, show cached data while first fetch runs
- Cache is a fallback for instant first-load, not a primary data source

### Task E.2: App.tsx Integration

- [ ] Add import for `useLiveMonitor` in [App.tsx](viewer/src/App.tsx)
- [ ] Call `useLiveMonitor()` in App function body (after other hook calls)
- [ ] Add connection status indicator in header (near stats area, line 310):
  - Small dot + "Live" text
  - Color: green (polling/idle), red (error), gray (paused)
  - Pulsing animation when actively polling/updating
  - Only renders when `liveConfig` is present

### Task E.3: Tests

- [ ] Create [viewer/src/__tests__/useLiveMonitor.test.ts](viewer/src/__tests__/useLiveMonitor.test.ts)
- [ ] Test interval calculation logic (extract as pure function for testability)
- [ ] Test circuit breaker state transitions
- [ ] Test with mock fetch (vitest vi.fn() + vi.useFakeTimers)
- [ ] Test visibility-based pause/resume

### Verification E

- [ ] Without `live-config.json`: viewer loads identically to current static mode
- [ ] With `live-config.json`: polling starts, connection indicator shows in header
- [ ] Circuit breaker activates after 5 failures, self-heals via slow-retry backoff
- [ ] Tab visibility pause/resume works
- [ ] localStorage caching works for instant reload
- [ ] `cd viewer && npm test && npx tsc -b`

---

## Stream F: GitHub Actions Workflow + CI Collection

**Purpose**: The automation that triggers on push, runs analysis, collects CI status, and deploys data to GitHub Pages
**Scope**: New workflow file, new CI collection script, action.yml updates
**Dependencies**: Stream A (pyproject.toml for pip install)

### Task F.1: Live Monitor Workflow

- [ ] Create [.github/workflows/live-monitor.yml](.github/workflows/live-monitor.yml)

Follow patterns from existing [architecture-viz.yml](.github/workflows/architecture-viz.yml).

**Triggers:**
- `push` to `main` (configurable via settings)
- `workflow_run` on monitored workflows (e.g., "Architecture Visualization") with `types: [completed]`
- `workflow_dispatch` for manual runs

**Concurrency:** `group: live-monitor-${{ github.ref }}`, `cancel-in-progress: true`

**Permissions:** `contents: read`, `pages: write`, `actions: read`

**Job: `update-architecture`** (runs on push/dispatch):
1. Checkout with `fetch-depth: 0` (full history for incremental)
2. Setup Python 3.12
3. `pip install -e ".[live]"`
4. Restore baseline from Actions cache: key `arch-baseline-${{ github.ref }}`
5. Run incremental analysis: `python analyze.py --incremental --base-sha "${{ github.event.before }}" --head-sha "${{ github.sha }}" --baseline .arch-baseline/architecture.json -o .arch-output/ --compact`
6. Collect CI status: `python scripts/collect-ci-status.py --repo "${{ github.repository }}" --sha "${{ github.sha }}" -o .arch-output/live/status-overlay.json`
7. Generate `version.json` (Python one-liner: version=timestamp, updated_at, commit_sha)
8. Generate `live-config.json` with GitHub-mode defaults:
   - `backend_mode: "github"`
   - `data_url: "https://{owner}.github.io/{repo}/live"`
   - Default polling intervals (30s default, 15s min, 120s idle)
   - Features: activity_log, admin_dashboard, version_history, ci_status_overlay all true
9. Generate `admin-summary.json` (Python script or inline)
10. Save baseline to Actions cache: key `arch-baseline-${{ github.ref }}-${{ github.sha }}`
11. Deploy all files in `.arch-output/live/` to GitHub Pages via `actions/upload-pages-artifact` + `actions/deploy-pages` with `destination_dir: live`

**Job: `update-ci-status`** (runs on workflow_run):
1. Checkout (fetch-depth: 1)
2. Setup Python 3.12
3. Collect CI status for the workflow run's head SHA
4. Deploy only `status-overlay.json` to GitHub Pages with `keep_files: true`

### Task F.2: CI Status Collection Script

- [ ] Create [scripts/collect-ci-status.py](scripts/collect-ci-status.py)

**Uses only stdlib** (`urllib.request`, `json`, `argparse`) to stay lightweight for CI.

**CLI:** `python scripts/collect-ci-status.py --repo owner/repo --sha abc123 -o status-overlay.json`

**What it collects via GitHub API:**
- Workflow runs for the commit SHA (`/repos/{repo}/actions/runs?head_sha={sha}`)
- Check suites for the commit (`/repos/{repo}/commits/{sha}/check-suites`)

**Mapping:**
- `conclusion: "success"` -> `level: "ok"`
- `conclusion: "failure"` -> `level: "error"`
- `conclusion: "cancelled"` -> `level: "warning"`
- `conclusion: null` (in progress) -> `level: "info"`

**Output:** `status-overlay.json` matching the `StatusOverlay` type

### Task F.3: Admin Summary Generator

- [ ] Create [scripts/generate-admin-summary.py](scripts/generate-admin-summary.py) or inline in workflow
- Reads the current architecture.json and version.json
- Produces `admin-summary.json` matching the `AdminSummary` type
- Includes repo health, diff summary from architecture `_diff_summary` field, daily counts

### Task F.4: action.yml Updates (Optional)

- [ ] Add `live-monitor` input to [action.yml](action.yml):
  ```yaml
  live-monitor:
    description: 'Enable live monitoring data generation'
    required: false
    default: 'false'
  ```
- [ ] When `live-monitor: 'true'`, generate `live-config.json` and `version.json` alongside the viewer build

### Verification F

- [ ] Workflow YAML validates (use `actionlint` or GitHub's workflow editor)
- [ ] `python scripts/collect-ci-status.py --repo sirfifer/solution-explorer --sha HEAD -o /tmp/status.json` runs with valid GITHUB_TOKEN
- [ ] Generated JSON files match their TypeScript type definitions
- [ ] `actions/upload-pages-artifact` + `actions/deploy-pages` correctly deploys to `live/` subdirectory

---

## Stream G: Incremental Analyzer

**Purpose**: Git-diff-based selective re-analysis to avoid full rescans on every push
**Scope**: New `analyzer/incremental.py`, CLI flag additions, tests
**Dependencies**: Stream A (pyproject.toml for gitpython)

### Task G.1: IncrementalAnalyzer Class

- [ ] Create [analyzer/incremental.py](analyzer/incremental.py)

**Class: `IncrementalAnalyzer`**

Constructor params: `root: Path, base_sha: str, head_sha: str, baseline_path: Optional[Path], max_file_size, max_symbols, preview_lines`

**Methods:**

`load_baseline()` -> `Optional[dict]`
- Loads previous `architecture.json` from `baseline_path`
- Returns parsed dict or None

`get_changed_files()` -> `list[tuple[str, str]]`
- Runs `git diff --name-status {base_sha}..{head_sha}` via subprocess
- Returns list of `(status, path)` tuples (A/M/D/R)
- Handles empty base_sha (first run) by returning empty list

`map_files_to_components(changed_files, baseline)` -> `set[str]`
- Builds file-to-component index from baseline's component tree
- Maps each changed file path to its component ID
- Returns set of affected component IDs

`should_full_rescan(changed_files)` -> `bool`
- True if: no base_sha, no baseline, >50% files changed, marker file changed (package.json, Cargo.toml, go.mod, pyproject.toml, etc.), force push (unreachable base SHA)

`compute_diff_summary(old_baseline, new_arch)` -> `dict`
- Compares old and new component sets
- Returns: `components_added`, `components_removed`, `components_modified`, `relationships_changed`, `files_changed`

`run()` -> `dict`
- Load baseline, get changed files
- If `should_full_rescan()`: run full `ArchitectureScanner.scan()` (delegates to existing [analyzer/scanner.py](analyzer/scanner.py))
- Otherwise: still run full scan for now (true selective re-analysis is a future optimization), but attach diff metadata
- Add `_diff_summary` and `_changed_files` to output dict
- Return architecture dict

**Note:** The initial implementation runs a full scan regardless but computes diff metadata. True incremental re-analysis (only scanning affected components) is a later optimization. The value now is the diff metadata and the cache/baseline infrastructure.

### Task G.2: CLI Integration

- [ ] Modify [analyzer/cli.py](analyzer/cli.py) to add new arguments (after line 66):
  - `--incremental` (action="store_true")
  - `--base-sha` (default="")
  - `--head-sha` (default="HEAD")
  - `--baseline` (default=None)

- [ ] Add incremental execution branch (after `args = parser.parse_args()`, around line 68):
  - When `--incremental` is set, import and use `IncrementalAnalyzer`
  - Output to directory (not single file): creates `architecture.json` in output dir
  - Also saves baseline to `.arch-baseline/architecture.json` for next run

### Task G.3: Tests

- [ ] Create [tests/test_incremental.py](tests/test_incremental.py)

Tests using the existing test patterns from [tests/test_cli.py](tests/test_cli.py):
- `should_full_rescan` returns True when no baseline
- `should_full_rescan` returns True when marker file (package.json) changed
- `should_full_rescan` returns False for normal code changes under threshold
- `map_files_to_components` correctly maps paths to component IDs
- `compute_diff_summary` calculates correct counts for add/remove/modify
- `get_changed_files` parses git diff output (mock subprocess)
- Full `run()` integration test with temp git repo and two commits

### Verification G

- [ ] `python analyze.py --incremental --base-sha HEAD~1 --head-sha HEAD -o /tmp/arch-test/ .` runs successfully
- [ ] Falls back to full rescan when no baseline exists (prints message)
- [ ] `pytest tests/test_incremental.py -v` passes
- [ ] `pytest tests/ -v` passes (existing tests unaffected)

---

## Default Configuration Summary (GitHub + CF Pages)

All defaults are tuned for: **public OSS repo on GitHub, viewer on Cloudflare Pages, zero cost**.

| Setting | Default | Why |
|---------|---------|-----|
| `backend.mode` | `"github"` | Zero cost for public repos, unlimited Actions |
| Viewer hosting | Cloudflare Pages | 330+ edge locations, unlimited BW, existing infra |
| Data hosting | GitHub Pages | Free, CDN-served, CORS enabled for public repos |
| `polling.default_interval_seconds` | 30 | Balances freshness vs. GitHub Pages 10-min cache |
| `polling.min_interval_seconds` | 15 | After recent update, poll more aggressively |
| `polling.idle_interval_seconds` | 120 | Save bandwidth when nothing changes |
| `polling.adaptive` | true | Auto-adjust based on update recency |
| `polling.pause_when_hidden` | true | No wasted polls when tab not visible |
| `features.realtime_ci_webhooks` | false | Requires Cloudflare Worker (not GitHub mode) |
| `features.realtime_push` | false | Requires Cloudflare paid tier |
| CI status collection | In Actions (batch) | Collected during workflow run via GitHub API |
| Update latency | 10-20 min | Bounded by Actions runtime + Pages 10-min cache |

---

## Stream H: Cloudflare-Enhanced Mode

**Purpose**: Add Cloudflare Worker + R2 + D1 infrastructure for real-time CI status updates and faster data hosting
**Scope**: New `infrastructure/cloudflare/` directory, workflow updates, viewer backend-mode support
**Dependencies**: Streams F (workflow), G (incremental analyzer), E (live monitor hooks)

### Architecture Overview

GitHub Actions remains the compute layer (unlimited for public repos, 10ms CF Worker CPU limit makes CF unsuitable for analysis). Cloudflare provides:
- **R2**: Data hosting with instant availability (no 10-min GitHub Pages cache)
- **D1**: Metadata storage (activity log, health tracking, resource usage)
- **Worker**: Webhook reception for real-time CI status, ingest endpoint for Actions uploads, admin API
- **KV** (optional): Settings cache, ephemeral overlay caching

### Task H.1: Worker Implementation

- [ ] Create [infrastructure/cloudflare/worker/src/index.ts](infrastructure/cloudflare/worker/src/index.ts)

**Endpoints:**

`POST /ingest` (called by GitHub Actions after R2 upload):
- Validates `Authorization: Bearer {ADMIN_TOKEN}` header
- Reads metadata JSON from request body (project_id, version, commit_sha, diff_summary)
- Writes version record to D1 `versions` table
- Writes activity record to D1 `patches` table
- Updates health record in D1 `health` table
- Regenerates `admin-summary.json` from D1 data, writes to R2
- Updates `version.json` in R2 (triggers viewer poll detection)
- Returns 204 on success

`POST /webhook` (receives GitHub webhooks directly):
- Validates `X-Hub-Signature-256` header using HMAC-SHA256 with `WEBHOOK_SECRET`
- Parses `workflow_run` event payload
- Maps `conclusion` to status level: success->ok, failure->error, cancelled->warning, null->info
- Reads current `status-overlay.json` from R2, merges new status, writes back
- Updates `version.json` to bump version (triggers viewer poll)
- Returns 200

`GET /health`:
- Returns JSON with worker version, D1 connection status, R2 bucket status
- No auth required (monitoring endpoint)

`GET /settings/:project_id`:
- Reads from KV (or D1 settings table as fallback)
- Returns LiveConfig for the project
- No auth required (public data)

`POST /settings/:project_id`:
- Requires `Authorization: Bearer {ADMIN_TOKEN}`
- Updates mutable settings (polling intervals, feature flags)
- Writes to KV and D1

**Worker constraints (10ms CPU free tier):**
- No heavy computation in any endpoint
- R2 reads/writes are I/O (don't count against CPU)
- D1 queries are I/O (don't count against CPU)
- JSON parse/stringify must be minimal (small payloads only)
- Keep webhook handler under 5ms CPU: parse event, one R2 read, one R2 write, one D1 write

### Task H.2: D1 Schema

- [ ] Create [infrastructure/cloudflare/worker/schema.sql](infrastructure/cloudflare/worker/schema.sql)

```sql
CREATE TABLE IF NOT EXISTS versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  commit_sha TEXT NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  UNIQUE(project_id, version)
);

CREATE TABLE IF NOT EXISTS patches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  commit_sha TEXT NOT NULL,
  commit_message TEXT,
  components_added INTEGER DEFAULT 0,
  components_removed INTEGER DEFAULT 0,
  components_modified INTEGER DEFAULT 0,
  relationships_changed INTEGER DEFAULT 0,
  files_changed INTEGER DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_patches_project ON patches(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS health (
  project_id TEXT PRIMARY KEY,
  last_update TEXT,
  version INTEGER,
  component_count INTEGER,
  relationship_count INTEGER,
  status TEXT CHECK(status IN ('ok', 'stale', 'error')) DEFAULT 'ok',
  error_message TEXT,
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS resource_usage (
  project_id TEXT NOT NULL,
  date TEXT NOT NULL,
  worker_requests INTEGER DEFAULT 0,
  d1_writes INTEGER DEFAULT 0,
  r2_reads INTEGER DEFAULT 0,
  r2_writes INTEGER DEFAULT 0,
  PRIMARY KEY (project_id, date)
);
```

### Task H.3: R2 Bucket Structure and Public Access

- [ ] Document R2 bucket layout:

```
solution-explorer-live/
  live/{project_id}/
    version.json              (~200 bytes, polled every 15-120s)
    manifest.json             (~500KB typical, fetched on version change)
    status-overlay.json       (~5KB, fetched on version change)
    admin-summary.json        (~50KB, fetched when admin opens)
    detail/                   (split mode per-component files)
      detail-{component-id}.json
```

- [ ] Configure R2 public access via Cloudflare dashboard or `r2.dev` subdomain
- [ ] Ensure CORS headers on R2 public bucket: `Access-Control-Allow-Origin: *`

### Task H.4: Resource Tracking and Self-Throttling

- [ ] Implement resource counter middleware in Worker

On every request, the Worker:
1. Reads today's usage from D1 `resource_usage` table
2. Checks against configured limits (defaults: 80% of CF free tier)
3. If any limit exceeded: returns 429 with `Retry-After` header
4. Otherwise: increments counter and proceeds

**Default limits (80% of free tier):**
- `max_daily_worker_requests`: 80,000 (free: 100,000)
- `max_daily_d1_writes`: 80,000 (free: 100,000)
- `max_monthly_r2_reads`: 8,000,000 (free: 10,000,000)
- `max_monthly_r2_writes`: 800,000 (free: 1,000,000)

**Optimization:** Cache today's usage count in a Worker global variable (resets on cold start, at most slightly stale). Only query D1 on first request or every 100th request.

### Task H.5: wrangler.toml

- [ ] Create [infrastructure/cloudflare/worker/wrangler.toml](infrastructure/cloudflare/worker/wrangler.toml)

```toml
name = "solution-explorer-api"
main = "src/index.ts"
compatibility_date = "2026-02-01"

[[d1_databases]]
binding = "DB"
database_name = "solution-explorer-d1"
database_id = ""  # Filled after `wrangler d1 create`

[[r2_buckets]]
binding = "LIVE_BUCKET"
bucket_name = "solution-explorer-live"

[[kv_namespaces]]
binding = "KV_CONFIG"
id = ""  # Filled after `wrangler kv:namespace create`

[vars]
WORKER_VERSION = "1.0.0"

# Secrets (set via `wrangler secret put`):
# WEBHOOK_SECRET - GitHub webhook HMAC secret
# ADMIN_TOKEN - Bearer token for /ingest and /settings POST
```

### Task H.6: GitHub Actions Workflow Updates for CF Mode

- [ ] Update [.github/workflows/live-monitor.yml](.github/workflows/live-monitor.yml) to add conditional R2 upload

After the analysis step, when `backend.mode != "github"`:
1. Install AWS CLI (for S3-compatible R2 API)
2. `aws s3 sync .arch-output/live/ s3://{R2_BUCKET}/live/{project_id}/ --endpoint-url https://{CF_ACCOUNT_ID}.r2.cloudflarestorage.com`
3. `curl -X POST {WORKER_URL}/ingest -H "Authorization: Bearer {WORKER_TOKEN}" -d @.arch-output/metadata.json`

**Required secrets for CF mode:**
- `CF_R2_ACCESS_KEY` and `CF_R2_SECRET_KEY` (R2 API tokens)
- `CF_ACCOUNT_ID`
- `WORKER_URL` and `WORKER_TOKEN`

### Task H.7: Webhook Signature Validation

- [ ] Implement in Worker `src/webhook.ts`

```typescript
async function verifyGitHubWebhook(request: Request, secret: string): Promise<boolean> {
  const signature = request.headers.get("x-hub-signature-256");
  if (!signature) return false;

  const body = await request.clone().text();
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(body));
  const expected = "sha256=" + Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, "0")).join("");

  return signature === expected;
}
```

Uses Web Crypto API (available in Workers, not Node's `crypto` module).

### Task H.8: Setup and Deployment Scripts

- [ ] Create [infrastructure/cloudflare/setup.sh](infrastructure/cloudflare/setup.sh)
  - `wrangler d1 create solution-explorer-d1`
  - `wrangler d1 execute solution-explorer-d1 --file=worker/schema.sql`
  - `wrangler r2 bucket create solution-explorer-live`
  - `wrangler kv:namespace create solution-explorer-kv`
  - `wrangler secret put WEBHOOK_SECRET`
  - `wrangler secret put ADMIN_TOKEN`
  - `wrangler deploy`

- [ ] Create [infrastructure/cloudflare/README.md](infrastructure/cloudflare/README.md) with setup instructions

### Task H.9: Viewer Updates for CF Mode

- [ ] Update [useLiveMonitor.ts](viewer/src/hooks/useLiveMonitor.ts) to handle `worker_url` in LiveConfig
  - When `backend_mode === "cloudflare"`, data URL points to R2 public URL (not GitHub Pages)
  - Status overlay may update more frequently (webhook-driven, 2-10s vs 10-20min)
  - Polling interval can be shorter (no 10-min cache constraint)

- [ ] Update admin Resources tab to show CF resource usage from `admin-summary.json`

### Verification H

- [ ] `cd infrastructure/cloudflare/worker && wrangler dev` starts local worker
- [ ] `curl -X POST localhost:8787/ingest -H "Authorization: Bearer test" -d '{"project_id":"test","version":1}'` returns 204
- [ ] `curl -X POST localhost:8787/webhook` with valid signature processes event
- [ ] `curl localhost:8787/health` returns status JSON
- [ ] R2 upload from Actions workflow succeeds
- [ ] Viewer polls R2 `version.json` and receives updates within 15-90s of push
- [ ] CI webhook -> Worker -> R2 -> viewer poll cycle completes within 2-10s
- [ ] Resource tracking increments correctly in D1
- [ ] Self-throttling returns 429 when limits approached

---

## Stream I: Pydantic Models + Validation

**Purpose**: Replace dataclass models with Pydantic for runtime validation, enum constraints, and cross-reference integrity
**Scope**: [analyzer/models.py](analyzer/models.py), scanner integration, test updates
**Dependencies**: Stream A (pyproject.toml for pydantic dependency)

### Design Rationale

The current dataclass models have no runtime validation. Component types, symbol kinds, visibility levels, and relationship types are unconstrained strings. Cross-references between components, files, and symbols are not validated. Pydantic solves this while maintaining `model_dump()` / `asdict()` compatibility for JSON serialization.

### Task I.1: Update pyproject.toml

- [ ] Add pydantic to optional dependencies in [pyproject.toml](pyproject.toml):

```toml
[project.optional-dependencies]
models = [
    "pydantic>=2.5",
]
live = [
    "gitpython>=3.1",
    "httpx>=0.27",
    "pydantic>=2.5",
]
```

### Task I.2: Pydantic Model Definitions

- [ ] Rewrite [analyzer/models.py](analyzer/models.py) with Pydantic BaseModel

**Strategy:** Keep backward compatibility by supporting both Pydantic (when installed) and plain dataclasses (fallback). Use a try/except import pattern:

```python
try:
    from pydantic import BaseModel, Field, field_validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    # Fall back to dataclass definitions (current code)
```

**Pydantic models to define:**

`SymbolKind` (str enum): `class`, `struct`, `enum`, `function`, `protocol`, `trait`, `interface`, `type`, `property`, `method`, `constant`, `extension`

`Visibility` (str enum): `public`, `internal`, `private`, `fileprivate`, `protected`, `package`

`ComponentType` (str enum): All valid types from [constants.py](analyzer/constants.py) and the type promotion logic in [scanner.py](analyzer/scanner.py) `_classify_architectural_role()`: `application`, `service`, `library`, `package`, `module`, `infrastructure`, `project`, `repository`, `mobile-client`, `ios-client`, `android-client`, `web-client`, `api-server`, `watch-app`, `desktop-app`, `cli-tool`, `screen`, `tab-container`, `tab`, `feature-group`, `content`

`RelationshipType` (str enum): `import`, `http`, `websocket`, `grpc`, `ffi`, `database`, `file`, `docker`, `navigation`, `tab`, `modal`, `embed`

`Symbol` (BaseModel):
- Validators: `line < end_line`, `kind in SymbolKind`, `visibility in Visibility`
- `id` auto-generated from `f"{file}:{name}:{line}"` if not provided

`FileInfo` (BaseModel):
- Validators: `path` not empty, `language` in LANGUAGE_MAP keys (or allow unknown), `lines >= 0`

`ComponentDoc` (BaseModel):
- All fields optional (matching current behavior)
- `api_endpoints` validated: each has `method` and `path`

`Component` (BaseModel):
- Validators: `type in ComponentType`, `port` in 1-65535 or None, `id` not empty
- `children` is recursive `list[Component]`
- `metrics` uses typed `ComponentMetrics` model (not bare dict)

`Relationship` (BaseModel):
- Validators: `type in RelationshipType`, `source` and `target` not empty
- `port` in 1-65535 or None

`Architecture` (BaseModel):
- Cross-reference validator (root_validator): all relationship sources/targets exist in component IDs
- `generated_at` validated as ISO format string
- `stats` uses typed `ArchitectureStats` model

### Task I.3: Scanner Integration

- [ ] Update [analyzer/scanner.py](analyzer/scanner.py) to use Pydantic models when available

Key integration points:
- Line ~337: Symbol construction in `_scan_files()`, replace `Symbol(...)` dataclass with Pydantic model
- Line ~370: FileInfo construction, replace with Pydantic model
- Line ~162: Component construction in `_discover_components()`, replace with Pydantic model
- Line ~1376: Relationship construction in `_detect_relationships()`, replace with Pydantic model
- Serialization: Replace `asdict(arch)` with `arch.model_dump()` (Pydantic) or keep `asdict()` for dataclass fallback

**Graceful degradation:** When pydantic is not installed, scanner uses original dataclass models. When installed, uses Pydantic models with validation. The `PYDANTIC_AVAILABLE` flag controls which path executes.

### Task I.4: Multi-Repo Orchestrator Updates

- [ ] Update [analyzer/multi_repo.py](analyzer/multi_repo.py) to handle Pydantic models
- Lines 144-147: ID prefixing logic needs to work with both dict and Pydantic model
- Lines 222: `asdict(comp)` needs Pydantic-aware path (`comp.model_dump()`)

### Task I.5: CLI Validation Mode

- [ ] Add `--validate` flag to [analyzer/cli.py](analyzer/cli.py)
  - When set, runs Pydantic validation on the output and reports any issues
  - Useful for CI: `python analyze.py . --validate` exits non-zero on validation errors
  - Reports: missing cross-references, invalid enum values, constraint violations

### Task I.6: Tests

- [ ] Create [tests/test_models.py](tests/test_models.py)

Tests:
- Valid Symbol construction succeeds
- Invalid Symbol kind raises ValidationError
- Invalid visibility raises ValidationError
- line > end_line raises ValidationError
- Valid Component with all fields passes
- Invalid ComponentType raises ValidationError
- Port out of range raises ValidationError
- Relationship with nonexistent source (when validated against Architecture) fails
- `model_dump()` produces same structure as `asdict()` for dataclass models
- Backward compat: when pydantic not installed, dataclass models work unchanged

- [ ] Update existing tests to work with either model backend

### Verification I

- [ ] `pip install -e ".[models]"` installs pydantic
- [ ] `python analyze.py . -o /tmp/test.json` works with pydantic installed (validates during scan)
- [ ] `python analyze.py . -o /tmp/test.json --validate` reports validation summary
- [ ] Core analyzer still works without pydantic: `pip uninstall pydantic && python analyze.py .`
- [ ] `pytest tests/test_models.py -v` passes
- [ ] `pytest tests/ -v` all existing tests pass
- [ ] JSON output structure unchanged (viewer compatibility)

---

## Stream J: Tree-Sitter Parsing

**Purpose**: Replace regex-based parsers with tree-sitter AST parsing for accuracy and incremental capability
**Scope**: New TreeSitterParser base, language-specific tree-sitter parsers, parser registry update
**Dependencies**: Stream I (Pydantic models for validated Symbol output)

### Design Rationale

Current parsers use regex + brace-counting, which produces ~70-80% accuracy. Known issues:
- **Swift**: misses property wrappers (@State, @Binding), multi-line generics, protocol extensions
- **TypeScript**: template literals confuse brace counting, destructured exports missed
- **Rust**: generic constraints and lifetime parameters misunderstood
- **All languages**: strings/comments not properly excluded from regex matches

Tree-sitter provides proper AST parsing with incremental re-parse capability, supporting 30+ languages.

### Task J.1: Update pyproject.toml

- [ ] Add tree-sitter dependencies:

```toml
[project.optional-dependencies]
treesitter = [
    "tree-sitter>=0.23",
    "tree-sitter-python>=0.23",
    "tree-sitter-javascript>=0.23",
    "tree-sitter-typescript>=0.23",
    "tree-sitter-swift>=0.6",
    "tree-sitter-rust>=0.23",
    "tree-sitter-go>=0.23",
    "tree-sitter-ruby>=0.23",
]
```

### Task J.2: TreeSitterParser Base Class

- [ ] Create [analyzer/parsers/tree_sitter_base.py](analyzer/parsers/tree_sitter_base.py)

```python
"""Base class for tree-sitter-based parsers."""

from typing import Optional
from .base import BaseParser

try:
    import tree_sitter
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


class TreeSitterParser(BaseParser):
    """Parser using tree-sitter for AST-based symbol extraction.

    Subclasses provide language-specific query files and
    node-to-symbol mapping logic. Falls back to regex parser
    if tree-sitter is not installed.
    """

    LANGUAGE = None  # Subclasses set this
    _parser = None
    _language = None

    def __init__(self, fallback_parser: BaseParser):
        self._fallback = fallback_parser
        if TREE_SITTER_AVAILABLE and self.LANGUAGE:
            self._parser = tree_sitter.Parser()
            self._language = self._load_language()
            if self._language:
                self._parser.language = self._language

    def _load_language(self):
        """Load the tree-sitter language. Subclasses override."""
        raise NotImplementedError

    def extract_symbols(self, content: str, file_path: str):
        if not TREE_SITTER_AVAILABLE or not self._parser:
            return self._fallback.extract_symbols(content, file_path)

        tree = self._parser.parse(content.encode("utf-8"))
        return self._extract_from_tree(tree, content, file_path)

    def _extract_from_tree(self, tree, content, file_path):
        """Walk AST and extract symbols. Subclasses implement."""
        raise NotImplementedError

    def extract_imports(self, content: str):
        if not TREE_SITTER_AVAILABLE or not self._parser:
            return self._fallback.extract_imports(content)

        tree = self._parser.parse(content.encode("utf-8"))
        return self._extract_imports_from_tree(tree, content)

    def _extract_imports_from_tree(self, tree, content):
        """Extract imports from AST. Subclasses implement."""
        # Default: delegate to fallback regex parser
        return self._fallback.extract_imports(content)

    # Framework detection, port detection, env vars, API endpoints
    # remain regex-based (no AST benefit, patterns work well enough)
    def detect_framework(self, content):
        return self._fallback.detect_framework(content)

    def detect_ports(self, content):
        return self._fallback.detect_ports(content)

    def detect_api_endpoints(self, content):
        return self._fallback.detect_api_endpoints(content)
```

**Key design decision:** Hybrid approach. Tree-sitter handles symbol extraction and import detection (where AST accuracy matters most). Framework detection, port detection, and API endpoint detection stay regex-based (pattern matching works well for these, and AST provides no significant advantage).

### Task J.3: Swift Tree-Sitter Parser (Highest Priority)

- [ ] Create [analyzer/parsers/swift_ts.py](analyzer/parsers/swift_ts.py)

Swift benefits most from tree-sitter because:
- Property wrappers (@State, @Binding, @ObservedObject) are invisible to regex
- Protocol extensions and conditional conformances are missed
- Multi-line generics with where clauses break brace counting
- SwiftUI view body detection needs accurate scope tracking

**AST node types to extract:**
- `class_declaration` -> Symbol(kind="class")
- `struct_declaration` -> Symbol(kind="struct")
- `enum_declaration` -> Symbol(kind="enum")
- `protocol_declaration` -> Symbol(kind="protocol")
- `function_declaration` -> Symbol(kind="function")
- `property_declaration` with `@State`/`@Binding`/etc. -> Symbol(kind="property", annotations=[...])
- `extension_declaration` -> Symbol(kind="extension")
- `typealias_declaration` -> Symbol(kind="type")

**Visibility extraction:** Parse `access_control_modifier` child nodes: `public`, `private`, `fileprivate`, `internal`, `open`, `package`

**Import extraction:** Parse `import_declaration` nodes, extract module name from `identifier` child

### Task J.4: TypeScript Tree-Sitter Parser (High Priority)

- [ ] Create [analyzer/parsers/typescript_ts.py](analyzer/parsers/typescript_ts.py)

TypeScript benefits from tree-sitter for:
- Accurate generic type parameter handling
- Destructured export detection
- Template literal strings no longer confuse scope
- Decorator parsing (experimental syntax)

**AST node types:** `class_declaration`, `interface_declaration`, `type_alias_declaration`, `function_declaration`, `arrow_function` (when assigned to exported const), `enum_declaration`

### Task J.5: Rust Tree-Sitter Parser (High Priority)

- [ ] Create [analyzer/parsers/rust_ts.py](analyzer/parsers/rust_ts.py)

Rust benefits from tree-sitter for:
- Trait bounds and where clauses parsed correctly
- Lifetime parameters distinguished from generics
- Macro invocations identified
- `pub(crate)`, `pub(in path)` visibility parsed from AST

### Task J.6: Remaining Language Parsers

- [ ] Create [analyzer/parsers/python_ts.py](analyzer/parsers/python_ts.py) (medium priority)
  - Better nested class handling, decorator extraction, type hint parsing
- [ ] Create [analyzer/parsers/go_ts.py](analyzer/parsers/go_ts.py) (medium priority)
  - Accurate interface vs struct, receiver methods
- [ ] Create [analyzer/parsers/ruby_ts.py](analyzer/parsers/ruby_ts.py) (low priority, regex works adequately)

### Task J.7: Parser Registry Update

- [ ] Update [analyzer/parsers/__init__.py](analyzer/parsers/__init__.py)

```python
from .swift import SwiftParser
from .python_lang import PythonParser
# ... existing imports

try:
    from .swift_ts import SwiftTreeSitterParser
    from .typescript_ts import TypeScriptTreeSitterParser
    from .rust_ts import RustTreeSitterParser
    # Tree-sitter parsers wrap regex parsers as fallback
    PARSERS = {
        "swift": SwiftTreeSitterParser(fallback=SwiftParser()),
        "typescript": TypeScriptTreeSitterParser(fallback=TypeScriptParser()),
        "javascript": TypeScriptTreeSitterParser(fallback=TypeScriptParser()),
        "rust": RustTreeSitterParser(fallback=RustParser()),
        "python": PythonParser(),   # Keep regex until python_ts ready
        "go": GoParser(),           # Keep regex until go_ts ready
        "ruby": RubyParser(),       # Keep regex until ruby_ts ready
    }
except ImportError:
    # tree-sitter not installed, use regex parsers
    PARSERS = {
        "swift": SwiftParser(),
        "typescript": TypeScriptParser(),
        "javascript": TypeScriptParser(),
        "rust": RustParser(),
        "python": PythonParser(),
        "go": GoParser(),
        "ruby": RubyParser(),
    }
```

### Task J.8: Tests

- [ ] Create [tests/test_tree_sitter.py](tests/test_tree_sitter.py)

**Comparison tests:** For each language, run the same source file through both regex and tree-sitter parsers, verify tree-sitter finds all symbols regex finds plus additional ones:
- Swift: test property wrapper extraction, protocol extension detection
- TypeScript: test generic types, destructured exports
- Rust: test trait bounds, lifetime parameters, pub(crate) visibility

**Regression tests:** Existing test fixtures must produce at least the same symbols with tree-sitter
**Performance tests:** Benchmark tree-sitter vs regex on a large file (>1000 lines)

### Verification J

- [ ] `pip install -e ".[treesitter]"` installs tree-sitter and language bindings
- [ ] `python analyze.py .` works with tree-sitter installed (uses tree-sitter parsers)
- [ ] `python analyze.py .` works without tree-sitter (falls back to regex parsers)
- [ ] Tree-sitter produces superset of regex parser symbols for all test fixtures
- [ ] `pytest tests/test_tree_sitter.py -v` passes
- [ ] `pytest tests/ -v` all existing tests pass
- [ ] JSON output structure unchanged (viewer compatibility)

---

## Stream K: True Incremental Re-Analysis

**Purpose**: Enable the IncrementalAnalyzer to re-scan only affected components instead of running a full scan
**Scope**: Major extension to [analyzer/incremental.py](analyzer/incremental.py), scanner modifications
**Dependencies**: Stream G (initial IncrementalAnalyzer), Stream J (tree-sitter for per-file incremental parsing)

### Design Rationale

Stream G's IncrementalAnalyzer runs a full scan and computes diff metadata. This stream makes it truly incremental: given a git diff, it identifies affected components, re-scans only those components' files, and patches the baseline architecture with the new results. For a typical commit touching 5-10 files in a 100-component project, this reduces scan time from minutes to seconds.

### Task K.1: Component Dependency Graph

- [ ] Add to [analyzer/incremental.py](analyzer/incremental.py):

`build_component_dependency_graph(baseline)` -> `dict[str, set[str]]`
- Analyzes import relationships from baseline to build a dependency graph
- Maps each component ID to the set of component IDs that import from it
- Used to determine the "blast radius" of a change: if component A changes, all components that import from A also need re-analysis

### Task K.2: Selective File Re-Scanning

- [ ] Add to [analyzer/incremental.py](analyzer/incremental.py):

`rescan_component(component_id, baseline, root)` -> `dict`
- Creates a mini ArchitectureScanner scoped to just one component's directory
- Re-parses only the files belonging to that component
- Returns updated component dict with new symbols, file info, metrics
- Uses tree-sitter's incremental parse when available (parse tree cached from previous scan)

`merge_component_into_baseline(baseline, component_id, new_component_data)` -> `dict`
- Replaces the component's data in the baseline architecture
- Updates symbols: removes old symbols for this component's files, adds new ones
- Updates file info: removes old file entries, adds new ones
- Recalculates component metrics
- Does NOT re-detect relationships (separate step)

### Task K.3: Incremental Relationship Detection

- [ ] Add to [analyzer/incremental.py](analyzer/incremental.py):

`redetect_relationships(baseline, affected_component_ids)` -> `list[dict]`
- For each affected component, re-runs import-based relationship detection
- Removes old relationships where source OR target is an affected component
- Adds newly detected relationships
- Preserves relationships between unaffected components unchanged

This is necessary because changing imports in one file can create or remove cross-component relationships.

### Task K.4: Incremental Pipeline

- [ ] Rewrite `IncrementalAnalyzer.run()` to implement true incremental flow:

```
1. Load baseline
2. Get changed files from git diff
3. If should_full_rescan(): delegate to full ArchitectureScanner (unchanged)
4. Map changed files to affected component IDs
5. Expand affected set via dependency graph (importers of changed components)
6. For each affected component: rescan_component()
7. Merge each rescanned component into baseline
8. Redetect relationships for affected components
9. Recalculate architecture-level stats
10. Compute diff summary (compare old baseline to new result)
11. Return updated architecture dict
```

### Task K.5: Baseline Caching Strategy

- [ ] Implement efficient baseline storage

The baseline needs to include not just the architecture JSON but also:
- Per-file parse tree hashes (for tree-sitter incremental re-parse)
- Per-component file lists (for quick affected-component lookup)
- Import graph snapshot (for dependency graph construction)

Store as a directory:
```
.arch-baseline/
  architecture.json        # Full architecture snapshot
  file-index.json          # { "path/to/file.ts": { "component_id": "...", "content_hash": "..." } }
  import-graph.json        # { "component-a": ["component-b", "component-c"] }
```

### Task K.6: Scanner Modifications for Scoped Re-Analysis

- [ ] Add scoped scanning mode to [analyzer/scanner.py](analyzer/scanner.py)

New constructor parameter: `scope_paths: Optional[list[str]]`
- When set, `_scan_files()` only processes files within the given paths
- `_discover_components()` uses baseline component tree (doesn't re-discover)
- `_detect_relationships()` only processes relationships involving scoped components

This allows the scanner to be used as a "focused lens" on a subset of the codebase.

### Task K.7: Tests

- [ ] Extend [tests/test_incremental.py](tests/test_incremental.py)

Tests:
- `build_component_dependency_graph` produces correct graph from baseline
- `rescan_component` re-analyzes only specified component's files
- `merge_component_into_baseline` correctly patches baseline
- `redetect_relationships` preserves unaffected relationships
- Full pipeline: create temp git repo, make initial commit (full scan), modify one file (incremental scan), verify only that component rescanned
- Edge case: deleted file removes component correctly
- Edge case: new file creates new component correctly
- Edge case: moved file updates component assignment
- Performance: incremental scan of 1 file in 100-component baseline completes in <5s

### Verification K

- [ ] `python analyze.py --incremental --base-sha HEAD~1 --head-sha HEAD -o /tmp/test/ .` uses true incremental path
- [ ] Only affected components are rescanned (visible in verbose output)
- [ ] Result matches full scan result for the same HEAD (correctness check)
- [ ] Incremental scan completes in <10% of full scan time for small changes
- [ ] `pytest tests/test_incremental.py -v` passes
- [ ] `pytest tests/ -v` all tests pass

---

## Integration Testing

Organized by milestone. Each milestone can be validated independently once its required streams are complete.

### Milestone 1: Core Live Monitoring (Streams A-G)

**Test 1.1: Static Mode Backward Compatibility**
- [ ] Remove any `live-config.json` from `viewer/public/`
- [ ] Start `cd viewer && npm run dev`
- [ ] Verify: viewer loads static architecture.json exactly as before
- [ ] Verify: no admin button, no status dashboard, no live indicators, no console errors

**Test 1.2: Live Mode Simulation (Local)**
- [ ] Create mock data files in `viewer/public/`:
  - `live-config.json` with `backend_mode: "github"`, `data_url: "."`, `enabled: true`
  - `version.json` with current timestamp
  - `status-overlay.json` with some error/warning statuses
  - `admin-summary.json` with sample repo health and activity
- [ ] Start `cd viewer && npm run dev`
- [ ] Verify: "Live" indicator in header (green dot)
- [ ] Verify: StatusDashboard shows between banners and graph
- [ ] Verify: Component nodes show status dots
- [ ] Verify: DetailPanel shows Status tab for components with statuses
- [ ] Verify: Cmd+Shift+A opens admin dashboard
- [ ] Verify: All 5 admin tabs render with mock data
- [ ] Verify: Resources tab hidden (GitHub mode)

**Test 1.3: GitHub Actions End-to-End**
- [ ] Push to a test repo with `live-monitor.yml` workflow
- [ ] Verify: Actions run completes successfully
- [ ] Verify: Files deployed to GitHub Pages `live/` directory
- [ ] Verify: Viewer (on CF Pages) picks up `live-config.json`
- [ ] Verify: Viewer polls `version.json` and fetches data within 10-20 min

**Test 1.4: Type Safety + Test Suite**
- [ ] `cd viewer && npx tsc -b` compiles without errors
- [ ] All optional chaining correct (no runtime errors when `live_status` absent)
- [ ] `pytest tests/ -v` all Python tests pass
- [ ] `cd viewer && npm test` all viewer tests pass
- [ ] `ruff check analyze.py analyzer/ scripts/ tests/` no lint errors
- [ ] `cd viewer && npx eslint src/` no lint errors

### Milestone 2: Cloudflare-Enhanced Mode (Stream H)

**Test 2.1: Worker Local Dev**
- [ ] `cd infrastructure/cloudflare/worker && wrangler dev` starts successfully
- [ ] `/health` endpoint returns status JSON
- [ ] `/ingest` with valid auth creates version and patch records in D1
- [ ] `/webhook` with valid GitHub signature processes workflow_run event
- [ ] `/webhook` with invalid signature returns 401

**Test 2.2: R2 Integration**
- [ ] GitHub Actions workflow uploads to R2 via S3 API
- [ ] Files accessible at R2 public URL with correct CORS headers
- [ ] Viewer polls R2 `version.json` and receives updates

**Test 2.3: Real-Time CI Status**
- [ ] Configure GitHub webhook pointing to Worker URL
- [ ] Trigger CI failure in test repo
- [ ] Verify: webhook -> Worker -> R2 status-overlay.json update within 2-10s
- [ ] Verify: viewer picks up status change on next poll

**Test 2.4: Resource Tracking**
- [ ] After 100 requests, D1 `resource_usage` table shows correct counts
- [ ] When limits approached (set low for testing), Worker returns 429
- [ ] Admin dashboard Resources tab shows accurate usage bars

### Milestone 3: Pydantic Validation (Stream I)

**Test 3.1: Validated Analysis**
- [ ] `pip install -e ".[models]" && python analyze.py .` works with validation
- [ ] `python analyze.py . --validate` produces validation report
- [ ] Invalid data (manually corrupted JSON) is caught and reported

**Test 3.2: Graceful Degradation**
- [ ] `pip uninstall pydantic && python analyze.py .` falls back to dataclass models
- [ ] JSON output identical with and without pydantic installed

### Milestone 4: Tree-Sitter Parsing (Stream J)

**Test 4.1: Parser Accuracy**
- [ ] Swift parser: test file with @State, @Binding, protocol extensions, generics
- [ ] TypeScript parser: test file with generics, destructured exports, template literals
- [ ] Rust parser: test file with trait bounds, lifetimes, pub(crate)
- [ ] Tree-sitter finds all symbols that regex finds, plus additional accurate ones

**Test 4.2: Fallback**
- [ ] `pip uninstall tree-sitter && python analyze.py .` uses regex parsers
- [ ] JSON output structure unchanged (viewer compatible)

### Milestone 5: True Incremental Analysis (Stream K)

**Test 5.1: Selective Re-Scan**
- [ ] Create test git repo with 10+ components
- [ ] Modify one file, run `--incremental`
- [ ] Verify: only the affected component (and its importers) are rescanned
- [ ] Verbose output confirms skipped components

**Test 5.2: Correctness**
- [ ] Run full scan on HEAD, save result A
- [ ] Run incremental scan (HEAD~1 -> HEAD), save result B
- [ ] Diff A and B: architecturally identical (may differ in generation timestamp)

**Test 5.3: Performance**
- [ ] Incremental scan of 1-file change completes in <10% of full scan time
- [ ] Baseline loading + diff computation takes <1s

---

## File Manifest

### New Files (30)

| File | Stream | Purpose |
|------|--------|---------|
| [pyproject.toml](pyproject.toml) | A, I, J | Python project config with optional deps |
| **Viewer: Hooks** | | |
| [viewer/src/hooks/useLiveMonitor.ts](viewer/src/hooks/useLiveMonitor.ts) | E | Polling, caching, circuit breaker |
| [viewer/src/hooks/useAdminData.ts](viewer/src/hooks/useAdminData.ts) | C | Admin summary fetching |
| [viewer/src/__tests__/useLiveMonitor.test.ts](viewer/src/__tests__/useLiveMonitor.test.ts) | E | Live monitor hook tests |
| **Viewer: Admin Dashboard** | | |
| [viewer/src/components/AdminDashboard.tsx](viewer/src/components/AdminDashboard.tsx) | C | Admin modal shell + tabs |
| [viewer/src/components/admin/HealthTab.tsx](viewer/src/components/admin/HealthTab.tsx) | C | System health view |
| [viewer/src/components/admin/ActivityTab.tsx](viewer/src/components/admin/ActivityTab.tsx) | C | Update activity log |
| [viewer/src/components/admin/HistoryTab.tsx](viewer/src/components/admin/HistoryTab.tsx) | C | Historical trends chart |
| [viewer/src/components/admin/SettingsTab.tsx](viewer/src/components/admin/SettingsTab.tsx) | C | Configuration display |
| [viewer/src/components/admin/ResourcesTab.tsx](viewer/src/components/admin/ResourcesTab.tsx) | C | CF resource usage (CF mode only) |
| **Viewer: Status UI** | | |
| [viewer/src/components/StatusDashboard.tsx](viewer/src/components/StatusDashboard.tsx) | D | Top-level status bar |
| **GitHub Actions + Scripts** | | |
| [.github/workflows/live-monitor.yml](.github/workflows/live-monitor.yml) | F | GitHub Actions live monitor workflow |
| [scripts/collect-ci-status.py](scripts/collect-ci-status.py) | F | CI status collection via GitHub API |
| [scripts/generate-admin-summary.py](scripts/generate-admin-summary.py) | F | Admin summary generation |
| **Analyzer: Incremental** | | |
| [analyzer/incremental.py](analyzer/incremental.py) | G, K | Incremental analysis engine |
| [tests/test_incremental.py](tests/test_incremental.py) | G, K | Incremental analyzer tests |
| **Cloudflare Infrastructure** | | |
| [infrastructure/cloudflare/worker/src/index.ts](infrastructure/cloudflare/worker/src/index.ts) | H | Worker: routes, ingest, webhook, health, settings |
| [infrastructure/cloudflare/worker/src/webhook.ts](infrastructure/cloudflare/worker/src/webhook.ts) | H | GitHub webhook signature validation |
| [infrastructure/cloudflare/worker/schema.sql](infrastructure/cloudflare/worker/schema.sql) | H | D1 database schema |
| [infrastructure/cloudflare/worker/wrangler.toml](infrastructure/cloudflare/worker/wrangler.toml) | H | Wrangler config with all bindings |
| [infrastructure/cloudflare/worker/package.json](infrastructure/cloudflare/worker/package.json) | H | Worker dependencies (wrangler, typescript) |
| [infrastructure/cloudflare/worker/tsconfig.json](infrastructure/cloudflare/worker/tsconfig.json) | H | Worker TypeScript config |
| [infrastructure/cloudflare/setup.sh](infrastructure/cloudflare/setup.sh) | H | One-command CF resource provisioning |
| [infrastructure/cloudflare/README.md](infrastructure/cloudflare/README.md) | H | CF setup and deployment guide |
| **Pydantic Models** | | |
| [tests/test_models.py](tests/test_models.py) | I | Model validation tests |
| **Tree-Sitter Parsers** | | |
| [analyzer/parsers/tree_sitter_base.py](analyzer/parsers/tree_sitter_base.py) | J | Tree-sitter base class with fallback |
| [analyzer/parsers/swift_ts.py](analyzer/parsers/swift_ts.py) | J | Swift tree-sitter parser |
| [analyzer/parsers/typescript_ts.py](analyzer/parsers/typescript_ts.py) | J | TypeScript tree-sitter parser |
| [analyzer/parsers/rust_ts.py](analyzer/parsers/rust_ts.py) | J | Rust tree-sitter parser |
| [tests/test_tree_sitter.py](tests/test_tree_sitter.py) | J | Tree-sitter comparison tests |

### Modified Files (14)

| File | Stream(s) | Changes |
|------|-----------|---------|
| [viewer/src/types.ts](viewer/src/types.ts) | B | ~100 lines: all new type definitions |
| [viewer/src/store.ts](viewer/src/store.ts) | B | ~80 lines: live state + actions |
| [viewer/src/__tests__/store.test.ts](viewer/src/__tests__/store.test.ts) | B | ~50 lines: status overlay + navigation tests |
| [viewer/src/App.tsx](viewer/src/App.tsx) | C, D, E | Admin button, StatusDashboard, useLiveMonitor, live indicator |
| [viewer/src/components/ComponentNode.tsx](viewer/src/components/ComponentNode.tsx) | D | ~20 lines: status badge rendering |
| [viewer/src/components/DetailPanel.tsx](viewer/src/components/DetailPanel.tsx) | D | ~50 lines: Status tab + StatusTab component |
| [analyzer/cli.py](analyzer/cli.py) | G, I | Incremental CLI flags + --validate flag |
| [analyzer/models.py](analyzer/models.py) | I | Pydantic BaseModel migration with dataclass fallback |
| [analyzer/scanner.py](analyzer/scanner.py) | I, K | Pydantic model usage + scoped re-analysis support |
| [analyzer/multi_repo.py](analyzer/multi_repo.py) | I | Pydantic-aware model handling |
| [analyzer/parsers/__init__.py](analyzer/parsers/__init__.py) | J | Registry update: tree-sitter with regex fallback |
| [README.md](README.md) | A | Dependency policy update |
| [CONTRIBUTING.md](CONTRIBUTING.md) | A | Dependency policy update |
| [PROJECT-OVERVIEW.md](PROJECT-OVERVIEW.md) | A | Dependency policy update |

### Key Existing Files (Reference)

| File | Why It Matters |
|------|---------------|
| [viewer/src/components/SearchOverlay.tsx](viewer/src/components/SearchOverlay.tsx) | Template for AdminDashboard modal pattern |
| [viewer/src/components/DetailPanel.tsx](viewer/src/components/DetailPanel.tsx) | Template for conditional tabs (lines 116-123) |
| [viewer/src/utils/layout.ts](viewer/src/utils/layout.ts) | `formatRelativeTime`, color utilities, ROLE_META |
| [analyzer/scanner.py](analyzer/scanner.py) | Core scan pipeline: IncrementalAnalyzer wraps, tree-sitter plugs in, pydantic validates |
| [analyzer/parsers/base.py](analyzer/parsers/base.py) | BaseParser interface that TreeSitterParser extends |
| [analyzer/parsers/swift.py](analyzer/parsers/swift.py) | Regex fallback for SwiftTreeSitterParser |
| [analyzer/parsers/typescript.py](analyzer/parsers/typescript.py) | Regex fallback for TypeScriptTreeSitterParser |
| [analyzer/parsers/rust.py](analyzer/parsers/rust.py) | Regex fallback for RustTreeSitterParser |
| [analyzer/constants.py](analyzer/constants.py) | LANGUAGE_MAP, valid component types, skip directories |
| [.github/workflows/architecture-viz.yml](.github/workflows/architecture-viz.yml) | Template for live-monitor workflow patterns |
| [action.yml](action.yml) | Composite action that may gain `live-monitor` input |

---

## Deferred (Out of Scope)

These items are intentionally not planned:

- **Real-time push via WebSocket/SSE**: Requires Cloudflare paid tier (Durable Objects for persistent connections). The polling-based approach in Stream E handles the free tier constraint.
- **Component-to-workflow mapping**: Advanced feature for mapping specific CI workflows to specific architecture components. The current approach maps at the architecture level. Per-component mapping requires user-defined configuration in `solution-explorer.json` and is a future enhancement after the core monitoring system is validated.
