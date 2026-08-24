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

```bash
cd viewer && npm run build
mkdir -p viewer/tests/gui/.datasets/split-mode
cp -R <projection-dir> viewer/tests/gui/.datasets/split-mode/architecture
python3 scripts/gui-datasets.py assemble split-mode
cd viewer && CRAWL_SERVE_DIR=$PWD/tests/gui/.serve/split-mode npm run test:crawl
```

Full details in `viewer/tests/crawl/README.md`. The shape of it:

- **Nothing about any subject is hardcoded.** The component set, parent/child
  lists and per-component file and symbol counts come from the manifest; the
  tab set is read off the rendered tab bar; the lens list is read off the lens
  switcher. A lens registered next month is exercised the day it ships.
- **Two navigation channels, compared.** Every component is visited by URL
  (`?component=<id>`), and separately the tree is expanded adaptively until it
  converges and every revealed node is collected. The two sets must be equal.
  Divergence is the "the data is there but you cannot get to it" class.
- **Per-level completeness.** Every parent the tree renders is opened and its
  revealed children compared against the manifest's child list for that exact
  id, so depth is checked level by level rather than as a single number.
- **The honest-empty rule.** A surface backed by no data must say so. Blank is
  a failure; "0 symbols" is a pass. This is what lets the same suite run
  against a deterministic dataset, where several surfaces are legitimately
  empty, without either lying or drowning in false positives.
- **Nothing may scream.** Any console error or undeclared 404 fails the case
  that caused it. The allowlist mirrors the probe inventory in
  `viewer/tests/gui/datasets.yaml`.
- **No silent caps.** `CRAWL_MAX_COMPONENTS` samples depth-stratified rather
  than in tree order, and what was dropped is reported in the run annotations.

### The selector contract

The crawl drives the app through attributes the components publish on purpose.
The tree gained `role="tree"`, `role="treeitem"`, `aria-level` and
`aria-expanded` in the same change, because a scripted walk and a screen reader
need the same thing: the structure stated rather than implied by styling.

The tab bar deliberately did not gain `role="tablist"`/`role="tab"`. That
pattern obliges arrow-key navigation and `aria-controls` pairing that these
buttons do not implement, so claiming it would be a false label rather than an
improvement. It is also a good illustration of the handoff's rule about the
viewer's environment-only test failures: the first attempt did add those roles,
which silently broke seven existing unit tests by changing the accessible role
they query. Capturing the failing FILE set before and after the change, and
diffing the two lists, is what separated the three real regressions from the
one known `localStorage` failure they were hiding among. The full selector
table is in `viewer/tests/crawl/README.md`.

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
