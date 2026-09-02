# SysCorpus comprehension-first viewer proposal

## Recommendation

Implementation and review are governed by the permanent
[Readability and usability standard](../standards/READABILITY-USABILITY-STANDARD.md),
including its distinct Fit versus Read graph contract and aspect-aware focus
geometry.

Build one adaptive product shell with two durable places:

1. **Overview** establishes what the system is, what it does, what is known, and where useful paths begin.
2. **Workbench** provides the existing depth: lenses, ranked lists, graph navigation, evidence, source detail, findings, review, sets, and directives.

They are not beginner and expert products. They are two apertures onto the same stable model. Every transition preserves subject, selected object, question, lens, semantic level, filters, tour step, and evidence state. A returning visitor can choose Overview, Workbench, or Resume as the default launch behavior.

The prototype implements three opening directions because they serve genuinely different arrival states:

- **System portrait — recommended default.** Best for an unknown visitor or a shared public link. It makes the product legible in five seconds, gives three useful first paths, and proves that depth exists without rendering it all.
- **Start with a question.** Best when the visitor has intent but lacks SysCorpus vocabulary. Questions deterministically dispatch into existing lenses and focused answers.
- **Atlas first.** Best for graph-literate technical visitors. It retains the analytical shell but starts at a bounded System semantic level rather than a repository root or full component graph.

All three lead to the same Workbench.

## What the product actually is

The redesign is grounded in the repository's canonical product commitments:

- A human-first, complete representation of a codebase or multi-repository system.
- One deterministic skeleton with optional, provenance-stamped AI interpretation.
- Every artifact accounted for; every meaningful claim drillable to evidence.
- Multiple question-shaped lenses with stable identity across them.
- Ranked answers before complete graphs.
- Guided tours and flows that build a situation model.
- Findings that are evidenced, confidence-bearing, verification-visible, and actionable.
- Review that closes the loop through annotations, sets, and structured directives for AI execution.
- A machine front door and MCP surface over the same facts.
- Static, local-first delivery with no model call at query time.
- A future two-tier delivery model: instant common projections plus a browser-queryable statement store.

This means the opening experience cannot be a marketing splash, a thin onboarding tour, or a prettier graph. It must establish comprehension and trust while preserving a direct route to serious work.

## Information architecture

### Global shell

Always available:

- SysCorpus identity and system switcher.
- Overview / Workbench switch.
- Search across concepts, components, files, symbols, and documentation contents.
- Compact trust state.
- Preferences.

### Overview

The default opening screen contains:

- One plain-language system statement.
- A bounded System portrait of four to seven architectural areas.
- Three primary journeys: core experience, capabilities, and ranked attention.
- A compact breadth ledger.
- Intent questions that dispatch into evidence-backed focused answers.
- A compact trust statement with a full ledger one action away.

It does not contain the full global lens switcher, the component tree, five status banners, a full inspector, or a long AI summary.

### Workbench

The Workbench keeps the product's real depth but gives every region one responsibility:

- Global rail selects the lens or assessment surface.
- Ranked panel answers “look here first.”
- Canvas shows relationships at the selected semantic level.
- Inspector explains the selected object and offers evidence-bearing continuations.
- One compact status strip exposes coverage, gaps, findings, and dependencies.

The current viewer should be evolved into this shell rather than replaced. Existing lens panels, graph, detail panel, search, tours, review, findings, supply chain, URL state, split loading, and local persistence remain valuable implementation assets.

## Return visits and advanced use

Avoid a binary “simple mode / advanced mode” that creates two products or makes evidence disappear. Use launch and density preferences:

- Start in Overview.
- Start in Workbench.
- Resume last lens, selection, semantic level, filters, and panels.
- Focused or Dense Workbench presentation.
- Preferred Overview direction.
- Remember navigation on/off.

Preferences persist locally. All shareable state also lives in the URL. The “show me the machinery” door remains present on every reduced surface.

## New projection: `orientation.json`

A new generated projection is justified. `manifest.json` is the workbench payload and `ai.json` is the machine front door. Neither is a stable, bounded contract for human orientation.

`orientation.json` should contain:

- System identity, scope, snapshot, and a deterministic system statement.
- Optional interpreted statement with evidence and verification state.
- Four to seven System portrait nodes and their aggregated, evidence-bearing edges.
- Stable targets from every portrait element into components, capabilities, concerns, entities, tours, findings, and lenses.
- A bounded question route table mapping ordinary-language intents to existing lens/view state.
- Representative journeys and a default path.
- Compact trust rollups that link to the authoritative detailed projections.
- Launch targets and provenance.

The example contract is in `orientation.v1.example.json`. This projection should be deterministic except for explicitly marked enrichment fields, byte-stable, small enough for first paint, and validated against the manifest in the publication gate.

### Why not derive all of it in the browser?

The browser can compute visual layout, but it should not invent architectural meaning. System grouping, representative paths, and answer routing need to be reproducible across the human viewer, `ai.json`, MCP, published demos, tests, and multi-repository composition. Generating the orientation projection keeps that meaning governed and testable.

## Lens decisions

### Do not create these lenses

- **Overview:** a front-door surface over several projections.
- **Questions:** a dispatcher into lenses, not a data representation.
- **Trust:** a cross-cutting evidence layer that must remain visible everywhere.
- **Dependencies:** currently answered jointly by Inventory, relationships, and Supply Chain; improve routing and labels before creating another lens.

### New or expanded views that are justified

1. **Security view.** The canonical vision requires it, and no current lens composes authentication, authorization, secrets, sensitive data, communication boundaries, dependency exposure, and security findings into one evidence-bearing view. It should land only when deterministic extraction and honest “not observable” states are specified.
2. **Support / Operations view.** The adopted stakeholder design already justifies a ranked surface for configuration, external dependencies, entry points, data handled, and “what could break at 3am.” This can begin as an audience preset over existing signals, with one new deterministic derivation; it does not require a separate ontology.
3. **System semantic level.** This is not another lens, but it is a required graph projection across Structure, Flow, Data, and multi-repository composition. Current repository-root presentation is not an adequate substitute.
4. **Queryable custom views — later.** The knowledge-graph direction correctly treats saved queries plus layout recipes as the generalization of lenses. Do not hard-code many more permanent lenses before the statement-store delivery spike proves this path.

## Data and state contracts

The front-door implementation requires:

- `orientation.json` as described above.
- Stable route state for subject, mode, question, lens, semantic level, object, tour step, filters, and selected set.
- Local preference state for launch behavior, density, panels, theme, and remembering navigation.
- Cross-surface identity resolution so a portrait node can become a ranked set or graph selection without losing context.
- Explicit provenance type on every front-door statement: deterministic, interpreted, inferred, unverified, or unavailable.

## Execution plan

### Phase 0 — instrument the baseline

- Run cold-start tasks against the current viewer with novice, technical outsider, returning expert, support, and reviewer missions.
- Record time to identify system purpose, first useful answer, first source evidence, and expert task completion.
- Capture viewport and banner-height budgets on desktop, laptop, tablet, and mobile.

### Phase 1 — orientation contract

- Specify `syscorpus.orientation/v1` and generate it from the fact store.
- Add deterministic System grouping and aggregated edge evidence.
- Add question-route validation against available lenses and targets.
- Cross-check trust rollups against manifest, coverage, findings, and SBOM in the publish gate.

### Phase 2 — shell and Overview

- Introduce Overview / Workbench routing around the current application.
- Build the System Portrait opening direction first.
- Add the compact trust ledger and universal search.
- Implement launch preferences and URL state.

### Phase 3 — focused answers and journeys

- Add Question entry backed by the generated route table.
- Reuse Tours and lens panels for focused answers.
- Preserve question, selection, lens, and tour step into the Workbench.

### Phase 4 — Workbench re-composition

- Consolidate status banners into one trust strip.
- Move the lens selector into a stable rail.
- Require every non-Structure lens to open with a ranked panel.
- Add System / Domain / Component semantic levels.
- Reduce the inspector's opening state to role, evidence state, four useful measures, and three continuations; keep full details one action away.

### Phase 5 — stakeholder and missing views

- Land Support / Operations as an audience preset and ranked view.
- Design and evidence-gate the Security view.
- Validate the “show me the machinery” transition on the same stable object.

### Phase 6 — migration and validation

- Preserve old deep links and annotation identities.
- Test split and monolithic projections, publications, solutions, mobile sheets, live refresh, and reduced-motion behavior.
- Repeat the cold-start tasks and compare against Phase 0.
- Roll out Overview as the default for first visits while respecting stored Workbench/Resume preferences.

## Acceptance criteria

- In five seconds, a cold visitor can state what the system is and see that the map is deep and evidence-bearing.
- In thirty seconds, the visitor can name three major areas and open one useful answer.
- A returning expert can land in the remembered Workbench state with no orientation gate.
- Search accepts domain language and lands on a concept, component, file, symbol, or documentation passage.
- Every front-door statement exposes evidence state and resolves to stable projected identity.
- No opening viewport contains simultaneous summary, coverage, gap, finding, dependency, tour, and status banners.
- A journey opened from Overview arrives in the Workbench with the correct lens, semantic level, object, and step.
- Reduced presentation never deletes facts or blocks the machinery door.
- Mobile provides Overview and focused answers as first-class surfaces; it does not squeeze the entire desktop graph onto a phone.

## Prototype scope

This prototype is intentionally static and dependency-free. It demonstrates:

- Three opening directions.
- Overview / Workbench continuity.
- A guided learning-loop journey.
- Question-to-answer routing.
- Search and trust surfaces.
- Node selection and inspector continuity.
- Lens switching.
- Persistent launch, overview, density, navigation, and evidence preferences.

It does not implement real analyzer integration, graph layout, source drill-in, authentication, collaboration, or production accessibility validation.
