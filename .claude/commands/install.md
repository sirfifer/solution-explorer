---
description: Install solution-explorer into a repo you control
---

# Install Solution Explorer

Sets up solution-explorer in a target repository with Cloudflare Pages deployment and optional live monitoring.

## Required Information

Ask the user for any of these that aren't provided as arguments:

1. **Local path** to the target repo (e.g., `/Users/ramerman/dev/some-project`)
2. **Cloudflare Pages project name** (e.g., `myproject-solution-explorer`)
3. **Deployment URL** if they have a custom domain (optional, defaults to `<cf-project>.pages.dev`)
4. **Live monitoring mode** (optional, default: `github`):
   - `github`: Free, live data served from GitHub Pages with ~10-min cache. CI status collected in batch.
   - `cloudflare`: Real-time updates via Cloudflare Worker + R2. Requires Worker infrastructure (see Step 5b).
   - `none`: Static deployment only, no live monitoring.

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

### 3. Create the static workflow file

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

### 5. Set up live monitoring (if not `none`)

#### 5a. Copy scripts to target repo

```bash
# From the solution-explorer repo
cp /Users/ramerman/dev/solution-explorer/scripts/collect-ci-status.py <target-repo>/scripts/collect-ci-status.py
cp /Users/ramerman/dev/solution-explorer/scripts/generate-admin-summary.py <target-repo>/scripts/generate-admin-summary.py
```

Create the `scripts/` directory in the target repo if it doesn't exist.

#### 5b. For Cloudflare enhanced mode: verify Worker is deployed

Check that the Cloudflare Worker infrastructure is running:

```bash
curl -s <worker-url>/health | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Worker: {d[\"status\"]}, DB: {d[\"db\"]}, R2: {d[\"r2\"]}')"
```

If the Worker is not deployed, tell the user:
> The Cloudflare Worker infrastructure needs to be deployed first. Run:
> ```bash
> cd /Users/ramerman/dev/solution-explorer/infrastructure/cloudflare
> bash setup.sh
> ```

Look up the Worker URL in `DEPLOYMENTS.md` or ask the user for it.

#### 5b (continued). Set Cloudflare secrets on the target repo

```bash
gh secret set CF_WORKER_URL -R <owner/repo>
gh secret set CF_INGEST_TOKEN -R <owner/repo>
gh secret set CF_R2_ACCESS_KEY_ID -R <owner/repo>
gh secret set CF_R2_SECRET_ACCESS_KEY -R <owner/repo>
gh secret set CF_R2_ENDPOINT -R <owner/repo>
```

Ask the user for values, or check if they exist on another installation.

#### 5c. Create the live monitor workflow

Write `.github/workflows/live-monitor.yml` in the target repo:

```yaml
name: Live Monitor

on:
  push:
    branches: [main]
  workflow_run:
    workflows: ["Architecture Visualization"]
    types: [completed]
  workflow_dispatch:

concurrency:
  group: live-monitor-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read
  pages: write
  id-token: write
  actions: read

jobs:
  update-and-deploy:
    name: Update Architecture & Deploy Live Data
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Checkout Solution Explorer
        uses: actions/checkout@v4
        with:
          repository: sirfifer/solution-explorer
          path: .solution-explorer

      - name: Install Dependencies
        run: |
          if [ -f ".solution-explorer/pyproject.toml" ]; then
            pip install -e ".solution-explorer[live]" 2>/dev/null || echo "Optional deps unavailable, using stdlib only"
          fi

      - name: Determine Commit SHA
        id: sha
        run: |
          if [ "${{ github.event_name }}" = "workflow_run" ]; then
            echo "sha=${{ github.event.workflow_run.head_sha }}" >> "$GITHUB_OUTPUT"
          else
            echo "sha=${{ github.sha }}" >> "$GITHUB_OUTPUT"
          fi

      - name: Restore Architecture Baseline
        uses: actions/cache/restore@v4
        with:
          path: .arch-baseline
          key: arch-baseline-${{ github.ref }}

      - name: Run Architecture Analyzer
        run: |
          mkdir -p .arch-output/live

          if [ -f "solution-explorer.json" ]; then
            python3 .solution-explorer/analyze.py --config solution-explorer.json \
              -o .arch-output/architecture.json --compact
          else
            python3 .solution-explorer/analyze.py . \
              -o .arch-output/architecture.json --compact
          fi

      - name: Collect CI Status
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python3 scripts/collect-ci-status.py \
            --repo "${{ github.repository }}" \
            --sha "${{ steps.sha.outputs.sha }}" \
            -o .arch-output/live/status-overlay.json

      - name: Generate version.json
        run: |
          python3 -c "
          import json, time, datetime
          data = {
              'version': int(time.time()),
              'updated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'commit_sha': '${{ steps.sha.outputs.sha }}'
          }
          with open('.arch-output/live/version.json', 'w') as f:
              json.dump(data, f, indent=2)
          "

      - name: Generate live-config.json
        run: |
          python3 -c "
          import json, os
          repo = '${{ github.repository }}'
          owner, repo_name = repo.split('/')
          worker_url = os.environ.get('CF_WORKER_URL', '')

          mode = 'cloudflare' if worker_url else 'github'
          data_url = f'https://{owner}.github.io/{repo_name}/live'

          config = {
              'enabled': True,
              'data_url': data_url,
              'backend_mode': mode,
              'polling': {
                  'default_interval_seconds': 15 if mode == 'cloudflare' else 30,
                  'min_interval_seconds': 10 if mode == 'cloudflare' else 15,
                  'idle_interval_seconds': 60 if mode == 'cloudflare' else 120,
                  'adaptive': True,
                  'pause_when_hidden': True
              },
              'features': {
                  'activity_log': True,
                  'admin_dashboard': True,
                  'version_history': True,
                  'ci_status_overlay': True,
                  'realtime_ci_webhooks': mode == 'cloudflare',
                  'realtime_push': False
              }
          }
          if worker_url:
              config['worker_url'] = worker_url
              config['project_id'] = repo_name
          with open('.arch-output/live/live-config.json', 'w') as f:
              json.dump(config, f, indent=2)
          "
        env:
          CF_WORKER_URL: ${{ secrets.CF_WORKER_URL }}

      - name: Generate Admin Summary
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python3 scripts/generate-admin-summary.py \
            --arch .arch-output/architecture.json \
            --version .arch-output/live/version.json \
            --repo "${{ github.repository }}" \
            --sha "${{ steps.sha.outputs.sha }}" \
            -o .arch-output/live/admin-summary.json

      - name: Copy Architecture to Live Directory
        run: cp .arch-output/architecture.json .arch-output/live/architecture.json

      - name: Save Architecture Baseline
        uses: actions/cache/save@v4
        with:
          path: .arch-baseline
          key: arch-baseline-${{ github.ref }}-${{ steps.sha.outputs.sha }}

      - name: Upload Pages Artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: .arch-output/live

      - name: Deploy to GitHub Pages
        id: deploy
        uses: actions/deploy-pages@v4

      # --- Cloudflare R2 Upload (only when CF_WORKER_URL is configured) ---

      - name: Upload to Cloudflare R2
        if: ${{ secrets.CF_WORKER_URL != '' }}
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.CF_R2_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.CF_R2_SECRET_ACCESS_KEY }}
          AWS_DEFAULT_REGION: auto
        run: |
          PROJECT_ID="${{ github.event.repository.name }}"
          ENDPOINT="${{ secrets.CF_R2_ENDPOINT }}"
          BUCKET="solution-explorer-data"

          for file in .arch-output/live/*.json; do
            filename=$(basename "$file")
            aws s3 cp "$file" "s3://${BUCKET}/${PROJECT_ID}/${filename}" \
              --endpoint-url "$ENDPOINT" \
              --content-type "application/json"
          done

          aws s3 cp .arch-output/architecture.json \
            "s3://${BUCKET}/${PROJECT_ID}/manifest.json" \
            --endpoint-url "$ENDPOINT" \
            --content-type "application/json"

          echo "Uploaded to R2: ${BUCKET}/${PROJECT_ID}/"

      - name: Notify Cloudflare Worker
        if: ${{ secrets.CF_WORKER_URL != '' }}
        run: |
          PROJECT_ID="${{ github.event.repository.name }}"

          COMPONENT_COUNT=$(python3 -c "
          import json
          with open('.arch-output/architecture.json') as f:
              arch = json.load(f)
          def count(comps):
              return sum(1 + count(c.get('children', [])) for c in comps)
          print(count(arch.get('components', [])))
          ")

          RELATIONSHIP_COUNT=$(python3 -c "
          import json
          with open('.arch-output/architecture.json') as f:
              arch = json.load(f)
          print(len(arch.get('relationships', [])))
          ")

          VERSION=$(python3 -c "
          import json
          with open('.arch-output/live/version.json') as f:
              print(json.load(f)['version'])
          ")

          COMMIT_MSG=$(python3 -c "
          import json
          msg = '''${{ github.event.head_commit.message || 'workflow dispatch' }}'''
          print(json.dumps(msg[:200]))
          ")

          HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
            -X POST '${{ secrets.CF_WORKER_URL }}/ingest' \
            -H 'Authorization: Bearer ${{ secrets.CF_INGEST_TOKEN }}' \
            -H 'Content-Type: application/json' \
            -d "{
              \"project_id\": \"${PROJECT_ID}\",
              \"version\": ${VERSION},
              \"commit_sha\": \"${{ steps.sha.outputs.sha }}\",
              \"commit_message\": ${COMMIT_MSG},
              \"component_count\": ${COMPONENT_COUNT},
              \"relationship_count\": ${RELATIONSHIP_COUNT}
            }")

          if [ "$HTTP_CODE" -eq 204 ]; then
            echo "Worker notified successfully"
          else
            echo "::warning::Worker returned HTTP ${HTTP_CODE}"
          fi
```

**Key difference from the solution-explorer version:** This workflow checks out `sirfifer/solution-explorer` to access the analyzer, but uses local `scripts/` for CI collection and admin summary generation.

#### 5d. Enable GitHub Pages

```bash
# Enable GitHub Pages with Actions as the source
gh api repos/<owner>/<repo>/pages -X POST -f source='{"branch":"","path":"/"}' --input - <<< '{"build_type":"workflow"}' 2>/dev/null || echo "Pages may already be enabled"
```

If this fails, tell the user to enable it manually: Settings > Pages > Source: GitHub Actions.

#### 5e. For Cloudflare enhanced mode: configure webhook

Tell the user:
> Configure a GitHub webhook on the target repo:
> 1. Go to Settings > Webhooks > Add webhook
> 2. Payload URL: `<worker-url>/webhook`
> 3. Content type: `application/json`
> 4. Secret: the `WEBHOOK_SECRET` configured on the Worker
> 5. Events: Select "Workflow runs"

### 6. Commit and push

Commit all files to the target repo's main branch:
- `.github/workflows/architecture.yml`
- `solution-explorer.json`
- If live monitoring: `.github/workflows/live-monitor.yml`
- If live monitoring: `scripts/collect-ci-status.py`
- If live monitoring: `scripts/generate-admin-summary.py`

Push to main so the workflows trigger automatically.

### 7. Update DEPLOYMENTS.md

Back in the solution-explorer repo, add a row to the Installations table in `DEPLOYMENTS.md`:

```markdown
| <Project> | `<owner/repo>` | `<cf-project>` | [url](https://url) | <live-mode> | <live-data-url> |
```

Also update the "How to Redeploy" section to include the new repo in the `gh workflow run` commands for both `Architecture Visualization` and (if live) `Live Monitor`.

### 8. Verify

Wait for the workflows to complete:
```bash
gh run list -R <owner/repo> -w "Architecture Visualization" --limit 1
```

If live monitoring is enabled:
```bash
gh run list -R <owner/repo> -w "Live Monitor" --limit 1
```

Report the deployment URL and live monitoring status to the user.

## Notes

- The first Cloudflare Pages deploy auto-creates the project if it doesn't exist
- Custom domains must be configured manually in the Cloudflare dashboard
- All installations share the same Cloudflare API token and account ID
- The Worker infrastructure is shared across all installations (each gets a unique `project_id`)
- GitHub Pages mode works without any Cloudflare infrastructure beyond Pages for the viewer
- The `live-monitor.yml` workflow auto-detects the mode: if `CF_WORKER_URL` secret is set, it uses Cloudflare enhanced mode; otherwise it uses GitHub Pages mode
