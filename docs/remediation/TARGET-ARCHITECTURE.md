# Target Architecture: the v2 engine and query surface

Date: 2026-07-11
Author: Claude (Fable 5) with the owner, from a product review plus two web-research passes (July 2026 sources)
Status: ADOPTED. This is the design authority for Program 2 (WORK-PLAN-2.md, tasks P4-* through P9-* in TASKS.md).
Audience: executor sessions (Opus 4.8 / Sonnet 5) implementing Program 2. Read this before any P4+ task.

---

## 1. The product goal this serves

SysCorpus exists because AI now writes code faster than humans can read it. The product must let a human, or an AI acting for a human, explore any codebase completely: every file accounted for, drill-down to the smallest meaningful unit, presented through perspectives that match how humans think (structure, capabilities, data, user flow), with zero silent omission. It must also answer architectural questions for AI agents with high token efficiency, backed by evidence, so agents stop re-reading whole repos.

Four properties define success:

1. **Uncompromising coverage.** Every file is parsed, intentionally excluded with a named rule, or reported as failed. Nothing disappears silently. Ever.
2. **Unlimited scale in principle.** Cost tracks the size of the change, not the size of the repo. The UI loads what it shows, never the whole model.
3. **Human perspectives.** Structure is one lens among several: capabilities (APIs, CLI commands, events), data organization, and user flow are first-class.
4. **Trustworthy answers.** Every derived fact carries evidence (file:line) and confidence. AI-generated content carries provenance and detectable staleness.

## 2. Research basis (July 2026)

Decisions below rest on these verified findings. Links preserved so future sessions can re-check.

- **Boring storage won.** The breakout code-intelligence tools of 2026 are local-first on embedded, unexciting storage: CodeGraph (tree-sitter to SQLite knowledge graph over MCP, ~47k stars in five months, https://github.com/colbymchenry/codegraph) and GitNexus (embedded graph, MCP, https://github.com/abhigyanpatwari/GitNexus). Meanwhile Kuzu, the fashionable embedded graph DB, was archived October 2025 after Apple acquired the company (https://www.theregister.com/2025/10/14/kuzudb_abandoned/), stranding Cognee and Graphiti, which had shipped it as a default backend. GitHub's stack-graphs was archived September 2025. DuckDB's graph extension (duckpgq) is a one-researcher community project. Conclusion: SQLite is the only five-year-safe embedded choice with graph-capable querying (recursive CTEs plus an in-memory adjacency index).
- **Exact search beats embeddings for code.** Claude Code removed its vector DB because agentic exact search outperformed it; a Feb 2026 Amazon study (arXiv 2602.23368) found keyword search reaches over 90 percent of RAG performance. Embeddings earn their keep only for fuzzy "where is the thing that does X" queries, run locally if at all.
- **SCIP became the vendor-neutral index standard** (https://scip-code.org/, steering committee with Uber and Meta). LSIF is dead. SCIP's contribution we adopt: stable, human-readable, globally unique symbol strings that make indexes mergeable across repos and diffable across commits.
- **The agent-memory world contributes patterns, not engines.** Graphiti/Zep's bitemporal validity (facts carry the time and version they were derived from, superseded facts are invalidated, never silently served) maps directly onto AI-enrichment staleness. Zep's 300ms P95 comes from doing all extraction at ingest and never calling an LLM at query time. Cursor's Merkle-tree hash sync and Cognee's hash-per-file ingest are the incremental pattern.
- **Curated tool surfaces win for agents.** Sourcegraph MCP ships a small default tool set; CodeGraph exposes nine tools; measured wins are 50 to 70 percent token reduction versus grep-only agents. Agents want search, overview, callers/callees, impact, and node detail. Not graph dumps.
- **GraphRAG's lesson:** LLM-extracted graphs hallucinate structure. Code is the exception domain because parsers give ground-truth entities and edges. Build the graph deterministically; use AI only for the semantic annotation layer. This is already SysCorpus's `ai_enhance` pattern, now elevated to a system invariant.

## 3. Non-negotiable invariants

Every Program 2 task inherits these. Violations are defects regardless of what the task card says.

- **I1. Deterministic skeleton, AI overlay.** Structural facts (files, symbols, components, edges, capabilities, data entities) come only from parsers and static rules. AI writes only into the enrichment overlay, keyed to structural identity, marked with origin.
- **I2. Coverage ledger.** Every file under the scan root appears in the ledger exactly once with a disposition: `parsed`, `excluded` (with the rule name), `failed` (with the error), or `binary`. There is no `skipped` without a reason. The viewer and every projection surface the ledger. Removing the silent 500KB skip and silent symbol caps is part of this invariant.
- **I3. Evidence and confidence on every derived fact.** Every edge and capability records at least one evidence location (file, line) and a confidence tier (`certain` for parse-level facts, `inferred` for heuristic matches, `ai` for AI-discovered). Consumers must be able to distinguish these at a glance.
- **I4. Stable identity.** Symbol IDs follow a SCIP-style scheme (see section 6). Component IDs derive from repo-relative paths, not discovery order. Identity survives re-analysis so enrichment, annotations, and diffs attach reliably.
- **I5. Provenance and staleness for AI content.** Every enrichment record stores the content hash and commit it was derived from. A projection or query response never serves enrichment for changed code without a `stale: true` marker.
- **I6. Incremental by construction.** Extraction is cached by (content hash, parser version). Unchanged files are never re-parsed. Derivation re-runs only for affected scopes.
- **I7. Local-first, zero server.** The store is a file. The viewer consumes static projections. The MCP server reads the store in-process. Nothing requires a running service or a cloud call.
- **I8. Exact-match primacy.** Name, path, and FTS search are the primary retrieval channels. Vector search, if added, is a secondary channel behind a swappable interface (sqlite-vec today, brute force acceptable at our scale).
- **I9. No LLM calls at query time.** All AI work happens at enrichment time. Queries and projections are pure reads.
- **I10. The old invariants still bind.** WORK-PLAN.md section 2 (verify before editing, regression tests that fail pre-fix, no silent anything, writing style, CI as arbiter) applies to all Program 2 work.

## 4. System shape: five tiers

```
 source tree
     |
 [T1 Extraction]   parallel per-file parse, content-hash cached
     |
 [T2 Fact store]   SQLite: files, symbols, signals, edges, capabilities,
     |             data entities, enrichment overlay, coverage ledger, FTS
 [T3 Derivation]   components, roles, relationships, capabilities:
     |             joins over signals; never re-reads source
 [T4 Projection]   manifest + detail shards + search shards + coverage report
     |             (the existing viewer delivery format, generated, compatible)
 [T5 Consumers]    viewer (lenses, prefetch) | MCP server | enrichment CLI
```

### 4.1 Tier 1: Extraction

- A multiprocessing worker pool parses files independently. Each worker runs the tree-sitter parser for the file's language (regex fallback unchanged) and emits a **fact record**: symbols, imports, exports, module doc, plus **signals**.
- **Symbols gain nesting.** Parsers emit methods and nested types with a `parent` reference. This closes the current "top-level only" gap. The 500-line block-end bound is removed for tree-sitter parsers (the tree gives exact ranges).
- **Signals** are the raw observations that Tier 3 joins over, extracted once per file: port bindings, URL and service-name references, database/queue/websocket/gRPC driver usage, endpoint declarations, CLI command declarations, UI actions with `target_view`, env var reads, framework markers. Today these are re-derived by re-reading files repeatedly in scanner.py; in v2 a file is read exactly once, in Tier 1.
- Results are cached in the store keyed by (content_hash, parser_version). A re-run parses only files whose hash or parser changed.
- Large files are parsed, not skipped. If a file genuinely cannot be parsed (pathological size, encoding), it goes in the ledger as `failed` with the reason. `--max-file-size` becomes an explicit opt-in bound whose effect is visible in the ledger, never a silent default.

### 4.2 Tier 2: Fact store

SQLite database (`.solution-explorer/index.db` by default, location configurable). Schema sketch, refined in P4-1:

```sql
files(id, path, language, lines, size_bytes, content_hash, parse_status)
symbols(id TEXT PRIMARY KEY,      -- SCIP-style, section 6
        file_id, name, kind, parent_id, line, end_line,
        visibility, docstring, code_preview)
signals(id, file_id, kind, value_json, line)
components(id TEXT PRIMARY KEY,   -- path-derived
           name, type, path, parent_id, role, meta_json)
component_files(component_id, file_id)
edges(id, source_id, target_id, type,
      evidence_json,              -- [{file, line, snippet}]
      confidence,                 -- 'certain' | 'inferred' | 'ai'
      origin)                     -- 'static' | 'config' | 'ai'
capabilities(id, component_id, kind,   -- 'api' | 'cli' | 'event' | 'job'
             name, detail_json,        -- method+path, command+flags, topic
             evidence_json, confidence)
data_entities(id, component_id, name, kind,  -- 'model' | 'table' | 'schema' | 'migration'
              fields_json, evidence_json)
entity_access(accessor_id, entity_id, mode,  -- 'read' | 'write'
              evidence_json, confidence)
enrichment(target_kind, target_id, payload_json,
           derived_from_hash, commit_sha, created_at)
coverage(path, disposition, reason)   -- I2 ledger
extraction_cache(content_hash, parser_version, facts_json)
meta(key, value)                      -- schema_version, analyzer_version, scan info
-- FTS5 virtual tables over: symbol names, component names + descriptions,
-- docstrings, enrichment help_text
```

- Multi-hop traversal: load the edges table into an in-memory adjacency structure (rustworkx; a 10M-edge graph is a few hundred MB) for impact and path queries; recursive CTEs remain the fallback for bounded-depth queries without the dependency. SQLite is durable truth, the in-memory graph is a disposable index. This is the standard pattern and it is deliberately boring (section 2).
- Python writes via stdlib `sqlite3`. No ORM.

### 4.3 Tier 3: Derivation

Passes that read only the store and write only the store:

1. **Component discovery**: marker files and directory rules over `files`, unchanged in spirit from today.
2. **Role classification**: dependency-manifest signals, framework signals.
3. **Relationship inference**: joins over signals. Port-binding signals join URL-reference signals for `http` edges; driver-usage signals join infrastructure components for `database`/`queue` edges; and so on. Every emitted edge carries evidence rows and a confidence tier (I3). The current O(components x files) full-text rescans disappear.
4. **Capability derivation**: endpoint and CLI declarations become `capabilities` rows (section 5).
5. **Data entity derivation**: model and schema parses become `data_entities` and `entity_access` rows (section 5).
6. **Testing and docs extraction**: as today, but reading cached content, not the disk.

An instrumentation hook counts source-file reads during derivation; the count must be zero (P4-3 acceptance).

### 4.4 Tier 4: Projection

Generators that read the store and write the delivery artifacts the viewer already understands:

- `architecture/manifest.json` plus `detail-*.json` shards: schema-compatible with `viewer/src/types.ts` today, extended with optional keys only (capabilities, data entities, coverage, confidence). The owner's original windowed-loading design is preserved exactly; it was always the right delivery shape. What changes is that it is generated from the store instead of assembled in memory.
- **Search shards**: prebuilt index files covering names, paths, descriptions, docstrings, and AI help text, loaded lazily by the viewer. This fixes "search only finds identifiers" and "split-mode symbols unsearchable until visited" in one move.
- **Coverage report**: the ledger, summarized and full.
- **Changelog**: diffing current store against the previous store (or previous projection), replacing the current file-diff changelog machinery.
- The monolithic `architecture.json` remains available as a projection for small repos and backward compatibility.

### 4.5 Tier 5: Consumers

- **Viewer**: unchanged rendering stack (React Flow, ELK). Gains lenses (Phase 6), coverage display, aggregation nodes instead of hidden internals, richer search from the shards, and predictive prefetch of likely-next detail shards (children of the selected node, breadcrumb ancestors).
- **MCP server**: section 8.
- **Enrichment CLI**: section 7 of WORK-PLAN-2; headless DPEA over the store via the Agent SDK, writing `enrichment` rows with provenance (I5).

## 5. New first-class concepts

### Capabilities

A capability is something the system can be asked to do through a defined surface. Kinds: `api` (REST/GraphQL/gRPC operation), `cli` (command or subcommand with flags), `event` (consumed or emitted topic/queue message), `job` (scheduled or background task). Each carries its owning component, its defining symbol where resolvable, evidence, confidence, and structured detail (method and path; command and flags; topic name). The AI overlay may attach the business meaning ("this endpoint authorizes a payment"), which static analysis cannot know. Capabilities exist because the product's unit of exploration must include *what the system does*, not only *where code lives*. Current endpoint regexes with known false positives (header names captured as routes) are replaced by per-framework extraction rules with tests per framework (P5-1).

### Data entities

ORM models, schema definitions, migration-declared tables, and standalone schema files become `data_entities` with fields where parseable. `entity_access` edges record which components (and symbols where resolvable) read or write each entity. The current behavior of excluding `models`, `schemas`, `migrations` directories from architectural consideration is inverted: those directories are where the data lens comes from (P5-2).

## 6. Identity, provenance, staleness

- **Symbol IDs**: SCIP-inspired human-readable strings: `<repo> <component-path> <file-path> <symbol-path>` with a documented grammar and escaping, stable across runs, mergeable across repos (multi-repo mode prefixes the repo segment, as today). Exact grammar fixed in P4-1 and frozen thereafter; every later phase depends on it.
- **Component IDs**: repo-relative path derived, as today, with the existing escape rules (`/` to `--`, `:` to `__`) kept in the projection layer for file naming. The safe_component_id triple-implementation stays in sync per the F-CRIT-5 comment convention.
- **Enrichment provenance**: each enrichment row stores `derived_from_hash` (the content hash of the component's files digest, defined precisely in P7-1) and `commit_sha`. Staleness is computed, not stored: enrichment is stale when the current digest differs. Stale enrichment is served with a marker, re-enhanced by the next `--update` enrichment run, and never silently dropped. This closes F-CRIT-6's root cause structurally. Interim state: P3-3 (PR #6, 2026-07-11) shipped a drift-tolerant four-wave matcher with a `--strict` threshold guard in the merge script, wired into all CI merge paths and validated at 251/251 preservation on real data; P7-1 builds on it and retires the merge-script path once provenance lands.
- **Annotations** (review mode) key on the same stable identity, which fixes their portability across re-analysis as a side effect.

## 7. Coverage ledger

The mechanism behind "shows you everything." Dispositions: `parsed`, `excluded:<rule>` (for example `excluded:node_modules`, `excluded:gitignore`), `failed:<error>`, `binary`. Invariants: the ledger row count equals the file count under the root; `parsed` count equals the `files` table count; projections carry a summary (counts per disposition) and the full ledger is queryable. The viewer shows the summary prominently (a coverage badge with a drill-in panel). The MCP `se_coverage` tool returns it. Any code path that would drop a file without a ledger row is a defect (I2).

## 8. MCP query surface

Seven tools, deliberately few (research: curated surfaces beat tool sprawl). All responses cite evidence and mark confidence and staleness. No LLM calls (I9).

| Tool | Input | Returns |
|---|---|---|
| `se_overview` | none | architecture summary: components, roles, capability counts, coverage summary, AI summary if present |
| `se_search` | query, optional kind filter | ranked matches over FTS (names, paths, docs, help text) with ids and one-line context |
| `se_component` | id | full component card: role, capabilities, entities touched, edges with evidence, enrichment (with staleness), files |
| `se_symbol` | id | symbol detail: signature, doc, code preview, file:line, containing component |
| `se_refs` | symbol or component id, direction | callers/callees at reference level, importers/importees, with confidence |
| `se_impact` | id, optional depth | blast radius: transitively affected components/capabilities/entities via the adjacency index |
| `se_coverage` | optional disposition filter | the ledger summary or filtered rows |

Benchmark target (P8-2): a defined battery of architectural questions answered with at least 50 percent fewer tokens than a grep-only agent baseline, published with methodology.

## 9. What survives, what is replaced

| Today | Fate |
|---|---|
| `viewer/` rendering stack, drill-down, detail tabs, review mode, help system | Survives; gains lenses, coverage, aggregation, prefetch |
| Split projection format (manifest + detail shards) | Survives as the Tier 4 output; the owner's windowed-loading design is confirmed |
| `ai_enhance` schema and viewer optional-chaining pattern | Survives; enrichment overlay is its generalization |
| Parsers (`analyzer/parsers/*`), tree-sitter tier | Survive as Tier 1 extraction logic; extended to nested symbols and signals |
| Component discovery rules, role classification heuristics | Survive as Tier 3 passes, re-expressed over the store |
| SwiftUI flow detection, action detection | Survive; their outputs become signals and navigation edges with evidence |
| `scanner.py` orchestration (the 2700-line class) | Replaced by Tiers 1 to 3 (supersedes P3-4) |
| `incremental.py` git-diff subsystem | Replaced by hash-keyed extraction cache plus scoped derivation (P4-6); changelog re-expressed as store diff |
| `scripts/merge-ai-enhancements.py` (drift-tolerant four-wave matcher with `--strict`, shipped as P3-3) | Remains the interim preservation path; retired by the P7-1 provenance model after parallel-run validation |
| Multi-repo orchestration | Survives; per-repo stores merged with repo-prefixed IDs; gains parallel repo scanning |
| CI workflows, action.yml, deployment skills | Survive; analyzer invocation swapped at cutover (P4-7) |

## 10. Honest limits and their representation

- **Reference resolution is name-and-import based, not compiler-grade.** Cross-language, fully resolved call graphs are a compiler-scale project (Sourcegraph-years of work). We ship reference-level `se_refs` with confidence marking instead of pretending. If demand proves out, SCIP indexer ingestion is a clean future add because our symbol IDs are SCIP-compatible by design.
- **Heuristic edges get noisier with scale.** Mitigation is I3 (evidence and confidence everywhere) plus the Phase 7 AI verification pass over `inferred` edges.
- **Embeddings are deferred, not rejected.** The store reserves a swappable vector channel (I8); it is added only when a real fuzzy-retrieval need is demonstrated, and runs locally.

## 11. Compatibility and migration

- The viewer keeps working against old projections throughout; all schema additions are optional keys (the `ai_enhance` precedent).
- The old engine remains the default until P4-7's parity gate: same fixture repos produce equivalent projections (documented, intended improvements enumerated), benchmarks recorded, then the new engine becomes the only path and dead code is removed in the same phase. No long-lived dual maintenance.
- Downstream installations (DEPLOYMENTS.md) are redeployed and verified at cutover, preserving enrichment via the provenance model.

## 12. Decisions deferred to execution

- Exact symbol ID grammar and escaping table: fixed in P4-1, then frozen.
- Worker pool implementation (multiprocessing vs concurrent.futures) and worker count heuristics: P4-2.
- rustworkx as a hard dependency vs optional accelerator over CTEs: P4-3, benchmark-driven.
- Component-files digest definition for enrichment provenance: P7-1.
- MCP server packaging (same PyPI package vs separate): P8-1.
