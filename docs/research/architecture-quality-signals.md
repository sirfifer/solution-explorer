# Architecture Quality Signals: From Depicting Structure to Evaluating It

## Context

Solution Explorer currently answers "what is here" and "how is it composed." This document
researches the next question a reviewer actually has: "is this architecture any good, and
where is it weak?" The source material is the body of software design theory that treats
boundaries, isolation, and dependency structure as measurable things. Much of it is
crystallized in Robert C. Martin's *Clean Architecture* (the component principles, the
Dependency Rule, boundary anatomy), but the concepts predate and outlive that book, and
this document deliberately treats them as abstract signals rather than as any one author's
doctrine. Where a signal has a name and a lineage, the lineage is cited so we can defend
the method behind the number.

The governing constraint is the project's existing epistemic stance: the map must not say
more than it can support. Every signal below is therefore classified by how substantiable
it is from facts the analyzer already extracts or could extract, and every signal carries
a statement of what it cannot see. A quality claim presented as flat fact, when it is
actually a heuristic, is exactly the "quietly, credibly wrong" failure mode the
Comprehension Review exposed.

**Why this matters more in the AI era, not less.** The product thesis is that AI generates
architecture faster than humans comprehend it. Comprehension is step one. Evaluation is
step two, and it is the step the review system exists for. A reviewer looking at an
AI-generated system needs to know not only that Component A calls Component B, but that
the dependency structure is cyclic, that the most-depended-upon component is also the most
frequently changed, and that a declared service boundary is being bypassed. These are the
findings that turn passive exploration into confident annotations. They are also precisely
the facts an agent consuming the MCP front door needs before it can safely parallelize
work across a codebase: boundaries define blast radius, and blast radius defines what an
agent fleet can touch independently.

There is now empirical support for this framing. A SonarSource controlled study (arXiv
2605.20049, 660 Claude Code trials on minimal-pair repos) found code cleanliness did not
change task pass rates but cut token consumption 7 to 8 percent and file re-visitation 34
percent. A CodeScene and Lund University study (arXiv 2601.02200, ACM FORGE 2026, six
LLMs) found healthy code reduced agent failure rates 15 to 30 percent and argues AI needs
a higher code-health bar than human readers. Both authors sell quality tooling, so the
affiliations should be disclosed when citing, but both studies are controlled and public.
Most striking, Thoughtworks measured a representative change to a 17,155-line AI-grown
Rust codebase before and after classical refactoring: input tokens for the change fell
83 percent, from 159,564 to 27,360, with line count roughly constant (Edwards-Alexander,
"The Economic Benefit of Refactoring," martinfowler.com Exploring Gen AI series, July
2026). The practical reading: structural quality is no longer only a human-comprehension
variable. It is an economic variable, priced in tokens and failure rates, and a tool that
can measure it per component is measuring something with a bill attached.

---

## Part 1: The Conceptual Inventory

The design literature offers a compact set of abstractions that describe how software is
shaped, independent of language or framework. These are the candidates worth representing.

### 1. Dependency direction

The single most load-bearing idea in *Clean Architecture* is that source-code dependencies
have a direction, and that the direction should point from volatile, concrete things
toward stable, abstract things (the Dependency Rule; also Martin's Stable Dependencies
Principle). A dependency edge is not just a line; it is a statement about who breaks when
the other changes. Everything else in this document is a refinement of this one idea.

### 2. Cycles

The Acyclic Dependencies Principle: the component dependency graph should be a DAG. A
cycle means a set of components that can only be understood, tested, released, and now
regenerated, as a unit. Cycle detection is the least controversial architecture check in
existence, it is pure graph analysis, and it produces findings that are true rather than
opinions.

### 3. Stability and abstractness

Martin's component metrics are directly computable:

- Fan-in (afferent coupling, Ca): how many components depend on this one.
- Fan-out (efferent coupling, Ce): how many components this one depends on.
- Instability: I = Ce / (Ca + Ce). A component with high fan-in and low fan-out is
  "stable" in the load-bearing sense: hard to change, because many things sit on it.
- Abstractness: A = abstract symbols / total symbols. The symbol extractors already
  distinguish protocols, interfaces, and abstract classes from concrete types.
- Distance from the main sequence: D = |A + I - 1|. Components that are concrete and
  heavily depended upon fall in the "zone of pain" (rigid, everything breaks when they
  change). Components that are abstract and depended on by nothing fall in the "zone of
  uselessness" (speculative generality).

These metrics have a forty-year lineage (they generalize structured-design coupling and
cohesion) and are the basis of commercial tools like NDepend and Structure101. They are
imperfect and gameable, and the interface must say what they measure, but they are honest
arithmetic over facts we already hold.

### 4. Boundary anatomy and boundary strength

*Clean Architecture* catalogs boundaries by mechanism: a source-level boundary (an import
across packages), a deployment boundary (separately built artifacts), a process boundary,
a service boundary (network protocol). Each step up buys isolation and costs latency and
operational complexity. Solution Explorer's relationship model already encodes exactly
this spectrum: structural edges (import, ffi) versus communication edges (http, websocket,
grpc, database). What the model does not yet do is treat the spectrum as a *strength*
attribute that can be reasoned about: "these two components are separated only by
convention" versus "these two are separated by a network contract."

### 5. Boundary integrity and erosion

A declared boundary that is routinely bypassed is worse than no boundary, because it
misleads the reader. Classic erosion patterns: a component importing another component's
internals rather than its public surface; two services sharing a database table; a
"layered" system where a lower layer reaches up. Erosion is detectable as a contradiction
between the declared structure (packages, services, public surfaces) and the observed
edges. This is the architecture-level version of the project's existing principle that two
surfaces disagreeing about the same fact must be surfaced loudly.

### 6. Cohesion, and change as evidence

Martin's Common Closure Principle says things that change together should live together.
Its contrapositive is testable against history: if two components repeatedly change in the
same commits, the boundary between them is drawn where the cracks are not. Adam Tornhill's
behavioral code analysis (CodeScene, *Your Code as a Crime Scene*) built an entire
discipline on this: hotspots (high churn × high complexity), change coupling across
declared boundaries, and knowledge distribution. The Activity lens already ingests git
history, so the raw material exists. Change coupling is the strongest empirical
counterweight to purely structural metrics, because it measures what the system actually
does under maintenance rather than what its shape suggests.

### 7. Interface depth and surface economy

John Ousterhout (*A Philosophy of Software Design*) frames module quality as depth: a good
module has a small interface hiding a large implementation. A shallow module exposes
roughly as much as it hides, so it adds cognitive load without absorbing complexity.
Related, Martin's Interface Segregation and Common Reuse principles both reduce to surface
economy: do not force dependents to see what they do not use. Computable proxies: exported
symbols versus symbols actually imported by other components (over-exposure ratio), and
interface size versus implementation size per component.

### 8. Policy versus detail, and ring discipline

The concentric-circles picture: entities and business rules at the center, orchestration
around them, adapters next, frameworks and I/O at the rim, with all dependencies pointing
inward. Whatever one thinks of it as a prescription, as a *description* it gives a
reviewer an immediate quality read: does the domain core import the web framework, or
does it not? The AI enhancement layer already assigns an 18-role vocabulary
(business-logic, data-access, presentation-layer, api-gateway, infrastructure, and so on)
that maps cleanly onto rings, which makes ring-discipline checking possible: an edge from
business-logic out to presentation-layer or to a vendor SDK is an inward ring depending
on an outer ring.

### 9. Blast radius

The practical meaning of all coupling metrics, collapsed into one question a reviewer and
an agent both ask: if this component changes, what is the transitive set of components
that could break? Small blast radii are what boundaries are *for*. This is also the
AI-era signal par excellence: it is the fact that decides whether ten agents can work the
codebase in parallel or must queue.

### 10. Connascence

Meilir Page-Jones's taxonomy of the ways two pieces of code must change together:
connascence of name, of type, of meaning, of position, of algorithm, of timing. The rule
of thumb is that stronger connascence is acceptable only at closer range. Strong
connascence across a component or service boundary (two services that must agree on an
algorithm or a magic value) is a boundary defect. Most forms resist static detection, so
this is a vocabulary for AI-assisted review rather than for the analyzer, but it is the
richest coupling vocabulary available and worth adopting in annotation and AI-insight
language.

### 11. Screaming architecture

Martin's naming test: the top level of the system should communicate the domain, not the
delivery technology. A tree that reads "accounts, lessons, billing" teaches; a tree that
reads "controllers, models, views, utils" does not. This is a heuristic about naming
vocabulary, cheap to approximate and easy to over-claim, so it belongs in the clearly
labeled opinion tier.

### 12. The lossy-compression principle for abstraction itself

One meta-concept, and it is the project's own: every abstraction level is a compression
of the level below, and compression is only trustworthy when the loss is declared. A
rolled-up component card that averages away a critical violation is a JPEG artifact
presented as a photograph. Whatever quality signals we render, the roll-up rule must be
worst-case-propagating (a summary never looks healthier than the worst thing it hides)
and every summary must disclose what it omits and offer the drill-down. C4's leveled
abstractions (context, container, component, code) succeed for exactly this reason: each
level admits it is a view, scoped to an audience, not the whole truth.

---

## Part 2: Substantiability Tiers

The tier decides how a signal may be presented. Tier 1 findings can be stated as facts
with method notes. Tier 2 requires new extraction work but remains factual. Tier 3 is
judgment, must be labeled as judgment, and must link its evidence.

### Tier 1: Computable now from the existing fact store

| Signal | Computation | Reads as |
|--------|------------|----------|
| Dependency cycles | Strongly connected components over the component import graph | Finding: "these 4 components form a cycle; they can only change as a unit" |
| Fan-in / fan-out / instability | Edge counting on the same graph | Per-component metric with tooltip explaining load-bearing vs volatile |
| Abstractness and main-sequence distance | Symbol kinds already extracted; A and D per component | Scatter plot lens panel; zone of pain and zone of uselessness callouts |
| Stable-depends-on-unstable edges | Compare I across each edge | Edge badge: "a load-bearing component depends on a frequently-shifting one" |
| Boundary strength classification | Reclassify existing relationship types onto the source / deployment / process / service spectrum | Edge attribute plus per-boundary summary |
| Blast radius | Transitive closure of dependents from any node | Interactive: select a node, shade every component that could break |
| Hotspot risk | Join Activity lens churn with fan-in | Finding: "most-depended-upon component is also the most-edited" |
| Change coupling across boundaries | Co-change pairs from git history that cross component lines | Finding: "these two components changed together in 23 of the last 30 commits touching either" |

Every one of these obeys the coverage-ledger ethic naturally: the method is mechanical,
the inputs are enumerable, and the caveat is uniform ("static import and declared
communication edges only; runtime reflection, dependency injection wiring, and dynamic
dispatch are invisible to this analysis").

### Tier 2: Computable with modest analyzer extension

- **Over-exposure ratio.** Requires tracking which exported symbols are actually imported
  by which components. The import extraction exists; the cross-reference does not yet.
- **Interface depth proxy.** Public symbol count versus total symbol count and line count
  per component.
- **Ring discipline checks.** Requires mapping the AI role vocabulary (or a static
  heuristic based on framework imports) onto ring levels, then flagging inward-ring to
  outer-ring edges. Static detection of "domain file imports web framework" is a regex
  away for known frameworks, and is factual; the *ring assignment* is the judgment part
  and belongs to Tier 3 unless the user confirms it.
- **Boundary erosion.** Requires a notion of a component's public surface (an index file,
  an `__init__.py`, an exported module list) so that deep imports bypassing it can be
  flagged.
- **Test seam coverage.** Which components have test files at all, and whether tests
  import the public surface or reach into internals.

### Tier 3: AI-assisted judgment, always labeled as judgment

- Ring assignment of components (entities / use cases / adapters / details) with the
  user able to correct it, feeding the same annotation loop that already exists.
- Screaming-architecture read on naming vocabulary.
- Connascence-vocabulary explanations of *why* a detected coupling is strong or weak.
- A narrative "design review" per component: the AI Insights tab already carries roles
  and criticality; it could carry a short strengths-and-risks paragraph whose every claim
  links to a Tier 1 or Tier 2 fact. The rule from the Comprehension Review applies with
  full force: a claim that cannot cite a fact is not rendered.

---

## Part 3: Presentation Concepts

### Speaking to two audiences at once

Every signal in this document has a canonical name earned over decades, and none of those
names may lead. The rule, which extends the product's existing design language (device
frames instead of component-type jargon, lenses phrased as questions a person would
actually ask), is:

1. **Lead with the value in common language.** The first thing a reader sees states the
   consequence: what this means for them, what it costs, what question it raises. No
   prior vocabulary required. This serves the executive persona and every first-time
   reader.
2. **Carry the established term as the second element, not the first.** A small chip or
   subtitle with the canonical name. A practitioner recognizes it instantly and knows
   exactly which body of theory stands behind the finding; everyone else can ignore it
   or tap it for the tooltip. The term needs no attribution in the interface. Lineage
   lives in documentation (the Sources section of this file), not on the canvas.
3. **Never let the translation lose the concept.** The plain phrasing must be a faithful
   restatement, not a dumbed-down neighbor. If a wording cannot carry the real meaning,
   the wording is wrong, not the concept. This is the lossy-compression rule applied to
   language: compress the jargon away, never the idea.

The working translation table for the Tier 1 and Tier 2 signals:

| Leads (common language, value first) | Follows (established term) |
|--------------------------------------|---------------------------|
| "These 4 parts are locked together. None of them can be understood, changed, or replaced without the others." | Dependency cycle |
| "If this changes, everything shaded red could break." | Blast radius (transitive dependents) |
| "This is load-bearing: 23 parts lean on it. It has no flexibility built in, and it keeps being changed anyway." | Zone of pain (high fan-in, concrete, high churn) |
| "This flexibility was built for consumers that never arrived. Nothing uses it." | Zone of uselessness (abstract, unused) |
| "Something the whole system leans on is itself standing on one of the most frequently changing parts." | Stability inversion (SDP violation) |
| "These two are separated on the diagram, but in practice they change together. The boundary may be drawn in the wrong place." | Cross-boundary change coupling (CCP) |
| "There is an official doorway between these two, and traffic is going through the wall." | Boundary erosion (bypassed public surface) |
| "Separated by convention only" / "separated by a real contract." | Boundary strength (source vs service boundary) |
| "The heart of the business logic is wired directly to a specific vendor. Replacing that vendor means surgery on the core." | Framework coupling in the core (Dependency Rule violation) |
| "A small handle on a big machine" / "a handle as big as the machine it operates." | Module depth (deep vs shallow interface) |
| "The folder names tell you what framework this uses, not what the business does." | Screaming architecture check |

One inversion worth making explicit: the machine front door flips the priority. For
`ai.json` and the MCP tools, the canonical term leads, because it is the compact,
unambiguous key an agent can map to the literature and act on; the plain-language
sentence rides along as the description field. Same facts, two projections, each ordered
for its reader, and the numbers must agree between them. This dual-audience discipline
is not a presentation nicety. It is the product's standing challenge: the tool exists
precisely because the same system must be legible to people who do not share a
vocabulary, and every new capability either rises to that or quietly narrows the
audience to experts.

### A Design lens

The lens system is the natural home. A **Design lens** (alternative names: Quality,
Soundness) joins Structure, Inventory, Flow, Activity, Capability, Data, and Rules. Like
every lens, it appears only when the dataset can support it. Its ranked panel lists
findings, most serious first:

1. Cycles (with the member components, navigable).
2. Zone-of-pain components (concrete, heavily depended upon, and, when Activity data
   exists, frequently changed).
3. Stable-depends-on-unstable edges.
4. Cross-boundary change coupling.
5. Boundary erosion instances.

Each row navigates into the graph with the implicated nodes and edges highlighted, the
same contract every other lens honors. Each finding renders per the two-audience rule
above: the plain-language consequence leads, the term chip follows, and a method chip
(static graph / git history / AI judgment) says which epistemic class the claim is in.

### The main-sequence scatter

A small A-versus-I scatter plot in the Design lens panel, each dot a component, the main
sequence as a diagonal, the two zones shaded. Clicking a dot selects the component on the
graph. This single chart summarizes the structural health of the whole system and has
been the signature visualization of this school of analysis since the 1990s.

### Blast radius as an interaction, not a report

Hold a modifier key (or toggle a mode) and hover a node: the transitive dependents shade
red, transitive dependencies shade blue, everything else dims. No numbers needed at
first; the *picture* of a blast radius is the fastest quality read there is. A per-node
count can live on the card afterward.

### Edge honesty

Edges currently distinguish structural from communication. Add the violation badges from
Tier 1 (cycle member, stability inversion, erosion) as small markers on the edge itself,
visible when zoomed in, aggregated into a count chip on the boundary when zoomed out,
following the worst-case-propagating roll-up rule.

### Review-mode integration

Every Design-lens finding should be one click away from becoming an annotation, with the
finding's evidence pre-filled. This is the shortest path from "the tool noticed" to "the
AI fixes it," and it is what distinguishes this feature from a static linter report: the
finding enters the same human-review, AI-implement loop the product is built around.

### The machine front door

Everything in Tier 1 belongs in `ai.json` and the MCP tools. An agent asked to modify a
codebase can query blast radius before editing, check whether it is inside a cycle, and
plan parallel work along real boundaries. This is the concrete mechanism behind the
claim that boundaries matter *more* under AI: they are the coordination primitive for
agent fleets, and today no tool hands agents that map.

---

## Part 4: What We Decline to Claim

To stay on the right side of the project's own epistemics, the following are explicitly
out of scope as claims, whatever the marketing temptation:

- **A single architecture score.** Averaging violations into one number is the purest
  form of lossy compression presented as truth. Rankings within a finding type are fine;
  a global grade is not defensible.
- **"Good" and "bad" as absolutes.** Every finding is a *tension*, not a verdict. A cycle
  in a deliberately co-released cluster may be fine. The interface should say "these can
  only change together; is that intended?", which is also the honest reading of the
  underlying theory: all of these principles are trade-off statements, not laws.
- **Runtime truth.** Static edges miss reflection, DI containers, service meshes, and
  feature flags. Every panel that renders graph-derived findings carries the same caveat
  the dependency count already carries: detected by method X, not exhaustive.
- **Intent.** The tool can show that a boundary is bypassed; it cannot know whether the
  bypass was a decision or an accident. That question is what the annotation system is
  for.

---

## Sources and Lineage

- Robert C. Martin, *Clean Architecture* (2017): Dependency Rule, component principles
  (REP, CCP, CRP, ADP, SDP, SAP), stability and abstractness metrics, main sequence,
  boundary anatomy, screaming architecture, humble object.
- Adam Tornhill, *Your Code as a Crime Scene* (2015) and CodeScene: hotspots, change
  coupling, behavioral code analysis over version history.
- John Ousterhout, *A Philosophy of Software Design* (2018): module depth, complexity as
  the metric that matters.
- Meilir Page-Jones: connascence taxonomy (strength, degree, locality).
- Simon Brown: C4 model's leveled abstractions and the "missing chapter" pragmatics of
  enforcing component boundaries (compiler-checked versus convention).
- Structured design lineage (Constantine, Yourdon, Stevens, Myers): coupling and cohesion
  as the original vocabulary all of the above refines.
- Neal Ford and Mark Richards, *Fundamentals of Software Architecture*: "everything is a
  trade-off," the framing behind Part 4.
