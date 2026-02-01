---
description: Install solution-explorer into a repo you control
---

# Install Solution Explorer

Sets up solution-explorer in a target repository with Cloudflare Pages deployment.

## Required Information

Ask the user for any of these that aren't provided as arguments:

1. **Local path** to the target repo (e.g., `/Users/ramerman/dev/some-project`)
2. **Cloudflare Pages project name** (e.g., `myproject-solution-explorer`)
3. **Deployment URL** if they have a custom domain (optional, defaults to `<cf-project>.pages.dev`)

## Steps

### 1. Gather info from the target repo

```bash
# Get the GitHub remote
cd <local-path>
gh repo view --json nameWithOwner,description
```

Store the `nameWithOwner` (e.g., `sirfifer/voicelearn-ios`) and `description`.

### 2. Check if secrets exist

```bash
gh secret list -R <owner/repo>
```

If `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` are not set:
- Check if they exist on `sirfifer/solution-explorer` (our repo has them)
- Copy them over using `gh secret set` with values from the user
- Or tell the user which secrets need to be set

### 3. Create the workflow file

Write `.github/workflows/architecture.yml` in the target repo:

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
          cloudflare-project-name: <CF_PROJECT_NAME>
```

Replace `<CF_PROJECT_NAME>` with the Cloudflare Pages project name provided.

### 4. Create the config file

Write `solution-explorer.json` in the target repo root:

```json
{
  "solution": "<Project Name from repo description or user>",
  "description": "<Description>",
  "repositories": [
    { "name": "<repo-name>", "path": "." }
  ]
}
```

### 5. Commit and push

Commit both files to the target repo's main branch:
- `.github/workflows/architecture.yml`
- `solution-explorer.json`

Push to main so the workflow triggers automatically.

### 6. Update DEPLOYMENTS.md

Back in the solution-explorer repo, add a row to the Installations table in `DEPLOYMENTS.md`.

Also update the "How to Redeploy" section to include the new repo in the `gh workflow run` commands.

### 7. Verify

Wait for the workflow to complete:
```bash
gh run list -R <owner/repo> -w "Architecture Visualization" --limit 1
```

Report the deployment URL to the user.

## Notes

- The first Cloudflare Pages deploy auto-creates the project if it doesn't exist
- Custom domains must be configured manually in the Cloudflare dashboard
- All installations share the same Cloudflare API token and account ID
