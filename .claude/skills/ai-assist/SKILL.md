---
name: ai-assist
description: Analyze a codebase, enhance the results with AI, and deploy the interactive architecture viewer
---

# /ai-assist - Architecture Enhancement Skill

Analyze a codebase with solution-explorer, enhance the results with AI-generated
descriptions and annotations, and deploy the interactive architecture viewer.

The AI enhancement itself (the DPEA pipeline: Digest, Partition, Enhance,
Assemble) is now industrialized behind a headless CLI, `analyze.py enhance`
(implemented in `analyzer/enrich/`, P7-2). This skill is a thin wrapper that
drives that CLI and then handles the interactive validate/preview/deploy flow.
It no longer runs the DPEA phases inline; the CLI does, deterministically and
with provenance.

## Usage

```
/ai-assist <path-to-codebase>
/ai-assist <path-to-codebase> --update
```

- `path-to-codebase`: absolute path to the project/repo to analyze
- `--update`: re-enhance only stale or missing components plus their
  architectural neighbours (staleness comes from enrichment provenance, so this
  is precise and cheap)

> **Working directory.** Run the commands in this skill from the root of your
> local `solution-explorer` checkout. All solution-explorer paths below
> (`analyze.py`, `viewer/`, `scripts/`, `DEPLOYMENTS.md`) are relative to that
> root. The `<codebase-path>` argument is the separate absolute path to the
> project you are analyzing.

## Step 1: Analyze into a fact store and project the viewer data

Run the v2 analyzer with `--split`. This builds (or updates) the persistent
fact store and projects the viewer's split manifest.

```bash
python3 analyze.py <codebase-path> --engine v2 --split \
  -o viewer/public/architecture \
  --store <codebase-path>/.solution-explorer/index.db
```

The store is the durable, incremental baseline. Enrichment rows are written into
it and carry provenance (the content digest and commit they were derived from),
so re-analysis never loses AI content and staleness is computed, not guessed.

## Step 2: Enhance headlessly

Run the enrichment CLI against the store. It partitions the components, invokes
Claude per partition, validates every response against the `ai_enhance` schema,
writes provenance-stamped enrichment rows, and runs the quality scorer as a
gate. A partition whose response fails schema validation twice is reported as
failed and its targets are left unenriched (never junk).

```bash
# Full enhancement
python3 analyze.py enhance <codebase-path> \
  --store <codebase-path>/.solution-explorer/index.db

# Staleness-scoped re-enhancement (only stale/new + neighbours)
python3 analyze.py enhance <codebase-path> --update \
  --store <codebase-path>/.solution-explorer/index.db
```

Useful flags (cost controls, all documented via `--help`):

- `--dry-run`: print the partition plan and prompt sizes without invoking the
  model. Run this first on an unfamiliar repo to see the shape and estimated
  cost.
- `--max-partitions N`: cap how many partitions are processed.
- `--max-parallel N`: bound concurrent invocations (default 4).
- `--model <name>`: model for enhancement (default `sonnet`, a sonnet-class
  model; the model strategy uses sonnet-class for enhancement).
- `--threshold <pct>`: minimum quality score the gate requires (default 85).
- `--report <path>`: write the machine-readable run report (partition
  outcomes, targets enriched, cost, gate result).

The CLI exits non-zero if any partition failed or the quality gate did not pass,
so it is safe to wire into CI. Cost and the gate verdict are printed at the end
of the run.

## Step 3: Re-project so the viewer data carries the enhancement

Enrichment lives in the store. The projection applies it (with staleness
markers) onto the viewer's manifest, so re-run the analyzer to refresh the
output with the new `ai_enhance` overlay:

```bash
python3 analyze.py <codebase-path> --engine v2 --split \
  -o viewer/public/architecture \
  --store <codebase-path>/.solution-explorer/index.db
```

This is incremental: the warm store means unchanged files are not re-parsed.

## Step 4: Validate

Verify the output is valid and loadable, then run the full quality scoring:

```bash
python3 -c "
import json
d = json.load(open('viewer/public/architecture/manifest.json'))
print(f'OK: {len(d[\"components\"])} components, {len(d[\"relationships\"])} relationships')
"

python3 scripts/score-ai-enhancement-quality.py \
  --architecture viewer/public/architecture/manifest.json
```

If any components are missing `ai_enhance` or quality is below threshold, re-run
Step 2 (optionally with `--update`) before proceeding.

## Step 5: Build and Deploy

After the enhanced JSON is validated, build locally and deploy to production.

### 5a. Build locally for validation

```bash
cd viewer && npm run build
```

If the build fails, fix the issue before proceeding.

### 5b. Start local preview

```bash
cd viewer && npx vite preview --port 4173
```

Do NOT tell the user the preview is ready yet. Run validation first.

### 5c. Validate the preview

```bash
sleep 2 && bash scripts/validate-preview.sh http://localhost:4173
```

This script verifies:
- Architecture JSON is valid with expected structure
- The built `dist/` has the expected files
- The preview server returns HTML for the index page
- The preview server returns valid JSON for the architecture data
- Non-existent JSON paths are not misidentified as JSON (SPA fallback guard)

**If validation fails, do NOT tell the user the preview is ready.** Diagnose,
fix, rebuild, and re-run validation. Only proceed after all checks pass.

Once validation passes, tell the user:

```
Local preview is ready at: http://localhost:4173/
```

### 5d. Determine deployment target

Get the target codebase's GitHub remote:

```bash
cd <codebase-path> && git remote get-url origin
```

Extract `owner/repo` from the URL (handles both HTTPS and SSH formats).

Read `DEPLOYMENTS.md` and find the row matching the GitHub repo. Extract the
deployment URL. If no matching installation is found, tell the user and skip
deployment.

### 5e. Deploy

Copy the enhanced architecture output to the target codebase and push:

```bash
cp -r viewer/public/architecture \
  <codebase-path>/architecture
cd <codebase-path>
git add architecture/
git commit -m "Update AI-enhanced architecture visualization"
git push
```

The push to main automatically triggers the Architecture Visualization and Live
Monitor workflows. These workflows run the analyzer fresh but preserve the
`ai_enhance` data from the committed baseline. (Provenance-tracked enrichment in
the store is the durable source; the committed baseline plus the preservation
step keep AI content across CI re-analysis.)

If the current branch is not main, warn the user that deployment to production
only triggers on push to main.

### 5f. Monitor deployment

Wait 15 seconds, then check the workflow status:

```bash
gh run list -R <owner/repo> -w "Architecture Visualization" --limit 1
```

If the run is still in progress, wait 30 seconds and check again (up to 3 times).

### 5g. Report results

```
Architecture viewer ready:
  Local preview:  http://localhost:4173/
  Production:     <deployment-url> (deploying...)
```

Once the workflow completes:

```
Deployment complete:
  Production: <deployment-url>
```

### 5h. Live monitoring note

Check `DEPLOYMENTS.md` for the target repo's live monitoring mode. If live
monitoring is enabled, inform the user:

```
Live monitoring: The enhanced JSON will propagate through the Live Monitor
workflow automatically on this push. The live dashboard will reflect AI
enhancements within 15-90 seconds (Cloudflare mode) or 10-20 minutes
(GitHub mode).
```

## Key Rules

1. NEVER remove or alter data produced by the static analyzer. AI writes only
   the `ai_enhance` overlay (invariant I1).
2. The enrichment CLI owns validation and the quality gate. Do not hand-edit
   `ai_enhance` blocks into the manifest; enhance the store and re-project.
3. Every enrichment row carries provenance (digest + commit). Stale enrichment
   renders with a marker and is re-enhanced by `--update`; it is never silently
   dropped (invariant I5).
4. The final output MUST include a local preview URL and, if deployed, the
   production URL and deployment status.
5. ALWAYS run the quality scoring script (or rely on the CLI's gate) before
   declaring success.

## Schema Reference

See [RESOURCES.md](RESOURCES.md) for the full schema of `ai_enhance` fields,
valid vocabulary values, criticality calibration guidance, and few-shot quality
examples. The enrichment CLI builds its prompts from this same contract.
