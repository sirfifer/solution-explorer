# VS Code Demo Gate Return

Return on the Demo Gate directive, 2026-09-02. Branch `wt/vscode-demo-gate`,
commit fb65c78. Published copy: https://claude.ai/code/artifact/53311fe0-9f4f-49c9-8304-8f29c52e0233.
Companion run record with commands and the full evidence:
`docs/testing/RUN-2026-09-02-vscode-demo-gate.md`.

| | |
|---|---|
| subject | vscode @ 474a349ad5b7 |
| directive run | 2026-09-02T20-41-56 |
| final run | 2026-09-02T22-53-08, 55 of 56 |
| control | unamentis-ios 22-56-17, 56 of 56 |
| unit tests | 648 of 648 |

## Verdict

**55 of 56 on VS Code, 56 of 56 on the UnaMentis control. One case open, and
it is the phone's deep double-tap drill.**

The first screen now shows src, extensions, test, cli, scripts and the server
bin with their rolled-up wiring instead of one Rust helper. Every tour stop is
on the canvas. Search answers in tens of milliseconds. The harness that could
not see any of this now can. Two gate conditions are still not met and both
are decisions rather than code: lens entry is layout time on the main thread,
and a human has not yet opened it cold.

The directive named six product defects and two harness defects. All eight
causes are established from code or measurement, and the directive's own
diagnosis was wrong on three of them. None of the fixes needed the projection
to change. The bigger news is that a deterministic re-parse keeps the
enrichment, so the list for "the expensive rerun" is a list for a two-minute
reprojection.

## The split you asked for is four buckets, not two

The directive treated anything wrong in the data as needing the whole
parse-plus-enrichment again. It does not. Enrichment rows are keyed by
component id plus a digest of the component's member files, never by symbols,
type or name. On a copy of the VS Code store (17,120 rows) a type or name
change invalidates 0 rows, rewriting every symbol invalidates 0, splitting one
component invalidates 13, and every v2 projection re-applies the store. A full
reprojection of the same commit under the venv interpreter took about two
minutes and produced the same 151,134 symbols and one extra relationship.
Total enrichment spend so far is about $236, not the $94 the latest run record
shows on its own, and none of it is at risk from a parser fix.

| Bucket | Cost | What went here |
|---|---|---|
| A. Viewer or crawl code | minutes, no data touched | P1, P2, P3, P4, P5, H1, H2, the mobile drill hint, the provenance path. All done. |
| B. Sidecar or assembly step | seconds, no model | orientation.json (done), security view built from refuted edges, portrait grouping, tour wording, bundle license and notice. |
| C. Deterministic re-parse | about 2 min, zero model calls | Content typing, entity naming, placeholder descriptions, refuted edges, workflow files, author emails. Twelve items, the first a guard to fix before trusting any of it. |
| D. Paid enrichment | $25 to $50 after code fixes | Three text defects baked into stored rows, and finishing the "done-with-reservations" run. |

## Phase 1: the instrument

**H1. Support and security judged unwarranted on every run. Fixed.**
Confirmed as described, with one correction: the merge belongs in the
contract, not only in the remote mirror. The contract read `manifest.support`,
which the app fills from `support.json` at load time, so the false finding
fired in local runs too. The contract now merges both sidecars the way the app
does and the mirror downloads them. UnaMentis was never affected: its bundle
ships neither sidecar, so the data and the DOM agreed by accident. Its
verdicts stand.

**H2. The root-level assertion could not fail the way P1 needed. Fixed as
`graph.missing_node`.** A root that renders is accounted for. A root the graph
promoted must have every non-blob child rendered, inside a rendered aggregate
(aggregate nodes now publish their member ids), or represented by a rendered
descendant. Fixing P1 exposed two more harness expectations that were wrong:
the drill journey treated a promoted single root as a hop, and the tour spec
expected a step onto a promoted root's child to drill into the root. The
journey also read a hop's node once before the level had rendered; it now
polls briefly, then falls back to the tree.

**Also found.** `control.py run crawl` posts to the control plane on port 4200,
which runs the harness from the checkout it was started in. Two of tonight's
runs silently used main's harness against the branch's bundle before this was
noticed. The runs reported here were made with Playwright directly in the
branch worktree.

## Phase 2: the product

**P1. One node at the top level. Fixed, cause established.** Neither of the
two candidates the directive named. The top level is built by a client/server
model: human-facing clients plus the servers they call, found by unwrapping at
most two levels of wrappers. VS Code's root is a `package`; the only client
within reach is `cli`, a 4-file cli-tool, 0.6% of the 15,204 mapped files.
`src` and `extensions` are typed module and content and were never candidates,
and the top level bypassed aggregation entirely, so nothing stood in for them.
The semantic level had no part in it: `semanticLevel` is stored, written to
the URL and the beacon, and read by nothing in the graph. The three buttons do
nothing (P7).

Fix: anchors must account for at least half the mapped files, otherwise the
structural top level is shown, the root's own children ranked and aggregated
exactly like a drill level. Measured on four projections. UnaMentis is
unchanged (its root is the client, 100%). flask and fastapi, a server with no
client, rendered an empty top level before and now render their root's
children.

**P2. Tour steps narrate components that aggregation grouped away. Fixed, the
mechanism and not the four tours.** Not budgeting. Hero promotion replaced any
wrapper with a hero anywhere beneath it by that hero plus the wrapper's
children, so `src` dissolved for a service four levels down and `extensions`
dissolved for a test fixture typed web-client six levels down. Promotion is
now bounded to direct hero children carrying at least 30% of their wrapper's
files, and never dissolves the component a tour step, search result or deep
link named. Over every level of UnaMentis (19) and VS Code (133), the bound
changes exactly the three VS Code levels that were wrong and none of
UnaMentis's. A second cause underneath: the analyzer types a directory by its
own files, so `extensions/` (337 components under a package.json and a README)
was `content` and filtered. 37 VS Code components are typed that way. The
viewer now filters only true content blobs; the typing itself is bucket C.

**P3. The "flow" route lands on a lens that does not exist. Decided and
fixed.** Withhold the lens. The Flow lens draws screen navigation, which this
subject does not have. The orientation builder and the viewer's fallback now
name Structure with the first tour when there is no flow data, using the
lens's own availability rule. Reversible in one line.

**P4. The heaviest component never comes into view on the last tour step.
Fixed, not P5 and not weight.** Reproduced on the crawl's iPhone 13 viewport.
Following a tour's evidence link opens the mobile detail sheet at half height,
which reserves 266 of the canvas's 469 px, and the reservation survives the
tour's exit and the next tour. A 231 px node cannot fit in 203 px. All 25
stops came into view when no evidence link had been followed; the last stop
never did after one had. A tour step and the start of a tour now send the
sheet back to its peek strip.

**P5. Search is blocked for 3 to 6 seconds after every landing. Fixed, and
the landing was not the cause.** Profiled with the CDP sampler in a real
browser. The whole stall is one Fuse search per keystroke over 167,479 index
documents, 1.6 to 4.9 s inside React's input flush. Landings cost 0.4 to 1.4
s; parsing the 33 MB manifest costs 30 ms; the architecture object is never
replaced. The relevance gate already decided admission by literal containment,
so admission now runs first over a lowercase haystack precomputed at index
time (12 ms over the same data) and Fuse ranks only the admitted candidates.
The "shrink the manifest or load it lazily" decision does not arise.

Still open under P5: lens entry is a different cost. Rules 0.5 to 5.1 s and
security 0.1 to 1.6 s are ELK laying out the bounded 40-node graph on the
main thread in one to three passes. The gate's "no lens over 2 s" is not met.
See decision 1.

**P6. A five-step welcome modal covers the canvas on first visit. Your
call.** Narrower than described. It fires only on a direct workbench entry
(`?mode=workbench` with no Overview handoff) on a browser that has not
dismissed it. The demo's bare URL lands on the Overview and the handoff
suppresses it. A shared workbench deep link is the case that shows it. See
decision 2.

**P8, new. The wider top level put a phone node under the drill hint.
Fixed.** With six nodes at the top level the phone's fit parked `test` under
the "Open a level" hint. Every fit on a small screen now reserves the height
of the chrome over the top of the canvas (the hint at the top level, the
breadcrumb bar below it), through the engine's own per-side padding.

**P10, new. On a phone, a double-tap three levels down does not drill. The
one open case.** The drill journey's hops at `src/vs/sessions` and below: the
double-tap leaves the drill where it was, the walk continues by URL, and Home
then fails to clear it. Isolated double-taps at the same hops drill correctly
on the same viewport. In the journey the previous hop was reached through a
tree double-click that left the level's own component selected, and a tap
that changes the selection re-runs the layout effect, the same S5-class move
already on record. The experiment to confirm the difference hung and was not
repeated. Not a regression: VS Code's mobile journey never got past the root
before tonight, and UnaMentis's passes. It belongs with decision 1.

**P7, new. The semantic level control does nothing. Follow-up.** System,
Domain and Component are in the Overview atlas and the workbench header, and
change a data attribute and a URL parameter only. Hide it or build it; a demo
reviewer will click it.

**P9, new. Refuted edges are drawn as real. Viewer follow-up, data in bucket
C.** All 17 websocket and 2 http edges target
`extensions/copilot/src/extension`; the enrichment verdicts mark 11 refuted
and 8 uncertain, and the two http edges carry "graphql" from test literals.
Only the findings surface reads verdicts. Ten components' help text asserts
the same refuted links (bucket D), and the security view's two "jwt"
mechanisms are built from the two refuted http edges (bucket B).

## Phase 3: what the crawl says now

Quick profile, desktop and mobile, same target and projection. The first row
is the directive's run. Rows two and three ran main's harness against the
branch's viewer by accident; the rest ran the branch's harness directly.

| Run | Viewer | Harness | Cases | Error findings | search.slow_input |
|---|---|---|---|---|---|
| directive 20-41-56 | main | main | 48 / 56 | 9 rules, 17 instances | 8 instances |
| 22-17-24 | P1 P2 P3 | main | 50 / 56 | H1, J1 root hop, tour level | 8 instances |
| 22-23-04 | + search | H1 H2 | 52 / 56 | J1 root beacon, hint, P4 | gone |
| 22-34-01 | + P4, hint | H1 H2 | 54 / 56 | J1 tree row | gone |
| 22-37-51, 22-44-03 | + tree reveal, top chrome | H1 H2 | 55 / 56 | J1 mobile deep drill | gone |
| **22-53-08 final** | final | final | **55 / 56** | J1 mobile deep drill | gone |
| **unamentis-ios 22-56-17 final** | final | final | **56 / 56** | none | none |

Lens entry times did not move: capability 3 s, support 3 s, rules 8 s,
security 7 s under the crawl's two workers. That is the one gate condition
the branch does not meet, and it is decision 1.

## The gate, condition by condition

- **Zero failing cases, zero error findings on the full profile.** Not met.
  One quick-profile case is open (P10) and the full profile was not run
  tonight.
- **search.slow_input gone, not reduced.** Gone in every run since the search
  fix; 0 instances.
- **H2's assertion in place and passing.** In place as graph.missing_node;
  passing on both subjects.
- **A human opens the demo cold on desktop and mobile.** Not done tonight,
  and not mine to sign. The first screen now shows src, extensions, test,
  cli, scripts and the server bin with their rolled-up edges (167 uses edges
  from extensions into src, 84 back, 9 websocket) instead of one Rust helper.

## Decisions for you

1. **Lens entry over 2 s: worker, blunt cap, or accept?** Rules and security
   take 3 to 8 s on this subject, all ELK on the main thread, one to three
   passes. Moving ELK to its worker build and skipping a re-layout whose
   inputs did not change is about an afternoon and touches the engine
   integration you have a standing rule about. Lowering the lens graph edge
   cap is immediate and blunt. Recommendation: the worker plus pass
   coalescing, on its own branch with its own no-regression crawl.
2. **The welcome modal for the select audience.** Keep it for direct
   workbench entry, suppress it whenever a publication.json is present so
   published demos never show it, or drop it. Recommendation: suppress on
   published bundles. The Overview is the first-run guide now.
3. **Publication safety before any URL exists.** security.json names five
   credential environment variables and one CRA gap about a third party's
   repository; the disclosure policy's step 2 calls for a private preview and
   maintainer outreach first. activity.json ships 2,754 contributor emails
   and the activity panel shows them on hover. The bundle has no upstream
   license, notice or publication.json; the UnaMentis demo ships all three.
   These are process calls, not code.
4. **The two thresholds.** 50% anchor coverage and 30% hero share were chosen
   from the four projections at hand and are exported constants. If a fifth
   subject argues with them, change the number, not the rule.

## Bucket C: the re-parse list (processing time only, enrichment survives)

1. **First, the guard.** The extractor calls the parser table directly and
   never the guarded getter, so the tree-sitter hard stop never fires: under
   an interpreter without tree-sitter a run reports "15204 parsed", 100%
   coverage and exit 0 with zero symbols and zero relationships, which would
   silently orphan every relationship and verdict row. Fix
   `analyzer/extract/runner.py` lines 212 and 455 before trusting any
   re-parse; always run the analyzer with the venv interpreter.
2. Content typing by a directory's own files: 37 components typed content
   hold code, including extensions/ (337 components) and test/ (30). The
   viewer now tolerates it; the data should not need tolerating.
3. extensions/copilot/script typed cli-tool; "script" is missing from the
   utility-directory names that block hero promotion.
4. Four data entities named "package" from schema files with no title, each
   with an identical 72-accessor set because package.json reads are
   name-matched to the schema entity: 288 bogus access edges.
5. The literal "%description%" on 91 extension components (package.nls.json
   not resolved); 43 components with no description at all.
6. The 19 websocket and http edges above: a keyword detector, and test
   literals read as GraphQL endpoints.
7. The root description is the README's badge markdown. Masked today by the
   interpreted summary; shows the moment that summary is withheld as stale.
8. 15 .github/workflows files parsed but in no component, so the trust chip
   says 15,219 mapped against 15,204 in the manifest.
9. Three zero-file PULL_REQUEST_TEMPLATE placeholder components.
10. Capability test attribution: 3,900 of 3,990 test references point
    outside the owning component.
11. Contributor emails as author keys in activity.json.
12. src/vs/workbench as one 3,582-file component with a 49.9 MB detail shard.
    Splitting it creates ids that carry no enrichment, so this one is C then D.

## Bucket D: what actually needs the model

- tech_context strings on 58 components name frameworks the map no longer
  asserts ("web-client; typescript; Next.js" on src/vs). Baked into stored
  rows by the compactor, so reprojection does not fix it; a viewer fallback
  hides it meanwhile.
- Help text on 10 components asserts the refuted websocket and http links.
  Hand-editable through component_edits in the corrections file.
- "19+ child extensions" (there are 97). Cosmetic.
- The run is "done-with-reservations": one edge stuck in escalate on the
  compact-invalid serializer defect, and the audit fails on input ceilings.
  Completing it is roughly $25 to $50 after the ceiling and serializer fixes,
  and it does not affect the served projection.

## Bucket B: regenerate in minutes

- The security view builds both "jwt" mechanisms and both cleartext
  boundaries from the two refuted http edges. Skip refuted edges and rerun
  assemble.
- Portrait grouping: "Services and interfaces" holds one member against 525
  in Core; "Data and persistence" catches src/vs/editor/common on a "model"
  regex.
- Deployment posture cites cli/src for "Anthropic, GitHub, Google AI, OpenAI"
  when that component's external services list GitHub only.
- Tour wording through tour_edits: three narrations claim the classifier
  "tagged this api-server" (served types: module, module, test-suite), one
  cites a "119-component cycle" no finding records, and the agent-host tour,
  the front door's default path, says "this fork adds".
- The served bundle has no upstream license, notice or publication.json.
  demos/registry/vscode.json was retired with the private plans and the demo
  validator fails on its absence.

## Bucket A: viewer items left for a follow-up

- P7 semantic level, P9 refuted-edge badge, "%description%" and
  blank-description fallbacks at the two render sites.
- Six component types missing from the type table (fixture, test-suite,
  test-fixtures, tooling, vscode-extension, ui-module), so the tree badge
  reads "fix", "tes", "vsc".
- Trust wording: "1009 remain unverified" is 499 unverified plus 510 refuted.
  The detail panel never reads a component's stale flag.
- ELK on the main thread (decision 1).

## What is on the branch

Twenty-two files in commit fb65c78, 648 unit tests passing (632 before, 16
new), analyzer tests passing. Changelog updated. Nothing pushed. The branch's
bundles are served at http://127.0.0.1:5175 (VS Code) and
http://127.0.0.1:5176 (UnaMentis).

Evidence: crawl run records under the branch worktree's `.testboard/runs`;
profiling scripts and measurements in the session scratchpad (p5, p4,
census). Subagent audits: projection data and publication safety (25 items),
search latency profile, enrichment reuse across re-parse.
