# SysCorpus front door and adaptive viewer execution plan

Status: **COMPLETE — historical execution record**

Integrated: `main`

Prototype: `docs/front-door-prototype/`
Design authority: `docs/front-door-prototype/DESIGN-PROPOSAL.md`

Current interface policy: Overview is the primary/default SysCorpus interface. The internal `workbench` route is deprecated and retained temporarily for historical comparison, compatible deep links, and validation. This file records the implementation path; it is not a second active product plan.

## 1. Outcome

Ship one production viewer with two durable apertures over the same projection:

- **Overview** establishes identity, purpose, system shape, useful questions,
  trustworthy scope, and a first journey.
- **Detailed workspace** preserves the full expert surface: ranked lenses, graph,
  inspector, evidence, source, findings, review, sets, directives, and search.

The transition is lossless. Subject, question, lens, semantic level, selected
object, tour step, filters, and panels are route state. Start posture, density,
theme, appearance, and restore behavior are user preferences.

The work is additive. Old projections open into a generated fallback Overview.
Old deep links still open the deprecated detailed workspace at the requested object. The same stable
IDs continue to key annotations, sets, tours, and URLs.

## 2. Product invariants

1. Humans first; agents consume the same facts through their own front door.
2. One deterministic skeleton, optional provenance-stamped interpretation.
3. Every artifact accounted for; every claim drills to evidence or says that it
   cannot.
4. Rank before rendering the complete graph.
5. Same object, every lens, one identity.
6. Questions are deterministic UI routes, not an ungrounded chat surface.
7. Overview, Questions, and Trust are not lenses.
8. Reduced presentation never deletes data and always offers the machinery door.
9. No model calls at query time.
10. Static and local-first delivery remains intact.

## 3. Historical worktree and integration strategy

The following bullets describe the completed implementation workflow and are retained only as a record.

- Develop and test on `wt/frontdoor-production` only.
- Preserve the existing theme implementation as the baseline; do not rebuild it
  inside front-door components.
- Keep the current viewer components operational and recompose them through
  routing and shell changes.
- Make projection additions optional and additive.
- Commit by independently reversible slices: theme baseline, projection
  contracts, Overview shell, Workbench composition, new lenses, verification.
- Rebase or merge current `origin/main` only at a controlled integration point;
  never mix unrelated live-run or licensing changes into this branch.

## 4. Theme wardrobe

The supported production set is exactly five themes:

1. **Signal** — original dark neon control room.
2. **Ledger** — paper, engineering, and boardroom.
3. **Atlas** — parchment map.
4. **Fold** — cut-paper diorama.
5. **Lumen** — bioluminescent living system.

Every theme has light and dark variants, a canvas-ground definition, a native
appearance, a hero-glow policy, and the same semantic hooks. Themes are pure
presentation; no theme branches data, navigation, or layout meaning. The
Overview and every new lens use the existing `--se-*` and Tailwind variable seam.

Acceptance:

- All five are selectable on desktop and mobile.
- Selection and appearance persist independently.
- Overview, drawers, ranked panels, new lenses, graph, inspector, and overlays
  render through the theme seam.
- No externally hosted font is required for core operation.
- Reduced motion suppresses theme motion.

## 5. Generated projection contracts

### 5.1 `orientation.json`

A small first-paint human orientation document:

- identity, scope, snapshot, repository or solution kind;
- deterministic system statement;
- optional interpreted statement with provenance;
- four to seven system portrait groups;
- aggregated, evidence-bearing group edges;
- bounded question routes into existing lenses and surfaces;
- representative tours and a default path;
- trust rollups linked to authoritative artifacts;
- stable launch targets.

The generator must be byte-stable. It may group from component roles/types and
existing concern, capability, entity, and tour membership, but it may not invent
a domain label without marking it interpreted.

### 5.2 `support.json`

The deterministic Support and Operations view contract:

- required configuration keys and their owning components;
- externally controlled services and protocols;
- ticket-facing entry points from capabilities;
- data handled from entities and access edges;
- ranked “what could break at 3am” members;
- explicit evidence and method caveat.

Error-handling-density, uptime, incident probability, and repair-cost scores are
forbidden.

### 5.3 `security.json`

The evidence-honest Security view contract:

- authentication and authorization mechanisms only when evidenced;
- credential-configuration surfaces, never secret values;
- communication boundaries and observable transport security;
- security-relevant data entities and access paths;
- security-related dependencies and findings;
- an explicit list of questions not observable from repository evidence.

It is not a security verdict, audit, compliance score, or guarantee.

### 5.4 Publication gates

- Sidecars and manifest summaries agree.
- Every stable target resolves.
- Counts match authoritative manifest, coverage, and SBOM sections.
- Optional interpreted statements carry provenance and verification state.
- A sidecar emitter failure becomes one honest producer gap.

## 6. Viewer architecture

### 6.1 Experience state

Add an experience slice to the existing Zustand store:

- `experienceMode`: `overview | workbench`;
- `overviewDirection`: `portrait | questions | atlas`;
- `startView`: `overview | workbench | last`;
- `workbenchDensity`: `focused | dense`;
- `rememberNavigation`;
- `trustOpen` and `preferencesOpen`.

Preferences use a versioned local-storage object. Route state remains in the URL.
An old URL containing lens, object, file, symbol, or tour state overrides the
Overview default and opens Workbench.

### 6.2 Overview shell

Build production components, not a pasted prototype:

- `ExperienceSwitcher` in the global header;
- `SystemOverview` container;
- `SystemPortrait` using stable targets from `orientation.json`;
- `QuestionEntry` and `FocusedAnswer`;
- `TrustLedger`;
- `ViewerPreferences`;
- `OverviewSearchEntry` reusing the production search overlay;
- `OrientationJourney` reusing production tours when available.

No hard-coded UnaMentis content is allowed in production components. The
prototype remains a design fixture only.

### 6.3 Workbench composition

- Keep the existing graph and detail machinery.
- Add a stable lens rail.
- Keep every non-Structure lens’s ranked panel.
- Replace stacked opening banners with one compact trust strip.
- Move long architecture summary content into Overview and on-demand detail.
- Add explicit System, Domain, and Component semantic level state.
- Keep tree and inspector collapsible and resizable.
- Focused density favors canvas; Dense gives ranked and inspector regions room.
- Provide a persistent return to Overview without resetting Workbench state.

### 6.4 Mobile

- Overview and focused answers are primary mobile surfaces.
- Questions become a list; portrait becomes a vertical relationship map.
- Workbench uses the existing bottom-sheet model.
- Do not compress the complete desktop atlas into one phone view.

## 7. New lenses and views

### 7.1 Support and Operations

Register a stable `support` lens when `architecture.support` contains evidence.
Its ranked panel starts with “what could break at 3am,” then configuration,
external reliance, entry points, and data. Every row selects a stable component
or opens exact evidence.

### 7.2 Security

Register a stable `security` lens when `architecture.security` contains evidence.
Rank confirmed mechanisms and exposed boundaries separately from inferred leads.
Keep “not observable from this repository” visible. Never collapse unknown into
safe.

### 7.3 System semantic level

This is shared graph state, not a new lens. Structure, Flow, Data, Support,
Security, and multi-repository solution views may each provide a System-level
projection. Domain and Component levels retain stable identity.

### 7.4 Later custom views

Do not hard-code an unbounded lens catalog. After the browser-queryable statement
store spike, generalize a custom view to a saved query plus layout recipe.

## 8. Implementation slices

### Slice A — baseline and plan

- Isolated worktree and branch.
- Preserve prototype and four implemented themes.
- Add this execution plan.
- Add Lumen and theme regression coverage.

### Slice B — projection layer

- Implement orientation, support, and security builders and emitters.
- Add paths to `ProjectionResult`.
- Emit before manifest and monolith so gaps are represented.
- Add deterministic, old-dataset, and sidecar-failure tests.

### Slice C — types, data loading, and fallback

- Add TypeScript contracts.
- Fetch optional orientation, support, and security sidecars in split mode.
- Prefer manifest-embedded summaries; sidecar detail may lazy-load.
- Build a deterministic client fallback for old projections.

### Slice D — Overview production UI

- Add experience state and migration.
- Implement System Portrait, Question entry, Trust, preferences, and journey
  continuity.
- Reuse search, tours, themes, and URL state.

### Slice E — Workbench re-composition

- Introduce the lens rail and compact trust strip.
- Gate legacy opening banners behind an expanded trust or details action.
- Add semantic-level selector and density behavior.
- Preserve legacy deep links and current graph behavior.

### Slice F — Support and Security

- Register lenses and build ranked panels.
- Wire row-to-graph and row-to-evidence behavior.
- Add question lists and routing from Overview.

### Slice G — verification and rollout

- Unit and integration tests.
- Production build and lint.
- Projection parity and deterministic tests.
- Desktop, laptop, tablet, and mobile visual pass across five themes.
- Keyboard, contrast, reduced-motion, focus, and screen-reader-name checks.
- Cold-start and expert-return task battery on multiple projections.

## 9. Test matrix

### Projection

- identical input produces byte-identical sidecars;
- empty and old datasets degrade without false claims;
- partial enrichment stays explicitly partial;
- unverified findings remain unverified;
- multi-repository members remain separately ledgered;
- missing sidecar records one producer gap and leaves the main projection valid.

### Viewer

- first visit opens Overview unless URL intent says otherwise;
- Workbench and Resume preferences survive reload;
- question route preserves lens, object, and tour state;
- trust counts agree with the loaded architecture;
- all five themes reach all new surfaces;
- old manifests without orientation, support, or security still work;
- annotation and selection-set identities do not change;
- split detail loading, live refresh, search shards, and publication metadata work.

### Human tasks

- cold visitor explains purpose and three major areas;
- technical outsider follows a core flow to source;
- returning expert resumes a lens and selected object;
- support engineer finds required configuration and external reliance;
- reviewer opens a ranked finding and exports an actionable directive;
- security reviewer distinguishes observed controls, inferred leads, and unknowns.

## 10. Rollout

1. Ship additive projections and hidden viewer support.
2. Enable Overview by query flag on private dogfood and two materially different
   demo subjects.
3. Run cold-start and returning-expert tasks.
4. Make Overview the first-visit default for publications; retain Workbench and
   Resume preferences.
5. Keep a temporary `classic` query escape during the first production cycle.
6. Remove the escape only after deep-link, annotation, search, tour, mobile, and
   live-refresh parity is measured.

## 11. Definition of done

- Five production themes cover every new surface.
- Overview works with rich and old projections.
- `orientation.json`, `support.json`, and `security.json` are deterministic and
  publication-validated.
- Overview routes preserve context into Workbench.
- Support and Security are evidence-bearing stable lenses.
- Stacked opening banners are replaced by one compact trust surface.
- Existing expert workflows, deep links, annotations, sets, directives, split
  loading, and live refresh pass regression tests.
- Multiple materially different projects complete both cold-start and expert
  task batteries before the feature becomes the publication default.
