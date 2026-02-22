# Solution Explorer Deployments

Tracks where solution-explorer is installed and how to redeploy after changes.

## Installations

| Project | GitHub Repo | CF Project | URL | Live Mode | Live Data URL |
|---------|-------------|------------|-----|-----------|---------------|
| UnaMentis | `UnaMentis/unamentis` | `um-solution-explorer` | [um-arch.unamentis.org](https://um-arch.unamentis.org) | cloudflare (pending) | TBD |

**Workflows per installation:**
- `architecture.yml`: Static build and Cloudflare Pages deploy (all installations)
- `live-monitor.yml`: Live data generation, GitHub Pages + optional R2 deploy (if live mode is set)

## How to Redeploy

After pushing changes to `sirfifer/solution-explorer` main:

```bash
# Redeploy all installations (static viewer)
gh workflow run "Architecture Visualization" -R UnaMentis/unamentis --ref main

# Redeploy live monitoring data (if live mode is enabled)
gh workflow run "Live Monitor" -R UnaMentis/unamentis --ref main
```

Each installation uses `sirfifer/solution-explorer@main` as a GitHub Action, so triggering their workflow picks up the latest analyzer and viewer code automatically.

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
