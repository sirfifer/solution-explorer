# Live Architecture Monitoring System: Research & Implementation Plan

## Part 1: Research Paper

### 1. Problem Statement

Solution-explorer currently operates as a **batch pipeline**: scan a codebase, produce a static JSON model, build a viewer, deploy. Every commit triggers a full rescan, full rebuild, and full redeploy. For an active project this is:

- **Wasteful**: 95%+ of the architecture is unchanged between commits
- **Slow**: Full pipeline takes 2-5 minutes (checkout, analyze, npm install, build, deploy)
- **Blind to runtime state**: CI failures, security findings, deployment status are invisible in the diagram
- **Missing context**: A developer looking at the architecture has no idea which components are healthy, broken, or at risk

The vision is a **live architecture dashboard** where the model updates incrementally on every commit, CI/CD and security status are reflected on components, and critical issues are surfaced at the top level rather than buried in drill-downs.

### 2. Research Findings

#### 2.1 Incremental Static Analysis

**SonarQube** distinguishes "old code" vs "new code," analyzing only changed portions per commit. **GitHub's internal analysis** (ACM Queue) uses tree-sitter for incremental parsing. **Key pattern**: `git diff` output drives selective re-analysis.

#### 2.2 Architecture-as-Data Standards

**Structurizr / C4 Model**: JSON schema for architecture storage. Solution-explorer already follows this pattern. **JSON Patch (RFC 6902)** and **JSON Merge Patch (RFC 7396)** are standards for incremental JSON changes.

#### 2.3 Production System Patterns

- **Datadog**: Guaranteed delivery over low latency
- **ArgoCD**: Polls Git directly for reliability; detects drift
- **Grafana Live**: Client self-heals from connection interruptions
- **PagerDuty**: Separates ingestion from processing

### 3. Platform Cost Analysis

#### 3.1 GitHub Free Tier (Public Repos)

| Service | Free Limit (Public Repos) | Notes |
|---------|--------------------------|-------|
| **Actions minutes** | **Unlimited** | Standard runners only |
| **Actions concurrent jobs** | 20 | 5 macOS max |
| **Actions job timeout** | 6 hours | Per job |
| **Actions cache** | 10 GB per repo | 7-day expiry if unused |
| **Actions artifacts** | 500 MB | 90-day retention |
| **Pages bandwidth** | 100 GB/month (soft) | Fastly CDN, 60+ PoPs |
| **Pages site size** | 1 GB | Hard limit |
| **Pages cache** | **10 min fixed** | Cannot customize headers |
| **Pages builds** | 10/hour (auto) | Unlimited via Actions |
| **Pages CORS** | `Access-Control-Allow-Origin: *` | All public repos |
| **Releases** | Unlimited, 2 GB/file | No expiry, CDN-served |
| **API rate limit** | 5,000 req/hour | 1,000/hour via GITHUB_TOKEN |
| **Webhooks** | 20 per event type | Don't count against API rate |

**Key insight**: For public repos, GitHub Actions compute is unlimited and free. GitHub Pages can serve JSON files with global CDN. The tradeoff is a fixed 10-minute CDN cache.

#### 3.2 GitHub Private Repos

| Plan | Cost | Actions Minutes | Storage |
|------|------|----------------|---------|
| Free | $0 | 2,000 min/month | 500 MB |
| Team | $4/user/month | 3,000 min/month | 2 GB |
| Enterprise | $21/user/month | 50,000 min/month | 50 GB |

Private repos have real costs. We assume private = commercial = has budget.

#### 3.3 Cloudflare Free Tier

| Service | Free Limit | Critical? |
|---------|-----------|-----------|
| **Workers requests** | 100,000/day | Yes |
| **Workers CPU** | **10ms/invocation** | Very limiting |
| **KV reads** | 100,000/day | Fine |
| **KV writes** | **1,000/day** | Critical bottleneck |
| **D1 reads** | 5,000,000/day | Generous |
| **D1 writes** | 100,000/day | Generous |
| **D1 storage** | 500 MB/database | Metadata only |
| **R2 reads** | 10,000,000/month | Generous |
| **R2 writes** | 1,000,000/month | Generous |
| **R2 storage** | 10 GB | Fine |
| **R2 egress** | Unlimited | Free |
| **Pages** | 500 builds/month, unlimited BW | Fine |
| **Durable Objects** | 100,000 req/day | Shares Workers quota |
| **Cron triggers** | 5 per account, 10ms CPU | Very limited |

#### 3.4 Feature-to-Platform Cost Mapping

This table shows where each function can run, what it costs on each platform, and the quality tradeoff.

| Function | GitHub (free/public) | Cloudflare (free) | Best for OSS | Best for Commercial |
|----------|---------------------|-------------------|-------------|-------------------|
| **Analysis compute** | Unlimited Actions | 10ms CPU Workers | GitHub | GitHub |
| **Snapshot hosting** | Pages (10min cache) | R2 (instant) | GitHub | Cloudflare |
| **Viewer hosting** | Pages (free) | Pages (free) | Either | Cloudflare |
| **Version file** | Pages or Release | R2 or KV | GitHub | Cloudflare |
| **Activity log storage** | Actions artifacts/Releases | D1 | GitHub | Cloudflare |
| **CI status aggregation** | Computed in Actions | Worker webhook handler | GitHub | Cloudflare |
| **Status overlay hosting** | Pages (10min cache) | R2 (instant) | GitHub | Cloudflare |
| **Admin summary** | Pages JSON | R2 JSON | GitHub | Cloudflare |
| **Settings persistence** | Repo file (committed) | KV | GitHub | Cloudflare |
| **Update latency** | 10-20 min | 15-90 sec | Acceptable for OSS | Need Cloudflare |
| **Webhook → status** | Actions (30-120s) | Worker direct (2-10s) | GitHub | Cloudflare |

### 4. The "Vanilla Python" Constraint (to be removed)

10 instances of restrictive "zero dependencies / stdlib only" language in:
- `README.md` lines 29, 105, 123
- `CONTRIBUTING.md` lines 15, 59, 141
- `analyze.py` lines 5-6
- `analyzer/__init__.py` lines 3-4
- `PROJECT-OVERVIEW.md` lines 175, 293, 337

Replace with pragmatic dependency policy.

---

## Part 2: Architecture Design

### 5. Dual-Mode Architecture

The system operates in two modes, selected via settings. Both modes share the same viewer code, the same data model, and the same admin dashboard. They differ in where *data* is hosted and how updates propagate.

**Defaults** (optimized for the primary use case: OSS project, public GitHub repo, zero cost):
- **Backend mode**: `"github"` (data served from GitHub Pages, zero cost)
- **Viewer hosting**: Cloudflare Pages (current deployment model, free, 330+ edge locations, unlimited bandwidth)
- **First deployment target**: UnaMentis (open source, public repo)

The viewer app always deploys to Cloudflare Pages regardless of backend mode. This is because CF Pages has superior performance (330+ vs 60+ edge locations), unlimited bandwidth (vs GitHub Pages' 100GB/month soft limit), and is already the existing deployment infrastructure. Only the architecture *data files* (JSON) are hosted differently depending on mode.

#### 5.1 GitHub-Native Mode (Default, OSS / Zero Cost)

Everything runs on GitHub infrastructure for data. The viewer app is on Cloudflare Pages (free).

```
GitHub (everything here)
========================

Push to monitored branch
    |
    v
GitHub Actions workflow
    |
    +--> [1] Checkout repo (fetch-depth: 0)
    +--> [2] Restore previous snapshot from Actions cache
    +--> [3] Run incremental analyzer (diff against cached baseline)
    +--> [4] Compute diff summary metadata
    +--> [5] Collect CI/CD status via GitHub API (workflow runs, check suites)
    +--> [6] Generate: architecture.json, manifest.json, version.json,
    |         status-overlay.json, admin-summary.json
    +--> [7] Save new snapshot to Actions cache (for next run's baseline)
    +--> [8] Deploy all files to GitHub Pages (gh-pages branch or deploy-pages action)
    |
GitHub Pages (Fastly CDN)
    |
    +--> /{repo}/version.json          (ETag-based conditional GET)
    +--> /{repo}/manifest.json         (architecture data)
    +--> /{repo}/architecture.json     (full snapshot)
    +--> /{repo}/status-overlay.json   (CI/CD status)
    +--> /{repo}/admin-summary.json    (admin dashboard data)
    +--> /{repo}/detail/{component}.json (split mode)
    |
Viewer (always on Cloudflare Pages)
    |
    +--> Polls version.json every 30-120s (adaptive)
    +--> ETag conditional GET → 304 if unchanged (zero bandwidth)
    +--> On change: fetch manifest + status overlay
```

**Characteristics:**
- Cost: $0 for public repos
- Update latency: 10-20 min (Actions run + Pages cache)
- CI status: Batch-collected during analysis run (not real-time)
- Reliability: Very high (GitHub's SLA)
- Complexity: Very low (just a workflow + static files)

#### 5.2 Cloudflare-Enhanced Mode (Commercial / Low Latency)

Adds Cloudflare infrastructure for faster updates and real-time CI/CD status.

```
GitHub Actions (compute)              Cloudflare (hosting + webhooks)
========================              ==============================

Push to monitored branch              CI/CD webhooks (workflow_run, check_suite)
    |                                      |
    v                                      v
Actions workflow                       Worker (Ingestion)
    |                                      |
    +--> Incremental analysis              +--> Validate webhook signature
    +--> Upload to R2 (S3 API)             +--> Generate status-overlay.json
    +--> POST metadata to Worker           +--> Write to R2
    |                                      +--> Write metadata to D1
    |                                      +--> Update admin-summary.json in R2
    |
R2 (data hosting)                      Viewer (always on CF Pages)
    |                                      |
    +--> version.json                      +--> Polls R2 version.json (15-60s)
    +--> manifest.json                     +--> Fetches manifest on change
    +--> status-overlay.json               +--> Merges status overlay client-side
    +--> admin-summary.json
```

**Characteristics:**
- Cost: $0-5/month (free tier covers most usage)
- Architecture update latency: 15-90 sec (Actions is the bottleneck)
- CI status update latency: 2-10 sec (webhook direct to Worker)
- Real-time status: Yes (Worker processes webhooks immediately)
- Complexity: Moderate (Worker + R2 + D1)

### 6. Settings-Driven Configuration

The settings file controls which mode to use, resource limits, and feature flags. It lives in `solution-explorer.json` alongside existing config.

```json
{
  "live_monitor": {
    "enabled": true,
    "branch": "main",
    "project_id": "my-project",

    "backend": {
      "mode": "github",                    // DEFAULT: "github" (zero cost for public repos)
                                            // Options: "github" | "cloudflare" | "hybrid"
      "github": {
        "pages_url": "https://myorg.github.io/myrepo",
        "data_branch": "gh-pages",
        "data_path": "live"
      },
      "cloudflare": {                       // Only needed if mode is "cloudflare" or "hybrid"
        "worker_url": "https://solution-explorer-api.workers.dev",
        "r2_public_url": "https://pub-xxxxx.r2.dev",
        "r2_bucket": "solution-explorer-live",
        "kv_namespace": "solution-explorer-kv",
        "d1_database": "solution-explorer-d1"
      }
    },

    "polling": {
      "default_interval_seconds": 30,
      "min_interval_seconds": 15,
      "idle_interval_seconds": 120,
      "adaptive": true,
      "pause_when_hidden": true
    },

    "resource_limits": {
      "max_daily_worker_requests": 80000,
      "max_daily_kv_writes": 800,
      "max_daily_d1_writes": 80000,
      "max_monthly_r2_reads": 8000000,
      "max_monthly_r2_writes": 800000,
      "alert_at_percent": 80
    },

    "storage": {
      "snapshot_retention_count": 10,
      "snapshot_retention_days": 30,
      "split_mode": true
    },

    "features": {
      "activity_log": true,
      "admin_dashboard": true,
      "version_history": true,
      "ci_status_overlay": true,
      "diff_metadata": true,
      "realtime_ci_webhooks": false,
      "realtime_push": false
    },

    "ci_integration": {
      "collect_in_actions": true,
      "webhook_direct": false,
      "component_mapping": {
        "backend/api-server": {
          "workflows": ["Backend CI"],
          "security_scans": ["CodeQL"]
        }
      }
    }
  }
}
```

**Key setting: `backend.mode`**

| Setting | Backend | Data Host | Viewer Host | CI Status | Cost |
|---------|---------|-----------|-------------|-----------|------|
| `"github"` (default) | GitHub only | GitHub Pages | CF Pages | Batch (in Actions) | $0 |
| `"cloudflare"` | CF Workers + R2 | Cloudflare R2 | CF Pages | Real-time (webhook) | $0-5 |
| `"hybrid"` | Actions compute + CF hosting | CF R2 | CF Pages | Real-time | $0-5 |

Note: The viewer application always deploys to Cloudflare Pages in all modes.

**`resource_limits`**: Only relevant in `cloudflare` or `hybrid` mode. The system self-throttles to stay within configured limits. Defaults are 80% of Cloudflare free tier.

**`ci_integration`**: `collect_in_actions: true` means CI status is gathered during the analysis workflow run (by querying the GitHub API for recent workflow conclusions). `webhook_direct: true` means CI webhooks go directly to a Cloudflare Worker for real-time updates. These are independent: you can collect in Actions on every push AND have real-time webhook updates.

### 7. Data Model

All data model extensions are the same regardless of backend mode.

#### 7.1 New Types (viewer/src/types.ts)

```typescript
// Status types (from status-overlay.json)
interface ComponentStatus {
  key: string;              // "ci:Backend CI", "security:CodeQL"
  level: "ok" | "warning" | "error" | "info";
  title: string;
  detail?: string;
  url?: string;
  expires_at?: string;
}

interface ArchitectureStatus {
  key: string;
  level: "ok" | "warning" | "error" | "info";
  title: string;
  detail?: string;
  affected_components?: string[];
  url?: string;
  expires_at?: string;
}

interface StatusOverlay {
  updated_at: string;
  commit_sha: string;
  statuses: Record<string, ArchitectureStatus>;
  component_statuses: Record<string, Record<string, ComponentStatus>>;
}

// Live status on existing types (optional, backward-compatible)
interface ComponentLiveStatus {
  statuses?: Record<string, ComponentStatus>;
  last_updated?: string;
}

// Extensions to existing interfaces (all optional)
// Component: + live_status?: ComponentLiveStatus
// Architecture: + live_status?: { statuses, patches_applied, last_patch_at, monitored_branch, last_commit_sha }

// Version file
interface LiveVersion {
  version: number;
  updated_at: string;
  commit_sha: string;
  manifest_etag?: string;
}

// Admin summary (pre-computed, served as static JSON)
interface AdminSummary {
  generated_at: string;
  backend_mode: "github" | "cloudflare" | "hybrid";
  health: {
    repos: Array<{
      name: string;
      last_update: string;
      version: number;
      status: "ok" | "stale" | "error";
      component_count: number;
      relationship_count: number;
      last_error?: string;
    }>;
    error_count_24h: number;
  };
  activity: Array<{
    timestamp: string;
    repo: string;
    version: number;
    commit_sha: string;
    commit_message: string;
    diff_summary: {
      components_added: number;
      components_removed: number;
      components_modified: number;
      relationships_changed: number;
      files_changed: number;
    };
  }>;
  history: {
    daily_counts: Array<{ date: string; count: number }>;
    total_updates: number;
    oldest_snapshot_date: string;
    snapshots_retained: number;
  };
  resources?: {
    worker_requests: { used: number; limit: number };
    kv_writes: { used: number; limit: number };
    d1_writes: { used: number; limit: number };
    r2_reads_month: { used: number; limit: number };
  };
}

// Live config (generated at build time, tells viewer where to find data)
interface LiveConfig {
  enabled: boolean;
  project_id: string;
  backend_mode: "github" | "cloudflare" | "hybrid";
  data_url: string;         // GH Pages URL or R2 public URL
  worker_url?: string;      // Only in cloudflare/hybrid mode
  polling: {
    default_interval_seconds: number;
    min_interval_seconds: number;
    idle_interval_seconds: number;
    adaptive: boolean;
    pause_when_hidden: boolean;
  };
  features: Record<string, boolean>;
}
```

### 8. Top-Level Status Dashboard

Renders between header banners and graph. Only appears when `live_status` has active non-ok statuses. Identical in both backend modes.

```
┌──────────────────────────────────────────────────────────┐
│ STATUS BAR                                               │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│ │ CI Pipeline  │ │ Security    │ │ Deploy      │        │
│ │  2 failing   │ │  3 issues   │ │  OK         │        │
│ │ > api-server │ │ > 1 critical│ │             │        │
│ │ > web-client │ │ > 2 moderate│ │             │        │
│ └─────────────┘ └─────────────┘ └─────────────┘        │
└──────────────────────────────────────────────────────────┘
```

Affected components are clickable via `navigateToComponent()`. Categories auto-hide when all clear.

In **GitHub mode**, statuses update every time the analysis workflow runs (10-20 min batch). In **Cloudflare mode**, CI statuses update within 2-10 seconds via webhook.

### 9. Component-Level Status Indicators

**ComponentNode.tsx**: Status badges alongside existing criticality dots.
- Red pulsing dot: error | Amber: warning | Blue: info | No dot: ok/absent

**DetailPanel.tsx**: Conditional "Status" tab (same conditional pattern as "AI Insights" tab).

### 10. Admin Dashboard

Full-screen modal overlay following `SearchOverlay` pattern. Triggered by header button (with status dot) between dark mode toggle and stats. Keyboard shortcut: Cmd+Shift+A.

#### Tab 1: Health
```
SYSTEM HEALTH                     Mode: GitHub-Native
===========================================================
[my-project]  Last update: 2m ago  v42  178 components  [OK]
[other-repo]  Last update: 3h ago  v8   43 components   [!!]

Connection: Polling version.json (30s, adaptive)
Next poll: 12s
Data source: GitHub Pages (https://myorg.github.io/myrepo)
Errors (24h): 0
```

Shows backend mode badge prominently. In Cloudflare mode, also shows Worker URL and R2 bucket.

#### Tab 2: Activity
Reverse-chronological list of updates with diff summaries. Data from admin-summary.json. Shows commit SHA (linked to GitHub), commit message, component changes.

#### Tab 3: History
CSS bar chart of daily update counts (last 30 days). Same pattern as language breakdown bars in DetailPanel. Snapshot retention stats.

#### Tab 4: Settings
Displays current settings from the `live_monitor` config. Mutable settings (polling interval, feature flags) can be edited. In Cloudflare mode, shows resource limits with CF free tier reference numbers. In GitHub mode, resource limits section is hidden (no CF resources to track).

Each feature shows which backend mode it requires:
```
Features
  [x] Activity log
  [x] Version history
  [x] CI status overlay
  [ ] Real-time CI webhooks        (requires: cloudflare)
  [ ] Real-time push               (requires: cloudflare + paid)
```

#### Tab 5: Resources
Only visible in Cloudflare/hybrid mode. Shows usage bars against configured limits with Cloudflare free tier numbers as reference.

In GitHub mode, this tab shows GitHub-specific stats instead:
```
GITHUB RESOURCES
===========================================================
Pages bandwidth (month):  2.1 GB / 100 GB (soft)
Actions cache:            45 MB / 10 GB
Snapshot versions stored: 10
```

### 11. Request Budget: GitHub Mode

In GitHub mode there are no per-request costs. The only limits are:

| Resource | Limit | Our Usage | Concern? |
|----------|-------|-----------|----------|
| Actions minutes | Unlimited (public) | ~5 min/push | No |
| Actions cache | 10 GB / repo | ~50 MB (2 snapshots) | No |
| Pages bandwidth | 100 GB/month (soft) | See below | Marginal at scale |
| Pages site size | 1 GB | ~10 MB typical | No |

Pages bandwidth calculation for version polling:
- `version.json` is ~100 bytes. With ETag conditional GET, 304 responses are ~200 bytes.
- 5 viewers x 2,880 polls/day x 200 bytes = 2.9 MB/day = 87 MB/month per repo
- At 100 repos: 8.7 GB/month (well under 100 GB)

**The only real constraint in GitHub mode is the 10-minute Pages cache.** After an Actions workflow deploys new data to Pages, viewers won't see it for up to 10 minutes regardless of poll frequency.

### 12. Request Budget: Cloudflare Mode

(Same as previous plan revision, summarized)

| Config | R2 Reads/day | Worker Req/day | Fits Free? |
|--------|-------------|---------------|------------|
| 1 repo, 2 viewers, 30s | 1,975 | 77 | Yes, <2% |
| 3 repos, 5 viewers, 15s | 10,059 | 211 | Yes, ~3% |
| 10 repos, 10 viewers, 15s | 22,708 | 570 | Yes, ~7% |
| 100 repos, 20 viewers, 30s | 60,800 | 3,800 | Yes, ~18% |

### 13. Incremental Analysis Engine

New module: `analyzer/incremental.py`. Runs in GitHub Actions (unlimited compute).

**Pipeline:**
1. Restore previous snapshot from Actions cache
2. `git diff <base-sha>..<head-sha> --name-status`
3. Map changed files to components; re-analyze affected components + importers
4. Generate full updated architecture JSON
5. Compute diff summary metadata
6. In GitHub mode: query GitHub API for CI/CD workflow run statuses, generate status-overlay.json
7. Upload all files to destination (Pages or R2)
8. Save new snapshot to Actions cache

**Fallback to full rescan**: >50% files changed, marker files modified, force push, unreachable SHA.

**Libraries** (removing stdlib constraint): `gitpython`, `tree-sitter`, `pydantic`, `httpx`.

### 14. Viewer Live Update Mechanism

New hook: `viewer/src/hooks/useLiveMonitor.ts`

**Unified polling** (works for both GitHub Pages and R2):
1. Fetch `{data_url}/version.json` with `If-None-Match` ETag header
2. 304 = no change, skip. 200 = new version, fetch manifest + status overlay
3. Merge status overlay into architecture data client-side
4. Update Zustand store, React re-renders

**Adaptive polling:**
- Just updated (within 2 min): poll at `min_interval_seconds`
- Updated within 10 min: poll at `default_interval_seconds`
- Idle: poll at `idle_interval_seconds`
- Tab hidden: pause entirely
- Tab re-visible after 5+ min: immediate poll, then resume adaptive

**Resilience:**
- Circuit breaker: 5 failures → 60s pause → retry → resume or stay paused
- localStorage cache of last-known-good snapshot (instant first load)
- Full refresh every 30 min as safety net

### 15. GitHub Actions Workflow

`.github/workflows/live-monitor.yml`

```yaml
name: Live Architecture Monitor
on:
  push:
    branches: [main]  # from settings
  workflow_run:
    workflows: ["CI", "Tests", "Security"]
    types: [completed]

concurrency:
  group: live-monitor-${{ github.ref }}
  cancel-in-progress: true

jobs:
  update-architecture:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - name: Restore baseline
        uses: actions/cache/restore@v4
        with:
          key: arch-baseline-${{ github.ref }}
          path: .arch-baseline/
      - name: Run incremental analysis
        run: |
          pip install gitpython tree-sitter pydantic httpx
          python analyze.py --incremental \
            --base-sha "${{ github.event.before }}" \
            --head-sha "${{ github.sha }}" \
            --baseline .arch-baseline/architecture.json \
            -o .arch-output/
      - name: Collect CI status
        if: ${{ fromJson(env.LIVE_SETTINGS).ci_integration.collect_in_actions }}
        run: python scripts/collect-ci-status.py  # queries GitHub API
      - name: Save baseline
        uses: actions/cache/save@v4
        with:
          key: arch-baseline-${{ github.ref }}-${{ github.sha }}
          path: .arch-baseline/

      # GitHub-native mode: deploy to Pages
      - name: Deploy to GitHub Pages
        if: ${{ fromJson(env.LIVE_SETTINGS).backend.mode == 'github' }}
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: .arch-output/live
          destination_dir: live

      # Cloudflare mode: upload to R2 + notify Worker
      - name: Upload to R2
        if: ${{ fromJson(env.LIVE_SETTINGS).backend.mode != 'github' }}
        run: |
          aws s3 sync .arch-output/live/ \
            s3://${{ secrets.R2_BUCKET }}/live/${{ github.event.repository.name }}/ \
            --endpoint-url https://${{ secrets.CF_ACCOUNT_ID }}.r2.cloudflarestorage.com
      - name: Notify Worker
        if: ${{ fromJson(env.LIVE_SETTINGS).backend.mode != 'github' }}
        run: |
          curl -X POST "${{ secrets.WORKER_URL }}/ingest" \
            -H "Authorization: Bearer ${{ secrets.WORKER_TOKEN }}" \
            -d @.arch-output/metadata.json

  update-status:
    if: github.event_name == 'workflow_run'
    runs-on: ubuntu-latest
    steps:
      # For GitHub mode: trigger a full update-architecture run
      # For Cloudflare mode: Worker handles this via direct webhook
      - name: Trigger architecture update
        if: ${{ fromJson(env.LIVE_SETTINGS).backend.mode == 'github' }}
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.actions.createWorkflowDispatch({
              owner: context.repo.owner,
              repo: context.repo.repo,
              workflow_id: 'live-monitor.yml',
              ref: 'main'
            });
```

### 16. Backward Compatibility

- Without `live-config.json`, viewer loads static JSON exactly as today
- Without `live_status` fields, no status UI appears
- `--incremental` flag is opt-in
- Admin dashboard only appears when live monitoring is configured
- All new TypeScript fields use optional chaining

---

## Part 3: Implementation Plan

### Phase 0: Remove Vanilla Python Constraint
**Files**: README.md, CONTRIBUTING.md, analyze.py, analyzer/__init__.py, PROJECT-OVERVIEW.md (10 locations)
- Replace "zero external dependencies / stdlib only" with pragmatic dependency policy
- Add `pyproject.toml` with `[project.optional-dependencies]`

### Phase 1: Foundation (Types + Store + Settings Schema)
**Files**: `viewer/src/types.ts`, `viewer/src/store.ts`
- Define all new types: LiveConfig, LiveVersion, AdminSummary, StatusOverlay, ComponentStatus, ArchitectureStatus, ComponentLiveStatus
- Add `live_status` optional fields to Component and Architecture
- Add store state: `adminOpen`, `liveConfig`, `liveVersion`, `liveMonitorStatus`
- Add store actions: `applyStatusOverlay()`, `navigateToComponent()`, `setAdminOpen()`
- Define `solution-explorer.json` schema extension for `live_monitor`
- Unit tests for status overlay merging

### Phase 2: Admin Dashboard UI
**New files**:
- `viewer/src/components/AdminDashboard.tsx` (modal, follows SearchOverlay pattern)
- `viewer/src/components/admin/HealthTab.tsx`
- `viewer/src/components/admin/ActivityTab.tsx`
- `viewer/src/components/admin/HistoryTab.tsx`
- `viewer/src/components/admin/SettingsTab.tsx`
- `viewer/src/components/admin/ResourcesTab.tsx`

**Modified**: `viewer/src/App.tsx` (header button with status dot, modal integration)
- Testable with mock admin-summary.json before any backend exists

### Phase 3: Status Dashboard + Component Status UI
**Modified**: `ComponentNode.tsx`, `DetailPanel.tsx`, `App.tsx`
- StatusDashboard component between header banners and graph
- Status badges on ComponentNode
- Status tab on DetailPanel
- `navigateToComponent()` with drill-level handling

### Phase 4: Live Viewer Integration (GitHub-Native Mode)
**New files**:
- `viewer/src/hooks/useLiveMonitor.ts`
- `viewer/src/hooks/useAdminData.ts`

**Modified**: `viewer/src/App.tsx`
- `live-config.json` detection in loading sequence
- Adaptive polling with circuit breaker
- Visibility-based polling control
- localStorage caching
- Connection status indicator in header
- Works against GitHub Pages (no CF needed)

### Phase 5: GitHub Actions Workflow
**New files**: `.github/workflows/live-monitor.yml`, `scripts/collect-ci-status.py`
**Modified**: `action.yml`
- Incremental analysis job with concurrency group
- CI status collection via GitHub API
- GitHub Pages deployment (for GitHub-native mode)
- R2 upload (for Cloudflare mode)
- `live-config.json` generation
- Actions cache for baseline snapshots

### Phase 6: Incremental Analyzer
**New files**: `analyzer/incremental.py`
**Modified**: `analyzer/cli.py`
- IncrementalAnalyzer class
- `--incremental`, `--base-sha`, `--head-sha`, `--baseline` CLI flags
- Diff summary computation
- Fallback-to-full-rescan logic
- Tests with git repo fixtures

### Phase 7: Cloudflare Infrastructure (optional, for enhanced mode)
**New files**: `infrastructure/cloudflare/worker/`
- Worker: ingest endpoint, webhook handler, settings API, health endpoint
- D1 schema: patches, health, resource_usage tables
- R2 public access setup
- Resource tracking and self-throttling
- wrangler.toml with bindings

### Phase 8: CI/CD Integration
- GitHub API status collection in Actions (GitHub mode)
- Direct webhook reception in Worker (Cloudflare mode)
- Security scan (SARIF) parsing
- Self-clearing status (supersession + expiration)
- Component-to-workflow mapping

### Verification Plan
1. **Unit tests**: Status overlay merging, adaptive polling, circuit breaker, budget calculator
2. **GitHub-native E2E**: Push → Actions → Pages → viewer poll → UI update
3. **Cloudflare E2E**: Push → Actions → R2 → viewer poll → UI update
4. **Webhook E2E** (CF mode): CI fail → webhook → Worker → R2 → viewer update
5. **Free tier validation**: Run 24h on both modes, verify all limits respected
6. **Backward compat**: Static-mode viewer unchanged without live-config.json
7. **Admin dashboard**: All 5 tabs render with mock and real data
8. **Mode switching**: Change `backend.mode` in settings, verify correct behavior

### Critical Files Reference

| File | Role |
|------|------|
| `viewer/src/types.ts` | All new type definitions |
| `viewer/src/store.ts` | Live monitor state, admin state, status merging |
| `viewer/src/App.tsx` | Loading (lines 119-147), header, modals |
| `viewer/src/components/SearchOverlay.tsx` | Pattern for AdminDashboard modal |
| `viewer/src/components/ComponentNode.tsx` | Status badge rendering |
| `viewer/src/components/DetailPanel.tsx` | Status tab (line ~116-123 tab list) |
| `analyzer/scanner.py` | Core scan pipeline for incremental analysis |
| `analyzer/cli.py` | New CLI flags |
| `.github/workflows/architecture-viz.yml` | Template for live-monitor.yml |
