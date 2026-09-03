---
description: Deploy solution-explorer changes to all installations
---

# Deploy Solution Explorer

Pushes the latest changes and redeploys to all tracked installations, including live monitoring workflows.

## Steps

1. Read `DEPLOYMENTS.md` to get the list of all installations (GitHub repos, CF project names, URLs, live mode).

2. Check if there are uncommitted changes:
   - If yes, show the diff summary and ask the user if they want to commit first
   - If no uncommitted changes, continue

3. Check if local main is ahead of remote:
   - If yes, push to origin main
   - If already pushed, continue

4. For each installation listed in `DEPLOYMENTS.md`:
   - Trigger the static workflow: `gh workflow run "Architecture Visualization" -R <repo> --ref main`
   - If the installation has a live mode set (not `none` or empty), also trigger: `gh workflow run "Live Monitor" -R <repo> --ref main`
   - If the Live Monitor workflow doesn't exist in the repo, skip it with a note (don't fail)
   - Report the trigger status for each workflow

5. Wait 10 seconds, then check run status for each triggered workflow.

6. Report results with links:
   - Workflow run URL for each installation (both static and live)
   - The deployment URL from `DEPLOYMENTS.md`
   - Live monitoring status (mode and data URL)

## If argument is "status":
1. Read `DEPLOYMENTS.md`
2. For each installation, run:
   ```bash
   gh run list -R <repo> -w "Architecture Visualization" --limit 1 --json status,conclusion,createdAt
   ```
3. If the installation has live monitoring, also check:
   ```bash
   gh run list -R <repo> -w "Live Monitor" --limit 1 --json status,conclusion,createdAt
   ```
4. Show a summary table of deployment status across all installations:
   ```
   Project      | Static Deploy | Live Monitor | URL
   -------------|---------------|--------------|----
   UnaMentis    | success (2m)  | success (3m) | um-arch.unamentis.org
   ```

## If argument is "live":
1. Read `DEPLOYMENTS.md`
2. Only trigger `Live Monitor` workflows (skip static deployments)
3. Useful for refreshing live data without rebuilding the viewer

## To install in a new repo, use `/install` instead.

## Demo sites are not installations

The VS Code and UnaMentis iOS demos on Cloudflare Pages are NOT redeployed by
the workflows above. They are reviewed, point-in-time bundles published by
hand through the `publish-demo` skill (`.claude/skills/publish-demo/SKILL.md`),
following `docs/publication/DEMO-DEPLOY-RUNBOOK.md`. A merge to `main` does
redeploy the UnaMentis installations through `deploy-downstream.yml`; it never
touches the demos.
