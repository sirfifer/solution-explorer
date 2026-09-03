# Show Me the App: the front door for a first-time viewer

Status: PROPOSAL, written 2026-09-03 for owner review. Analysis only; nothing
implemented. Evidence was taken from the VS Code demo running locally at
`http://127.0.0.1:5175/?mode=overview` (bundle `.testboard/serve/vscode`,
commit `474a349a`, generated 2026-09-01), from the served bundle's
`orientation.json` and `manifest.json`, from the VS Code checkout at
`/Volumes/Studio/dev/.demo-corpus/vscode`, and from web research on
comparable products. Screenshots are in this directory.

## 1. The question

The owner asked: when someone who is not a developer, and may not even know
whether the subject is a phone app, a web site, a desktop program or a
server, opens the overview for the first time, do they glide into a usable
space where they come to understand what the thing is and how it works? The
sharper claim behind the question: for anything with a user interface, an
abstract representation of the code is not good enough as the first
encounter. The interface itself should be the gateway. Hover a control to
learn what it does, click it to go where it goes, and see honestly what the
code does on that journey. For subjects with no interface (Kubernetes is the
next demo) the top level has to be an executive summary that leans on a
diagram and drills into mechanism. Everything must stay tied to what is in
the source, with the repository's own documentation used as a claim to be
checked, never as the truth.

## 2. What a newcomer sees today

The overview is well built for what it tries to do. The trust posture is
right: "How do we know?" links, claims separated from observed references,
the mapped-files chip, "Unpublished preview" banner. Overview and Workbench
are one click apart in both directions, so getting back to the start is
solved. The Questions posture is the best surface on the page. None of that
should regress.

The gaps are in what the page says, not how it is built.

### F1. The page never says what VS Code is to a person

The headline reads: "This snapshot contains the Visual Studio Code source
code at the recorded Microsoft repository commit." That is a sentence about
the snapshot. The line under it is a sentence about the map ("571 mapped
components across 4 system areas, connected by 5453 relationships"). Nowhere
above the fold does it say: a desktop program for editing code that you
install on Mac, Windows or Linux, which also runs in a browser, ships a
command-line tool and a remote server, and is extended by plug-ins. The
interpreted statement does contain "Electron main, browser renderer, Node,
and web-worker targets" and "a Rust command-line interface", but only behind
"Read the full system description", and phrased for engineers.

The facts needed for a plain statement are deterministic and in the repo:
`package.json` names `./out/main.js` as the Electron entry; `product.json`
carries `darwinBundleIdentifier`, `win32x64AppId` and `linuxIconName`, which
is a desktop application on three platforms by construction; `src/vs/server`
and `resources/server` are the remote server; `cli/` is the Rust CLI;
`extensions/` holds 95 built-in extension manifests. The tool has all of it
and states none of it.

### F2. The portrait is not a portrait

The "System portrait" shows four areas: Experiences (5 components), Core
system (558), Data & persistence (3), Operations & tools (5). It is a
grouping by component type and path, and for VS Code that grouping puts 98%
of the system into one box. The five "Experiences" members include
`extensions/copilot/test/simulation/workbench`, a test harness. "Data &
persistence" is the editor's text model plus two directories of JSON
schemas.

What a person would recognise as the portrait of VS Code exists as
directories: `src/vs/workbench/browser/parts/` contains `titlebar`,
`activitybar`, `sidebar`, `editor`, `panel`, `statusbar`, `auxiliarybar`,
`notifications` and `dialogs`. Those are the regions of the window every
user has looked at. Beside them: the editor core (`src/vs/editor`), the
extension host (`src/vs/workbench/api`), built-in extensions, the remote
server and the CLI. A portrait built from surfaces and processes would be
recognisable; the one built from types is not.

### F3. "How does the core experience work?" answers with the wrong experience

The question routes to the `agent-host` tour ("the platform-level subsystem
that connects Claude, Codex, and Copilot CLI agents into the editor").
That is the newest subsystem in the snapshot, not the core experience. A
first-time visitor who follows the recommended path would conclude VS Code is
a host for AI coding agents. The route is chosen as the orientation's
default path (`orientation.default_path = agent-host`), which the
orientation builder picks without any notion of what the product's primary
experience is. The `layering-spine` and `process-model` tours are closer to
the truth of the system, and none of the four is "a person opens a folder
and edits a file".

### F4. There is no picture of anything

The overview is text, four count tiles and four cards. The first image a
visitor meets is the Workbench graph: six boxes named `test`, `bin`,
`code-cli`, `src`, `scripts` and `vscode-extensions` joined by dotted lines
(see `workbench.jpg`). That is the "representation of a representation" the
owner described. It is honest and it is navigable, and it tells a
non-developer nothing they can recognise. The device-frame rendering that
carried the UnaMentis study (iPhone bezels, terminal chrome) does not help
here because VS Code's top level has no client-typed node to frame; its only
client is the 4-file CLI.

### F5. The model knows about interfaces only for iOS

The analyzer has a real UI vocabulary: component types `screen`, `tab`,
`tab-container`; relationship types `navigation`, `modal`, `tab`, `embed`;
`UIAction` records with `label`, `action_type`, `handler`, `file`, `line`
and `target_view`. It is populated by two derivations, SwiftUI navigation
(`analyzer/swiftui_flow.py`) and Interface Builder storyboards
(`analyzer/derive/storyboard.py`). On the UnaMentis iOS bundle that yields
71 screens, 34 navigation edges, 12 modal edges, 5 tabs and 13 actions, and
the Flow lens lists 36 entry flows. On VS Code it yields zero screens, zero
navigation edges and 8 actions, all of them inside test fixtures under
`extensions/copilot/src/platform/parser/test`.

Meanwhile the VS Code repository declares its interface in machine-readable
form and the tool ignores it:

| Declared UI surface in the checkout | Count |
|---|---|
| Built-in extension manifests with `contributes` | 95 |
| Contributed commands | 487 |
| Contributed menu items | 850 |
| Contributed keybindings | 78 |
| Source files calling `registerAction2` | 357 |
| `MenuId.CommandPalette` references | 205 |
| `MenuId.ViewTitle` / `EditorTitle` / `EditorContext` references | 151 / 116 / 42 |

Every one of those is a control a user can reach, with a handler symbol,
a file and a line. No web route extraction exists either (no React Router,
Next.js pages or Angular route derivation in `analyzer/`), so a web app
would be as blind as VS Code is.

### F6. The numbers lead, and they mean nothing to the audience

The first row of hard facts a novice reads is 571, 15,204, 5,453 and
3,938,860. Those belong on the trust ledger, one click away. They are shown
prominently because they are what the tool is proud of, not because a
newcomer can use them.

### F7. Minor: "Choose the opening posture" is a choice before understanding

Three postures are offered before the visitor knows what a posture is. The
Portrait default is right; the chooser could be demoted to a quiet
secondary control once the Portrait carries an identity statement.

## 3. What others do

Research summary; every claim below was checked against the linked source
on 2026-09-03.

**Nobody grounds a user interface in code.** The interactive-demo tools
(Arcade, Storylane, Navattic, Guideflow) have solved the overlay mechanics:
capture a screen as an image or as a DOM clone, auto-detect clickable
regions, place tooltips, chain screens into a click-through. Their hotspots
are authored by a person or guessed by a model from the picture; none link
to the implementation. Sources: arcade.software/post/click-through-software,
docs.storylane.io/recording-demos/recording-html-demos.

**The one product that links a rendered surface to its source is
Storybook with Chromatic**: a rendered component opens directly on the code
that renders it (chromatic.com/blog/connect-figma-to-storybook). It is
component-level, not screen-level, and depends on the team maintaining
stories.

**Screen graphs from running apps are a solved research problem.** Rico
(66k Android screens paired with view hierarchies), Stoat and APE (screen
transition models built by fusing static analysis with runtime exploration),
Maestro Studio (click a live screenshot, get the underlying element). All
require the app to run. Sources: dl.acm.org/doi/10.1145/3126594.3126651,
github.com/tingsu/Stoat, maestro.dev.

**The closest existing shape to "click through and see what the code did"
is the Playwright Trace Viewer**: synchronized screenshot, step list, DOM
snapshot, network calls and source location per step (playwright.dev/docs/
trace-viewer). AppMap does the same for the server side, recording HTTP,
function and SQL calls as a trace diagram (appmap.io). Both are forensic
tools for developers; the three-pane layout is what to borrow.

**Codebase-explanation products all open on prose or a graph.** DeepWiki
opens on a generated architecture diagram and wiki; it has been documented
asserting a non-existent installation method as the primary one
(blopker.com/writing/12-deepwiki). GitDiagram makes one clickable Mermaid
diagram from the tree and README. Sourcetrail was discontinued in 2021 and
CodeSee was folded into GitKraken in 2024: pure structural graphs did not
survive as standalone onboarding products. Structurizr's C4 model (Context,
Container, Component, Code) is the accepted altitude ladder for the
diagram-led path and is what enterprises actually use to onboard.

**For Kubernetes, the reference to beat is kubernetes.io's own Components
page**: one diagram, two zones (control plane, nodes), each exploded into
named parts with one line of purpose. KubeDiagrams and KubeView draw
deployed resources, not the source that implements them. No tool drills
from that diagram into the controller code.

**For honesty, Swimm's Smart Tokens** bind a documentation claim to a code
symbol and re-verify on every commit, flagging drift (swimm.io). That is the
mechanism for showing a README claim beside what the code does.

The white space is exactly the owner's idea: a comprehension surface where
the interface is the map and every hotspot resolves to a symbol, a handler,
a target screen and the observed calls on the way. The failure modes to
avoid are also clear: a graph with no story (Sourcetrail), confident
narration with no citation (DeepWiki), and pictures with no code behind them
(the demo tools).

## 4. The proposal

Three layers, in the order a person needs them. Each is deterministic first,
with enrichment allowed only to phrase what the parser already established,
and each row carries the same two-tier statement kind the deployment posture
already uses: `observed_source_reference` or `repository_claim`.

### Layer A. The identity card: what is this, to a person

A new deterministic projection, `identity` inside `orientation.json`, that
answers five things in one paragraph and a row of facts:

1. **Form factors.** Desktop application, web application, iOS app, watch
   app, command-line tool, server, library, cluster. Derived from markers the
   scanner mostly already reads: Electron entry plus `product.json` platform
   identifiers, Xcode projects, `Dockerfile`, Helm charts, `cmd/` binaries,
   `bin` fields, `setup.py` console scripts.
2. **How a person meets it.** Installed and opened, visited in a browser,
   run from a terminal, deployed and operated. Derived from the form factors.
3. **Who it is for.** The README's own first paragraph, quoted and labelled
   as the authors' claim, with the date of the commit.
4. **What it is made of.** Languages by mapped lines, in words.
5. **What it talks to.** The external services already extracted, in words.

For VS Code the card would read, in plain language: a desktop program for
editing code, installed on Mac, Windows and Linux, which also runs in a
browser and as a remote server, driven from a terminal by a command-line
tool, and extended by plug-ins; written mostly in TypeScript with a Rust
CLI; it calls GitHub, OpenAI, Anthropic and Google AI from the Copilot
extension. Every clause with its evidence link.

The portrait is regrouped around this card: surfaces and processes first
(the window and its parts, the editor, the extension host, extensions, the
server, the CLI), with the type-based grouping kept as the fallback when no
surface can be found.

### Layer B. The face of the system: the interface as the map

Only for subjects with a form factor a person looks at. Three sources of
imagery, used in this order of honesty, with the source stamped on every
image:

- **B1. Author-provided.** Images the maintainers put in README and docs.
  VS Code's README carries one "VS Code in action" image, hosted on GitHub
  rather than in the tree. Cheap, fully honest, often absent, never
  hotspot-able beyond a whole-image link.
- **B2. Structural render.** A wireframe of each screen drawn from the code's
  own declared structure, without running anything: SwiftUI view trees and
  storyboard scenes for iOS; `workbench/browser/parts` and the contribution
  points for VS Code; routes and page components for web apps. Always
  available, honest by construction, and it is the skeleton the hotspots
  attach to. This is the layer that makes the screen graph the tool already
  derives for iOS visible instead of being a ranked list in the Flow lens.
- **B3. Real captures.** Build and run the subject, walk the derived screen
  graph, capture each screen with its accessibility tree or DOM. Web apps
  via Playwright; Electron via Playwright's Electron driver (VS Code already
  ships a Playwright-driven smoke test harness under `test/automation` and
  `test/smoke`); iOS via the simulator and XCUITest or Maestro. Highest
  impact, and the only tier that costs a per-subject build recipe.

**Hotspots are code-bound, not picture-bound.** A hotspot is a record:
region, control label and kind, `file:line` of the declaration, handler
symbol, and what follows from the handler: the target screen if it
navigates, the command it runs, the endpoints and entities reached through
the existing relationship graph, and any validation found on the path.
Hover shows the label and the deterministic "what it does"; click either
moves to the target screen's image or opens the journey panel. In B2 the
region comes from the wireframe's own layout; in B3 it comes from the
accessibility tree at capture time, matched to the declaration by
identifier, label or test id. A control with no handler found is shown as a
control with no handler found.

**The journey panel** is a Playwright-trace-shaped view: the screen on the
left, the steps in the middle (handler, calls, endpoint, entity), the
evidence on the right. It exists for both UI subjects and backend subjects,
because a CLI command, an HTTP request or a `kubectl apply` is an entry in
exactly the same sense as a button. Form validation, which the owner named,
needs one new extractor (validators attached to a form's submit path) and
is cheap once the journey panel exists.

### Layer C. The runtime picture: the executive diagram for everything

One generated diagram at C4 "container" altitude: the processes, binaries
and deployables of the system and the observed channels between them
(http, websocket, grpc, ipc), each box opening into its mechanism. The
existing `process-model` tour for VS Code ("which process runs this code")
is the seed; it becomes the picture instead of a tour.

For Kubernetes this is the whole front door. The repository's `cmd/`
directory holds the binaries (kube-apiserver, kube-controller-manager,
kube-scheduler, kubelet, kube-proxy, kubectl), which is the same set of
boxes as kubernetes.io's Components diagram, so the deterministic runtime
picture and the project's own explanation of itself agree by construction.
The drill from each box is the mechanism: what it watches, what it writes,
which API groups it serves. To be confirmed at the Kubernetes
reconnaissance, not assumed.

### What stays out

No generated mockups, no model-drawn screens, no captions a parser did not
establish. Every image carries its tier, commit and capture date. When a
screen has no capture, the wireframe says so. When the README claims a
surface the code does not contain, the identity card shows the claim and
the absence side by side. That is the product's promise and the only thing
that separates it from the demo-tool category.

## 5. Options

| Option | What ships | Effort | For | Against |
|---|---|---|---|---|
| **1. Fix the overview with what we have** | Identity card from existing signals; portrait regrouped around surfaces and processes; core-experience route corrected; counts demoted to the trust ledger; README image as a stamped hero where one exists | Days. Analyzer projection plus overview changes; no new parsing | Repairs F1, F2, F3, F6 before the VS Code demo goes public; subject-agnostic; zero model spend | Still no picture for subjects without README imagery; does nothing for F4 and F5 |
| **2. Structural screen map (B2) with code-bound hotspots** | Wireframe screens from derived structure; hotspot records; journey panel; VS Code contribution-point and workbench-part extraction; web route extraction | 3 to 5 weeks. New derivations, new projection, new viewer surface | Honest by construction; needs no build; UnaMentis works on day one from the existing screen graph; it is the skeleton B3 needs anyway | Wireframes are recognisable but not the real face; VS Code's window model needs a hand-written layout rule for the workbench parts |
| **3. Real captures (B3) via a subject build-and-crawl harness** | Per-subject build recipe, screen walk, captures with accessibility trees, hotspots matched to declarations | 4 to 8 weeks plus a recipe per subject; VS Code and UnaMentis both already ship automation harnesses | The owner's full vision; the demo-tool polish with the code behind it, which nobody else has | Highest cost; a build that fails silently produces a blank; captures must be re-taken on every snapshot; depends on option 2 for the hotspot skeleton |
| **4. Runtime picture (Layer C) and the journey panel for non-UI subjects** | Generated container diagram from processes and channels; drill into mechanism; entry-to-effect journeys for CLI, API and controller entries | 3 to 5 weeks; shares the journey panel with option 2 | Required before Kubernetes; also improves VS Code (process model becomes the picture) | Not the UI story; diagram quality depends on process detection which today is a tour, not a projection |

## 6. Recommendation

Do option 1 now, before the VS Code demo publishes; it removes the four
defects a first visitor hits in the first minute and costs days. Then build
option 2 as the durable skeleton, because option 3 needs its hotspot model
regardless and because it makes the iOS screen graph the tool already has
visible. Run option 4 in parallel with option 2 since they share the journey
panel and Kubernetes cannot ship without it. Take option 3 per subject only
when a build recipe is cheap: UnaMentis first (we control it), VS Code
second through its own smoke-test harness.

The sequence keeps the honesty ladder intact: nothing is ever shown that the
source did not establish, and each tier that adds fidelity adds its own
provenance stamp.

## 7. Owner decisions (recorded 2026-09-03)

1. **Option 1 ships before the VS Code demo goes public.** The overview fix
   (identity card, portrait regrouped around surfaces and processes,
   corrected core-experience route, counts demoted to the trust ledger) is
   now a gate for publication.
2. **Layer order confirmed:** identity card, then structural screens with
   code-bound hotspots, then real captures.
3. **VS Code is the first capture subject**, not UnaMentis. The capture
   harness will be built against VS Code's own Playwright smoke-test
   automation under `test/automation` and `test/smoke`. UnaMentis follows.
4. **Kubernetes stays third in wave 1**, and the runtime picture with the
   journey panel (option 4) is its gate. Option 4 runs in parallel with
   option 2.

Implementation of option 1 has not started. It should begin on a fresh
worktree with its own branch, per the no-regression protocol, and be
validated against both the VS Code and UnaMentis bundles before merge.
