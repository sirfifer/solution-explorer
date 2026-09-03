# Spec: the identity front door (option 1)

Status: ADOPTED 2026-09-03 by owner decision (see SHOW-ME-THE-APP.md section 7).
Ship gate: this must land before the VS Code demo goes public. Branch
`wt/ui-gateway-option1`, worktree `/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway`.

This document is the contract every delegated task in `tasks/` is written
against. Where a task and this spec disagree, this spec wins; report the
disagreement rather than resolving it silently.

## 1. What changes for the reader

Today the overview headline is a sentence about the snapshot and the portrait
puts 558 of 571 VS Code components into "Core system". After this spec:

- The headline says what the system is to a person, from markers in the
  checkout, with the file that proves each clause one click away.
- The maintainers' own description of the system is quoted, labelled as
  their claim, beside what the source shows.
- The portrait counts a user-interface subtree as user interface, so VS
  Code's workbench (4,281 files) stops being "core".
- The recommended path is the broadest guided tour, not the first one the
  enrichment happened to write. For VS Code that means the layering spine or
  the process model, never the agent host.
- Raw counts leave the first viewport. They stay in the trust ledger.

Nothing here calls a model. Every new statement is deterministic and carries
`statement_kind` of `observed_source_reference`, `repository_claim`, or
`deterministic_composition`.

## 2. Identity facts: a new derive pass

File: `analyzer/derive/identity.py`, registered in `derive_all`
(`analyzer/derive/pipeline.py`) after `derive.docs` and before
`derive.capabilities`, under the isolator name `derive.identity`. It reads
through `StoreView` / `StoreFS` only, never the disk. Output: `arch["identity"]`
as below, which must survive projection into `manifest.json` (top-level key)
in both split and monolithic modes.

### 2.1 Form-factor detectors

Each detector yields zero or more `form_factor` records. Every record names
the file (and line where a line is meaningful) that proves it. A record
without evidence is a bug.

| kind | Fires when | platforms | how_met |
|---|---|---|---|
| `desktop-app` | root or any component `package.json` lists `electron`, `@tauri-apps/api` or `tauri` in dependencies or devDependencies; or a `product.json` at root carries any of `darwinBundleIdentifier`, `win32x64AppId`, `win32arm64AppId`, `linuxIconName` (each key maps to its platform); or a component is typed `desktop-app` | from product.json keys; else `["macos","windows","linux"]` for Electron/Tauri with a note `platforms_assumed: true` | "installed and opened on a computer" |
| `ios-app` | component typed `ios-client`, or an `Info.plist` / `*.xcodeproj` under a component whose framework is SwiftUI or UIKit | `["ios"]` | "installed from the App Store on a phone or tablet" |
| `watch-app` | component typed `watch-app` | `["watchos"]` | "installed on a watch" |
| `android-app` | component typed `android-client` or an `AndroidManifest.xml` | `["android"]` | "installed on a phone or tablet" |
| `web-app` | a component typed `web-client` AND an `.html` file exists whose path contains `/browser/` or whose name is `index.html` and sits at that component's root; or root manifests name `next`, `nuxt`, `@sveltejs/kit`, `vite`, `react-scripts` | `["browser"]` | "opened in a web browser" |
| `cli` | component typed `cli-tool`; `package.json` has `bin`; `Cargo.toml` has `[[bin]]` or is a crate whose `src/main.rs` exists; `pyproject.toml` has `[project.scripts]`; Go repo has `cmd/<name>/main.go` (one record per binary, capped at 12) | `[]` | "run from a terminal" |
| `server` | component typed `api-server`, `service` or `server` with a port; or a root `Dockerfile`, `docker-compose*.yml`, `Procfile`; or a Kubernetes manifest (`kind: Deployment` or `kind: Service` in yaml under the repo) | `[]` | "deployed and reached over the network" |
| `plugin-host` | three or more `package.json` files under a top-level `extensions/` or `plugins/` directory carry a `contributes` or `engines.vscode` key; or a component typed `vscode-extension` | `[]` | "extended by plug-ins" |
| `infrastructure` | a Helm `Chart.yaml`, `*.tf` files, or CloudFormation templates | `[]` | "deployed as infrastructure" |
| `library` | none of the above fired AND a root manifest exists (`package.json` with `main` or `exports`, `pyproject.toml`/`setup.py`, `Cargo.toml` with `[lib]`, `go.mod` without `cmd/`) | `[]` | "used by other programs" |

Record shape:

```json
{
  "kind": "desktop-app",
  "label": "Desktop application",
  "platforms": ["macos", "windows", "linux"],
  "platforms_assumed": false,
  "how_met": "installed and opened on a computer",
  "component_id": "root",
  "evidence": [
    {"file": "product.json", "line": 30, "marker": "darwinBundleIdentifier"},
    {"file": "package.json", "line": 188, "marker": "devDependencies.electron"}
  ],
  "statement_kind": "observed_source_reference",
  "weight": 9708
}
```

`weight` is the count of mapped files under the component(s) the evidence
belongs to (root markers weigh the whole repo's mapped files). It ranks
primary against secondary form factors. Ties break by the table order above.

Dedupe: one record per `kind` per `component_id`; merge evidence lists.
Order records by `weight` desc then table order. Cap at 8 records; record
`truncated: true` when capped.

### 2.2 The authors' claim

From the root README (the `docs.readme` text the docs pass already
extracted): the first paragraph that is prose. Skip headings, badge lines
(lines starting with `[![` or `<img`), HTML, blockquotes and lists. Strip
Markdown links to their text. Cap at 400 characters on a sentence boundary.
Record `{ "text", "source": "README.md", "line", "statement_kind": "repository_claim" }`.
For VS Code this yields the paragraph beginning "This repository ("Code -
OSS") is where we (Microsoft) develop the Visual Studio Code product". That
is the correct first prose paragraph; do not skip ahead to a nicer one.

Absent README: `authors_claim: null`.

### 2.3 Languages and external services

`languages`: top three by mapped lines from `stats` (whatever key the stats
block already carries for per-language line counts; if none, from file
extensions of mapped files), each `{ "language", "share" }` with share as a
0 to 1 fraction rounded to two places.

`external_services`: the union of `external_services` across components,
each `{ "name", "component_id" }`, first 8 by component weight.

### 2.4 The statement

Composed deterministically in `human_views.py`, not in the derive pass, so
the fallback in the viewer can never disagree with it.

Template, in order, dropping absent parts:

1. `{Name} is {a|an} {primary.label lowercase}` plus, when primary has
   platforms that the label does not already name, ` for {platforms joined
   with commas and "and"}`. The label already names the platform for
   `ios-app`, `watch-app`, `android-app` and `web-app`, so those never get
   the clause; `desktop-app` does.
2. If secondary form factors exist: `, that also {phrase list}` where each
   phrase is from `how_met` rewritten to the "also" form (table: web-app
   "runs in a web browser"; server "runs as a server"; cli "is driven from a
   terminal by a command-line tool"; plugin-host "is extended by plug-ins";
   infrastructure "is deployed as infrastructure"; library "is used by other
   programs"; app kinds "has a {platform} app").
3. Sentence two: `It is written mostly in {lang1}` plus `, with {lang2}`
   when lang2 share ≥ 0.10.
4. Sentence three, only when external_services is non-empty: `It calls
   {names joined}.`

VS Code must produce, given the detectors above: "Visual Studio Code is a
desktop application for macOS, Windows and Linux, that also runs in a web
browser, is driven from a terminal by a command-line tool, and is extended
by plug-ins. It is written mostly in TypeScript, with Rust." The final
sentence depends on external_services detection and is not asserted.

When no form factor fired: `identity.statement` is null and the viewer
falls back to today's headline. Never invent.

Platform display names: macos → macOS, windows → Windows, linux → Linux,
ios → iOS, watchos → watchOS, android → Android, browser → the browser.

## 3. Orientation contract changes

Schema string stays `syscorpus.orientation/v1`; all changes are additive.

### 3.1 New `identity` block

```json
"identity": {
  "statement": "Visual Studio Code is a desktop application for ...",
  "statement_kind": "deterministic_composition",
  "primary": "desktop-app",
  "form_factors": [ ...records from 2.1... ],
  "authors_claim": { "text": "...", "source": "README.md", "line": 5, "statement_kind": "repository_claim" },
  "languages": [ {"language": "typescript", "share": 0.86}, {"language": "rust", "share": 0.11} ],
  "external_services": [ {"name": "GitHub", "component_id": "extensions/copilot/src/extension"} ],
  "truncated": false
}
```

`identity` is null when the derive pass produced nothing.

### 3.2 Portrait v2

Grouping (`_group_for`) gains ancestor inheritance: a component whose own
type is neutral (`module`, `content`, `package`, `library`, `fixture`,
`tooling`, `test-suite`, `test-fixtures`, `module (test suite)`) inherits
the group of its nearest ancestor that has a non-neutral group, walking up
the component tree. A component with a non-neutral type keeps its own
group. The data-word path rule keeps its current precedence for the
component itself but does not propagate to descendants.

Labels change to plain language. Keep the group ids.

| id | label | role |
|---|---|---|
| experience | User interface | What people see and use |
| core | Inner workings | Application and domain logic |
| services | Services and APIs | Runtime services and network boundaries |
| data | Data | Models, schemas, stores and migrations |
| operations | Tools and operations | Build, deploy and operate |

Each portrait node gains:

```json
"share": 0.28,
"representative": {
  "id": "src/vs/workbench",
  "name": "Workbench",
  "description": "Workbench: the desktop-editor UI shell and extension host bridge",
  "description_kind": "interpreted"
}
```

`share` is the group's mapped files over total mapped files, two places.
`representative` is `stable_targets[0]` with its description, first
sentence, capped at 140 characters; `description_kind` is `interpreted`
when the component's description came from `ai_enhance`, else
`deterministic`. When the representative has no description, omit
`description` and set `description_kind` to `unavailable`.

`portrait.method` becomes "component type and path grouping, with nested
components counted under their nearest typed parent".

### 3.3 Default path and the flow route

Tours are ranked by breadth: for each tour, the set of components that own
the step evidence files, weighted by each component's mapped file count,
divided by total mapped files. Highest breadth wins; ties by tour order.
`orientation.default_path` gains `"reason": "broadest guided path: touches N
components holding P% of mapped files"`.

The flow question route uses the ranked tour when no Flow lens data exists.
Its label becomes "How does the code fit together?" in that case; it stays
"How does the core experience work?" when the Flow lens is available. The
question `id` stays `flow` in both cases.

## 4. Viewer

File: `viewer/src/components/SystemOverview.tsx`, plus `viewer/src/types.ts`
(`OrientationProjection.identity`, `OrientationNode.share` and
`.representative`, `default_path.reason`) and
`viewer/src/utils/orientation.ts` (fallback emits `identity: null`, portrait
nodes without `representative`).

Portrait posture, top to bottom in the left column:

1. Eyebrow "{name} at a glance".
2. H2: `identity.statement` when present; else the current opening
   statement logic unchanged.
3. Form-factor row: one chip per `form_factors` record: `label`, platforms
   in small text, and a provenance mark ("observed in source"). Clicking a
   chip opens a small popover listing each evidence `file:line` and
   `marker`; a chip with a `component_id` that is not root also offers
   "Open in workbench" which calls `openComponent`. Chips wrap; no
   horizontal scrolling.
4. "In the maintainers' words": `authors_claim.text` as a blockquote, with
   the caption "README.md at commit {subject commit short}, repository
   claim". Hidden when null.
5. Details disclosure "Interpreted summary" holding the AI interpreted
   statement, with the existing stale-withheld behaviour. This replaces the
   H2's use of the interpreted text: the interpreted text is never the
   headline when `identity.statement` exists.
6. Deployment posture panel, unchanged.
7. The three question cards, unchanged.
8. One line of small text: "{components} components · {files} files ·
   {relationships} relationships · full ledger →" opening the trust drawer.
   The four `Scale` tiles are removed from the Portrait posture. They stay
   in the Questions answers.

Right column, the portrait panel: heading becomes "{n} areas of the system".
Each card shows `label`, then `representative.name` in bold with
`representative.description` in two lines, then "{member_count} components
· {share as percent}". A tiny provenance mark shows "interpreted" when
`description_kind` is interpreted. Card click behaviour unchanged.

The posture chooser ("Choose the opening posture") moves to the right end
of its row as a compact segmented control labelled "Other ways in"; keep
`data-testid="overview-direction"`, `data-direction`, `data-selected` and
the three values exactly.

All existing `data-testid` and `data-se` hooks stay: `system-overview`,
`overview-direction`, `portrait-card` with `data-node-id` and
`data-target`, `question-route`, `question-route-continue`,
`open-workbench`, `search-button`. New hooks: `identity-statement` on the
H2 when it renders the identity, `form-factor` on each chip with
`data-kind`, `authors-claim` on the blockquote.

Dark mode, mobile (390 px) and reduced motion must all hold. The mobile
overview must not scroll horizontally.

## 5. A script to regenerate orientation without re-parsing

`scripts/reorient.py <projection-dir> [--check]`: loads `manifest.json`,
`coverage.json`, `support.json`, `security.json` (the latter three optional),
calls `build_orientation`, writes `orientation.json` in place, or with
`--check` prints a unified diff against the existing file and exits 1 on
difference. It warns, and exits 2, when `manifest.json` has no `identity`
key, because that projection predates the identity pass and needs a full
reprojection. This exists so viewer work and portrait changes can be
checked on the real VS Code and UnaMentis bundles in seconds.

## 6. Verification, in order

1. `pytest tests/ -q` under the worktree venv (`.venv-wt/bin/python -m pytest`).
   Expect the known single worktree-only failure and nothing new.
2. `ruff check analyze.py analyzer/ scripts/ tests/`.
3. `scripts/golden-corpus.py check flask` and `check fastapi`: the identity
   key is a deliberate addition; report the diff, do not refresh baselines.
   The orchestrator refreshes them at integration.
4. Viewer: `npx tsc --noEmit`, `npx eslint src/`, `npx vitest run` (86
   localStorage failures are environment noise; diff the failing file set
   before and after).
5. Reprojection of both canonical subjects (orchestrator step, venv
   interpreter, copies of the stores, never the originals):

```
.venv-wt/bin/python analyze.py /Volumes/Studio/dev/.demo-corpus/vscode \
  --engine v2 --store <copy of vscode index.db> --output .testboard/derived/vscode/architecture --split
.venv-wt/bin/python analyze.py /Volumes/Studio/dev/unamentis-ios \
  --engine v2 --store <copy of unamentis index.db> --output .testboard/derived/unamentis-ios/architecture --split
```

6. Serve both with `scripts/assemble-serve.py` and run the crawl with this
   worktree's harness (`CRAWL_BASE_URL=... CRAWL_PROFILE=quick npx playwright
   test -c tests/crawl/playwright.config.ts` from `viewer/`). O1 to O8 must
   pass on both; O9 and O10 (added by UG-6) must pass on VS Code.

## 7. Acceptance for the whole option

- VS Code overview headline reads the statement in 2.4, with a chip per
  form factor and evidence on click.
- VS Code portrait: "User interface" holds the workbench subtree; no group
  holds more than 70 percent of components; every card shows a
  representative with a description.
- VS Code "How does the code fit together?" opens the layering-spine or
  process-model tour, never agent-host, and the answer panel names the
  tour and the reason.
- UnaMentis iOS: headline names an iOS app (and the watch app), the Flow
  lens route keeps its label and target, and nothing that passed the
  2026-09-02 gate regresses (56/56).
- No count tile in the first viewport of the Portrait posture at 1440×900
  or 390×844.
- Every new statement on the page carries a provenance mark.
