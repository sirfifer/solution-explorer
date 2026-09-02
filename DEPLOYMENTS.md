# SysCorpus Deployments

Tracks where solution-explorer is installed and how to redeploy after changes.

## Installations

| Project | GitHub Repo | CF Project | URL | Live Mode | Live Data URL |
|---------|-------------|------------|-----|-----------|---------------|
| UnaMentis iOS (SysCorpus demo) | `UnaMentis/unamentis-ios` @ `a5717bf` | `unamentis-ios-demo` | [unamentis-ios-demo.pages.dev](https://unamentis-ios-demo.pages.dev) | reviewed snapshot | [canonical split manifest](https://unamentis-ios-demo.pages.dev/architecture/manifest.json) |
| UnaMentis (static) | `UnaMentis/unamentis` | `um-solution-explorer` | [um-arch.unamentis.org](https://um-arch.unamentis.org) | - | - |
| UnaMentis (full) | `UnaMentis/unamentis` | `solution-explorer-unamentis` | [solution-explorer.unamentis.org](https://solution-explorer.unamentis.org) | github | [unamentis.github.io/unamentis](https://unamentis.github.io/unamentis) |

**Workflows per installation:**
- `architecture.yml`: Static build and Cloudflare Pages deploy (all installations)
- `architecture-full.yml`: Advanced build with live-config injection and Cloudflare Pages deploy
- `live-monitor.yml`: Live data generation, GitHub Pages + optional R2 deploy (if live mode is set)

### UnaMentis iOS public demo (2026-09-02)

The first public SysCorpus demo is a reviewed, point-in-time split projection of
`UnaMentis/unamentis-ios` at commit
`a5717bf00918be39e8e5d1bbc0662ea11ebd7b9c`. The production Pages deployment
is `35beb518-1b96-4c40-8ce4-4f9a25b46478`, built from solution-explorer commit
`0cf0ba3165b6f73029ada51030f153a8c8de31eb`. Its production branch is `main`.
The published manifest has 165 components, 559 mapped files, 458 relationships,
4 tours, and 8 commit-bound review corrections. The bundle carries the upstream
MIT license, notice, and public owner publication metadata.

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

## Known issues and divergence (2026-07-13, resolved items updated 2026-08-20)

- **UnaMentis (full), `solution-explorer.unamentis.org`: verified on v2.** At the Phase 4 gate this install ran `engine=v2` in production and reported "251/251 enhanced components preserved (100.0% of still-present)" after the AI-enhancement merge, so the v2 cutover with enrichment preservation is confirmed end to end here. Its `architecture-full.yml` is pinned to `sirfifer/solution-explorer@main`.

- **UnaMentis (static), `um-arch.unamentis.org`: fixed, now verified on v2.** The stale pin (`sirfifer/solution-explorer@31145dcdc4da6cb95b17a08d5422fe1cfe6e4b16`, a 2026-03-06 pre-v2 commit, behind a misleading `# main` comment) has been re-pinned: `architecture.yml` on the UnaMentis repo now reads `sirfifer/solution-explorer@main`. A separate stale-data defect (the Live overlay serving a stale committed 2026-02-23 file that looked fresh) was fixed 2026-08-21 in `UnaMentis/unamentis#123`, which removed the stale committed file. Live-checked 2026-08-20: `https://um-arch.unamentis.org/architecture/manifest.json` reports `generated_at` 2026-08-21T02:18:42Z, `analyzer_version` 1.2.0, `stats.total_components` 254, no longer "0/254 preserved". Both live demos are now redeployed and verified carrying current engine output; see `docs/publication/HANDOFF-DEMO-PROGRAM.md`.

- **Upstream vs downstream `live-monitor.yml` divergence (F-PL-8).** The UnaMentis `live-monitor.yml` has diverged substantially from the upstream template: it uses the pre-built-JSON path, has no incremental mode, and has no R2/worker steps. Upstream template changes no longer describe what is deployed downstream. Downstream is green; do not assume the upstream template is the source of truth for a given install. When changing the template, verify the effect against the actual downstream workflow files rather than the template alone. Under the v2 default, `live-monitor.yml` runs correctly but its `--incremental`/`--baseline` flags are no-ops, so it re-scans cold each run (see the Analysis engine section above).

## Blue/green projection diff (two-slot health check, card G3)

Every build should be comparable to the one before it. On a deploy, the prior
projection (blue) is diffed against the newly built one (green) with the G1
projection-diff tool (`scripts/blue-green-diff.py`), and the report is written to
the GitHub job step summary plus a `projection-diff.json` run artifact. It is a
HEALTH CHECK, not a gate: the analyzed project moves on its own, so a non-empty
diff mixes engine changes with project changes and must never block the deploy.
`blue-green-diff.py` always exits 0; a missing, unreachable, or malformed blue
degrades to a loud honest note in the summary and the deploy continues.

- **Dogfood (this repo).** Automatic, no configuration. VISION.md keeps the
  self-repo dogfood site LOCAL (no public deploy), so git is the retention slot:
  the committed `architecture.json` is blue and the freshly generated
  `viewer/public/architecture.json` is green. The `Blue/green projection diff
  (dogfood)` step in `.github/workflows/architecture-viz.yml` runs on every push,
  PR, and dispatch and uploads the `projection-diff` artifact.

- **Demo (downstream consumers of `action.yml`).** Opt-in, one line. Add the
  `diff-against-url` input pointing at your currently-live projection JSON and
  the action diffs the just-built projection against it:

  ```yaml
  - uses: sirfifer/solution-explorer@main
    with:
      config: solution-explorer.json
      deploy-to: cloudflare
      diff-against-url: https://<cf-project>.pages.dev/architecture.json
      # ... existing cloudflare-* inputs ...
  ```

  Split-mode installs point it at the manifest instead (for example
  `https://<cf-project>.pages.dev/architecture/manifest.json`); the diff then
  runs at manifest level. Default (unset) skips the step entirely, so existing
  consumers see zero behavior change.

  HONEST OPEN EDGE: the demo side is NOT yet verified end to end. The downstream
  UnaMentis deploy is currently broken on an owner-gated Cloudflare token
  (`DEPLOY_TOKEN` / the downstream workflows), so adding `diff-against-url` to a
  live demo install and confirming a real blue-versus-green demo diff is gated on
  the owner fixing that token. Until then the demo path is exercised only by the
  hermetic tests (`tests/test_blue_green_diff.py`, including the URL-fetch branch)
  and is documented here for one-line adoption once the token is restored. The
  dogfood side IS proven end to end (a real committed-baseline-versus-current
  diff).

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
