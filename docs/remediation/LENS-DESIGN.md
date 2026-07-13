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
- **P5-6 (NEW): correlation extraction.** Clone clusters, orphans, and concern membership into the store (section 9). Deterministic tier only; naming and judgment are Phase 7 work.
- **P6-8 (NEW): Concerns and Findings.** The concern browser and the ranked findings surface (section 9), wired into every lens per I15.
- **P6-9 (NEW): set-level review actions.** Selection sets and directives (section 10), extending review mode.
- **P7-4 (NEW): concern naming, intent conformance, finding verification.** Enrichment names concerns in domain language, evaluates declared intents against the model, and adversarially verifies findings before they surface (I15).
- **P8 (extend by one more tool).** `se_findings` (query findings and concern membership), bringing the surface to nine tools.

Sequencing note: L5 (Activity) is the highest value-per-cost addition and has no dependency on Phase 5 semantics; it needs only the store (Phase 4) and git. It should be the first NEW lens built, and it is demo-strong: pointing it at any repo produces an immediately legible "here is where the action is" map that no static view can.

## 8. The question grammar: answers as UI affordances, not chat

The owner's directive, and the Sillito finding, converge: exploration IS asking questions, and the deterministic UI must answer them through built interactions (expand, follow, compare), with conversational AI as a complement, never the primary path. Two invariants follow:

- **I14. Every question has a gesture.** Each lens ships with a documented question list: the specific questions it answers and the exact interaction that answers each. A question without a gesture is a named backlog item, not an implicit hope. Lens acceptance criteria in Phase 6 cards enumerate the question list and test the gestures.
- **I15. Findings are ranked, evidenced, and actionable.** Every automatically surfaced correlation (section 9) carries evidence, confidence, a verification status, and at least one action affordance (open members, annotate the set, export a directive). A finding the user cannot act on from where they see it is a defect.

The core question-to-gesture grammar, spanning Sillito's four scopes:

| Question | Gesture |
|---|---|
| What is this, what does it do? | Select: the identity card leads with the plain-language statement (existing help text), rationale strip per I13 |
| Why does this connect to that? | Click the edge: evidence locations, confidence, data-flow narration; "open the lines" jumps to proof |
| What does this provide, what does it need? | Expand the node's two-sided contract: capabilities offered above, dependencies and consumed contracts below |
| What happens from here? | Follow: walk the outgoing path step by step (flow following, not manual call-graph hopping), breadcrumbing each hop |
| What reaches or uses this? | Invert: same walk inbound (who calls, who imports, who navigates here) |
| What breaks if this changes? | Impact: the blast-radius set, rendered as a ranked list first (I11), graph second |
| Where else does this pattern appear? | Similar: the clone or concern membership of the selected element (section 9) |
| How sure are we it works? | Proof: the tests exercising this element, with coverage and last-run status |
| Why is it this way, who touched it? | History: the rationale strip expanded: commits, PRs, authors, churn trend |

## 9. Built-in correlations: the system volunteers what it noticed

Understanding at the "informed decision" level (including "this is a mess, rebuild it") requires the system to surface cross-cutting facts nobody thought to ask about. These are deterministic derivations over the store, AI-verified before surfacing, never AI-invented (I1):

- **Clone clusters.** Near-duplicate code detection (token-stream fingerprinting over tree-sitter tokens; the established type-1/2/3 clone families) producing ranked duplicate sets with member evidence. Answers "is there duplicate code" without being asked.
- **Concerns (strata).** First-class sets orthogonal to the containment hierarchy: every member touching a shared cross-cutting concern (logging, auth, error handling, caching, configuration, audio, persistence access), detected from signals (imports, API usage, naming) and clone clusters, named in domain language by enrichment. Concerns are the answer to "the ten logging implementations" and the addressable unit for section 10.
- **Convergence findings.** The five-audio-pipelines case. Mechanism: **declared intents** (a small set of statements like "single audio pipeline", "all persistence goes through the repository layer"), authored by the human or proposed by enrichment from docs and observed architecture, checked continuously against the model; violations surface as findings with the members and the evidence. This is the software reflexion model pattern (intended versus as-built architecture), which has decades of validation, applied at concern granularity.
- **Orphans and inconsistencies.** Components or concern members unreachable from any entry point; members of one concern following visibly different patterns (same concern, divergent shape) ranked for reconciliation.

Findings land in the store as typed entities (kind, members, evidence, confidence, verification status), flow through projections to a ranked findings surface in the viewer (I11), appear contextually on affected elements in every lens, and are queryable via `se_findings`. The Phase 7 verification pass gates surfacing: a finding that does not survive adversarial checking against its own evidence is marked unverified, never presented as fact (the DeepWiki lesson).

## 10. From understanding to action: sets and directives

Review mode already attaches feedback to single elements with full context. The missing power is sweeping, non-hierarchical action:

- **Selection sets.** Any collection becomes an addressable set: a concern's members, a clone cluster, a finding's members, search results, or manual multi-select. Sets are first-class, nameable, and persisted with the same stable-identity keying as annotations.
- **Set-level annotations.** Feedback attaches to the set with the shared intent stated once ("all logging goes through the structured logger, level from config") plus optional per-member notes.
- **Directives.** The export is not a prompt paragraph, it is a structured work order for an AI executor: the intent, the member list with each member's file, lines, and relevant evidence, the constraints (which members are exempt and why), and acceptance criteria. Directives ride the existing prompt-generator pipeline but become the primary artifact; the MCP surface makes them consumable by agents directly. This closes the product's loop as stated in PROJECT-OVERVIEW: AI builds, human reviews and directs at any grain from one line to a stratum of fifty sites, AI refines.

## 11. Why this wins

Every incumbent owns at most one or two of these lenses: CodeScene owns L5, Swimm owns L7, Sourcegraph owns L8, EA tools gesture at L2 without reaching code. Nobody ships them unified over one evidence-bearing model where the same element is visible through every lens and every claim, human or AI, drills to the line. That unification is not a feature of any competitor's roadmap because none of them owns the full stack of deterministic skeleton, provenance-stamped AI overlay, and viewer. We do.
