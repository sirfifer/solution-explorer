---
name: ai-assist
description: Analyze a codebase, enhance the results with AI, and deploy the interactive architecture viewer
---

# /ai-assist - Architecture Enhancement Skill

Analyze a codebase with solution-explorer, enhance the results with AI-generated
descriptions and annotations using the DPEA (Digest, Partition, Enhance, Assemble)
pattern, and deploy the interactive architecture viewer.

## Usage

```
/ai-assist <path-to-codebase>
/ai-assist <path-to-codebase> --update
```

- `path-to-codebase`: absolute path to the project/repo to analyze
- `--update`: skip re-analysis, enhance only new/changed components (see Step 1b)

> **Working directory.** Run the commands in this skill from the root of your
> local `solution-explorer` checkout. All solution-explorer paths below
> (`analyze.py`, `viewer/`, `scripts/`, `DEPLOYMENTS.md`) are relative to that
> root. The `<codebase-path>` argument is the separate absolute path to the
> project you are analyzing.

## Pipeline Overview

The enhancement pipeline uses four phases that scale from 10-component projects
to 2000+ component codebases. For small codebases (<25 components), Phase 2
produces a single partition and the pipeline behaves identically to a single-agent
enhancement pass.

```
Step 1: Analyze ─> Phase 1: DIGEST ─> Phase 2: PARTITION ─> Phase 3: ENHANCE ─> Phase 4: ASSEMBLE ─> Step 5-6: Validate & Deploy
(static analyzer)  (single agent)     (deterministic)        (parallel agents)    (single agent)
```

## Step 1: Run the Analyzer

Run the static analyzer with the `--split` flag. Split mode is required for the
DPEA pipeline.

```bash
python3 analyze.py <codebase-path> \
  --split -o viewer/public/architecture --pretty
```

This produces `architecture/manifest.json` + per-component `data/detail-{id}.json`
files. The manifest contains the full component tree, relationships, stats, and
is the primary input for the enhancement pipeline.

> `analyze.py` is a thin CLI wrapper around the `analyzer/` package.

If `viewer/public/architecture/manifest.json` already exists from a previous run,
ask the user whether to re-analyze from scratch or enhance the existing file.

### Step 1b: Update mode (when --update is specified)

When `--update` is provided, skip the analyzer run entirely. The manifest must
already exist.

1. Read the existing `manifest.json`.
2. Determine the "core update set" of components that need re-enhancement:
   - Components with no `ai_enhance` at all (newly added, never enhanced)
   - Components where `ai_enhance.ai_enhanced_at` is older than the architecture's
     `generated_at` timestamp (stale after re-analysis)
   - Components listed in the most recent `changelog` entries as `component_added`
     or `component_modified`
3. Expand the update set to include **architectural neighbors**: any component
   connected to a core update set member via ANY relationship type (not just
   imports). Use the `build_architectural_neighbor_graph` function from
   `analyzer/incremental.py`. This catches ripple effects where a change in one
   component affects how its neighbors should be described (e.g., a server
   changing its auth scheme invalidates the client's relationship description).
4. Report scope to user: "Update mode: N core + M neighbor components to
   re-enhance out of T total."
5. Always re-run Phase 1 (Digest), since it is cheap and provides current
   architectural framing for downstream agents.
6. Run Phase 2 on just the update set components, creating temporary
   mini-partitions.
7. Run Phase 3 and Phase 4 on only those mini-partitions.
8. Merge results into the existing manifest using component ID-based merge.
   Preserve existing `ai_enhance` data on all other components untouched.
9. Always regenerate architecture-level `ai_enhance` (Phase 1 output) since the
   overall narrative may have shifted.

Then continue to Step 5-6 as normal.

## Phase 1: Digest (Single Agent, Full Manifest)

Read the full manifest (all components, relationships, stats, changelog, metrics,
but NO source code) and produce:

### 1a. Digest input preparation

Prepare the manifest context for the digest agent:

1. Read the full `manifest.json` contents.
2. For **digest enrichment**, include:
   - Any non-null `description` and `docs.purpose` fields from existing component data
   - For the top 5-10 most-connected components (by relationship count, both inbound
     and outbound), include the first 20-30 lines of their main entry point file
     (~2-3K additional tokens). This gives domain context beyond structural metadata.

### 1b. Produce the Structured Architectural Digest

The digest agent produces a structured template (NOT free-form prose) saved to
`enhancement/digest.md`:

```markdown
## System Type
[monolith / modular monolith / microservices / client-server / mobile+server / etc.]

## Deployment Topology
[single binary / containerized / mobile+server / serverless / etc.]

## Primary Data Flows
1. [numbered list of 3-7 primary user-facing data flows]
2. ...

## Technology Map
| Language | Purpose |
|----------|---------|
| Swift    | iOS client |
| Python   | Server management |
| ...      | ... |

## Critical Path Components
[list of component IDs on the primary user-facing path]

## Terminology Glossary
| Term | Canonical Name | Do NOT use |
|------|---------------|------------|
| [domain entity] | [exact term to use] | [synonyms to avoid] |
| ... | ... | ... |

All downstream agents MUST use glossary terms exactly. Do not introduce synonyms.

## Preliminary Role Assignments
| Component ID | Suggested Role | Rationale |
|-------------|---------------|-----------|
| [top-level comp] | [role from vocabulary] | [1-sentence why] |
| ... | ... | ... |

Downstream agents may override with justification based on source code reading.

## Criticality Calibration
In this codebase:
- "critical" means: [specific description with example component IDs]
- "important" means: [specific description with example component IDs]
- "supporting" means: [specific description with example component IDs]

## Confidence Self-Assessment
- Confidence: [1-5]
- Ambiguous areas: [list of areas where the manifest was insufficient]
```

### 1c. Produce architecture-level `ai_enhance`

Write `enhancement/architecture-ai-enhance.json` containing the root-level
`ai_enhance` object:

```json
{
  "summary": "3-5 sentence executive summary of the entire system.",
  "data_flow_narrative": "A paragraph describing how a typical user request flows through the system.",
  "component_groups": [
    { "name": "Client Layer", "component_ids": ["ios-app", "web-app"] }
  ],
  "recent_changes_summary": "2-3 sentence summary when changelog exists.",
  "tech_diversity": "1-2 sentence summary of the technology mix.",
  "test_health_summary": "1-2 sentence overview of testing across the codebase.",
  "observations": [],
  "ai_enhanced_at": "<current ISO timestamp>",
  "ai_enhance_version": 2
}
```

### 1d. Digest validation

After Phase 1, validate programmatically:
- Does the digest mention all top-level components?
- Does the technology map match `stats.languages`?
- Are all major relationship types (http, websocket, database, etc.) referenced?

If confidence is below 4, provide README content or additional entry point files
and re-run Phase 1.

## Phase 2: Partition (Deterministic Algorithm)

A Python script (NOT an AI agent) partitions the component tree. This is
deterministic and fast.

### 2a. Natural boundary grouping

1. Each top-level subtree under root that fits the complexity budget becomes its
   own partition. "Fits" is determined by estimated source token weight (from
   `metrics.lines`), targeting ~20,000-50,000 lines per partition.
2. Oversized subtrees recurse at their child level, not at arbitrary DFS boundaries.
3. **Never split a parent from its direct children.** If a subtree must be split,
   split at the grandchild level but always include the subtree root in one partition.
4. Allow partitions as small as 5 components (for code-heavy server modules) and as
   large as 30 (for lightweight UI screens with 1 file each). Soft limits.

### 2b. Affinity-based merging

For undersized orphan components or singleton subtrees, assign to the partition
containing the most of their relationship neighbors. This is greedy bin-packing:
for each orphan, count relationships to each existing partition, assign to the
highest-affinity partition that still has budget.

### 2c. Dependency metrics computation

For each component, compute (O(V+E) on the full graph):
- Inbound relationship count
- Outbound relationship count
- Whether it is a leaf or articulation point in the dependency graph

Include these metrics in the partition manifest so subagents can make
structurally-informed criticality assessments.

### 2d. Token budget estimation

For each partition, estimate total source code tokens from file sizes. If a
partition exceeds 50K estimated source tokens, split it further regardless of
component count.

### 2e. Cross-partition relationship context

For each relationship where the target is in a different partition, include a
compact summary of the target component: name, type, framework, metrics, and
existing description if any (~50-100 tokens per relationship). This gives the
source agent enough context to describe the relationship without reading the
target's source code.

### 2f. Output

Write partition files to `enhancement/`:
- `partition-plan.json`: full partition plan with metrics
- `partition-{n}.json` for each partition, containing:
  - Component IDs in this partition
  - Relationship keys assigned to this partition
  - File paths that need reading for this partition's components
  - Per-component dependency metrics (inbound/outbound counts, articulation point flag)
  - Cross-partition relationship neighbor summaries
  - Estimated source token budget

### Implementation

Write a Python script to perform partitioning. The algorithm is:

```python
# Pseudocode for the partitioner
def partition(manifest):
    components = flatten_tree(manifest["components"])
    relationships = manifest["relationships"]

    # 2a: Group by natural subtree boundaries
    partitions = []
    for subtree_root in manifest["components"]:
        lines = sum_lines(subtree_root)  # recursive metrics.lines
        if lines <= 50000:
            partitions.append(collect_all_ids(subtree_root))
        else:
            # Recurse at child level
            for child in subtree_root.get("children", []):
                child_lines = sum_lines(child)
                if child_lines <= 50000:
                    partitions.append(collect_all_ids(child))
                else:
                    # Split further at grandchild level, keeping child root
                    # ... recursive splitting
                    pass

    # 2b: Merge undersized partitions via affinity
    # 2c: Compute dependency metrics
    # 2d: Check token budgets, split oversized
    # 2e: Build cross-partition neighbor summaries
    # 2f: Write output files

    return partitions
```

For codebases with <25 components, this produces a single partition containing
all components. The pipeline degenerates to a single enhancement pass.

## Phase 3: Enhance (Parallel Subagents)

For each partition, spawn a subagent using the Task tool.

### Subagent context (what each subagent receives)

1. **The Structured Digest** from Phase 1 (top-down context, terminology glossary,
   criticality calibration, preliminary role assignments)
2. **The partition manifest**: component IDs, relationship keys, dependency metrics,
   cross-partition neighbor summaries
3. **The component tree** (names and structure only, for understanding neighbors).
   For codebases above 500 components, include a contextual subset: full path from
   root to each partition component, immediate siblings/parent, and components on
   the other end of cross-partition relationships (~100-150 entries instead of full)
4. **Quality rubric**: 2-3 example `ai_enhance` blocks from RESOURCES.md as
   few-shot calibration, plus explicit constraints (help_text must be 3-5 sentences,
   use glossary terms only, justify criticality against dependency metrics)
5. **Enhancement schema**: the full schema from RESOURCES.md

### Subagent instructions

Each subagent:

1. **Reads source files** only for its partition's components:
   - Max 3 files per component, max 200 lines per file
   - Prioritize: entry points first, then name-matching files, then largest files
   - Skip test files and vendor/third-party files
   - Use the `files` array from the component; if empty, check `path`

2. **Produces `ai_enhance` for every component** in its partition. See
   RESOURCES.md for the full schema. Key fields:

   **Existing fields** (fill only if empty/null):
   - `description`: 1-2 sentence description
   - `docs.purpose`: concise purpose statement
   - `docs.key_decisions`: architectural decisions visible in the code
   - `docs.patterns`: verify and supplement detected patterns

   **Required `ai_enhance` fields** (always populate):
   - `help_text` (string): 3-5 sentence explanation for help tooltip
   - `data_handled` (string): what data flows through this component
   - `criticality` ("critical"|"important"|"supporting"): use digest calibration

   **Strongly recommended fields** (populate when determinable, null otherwise):
   - `architectural_role` (string|null): from vocabulary in RESOURCES.md, or null
   - `testing_assessment` (string|null): evaluate when `testing` data exists

   **Context-dependent fields** (populate when relevant data exists):
   - `actions_summary`, `key_user_flows`: when `actions` array exists
   - `testing_gaps`, `testing_maturity`: when `testing` data exists
   - `external_services_assessment`: when `external_services` exists
   - `port_assessment`: when `port` is set
   - `complexity_assessment`: when >5000 lines or >20 files
   - `tech_context`: when `language`/`framework` are set

   **Enhancement metadata** (always set):
   - `ai_enhanced_at`: current ISO timestamp
   - `ai_enhance_version`: 2

3. **Produces `ai_enhance` for every relationship** assigned to it. See
   RESOURCES.md for the full schema. For cross-partition relationships (where the
   target is in a different partition), scope enhancement to source-observable data.
   `data_flow_description` and `importance` are accurate from the source side.
   Fields like `payload_examples` and `error_handling` describe what the source
   code reveals, without hallucinating target-side behavior.

   Also fill empty base relationship fields where detectable:
   - `label`, `authentication`, `data_format`, `api_style`, `endpoints`,
     `middleware`, `transport`, `connection_pattern`

4. **Discovers missing relationships** (marked with `ai_enhance.ai_discovered: true`):
   - HTTP calls inferred from URL construction or API client usage
   - Database connections inferred from ORM configuration
   - Message queue connections from producer/consumer patterns
   - Shared state through Redis, caches, or shared file systems
   - WebSocket connections, gRPC services

5. **Produces `local_observations`**: a list of observations about things the
   subagent noticed while reading source code. Categories: `missing_relationship`,
   `misclassified_component`, `naming_issue`, `structural_suggestion`,
   `detection_gap`, `data_quality`.

6. **Writes output** to `enhancement/result-{n}.json`

### Subagent output format

Each `result-{n}.json` contains:

```json
{
  "partition_id": 0,
  "components": {
    "<component-id>": {
      "help_text": "...",
      "architectural_role": "...",
      "data_handled": "...",
      "criticality": "...",
      "ai_enhanced_at": "...",
      "ai_enhance_version": 2
    }
  },
  "component_fields": {
    "<component-id>": {
      "description": "...",
      "docs": { "purpose": "...", "key_decisions": [...], "patterns": [...] }
    }
  },
  "relationships": {
    "<source>|<target>|<type>": {
      "data_flow_description": "...",
      "importance": "...",
      "ai_enhanced_at": "..."
    }
  },
  "relationship_fields": {
    "<source>|<target>|<type>": {
      "label": "...",
      "authentication": "..."
    }
  },
  "discovered_relationships": [
    {
      "source": "...", "target": "...", "type": "...",
      "label": "...",
      "ai_enhance": { "ai_discovered": true, "data_flow_description": "...", "importance": "..." }
    }
  ],
  "local_observations": [
    { "category": "...", "component_id": "...", "description": "...", "suggestion": "...", "confidence": "..." }
  ]
}
```

### Parallelism strategy

- Launch subagents using the Task tool with `subagent_type: "general-purpose"`
- Launch up to 5 concurrent subagents (conservative default)
- Use a task-queue model: maintain N concurrent slots, start next partition as
  each completes. This eliminates "waiting for slowest agent in batch."
- For single-partition codebases (<25 components), skip parallelism entirely
  and run one subagent

### Coverage requirement

**Every component at every nesting level must receive `ai_enhance` data.** This
includes top-level components, tab containers, tabs, screens, and sub-modules at
any depth under `children`. If a component has no source files to read, still
provide `ai_enhance` based on its name, type, and position in the hierarchy.

## Phase 4: Assemble (Single Agent, Mandatory)

Phase 4 is a **mandatory agent pass**, not an optional merge. It ensures the
output reads as if one expert wrote it.

### 4a. Schema validation (Python)

Before the agent pass, validate each `result-{n}.json`:

```bash
python3 scripts/score-ai-enhancement-quality.py \
  --partitions-dir enhancement/
```

This checks:
- Every component ID in the partition has an `ai_enhance` block
- Every assigned relationship has an `ai_enhance` block
- All enum fields use valid values
- `ai_enhanced_at` is a valid ISO timestamp
- No unexpected keys

Partitions that fail validation are re-queued for Phase 3 retry (up to 3 attempts).

### 4b. Quantitative quality scoring (Python)

The quality scoring script also computes per-partition metrics:
- **Completeness**: percentage of applicable fields populated
- **Length conformance**: `help_text` must be 3-5 sentences
- **Criticality distribution**: flags uniform distributions as suspicious
- **Detail level**: average non-null optional field count

Minimum quality score: 85%. Below threshold, re-enhance that partition.

### 4c. Agent normalization pass

The assembly agent reads ALL `ai_enhance` data from all partitions (no source
code) and performs:

- **Terminology normalization**: scan all text fields for terminology variants
  not in the glossary. Produce a list of replacements.
- **Criticality calibration review**: flag components where criticality
  contradicts dependency metrics (>10 inbound marked "supporting", leaf with
  0 inbound marked "critical")
- **Role consistency**: flag suspicious role distributions (e.g., 50
  `business-logic` and 0 `data-access`)
- **Tone consistency**: flag descriptions much shorter or longer than peers
- **Observation aggregation**: merge `local_observations` from all partitions
  plus Phase 1 observations, deduplicate (if two agents flag the same missing
  relationship, merge with "high" confidence)

The agent produces `enhancement/adjustments.json` containing:
- Terminology replacements: `[{"component_id": "...", "field": "...", "old": "...", "new": "..."}]`
- Criticality overrides: `[{"component_id": "...", "old": "...", "new": "...", "reason": "..."}]`
- Aggregated observations for the root-level `ai_enhance`
- Quality flags for human review

The agent does NOT re-enhance or rewrite entire blocks. It produces targeted
adjustments that the merge step applies.

### 4d. Final merge and output

A Python script performs the actual merge:

1. Read the current `manifest.json`
2. For each `result-{n}.json`:
   - Copy `ai_enhance` onto matching components by ID
   - Fill empty component fields (`description`, `docs`) from `component_fields`
   - Copy `ai_enhance` onto matching relationships by (source, target, type) key
   - Fill empty relationship fields from `relationship_fields`
   - Append `discovered_relationships` to the relationships array
3. Apply Phase 4c adjustments (terminology replacements, criticality overrides)
4. Set root-level `ai_enhance` from Phase 1 output, adding aggregated observations
5. Validate 100% coverage
6. Run the quality scoring script on the final output
7. Write the final `manifest.json`

```bash
python3 scripts/score-ai-enhancement-quality.py \
  --architecture viewer/public/architecture/manifest.json
```

### Failure handling

- **Per-partition retry**: up to 3 attempts with the same partition context
- **Schema validation before assembly**: catches structural problems early
- **Graceful degradation**: if some partitions fail permanently, the final output
  is still valid. Those partitions simply have no `ai_enhance`. The viewer handles
  this (all `ai_enhance?.` optional chaining). Report coverage:
  "Enhanced 230/256 components (89.8%). 26 components in 2 failed partitions
  have no AI data."
- **Progress reporting**: "Phase 3: Enhanced 12/18 partitions (67%). Running:
  partitions 13-17."

## Step 5: Validate

Verify the output is valid and loadable:

```bash
python3 -c "
import json
d = json.load(open('viewer/public/architecture/manifest.json'))
print(f'OK: {len(d[\"components\"])} components, {len(d[\"relationships\"])} relationships')
"
```

Then run the full quality scoring:

```bash
python3 scripts/score-ai-enhancement-quality.py \
  --architecture viewer/public/architecture/manifest.json
```

If any components are missing `ai_enhance` or quality is below threshold, go back
to Phase 3 for the affected partitions before proceeding.

## Step 6: Build and Deploy

After the enhanced JSON is validated, build locally and deploy to production.

### 6a. Build locally for validation

```bash
cd viewer && npm run build
```

If the build fails, fix the issue before proceeding.

### 6b. Start local preview

```bash
cd viewer && npx vite preview --port 4173
```

Do NOT tell the user the preview is ready yet. Run validation first.

### 6c. Validate the preview

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

### 6d. Determine deployment target

Get the target codebase's GitHub remote:

```bash
cd <codebase-path> && git remote get-url origin
```

Extract `owner/repo` from the URL (handles both HTTPS and SSH formats).

Read `DEPLOYMENTS.md` and find the row
matching the GitHub repo. Extract the deployment URL.

If no matching installation is found, tell the user and skip deployment.

### 6e. Deploy

Copy the enhanced architecture output to the target codebase and push:

```bash
# For split mode, copy the entire architecture directory
cp -r viewer/public/architecture \
  <codebase-path>/architecture
cd <codebase-path>
git add architecture/
git commit -m "Update AI-enhanced architecture visualization"
git push
```

The push to main automatically triggers the Architecture Visualization and Live
Monitor workflows. These workflows run the analyzer fresh but include a "Preserve
AI Enhancements" step that merges `ai_enhance` data from the committed baseline
back into the fresh analysis output.

If the current branch is not main, warn the user that deployment to production
only triggers on push to main.

### 6f. Monitor deployment

Wait 15 seconds, then check the workflow status:

```bash
gh run list -R <owner/repo> -w "Architecture Visualization" --limit 1
```

If the run is still in progress, wait 30 seconds and check again (up to 3 times).

### 6g. Report results

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

### 6h. Live monitoring note

Check `DEPLOYMENTS.md` for the target repo's live monitoring mode. If live
monitoring is enabled, inform the user:

```
Live monitoring: The enhanced JSON will propagate through the Live Monitor
workflow automatically on this push. The live dashboard will reflect AI
enhancements within 15-90 seconds (Cloudflare mode) or 10-20 minutes
(GitHub mode).
```

## Cleanup

After successful assembly and validation, delete the `enhancement/` working
directory. Only the final `manifest.json` (and detail files) persist.

## Key Rules

1. NEVER remove or alter data produced by the static analyzer
2. Only ADD to existing fields (fill empty descriptions) or add `ai_enhance` sub-objects
3. Every description must be written for an architectural reviewer who has never seen the code
4. Keep `help_text` concise but complete (3-5 sentences max)
5. Mark all AI-discovered relationships with `ai_enhance.ai_discovered: true`
6. Use the exact `architectural_role` vocabulary from RESOURCES.md
7. Use the terminology glossary from the digest. Do not introduce synonyms.
8. Validate the JSON is parseable before declaring success
9. When filling `docs.purpose` or `description`, do not overwrite non-empty values
10. The final output MUST include a local preview URL and, if deployed, the production URL and deployment status
11. ALWAYS run the quality scoring script after assembly. Never declare success until all validation checks pass.
12. Phase 4 (Assemble) is MANDATORY. Never skip the normalization pass, even for single-partition codebases.

## Schema Reference

See [RESOURCES.md](RESOURCES.md) for the full schema of `ai_enhance` fields,
valid vocabulary values, terminology glossary template, criticality calibration
guidance, and few-shot quality examples.
