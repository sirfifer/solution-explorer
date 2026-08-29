# The Knowledge Graph Direction

**Status:** Direction record. Nothing here is committed work; this captures a design conversation and the destination it reached, as input to a future design record (candidate Program 3).
**Date:** 2026-08-29
**Participants:** Richard Amerman (owner), Claude

## Why this document exists

This began as a one-line question, "take a look at Neo4j," and ended somewhere much larger: a redefinition of what this product's data layer is and what its final deliverable should be. The result matters most, so it comes first. But the journey is recorded too, because each step was a genuine correction of the step before it, and the reasoning is part of the asset. A future reader who sees only the conclusion will not understand why the alternatives were rejected, or which of them stays available if circumstances change.

## The result

### 1. What we are building is a knowledge graph, not a database schema

The product's data layer is a probabilistic, provenance-carrying knowledge graph of a software system, deterministically extracted. That names the whole design, not a piece of it. The defining features live above any storage engine:

- **An open statement model.** The atom of the graph is not an edge with properties but a statement: subject, predicate, object, evidence set, likelihood, frame membership, derivation parents, staleness. Entity kinds, edge types, and dimensions are data, not schema. This is what lets pass N+2 discover a kind of thing nobody predicted and make it a first-class citizen.
- **A governed vocabulary (an ontology).** Total schema freedom would mean passes cannot rely on each other's output. The vocabulary of labels and relation types is itself a versioned artifact that grows deliberately, only when a pass needs it. This guards against the classic knowledge-graph failure of ontology over-engineering.
- **Relationship-first identity.** An entity is constituted by its relationship neighborhood. The classifier literally decides what a thing is by looking at its edges.

### 2. Inference is differential, Bayesian, and multi-pass

- **Frames.** Every classification question is a frame: a set of mutually exclusive hypotheses that cannot all be true. Evidence is scored by likelihood ratio, "how much more likely is this observation under H1 than H2," so belief mass is conserved: evidence for one interpretation automatically drains its competitors. Conflict resolution becomes arithmetic instead of a bolt-on.
- **Multi-pass derivation to fixpoint.** Each pass discovers virtual entities and patterns that become first-class subjects for the next pass. Every derived fact records its parents (a provenance DAG), which enables incremental re-derivation, explanation, and cascade trimming.
- **Principled stopping and trimming.** Borrowed from clinical decision theory: below a test threshold a hypothesis is discarded; above a commit threshold the frame is resolved and passes stop spending on it. Confidence decays with inference depth unless independently corroborated, which bounds the fixpoint and prevents hallucination cascades. Expensive probes are scheduled by which one best discriminates the top competitors, not by a fixed pipeline order.
- **Non-negotiable guardrails.** Every frame carries a residual "none of the above" hypothesis, because normalization over a closed candidate list will confidently crown a winner even when every candidate is wrong. Exclusivity is declared per frame, never assumed. Evidence carries source keys so correlated observations are not double-counted. No confidence number ships uncalibrated; calibration runs against hand-verified benchmark repos.
- **An honest output class.** A frame no candidate can win is reported as an unresolved differential, with the evidence that would settle it. That is a product feature, not a failure.

### 3. The engine is a substrate choice, made on quality grounds

- Neo4j as a backend is rejected. Not on performance grounds, on architectural ones: it is a server (there is no supported embedded mode), which breaks the local-first, zero-server invariant (I7) that makes the CI action, the install story, and the static viewer possible, and its useful algorithm layer is commercially licensed.
- The store stays an embedded file. The candidates are a generic node/statement schema in SQLite (boring, zero new dependencies) and Kuzu (embedded, file-based, speaks openCypher). The deciding criterion is not speed but rule quality: pattern-discovery rules written as declarative graph patterns are shorter, more reviewable, and less buggy than imperative traversal code. A spike implements the same pattern rules on both substrates and compares them for clarity and correctness, with a scale-gate benchmark so the performance question stays empirical.
- Neo4j returns as an export projection (Cypher statements or GraphML alongside the SBOM and SARIF outputs), turning it from a dependency into an audience.
- Performance is a constraint to satisfy, not an objective. Measured on this machine: at 100x current scale (1M nodes, 10M edges), a 6-hop traversal is roughly 40 ms via SQLite recursive CTE and 3 ms via a disposable in-memory adjacency structure, which is index-free adjacency without the server. The database matters at build and enrichment time; nothing user-facing waits on it.

### 4. Delivery is two-tier: ship the views, and ship the graph

The decisive realization: the current JSON projections are not the knowledge graph, they are a handful of pre-answered questions. Every question the viewer can answer was anticipated at projection time. That is why they load fast, and it is also the ceiling: ad hoc exploration means users compose questions nobody anticipated, and no set of pre-baked files answers arbitrary compositions. The richness exists at build time and is amputated at delivery time (evidence detail, confidence gradations, provenance chains, losing hypotheses, cross-dimensional joins).

The resolution keeps both virtues:

- **Tier 1: the JSON projections, exactly as today.** First paint in milliseconds, the guided experience, mobile on hotel wifi, zero regression. Philosophically demoted from "the product" to "a cache of the common questions."
- **Tier 2: the statement store itself, published as a static artifact.** The store is a single file (I7), and a file can be a CDN asset. SQLite compiled to WebAssembly runs in every modern browser, including iOS Safari, and can page in only the database pages a query touches via HTTP range requests. No server, no full download, real queries. Kuzu's WASM build joins the spike as the Cypher-in-browser candidate. Nothing is lost in translation because there is no translation.
- **User-composed views become data.** With a queryable graph on the client, a custom view is a saved query plus a layout recipe. The lens concept generalizes into building blocks users can compose and share. Competitors ship diagrams; this ships the codebase's knowledge graph with the diagram as its default face.
- **One truth for humans and agents.** The MCP server already queries the store. Tier 2 puts humans and agents on the same artifact.

The headroom audit against the owner's standard ("nothing barely achieved"): Tier 1 alone was maxed out against the ad hoc vision and would have failed it on the first cross-dimensional query. Tier 2's bound is the working set of a query, not the dataset size. Mobile stays first-class in both tiers.

### 5. What stands, what changes

The invariants survive, generalized rather than broken: deterministic skeleton with AI overlay (I1), evidence and confidence on every fact (I3, upgraded from a three-value enum to calibrated likelihoods), stable identity (I4), local-first zero-server (I7), no LLM calls at query time (I9). What dies is the fixed-table schema and the one-shot derivation pipeline. The biggest single cost is migrating the store and every projection writer onto the statement model; it is on the critical path for everything else. The most technically novel piece is in-browser query over range requests, which must be proven on a real phone before the design record promises it.

## The journey

The path mattered because every stop corrected the frame of the one before it. In compressed form:

1. **"Look at Neo4j."** First assessment: wrong fit. It breaks the zero-server invariant, and at this scale (hundreds of components, thousands of symbols) graph-engine performance advantages are orders of magnitude away from activating. Counterproposal: the already-planned in-memory graph tier, Kuzu if ever needed, Neo4j as export.
2. **"Relationships are the most important thing, and we must scale dimensionally."** This landed. The fixed-table schema is closed-world: every new kind of discovered thing is a schema migration. The owner's multi-pass vision, where each pass exposes virtual entities that the next pass must parse, kills fixed tables outright. Conceded: the data model must be an open property graph. Distinction drawn: that is a model requirement, not an engine requirement.
3. **"Make it Bayesian, build confidence, stop and trim when confidence decreases."** Sharpened into log-odds evidence accumulation rather than a full Bayes net, with the correlated-evidence trap (ten regex hits in one generated file are not ten pieces of evidence) identified as the day-one failure mode.
4. **"Think differential diagnosis: relative likelihood between conflicting elements that cannot both be true."** The key upgrade. Standalone confidence scores let two incompatible interpretations both look plausible. Frames with likelihood ratios force every belief to answer "compared to what," give principled test-ordering and stopping thresholds for free, and make the differential itself product content: the tool shows what it considered and why the losers lost.
5. **"This is why Neo4j seems like a hard requirement: the form of the data cannot be predicted."** Half conceded, half resisted. Schema flexibility is a property of the data model, not the database; a generic statement store is exactly as unbounded in SQLite as in Neo4j. What a Cypher-class engine genuinely offers is declarative subgraph pattern matching, which is a quality argument for the passes. That selects an embedded Cypher engine as a candidate, not a server.
6. **"Take seriously the difference between a graph database and a knowledge graph."** The naming breakthrough. Mapping every requirement from the prior turns against the two definitions showed the design was a knowledge graph all along: ontology, materialized entailment, open-world assumption, qualified statements, identity resolution. The engine debate had felt unsatisfying because the requirement lived a layer above every engine. What the owner's instinct was reaching for was real; the nearest available word for it had been "graph database."
7. **Textbook Neo4j claims, benchmarked.** Index-free adjacency is real and its constant-factor advantage activates two to three orders of magnitude above the stress case, per measurements at 10x and 100x scale on the development machine. The one claim that applies at every scale, server versus file, decides against the server.
8. **"The database only matters at build time; the site consumes generated files."** Correct, and it inverted the debate: strip performance out as a criterion, as this observation rightly does, and what remains is representation quality, rule reviewability, determinism, and distribution. A performance-and-concurrency machine loses its remaining rationale.
9. **"Is JSON limiting us? Could we load fast and backfill with richness? Everything needs headroom."** The final synthesis. The constraint was never JSON the format but JSON as precomputed views. The owner's own suggestion, fast load backfilled by something richer, is the two-tier delivery: projections for instant paint, the knowledge graph artifact itself for ad hoc exploration.

The pattern across all nine steps: the owner kept pushing on capability (dimensionality, relationships, exploration, headroom) and the analysis kept relocating the requirement to the correct layer (model, not engine; semantics, not storage; delivery shape, not serialization). Both motions were necessary. The pushes prevented settling for the incumbent design; the relocations prevented buying a server to solve a modeling problem.

## Next steps (owner-gated)

1. Write the full Program 3 design record: statement model, vocabulary governance, frame and likelihood-ratio calculus, pass scheduler, thresholds, calibration protocol, two-tier delivery.
2. Substrate spike: the same three pattern-discovery rules on SQLite-generic and Kuzu, judged on clarity and correctness, plus the scale-gate benchmark.
3. In-browser graph spike: a real statement store behind HTTP range requests, queried from WASM on a real phone.
4. Neo4j export projection as a low-cost line item.
