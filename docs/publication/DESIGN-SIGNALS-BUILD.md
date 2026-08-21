# Design Signals: build architecture and task plan

Status: execution plan, written 2026-08-21 by Fable for an Opus build session.
This work extends the Enrichment Engine and stacks on its branch
(`wt/enrichment-engine`, T1 through T12 complete, unmerged). The design sources
are `docs/research/architecture-quality-signals.md` (the signal catalog, the
substantiability tiers, the two-audience rule) and `ENRICHMENT-ENGINE.md` (the
engine this plugs into). Where this document and those sources conflict, the
sources win; where any of them conflicts with code reality, stop, record the
conflict in the PR description, and choose the smallest faithful resolution.

The prize at the end: the analyzer derives the Tier 1 architecture quality
signals deterministically for any subject, the viewer gains a Design lens that
presents them under the two-audience rule, blast radius becomes an interaction
on the graph, and the machine front door serves the same facts term-first to
agents. No AI is required to produce any of it. The enrichment pipeline gains
the signals as context, not as obligations.

## 0. Ground rules

All eight ground rules of `ENRICHMENT-ENGINE-BUILD.md` section 0 apply
unchanged: no real model invocations, no Cloudflare or deploys, mechanical
no-regression via both golden corpora, environment first, known baselines, no
em or en dashes anywhere, delegation per the routing table, cost language.
Three additions:

1. **Base branch.** Work in a fresh worktree branched from
   `wt/enrichment-engine`, not from main. This work is part of the enrichment
   program and rides its PR train. Do not merge or rebase anything; do not
   push; do not open a PR. The owner reviews and ships.
2. **The two-audience rule is a build requirement, not a style note.** Every
   human-facing finding renders the plain-language consequence first, the
   canonical term second as a chip, and a method chip naming its epistemic
   class. The machine front door inverts the order: term as key, plain
   sentence as description. The translation table in
   `architecture-quality-signals.md` Part 3 is the copy source; do not invent
   divergent phrasings when the table already has one.
3. **Decline-to-claim is enforced in schema.** No global architecture score
   field exists anywhere. Findings carry rank within their kind only. Every
   projection surface that renders graph-derived findings carries the method
   caveat (static edges only; reflection, DI wiring, and dynamic dispatch are
   invisible). See `architecture-quality-signals.md` Part 4.

## 1. What gets built, and where it sits in the engine

The signals are P0 material under the engine's "deterministic majority"
mandate: everything derivable is derived, free, forever. They join structure,
symbols, metrics, relationships, coverage, activity, and the importance
ranking as facts in the store. Model spend touches none of this.

| Piece | New/Ext | Responsibility |
|---|---|---|
| `analyzer/derive/design_signals.py` | new | The deterministic core. Component dependency graph assembly from stored edges; fan-in, fan-out, instability per component; abstractness from stored symbol kinds; distance from the main sequence with band; cycle detection (strongly connected components, Tarjan or equivalent, deterministic ordering); stability inversions (an edge whose source is more stable than its target); boundary strength classification per edge from relationship types (source, deployment, process, service); blast radius counts (transitive dependents); hotspot join of churn and fan-in where activity facts exist; cross-boundary change coupling from commit co-change where the store's activity facts support it. Persisted in the store following the `importance.py` precedent from T2 (store, not projection, by default) |
| projection extension | ext | An opt-in `--design-signals` flag on the analyze/enhance CLI. When on: each component gains a `design` metrics block, and the architecture gains `design_signals.findings[]` in the dual-audience shape below. When off: byte-identical output, proven by both golden corpora at every task boundary |
| `viewer` Design lens | new | Joins the seven existing lenses under the existing gating principle: the lens exists only when the dataset carries `design_signals`. Ranked findings panel, most serious first (cycles, zone-of-pain components, stability inversions, cross-boundary change coupling), each row navigating into the graph with implicated nodes and edges highlighted, per the standing lens contract. The abstractness-instability scatter with the main sequence and both zones shaded, dots clickable. Mobile bottom sheet parity, dark and light mode |
| `viewer` blast radius | new | An interaction, not a report: a toggle or modifier plus hover/select shades transitive dependents one way, transitive dependencies another, dims the rest. Computed client-side from the graph the viewer already holds. The per-component count from the store appears on the card metrics bar when signals are present |
| `frontdoor.py` and MCP | ext | `ai.json` advertises design signals term-first with the plain sentence as description. MCP tools gain: design-signals overview, per-component design metrics, and blast-radius query. Same facts as the viewer, checked against it, neither privileged |
| pipeline context | ext | A compact signals digest (top findings, worst bands, counts) made available to P1 orientation and P4 synthesis context assembly, behind `--ladder`, so lens discovery and the subject brief can consume the facts. No prompt overhauls in this build; the digest is offered, not woven through |

### Data shapes (canonical, keep exactly)

```jsonc
// Per-component design metrics (projection, flag-gated)
{"fan_in": 12, "fan_out": 3, "instability": 0.2, "abstractness": 0.4,
 "distance_main_sequence": 0.4, "blast_radius": 47,
 "bands": {"fan_in": "q5", "churn": "q4"}}

// One architecture-level finding (the dual-audience shape)
{"id": "cycle-001",
 "kind": "cycle|stability_inversion|zone_of_pain|zone_of_uselessness|change_coupling|boundary_strength",
 "lead": "These 4 parts are locked together. None of them can be understood, changed, or replaced without the others.",
 "term": "Dependency cycle",
 "method": "static-graph|git-history",
 "targets": ["component-ids"],
 "edges": [["source-id", "target-id"]],
 "evidence": [{"kind": "edge", "path": null, "line": null, "symbol": null}],
 "rank_within_kind": 1}
```

The evidence entries reuse the contract's evidence schema from
`ENRICHMENT-ENGINE-BUILD.md` so the no-AI evidence validator can check
finding citations the same way it checks enrichment citations. There is no
severity score, no global grade, and no cross-kind ranking.

## 2. Tasks, in order

Each task ends with: pytest green modulo the known worktree failure, ruff
clean, both golden corpora no-drift, viewer checks where touched, and a commit
whose message says what became true.

**D0 (S). Docs land first.** Copy `docs/research/architecture-quality-signals.md`
and this plan from the main checkout into the worktree and commit them, so the
branch carries its own design sources.

**D1 (M). Metrics core.** `design_signals.py`: graph assembly, fan-in and
fan-out, instability, abstractness, distance and bands, blast radius counts.
Deterministic and stable under re-run; unit tests on a synthetic store cover
the arithmetic including edge cases (no dependents, no type symbols, isolated
components). Store persistence per the importance precedent. Golden corpora
prove no projection movement.

**D2 (M). Findings.** Cycles via strongly connected components with
deterministic member ordering; stability inversions; zone-of-pain and
zone-of-uselessness callouts from the metrics plus churn bands where activity
facts exist; boundary strength classification; cross-boundary change coupling
from co-change pairs. If the store's activity facts do not carry commit-level
co-change, extend derivation from what extraction already stores; if that
proves disproportionate, record the conflict and ship change coupling as a
named follow-on rather than forcing it. Every finding is emitted in the
canonical shape with lead and term drawn from the translation table.

**D3 (M). Projection behind the flag.** `--design-signals` on the CLI, default
off, default path byte-identical (golden corpora at the boundary). With the
flag on, the component `design` block and `design_signals.findings[]` appear,
schema-validated. The method caveat string is part of the projected payload,
not something the viewer invents.

**D4 (L). The Design lens.** Viewer lens under the existing gating principle,
ranked panel, row-to-graph navigation matching the other lenses' contract,
finding rows rendered lead-first with term chip and method chip, the
abstractness-instability scatter, edge badges for cycle membership and
stability inversions with worst-case-propagating roll-up on collapsed views.
Viewer tsc, eslint, vitest failing-file set identical to baseline.

**D5 (M). Blast radius interaction.** Client-side transitive shading on the
graph, count on the card, works at drill-down levels, mobile-safe degradation.

**D6 (S). The machine front door.** `frontdoor.py` advertisement and the MCP
tools (overview, per-component, blast radius), term-first with descriptions,
consistent by construction with the viewer's numbers (same store, same
derivation, asserted in a test that compares the two surfaces).

**D7 (S). Pipeline digest.** The compact signals digest offered to P1 and P4
context assembly behind `--ladder`, with a test proving the digest is present
in the assembled context and absent when signals are absent.

**D8 (S). Sweep and handoff.** Full posture as T12 defined it. Update the
CHANGELOG Unreleased section. Write a short handoff note in the final commit
message and the PR-description file (not a pushed PR): what was built, what
was not run, what the owner should look at first, and the named follow-ons.

## 3. Explicitly out of scope, named as follow-ons

Tier 2 signals (over-exposure ratio, interface depth, ring discipline checks,
boundary erosion, test seams). Tier 3 AI judgments (ring assignment,
screaming-architecture reads, connascence language in AI Insights), which
belong to the ladder's prompts and come after the first real ladder run.
Review-mode integration (one click from finding to pre-filled annotation),
which is the product's differentiator and deserves its own card once the lens
exists. Honest-gap UI. Anything Cloudflare. Real model invocations of any
kind.
