# AI Enhancement at Scale: Investigation & Architectural Research

## Context

The `/ai-assist` skill enhances static analysis output with AI-generated descriptions,
roles, criticality assessments, and help text. On the UnaMentis codebase (256 components,
168 relationships, 1.1M lines of code), the enhancement step exceeds what a single agent
pass can produce. This document captures the investigation findings and research into
scalable patterns, to inform the actual implementation plan.

**Primary requirement:** The absolute highest quality architectural representation in
the JSON that can possibly be assembled from a codebase. Not just correct parsing of
individual code, but the ability to detect and document architecture at a high level,
understand the entire codebase holistically, and produce descriptions so good that both
humans viewing the architecture and AI agents consuming the JSON can do the highest
quality work possible. Quality must be uniform whether the codebase is 500 lines or
4 million.

---

## Part 1: Current State Assessment

### What We Already Have (Good News)

**The static analysis already scales.** The analyzer supports two output modes:

1. **Split mode** (`--split` flag): Produces `manifest.json` + per-component
   `detail-{id}.json` files in an `architecture/` directory. The manifest contains the
   full component tree, all relationships, stats, and AI enhancement data. Detail files
   contain only symbols and files, loaded lazily by the viewer on demand.

2. **Monolithic mode** (default): Single `architecture.json` with everything.

The viewer auto-detects which format is present and handles both. Split mode keeps
initial page load to 20-100KB vs 5.9MB+ for monolithic. This is already implemented,
tested, and working. See [cli.py](analyzer/cli.py) lines 58-60 for the `--split` flag
and line 275 for `write_split()`.

**Key files for the split format:**
- [analyzer/cli.py](analyzer/cli.py): `write_split()` at line 275
- [viewer/src/App.tsx](viewer/src/App.tsx): dual-mode loading (manifest first, fallback to monolithic)
- [viewer/src/store.ts](viewer/src/store.ts): `loadComponentDetail()` for lazy loading
- [tests/test_cli.py](tests/test_cli.py): split format test coverage

### What Doesn't Scale (The Real Problem)

**The AI enhancement pipeline is completely monolithic.** The entire
[SKILL.md](.claude/skills/ai-assist/SKILL.md) workflow operates as:

1. One agent reads ALL source files for ALL components (Step 2)
2. One agent enhances ALL components and ALL relationships in a single pass (Step 3)
3. One agent writes the entire enhanced JSON as one output (Step 4)

There is no batching, no chunking, no multi-pass strategy. The skill was designed
assuming codebases would have fewer than ~50-80 components.

**Specific bottlenecks:**
- Each component's `ai_enhance` needs ~200 tokens of structured output
- Each relationship needs ~100 tokens
- 256 components + 168 relationships = ~68,000 tokens of structured output minimum
- Plus the agent needs source code context (~50-200 lines per component)
- Single agent output limits hit around 50-80 components

### What We Also Have (Supporting Infrastructure)

- **Merge script** ([scripts/merge-ai-enhancements.py](scripts/merge-ai-enhancements.py)):
  Restores `ai_enhance` data from a baseline into fresh analysis output. Uses component
  ID matching and (source, target, type) tuple matching for relationships.
- **Preservation validation** ([scripts/validate-ai-preservation.py](scripts/validate-ai-preservation.py)):
  Verifies AI data survives the CI merge pipeline.
- **Update mode** (`--update` flag): Identifies components needing re-enhancement
  (new, stale, or changed) plus their neighbors. But this still tries to do all
  enhancement in one pass.
- **CI integration**: Both `architecture-viz.yml` and `live-monitor.yml` workflows
  automatically run the merge script to preserve AI enhancements through re-analysis.

### Known Gap in Merge Script

The merge script (`merge-ai-enhancements.py`) silently drops AI-discovered
relationships. When the static analyzer runs fresh, AI-discovered relationships are not
in the fresh output. The merge script only copies `ai_enhance` onto relationships that
exist in BOTH baseline and target. AI-discovered relationships that exist only in the
baseline are lost. The validation script treats this as a warning, not an error, but
the data is still gone.

**Required fix:** After the relationship merge loop (line 73), append baseline
relationships with `ai_enhance.ai_discovered == True` to the target's relationship
list, provided no duplicate (source, target, type) tuple already exists.

---

## Part 2: Research Findings

### Pattern 1: LLM Map-Reduce

**Source:** [Agentic Patterns: LLM Map-Reduce](https://agentic-patterns.com/patterns/llm-map-reduce-pattern/), [LLMxMapReduce (Tsinghua)](https://github.com/thunlp/LLMxMapReduce)

The classic Map-Reduce pattern adapted for LLMs:
- **Map phase**: Isolated agents each process one chunk independently, producing
  constrained structured output
- **Collapse phase**: Mapped results are grouped and summarized
- **Reduce phase**: Aggregation produces the final answer, resolving inter-chunk
  dependencies and conflicts

**Relevance to our problem:** Strong for the parallel enhancement of individual
components. Weak for cross-component context, since the pure map phase is isolated
and loses the "whole system" understanding.

**Key insight from the research:** Inter-chunk dependency (evidence spread across
chunks that relies on each other) and inter-chunk conflict (contradictory evidence)
are the two main failure modes. A "structured information protocol" is needed to
handle inter-chunk dependencies.

### Pattern 2: Hierarchical Summarization

**Source:** [Hierarchical Repository-Level Code Summarization](https://arxiv.org/html/2501.07857v1), [Code-Craft](https://arxiv.org/html/2504.08975v1)

Bottom-up summarization through the code hierarchy:
- Parse into segments (functions, files, packages)
- Summarize each segment independently
- Aggregate summaries upward: segment to file to package to repository
- Each level incorporates domain context through prompts
- Two algorithms: sequential DFS-based and parallel level-based

**Relevance:** The level-based approach is directly applicable. Process leaf components
first, propagate summaries up through the tree. But our problem requires top-down
context (understanding the whole system) before enhancing individual components, which
is the opposite direction.

**Key insight:** Context propagation works in both directions. Bottom-up gives you
detail aggregation. Top-down gives you architectural framing. The optimal approach
combines both.

### Pattern 3: Claude Code Subagents (Task Tool)

**Source:** [Claude Code Docs](https://code.claude.com/docs/en/agent-teams), already available in our toolchain

Subagents run within a single session:
- Each gets its own context window
- Results return to the main agent
- Cannot communicate with each other
- Lower token cost than agent teams
- Good for focused tasks where only the result matters

**Relevance:** High. This is the mechanism we should use. The main agent acts as
orchestrator, spawning subagents for enhancement work. Each subagent receives
the architectural digest as context plus its assigned partition's source code.

### Pattern 4: Claude Code Agent Teams (Experimental)

**Source:** [Agent Teams Docs](https://code.claude.com/docs/en/agent-teams)

Full multi-agent coordination:
- Teammates can message each other directly
- Shared task list with self-coordination
- Each teammate is a full Claude Code session
- Higher token cost, more coordination overhead

**Relevance:** Overkill for this problem. Enhancement is inherently a "fan-out then
merge" pattern, not a collaborative discussion. Subagents are sufficient and more
efficient.

### Pattern 5: The Architectural Digest Pattern (Novel Synthesis)

This is the pattern I believe fits our problem best, synthesized from the research:

**Core insight:** The top-down context requirement and the parallelization requirement
seem contradictory, but they aren't. The full architecture tree is compact
(the manifest without source code is 20-100KB). Only the source code reading is heavy.
We can give every worker the full architectural picture cheaply, then have them
deep-dive into their assigned partition's source code.

---

## Part 3: Recommended Architecture

### The "Digest, Partition, Enhance, Assemble" (DPEA) Pattern

```
Phase 1: DIGEST          Phase 2: PARTITION         Phase 3: ENHANCE           Phase 4: ASSEMBLE
(single agent)           (deterministic)            (parallel subagents)       (single agent, mandatory)

Read manifest ──────> Group components ──────> [Agent A: Group 1] ──────> Merge all ai_enhance
Understand full         into logical              Read source for            Schema-validate results
  architecture          partitions                  partition only           Terminology normalization
Write structured        (by complexity weight,      Has full digest          Criticality calibration
  digest (template)       relationship affinity)      as context             Consistency review
Write architecture-     Compute dependency         Produce ai_enhance       Aggregate observations
  level ai_enhance        metrics per component       for all components     Validate 100% coverage
Write calibration       Estimate token budgets       in partition           Quality score check
  guidance              Assign relationships        Produce local            Write final JSON
                        Include neighbor              observations
                          summaries for
                          cross-partition rels      [Agent B: Group 2]
                                                   [Agent C: Group 3]
                                                   ...
```

#### Phase 1: Digest (Single Agent, Full Manifest)

The orchestrator reads the full manifest (all components, relationships, stats,
changelog, metrics, but no source code) and produces:

1. **Structured Architectural Digest**: Not free-form prose, but a template-driven
   document covering:
   - **System type**: monolith / modular monolith / microservices / client-server / etc.
   - **Deployment topology**: single binary / containerized / mobile+server / etc.
   - **Primary data flows**: numbered list (e.g., "1. User opens app, selects curriculum,
     app fetches from server via REST")
   - **Technology map**: language -> purpose (e.g., "Swift: iOS client, Python: server
     management, TypeScript: web dashboard")
   - **Critical path components**: list of component IDs on the primary user-facing path
   - **Terminology glossary**: canonical names for services, protocols, data entities,
     and domain concepts. All downstream agents must use these terms exactly.
   - **Preliminary role assignments**: table mapping each top-level component and major
     subtree root to a suggested `architectural_role` with 1-sentence rationale.
     Downstream agents can override with justification.
   - **Criticality calibration**: "In this codebase, 'critical' means X (examples:
     component A, B). 'important' means Y. 'supporting' means Z." This prevents
     agent drift where one subagent rates everything critical and another rates
     everything important.

2. **Architecture-level `ai_enhance`**: The root-level summary, data_flow_narrative,
   component_groups, tech_diversity, test_health_summary. This requires whole-system
   understanding and is cheap to produce (one object).

3. **Optional partition hints**: The agent may suggest logical groupings that the
   algorithmic partitioner can use as soft boundaries. These are advisory, not
   required.

This phase is lightweight because it only reads the manifest (20-100KB), not source
code. The full component tree with names, types, paths, metrics, relationships, and
framework info gives enough signal for an architectural overview.

**Digest input enrichment:** To provide domain context beyond structural metadata,
include any non-null `description` and `docs.purpose` fields from existing component
data. For the top 5-10 most-connected components (by relationship count), include the
first 20-30 lines of their main entry point file (~2-3K additional tokens). This gives
the digest agent enough to understand *what the system does*, not just how it is
structured.

**Digest validation:** After Phase 1, a programmatic check verifies: Does the digest
mention all top-level components? Does the technology map match `stats.languages`?
Are all major relationship types (http, websocket, database, etc.) referenced? If
validation fails, the orchestrator provides additional context and re-runs Phase 1.

**Digest self-assessment:** The prompt asks the agent to rate confidence 1-5 and list
areas where the manifest was ambiguous. Below confidence 4, the orchestrator provides
README content or additional entry point files and re-runs.

#### Phase 2: Partition (Deterministic Algorithm)

A Python script (not an AI agent) partitions the component tree using a
**relationship-aware, complexity-weighted** algorithm:

**Phase 2a: Natural boundary grouping**
1. Each top-level subtree under root that fits the complexity budget becomes its own
   partition. "Fits" is determined by estimated source token weight (from
   `metrics.lines`), targeting ~20,000-50,000 lines per partition, not a raw component
   count.
2. Oversized subtrees recurse at their child level, not at arbitrary DFS boundaries.
3. **Never split a parent from its direct children.** If a subtree must be split,
   split at the grandchild level but always include the subtree root in one partition.
4. Allow partitions as small as 5 components (for code-heavy server modules) and as
   large as 30 (for lightweight UI screens with 1 file each). Soft limits, not hard.

**Phase 2b: Affinity-based merging**
1. For undersized orphan components or singleton subtrees, assign to the partition
   containing the most of their relationship neighbors. This is a greedy bin-packing:
   for each orphan, count relationships to each existing partition, assign to the
   highest-affinity partition that still has budget.
2. This is deterministic, O(n*r) where n is components and r is relationships.

**Phase 2c: Dependency metrics computation**
For each component, compute (cheap, O(V+E) on the full graph):
- Inbound relationship count
- Outbound relationship count
- Whether it is a leaf or articulation point in the dependency graph
These metrics are included in the partition manifest so subagents can make
structurally-informed criticality assessments.

**Phase 2d: Token budget estimation**
For each partition, estimate total source code tokens from file sizes in the manifest.
If a partition exceeds 50K estimated source tokens, split it further regardless of
component count. This prevents context window overflow for partitions containing
large, code-heavy components.

**Phase 2e: Cross-partition relationship context**
For each relationship where the target is in a different partition, include a compact
summary of the target component in the source partition's manifest: name, type,
framework, metrics, and existing description if any (~50-100 tokens per relationship).
This gives the source agent enough context to describe the relationship without having
read the target's source code.

**Phase 2f: Output**
Write partition assignment files: `enhancement/partition-{n}.json` containing:
- The component IDs in this partition
- The relationship keys assigned to this partition
- File paths that need reading for this partition's components
- Per-component dependency metrics (inbound/outbound counts, articulation point flag)
- Cross-partition relationship neighbor summaries
- Estimated source token budget

**Why relationship-aware partitioning matters:** Simulation against the real UnaMentis
tree with naive DFS produced 18 partitions where 62% of relationships crossed partition
boundaries. Architecturally unrelated components were lumped together by DFS traversal
order, while important groupings (like a module and its services) were split across
partitions. Relationship-aware partitioning with affinity merging reduces cross-partition
relationships to an estimated 20-30%, keeping related components together where it
matters for enhancement quality.

#### Phase 3: Enhance (Parallel Subagents)

For each partition, spawn a subagent that receives:

1. **The Structured Digest** from Phase 1 (top-down context, terminology glossary,
   criticality calibration, preliminary role assignments)
2. **The partition manifest**: component IDs, relationship keys, dependency metrics,
   cross-partition neighbor summaries
3. **The component tree** (names and structure only, for understanding neighbors).
   For codebases above 500 components, include a contextual subset: full path from
   root to each partition component, immediate siblings/parent, and components on the
   other end of cross-partition relationships (~100-150 entries instead of the full tree)
4. **Quality rubric**: 2-3 example `ai_enhance` blocks as few-shot calibration,
   explicit constraints (help_text must be 3-5 sentences, use glossary terms only,
   justify criticality against dependency metrics)
5. **Instructions**: the enhancement schema from RESOURCES.md

Each subagent then:
1. Reads source files only for its partition's components (max 3 files per component,
   max 200 lines per file; prioritize entry points, then name-matching files, then
   largest files; skip test and vendor files)
2. Produces `ai_enhance` for every component in its partition
3. Produces `ai_enhance` for every relationship assigned to it
4. Notes any discovered relationships (marked with `ai_discovered: true`)
5. Produces a `local_observations` list: missing relationships it discovered, patterns
   it noticed, misclassifications it identified from reading source code
6. Writes output to `enhancement/result-{n}.json`

Each subagent handles a complexity-weighted partition well within the output capacity
of a single agent pass. With the digest providing whole-system context, terminology
glossary, and criticality calibration, each agent understands the forest while
deep-diving into its section of trees.

**Cross-partition relationship scoping:** For relationships where the target is in a
different partition, the subagent scopes its enhancement to source-observable data.
`data_flow_description` and `importance` are accurate from the source side. Fields like
`payload_examples` and `error_handling` describe what the source code reveals, without
hallucinating target-side behavior. The cross-partition neighbor summary provides enough
context for a useful description without requiring the agent to read the target's code.

**Context window budget (validated against real data):**

| Budget Item | Tokens (estimated) |
|---|---|
| Structured digest | ~4,000 |
| Component tree (256 comps, names-only) | ~6,200 |
| Quality rubric + enhancement instructions | ~4,000 |
| Partition manifest + dependency metrics | ~1,000 |
| Source code (25 comps * 2.5 files * 150 lines * 4 tok/line) | ~37,500 |
| **Total input** | **~52,700** |
| Output (25 comps * 290 tok + 15 rels * 115 tok) | ~9,000 |
| **Total context** | **~61,700** |

This fits comfortably in Claude's 200K context window with ~138K tokens of headroom.
For 2000-component codebases, the contextual tree subset (~150 entries) keeps the
tree portion at ~3,750 tokens instead of ~50,000.

#### Phase 4: Assemble (Single Agent, Mandatory)

Phase 4 is a **mandatory agent pass**, not an optional Python-only merge. This is
the quality normalization step that ensures the output reads as if one expert wrote it.

**Phase 4a: Schema validation (Python, pre-assembly)**

Before the agent pass, a Python validation script checks each `result-{n}.json`:
- Every component ID in the partition has an `ai_enhance` block
- Every assigned relationship has an `ai_enhance` block
- All enum fields use valid values (`architectural_role` in the 17-value vocabulary,
  `criticality` in {critical, important, supporting}, `testing_maturity` in
  {comprehensive, adequate, minimal, untested})
- `ai_enhanced_at` is a valid ISO timestamp
- No unexpected keys (catches hallucinated field names)
- Partitions that fail validation are re-queued for retry (up to 3 attempts)

**Phase 4b: Quantitative quality scoring (Python)**

Compute per-partition quality metrics:
- **Completeness**: percentage of applicable fields populated (only score
  `actions_summary` for components with `actions`, only score `testing_gaps` for
  components with `testing` data)
- **Length conformance**: `help_text` must be 3-5 sentences (count by `. ` splits)
- **Criticality distribution**: flag if a partition marks everything "supporting"
  when the digest identifies critical infrastructure, or everything "critical"
- **Detail level**: average non-null optional field count per component

Flag partitions that are statistical outliers. Outlier partitions are re-queued.
Set a minimum quality score threshold (85%). Below threshold, re-enhance.

**Phase 4c: Agent normalization pass**

The assembly agent reads ALL `ai_enhance` data from all partitions (no source code,
~74K tokens for 256 components) and performs:
- **Terminology normalization**: scan all `data_flow_description`, `help_text`, and
  `data_handled` fields for terminology variants and normalize to the glossary
- **Criticality calibration review**: flag components where criticality contradicts
  dependency metrics (>10 inbound marked "supporting," leaf with 0 inbound marked
  "critical")
- **Role consistency**: if a 256-component codebase has 50 `business-logic` and 0
  `data-access`, something is wrong
- **Tone consistency**: flag descriptions that are much shorter or longer than peers
- **Observation aggregation**: merge `local_observations` from all partitions plus
  Phase 1 observations, deduplicate (if two agents flag the same missing relationship,
  merge with "high" confidence)

The agent does NOT re-enhance or rewrite. It produces adjustments and flags. The
Python merge step applies the adjustments.

**Phase 4d: Final merge and output**

1. Merge all `ai_enhance` data into the architecture JSON by component ID
2. Apply Phase 4c adjustments
3. Add aggregated observations to root-level `ai_enhance`
4. Validate 100% coverage
5. Run existing validation checks
6. Write the final enhanced JSON

### Failure Handling

For 2000-component codebases (~80 partitions), subagent failures are a certainty,
not a possibility. The pipeline must handle them gracefully.

**Failure modes:**
- Timeout (a partition with a component containing 800+ files)
- Partial output (valid JSON for 15 of 25 components, then output limit hit)
- Malformed output (invalid JSON, wrong structure)
- Rate limiting during parallel invocations
- Hallucinated field names or enum values

**Mitigation strategy:**
1. **Per-partition retry** with up to 3 attempts and exponential backoff
2. **Schema validation before assembly** (Phase 4a catches structural problems)
3. **Graceful degradation**: if some partitions fail permanently, the final output is
   still valid. Those partitions simply have no `ai_enhance`. The viewer already
   handles this (all `ai_enhance?.` optional chaining). Report coverage: "Enhanced
   230/256 components (89.8%). 26 components in 2 failed partitions have no AI data."
4. **File-size gating**: Phase 2 estimates source tokens per partition. Partitions
   exceeding 50K source tokens are split further, preventing context overflow
5. **Progress reporting**: "Phase 3: Enhanced 12/18 partitions (67%). Running:
   partitions 13-17. Est. remaining: 4 min"

### Why This Pattern is Elegant

1. **Top-down context is preserved cheaply.** The structured digest is compact and
   every worker gets it, including terminology glossary and criticality calibration.
   No information loss.

2. **Scales linearly.** Partitions scale with codebase complexity (by LOC weight,
   not raw count). Partitions can run in parallel via task queue.

3. **Each worker stays within capacity.** Complexity-weighted partitions keep each
   agent well within the context window sweet spot for structured output.

4. **The partition boundaries are natural.** Relationship-aware grouping with natural
   subtree boundaries keeps related components together, preserving local context.

5. **Deterministic partitioning.** Phase 2 is a script, not AI. Reproducible and fast.

6. **Quality is enforced, not hoped for.** Phase 4's mandatory normalization pass,
   quality scoring, and schema validation ensure consistent output across partitions.

7. **Compatible with existing infrastructure.** The merge script, validation scripts,
   CI preservation pipeline, and update mode all continue to work. The output format
   is identical.

8. **Failure-resilient.** Per-partition retry, schema validation, and graceful
   degradation mean partial failures do not block the entire pipeline.

9. **Graceful degeneration.** For small codebases (<25 components), it naturally
   becomes a single partition, producing output identical to the current single-agent
   approach.

### Scaling Characteristics

| Codebase Size | Components | Partitions | Concurrent Agents | Est. Time |
|--------------|-----------|-----------|-------------------|----------|
| Small        | 10-25     | 1         | 1                 | ~2 min   |
| Medium       | 50-100    | 3-5       | 3-5               | ~5 min   |
| Large        | 200-300   | 10-15     | 5-8               | ~12-15 min |
| Very Large   | 500-1000  | 25-50     | 5-8               | ~20-25 min |
| Massive      | 1500-2500 | 60-100    | 5-8               | ~30-40 min |

Estimates based on ~3 minutes per subagent invocation (file reads + structured output).
Uses task queue model: maintain N concurrent slots, start next partition as each
completes (eliminates "waiting for slowest agent in batch" problem). Concurrency
bounded by API rate limits, not client-side constraints. Actual limits need testing
at 5, 8, and 10 concurrent.

---

## Part 4: Format Considerations

### Split Mode is Now Required

The `/ai-assist` pipeline will require split mode output. The split JSON format
already handles viewer-side scaling perfectly:

- `manifest.json`: Component tree, relationships, stats, AI enhancement data
- `detail-{id}.json`: Symbols and files per component (lazy-loaded)

AI enhancement data (`ai_enhance` keys) lives in the manifest, which is always
fully loaded. This is correct because `ai_enhance` data is small per component
(~200 tokens = ~500 bytes) and is needed for rendering (role badges, help text,
criticality dots). Even for 1000 components, ai_enhance data totals ~500KB.

Existing monolithic deployments will be migrated to split mode. The analyzer's
`--split` flag becomes the default for `/ai-assist` invocations.

### Intermediate Format for Enhancement Pipeline

The enhancement pipeline needs its own intermediate file format for passing work
between phases:

```
enhancement/                    # Temporary working directory
  digest.md                    # Phase 1: structured architectural digest
  architecture-ai-enhance.json # Phase 1: root-level ai_enhance
  partition-plan.json          # Phase 2: full partition plan with metrics
  partition-0.json             # Phase 2: partition assignment + dep metrics
  partition-1.json               + cross-partition neighbor summaries
  ...
  result-0.json                # Phase 3: enhancement output per partition
  result-1.json                  + local_observations per partition
  ...
  quality-scores.json          # Phase 4a/b: validation and scoring results
  adjustments.json             # Phase 4c: normalization adjustments
```

These are temporary artifacts deleted after assembly. Only the final
`architecture.json` (or `manifest.json`) persists.

---

## Part 5: Resolved Design Decisions

1. **Partition strategy: Relationship-aware, complexity-weighted.** Group by natural
   subtree boundaries first, then merge undersized groups using relationship density
   as the affinity metric. Weight by `metrics.lines`, not raw component count. Never
   split a parent from its direct children. Allow partition sizes from 5-30 components
   depending on per-component complexity.

2. **Cross-partition relationships: Source partition owns, scoped to source-observable
   data.** The agent enhancing the source component enhances outgoing relationships
   using what its source code reveals. Fields like `payload_examples` and
   `error_handling` describe source-side behavior only. Cross-partition neighbor
   summaries (name, type, framework, metrics, description) are included in the
   partition manifest to provide target context without reading target source code.

3. **Skill rewrite: In-place.** Rewrite SKILL.md with the DPEA pattern. For small
   codebases (<25 components), it naturally degenerates to a single partition. No
   need for two skills.

4. **Format requirement: Split mode required.** The `/ai-assist` pipeline will require
   the `--split` output format. Existing monolithic deployments will be migrated.
   This simplifies the pipeline significantly.

5. **Digest format: Structured template, not free-form prose.** The digest follows a
   mandatory template (system type, topology, data flows, technology map, critical path,
   terminology glossary, preliminary role assignments, criticality calibration). This
   is harder to get wrong and easier to validate programmatically.

6. **Partition logic: Algorithm-first, relationship-aware.** A deterministic Python
   script handles partitioning using natural subtree boundaries and relationship
   affinity merging. This scales reliably to any codebase size and keeps related
   components together. The AI digest agent can optionally suggest refinements, but
   the algorithm is the primary mechanism and never becomes a bottleneck.

7. **Phase 4: Mandatory agent pass.** Assembly is not optional. The normalization agent
   ensures terminology consistency, criticality calibration, and tone uniformity across
   all partitions. Without this, parallel agents produce output with visible seams.

8. **Quality enforcement: Quantitative scoring.** A deterministic scoring script checks
   completeness, length conformance, vocabulary conformance, and cross-component
   consistency. Minimum threshold (85%) gates the final output. Below-threshold
   partitions are re-queued.

9. **Observations: Aggregated from all phases.** Phase 1 produces structural
   observations from the manifest. Phase 3 subagents produce source-code-level
   `local_observations`. Phase 4 aggregates and deduplicates. The most valuable
   observations (missing relationships, misclassified components) come from the
   source-code-reading agents, not the manifest-only digest.

10. **Failure handling: Retry with graceful degradation.** Per-partition retry (3
    attempts), schema validation before assembly, graceful degradation for permanently
    failed partitions (output is still valid, just missing `ai_enhance` for those
    components). Progress reporting at every stage.

### Remaining Open Questions

- **Subagent concurrency limits**: The practical limit on parallel subagents in
  Claude Code needs testing. For the implementation plan, assume a conservative
  batch size (e.g., 5 concurrent) with task-queue scheduling for larger partition
  counts. Test at 5, 8, and 10 concurrent to find the actual limit.

---

## Part 6: Incremental Enhancement Strategy

The original plan's incremental approach ("target specific partitions") has a
structural problem: partition boundaries shift when the component tree changes. If
partition-3 was [A, B, C] last run and [B, C, D] this run, partition-targeted updates
are meaningless.

### Partition-Independent Incremental Updates

Incremental enhancement should target **component ID sets**, not partition numbers:

1. **Identify changed component IDs** from git diff or changelog
2. **Expand to relationship neighbors** using ALL relationship types (not just imports).
   The current `build_component_dependency_graph` in [analyzer/incremental.py](analyzer/incremental.py)
   at line 56 filters to `import` relationships only. AI enhancement cares about
   architectural neighbors: if a server changes its auth scheme, the client's
   relationship description is wrong, but the client is not an import neighbor. A
   parallel function should use all relationship types for AI-enhancement expansion.
3. **Collect all affected component IDs** into a set
4. **Run the partitioner on just those components**, creating temporary mini-partitions
5. **Re-enhance only the mini-partitions**
6. **Merge results** into the existing enhanced JSON using ID-based merge

### Always Re-Run Phase 1 on Updates

The digest is cheap (~2 minutes, manifest-only) and provides the context downstream
agents need. Always re-run it on incremental updates so subagents have current
architectural framing.

### Staleness Policy

Define when full re-enhancement should be triggered:
- After 5 incremental update cycles, OR
- After 3 months since last full enhancement, OR
- When the component tree changes structurally (components added/removed, not just
  modified)

Track a `digest_hash` in each component's `ai_enhance` metadata. When the digest
changes significantly, all components enhanced with the old digest become stale
candidates. Update mode can prioritize these alongside structurally changed components.

### Quality Degradation Over Time

When only some components are re-enhanced, the re-enhanced ones use a new digest while
old ones used a previous digest. Over multiple cycles, descriptions drift: newer
descriptions reference components or patterns that didn't exist when older descriptions
were written. The staleness policy and periodic full re-enhancement are the primary
mitigations. Phase 4's coherence check should also flag freshly enhanced components
that reference removed component IDs, and preserved components that reference newly
added IDs.

---

## Part 7: Quality Assurance Framework

### The Fundamental Quality Question

For codebases under ~80 components, a single agent pass produces higher quality:
consistent terminology, cross-cutting insights from simultaneous context. For codebases
over ~80 components, a single agent cannot complete the work at all. The existing data
confirms this: 115/256 components are enhanced, and enhancement appears to have stopped
partway through, hitting output capacity.

DPEA trades the single-expert advantage for the ability to complete the work at all.
The structured digest, quality rubric, terminology glossary, Phase 4 normalization
pass, and quantitative scoring close the gap. The plan should degenerate gracefully:
for <25 components, a single partition (identical to current behavior). For 25-80,
2-4 partitions with minimal consistency risk. Above 80, the full pipeline with all
quality mitigations active.

### Quality Risks and Mitigations

**Risk 1: Terminology drift across partitions.**
Without coordination, Agent A calls a data flow "user authentication tokens" while
Agent B calls it "JWT credentials." The viewer displays these side-by-side, eroding
trust.
*Mitigation:* Structured digest includes a terminology glossary. Subagent prompt
states: "Use the terminology from the glossary. Do not introduce synonyms." Phase 4
performs a terminology normalization pass.

**Risk 2: Criticality calibration drift.**
One agent rates everything "critical" while another rates equivalent components
"important."
*Mitigation:* Digest includes explicit calibration with examples. Partition manifests
include dependency metrics (inbound count, articulation point flag). Phase 4 flags
criticality-vs-structure contradictions.

**Risk 3: Architectural role accuracy.**
A partition-scoped agent sees a FastAPI endpoint and labels it `api-gateway` when it
is actually `business-logic` behind a separate gateway. Only 55% of currently enhanced
components have a role assigned, confirming this is genuinely hard.
*Mitigation:* Digest includes preliminary role assignments for top-level components.
Phase 4 validates role distribution (50 `business-logic` and 0 `data-access` flags a
systematic problem).

**Risk 4: Field population inconsistency.**
Current single-agent data shows: `help_text` at 100% but `actions_summary` at 1%,
`architectural_role` at 55%, `key_user_flows` at 1%. Parallel agents will compound
this variance.
*Mitigation:* Quality rubric with few-shot examples. Quality scoring script checks
completeness of applicable fields. Phase 4 flags statistical outliers per partition.

**Risk 5: Cross-partition relationship quality.**
Source agent cannot describe target-side behavior (authentication validation, error
responses, rate limiting) because it never read the target's code.
*Mitigation:* Phase 2 includes cross-partition neighbor summaries. Enhancement is
scoped to source-observable data. Fields like `payload_examples` and `error_handling`
describe source-side behavior honestly. Follow-on improvement: target partition
produces a brief for source partition's cross-partition relationships.

### Quality Validation Pipeline

1. **Schema validation** (Phase 4a): structural correctness, enum conformance
2. **Quantitative scoring** (Phase 4b): completeness, length, distribution, consistency
3. **Agent normalization** (Phase 4c): terminology, tone, criticality calibration
4. **Quality parity test** (one-time): for a small reference codebase, compare
   single-agent vs DPEA output using the scoring script. DPEA must score within 10%

### Schema Evolution

The current schema is `ai_enhance_version: 2`. The merge script copies `ai_enhance`
verbatim without inspecting version. For future schema bumps:
- Schema version changes should trigger full re-enhancement (infrequent, acceptable)
- The quality scoring script should apply version-appropriate validation rules
- Add `ai_enhance_schema_version` at the architecture root level to declare the most
  recent full enhancement's schema version

---

## Part 8: CI Integration

DPEA integrates cleanly with existing CI because the merge script is partition-agnostic.
It matches by component ID and (source, target, type) tuple. DPEA's output is a
standard `architecture.json` with `ai_enhance` blocks, exactly what the merge script
expects as a baseline.

CI workflows (`architecture-viz.yml`, `live-monitor.yml`) do not need to know about
DPEA. It runs locally or in a development context, produces a standard enhanced JSON,
which gets committed and preserved through CI like before.

**Required merge script fix:** Forward-carry AI-discovered relationships (see Part 1).

---

## Part 9: Implementation Files

| File | Change |
|------|--------|
| `.claude/skills/ai-assist/SKILL.md` | Rewrite with DPEA orchestration, structured digest template, quality rubric, Phase 4 normalization |
| `.claude/skills/ai-assist/RESOURCES.md` | Add terminology glossary template, calibration guidance, few-shot examples |
| `scripts/merge-ai-enhancements.py` | Forward-carry AI-discovered relationships (after line 73) |
| `analyzer/incremental.py` | Add all-relationship-types neighbor expansion (parallel to import-only function at line 56) |
| New: `scripts/score-ai-enhancement-quality.py` | Deterministic quality scoring with threshold gating |
| This document | Updated with evaluation findings (done) |

---

## Part 10: Research Sources

- [Agentic Patterns: LLM Map-Reduce](https://agentic-patterns.com/patterns/llm-map-reduce-pattern/)
- [LLMxMapReduce (Tsinghua)](https://github.com/thunlp/LLMxMapReduce)
- [Hierarchical Repository-Level Code Summarization](https://arxiv.org/html/2501.07857v1)
- [Code-Craft: Hierarchical Graph-Based Code Summarization](https://arxiv.org/html/2504.08975v1)
- [Claude Code: Agent Teams Documentation](https://code.claude.com/docs/en/agent-teams)
- [Google Research: Scaling Agent Systems](https://research.google/blog/towards-a-science-of-scaling-agent-systems-when-and-why-agent-systems-work/)
- [2026 Guide to Agentic Workflow Architectures](https://www.stack-ai.com/blog/the-2026-guide-to-agentic-workflow-architectures)
- [Multi-Agent Orchestration: Running 10+ Claude Instances in Parallel](https://dev.to/bredmond1019/multi-agent-orchestration-running-10-claude-instances-in-parallel-part-3-29da)
