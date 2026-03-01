---
name: ai-assist
description: Analyze a codebase, enhance the results with AI, and deploy the interactive architecture viewer
---

# /ai-assist - Architecture Enhancement Skill

Analyze a codebase with solution-explorer, enhance the results with AI-generated
descriptions and annotations, and deploy the interactive architecture viewer.

## Usage

```
/ai-assist <path-to-codebase>
/ai-assist <path-to-codebase> --update
```

- `path-to-codebase`: absolute path to the project/repo to analyze
- `--update`: skip re-analysis, enhance only new/changed components (see Step 1b)

## Workflow

### Step 1: Run the analyzer

Run the static analyzer on the target codebase. Output directly to the viewer's
public directory so it will be served by the local site:

```bash
python3 /Users/ramerman/dev/solution-explorer/analyze.py <codebase-path> \
  -o /Users/ramerman/dev/solution-explorer/viewer/public/architecture.json --pretty
```

> `analyze.py` is a thin CLI wrapper around the `analyzer/` package. The command works identically.

If `viewer/public/architecture.json` already exists from a previous run, ask the
user whether to re-analyze from scratch or enhance the existing file.

### Step 1b: Update mode (when --update is specified)

When `--update` is provided, skip the analyzer run entirely. The JSON must already
exist at `viewer/public/architecture.json`.

1. Read the existing architecture JSON.
2. Determine the "core update set" of components that need re-enhancement:
   - Components with no `ai_enhance` at all (newly added, never enhanced)
   - Components where `ai_enhance.ai_enhanced_at` is older than the architecture's
     `generated_at` timestamp (stale after re-analysis)
   - Components listed in the most recent `changelog` entries as `component_added`
     or `component_modified`
3. Expand the update set to include **direct neighbors**: any component connected to
   a core update set member via a relationship (source or target). This catches
   ripple effects where a change in one component affects how its neighbors should
   be described.
4. Report scope to user: "Update mode: N core + M neighbor components to re-enhance
   out of T total."
5. Proceed to Step 2, but only read source files for the expanded update set.
6. Proceed to Step 3, but only modify `ai_enhance` for the expanded update set.
   Preserve existing `ai_enhance` data on all other components untouched.
7. Always regenerate architecture-level `ai_enhance` (Step 3c) since the overall
   narrative may have shifted.

Then continue to Steps 4-6 as normal.

### Step 2: Load and understand the architecture

Read the resulting JSON. Process EVERY component at ALL levels of nesting:

1. Walk the `components` array recursively: each component may have a `children`
   array containing nested components (tabs, screens, sub-modules). Every single
   component at every depth must be processed.
2. For each component, locate its source files:
   - Use the `files` array (pick 2-3 most important: entry points first, then main
     files, then others)
   - If `files` is empty, check `path`: if it points to a file (has an extension like
     `.swift`, `.ts`, `.py`), read that file directly
   - If `path` is a directory, look for README, main/index files in that directory
3. Read the selected source files and understand what each component does
   architecturally
4. Note any relationships the static analyzer may have missed
5. For each component, also examine the analyzer's structured data:
   - `actions` array: count UI actions by type (buttons, gestures, forms, etc.),
     identify the key user flows they represent
   - `testing` object: note test_files, unit/integration/e2e counts, coverage %,
     frameworks. Assess testing maturity and identify gaps.
   - `external_services` array: understand third-party dependencies and whether
     any are on the critical path
   - `port` field: understand what network service this component exposes
   - `entry_points` array: understand how the component is invoked
   - `metrics` object: note component size (lines, files, symbols) for complexity
     assessment
   - `language` and `framework` fields: understand the technology choices
6. At the architecture level, examine:
   - `changelog` array: understand recent evolution (components added, removed,
     modified) to summarize architectural trends
   - `stats`: aggregate language and size data for cross-cutting summaries

### Step 3: Enhance the JSON

Load the JSON as a Python dict, then enhance each section as described below.
Use a Python script or inline edits to modify the dict and write it back.

#### 3a. Component enhancements

For every component (recursively through children), add or fill:

**Coverage requirement:** Every component at every nesting level must receive
`ai_enhance` data. This includes top-level components, tab containers, tabs,
screens, and sub-modules at any depth under `children`. If a component has no
source files to read, still provide `ai_enhance` based on its name, type, and
position in the hierarchy.

**Existing fields** (fill only if empty/null):
- `description`: 1-2 sentence description of what this component does and why it exists.
  Written for someone who has never seen the codebase.
- `docs.purpose`: concise purpose statement if empty.
- `docs.key_decisions`: architectural decisions visible in the code (e.g., "Uses WebSocket
  for real-time updates instead of polling").
- `docs.patterns`: verify and supplement detected patterns.

**New `ai_enhance` sub-object** (add to each component):

Core fields:
- `help_text` (string): 3-5 sentence explanation for a help tooltip. Cover what it is,
  what it depends on, and what depends on it. Written for someone reviewing the architecture.
- `architectural_role` (string|null): one value from the vocabulary in RESOURCES.md, or null.
- `data_handled` (string): brief description of what data flows through this component.
- `criticality` ("critical"|"important"|"supporting"): critical means the system fails
  without it, important means degraded behavior, supporting means convenience or tooling.
- `testing_assessment` (string|null): 1-2 sentence evaluation of test quality when
  `testing` data exists. Consider coverage %, test type distribution, and likely gaps.

UI actions analysis (populate when `actions` array exists on the component):
- `actions_summary` (string|null): 1-2 sentence summary of the user interactions
  available. Group by type (buttons, gestures, forms, etc.) and call out destructive
  or critical actions. Null if no actions exist.
- `key_user_flows` (string[]|null): 2-5 key user flows this component enables,
  written as user-facing descriptions (e.g., "Submit payment form", "Navigate to
  settings"). Null if no actions exist.

Deeper testing insight (populate when `testing` data exists):
- `testing_gaps` (string[]|null): 1-3 specific gaps in test coverage. Consider:
  missing test types (e.g., no integration tests for an API component), low coverage
  areas, critical paths without tests. Null if testing data absent or comprehensive.
- `testing_maturity` ("comprehensive"|"adequate"|"minimal"|"untested"|null):
  See RESOURCES.md for thresholds. Null if no testing data exists.

Context fields (populate when the relevant source data exists):
- `external_services_assessment` (string|null): When `external_services` exists,
  describe the dependencies and whether any are on the critical path.
- `port_assessment` (string|null): When `port` is set, explain what this port is
  used for in the architecture context.
- `complexity_assessment` (string|null): When the component has significant
  `metrics` (>5000 lines or >20 files), provide a brief assessment of complexity
  and whether decomposition might be warranted. Null for small components.
- `tech_context` (string|null): When `language` and/or `framework` are set,
  describe how this component's technology choices fit the broader architecture.

Enhancement metadata (always set):
- `ai_enhanced_at`: current ISO timestamp (e.g., "2026-03-01T12:00:00Z").
- `ai_enhance_version`: set to 2.

#### 3b. Relationship enhancements

For every existing relationship:

**Existing fields** (fill only if empty/null):
- `label`: what flows across this connection (e.g., "REST API calls for user management").
- `authentication`: auth mechanism if detectable ("jwt", "oauth2", "api_key", "mtls", "basic", "session").
- `data_format`: serialization format ("json", "protobuf", "graphql", "xml", "binary").
- `api_style`: API paradigm ("rest", "graphql", "grpc", "websocket", "soap", "rpc").
- `endpoints`: list of `{"method": "GET", "path": "/users"}` for specific API endpoints used.
- `middleware`: middleware layers in the request path (e.g., ["rate_limit", "cors", "auth"]).
- `transport`: underlying transport protocol ("http/2", "tcp", "udp", "amqp").
- `connection_pattern`: connection management ("connection_pool", "orm", "per_request", "singleton").

**New `ai_enhance` sub-object**:
- `data_flow_description` (string): 1 sentence describing what data flows and in which direction.
- `importance` ("primary"|"secondary"|"internal"): primary = core data path,
  secondary = used but not critical, internal = implementation detail.
- `authentication_detail` (string|null): prose explanation of the auth flow.
- `payload_examples` (string[]|null): 2-3 example payload descriptions.
- `error_handling` (string|null): how errors are handled on this connection.
- `sla_notes` (string|null): latency expectations, rate limits, timeouts.
- `security_notes` (string|null): encryption, certificate pinning, network policies.
- `port_context` (string|null): When the relationship has a `port`, explain what
  service listens there and how the connection is managed.
- `ai_enhanced_at`: current ISO timestamp.

**Discover missing relationships**: Look for connections the static analyzer missed:
- HTTP calls inferred from URL construction or API client usage
- Database connections inferred from ORM configuration
- Message queue connections from producer/consumer patterns
- Shared state through Redis, caches, or shared file systems
- WebSocket connections for real-time features
- gRPC services between microservices

Add new relationships to the `relationships` array. Mark them with:
```json
"ai_enhance": { "ai_discovered": true, "data_flow_description": "...", "importance": "..." }
```

#### 3c. Top-level enhancements

Add to the root Architecture object:

```json
"ai_enhance": {
  "summary": "3-5 sentence executive summary of the entire system.",
  "data_flow_narrative": "A paragraph describing how a typical user request flows through the system.",
  "component_groups": [
    { "name": "Client Layer", "component_ids": ["ios-app", "web-app"] },
    { "name": "API Layer", "component_ids": ["api-server"] },
    { "name": "Data Layer", "component_ids": ["postgres", "redis"] }
  ],
  "recent_changes_summary": "2-3 sentence summary when changelog exists.",
  "tech_diversity": "1-2 sentence summary of the technology mix.",
  "test_health_summary": "1-2 sentence overview of testing across the codebase.",
  "observations": [],
  "ai_enhanced_at": "2026-03-01T12:00:00Z",
  "ai_enhance_version": 2
}
```

**Changelog interpretation:** When the architecture has a `changelog` array, read
the recent entries and summarize the architectural evolution in `recent_changes_summary`.
What components were added or removed? What trend do the changes suggest?

**Cross-cutting summaries:**
- `tech_diversity`: Aggregate from `stats.languages` and component `language` fields.
  Describe the technology mix and what it means architecturally.
- `test_health_summary`: Aggregate from component `testing` data. What percentage of
  components have tests? Where are the biggest gaps?

**Observations:** After enhancing all components and relationships, compile a list of
observations about potential improvements to the automated analysis. Each observation
should include a `category`, `description`, optional `component_id`, optional `suggestion`,
and `confidence` level. See RESOURCES.md for valid categories and guidelines.

Focus observations on things that would genuinely improve the analyzer output: missing
relationships that the analyzer should detect, components that are misclassified,
names that are misleading, or patterns the analyzer doesn't handle yet. Aim for 3-10
high-quality observations rather than exhaustive lists.

### Step 4: Write the enhanced JSON

Write the enhanced JSON back to the viewer's public directory:

```python
import json

output_path = "/Users/ramerman/dev/solution-explorer/viewer/public/architecture.json"
with open(output_path, 'w') as f:
    json.dump(enhanced_data, f, indent=2, ensure_ascii=False)
```

### Step 5: Validate

Verify the output is valid and loadable:

```bash
python3 -c "import json; d=json.load(open('/Users/ramerman/dev/solution-explorer/viewer/public/architecture.json')); print(f'OK: {len(d[\"components\"])} components, {len(d[\"relationships\"])} relationships')"
```

Then verify 100% AI enhancement coverage and metadata:

```bash
python3 -c "
import json

def check(components):
    missing, stale, total = [], [], 0
    for c in components:
        total += 1
        ai = c.get('ai_enhance')
        if not ai:
            missing.append(c.get('id', 'unknown'))
        elif not ai.get('ai_enhanced_at'):
            stale.append(c.get('id', 'unknown'))
        m, s, t = check(c.get('children', []))
        missing.extend(m)
        stale.extend(s)
        total += t
    return missing, stale, total

d = json.load(open('/Users/ramerman/dev/solution-explorer/viewer/public/architecture.json'))
missing, stale, total = check(d['components'])
obs = len(d.get('ai_enhance', {}).get('observations', []))
version = d.get('ai_enhance', {}).get('ai_enhance_version', 'not set')

if missing:
    print(f'INCOMPLETE: {len(missing)}/{total} components missing ai_enhance:')
    for m in missing: print(f'  - {m}')
else:
    print(f'OK: all {total} components have ai_enhance data')
if stale:
    print(f'WARNING: {len(stale)} components missing ai_enhanced_at timestamp')
print(f'Schema version: {version}')
print(f'Observations: {obs}')
"
```

If any components are missing `ai_enhance`, go back to Step 3 and enhance them
before proceeding to Step 6.

### Step 6: Build and deploy

After the enhanced JSON is validated, build locally and deploy to production.

#### 6a. Build locally for validation

Build the viewer to verify the enhanced JSON renders correctly:

```bash
cd /Users/ramerman/dev/solution-explorer/viewer && npm run build
```

If the build fails, fix the issue before proceeding.

#### 6b. Start local preview

Start the local preview server in the background for immediate review:

```bash
cd /Users/ramerman/dev/solution-explorer/viewer && npx vite preview --port 4173
```

Do NOT tell the user the preview is ready yet. Run validation first.

#### 6c. Validate the preview

After the preview server is running, validate that the viewer is serving correctly:

```bash
sleep 2 && bash /Users/ramerman/dev/solution-explorer/scripts/validate-preview.sh http://localhost:4173
```

This script verifies:
- `architecture.json` is valid JSON with expected structure
- The built `dist/` has the expected files
- The preview server returns HTML for the index page
- The preview server returns valid JSON for `/architecture.json`
- Non-existent JSON paths are not misidentified as JSON (SPA fallback guard)

**If validation fails, do NOT tell the user the preview is ready.** Instead, read the
failure output, diagnose the issue, fix it, rebuild, and re-run validation. Only
proceed to deployment (or report the preview URL) after all checks pass.

Once validation passes, tell the user:

```
Local preview is ready at: http://localhost:4173/
```

#### 6d. Determine deployment target

Get the target codebase's GitHub remote:

```bash
cd <codebase-path> && git remote get-url origin
```

Extract `owner/repo` from the URL (handles both HTTPS `https://github.com/owner/repo.git`
and SSH `git@github.com:owner/repo.git` formats).

Read `/Users/ramerman/dev/solution-explorer/DEPLOYMENTS.md` and find the row matching
the GitHub repo. Extract the deployment URL.

If no matching installation is found in DEPLOYMENTS.md, tell the user and skip
deployment. The local preview URL is the final output.

#### 6e. Deploy

Copy the enhanced JSON to the target codebase and push:

```bash
cp /Users/ramerman/dev/solution-explorer/viewer/public/architecture.json \
  <codebase-path>/architecture.json
cd <codebase-path>
git add architecture.json
git commit -m "Update AI-enhanced architecture visualization"
git push
```

The push to main automatically triggers the Architecture Visualization and Live
Monitor workflows. These workflows run the analyzer fresh but include a
"Preserve AI Enhancements" step that merges `ai_enhance` data from the committed
`architecture.json` (or cached baseline) back into the fresh analysis output. This
ensures all AI enhancements survive through CI-triggered re-analysis.

If the current branch is not main, warn the user that deployment to production
only triggers on push to main.

#### 6f. Monitor deployment

Wait 15 seconds, then check the workflow status:

```bash
gh run list -R <owner/repo> -w "Architecture Visualization" --limit 1
```

If the run is still in progress, wait 30 seconds and check again (up to 3 times).

#### 6g. Report results

Output both URLs:

```
Architecture viewer ready:
  Local preview:  http://localhost:4173/
  Production:     <deployment-url> (deploying...)
```

Once the workflow completes, update the status:

```
Deployment complete:
  Production: <deployment-url>
```

#### 6h. Live monitoring note

Check `DEPLOYMENTS.md` for the target repo's live monitoring mode. If it has live monitoring
enabled (any mode), inform the user:

```
Live monitoring: The enhanced JSON will propagate through the Live Monitor workflow
automatically on this push. The live dashboard will reflect AI enhancements within
15-90 seconds (Cloudflare mode) or 10-20 minutes (GitHub mode).
```

No additional action is needed. The `live-monitor.yml` workflow triggers on push to main
alongside the `Architecture Visualization` workflow, and both use the same committed
`architecture.json` as their input.

## Key Rules

1. NEVER remove or alter data produced by the static analyzer
2. Only ADD to existing fields (fill empty descriptions) or add `ai_enhance` sub-objects
3. Every description must be written for an architectural reviewer who has never seen the code
4. Keep `help_text` concise but complete (3-5 sentences max)
5. Mark all AI-discovered relationships with `ai_enhance.ai_discovered: true`
6. Use the exact `architectural_role` vocabulary from RESOURCES.md
7. Validate the JSON is parseable before declaring success
8. When filling `docs.purpose` or `description`, do not overwrite non-empty values
9. The final output MUST include a local preview URL and, if deployed, the production URL and deployment status
10. ALWAYS run the validation script (Step 6c) after building and starting the preview. Never tell the user the preview is ready until all validation checks pass.

## Schema Reference

See [RESOURCES.md](RESOURCES.md) for the full schema of `ai_enhance` fields and valid vocabulary values.
