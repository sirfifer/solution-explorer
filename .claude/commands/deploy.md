---
description: Deploy solution-explorer changes to all installations
---

# Deploy Solution Explorer

Pushes the latest changes and redeploys to all tracked installations.

## Steps

1. Read `DEPLOYMENTS.md` to get the list of all installations (GitHub repos, CF project names, URLs).

2. Check if there are uncommitted changes:
   - If yes, show the diff summary and ask the user if they want to commit first
   - If no uncommitted changes, continue

3. Check if local main is ahead of remote:
   - If yes, push to origin main
   - If already pushed, continue

4. For each installation listed in `DEPLOYMENTS.md`:
   - Trigger the workflow: `gh workflow run "Architecture Visualization" -R <repo> --ref main`
   - Report the trigger status

5. Wait 10 seconds, then check run status for each triggered workflow.

6. Report results with links:
   - Workflow run URL for each installation
   - The deployment URL from `DEPLOYMENTS.md`

## If argument is "status":
1. Read `DEPLOYMENTS.md`
2. For each installation, run: `gh run list -R <repo> -w "Architecture Visualization" --limit 1 --json status,conclusion,createdAt`
3. Show a summary table of deployment status across all installations

## To install in a new repo, use `/install` instead.
