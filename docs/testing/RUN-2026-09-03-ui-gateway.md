# The identity front door, 2026-09-03: what shipped, what it says, what is still open

Executes option 1 of `docs/research/ui-gateway/SHOW-ME-THE-APP.md` against the
contract in `SPEC-OPTION1-IDENTITY-FRONT-DOOR.md`, task contracts UG-1, UG-2,
UG-4, UG-6 and UG-7. Branch `wt/ui-gateway-option1`, worktree
`/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway`, committed
locally and never pushed. Both canonical subjects were reprojected from copies
of their stores, served on 5185 and 5186, and crawled with this worktree's
harness. The owner's demos on 5175 and 5176 were not touched.

## What a first-time reader now sees

The VS Code overview opens on this sentence, composed deterministically from
markers in the checkout:

> Visual Studio Code is a desktop application for macOS, Windows and Linux,
> that also runs in a web browser, is driven from a terminal by a command-line
> tool, and is extended by plug-ins. It is written mostly in TypeScript. It
> calls GitHub, OpenAI, Anthropic and Google AI.

Under it, five chips, each opening on the file that proves it:

| Chip | Component | Evidence |
|---|---|---|
| Desktop application (macOS, Windows, Linux) | root | `package.json:221 devDependencies.electron`, `product.json:20 win32x64AppId`, `product.json:21 win32arm64AppId`, `product.json:28 darwinBundleIdentifier`, `product.json:31 linuxIconName` |
| Web application (the browser) | `src/vs` | `src/vs/code/browser/workbench/workbench.html` html entry |
| Extensible by plug-ins | `extensions` | `extensions/bat/package.json:15`, `extensions/clojure/package.json:15`, `extensions/coffeescript/package.json:15`, each `contributes` |
| Command-line tool (cli) | `cli` | `cli/Cargo.toml:11 [[bin]]`, component typed cli-tool |
| Command-line tool (json-language-features/server) | `extensions/json-language-features/server` | `extensions/json-language-features/server/package.json:11 bin` |

Then the maintainers' own paragraph, quoted and captioned "README.md at commit
474a349, Repository claim", then the interpreted AI summary demoted into a
disclosure, then the deployment posture, then the three question cards, then one
line reading "571 components, 15,219 files, 5,454 relationships, full ledger"
that opens the trust drawer. No count tile is in the first viewport at either
size.

UnaMentis iOS opens on "unamentis-ios is an iOS app, that also has a watchOS
app. It is written mostly in Swift. It calls OpenAI, AssemblyAI, Deepgram, Groq,
ElevenLabs, Anthropic and Google AI." with two chips.

## The four-bucket split of everything found

| Bucket | What it costs | What went here |
|---|---|---|
| A. Viewer or crawl code | minutes | the whole of UG-4 and UG-6; the chip-detail and under-1% fixes found at integration |
| B. Deterministic sidecar or assembly step | seconds | the whole of UG-2; the subject-name review correction |
| C. Deterministic re-parse of the same commit | about seven minutes for VS Code, zero model calls, enrichment re-attaches | the whole of UG-1 and the identity prune |
| D. Paid enrichment | model spend | nothing. No model call was made anywhere in this work |

## What changed, by task

**UG-1, `analyzer/derive/identity.py`.** A new deterministic derive pass,
`derive.identity`, registered after `derive.docs` and before
`derive.capabilities`. Ten form-factor detectors, the README's first prose
paragraph as a labelled claim, language shares over code languages, and the
external services already extracted. `arch["identity"]` is a top-level key, so
it rides into `manifest.json` and `architecture.json` untouched; it is null
rather than absent when the pass degraded, so a consumer can tell "no identity
derived" from "this projection predates the pass". Each detector runs under the
driver's isolator, so one marker reader that trips records an honest gap and the
other form factors still reach the reader.

**UG-2, `analyzer/project/human_views.py`.** `build_orientation` emits the
identity block with the statement composed here, not in the viewer, so the
browser fallback can never phrase the same facts differently. Portrait v2 lets a
typed parent speak for its subtree. The recommended path is the tour whose
evidence reaches the most mapped files, with a reason. The flow question keeps
its id and, without a Flow lens, is renamed.

**UG-4, `viewer/src/components/IdentityCard.tsx` and `SystemOverview.tsx`.** The
Portrait posture leads with the statement, the chips and the quoted claim; the
interpreted summary is a disclosure; the four count tiles become one line into
the trust ledger; the posture chooser is a quiet control labelled "Other ways
in". Portrait cards name the component a click opens, with its description and
whether that description was interpreted or read from the source.

**UG-6, `scripts/reorient.py` and crawl rules O9 and O10.** The script rebuilds
`orientation.json` for an existing projection in seconds. O9 holds the headline
and the chips to the sidecar and opens one chip to reach its evidence; O10
measures that no count tile is in the first viewport. Both run desktop and
mobile, so the crawl total is 60, not 56.

**UG-7, this record.** Reprojection, serving, crawls, screenshots, and the
review correction below.

## Defects the real subjects exposed, and what was done

Four of these were invisible against a fixture and only appeared on the first
VS Code reprojection.

1. **A detector citing a file because one was needed.** A component-type
   detector that found no manifest fell back to the component's first source
   file. That put "runs as a server" in the opening sentence on the strength of
   `extensions/terminal-suggest/src/completions/azd.ts`, a shell-completion spec
   the roles pass had typed `api-server` on a port scraped out of a string.
   Fixed: the server and cli component-type detectors now require a marker that
   declares how the software is run, and do not fire without one.

2. **The identity pass runs a tier below the corrections that contradict it.**
   `derive.identity` reads component types at tier 3; the enrichment's identity
   verdicts correct those types at tier 4, after it has run. A record whose only
   proof was "component typed api-server" outlived the correction saying the
   component is a module. Fixed: `project.identity-prune` re-checks every record
   against the corrected types after the verdict overlay. This is a patch over a
   layering problem, not a solution to it; see the open items.

3. **The same command-line tool twice.** A component-typed CLI carried the
   component's name while the same claim from its Cargo manifest carried none,
   so the two never merged. Fixed by dropping the name from the component-typed
   record.

4. **The strongest evidence dropped by the cap.** A merged root record was
   spending its six-row cap on nested extension manifests before it reached
   `product.json`. Fixed: evidence is ordered shallowest file first.

5. **`.testboard/derived/<subject>/architecture` is not a safe output path.**
   UG-7's command block names it, and it is exactly the directory
   `scripts/assemble-serve.py` deletes and rebuilds as its own overlay. The
   first assemble destroyed a seven-minute VS Code projection. The projections
   for this run live in `.testboard/projections/<subject>/architecture` instead.

6. **Two identical chips said nothing.** With the name dropped, the two
   command-line tools rendered as two identical chips. The chip's small text now
   falls back to the last part of the component path, and the evidence panel
   carries the whole of it.

7. **A card reading "0%".** An area the analyzer rounded to 0.00 rendered as
   "0 percent", which is a different statement from "small". It now reads
   "under 1%".

## Owner review, same day: two corrections

The bundle was served for owner review and two things came back.

**The demo lost its Atlas theme.** `viewer/.env.vscode-demo` pins
`VITE_DEFAULT_THEME=atlas`, and Vite loads that file only for a build run with
`--mode vscode-demo`. `scripts/assemble-serve.py` ran a plain `npm run build`,
which is production mode, so the file was ignored and the served bundle fell
back to Signal. Every bundle this script has assembled had the same problem; it
became visible now because the front door was being looked at closely.
`build_viewer` now builds in `<slug>-demo` mode whenever
`viewer/.env.<slug>-demo` exists. The two subjects share one build, so the
UnaMentis bundle assembled beside VS Code inherits the VS Code demo's theme
default; per-subject themes would need a build each.

**The headline was informationally right and visually wrong.** The whole
composed statement was the H2, in black bold at up to 3.25rem, which on VS Code
is eight lines occupying the entire left column above the fold, under a tiny
eyebrow that repeated the subject's name. It is now a title and a subtitle: the
subject's name as the H2 at `text-3xl sm:text-4xl`, and the statement under it
as body text at `text-base sm:text-lg`.

The subtitle is not the statement with a prefix chopped off in the browser.
`compose_identity_summary` in `human_views.py` composes the same facts from the
same records without the subject clause, beside `compose_identity_statement`, so
`identity.summary` reads "A desktop application for macOS, Windows and Linux,
that also runs in a web browser, ..." and the two forms cannot drift apart. The
sidecar carries both; O9 checks the rendered subtitle against `summary` when the
sidecar has one and against `statement` when it does not.

The counts sentence ("Visual Studio Code contains 571 mapped components across 5
system areas ...") no longer renders when an identity statement leads: it is the
same numbers the demoted count line already carries, which was the point of
demoting them. A bundle with no identity keeps it.

The Portrait posture remains the opening posture. `overviewDirection` defaults
to `portrait` in `store.ts`, this branch does not touch that file, and "Atlas"
in the owner's report meant the theme, not the posture.

## The review correction, stated plainly

`demos/review-corrections/vscode.json` gains one `manifest_edits` entry setting
the subject name from `vscode` to `Visual Studio Code`. This is a human review
correction, not a detector inference, and it applies only to the derived serving
assembly; the canonical projection is untouched.

It exists because the analyzer names a subject after the directory it scanned,
and the name leads the identity statement. Without it the headline reads "vscode
is a desktop application", while the page header and the repository's own README
both say Visual Studio Code. The repository's machine-readable names are
`code-oss-dev` (package.json) and `Code - OSS` (product.json), so no detector
can produce "Visual Studio Code" deterministically. Removing the one entry backs
the change out completely.

`ai.json` and `llms.txt` are symlinked from the projection and still say
`vscode`. Not corrected; noted.

## Acceptance, spec section 7, line by line

| Line | Verdict | Evidence |
|---|---|---|
| VS Code headline reads the statement in 2.4, with a chip per form factor and evidence on click | met, with one data-explained difference | `docs/testing/ui-gateway-screens/vscode-1440x900-light.png`; crawl O9 desktop and mobile; sentence 1 is character for character the spec's, sentence 2 reads "It is written mostly in TypeScript" without ", with Rust" because Rust is 1% of mapped code lines against the 10% threshold in spec 2.4 |
| Portrait: "User interface" holds the workbench subtree | met | `orientation.json` portrait, `orientation:experience` member_count 18 with representative `src/vs/workbench`; the same grouping with the old rule gives 5 |
| Portrait: no group holds more than 70 percent of components | NOT met | "Inner workings" holds 534 of 571, 94%. By mapped files it holds 58%. Ancestor inheritance is the whole of what spec 3.2 asks for and it does not reach 70% on this subject; see open items |
| Portrait: every card shows a representative with a description | met | all five cards; four interpreted, one deterministic (`extensions/copilot/docs/monitoring`) |
| "How does the code fit together?" opens layering-spine or process-model, never agent-host, and the answer names the tour and the reason | met | flow route target `{lens: structure, tour_id: layering-spine}`; `default_path.reason` reads "broadest guided path: touches 7 components holding 26% of mapped files" |
| UnaMentis: headline names an iOS app and the watch app | met | "unamentis-ios is an iOS app, that also has a watchOS app." |
| UnaMentis: the Flow lens route keeps its label and target | met | `{id: flow, label: "How does the core experience work?", target: {lens: flow, tour_id: live-voice-loop}}` |
| UnaMentis: nothing that passed the 2026-09-02 gate regresses | met, on a caveat | 60 of 60 cases pass, which is the 2026-09-02 gate's 56 plus O9 and O10 at both sizes. The caveat is the projection, not the viewer: see the file-count note below |
| No count tile in the first viewport at 1440x900 or 390x844 | met | measured directly during the screenshot capture (0 tiles in view at both sizes, both subjects) and by crawl O10 at 1280x720 and 390x664 |
| Every new statement carries a provenance mark | met | chips carry "Observed source reference", the quote carries "Repository claim", the representative carries "interpreted" when it is, the statement carries `statement_kind: deterministic_composition` |

## Crawl numbers

Quick profile, desktop and mobile, this worktree's harness, run directly rather
than through the control plane.

| Subject | Origin | Cases | Findings | O9 | O10 |
|---|---|---|---|---|---|
| Visual Studio Code | `http://127.0.0.1:5185` | **60 / 60** | none, error or warning | checked the statement and 5 chips against the sidecar, both sizes | 0 count tiles at 1280x720 and 390x664 |
| unamentis-ios | `http://127.0.0.1:5186` | **60 / 60** | none, error or warning | checked the statement and 2 chips against the sidecar, both sizes | 0 count tiles at 1280x720 and 390x664 |

The store copies stay at `.testboard/stores/<subject>/index.db` (1.0 GB and
53 MB, gitignored) so a re-run needs no recopy.

Run records: `.testboard/runs/2026-09-03T17-06-04-800Z-crawl-Visual-Studio-Code`
and `.testboard/runs/2026-09-03T17-08-21-793Z-crawl-unamentis-ios`, each with
`REPORT.md`. Both are gitignored, as `.testboard/` is.

VS Code lens entry times under the crawl's two workers: structure 0s, inventory
0s, activity 0s, capability 0s, data 0s, rules 1s, support 0s, security 0s. The
2026-09-02 record measured rules at 8s and security at 7s on the same subject;
the change is not attributable to anything in this branch and was not
investigated.

## Screenshots

`docs/testing/ui-gateway-screens/`

- `vscode-1440x900-light.png`, `vscode-1440x900-dark.png`
- `vscode-390x844-light.png`, `vscode-390x844-dark.png`
- `unamentis-ios-1440x900-light.png`, `unamentis-ios-1440x900-dark.png`
- `unamentis-ios-390x844-light.png`, `unamentis-ios-390x844-dark.png`

Every capture also measured `document.scrollWidth` against `clientWidth`: no
horizontal scroll at either size on either subject.

## The portrait, before and after

Both columns computed over the same reprojected manifest, so the comparison
isolates the grouping change.

| Subject | Group | Before | After |
|---|---|---|---|
| VS Code (571) | User interface | 5 | 18 |
| | Inner workings | 557 | 534 |
| | Services and APIs | 1 | 5 |
| | Data | 3 | 3 |
| | Tools and operations | 5 | 11 |
| unamentis-ios (165) | User interface | 80 | 129 |
| | Inner workings | 83 | 34 |
| | Data | 2 | 2 |

VS Code moves 13 components into User interface: the workbench subtree, which is
28% of mapped files. UnaMentis moves 49 neutral descendants of the `unamentis`
iOS client out of Inner workings. The repository root is deliberately not
allowed to speak for the tree, which is what stops UnaMentis (whose root is
typed `ios-client`) collapsing into a single area.

## Reprojection

Venv interpreter throughout, from copies of the stores in
`.testboard/stores/<subject>/index.db`. The canonical stores were never opened.

| Subject | Components | Files | Symbols | Relationships |
|---|---|---|---|---|
| VS Code, this run | 571 | 15,219 | 151,134 | 5,454 |
| VS Code, 2026-09-02 record | 571 | 15,204 | 151,134 | 5,454 |
| unamentis-ios, this run | 165 | 559 | 7,617 | 449 |
| unamentis-ios, canonical served bundle | 168 | 751 | 7,617 | 458 |

VS Code's file count moved by 15 (15,204 to 15,219) in the same direction and
for the same reason as UnaMentis's larger move: enumeration drift between the
canonical runs and current main. Symbols and relationships are unchanged.

**The UnaMentis file count difference predates this branch.** The reprojection
excludes the repository's committed `architecture/` directory as a generated
SysCorpus projection (198 files, reported by the analyzer as a note), which the
2026-08-30 canonical run counted as source. Nothing in this branch touches file
enumeration, coverage classification or component discovery:
`git diff main..HEAD --stat` is confined to `analyzer/derive/identity.py`,
`analyzer/derive/pipeline.py` (registration only),
`analyzer/project/pipeline.py` (the prune), `analyzer/project/human_views.py`,
`scripts/reorient.py`, `viewer/**`, `tests/**` and `docs/**`. It was not
reproduced against main's code in a separate checkout, so it is recorded as
unverified attribution rather than proven.

`scripts/reorient.py --check` exits 0 on both projections: the projection and
the script agree byte for byte.

## Verification

| Check | Result |
|---|---|
| `.venv-wt/bin/python -m pytest tests/ -q` | 2455 passed, 5 skipped, 1 xfailed. The 2026-09-02 record's known worktree-only failure (`test_pruned_directory_row_stands_in_for_its_contents`) did not occur |
| `.venv-wt/bin/python -m ruff check analyze.py analyzer/ scripts/ tests/` | All checks passed |
| `npx tsc --noEmit` | clean |
| `npx eslint src/` | clean |
| `npx vitest run` | 65 files, 664 tests, 0 failures, before and after. The task contracts anticipated 86 localStorage failures; the jsdom shim in `src/__tests__/setup.ts` means there are none, so the before-set and after-set are both empty |
| `scripts/golden-corpus.py check flask` | no drift |
| `scripts/golden-corpus.py check fastapi` | no drift |

**No golden baseline was refreshed, because none drifted.** The spec expected
the identity key to change the flask and fastapi baselines. It does not: the
projection diff (`scripts/projection-diff.py::diff_projections`) compares twelve
named sections (components, relationships, findings, coverage, inventory,
data_entities, entity_access, capabilities, concerns, enrichment, stats,
supply_chain) and the new top-level `identity` key is in none of them, and
`orientation.json` is not a golden artifact at all. That is a gap in the golden
corpus, not a clean bill of health for the identity pass; see the open items.

## Choices made where the spec left room

1. **Language shares count code languages only**, following the metrics pass's
   own rule that a SwiftUI app whose docs outweigh its Swift must read as swift.
   Unfiltered, VS Code would describe itself as written in TypeScript and JSON.
2. **A record whose component sits inside another record's component of the
   same kind folds into it** and hands over its evidence. Not in spec 2.1, whose
   dedupe is per component id. Without it, UnaMentis shows two identical "iOS
   app" chips (the root and the `unamentis` target) and VS Code shows two
   "Extensible by plug-ins".
3. **A root-attributed record whose evidence all lives in a subtree is weighed
   by that subtree**, not by the whole repository, so a side feature cannot
   outrank the product.
4. **`form_factors` stay in weight order per spec 2.1, while the statement reads
   its secondary clauses in detector order per spec 2.4.** The spec's required
   VS Code sentence is in detector order and its record ordering rule is by
   weight; both cannot hold at once. The visible consequence is that the chips
   and the sentence can list the same facts in different orders.
5. **UG-1's acceptance says the VS Code fixture yields its four kinds "in that
   order after weighting when all weights tie".** Weights do not tie on any real
   repository, so the test asserts the set and the ordering rule instead.
6. **`description_kind` is `interpreted` only when the component's description
   is the enriched one.** 114 of VS Code's 571 components carry `ai_enhance` and
   a description that came from a package manifest instead; those read
   `deterministic`.
7. **Viewer unit tests live in `viewer/src/__tests__/`**, the viewer's actual
   convention, not the `components/__tests__` path UG-4 named.
8. **The evidence panel sits under the chip row**, not floating beside its chip:
   an anchored 288px popover next to the fourth chip runs off a 390px phone.
9. **The disclosure summary reads "Interpreted summary" on both paths**, so the
   page keeps one vocabulary, and the claim caption reads "Repository claim",
   matching the deployment posture panel rather than the lowercase form in the
   spec's prose.
10. **The viewer's compatibility fallback keeps its old group labels.** It
    computes the old grouping, so relabelling it would put plain-language names
    on a different computation.

## Scope fences crossed, and why

- `tests/test_derive.py` gained one line and one comment (D12) to the enumerated
  parity differences. It is outside UG-1's `scope_allow` and is not in its
  `test_paths` either. The polyglot parity snapshot fails on any new top-level
  arch key, and that list exists precisely to record intended additions.
- `analyzer/project/pipeline.py` gained `prune_identity_against_corrections`.
  It is in UG-1's `scope_allow`, but the work was done at integration time.
- `demos/review-corrections/vscode.json` gained the subject-name entry. In
  UG-7's `scope_allow`.

## Open items

| # | Item | Bucket | Why it is open |
|---|---|---|---|
| 1 | "Inner workings" holds 94% of VS Code's components (58% of its files). The spec's 70% acceptance is not met | B | Ancestor inheritance is all spec 3.2 specifies and it does not get there. Reaching 70% needs a second rule, for example promoting `src/vs/editor` and `src/vs/platform` out of the default, which is a design decision, not an implementation gap |
| 2 | The identity pass reads component types one tier below the enrichment corrections that overrule them | A/C | `project.identity-prune` removes the wrong claims after the fact, but a record can still be ATTRIBUTED to a component whose type has since changed: VS Code's web-app record names `src/vs`, which was typed `web-client` at derive time and `module` after correction. Its evidence (an html entry) is independent of the type, so the claim holds and the attribution is stale |
| 3 | The golden corpus cannot see the identity key or the orientation sidecar | B | A regression in either would not drift flask or fastapi. Adding an `identity` section to `projection-diff.py` is the fix |
| 4 | CLOSED at owner review: the VS Code headline was five lines at 1440px and eleven at 390px | A | The name is now the title and the statement is a subtitle. Spec section 4's "the H2 carries identity.statement" is deliberately not followed to the letter: the H2 carries the subject, the statement sits under it as body text, and the analyzer composes the subject-free form so the browser does no string surgery |
| 5 | Two "Command-line tool" chips on VS Code | B | Both are evidenced (`cli/Cargo.toml [[bin]]` and a `bin` field in a language-server package). Honest, and arguably more than a reader needs |
| 6 | UnaMentis reads "unamentis-ios", not "UnaMentis" | B | Same cause as the VS Code name. No review correction was added, because the served demo's header already reads `unamentis-ios` and changing it was not asked for |
| 7 | UnaMentis reprojects to 559 files against the canonical 751 | C | Attributed to the generated-projection exclusion, not to this branch, and not proven against main's code in a separate checkout |
| 8 | `identity.languages` can carry a language whose share rounds to 0.00 | B | UnaMentis lists python at 0.0. Harmless today: the statement only reads the first two entries |
| 9 | UG-5, the README hero image | A/C | Not started, and deliberately so. It is optional and gated on UG-7. Neither canonical subject would show an image: VS Code's only non-badge README image is a remote github.com/user-attachments URL, which UG-5 specifies must render as a link and never be fetched, and UnaMentis's README carries no image at all. Building it now would re-open a green gate and make this record stale for no visible gain on either demo |
| 10 | The `.testboard/derived` collision | A | `scripts/assemble-serve.py` silently deletes whatever is at its overlay path. It should refuse to delete a directory holding a `manifest.json` it did not write |
| 11 | Two subjects assembled together share one viewer build, so they share one default theme | A | Only matters when two demos want different themes. Assembling each with its own build is the fix, at the cost of a build per subject |

## Cumulative token spend

One Opus session, no subagents. The harness's remaining-token counter went from
15,000,000 at the first message to about 14,490,000 at the end of the run, so
about **510,000 session tokens** across UG-1, UG-2, UG-4, UG-6 and UG-7. That is
against the plan's estimate of 1.05M to 1.2M for three Opus executors, one
Sonnet executor and a frontier orchestrator; executing all five contracts in one
session avoided the handoff cost the estimate assumed. Zero model spend in the
product: no enrichment call was made, and none of the new code can make one.

## Commands

```
# copy the stores, never open the canonical ones
cp /Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/index.db \
   .testboard/stores/vscode/index.db
cp /Volumes/Studio/dev/solution-explorer/.testboard/live/unamentis-ios-full-20260830-a5717bf/index.db \
   .testboard/stores/unamentis-ios/index.db

# reproject, venv interpreter only, NOT into .testboard/derived (assemble-serve owns that)
.venv-wt/bin/python analyze.py /Volumes/Studio/dev/.demo-corpus/vscode \
  --engine v2 --store .testboard/stores/vscode/index.db \
  --output .testboard/projections/vscode/architecture --split
.venv-wt/bin/python analyze.py /Volumes/Studio/dev/unamentis-ios \
  --engine v2 --store .testboard/stores/unamentis-ios/index.db \
  --output .testboard/projections/unamentis-ios/architecture --split

# the sidecar and the script must agree
.venv-wt/bin/python scripts/reorient.py .testboard/projections/vscode/architecture --check
.venv-wt/bin/python scripts/reorient.py .testboard/projections/unamentis-ios/architecture --check

# bundle and serve, away from the owner's 5175 and 5176
python3 scripts/assemble-serve.py vscode \
  --projection "$(pwd)/.testboard/projections/vscode/architecture" \
  --corrections demos/review-corrections/vscode.json
python3 scripts/assemble-serve.py unamentis-ios \
  --projection "$(pwd)/.testboard/projections/unamentis-ios/architecture" \
  --corrections demos/review-corrections/unamentis-ios.json --no-build
python3 -m http.server 5185 --bind 127.0.0.1 --directory "$(pwd)/.testboard/serve/vscode"
python3 -m http.server 5186 --bind 127.0.0.1 --directory "$(pwd)/.testboard/serve/unamentis-ios"

# crawl with THIS worktree's harness, reading the served projection off disk
cd viewer
CRAWL_BASE_URL=http://127.0.0.1:5185 CRAWL_PROFILE=quick \
  CRAWL_DATA_DIR="$(cd .. && pwd)/.testboard/serve/vscode/architecture" \
  npx playwright test -c tests/crawl/playwright.config.ts
cd .. && python3 scripts/crawl-report.py .testboard/runs/<run id>
```
