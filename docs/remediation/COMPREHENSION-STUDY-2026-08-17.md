# Cold-Start Comprehension Study (2026-08-17)

Findings and strategy from a three-persona, cold-start field test of the claim at the
center of VISION.md: "A person in technology who does not know the codebase or even
the language must navigate efficiently, figure out how it works, and start finding
issues with no AI required."

## Method

- Target: the flagship UnaMentis demo dataset (254 components, split mode,
  AI-enriched), mirrored byte-for-byte from solution-explorer.unamentis.org and
  served locally under a fresh production build of `main` (viewer v1.2.0).
- Three personas ran genuinely cold, each on an isolated port with cleared storage,
  each experiencing only what the site offers. None read repo files or docs.
  - **Maya**, senior backend engineer, has never written Swift. Mission: understand
    the system, answer five concrete questions, plan a first bug investigation.
  - **Doug**, VP of Technology Operations, last wrote code 15 years ago. Mission:
    stakeholder comprehension, criticality, dependencies, a founder-ready summary,
    plus a mobile hallway check.
  - **Priya**, staff engineer and AI-tooling power user. Mission: test every
    pathway: UI, search, machine endpoints (llms.txt, ai.json), deep links, and the
    review-and-export loop, plus cross-pathway consistency.
- The orchestrator then verified every load-bearing claim independently: against the
  dataset JSON, against viewer and analyzer source, and first-hand in the browser.
  Findings below marked VERIFIED carry a root cause; persona-reported items that
  were reproduced or corroborated are marked CONFIRMED.
- Evidence: three journals, three findings documents, 124 screenshots, in the
  session scratchpad under `persona-runs/20260817/`.

## Verdict

**The claim substantially holds. All three personas, independently, graded the
one-sitting comprehension claim B+.** In 60 to 90 minutes each persona built an
accurate, specific, gradeable mental model of a 254-component, six-language,
multi-client system: voice-first AI tutoring platform, iOS and watch clients, two
Next.js frontends, aiohttp management server on :8766 with WebSocket audio, Rust
usm-core on :8767, Postgres, Lambda, and the cloud/self-hosted/on-device provider
routing strategy. Maya produced a credible, layered starting plan for a realistic
bug ("audio drops mid-lesson") without reading a line of Swift. Doug, a non-coder,
delivered a founder-ready summary that was correct in every checked particular.

**What blocks an A is not architecture. It is a short, fixable list of trust and
navigation defects.** Every persona lost the same points for the same two reasons:

1. The tool states false things in the same confident voice as true things, so a
   careful reader enters verify-everything mode, and that tax is real.
2. The most important questions ("who talks to whom," "what is critical," "what
   does this depend on") have no first-class surface where a newcomer looks first.

The consensus one-liner: an expert-shaped map with a few confident hallucinations
and no executive rollup. Both are addressable with far less effort than what built
the guts.

## What worked (protect these)

These surfaces did the heavy lifting in every session and must not regress:

- **The pinned AI summary banner and 5-step tour.** Every persona had the elevator
  pitch in under two minutes. Tour step 2 is the single best onboarding surface.
- **Device-frame node rendering.** iPhone bezels, watch crowns, terminal chrome:
  the top-level map is legible before any text is read.
- **The detail panel.** Real READMEs and CLAUDE.md rendered in-panel, endpoint
  lists with file:line provenance and TESTED BY links, the Data tab with 28 typed
  tables linked to schema.sql line numbers ("instantly credible," Doug).
- **Search as a navigation spine.** 14k entries, ranked, drill-and-highlight on
  Enter. Doug used it as his dependency-audit tool.
- **The incoming-links view** on the management server: every caller with protocol,
  auth flavor, and concerns. Maya: "the single most informative screen in the
  product."
- **The machine front door's design.** ai.json's endpoint map, walk orders, and
  token-economy contract let Priya answer "how does login work" in 4 fetches
  (~40 KB). The ergonomics are right; the metadata truthfulness is not (S3).
- **The review-loop export.** 4 annotations produced a 6.5 KB structured prompt
  pairing verbatim human intent with machine-gathered context. Priya's judgment:
  a coding agent could act on it without clarifying questions, learned with zero
  documentation.
- **URL state.** Component, tab, drill path, lens, flow, and step all live in the
  URL; "Copy link to this component" works.

## Findings, ranked

### S1. Cross-level edges are silently dropped, so the client-to-server edge is invisible where everyone looks first. VERIFIED

The top-level graph draws no edge between the iOS client and the management server,
and the iOS client's own Links tab shows 27 of 28 outgoing links as bare "uses"
with no protocol. The truth (WebSocket from services/stt and services/tts, HTTP
:8766 from services/knowledgebowl) exists only in the manifest and in the
management server's incoming list, three levels deep on the receiving end. Maya
lost 20 minutes; a less persistent reader would conclude the iOS app only talks to
a log server.

Root cause: `getComponentRelationships` in `viewer/src/store.ts` (~line 2132)
filters relationships to `visibleIds.has(r.source) && visibleIds.has(r.target)`,
exact ids only. Any edge between descendants of two visible nodes is dropped.

Fix shape: map each relationship endpoint to its nearest visible ancestor, merge
duplicates, drop self-loops, and label the aggregate edge with the union of
protocols (with a count). Apply the same ancestor roll-up to the Links tab so both
sides of an edge tell the same story.

### S2. The analyzer misclassifies, and the viewer presents every classification with unearned confidence. VERIFIED (each instance checked in data)

The instances the personas hit, all real in the shipped demo dataset:

- `unamentis/scripts` (a build/test automation directory) is presented as "Remote
  Log Server, Service, Ruby, :8765". Two identities fused into one node; Maya could
  not tell which facts belong to which. A `log_server.rb` inside the directory
  evidently drove name, type, and port for the whole component.
- `unamentis/server/management/tests` (a 50-file pytest suite) is classified "API
  Server" with framework aiohttp and endpoints GET /test, GET /get, POST /post
  extracted from test fixtures. Sibling `tts_cache` similarly. The iOS test tree is
  correctly tagged as tests, so the capability exists and is inconsistently applied.
- A markdown docs tree renders as "API Server, aiohttp, Plugin Architecture"; a
  markdown-language component wears a "Desktop App" frame.
- The management server's hover card lists exactly one environment variable for the
  whole server: `CFG_SCALE`, a misdetected image-generation parameter.
- Database Data tab shows garbled column fragments ("PT4H: LANGUAGE", "course: IS",
  "true_false: QUESTION") among otherwise excellent schema rows.
- The iOS client shows a UIKit badge while the AI text says "built with SwiftUI".
- Leftover `/api/foo` scaffolding endpoints are listed uncritically among 265 real
  ones.

The compounding defect: TESTED BY links carry INFERRED confidence labels, but type,
framework, port, and endpoint classifications carry no confidence marking at all.
One "Remote Log Server" costs ten minutes of confusion and permanent suspicion of
every other label ("forces verify-everything mode," all three personas).

Fix shape, two independent tracks:
1. Analyzer accuracy: exclude test directories from endpoint/API-server promotion,
   scope a marker file's identity (name, port, type) to itself rather than its
   whole directory when siblings dominate, fix the SQL column regex, filter
   fixture/sample endpoints and env vars.
2. Honest presentation: classifications get the same confidence treatment TESTED BY
   already has, and low-confidence promotions degrade to neutral types instead of
   confident wrong ones.

### S3. The machine front door lies about the dataset. VERIFIED

`architecture/ai.json` on the deployed demo asserts `dataset.enriched: false` and
`ai_enhance present: false` while manifest.json carries ai_enhance on the root and
on 250 of 254 components, and the UI is saturated with AI Insights. An agent
consumer, the exact audience that cannot hover to double-check, is told the most
valuable layer does not exist.

Root cause: `analyzer/project/frontdoor.py` computes `enriched` at projection time,
and the deploy pipeline's `scripts/merge-ai-enhancements.py` step runs afterward and
never regenerates the front door. The deployed ai.json is truthful about the
pre-merge state of a file that no longer exists.

Related count drift, same class: the header and stats say 175 components (from
`scanner.py`'s component map at scan time) while the manifest tree and the search
index both contain 254 (derived nodes added later are never reconciled); AI
Insights prose says "69+ HTTP endpoints" for the server the Capabilities tab counts
265 for (numbers baked into enrichment prose drift from analyzer facts);
`manifest_sections` omits that component nodes embed capabilities, endpoints, and
testing data, so the richest content is undocumented to agents.

Fix shape: regenerate the front door (and any stats it repeats) as the last step of
the deploy, after enrichment merge; derive one component count from the projected
tree and use it everywhere; stop baking mutable counts into enrichment prose (or
post-check prose numbers against facts at merge time); document the embedded
sections.

### S4. Review mode captures selection and its panel double-mounts. VERIFIED

While review mode is on, `selectComponent` (store.ts ~line 969) deliberately does
not open the detail panel, so clicking a tree row or node appears dead until review
is dismissed; the Review Summary effectively owns the right rail, reopening over
deep-linked panels. The panel is also mounted twice in the DOM (desktop rail,
App.tsx ~line 937, and the mobile bottom sheet, ~line 141), so locators and
assistive tech see duplicated "Copy All"/"Clear All" controls, and each mount holds
its own arm-to-confirm state for Clear All, which reads as a silent no-op.

Fix shape: in review mode, selection should still show details (annotation is an
overlay action, not a replacement for comprehension); render one panel instance per
form factor; replace the timed arm-to-confirm with an explicit confirm affordance.

### S5. Double-click drill is broken at top level, and the tour teaches it. CONFIRMED first-hand

Real mouse double-clicks on hero nodes (iOS client, management server) do not
drill; the handler exists (`ComponentNode.tsx` line 831) and drill works via the
hover "drill into" button, so this is an event-delivery defect, likely the
selection re-render or React Flow's zoom handling swallowing the second click. A
core interaction advertised by the tour failing on first use is a
first-five-minutes trust hit.

### S6. The first executive questions have no rollup surface. CONFIRMED by two personas independently

"Show me everything critical" and "show me every external dependency" have correct
per-component answers (criticality tags, EXTERNAL SERVICES chips) but no aggregate
surface anywhere. Doug: "Eighty percent of my clicking was manually building
exactly that screen." This independently re-derives what VISION.md already
mandates: stakeholder views and the SBOM/supply-chain view. The study confirms
demand from the exact audience those views target.

### S7. Search result landing and edges of search quality. CONFIRMED first-hand

- Clicking a file result opens the parent component's panel (not the file), drops
  drill context, and leaves a single orphan node on the canvas.
- No relevance floor: "billing", absent from the codebase, returns fuzzy-subsequence
  noise instead of "no results", which quietly poisons trust in real results.
- API endpoints are not indexed ("/ws/audio" finds nothing relevant).

### S8. Presentation-of-truth defects that spend trust. CONFIRMED

- The headline "3,767,918 lines" is 87% JSON data files; no first-party versus
  data/vendored breakdown is offered. Two personas independently refused to believe
  it, which is worse than the number being smaller.
- "Generated 7/22/2026" was 26 days stale, with no explanation that the source repo
  simply had not changed (verified: last UnaMentis commit is 7/22). Fresh-looking
  data with an old date reads as a broken pipeline to a skeptic.
- The breadcrumb path renders "unamentis / unamentis" (repo name equals directory
  name), reading as a bug.
- Coverage: "Coverage unavailable for this dataset" on the flagship demo (known
  multi-repo ledger gap, tracked as P4-7 Discovered).

### S9. Interaction and polish nits (each small, several per sitting). CONFIRMED

Aggregate "31 Modules" expansion scatters ~50 unreadable chips with no auto-fit;
dismissing the summary banner is one misclick with no in-session restore; the lens
switcher is a native select that looks inert; panel can show a component the canvas
does not; Esc does not close the Help modal, and the modal swallows Cmd+K; a
recurring console SyntaxError from a querySelector built with an invalid id;
back/forward history sticks after one hop; mobile shows an empty "Select a
component" sheet after drilling; search input ignores select-all.

## Grading the personas' mental models

All three models were checked against the manifest and detail data. Accuracy was
high: components, ports, protocols, provider matrix, data layer, and content
pipeline were correct in every verified particular. The two shared errors were
both induced by tool defects: the log server identity (S2) and initial
under-estimation of client-to-server coupling (S1). The comprehension claim
survives contact with reality; the tool's mistakes were the personas' mistakes.

## Strategy

Three thrusts, ordered by leverage per unit of work. The guts (analysis
completeness, lazy loading, enrichment) needed no defense in any session; the work
is all at the presentation and trust layer.

### Thrust 1: The map must never lie (S1, S2, S3)

The single theme behind every lost grade point. Concrete, bounded work:

- Edge roll-up to nearest visible ancestor, both on canvas and in the Links tab.
  One store function plus label merging.
- Front-door regeneration after enrichment merge in the deploy path; one component
  count derived from the projected tree used by header, stats, and ai.json.
- Analyzer accuracy pass: test-directory endpoint suppression, marker-file identity
  scoping, SQL column parsing, fixture endpoint/env-var filtering.
- Confidence marking on classifications, reusing the existing INFERRED treatment.
- Prose/fact reconciliation at merge time (flag enrichment prose whose numbers
  contradict analyzer facts).

### Thrust 2: Answer the first questions first (S6, S8)

- A rollup surface: every critical/important component with its one-line purpose,
  plus the external-dependency inventory (vendors, ports, env vars). This is the
  first deliverable slice of VISION.md's stakeholder views and SBOM mandate, and
  two personas independently specified it as their number one ask.
- Honest headline numbers: split code lines from data/vendored lines in the header
  stats; explain snapshot age ("source unchanged since 7/22") instead of wearing
  it silently.
- Banner restore affordance; breadcrumb dedup for repo-equals-directory names.

### Thrust 3: Interaction hardening (S4, S5, S7, S9)

Mostly small, independent fixes: double-click drill event handling, review-mode
selection model and single-mount panel, search file-result landing (open the file
detail, keep drill context), a search relevance floor, endpoint indexing, aggregate
expansion auto-fit, Esc/shortcut hygiene, the querySelector error, mobile
empty-sheet.

### Sequencing recommendation

Thrust 1 first, and within it the front-door/count fixes (hours, pipeline-level,
zero UI risk) before the edge roll-up (the highest-leverage viewer change), before
the analyzer accuracy pass (broadest). Thrust 2's rollup surface is the one item
that needs design intent from the owner before code. Thrust 3 can proceed as
independent small PRs in any order, suitable for delegation.

### Decisions (adopted by the owner, 2026-08-17)

1. **Rollup surface: both the Inventory lens and the expanded summary banner.**
   The Inventory lens is the architectural home (per LENS-DESIGN.md I11/I12): it
   must be complete in the story it tells for the given solution and built so the
   concept can expand as the stakeholder-view roadmap matures (Security,
   Supply-chain/SBOM views will reuse the pattern). The summary banner grows an
   expandable rollup that starts expanded for a new user, answering the first
   questions right up front. Rationale: the product serves different audiences
   through different pathways, so the same answers appear where each audience
   looks. The dedicated dashboard page is NOT built now; the concept is kept on
   file (this document, Strategy Thrust 2) for future exploration as a possible
   executive landing surface.
2. **Classification: resolve-or-flag, never publish uncertainty.** "Low
   confidence" is a pipeline problem, not a UI state. Three layers: deterministic
   parser fixes outright; the AI enrichment pass becomes a verification gate
   contracted to confirm, correct with cited evidence, or file a gap for every
   identity claim (name, type, framework, port, endpoints, env vars); residual
   unknowns land in the honest-gaps record. Deploy behavior: publish with loud
   gaps (deploys never wedge; gaps are surfaced prominently to the owner).
   Confidence labels on nodes are explicitly rejected.
3. **Line-count policy (decided, execute with Thrust 2).** Counts stay in the
   header, transparent. Files classify as Code, Data, Docs, Config, with
   generated/vendored bucketed separately (Linguist/cloc conventions). Gray zones
   resolve by role: structured files under data-shaped paths or above a size
   threshold are Data; migrations are Code; lockfiles are generated. Header leads
   with Code lines, other buckets adjacent, per-language breakdown one hover
   away, all backed by the coverage ledger.
4. **Tracking** (TASKS.md phase vs. focused engagement): deferred by the owner.

## Remediation status (branch `wt/comprehension-fixes`, 2026-08-17)

Every finding below was fixed and verified on this branch. Nothing is merged or
pushed; `main` is untouched.

| Finding | Status | Verified by |
|---------|--------|-------------|
| S1 cross-level edges dropped | Fixed | Live dataset: top-level edges 5 -> 36, iOS-to-management now drawn |
| S2 misclassification | Fixed | Re-analyzed UnaMentis: scripts/docs/tests no longer hero types, CFG_SCALE gone, zero garbled SQL columns |
| S3 front door lies / count drift | Fixed | Byte-identical no-op refresh test; one tree-derived count |
| S4 review captures selection, double mount | Fixed | Browser: selection shows detail in review mode; one panel per form factor |
| S5 double-click drill broken | Fixed | Browser: real mouse double-click drills (8 nodes -> 6) |
| S6 no rollup surface | Fixed | Inventory lens + expanded banner rollup, live |
| S7 search landing / relevance / endpoints | Fixed | Browser: "billing" -> "No results"; "/ws/audio" -> management |
| S8 headline numbers, breadcrumb | Fixed | Code/data/docs/config taxonomy in header; breadcrumb dedup |
| S9 help Escape, banner restore | Fixed | Browser: Escape closes help; "Show summary" restore |

Aggregation (the drill-level visibility rule) was investigated properly after
the first report and turned out to be worse than a readability nuisance: the
rule used SIZE as a proxy for IMPORTANCE ("not a hero type, no children, fewer
than ten files"), which on the iOS client buried 31 of 44 children behind one
box, ten of them tagged critical (STT, LLM, Voice, Session, Context,
Curriculum, Config, Models, Protocols). Expanding put 45 nodes on the canvas at
minimum zoom, 7px tall. Owner decision 2026-08-17 (options A + B, with the node
count adjusting to the viewport rather than a fixed number), now implemented:
visibility ranked by criticality then connections then size with hero types
always shown; the node count derived from the actual canvas and remeasured on
every change; a bounded shrink-only loop that measures the zoom each layout
achieved and reduces the budget until readable; and aggregate expansion opening
a ranked, filterable member list in the panel instead of adding nodes. Measured
after: laptop 7 nodes at 0.72 zoom (179x79px), large display 10 nodes at 1.01
zoom (251x97px). Known remaining case: a phone shows 8 hero nodes at 0.23 zoom,
because heroes are never aggregated; the two ways to close it are in the
decision document.

Deliberately NOT fixed, and why:
- **The console `querySelector` SyntaxError.** Not reproducible from any call
  site in `viewer/src`; it appears to originate in a dependency. Chasing it
  without a reproduction would be guesswork.
- **Snapshot staleness.** The 7/22 date is honest: the UnaMentis repo's last
  commit is also 7/22 (verified). What is missing is an explanation in the UI,
  which is a copy decision.

Test posture on the branch: Python 1451 passed / 3 failed, viewer 357 passed /
86 failed. Every failure is pre-existing on `main` and unrelated: the two MCP
failures and the 86 viewer failures reproduce identically on a clean `main`
(failing-file sets compared and identical), and the coverage-ledger failure is
an artifact of running the suite inside a git worktree, where `.git` is a file
rather than a directory (proven by running the same analyzer code against both
checkouts). Lint clean on both sides.

## Study artifacts

- Persona journals, findings, and 124 screenshots: session scratchpad,
  `persona-runs/20260817/{p1,p2,p3}/`.
- Verified root causes: `viewer/src/store.ts` 2132 (S1), 969 (S4);
  `viewer/src/App.tsx` 141/937 (S4); `viewer/src/components/ComponentNode.tsx` 831
  (S5); `analyzer/project/frontdoor.py` 117 (S3); `analyzer/scanner.py` 224 (S3
  count); dataset instances for S2 checked in the mirrored demo JSON.
- The mirrored demo dataset and a running local instance were left on
  localhost:5300 for the owner to inspect.
