---
name: ai-assist
description: Analyze a codebase, enhance the results with AI, and serve an interactive architecture viewer locally
---

# /ai-assist - Architecture Enhancement Skill

Analyze a codebase with solution-explorer, enhance the results with AI-generated
descriptions and annotations, and launch a local interactive viewer.

## Usage

```
/ai-assist <path-to-codebase>
```

- `path-to-codebase`: absolute path to the project/repo to analyze

## Workflow

### Step 1: Run the analyzer

Run the static analyzer on the target codebase. Output directly to the viewer's
public directory so it will be served by the local site:

```bash
python3 /Users/ramerman/dev/solution-explorer/analyze.py <codebase-path> \
  -o /Users/ramerman/dev/solution-explorer/viewer/public/architecture.json --pretty
```

If `viewer/public/architecture.json` already exists from a previous run, ask the
user whether to re-analyze from scratch or enhance the existing file.

### Step 2: Load and understand the architecture

Read the resulting JSON. For each top-level component and its children:

1. Read 2-3 of its most important source files (entry points first, then README, then main files)
2. Understand what the component does architecturally
3. Note any relationships the static analyzer may have missed

### Step 3: Enhance the JSON

Load the JSON as a Python dict, then enhance each section as described below.
Use a Python script or inline edits to modify the dict and write it back.

#### 3a. Component enhancements

For every component (recursively through children), add or fill:

**Existing fields** (fill only if empty/null):
- `description`: 1-2 sentence description of what this component does and why it exists.
  Written for someone who has never seen the codebase.
- `docs.purpose`: concise purpose statement if empty.
- `docs.key_decisions`: architectural decisions visible in the code (e.g., "Uses WebSocket
  for real-time updates instead of polling").
- `docs.patterns`: verify and supplement detected patterns.

**New `ai_enhance` sub-object** (add to each component):
- `help_text` (string): 3-5 sentence explanation for a help tooltip. Cover what it is,
  what it depends on, and what depends on it. Written for someone reviewing the architecture.
- `architectural_role` (string|null): one value from the vocabulary in RESOURCES.md, or null.
- `data_handled` (string): brief description of what data flows through this component.
- `criticality` ("critical"|"important"|"supporting"): critical means the system fails
  without it, important means degraded behavior, supporting means convenience or tooling.

#### 3b. Relationship enhancements

For every existing relationship:

**Existing fields** (fill only if empty/null):
- `label`: what flows across this connection (e.g., "REST API calls for user management").

**New `ai_enhance` sub-object**:
- `data_flow_description` (string): 1 sentence describing what data flows and in which direction.
- `importance` ("primary"|"secondary"|"internal"): primary = core data path,
  secondary = used but not critical, internal = implementation detail.

**Discover missing relationships**: Look for connections the static analyzer missed:
- HTTP calls inferred from URL construction or API client usage
- Database connections inferred from ORM configuration
- Message queue connections from producer/consumer patterns
- Shared state through Redis, caches, or shared file systems

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
  ]
}
```

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

### Step 6: Build and serve locally

Build the viewer and start the local preview server:

```bash
cd /Users/ramerman/dev/solution-explorer/viewer && npm run build
```

Then start the local server:

```bash
cd /Users/ramerman/dev/solution-explorer/viewer && npx vite preview --port 4173
```

Run the preview server in the background. Once it starts, output the local URL
to the user as the final message:

```
Architecture viewer is ready at: http://localhost:4173/
```

This is the final output of the skill. The user should be able to open that URL
and explore the full AI-enhanced architecture diagram.

## Key Rules

1. NEVER remove or alter data produced by the static analyzer
2. Only ADD to existing fields (fill empty descriptions) or add `ai_enhance` sub-objects
3. Every description must be written for an architectural reviewer who has never seen the code
4. Keep `help_text` concise but complete (3-5 sentences max)
5. Mark all AI-discovered relationships with `ai_enhance.ai_discovered: true`
6. Use the exact `architectural_role` vocabulary from RESOURCES.md
7. Validate the JSON is parseable before declaring success
8. When filling `docs.purpose` or `description`, do not overwrite non-empty values
9. The final output MUST be a local URL the user can open in their browser

## Schema Reference

See [RESOURCES.md](RESOURCES.md) for the full schema of `ai_enhance` fields and valid vocabulary values.
