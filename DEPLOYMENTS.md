# Solution Explorer Deployments

Tracks where solution-explorer is installed and how to redeploy after changes.

## Installations

| Project | GitHub Repo | CF Project | URL | Workflow |
|---------|-------------|------------|-----|----------|
| UnaMentis | `UnaMentis/unamentis` | `um-solution-explorer` | [um-arch.unamentis.org](https://um-arch.unamentis.org) | `.github/workflows/architecture.yml` |

## How to Redeploy

After pushing changes to `sirfifer/solution-explorer` main:

```bash
# Redeploy all installations
gh workflow run "Architecture Visualization" -R UnaMentis/unamentis --ref main
```

Each installation uses `sirfifer/solution-explorer@main` as a GitHub Action, so triggering their workflow picks up the latest analyzer and viewer code automatically.

## Adding a New Installation

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

## Required Secrets per Installation

- `CLOUDFLARE_API_TOKEN`: Cloudflare API token with Pages edit permissions
- `CLOUDFLARE_ACCOUNT_ID`: Cloudflare account ID
