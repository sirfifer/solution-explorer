---
id: ug-2-orientation-v1-identity
work_class: delegated-primary
task_class: small-feature
tier: opus
model: claude-opus-5
effort: medium
attempts_max: 2
escalate_to: frontier
branch: wt/ui-gateway-option1
scope_allow: [analyzer/project/human_views.py, tests/test_human_views.py, docs/front-door-prototype/orientation.v1.example.json]
test_paths: [tests/test_identity.py, tests/golden/**, viewer/tests/crawl/**]
verify_cmd: "cd /Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway && .venv-wt/bin/python -m pytest tests/test_human_views.py tests/test_identity.py tests/test_project_frontdoor.py tests/test_assemble_serve.py -q && .venv-wt/bin/python -m ruff check analyze.py analyzer/ scripts/ tests/"
est_frontier_units: 70000
review_level: probation
---
## Objective
`build_orientation` in `analyzer/project/human_views.py` emits the `identity` block with the composed plain-language statement, the portrait v2 (ancestor inheritance, plain labels, `share` and `representative` per node), the breadth-ranked default path with its reason, and the flow route's conditional label, exactly as SPEC-OPTION1-IDENTITY-FRONT-DOOR.md sections 2.4 and 3 specify. Done means the VS Code-shaped test produces the exact statement in the spec, the workbench subtree lands in the `experience` group, and the ranked tour is the broad one.

## Context
Worktree `/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway`, venv `.venv-wt/bin/python`. UG-1 has landed: `arch["identity"]` exists with the record shapes in spec section 2.1 to 2.3. Read the spec sections 2.4, 3.1, 3.2, 3.3 first, then `build_orientation`, `_group_for`, `_GROUP_META`, `_representative_rank` and `_has_flow_data` in `human_views.py`, and the existing tests in `tests/test_human_views.py` (the `_architecture()` helper is the fixture idiom; extend it, do not fork it).

Statement composition lives here, in a pure function `compose_identity_statement(identity: dict, name: str) -> Optional[str]`, so the viewer fallback can never disagree with it. Template rules are spec 2.4; platform display names are listed there. Article: "an" before a vowel sound of the label ("an iOS app"), "a" otherwise.

Portrait inheritance: walk the component tree, not the flat list; a neutral-typed component takes the group of its nearest non-neutral ancestor; the root itself is neutral. Keep the existing lone-service fold at 50+ components. Keep `_representative_rank` for choosing `stable_targets[0]`. `share` uses each component's own mapped file count summed per group over the total; the file count is `len(component["files"])` summed over the subtree only once per component (no double counting: sum own files per component, not subtree totals).

`representative.description_kind`: `interpreted` when the component has `ai_enhance` and its description equals or derives from the enriched summary; if you cannot distinguish reliably, treat a component with `ai_enhance` as interpreted and one without as deterministic, and say so in the report.

Tour breadth: for each tour, collect step evidence files (`steps[].evidence.file`), map each file to the component that lists it in `files` (build one index once), weight by that component's `len(files)`, divide by total mapped files. Ties by tour order. Emit `default_path.reason`.

Flow route: when `_has_flow_data` is false, label "How does the code fit together?" and target the ranked tour on `structure`; when true, keep "How does the core experience work?" and the flow lens. Keep id `flow`. Update the existing test `test_orientation_flow_route_names_a_lens_the_viewer_can_offer` for the label, not the id.

Update `docs/front-door-prototype/orientation.v1.example.json` to carry the new fields so the example stays a truthful contract.

## Acceptance
- A VS Code-shaped fixture (root with identity records for desktop-app [macos, windows, linux], web-app, cli, plugin-host; languages typescript 0.86, rust 0.11; no external services) yields `identity.statement` exactly: "Visual Studio Code is a desktop application for macOS, Windows and Linux, that also runs in a web browser, is driven from a terminal by a command-line tool, and is extended by plug-ins. It is written mostly in TypeScript, with Rust."
- An iOS-shaped fixture named "UnaMentis" (ios-app primary, watch-app secondary, swift 0.95) yields "UnaMentis is an iOS app, that also has a watchOS app. It is written mostly in Swift." No platform clause after a label that already names its platform (spec 2.4 rule 1). Adjust the spec's phrase table only by reporting; do not invent a nicer sentence.
- `identity` is null (and no exception) when `arch` has no identity key; the flow and portrait sections still build.
- Portrait: a fixture with `src/vs/workbench` typed `web-client` holding 20 neutral descendants puts all 21 in `experience`; a neutral sibling outside stays in `core`; a `screen` under a `module` under a `web-client` stays `experience` by its own type. `share` values sum to 1.00 ± 0.01 across nodes. Every node has `representative` with `id`, `name`, `description_kind`.
- Labels are the plain-language set in spec 3.2; ids unchanged.
- Default path: fixture with tour A (steps touching two components of 10 files) and tour B (five components of 500 files) selects B, `reason` names five components and the percentage; with no tours falls back to the organization question as today.
- Existing tests keep passing except the ones you deliberately update for labels, each update explained in the report.
- Determinism holds: the new `test_human_view_builders_are_deterministic_and_evidence_honest` coverage extends to identity and representatives.
- Report: files changed, verify output tail, and the output of `.venv-wt/bin/python scripts/reorient.py` on both real bundles if UG-6's script exists by then (paths: `.testboard/derived/vscode/architecture` and `.testboard/derived/unamentis-ios/architecture` in this worktree; if absent, say so).

## Out of scope
- Do not edit `analyzer/derive/**` (UG-1) or `viewer/**` (UG-4) or `scripts/**` (UG-6).
- Do not refresh golden baselines; report the golden check output.
- Commit when the verify command is green, on `wt/ui-gateway-option1`, message starting with the task id. Never push.
- Do not add enrichment or any model call.

## House conventions
- No em dashes or en dashes anywhere. Commas and full stops.
- Docstrings and comments explain why in the voice of the file (see the comments above `_group_for` and in the flow-route block).
- Keep `build_orientation` readable: extract helpers (`_portrait_nodes`, `_rank_tours`, `compose_identity_statement`) rather than growing the function.
- Run the verify command before reporting. Use `.venv-wt/bin/python`.
