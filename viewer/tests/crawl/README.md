# The deterministic GUI crawl

A scripted, subject-agnostic Playwright suite that proves the viewer can reach
and render everything the projection holds. It is the mechanical half of GUI
testing; `viewer/tests/gui/` (the AI-operated vector plan) is the judgement
half. Neither replaces the other.

## What each one is for

| | `viewer/tests/gui/` | `viewer/tests/crawl/` (here) |
|---|---|---|
| Operated by | an LLM agent driving a browser | `@playwright/test`, unattended |
| Cases | ~100 hand-authored, hand-walked | none; the shape is discovered per dataset |
| Answers | does this surface read correctly to a person | is everything in the data reachable and non-broken |
| Cost | hours, agent-attended | minutes, free to rerun |
| Catches | wrong copy, bad affordance, misleading layout | unreachable components, blank tabs, dead deep links, console errors at scale |

The crawl exists because the defects that actually hurt us were coverage
defects, not aesthetic ones: the data was whole and the UI still could not get
you to it. That question is exhaustively checkable by machine, and checking it
by hand across a subject the size of VS Code is not realistic.

## Running it

The suite needs two things: a served build, and the projection that build is
serving, so it can compare the UI against the data.

```bash
# 1. Build the viewer
cd viewer && npm run build

# 2. Stage the projection you want to crawl as the dataset payload, then
#    assemble a serve root from it (the same harness the AI plan uses).
mkdir -p viewer/tests/gui/.datasets/split-mode
cp -R <your-projection-dir> viewer/tests/gui/.datasets/split-mode/architecture
python3 scripts/gui-datasets.py assemble split-mode

# 3. Crawl it. Playwright starts the static server itself.
cd viewer
CRAWL_SERVE_DIR=$PWD/tests/gui/.serve/split-mode npm run test:crawl
```

Environment:

| Variable | Meaning |
|---|---|
| `CRAWL_SERVE_DIR` | directory to serve; Playwright starts `http.server` on it |
| `CRAWL_BASE_URL` | crawl an already-running origin instead (default `http://127.0.0.1:4180`) |
| `CRAWL_DATA_DIR` | the projection to read as ground truth (default `<serve dir>/architecture`) |
| `CRAWL_MAX_COMPONENTS` | budget for the per-component sweeps; unset or `0` means every component |
| `CRAWL_ALLOW_ERRORS` | extra comma-separated URL fragments allowed to 404 |

Results land in `viewer/tests/crawl/results/` (gitignored): `crawl-results.json`
plus failure screenshots and traces.

## How it stays subject-agnostic

Every expectation comes from the artifact, never from a constant in a spec:

- the component set, the parent/child lists and the per-component file and
  symbol counts come from `manifest.json` and `component_detail_index`
- the tab set is read off the rendered tab bar for each component
- the lens list is read off the lens switcher, so a lens registered next month
  is exercised the day it ships
- the sample, when a budget is set, is depth-stratified so deep nodes are not
  the ones dropped, and what was dropped is reported in the run annotations

The two things it does hardcode are the honest-empty rule (a surface with no
data must say so; blank is a failure) and the requirement that nothing logs a
console error or an undeclared 404. The 404 allowlist mirrors the probe
inventory in `viewer/tests/gui/datasets.yaml`.

## The selector contract

The suite drives the app through attributes the components publish on purpose.

An ARIA role is a contract, not a label, so one is added only where the
component keeps the promise the role makes.

The tab bar deliberately did **not** gain `role="tablist"`/`role="tab"`. That
pattern obliges arrow-key navigation between tabs and `aria-controls` pairing,
neither of which these buttons implement, and claiming the role without the
behavior leaves a screen-reader user worse off than a plain button does. Adding
it also changed the accessible role that seven existing unit tests query by,
which is how the overreach got caught. The tabs carry identity attributes only.

The tree did not gain `role="tree"`/`role="treeitem"` either, for the same
reason and after making the same mistake. An earlier revision added them, along
with `aria-level` and `aria-selected`. The tree pattern obliges a roving
tabindex, Up/Down between visible items, Right to expand, Left to collapse and
move to the parent, and Home/End; this tree implements none of it. Announcing
"tree" and then ignoring every key that announcement teaches a reader to press
is the tab-bar error wearing a different role name. `aria-expanded` stays on
the expanders, because a disclosure button really does expand.

So the crawl drives the tree through `data-*` attributes alone.

| Attribute | On | Carries |
|---|---|---|
| `data-testid="tree-navigator"` | the tree container | the tree root |
| `data-testid="tree-node"` | each component row | `data-component-id`, `data-depth`, `data-has-children`, `data-expanded`, `data-selected` |
| `data-testid="tree-node-toggle"` | the expander | click target that does not select |
| `data-testid="tree-children"` | a revealed child group | `data-parent-id` |
| `data-testid="tree-folder"` | an "Internal Components" group | `data-folder-name`, `data-expanded` |
| `data-testid="detail-panel"` | the detail pane | `data-component-id` actually rendered |
| `data-testid="detail-title"` | its heading | the component name |
| `data-testid="detail-tab"` | each tab | `data-tab`, `data-active` |
| `data-testid="detail-tabpanel"` | the tab body | `data-tab` currently shown |
| `data-testid="lens-select"` | the lens switcher | `data-lens` |

Changing or removing any of these breaks the crawl loudly, which is the point:
the attributes are the contract, and a refactor that drops them should have to
say so.

## What this has actually found

Kept as a record of what the suite is for, and of which defects only appeared at
real scale. Every one of these was invisible to the 1,600 unit tests and to the
data linter, because all of them are about whether a reader can reach and use
what the data holds.

**Found and fixed:**

1. **A deep link never revealed its component in the tree.** You arrived at a
   detail panel with no row in the navigator: no sense of place, no siblings, no
   way further down without restarting from the top. `expandedIds` was local to
   `TreeNavigator` and nothing reacted to `selectedComponentId`, so URL, search
   and graph-click selection all left the tree untouched.
2. **The same fix was incomplete, and only VS Code showed it.** Revealing the
   ancestor chain was not enough for components under an "Internal Components"
   folder, because `collectOtherComponents` puts a component in a group and
   never recurses into its children. At depth 5 the thing in the group is an
   ANCESTOR, so matching only the selected id left eleven `extensions/`
   components with no row at all. It passed on this repo because our tree is
   shallow enough that the selected component usually is the grouped one.
3. **The Files tab rendered blank** for a component with zero files instead of
   saying so. A blank panel and a broken panel look identical, and that
   ambiguity teaches people to distrust every empty surface in the product.
4. **The Rules lens hung the browser indefinitely on VS Code.** Isolating panel
   load from graph load found it: 3,745 rules under one owner render in 636 ms,
   while 335 rules under 194 owners never finish. `getLensGraph` never applied
   the node budget the viewer already had, so the lens handed elk 194 nodes and
   2,892 edges. Bounding nodes alone was not enough, since the kept nodes carry
   the edges with them; edges are the real driver. Now bounded centrally, so no
   lens can do this again. Full VS Code Rules lens: 1.5 s.

**Two lessons about the harness itself, both paid for:**

- **Every wait must be one Playwright enforces from Node.** The lens sweep first
  used `page.evaluate` to ask whether the page had settled. That takes an
  argument rather than options, so it carries no timeout, and on a main thread
  spinning at 100% CPU it never returns. The budget existed and never fired, and
  the suite hung exactly as the product had. A harness that hangs instead of
  reporting is the same failure as a product that hangs instead of rendering.
- **Do not pick the biggest thing as your representative.** The lens sweep chose
  the component with the most files, which on VS Code is `src/vs/workbench`, so
  every lens failed for the same unrelated reason and the sweep proved nothing
  about lenses. It now uses an upper-middle component, and the pathological end
  gets its own test where being the worst case is the point.

## What it does not cover yet

Named so the gaps are decisions rather than oversights:

- **Search.** `SearchOverlay` has no selector contract yet, so search results
  are not walked back to their targets. This is the next thing worth adding:
  the linter already proves every search entry resolves in the data, and the
  crawl should prove every result navigates in the UI.
- **The graph canvas.** Node positions are layout-engine output; asserting on
  them would be brittle. Reachability is checked through the tree and the URL.
- **Mobile viewport.** One desktop profile today. The AI plan covers the second
  viewport, and adding a project here is a config line when it is wanted.
- **Visual regression.** Deliberately out of scope. Screenshots are captured on
  failure only, as evidence, never as an assertion.
