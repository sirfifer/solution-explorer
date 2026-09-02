# VS Code demo gate, 2026-09-02: what was wrong, what changed, what waits for the re-parse

Answers the Demo Gate directive (artifact "VS Code Demo Gate", crawl run
`2026-09-02T20-41-56-206Z-crawl-vscode-remote`). Branch `wt/vscode-demo-gate`,
worktree `/Volumes/Studio/dev/.worktrees/solution-explorer--vscode-demo-gate`.
Served bundle for the runs below: `http://127.0.0.1:5175` (VS Code, projection
`.testboard/live/vscode-full-20260831-5f6a814/viewer-projection` with
`demos/review-corrections/vscode.json` applied) and `http://127.0.0.1:5176`
(UnaMentis iOS reviewed snapshot, the no-regression control).

## The split the owner asked for

Four buckets, not two. The directive assumed that anything wrong in the data
needs the whole expensive parse-plus-enrichment again. It does not.

| Bucket | What it costs | What went here |
|---|---|---|
| A. Viewer or crawl code | minutes, no data touched | P1, P2, P3 (viewer half), P4, P5, H1, H2, drill-hint occlusion, provenance path |
| B. Deterministic sidecar or assembly step | seconds to minutes, no model calls | P3 (orientation.json), security view built from refuted edges, portrait grouping, tour wording, bundle license and notice |
| C. Deterministic re-parse of the same commit | about two minutes of processing, zero model calls, enrichment re-attaches | content typing, `script` typed cli-tool, entity naming, `%description%`, refuted edges, workflow files, placeholders, capability test links, author emails |
| D. Paid enrichment | model spend | three text defects baked into enrichment rows, and finishing the incomplete run |

Bucket C exists because enrichment rows are keyed by component id plus a
digest of the component's member files, never by symbols, type or name
(`analyzer/store/schema.py`, `analyzer/enrich/digest.py`). Measured on a copy
of the VS Code store (17,120 rows): a type or name change invalidates 0 rows,
rewriting every symbol invalidates 0, splitting one component invalidates 13,
renaming an id orphans its rows. Every v2 projection re-applies the store
(`analyzer/project/pipeline.py`, `apply_enrichment_overlay`). A full reprojection of
the same commit under the venv interpreter took about two minutes and
produced the same 151,134 symbols and 5,454 relationships against 5,453
(one new edge); the per-row survival diff of that run was not completed. The
reprojection must run under the venv interpreter; the Homebrew `python3` has
no tree-sitter and silently produces 0 symbols and 0 relationships while
reporting 100% coverage, which is item 1 below. Total VS Code enrichment spend to date is about $236 (the original
run paused at $141.86, the continuation added $94.19), not the $94 the latest
run record shows on its own.

## Phase 1: the instrument

**H1, support and security judged unwarranted on every run.** The contract
read `manifest.support` and `manifest.security`, which the app merges from
`support.json` and `security.json` at load time. `loadContract` now merges the
two sidecars the same way, and the remote mirror downloads them. Both remain
optional. UnaMentis was never affected: its bundle ships neither sidecar, so
the data and the DOM agreed by accident. Its verdicts stand.

**H2, the root-level assertion could not fail.** `graph.spec.ts` now asserts
the other direction under a new rule id, `graph.missing_node`: a root that
renders is accounted for; a root the graph promoted must have every non-blob
child rendered, inside a rendered aggregate (aggregate nodes now publish
`data-members`), or represented by a rendered descendant. Two expectations
the fix to P1 exposed were also wrong: the drill journey treated a promoted
single root as a hop, and the tour spec expected a step onto a promoted root's
child to drill into the root. Both now accept the top level.

**Not in the directive.** `control.py run crawl` posts to the control plane
on port 4200, which executes the harness from the checkout it was started in
(the relicense worktree, on main). A crawl requested from another worktree
runs main's harness against the requested URL. The runs below were made with
Playwright directly in the branch worktree.

## Phase 2: the product

**P1, one node at the top level.** Cause established, and it is neither of the
two candidates the directive named. The top level is built by a client/server
model (`flattenTopLevel` in `store.ts`): human-facing clients plus the servers
they call, found by unwrapping at most two levels of wrappers. VS Code's root
is a `package`; the only client within reach is `cli`, a `cli-tool` of 4
files, 0.6% of the 15,204 mapped files. `src` and `extensions` are typed
`module` and `content`, never candidates, and the top level bypassed
aggregation entirely, so nothing stood in for them. The semantic level had no
part in it: `semanticLevel` is stored and written to the URL and to the
beacon, and nothing in the graph reads it (see P7).

Fix, subject-agnostic and measured on four projections: the anchors must
account for at least half of the mapped files (`TOP_LEVEL_MIN_COVERAGE`),
otherwise the structural top level is shown, which is the root's own children
ranked and aggregated exactly like a drill level. Anchors that do cover the
subject keep the rest of the top level beside them instead of dropping it.
UnaMentis is unchanged (its root is the client, 100% coverage). flask and
fastapi, which have a server and no client, rendered an empty top level before
and now render their root's children.

**P2, tour steps naming components that aggregation grouped away.** The
mechanism was hero promotion, not budgeting: a wrapper with a hero anywhere
beneath it was replaced by that hero plus the wrapper's children, so `src`
dissolved for a `service` four levels down and `extensions` dissolved for a
test fixture typed `web-client` six levels down. Promotion is now bounded to
direct hero children that carry at least 30% of their wrapper's files
(`PROMOTION_MIN_SHARE`), and never dissolves the component a tour step, search
result or deep link named. Measured over every level of UnaMentis (19) and VS
Code (133), the bound changes exactly the three VS Code levels that were wrong
and none of UnaMentis's. A content-typed component with code beneath it is no
longer filtered: the analyzer types a directory by its own files, so
`extensions/` (337 components under a `package.json` and a README) was
`content`. 37 VS Code components are typed that way.

**P3, the flow route lands on Structure.** Decided: withhold the lens. The
Flow lens draws screen navigation (screens, tabs, navigation edges), which
this subject does not have. `build_orientation` and the viewer's fallback now
name Structure with the first tour when there is no flow data, using the same
rule the lens uses. The Atlas lists one entry per lens so two routes on
Structure do not read as a duplicate. Reversible in one line if a Flow lens
for non-UI subjects is ever wanted.

**P4, the heaviest tour stop never came into view.** Not the weight, and not
P5. Reproduced on the crawl's iPhone 13 viewport: following a tour's evidence
link opens the mobile detail sheet at half height, which reserves 266 of the
canvas's 469 px, and that reservation survives the tour's exit and the next
tour. A 231 px node cannot fit in 203 px. A tour step and the start of a tour
now ask the sheet to drop back to its peek strip (`collapseDetail`, the mirror
of `revealDetail`). Measured step by step before the fix: all 25 stops in view
when no evidence link had been followed; the last stop never in view after
one had.

**P5, search blocked for 3 to 6 s.** Profiled in a real browser with the CDP
sampler. The whole of it is one Fuse search per keystroke over 167,479 index
documents (20 MB of indexed text), 1.6 to 4.9 s inside React's input flush.
Landings cost 0.4 to 1.4 s and are not the cause; JSON parsing of a 33 MB
manifest is 30 ms; the architecture object is never replaced. The relevance
gate already decided admission by literal containment, so admission now runs
first over a lowercase haystack precomputed at index time (12 ms over the same
data) and Fuse ranks only the admitted candidates, capped at 2,000. The
incremental index also rebuilt on every first landing because a detail entry
filled in `language` on a shard entry; non-searchable fields are now patched
in place. The decision the directive raised, shrink the manifest or load it
lazily, does not arise: no measured stall needs the data to change.

Lens entry is a separate cost and is not fixed: rules 0.5 to 5.1 s and
security 0.1 to 1.6 s are ELK laying out the bounded 40-node graph on the main
thread in one to three passes, the extra passes from measured node sizes and
the panel mount. The fix is elkjs's worker build plus skipping a re-layout
whose inputs did not change. That touches the engine integration the owner has
a standing rule about and was left for a decision (below).

**P6, the welcome modal.** It fires only on a direct workbench entry
(`?mode=workbench` with no Overview handoff) on a browser that has not
dismissed it. The demo's bare URL lands on the Overview, and the handoff
suppresses it. A shared workbench deep link is the case that shows it.
Decision left to the owner (below).

**New, mobile top level.** With six nodes at the top level the phone's fit
parked `test` under the drill hint. Every fit on a small screen at the
Structure top level now reserves the hint's height, through the engine's own
per-side padding.

## Two data-side notes from the directive

The four entities named `package` come from `*/schemas/package.schema.json`
files with no `title`, and each carries an identical 72-accessor set because
reads of `package.json` are name-matched to the schema entity. Bucket C
(`analyzer/extract/entities.py`). `review_corrections.source` now records the
corrections file's name and digest, not a path.

## Bucket C: the re-parse list

Each item carries evidence from the served projection. None of them needs a
model call to fix, and the existing enrichment re-attaches on reprojection.

1. The extractor bypasses the parser hard stop. `analyzer/extract/runner.py`
   (lines 212 and 455) calls `PARSERS.get(language)` and never
   `get_parser()`, so the tree-sitter guard in `analyzer/parsers/__init__.py`
   never fires. Under an interpreter without tree-sitter a run reports
   "15204 parsed", 100% coverage and exit 0 with zero symbols and zero
   relationships, which would silently orphan every relationship and verdict
   row on reprojection. Fix this before any re-parse is trusted.
2. Content typing by a directory's own files. 37 components typed `content`
   hold code, including `extensions/` (337 components, 5,145 files) and
   `test/` (30 components). `analyzer/derive/roles.py`, `_is_content_only`.
   The viewer now tolerates it; the data should not need tolerating.
3. `extensions/copilot/script` typed `cli-tool`. A scripts directory is a
   utility dir; `script` is missing from `_UTILITY_DIR_NAMES` in `roles.py`.
4. Entity naming and access matching (above). Four `package` entities, 288
   name-matched access edges.
5. `%description%` literal in 91 extension components (`package.nls.json`
   indirection not resolved); 43 components with no description at all.
6. 17 websocket and 2 http edges, every one targeting
   `extensions/copilot/src/extension`, 11 refuted and 8 uncertain by the
   enrichment verdicts; the detector is keyword-only and the two http edges
   carry `api_style: graphql` from test literals. The viewer draws them as
   real (see A-list, refuted edge badge).
7. Root description is the README's badge markdown. Masked today because the
   interpreted summary wins; shows the moment that summary is withheld as
   stale. `analyzer/derive/pipeline.py` README extraction.
8. 15 `.github/workflows/*.yml` files parsed but in no component, so the
   trust chip says 15,219 mapped while the manifest maps 15,204.
9. Three zero-file `PULL_REQUEST_TEMPLATE` placeholder components.
10. Capability test attribution: 3,900 of 3,990 capability test references
   point outside the owning component.
11. `activity.json` carries 2,754 distinct contributor emails as
    `author_key`, and `ActivityPanel.tsx` puts them in a hover title. Policy
    item before any public URL.
12. `src/vs/workbench` is one component of 3,582 files with a 49.9 MB detail
    shard. Splitting it creates ids that carry no enrichment, so this one is
    bucket C then D.

## Bucket D: what actually needs the model

1. `tech_context` strings on 58 components name frameworks the map no longer
   asserts ("web-client; typescript; Next.js" on `src/vs`; "api-server;
   Express" on `editor/common`). Baked into the stored rows by
   `analyzer/enrich/compact.py`, so reprojection does not fix it. A viewer
   fallback (render from `type/language/framework`) hides it meanwhile.
2. `help_text` on 10 components asserts websocket or http links the verdicts
   refuted. Hand-editable through `component_edits` in the corrections file.
3. "19+ child extensions" (97). Cosmetic.
4. The run itself is "done-with-reservations": one edge stuck in escalate on
   the `compact-invalid` serializer defect, and the audit fails on input
   ceilings (P5 calls at 340k tokens against 70k). Completing it is roughly
   $25 to $50 after the ceiling and serializer fixes, and it does not affect
   the served projection.

## Bucket B: regenerate in minutes

1. `build_security_view` builds both "jwt" mechanisms and both cleartext
   boundaries from the two http edges whose verdict is refuted. Skip refuted
   edges; rerun `assemble-serve.py`.
2. Portrait grouping: "Services and interfaces" holds one member against 525
   in Core; "Data and persistence" catches `src/vs/editor/common` on a
   "model" regex. `human_views.py` `_DATA_WORDS`.
3. Deployment posture cites `cli/src` for "Anthropic, GitHub, Google AI,
   OpenAI" when that component's external services list GitHub only.
4. Tour wording through `tour_edits`: three narrations claim the classifier
   "tagged this api-server" (served types: module, module, test-suite); one
   cites a "119-component cycle" no finding records; the agent-host tour
   says "this fork adds" and that tour is the front door's default path.
5. The served bundle has no upstream license, notice or `publication.json`;
   the UnaMentis demo ships all three. `demos/registry/vscode.json` was
   retired with the private plans and `demo-site.py validate` fails on its
   absence.

## Bucket A: viewer items left for a follow-up

- P7. The semantic level control (Overview atlas and workbench header) is a
  no-op; it changes a data attribute and a URL parameter. The front-door
  design describes System, Domain and Component altitudes that were never
  built. Hide it or build it.
- P9. Refuted and uncertain relationship verdicts are drawn as real edges;
  only `FindingsSurface.tsx` reads `verdict`.
- `%description%` and blank descriptions: fall back to the enrichment
  description or the first sentence of `help_text` at the two render sites.
- `TYPE_META` lacks `fixture`, `test-suite`, `test-fixtures`, `tooling`,
  `vscode-extension`, `ui-module`, so the tree badge shows "fix", "tes",
  "vsc". `module (test suite)` is a bad correction value.
- Trust wording: "1009 remain unverified" is 499 unverified plus 510 refuted.
- ELK on the main thread (P5, lens entry). Worker build plus pass coalescing.
- `DetailPanel.tsx` and `ComponentNode.tsx` never read `ai_enhance.stale`, so
  a stale component renders as fresh.

## Decisions for the owner

1. **Lens entry over 2 s.** The gate says no lens takes more than 2 s. Rules
   and security still take 3 to 8 s on this subject, all layout. Options:
   move ELK to its worker and coalesce passes (engine integration, one
   afternoon, needs its own crawl), lower `LENS_GRAPH_MAX_EDGES` for lens
   graphs (blunt, immediate), or accept the numbers for a select audience
   and record them. Recommendation: the worker plus coalescing, as a
   separate branch with its own no-regression run.
2. **P6.** Keep the modal for direct workbench entry, or suppress it whenever
   a `publication.json` is present (published demos never show it), or drop
   it. Recommendation: suppress on published bundles; the Overview is the
   first-run guide now.
3. **Publication safety before any URL.** `security.json` names five
   credential environment variables and one CRA gap about a third party's
   repository; the disclosure policy's step 2 calls for a private preview and
   maintainer outreach first. Contributor emails ship in `activity.json`.
   These are process decisions, not code.
4. **The two thresholds.** 50% anchor coverage and 30% hero share were chosen
   from the four projections at hand and are exported constants. If a fifth
   subject argues with them, change the number, not the rule.

## Re-validation

Filled in below from the runs on the branch's harness and bundle.

Quick profile, desktop and mobile, same target and projection throughout.
The first row is the directive's run. Rows two and three ran main's harness
against the branch's viewer by accident (the control plane runs its own
checkout); every later row ran the branch's harness directly.

| Run | Viewer | Harness | Cases | Error findings | search.slow_input |
|---|---|---|---|---|---|
| directive 20-41-56 | main | main | 48 / 56 | 9 rules, 17 instances | 8 instances |
| 22-17-24 | P1 P2 P3 | main | 50 / 56 | H1, J1 root hop, tour level | 8 instances |
| 22-23-04 | + search | branch | 52 / 56 | J1 root beacon, hint occlusion, P4 | 0 |
| 22-34-01 | + P4, hint reserve | branch | 54 / 56 | J1 tree row, both viewports | 0 |
| 22-37-51 | + tree reveal | branch | 55 / 56 | J1 mobile deep drill | 0 |
| 22-44-03 | + top chrome reserve | branch | 55 / 56 | J1 mobile deep drill | 0 |
| **22-53-08 final** | final | final | **55 / 56** | J1 mobile deep drill | 0 |
| **unamentis-ios 22-56-17 final** | final | final | **56 / 56** | none | none |

Lens entry times did not move: capability 3 s, support 3 s, rules 8 s,
security 7 s under the crawl's two workers.

**The one open case.** Mobile J1 at depths 3 to 5 (`src/vs/sessions` and
below): the double-tap on the node does not drill, the walk continues by URL,
and the reset then reports the drill surviving Home. Isolated double-taps at
the same hops drill correctly (measured on the iPhone 13 viewport, scratchpad
`p4/drill.mjs`). In the journey the previous hop was reached through a tree
double-click that left the level's own component selected, and a tap that
changes the selection re-runs the layout effect (`ArchitectureGraph.tsx`, the
raw-node effect depends on `selectedComponentId`), which is the S5-class move
already on record. The experiment to confirm that difference hung and was
not repeated. Not a regression: mobile J1 on VS Code never got past the root
before tonight, and UnaMentis's mobile J1 passes. It belongs with the ELK
decision, since both are layout passes that should not run.

**Gate, condition by condition.** Zero failing cases on the full profile:
not met, one quick-profile case open and the full profile not run tonight.
search.slow_input gone: met, zero instances in every run since the search
fix. H2 in place and passing: met on both subjects. A human opening the demo
cold: not done and not mine to sign. The first screen now shows src,
extensions, test, cli, scripts and the server bin with their rolled-up edges
(167 uses edges from extensions into src, 84 back, 9 websocket) instead of one
Rust helper.

## Commands

```
# bundle and serve the branch's viewer over the canonical projection
python3 scripts/assemble-serve.py vscode \
  --projection /Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/viewer-projection/architecture \
  --corrections demos/review-corrections/vscode.json
python3 -m http.server 5175 --bind 127.0.0.1 --directory .testboard/serve/vscode

# crawl with THIS worktree's harness (control.py would run the control plane's checkout)
cd viewer && CRAWL_BASE_URL=http://127.0.0.1:5175 CRAWL_PROFILE=quick \
  npx playwright test -c tests/crawl/playwright.config.ts
python3 scripts/crawl-report.py .testboard/runs/<run id>

# reproject after a parser or derive fix, keeping the enrichment (venv interpreter, not python3)
/Volumes/Studio/dev/solution-explorer/.venv/bin/python analyze.py /Volumes/Studio/dev/.demo-corpus/vscode \
  --engine v2 --store <copy of index.db> --output <dir> --split
```
