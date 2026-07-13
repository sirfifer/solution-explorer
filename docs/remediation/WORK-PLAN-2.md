# Work Plan 2: from remediation to the target architecture

Date: 2026-07-11
Design authority: [TARGET-ARCHITECTURE.md](TARGET-ARCHITECTURE.md) (invariants I1 to I10 bind every task)
Task detail: [TASKS.md](TASKS.md), Program 2 section (single source of truth for status, acceptance, evidence)
Predecessor: [WORK-PLAN.md](WORK-PLAN.md). Its section 2 working principles and section 6 handoff protocol apply verbatim to Program 2 and are not repeated here.

Program 1 (the audit remediation) fixed the ground truth. Program 2 builds the product the vision demands: unlimited-scale analysis, uncompromising coverage, human perspectives beyond structure, industrialized AI enrichment, and a token-efficient query surface for agents.

---

## 1. Objectives

| # | Objective | Measured by |
|---|---|---|
| O5 | Scale without compromise | A repo of 1M+ lines analyzes completely on a laptop; re-analysis cost tracks the change size; the coverage ledger accounts for every file; no silent cap anywhere |
| O6 | The index is the product | A SQLite store is the system of record; viewer projections and MCP answers are generated from it; every derived fact carries evidence and confidence |
| O7 | Perspectives for humans | Capability, Data, and Flow lenses ship in the viewer alongside Structure, driven by first-class capabilities and data entities |
| O8 | Trustworthy AI at scale | Enrichment runs headlessly with provenance and staleness; agents answer architectural questions via MCP with at least 50 percent fewer tokens than grep-only, published benchmark |

## 2. Relationship to Program 1's remaining work

Phases 1 to 3 of WORK-PLAN.md are re-scoped as follows. TASKS.md carries a Program 2 note on each affected card.

**Runs first, unchanged: all of Phase 1** (P1-1 release, P1-2 loud truncation, P1-3 annotations, P1-4 popstate, P1-5 live refresh). The front-door promise and core-loop fixes are prerequisites for credibility and are worth having regardless of the engine swap. P1-2 is an interim fix on the current engine; the ledger (P4-4) is its structural replacement.

**Stays, runs in parallel with Program 2** (the viewer and pipeline survive the engine swap): P2-3, P2-4 (viewer perf and bug sweep), P2-5 (docs reconciliation), P2-6 (hygiene), P2-8 (pipeline hardening), P3-1 (behavioral tests for surviving code), P3-2 (deep links).

**Stays, cheap interim protection**: P2-1 (incremental fallback bug) because live deployments run the current engine until P4-7 cutover. P2-7 items 1, 2, 3, 5 likewise; its dead-code items fold into the P4-7 removal.

**Superseded by Program 2**: P2-2 (scanner cache refactor) by Tier 1/2; its fixture-snapshot guard moves into P4-1. P3-4 (scanner decomposition) by the engine replacement itself.

**Already done, pulled forward: P3-3** (PR #6, merged 2026-07-11). After a production ID-drift incident on the live demo redeploy, the drift-tolerant four-wave matcher with a `--strict` threshold guard shipped, wired into action.yml and both workflows, and validated at 251/251 preservation on real data. It is the interim preservation path; P7-1 builds on it and retires the merge-script path once provenance lands.

## 3. Phase structure

Phases gate sequentially except where streams are explicitly parallel. Phase 4 gates everything in Program 2.

### Phase 4: The index engine

Goal: replace the in-memory single-pass scanner with extraction, store, derivation, and projection tiers per TARGET-ARCHITECTURE sections 4.1 to 4.4. Tasks P4-1 to P4-7.

Exit gate:
- Fixture parity: current fixture repos produce projections the existing viewer renders identically (intended improvements enumerated and reviewed, nothing else changed).
- Coverage ledger complete on every fixture and on this repo: ledger rows equal files under root; zero silent skips (grep the codebase for the old cap paths).
- Derivation reads zero source files (instrumentation assertion green).
- Incremental: touching one file re-parses exactly one file; full-vs-incremental outputs byte-identical on fixtures (normalized timestamps).
- Benchmarks recorded in TASKS.md: this repo, unamentis, and one 1M+ line OSS repo; wall time, peak memory, cold vs warm.
- Nested symbols present: methods with parent references appear in the store and projections for all tree-sitter languages.
- Old engine removed or behind an explicit `--legacy` flag scheduled for deletion; CI and action.yml run the new path; downstream redeploy verified green with enrichment preserved.

### Phase 5: Capabilities and data entities (analyzer stream)

Goal: what the system does, and what data it holds, become first-class. Tasks P5-1 to P5-3.

Exit gate:
- Per-framework endpoint extraction has tests per framework and the audit's false-positive class (header names as routes) is demonstrably gone.
- CLI commands extracted for click/typer/clap/commander fixtures with flags.
- Data entities extracted from ORM models and migrations on fixtures; entity_access edges carry evidence; models/schemas directories are no longer excluded.
- Projections carry capabilities and entities as optional keys; the existing viewer ignores them without error (backward compatibility test).

### Phase 6: Perspectives (viewer stream, 6a may start once Phase 4 gates)

Goal: lenses. Tasks P6-1 to P6-4. 6a (lens framework, flow lens, scale UX) needs only Phase 4 data; 6b (capability and data lenses) needs Phase 5.

Exit gate:
- Lens switcher with URL state; Structure, Flow, Capability, Data lenses render on the demo dataset; deep links compose.
- Flow lens renders navigation and target_view edges as a diagram, not a list.
- Aggregation nodes replace hidden internals: at every drill level, all children are visible individually or inside an expandable aggregate; the hero filter no longer hides anything without a visible trace.
- Search finds components by description and AI help text (shard-backed), test-asserted.
- Coverage badge and panel display the ledger.

### Phase 7: AI enrichment industrialization (enrichment stream, parallel with 5/6 after Phase 4)

Goal: enrichment becomes provenance-tracked, headless, and CI-capable. Tasks P7-1 to P7-3.

Exit gate:
- Every enrichment row carries derived_from_hash and commit; stale enrichment renders with a marker in viewer and MCP output; a changed-file scenario flips staleness in a test.
- `solution-explorer enhance` runs headlessly via the Agent SDK against a fixture repo from a clean checkout (no hardcoded paths), honoring partition/parallel limits, passing the existing quality scorer at threshold.
- Low-confidence edges get an AI verification verdict recorded with provenance; refuted edges are marked, not deleted.
- The merge-script path (drift-tolerant since P3-3) is retired from CI in favor of the provenance model, after a parallel-run validation period shows parity on real deploys.

### Phase 8: The query surface

Goal: the MCP server and the token-efficiency proof. Tasks P8-1 to P8-2. Requires Phases 4 and 7 (trustworthy, provenance-marked answers).

Exit gate:
- All seven tools of TARGET-ARCHITECTURE section 8 implemented, reading only the store; every response cites evidence, confidence, and staleness where applicable.
- Registered and working in Claude Code against this repo and one large repo; README documents setup.
- Benchmark published: the defined question battery, grep-only baseline vs MCP-assisted, methodology and token counts in the repo; target at least 50 percent reduction met or the miss analyzed honestly.

### Phase 9: Scale proof and release

Goal: public evidence. Tasks P9-1 to P9-2.

Exit gate:
- A 1M+ line public OSS repo analyzed and enriched, deployed as a public living demo with the coverage ledger visible; benchmark numbers published.
- v2 released (npm and PyPI per the P1-1 machinery); README, PROJECT-OVERVIEW, and DEPLOYMENTS updated; claims re-audit shows every capability claim true.

## 4. Model strategy

Fable 5 produced this plan and TARGET-ARCHITECTURE.md; its remaining Program 2 role is at most two design-review checkpoints (the Phase 4 gate and the Phase 8 tool-surface review), and only if the owner chooses to spend the tokens. Everything else runs without Fable.

| Work | Model |
|---|---|
| Default executor for all P4 to P9 tasks | Opus 4.8 |
| Phase-boundary task-card elaboration (section 6) | Opus 4.8 |
| Mechanical, fully specified tasks (marked on the card): fixture authoring, projection plumbing after the schema exists, docs updates, benchmark harness runs | Sonnet 5 |
| Store schema (P4-1), derivation correctness (P4-3), cutover gate (P4-7), provenance design (P7-1), MCP tool semantics (P8-1) | Opus 4.8, no substitution |
| Phase-gate reviews | Fresh Opus session per WORK-PLAN.md 6.3 |

## 5. Parallelization

Same rules as WORK-PLAN.md section 5: at most three concurrent sessions, disjoint file territories, one branch per stream per phase, worktrees, code-review before merge.

| Window | Streams |
|---|---|
| Program 1 Phase 1 | As WORK-PLAN.md: release solo, then analyzer and viewer streams |
| Phase 4 | Stream A: P4-1 then P4-2/P4-3 (analyzer/store). Stream B: surviving Program 1 viewer tasks (P2-3, P2-4, then P3-2). Stream C: P2-5/P2-6/P2-8 hygiene and docs |
| Phase 4 tail | P4-4/P4-5/P4-6 sequenced in Stream A (shared store territory); P4-7 gate solo |
| Phases 5, 6a, 7 | Stream A: P5-*. Stream B: P6-1, P6-2, P6-4. Stream C: P7-* (scripts, skills, worker; disjoint from A and B) |
| Phases 6b, 8 | Stream B: P6-3. Stream A or C: P8-* |
| Phase 9 | Single stream plus the human for publishes |

## 6. Handoff protocol

WORK-PLAN.md section 6 applies with one change to the reading list in the executor template: replace item 3 with "docs/remediation/TARGET-ARCHITECTURE.md, the sections your task cites, and the invariants I1 to I10." TASKS.md remains the single source of truth for status and evidence.

Phase 5 to 9 task cards in TASKS.md are intentionally lighter than Phase 4's. At each phase boundary, the gate-review session (or the first executor of the next phase) elaborates the next phase's cards to full Do/Accept/Verify fidelity using TARGET-ARCHITECTURE.md, and records the elaboration in the card before implementation starts. Elaboration must not change scope; scope changes go to the owner.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Engine rewrite drifts from current behavior in unnoticed ways | P4-1 fixture-snapshot guard from day one; P4-7 parity gate enumerates every intended difference; old engine deletable only after the gate |
| Rewrite stalls and the product is frozen mid-swap | Old engine remains the default until the P4-7 gate; every P4 task lands green on main without switching the default |
| Store schema churn invalidates downstream work | Schema and symbol ID grammar frozen at P4-1 review; later changes require a recorded decision and a migration |
| Parallel-parse nondeterminism (ordering, ids) | IDs are content/path-derived, never order-derived (I4); projections sort deterministically; parity tests run twice and diff |
| Enrichment cost explodes on large repos | DPEA partitioning already scales; provenance staleness limits re-enhancement to changed scopes; quality scorer bounds are enforced in CI |
| MCP benchmark disappoints | Publish honestly, analyze, iterate on tool responses; the benchmark is a measurement, not a marketing constraint (I10 honesty) |
| Downstream installations break at cutover | P4-7 includes downstream redeploy verification with enrichment preserved, per DEPLOYMENTS.md URLs |

## 8. What done looks like

O5 to O8 verified by their measurements, all phase gates recorded in TASKS.md, the v2 release live, at least one large-repo public demo with a visible coverage ledger, the MCP benchmark published, and the claims re-audit green. At that point the product matches the vision statement in TARGET-ARCHITECTURE section 1, and the remaining work is growth, not gap-filling.
