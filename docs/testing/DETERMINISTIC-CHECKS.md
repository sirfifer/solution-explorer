# Deterministic checks: the artifact linter and the GUI crawl

Two automated suites that answer, without a model in the loop, the two
questions a full generation raises before anyone forms an opinion about it:

1. **Is the data whole?** `scripts/lint-projection.py` reads a finished
   projection end to end and checks that it is internally consistent, that
   every claim in it points at something real, and that it looks as complete as
   it should.
2. **Can a reader reach it?** `viewer/tests/crawl/` drives a real browser over
   a served build of that same projection and proves that everything in the
   data is reachable in the UI and renders without erroring.

They are deliberately a pair. Either alone gives a false read: a green linter
over a viewer that cannot show half the tree is a map nobody can use, and a
green crawl over a broken projection is a UI faithfully rendering nonsense.

## Why these exist alongside what we already have

| Existing check | What it proves | What it leaves open |
|---|---|---|
| `tests/` (1600+ unit tests) | each analyzer unit behaves | nothing reads the finished artifact as a whole |
| `analyzer/contracts.py` postconditions | a producer handed off a well-formed result | in-run only; no cross-artifact integrity after assembly |
| `scripts/demo-site.py validate` | a bundle is publishable | publication obligations, not data integrity or reachability |
| `viewer/tests/gui/` (AI-operated) | surfaces read correctly to a person | hours per run, agent-attended, ~100 hand-authored cases |
| `viewer/src/__tests__` (vitest) | components behave in jsdom | never loads a real dataset, never navigates |

The gap both new suites fill is the same one: **nobody was checking the whole
finished thing, mechanically, at the scale a real subject has.** The defects
that have actually cost time were of exactly that shape. The manifest, `ai.json`
and the admin summary each passed their own validity checks while contradicting
each other. A dataset shipped with `stats.total_components` saying 178 over a
tree of 256. A projection was complete and the viewer still could not navigate
to parts of it.

Both suites are free to rerun and cost no model tokens, which is what makes
them the right thing to run first, before any enrichment pass is paid for.

## 1. The artifact linter

```bash
python3 scripts/lint-projection.py <projection-dir> \
    [--src <source-tree>] [--profile deterministic|enriched] \
    [--json lint.json] [--strict]
```

Six bands, each named so a failure says what kind of failure it is:

| Band | Asks |
|---|---|
| `parse.*` | does the artifact set exist, and is it UTF-8 JSON |
| `shape.*` | do the required keys exist with the right types, everywhere |
| `ref.*` | does every id resolve: relationship endpoints, detail index against tree and disk in both directions, lens arrays, entity access, findings, changelog edges, search entries, front-door endpoints and section claims |
| `count.*` | do the numbers the artifact states about itself agree with its own payload |
| `source.*` | accusability: does every cited file exist, is every cited line inside it, is a sampled symbol actually on the line the map names |
| `census.*` | completeness heuristics: depth histogram, dead-end nodes, unknown languages, per-lens population, coverage, enrichment uniformity |

Two design rules worth keeping:

- **A skipped check is never silent.** No source tree means the whole `source.*`
  band reports as skipped, by name, rather than passing by omission.
- **Content checks stay out of `shape.*`.** Presence and type only, the same
  line `analyzer/contracts.py` draws for postconditions and for the same
  reason: validation creep toward asserting what a value *means* is the failure
  mode that makes a checker useless on the next subject.

`--profile deterministic` (the default) additionally asserts that no
`ai_enhance` key exists anywhere, so a run intended as a clean baseline cannot
quietly contain enrichment. `--profile enriched` asserts the opposite and, more
usefully, rejects a *partial* posture in either direction.

The linter is proved by mutation in `tests/test_lint_projection.py`: one small
whole projection, asserted clean, then broken one defect at a time with a test
per defect class. A linter that has only ever seen good input proves nothing.

## 2. The GUI crawl

Design authority is `docs/testing/GUI-CRAWL-DESIGN.md`, which states what the
suite must prove and why; `viewer/tests/crawl/README.md` is the operator's
manual, with the full selector table and the record of what it has found;
`docs/testing/RUN-2026-09-01-adaptive-crawl.md` is the first run and the fix
iterations that followed it.

```bash
# stage the viewer beside a projection (symlinked, never copied), then crawl
python3 scripts/assemble-serve.py <slug> --projection <projection-dir>
cd viewer && CRAWL_SERVE_DIR=$PWD/../.testboard/serve/<slug> npm run test:crawl
```

The shape of it:

- **Nothing about any subject is hardcoded.** The component set, parent/child
  lists and per-component file and symbol counts come from the manifest; the
  tab set is read off the rendered tab bar; the lens list is read off the lens
  switcher and compared with what the data warrants (each lens's own
  availability gate, mirrored in `contract.ts`); the Overview's question
  routes and portrait cards come from `orientation.json`. A lens registered
  next month is exercised the day it ships.
- **Presence in both directions.** An entry point, lens or tab the data
  warrants but the DOM lacks is a finding; one the DOM shows but the data does
  not warrant is also a finding. Features deliberately switched off are named
  in a parameters file (`CRAWL_PARAMS`, `declared_off`) so their absence is
  expected and their presence is the finding.
- **Two navigation channels, compared.** Every component is visited by URL
  (`?component=<id>`), and separately the tree is expanded adaptively until it
  converges and every revealed node is collected. The two sets must be equal.
- **Per-level completeness.** Every parent the tree renders is opened and its
  revealed children compared against the manifest's child list for that id.
- **Every path ends with a reset probe.** After each journey the suite returns
  to the start the way a reader would (Home, Escape) and asserts that nothing
  of the journey survives, on the app's own state beacon and on screen.
- **The honest-empty rule.** A surface backed by no data must say so. Blank is
  a failure; "0 symbols" is a pass.
- **Nothing may scream.** Any console error or undeclared 404 fails the case
  that caused it. The allowlist mirrors the probe inventory in
  `viewer/tests/gui/datasets.yaml`.
- **No silent caps.** `CRAWL_MAX_COMPONENTS` samples depth-stratified rather
  than in tree order, and what was dropped is reported in the run annotations.

### The specs

- `reachability.spec.ts`, `depth.spec.ts`, `search.spec.ts`: the original
  three. Can every component be reached by URL and by the tree, does every tab
  render something honest, does every kind of search result land where it
  says.
- `surfaces.spec.ts`: presence in both directions for entry points, lenses and
  detail tabs; every present surface opens, shows real content, closes clean
  and leaves navigation untouched.
- `graph.spec.ts`: the canvas renders only real nodes; click, double-click
  drill and Home behave; an off-screen selection snaps into view; no node
  preview ever covers the header; no target is occluded at its centre.
- `journeys.spec.ts`: named paths (drill to the bottom, back and forward, a
  lens round trip, lens-scoped selection, overlay hygiene, a cold reload) each
  followed by the reset probe. Residue is reported by name as a context leak.
- `tours.spec.ts`: every guided tour played end to end; each stop must be
  selected, drawn, uncovered and inside the canvas, the progress text right,
  the evidence link showing the file, exit leaving nothing behind.
- `overview.spec.ts`: the front door. A bare URL lands on the Overview; each
  direction renders; question routes match `orientation.json` and hand off to
  the right lens, surface or tour; portrait cards land on their component;
  the Overview to workbench round trip is lossless and Back returns to the
  Overview; trust and preferences open and close; search from the Overview
  enters the workbench.

A second Playwright project, `mobile` (`devices["iPhone 13"]`), runs the
`@mobile`-tagged subset concurrently with desktop against the identical
selector contract; `CRAWL_MOBILE=0` disables it. Every run writes
`discovery.json` beside `run.json`: what the build exposed (entry points,
lenses, tours, routes, sample sizes), so a later reader compares versions
instead of re-deriving them.

### The contract-presence gate

The app publishes its navigation state on a hidden `nav-state` element and
identity attributes on the surfaces the crawl drives (the README's selector
table). A build that predates the contract is not failed forty times for one
reason: the gate skips every contract-dependent case with one annotation and
the run is reported as LIMITED, never green.

### Running it

All routine runs go through the control plane (`scripts/control.py`) so they
are serial and land on the testboard:

```bash
# local, against a subject already fetched and analyzed
python3 scripts/control.py run assemble --slug <slug> [--projection <dir>]
python3 scripts/control.py run crawl --slug <slug>                 # quick (default)
python3 scripts/control.py run crawl --slug <slug> --profile full  # no budget

# remote, against a served site (no assemble step, no slug)
python3 scripts/control.py run crawl --url https://<host>
```

`quick` bounds only the exhaustive per-component sweeps
(`CRAWL_MAX_COMPONENTS=40`); the bounded specs always run in full. On a
165-component subject the quick profile takes about a minute on both
viewports; `full` is minutes there and hour-scale on a subject the size of
VS Code. `python3 scripts/crawl-report.py <run-dir>` (or `--latest`) renders
`run.json` into a plain-English `REPORT.md` beside it, findings grouped by
rule id; `control.py run crawl` from the CLI does this once the run finishes.

### When it runs

1. After any significant change to the viewer, the store, the lenses, or the
   projection schema: `quick` against the current canonical subject before
   the work is called done. A PR that changes viewer behaviour reports the
   run id.
2. After every new subject's full pass: `quick` at least, once after
   `assemble` and again after `enhance`, since enrichment adds tours and AI
   surfaces the deterministic gates do not check; `full` before publication.
3. Not in CI. It needs a served projection and a real browser; `gui-plan-check`
   remains the only CI-side GUI check.

### The selector contract

The crawl drives the app through `data-*` attributes the components publish
on purpose, never through styling classes and never through ARIA roles the
components do not honour. Two React Flow natives (`.react-flow__node[data-id]`
and `.react-flow`) are the only class selectors, because they are the
framework's published identity for nodes and canvas. The README records why
the tree and the tab bar deliberately carry no `tree` or `tablist` roles: a
role is a promise of keyboard behaviour, and claiming it without the behaviour
leaves a screen-reader user worse off. Changing or removing any contract
attribute breaks the crawl loudly, which is the point.

## Relationship to the AI-operated plan

`GUI-REGRESSION-STRATEGY.md` anticipated this: "If specific hot vectors later
prove perfectly stable, freezing them into scripted specs for cheap unattended
reruns is a Phase 4 option." The crawl is not that. It does not freeze any
authored vector; it is a different kind of test that could not be written as a
list of cases at all, because its cases are generated from whatever dataset it
is pointed at.

The division stays clean:

- **Crawl:** coverage and integrity. Mechanical, exhaustive, cheap, unattended.
  Can say "component X is unreachable". Cannot say "this panel is confusing".
- **AI plan:** judgement. Expensive, attended, hand-authored. Can say "the
  empty state here reads as a bug". Cannot exhaustively walk 16,000 files.

Run the crawl on every dataset generation. Run the AI plan when the question is
whether the product is any good.
