---
id: ug-1-identity-facts
work_class: delegated-primary
task_class: small-feature
tier: opus
model: claude-opus-5
effort: medium
attempts_max: 2
escalate_to: frontier
branch: wt/ui-gateway-option1
scope_allow: [analyzer/derive/identity.py, analyzer/derive/pipeline.py, analyzer/project/pipeline.py, tests/test_identity.py, tests/fixtures/identity/]
test_paths: [tests/test_human_views.py, tests/golden/**, viewer/tests/crawl/**]
verify_cmd: "cd /Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway && .venv-wt/bin/python -m pytest tests/test_identity.py tests/test_human_views.py tests/test_project_frontdoor.py -q && .venv-wt/bin/python -m ruff check analyze.py analyzer/ scripts/ tests/"
est_frontier_units: 60000
review_level: probation
---
## Objective
A new deterministic derive pass, `derive.identity`, that reads the repository's own markers through the store and writes `arch["identity"]` with form-factor records, the maintainers' first README paragraph, language shares and external services, exactly as SPEC-OPTION1-IDENTITY-FRONT-DOOR.md section 2 specifies. The key survives into `manifest.json` in split and monolithic projections. Done means: the fixtures in this contract produce the expected records with evidence, the VS Code-shaped fixture yields desktop-app (macOS, Windows, Linux), web-app, cli and plugin-host, and nothing fires without a file to point at.

## Context
Worktree: `/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway` (branch `wt/ui-gateway-option1`). Venv is installed at `.venv-wt`; always use `.venv-wt/bin/python`. The Homebrew `python3` has no tree-sitter and silently produces wrong results.

Read first: `docs/research/ui-gateway/SPEC-OPTION1-IDENTITY-FRONT-DOOR.md` sections 2 and 3.1. Then `analyzer/derive/pipeline.py` (`derive_all`, the isolator pattern, and where passes register), `analyzer/derive/context.py` (`Deriver`, `StoreView`, `StoreFS`, `StorePath.read_text`), `analyzer/derive/docs.py` (how README text is already captured on the root component's `docs.readme`), `analyzer/derive/flow.py` (a small pass in the house style), and `analyzer/project/pipeline.py` (how top-level arch keys reach `manifest.json`; confirm `identity` is carried, add it to whatever allow-list exists if one does).

The derive pass must read files only through `d.view.fs` / `StorePath` (cached content), never `open()` on disk. It runs after `derive.docs` and before `derive.capabilities`. Root README text: prefer the root component's `docs.readme` if already populated when the pass runs; otherwise read `README.md` via the store.

Marker details:
- `package.json`: look at `dependencies` and `devDependencies` for `electron`, `tauri`, `@tauri-apps/api`; `bin` for cli; `main`/`exports` for library; framework names for web-app (`next`, `nuxt`, `@sveltejs/kit`, `vite`, `react-scripts`). Record the line number of the matching key by scanning the file text for the key; if not findable, omit `line`.
- `product.json` at root: `darwinBundleIdentifier` → macos, `win32x64AppId` or `win32arm64AppId` → windows, `linuxIconName` → linux.
- `Cargo.toml`: `[[bin]]` tables, or a `src/main.rs` beside it → cli; `[lib]` → library.
- `pyproject.toml`: `[project.scripts]` → cli; `setup.py` with `console_scripts` → cli.
- Go: `go.mod` at root and `cmd/<name>/main.go` → one cli record per binary, cap 12, `truncated` when capped.
- Kubernetes manifests: any `.yaml`/`.yml` outside `node_modules`/vendored paths containing a line matching `^kind:\s*(Deployment|Service|StatefulSet|DaemonSet)` → server. Helm `Chart.yaml`, `*.tf` → infrastructure.
- `web-app` requires a `web-client` typed component plus an `.html` file whose path contains `/browser/` or that is `index.html` at that component's root; OR a root framework marker. VS Code's proof is `src/vs/code/browser/workbench/workbench.html` with component `src/vs/workbench` typed `web-client`; encode that shape in a fixture.
- `plugin-host`: three or more `package.json` under top-level `extensions/` or `plugins/` with `contributes` or `engines.vscode`.
- Component-type detectors use the component tree the earlier passes built (`d` holds components; see how `flow.py` iterates `CLIENT_TYPES`).

`weight`: mapped file count under the evidence component(s); root markers weigh the repo total. Sort by weight desc, then table order; cap 8.

Fixtures: build small in-memory or tmp-path repos through the same store loading path the existing derive tests use (look at how `tests/test_human_views.py` or the derive tests construct a `FactStore`; reuse the helper rather than inventing one). Required fixture shapes: (a) VS Code-shaped: root package.json with electron devDependency and no bin, product.json with the three platform keys, `extensions/a|b|c/package.json` with `contributes`, `cli/Cargo.toml` with `[[bin]]`, `src/vs/code/browser/workbench/workbench.html` and a component `src/vs/workbench` typed web-client; (b) iOS-shaped: an `ios-client` component and an Info.plist, plus a `watch-app` component; (c) Go-shaped: `go.mod` and `cmd/apiserver/main.go`, `cmd/kubelet/main.go`, plus a `Deployment` manifest; (d) library-shaped: pyproject with no scripts and nothing else; (e) empty: a repo with only source files and no manifests produces `identity` with empty `form_factors` and `statement`-relevant fields null, never an exception.

## Acceptance
- Every record has at least one evidence entry with a `file` that exists in the fixture. A test asserts this for all fixtures.
- Fixture (a) yields exactly desktop-app (platforms macos, windows, linux, `platforms_assumed: false`), web-app, cli, plugin-host, in that order after weighting when all weights tie (table order). Fixture (c) yields two cli records named by binary plus server. Fixture (d) yields only library. Fixture (e) yields no records and no gap.
- The README paragraph extraction skips headings, badge lines, HTML and lists, strips link markup, caps at 400 chars on a sentence boundary, and records the line number. A test uses the first 12 lines of the real VS Code README (copy them into the fixture) and asserts the paragraph starting "This repository (\"Code - OSS\") is where we (Microsoft) develop".
- `identity` is present at the top level of `manifest.json` for a split projection and of the monolithic JSON. A test proves it through the projection path, not by inspecting the arch dict.
- The pass is isolated: a raising detector records a gap under `derive.identity` and the run continues (follow the existing isolator idiom; a test monkeypatches one detector to raise).
- Determinism: two runs over the same fixture produce byte-identical `identity` JSON.
- No new dependency. No disk reads outside the store. `ruff` clean.
- Report, in the final message: the list of files changed, the verify command output tail, the golden-corpus check output for flask and fastapi (`.venv-wt/bin/python scripts/golden-corpus.py check flask` and `check fastapi`), and any place where the spec was ambiguous and what you chose.

## Out of scope
- Do not touch `analyzer/project/human_views.py` (UG-2 owns it) or the viewer.
- Do not refresh golden baselines; report the diff.
- Commit when the verify command is green, on `wt/ui-gateway-option1`, message starting with the task id. Never push.
- Do not change component typing in the scanner or roles pass.

## House conventions
- No em dashes or en dashes anywhere, in code comments, docstrings, tests or your report. Use commas or full stops.
- Docstrings explain why, briefly, in the voice of the existing derive passes.
- Tests are pytest functions with descriptive names; fixtures live under `tests/fixtures/identity/` if files are needed, else inline.
- Run the verify command before reporting. A report without its output is returned unread.
- Use `.venv-wt/bin/python`, never `python3`.
