# Lens Design: how people engage a codebase

Date: 2026-07-13
Author: Claude (Fable 5) with the owner, from two research passes (program-comprehension science; tool-landscape survey, July 2026 sources)
Status: ADOPTED as the design authority for lens work in Program 2 Phases 5 to 7. Extends TARGET-ARCHITECTURE.md (which remains the engine authority); where this document adds lenses beyond the four named there, this document governs.
Audience: the owner; phase-gate sessions elaborating P5/P6/P7 cards; executor sessions building lenses.

---

## 1. The question this answers

The product's goal is that a technical person can genuinely understand an unfamiliar codebase: wrong language, decisions they did not make, possibly business-side-technical. Traditional views answer "how is the code organized." The questions that actually block understanding are different, and the research base is unambiguous that no single representation serves them. This document defines the lens set, what each is for, what evidence supports it, and what it costs to build.

## 2. What the research established

Findings that bind the design (sources in the research reports; key citations inline):

- **Comprehension is opportunistic switching** between a domain-level model, a control-flow model, and a data/situation model (von Mayrhauser and Vans integrated metamodel). A product must let the user change footholds without losing place. This mandates cross-lens navigation on stable identity: the same element reachable in every lens, with a persistent "you are here."
- **Non-authors cannot do top-down comprehension unaided** because they lack the domain hypothesis. The product must supply it: every lens leads with a plain-language statement of what the thing is and does, then descends to code.
- **The hardest, most frequent unmet questions are intent and rationale** ("what is this meant to do, why this way"), normally answered by asking a colleague (LaToza and Myers; Ko et al.). For a non-author with no colleague, the product must stand in: ownership, history, originating change, and AI-written rationale, threaded through every lens.
- **Navigation follows information scent** (information foraging theory). Misleading names cause failed searches; manual call-graph traversal causes disorientation. Lenses must maximize scent (strong labels and summaries on every node and edge) and minimize foraging cost (jump along flow, not hop by hop).
- **Questions come at four escalating scopes** (Sillito): find a focus point; expand it; understand a subgraph; relate subgraphs. Different scopes need different representations. The lens set must cover all four, cross-linked.
- **Market verdict on view types.** Earned love: hotspot rankings (change frequency times health), conversational Q&A with source citations, code-anchored guided tours, ownership and knowledge maps, C4-style hierarchical zoom, PR-level deltas, runtime service maps from telemetry already flowing. Proven failures: 3D city metaphors (comprehension gains in studies, fifteen years of non-adoption), unranked full dependency graphs ("hairy ball"), standalone structure visualizers as products (CodeSee absorbed, Sourcetrail discontinued), manually maintained business-capability-to-code links (rot outside regulated industries).
- **The AI era's failure mode is unverifiable claims** (DeepWiki backlash: hallucinated build systems, wrong emphasis). Source-linked citation is the antidote and is already our invariant I3. Every AI sentence in every lens cites file:line or is marked as inference.

## 3. Three product invariants this adds

These join TARGET-ARCHITECTURE.md I1 to I10 for all lens work:

- **I11. Rank, do not just render.** Every lens opens with "look here first": a ranked, bounded list or ordered path, never an unranked complete graph. The full graph is reachable, but it is the second click, not the first screen.
- **I12. Same element, every lens, one identity.** Any selected element (component, capability, rule, entity, file, symbol) can be viewed through every applicable lens without losing selection, breadcrumbs, or URL state. This rides on I4 stable identity.
- **I13. Rationale is a layer, not a lens.** Ownership, last-change, originating commit and PR, churn trend, and AI-written intent appear as a context strip on every element in every lens, standing in for the colleague the reader cannot ask.

## 4. The lens set

Organized by the human question. Status: SHIPPED (exists today), PLANNED (already in Program 2), NEW (added by this document).

### L1. Structure: "How is it organized?" (SHIPPED, refine)
Today's drill-down graph. The research validates its shape: it is a C4-style hierarchical zoom, which won the communication war precisely by stopping before drawing everything. Refinements: label the altitudes explicitly (system context, containers, components, code) so the zoom levels match the vocabulary people already use; aggregation nodes instead of hidden internals (already P6-4).

### L2. Capability: "What can it do?" (PLANNED, P5-1/P6-3, extend)
Capabilities (API operations, CLI commands, events, jobs) as first-class objects with contracts, owning components, and AI-attached business meaning. Research extension: **the test linkage is the bridge that works.** Requirement-to-code traceability survives only where tests connect them; we already extract per-component test data, so each capability should link to the tests that exercise it. That yields "what can it do, how sure are we it works, and where is the proof" in one view, and it is genuine white space: no mainstream tool ships automated capability-to-code-to-test linkage.

### L3. Data: "What does it know?" (PLANNED, P5-2/P6-3)
Entities, fields, and read/write access edges. Unchanged from the Program 2 plan; the research confirms the demand and that no incumbent serves it below the application level.

### L4. Flow: "What happens when...?" (PLANNED, P6-2, extend)
Screen and navigation flows from existing action and navigation data. Research extension: flows should be walkable as **scenarios** ("follow a request from the endpoint through the layers it touches"), because trace-following teaches the situation model and locates features at once. Static call/reference paths first; a runtime variant (OpenTelemetry ingestion) is deliberately deferred: the market lesson is that runtime views win only when the data already flows, so it waits until real deployments emit traces we can consume (candidate for Program 2 backlog, not a phase).

### L5. Activity and knowledge: "What is alive here, and who knows it?" (NEW)
The strongest-evidence view family in the entire survey, and absent from our plan until now. Derived entirely from git history, so it is language-agnostic and free, which is exactly the unfamiliar-codebase scenario. Three connected views, one entry point:
- **Hotspots**: files and components ranked by change frequency times complexity or health. The gateway view; answers "where should I look first" for risk, onboarding, and refactoring alike.
- **Knowledge map**: authorship distribution, knowledge islands, bus factor, at component granularity. Answers "who knows this" and "what is at risk."
- **Change coupling**: what changes together despite no static dependency. Reached from hotspots (the market lesson: standalone coupling views go unused; hotspot-anchored ones get discovered).
Data lands in the fact store as git-derived signals (per-file churn series, author shares, co-change pairs); extraction is a Tier 1-adjacent pass reading `git log`, cached by commit range.

### L6. Rules: "Where do the decisions live?" (NEW)
The owner's hunch, validated by thirty years of business-rule mining practice. A rule is a discrete unit of decision or constraint logic, operationally typed: **validation, calculation, policy or decision, input/output constraint**. Rule-bearing code is identifiable statically (domain conditionals, validation clusters, formulae with domain constants, decision-table-shaped branching); the 2025 to 2026 practice fuses that deterministic detection with LLM narration into plain-language statements, which is precisely our engine-plus-enrichment split (I1). Each rule carries: type, plain-language statement (AI overlay, provenance-stamped), inputs and outputs (data elements, linking into L3), trigger context, and evidence to exact lines. Rules become store entities like capabilities. Normalization toward decision-table form where branching warrants it. This is the lens that lets a business-side-technical reader audit what the system actually enforces.

### L7. Tours: "Walk me through it." (NEW)
Code-anchored guided walkthroughs: an ordered sequence of steps, each a highlighted location plus narration. Independently reinvented by CodeTour, Swimm, and IcePanel because it matches how humans onboard, and the research shows it supplies the top-down scaffold non-authors lack. Two properties make ours defensible: (a) tours are generated by the enrichment pipeline (candidate tours per capability, per scenario, plus an onboarding path), human-editable, stored as first-class artifacts keyed to stable IDs; (b) **tours detect their own staleness** via the same content-hash provenance as all enrichment (I5), which is the feature that made Swimm's walkthroughs durable and which we get from Phase 7 infrastructure for free.

### L8. Ask: "Where is the thing that does X?" (PLANNED via Phase 8, name it)
Concept-to-code location: a plain-language concept ("checkout", "authorization") resolved to all relevant code units. The research recipe is settled: semantic retrieval anchored to the structural graph, human steering, every hit cited. The MCP server (Phase 8) is this lens for agents; the viewer gets the human face: search shards over names, docs, and AI text now (P6-4), a conversational surface later once the store and MCP tools exist to ground it. Embeddings remain the optional secondary channel per I8.

## 5. What we deliberately will not build

Recorded so future sessions do not relitigate: no 3D or city metaphors; no unranked full-graph landing views; no manual capability-to-code link editor (links are inferred and provenance-checked or they do not exist); no runtime lens that requires a separate recording ritual (runtime waits for telemetry that already flows).

## 6. Program 2 integration

Phase and task deltas (cards to be added to TASKS.md when the current execution streams land, to avoid tracker collisions; the phase-gate session elaborates them per WORK-PLAN-2 section 6):

- **P4 (no change now).** The store schema gains git-activity and rules tables additively via schema_version migration when P5-4/P5-5 land; the P4-1 symbol ID grammar is unaffected.
- **P5-4 (NEW): git activity extraction.** Churn series, author shares, co-change pairs into the store; cached by commit range; ledger-accounted. Wholly language-agnostic.
- **P5-5 (NEW): rule extraction.** Deterministic detection of rule-bearing code (validation clusters, domain conditionals, calculations, decision-shaped branching) into typed rule entities with evidence and confidence; plain-language statements come from enrichment (Phase 7), not extraction (I1).
- **P6-1 (extend).** The lens framework implements I11, I12, I13: ranked landing views per lens, cross-lens element identity, and the rationale strip.
- **P6-5 (NEW): Activity lens** (hotspots, knowledge map, coupling drill-in).
- **P6-6 (NEW): Rules lens** (typed rule browser, decision-table rendering where applicable, links into Data and Capability lenses).
- **P6-7 (NEW): Tours** (player in the viewer; tour artifacts in the store; authoring is enrichment work).
- **P7 (extend).** Enrichment generates rule statements and candidate tours; staleness (I5) applies to both. The verification pass (P7-3) covers rule statements: a stated rule that does not match its cited code is marked, never silently served.
- **P8 (extend by one tool).** `se_rules` joins the MCP surface (query rules by component, entity, or concept), bringing it to eight tools; the curated-surface principle holds.

Sequencing note: L5 (Activity) is the highest value-per-cost addition and has no dependency on Phase 5 semantics; it needs only the store (Phase 4) and git. It should be the first NEW lens built, and it is demo-strong: pointing it at any repo produces an immediately legible "here is where the action is" map that no static view can.

## 7. Why this wins

Every incumbent owns at most one or two of these lenses: CodeScene owns L5, Swimm owns L7, Sourcegraph owns L8, EA tools gesture at L2 without reaching code. Nobody ships them unified over one evidence-bearing model where the same element is visible through every lens and every claim, human or AI, drills to the line. That unification is not a feature of any competitor's roadmap because none of them owns the full stack of deterministic skeleton, provenance-stamped AI overlay, and viewer. We do.
