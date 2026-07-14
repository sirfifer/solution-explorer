# Solution Explorer Deployments

Tracks where solution-explorer is installed and how to redeploy after changes.

## Installations

| Project | GitHub Repo | CF Project | URL | Live Mode | Live Data URL |
|---------|-------------|------------|-----|-----------|---------------|
| UnaMentis (static) | `UnaMentis/unamentis` | `um-solution-explorer` | [um-arch.unamentis.org](https://um-arch.unamentis.org) | - | - |
| UnaMentis (full) | `UnaMentis/unamentis` | `solution-explorer-unamentis` | [solution-explorer.unamentis.org](https://solution-explorer.unamentis.org) | github | [unamentis.github.io/unamentis](https://unamentis.github.io/unamentis) |

**Workflows per installation:**
- `architecture.yml`: Static build and Cloudflare Pages deploy (all installations)
- `architecture-full.yml`: Advanced build with live-config injection and Cloudflare Pages deploy
- `live-monitor.yml`: Live data generation, GitHub Pages + optional R2 deploy (if live mode is set)

## Analysis engine (v2 cutover, 2026-07-13)

The default analysis engine is **v2** (the extract/derive/project index engine:
scale, a coverage ledger, and incremental analysis by construction). The legacy
v1 single-pass scanner is reachable only via `--engine v1` and is scheduled for
deletion at the Phase 5 gate. Rollback is a flag flip: pass `--engine v1`, or
revert the one-line default in `analyzer/cli.py`.

Every deploy surface (`action.yml`, `build.sh`, the workflows, and the npx CLI)
invokes `analyze.py` with no `--engine` flag, so all of them inherit this single
default. Nothing overrides it, so the cutover and its rollback happen in one
place.

Downstream impact, verified at cutover:

- Single-repo installs get the full v2 projection with a coverage ledger and the
  viewer coverage badge.
- Multi-repo installs (both UnaMentis installations use a local-path
  `solution-explorer.json`) run v2's multi-repo path. It produces the same
  component tree the viewer already renders. A **unified coverage ledger across
  the per-repo stores is not yet emitted** for multi-repo output, so the viewer
  shows "Coverage unavailable for this dataset" rather than a badge (a graceful
  degrade, not an error). Deferred, see TASKS.md P4-7 Discovered.
- AI-enhancement preservation is unchanged: the deploy merges enhancements from
  the committed baseline into the fresh output with `merge-ai-enhancements.py
  --strict`, which is engine-agnostic and drift-tolerant (P3-3).
- The UnaMentis CI checkout carries only tracked source (its ML weights, GGUF,
  and build artifacts are gitignored), so v2's extraction never touches the
  multi-gigabyte model blobs that live in a local working tree.

`live-monitor.yml` also rides v2. It keeps working (correct output, AI
preserved), but its `--incremental`/`--baseline` flags are accepted no-ops under
v2, so it re-scans cold each run instead of using v1's surgical incremental.
Making it cache the v2 fact store for true incremental is a deferred follow-up
(TASKS.md P4-7 Discovered).

## How Redeployment Works

Downstream deploys are **automatic**. When changes are pushed to `sirfifer/solution-explorer` main:

1. The Architecture Visualization workflow runs CI + self-deploy
2. On success, the Deploy Downstream workflow triggers all UnaMentis workflows
3. Each UnaMentis workflow pulls the latest code from `@main` and redeploys

This is powered by `.github/workflows/deploy-downstream.yml` using a fine-grained PAT (`DEPLOY_TOKEN` secret) with Actions write permission on UnaMentis repos.

### Manual Fallback

If automatic triggers fail or you need to redeploy on demand:

```bash
# Redeploy all installations (static viewer)
gh workflow run "Architecture Visualization" -R UnaMentis/unamentis --ref main

# Redeploy advanced viewer (with live monitoring support)
gh workflow run "Advanced Architecture Visualization" -R UnaMentis/unamentis --ref main

# Redeploy live monitoring data (if live mode is enabled)
gh workflow run "Live Monitor" -R UnaMentis/unamentis --ref main
```

## Adding a New Installation

Use the `/install` command, which handles all steps below automatically.

### Manual Setup

1. In the target repo, create `.github/workflows/architecture.yml`:
   ```yaml
   name: Architecture Visualization
   on:
     push:
       branches: [main, develop]
     pull_request:
       branches: [main]
     workflow_dispatch:
   concurrency:
     group: architecture-${{ github.ref }}
     cancel-in-progress: true
   permissions:
     contents: read
   jobs:
     visualize:
       name: Generate & Deploy Architecture Viz
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: sirfifer/solution-explorer@main
           with:
             config: solution-explorer.json
             deploy-to: cloudflare
             cloudflare-api-token: ${{ secrets.CLOUDFLARE_API_TOKEN }}
             cloudflare-account-id: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
             cloudflare-project-name: <project-name>
   ```

2. Create `solution-explorer.json` in the target repo root:
   ```json
   {
     "solution": "<Project Name>",
     "description": "<Description>",
     "repositories": [
       { "name": "<repo-name>", "path": "." }
     ]
   }
   ```

3. Set secrets on the target repo:
   ```bash
   gh secret set CLOUDFLARE_API_TOKEN -R <owner>/<repo>
   gh secret set CLOUDFLARE_ACCOUNT_ID -R <owner>/<repo>
   ```

4. Create the Cloudflare Pages project (first deploy creates it automatically).

5. Add the installation to the table above.

### Enabling Live Monitoring

After the static installation is working, add live monitoring:

1. Copy scripts to the target repo:
   ```bash
   cp scripts/collect-ci-status.py <target-repo>/scripts/
   cp scripts/generate-admin-summary.py <target-repo>/scripts/
   ```

2. Create `.github/workflows/live-monitor.yml` in the target repo (see the `/install` command for the template).

3. Enable GitHub Pages on the target repo (Settings > Pages > Source: GitHub Actions).

4. **For Cloudflare enhanced mode**, set additional secrets:
   ```bash
   gh secret set CF_WORKER_URL -R <owner>/<repo>
   gh secret set CF_INGEST_TOKEN -R <owner>/<repo>
   gh secret set CF_R2_ACCESS_KEY_ID -R <owner>/<repo>
   gh secret set CF_R2_SECRET_ACCESS_KEY -R <owner>/<repo>
   gh secret set CF_R2_ENDPOINT -R <owner>/<repo>
   ```

5. **For Cloudflare enhanced mode**, configure a GitHub webhook:
   - URL: `<worker-url>/webhook`
   - Content type: `application/json`
   - Secret: the `WEBHOOK_SECRET` configured on the Worker
   - Events: Workflow runs

6. Update the installation table with the live mode and data URL.

## Required Secrets per Installation

**Static deployment (all installations):**
- `CLOUDFLARE_API_TOKEN`: Cloudflare API token with Pages edit permissions
- `CLOUDFLARE_ACCOUNT_ID`: Cloudflare account ID

**Live monitoring, Cloudflare enhanced mode (optional):**
- `CF_WORKER_URL`: Deployed Worker URL (e.g., `https://solution-explorer-api.<account>.workers.dev`)
- `CF_INGEST_TOKEN`: Bearer token for the Worker's `/ingest` endpoint
- `CF_R2_ACCESS_KEY_ID`: R2 API token key ID
- `CF_R2_SECRET_ACCESS_KEY`: R2 API token secret
- `CF_R2_ENDPOINT`: R2 S3-compatible endpoint (`https://<account-id>.r2.cloudflarestorage.com`)
